"""Decision engine — pure function from announcement to (optional) trade.

Reads the frozen category x horizon x sentiment-bucket lookup table and produces:
    - direction (LONG / SHORT / SKIP)
    - position size (fractional Kelly, capped)
    - take-profit and stop-loss levels (in-sample percentiles)
    - time-stop (the chosen horizon for that category)

See docs/02-methodology.md §5.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    SKIP = "SKIP"


@dataclass
class TradeDecision:
    symbol: str
    direction: Direction
    size_pct_equity: float
    take_profit_pct: float
    stop_loss_pct: float
    time_stop: timedelta
    rationale: str


def decide(
    announcement_id: str,
    category: str,
    sentiment_score: float,
    symbol: str,
    now_utc: datetime,
) -> TradeDecision:
    """Return a TradeDecision; size==0 / direction==SKIP means no trade."""
    raise NotImplementedError("Implement in Phase 5. See docs/03-project-plan.md.")
