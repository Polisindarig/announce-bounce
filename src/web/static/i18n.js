/* ============================================================
   i18n.js — EN / TR language toggle
   - Rich landing blocks (markup inside) are swapped via SELECTOR_MAP;
     the original English innerHTML is cached on the element.
   - Simple strings everywhere else are swapped by exact text-node
     match via EN2TR / TR2EN dictionaries.
   - Counter value elements (.lv2-stat-value / .lv2-num-value) are
     never touched, so the decryption counters keep working.
   Preference persists in localStorage("ab_lang"); default "en".
   ============================================================ */
(function () {
  "use strict";

  /* ---------- rich blocks (landing) ---------- */
  const SELECTOR_MAP = [
    [".lv2-hero-title",
      'Söylentiyi değil,<br/>\n<em>duyuruyu</em><br/>\nişleyen bot.'],
    [".lv2-hero-lede",
      "Binance'in resmî duyuru akışını gerçek zamanlı okuyan, olay güdümlü bir spot bot. Bir coin Binance ekosistemine ilk kez girdiğinde bot onu hâlihazırda işlem gördüğü MEXC'te satın alır. Binance bir delisting ya da monitoring tag duyurduğunda satar."],
    ["#strategy .lv2-section-title",
      'Dört kural.<br/>\n<em>İki yön.</em><br/>\nSadece spot.'],
    ["#numbers .lv2-section-title",
      'Örneklem dışı,<br/>\n<em>dondurulmuş parametreler,</em><br/>\ngerçek fiyatlar.'],
    ["#risk .lv2-section-title",
      'Kaldıraç yok.<br/>\nİnisiyatif yok.<br/>\n<em>Katı limitler.</em>'],
    [".lv2-closing-title",
      'Kanıtların tamamı<br/>\n<em>panelin</em> içinde.'],
    [".lv2-strategy-item:nth-of-type(1) .lv2-strategy-body",
      'Binance bir coin için ilk listeleme duyurusunu yayınladığında — spot, vadeli, Hodler airdrop, Launchpool veya Launchpad — bot coini hâlihazırda işlem gördüğü MEXC\'te satın alır. Kalibre edilmiş çıkış: <code>TP +25%</code> / <code>SL −8%</code> / <code>1s zaman stopu</code>.'],
    [".lv2-strategy-item:nth-of-type(2) .lv2-strategy-body",
      '<em>"Will Delist X"</em> duyurusu açık pozisyonlarda anında piyasa satışı tetikler. OOS ortalama düşüş 5. dakikada <code>−7.75%</code>, 8. saatte <code>−17.30%</code> <span style="color:var(--lv2-ink-faint)">(p &lt; 0.001)</span>. Bir sonraki barda satmak derin kuyruktan kaçınmayı sağlar.'],
    [".lv2-strategy-item:nth-of-type(3) .lv2-strategy-body",
      'Binance\'in belgelenmiş delisting öncülü. Kısa vadeli tepki dağınıktır — 5. dakikada <code>−1.27%</code> — ancak düşüş 24 saatte <code>−5.56%</code>\'ya birikir. OOS örnekleminde fiili delisting\'e medyan süre: <strong>42 gün.</strong>'],
    [".lv2-strategy-item:nth-of-type(4) .lv2-strategy-body",
      'Bakım pencereleri, regülasyon notları, ortaklık entegrasyonları, kampanyalar. Hiçbiri titiz örneklem-içi testlerden sonra işlem edilebilir bir avantaj üretmiyor. Bot bunları kaydeder ve geçer.'],
    [".lv2-risk-row:nth-of-type(1) .lv2-risk-detail",
      '$10,000 bakiyede işlem başına sabit <code>$1,000</code> — özsermayenin %10\'u, OOS avantajının ima ettiği tam-Kelly oranının kabaca sekizde biri. Tek sembol, tek işlem.'],
    [".lv2-risk-row:nth-of-type(2) .lv2-risk-detail",
      'Girişten <code>−8%</code> katı SL; 1.408 varyantlı örneklem-içi grid taramasıyla seçildi. Kalibrasyon OOS penceresi boyunca donduruldu.'],
    [".lv2-risk-row:nth-of-type(3) .lv2-risk-detail",
      '<code>1s</code> sonunda zorunlu kapanış. Listeleme momentumu hızla söner — Empirica (2024), listelenen tokenların ilk haftada %6.34 kaybettiğini gösteriyor.'],
    [".lv2-risk-row:nth-of-type(4) .lv2-risk-detail",
      'En fazla <code>3</code> açık pozisyon, sembol başına bir. Portföy sürüklenmesi yok, birikimli korelasyon riski yok.'],
    [".lv2-risk-row:nth-of-type(5) .lv2-risk-detail",
      'Her giriş <code>%1</code> kayma tahmini ve 10 bps gidiş-dönüş komisyonu öder. Raporlanan tüm getiriler bunların netidir.'],
    [".lv2-risk-row:nth-of-type(6) .lv2-risk-detail",
      'Vadeli yok, kaldıraç yok. Şu an paper modda; canlı dağıtım tezin kapsamı dışında.'],
  ];

  /* ---------- simple strings (text-node swap) ---------- */
  const EN2TR = {
    // landing nav + hero
    "Strategy": "Strateji",
    "Evidence": "Kanıtlar",
    "Dashboard": "Panel",
    "Marmara MIS · Thesis Research": "Marmara MIS · Tez Araştırması",
    "Open dashboard": "Paneli aç",
    "Read the method": "Yöntemi oku",
    "OOS cumulative return": "OOS kümülatif getiri",
    "Win rate · 64 trades": "Kazanma oranı · 64 işlem",
    "Profit factor": "Kâr faktörü",
    // section metas
    "§ 01 — Strategy": "§ 01 — Strateji",
    "§ 02 — Evidence": "§ 02 — Kanıtlar",
    // strategy cards
    "↗ Buy · MEXC": "↗ Al · MEXC",
    "↘ Sell · Binance": "↘ Sat · Binance",
    "— Skip": "— Atla",
    "First Binance ecosystem entry": "Binance ekosistemine ilk giriş",
    "Delisting announcement": "Delisting duyurusu",
    "Monitoring tag added": "Monitoring tag eklendi",
    "Everything else": "Geri kalan her şey",
    // numbers cells
    "Cumulative return": "Kümülatif getiri",
    "Win rate": "Kazanma oranı",
    "Maximum drawdown": "Maksimum düşüş",
    "Delisting drop · t+5m": "Delisting düşüşü · t+5dk",
    "Monitoring drop · t+24h": "Monitoring düşüşü · t+24s",
    "64 trades over 11 months on MEXC, after fees and slippage. $10,000 → $18,709.":
      "MEXC'te 11 ayda 64 işlem; komisyon ve kayma sonrası. $10,000 → $18,709.",
    "30 take-profit hits, 22 profitable time stops, 5 losing time stops, 7 stop-loss.":
      "30 take-profit, 22 kârlı zaman stopu, 5 zararlı zaman stopu, 7 stop-loss.",
    "Gross winners ÷ |gross losers|. Standard threshold: anything above 2 is considered strong.":
      "Brüt kazançlar ÷ |brüt kayıplar|. Standart eşik: 2 üzeri güçlü kabul edilir.",
    "Peak-to-trough on equity. Fixed $1,000 per trade on a $10,000 starting balance.":
      "Özsermayede tepe-dip. $10,000 başlangıç bakiyesinde işlem başına sabit $1,000.",
    "Mean across 38 OOS delisting announcements. p < 0.001. Defensive sell triggers here.":
      "38 OOS delisting duyurusunun ortalaması. p < 0.001. Savunma satışı burada tetiklenir.",
    "Mean across 38 OOS monitoring-tag announcements. Slower decay, same direction.":
      "38 OOS monitoring-tag duyurusunun ortalaması. Daha yavaş sönüm, aynı yön.",
    // risk labels
    "Position sizing": "Pozisyon boyutu",
    "Time stop": "Zaman stopu",
    "Concurrency": "Eşzamanlılık",
    "Cost modeling": "Maliyet modeli",
    "Spot only · paper": "Sadece spot · paper",
    // closing + footer
    "Open ↗": "Aç ↗",
    "Built for academic research · Not financial advice":
      "Akademik araştırma için geliştirildi · Yatırım tavsiyesi değildir",
    // dashboard sidebar + topbar
    "Trades": "İşlemler",
    "Announcements": "Duyurular",
    "Live Monitor": "Canlı İzleme",
    "← Back to Home": "← Ana sayfa",
    "Out-of-sample": "Örneklem dışı",
    "Return": "Getiri",
    // page headers
    "Bot status, recent activity, and performance overview.":
      "Bot durumu, son aktivite ve performans özeti.",
    "Trade History": "İşlem Geçmişi",
    "Every trade the bot executed — entry, exit, and result. Out-of-sample (64 trades).":
      "Botun gerçekleştirdiği her işlem — giriş, çıkış ve sonuç. Örneklem dışı (64 işlem).",
    "Every Binance announcement in the out-of-sample window — with its categorization and decision.":
      "Örneklem dışı penceredeki her Binance duyurusu — kategorisi ve kararıyla.",
    "Real-time bot status, connections, and open positions.":
      "Gerçek zamanlı bot durumu, bağlantılar ve açık pozisyonlar.",
    // cards
    "Equity Curve": "Özsermaye Eğrisi",
    "Exit Breakdown": "Çıkış Dağılımı",
    "OOS Validation": "OOS Doğrulaması",
    "Performance by Category": "Kategoriye Göre Performans",
    "All Trades": "Tüm İşlemler",
    "Filter": "Filtre",
    "API Configuration": "API Yapılandırması",
    "Connections": "Bağlantılar",
    "Open Positions": "Açık Pozisyonlar",
    "By Category": "Kategoriye Göre",
    "By Exit Reason": "Çıkış Nedenine Göre",
    // hints
    "portfolio value over time": "zaman içinde portföy değeri",
    "TP / SL / time-stop": "TP / SL / zaman stopu",
    "bullish event categories": "boğa olay kategorileri",
    "add all three keys to arm the live loop": "canlı döngüyü kurmak için üç anahtarı da ekleyin",
    "live loop armed · paper mode": "canlı döngü kuruldu · paper mod",
    "data feeds": "veri akışları",
    "all-time": "tüm zamanlar",
    // API config
    "MEXC API Key": "MEXC API Anahtarı",
    "Binance API Key": "Binance API Anahtarı",
    "Binance Announcement API": "Binance Duyuru API'si",
    "Save & Connect": "Kaydet & Bağlan",
    "Clear": "Temizle",
    "keys are stored locally in this browser only": "anahtarlar yalnızca bu tarayıcıda yerel olarak saklanır",
    // dynamic monitor / KPI labels (re-applied after each page render)
    "Trading mode": "İşlem modu",
    "Bot status": "Bot durumu",
    "Tracking since": "Takip başlangıcı",
    "Portfolio": "Portföy",
    "All-time return": "Toplam getiri",
    "Trades total": "Toplam işlem",
    "PAPER — SIMULATED": "PAPER — SİMÜLASYON",
    "WAITING FOR API KEYS": "API ANAHTARLARI BEKLENİYOR",
    "READY — MONITORING": "HAZIR — İZLEMEDE",
    "○ not set": "○ girilmedi",
    "● configured": "● yapılandırıldı",
    "connected · key armed": "bağlı · anahtar kurulu",
    "no API key": "API anahtarı yok",
    "not configured": "yapılandırılmadı",
    "polling · 1s interval": "sorgulama · 1 sn aralık",
    "Last announcement seen": "Son görülen duyuru",
    "ARMED — all connections configured, live loop ready (paper mode)":
      "KURULDU — tüm bağlantılar yapılandırıldı, canlı döngü hazır (paper mod)",
    "No open positions. Bot is idle, waiting for the next announcement.":
      "Açık pozisyon yok. Bot beklemede, bir sonraki duyuruyu bekliyor.",
    "Final equity": "Son bakiye",
    "Total return": "Toplam getiri",
    "start $10,000.00": "başlangıç $10,000.00",
    "64 trades · OOS": "64 işlem · OOS",
    "52W / 12L · wins / losses": "52K / 12Z · kazanç / kayıp",
    "Total Trades": "Toplam İşlem",
    "Win Rate": "Kazanma Oranı",
    "Total P&L": "Toplam K/Z",
    "Best Trade": "En İyi İşlem",
    "Worst Trade": "En Kötü İşlem",
    "net of fees": "komisyon sonrası net",
    "Total": "Toplam",
    "Buy signals": "Al sinyalleri",
    "Sell signals": "Sat sinyalleri",
    "Skipped": "Atlandı",
    "announcements in OOS window · corpus: 3,340": "OOS penceresindeki duyurular · korpus: 3,340",
    "first Binance-entry triggers": "ilk Binance girişi tetikleyicileri",
    "no tradeable edge": "işlem edilebilir avantaj yok",
    "Take Profit": "Take Profit",
    "Sharpe / trade": "Sharpe / işlem",
    // table headers
    "Entry Time": "Giriş Zamanı",
    "Symbol": "Sembol",
    "Category": "Kategori",
    "Exit": "Çıkış",
    "Return %": "Getiri %",
    "P&L": "K/Z",
    "Equity After": "Sonraki Bakiye",
    "Time": "Zaman",
    "Asset": "Varlık",
    "Decision": "Karar",
    "Title": "Başlık",
    "Reason": "Gerekçe",
    "Venue": "Borsa",
    "Entry Price": "Giriş Fiyatı",
    "Time Stop": "Zaman Stopu",
  };
  const TR2EN = {};
  Object.entries(EN2TR).forEach(([en, tr]) => { TR2EN[tr] = en; });

  function swapTextNodes(dict) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const p = node.parentElement;
        if (!p || p.closest("script, style")) return NodeFilter.FILTER_REJECT;
        // never touch animated counter values
        if (p.closest(".lv2-stat-value, .lv2-num-value")) return NodeFilter.FILTER_REJECT;
        return dict[node.nodeValue.trim()] ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
      },
    });
    const hits = [];
    while (walker.nextNode()) hits.push(walker.currentNode);
    hits.forEach((node) => {
      const t = node.nodeValue.trim();
      node.nodeValue = node.nodeValue.replace(t, dict[t]);
    });
  }

  function applyRich(lang) {
    SELECTOR_MAP.forEach(([sel, trHtml]) => {
      document.querySelectorAll(sel).forEach((el) => {
        if (lang === "tr") {
          if (el.dataset.i18nEn == null) el.dataset.i18nEn = el.innerHTML;
          el.innerHTML = trHtml;
        } else if (el.dataset.i18nEn != null) {
          el.innerHTML = el.dataset.i18nEn;
        }
      });
    });
  }

  function setLang(lang) {
    window.AB_LANG = lang;
    localStorage.setItem("ab_lang", lang);
    document.documentElement.lang = lang;
    applyRich(lang);
    swapTextNodes(lang === "tr" ? EN2TR : TR2EN);
    document.querySelectorAll("[data-lang-toggle]").forEach((btn) => {
      btn.textContent = lang === "tr" ? "EN" : "TR";
      btn.setAttribute("aria-label", lang === "tr" ? "Switch to English" : "Türkçeye geç");
    });
  }

  // Re-apply the current language after dynamic re-renders (router hook).
  window.AB_I18N_APPLY = function () {
    if (window.AB_LANG === "tr") swapTextNodes(EN2TR);
  };

  function boot() {
    document.querySelectorAll("[data-lang-toggle]").forEach((btn) => {
      btn.addEventListener("click", () => {
        setLang(window.AB_LANG === "tr" ? "en" : "tr");
      });
    });
    const saved = localStorage.getItem("ab_lang") || "en";
    // run after app.js boot has had a chance to render the first frame
    setTimeout(() => setLang(saved), 0);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
