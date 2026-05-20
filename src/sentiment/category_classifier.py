"""Stage-1 category classifier (rule-based MVP).

Maps title + optional ``catalog_name`` to thesis categories.
"""

from __future__ import annotations

import re
from enum import Enum


class Category(str, Enum):
    LISTING_SPOT = "LISTING_SPOT"
    LISTING_FUTURES = "LISTING_FUTURES"
    LAUNCHPOOL_LAUNCHPAD = "LAUNCHPOOL_LAUNCHPAD"
    HODLER_AIRDROP = "HODLER_AIRDROP"
    AIRDROP = "AIRDROP"
    STAKING_EARN = "STAKING_EARN"
    DELISTING = "DELISTING"
    PARTNERSHIP_INTEGRATION = "PARTNERSHIP_INTEGRATION"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    REGULATORY = "REGULATORY"
    FORK_UPGRADE = "FORK_UPGRADE"
    MAINTENANCE_SUSPENSION = "MAINTENANCE_SUSPENSION"
    OTHER = "OTHER"


def classify(
    title: str,
    body: str = "",
    catalog_name: str | None = None,
) -> tuple[Category, float]:
    """Return (category, confidence)."""
    t = f"{title}\n{body}".lower()
    cn = (catalog_name or "").lower().strip()

    # --- Delisting (highest priority — "delist" keyword is unambiguous) ---
    if "delist" in t or cn == "delisting":
        return Category.DELISTING, 0.9

    # --- Security / Regulatory ---
    if re.search(r"\bsec\b|regulator|regulatory|lawsuit|fine\b", t):
        return Category.REGULATORY, 0.75
    if re.search(r"\b(hack|exploit|breach|stolen|incident)\b", t):
        return Category.SECURITY_INCIDENT, 0.72

    # --- Maintenance ---
    if cn == "wallet_maintenance_updates" or re.search(
        r"\b(maintenance|suspend|suspension|halt deposits|halt withdrawals)\b", t
    ):
        return Category.MAINTENANCE_SUSPENSION, 0.7

    # --- Fork / Upgrade ---
    if "fork" in t or "network upgrade" in t or "hard fork" in t:
        return Category.FORK_UPGRADE, 0.65

    # --- HODLer Airdrop (BNB hodler + BNSOL Super Stake variants) ---
    if re.search(r"hodler airdrop|hodler airdrops", t):
        return Category.HODLER_AIRDROP, 0.92
    if "bnsol super stake" in t or "super stake" in t:
        return Category.HODLER_AIRDROP, 0.88
    if "hodler" in t and "airdrop" in t:
        return Category.HODLER_AIRDROP, 0.85

    # --- Launchpool / Launchpad / Megadrop ---
    if re.search(r"\b(launchpool|launchpad|megadrop)\b", t) or cn == "crypto_airdrop":
        return Category.LAUNCHPOOL_LAUNCHPAD, 0.72

    # --- Generic Airdrop (not hodler, not launchpool) ---
    if re.search(r"\b(airdrop|air drop)\b", t):
        return Category.AIRDROP, 0.78

    # --- Partnership ---
    if re.search(r"\b(partnership|integrates|integration with)\b", t):
        return Category.PARTNERSHIP_INTEGRATION, 0.6

    # --- Staking / Earn ---
    if re.search(r"\b(staking|binance earn|savings|locked)\b", t):
        return Category.STAKING_EARN, 0.68

    # --- Futures listing ---
    if "futures" in t and re.search(r"\b(launch|list|will)\b", t):
        return Category.LISTING_FUTURES, 0.82

    # --- Spot listing ---
    if "will list" in t or "new trading pair" in t or "opens trading for" in t:
        return Category.LISTING_SPOT, 0.8

    # --- Catalog-based fallbacks ---
    if cn == "new_cryptocurrency_listing":
        if "futures" in t or "perpetual" in t or "margined" in t:
            return Category.LISTING_FUTURES, 0.55
        return Category.LISTING_SPOT, 0.45
    if cn == "new_fiat_listings":
        return Category.LISTING_SPOT, 0.4
    if cn in {"api_updates", "latest_activities", "latest_binance_news"}:
        return Category.OTHER, 0.3

    return Category.OTHER, 0.25
