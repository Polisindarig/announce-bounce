"""Headline 24-test FDR family: 4 Tier-1 categories × 6 horizons (index-adjusted AR)."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from src.analysis.event_study_stats import apply_fdr, horizon_columns, run_test_battery
from src.analysis.train_baseline import load_window_bounds, time_split_masks
from src.sentiment.category_classifier import Category, classify

logger = logging.getLogger(__name__)

TIER1_CATEGORIES = (
    Category.LISTING_SPOT,
    Category.LISTING_FUTURES,
    Category.LAUNCHPOOL_LAUNCHPAD,
    Category.STAKING_EARN,
)

TIER1_LABELS = {
    Category.LISTING_SPOT: "listing_spot",
    Category.LISTING_FUTURES: "futures_launch",
    Category.LAUNCHPOOL_LAUNCHPAD: "launchpool_launchpad",
    Category.STAKING_EARN: "staking_earn",
}

TIER2_CATEGORIES = (
    Category.DELISTING,
    Category.SECURITY_INCIDENT,
    Category.REGULATORY,
    Category.FORK_UPGRADE,
    Category.MAINTENANCE_SUSPENSION,
)


def assign_tier1(df: pd.DataFrame) -> pd.DataFrame:
    if "event_category" in df.columns:
        return df
    out = df.copy()
    cats: list[str] = []
    for _, row in out.iterrows():
        cat, _ = classify(
            str(row.get("title", "") or ""),
            "",
            catalog_name=row.get("catalog_name"),
        )
        cats.append(cat.value)
    out["event_category"] = cats
    return out


def descriptive_tier2(df: pd.DataFrame, horizon: str = "ret_15m") -> dict:
    block: dict = {}
    for cat in TIER2_CATEGORIES:
        sub = df[df["event_category"] == cat.value]
        if sub.empty or horizon not in sub.columns:
            block[cat.value] = {"n": int(len(sub))}
            continue
        r = pd.to_numeric(sub[horizon], errors="coerce").dropna()
        block[cat.value] = {
            "n": int(len(sub)),
            "n_with_horizon": int(len(r)),
            "mean": float(r.mean()) if len(r) else None,
            "median": float(r.median()) if len(r) else None,
        }
    return block


def build_tier1_report(
    events_path: Path,
    window_config: Path,
    alpha: float = 0.05,
    headline_baseline: str = "index_adj",
    exclude_contaminated: bool = True,
) -> dict:
    df = assign_tier1(pd.read_parquet(events_path))
    if exclude_contaminated and "contaminated" in df.columns:
        df = df[~df["contaminated"].fillna(False)].copy()

    tier1 = df[df["event_category"].isin([c.value for c in TIER1_CATEGORIES])].copy()

    bounds = load_window_bounds(window_config)
    _, oos_mask = time_split_masks(df["published_at"], bounds)
    subsets = {
        "full_sample": tier1,
        "oos": tier1.loc[oos_mask.loc[tier1.index]],
    }

    report: dict = {
        "headline_baseline": headline_baseline,
        "exclude_contaminated": exclude_contaminated,
        "fdr_alpha": alpha,
        "n_tier1_rows_total": int(len(tier1)),
        "tier1_category_counts": tier1["event_category"].value_counts().to_dict(),
        "subsets": {},
        "tier2_descriptive_ret_15m": descriptive_tier2(df),
    }

    baselines = ("raw", "btc_adj", "index_adj")
    for subset_name, sub in subsets.items():
        if sub.empty:
            report["subsets"][subset_name] = {"n": 0}
            continue

        by_cat: dict = {}
        headline_rows: list[dict] = []

        for cat in TIER1_CATEGORIES:
            cat_df = sub[sub["event_category"] == cat.value]
            label = TIER1_LABELS[cat]
            cat_block: dict = {"n": int(len(cat_df)), "baselines": {}}
            for bl in baselines:
                cols = horizon_columns(bl)
                bat = run_test_battery(cat_df, cols, bl, alpha)
                cat_block["baselines"][bl] = bat
                if bl == headline_baseline:
                    for t in bat["tests"]:
                        headline_rows.append(
                            {"tier1_category": label, "event_category": cat.value, **t}
                        )
            by_cat[label] = cat_block

        headline_rows = apply_fdr(headline_rows, alpha=alpha)
        sig = [r for r in headline_rows if r.get("reject_h0_fdr")]

        report["subsets"][subset_name] = {
            "n": int(len(sub)),
            "by_category": by_cat,
            "headline_family_24_tests": {
                "n_tests": len(headline_rows),
                "n_significant_fdr": len(sig),
                "tests": headline_rows,
            },
        }

    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Tier-1 24-test FDR event study")
    parser.add_argument("--events", default=str(root / "data" / "processed" / "events.parquet"))
    parser.add_argument("--window-config", default=str(root / "config" / "listing_eval_window.yaml"))
    parser.add_argument("--output", default=str(root / "data" / "processed" / "tier1_event_study_fdr.json"))
    parser.add_argument("--alpha", type=float, default=0.05)
    args = parser.parse_args()

    report = build_tier1_report(Path(args.events), Path(args.window_config), alpha=args.alpha)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)

    hf = report["subsets"].get("oos", {}).get("headline_family_24_tests", {})
    print(json.dumps({"n_tier1": report["n_tier1_rows_total"], "oos_sig": hf.get("n_significant_fdr")}, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
