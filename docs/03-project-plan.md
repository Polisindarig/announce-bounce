# Project Plan — v5 (Final Pre-Registration)

> **Thesis contribution:**
> **"Measuring the category-conditional short-horizon price impact of Binance announcements and testing tradability under realistic transaction-cost and latency assumptions."**
>
> **Revision history:**
> - **v1 (initial):** Broad scope — all coins, all categories, live trading, Kelly sizing, 10 event windows.
> - **v2:** Scope narrowed: sentiment → secondary layer; live trading → removed; windows pre-registered; baselines expanded; ablation study added.
> - **v3:** USDT-only pairs; futures_launch clarified; slippage simplified; FDR headline baseline declared; classifier targets adjusted; CryptoBERT leakage acknowledged; event-contamination filter added; reproducibility manifest added.
> - **v4:** Tier 1/Tier 2 category split (8→4 deep); subwindow drift decision rule (CV threshold); intra-bar TP/SL pessimistic convention; slippage → tier-floor only; M0/M1 ablation threshold (Sharpe ≥ 0.15); Politis-White block bootstrap; 800 labels + 5-fold CV; index weekly rebalance; CCXT Plan B; contamination adaptive window.
> - **v5 (this):** Revision note updated; phase durations decoupled from calendar weeks; robustness/calibration overlap resolved; conditional robustness tests; risk register refreshed; walk-forward rejection justified; contamination demotion rule clarified; timestamp discipline reframed as future-work infrastructure.

Phases are executed **sequentially** with no fixed calendar deadline. Duration estimates are indicative only.

---

## 0. Locked-In Design Decisions (Pre-Registered)

These are committed **before** any analysis on the in-sample window. Changing any of them later requires a written justification in the thesis and re-running with the new spec.

### 0.1 Scope
- **Market:** Binance **Spot, USDT-quoted pairs only.** This is the single biggest simplification: avoids quote-currency conversion (BTC/ETH/BNB pairs), homogenizes liquidity comparisons, and matches the most-liquid segment of Binance spot.
- **Pair-selection rule:** For each event, the traded pair is the `<COIN>/USDT` spot pair. If multiple pairs exist for the same base asset (e.g., COINUSDT and COINFDUSD), use `COINUSDT`. If no USDT pair exists or it does not pass the liquidity filter, the event is **analyzed in the event study but skipped in the strategy**.
- **Asset universe:** Coins with a USDT pair on Binance at any point during the data window (**point-in-time universe**, no survivorship bias).
- **Liquidity filter at execution time:** 24 h USDT volume of the traded pair ≥ \$1M, measured at `t_0 − 1h`.
- **Language filter:** English-only announcements (multilingual posts processed in their English version).
- **Categories — two tiers:**

  **Tier 1 (full event study + strategy + backtest):**
  1. `listing_spot` — new spot listing
  2. `futures_launch` — new perpetual/quarterly futures contract
  3. `launchpool_launchpad` — token-sale or yield-farming launches
  4. `staking_earn` — new staking / earn product

  All Tier 1 events are **executed on the spot USDT pair**. For `futures_launch`: we do *not* trade the futures contract; we trade the spot USDT pair of the same underlying coin as a reaction to the futures-launch announcement (an information event). If no USDT pair exists at event time, the event is skipped from the strategy.

  **Tier 2 (descriptive analysis only — mean/median AR table + one paragraph in thesis, no strategy, no robustness):**
  5. `delisting` — pair/token removal
  6. `maintenance_suspension` — deposits/withdrawals halted, system maintenance
  7. `airdrop_fork` — token distribution / fork support
  8. `regulatory_security` — security incidents, regulatory actions, freezes

  Tier 2 categories are reported for completeness and to show the bot *chose* not to trade them. They are not part of the headline result, robustness tests, or FDR test family.

  **Delisting as forced-exit signal:** If the bot holds an open Tier 1 position and a `delisting` announcement appears for the same asset, exit immediately (market sell), overriding TP/SL/time-stop. This is the only Tier 2 category that interacts with the strategy.

