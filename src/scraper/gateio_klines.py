"""Gate.io spot 1-minute OHLCV (public API via CCXT).

Useful when another venue (e.g. MEXC) has gaps for older windows. Output columns match
``klines.py`` / ``mexc_klines.py`` for downstream ``event_table`` use.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml

from src.scraper.mexc_klines import _parse_optional_iso_dt, collect_windows_by_pair

logger = logging.getLogger(__name__)

MINUTE_MS = 60_000
OHLCV_LIMIT = 1000


def _gateio_exchange():
    import ccxt

    return ccxt.gateio(
        {
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
    )


def resolve_gateio_symbol(exchange, pair: str) -> str | None:
    """Map ``BTCUSDT`` → CCXT unified ``BTC/USDT`` if spot market exists."""
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


def fetch_ohlcv_range_ccxt(
    exchange,
    unified_symbol: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Paginated 1m OHLCV between ``start`` and ``end`` (UTC)."""
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    since = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    raw: list[list] = []
    cursor = since
    while cursor < end_ms:
        batch = exchange.fetch_ohlcv(
            unified_symbol, "1m", since=cursor, limit=OHLCV_LIMIT
        )
        if not batch:
            break
        for c in batch:
            ts = int(c[0])
            if ts < since or ts > end_ms:
                continue
            raw.append(c)
        last_ts = int(batch[-1][0])
        nxt = last_ts + MINUTE_MS
        if nxt <= cursor:
            break
        cursor = nxt
        if last_ts >= end_ms:
            break

    if not raw:
        return pd.DataFrame()

    df = pd.DataFrame(
        raw,
        columns=["open_time_ms", "open", "high", "low", "close", "volume"],
    )
    df["open_time"] = pd.to_datetime(df["open_time_ms"], unit="ms", utc=True)
    df["close_time"] = df["open_time"] + pd.Timedelta(seconds=59)
    df = df.drop(columns=["open_time_ms"])
    df["symbol"] = unified_symbol.replace("/", "")
    for c in ("open", "high", "low", "close", "volume"):
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


def save_parquet(df: pd.DataFrame, pair: str, output_dir: Path) -> Path | None:
    if df.empty:
        return None
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{pair}.parquet"
    df.to_parquet(path, index=False)
    logger.info("Saved %d Gate.io bars → %s", len(df), path)
    return path


def download_gateio_for_announcements(
    announcements_path: Path,
    output_dir: Path,
    catalogs: set[str] | None,
    pre_hours: float,
    post_hours: float,
    sleep_between_symbols_s: float = 0.25,
    fetch_btc_baseline: bool = True,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
) -> dict[str, Path | None]:
    exchange = _gateio_exchange()
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

    if fetch_btc_baseline:
        ubtc = resolve_gateio_symbol(exchange, "BTCUSDT")
        if ubtc:
            all_btc: list[tuple[datetime, datetime]] = []
            for wins in windows.values():
                all_btc.extend(wins)
            if all_btc:
                bs = min(s for s, _ in all_btc)
                be = max(e for _, e in all_btc)
                p = output_dir / "BTCUSDT.parquet"
                if p.exists():
                    logger.info("BTCUSDT Gate.io already exists, skipping baseline")
                    results["BTCUSDT"] = p
                else:
                    logger.info("Fetching Gate.io baseline %s %s → %s", ubtc, bs, be)
                    df = fetch_ohlcv_range_ccxt(exchange, ubtc, bs, be)
                    results["BTCUSDT"] = save_parquet(df, "BTCUSDT", output_dir)
                time.sleep(sleep_between_symbols_s)

    pairs = sorted(windows.keys())
    for i, pair in enumerate(pairs):
        unified = resolve_gateio_symbol(exchange, pair)
        if not unified:
            logger.info("[%d/%d] %s — no Gate.io spot market", i + 1, len(pairs), pair)
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
            unified,
            overall_start,
            overall_end,
        )
        try:
            df = fetch_ohlcv_range_ccxt(exchange, unified, overall_start, overall_end)
            results[pair] = save_parquet(df, pair, output_dir)
        except Exception as e:
            logger.warning("Failed %s: %s", pair, e)
            results[pair] = None
        time.sleep(sleep_between_symbols_s)

    ok = sum(1 for v in results.values() if v is not None)
    logger.info("Gate.io download finished: %d parquet paths (incl. skips)", ok)
    return results


def main() -> None:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Gate.io 1m klines (spot, CCXT)")
    parser.add_argument(
        "--config",
        default=str(root / "config" / "gateio.yaml"),
        help="YAML for announcement-window bulk pull",
    )
    parser.add_argument(
        "--announcements",
        default=str(root / "data" / "processed" / "announcements_with_symbols.jsonl"),
    )
    parser.add_argument("--no-btc", action="store_true", help="Skip BTCUSDT baseline")
    parser.add_argument(
        "--pair",
        default="",
        help="If set: fetch this pair only (e.g. BTCUSDT), last N hours; ignores --config bulk",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=48.0,
        help="With --pair: lookback hours (default 48)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(root / "data" / "raw" / "gateio_klines"),
        help="Parquet output directory",
    )
    args = parser.parse_args()

    if args.pair:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=args.hours)
        ex = _gateio_exchange()
        ex.load_markets()
        u = resolve_gateio_symbol(ex, args.pair.upper())
        if not u:
            logger.error("No Gate.io spot market for %s", args.pair)
            return
        df = fetch_ohlcv_range_ccxt(ex, u, start, end)
        p = save_parquet(df, args.pair.upper(), Path(args.output_dir))
        logger.info("bars=%d path=%s", len(df), p)
        return

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    cats = cfg.get("catalogs") or []
    catalog_set = set(cats) if cats else None

    pub_after = _parse_optional_iso_dt(cfg.get("published_after"))
    pub_before = _parse_optional_iso_dt(cfg.get("published_before"))

    download_gateio_for_announcements(
        announcements_path=Path(args.announcements),
        output_dir=Path(cfg.get("output_dir", "data/raw/gateio_klines")),
        catalogs=catalog_set,
        pre_hours=float(cfg.get("pre_hours", 2.0)),
        post_hours=float(cfg.get("post_hours", 26.0)),
        sleep_between_symbols_s=float(cfg.get("sleep_between_symbols_s", 0.25)),
        fetch_btc_baseline=not args.no_btc,
        published_after=pub_after,
        published_before=pub_before,
    )


if __name__ == "__main__":
    main()
