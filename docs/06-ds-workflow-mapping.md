# 06 — Data Science Workflow Eşleştirmesi

> **Referans:** Week 2 — Machine Learning in Finance (Fintech AI dersi, Imperial College / ders notları).
> Bu doküman, derste anlatılan **7-adımlı standart DS workflow**'unu projemize birebir eşler.
> Tez Bölüm 3 (Metodoloji) bu yapıya göre yazılacak.

---

## 0. Workflow Eşleştirme Tablosu

| # | DS Adımı (ders) | Projedeki karşılığı | Durum | Ana çıktı |
|---|---|---|---|---|
| 1 | **Problem Definition** | Araştırma sorusu + hipotez | ✅ tam | `docs/02-methodology.md`, Walkthrough §0 |
| 2 | **Data Collection** | Binance announcement scraping + MEXC klines | ✅ tam | 2913 anons, 39 coin kline parquet |
| 3 | **Data Pre-processing** | Symbol extraction, dedup, manuel doğrulama | ✅ tam | `manual_verified_mexc_listing_pumps.csv` |
| 4 | **Exploratory Analysis** | Catalog returns, sentiment dağılımı, pump distribütion | ✅ tam | `docs/*_short_window_analysis.md` × 4 |
| 5 | **Data Modelling** | Rule-based strategy + ML filter (planlanmış) | ⚠️ Rule-based hazır, ML PoC eksik | `decision_engine.py` + `train_listing_filter.py` (yapılacak) |
| 6 | **Model Evaluation** | Backtest (n=42), latency sensitivity, confusion matrix | ⚠️ Backtest var, classification metrics ML ile gelecek | `docs/listing_backtest_final.md` |
| 7 | **Result Interpretation** | Latency cliff, MEXC pre-listing importance | ✅ tam | Walkthrough §11 + tez Bölüm 5 |

---

## 1. Problem Definition

**Ders tanımı:** "Defining the objective, questions and goals of the data science project to address a specific problem or challenge."

**Bizim projemizde:**

- **Hedef:** Binance anonsları + MEXC fiyat hareketi → kısa vadeli ekonomik alfa kaynağı mı?
- **Araştırma sorusu:** "Binance'in 'Will List X' anonsları, X coininin MEXC'te zaten işlem gördüğü durumlarda kısa vadeli (1-60dk) fiyat şokları yaratır mı, ve bu şoklar realistik latency varsayımı altında trade edilebilir mi?"
- **Pratik hedef:** TP+15% / SL-12% / 8-bar time-stop kuralıyla **trade başı pozitif net beklenen getiri** ölçmek.
- **Sınırlandırma:** Yalnızca long pozisyon, sadece USDT pair, MEXC execution.

**Kaynak dosya:** `docs/02-methodology.md`

---

## 2. Data Collection

**Ders tanımı:** "Gathering relevant data from various data sources, ensuring its quality and suitability for analysis."

**Ders ayrımı:**
- **Secondary Data Collection** (existing data) — bizim durum
- **Primary Data Collection** (surveys, experiments) — bizim durum değil

### 2.1 Anonslar — 4 Kategori Bazında Tam Envanter

Bizim 4-kategorili stratejimiz için **tüm anons tiplerinden** veri toplandı.

**Ana anons dosyası (30 ay tam):**

| Dosya | Anons sayısı | Kapsam |
|---|---:|---|
| `data/raw/announcements.jsonl` | **2616** | 30-ay tam (2023-11 → 2026-05) |
| `data/raw/announcements_from_2025-06-01.jsonl` | **2913** | Son 11 ay (in-sample + OOS dönemi) |

**Katalog bazında dağılım (2913 anons üzerinden):**

| Katalog | n | Strateji karşılığı |
|---|---:|---|
| `new_cryptocurrency_listing` | **409** | listing_spot (BUY adayları) + sub-events |
| `delisting` | **254** | delisting (FORCE_SELL trigger) |
| `wallet_maintenance_updates` | **308** | maintenance (SKIP) |
| `latest_activities` | 1064 | other (SKIP) — yarışmalar, kampanyalar |
| `latest_binance_news` | 862 | other (SKIP) — postpone, fiyat duyuruları |
| `crypto_airdrop` | 10 | airdrop (NO_TRADE) |
| `api_updates` | 6 | other (SKIP) |

**Listing katalogundan çıkarılmış event detayı (sub-classification yapıldı):**

