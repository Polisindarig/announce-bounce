"""Listing-catalog OOS report: strategy LONG vs naive long-all at each horizon."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.analysis.train_baseline import load_window_bounds, time_split_masks
from src.backtest.engine import run_backtest
from src.sentiment.sentiment_scorer import score as lexical_score

logger = logging.getLogger(__name__)

LISTING_CATALOG = "new_cryptocurrency_listing"
HORIZONS = ("ret_1m", "ret_5m", "ret_15m", "ret_1h", "ret_4h", "ret_24h")


def _window_config_label(repo_root: Path, window_path: Path) -> str:
    try:
        return str(window_path.relative_to(repo_root))
    except ValueError:
        return str(window_path)


def _resolve(repo_root: Path, p: str | Path) -> Path:
    pp = Path(p)
    return pp.resolve() if pp.is_absolute() else (repo_root / pp).resolve()


def naive_long_stats(oos: pd.DataFrame, horizon: str, costs: float) -> dict:
    col = horizon
    if col not in oos.columns:
        return {"n_trades": 0}
    r = pd.to_numeric(oos[col], errors="coerce")
    mask = r.notna()
    pnls = r[mask] - costs
    n = int(mask.sum())
    if n == 0:
        return {"n_trades": 0}
    arr = pnls.to_numpy(dtype=float)
    return {
        "n_trades": n,
        "mean_pnl": float(arr.mean()),
        "median_pnl": float(np.median(arr)),
        "sum_pnl": float(arr.sum()),
        "win_rate": float((arr > 0).mean()),
    }


def sentiment_return_corr(df: pd.DataFrame, horizon: str) -> dict | None:
    if horizon not in df.columns or df.empty:
        return None
    sent = df.apply(
        lambda r: lexical_score(str(r.get("title", "") or ""), ""), axis=1
    )
    ret = pd.to_numeric(df[horizon], errors="coerce")
    mask = ret.notna()
    if int(mask.sum()) < 3:
        return {"n": int(mask.sum())}
    return {
        "n": int(mask.sum()),
        "pearson_sent_vs_ret": float(sent[mask].corr(ret[mask])),
        "median_sent": float(sent[mask].median()),
    }


def horizon_medians(oos: pd.DataFrame) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for h in HORIZONS:
        if h not in oos.columns:
            out[h] = None
            continue
        s = pd.to_numeric(oos[h], errors="coerce")
        out[h] = float(s.median()) if s.notna().any() else None
    return out


def build_listing_report(backtest_config: Path) -> dict:
    with open(backtest_config) as f:
        cfg = yaml.safe_load(f)

    repo_root = backtest_config.parent.parent
    events_path = _resolve(repo_root, cfg["events_path"])
    window_path = _resolve(repo_root, cfg["window_config"])
    horizon = str(cfg.get("horizon_col", "ret_15m"))
    fee_rt = float(cfg.get("fee_roundtrip", 0.002))
    slip = float(cfg.get("slippage_each_leg", 0.00075))
    costs = fee_rt + 2.0 * slip

    df = pd.read_parquet(events_path)
    df = df[df["catalog_name"] == LISTING_CATALOG].copy()

    bounds = load_window_bounds(window_path)
    is_mask, oos_mask = time_split_masks(df["published_at"], bounds)
    is_df = df.loc[is_mask]
    oos_df = df.loc[oos_mask]

    strategy = run_backtest(str(backtest_config))

    report: dict = {
        "catalog": LISTING_CATALOG,
        "window_config": _window_config_label(repo_root, window_path),
        "is_range": [bounds["is_start"].isoformat(), bounds["is_end"].isoformat()],
        "oos_range": [bounds["oos_start"].isoformat(), bounds["oos_end"].isoformat()],
        "horizon_col": horizon,
        "costs_per_trade": costs,
        "n_total_rows": int(len(df)),
        "n_in_sample": int(len(is_df)),
        "n_oos": int(len(oos_df)),
        "is_horizon_medians_raw": horizon_medians(is_df),
        "oos_horizon_medians_raw": horizon_medians(oos_df),
        "is_naive_long_all": {},
        "oos_naive_long_all": {},
        "is_sentiment_vs_ret_15m": sentiment_return_corr(is_df, horizon),
        "oos_sentiment_vs_ret_15m": sentiment_return_corr(oos_df, horizon),
        "oos_strategy_long": strategy,
    }

    for h in HORIZONS:
        report["is_naive_long_all"][h] = naive_long_stats(is_df, h, costs)
        report["oos_naive_long_all"][h] = naive_long_stats(oos_df, h, costs)

    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Listing-only OOS backtest report")
    parser.add_argument(
        "--config",
        default=str(root / "config" / "backtest_listing.yaml"),
    )
    parser.add_argument(
        "--output",
        default=str(root / "data" / "processed" / "listing_backtest_report.json"),
    )
    args = parser.parse_args()

    report = build_listing_report(Path(args.config))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
