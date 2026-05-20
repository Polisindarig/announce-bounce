l# Binance Announcement-Driven Algorithmic Trading Bot

**Senior Thesis Project** — An event-driven cryptocurrency trading bot that classifies Binance announcements by category and sentiment, then executes calibrated trades with category-specific position sizing and dynamic take-profit / stop-loss levels.

---

## Research Question

> Can a systematic, category-aware sentiment-driven strategy on Binance's own announcements generate statistically and economically significant returns at retail-realistic intraday horizons (1 m – 1 h), after transaction costs, out-of-sample?

## Core Hypothesis

Binance announcements are an *information event* in a partially-inefficient market (Urquhart, 2016). Different announcement categories (listing, delisting, futures launch, partnership, regulatory, security incident, staking, fork) produce **systematically different price responses** at **different horizons**. A bot that (a) correctly classifies category, (b) measures within-category sentiment, and (c) sizes positions according to historical category-conditional abnormal returns should outperform a naive buy-the-listing baseline.

## Data Split (2.5 years)

| Window | Use | Duration |
|---|---|---|
| **In-sample (training/analysis)** | Build category taxonomy, label sentiment, fit category × horizon impact distributions, calibrate TP/SL | **First 24 months** |
| **Out-of-sample (live-style backtest)** | Walk-forward execution of the frozen strategy. No re-fitting. | **Last 6 months** |

## Repository Layout

```
binance-sentiment-bot/
├── README.md                       <- you are here
├── docs/
│   ├── 01-literature-review.md     <- ~2,500-word academic lit review with citations
│   ├── 02-methodology.md           <- chosen approach + justification
│   ├── 03-project-plan.md          <- phased plan, milestones, risks
│   └── 04-thesis-outline.md        <- 40-page paper structure
├── data/
│   ├── raw/                        <- scraped announcements (HTML/JSON), raw OHLCV
│   ├── processed/                  <- cleaned + joined announcement-price tables
│   └── labeled/                    <- human-labeled subset for sentiment validation
├── src/
│   ├── scraper/                    <- Binance announcement scraper + price fetcher
│   ├── sentiment/                  <- category classifier + sentiment scorer
│   ├── strategy/                   <- decision engine, position sizing, TP/SL
│   ├── backtest/                   <- event-driven backtester with cost modeling
│   └── utils/                      <- shared helpers
├── notebooks/                      <- exploratory analysis, event studies, plots
├── backtest/results/               <- run outputs, equity curves, metrics
└── tests/
```

## Tech Stack (recommended)

- **Python 3.11+**
- **Data**: `pandas`, `numpy`, `polars` (large OHLCV joins)
- **Scraping**: `httpx`, `playwright` (Binance announcements page is JS-rendered), `tenacity`
- **NLP / sentiment**: `transformers` (FinBERT + CryptoBERT), `spaCy`, optional OpenAI/Anthropic for LLM zero-shot
- **Statistics / event study**: `statsmodels`, `scipy`
- **Backtest**: custom event-driven engine (lightweight; `vectorbt` / `backtrader` optional)
- **Plotting / reports**: `matplotlib`, `plotly`, `seaborn`
- **Reproducibility**: `pydantic` configs, `dvc` or simple file-versioning, `pytest`

## How to Read These Docs (Recommended Order)

1. **`docs/01-literature-review.md`** — the academic grounding. Read first; everything else flows from here.
2. **`docs/02-methodology.md`** — the *what* and *why* of our chosen approach, including the differentiation angle vs. existing literature.
3. **`docs/03-project-plan.md`** — phased timeline with deliverables, risks, and stop-criteria.
4. **`docs/04-thesis-outline.md`** — chapter-by-chapter outline mapped to the ~40-page target.

## Differentiation in One Paragraph

Existing literature on exchange announcement effects (Hartmann et al., 2019; Ren & Heinrich, 2023) measures *daily* abnormal returns on *listings only*, treating the announcement as a homogeneous event. Existing crypto sentiment work (Mai et al., 2018; Kraaijeveld & De Smedt, 2020) uses *noisy retail signals* (Twitter, Reddit) to predict *daily* prices. **No published study, to our knowledge, combines (i) the official low-noise Binance announcement feed, (ii) a multi-category taxonomy beyond listings, (iii) intraday horizons matching retail bot reality, (iv) category-conditional position sizing, and (v) a strict 6-month out-of-sample walk-forward.** That intersection is our contribution.

---

*Author: [your name] · Advisor: [advisor] · Department: [department] · Year: 2026*
