"""Shared event-study test helpers (t-test + Benjamini-Hochberg FDR)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

HORIZONS = (
    "ret_1m",
    "ret_5m",
    "ret_15m",
    "ret_1h",
    "ret_4h",
    "ret_24h",
)


def horizon_columns(baseline: str) -> tuple[str, ...]:
    """Map baseline name to return column suffixes."""
    if baseline == "raw":
        return HORIZONS
    if baseline == "btc_adj":
        return tuple(f"{h}_btc_adj" for h in HORIZONS)
    if baseline == "index_adj":
        return tuple(f"{h}_index_adj" for h in HORIZONS)
    raise ValueError(f"Unknown baseline {baseline!r}")


def mean_return_ttest(returns: pd.Series) -> dict:
    r = pd.to_numeric(returns, errors="coerce").dropna()
    n = int(len(r))
    if n < 2:
        return {"n": n, "mean": None, "t_stat": None, "p_value": None}
    t_stat, p_val = stats.ttest_1samp(r, popmean=0.0, nan_policy="omit")
    return {
        "n": n,
        "mean": float(r.mean()),
        "median": float(r.median()),
        "std": float(r.std(ddof=1)) if n > 1 else None,
        "t_stat": float(t_stat),
        "p_value": float(p_val),
    }


def fdr_bh(p_values: list[float], alpha: float = 0.05) -> tuple[list[float], list[bool]]:
    m = len(p_values)
    if m == 0:
        return [], []
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p)
    ranked = p[order]
    ranks = np.arange(1, m + 1)
    raw_adj = ranked * m / ranks
    adj_sorted = np.minimum.accumulate(raw_adj[::-1])[::-1]
    adj_sorted = np.clip(adj_sorted, 0.0, 1.0)

    thresh = alpha * ranks / m
    below = ranked <= thresh
    reject_sorted = np.zeros(m, dtype=bool)
    if below.any():
        k_max = int(np.max(np.where(below)[0]))
        reject_sorted[: k_max + 1] = True

    out_adj = np.zeros(m, dtype=float)
    out_reject = np.zeros(m, dtype=bool)
    out_adj[order] = adj_sorted
    out_reject[order] = reject_sorted
    return out_adj.tolist(), out_reject.tolist()


def apply_fdr(rows: list[dict], alpha: float = 0.05) -> list[dict]:
    idx = [i for i, r in enumerate(rows) if r.get("p_value") is not None]
    if not idx:
        return rows
    pvals = [rows[i]["p_value"] for i in idx]
    p_adj, reject = fdr_bh(pvals, alpha=alpha)
    for j, i in enumerate(idx):
        rows[i]["p_adj"] = float(p_adj[j])
        rows[i]["reject_h0_fdr"] = bool(reject[j])
    return rows


def run_test_battery(
    df: pd.DataFrame,
    columns: tuple[str, ...],
    label: str,
    alpha: float,
) -> dict:
    rows: list[dict] = []
    for col in columns:
        if col not in df.columns:
            continue
        rows.append({"family": label, "column": col, **mean_return_ttest(df[col])})
    rows = apply_fdr(rows, alpha=alpha)
    sig = sum(1 for r in rows if r.get("reject_h0_fdr"))
    return {
        "label": label,
        "n_tests": len(rows),
        "n_significant_fdr": sig,
        "tests": rows,
    }
