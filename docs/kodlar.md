# Kodlar — Dosya Haritası

Bu dosya, binance-sentiment-bot projesindeki **regex**, **coin seçimi**, **backtest**, **veri**, **dashboard** ve **çıktı** dosyalarının tek yerden referansıdır.

Repo kökü: `/Users/hamzabalik/binance-sentiment-bot`

---

## 1. Regex ve sınıflandırma

| Ne yapıyor | Dosya |
|------------|--------|
| Kategori sınıflandırıcı (`classify`, `re.search`) | `src/sentiment/category_classifier.py` |
| Başlıktan ticker çıkarma (`TITLE_PATTERNS`) | `src/scraper/symbol_extractor.py` |
| Olay tablosu; her satırda `classify()` | `src/processing/build_events.py` |
| Trade kararı: LONG/SKIP, TP/SL, stablecoin | `src/strategy/decision_engine.py` |
| FinBERT skorlama (offline; üretim yolu değil) | `src/sentiment/sentiment_scorer.py` |
| Hibrit skor (regex + lexical) | `src/sentiment/hybrid_scorer.py` |
| SVM / Ridge benchmark (Appendix B) | `src/analysis/train_baseline.py` |
| Kirlenme bayrakları | `src/processing/contamination.py` |
| Listing zamanı `t_0` | `src/scraper/listing_time.py` |

**Üretim akışı:** duyuru → `symbol_extractor` → `build_events` + `category_classifier` → `decision_engine`

---

## 2. Coin seçimi ve evren

| Ne yapıyor | Dosya |
|------------|--------|
| İlk listing filtresi, stablecoin, dedup, reject phrases | `src/backtest/engine.py` → `filter_real_tier1_events()` |
| MEXC’de duyurudan önce işlem (tradability) | `src/backtest/engine.py` → `run_backtest()` (~satır 311+) |
| Kategori → venue, TP, SL, time stop | `src/strategy/decision_engine.py` → `CALIBRATION_TABLE`, `decide()` |
| Dashboard BUY/SKIP ve “target universe” | `src/web/data_loader.py` → `recent_announcements()` |
| Tez OOS senkron (four-filter notu; eski 17-trade) | `scripts/sync_oos_to_thesis.py` |

**Çıktı / evren verisi (CSV/parquet):**

| Ne | Dosya |
|----|--------|
| Tüm duyuru × coin olay tablosu | `data/processed/events.parquet` |
| 165 coin evreni (four-filter sonucu) | `data/processed/universe_combined.csv` |
| Manuel doğrulanmış MEXC listing listesi | `data/processed/manual_verified_mexc_listing_pumps.csv` |

> `universe_combined.csv` üreten tek bir `build_universe.py` yok; seçim `engine.py` + `decision_engine.py` + manuel/OHLCV adımlarıyla dağıtık.

**Four-filter ↔ kod eşlemesi:**

| Filtre (tez) | Kod karşılığı |
|--------------|----------------|
| 1 — İlk bullish duyuru | `filter_real_tier1_events`: `drop_duplicates(symbol, keep="first")` |
| 2 — Henüz Binance’te değil | `run_backtest` tradability: duyurudan önce MEXC bar yoksa skip |
| 3 — MEXC’de USDT ile işlem | Kline varlığı + tradability; `mexc_klines.py` indirme |
| 4 — Stablecoin değil | `filter_real_tier1_events` → `EXCLUDED_SYMBOLS`; `decision_engine` → `STABLECOINS` |

---

## 3. Backtest

| Ne yapıyor | Dosya |
|------------|--------|
| Ana motor: `run_backtest`, `BacktestConfig`, `main()` | `src/backtest/engine.py` |
| OOS koşusu (frozen parametreler) | `src/backtest/oos_run.py` |
| Gecikme / fee duyarlılığı | `src/backtest/robustness_run.py` |
| Listing-catalog OOS raporu | `src/analysis/listing_backtest_report.py` |

**Config:**

| Ne | Dosya |
|----|--------|
| IS/OOS tarih penceresi | `config/data_window.yaml` |
| OOS parametreleri | `config/oos.yaml` |
| Baseline backtest | `config/backtest_baseline.yaml` |
| Listing backtest | `config/backtest_listing.yaml`, `config/backtest_listing_balanced.yaml` |
| MEXC | `config/mexc.yaml`, `config/mexc_5m_from_june2025.yaml` |
| Gate.io | `config/gateio.yaml` |
| Listing eval penceresi | `config/listing_eval_window.yaml` |

**Çalıştırma (repo kökünden):**

```bash
python -m src.processing.build_events
python -m src.backtest.engine
python -m src.backtest.oos_run
```

---

## 4. Backtest ve analiz çıktıları

`data/processed/` altında:

| Ne | Dosya |
|----|--------|
| Olay tablosu | `events.parquet` |
| IS M0 sonuç | `backtest_m0_result.json` |
| IS M1 sonuç | `backtest_m1_result.json` |
| OOS sonuç (dashboard ana kaynak) | `phase6_oos_result.json` |
| 165 trade tablosu (101 IS + 64 OOS, tez v4) | `strategy_h1_sl8_tp25.csv` |
| FinBERT 3340 başlık | `finbert_full_3340.json` |
| Train baseline raporu | `train_baseline_report.json` |
| Reproducibility manifest | `reproducibility_manifest.json` |

