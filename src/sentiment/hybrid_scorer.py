"""Unified sentiment scorer: CryptoBERT → FinBERT → lexical fallback.

Preferred model order:
1. ElKulako/cryptobert  — trained on crypto tweets/news (Bullish/Bearish/Neutral)
2. ProsusAI/finbert     — trained on financial news (positive/negative/neutral)
3. Lexical keyword scorer — zero-dependency baseline

The hybrid scorer tries each in order and falls back on ImportError
or model load failure.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_cryptobert_pipe = None
_cryptobert_failed = False


def _ensure_cryptobert():
    """Lazy-load CryptoBERT pipeline."""
    global _cryptobert_pipe, _cryptobert_failed
    if _cryptobert_failed:
        return None
    if _cryptobert_pipe is not None:
        return _cryptobert_pipe
    try:
        from transformers import pipeline

        logger.info("Loading ElKulako/cryptobert...")
        _cryptobert_pipe = pipeline(
            "sentiment-analysis",
            model="ElKulako/cryptobert",
            truncation=True,
            max_length=512,
        )
        logger.info("CryptoBERT loaded.")
        return _cryptobert_pipe
    except Exception as exc:
        logger.warning("CryptoBERT unavailable: %s", exc)
        _cryptobert_failed = True
        return None


def _cryptobert_score(text: str) -> float:
    """Score a single text with CryptoBERT → float in [-1, +1]."""
    pipe = _ensure_cryptobert()
    if pipe is None:
        raise RuntimeError("CryptoBERT not available")
    out = pipe(text[:512])[0]
    lab = out["label"].lower()
    conf = float(out["score"])
    if "bull" in lab or "positive" in lab:
        return conf
    if "bear" in lab or "negative" in lab:
        return -conf
    return 0.0


def score(
    title: str,
    body: str = "",
    category: str | None = None,
    prefer: str = "cryptobert",
) -> tuple[float, str]:
    """Return ``(score_in_[-1,1], backend_name)``.

    Parameters
    ----------
    title : str
        Announcement title.
    body : str
        Optional body text (used only by lexical fallback).
    category : str | None
        Category label (used only by lexical fallback for prior shift).
    prefer : str
        Model preference order: ``"cryptobert"`` (default), ``"finbert"``,
        or ``"lexical"``.
    """
    text = title.strip()

    # --- Try CryptoBERT first ---
    if prefer in ("cryptobert", "finbert"):
        try:
            return _cryptobert_score(text), "cryptobert"
        except Exception:
            pass

    # --- Fallback to FinBERT ---
    if prefer in ("cryptobert", "finbert"):
        try:
            from src.sentiment.finbert_scorer import score_finbert

            return score_finbert(title, body), "finbert"
        except Exception:
            pass

    # --- Final fallback: lexical ---
    from src.sentiment.sentiment_scorer import score as lexical_score

    return lexical_score(title, body, category=category), "lexical"
