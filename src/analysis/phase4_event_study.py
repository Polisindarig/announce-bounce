"""Phase 4 — Exploratory Data Analysis: Event Study & Calibration.

Computes per-category abnormal returns across 6 horizons × 3 baselines,
runs hypothesis tests (parametric + non-parametric) with BH-FDR correction,
calibrates TP/SL levels, and produces thesis-ready summary tables.

Statistical methods:
    - One-sample t-test (H₀: mean AR = 0)
    - Wilcoxon signed-rank test (non-parametric alternative)
    - Benjamini-Hochberg FDR correction (α = 0.05)
    - Bootstrap confidence intervals (10,000 resamples)
    - Percentile-based TP/SL calibration (p70 favorable / p30 adverse)

References:
    - MacKinlay (1997) — event study methodology
    - Benjamini & Hochberg (1995) — FDR
    - Efron & Tibshirani (1993) — bootstrap CI

Usage:
    python -m src.analysis.phase4_event_study
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analysis.event_study_stats import fdr_bh
from src.sentiment.category_classifier import Category, classify

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────

HORIZONS = ["ret_1m", "ret_5m", "ret_15m", "ret_1h", "ret_4h", "ret_24h"]
BASELINES = ["raw", "btc_adj", "index_adj"]
HORIZON_LABELS = {
    "ret_1m": "t+1m",
    "ret_5m": "t+5m",
    "ret_15m": "t+15m",
    "ret_1h": "t+1h",
    "ret_4h": "t+4h",
    "ret_24h": "t+24h",
}

TIER1_CATEGORIES = {
    "LISTING_SPOT",
    "LISTING_FUTURES",
    "LAUNCHPOOL_LAUNCHPAD",
    "STAKING_EARN",
}

TIER2_CATEGORIES = {
    "DELISTING",
    "MAINTENANCE_SUSPENSION",
    "HODLER_AIRDROP",
    "AIRDROP",
    "REGULATORY",
    "SECURITY_INCIDENT",
    "PARTNERSHIP_INTEGRATION",
    "FORK_UPGRADE",
}

N_BOOTSTRAP = 10_000
FDR_ALPHA = 0.05
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


# ── Helpers ────────────────────────────────────────────────────────────────


def _col(horizon: str, baseline: str) -> str:
    """Return the column name for a given horizon × baseline."""
    if baseline == "raw":
        return horizon
    return f"{horizon}_{baseline}"


def _bootstrap_ci(
    values: np.ndarray,
    n_bootstrap: int = N_BOOTSTRAP,
    ci: float = 0.95,
    statistic: str = "mean",
) -> dict:
    """Compute bootstrap CI for mean or median."""
    rng = np.random.default_rng(42)
    n = len(values)
    boot_stats = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        sample = values[rng.integers(0, n, size=n)]
        if statistic == "mean":
            boot_stats[i] = np.mean(sample)
        else:
            boot_stats[i] = np.median(sample)
    alpha = (1 - ci) / 2
    lo, hi = np.percentile(boot_stats, [alpha * 100, (1 - alpha) * 100])
    return {
        f"{statistic}": float(np.mean(values) if statistic == "mean" else np.median(values)),
        f"boot_ci_lo": float(lo),
        f"boot_ci_hi": float(hi),
        f"boot_se": float(np.std(boot_stats, ddof=1)),
    }


def _test_single_horizon(values: np.ndarray) -> dict:
    """Run parametric + non-parametric tests on a single return series."""
    n = len(values)
    if n < 5:
        return {
            "n": n,
            "mean": float(np.mean(values)) if n > 0 else None,
            "median": float(np.median(values)) if n > 0 else None,
            "std": None,
            "t_stat": None,
            "t_pvalue": None,
            "wilcoxon_stat": None,
            "wilcoxon_pvalue": None,
            "win_rate": None,
        }

    mean_val = float(np.mean(values))
    median_val = float(np.median(values))
    std_val = float(np.std(values, ddof=1))

    # Parametric: one-sample t-test (H₀: μ = 0)
    t_stat, t_pval = stats.ttest_1samp(values, popmean=0.0)

    # Non-parametric: Wilcoxon signed-rank test (H₀: median = 0)
    # Requires at least some non-zero values
    nonzero = values[values != 0]
    if len(nonzero) >= 5:
        w_stat, w_pval = stats.wilcoxon(nonzero, alternative="two-sided")
    else:
        w_stat, w_pval = None, None

    # Win rate
    win_rate = float(np.sum(values > 0) / n)

    result = {
        "n": n,
        "mean": mean_val,
        "median": median_val,
        "std": std_val,
        "skewness": float(stats.skew(values)),
        "kurtosis": float(stats.kurtosis(values)),
        "win_rate": win_rate,
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "p10": float(np.percentile(values, 10)),
        "p25": float(np.percentile(values, 25)),
        "p75": float(np.percentile(values, 75)),
        "p90": float(np.percentile(values, 90)),
        "t_stat": float(t_stat),
        "t_pvalue": float(t_pval),
        "wilcoxon_stat": float(w_stat) if w_stat is not None else None,
        "wilcoxon_pvalue": float(w_pval) if w_pval is not None else None,
    }

    # Bootstrap CI (only for groups with enough data)
    if n >= 20:
        boot = _bootstrap_ci(values, N_BOOTSTRAP, ci=0.95, statistic="mean")
        result.update(boot)

    return result


# ── Re-classify events ─────────────────────────────────────────────────────


def reclassify_events(df: pd.DataFrame) -> pd.DataFrame:
    """Enhance existing event_category with new sub-categories.

    Keeps the original (body-text-aware) classification but splits out
    HODLER_AIRDROP and AIRDROP from LAUNCHPOOL_LAUNCHPAD / STAKING_EARN / OTHER.
    """
    import re

    df = df.copy()
    # Start from the existing (richer) classification
    df["category"] = df["event_category"]

    # Extract HODLER_AIRDROP from any category
    hodler_mask = df["title"].str.lower().str.contains(
        r"hodler airdrop|hodler airdrops|bnsol super stake|super stake",
        regex=True,
        na=False,
    )
    df.loc[hodler_mask, "category"] = "HODLER_AIRDROP"

    # Extract AIRDROP (generic, not hodler/launchpool)
    airdrop_mask = (
        df["title"].str.lower().str.contains(r"\bairdrop\b|\bair drop\b", regex=True, na=False)
        & ~hodler_mask
        & ~df["category"].isin({"LAUNCHPOOL_LAUNCHPAD"})
    )
    df.loc[airdrop_mask, "category"] = "AIRDROP"

    return df


# ── Main event study ───────────────────────────────────────────────────────


def run_event_study(df: pd.DataFrame) -> dict:
    """Run the full event study across all categories × horizons × baselines."""

    results = {
        "metadata": {
            "total_events": len(df),
            "date_range": {
                "start": str(df["published_at"].min()),
                "end": str(df["published_at"].max()),
            },
            "n_bootstrap": N_BOOTSTRAP,
            "fdr_alpha": FDR_ALPHA,
            "baselines": BASELINES,
            "horizons": [HORIZON_LABELS[h] for h in HORIZONS],
        },
        "category_distribution": {},
        "tier1_results": {},
        "tier2_results": {},
        "fdr_correction": {},
        "tp_sl_calibration": {},
    }

    # ── Category distribution ──
    cat_counts = df["category"].value_counts().to_dict()
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        n_with_returns = int(df[df["category"] == cat]["ret_15m"].notna().sum())
        results["category_distribution"][cat] = {
            "total": int(count),
            "with_returns": n_with_returns,
            "tier": "tier1" if cat in TIER1_CATEGORIES else "tier2",
        }

    # ── Per-category × baseline × horizon tests ──
    all_pvalues = []  # For FDR correction across Tier 1

    for cat in sorted(set(TIER1_CATEGORIES | TIER2_CATEGORIES)):
        sub = df[df["category"] == cat].copy()
        if len(sub) < 5:
            continue

        tier_key = "tier1_results" if cat in TIER1_CATEGORIES else "tier2_results"
        results[tier_key][cat] = {"baselines": {}}

        for baseline in BASELINES:
            baseline_results = {}
            for horizon in HORIZONS:
                col = _col(horizon, baseline)
                if col not in sub.columns:
                    continue
                vals = sub[col].dropna().values.astype(float)
                if len(vals) < 5:
                    continue

                test_result = _test_single_horizon(vals)
                test_result["horizon"] = HORIZON_LABELS[horizon]
                baseline_results[HORIZON_LABELS[horizon]] = test_result

                # Collect p-values for Tier 1 FDR correction
                if cat in TIER1_CATEGORIES and test_result["t_pvalue"] is not None:
                    all_pvalues.append({
                        "category": cat,
                        "baseline": baseline,
                        "horizon": HORIZON_LABELS[horizon],
                        "t_pvalue": test_result["t_pvalue"],
                        "wilcoxon_pvalue": test_result.get("wilcoxon_pvalue"),
                    })

            results[tier_key][cat]["baselines"][baseline] = baseline_results

    # ── FDR correction (Tier 1 only, per project plan) ──
    if all_pvalues:
        # T-test FDR
        t_pvals = [p["t_pvalue"] for p in all_pvalues]
        t_adj, t_reject = fdr_bh(t_pvals, alpha=FDR_ALPHA)

        # Wilcoxon FDR (where available)
        w_pvals_raw = [p.get("wilcoxon_pvalue") for p in all_pvalues]
        w_valid_idx = [i for i, p in enumerate(w_pvals_raw) if p is not None]
        w_pvals = [w_pvals_raw[i] for i in w_valid_idx]
        w_adj, w_reject = fdr_bh(w_pvals, alpha=FDR_ALPHA) if w_pvals else ([], [])

        fdr_rows = []
        w_j = 0
        for i, entry in enumerate(all_pvalues):
            row = {
                **entry,
                "t_pvalue_adj": t_adj[i],
                "t_reject_h0": t_reject[i],
            }
            if entry.get("wilcoxon_pvalue") is not None:
                row["wilcoxon_pvalue_adj"] = w_adj[w_j]
                row["wilcoxon_reject_h0"] = w_reject[w_j]
                w_j += 1
            fdr_rows.append(row)

        results["fdr_correction"] = {
            "n_tests": len(all_pvalues),
            "n_significant_ttest": sum(t_reject),
            "n_significant_wilcoxon": sum(w_reject) if w_reject else 0,
            "alpha": FDR_ALPHA,
            "tests": fdr_rows,
        }

    # ── TP/SL Calibration (Tier 1 only, in-sample) ──
    for cat in TIER1_CATEGORIES:
        sub = df[df["category"] == cat].copy()
        if len(sub) < 10:
            continue

        calibration = {}
        for horizon in HORIZONS:
            col = _col(horizon, "raw")  # TP/SL on raw returns
            vals = sub[col].dropna().values.astype(float)
            if len(vals) < 10:
                continue

            favorable = vals[vals > 0]
            adverse = vals[vals < 0]

            tp_fraction = float(np.percentile(favorable, 70)) if len(favorable) >= 5 else None
            sl_fraction = float(abs(np.percentile(adverse, 30))) if len(adverse) >= 5 else None

            # Clamp per project plan: TP [1%, 30%], SL [1%, 8%]
            if tp_fraction is not None:
                tp_fraction = max(0.01, min(0.30, tp_fraction))
            if sl_fraction is not None:
                sl_fraction = max(0.01, min(0.08, sl_fraction))

            calibration[HORIZON_LABELS[horizon]] = {
                "n": len(vals),
                "n_favorable": len(favorable),
                "n_adverse": len(adverse),
                "tp_fraction": tp_fraction,
                "sl_fraction": sl_fraction,
                "max_favorable_excursion": float(np.max(favorable)) if len(favorable) > 0 else None,
                "max_adverse_excursion": float(abs(np.min(adverse))) if len(adverse) > 0 else None,
                "mean_favorable": float(np.mean(favorable)) if len(favorable) > 0 else None,
                "mean_adverse": float(np.mean(adverse)) if len(adverse) > 0 else None,
            }

        if calibration:
            results["tp_sl_calibration"][cat] = calibration

    return results


# ── Summary table for thesis ──────────────────────────────────────────────


def format_summary_table(results: dict) -> str:
    """Format a human-readable summary table for thesis Bölüm 4."""
    lines = []
    lines.append("=" * 100)
    lines.append("EVENT STUDY SUMMARY — Phase 4 (Exploratory Data Analysis)")
    lines.append("=" * 100)

    meta = results["metadata"]
    lines.append(f"Period: {meta['date_range']['start'][:10]} → {meta['date_range']['end'][:10]}")
    lines.append(f"Total events: {meta['total_events']}")
    lines.append(f"FDR α: {meta['fdr_alpha']}, Bootstrap resamples: {meta['n_bootstrap']}")
    lines.append("")

    # Category distribution
    lines.append("── Category Distribution ──")
    lines.append(f"{'Category':<28s} {'Tier':>5s} {'Total':>7s} {'w/Returns':>10s}")
    lines.append("-" * 55)
    for cat, info in results["category_distribution"].items():
        lines.append(f"{cat:<28s} {info['tier']:>5s} {info['total']:>7d} {info['with_returns']:>10d}")

    # Tier 1 headline results (raw baseline)
    lines.append("")
    lines.append("── Tier 1: Mean Abnormal Return (raw) ──")
    header = f"{'Category':<24s}"
    for h in ["t+1m", "t+5m", "t+15m", "t+1h", "t+4h", "t+24h"]:
        header += f" {h:>10s}"
    lines.append(header)
    lines.append("-" * 90)

    for cat in ["LISTING_SPOT", "LISTING_FUTURES", "LAUNCHPOOL_LAUNCHPAD", "STAKING_EARN"]:
        if cat not in results["tier1_results"]:
            continue
        raw = results["tier1_results"][cat]["baselines"].get("raw", {})
        row = f"{cat:<24s}"
        for h in ["t+1m", "t+5m", "t+15m", "t+1h", "t+4h", "t+24h"]:
            info = raw.get(h, {})
            mean = info.get("mean")
            if mean is not None:
                star = "*" if any(
                    t.get("t_reject_h0") and t["category"] == cat and t["horizon"] == h and t["baseline"] == "raw"
                    for t in results.get("fdr_correction", {}).get("tests", [])
                ) else ""
                row += f" {mean:>+9.4f}{star}"
            else:
                row += f" {'—':>10s}"
        lines.append(row)

    # FDR summary
    fdr = results.get("fdr_correction", {})
    if fdr:
        lines.append("")
        lines.append(f"── FDR Correction: {fdr.get('n_significant_ttest', 0)}/{fdr.get('n_tests', 0)} "
                      f"significant (t-test), {fdr.get('n_significant_wilcoxon', 0)}/{fdr.get('n_tests', 0)} "
                      f"significant (Wilcoxon) at α={fdr.get('alpha', 0.05)} ──")

    # TP/SL calibration
    if results.get("tp_sl_calibration"):
        lines.append("")
        lines.append("── TP/SL Calibration (raw returns, clamped) ──")
        lines.append(f"{'Category':<24s} {'Horizon':<8s} {'TP%':>6s} {'SL%':>6s} {'MaxFav':>8s} {'MaxAdv':>8s}")
        lines.append("-" * 65)
        for cat, horizons in results["tp_sl_calibration"].items():
            for h, cal in horizons.items():
                tp = f"{cal['tp_fraction']*100:.1f}%" if cal.get("tp_fraction") else "—"
                sl = f"{cal['sl_fraction']*100:.1f}%" if cal.get("sl_fraction") else "—"
                mf = f"{cal['max_favorable_excursion']*100:.1f}%" if cal.get("max_favorable_excursion") else "—"
                ma = f"{cal['max_adverse_excursion']*100:.1f}%" if cal.get("max_adverse_excursion") else "—"
                lines.append(f"{cat:<24s} {h:<8s} {tp:>6s} {sl:>6s} {mf:>8s} {ma:>8s}")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    events_path = DATA_DIR / "processed" / "events.parquet"
    if not events_path.exists():
        logger.error("events.parquet not found at %s", events_path)
        return

    logger.info("Loading events from %s ...", events_path)
    df = pd.read_parquet(events_path)
    logger.info("Loaded %d events", len(df))

    # Re-classify with updated classifier
    logger.info("Re-classifying events with updated 12-category classifier...")
    df = reclassify_events(df)
    logger.info("Category distribution after reclassification:")
    for cat, n in df["category"].value_counts().items():
        logger.info("  %-28s %5d", cat, n)

    # Run event study
    logger.info("\nRunning event study (tests + calibration)...")
    results = run_event_study(df)

    # Save JSON
    output_path = DATA_DIR / "processed" / "phase4_event_study.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info("\nSaved: %s", output_path)

    # Print summary
    summary = format_summary_table(results)
    print("\n" + summary)

    # Save summary text
    summary_path = DATA_DIR / "processed" / "phase4_event_study_summary.txt"
    with open(summary_path, "w") as f:
        f.write(summary)
    logger.info("Saved: %s", summary_path)


if __name__ == "__main__":
    main()