### 0.1.1 Listing event-time convention (CRITICAL)
For `listing_spot` events, the coin is **not yet tradable on Binance at announcement time**. We distinguish:
- `t_announcement` — when the "Binance Will List X" post is published
- `t_binance_trading` — when X/USDT spot trading actually opens on Binance (typically 6–48 h later, stated in the announcement body)

**The bot can only execute on Binance.** Therefore for `listing_spot`:
- **Event time `t_0` ≔ `t_binance_trading`** (the first 1-min bar on Binance for that pair). This aligns with Ante (2019)'s "listing day" definition.
- The pre-`t_binance_trading` price action on other exchanges (Gate, MEXC, KuCoin) is **measured and reported descriptively** using third-party data (CoinGecko / CCXT public endpoints) as part of the discussion, to quantify the **opportunity cost of being Binance-only**. This is reported as a finding ("a multi-exchange variant would have captured an additional X% on average") but is not part of the traded strategy.
- **Multi-exchange execution is documented as Future Work**, not implemented.

For all other categories, `t_0 ≔ t_announcement`.

### 0.2 Time periods
- **Total data window:** 30 months ending at the data-extraction date.
- **In-sample (training & calibration):** First 24 months of the window.
- **Out-of-sample (frozen test):** Final 6 months of the window. **One run only.**
- **Paper-trading demo window:** Latest 7 days of live announcements at defense time. This is **not** part of the research results; it is illustrative only.
- All three boundaries committed in `config/data_window.yaml` and git-tagged before any modeling.

### 0.2.1 Timestamp discipline (CRITICAL for event-study validity)
For every announcement, the following timestamps are stored separately:
| Field | Meaning |
|---|---|
| `published_at` | Timestamp displayed on the Binance announcement page (proxy for original publication). |
| `updated_at` | If Binance edits the post, the latest edit timestamp. |
| `first_seen_at` | If scraping forward in time (live / paper-demo), the first time our scraper observed the post. Null for historical data. |
| `scraped_at` | Timestamp of the latest scrape that produced the current row. |

`first_seen_at` and `scraped_at` are stored primarily as **infrastructure for future live-bot extensions** and for the paper-trading demo. Historical backtest uses only `published_at`.

**Event-time conventions:**
- **Historical (in-sample + OOS) backtest:** `t_0 = published_at` (no `first_seen_at` is available retrospectively). Acknowledged as a **timestamp proxy** in §Methodology limitations.
- **Live / paper-trading demo:** `t_0 = first_seen_at` (the most honest signal arrival time for a real bot).
- **Latency model is applied as `t_0 + latency` regardless** of which timestamp is used.
- A robustness check explicitly stresses the listing case by re-running the OOS backtest with `t_0 = t_binance_trading + 1` minute (worst-case bar-aligned), to bound the effect of `published_at` inaccuracy on the headline result.

### 0.3 Event windows (PRE-REGISTERED, fixed ex-ante)
**Six horizons, reported in all analyses:**

| Window | Purpose |
|---|---|
| `t+1m` | Immediate impact; informs market-order vs limit-order decision |
| `t+5m` | Realistic execution horizon after latency |
| `t+15m` | TP-hit window (most pumps peak here per Ante 2019 + Empirica 2024) |
| `t+1h` | Mean-reversion onset; primary exit horizon candidate |
| `t+4h` | Mean-reversion confirmation |
| `t+24h` | Long-horizon control — supports time-stop justification |

**Multiple-testing correction:**
- **Headline test family:** 6 horizons × 4 Tier 1 categories = **24 tests**, computed on the **index-adjusted abnormal return** baseline only. Benjamini-Hochberg FDR, α = 0.05.
- **Secondary (robustness) test families:** Same 24 tests repeated under raw-return and BTC-adjusted baselines. These are reported with their own FDR corrections but are labeled as robustness, not headline.
- Tier 2 categories receive descriptive statistics only (mean, median, n) with no formal hypothesis testing.

