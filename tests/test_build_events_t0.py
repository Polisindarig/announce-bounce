"""Event time and index-adjusted return columns."""

from datetime import datetime, timezone

import pandas as pd
import pytest

from src.scraper.listing_time import resolve_event_time


def test_listing_spot_uses_body_trading_time():
    ann = {
        "published_at": "2025-06-01T10:00:00+00:00",
        "catalog_name": "new_cryptocurrency_listing",
        "title": "Binance Will List Foo (FOO)",
        "body_text": "Trading opens 2025-06-02 12:00 (UTC) for all users.",
    }
    t_ann, t0, src = resolve_event_time(ann, None, is_listing_spot=True)
    assert src == "t_binance_trading"
    assert t0 == datetime(2025, 6, 2, 12, 0, tzinfo=timezone.utc)


@pytest.mark.skipif(
    not __import__("pathlib").Path("data/processed/events.parquet").exists(),
    reason="events not built",
)
def test_events_has_index_adj_columns():
    df = pd.read_parquet("data/processed/events.parquet")
    assert "ret_15m_index_adj" in df.columns
    assert "t_0_source" in df.columns
    assert "contaminated" in df.columns
