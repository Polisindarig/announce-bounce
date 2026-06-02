"""Listing event-study: one-sample t-tests on mean returns + Benjamini-Hochberg FDR."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from src.analysis.event_study_stats import (
    HORIZONS,
    apply_fdr,
    horizon_columns,
    run_test_battery,
)
from src.analysis.train_baseline import load_window_bounds, time_split_masks

logger = logging.getLogger(__name__)

LISTING_CATALOG = "new_cryptocurrency_listing"
BTC_ADJ = horizon_columns("btc_adj")


def run_horizon_battery(
    df: pd.DataFrame,
    columns: tuple[str, ...],
    label: str,
    alpha: float,
) -> dict:
    bat = run_test_battery(df, columns, label, alpha)
    bat["n_rows_input"] = int(len(df))
    return bat


def build_event_study_report(
    events_path: Path,
    window_config: Path,
    alpha: float = 0.05,
    use_oos_only: bool = False,
) -> dict:
    df = pd.read_parquet(events_path)
    df = df[df["catalog_name"] == LISTING_CATALOG].copy()

    bounds = load_window_bounds(window_config)
    is_mask, oos_mask = time_split_masks(df["published_at"], bounds)

    subsets = {"full_sample": df}
    if use_oos_only:
        subsets = {"oos": df.loc[oos_mask]}
    else:
        subsets["in_sample"] = df.loc[is_mask]
        subsets["oos"] = df.loc[oos_mask]

    report: dict = {
        "catalog": LISTING_CATALOG,
        "window_config": str(window_config),
        "fdr_alpha": alpha,
        "subsets": {},
    }

    for name, sub in subsets.items():
        if sub.empty:
            report["subsets"][name] = {"n": 0}
            continue
        report["subsets"][name] = {
            "n": int(len(sub)),
            "raw_returns": run_horizon_battery(sub, HORIZONS, "raw", alpha),
            "btc_adjusted": run_horizon_battery(sub, BTC_ADJ, "btc_adj", alpha),
        }

    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Listing event-study FDR report")
    parser.add_argument(
        "--events",
        default=str(root / "data" / "processed" / "events.parquet"),
    )
    parser.add_argument(
        "--window-config",
        default=str(root / "config" / "listing_eval_window.yaml"),
    )
    parser.add_argument(
        "--output",
        default=str(root / "data" / "processed" / "listing_event_study_fdr.json"),
    )
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument(
        "--oos-only",
        action="store_true",
        help="Only test OOS subset",
    )
    args = parser.parse_args()

    report = build_event_study_report(
        Path(args.events),
        Path(args.window_config),
        alpha=args.alpha,
        use_oos_only=args.oos_only,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2)[:4000])
    print(f"\n... Wrote {out}")


if __name__ == "__main__":
    main()
