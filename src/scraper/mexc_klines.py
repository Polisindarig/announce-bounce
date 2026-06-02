"""MEXC spot OHLCV for announcement-time prices (often before Binance listing).

**June 2025 onward:** many pairs have usable **5m** history on public v3 while **1m** is
empty for the same window — use ``interval: 5m`` and ``published_after: 2025-06-01…`` in
YAML (see ``config/mexc_5m_from_june2025.yaml``).

Uses public ``GET /api/v3/klines`` (default interval ``1m``; set ``interval: 60m`` in YAML
or ``--interval 60m`` for hourly candles — MEXC spot uses ``60m``, not ``1h``).

**Important (data retention):** MEXC public klines often return **no rows**
for fine intervals far in the past (empirically: multi-year backfill is unreliable vs Binance
Vision). For a 30-month thesis window you may need **another venue** (e.g. Gate/KuCoin) or
**coarser interval** / paid archives. This module still automates pulls when data exists.

Output Parquet columns align with ``klines.py`` so ``event_table`` can use
``--klines-dir data/raw/mexc_klines``.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


def _parse_optional_iso_dt(value: object) -> datetime | None:
    """Parse YAML/CLI date string to UTC ``datetime``; ``None`` / empty → ``None``."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


MEXC_KLINES_URL = "https://api.mexc.com/api/v3/klines"
MAX_CANDLES = 1000
MINUTE_MS = 60_000

# Spot v3 ``interval`` values include: 1m, 5m, 15m, 30m, 60m (hourly), 4h, 1d, …
# Use ``60m`` for 1-hour candles (``1h`` is not accepted on MEXC spot v3).
INTERVAL_MS = {
    "1m": MINUTE_MS,
    "3m": 3 * MINUTE_MS,
    "5m": 5 * MINUTE_MS,
    "15m": 15 * MINUTE_MS,
    "30m": 30 * MINUTE_MS,
    "60m": 60 * MINUTE_MS,
    "4h": 4 * 60 * MINUTE_MS,
}


