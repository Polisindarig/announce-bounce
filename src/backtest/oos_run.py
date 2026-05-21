"""Phase 6 — Out-of-Sample Run (HEADLINE RESULT).

Runs the FROZEN strategy exactly once on the OOS window.
No parameter tuning, no re-calibration. One shot.

If OOS Sharpe ≤ 0: document honestly as negative result.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.backtest.engine import BacktestConfig, filter_real_tier1_events, run_backtest

logger = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_data():
    """Load events (OOS only) and klines."""
    import yaml

    # Load window config
    with open(DATA_DIR.parent / "config" / "data_window.yaml") as f:
        window = yaml.safe_load(f)

    oos_start = pd.Timestamp(window["oos_start"], tz="UTC")
    oos_end = pd.Timestamp(window["oos_end"], tz="UTC")

    # Events — OOS only
    events = pd.read_parquet(DATA_DIR / "processed" / "events.parquet")
    events["published_at"] = pd.to_datetime(events["published_at"], utc=True)
    oos_events = events[
        (events["published_at"] >= oos_start) & (events["published_at"] <= oos_end)
    ].copy()

    # Filter to REAL Tier 1 events (catalog + title verified)
    oos_events = filter_real_tier1_events(oos_events)

    logger.info("OOS window: %s → %s", oos_start.date(), oos_end.date())
    logger.info("OOS real Tier 1 events: %d", len(oos_events))
    for cat in oos_events["event_category"].unique():
        n = len(oos_events[oos_events["event_category"] == cat])
        logger.info("  %s: %d", cat, n)

    # Load klines (only needed pairs)
    needed = {s + "USDT" for s in oos_events["symbol"].dropna().unique()}
    klines: dict[str, pd.DataFrame] = {}

    # MEXC klines — 5-min bars first, then 1h CryptoCompare fallback
    for f in glob.glob(str(DATA_DIR / "raw" / "mexc_klines_5m_from_2025-06" / "*.parquet")):
        pair = os.path.basename(f).replace(".parquet", "")
        if pair not in needed:
            continue
        df = pd.read_parquet(f)
        if "open_time" in df.columns:
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
            klines[pair] = df.sort_values("open_time")

    # Codex MEXC klines (actual MEXC API data, 60m/5m/1m)
    codex_dir = DATA_DIR / "raw" / "mexc_klines_codex"
    if codex_dir.exists():
        for f in glob.glob(str(codex_dir / "*.parquet")):
            pair = os.path.basename(f).replace(".parquet", "")
            if pair not in needed or pair in klines:
                continue
            df = pd.read_parquet(f)
            if "open_time" in df.columns:
                df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
                klines[pair] = df.sort_values("open_time")

    # 1h CryptoCompare klines for coins still missing
    cc_dir = DATA_DIR / "raw" / "mexc_klines_1h_cryptocompare"
    if cc_dir.exists():
        for f in glob.glob(str(cc_dir / "*.parquet")):
            pair = os.path.basename(f).replace(".parquet", "")
            if pair not in needed or pair in klines:
                continue
            df = pd.read_parquet(f)
            if "open_time" in df.columns:
                df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
                klines[pair] = df.sort_values("open_time")

    logger.info("Loaded %d MEXC kline pairs for OOS (out of %d needed)", len(klines), len(needed))
    return oos_events, klines, window


def bootstrap_sharpe_ci(returns: np.ndarray, n_boot: int = 10_000, ci: float = 0.95):
    """Bootstrap CI for Sharpe ratio."""
    rng = np.random.default_rng(42)
    n = len(returns)
    boot_sharpes = []
    for _ in range(n_boot):
        sample = returns[rng.integers(0, n, n)]
        std = sample.std(ddof=1)
        if std > 0:
            boot_sharpes.append(sample.mean() / std)
        else:
            boot_sharpes.append(0)
    boot_sharpes = np.array(boot_sharpes)
    alpha = (1 - ci) / 2
    return float(np.percentile(boot_sharpes, alpha * 100)), float(np.percentile(boot_sharpes, (1 - alpha) * 100))


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    oos_events, klines, window = load_data()

    if len(oos_events) == 0:
        logger.error("No OOS events found!")
        return

    # ── FROZEN strategy, one run ──
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 6 — OUT-OF-SAMPLE RUN (HEADLINE RESULT)")
    logger.info("Strategy: FROZEN M0 (category-only, no sentiment)")
    logger.info("=" * 60)

    config = BacktestConfig(
        initial_equity=10_000.0,
        fee_per_leg=0.001,
        slippage_bps=15,
        latency_seconds=30.0,
        max_concurrent=3,
        max_same_asset=1,
        daily_loss_limit=0.05,
        model_variant="M0",
    )

    result = run_backtest(oos_events, klines, config)
    s = result.summary

    # ── Bootstrap CI on returns ──
    returns = np.array([t["return_pct"] for t in result.trades])
    if len(returns) > 5:
        sharpe_lo, sharpe_hi = bootstrap_sharpe_ci(returns)
        t_stat, t_pval = stats.ttest_1samp(returns, popmean=0.0)
    else:
        sharpe_lo = sharpe_hi = t_stat = t_pval = None

    # ── Baselines ──
    # B2: BTC buy-and-hold over OOS window
    btc_ret = None
    if "BTCUSDT" in klines:
        btc = klines["BTCUSDT"]
        oos_start = pd.Timestamp(window["oos_start"], tz="UTC")
        oos_end = pd.Timestamp(window["oos_end"], tz="UTC")
        btc_oos = btc[(btc["open_time"] >= oos_start) & (btc["open_time"] <= oos_end)]
        if len(btc_oos) > 1:
            btc_ret = (float(btc_oos.iloc[-1]["close"]) - float(btc_oos.iloc[0]["open"])) / float(btc_oos.iloc[0]["open"])

    # ── Build OOS report ──
    oos_report = {
        "phase": "Phase 6 — Model Evaluation (Out-of-Sample)",
        "window": {
            "oos_start": window["oos_start"],
            "oos_end": window["oos_end"],
        },
        "strategy": "M0 (category-only, frozen from IS calibration)",
        "config": {
            "initial_equity": config.initial_equity,
            "fee_per_leg": config.fee_per_leg,
            "slippage_bps": config.slippage_bps,
            "latency_seconds": config.latency_seconds,
        },
        "summary": s,
        "statistical_tests": {
            "t_test_mean_return": {
                "t_stat": float(t_stat) if t_stat is not None else None,
                "p_value": float(t_pval) if t_pval is not None else None,
                "h0": "mean per-trade return = 0",
            },
            "bootstrap_sharpe_95ci": {
                "lower": sharpe_lo,
                "upper": sharpe_hi,
                "n_bootstrap": 10_000,
            },
        },
        "baselines": {
            "btc_buy_hold_return": round(btc_ret * 100, 2) if btc_ret is not None else None,
        },
        "trades": result.trades,
        "equity_curve": result.equity_curve,
    }

    out_path = DATA_DIR / "processed" / "phase6_oos_result.json"
    with open(out_path, "w") as f:
        json.dump(oos_report, f, indent=2, default=str)
    logger.info("Saved: %s", out_path)

    # ── Print headline ──
    print("\n" + "=" * 60)
    print("OOS HEADLINE RESULT")
    print("=" * 60)
    print(f"  Window:         {window['oos_start']} → {window['oos_end']}")
    print(f"  Trades:         {s['n_trades']}")
    print(f"  Total return:   {s['total_return_pct']:+.2f}%")
    print(f"  Win rate:       {s['win_rate']:.1f}%")
    print(f"  Profit factor:  {s['profit_factor']:.2f}")
    print(f"  Sharpe/trade:   {s['sharpe_per_trade']:.3f}", end="")
    if sharpe_lo is not None:
        print(f"  (95% CI: [{sharpe_lo:.3f}, {sharpe_hi:.3f}])")
    else:
        print()
    print(f"  Max DD:         {s['max_drawdown_pct']:.2f}%")
    print(f"  Avg duration:   {s['avg_duration_min']:.0f} min")

    if t_pval is not None:
        sig = "***" if t_pval < 0.001 else "**" if t_pval < 0.01 else "*" if t_pval < 0.05 else "n.s."
        print(f"  t-test (μ=0):   t={t_stat:.2f}, p={t_pval:.4f} {sig}")

    if btc_ret is not None:
        print(f"\n  BTC buy-hold:   {btc_ret*100:+.2f}%")
        print(f"  Strategy alpha: {s['total_return_pct'] - btc_ret*100:+.2f}% vs BTC")

    if s.get("by_category"):
        print("\n  By category:")
        for cat, cs in s["by_category"].items():
            print(f"    {cat}: n={cs['n']}, return={cs['mean_return']:+.2%}, wr={cs['win_rate']:.0%}, pnl=${cs['total_pnl']:.2f}")

    if s.get("by_exit_reason"):
        print("\n  By exit:")
        for reason, rs in s["by_exit_reason"].items():
            print(f"    {reason}: n={rs['n']}, return={rs['mean_return']:+.2%}")

    # Verdict
    print("\n" + "-" * 60)
    if s["n_trades"] == 0:
        print("VERDICT: No trades in OOS window.")
    elif s.get("sharpe_per_trade", 0) > 0:
        print("VERDICT: POSITIVE — strategy shows positive edge in OOS.")
    else:
        print("VERDICT: NEGATIVE — strategy does not show edge in OOS.")
        print("Document honestly. Do not re-tune.")


if __name__ == "__main__":
    main()
