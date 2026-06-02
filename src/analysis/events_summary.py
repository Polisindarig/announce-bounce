"""Print and save category-level return stats from ``events.parquet``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

HORIZONS = ("ret_1m", "ret_5m", "ret_15m", "ret_1h", "ret_4h", "ret_24h")
BTC_ADJ = tuple(f"{h}_btc_adj" for h in HORIZONS)


def summarize_events(df: pd.DataFrame) -> dict:
    out: dict = {
        "n_rows": int(len(df)),
        "n_with_ret_15m": int(df["ret_15m"].notna().sum()) if "ret_15m" in df.columns else 0,
        "catalogs": {},
    }
    for cat, g in df.groupby("catalog_name"):
        block: dict = {"n": int(len(g))}
        for col in (*HORIZONS, *BTC_ADJ):
            if col not in g.columns:
                continue
            s = pd.to_numeric(g[col], errors="coerce")
            block[col] = {
                "mean": float(s.mean()) if s.notna().any() else None,
                "median": float(s.median()) if s.notna().any() else None,
                "non_null": int(s.notna().sum()),
            }
        out["catalogs"][str(cat)] = block
    return out


def print_summary(report: dict) -> None:
    print(f"Total events: {report['n_rows']:,}  (ret_15m non-null: {report['n_with_ret_15m']:,})")
    for cat, block in report["catalogs"].items():
        n = block["n"]
        r15 = block.get("ret_15m", {})
        r1h = block.get("ret_1h", {})
        m15 = r15.get("median")
        m1h = r1h.get("median")
        s15 = f"{m15:+.4f}" if m15 is not None else "n/a"
        s1h = f"{m1h:+.4f}" if m1h is not None else "n/a"
        print(f"  {cat}: n={n:,}  median ret_15m={s15}  median ret_1h={s1h}")


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Summarize events.parquet by catalog")
    parser.add_argument(
        "--events",
        default=str(root / "data" / "processed" / "events.parquet"),
    )
    parser.add_argument(
        "--output",
        default=str(root / "data" / "processed" / "events_summary.json"),
    )
    args = parser.parse_args()

    df = pd.read_parquet(args.events)
    report = summarize_events(df)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print_summary(report)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