def _mexc_exchange():
    import ccxt

    return ccxt.mexc(
        {
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
    )


def resolve_mexc_symbol(exchange, pair: str) -> str | None:
    """Map `BTCUSDT` → CCXT unified `BTC/USDT` if spot market exists."""
    if not pair.endswith("USDT"):
        return None
    base = pair[:-4]
    sym = f"{base}/USDT"
    m = exchange.markets.get(sym)
    if not m:
        return None
    if not m.get("spot", True):
        return None
    if m.get("active") is False:
        return None
    return sym


def fetch_ohlcv_range_http(
    pair: str,
    start: datetime,
    end: datetime,
    client: httpx.Client | None = None,
    interval: str = "1m",
) -> pd.DataFrame:
    """Paginated MEXC spot klines. ``pair`` is MEXC native id, e.g. ``BTCUSDT``."""
    step_ms = INTERVAL_MS.get(interval)
    if not step_ms:
        raise ValueError(f"Unsupported interval {interval!r}; allowed: {sorted(INTERVAL_MS)}")

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    own = client is None
    if own:
        client = httpx.Client(timeout=60.0, follow_redirects=True)

    rows: list[list] = []
    cursor = start_ms
    try:
        while cursor <= end_ms:
            chunk_end = min(cursor + MAX_CANDLES * step_ms - 1, end_ms)
            resp = client.get(
                MEXC_KLINES_URL,
                params={
                    "symbol": pair,
                    "interval": interval,
                    "startTime": cursor,
                    "endTime": chunk_end,
                    "limit": MAX_CANDLES,
                },
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            for c in batch:
                ts = int(c[0])
                if ts < start_ms or ts > end_ms:
                    continue
                rows.append(c)
            last_ts = int(batch[-1][0])
            nxt = last_ts + step_ms
            if nxt <= cursor:
                break
            cursor = nxt
            if last_ts >= end_ms:
                break
    finally:
        if own:
            client.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        rows,
        columns=[
            "open_time_ms",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time_ms",
            "quote_volume",
        ],
    )
    df["open_time"] = pd.to_datetime(df["open_time_ms"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time_ms"], unit="ms", utc=True)
    df = df.drop(columns=["open_time_ms", "close_time_ms"])
    df["symbol"] = pair
    for c in ("open", "high", "low", "close", "volume", "quote_volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time")
    return df[
        [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "symbol",
        ]
    ]


def resolve_mexc_native_id(exchange, pair: str) -> str | None:
    """Return MEXC REST ``symbol`` id (e.g. ``BTCUSDT``) for our ``PAIR`` key."""
    sym = resolve_mexc_symbol(exchange, pair)
    if not sym:
        return None
    m = exchange.markets[sym]
    return str(m.get("id", sym.replace("/", "")))


def save_parquet(df: pd.DataFrame, pair: str, output_dir: Path) -> Path | None:
    if df.empty:
        return None
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{pair}.parquet"
    df.to_parquet(path, index=False)
    logger.info("Saved %d MEXC bars → %s", len(df), path)
    return path


def _merge_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    intervals = sorted(intervals)
    out = [intervals[0]]
    for s, e in intervals[1:]:
        ps, pe = out[-1]
        if s <= pe:
            out[-1] = (ps, max(pe, e))
        else:
            out.append((s, e))
    return out


def collect_windows_by_pair(
    announcements_path: Path,
    catalogs: set[str] | None,
    pre_hours: float,
    post_hours: float,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
) -> dict[str, list[tuple[datetime, datetime]]]:
    """Per `PAIR` (e.g. SOLUSDT), merged [t0-pre, t0+post] windows.

    If ``published_after`` / ``published_before`` are set, only announcements whose
    ``published_at`` falls in ``[after, before]`` (inclusive) are used.
    """
    by_pair: dict[str, list[tuple[datetime, datetime]]] = {}

    with open(announcements_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if catalogs is not None and row.get("catalog_name") not in catalogs:
                continue
            pub = row.get("published_at")
            pairs = row.get("extracted_pairs") or []
            if not pub or not pairs:
                continue
            t0 = datetime.fromisoformat(pub)
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
            if published_after is not None and t0 < published_after:
                continue
            if published_before is not None and t0 > published_before:
                continue
            start = t0 - timedelta(hours=pre_hours)
            end = t0 + timedelta(hours=post_hours)
            for pair in pairs:
                if not pair.endswith("USDT"):
                    continue
                by_pair.setdefault(pair, []).append((start, end))

    merged: dict[str, list[tuple[datetime, datetime]]] = {}
    for pair, wins in by_pair.items():
        merged[pair] = _merge_intervals(wins)
    return merged


def filtered_announcement_stats(
    announcements_path: Path,
    catalogs: set[str] | None,
    published_after: datetime | None,
    published_before: datetime | None,
) -> dict[str, object]:
    """Counts rows that contribute to ``collect_windows_by_pair`` (USDT pairs, catalog, dates)."""
    n_ann = 0
    usdt_pairs: set[str] = set()
    t_min: datetime | None = None
    t_max: datetime | None = None

    with open(announcements_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if catalogs is not None and row.get("catalog_name") not in catalogs:
                continue
            pub = row.get("published_at")
            pairs = row.get("extracted_pairs") or []
            if not pub or not pairs:
                continue
            t0 = datetime.fromisoformat(pub)
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
            if published_after is not None and t0 < published_after:
                continue
            if published_before is not None and t0 > published_before:
                continue
            up = [p for p in pairs if isinstance(p, str) and p.endswith("USDT")]
            if not up:
                continue
            n_ann += 1
            for p in up:
                usdt_pairs.add(p)
            if t_min is None or t0 < t_min:
                t_min = t0
            if t_max is None or t0 > t_max:
                t_max = t0

    return {
        "n_announcements": n_ann,
        "n_unique_usdt_pairs": len(usdt_pairs),
        "published_at_min": t_min.isoformat() if t_min else None,
        "published_at_max": t_max.isoformat() if t_max else None,
    }


def download_mexc_for_announcements(
    announcements_path: Path,
    output_dir: Path,
    catalogs: set[str] | None,
    pre_hours: float,
    post_hours: float,
    sleep_between_symbols_s: float = 0.35,
    fetch_btc_baseline: bool = True,
    interval: str = "1m",
    published_after: datetime | None = None,
    published_before: datetime | None = None,
) -> dict[str, Path | None]:
    """Fetch MEXC OHLCV for each pair window; optionally BTCUSDT baseline on MEXC."""
    exchange = _mexc_exchange()
    exchange.load_markets()
    output_dir = Path(output_dir)
    results: dict[str, Path | None] = {}

    windows = collect_windows_by_pair(
        announcements_path,
        catalogs,
        pre_hours,
        post_hours,
        published_after=published_after,
        published_before=published_before,
    )

    http_client = httpx.Client(timeout=60.0, follow_redirects=True)
    try:
        if fetch_btc_baseline:
            native = resolve_mexc_native_id(exchange, "BTCUSDT")
            if native:
                all_btc: list[tuple[datetime, datetime]] = []
                for wins in windows.values():
                    all_btc.extend(wins)
                if all_btc:
                    bs = min(s for s, _ in all_btc)
                    be = max(e for _, e in all_btc)
                    p = output_dir / "BTCUSDT.parquet"
                    if p.exists():
                        logger.info("BTCUSDT MEXC already exists, skipping baseline fetch")
                        results["BTCUSDT"] = p
                    else:
                        logger.info("Fetching MEXC baseline %s %s → %s", native, bs, be)
                        df = fetch_ohlcv_range_http(native, bs, be, http_client, interval=interval)
                        results["BTCUSDT"] = save_parquet(df, "BTCUSDT", output_dir)
                    time.sleep(sleep_between_symbols_s)

        pairs = sorted(windows.keys())
        for i, pair in enumerate(pairs):
            native = resolve_mexc_native_id(exchange, pair)
            if not native:
                logger.info("[%d/%d] %s — no MEXC spot market", i + 1, len(pairs), pair)
                results[pair] = None
                continue
            out_path = output_dir / f"{pair}.parquet"
            if out_path.exists():
                logger.info("[%d/%d] %s already exists, skipping", i + 1, len(pairs), pair)
                results[pair] = out_path
                time.sleep(sleep_between_symbols_s)
                continue

            wins = windows[pair]
            overall_start = min(s for s, _ in wins)
            overall_end = max(e for _, e in wins)
            logger.info(
                "[%d/%d] %s (%s) %s → %s",
                i + 1,
                len(pairs),
                pair,
                native,
                overall_start,
                overall_end,
            )
            try:
                df = fetch_ohlcv_range_http(native, overall_start, overall_end, http_client, interval=interval)
                results[pair] = save_parquet(df, pair, output_dir)
            except Exception as e:
                logger.warning("Failed %s: %s", pair, e)
                results[pair] = None
            time.sleep(sleep_between_symbols_s)
    finally:
        http_client.close()

    ok = sum(1 for v in results.values() if v is not None)
    logger.info("MEXC download finished: %d parquet paths (incl. skips)", ok)
    return results


def main() -> None:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="MEXC 1m klines around announcements")
    parser.add_argument(
        "--config",
        default=str(root / "config" / "mexc.yaml"),
        help="YAML with catalogs, pre/post hours, output_dir",
    )
    parser.add_argument(
        "--announcements",
        default=str(root / "data" / "processed" / "announcements_with_symbols.jsonl"),
    )
    parser.add_argument(
        "--interval",
        default="",
        help="Kline interval for REST v3 (default: from config or 1m). Example: 60m for hourly.",
    )
    parser.add_argument("--no-btc", action="store_true", help="Skip MEXC BTCUSDT baseline")
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only print announcement counts for the same filters (no MEXC download).",
    )
    parser.add_argument(
        "--published-after",
        default="",
        help="ISO datetime UTC (overrides YAML). Example: 2025-06-01T00:00:00+00:00",
    )
    parser.add_argument(
        "--published-before",
        default="",
        help="ISO datetime UTC inclusive upper bound (overrides YAML). Omit for open-ended.",
    )
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    cats = cfg.get("catalogs") or []
    catalog_set = set(cats) if cats else None

    interval = args.interval or cfg.get("interval", "1m")

    pub_after = _parse_optional_iso_dt(
        args.published_after or cfg.get("published_after")
    )
    pub_before = _parse_optional_iso_dt(
        args.published_before or cfg.get("published_before")
    )

    ann_path = Path(args.announcements)
    if args.stats_only:
        st = filtered_announcement_stats(
            ann_path, catalog_set, pub_after, pub_before
        )
        print(
            "announcements_path",
            str(ann_path),
            "catalogs",
            sorted(catalog_set) if catalog_set else None,
            "published_after",
            pub_after.isoformat() if pub_after else None,
            "published_before",
            pub_before.isoformat() if pub_before else None,
        )
        for k, v in st.items():
            print(f"{k}: {v}")
        return

    download_mexc_for_announcements(
        announcements_path=ann_path,
        output_dir=Path(cfg.get("output_dir", "data/raw/mexc_klines")),
        catalogs=catalog_set,
        pre_hours=float(cfg.get("pre_hours", 2.0)),
        post_hours=float(cfg.get("post_hours", 26.0)),
        sleep_between_symbols_s=float(cfg.get("sleep_between_symbols_s", 0.35)),
        fetch_btc_baseline=not args.no_btc,
        interval=interval,
        published_after=pub_after,
        published_before=pub_before,
    )


if __name__ == "__main__":
    main()
