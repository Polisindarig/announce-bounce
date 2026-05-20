"""Event-driven backtester with bar-by-bar TP/SL/time-stop simulation.

Processes events chronologically, opens trades via decision_engine, then
walks forward through 5-minute OHLCV bars checking exit conditions:

Exit priority (first match per bar):
    1. Delisting override — forced market sell
    2. TP hit  — bar.high ≥ entry × (1 + TP)  → fill at TP level
    3. SL hit  — bar.low  ≤ entry × (1 - SL)  → fill at SL level
    4. If both trigger same bar → pessimistic: SL taken (pre-registered)
    5. Time-stop — close at bar close after horizon expires

Execution model:
    - Market order at t₀ + latency
    - Fee: 0.10% taker per leg (0.20% round-trip)
    - Slippage: tier-based (see project plan §0.5)
    - LISTING_SPOT on MEXC, others on Binance

Usage:
    python -m src.backtest.engine
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


# ── Data structures ────────────────────────────────────────────────────────


@dataclass
class Trade:
    trade_id: int
    symbol: str
    category: str
    venue: str
    direction: str

    entry_time: datetime
    entry_price: float
    notional: float
    size_units: float

    tp_price: float
    sl_price: float
    time_stop_at: datetime

    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None

    fee_entry: float = 0.0
    fee_exit: float = 0.0
    slippage_entry: float = 0.0
    slippage_exit: float = 0.0

    pnl_gross: float = 0.0
    pnl_net: float = 0.0
    return_pct: float = 0.0
    duration_minutes: float = 0.0


@dataclass
class BacktestConfig:
    initial_equity: float = 10_000.0
    fee_per_leg: float = 0.001        # 0.10% taker
    slippage_bps: float = 15          # basis points (default mid-tier)
    latency_seconds: float = 30.0     # detection + execution latency
    max_concurrent: int = 3
    max_same_asset: int = 1
    daily_loss_limit: float = 0.05    # -5% of equity → halt
    model_variant: str = "M0"


@dataclass
class BacktestResult:
    config: dict
    trades: list[dict]
    equity_curve: list[dict]
    summary: dict


# ── Core engine ────────────────────────────────────────────────────────────


def _slippage_for_venue(venue: str, category: str, slippage_bps: float) -> float:
    """Return slippage as a fraction.

    Listing-spot first 5 minutes: 100 bps (1%).
    Otherwise: configured tier-based bps.
    """
    if category == "LISTING_SPOT":
        return 100 / 10_000  # 1% for new listings (thin book)
    return slippage_bps / 10_000


def run_backtest(
    events: pd.DataFrame,
    klines: dict[str, pd.DataFrame],
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Run bar-by-bar backtest over events + kline data.

    Parameters
    ----------
    events : DataFrame
        Must have: title, catalog_name, symbol, published_at, event_category
    klines : dict
        {pair: DataFrame with columns [open_time, open, high, low, close, volume]}
        5-minute bars, sorted by open_time.
    config : BacktestConfig
        Backtest parameters.
    """
    from src.sentiment.category_classifier import classify
    from src.sentiment.sentiment_scorer import score
    from src.strategy.decision_engine import Direction, Venue, decide

    if config is None:
        config = BacktestConfig()

    # Sort events by time
    events = events.sort_values("published_at").copy()
    events["published_at"] = pd.to_datetime(events["published_at"], utc=True)

    equity = config.initial_equity
    peak_equity = equity
    open_trades: list[Trade] = []
    closed_trades: list[Trade] = []
    equity_curve: list[dict] = [{"time": str(events["published_at"].iloc[0]), "equity": equity}]
    trade_counter = 0
    daily_pnl: dict[str, float] = {}  # date_str → cumulative pnl

    for _, event in events.iterrows():
        t_announcement = event["published_at"]
        title = str(event.get("title", ""))
        catalog = str(event.get("catalog_name", "")) if pd.notna(event.get("catalog_name")) else None
        symbol = str(event.get("symbol", ""))
        ann_id = str(event.get("announcement_id", ""))

        # Classify & decide
        cat, conf = classify(title, "", catalog_name=catalog)
        sent = score(title, "", category=cat.value)
        decision = decide(
            ann_id, cat.value, sent, symbol,
            t_announcement.to_pydatetime(),
            model_variant=config.model_variant,
            account_equity=equity,
        )

        # Check forced exit for open positions
        from src.strategy.decision_engine import check_forced_exit
        for trade in list(open_trades):
            if check_forced_exit(cat.value, trade.symbol) and trade.symbol == symbol:
                # Force exit at next available price
                pair = trade.symbol + "USDT"
                if pair in klines:
                    kl = klines[pair]
                    mask = kl["open_time"] >= t_announcement
                    if mask.any():
                        exit_bar = kl[mask].iloc[0]
                        _close_trade(
                            trade, exit_bar["open_time"], float(exit_bar["open"]),
                            "delisting_override", config.fee_per_leg,
                            _slippage_for_venue(trade.venue, trade.category, config.slippage_bps),
                        )
                        equity += trade.pnl_net
                        closed_trades.append(trade)
                        open_trades.remove(trade)

        if decision.direction == Direction.SKIP:
            continue

        # ── Position limits ──
        if len(open_trades) >= config.max_concurrent:
            continue
        if sum(1 for t in open_trades if t.symbol == symbol) >= config.max_same_asset:
            continue

        # ── Daily loss limit ──
        day_key = t_announcement.strftime("%Y-%m-%d")
        if daily_pnl.get(day_key, 0) / max(equity, 1) < -config.daily_loss_limit:
            continue

        # ── Find entry bar (t_announcement + latency) ──
        pair = symbol + "USDT"
        if pair not in klines:
            continue

        kl = klines[pair]
        t_entry = t_announcement + timedelta(seconds=config.latency_seconds)
        entry_mask = kl["open_time"] >= t_entry
        if not entry_mask.any():
            continue

        entry_bar = kl[entry_mask].iloc[0]
        entry_price = float(entry_bar["open"])
        if entry_price <= 0:
            continue

        # Apply slippage to entry (buy → price goes up)
        slip = _slippage_for_venue(decision.venue.value, cat.value, config.slippage_bps)
        entry_price_adj = entry_price * (1 + slip)

        # Position sizing
        size_pct = decision.size_pct_equity
        notional = equity * size_pct
        size_units = notional / entry_price_adj
        fee_entry = notional * config.fee_per_leg

        # TP/SL prices
        tp_price = entry_price_adj * (1 + decision.take_profit_pct)
        sl_price = entry_price_adj * (1 - decision.stop_loss_pct)
        time_stop_at = t_entry + decision.time_stop

        trade_counter += 1
        trade = Trade(
            trade_id=trade_counter,
            symbol=symbol,
            category=cat.value,
            venue=decision.venue.value,
            direction=decision.direction.value,
            entry_time=entry_bar["open_time"],
            entry_price=entry_price_adj,
            notional=notional,
            size_units=size_units,
            tp_price=tp_price,
            sl_price=sl_price,
            time_stop_at=time_stop_at,
            fee_entry=fee_entry,
        )

        # ── Walk forward through bars to find exit ──
        future_bars = kl[kl["open_time"] > entry_bar["open_time"]]

        for _, bar in future_bars.iterrows():
            bar_time = bar["open_time"]
            bar_high = float(bar["high"])
            bar_low = float(bar["low"])
            bar_close = float(bar["close"])

            tp_hit = bar_high >= tp_price
            sl_hit = bar_low <= sl_price
            time_expired = bar_time >= time_stop_at

            if tp_hit and sl_hit:
                # Pessimistic: SL taken (pre-registered convention)
                _close_trade(trade, bar_time, sl_price, "sl_hit_pessimistic",
                             config.fee_per_leg, slip)
                break
            elif sl_hit:
                _close_trade(trade, bar_time, sl_price, "sl_hit",
                             config.fee_per_leg, slip)
                break
            elif tp_hit:
                _close_trade(trade, bar_time, tp_price, "tp_hit",
                             config.fee_per_leg, slip)
                break
            elif time_expired:
                _close_trade(trade, bar_time, bar_close, "time_stop",
                             config.fee_per_leg, slip)
                break

        # If no exit found (ran out of kline data), close at last bar
        if trade.exit_time is None and len(future_bars) > 0:
            last_bar = future_bars.iloc[-1]
            _close_trade(trade, last_bar["open_time"], float(last_bar["close"]),
                         "data_end", config.fee_per_leg, slip)

        if trade.exit_time is not None:
            equity += trade.pnl_net
            daily_pnl[day_key] = daily_pnl.get(day_key, 0) + trade.pnl_net
            peak_equity = max(peak_equity, equity)
            closed_trades.append(trade)
            equity_curve.append({"time": str(trade.exit_time), "equity": equity})
        else:
            # No kline data at all — can't trade
            pass

    # ── Summary metrics ──
    summary = _compute_summary(closed_trades, config.initial_equity, equity, peak_equity)

    return BacktestResult(
        config=asdict(config) if hasattr(config, "__dataclass_fields__") else {},
        trades=[asdict(t) for t in closed_trades],
        equity_curve=equity_curve,
        summary=summary,
    )


