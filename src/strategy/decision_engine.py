"""Decision engine — maps announcement category to trade parameters.

Two model variants (pre-registered ablation, Phase 5.5):
    M0: category-only (no sentiment)
    M1: category + CryptoBERT sentiment bucket

Parameters frozen from the in-sample grid-search (1,408 variants over the
101-event in-sample universe; see Section 4.6 of the thesis):
    - Take-profit:    +25%
    - Stop-loss:      -8%
    - Holding period: 1 hour
    - Slippage proxy: 1% on entry
    - Position sizing: 10% of current equity per trade (production)

Execution venues:
    - All bullish trades → MEXC (Binance is only the signal source)
    - Bearish forced-exit → Binance (closes any open spot position there)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from src.sentiment.category_classifier import Category


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    SKIP = "SKIP"


class Venue(str, Enum):
    BINANCE = "BINANCE"
    MEXC = "MEXC"


@dataclass
class TradeDecision:
    symbol: str
    direction: Direction
    venue: Venue
    size_pct_equity: float
    take_profit_pct: float
    stop_loss_pct: float
    time_stop: timedelta
    rationale: str
    category: str = ""
    model_variant: str = "M0"


# Frozen grid-search optimum applied uniformly to all bullish categories.
_BULLISH_PARAMS = {
    "tp": 0.25,
    "sl": 0.08,
    "time_stop_min": 60,
    "venue": Venue.MEXC,
}

CALIBRATION_TABLE = {
    Category.LISTING_SPOT:        _BULLISH_PARAMS,
    Category.LISTING_FUTURES:     _BULLISH_PARAMS,
    Category.LAUNCHPOOL_LAUNCHPAD: _BULLISH_PARAMS,
    Category.HODLER_AIRDROP:      _BULLISH_PARAMS,
}

# Slippage proxy applied at entry by the execution layer (1% of entry price).
ENTRY_SLIPPAGE_PCT = 0.01

# Production position sizing: 10% of current account equity per trade
# (compounding). The OOS backtest in Section 5.2.3 uses a fixed $1,000-per-trade
# allocation as a conservative lower bound; see Section 4.7.
PRODUCTION_SIZE_PCT_EQUITY = 0.10

# Categories that trigger forced exit of open positions.
# MONITORING_TAG is treated as an early-warning bearish signal: empirically
# (Section 5.3.2) the announcement precedes a sustained negative drift, and
# 29/64 OOS delistings were preceded by a monitoring-tag with a median lead
# time of 42 days, so exiting on the tag captures most of the downside before
# the eventual delisting shock.
FORCED_EXIT_CATEGORIES = {
    Category.DELISTING,
    Category.MONITORING_TAG,
}

# Tier 2 — skip (no new trade)
SKIP_CATEGORIES = {
    Category.DELISTING,
    Category.MONITORING_TAG,
    Category.SECURITY_INCIDENT,
    Category.REGULATORY,
    Category.MAINTENANCE_SUSPENSION,
    Category.FORK_UPGRADE,
    Category.PARTNERSHIP_INTEGRATION,
    Category.OTHER,
}


def decide(
    announcement_id: str,
    category: str,
    sentiment_score: float,
    symbol: str,
    now_utc: datetime,
    model_variant: str = "M0",
    account_equity: float = 10_000.0,
) -> TradeDecision:
    """Return a TradeDecision for a given announcement.

    Parameters
    ----------
    model_variant : str
        "M0" = category-only (default),
        "M1" = category + sentiment filter.
    """
    _ = announcement_id, now_utc  # reserved for logging

    try:
        cat = Category(category)
    except ValueError:
        return _skip(symbol, "unknown_category")

    # ── Tier 2 → skip ──
    if cat in SKIP_CATEGORIES:
        return _skip(symbol, f"tier2_skip:{cat.value}")

    # ── AIRDROP (non-HODLer) → skip ──
    if cat == Category.AIRDROP:
        return _skip(symbol, f"airdrop_skip:{cat.value}")

    # ── Stablecoin filter — no pump expected ──
    if _is_stablecoin(symbol):
        return _skip(symbol, f"stablecoin_skip:{symbol}")

    # ── Tier 1 → check calibration table ──
    params = CALIBRATION_TABLE.get(cat)
    if params is None:
        return _skip(symbol, f"no_calibration:{cat.value}")

    # ── M1: sentiment filter ──
    if model_variant == "M1" and sentiment_score < -0.33:
        return _skip(symbol, f"m1_negative_sentiment:{cat.value}")

    return TradeDecision(
        symbol=symbol,
        direction=Direction.LONG,
        venue=params["venue"],
        size_pct_equity=PRODUCTION_SIZE_PCT_EQUITY,
        take_profit_pct=params["tp"],
        stop_loss_pct=params["sl"],
        time_stop=timedelta(minutes=params["time_stop_min"]),
        rationale=f"long:{cat.value}",
        category=cat.value,
        model_variant=model_variant,
    )


STABLECOINS = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "GUSD",
    "USDE", "USDS", "RLUSD", "FDUSD", "PYUSD", "EURC", "AEUR",
    "UST", "USTC", "USDD", "CEUR", "CUSD",
}


def _is_stablecoin(symbol: str) -> bool:
    """Return True if the symbol is a known stablecoin."""
    return symbol.upper() in STABLECOINS


def check_forced_exit(category: str, held_symbol: str) -> bool:
    """Return True if this announcement should force-exit a held position."""
    try:
        cat = Category(category)
    except ValueError:
        return False
    return cat in FORCED_EXIT_CATEGORIES


def _skip(symbol: str, reason: str) -> TradeDecision:
    return TradeDecision(
        symbol=symbol,
        direction=Direction.SKIP,
        venue=Venue.BINANCE,
        size_pct_equity=0.0,
        take_profit_pct=0.0,
        stop_loss_pct=0.0,
        time_stop=timedelta(0),
        rationale=reason,
    )
