"""Stage-2 within-category sentiment scorer.

Combines three signals into one number in [-1, +1]:
    1. FinBERT (Araci, 2019)
    2. CryptoBERT (ElKulako & Pintus, 2022)
    3. Loughran-McDonald negative-word density (Loughran & McDonald, 2011)

The three signals are combined via an L2-regularized linear regression fit
on the in-sample training window. Weights are frozen before touching OOS data.

See docs/02-methodology.md §3.
"""

from __future__ import annotations


def score(title: str, body: str) -> float:
    """Return a sentiment score in [-1, +1]."""
    raise NotImplementedError("Implement in Phase 3. See docs/03-project-plan.md.")