def _close_trade(
    trade: Trade,
    exit_time,
    exit_price: float,
    reason: str,
    fee_per_leg: float,
    slippage: float,
) -> None:
    """Fill exit fields on a Trade."""
    # Slippage on exit (sell → price goes down)
    exit_price_adj = exit_price * (1 - slippage)
    fee_exit = trade.size_units * exit_price_adj * fee_per_leg

    trade.exit_time = exit_time
    trade.exit_price = exit_price_adj
    trade.exit_reason = reason
    trade.fee_exit = fee_exit
    trade.slippage_entry = slippage
    trade.slippage_exit = slippage
    trade.pnl_gross = (exit_price_adj - trade.entry_price) * trade.size_units
    trade.pnl_net = trade.pnl_gross - trade.fee_entry - fee_exit
    trade.return_pct = trade.pnl_net / trade.notional if trade.notional > 0 else 0
    trade.duration_minutes = (
        (pd.Timestamp(exit_time) - pd.Timestamp(trade.entry_time)).total_seconds() / 60
    )


def _compute_summary(
    trades: list[Trade],
    initial_equity: float,
    final_equity: float,
    peak_equity: float,
) -> dict:
    """Compute headline metrics from closed trades."""
    if not trades:
        return {"n_trades": 0, "error": "no trades executed"}

    returns = np.array([t.return_pct for t in trades])
    pnls = np.array([t.pnl_net for t in trades])
    durations = np.array([t.duration_minutes for t in trades])

    winners = returns[returns > 0]
    losers = returns[returns < 0]

    total_return = (final_equity - initial_equity) / initial_equity
    max_dd = (peak_equity - final_equity) / peak_equity if peak_equity > 0 else 0

    # Sharpe (per-trade, annualized assuming ~250 trades/year)
    sharpe = float(returns.mean() / returns.std(ddof=1)) if len(returns) > 1 and returns.std(ddof=1) > 0 else 0

    # Profit factor
    gross_profit = float(pnls[pnls > 0].sum()) if (pnls > 0).any() else 0
    gross_loss = float(abs(pnls[pnls < 0].sum())) if (pnls < 0).any() else 0.01
    profit_factor = gross_profit / gross_loss

    # By category
    cat_stats = {}
    for cat in set(t.category for t in trades):
        cat_trades = [t for t in trades if t.category == cat]
        cat_rets = np.array([t.return_pct for t in cat_trades])
        cat_stats[cat] = {
            "n": len(cat_trades),
            "mean_return": float(cat_rets.mean()),
            "win_rate": float((cat_rets > 0).sum() / len(cat_rets)),
            "total_pnl": float(sum(t.pnl_net for t in cat_trades)),
        }

    # By exit reason
    exit_stats = {}
    for reason in set(t.exit_reason for t in trades if t.exit_reason):
        r_trades = [t for t in trades if t.exit_reason == reason]
        r_rets = np.array([t.return_pct for t in r_trades])
        exit_stats[reason] = {
            "n": len(r_trades),
            "mean_return": float(r_rets.mean()),
        }

    return {
        "n_trades": len(trades),
        "initial_equity": initial_equity,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "win_rate": round(float(len(winners) / len(returns)) * 100, 1),
        "avg_win_pct": round(float(winners.mean()) * 100, 2) if len(winners) > 0 else 0,
        "avg_loss_pct": round(float(losers.mean()) * 100, 2) if len(losers) > 0 else 0,
        "profit_factor": round(profit_factor, 2),
        "sharpe_per_trade": round(sharpe, 3),
        "avg_duration_min": round(float(durations.mean()), 1),
        "by_category": cat_stats,
        "by_exit_reason": exit_stats,
    }


