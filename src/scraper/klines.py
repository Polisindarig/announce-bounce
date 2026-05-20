"""Binance 1-minute OHLCV kline fetcher.

Pulls historical klines from the public Binance REST API:
  GET /api/v3/klines

Stores as Parquet partitioned by symbol/year/month.

See docs/03-project-plan.md Phase 1, Task 4.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


def _retryable_klines_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code in (429, 418, 500, 502, 503, 504)
    return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout))

logger = logging.getLogger(__name__)

KLINES_URL = "https://api.binance.com/api/v3/klines"
MAX_BARS_PER_REQUEST = 1000
REQUEST_DELAY_S = 0.5  # Binance allows ~1200 weight/min; klines = 2 weight

COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_buy_base",
    "taker_buy_quote",
    "ignore",
]


@retry(
    retry=retry_if_exception(_retryable_klines_error),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
)
def _fetch_klines_page(
    client: httpx.Client,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    limit: int = MAX_BARS_PER_REQUEST,
) -> list[list]:
    resp = client.get(
        KLINES_URL,
        params={
            "symbol": symbol,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": limit,
        },
    )
    resp.raise_for_status()
    return resp.json()


def fetch_klines(
    symbol: str,
    start: datetime,
    end: datetime,
    interval: str = "1m",
    client: httpx.Client | None = None,
) -> pd.DataFrame:
    """Fetch klines for a symbol in [start, end]. Returns a DataFrame."""
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=30, follow_redirects=True)

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    all_bars: list[list] = []

    try:
        cursor_ms = start_ms
        while cursor_ms < end_ms:
            try:
                bars = _fetch_klines_page(client, symbol, interval, cursor_ms, end_ms)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (400, 404):
                    break
                raise
            if not bars:
                break

            all_bars.extend(bars)
            last_open = bars[-1][0]
            cursor_ms = last_open + 60_000  # next minute

            if len(bars) < MAX_BARS_PER_REQUEST:
                break

            time.sleep(REQUEST_DELAY_S)
    finally:
        if own_client:
            client.close()

    if not all_bars:
        return pd.DataFrame(columns=COLUMNS)

    df = pd.DataFrame(all_bars, columns=COLUMNS)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

    for col in ["open", "high", "low", "close", "volume", "quote_volume",
                 "taker_buy_base", "taker_buy_quote"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["trades"] = df["trades"].astype(int)
    df = df.drop(columns=["ignore"])
    df["symbol"] = symbol

    return df


def save_klines_parquet(
    df: pd.DataFrame,
    symbol: str,
    output_dir: str | Path = "data/raw/klines",
) -> Path:
    """Save klines DataFrame as a single Parquet file per symbol."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{symbol}.parquet"
    df.to_parquet(path, index=False, engine="pyarrow")
    logger.info("Saved %d bars for %s → %s", len(df), symbol, path)
    return path


def fetch_event_window(
    symbol: str,
    event_time: datetime,
    pre_hours: float = 2.0,
    post_hours: float = 25.0,
    client: httpx.Client | None = None,
) -> pd.DataFrame:
    """Fetch klines around an event: [t0 - pre_hours, t0 + post_hours]."""
    start = event_time - timedelta(hours=pre_hours)
    end = event_time + timedelta(hours=post_hours)
    return fetch_klines(symbol, start, end, client=client)


def fetch_continuous(
    symbol: str,
    start: datetime,
    end: datetime,
    output_dir: str | Path = "data/raw/klines",
    client: httpx.Client | None = None,
) -> Path:
    """Fetch full continuous klines for a symbol over the entire window."""
    logger.info("Fetching continuous klines for %s: %s → %s", symbol, start, end)
    df = fetch_klines(symbol, start, end, client=client)
    if df.empty:
        logger.warning("No data for %s", symbol)
        return Path(output_dir) / f"{symbol}.parquet"
    return save_klines_parquet(df, symbol, output_dir)


if __name__ == "__main__":
    import argparse

    import yaml

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Fetch Binance klines")
    parser.add_argument("symbol", help="Trading pair (e.g. BTCUSDT)")
    parser.add_argument("--config", default="config/data_window.yaml")
    parser.add_argument("--output-dir", default="data/raw/klines")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    start = datetime.fromisoformat(cfg["window_start"]).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(cfg["window_end"]).replace(tzinfo=timezone.utc)

    path = fetch_continuous(args.symbol, start, end, args.output_dir)
    print(f"Saved to {path}")
