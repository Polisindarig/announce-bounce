"""Flag events with another same-pair announcement within ±24h (plan §0.9)."""

from __future__ import annotations

import pandas as pd


def flag_contamination(df: pd.DataFrame, hours: float = 24.0) -> pd.DataFrame:
    """Add boolean column ``contaminated``."""
    out = df.copy()
    if out.empty or "pair" not in out.columns:
        out["contaminated"] = False
        return out

    delta = pd.Timedelta(hours=hours)
    pub = pd.to_datetime(out["published_at"], utc=True)
    out = out.assign(_pub=pub).sort_values(["pair", "_pub"])
    prev = out.groupby("pair")["_pub"].diff()
    nxt = out.groupby("pair")["_pub"].diff(-1).abs()
    contaminated = (prev <= delta) | (nxt <= delta)
    out["contaminated"] = contaminated.fillna(False).values
    return out.drop(columns=["_pub"])