# ── CLI ────────────────────────────────────────────────────────────────────


def main():
    """Run backtest on available data."""
    import glob
    import os

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Load events — pre-filter to Tier 1 categories for speed
    events_path = DATA_DIR / "processed" / "events.parquet"
    logger.info("Loading events from %s", events_path)
    events = pd.read_parquet(events_path)

    tier1_cats = {"LISTING_SPOT", "LISTING_FUTURES", "LAUNCHPOOL_LAUNCHPAD", "STAKING_EARN"}
    events = events[events["event_category"].isin(tier1_cats)].copy()
    events = events.drop_duplicates(subset=["symbol", "published_at"])
    logger.info("Filtered to %d Tier 1 events", len(events))

    # Collect needed pairs
    needed_pairs = set(events["symbol"].dropna().unique())
    needed_pairs = {s + "USDT" for s in needed_pairs}
    logger.info("Need klines for %d unique pairs", len(needed_pairs))

    # Load klines — only pairs we actually need
    klines: dict[str, pd.DataFrame] = {}

    # Binance klines
    for f in glob.glob(str(DATA_DIR / "raw" / "klines" / "*.parquet")):
        pair = os.path.basename(f).replace(".parquet", "")
        if pair not in needed_pairs:
            continue
        df = pd.read_parquet(f)
        if "open_time" in df.columns:
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
            df = df.sort_values("open_time")
            klines[pair] = df

    # MEXC klines (for LISTING_SPOT)
    for f in glob.glob(str(DATA_DIR / "raw" / "mexc_klines_5m_from_2025-06" / "*.parquet")):
        pair = os.path.basename(f).replace(".parquet", "")
        if pair not in needed_pairs:
            continue
        df = pd.read_parquet(f)
        if "open_time" in df.columns:
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
            df = df.sort_values("open_time")
            if pair not in klines:
                klines[pair] = df

    logger.info("Loaded %d kline pairs", len(klines))

    # Run M0
    logger.info("\n=== Running M0 (category-only) backtest ===")
    config_m0 = BacktestConfig(model_variant="M0")
    result_m0 = run_backtest(events, klines, config_m0)

    # Run M1
    logger.info("\n=== Running M1 (category + sentiment) backtest ===")
    config_m1 = BacktestConfig(model_variant="M1")
    result_m1 = run_backtest(events, klines, config_m1)

    # Save results
    for label, result in [("m0", result_m0), ("m1", result_m1)]:
        out_path = DATA_DIR / "processed" / f"backtest_{label}_result.json"
        with open(out_path, "w") as f:
            json.dump({"summary": result.summary, "config": result.config,
                        "n_trades_detail": len(result.trades)},
                       f, indent=2, default=str)
        logger.info("Saved: %s", out_path)

    # Print comparison
    print("\n" + "=" * 70)
    print("BACKTEST COMPARISON: M0 vs M1")
    print("=" * 70)
    for label, r in [("M0", result_m0), ("M1", result_m1)]:
        s = r.summary
        print(f"\n{label}:")
        print(f"  Trades:       {s['n_trades']}")
        print(f"  Total return: {s['total_return_pct']:+.2f}%")
        print(f"  Win rate:     {s['win_rate']:.1f}%")
        print(f"  Profit factor:{s['profit_factor']:.2f}")
        print(f"  Sharpe/trade: {s['sharpe_per_trade']:.3f}")
        print(f"  Max DD:       {s['max_drawdown_pct']:.2f}%")
        print(f"  Avg duration: {s['avg_duration_min']:.0f} min")
        if s.get("by_category"):
            print("  By category:")
            for cat, cs in s["by_category"].items():
                print(f"    {cat}: n={cs['n']}, return={cs['mean_return']:+.2%}, wr={cs['win_rate']:.0%}")
        if s.get("by_exit_reason"):
            print("  By exit reason:")
            for reason, rs in s["by_exit_reason"].items():
                print(f"    {reason}: n={rs['n']}, return={rs['mean_return']:+.2%}")


if __name__ == "__main__":
    main()
