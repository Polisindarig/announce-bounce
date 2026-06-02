"""Listing backtest report smoke test."""

from pathlib import Path

import pandas as pd
import pytest

from src.analysis.listing_backtest_report import build_listing_report


@pytest.mark.skipif(
    not Path("data/processed/events.parquet").exists(),
    reason="events.parquet not built",
)
def test_listing_report_structure():
    root = Path(__file__).resolve().parents[1]
    cfg = root / "config" / "backtest_listing.yaml"
    report = build_listing_report(cfg)
    assert report["catalog"] == "new_cryptocurrency_listing"
    assert report["n_total_rows"] > 0
    assert "oos_strategy_long" in report
    assert "ret_15m" in report["oos_naive_long_all"]
