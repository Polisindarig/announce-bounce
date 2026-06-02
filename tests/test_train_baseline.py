"""Tests for announcement-time IS/OOS baseline training."""

import pandas as pd

from src.analysis.train_baseline import time_split_masks, train_baseline


def test_time_split_no_gap():
    bounds = {
        "is_start": pd.Timestamp("2025-01-01", tz="UTC"),
        "is_end": pd.Timestamp("2025-01-10 23:59:59.999999", tz="UTC"),
        "oos_start": pd.Timestamp("2025-02-01", tz="UTC"),
        "oos_end": pd.Timestamp("2025-02-05 23:59:59.999999", tz="UTC"),
    }
    pub = pd.to_datetime(
        ["2025-01-05", "2025-01-20", "2025-02-03"], utc=True
    )
    is_m, oos_m = time_split_masks(pub, bounds)
    assert is_m.tolist() == [True, False, False]
    assert oos_m.tolist() == [False, False, True]


def test_time_split_overlap_feb14_handling():
    """When OOS start <= IS end, IS ends the instant before OOS begins."""
    bounds = {
        "is_start": pd.Timestamp("2025-06-01", tz="UTC"),
        "is_end": pd.Timestamp("2026-02-14 23:59:59.999999", tz="UTC"),
        "oos_start": pd.Timestamp("2026-02-14", tz="UTC"),
        "oos_end": pd.Timestamp("2026-05-14 23:59:59.999999", tz="UTC"),
    }
    pub = pd.to_datetime(["2026-02-13 12:00:00", "2026-02-14 12:00:00"], utc=True)
    is_m, oos_m = time_split_masks(pub, bounds)
    assert bool(is_m.iloc[0])
    assert not bool(is_m.iloc[1])
    assert not bool(oos_m.iloc[0])
    assert bool(oos_m.iloc[1])


def test_train_baseline_smoke():
    rows = []
    for i in range(30):
        day = f"2025-07-{(i % 28) + 1:02d}T12:00:00+00:00"
        rows.append(
            {
                "catalog_name": "new_cryptocurrency_listing" if i % 3 else "other",
                "t0_volume": float(1e6 + i * 1e3),
                "published_at": day,
                "ret_5m_btc_adj": (i % 5) * 0.001 - 0.002,
            }
        )
    for i in range(10):
        rows.append(
            {
                "catalog_name": "new_cryptocurrency_listing",
                "t0_volume": 2e6,
                "published_at": f"2026-03-{(i % 28) + 1:02d}T12:00:00+00:00",
                "ret_5m_btc_adj": 0.001 * i,
            }
        )
    df = pd.DataFrame(rows)
    bounds = {
        "is_start": pd.Timestamp("2025-06-01", tz="UTC"),
        "is_end": pd.Timestamp("2026-02-14 23:59:59.999999", tz="UTC"),
        "oos_start": pd.Timestamp("2026-02-14", tz="UTC"),
        "oos_end": pd.Timestamp("2026-05-14 23:59:59.999999", tz="UTC"),
    }
    report = train_baseline(df, bounds, target_col="ret_5m_btc_adj")
    assert "error" not in report
    assert report["n_in_sample"] >= 10
    assert report["n_oos"] >= 1
    assert "mae" in report["metrics"]["oos"]