### 0.4 Abnormal-return model
Three baselines reported side-by-side for every result:
1. **Raw return** — `r_coin(t)`
2. **BTC-adjusted** — `r_coin(t) − r_BTC(t)` (market-adjusted, MacKinlay 1997 standard)
3. **Equal-weight crypto-index-adjusted** — `r_coin(t) − r_index(t)`, where the index is the **equal-weighted Top-50 Binance spot USDT pairs ranked by 24h USDT volume**. The index composition is **rebalanced weekly** (every Monday 00:00 UTC) using volume at the prior Sunday 23:59 UTC. This fixed cadence avoids per-event rebalancing (which would create a different benchmark for every event and introduce survivorship/momentum bias). It is an *exchange-internal benchmark* and labeled as such in the thesis.

No CAPM/factor-model beta is estimated, given the intraday focus and short estimation windows. This is acknowledged as a limitation in §Methodology.

### 0.5 Execution model
- **Order type:** market order (worst-case slippage scenario).
- **Fees:** 0.10% taker (no BNB discount in base case; sensitivity test with 0.075%).
- **Return-measurement convention:** Event-study returns are measured from `t_0` (event time). Strategy returns are measured from `t_0 + latency` (the actual fill timestamp). The two are reported separately and never conflated.
- **Slippage model — tier-floor (simple, transparent):**
  | Pair tier (by 24h USDT volume at `t_0 − 1h`) | Slippage (bps) |
  |---|---|
  | Top-20 | 5 |
  | Top-21–100 | 15 |
  | Beyond Top-100 | 50 |
  | First 5 minutes of a `listing_spot` event (any tier) | 100 |

  Rationale for simplicity: a volume-proportional impact model (Almgren-Chriss style) requires order-book depth data that Binance does not publish historically. Rather than calibrate a k-parameter on fiction, we use a conservative tier-floor and stress-test it at ±50% in Phase 7 robustness. The order-size cap (below) ensures we stay in the small-order regime where tier-floor is a reasonable proxy.
- **Order-size cap:** Per-trade notional cannot exceed **0.5%** of the trailing 1-min USDT volume of the pair. This is a hard cap independent of risk sizing (§0.6) — the smaller of the two binds.
- **Latency stress test:** strategy run at **5 s, 30 s, 60 s, 120 s** delay; report all four. **Base case = 30 s.** Justification: if scraper polls every 60 s, the announcement detection latency is `Uniform(0, 60)` with mean 30 s; adding ~2–5 s for classification + REST order submission gives ~32–35 s. 30 s is a rounded conservative estimate. The actual latency *distribution* is discussed in §Methodology; robustness at 5 s and 120 s bounds the sensitivity.

### 0.6 Position sizing, SL/TP, and exit logic

#### SL/TP calibration
- **Per-category SL (stop-loss):** `SL_fraction` for Tier 1 category *c* is the absolute value of the **30th-percentile** in-sample adverse excursion within the category's primary horizon, clamped to `[1%, 8%]`.
- **Per-category TP (take-profit):** `TP_fraction` is the **70th-percentile** in-sample favorable excursion within the category's primary horizon, clamped to `[1%, 30%]`.
- Both frozen in the lookup table before OOS.

#### Subwindow parameter-drift decision rule (PRE-REGISTERED)
The in-sample period (24 months) is split into 4 × 6-month subwindows. For each Tier 1 category, the coefficient of variation (CV) of the SL and TP fractions across the 4 subwindows is computed.
- **If CV ≤ 0.40** for both SL and TP: use the **full 24-month** percentiles (stable regime).
- **If CV > 0.40** for either SL or TP: use the **last 12-month** percentiles only (regime-shift adaptation).
- This rule is applied per-category independently. The CV values and the resulting table-selection decision are reported in the thesis.

#### Intra-bar TP/SL evaluation convention (PRE-REGISTERED, CRITICAL)
TP and SL are evaluated against the **high** and **low** of each 1-minute bar, not the close:
- If `bar.high ≥ entry × (1 + TP_fraction)` → TP triggered; fill at TP level.
- If `bar.low ≤ entry × (1 − SL_fraction)` → SL triggered; fill at SL level.
- **If both trigger in the same bar → pessimistic assumption: SL is taken.** This is a worst-case convention that biases *against* the strategy, ensuring reported Sharpe is conservative.
- This convention is locked before any backtest run and is not varied in robustness checks (it is a structural assumption, not a tunable parameter).

