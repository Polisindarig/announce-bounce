# Methodology — Chosen Approach and Justification

This document specifies *what* we will build and *why* — i.e., which methodological choices we make at each layer of the pipeline and the academic/practical reasoning behind each one. It is the bridge between `01-literature-review.md` and `03-project-plan.md`.

The recommended pipeline is a **two-stage hybrid**:

```
   Binance announcement (title + body + tags)
                  │
                  ▼
   [Stage 1]  Category Classifier   ──── rules + keyword + light ML
                  │
       category ∈ {LISTING, DELISTING, FUTURES_LAUNCH,
                   PARTNERSHIP, SECURITY_INCIDENT,
                   REGULATORY, FORK_UPGRADE, STAKING_AIRDROP, OTHER}
                  │
                  ▼
   [Stage 2]  Within-category Sentiment Scorer   ──── FinBERT + CryptoBERT
                  │
       sentiment ∈ [-1, +1]
                  │
                  ▼
   [Stage 3]  Decision Engine
                  │
       ├── lookup: (category, sentiment_bucket) → in-sample distribution
       │           of abnormal returns at chosen horizon
       ├── decide: BUY / SELL-SHORT / SKIP
       ├── size:   fractional-Kelly conditioned on (category, sentiment)
       └── set:    TP / SL at calibrated percentiles
                  │
                  ▼
   [Stage 4]  Execution + Backtester (event-driven, cost-aware)
```

We address the user's "you decide and justify" instruction below at every stage.

---

## 1. Why a two-stage hybrid (not pure LLM, not pure rules)

The three candidate paradigms considered were:

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Pure rule/keyword** | Fully transparent, zero-cost inference, easily auditable | Brittle — Binance often rewords announcements; can't capture nuance like "delisting at user request" (mild) vs. "delisting due to insufficient liquidity" (bearish) | ❌ Insufficient |
| **Pure FinBERT/CryptoBERT** | Strong on natural-language sentiment, well-cited (Araci, 2019; ElKulako & Pintus, 2022), reproducible | Trained on financial *news*, not exchange announcements; will conflate category with sentiment (a "DELISTING" announcement is structurally negative, but FinBERT will say "negative" regardless of the cause, hiding the within-category variation we care about) | ❌ Insufficient alone |
| **Pure LLM zero-shot** (GPT-4 / Claude) | Highest accuracy on out-of-distribution text, can extract structured fields and reasoning | Cost (~$0.01–0.03 per announcement × 5,000–10,000 announcements is manageable, but reproducibility is harder; model versions change; thesis defense weaker on "we asked an LLM") | ⚠️ Useful as auxiliary, not primary |
| **Two-stage hybrid** (rules+keyword for category, FinBERT-family for sentiment) | Reproducible, interpretable, defensible academically, and leverages each method where it is strong: category is structural and rule-friendly; sentiment within category is linguistic | More engineering effort | ✅ **Adopted** |

We additionally use an LLM (GPT-4 class) **only** for:
1. **Labeling validation**: blind double-annotation of a held-out 500-announcement subset to estimate classifier accuracy. LLM is the second annotator alongside a human.
2. **Edge cases**: announcements flagged as `OTHER` by the rule layer with low classifier confidence get an LLM "second opinion." The LLM's output is logged but applied with a confidence threshold so behavior remains reproducible.

This dual approach is defended explicitly in the thesis: we get the rigor of small reproducible models for the main pipeline, *and* an LLM as a quality-assurance instrument — a methodology pattern increasingly common in 2024–2025 NLP-for-finance papers.

## 2. Category Taxonomy (Stage 1)

Categories are constructed from a **bottom-up read of ~200 sampled in-sample announcements**, then formalized. Initial proposal:

| Category | Definition / typical keywords | A-priori hypothesis on price effect |
|---|---|---|
| `LISTING_SPOT` | "Will List X (XYZ)", "Will Open Trading for X" | Strong positive (Hartmann et al., 2019: +14.7% on Binance) |
| `LISTING_FUTURES` | "USDⓈ-M Perpetual Contract for X" | Positive but smaller; informational signal |
| `DELISTING` | "Will Delist", "Will Remove" | Strong negative, fast |
| `PARTNERSHIP_INTEGRATION` | "Launchpool", "Megadrop", "Earn Integration" | Positive, modest, asset-specific |
| `SECURITY_INCIDENT` | "Suspending Deposits/Withdrawals due to…", hack, exploit | Strong negative, mean-reverting |
| `REGULATORY` | jurisdiction restrictions, KYC, compliance | Mixed; jurisdiction-dependent |
| `FORK_UPGRADE` | "Will Support [Network] Upgrade/Hard Fork" | Mostly neutral, occasional positive |
| `STAKING_AIRDROP` | "Launchpool", "Simple Earn", airdrop distribution | Positive, modest |
| `OTHER` | catch-all | Treated as no-signal; not traded |

The taxonomy is **fixed before the OOS window**. Adding a category mid-OOS is forbidden.

## 3. Sentiment Scoring Within Category (Stage 2)

For each announcement we generate three signals:
1. **FinBERT score** ∈ [−1, +1] (Araci, 2019; baseline).
2. **CryptoBERT score** ∈ [−1, +1] (ElKulako & Pintus, 2022; handles tickers and crypto slang).
3. **Loughran-McDonald lexicon ratio** (negative-word density; transparent baseline; Loughran & McDonald, 2011).

