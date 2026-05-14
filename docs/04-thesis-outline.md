# Thesis Outline — Target ~40 Pages

Page budget assumes A4, 1.5 line spacing, Times New Roman 12 pt, ~350 words/page. Adjust to your institution's template.

| # | Chapter | Pages | Word target | Notes |
|---|---|------|-------------|-------|
| 0 | Title page, abstract, acknowledgements, ToC, list of figures/tables | 4 | 400 (abstract) | Abstract = 250–300 words, structured |
| 1 | **Introduction** | 3 | ~1,000 | Motivation, research question, hypotheses, contribution in one paragraph, thesis outline |
| 2 | **Literature Review** | 6 | ~2,000 | Mirror `docs/01-literature-review.md`; trim and tighten for the paper |
| 3 | **Data** | 5 | ~1,700 | Sources, scraping, cleaning, descriptive statistics, taxonomy with examples, in-sample vs. OOS split rationale |
| 4 | **Methodology** | 7 | ~2,400 | Mirror `docs/02-methodology.md`; add formal definitions and pseudo-code; pre-register all hypotheses here |
| 5 | **Empirical Results** | 8 | ~2,800 | Event-study plots per category, sentiment-scorer validation, in-sample lookup table, **OOS headline result**, baselines comparison, robustness |
| 6 | **Discussion** | 3 | ~1,000 | Interpretation, what worked and why, what didn't, limitations |
| 7 | **Conclusion and Future Work** | 2 | ~700 | Summary + three concrete next-step ideas |
| R | References | 2 | – | APA-7, 35–50 references |
| A | Appendices | A1–A3 (pages additional or counted) | – | Full classifier confusion matrix, full hyperparameter table, reproducibility checklist |
| | **Total body** | **~40** | **~12,000** words | |

---

## Chapter-by-Chapter Detail

### Chapter 1 — Introduction (3 pages)

- **1.1 Motivation**: Crypto markets are widely participated by retail; many retail bots react to Binance announcements but few academic studies evaluate this systematically at intraday horizons.
- **1.2 Research question** (verbatim from README).
- **1.3 Hypotheses** (H1–H4 from methodology §7).
- **1.4 Contribution**: The single-paragraph differentiation table — copy verbatim from §9 of the literature review.
- **1.5 Thesis outline**: One sentence per remaining chapter.

### Chapter 2 — Literature Review (6 pages)

Compress `docs/01-literature-review.md` to a tighter, paper-style narrative. Retain all 9 sub-sections; drop ~30% of prose; keep all citations and the gap-analysis table.

### Chapter 3 — Data (5 pages)

- **3.1 Sources**: Binance announcement page, Binance public REST klines.
- **3.2 Scraping methodology**: rate-limiting, parsing, deduplication, completeness check (number of announcements per month vs. press-coverage cross-check).
- **3.3 Symbol resolution**: how we map announcement text to tradable symbols; manual-override table.
- **3.4 Descriptive statistics**:
  - Total events by category (table).
  - Events per month (figure).
  - Distribution of body length, of native Binance category tags.
- **3.5 In-sample / OOS split rationale**: justify the 24/6 split given total of 30 months; cite Pardo (2008).

### Chapter 4 — Methodology (7 pages)

Mirror `docs/02-methodology.md`. Add:
- **4.1 Formal model**: define $R_{i,t}$, $\text{CAR}$, position-sizing equation in display math.
- **4.2 Algorithm 1**: pseudo-code of the decision engine.
- **4.3 Algorithm 2**: pseudo-code of the backtester.
- **4.4 Pre-registered hypotheses and tests**: explicit list, then proceed to results without modification.

### Chapter 5 — Empirical Results (8 pages — the heart of the paper)

- **5.1 Category classifier validation**: confusion matrix, per-class P/R/F1, Cohen's κ between human and LLM annotators.
- **5.2 Sentiment scorer validation**: scatter, R², coefficients of the L2 combiner.
- **5.3 In-sample event study**: for each category, the canonical plot — CAR vs. event time at minute resolution — with 95% CI bands. *This will be your most-screenshot-worthy figure.*
- **5.4 Category × horizon lookup**: the table; highlight which (category, horizon) cells are statistically significant.
- **5.5 Out-of-sample results**:
  - Equity curve vs. B1 (buy-every-listing) and B2 (BTC buy-and-hold).
  - Headline metrics table: CAGR, Sharpe, Sortino, max DD, win rate, profit factor — bot vs. baselines.
  - Bootstrap CIs.
  - Per-category P&L breakdown.
- **5.6 Robustness**: parameter-stability heat-map across rolling sub-windows; cost-sensitivity table; execution-delay sensitivity.

### Chapter 6 — Discussion (3 pages)

- Which categories carried the P&L? (Hypothesis: LISTING_SPOT and SECURITY_INCIDENT, the latter on short side.)
- Why did the others underperform expectation? Possible explanations.
- Comparison to literature: does our +X% on listing match Hartmann et al. / Ren & Heinrich's daily numbers when aggregated up? *This is a chance to triangulate.*
- **Limitations**: single-exchange, English-only, no order-book microstructure, sample size for rare categories.
- **Ethical considerations**: retail-trading-bot proliferation, latency-advantage vs. retail human, market-impact at scale (likely negligible at thesis scale but worth a paragraph).

### Chapter 7 — Conclusion and Future Work (2 pages)

- Restate findings in plain language.
- Three concrete next steps:
  1. Multi-exchange (add Coinbase, OKX; "stamp-of-approval" hypothesis).
  2. Multilingual announcements (the localized versions sometimes precede the English one by minutes).
  3. Replace linear sentiment-combiner with a small task-specific fine-tuned model now that we have a labeled dataset.

### References (2 pages, ~35–50 entries)

Use the seed list in `01-literature-review.md` §References. Add citations as new sources appear during writing.

### Appendices

- **A. Full confusion matrix and per-class metrics** of the category classifier.
- **B. Full category × horizon × sentiment-bucket lookup table** (this is too big for the main body).
- **C. Reproducibility checklist**: git tag, data hash, environment file, exact CLI command to reproduce the OOS run.

---

## Writing-Phase Tips

- **Write the abstract last**, but draft the contribution paragraph (Ch. 1.4) on Day 1 — it disciplines the rest.
- **One figure per page** average is a good visual-density target.
- **Every claim that isn't yours gets a citation.** Treat the lit review as your reference reservoir.
- **Defend honest negative results.** A thesis that says "our bot's OOS Sharpe was 0.4, baseline was 0.6, here's why" with rigorous methodology will be defended more easily than one with a magical 3.0 Sharpe and a leakage bug.
