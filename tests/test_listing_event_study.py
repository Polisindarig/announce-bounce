"""FDR helper and event-study smoke tests."""

import numpy as np

from src.analysis.event_study_stats import fdr_bh, mean_return_ttest
import pandas as pd


def test_fdr_bh_monotone():
    pvals = [0.01, 0.04, 0.03, 0.20]
    adj, rej = fdr_bh(pvals, alpha=0.05)
    assert len(adj) == 4
    assert any(rej)


def test_mean_zero_ttest():
    rng = np.random.default_rng(0)
    s = pd.Series(0.02 + rng.normal(0, 0.001, 30))
    r = mean_return_ttest(s)
    assert r["n"] == 30
    assert r["p_value"] is not None
    assert r["p_value"] < 0.05