#### Position notional sizing
$$
\text{notional} = \min\Big(\frac{\text{account\_equity} \times 0.01}{\text{SL\_fraction}},\quad 0.005 \times V_{1\text{m}}\Big)
$$
i.e., the smaller of "1% account risk if SL hits" and "0.5% of trailing 1-min pair volume". Either constraint can bind.

#### Position and loss limits
- **Position cap:** max 3 concurrent open positions, no two on the same base asset.
- **Daily loss limit:** −5% of account equity → trading halted for the rest of UTC day. This limit's binding frequency is reported in the in-sample consistency run; if it triggers in < 1% of trading days in-sample, it is documented as non-binding and its effect on OOS is noted as negligible.

#### Exit priority order (first match wins, evaluated per 1-min bar)
1. **Delisting override** — if a `delisting` announcement appears for the asset, exit at next bar (market sell), overriding TP/SL/time-stop.
2. **TP hit** — close at TP level (per intra-bar convention above).
3. **SL hit** — close at SL level (per intra-bar convention above).
4. **Time-stop** — close at bar close of the category-specific horizon (from frozen lookup table).

- **Kelly criterion:** documented as future work, not implemented.

### 0.7 Sentiment usage
- Sentiment is a **secondary feature**, not the primary signal.
- The thesis explicitly tests whether sentiment adds value via an **ablation study** (§ Phase 5.5).
- Two models compared: rule-based category-only (M0) vs. category + within-category CryptoBERT sentiment bucket (M1).

### 0.8 Live trading
- **Not in scope.** The deliverable bot runs in **paper-trading mode only** on the latest 7 days for the defense demo. The paper-demo window is not used to compute headline results.

### 0.9 Event-contamination filter
For every event in the analysis, flag whether another announcement for the same base asset occurred in `[t_0 − 24h, t_0 + 24h]`.
- **Headline results** are reported on the **non-contaminated subset**.
- **Full-sample results** (including contaminated events) are reported as a robustness check.
- **Per-category contamination rate** is computed in-sample. If a Tier 1 category has > 50% contamination (likely for `maintenance_suspension` if it were Tier 1, but less likely for listing/launchpool), the contamination window is tightened to ±6h for that category specifically, and this is documented. If contamination still exceeds 50% after tightening, the category is **demoted to Tier 2** (descriptive only, removed from trading strategy) and this demotion is documented in the thesis.

### 0.10 Reproducibility manifest
Before the OOS backtest is executed, the following fingerprint is generated and committed:
| Artifact | Hash type |
|---|---|
| `config/oos.yaml` | SHA-256 |
| `config/category_horizon_table.parquet` | SHA-256 |
| Classifier model artifact | SHA-256 |
| Sentiment model artifact (if M1 wins ablation) | SHA-256 |
| Source-tree state | `git rev-parse HEAD` |
| Python/package versions | `pip freeze` snapshot |
| GPT-4 model version + date (if used in classifier QA) | string log |
The OOS result file `oos_run.json` embeds this manifest. The thesis prints it as a table in §Reproducibility. This makes the "one OOS run" claim *verifiable* by anyone with the repo, not just trusted on faith.

---

## Phase 1 — Data Collection

**Goal:** Clean `announcements × price_bars` dataset for 30 months.

### Tasks
1. **Binance announcement scraper** (`src/scraper/announcements.py`)
   - URL: `https://www.binance.com/en/support/announcement` (JS-rendered → `playwright`)
   - Fallback: undocumented JSON endpoint `bapi/composite/v1/public/cms/article/catalog/list/query`
   - Pull all English-language announcements in window
   - Rate limit: 1 req / 2 s with `tenacity` retry/backoff
   - Persist raw HTML snapshot **before** parsing (re-parseable forever)
   - Schema: `announcement_id, timestamp_utc, title, body_html, body_text, category_native, url, scraped_at, language`
