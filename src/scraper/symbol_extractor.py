"""Extract coin tickers / trading pairs from Binance announcement text.

Strategy:
1. Regex patterns for known Binance title templates
   ("Binance Will List X (Y)", "Binance Futures Will Launch ... XUSDT")
2. Cross-reference against a historical pairs list from Binance API
3. Manual override table for ambiguous tickers

See docs/03-project-plan.md Phase 1, Task 2.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

TITLE_PATTERNS = [
    # "Binance Will List X (TICKER)"
    re.compile(
        r"Binance\s+Will\s+List\s+(.+?)\s*\((\w+)\)", re.IGNORECASE
    ),
    # "Binance Will List TICKER"
    re.compile(
        r"Binance\s+Will\s+List\s+(\w+)", re.IGNORECASE
    ),
    # "Binance Will Add X (TICKER) on Earn/Margin/Futures..."
    re.compile(
        r"Binance\s+Will\s+Add\s+(.+?)\s*\((\w+)\)\s+on", re.IGNORECASE
    ),
    # "Binance Futures Will Launch TICKERUSDT Perpetual"
    re.compile(
        r"Launch\s+.*?(\w+)USDT\s+Perpetual", re.IGNORECASE
    ),
    # Multiple futures: "Launch AMDUSDT, QCOMUSDT and USARUSDT"
    re.compile(
        r"Launch\s+([\w,\s]+USDT[\w,\s]*USDT[^()]*?)(?:\s+USD|\s+Perpetual)", re.IGNORECASE
    ),
    # "Binance Will Delist X, Y, Z"
    re.compile(
        r"(?:Will\s+Delist|Delisting)\s+(.+?)(?:\s+on\s+|\s*$)", re.IGNORECASE
    ),
    # "Binance Launchpool: X (TICKER)"
    re.compile(
        r"Launchpool[:\s]+(.+?)\s*\((\w+)\)", re.IGNORECASE
    ),
    # "Binance Launchpad: X (TICKER)"
    re.compile(
        r"Launchpad[:\s]+(.+?)\s*\((\w+)\)", re.IGNORECASE
    ),
    # "Introducing X (TICKER) on Binance Earn"
    re.compile(
        r"Introducing\s+(.+?)\s*\((\w+)\)\s+on\s+Binance", re.IGNORECASE
    ),
]

# Extract plausible "BASEUSDT" tokens from title; filtered later against exchangeInfo.
USDT_PAIR_PATTERN = re.compile(r"\b([A-Z0-9]{2,10})USDT\b")

MANUAL_OVERRIDES: dict[str, list[str]] = {
    # announcement_id -> [ticker, ...]
    # Fill this as edge cases are discovered during the manual audit
}

EXCLUDED_WORDS = {
    "BINANCE", "USDT", "BTC", "USD", "THE", "AND", "FOR", "NEW",
    "WILL", "LIST", "DELIST", "NOTICE", "UPDATE", "PERPETUAL",
    "FUTURES", "MARGIN", "SPOT", "CONTRACT", "TRADING", "PAIR",
    "PAIRS", "OPEN", "LAUNCH", "LAUNCHPOOL", "LAUNCHPAD",
}

# Dropped when inferring symbols from body only (boilerplate / majors in generic posts).
BODY_ONLY_SKIP = {
    "ETH", "BTC", "BNB", "SOL", "XRP", "USDC", "FDUSD", "USD", "USDT",
    "DOGE", "ADA", "EUR", "GBP", "AUD",
}

# Body fallback adds false pairs on generic futures/news posts (MULTI, DATA in boilerplate).
TITLE_ONLY_CATALOGS = frozenset(
    {"new_cryptocurrency_listing", "delisting", "wallet_maintenance_updates"}
)


def fetch_binance_symbols(cache_path: str | Path = "data/raw/binance_symbols.json") -> set[str]:
    """Fetch all known Binance spot symbols. Cache locally."""
    cache_path = Path(cache_path)
    if cache_path.exists():
        with open(cache_path) as f:
            return set(json.load(f))

    logger.info("Fetching Binance exchange info for symbol list...")
    resp = httpx.get(
        "https://api.binance.com/api/v3/exchangeInfo",
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    base_assets = set()
    for s in data.get("symbols", []):
        base_assets.add(s["baseAsset"].upper())

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(sorted(base_assets), f)

    logger.info("Cached %d base assets", len(base_assets))
    return base_assets


def extract_tickers_from_title(title: str) -> list[str]:
    """Extract candidate tickers from an announcement title using regex."""
    tickers = []

    for pattern in TITLE_PATTERNS:
        match = pattern.search(title)
        if not match:
            continue

        for group in match.groups():
            if not group:
                continue
            candidates = re.split(r"[,&/\s]+", group.strip())
            for c in candidates:
                c = c.strip().upper()
                c = re.sub(r"USDT$", "", c)
                c = re.sub(r"[^A-Z0-9]", "", c)
                if len(c) >= 2 and c not in EXCLUDED_WORDS:
                    tickers.append(c)

    usdt_matches = USDT_PAIR_PATTERN.findall(title.upper())
    for m in usdt_matches:
        if m not in EXCLUDED_WORDS and not re.fullmatch(r"\d+", m):
            tickers.append(m)

    return list(dict.fromkeys(tickers))


def extract_tickers_from_body(body_text: str, known_symbols: set[str]) -> list[str]:
    """Find known tickers mentioned in the body text."""
    words = set(re.findall(r"\b[A-Z]{2,10}\b", body_text.upper()))
    return [w for w in words if w in known_symbols and w not in EXCLUDED_WORDS]


def extract_symbols(
    announcement: dict,
    known_symbols: set[str] | None = None,
) -> list[str]:
    """Extract ticker symbols from an announcement dict.

    Returns deduplicated list of base-asset tickers (e.g. ["SOL", "PEPE"]).
    """
    ann_id = str(announcement.get("announcement_id", ""))
    if ann_id in MANUAL_OVERRIDES:
        return MANUAL_OVERRIDES[ann_id]

    title = announcement.get("title", "")
    body = announcement.get("body_text", "")

    title_tickers = extract_tickers_from_title(title)
    catalog = str(announcement.get("catalog_name", ""))

    if known_symbols:
        title_validated = [t for t in title_tickers if t in known_symbols]
        if catalog in TITLE_ONLY_CATALOGS:
            return list(dict.fromkeys(title_validated))
        if title_tickers:
            return list(dict.fromkeys(title_validated))
        if body:
            body_tickers = extract_tickers_from_body(body, known_symbols)
            body_tickers = [t for t in body_tickers if t not in BODY_ONLY_SKIP]
            return list(dict.fromkeys(body_tickers))
        return []

    if catalog in TITLE_ONLY_CATALOGS or title_tickers:
        return list(dict.fromkeys(title_tickers))
    if body:
        return list(dict.fromkeys(extract_tickers_from_body(body, set())))
    return []


def process_announcements(
    jsonl_path: str | Path,
    output_path: str | Path,
    symbols_cache: str | Path = "data/raw/binance_symbols.json",
) -> int:
    """Add 'extracted_symbols' field to each announcement. Write enriched JSONL."""
    jsonl_path = Path(jsonl_path)
    output_path = Path(output_path)

    known_symbols = fetch_binance_symbols(symbols_cache)
    logger.info("Loaded %d known symbols", len(known_symbols))

    count = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(jsonl_path) as fin, open(output_path, "w") as fout:
        for line in fin:
            ann = json.loads(line)
            tickers = extract_symbols(ann, known_symbols)
            ann["extracted_symbols"] = tickers
            ann["extracted_pairs"] = [f"{t}USDT" for t in tickers]
            fout.write(json.dumps(ann, ensure_ascii=False) + "\n")
            count += 1

    logger.info("Processed %d announcements, wrote to %s", count, output_path)
    return count


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Extract symbols from announcements")
    parser.add_argument("--input", default="data/raw/announcements.jsonl")
    parser.add_argument("--output", default="data/processed/announcements_with_symbols.jsonl")
    args = parser.parse_args()

    n = process_announcements(args.input, args.output)
    print(f"Processed {n} announcements")