Manifest üretimi: `src/utils/reproducibility_manifest.py`

---

## 5. Veri toplama ve kline

| Ne | Dosya |
|----|--------|
| Binance duyuruları | `src/scraper/announcements.py` |
| Spyder scrape script | `scripts/scrape_announcements_spyder.py` |
| MEXC OHLCV | `src/scraper/mexc_klines.py`, `src/scraper/mexc_web_klines.py` |
| Gate.io klines | `src/scraper/gateio_klines.py` |
| Genel klines | `src/scraper/klines.py` |
| Toplu kline | `src/scraper/klines_bulk.py` |
| Event penceresi kline | `src/scraper/klines_event.py` |
| REST gap fill | `src/scraper/klines_rest_gapfill.py` |
| Phase 1 koşucu | `src/scraper/run_phase1.py` |
| Hızlı scrape | `src/scraper/fast_scrape.py` |
| MEXC CSV klasör ingest | `scripts/ingest_mexc_csv_folder.py` |
| BTC / index ayarlı getiri | `src/processing/crypto_index.py` |
| Pipeline downstream | `src/pipeline/downstream.py` |

Ham veri genelde: `data/raw/`, işlenmiş: `data/processed/`

---

## 6. Event study ve listing analizi (backtest dışı)

| Ne | Dosya |
|----|--------|
| Listing event study | `src/analysis/listing_event_study.py` |
| Tier-1 event study | `src/analysis/tier1_event_study.py` |
| Event study istatistik | `src/analysis/event_study_stats.py` |
| Event tablosu | `src/analysis/event_table.py` |
| Events özet | `src/analysis/events_summary.py` |
| Venue karşılaştırma (MEXC vs Gate) | `src/analysis/compare_listing_venues.py` |
| Listing sentiment zenginleştirme | `src/analysis/enrich_listing_sentiment.py` |
| Phase 4 event study | `src/analysis/phase4_event_study.py` |

---

## 7. Web / dashboard

| Ne | Dosya |
|----|--------|
| Veri yükleme, duyuru feed, bot state | `src/web/data_loader.py` |
| Uygulama girişi | `src/web/app.py` |
| HTML / JS / CSS | `src/web/static/index.html`, `app.js`, `styles.css`, `dashboard.css`, `landing.css`, `enhancements.js`, `enhancements.css`, `transition.css` |

---

## 8. Testler

| Ne | Dosya |
|----|--------|
| Symbol extractor | `tests/test_symbol_extractor.py` |
| Build events `t_0` | `tests/test_build_events_t0.py` |
| Listing backtest | `tests/test_listing_backtest.py` |
| Listing event study | `tests/test_listing_event_study.py` |
| Train baseline | `tests/test_train_baseline.py` |
| MVP stack | `tests/test_mvp_stack.py` |
| Smoke | `tests/test_smoke.py` |

---

## 9. Dokümantasyon ve tez

| Ne | Dosya |
|----|--------|
| Metodoloji | `docs/02-methodology.md` |
| Proje planı, IS/OOS | `docs/03-project-plan.md` |
| Walkthrough | `docs/05-project-walkthrough.md` |
| DS workflow | `docs/06-ds-workflow-mapping.md` |
| Tez–kod uyumu | `thesis/CHANGE_SPEC.md` |
| Tez Word builder (EN v4) | `thesis/build_thesis_v4_EN.py` |
| Diğer tez builder’lar | `thesis/build_thesis.py`, `build_thesis_v2.py`, `build_thesis_v3*.py`, `build_thesis_v4_TR.py` |
| Tez çıktıları | `thesis/thesis_v4_EN_1115.docx`, `thesis/thesis_v4_EN_FINAL.docx` |

---

## 10. Hızlı başlangıç (sıra)

1. Regex kategori → `src/sentiment/category_classifier.py`
2. Ticker regex → `src/scraper/symbol_extractor.py`
3. Olay tablosu → `src/processing/build_events.py` → `data/processed/events.parquet`
4. Coin filtresi → `src/backtest/engine.py` → `filter_real_tier1_events`
5. Trade kuralı → `src/strategy/decision_engine.py`
6. Backtest → `src/backtest/engine.py` (IS), `src/backtest/oos_run.py` (OOS)
7. Sonuçlar → `data/processed/phase6_oos_result.json`, `strategy_h1_sl8_tp25.csv`
8. Dashboard → `src/web/data_loader.py`

---

## 11. Üretim vs offline (özet)

| Bileşen | Üretim | Offline / tez |
|---------|--------|----------------|
| Kategori | `category_classifier.py` (regex) | FinBERT: `finbert_full_3340.json` |
| Trade sinyali | `decision_engine.py` (M0) | SVM: `train_baseline.py` |
| Backtest | `engine.py`, `oos_run.py` | `listing_backtest_report.py` |
| Evren | `filter_real_tier1_events` + tradability | `universe_combined.csv` |

---

*Son güncelleme: proje dosya yapısına göre; yeni script eklenirse bu listeyi güncelle.*