2. **Coin/ticker extraction** (`src/scraper/symbol_extractor.py`)
   - Regex over title + body
   - Cross-reference against historical Binance pairs list
   - Manual override table for ambiguous tickers
3. **Listing-time extractor** (`src/scraper/listing_time.py`) — for `listing_spot` events only
   - Parse the announcement body for the stated trading-open time (Binance always publishes UTC timestamp)
   - Cross-check against actual Binance OHLCV: `t_binance_trading` = timestamp of the first non-null 1-min bar for the new pair
   - Persist both `t_announcement` and `t_binance_trading` per event; the difference (announcement-to-trading lag) is a feature in its own right
4. **OHLCV pull from Binance** public REST `/api/v3/klines`
   - 1-minute bars, max 1000/call
   - Per-event window: `t_0 − 2h` to `t_0 + 25h` where `t_0` is the category-specific event time (§0.1.1)
   - Also pull BTC and Top-50 universe for the full 30-month window (baseline construction)
   - Parquet, partitioned by `symbol/year/month`
5. **Multi-exchange OHLCV pull (descriptive only)** via CCXT for `listing_spot` events
   - Pull 1-min bars from Gate, MEXC, KuCoin (whichever has the pair) for the window `t_announcement − 1h` to `t_binance_trading + 1h`
   - Used in the Discussion chapter to quantify the pre-Binance-trading pump (opportunity cost analysis)
   - **Not** used by the trading strategy
   - **Plan B:** CCXT historical 1-min data quality varies by exchange and age. If a given exchange has no 1-min data for events > 12 months old, fall back to daily OHLCV. If no exchange has data for a listing, mark as `multi_exchange_data = missing` and exclude from the opportunity-cost analysis. Report the coverage rate (% of listing events with multi-exchange data).
6. **Join** announcements ↔ Binance price bars → `data/processed/events.parquet`
5. **Sanity checks** in `notebooks/01_eda.ipynb`:
   - Announcement count per week (expect steady cadence)
   - 20 random listings — qualitative pump check
   - 50-event manual audit for parsing errors

### Deliverables
- `data/raw/announcements.jsonl` + raw HTML snapshots
- `data/raw/klines/<symbol>.parquet`
- `data/processed/events.parquet`
- `notebooks/01_eda.ipynb`

### Risks
| Risk | Mitigation |
|---|---|
| Binance changes page structure | Thin parser layer; raw HTML kept for reparse |
| Rate-limit ban | Conservative 1 req / 2 s; pause on 429 |
| Symbol disambiguation | Manual override table |
| Missing 1-min bars for low-cap coins | Mark as missing, exclude from event study if estimation window incomplete |

---

## Phase 2 — Data Pre-processing (Category Labeling & Classifier)

**Goal:** Frozen category classifier.
- **Minimum acceptable:** macro-F1 ≥ 0.85, Cohen's κ ≥ 0.75. Per-class precision/recall reported separately because category support is unbalanced.
- **Stretch target:** macro-F1 ≥ 0.90, κ ≥ 0.80.
- Trading-category accuracy (the 4 entry-signal categories) is reported separately and weighed more heavily in the decision to ship vs. iterate.

### Tasks
1. **Hand-label 800 announcements**, stratified across all 8 categories with **active oversampling of rare categories** (regulatory_security, airdrop_fork) to ensure ≥ 60 examples per class.
   - Two annotators (you + advisor/friend).
   - Compute Cohen's κ on a shared 200-example overlap set.
2. **Evaluation split:** Stratified 5-fold cross-validation on the 800-set. Report mean ± std of macro-F1 and per-class metrics across folds.
3. **Rule-based classifier** (`src/classifier/rules.py`)
   - Regex over titles ("Binance Will List", "Delisting Notice", "Launchpool", etc.)
   - Expected coverage ≥ 80%.
