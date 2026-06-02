"""Build the unified events table.

Joins announcements (with extracted symbols) to kline data, computes
returns at pre-registered horizons (1m, 5m, 15m, 1h, 4h, 24h), and
outputs data/processed/events.parquet.

Each row = one (announcement, symbol) pair with:
  - Event metadata and ``t_0`` (listing spot → trading open when known)
  - Returns: raw, BTC-adjusted, equal-weight Top-50 index-adjusted
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from src.processing.contamination import flag_contamination
from src.processing.crypto_index import (
    build_ew_index_close_series,
    load_or_build_membership,
    membership_for_time,
)
from src.scraper.listing_time import resolve_event_time
from src.sentiment.category_classifier import Category, classify

logger = logging.getLogger(__name__)

HORIZONS_MINUTES = {
    "ret_1m": 1,
    "ret_5m": 5,
    "ret_15m": 15,
    "ret_1h": 60,
    "ret_4h": 240,
    "ret_24h": 1440,
}


def load_klines(symbol: str, klines_dir: Path) -> pd.DataFrame | None:
    path = klines_dir / f"{symbol}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if "open_time" not in df.columns or df.empty:
        return None
    df = df.sort_values("open_time").reset_index(drop=True)
    df = df.set_index(pd.to_datetime(df["open_time"], utc=True))
    return df


def compute_returns(
    klines: pd.DataFrame,
    event_time: pd.Timestamp,
    horizons: dict[str, int] = HORIZONS_MINUTES,
) -> dict:
    """Compute returns at each horizon from the first bar at or after event_time."""
    results: dict = {}
    mask = klines.index >= event_time
    if not mask.any():
        return {h: None for h in horizons}

    t0_idx = klines.index[mask][0]
    t0_price = klines.loc[t0_idx, "close"]
    results["t0_price"] = float(t0_price)
    results["t0_volume"] = float(klines.loc[t0_idx, "volume"])
    results["t0_actual"] = str(t0_idx)

    for name, minutes in horizons.items():
        target_time = t0_idx + pd.Timedelta(minutes=minutes)
        future_mask = klines.index >= target_time
        if not future_mask.any():
            results[name] = None
            continue
        t_end_idx = klines.index[future_mask][0]
        t_end_price = klines.loc[t_end_idx, "close"]
        results[name] = float((t_end_price - t0_price) / t0_price)

    return results


def _load_window(klines_dir: Path) -> tuple[datetime, datetime]:
    cfg_path = Path(__file__).resolve().parents[2] / "config" / "data_window.yaml"
    if cfg_path.exists():
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        ws = datetime.fromisoformat(str(cfg["window_start"]).replace("Z", "+00:00"))
        we = datetime.fromisoformat(str(cfg["window_end"]).replace("Z", "+00:00"))
        if ws.tzinfo is None:
            ws = ws.replace(tzinfo=timezone.utc)
        if we.tzinfo is None:
            we = we.replace(tzinfo=timezone.utc)
        return ws, we
    return datetime(2025, 6, 1, tzinfo=timezone.utc), datetime(2026, 5, 15, tzinfo=timezone.utc)


def build_events_table(
    announcements_path: str | Path = "data/processed/announcements_with_symbols.jsonl",
    klines_dir: str | Path = "data/raw/klines",
    btc_symbol: str = "BTCUSDT",
    output_path: str | Path = "data/processed/events.parquet",
    membership_cache: str | Path | None = "data/processed/ew_top50_membership.json",
) -> pd.DataFrame:
    klines_dir = Path(klines_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    btc_klines = load_klines(btc_symbol, klines_dir)
    if btc_klines is None:
        raise FileNotFoundError("BTCUSDT klines required")

    w_start, w_end = _load_window(klines_dir)
    membership = load_or_build_membership(
        klines_dir, w_start, w_end, Path(membership_cache) if membership_cache else None
    )

    rows = []
    kline_cache: dict[str, pd.DataFrame | None] = {btc_symbol: btc_klines}
    constituents = membership_for_time(membership, w_start)
    for pair in constituents:
        if pair not in kline_cache:
            kline_cache[pair] = load_klines(pair, klines_dir)
    ew_index = build_ew_index_close_series(constituents, kline_cache)
    if ew_index.empty:
        logger.warning("EW index series empty; index_adj columns will be null")
        ew_klines = None
    else:
        ew_klines = pd.DataFrame({"close": ew_index, "volume": 0.0})

    with open(announcements_path) as f:
        for line in f:
            ann = json.loads(line)
            pub = ann.get("published_at")
            if not pub:
                continue
            pairs = ann.get("extracted_pairs", [])
            symbols = ann.get("extracted_symbols", [])
            if not pairs:
                continue

            cat, _ = classify(
                str(ann.get("title", "") or ""),
                str(ann.get("body_text", "") or ""),
                catalog_name=ann.get("catalog_name"),
            )
            is_listing_spot = cat == Category.LISTING_SPOT

            for sym, pair in zip(symbols, pairs):
                if pair not in kline_cache:
                    kline_cache[pair] = load_klines(pair, klines_dir)
                klines = kline_cache[pair]
                if klines is None:
                    continue

                if ann.get("t_0"):
                    t0 = pd.Timestamp(ann["t_0"])
                    if t0.tzinfo is None:
                        t0 = t0.tz_localize("UTC")
                    t0_source = ann.get("t_0_source", "enriched_jsonl")
                else:
                    _, t0_dt, t0_source = resolve_event_time(ann, klines, is_listing_spot)
                    if t0_dt is None:
                        continue
                    t0 = pd.Timestamp(t0_dt).tz_convert("UTC")

                t_ann = pd.Timestamp(pub)
                if t_ann.tzinfo is None:
                    t_ann = t_ann.tz_localize("UTC")

                rets = compute_returns(klines, t0)
                if not rets:
                    continue

                btc_rets = compute_returns(btc_klines, t0)
                idx_rets = compute_returns(ew_klines, t0) if ew_klines is not None else {}

                row = {
                    "announcement_id": ann.get("announcement_id", ""),
                    "code": ann.get("code", ""),
                    "title": ann.get("title", ""),
                    "catalog_name": ann.get("catalog_name", ""),
                    "event_category": cat.value,
                    "published_at": pub,
                    "t_announcement": ann.get("t_announcement", pub),
                    "t_binance_trading": ann.get("t_binance_trading"),
                    "t_0": t0.isoformat(),
                    "t_0_source": t0_source,
                    "symbol": sym,
                    "pair": pair,
                    "t0_price": rets.get("t0_price"),
                    "t0_volume": rets.get("t0_volume"),
                    "t0_actual": rets.get("t0_actual"),
                    "index_n_constituents": len(constituents),
                }

                for h in HORIZONS_MINUTES:
                    raw = rets.get(h)
                    btc = btc_rets.get(h)
                    idx = idx_rets.get(h) if idx_rets else None
                    row[h] = raw
                    row[f"{h}_btc_adj"] = (raw - btc) if raw is not None and btc is not None else None
                    row[f"{h}_index_adj"] = (raw - idx) if raw is not None and idx is not None else None

                rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        logger.warning("No events with kline data found!")
        df.to_parquet(output_path, index=False)
        return df

    df["published_at"] = pd.to_datetime(df["published_at"], format="ISO8601", utc=True)
    df = flag_contamination(df)
    df = df.sort_values("published_at").reset_index(drop=True)

    df.to_parquet(output_path, index=False, engine="pyarrow")
    logger.info("Built events table: %d rows → %s", len(df), output_path)

    for cat in df["catalog_name"].dropna().unique()[:8]:
        sub = df[df["catalog_name"] == cat]
        med = sub["ret_1h"].median() if sub["ret_1h"].notna().any() else 0.0
        logger.info("  %s: %d events, median ret_1h=%.4f", cat, len(sub), med)

    return df


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Build events.parquet")
    parser.add_argument(
        "--announcements",
        default=str(root / "data" / "processed" / "announcements_with_symbols.jsonl"),
    )
    parser.add_argument("--klines-dir", default=str(root / "data" / "raw" / "klines"))
    parser.add_argument("--output", default=str(root / "data" / "processed" / "events.parquet"))
    args = parser.parse_args()

    df = build_events_table(args.announcements, args.klines_dir, output_path=args.output)
    print(f"Events: {len(df)} rows")
