"""Stage-1 category classifier.

Maps a Binance announcement (title + body) to one of nine categories:
    LISTING_SPOT, LISTING_FUTURES, DELISTING, PARTNERSHIP_INTEGRATION,
    SECURITY_INCIDENT, REGULATORY, FORK_UPGRADE, STAKING_AIRDROP, OTHER

Architecture (see docs/02-methodology.md §2):
    1. Regex / keyword rules first (covers ~80% of announcements).
    2. Light TF-IDF + logistic regression classifier for residuals.
    3. Optional LLM second-opinion for low-confidence cases (logged, not auto-applied).
"""

from __future__ import annotations

from enum import Enum


class Category(str, Enum):
    LISTING_SPOT = "LISTING_SPOT"
    LISTING_FUTURES = "LISTING_FUTURES"
    DELISTING = "DELISTING"
    PARTNERSHIP_INTEGRATION = "PARTNERSHIP_INTEGRATION"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    REGULATORY = "REGULATORY"
    FORK_UPGRADE = "FORK_UPGRADE"
    STAKING_AIRDROP = "STAKING_AIRDROP"
    OTHER = "OTHER"


def classify(title: str, body: str) -> tuple[Category, float]:
    """Return (category, confidence)."""
    raise NotImplementedError("Implement in Phase 2. See docs/03-project-plan.md.")
