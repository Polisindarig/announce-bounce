"""Parse Binance spot listing trading-open time from announcement text."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

UTC_DT = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})\s*\(UTC\)",
    re.IGNORECASE,
)


def _parse_pub(pub: str | None) -> datetime | None:
    if not pub:
        return None
    dt = datetime.fromisoformat(str(pub).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_utc_datetimes(text: str) -> list[datetime]:
    out: list[datetime] = []
    for m in UTC_DT.finditer(text or ""):
        y, mo, d, h, mi = map(int, m.groups())
        out.append(datetime(y, mo, d, h, mi, tzinfo=timezone.utc))
    return out


def first_kline_at_or_after(
    klines: pd.DataFrame, after: datetime
) -> datetime | None:
    if klines is None or klines.empty:
        return None
    idx = klines.index if isinstance(klines.index, pd.DatetimeIndex) else pd.to_datetime(
        klines["open_time"], utc=True
    )
    ts = pd.Timestamp(after).tz_convert("UTC")
    mask = idx >= ts
    if not mask.any():
        return None
    t0 = idx[mask][0]
    return t0.to_pydatetime()


def resolve_event_time(
    announcement: dict,
    pair_klines: pd.DataFrame | None = None,
    is_listing_spot: bool = False,
) -> tuple[datetime | None, datetime | None, str]:
    """Return (t_announcement, t_0, t_0_source)."""
    pub = _parse_pub(announcement.get("published_at"))
    if pub is None:
        return None, None, "missing_published_at"

    title = str(announcement.get("title", "") or "")
    body = str(announcement.get("body_text", "") or "")
    catalog = str(announcement.get("catalog_name", "") or "")

    listing_like = is_listing_spot or (
        catalog == "new_cryptocurrency_listing"
        and "will list" in title.lower()
        and "futures" not in title.lower()
    )

    t_trading: datetime | None = None
    if listing_like:
        candidates = parse_utc_datetimes(body)
        window_end = pub + timedelta(days=14)
        in_window = [t for t in candidates if pub - timedelta(hours=1) <= t <= window_end]
        if in_window:
            t_trading = min(in_window)

    if t_trading is None and pair_klines is not None and listing_like:
        t_trading = first_kline_at_or_after(pair_klines, pub)

    if t_trading is not None:
        return pub, t_trading, "t_binance_trading"

    return pub, pub, "published_at"


def enrich_announcements_jsonl(
    input_path: Path,
    output_path: Path,
    klines_dir: Path | None = None,
) -> int:
    """Add t_announcement, t_binance_trading, t_0, t_0_source to each JSONL row."""
    klines_dir = Path(klines_dir) if klines_dir else None
    kcache: dict[str, pd.DataFrame] = {}
    n = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_path = output_path
    if input_path.resolve() == output_path.resolve():
        write_path = output_path.with_suffix(".tmp.jsonl")

    with open(input_path) as fin, open(write_path, "w") as fout:
        for line in fin:
            ann = json.loads(line)
            pair = (ann.get("extracted_pairs") or [None])[0]
            kl = None
            if klines_dir and pair:
                if pair not in kcache:
                    p = klines_dir / f"{pair}.parquet"
                    if p.exists():
                        df = pd.read_parquet(p)
                        if "open_time" in df.columns:
                            df = df.set_index(pd.to_datetime(df["open_time"], utc=True))
                        kcache[pair] = df
                    else:
                        kcache[pair] = pd.DataFrame()
                kl = kcache.get(pair)

            t_ann, t0, src = resolve_event_time(ann, kl, is_listing_spot=False)
            if t_ann:
                ann["t_announcement"] = t_ann.isoformat()
            if t0:
                ann["t_0"] = t0.isoformat()
                ann["t_0_source"] = src
            if t_ann and t0 and src == "t_binance_trading":
                ann["t_binance_trading"] = t0.isoformat()
            fout.write(json.dumps(ann, ensure_ascii=False) + "\n")
            n += 1

    if write_path != output_path:
        write_path.replace(output_path)
    return n
