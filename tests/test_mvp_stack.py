"""End-to-end MVP: classify, score, decide, backtest imports."""

from datetime import datetime, timezone

import pandas as pd

from src.backtest.engine import run_backtest
from src.sentiment.category_classifier import Category, classify
from src.sentiment.sentiment_scorer import score
from src.strategy.decision_engine import Direction, decide


def test_classify_listing_spot():
    cat, conf = classify("Binance Will List FOO (FOO)", catalog_name="new_cryptocurrency_listing")
    assert cat == Category.LISTING_SPOT
    assert conf > 0.4


def test_classify_delisting():
    cat, _ = classify("Notice on Delisting of BARUSDT", catalog_name="delisting")
    assert cat == Category.DELISTING


def test_decide_skips_delisting():
    d = decide(
        "1",
        Category.DELISTING.value,
        0.9,
        "BAR",
        datetime.now(timezone.utc),
    )
    assert d.direction == Direction.SKIP


def test_decide_long_when_listing_positive_sentiment():
    d = decide(
        "2",
        Category.LISTING_SPOT.value,
        0.2,
        "FOO",
        datetime.now(timezone.utc),
    )
    assert d.direction == Direction.LONG
    assert d.size_pct_equity > 0


def test_classify_launchpool():
    cat, _ = classify("New Launchpool: Foo (FOO)", catalog_name="crypto_airdrop")
    assert cat == Category.LAUNCHPOOL_LAUNCHPAD


def test_score_bounded():
    s = score("Binance Will List NEWTOKEN with launch rewards", "")
    assert -1.0 <= s <= 1.0


def test_run_backtest_runs(tmp_path):
    ev = tmp_path / "ev.parquet"
    df = pd.DataFrame(
        {
            "announcement_id": ["a"],
            "title": ["Binance Will List ZED (ZED)"],
            "catalog_name": ["new_cryptocurrency_listing"],
            "symbol": ["ZED"],
            "published_at": pd.Timestamp("2026-03-01T12:00:00Z"),
            "ret_15m": [0.01],
        }
    )
    df.to_parquet(ev, index=False)

    dw = tmp_path / "dw.yaml"
    dw.write_text(
        "in_sample_start: '2025-06-01'\n"
        "in_sample_end: '2026-02-14'\n"
        "oos_start: '2026-02-14'\n"
        "oos_end: '2026-05-14'\n"
    )

    cfg = tmp_path / "backtest_baseline.yaml"
    cfg.write_text(
        f"events_path: {ev.resolve()}\n"
        f"window_config: {dw.resolve()}\n"
        "horizon_col: ret_15m\n"
        "fee_roundtrip: 0.002\n"
        "slippage_each_leg: 0.00075\n"
    )

    r = run_backtest(str(cfg))
    assert r["n_long_trades"] == 1
    assert r["mean_pnl"] is not None
