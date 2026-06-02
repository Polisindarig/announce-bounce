"""Equal-weight Top-50 USDT index (exchange-internal benchmark, MVP snapshot)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TOP_N = 50


def build_top50_snapshot(klines_dir: Path, top_n: int = TOP_N) -> list[str]:
    """Rank pairs by total in-window USDT volume (single snapshot, MVP)."""
    scores: list[tuple[str, float]] = []
    for path in klines_dir.glob("*USDT.parquet"):
        pair = path.stem
        if pair == "BTCUSDT":
            continue
        try:
            vol = pd.read_parquet(path, columns=["volume"])["volume"].sum()
        except Exception:
            continue
        if vol > 0:
            scores.append((pair, float(vol)))
    scores.sort(key=lambda x: -x[1])
    return [p for p, _ in scores[:top_n]]


def load_or_build_membership(
    klines_dir: Path,
    window_start: datetime,
    window_end: datetime,
    cache_path: Path | None = None,
) -> dict[str, list[str]]:
    """Return dict with single key ``snapshot`` → Top-50 pairs (fast MVP)."""
    _ = window_start, window_end
    cache_path = cache_path or Path("data/processed/ew_top50_membership.json")
    if cache_path.exists():
        with open(cache_path) as f:
            data = json.load(f)
        if "snapshot" in data:
            return data

    pairs = build_top50_snapshot(klines_dir)
    mem = {"snapshot": pairs, "note": "MVP single snapshot; thesis target is weekly rebalance."}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(mem, f, indent=2)
    logger.info("Top-50 index snapshot: %d pairs → %s", len(pairs), cache_path)
    return mem


def membership_for_time(membership: dict[str, list[str]], event_time: datetime) -> list[str]:
    _ = event_time
    return membership.get("snapshot", membership.get(next(iter(membership), ""), []))


def build_ew_index_close_series(
    constituents: list[str],
    kline_cache: dict[str, pd.DataFrame | None],
    max_pairs: int = 30,
) -> pd.Series:
    """Equal-weight average close (MVP: cap pairs for memory)."""
    series_list: list[pd.Series] = []
    for pair in constituents[:max_pairs]:
        kl = kline_cache.get(pair)
        if kl is None or kl.empty:
            continue
        s = kl["close"]
        if len(s) > 200_000:
            s = s.iloc[-200_000:]
        series_list.append(s.rename(pair))
    if not series_list:
        return pd.Series(dtype=float)
    panel = pd.concat(series_list, axis=1).sort_index().ffill()
    return panel.mean(axis=1)


def equal_weight_horizon_return(
    constituents: list[str],
    event_time: datetime,
    minutes: int,
    kline_cache: dict[str, pd.DataFrame | None],
    min_names: int = 10,
) -> float | None:
    """Mean raw return across constituents from event_time to +minutes."""
    rets: list[float] = []
    target_delta = pd.Timedelta(minutes=minutes)
    ts = pd.Timestamp(event_time).tz_convert("UTC")

    for pair in constituents:
        kl = kline_cache.get(pair)
        if kl is None or kl.empty:
            continue
        mask = kl.index >= ts
        if not mask.any():
            continue
        t0 = kl.index[mask][0]
        t1_target = t0 + target_delta
        fmask = kl.index >= t1_target
        if not fmask.any():
            continue
        p0 = float(kl.loc[t0, "close"])
        p1 = float(kl.loc[kl.index[fmask][0], "close"])
        if p0 > 0:
            rets.append((p1 - p0) / p0)

    if len(rets) < min_names:
        return None
    return float(np.mean(rets))
