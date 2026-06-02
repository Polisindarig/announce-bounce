"""Bulk kline downloader using data.binance.vision (no rate limits).

Downloads monthly/daily 1-minute kline ZIP files from Binance's public
data repository. Much faster than the REST API approach.

Usage:
    python -m src.scraper.klines_bulk BTCUSDT --config config/data_window.yaml
    python -m src.scraper.klines_bulk --symbols-from data/raw/announcements_enriched.jsonl
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

VISION_BASE = "https://data.binance.vision/data/spot/monthly/klines"
DAILY_BASE = "https://data.binance.vision/data/spot/daily/klines"

COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]


def _download_zip(client: httpx.Client, url: str) -> bytes | None:
    try:
        resp = client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        logger.warning("Download failed: %s — %s", url, e)
        return None


def _parse_kline_csv(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            df = pd.read_csv(f, header=None, names=COLUMNS)
    return df


def download_symbol_klines(
    symbol: str,
    start: datetime,
    end: datetime,
    output_dir: str | Path = "data/raw/klines",
) -> Path | None:
    """Download 1m klines for a symbol from data.binance.vision."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{symbol}.parquet"

    if out_path.exists() and not getattr(download_symbol_klines, "_force", False):
        existing = pd.read_parquet(out_path)
        if len(existing) > 0:
            logger.info("Already have %d bars for %s, skipping", len(existing), symbol)
            return out_path

    all_dfs: list[pd.DataFrame] = []
    consecutive_misses = 0
    client = httpx.Client(timeout=60, follow_redirects=True)

    try:
        current = datetime(start.year, start.month, 1)
        end_month = datetime(end.year, end.month, 1)

        while current <= end_month:
            ym = f"{current.year}-{current.month:02d}"
            url = f"{VISION_BASE}/{symbol}/1m/{symbol}-1m-{ym}.zip"
            logger.info("Downloading %s %s", symbol, ym)

            zip_bytes = _download_zip(client, url)
            if zip_bytes:
                df = _parse_kline_csv(zip_bytes)
                all_dfs.append(df)
                consecutive_misses = 0
            else:
                # Try a few sample days instead of all 30
                import calendar
                days_in_month = calendar.monthrange(current.year, current.month)[1]
                sample_days = [1, 10, 20, min(days_in_month, 28)]
                found_any = False
                for day in sample_days:
                    d = datetime(current.year, current.month, day, tzinfo=timezone.utc)
                    if d < start or d > end:
                        continue
                    ds = f"{d.year}-{d.month:02d}-{d.day:02d}"
                    daily_url = f"{DAILY_BASE}/{symbol}/1m/{symbol}-1m-{ds}.zip"
                    zb = _download_zip(client, daily_url)
                    if zb:
                        found_any = True
                        break

                if found_any:
                    # This month has data — fetch all days
                    for day in range(1, days_in_month + 1):
                        d = datetime(current.year, current.month, day, tzinfo=timezone.utc)
                        if d < start or d > end:
                            continue
                        ds = f"{d.year}-{d.month:02d}-{d.day:02d}"
                        daily_url = f"{DAILY_BASE}/{symbol}/1m/{symbol}-1m-{ds}.zip"
                        zb = _download_zip(client, daily_url)
                        if zb:
                            all_dfs.append(_parse_kline_csv(zb))
                    consecutive_misses = 0
                else:
                    consecutive_misses += 1
                    if consecutive_misses >= 3 and not all_dfs:
                        logger.info("Skipping %s — no data found after 3 consecutive months", symbol)
                        break

            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)

    finally:
        client.close()

    if not all_dfs:
        logger.warning("No kline data found for %s", symbol)
        return None

    df = pd.concat(all_dfs, ignore_index=True)
    df = df.drop_duplicates(subset=["open_time"])
    df = df.sort_values("open_time").reset_index(drop=True)

    for col in ["open_time", "close_time"]:
        vals = pd.to_numeric(df[col], errors="coerce")
        # Binance switched to microseconds for spot data from 2025-01-01
        mask_us = vals > 1e15
        vals[mask_us] = vals[mask_us] // 1000
        df[col] = pd.to_datetime(vals, unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume", "quote_volume",
                 "taker_buy_base", "taker_buy_quote"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["trades"] = df["trades"].astype(int)
    df = df.drop(columns=["ignore"], errors="ignore")
    df["symbol"] = symbol

    ts_start = pd.Timestamp(start.replace(tzinfo=None), tz="UTC")
    ts_end = pd.Timestamp(end.replace(tzinfo=None), tz="UTC")
    df = df[(df["open_time"] >= ts_start) & (df["open_time"] <= ts_end)]

    df.to_parquet(out_path, index=False, engine="pyarrow")
    logger.info("Saved %d bars for %s → %s", len(df), symbol, out_path)
    return out_path


def download_multiple(
    symbols: list[str],
    start: datetime,
    end: datetime,
    output_dir: str | Path = "data/raw/klines",
) -> dict[str, Path | None]:
    results = {}
    for i, sym in enumerate(symbols):
        logger.info("=== [%d/%d] %s ===", i + 1, len(symbols), sym)
        results[sym] = download_symbol_klines(sym, start, end, output_dir)
    return results


if __name__ == "__main__":
    import argparse
    import json

    import yaml

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Bulk kline download from data.binance.vision")
    parser.add_argument("symbols", nargs="*", help="Symbols like BTCUSDT ETHUSDT")
    parser.add_argument("--symbols-from", help="JSONL file to extract symbols from")
    parser.add_argument("--config", default="config/data_window.yaml")
    parser.add_argument("--output-dir", default="data/raw/klines")
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Keep only symbols with no parquet yet in --output-dir",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=0,
        help="Cap symbol count after filters (0 = no cap)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if parquet already exists",
    )
    args = parser.parse_args()

    download_symbol_klines._force = args.force  # type: ignore[attr-defined]

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    start = datetime.fromisoformat(cfg["window_start"]).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(cfg["window_end"]).replace(tzinfo=timezone.utc)

    symbols = list(args.symbols) if args.symbols else []

    if args.symbols_from:
        seen = set(symbols)
        with open(args.symbols_from) as f:
            for line in f:
                row = json.loads(line)
                pairs = row.get("extracted_pairs") or []
                if pairs:
                    for pair in pairs:
                        if pair not in seen:
                            symbols.append(pair)
                            seen.add(pair)
                    continue
                for s in row.get("extracted_symbols", []):
                    pair = s + "USDT"
                    if pair not in seen:
                        symbols.append(pair)
                        seen.add(pair)

    if not symbols:
        symbols = ["BTCUSDT"]

    out_dir = Path(args.output_dir)
    if args.only_missing:
        before = len(symbols)
        symbols = [s for s in symbols if not (out_dir / f"{s}.parquet").exists()]
        print(f"--only-missing: {before} → {len(symbols)} symbols without parquet")

    if args.max_symbols > 0:
        symbols = symbols[: args.max_symbols]

    print(f"Downloading klines for {len(symbols)} symbols: {start.date()} → {end.date()}")
    results = download_multiple(symbols, start, end, args.output_dir)
    ok = sum(1 for v in results.values() if v is not None)
    print(f"\nDone: {ok}/{len(results)} symbols downloaded")