4. **TF-IDF + logistic-regression fallback** for residuals.
5. **LLM cross-check** (GPT-4 zero-shot, model version and date logged) on a held-out 200-set → agreement audit.
6. **Validation:** confusion matrix, per-class precision/recall/F1.  
   **Separate accuracy report for Tier 1 (4 trading) categories** — these drive the strategy and matter more than overall accuracy.
7. **Freeze** classifier as `category-classifier-v1.0` git-tag.

### Deliverables
- `data/labeled/category_labels.csv`
- `src/classifier/` + pinned model artifact
- `notebooks/02_category_validation.ipynb`

---

## Phase 3 — Data Pre-processing (Sentiment Scoring)

**Goal:** Frozen per-category sentiment scorer using CryptoBERT (ElKulako 2022).

### Tasks
1. CryptoBERT inference on all in-sample announcements → continuous score ∈ [−1, +1].
2. Bucket into 3 bins: negative [−1, −0.33), neutral [−0.33, +0.33], positive (+0.33, +1].
3. Validate: distribution per category; spot-check edge cases.
4. Persist as `src/sentiment/cryptobert_inference.py` + cached scores.

**Note:** Phase 3 output is consumed only by the M1 (with-sentiment) model. If M0 (rules-only) outperforms M1 in the ablation, the thesis concludes sentiment is not value-additive — itself a publishable finding.

### Deliverables
- `data/processed/sentiment_scores.parquet`
- `notebooks/03_sentiment_validation.ipynb`

---

## Phase 4 — Exploratory Data Analysis (Event Study & Calibration)

**Goal:** Frozen category-horizon lookup table that drives the bot.

### Tasks
1. **Compute abnormal returns** under all 3 baselines (raw, BTC-adj, index-adj) at all 6 horizons for every event in the in-sample period.
2. **Per-category statistics:**
   - Mean, median, std, win-rate
   - 30th / 70th percentile of returns (TP/SL calibration)
   - Max favorable / adverse excursion within window
   - Sample size n
3. **Hypothesis tests** (H₀: mean AR = 0) with Benjamini-Hochberg FDR correction over 48 tests.
4. **Per-category optimal horizon selection:** the horizon that maximizes in-sample Sharpe **subject to n ≥ 30 and FDR-adjusted p < 0.05**.
5. **Freeze** lookup table: `config/category_horizon_table.parquet`
6. **Required plots:**
   - CAR curves per category with 95% CI (lit-review-standard event-study plot)
   - Heatmap: category × horizon → mean AR
   - Distribution histograms per (category, horizon)

### Deliverables
- `config/category_horizon_table.parquet`
- `notebooks/04_event_study.ipynb`

---

## Phase 5 — Data Modelling (Strategy & Backtester)

**Goal:** Event-driven backtester producing trade log + equity curve.

### Tasks
1. **Decision engine** (`src/strategy/decision_engine.py`) — pure function `(announcement) → Trade | None`.
   - Reads frozen category-horizon table.
   - Two variants: **M0 (category-only)** and **M1 (category + sentiment bucket)**.
   - Applies liquidity filter, position cap, daily-loss limit.
2. **Backtest engine** (`src/backtest/engine.py`):
   - Iterate events chronologically.
   - Open trades at `t + latency` with slippage model.
   - Per subsequent 1-min bar: check TP / SL / time-stop.
   - Log fills with all costs.
3. **Unit tests** (`tests/`):
   - TP-hit, SL-hit, time-stop
   - Liquidity filter
   - Concurrent-position cap
   - Fee + slippage accounting
   - **Look-ahead assertion test**: every decision uses only data with `ts < trade_open_time`
4. **In-sample consistency run.** This run is used solely to (a) verify implementation correctness (e.g., trades open and close at expected timestamps, fees and slippage apply as specified), and (b) inspect whether calibrated signals produce economically plausible behavior. Lack of in-sample profitability is **not** automatically treated as a bug — it may indicate the calibrated signals are weak relative to costs, which is itself a research finding.

