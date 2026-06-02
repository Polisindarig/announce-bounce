"""Add hybrid sentiment scores to listing rows in events.parquet subset."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from src.sentiment.hybrid_scorer import score

logger = logging.getLogger(__name__)

LISTING_CATALOG = "new_cryptocurrency_listing"


def enrich_listing_sentiment(events_path: Path, output_path: Path, prefer_finbert: bool = True) -> dict:
    df = pd.read_parquet(events_path)
    listing = df[df["catalog_name"] == LISTING_CATALOG].copy()
    scores: list[float] = []
    backends: list[str] = []
    for _, row in listing.iterrows():
        s, backend = score(str(row.get("title", "") or ""), "", prefer_finbert=prefer_finbert)
        scores.append(s)
        backends.append(backend)
    listing["sentiment_score"] = scores
    listing["sentiment_backend"] = backends

    out = {
        "n_rows": int(len(listing)),
        "backend_counts": listing["sentiment_backend"].value_counts().to_dict(),
        "pearson_sent_vs_ret_15m": None,
    }
    if "ret_15m" in listing.columns:
        r = pd.to_numeric(listing["ret_15m"], errors="coerce")
        mask = r.notna()
        if int(mask.sum()) >= 3:
            out["pearson_sent_vs_ret_15m"] = float(
                listing.loc[mask, "sentiment_score"].corr(r[mask])
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    listing.to_parquet(output_path, index=False)
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--events",
        default=str(root / "data" / "processed" / "events.parquet"),
    )
    parser.add_argument(
        "--output",
        default=str(root / "data" / "processed" / "listing_events_with_sentiment.parquet"),
    )
    parser.add_argument(
        "--lexical-only",
        action="store_true",
        help="Skip FinBERT even if installed",
    )
    args = parser.parse_args()

    meta = enrich_listing_sentiment(
        Path(args.events),
        Path(args.output),
        prefer_finbert=not args.lexical_only,
    )
    meta_path = Path(args.output).with_suffix(".json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(json.dumps(meta, indent=2))
    print(f"Wrote {args.output} and {meta_path}")


if __name__ == "__main__":
    main()
