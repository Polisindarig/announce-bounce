"""In-sample / OOS baseline regression on `events.parquet`.

Uses ``published_at`` as the event clock (aligned with announcement time in
``build_events_table``). Features: one-hot ``catalog_name`` + log1p volume.
Target: a return column (default ``ret_5m_btc_adj``).

Writes ``data/processed/train_baseline_report.json`` by default.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    mean_absolute_error,
    r2_score,
    root_mean_squared_error,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder

logger = logging.getLogger(__name__)


def _parse_ts_utc(s: str) -> pd.Timestamp:
    t = pd.Timestamp(str(s).replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return t


def _end_of_utc_day(t: pd.Timestamp) -> pd.Timestamp:
    return t.normalize() + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)


def load_window_bounds(config_path: Path) -> dict[str, pd.Timestamp]:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    is_start = _parse_ts_utc(cfg["in_sample_start"])
    is_end = _end_of_utc_day(_parse_ts_utc(cfg["in_sample_end"]))
    oos_start = _parse_ts_utc(cfg["oos_start"]).normalize()
    oos_end = _end_of_utc_day(_parse_ts_utc(cfg["oos_end"]))
    return {
        "is_start": is_start,
        "is_end": is_end,
        "oos_start": oos_start,
        "oos_end": oos_end,
    }


def time_split_masks(
    published_at: pd.Series, bounds: dict[str, pd.Timestamp]
) -> tuple[pd.Series, pd.Series]:
    """IS = [is_start, min(is_end, oos_start - 1ns)] if calendars touch; OOS = [oos_start, oos_end]."""
    pub = pd.to_datetime(published_at, utc=True)
    if not isinstance(pub, pd.Series):
        pub = pd.Series(pub)

    t0, t1 = bounds["is_start"], bounds["is_end"]
    t2, t3 = bounds["oos_start"], bounds["oos_end"]

    if t2 <= t1:
        is_upper = t2 - pd.Timedelta(nanoseconds=1)
    else:
        is_upper = t1

    is_mask = (pub >= t0) & (pub <= is_upper)
    oos_mask = (pub >= t2) & (pub <= t3)
    return is_mask, oos_mask


def _log1p_safe(X: np.ndarray) -> np.ndarray:
    return np.log1p(np.clip(np.asarray(X, dtype=float), a_min=0.0, a_max=None))


def build_model_pipeline() -> Pipeline:
    pre = ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                ["catalog_name"],
            ),
            (
                "vol",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("log1p", FunctionTransformer(_log1p_safe, feature_names_out="one-to-one")),
                    ]
                ),
                ["t0_volume"],
            ),
        ]
    )
    return Pipeline([("prep", pre), ("ridge", Ridge(alpha=1.0, random_state=42))])


def train_baseline(
    events: pd.DataFrame,
    bounds: dict[str, pd.Timestamp],
    target_col: str = "ret_5m_btc_adj",
) -> dict[str, Any]:
    df = events.copy()
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True)

    is_mask, oos_mask = time_split_masks(df["published_at"], bounds)
    df_is = df.loc[is_mask].copy()
    df_oos = df.loc[oos_mask].copy()

    feature_cols = ["catalog_name", "t0_volume"]
    for c in feature_cols + [target_col]:
        if c not in df.columns:
            raise KeyError(f"Missing column {c!r} in events table")

    df_is = df_is.dropna(subset=[target_col])
    df_oos = df_oos.dropna(subset=[target_col])

    report: dict[str, Any] = {
        "n_in_sample": int(len(df_is)),
        "n_oos": int(len(df_oos)),
        "target": target_col,
        "is_range": [bounds["is_start"].isoformat(), bounds["is_end"].isoformat()],
        "oos_range": [bounds["oos_start"].isoformat(), bounds["oos_end"].isoformat()],
    }

    if len(df_is) < 10:
        report["error"] = "Too few in-sample rows after dropna; rebuild events or widen window."
        return report
    if len(df_oos) < 1:
        report["error"] = "No OOS rows with non-null target; check dates vs. announcements."
        return report

    X_is, y_is = df_is[feature_cols], df_is[target_col].astype(float)
    X_oos, y_oos = df_oos[feature_cols], df_oos[target_col].astype(float)

    model = build_model_pipeline()
    model.fit(X_is, y_is)
    pred_is = model.predict(X_is)
    pred_oos = model.predict(X_oos)

    naive_oos = float(y_is.mean())
    naive_pred_oos = np.full(len(y_oos), naive_oos)

    report["metrics"] = {
        "in_sample": {
            "mae": float(mean_absolute_error(y_is, pred_is)),
            "rmse": float(root_mean_squared_error(y_is, pred_is)),
            "r2": float(r2_score(y_is, pred_is)),
        },
        "oos": {
            "mae": float(mean_absolute_error(y_oos, pred_oos)),
            "rmse": float(root_mean_squared_error(y_oos, pred_oos)),
            "r2": float(r2_score(y_oos, pred_oos)),
        },
        "oos_naive_mean_is": {
            "mae": float(mean_absolute_error(y_oos, naive_pred_oos)),
            "rmse": float(root_mean_squared_error(y_oos, naive_pred_oos)),
            "r2": float(r2_score(y_oos, naive_pred_oos)),
        },
    }
    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Train IS/OOS Ridge baseline on events (announcement-time aligned)."
    )
    parser.add_argument(
        "--events",
        default=str(root / "data" / "processed" / "events.parquet"),
    )
    parser.add_argument(
        "--config",
        default=str(root / "config" / "data_window.yaml"),
    )
    parser.add_argument(
        "--target",
        default="ret_5m_btc_adj",
        help="Target column, e.g. ret_5m_btc_adj, ret_1h_btc_adj",
    )
    parser.add_argument(
        "--report",
        default=str(root / "data" / "processed" / "train_baseline_report.json"),
    )
    args = parser.parse_args()

    events_path = Path(args.events)
    if not events_path.exists():
        logger.error("Missing %s — run build_events_table first.", events_path)
        raise SystemExit(1)

    bounds = load_window_bounds(Path(args.config))
    df = pd.read_parquet(events_path)
    report = train_baseline(df, bounds, target_col=args.target)

    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("Wrote %s", out)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