### Phase 5.5 — Ablation Study (PRE-REGISTERED decision rule)
Run M0 (category-only) and M1 (category + CryptoBERT sentiment bucket) separately on the in-sample window.
- Report in-sample Sharpe difference with bootstrap 95% CI.
- **Decision rule:** M1 is selected for OOS **only if** its in-sample Sharpe exceeds M0's by ≥ 0.15 AND the bootstrap 95% CI of the difference excludes zero. Otherwise, **M0 is selected** (Occam's razor: do not add complexity without clear evidence of improvement).
- This threshold (0.15) is pre-registered and not tuned after observing results.

### Deliverables
- `src/strategy/`, `src/backtest/`, `tests/`
- `notebooks/05_in_sample_run.ipynb`
- `notebooks/05b_ablation.ipynb`

---

## Phase 6 — Model Evaluation (Out-of-Sample Test)

**Goal:** Headline thesis result.

### Tasks
1. **Freeze everything**: classifier, sentiment (if M1 won), lookup table, code, cost model, latency = 30 s base.
2. **Run backtester on the last 6 months — exactly once.**
3. **Headline metrics:** CAGR, Sharpe, Sortino, Calmar, max DD, win rate, profit factor, per-category breakdown.
4. **Baselines:**
   - **B1:** Buy every `listing_spot` event at `t_binance_trading + 30 s` (same latency as the strategy), equal-weight, 1 h hold, same fee/slippage model.
   - **B2:** Buy-and-hold BTC over the same window.
   - **B3:** Buy-and-hold equal-weight Top-50 crypto index.
5. **Significance tests:** **Bootstrap confidence intervals** (10,000 resamples, stationary block bootstrap) are the **primary** inference tool for Sharpe and CAGR differences vs. each baseline. Block length is determined by the **Politis-White (2004) automatic optimal block-length selection** procedure, computed on the in-sample daily return series and frozen before OOS. The selected block length and its ACF justification are reported in the thesis. Paired *t*-tests and the Sharpe-ratio test (Memmel 2003) are reported as **secondary** corroboration only.

### Stop criterion
**If OOS Sharpe ≤ 0:** do **not** re-tune. Document honestly as a negative result with attribution. Negative-result theses with clean methodology are defensible; p-hacked positive theses are not.

### Deliverables
- `backtest/results/oos_run.json`
- `notebooks/06_oos_results.ipynb`

---

## Phase 7 — Result Interpretation (Robustness & Sensitivity)

Required tests:
1. **Latency stress:** 5 s, 30 s, 60 s, 120 s — report all.
2. **Cost sensitivity:** fees ±50%, slippage ±50%.
3. **Subwindow performance stability:** Run the frozen OOS strategy on each of the 4 × 6-month in-sample subwindows individually. Report per-subwindow Sharpe, win-rate, and profit factor. This is **distinct from** the §0.6 calibration-window selection (which uses CV to decide *which* data to calibrate TP/SL from); this test checks whether the *final frozen strategy* would have performed consistently across different market regimes.
4. **Universe sensitivity:** rerun with Top-100 only vs full universe.
5. **Sentiment-bucket boundary sensitivity (conditional):** tested **only if M1 was selected** per §5.5. Boundaries at ±0.25 vs ±0.33 vs ±0.40. If M0 was selected, this test is omitted (no sentiment buckets to vary).

### Deliverable
- `notebooks/07_robustness.ipynb`

---

## Phase 8 — Thesis Writing & Presentation (parallel with later phases)

Outline in `docs/04-thesis-outline.md`.
- Week 12: Chapters 1–2 (Intro, Lit Review) — already drafted in `docs/01-literature-review.md`
- Week 13: Chapters 3–4 (Data, Methodology) — from `docs/02-methodology.md`
- Week 14: Chapters 5–6 (Results, Discussion) — from notebooks 04, 06, 07
- Week 15: Conclusion + full citation pass

---

## Phase 9 — Defense Prep

- 20-slide deck.
- **Paper-trading demo** on latest 7 days of live announcements (no real money, no execution to exchange).
- Q-bank for anticipated jury questions (look-ahead, overfitting, p-hacking, generalizability, ethics).

---

## Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| 1 | Binance blocks scraper IP | Med | High | Conservative rate-limit; raw HTML snapshots |
| 2 | OOS Sharpe ≤ 0 | Med | Med | Pre-committed to honest negative result |
| 3 | Project stalls / loss of momentum | Med | Med | Sequential phase structure with clear deliverables; thesis writing parallel |
| 4 | Sentiment ablation shows no value | Med | Low | This is itself a finding (M0 baseline is the bot) |
| 5 | Advisor disagrees with scope | Med | High | Share `01-` and this doc in Week 1 |
| 6 | Look-ahead leakage | Low | Critical | Automated unit test asserting `decision_time < open_time` |
| 7 | Category classifier κ < 0.75 | Low | Med | Iterate labeling guidelines; increase from 800 to 1000 samples with targeted oversampling |
| 8 | Insufficient sample size per category | Med | Med | Pool subcategories; report n alongside every stat |

---

## Definition of Done

1. `python -m src.backtest.engine --config config/oos.yaml` reproduces OOS metrics byte-for-byte from a fresh checkout.
2. Thesis PDF ~40 pages, every figure regenerable from notebooks.
3. Classifier, sentiment scorer (if M1 selected), and lookup table all git-tagged at OOS-run version.
4. Advisor signed off on methodology **before** OOS was run.
5. All 24 headline statistical tests reported with FDR-adjusted p-values.
6. All 4 latency scenarios, 3 baselines, and 4–5 robustness tests (5 if M1 selected, 4 if M0) reported.

---

## Known Limitations (to discuss in thesis §Methodology)
1. **Timestamp proxy:** historical `published_at` may not equal true market-information-arrival time; `first_seen_at` is only available for live data. Bounded by listing-time robustness check.
2. **No CAPM/factor beta** in abnormal-return model — intraday focus and short estimation windows do not support reliable beta estimation. BTC- and index-adjustment used instead.
3. **Single OOS window** (6 months) rather than walk-forward. Walk-forward was considered but rejected: with only 4 Tier 1 categories and ~30 months of data, each walk-forward fold would contain too few events per category for reliable TP/SL percentile estimation (n < 30 per fold is likely for smaller categories like `staking_earn`). The 4-subwindow performance stability test in Phase 7 provides a weaker but feasible proxy for temporal robustness.
4. **Spot-USDT-only universe** excludes BTC- and ETH-quoted pairs and may underestimate liquidity available to a more sophisticated execution layer.
5. **Cross-sectional dependence** when one announcement names multiple coins is handled by event-contamination flagging; residual clustering is acknowledged.
6. **Binance-only execution** misses pre-`t_binance_trading` pump on other exchanges for `listing_spot` events; quantified descriptively (§Discussion) but not traded. **This is a headline limitation for the listing category:** the pre-Binance pump may represent the majority of the total listing alpha. OOS results for `listing_spot` must be framed as "the tradable alpha available to a **Binance-only** bot", not the total listing-announcement alpha. The Discussion chapter must explicitly state this.
7. **CryptoBERT temporal leakage:** CryptoBERT (ElKulako 2022) was trained on StockTwits data from Nov 2021 – Jun 2022, which overlaps our in-sample data window. This means the sentiment model may have seen text patterns contemporaneous with our analysis period. We do not fine-tune CryptoBERT (inference-only), which limits the leakage to pretrain-level contamination, but it cannot be fully ruled out. This is acknowledged as a limitation; a cleaner alternative (FinBERT, trained on pre-crypto data) is tested as a sensitivity check if M1 is selected.

## Current Status (2026-05-20)

✅ **Phase 0 — Setup & Pre-flight:** Complete (this document is the lock-in).
✅ **Phase 1 — Data Collection:** 2616 anons scraped, kline verileri mevcut.
✅ **Phase 2 — Data Pre-processing (Category):** 12-sınıf rule-based classifier hazır.
✅ **Phase 3 — Data Pre-processing (Sentiment):** CryptoBERT + FinBERT + lexical baseline tamamlandı.
👉 **NEXT: Phase 4 — Exploratory Data Analysis** (event study & calibration).
