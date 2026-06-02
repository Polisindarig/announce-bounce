"""Phase 1 orchestrator — run all data acquisition steps in sequence.

Usage:
    python -m src.scraper.run_phase1 [--config config/data_window.yaml]

Steps:
    1. Scrape announcements → data/raw/announcements.jsonl
    2. Extract symbols → data/processed/announcements_with_symbols.jsonl
    3. Fetch BTCUSDT continuous klines (baseline)
    4. Fetch event-window klines for each announcement's extracted symbols
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from src.scraper.announcements import scrape_announcements
from src.scraper.klines import fetch_continuous, fetch_event_window, save_klines_parquet
from src.scraper.symbol_extractor import fetch_binance_symbols, process_announcements

logger = logging.getLogger(__name__)


def run(config_path: str = "config/data_window.yaml"):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    start = datetime.fromisoformat(cfg["window_start"]).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(cfg["window_end"]).replace(tzinfo=timezone.utc)

    raw_jsonl = Path("data/raw/announcements.jsonl")
    enriched_jsonl = Path("data/processed/announcements_with_symbols.jsonl")

    # --- Step 1: Scrape announcements ---
    logger.info("=" * 60)
    logger.info("STEP 1: Scraping Binance announcements")
    logger.info("=" * 60)
    result = scrape_announcements(start, end, raw_jsonl)
    logger.info("Scrape result: %d written, %d errors", result.total_written, len(result.errors))

    # --- Step 2: Extract symbols ---
    logger.info("=" * 60)
    logger.info("STEP 2: Extracting symbols from announcements")
    logger.info("=" * 60)
    n = process_announcements(raw_jsonl, enriched_jsonl)
    logger.info("Enriched %d announcements with symbols", n)

    # --- Step 3: Fetch BTC baseline klines ---
    logger.info("=" * 60)
    logger.info("STEP 3: Fetching BTCUSDT continuous klines (baseline)")
    logger.info("=" * 60)
    client = httpx.Client(timeout=30, follow_redirects=True)
    try:
        fetch_continuous("BTCUSDT", start, end, client=client)
    finally:
        client.close()

    # --- Step 4: Fetch event-window klines per announcement ---
    logger.info("=" * 60)
    logger.info("STEP 4: Fetching event-window klines for each symbol")
    logger.info("=" * 60)

    fetched_symbols: set[str] = set()
    events_dir = Path("data/raw/klines")
    client = httpx.Client(timeout=30, follow_redirects=True)

    try:
        with open(enriched_jsonl) as f:
            for line in f:
                ann = json.loads(line)
                pairs = ann.get("extracted_pairs", [])
                event_time_str = ann.get("published_at", "")
                if not event_time_str or not pairs:
                    continue

                event_time = datetime.fromisoformat(event_time_str)

                for pair in pairs:
                    if pair in fetched_symbols:
                        continue

                    logger.info("Fetching event klines for %s around %s", pair, event_time_str)
                    try:
                        df = fetch_event_window(pair, event_time, client=client)
                        if not df.empty:
                            save_klines_parquet(df, pair, events_dir)
                        fetched_symbols.add(pair)
                    except Exception as e:
                        logger.warning("Failed %s: %s", pair, e)
    finally:
        client.close()

    logger.info("=" * 60)
    logger.info("PHASE 1 COMPLETE")
    logger.info("  Announcements: %s", raw_jsonl)
    logger.info("  Enriched: %s", enriched_jsonl)
    logger.info("  Klines fetched for %d symbols", len(fetched_symbols))
    logger.info("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/data_window.yaml")
    args = parser.parse_args()
    run(args.config)
