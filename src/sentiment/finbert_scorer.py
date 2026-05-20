"""FinBERT-based financial sentiment scorer.

Uses ProsusAI/finbert (pre-trained on financial news, ~110M params).
Returns sentiment in [-1, +1]:  positive → +score, negative → -score, neutral → 0.

Supports both single-text and batch inference for efficiency.
Falls back gracefully if torch/transformers are not installed.
"""

from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)

_pipeline = None
_load_failed = False


def _map_label(label: str, conf: float) -> float:
    """Map FinBERT label + confidence → [-1, +1] score."""
    lab = label.lower()
    if "positive" in lab:
        return float(conf)
    if "negative" in lab:
        return -float(conf)
    return 0.0  # neutral


def finbert_available() -> bool:
    """Check whether the FinBERT model stack can be loaded."""
    if _load_failed:
        return False
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401

        return True
    except ImportError:
        return False


def _ensure_pipeline():
    """Lazy-load the HuggingFace pipeline (downloads weights on first call)."""
    global _pipeline, _load_failed

    if _load_failed:
        raise RuntimeError("FinBERT load previously failed")

    if _pipeline is None:
        from transformers import pipeline

        logger.info("Loading ProsusAI/finbert (first call may download ~440 MB)...")
        _pipeline = pipeline(
            "sentiment-analysis",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            truncation=True,
            max_length=512,
        )
        logger.info("FinBERT loaded successfully.")
    return _pipeline


def score_finbert(title: str, body: str = "") -> float:
    """Score a single announcement. Returns float in [-1, +1]."""
    pipe = _ensure_pipeline()
    text = f"{title}. {body}".strip()[:512]
    if not text:
        return 0.0
    try:
        out = pipe(text)[0]
        return max(-1.0, min(1.0, _map_label(str(out["label"]), float(out["score"]))))
    except Exception:
        global _load_failed
        _load_failed = True
        raise


def score_finbert_batch(
    texts: Sequence[str],
    batch_size: int = 32,
) -> list[float]:
    """Score a batch of texts efficiently. Returns list of [-1, +1] scores."""
    pipe = _ensure_pipeline()
    # Truncate each text to 512 chars (tokenizer handles sub-word truncation)
    truncated = [t[:512] if t else "" for t in texts]
    results: list[float] = []
    for i in range(0, len(truncated), batch_size):
        batch = truncated[i : i + batch_size]
        try:
            outputs = pipe(batch)
            for out in outputs:
                results.append(
                    max(-1.0, min(1.0, _map_label(str(out["label"]), float(out["score"]))))
                )
        except Exception as exc:
            logger.error("FinBERT batch error at index %d: %s", i, exc)
            # Fill failed batch with 0.0 (neutral) so indices stay aligned
            results.extend([0.0] * len(batch))
    return results
