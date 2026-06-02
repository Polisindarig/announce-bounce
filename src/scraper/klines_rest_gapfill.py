"""Fill missing ``{PAIR}.parquet`` via Binance REST (1m), for pairs absent from Vision.

Fetches only **event windows** around ``published_at`` (not the full data window),
so gap-fill finishes in minutes instead of hours per symbol.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import time

import httpx
import pandas as pd

from src.scraper.klines import fetch_klines, save_klines_parquet

logger = logging.getLogger(__name__)


def pairs_missing_klines(
    jsonl_path: Path, klines_dir: Path, use_pairs_field: bool = True
) -> list[str]:
    need: set[str] = set()
    with open(jsonl_path) as f:
        for line in f:
            row = json.loads(line)
            if use_pairs_field and row.get("extracted_pairs"):
                need.update(row["extracted_pairs"])
            else:
                for s in row.get("extracted_symbols", []):
                    need.add(f"{s}USDT")
    have = {p.stem for p in klines_dir.glob("*.parquet")}
    return sorted(need - have)


def event_windows_for_pairs(
    jsonl_path: Path,
    pairs: set[str],
    pre_hours: float = 2.0,
    post_hours: float = 26.0,
) -> dict[str, list[tuple[datetime, datetime]]]:
    """Per pair: merged [start, end] windows around each announcement time."""
    raw: dict[str, list[tuple[datetime, datetime]]] = {p: [] for p in pairs}

    with open(jsonl_path) as f:
        for line in f:
            row = json.loads(line)
            pub = row.get("published_at")
            if not pub:
                continue
            ann_pairs = row.get("extracted_pairs") or []
            if not ann_pairs:
                continue

            event_dt = datetime.fromisoformat(str(pub).replace("Z", "+00:00"))
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=timezone.utc)

            start = event_dt - timedelta(hours=pre_hours)
            end = event_dt + timedelta(hours=post_hours)

            for pair in ann_pairs:
                if pair in raw:
                    raw[pair].append((start, end))

    merged: dict[str, list[tuple[datetime, datetime]]] = {}
    for pair, wins in raw.items():
        if not wins:
            continue
        wins.sort()
        result = [wins[0]]
        for s, e in wins[1:]:
            if s <= result[-1][1]:
                result[-1] = (result[-1][0], max(result[-1][1], e))
            else:
                result.append((s, e))
        merged[pair] = result
    return merged


def collapse_to_single_span(
    windows: dict[str, list[tuple[datetime, datetime]]],
) -> dict[str, list[tuple[datetime, datetime]]]:
    """One REST pull per symbol (min start → max end) instead of hundreds of windows."""
    out: dict[str, list[tuple[datetime, datetime]]] = {}
    for pair, wins in windows.items():
        if not wins:
            continue
        out[pair] = [(min(s for s, _ in wins), max(e for _, e in wins))]
    return out


def fetch_pair_event_windows(
    symbol: str,
    windows: list[tuple[datetime, datetime]],
    client: httpx.Client,
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for start, end in windows:
        df = fetch_klines(symbol, start, end, client=client)
        if not df.empty:
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    out = out.drop_duplicates(subset=["open_time"]).sort_values("open_time")
    return out.reset_index(drop=True)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="REST gap-fill for missing kline parquets")
    parser.add_argument(
        "--symbols-from",
        default=str(root / "data" / "processed" / "announcements_with_symbols_june2025.jsonl"),
    )
    parser.add_argument("--klines-dir", default=str(root / "data" / "raw" / "klines"))
    parser.add_argument("symbols", nargs="*", help="Optional explicit symbols (else --only-missing)")
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Use pairs from JSONL that have no parquet yet",
    )
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument(
        "--delay-s",
        type=float,
        default=0.35,
        help="Pause between symbols (rate limit)",
    )
    parser.add_argument(
        "--multi-window",
        action="store_true",
        help="Keep separate windows per announcement (default: one span per symbol)",
    )
    parser.add_argument(
        "--pre-hours",
        type=float,
        default=2.0,
        help="Hours before published_at to fetch",
    )
    parser.add_argument(
        "--post-hours",
        type=float,
        default=26.0,
        help="Hours after published_at (covers ret_24h)",
    )
    args = parser.parse_args()

    kdir = Path(args.klines_dir)
    jsonl = Path(args.symbols_from)

    if args.symbols:
        symbols = list(args.symbols)
    elif args.only_missing:
        symbols = pairs_missing_klines(jsonl, kdir)
    else:
        raise SystemExit("Pass symbol names or --only-missing")

    if args.max_symbols > 0:
        symbols = symbols[: args.max_symbols]

    pair_windows = event_windows_for_pairs(
        jsonl, set(symbols), pre_hours=args.pre_hours, post_hours=args.post_hours
    )
    if not args.multi_window:
        pair_windows = collapse_to_single_span(pair_windows)

    logger.info(
        "REST event-window gap-fill for %d symbols (%d with announcement windows)",
        len(symbols),
        len(pair_windows),
    )

    ok = 0
    client = httpx.Client(timeout=60, follow_redirects=True)
    try:
        for i, sym in enumerate(symbols):
            logger.info("[%d/%d] %s", i + 1, len(symbols), sym)
            wins = pair_windows.get(sym)
            if not wins:
                logger.warning("%s: no announcements with this pair in %s", sym, jsonl)
                continue
            try:
                df = fetch_pair_event_windows(sym, wins, client)
            except Exception as e:
                logger.warning("%s: fetch failed: %s", sym, e)
                continue
            if df.empty:
                logger.warning("%s: no bars from REST (invalid pair or outside listing window)", sym)
                continue
            save_klines_parquet(df, sym, kdir)
            logger.info("%s: saved %d bars across %d window(s)", sym, len(df), len(wins))
            ok += 1
            if args.delay_s > 0 and i + 1 < len(symbols):
                time.sleep(args.delay_s)
    finally:
        client.close()

    logger.info("Saved %d / %d symbols", ok, len(symbols))


if __name__ == "__main__":
    main()
