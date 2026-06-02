/* ============================================================
   enhancements.js v2 — premium interactions
   Cursor spotlight · 3D tilt · magnetic CTA · decryption counters
   · live ticker · scroll progress · reveal observers
   ============================================================ */
(function () {
  "use strict";

  const $  = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  /* ---------- 1. CURSOR SPOTLIGHT ---------- */
  function initCursorSpotlight() {
    const root = $(".lv2-root");
    if (!root) return;
    let raf = null;
    let pendingX = 0, pendingY = 0;
    window.addEventListener("mousemove", (e) => {
      pendingX = e.clientX;
      pendingY = e.clientY;
      if (raf) return;
      raf = requestAnimationFrame(() => {
        root.style.setProperty("--cursor-x", pendingX + "px");
        root.style.setProperty("--cursor-y", pendingY + "px");
        raf = null;
      });
    });
    // Fade in after first mouse move (skip on touch)
    window.addEventListener("mousemove", () => root.classList.add("cursor-active"), { once: true });
  }

  /* ---------- 2. SCROLL REVEAL ---------- */
  function initReveal() {
    const targets = $$(".lv2-section-head, .lv2-strategy-item, .lv2-num-cell, .lv2-risk-row, .lv2-closing-grid");
    if (!("IntersectionObserver" in window)) {
      targets.forEach((el) => el.classList.add("is-visible"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    targets.forEach((el) => io.observe(el));
  }

  /* ---------- 3. DECRYPTION-STYLE COUNTERS ---------- */
  // Numbers scramble through digits before settling on the real value.
  const SCRAMBLE_CHARS = "0123456789";
  const easeOutExpo = (t) => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t));

  function animateValue(el, finalText, durationMs = 1800) {
    const match = finalText.match(/(-?\+?\d+(?:\.\d+)?)/);
    if (!match) return;
    const finalNum = parseFloat(match[1]);
    const prefix = finalText.slice(0, match.index);
    const suffix = finalText.slice(match.index + match[1].length);
    const decimals = (match[1].split(".")[1] || "").length;

    const startTime = performance.now();
    function tick(now) {
      const elapsed = now - startTime;
      const t = Math.min(elapsed / durationMs, 1);

      if (t < 0.5) {
        // Scramble phase
        const totalDigits = match[1].replace(/[-+.]/g, "").length;
        let scrambled = "";
        if (finalNum < 0) scrambled += "−";
        else if (finalText.startsWith("+")) scrambled += "+";
        for (let i = 0; i < totalDigits; i++) {
          if (decimals > 0 && i === totalDigits - decimals) scrambled += ".";
          scrambled += SCRAMBLE_CHARS[Math.floor(Math.random() * 10)];
        }
        el.firstChild.nodeValue = prefix + scrambled + suffix;
      } else {
        // Count-up phase
        const phaseT = (t - 0.5) * 2;
        const eased = easeOutExpo(phaseT);
        const current = finalNum * eased;
        el.firstChild.nodeValue = prefix + current.toFixed(decimals) + suffix;
      }

      if (t < 1) requestAnimationFrame(tick);
      else el.firstChild.nodeValue = prefix + finalNum.toFixed(decimals) + suffix;
    }
    requestAnimationFrame(tick);
  }

  function initCounters() {
    const heroValues = $$(".lv2-hero-data .lv2-stat-value");
    heroValues.forEach((el) => {
      if (!el.firstChild || el.firstChild.nodeType !== Node.TEXT_NODE) return;
      const original = el.firstChild.nodeValue.trim();
      if (!original) return;
      el.dataset.finalText = original;
      el.firstChild.nodeValue = original.replace(/[\d.]/g, "0");
    });

    const numCells = $$(".lv2-num-value");
    numCells.forEach((el) => {
      const first = el.firstChild;
      if (!first || first.nodeType !== Node.TEXT_NODE) return;
      const original = first.nodeValue.trim();
      if (!original || !/\d/.test(original)) return;
      el.dataset.finalText = original;
      first.nodeValue = original.replace(/[\d.]/g, "0");
    });

    const all = [...heroValues, ...numCells];
    if (!("IntersectionObserver" in window)) {
      all.forEach((el) => el.dataset.finalText && animateValue(el, el.dataset.finalText));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && entry.target.dataset.finalText) {
            animateValue(entry.target, entry.target.dataset.finalText);
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.4 }
    );
    all.forEach((el) => io.observe(el));
  }

  /* ---------- 4. 3D TILT ON CARDS ---------- */
  function initTilt() {
    const cards = $$(".lv2-strategy-item, .lv2-num-cell");
    const maxTilt = 6; // degrees
    cards.forEach((card) => {
      let raf = null;
      let pe = null;
      const update = () => {
        if (!pe) return;
        const rect = card.getBoundingClientRect();
        const x = (pe.clientX - rect.left) / rect.width;
        const y = (pe.clientY - rect.top) / rect.height;
        const ty = (x - 0.5) * maxTilt * 2;     // rotateY
        const tx = (0.5 - y) * maxTilt * 2;     // rotateX
        card.style.setProperty("--tilt-x", tx.toFixed(2) + "deg");
        card.style.setProperty("--tilt-y", ty.toFixed(2) + "deg");
        card.style.setProperty("--spot-x", (x * 100).toFixed(2) + "%");
        card.style.setProperty("--spot-y", (y * 100).toFixed(2) + "%");
        raf = null;
      };
      card.addEventListener("mouseenter", () => card.classList.add("is-tilting"));
      card.addEventListener("mousemove", (e) => {
        pe = e;
        if (raf) return;
        raf = requestAnimationFrame(update);
      });
      card.addEventListener("mouseleave", () => {
        card.classList.remove("is-tilting");
        card.style.removeProperty("--tilt-x");
        card.style.removeProperty("--tilt-y");
      });
    });
  }

  /* ---------- 5. MAGNETIC CTA BUTTONS ---------- */
  function initMagnetic() {
    const targets = $$(".lv2-cta");
    const strength = 0.25;
    targets.forEach((el) => {
      let raf = null;
      let pe = null;
      el.addEventListener("mousemove", (e) => {
        pe = e;
        if (raf) return;
        raf = requestAnimationFrame(() => {
          const rect = el.getBoundingClientRect();
          const x = pe.clientX - rect.left - rect.width / 2;
          const y = pe.clientY - rect.top - rect.height / 2;
          el.style.transform = `translate(${x * strength}px, ${y * strength}px)`;
          raf = null;
        });
      });
      el.addEventListener("mouseleave", () => {
        el.style.transition = "transform 0.5s cubic-bezier(0.2, 0.7, 0.2, 1)";
        el.style.transform = "translate(0, 0)";
        setTimeout(() => (el.style.transition = ""), 500);
      });
    });
  }

  /* ---------- 6. LIVE TICKER ---------- */
  function initTicker() {
    const hero = $(".lv2-hero");
    if (!hero) return;

    const items = [
      { sym: "PEPE",  evt: "Listed · Spot",         pct: "+12.4%", cls: "tk-pos" },
      { sym: "SUSHI", evt: "Monitoring tag",         pct: "−3.1%",  cls: "tk-neg" },
      { sym: "WLD",   evt: "Launchpool",             pct: "+8.9%",  cls: "tk-pos" },
      { sym: "OMG",   evt: "Will delist",            pct: "−7.8%",  cls: "tk-neg" },
      { sym: "JTO",   evt: "Hodler Airdrop",         pct: "+15.0%", cls: "tk-pos" },
      { sym: "WAVES", evt: "Monitoring tag",         pct: "−5.6%",  cls: "tk-neg" },
      { sym: "STRK",  evt: "Listed · Spot",          pct: "+9.2%",  cls: "tk-pos" },
      { sym: "BTS",   evt: "Will delist",            pct: "−12.1%", cls: "tk-neg" },
      { sym: "PORTAL",evt: "Launchpad",              pct: "+22.5%", cls: "tk-pos" },
      { sym: "FTT",   evt: "Monitoring tag",         pct: "−4.4%",  cls: "tk-neg" },
      { sym: "MEME",  evt: "Listed · Spot",          pct: "+6.7%",  cls: "tk-pos" },
      { sym: "MOB",   evt: "Will delist",            pct: "−8.2%",  cls: "tk-neg" },
    ];

    const ticker = document.createElement("div");
    ticker.className = "lv2-ticker";
    ticker.innerHTML = `
      <div class="lv2-ticker-tag">● LIVE</div>
      <div class="lv2-ticker-track"></div>
    `;
    const track = ticker.querySelector(".lv2-ticker-track");
    // Duplicate items so the marquee loops seamlessly
    const html = items.concat(items).map(it => `
      <span class="lv2-ticker-item">
        <strong>${it.sym}</strong>
        <span class="tk-dot"></span>
        <span>${it.evt}</span>
        <span class="tk-dot"></span>
        <span class="${it.cls}">${it.pct}</span>
      </span>
    `).join("");
    track.innerHTML = html;

    hero.insertAdjacentElement("afterend", ticker);
  }

  /* ---------- 7. SCROLL PROGRESS BAR ---------- */
  function initScrollProgress() {
    const bar = document.createElement("div");
    bar.className = "lv2-scroll-progress";
    document.body.appendChild(bar);
    let raf = null;
    const update = () => {
      const h = document.documentElement;
      const scrolled = h.scrollTop / (h.scrollHeight - h.clientHeight);
      bar.style.width = (scrolled * 100).toFixed(2) + "%";
      raf = null;
    };
    window.addEventListener("scroll", () => {
      if (raf) return;
      raf = requestAnimationFrame(update);
    }, { passive: true });
    update();
  }

  /* ============================================================
     DASHBOARD ENHANCEMENTS
     ============================================================ */

  /* ---------- D1. CARD CURSOR SPOTLIGHT ---------- */
  function initDashboardCardSpotlight() {
    const cards = $$("#dashboard .card, #dashboard .kpi-grid > *");
    cards.forEach((card) => {
      let raf = null;
      let pe = null;
      const update = () => {
        if (!pe) return;
        const rect = card.getBoundingClientRect();
        const x = ((pe.clientX - rect.left) / rect.width) * 100;
        const y = ((pe.clientY - rect.top) / rect.height) * 100;
        card.style.setProperty("--d-spot-x", x.toFixed(2) + "%");
        card.style.setProperty("--d-spot-y", y.toFixed(2) + "%");
        raf = null;
      };
      card.addEventListener("mousemove", (e) => {
        pe = e;
        if (raf) return;
        raf = requestAnimationFrame(update);
      });
    });
  }

  /* ---------- D2. KPI VALUE COUNTER (when data populates) ---------- */
  function animateNumber(el, finalText, durationMs = 1200) {
    const match = String(finalText).match(/(-?\+?\d+(?:[.,]\d+)?)/);
    if (!match) return;
    const cleaned = match[1].replace(",", ".");
    const finalNum = parseFloat(cleaned);
    if (isNaN(finalNum)) return;
    const prefix = String(finalText).slice(0, match.index);
    const suffix = String(finalText).slice(match.index + match[1].length);
    const decimals = (cleaned.split(".")[1] || "").length;
    const startTime = performance.now();
    function tick(now) {
      const t = Math.min((now - startTime) / durationMs, 1);
      const eased = easeOutExpo(t);
      const cur = finalNum * eased;
      el.textContent = prefix + cur.toFixed(decimals) + suffix;
      if (t < 1) requestAnimationFrame(tick);
      else el.textContent = String(finalText);
    }
    requestAnimationFrame(tick);
  }

  function initKpiCounters() {
    // Watch topbar values (Return / Trades / Win rate / PF) for the
    // moment app.js swaps "—" for real numbers
    const targets = ["all-time-return", "total-trades", "topbar-wr", "topbar-pf"]
      .map((id) => document.getElementById(id))
      .filter(Boolean);
    targets.forEach((el) => {
      const mo = new MutationObserver(() => {
        const text = el.textContent.trim();
        if (!text || text === "—" || el.dataset.animated === "1") return;
        if (!/\d/.test(text)) return;
        el.dataset.animated = "1";
        const final = text;
        animateNumber(el, final, 1100);
      });
      mo.observe(el, { childList: true, characterData: true, subtree: true });
    });

    // Watch the KPI grid for newly-injected cards
    const kpiGrids = $$("#dashboard .kpi-grid");
    kpiGrids.forEach((grid) => {
      const mo = new MutationObserver(() => {
        const values = grid.querySelectorAll(
          ".value, .kpi-value, [data-value], strong"
        );
        values.forEach((el) => {
          if (el.dataset.animated === "1") return;
          const text = el.textContent.trim();
          if (!/\d/.test(text)) return;
          if (text === "—") return;
          el.dataset.animated = "1";
          animateNumber(el, text, 1100);
        });
      });
      mo.observe(grid, { childList: true, subtree: true });
    });
  }

  /* ---------- D3. TRADE ROWS STAGGERED FADE-IN ---------- */
  function initTradeRowStagger() {
    const tables = $$("#dashboard table");
    tables.forEach((tbl) => {
      const tbody = tbl.querySelector("tbody");
      if (!tbody) return;
      const mo = new MutationObserver(() => {
        const rows = tbody.querySelectorAll("tr");
        rows.forEach((row, i) => {
          if (row.dataset.fadedIn === "1") return;
          row.dataset.fadedIn = "1";
          row.style.opacity = "0";
          row.style.transform = "translateY(8px)";
          row.style.transition =
            "opacity 0.5s cubic-bezier(0.2, 0.7, 0.2, 1), transform 0.5s cubic-bezier(0.2, 0.7, 0.2, 1)";
          const delay = Math.min(i * 30, 600);
          setTimeout(() => {
            row.style.opacity = "1";
            row.style.transform = "translateY(0)";
          }, delay);

          // Auto-color numeric return cells
          row.querySelectorAll("td.num").forEach((cell) => {
            const t = cell.textContent.trim();
            if (t.startsWith("+") || (/^\d/.test(t) && parseFloat(t) > 0)) {
              if (t.includes("%") || cell.classList.contains("return")) {
                cell.classList.add("return-pos");
              }
            } else if (t.startsWith("-") || t.startsWith("−")) {
              cell.classList.add("return-neg");
            }
          });
        });
      });
      mo.observe(tbody, { childList: true });
    });
  }

  /* ---------- D4. KEYBOARD SHORTCUT — '/' focuses search if any, 'g d' goto dashboard ---------- */
  function initShortcuts() {
    let lastKey = "";
    let lastKeyTime = 0;
    window.addEventListener("keydown", (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      const now = Date.now();
      // 'g' then 'd' → enter dashboard
      if (lastKey === "g" && e.key === "d" && now - lastKeyTime < 800) {
        if (typeof enterDashboard === "function") enterDashboard();
        lastKey = "";
        return;
      }
      // 'g' then 'h' → exit to landing
      if (lastKey === "g" && e.key === "h" && now - lastKeyTime < 800) {
        if (typeof exitDashboard === "function") exitDashboard();
        lastKey = "";
        return;
      }
      lastKey = e.key;
      lastKeyTime = now;
    });
  }

  /* ---------- BOOT ---------- */
  function boot() {
    const landing = $("#landing");
    const dashboard = $("#dashboard");

    if (landing) {
      initCursorSpotlight();
      initReveal();
      initCounters();
      initTilt();
      initMagnetic();
      initTicker();
      initScrollProgress();
    }

    if (dashboard) {
      initDashboardCardSpotlight();
      initKpiCounters();
      initTradeRowStagger();
      initShortcuts();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
