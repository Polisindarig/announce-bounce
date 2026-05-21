"""Phase 7 — Robustness / Stress Tests.

Runs the FROZEN M0 strategy under different latency scenarios
to test sensitivity. Also documents bot architecture and design
choices for the thesis.

All tests use LISTING_SPOT only (filter_real_tier1_events).
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.backtest.engine import BacktestConfig, filter_real_tier1_events, run_backtest

logger = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_data():
    """Load events (full sample) and klines."""
    events = pd.read_parquet(DATA_DIR / "processed" / "events.parquet")
    events["published_at"] = pd.to_datetime(events["published_at"], utc=True)

    # Filter to REAL Tier 1 events (catalog + title verified)
    events = filter_real_tier1_events(events)
    logger.info("Real Tier 1 events: %d", len(events))

    # Collect needed pairs
    needed = {s + "USDT" for s in events["symbol"].dropna().unique()}
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

    logger.info("Loaded %d MEXC kline pairs (out of %d needed)", len(klines), len(needed))
    return events, klines


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    events, klines = load_data()

    if len(events) == 0:
        logger.error("No events found!")
        return

    # ── Latency sensitivity ──
    # Realistic scenarios: bot targets <5s, worst-case 30s.
    # Note: with 5-min bars, sub-300s latencies give identical results
    # (all fall within the same bar). This is a known limitation.
    latency_scenarios = [1, 3, 5, 10, 30]
    latency_results = {}

    logger.info("\n" + "=" * 60)
    logger.info("PHASE 7 — ROBUSTNESS: LATENCY SENSITIVITY")
    logger.info("=" * 60)

    for lat in latency_scenarios:
        logger.info("\nRunning latency=%ds ...", lat)
        config = BacktestConfig(
            initial_equity=10_000.0,
            fee_per_leg=0.001,
            slippage_bps=15,
            latency_seconds=float(lat),
            max_concurrent=3,
            max_same_asset=1,
            daily_loss_limit=0.05,
            model_variant="M0",
        )
        result = run_backtest(events, klines, config)
        s = result.summary
        latency_results[str(lat)] = s
        logger.info(
            "  lat=%ds → trades=%d, return=%+.2f%%, WR=%.1f%%, PF=%.2f, Sharpe=%.3f",
            lat, s["n_trades"], s["total_return_pct"], s["win_rate"],
            s["profit_factor"], s["sharpe_per_trade"],
        )

    # ── Fee sensitivity ──
    fee_scenarios = [0.0005, 0.001, 0.002]  # 5bps, 10bps, 20bps
    fee_results = {}

    logger.info("\n" + "=" * 60)
    logger.info("PHASE 7 — ROBUSTNESS: FEE SENSITIVITY")
    logger.info("=" * 60)

    for fee in fee_scenarios:
        logger.info("\nRunning fee=%.2f%% per leg ...", fee * 100)
        config = BacktestConfig(
            initial_equity=10_000.0,
            fee_per_leg=fee,
            slippage_bps=15,
            latency_seconds=30.0,
            max_concurrent=3,
            max_same_asset=1,
            daily_loss_limit=0.05,
            model_variant="M0",
        )
        result = run_backtest(events, klines, config)
        s = result.summary
        fee_results[str(fee)] = s
        logger.info(
            "  fee=%.2f%% → trades=%d, return=%+.2f%%, WR=%.1f%%, PF=%.2f",
            fee * 100, s["n_trades"], s["total_return_pct"], s["win_rate"],
            s["profit_factor"],
        )

    # ── Slippage sensitivity ──
    slippage_scenarios = [50, 100, 150, 200]  # bps
    slippage_results = {}

    logger.info("\n" + "=" * 60)
    logger.info("PHASE 7 — ROBUSTNESS: SLIPPAGE SENSITIVITY")
    logger.info("=" * 60)

    for slip in slippage_scenarios:
        logger.info("\nRunning slippage=%d bps ...", slip)
        config = BacktestConfig(
            initial_equity=10_000.0,
            fee_per_leg=0.001,
            slippage_bps=float(slip),
            latency_seconds=30.0,
            max_concurrent=3,
            max_same_asset=1,
            daily_loss_limit=0.05,
            model_variant="M0",
        )
        result = run_backtest(events, klines, config)
        s = result.summary
        slippage_results[str(slip)] = s
        logger.info(
            "  slip=%dbps → trades=%d, return=%+.2f%%, WR=%.1f%%, PF=%.2f",
            slip, s["n_trades"], s["total_return_pct"], s["win_rate"],
            s["profit_factor"],
        )

    # ── Build report ──
    report = {
        "phase": "Phase 7 — Robustness Tests",
        "strategy": "M0 (category-only, LISTING_SPOT only)",
        "note": "Full sample IS+OOS",
        "latency": latency_results,
        "latency_note": (
            "With 5-min bar resolution, latency scenarios below 300s (5 min) "
            "fall within the same bar, so the backtest cannot differentiate them. "
            "At 30s the entry may shift to the next bar for some trades. "
            "Target latency is 1-5 seconds (poll + classify + order). "
            "Literature (Ante 2019, Empirica 2024) confirms most of the pump "
            "occurs in the first 1-5 minutes. A tick-level backtest would "
            "reveal true latency sensitivity; this is a documented limitation."
        ),
        "target_latency": "< 5 seconds (scraper poll + classify + order submission)",
        "fee_sensitivity": fee_results,
        "slippage_sensitivity": slippage_results,
        "bot_design": {
            "scraper_poll_interval": "1-2 seconds (Binance CMS API)",
            "classification_time": "< 100ms (rule-based, no ML in hot path)",
            "order_submission": "< 500ms (MEXC REST API market order)",
            "total_target": "< 3 seconds end-to-end",
        },
    }

    out_path = DATA_DIR / "processed" / "phase7_robustness.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("\nSaved: %s", out_path)

    # ── Print summary table ──
    print("\n" + "=" * 70)
    print("ROBUSTNESS SUMMARY")
    print("=" * 70)

    print("\nLatency sensitivity:")
    print(f"  {'Latency':>8}  {'Trades':>6}  {'Return%':>8}  {'WinRate':>7}  {'PF':>5}  {'Sharpe':>6}  {'MaxDD%':>6}")
    for lat in latency_scenarios:
        s = latency_results[str(lat)]
        print(
            f"  {lat:>6}s  {s['n_trades']:>6}  {s['total_return_pct']:>+7.2f}%  "
            f"{s['win_rate']:>6.1f}%  {s['profit_factor']:>5.2f}  "
            f"{s['sharpe_per_trade']:>6.3f}  {s['max_drawdown_pct']:>5.2f}%"
        )

    print("\nFee sensitivity:")
    print(f"  {'Fee/leg':>8}  {'Trades':>6}  {'Return%':>8}  {'WinRate':>7}  {'PF':>5}")
    for fee in fee_scenarios:
        s = fee_results[str(fee)]
        print(
            f"  {fee*100:>6.2f}%  {s['n_trades']:>6}  {s['total_return_pct']:>+7.2f}%  "
            f"{s['win_rate']:>6.1f}%  {s['profit_factor']:>5.2f}"
        )

    print("\nSlippage sensitivity:")
    print(f"  {'Slippage':>8}  {'Trades':>6}  {'Return%':>8}  {'WinRate':>7}  {'PF':>5}")
    for slip in slippage_scenarios:
        s = slippage_results[str(slip)]
        print(
            f"  {slip:>5}bps  {s['n_trades']:>6}  {s['total_return_pct']:>+7.2f}%  "
            f"{s['win_rate']:>6.1f}%  {s['profit_factor']:>5.2f}"
        )


if __name__ == "__main__":
    main()
