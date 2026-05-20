"""Lightweight lexical sentiment in [-1, +1] (no neural models).

Sufficient for wiring the strategy/backtest stack offline. Replace with
FinBERT / CryptoBERT stack in Phase 3 when labels exist.
"""

from __future__ import annotations

import re

_POS = {
    "list",
    "launch",
    "new",
    "support",
    "expand",
    "reward",
    "staking",
    "airdrop",
    "partnership",
    "upgrade",
    "adds",
    "available",
    "open",
    "success",
    "complete",
}
_NEG = {
    "delist",
    "halt",
    "suspend",
    "suspension",
    "hack",
    "breach",
    "exploit",
    "stolen",
    "loss",
    "warning",
    "emergency",
    "lawsuit",
    "fine",
    "fraud",
    "risk",
    "delay",
    "cancel",
    "unavailable",
}


def score(title: str, body: str = "", category: str | None = None) -> float:
    """Return a sentiment score in [-1, +1].

    When *category* is supplied the scorer applies a category-aware prior
    so that e.g. delisting announcements lean negative even when they
    contain boiler-plate positive words like "support".
    """
    text = f"{title}\n{body}".lower()
    tokens = re.findall(r"[a-z][a-z']+", text)
    if not tokens:
        return 0.0
    pos = sum(1 for w in tokens if w in _POS)
    neg = sum(1 for w in tokens if w in _NEG)
    raw = (pos - neg) / max(len(tokens), 12)
    base = max(-1.0, min(1.0, raw * 6.0))

    # Category-aware adjustments (prior shift)
    if category:
        cat = category.upper()
        if cat == "DELISTING":
            # Delisting is inherently negative; shift toward negative
            base = base - 0.35
        elif cat == "MAINTENANCE_SUSPENSION":
            # Maintenance text often has false-positive "support/complete"
            base = base - 0.25
        elif cat in ("LISTING_SPOT", "LISTING_FUTURES"):
            base = base + 0.10
        elif cat in ("HODLER_AIRDROP", "AIRDROP", "LAUNCHPOOL_LAUNCHPAD"):
            # Free token distributions are positive events
            base = base + 0.12
    return max(-1.0, min(1.0, base))