| Sub-event | n (yaklaşık) | Strateji kararı |
|---|---:|---|
| "Binance Will List X" (gerçek spot listing) | ~70 | **listing_spot → BUY** |
| "Will Add X on Earn / Buy / Convert / Margin" | ~120 | listing_extension → NO_TRADE |
| "Futures Will Launch USDⓈ-Margined ..." | ~100 | futures_launch → NO_TRADE |
| "Introducing HODLer Airdrops" | ~40 | airdrop_launchpool → NO_TRADE |
| "Launchpool / Launchpad" | ~30 | airdrop_launchpool → NO_TRADE |
| "Postponed / Trading Open Time / Misc" | ~50 | other → SKIP |

### 2.2 Fiyat Verisi — Her Kategori için Ayrı Çekim

Her trade kararı kategorisinde **fiyat tepkisini ölçmek için** kline verisi topladık. Bu sadece listing değil:

#### A) listing_spot için (BUY adayları)

| Klasör | İçerik | Volume |
|---|---|---:|
| `data/raw/mexc_klines_5m_from_2025-06/` | MEXC 5m bar, son 11 ay listing coinleri | **39 coin** |
| `data/raw/mexc_klines_5m_desktop/` | MEXC 5m bar, ek doğrulama | 23 coin |
| Codex `mexc_listing_klines_30m_no_wallet/` | 30 aylık MEXC (multi-interval: 1m/5m/60m) | **64 coin** |
| `data/processed/manual_verified_mexc_listing_pumps.csv` | TV ekran-okuma OHLC | **47 coin** |

#### B) delisting için (FORCE_SELL kuralının kalibrasyonu)

| Klasör | İçerik | Volume |
|---|---|---:|
| Codex `binance_spot_asset_delisting_klines/` | Spot delist coinlerin 1m bar (anonstan sonra dump) | **90 coin** |
| `data/processed/delisting_event_coins_complete.csv` | Gövdeden çıkarılan delist coin envanteri | 253 anons → 93 unique asset |
| `data/processed/delisting_short_window_metrics.csv` | 1m/5m/15m/30m/45m/1h düşüş metrikleri | 90 event |

#### C) futures_launch için (NO_TRADE kararının kanıtı)

| Klasör | İçerik | Volume |
|---|---|---:|
| Codex `binance_event_klines_30m_no_wallet/futures_launch/` | Spot fiyat tepkisi 1m bar | n alt-klasör |
| `data/processed/futures_launch_short_window_metrics.csv` | Path metrikleri (MFE/MAE) | **55 event** |

#### D) staking_earn için (NO_TRADE kararının kanıtı)

| Klasör | İçerik | Volume |
|---|---|---:|
| Codex `binance_event_klines_30m_no_wallet/staking_earn/` | Spot 1m bar | ~80 alt-klasör |
| `data/processed/staking_earn_short_window_metrics.csv` | Path metrikleri | **65 event** |

#### E) airdrop / launchpool için (NO_TRADE kararının kanıtı)

| Klasör | İçerik | Volume |
|---|---|---:|
| Codex `binance_event_klines_30m_no_wallet/launchpool_launchpad/` | Spot 1m bar | alt-klasörler |
| `data/processed/airdrop_fork_short_window_metrics.csv` | Path metrikleri | **48 event** |
| `data/processed/airdrop_launchpool_short_window_metrics.csv` | Birleşik (airdrop + launchpool) | **56 event** |

#### F) Baseline / market state

| Klasör | İçerik | Volume |
|---|---|---:|
| `data/raw/klines/` | BTC + Top-50 + event coinlerin 1m bar | **521 dosya** |
| Bu BTC-adjusted ve index-adjusted return hesaplaması için gerekli | |

**Toplam kline klasörü:** **39 + 23 + 64 + 90 + 261 + 521 ≈ 998 ayrı coin/dosya seviyesinde fiyat verisi.**

### 2.3 İkincil (manuel) veri kaynakları

| Kaynak | Method | Volume | Konum |
|---|---|---|---|
| TradingView ekran okuma | Görsel OHLC kayıt | 47 coin × pre/news candle | `manual_verified_mexc_listing_pumps.csv` |
| Binance article body extraction | API + manual parse | 253 delisting gövde | `delisting_announcement_coins_from_bodies.csv` |
| Literature | Academic citation | Ante 2019, Empirica 2024, ScienceDirect, Imperial College | `docs/01-literature-review.md` |
| Industry sources | Web search | Latency benchmarks (sniper bot, MEXC docs) | Walkthrough §5.2 |

### 2.4 Veri kalitesi kontrolü

