"""Smoke tests — verify the package imports and Phase-1-onward stubs are reachable."""

import src
from src.sentiment.category_classifier import Category
from src.strategy.decision_engine import Direction


def test_version():
    assert isinstance(src.__version__, str)


def test_category_enum_has_tier1_values():
    assert Category.LISTING_SPOT.value == "LISTING_SPOT"
    assert Category.LAUNCHPOOL_LAUNCHPAD.value == "LAUNCHPOOL_LAUNCHPAD"


def test_direction_enum():
    assert Direction.LONG.value == "LONG"
    assert Direction.SKIP.value == "SKIP"
