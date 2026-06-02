"""Event-window kline downloader.

For each announcement with extracted symbols, download only the months
around the event (the event month + previous month). This is much faster
than downloading 30 months for every coin.

Also downloads BTCUSDT for the full 30-month window (baseline).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.scraper.klines_bulk import download_symbol_klines

logger = logging.getLogger(__name__)


def collect_needed_windows(
    announcements_path: str | Path,
) -> dict[str, list[tuple[datetime, datetime]]]:
    """Parse announcements and collect (start, end) windows per symbol."""
    windows: dict[str, list[tuple[datetime, datetime]]] = {}

    with open(announcements_path) as f:
        for line in f:
            row = json.loads(line)
            pub = row.get("published_at")
            if not pub:
                continue
            pairs = row.get("extracted_pairs", [])
            if not pairs:
                continue

            event_dt = datetime.fromisoformat(pub)
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=timezone.utc)

            # Window: 1 month before event to 1 month after
            m = event_dt.month
            y = event_dt.year

            if m == 1:
                start = datetime(y - 1, 12, 1, tzinfo=timezone.utc)
            else:
                start = datetime(y, m - 1, 1, tzinfo=timezone.utc)

            if m >= 11:
                end_m = (m + 2 - 1) % 12 + 1
                end_y = y + 1 if m + 1 > 12 else y
            else:
                end_m = m + 2
                end_y = y
            end = datetime(end_y, end_m, 1, tzinfo=timezone.utc)

            for pair in pairs:
                if pair not in windows:
                    windows[pair] = []
                windows[pair].append((start, end))

    # Merge overlapping windows per symbol
    merged: dict[str, list[tuple[datetime, datetime]]] = {}
    for pair, wins in windows.items():
        wins.sort()
        result = [wins[0]]
        for s, e in wins[1:]:
            if s <= result[-1][1]:
                result[-1] = (result[-1][0], max(result[-1][1], e))
            else:
                result.append((s, e))
        merged[pair] = result

    return merged


def download_event_klines(
    announcements_path: str | Path,
    output_dir: str | Path = "data/raw/klines",
) -> dict[str, Path | None]:
    """Download klines only for event windows."""
    windows = collect_needed_windows(announcements_path)
    output_dir = Path(output_dir)
    results: dict[str, Path | None] = {}

    total = len(windows)
    logger.info("Downloading event-window klines for %d symbols", total)

    for i, (pair, wins) in enumerate(sorted(windows.items())):
        out_path = output_dir / f"{pair}.parquet"
        if out_path.exists():
            logger.info("[%d/%d] %s already exists, skipping", i + 1, total, pair)
            results[pair] = out_path
            continue

        logger.info("[%d/%d] %s — %d window(s)", i + 1, total, pair, len(wins))

        # Use the merged windows' overall start/end
        overall_start = min(s for s, _ in wins)
        overall_end = max(e for _, e in wins)

        try:
            path = download_symbol_klines(pair, overall_start, overall_end, output_dir)
            results[pair] = path
        except Exception as e:
            logger.error("Failed %s: %s", pair, e)
            results[pair] = None

    ok = sum(1 for v in results.values() if v is not None)
    logger.info("Done: %d/%d symbols downloaded", ok, total)
    return results


if __name__ == "__main__":
    import argparse

    import yaml

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--announcements", default="data/processed/announcements_with_symbols.jsonl")
    parser.add_argument("--output-dir", default="data/raw/klines")
    parser.add_argument("--config", default="config/data_window.yaml")
    args = parser.parse_args()

    # Also ensure BTCUSDT baseline exists
    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    start = datetime.fromisoformat(cfg["window_start"]).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(cfg["window_end"]).replace(tzinfo=timezone.utc)

    btc_path = Path(args.output_dir) / "BTCUSDT.parquet"
    if not btc_path.exists():
        print("Downloading BTCUSDT baseline...")
        download_symbol_klines("BTCUSDT", start, end, args.output_dir)
    else:
        print("BTCUSDT baseline already exists")

    # Download event windows
    results = download_event_klines(args.announcements, args.output_dir)
    ok = sum(1 for v in results.values() if v is not None)
    print(f"\nDone: {ok}/{len(results)} symbols")
