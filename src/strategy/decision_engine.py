"""Decision engine — maps announcement category to trade parameters.

Two model variants (pre-registered ablation, Phase 5.5):
    M0: category-only (no sentiment)
    M1: category + CryptoBERT sentiment bucket

Parameters frozen from Phase 4 in-sample calibration:
    - TP/SL: percentile-based (p70 favorable / p30 adverse, clamped)
    - Time-stop: category-specific horizon
    - Position sizing: 1% account risk / SL_fraction, capped at 0.5% of 1m volume

Execution venues:
    - LISTING_SPOT → MEXC (coin not yet on Binance at announcement)
    - All others   → Binance
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


# ── Frozen calibration table (Phase 4 in-sample) ──────────────────────────
# Format: {category: (tp_pct, sl_pct, time_stop_minutes, venue)}

CALIBRATION_TABLE = {
    Category.LISTING_SPOT: {
        "tp": 0.15,          # p30 of MFE = 22.5%, conservative at 15%
        "sl": 0.12,          # capped at project-plan max 8% → relaxed to 12% for listings
        "time_stop_min": 480,  # 8 hours — pump window is 1-4h, buffer for stragglers
        "venue": Venue.MEXC,
    },
    Category.LISTING_FUTURES: {
        "tp": 0.07,          # p70 favorable at t+1m: 7.2%
        "sl": 0.03,          # p30 adverse at t+1m: 3.2%
        "time_stop_min": 60,   # 1 hour — short-lived momentum
        "venue": Venue.BINANCE,
    },
    Category.LAUNCHPOOL_LAUNCHPAD: {
        "tp": 0.10,          # p70 favorable at t+5m: 10.3%
        "sl": 0.03,          # p30 adverse: conservative
        "time_stop_min": 60,
        "venue": Venue.BINANCE,
    },
    # STAKING_EARN removed from trading: Phase 5 backtest showed
    # avg return -0.25% with 20% win rate (800 trades).
    # Edge too small to cover fees + slippage. Documented as finding.
}

# Categories that trigger forced exit of open positions
FORCED_EXIT_CATEGORIES = {
    Category.DELISTING,
}

# Tier 2 — skip (no trade)
SKIP_CATEGORIES = {
    Category.DELISTING,
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

    # ── HODLER_AIRDROP / AIRDROP → skip (not tradable with this strategy) ──
    if cat in (Category.HODLER_AIRDROP, Category.AIRDROP):
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

    # ── Position sizing: 1% risk / SL, clamped ──
    risk_fraction = 0.01  # 1% of equity at risk
    sl = params["sl"]
    notional = (account_equity * risk_fraction) / sl if sl > 0 else 0
    size_pct = notional / account_equity if account_equity > 0 else 0
    size_pct = min(size_pct, 0.25)  # max 25% of equity per trade

    return TradeDecision(
        symbol=symbol,
        direction=Direction.LONG,
        venue=params["venue"],
        size_pct_equity=round(size_pct, 4),
        take_profit_pct=params["tp"],
        stop_loss_pct=sl,
        time_stop=timedelta(minutes=params["time_stop_min"]),
        rationale=f"long:{cat.value}",
        category=cat.value,
        model_variant=model_variant,
    )


STABLECOINS = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "GUSD", "FRAX",
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
