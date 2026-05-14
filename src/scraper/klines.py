"""Binance public klines (OHLCV) fetcher.

Wraps the Binance Spot REST endpoint `/api/v3/klines` and persists 1-minute
bars per symbol as Parquet partitioned by year/month.

See: https://developers.binance.com/docs/binance-spot-api-docs/rest-api
"""

from __future__ import annotations

from datetime import datetime


def fetch_klines(
    symbol: str,
    start: datetime,
    end: datetime,
    interval: str = "1m",
    output_dir: str = "data/raw/klines",
) -> int:
    """Fetch klines for one symbol in [start, end] and persist as Parquet.

    Returns the number of bars written.
    """
    raise NotImplementedError("Implement in Phase 1. See docs/03-project-plan.md.")