We **do not average naively**. We *learn* an in-sample mapping from the 3-tuple → forward return at each horizon, using L2-regularized linear regression. This gives an interpretable weight per signal and a defensible "we used these three established methods and let the data weight them."

Output: a single `sentiment_score` ∈ [−1, +1] per announcement.

## 4. Event Window and Horizon Choice

Following MacKinlay (1997), define for each announcement:
- **t₀** = exchange-published timestamp (UTC).
- **Pre-event window** [t₀ − 30 m, t₀): used for leakage diagnostics, **not** for trading signal.
- **Post-event windows**: [t₀, t₀+1 m], [t₀+1 m, t₀+5 m], [t₀+5 m, t₀+15 m], [t₀+15 m, t₀+1 h], [t₀+1 h, t₀+4 h], [t₀+4 h, t₀+24 h].

For each (category, sentiment-bucket), we estimate the empirical distribution of returns at each horizon in-sample. The **chosen trading horizon** per category is the one that maximizes in-sample expected-return / volatility ratio, with a minimum-sample-size guard (≥ 20 events).

**Important constraint**: the timestamp we observe in the backtest is the *announcement-published* time, not the *scrape-detected* time. In live operation a scraper has detection latency. We bake in a **simulated 30-second execution delay** in the backtester to be conservative (Hartmann et al.'s pre-announcement leakage finding implies real fills will be *worse* than announcement-time fills).

## 5. Decision and Position Sizing (Stage 3)

For each new announcement at OOS time *t*:
1. Compute (category, sentiment_score, sentiment_bucket).
2. Look up `(category, bucket)` row in the frozen in-sample table.
3. If `expected_return / volatility < threshold` (e.g., 0.3) **or** sample size is small → **SKIP**.
4. Otherwise compute **fractional Kelly** position size:
   `f* = (p·b − q) / b` with `p`, `q` = empirical win/loss probabilities and `b` = avg win / avg loss, both from in-sample data for that bucket. Apply **25% of full Kelly** and **cap at 5% of equity per trade**.
5. **TP** = in-sample 70th-percentile favorable move at chosen horizon.
6. **SL** = in-sample 30th-percentile adverse move at chosen horizon (i.e., we accept that ~30% of trades hit SL by design).
7. **Time-stop** = horizon end.

The trade closes at the first of TP / SL / time-stop. This is *triple-barrier labeling* (López de Prado, 2018, ch. 3) operationalized as the exit rule itself — making the in-sample labels and the live execution mathematically identical, which is a strong methodological coherence point.

## 6. Backtester Design (Stage 4)

Event-driven, custom, ~500 lines of Python. Key properties:
- **Bar resolution**: 1-minute OHLCV (Binance public klines).
- **Fills**: assume TP/SL fills at the *worst* price within the bar that crosses the level. Time-stop fills at bar close.
- **Costs**: taker fee 0.10% per side (0.20% round-trip) + a category-specific slippage assumption (50 bps for new listings, 10 bps for liquid pairs).
- **Funding rates**: included only for `LISTING_FUTURES` shorts/longs held > 8 h (rare in our setup).
- **Position cap**: max 5 simultaneous positions; one position per symbol at a time.

Output: per-trade log, equity curve, summary metrics (CAGR, Sharpe, Sortino, max drawdown, win rate, profit factor, per-category breakdown).

## 7. Statistical Hypothesis Tests

For the thesis Results chapter we will report:
- **H1**: Within each category, in-sample mean abnormal return ≠ 0 (t-test with Newey-West HAC standard errors).
- **H2**: Bot OOS Sharpe ratio > 0 (bootstrap CI on Sharpe, n=10,000 resamples).
- **H3**: Bot OOS Sharpe > Sharpe of an equal-weight buy-every-LISTING baseline (paired bootstrap).
- **H4**: Category-conditional sizing outperforms category-blind sizing (paired bootstrap on per-trade returns).
- **Robustness**: parameter-stability across rolling 6-month sub-windows; alternative cost assumptions ±50%.

## 8. What We Are *Not* Doing (and why)

- **Reinforcement learning.** Insufficient events, opaque defense, high overfit risk (see §7 of the lit review).
- **On-chain features.** Out of scope; would balloon data engineering.
- **Order-book microstructure.** Binance does not publish historical L2 order book; reconstructing it is a thesis on its own.
- **Multi-exchange execution.** Useful in practice but distracts from the announcement-effect research question.
- **Multilingual announcements.** Binance publishes in English first then localizes; we use only the English version to avoid translation noise.

## 9. Validity Threats and Mitigations

| Threat | Mitigation |
|---|---|
| Look-ahead bias in sentiment models | All models frozen on first 24 months of *text only* before touching OOS prices |
| Overfitting on category-horizon grid | Minimum-sample guard (≥ 20 events) + parameter-stability across rolling sub-windows |
| Survivorship bias | Use point-in-time symbol universe; explicitly keep delisted tokens in the dataset |
| Announcement-timestamp inaccuracy | 30-second simulated execution delay; sensitivity analysis at 0/30/60/120 s |
| Slippage under-estimation | Use 75th-percentile observed spread on first-minute bars after listings as slippage proxy |
| Multiple-testing inflation | Pre-register categories and horizons in this document; the OOS test set is touched exactly once |
| LLM non-reproducibility | LLM used only for QA/labeling, with version pinned; primary pipeline is FinBERT/CryptoBERT |
