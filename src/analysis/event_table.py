"""Build event-level return table from announcements + 1-minute klines.

Row = one announcement × one traded pair when kline parquet exists.
Returns use first 1-minute bar at or after published_at as entry (close),
same convention for horizons (first bar at or after t0 + H).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

HORIZONS_MIN: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "24h": 1440,
}


@dataclass
class BarSeries:
    times: pd.Series
    closes: pd.Series

    @classmethod
    def from_parquet(cls, path: Path) -> BarSeries | None:
        if not path.exists():
            return None
        df = pd.read_parquet(path, columns=["open_time", "close"])
        if df.empty:
            return None
        df = df.sort_values("open_time").reset_index(drop=True)
        return cls(df["open_time"], df["close"])

    def ret_from_t0(self, t0: pd.Timestamp, minutes: int) -> float | None:
        if t0.tzinfo is None:
            t0 = t0.tz_localize("UTC")
        i0 = self.times.searchsorted(t0, side="left")
        if i0 >= len(self.times):
            return None
        t1 = t0 + pd.Timedelta(minutes=minutes)
        i1 = self.times.searchsorted(t1, side="left")
        if i1 >= len(self.times):
            return None
        p0, p1 = float(self.closes.iloc[i0]), float(self.closes.iloc[i1])
        if p0 <= 0:
            return None
        return p1 / p0 - 1.0


def load_announcements(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def build_events(
    announcements_path: Path,
    klines_dir: Path,
    btc_path: Path,
    price_venue: str | None = None,
) -> pd.DataFrame:
    btc = BarSeries.from_parquet(btc_path)
    if btc is None:
        raise FileNotFoundError(f"Missing BTC klines: {btc_path}")

    cache: dict[str, BarSeries | None] = {}
    out_rows: list[dict] = []

    for ann in load_announcements(announcements_path):
        pairs = ann.get("extracted_pairs") or []
        if not pairs:
            continue
        pub = ann.get("published_at")
        if not pub:
            continue
        t0 = pd.Timestamp(pub)
        if t0.tzinfo is None:
            t0 = t0.tz_localize("UTC")

        for pair in pairs:
            p = klines_dir / f"{pair}.parquet"
            if pair not in cache:
                cache[pair] = BarSeries.from_parquet(p)
            series = cache[pair]
            if series is None:
                continue

            row: dict = {
                "announcement_id": str(ann.get("announcement_id", "")),
                "code": ann.get("code", ""),
                "title": ann.get("title", ""),
                "published_at": t0.isoformat(),
                "catalog_name": ann.get("catalog_name", ""),
                "symbol": pair.replace("USDT", ""),
                "pair": pair,
            }
            if price_venue:
                row["price_venue"] = price_venue

            for label, mins in HORIZONS_MIN.items():
                r = series.ret_from_t0(t0, mins)
                row[f"ret_{label}"] = r
                br = btc.ret_from_t0(t0, mins)
                row[f"btc_ret_{label}"] = br
                if r is not None and br is not None:
                    row[f"adj_ret_{label}"] = r - br
                else:
                    row[f"adj_ret_{label}"] = None

            out_rows.append(row)

    return pd.DataFrame(out_rows)


def category_summary(df: pd.DataFrame) -> None:
    ret_cols = [f"ret_{k}" for k in HORIZONS_MIN]
    for cat, g in df.groupby("catalog_name"):
        print(f"\n=== {cat} (n={len(g)}) ===")
        for c in ret_cols:
            s = pd.to_numeric(g[c], errors="coerce")
            print(
                f"  {c}: mean={s.mean():+.4%}  median={s.median():+.4%}  "
                f"non-null={s.notna().sum()}"
            )


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Build events.parquet from klines")
    parser.add_argument(
        "--announcements",
        default=str(root / "data" / "processed" / "announcements_with_symbols.jsonl"),
    )
    parser.add_argument(
        "--klines-dir",
        default=str(root / "data" / "raw" / "klines"),
        help="Directory with {PAIR}.parquet (Binance or MEXC)",
    )
    parser.add_argument(
        "--btc-path",
        default=None,
        help="Defaults to {klines-dir}/BTCUSDT.parquet",
    )
    parser.add_argument(
        "--output",
        default=str(root / "data" / "processed" / "events.parquet"),
    )
    parser.add_argument(
        "--price-venue",
        default=None,
        help="If set, add column price_venue (e.g. mexc, binance)",
    )
    args = parser.parse_args()

    cfg_path = root / "config" / "data_window.yaml"
    with open(cfg_path) as f:
        yaml.safe_load(f)

    ann_path = Path(args.announcements)
    klines_dir = Path(args.klines_dir)
    btc_path = Path(args.btc_path) if args.btc_path else klines_dir / "BTCUSDT.parquet"
    out_path = Path(args.output)

    logger.info("Building events from %s (klines=%s)", ann_path, klines_dir)
    df = build_events(ann_path, klines_dir, btc_path, price_venue=args.price_venue)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %d rows → %s", len(df), out_path)
    category_summary(df)


if __name__ == "__main__":
    main()
