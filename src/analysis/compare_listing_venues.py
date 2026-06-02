"""Compare listing-event returns: Binance 1m vs MEXC 5m (desktop ingest)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--binance-events",
        default=str(root / "data" / "processed" / "events.parquet"),
    )
    parser.add_argument(
        "--mexc-events",
        default=str(root / "data" / "processed" / "events_mexc_5m_desktop.parquet"),
    )
    parser.add_argument(
        "--output",
        default=str(root / "data" / "processed" / "listing_binance_vs_mexc.json"),
    )
    args = parser.parse_args()

    b = pd.read_parquet(args.binance_events)
    b = b[b["catalog_name"] == "new_cryptocurrency_listing"].copy()
    m = pd.read_parquet(args.mexc_events)
    m = m[m["catalog_name"] == "new_cryptocurrency_listing"].copy()

    keys = ["announcement_id", "pair"]
    b = b.rename(columns={c: f"binance_{c}" for c in b.columns if c.startswith("ret_")})
    m = m.rename(columns={c: f"mexc_{c}" for c in m.columns if c.startswith("ret_")})

    j = b.merge(
        m[keys + [c for c in m.columns if c.startswith("mexc_ret_")]],
        on=keys,
        how="inner",
    )

    report: dict = {
        "n_binance_listing_rows": int(len(b)),
        "n_mexc_listing_rows": int(len(m)),
        "n_matched_pairs": int(len(j)),
        "horizons": {},
    }
    for h in ("1m", "5m", "15m", "1h"):
        bc, mc = f"binance_ret_{h}", f"mexc_ret_{h}"
        if bc not in j.columns or mc not in j.columns:
            continue
        bs = pd.to_numeric(j[bc], errors="coerce")
        ms = pd.to_numeric(j[mc], errors="coerce")
        both = bs.notna() & ms.notna()
        report["horizons"][h] = {
            "n_both": int(both.sum()),
            "binance_median": float(bs.median()) if bs.notna().any() else None,
            "mexc_median": float(ms.median()) if ms.notna().any() else None,
            "corr": float(bs[both].corr(ms[both])) if both.sum() > 2 else None,
        }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
