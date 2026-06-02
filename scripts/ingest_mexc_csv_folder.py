#!/usr/bin/env python3
"""Convert Desktop-style MEXC 5m CSV files to parquet under data/raw/."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def csv_to_parquet(csv_path: Path, out_dir: Path) -> Path | None:
    pair = csv_path.stem.replace("_5m", "").upper()
    if not pair.endswith("USDT"):
        pair = f"{pair}USDT"
    out = out_dir / f"{pair}.parquet"
    if out.exists():
        return out

    df = pd.read_csv(csv_path)
    if df.empty or "open_time" not in df.columns:
        return None

    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    if "close_time" in df.columns:
        df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    for col in ("open", "high", "low", "close", "volume", "quote_volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["symbol"] = pair
    df.to_parquet(out, index=False)
    return out


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        default=str(Path.home() / "Desktop" / "mexc_5m_data"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(root / "data" / "raw" / "mexc_klines_5m_desktop"),
    )
    args = parser.parse_args()

    inp = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for csv in sorted(inp.glob("*_5m.csv")):
        p = csv_to_parquet(csv, out_dir)
        if p:
            ok += 1
            print(f"  {p.name}")
    print(f"\nIngested {ok} parquets → {out_dir}")


if __name__ == "__main__":
    main()