- Rate-limit'e takılma → conservative 1 req/2s polling
- Sembol eşleşmemesi → manuel override (`config/mexc_symbol_overrides.csv`)
- Eksik dakikalık veri → daha geniş timeframe fallback (1m → 5m → 60m)
- Delisting gövdesinde coin yoksa → article detail endpoint ile gövde tekrar çekildi (181/253 gövde)
- Coin name extraction → regex + manuel override (alias durumları için)

### 2.5 Özet: Her Strateji Kararı için Veri Var

| Bot kararı | Kanıtlayan veri | n event |
|---|---|---:|
| **BUY** (listing_spot + MEXC pre-listed) | MEXC kline + manuel TV doğrulama | 47 |
| **FORCE_SELL** (delisting) | Spot delist kline + dump path | 90 |
| **NO_TRADE** (futures_launch) | Binance event kline + path metrics | 55 |
| **NO_TRADE** (staking_earn) | Binance event kline + path metrics | 65 |
| **NO_TRADE** (airdrop/launchpool) | Binance event kline + path metrics | 56 |
| **SKIP** (maintenance / other) | Anons metadata, fiyat verisi gerekmedi | 308 + 1064 + 862 |

**Toplam event-bazlı analiz örneklemi: 313 olay** (her biri ayrı bir trade kararı çıkarımı için fiyat verisiyle).

---

## 3. Data Pre-Processing

**Ders 4-katmanı:** Cleansing → Reduction → Scaling → Transformation

### 3.1 Data Cleansing (eksik veri + outlier'lar)

**Eksik veri yönetimi:**
- "Missing symbol" anonslar → tezden hariç (3 coin: AIGENSYN, KGST, U)
- MEXC'de mum bulunamayan eski tarihler → ayrı manifest, fallback fail-soft
- Sembol uyuşmazlığı (XAUT → GOLD(XAUT)USDT, vb.) → manuel override

**Outlier tespiti (IQR yöntemi — ders sayfası 11):**
- Manuel doğrulama setinde pump dağılımı kontrol edildi
- Uç değerler (ACT +1018%, BANK +101%) raporlandı **ama dışlanmadı** — gerçek olaylar
- TP+15 / SL-12 zaten outlier'ları clamp ediyor → strateji düzeyinde outlier kontrolü

**Kod:** `scripts/build_announcement_events.py`, `scripts/clean_listing_universe.py`

### 3.2 Data Reduction (boyut azaltma)

**Feature reduction (column-wise):**
- 24 kolonlu `listing_events_with_sentiment.parquet` → strateji için 6-8 anlamlı feature
- Çok kategorili katalog → 4 makro kategori (listing / delisting / no-trade / skip)

**Case reduction (row-wise):**
- 183 listing event → manuel doğrulanmış 47 → traded 42 (3 coin eksik sembol)
- Symbol deduplication (her coin tek event, en erken anons)
- Same-day filter (aynı coin 24h içinde ikinci anons → dahil değil)

### 3.3 Data Scaling

Bu projede **scaling kritik değil** çünkü strateji rule-based, distance-based algoritma yok. Ama ML genişletmesinde:
- **Z-score normalization** sayısal özelliklere (sentiment_score, hour_utc, btc_ret_24h_before)
- **Min-max scaling** [0,1]'e bağlı özelliklere
- Yapılacak: `scripts/train_listing_filter.py` içinde sklearn `StandardScaler`

### 3.4 Data Transformation

**One-hot encoding:**
- Categorical anons kategorisi → 4 binary feature
- "has_seed_tag" → binary indicator from title

**Binning:**
- `hour_utc` → 6-saatlik dilim (Asia / Europe / US trading hours)
- `n_tickers_in_title` → {1, 2, 3+}

**Kod (yapılacak):** `src/ml/features.py`

---

## 4. Exploratory Data Analysis

**Ders ayrımı:** Univariate non-graphical + Univariate graphical

### 4.1 Univariate non-graphical

**Central tendency:**

| Coin grubu | Mean pump | Median pump |
|---|---:|---:|
| Manuel doğrulanmış (n=42) realistic latency | +7.01% | +14.40% |
| Strong prelisted (n=10) raw | +21.59% | +14.50% |
| Last 3 months (n=2) realistic | +3.62% | +3.62% |

**Spread:**
- Range manuel set: [-12.60%, +14.40%] (TP/SL clamp sonrası)
- IQR fast scenario: ~[0%, +14.4%]
- Standard deviation: tezde bootstrap CI ile rapor edilecek

