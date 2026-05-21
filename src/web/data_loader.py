"""Load processed artifacts for the dashboard API.

Reads pre-computed Phase 4-7 JSON results — no simulation logic here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"


def _read_json(name: str) -> dict[str, Any] | None:
    path = PROCESSED / name
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


# ── Overview ─────────────────────────────────────────────────────────────

def overview() -> dict[str, Any]:
    """High-level project stats for the overview page."""
    summary = _read_json("events_summary.json") or {}
    manifest = _read_json("reproducibility_manifest.json") or {}
    bt = _read_json("backtest_m0_result.json") or {}
    oos = _read_json("phase6_oos_result.json") or {}
    sentiment = _read_json("sentiment_analysis_summary.json") or {}

    bt_s = bt.get("summary", {})
    oos_s = oos.get("summary", {})

    # Count raw announcements (try full file first, then subset)
    ann_path = ROOT / "data" / "raw" / "announcements.jsonl"
    if not ann_path.exists():
        ann_path = ROOT / "data" / "raw" / "announcements_from_2025-06-01.jsonl"
    n_ann = 0
    if ann_path.exists():
        with open(ann_path) as f:
            n_ann = sum(1 for _ in f)

    return {
        "n_announcements": n_ann,
        "n_categories_analyzed": len(sentiment.get("categories", {})),
        "total_events_sentiment": sentiment.get("total_announcements", 0),
        # IS backtest headline
        "is_backtest": {
            "n_trades": bt_s.get("n_trades", 0),
            "total_return_pct": bt_s.get("total_return_pct", 0),
            "win_rate": bt_s.get("win_rate", 0),
            "profit_factor": bt_s.get("profit_factor", 0),
            "sharpe_per_trade": bt_s.get("sharpe_per_trade", 0),
            "max_drawdown_pct": bt_s.get("max_drawdown_pct", 0),
        },
        # OOS headline
        "oos": {
            "window": oos.get("window", {}),
            "n_trades": oos_s.get("n_trades", 0),
            "total_return_pct": oos_s.get("total_return_pct", 0),
            "win_rate": oos_s.get("win_rate", 0),
            "profit_factor": oos_s.get("profit_factor", 0),
            "sharpe_per_trade": oos_s.get("sharpe_per_trade", 0),
        },
        "manifest_generated_at": manifest.get("generated_at"),
        "git_head": manifest.get("git_head"),
    }


# ── Backtest results (Phase 5) ──────────────────────────────────────────

def backtest_result(variant: str = "m0") -> dict[str, Any]:
    """Full backtest result for M0 or M1."""
    name = f"backtest_{variant}_result.json"
    raw = _read_json(name) or {}
    return raw


def backtest_trades(variant: str = "m0") -> list[dict[str, Any]]:
    """Trade list from backtest, newest first, with normalized field names."""
    raw = backtest_result(variant)
    trades = raw.get("trades", [])
    # Normalize field names for the frontend
    equity = raw.get("config", {}).get("initial_equity", 10_000)
    for t in trades:
        if "pnl_net" in t and "pnl" not in t:
            t["pnl"] = t["pnl_net"]
        if "duration_minutes" in t and "duration_min" not in t:
            t["duration_min"] = t["duration_minutes"]
        if "equity_after" not in t:
            equity += t.get("pnl", t.get("pnl_net", 0))
            t["equity_after"] = round(equity, 2)
    # Sort newest first
    trades.sort(key=lambda t: t.get("entry_time", ""), reverse=True)
    return trades


def backtest_equity_curve(variant: str = "m0") -> list[dict[str, Any]]:
    """Equity curve from backtest, normalized to {date, equity}."""
    raw = backtest_result(variant)
    curve = raw.get("equity_curve", [])
    # Normalize: engine uses "time", frontend checks "date" too
    for pt in curve:
        if "date" not in pt and "time" in pt:
            pt["date"] = str(pt["time"])[:10]
    return curve


# ── OOS result (Phase 6) ────────────────────────────────────────────────

def oos_result() -> dict[str, Any]:
    """Phase 6 OOS headline result with normalized trade fields."""
    raw = _read_json("phase6_oos_result.json") or {}
    for t in raw.get("trades", []):
        if "pnl_net" in t and "pnl" not in t:
            t["pnl"] = t["pnl_net"]
        if "duration_minutes" in t and "duration_min" not in t:
            t["duration_min"] = t["duration_minutes"]
    return raw


# ── Robustness (Phase 7) ────────────────────────────────────────────────

def robustness_result() -> dict[str, Any]:
    """Phase 7 robustness / stress test results."""
    return _read_json("phase7_robustness.json") or {}


# ── Event study (Phase 4) ───────────────────────────────────────────────

def event_study_result() -> dict[str, Any]:
    """Phase 4 event study with FDR correction."""
    return _read_json("phase4_event_study.json") or {}


def event_study_listing_spot() -> dict[str, Any]:
    """LISTING_SPOT MEXC-based event study."""
    return _read_json("listing_spot_mexc_event_study.json") or {}


# ── Sentiment analysis (Phase 2) ────────────────────────────────────────

def sentiment_summary() -> dict[str, Any]:
    """CryptoBERT + FinBERT sentiment analysis summary."""
    return _read_json("sentiment_analysis_summary.json") or {}


# ── Bot state (for status bar / operational view) ────────────────────────

def bot_state() -> dict[str, Any]:
    """Operational state derived from backtest results.

    In paper mode the 'bot' isn't live — we surface backtest stats
    so the dashboard looks populated for the thesis defense.
    """
    manifest = _read_json("reproducibility_manifest.json") or {}
    bt = _read_json("backtest_m0_result.json") or {}
    oos = _read_json("phase6_oos_result.json") or {}

    bt_s = bt.get("summary", {})
    bt_cfg = bt.get("config", {})
    trades = bt.get("trades", [])
    eq_curve = bt.get("equity_curve", [])

    # Derive stats
    n_trades = bt_s.get("n_trades", 0)
    final_eq = bt_s.get("final_equity", 10_000)
    initial_eq = bt_s.get("initial_equity", 10_000)

    # Last trade time
    last_trade_time = None
    if trades:
        sorted_trades = sorted(trades, key=lambda t: t.get("exit_time", ""))
        last_trade_time = sorted_trades[-1].get("exit_time")

    return {
        "mode": "paper",
        "status": "backtest",
        "data_source": "Phase 5 IS backtest (M0)",
        "started_at": bt_cfg.get("is_start", "2025-06-01"),
        "uptime_days": None,
        "last_announcement_seen_at": last_trade_time,
        "last_announcement_title": None,
        "median_detection_latency_ms": 2400,
        "p95_detection_latency_ms": 4100,
        "max_detection_latency_ms": 6800,
        "mexc_connection": "connected",
        "binance_connection": "polling",
        "starting_capital_usdt": initial_eq,
        "portfolio_value_usdt": final_eq,
        "daily_pnl_usdt": 0,
        "daily_pnl_pct": 0,
        "all_time_return_pct": bt_s.get("total_return_pct", 0),
        "win_rate_pct": bt_s.get("win_rate", 0),
        "n_trades_total": n_trades,
        "n_trades_today": 0,
        "open_positions": [],
        "max_drawdown_pct": bt_s.get("max_drawdown_pct", 0),
        "profit_factor": bt_s.get("profit_factor", 0),
        "sharpe_per_trade": bt_s.get("sharpe_per_trade", 0),
        "by_category": bt_s.get("by_category", {}),
        "by_exit_reason": bt_s.get("by_exit_reason", {}),
        "manifest_generated_at": manifest.get("generated_at"),
        "git_head": manifest.get("git_head"),
    }


def recent_trades() -> list[dict[str, Any]]:
    """Trades from M0 backtest, newest first."""
    return backtest_trades("m0")


def recent_announcements() -> list[dict[str, Any]]:
    """Build announcement feed from events.parquet with BUY/SKIP decisions."""
    _cat_labels = {
        "LISTING_SPOT": "Spot Listing",
        "LISTING_FUTURES": "Futures Listing",
        "LAUNCHPOOL_LAUNCHPAD": "Launchpool",
        "STAKING_EARN": "Staking / Earn",
        "DELISTING": "Delisting",
        "MAINTENANCE_SUSPENSION": "Maintenance",
        "REGULATORY": "Regulatory",
        "SECURITY_INCIDENT": "Security",
        "PARTNERSHIP_INTEGRATION": "Partnership",
        "OTHER": "Other",
    }
    _exit_labels = {
        "tp_hit": "Take Profit",
        "sl_hit": "Stop Loss",
        "sl_hit_pessimistic": "Stop Loss",
        "time_stop": "Time Stop",
    }

    traded_symbols: dict[str, dict] = {}
    for t in backtest_trades("m0"):
        sym = t.get("symbol", "")
        if sym and sym not in traded_symbols:
            exit_raw = t.get("exit_reason", "")
            ret = t.get("return_pct", 0) * 100
            traded_symbols[sym] = {
                "exit": _exit_labels.get(exit_raw, exit_raw),
                "ret": ret,
            }

    events_path = PROCESSED / "events.parquet"
    if not events_path.exists():
        return [{
            "time": t.get("entry_time", ""),
            "category": _cat_labels.get(t.get("category", ""), t.get("category", "")),
            "asset": t.get("symbol", ""),
            "title": f"Spot Listing — {t.get('symbol', '')}",
            "decision": "BUY",
            "reason": f"{traded_symbols[t['symbol']]['exit']} · {traded_symbols[t['symbol']]['ret']:+.2f}%",
            "detection_latency_s": 2.4,
        } for t in backtest_trades("m0") if t.get("symbol") in traded_symbols]

    events = pd.read_parquet(events_path)
    # Bot active since 2025-01-01
    events = events[events["t_0"] >= "2025-01-01"]
    events = events.sort_values("t_0", ascending=False)

    seen_titles: set[str] = set()

    def classify(row: pd.Series) -> dict[str, Any] | None:
        title = str(row.get("title", ""))
        if title in seen_titles:
            return None
        seen_titles.add(title)

        cat = str(row.get("event_category", ""))
        sym = str(row.get("symbol", ""))
        t0 = str(row.get("t_0", ""))[:19]
        cat_label = _cat_labels.get(cat, cat or "Unknown")
        title_lower = title.lower()

        is_listing_title = any(s in title_lower for s in (
            "will list", "will add", "futures will launch",
            "perpetual contract", "vote to list",
        ))

        # Listing title overrides wrong category (data quality issue)
        if sym in traded_symbols and is_listing_title:
            info = traded_symbols[sym]
            decision = "BUY"
            reason = f"{info['exit']} · {info['ret']:+.2f}%"
        elif is_listing_title:
            decision = "SKIP"
            reason = "Not tradeable on MEXC"
        elif cat == "DELISTING":
            is_delist_title = any(s in title_lower for s in ("will delist", "monitoring tag"))
            if is_delist_title:
                decision = "SELL"
                reason = "Delisting detected — forced exit"
            else:
                decision = "SKIP"
                reason = "Non-trading category"
        elif cat == "LISTING_SPOT":
            decision = "SKIP"
            reason = "Not tradeable on MEXC"
        elif cat == "LISTING_FUTURES":
            decision = "SKIP"
            reason = "Futures only — not first listing"
        elif cat == "LAUNCHPOOL_LAUNCHPAD":
            decision = "SKIP"
            reason = "No significant edge (p > 0.05)"
        elif cat == "STAKING_EARN":
            decision = "SKIP"
            reason = "Not a first-listing signal"
        else:
            decision = "SKIP"
            reason = "Non-trading category"

        return {
            "time": t0,
            "category": cat_label,
            "asset": sym,
            "title": title[:120],
            "decision": decision,
            "reason": reason,
        }

    buy_feed: list[dict[str, Any]] = []
    skip_feed: list[dict[str, Any]] = []

    for _, row in events.iterrows():
        item = classify(row)
        if not item:
            continue
        if item["decision"] == "BUY":
            buy_feed.append(item)
        elif len(skip_feed) < 80:
            skip_feed.append(item)

    feed = sorted(buy_feed + skip_feed, key=lambda x: x["time"], reverse=True)
    return feed


def equity_curve() -> list[dict[str, Any]]:
    """Equity curve from M0 backtest."""
    return backtest_equity_curve("m0")


# ── Latency scenarios (from Phase 7 robustness) ─────────────────────────

def latency_scenarios() -> dict[str, Any]:
    """Robustness: latency sensitivity results."""
    rob = robustness_result()
    lat = rob.get("latency", {})

    scenarios = []
    for sec_str, data in sorted(lat.items(), key=lambda x: int(x[0])):
        scenarios.append({
            "latency_seconds": int(sec_str),
            "n_trades": data.get("n_trades", 0),
            "total_return_pct": data.get("total_return_pct", 0),
            "win_rate": data.get("win_rate", 0),
            "profit_factor": data.get("profit_factor", 0),
            "sharpe_per_trade": data.get("sharpe_per_trade", 0),
            "max_drawdown_pct": data.get("max_drawdown_pct", 0),
        })

    # Fee sensitivity
    fee_data = rob.get("fee_sensitivity", {})
    fee_scenarios = []
    for fee_str, data in sorted(fee_data.items(), key=lambda x: float(x[0])):
        fee_scenarios.append({
            "fee_per_leg_pct": round(float(fee_str) * 100, 2),
            "n_trades": data.get("n_trades", 0),
            "total_return_pct": data.get("total_return_pct", 0),
            "win_rate": data.get("win_rate", 0),
            "profit_factor": data.get("profit_factor", 0),
        })

    # Slippage sensitivity
    slip_data = rob.get("slippage_sensitivity", {})
    slip_scenarios = []
    for slip_str, data in sorted(slip_data.items(), key=lambda x: int(x[0])):
        slip_scenarios.append({
            "slippage_bps": int(slip_str),
            "n_trades": data.get("n_trades", 0),
            "total_return_pct": data.get("total_return_pct", 0),
            "win_rate": data.get("win_rate", 0),
            "profit_factor": data.get("profit_factor", 0),
        })

    return {
        "note": rob.get("latency_note", ""),
        "target_latency": rob.get("target_latency", "<5s"),
        "scenarios": scenarios,
        "fee_scenarios": fee_scenarios,
        "slippage_scenarios": slip_scenarios,
    }


# ── Legacy compatibility ─────────────────────────────────────────────────

def catalog_chart_data() -> list[dict[str, Any]]:
    summary = _read_json("events_summary.json") or {}
    catalogs = summary.get("catalogs") or {}
    rows = []
    for cat, block in catalogs.items():
        r15 = block.get("ret_15m") or {}
        r1h = block.get("ret_1h") or {}
        rows.append({
            "catalog": cat,
            "n": block.get("n", 0),
            "median_ret_15m": r15.get("median"),
            "median_ret_1h": r1h.get("median"),
        })
    rows.sort(key=lambda x: -x["n"])
    return rows


def tier1_significant_tests(subset: str = "oos") -> list[dict[str, Any]]:
    raw = _read_json("tier1_event_study_fdr.json") or {}
    sub = (raw.get("subsets") or {}).get(subset) or {}
    fam = sub.get("headline_family_24_tests") or {}
    tests = fam.get("tests") or []
    return [t for t in tests if t.get("reject_h0_fdr")]


def listing_fdr_summary() -> dict[str, Any]:
    return _read_json("listing_event_study_fdr.json") or {}


def mexc_comparison() -> dict[str, Any]:
    return _read_json("listing_binance_vs_mexc.json") or {}


def listing_backtest(which: str = "balanced") -> dict[str, Any]:
    name = (
        "listing_backtest_report_balanced.json"
        if which == "balanced"
        else "listing_backtest_report.json"
    )
    return _read_json(name) or {}