### 4.2 Univariate graphical

- **Histogram:** trade return distribution → dashboard `Performance` sayfası (mock şu an, ML PoC sonrası gerçek)
- **Bar chart:** kategori bazında medyan getiri → dashboard'da vardı, academic version
- **Time series:** equity curve over 90 days → dashboard `Overview`

### 4.3 Bivariate / Multivariate

- **Sentiment vs return:** scatter plot (yapılacak EDA notebook'ta)
- **Latency vs return:** key thesis figure (Walkthrough §5)
- **Day-of-week vs return:** muhtemel pattern (yapılacak)

---

## 5. Data Modelling

**Ders ayrımı:**
- Supervised (Regression, Classification)
- Unsupervised (Clustering)
- Reinforcement Learning

### 5.1 Mevcut: Rule-based Decision Engine

**Tip:** Heuristic + threshold-based (ML değil, ama ML için baseline).

```
IF announcement.category == "listing_spot" AND asset in MEXC_pre_listed:
    BUY (size = 10% equity, TP +15%, SL -12%, time-stop 8 bars)
ELIF announcement.category == "delisting" AND asset in open_positions:
    FORCE_SELL (100% market)
ELSE:
    NO_TRADE / SKIP
```

**Kod:** `src/web/data_loader.py::_classify_announcement()`, `_simulate_trade_on_mexc()`

### 5.2 Eklenmesi planlanan: ML Filter (Supervised Classification)

**Tip:** Supervised Classification (binary)
- **Input:** announcement features (sentiment, time-of-day, title features, market state, asset metadata)
- **Target:** `outcome == 'tp'` (1 if TP hit, 0 if SL/time-stop)
- **Veri:** n=47 manuel set + 183 tüm listing events

**Aday algoritmalar (ders sayfası 31-33):**

| Algoritma | Avantaj | Risk |
|---|---|---|
| **Logistic Regression** | Hızlı, yorumlanabilir, küçük n için ideal | Linear ilişkiler |
| **Decision Tree** | Yorumlanabilir, feature importance | Overfitting |
| **Random Forest** | Robust, outlier-resistant, ensemble | Daha az yorumlanabilir |
| **Gradient Boosting (XGBoost/LightGBM)** | High accuracy small data | Çok parametrik, overfit riski |

**Önerilen yaklaşım:** Logistic Regression baseline + Random Forest karşılaştırma.

**Düzenleme (Regularization — ders sayfası 30):**
- L2 regularization (Ridge) logistic regression için
- Max depth + min samples leaf decision tree için
- Random Forest n_estimators capped, max_features='sqrt'

**Cross-Validation (ders sayfası 30):**
- **Time-series split** (KFold değil, gelecek leak engeli için)
- 5 fold üzerinden mean ± std raporla

**Kod (yapılacak):** `scripts/train_listing_filter.py`

### 5.3 Bias-Variance Tradeoff (ders sayfası 30)

- **Underfitting riski:** Rule-based modelin n=42'de %95 win rate çıktı → sample-specific olabilir, generalize etmeyebilir
- **Overfitting riski:** ML modeli n=47'de overtune edilirse → time-series CV ile kontrol
- **Çözüm:** Out-of-sample test seti (son 3 ay) + bootstrap CI

### 5.4 Unsupervised Learning (opsiyonel ek)

**K-Means clustering** kullanım fikri:
- Listing event'leri sentiment + market state özelliklerine göre 3 cluster'a ayır
- Her cluster için ayrı TP/SL parametresi eğit
- "Different listing types have different optimal exit policies"

**Bu opsiyonel** — tezin asıl mesajı için kritik değil, ama ekstra deep dive olarak yer alabilir.

---

## 6. Model Evaluation

**Ders metriği seti (sayfa 35-36):** Confusion Matrix → Precision → Recall → F1 Score

### 6.1 Rule-based strateji için (mevcut)

**Backtest metrikleri:**
- Net per-trade return (mean, median, std)
- Win rate
- Outcome distribution (TP / SL / time-stop %)
- Annualized return
- Latency sensitivity (3 senaryo)

**Backtesting metodolojisi:**
- 8-bar time-stop ile bar-by-bar simulation
- 0.60% round-trip cost düşülmüş
- Pessimistic intra-bar rule: TP + SL aynı bar → SL kazanır

### 6.2 ML filter için (yapılacak)

**Sınıflandırma metrikleri (ders sayfası 36):**

```
              Predicted: TP   Predicted: NO-TP
Actual: TP        TP             FN
Actual: NO-TP     FP             TN

Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 × (P × R) / (P + R)
ROC-AUC   = area under TPR-FPR curve
```

**Yorumlama:**
- **Precision yüksek olsun istiyoruz:** "Bot BUY dediğinde gerçekten TP gelmeli" (false BUY → para kaybı)
- **Recall daha az kritik:** "Bazı TP'leri kaçırmak" SL yemekten daha az ağır
- **F1 dengeli ölçüm**

### 6.3 Strateji-düzey değerlendirme

ML filter'ı uygulayınca:
- Trade sayısı azalır mı?
- Win rate yükselir mi? (%71 → %80+ hedef)
- Net per-trade return artar mı? (+%6.41 → +%8-10 hedef)
- Sharpe iyileşir mi?

**Karşılaştırma (yapılacak):**
```
Strategy          Trades  WinRate  NetMean  AnnRet
Baseline rule        42   71.4%   +6.41%   +82%
Baseline + ML filter  ?     ?        ?       ?
```

---

## 7. Result Interpretation

**Ders tanımı:** "Interpreting the results and findings to derive meaningful insights and make informed decisions."

### 7.1 Ana bulgular

1. **Latency-driven alpha:** Profitability detection latency ile monotonik ters orantılı. 15-saniye eşik karlılık-zarar sınırı.
2. **MEXC pre-listing filter kritik:** Filtresiz uygulanırsa zarar (-%5.16 son 3 ay), filtreyle pozitif (+%6.41 manuel set).
3. **Diğer kategoriler descriptive:** Futures launch, staking, airdrop tek başına trade sinyali değil.
4. **Delisting forced-exit:** Median 1h düşüş -%13.16, beklemek matematiksel olarak kötü.

### 7.2 Defansta savunulabilir cümleler

(Walkthrough §11'e bkz, oradaki 3 cümle bu adıma denk geliyor.)

### 7.3 Limitasyonlar

(Walkthrough §9'a bkz.)

---

## 8. Tez Bölüm Planı (DS Workflow'a Göre)

```
Tez Bölüm 3 — Veri ve Metodoloji
  3.1 Problem Tanımı           → DS Step 1
  3.2 Veri Toplama              → DS Step 2
       3.2.1 Birincil (scrape)
       3.2.2 İkincil (manual)
  3.3 Veri Ön İşleme            → DS Step 3
       3.3.1 Temizleme
       3.3.2 Boyut indirgeme
       3.3.3 Scaling
       3.3.4 Transformation
  3.4 Keşifsel Veri Analizi    → DS Step 4
  3.5 Strateji Modelleme       → DS Step 5
       3.5.1 Rule-based decision engine
       3.5.2 ML filter (opsiyonel)
  3.6 Değerlendirme Metrikleri → DS Step 6

Tez Bölüm 4 — Sonuçlar
  4.1 Backtest performans
  4.2 Latency sensitivity
  4.3 Out-of-sample (son 3 ay)
  4.4 ML filter etkisi (opsiyonel)
  4.5 Bulgular ve yorumlama   → DS Step 7
```

Bu yapı **derste anlatılan workflow'la 1:1** uyumlu. Tezde Bölüm 3'ün başında 7-adımlı workflow şemasını ders sunumundan kopyala (referans ile), sonra her alt-bölümü buna eşle.

---

## 9. Şu Anda Yapılması Gerekenler

| Öncelik | İş | Tahmini süre |
|---|---|---|
| 🔴 Yüksek | ML filter PoC script (`train_listing_filter.py`) | 1.5 saat |
| 🔴 Yüksek | Confusion matrix + precision/recall/F1 raporlama | 30 dk |
| 🟡 Orta | EDA notebook (`notebooks/eda_listing_events.ipynb`) | 1 saat |
| 🟡 Orta | Bootstrap CI ekle (n=42 için %95 güven aralığı) | 45 dk |
| 🟢 Düşük | K-Means clustering deneme (3 cluster) | 1 saat |
| 🟢 Düşük | Dashboard'a "ML model performance" sayfası | 1 saat |

ML PoC'yi yapınca tez Bölüm 3.5.2 ve Bölüm 4.4 doldurulabilir hale gelir. Şu anda eksik tek metodolojik adım bu.

---

*Bu doküman, derste anlatılan standart DS workflow'unun projeye uygulanma haritasıdır. Tez metodoloji bölümünde aynı sıralamayla yazılacaktır.*
