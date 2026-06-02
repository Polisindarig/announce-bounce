/* =========================================================
   Announce & Bounce — Bot Dashboard
   ========================================================= */

const API = "/api";

/* ----- Formatters --------------------------------------- */
const fmtPct = (v, dp = 2) => {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  return `${n > 0 ? "+" : ""}${n.toFixed(dp)}%`;
};

const fmtUsd = (v, dp = 2) => {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return "$" + Number(v).toLocaleString("en-US", {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  });
};

const fmtUsdSigned = (v, dp = 2) => {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const sign = n > 0 ? "+" : "";
  return sign + fmtUsd(n, dp);
};

const fmtInt = (v) =>
  v == null ? "—" : Number(v).toLocaleString("en-US");

const fmtTime = (iso) => {
  if (!iso) return "—";
  return String(iso).replace("T", " ").slice(0, 16);
};

const shortHash = (h) => (h ? String(h).slice(0, 8) : "—");
const colorOf = (v) => (v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "");

/* ----- Labels ------------------------------------------ */
const categoryLabel = (c) => ({
  LISTING_SPOT: "Spot Listing",
  LISTING_FUTURES: "Futures Listing",
  LAUNCHPOOL_LAUNCHPAD: "Launchpool",
  DELISTING: "Delisting",
})[c] || c;

const exitLabel = (e) => ({
  tp_hit: "Take Profit",
  sl_hit: "Stop Loss",
  sl_hit_pessimistic: "Stop Loss",
  time_stop: "Time Stop",
  forced_exit: "Forced Exit",
})[e] || e;

const exitBadge = (e) => ({
  tp_hit: "badge-buy",
  sl_hit: "badge-sell",
  sl_hit_pessimistic: "badge-sell",
  time_stop: "badge-skip",
  forced_exit: "badge-sell",
})[e] || "badge-skip";

const exitShort = (e) => ({
  tp_hit: "TP",
  sl_hit: "SL",
  sl_hit_pessimistic: "SL",
  time_stop: "TIME",
  forced_exit: "EXIT",
})[e] || e;

/* ----- API ---------------------------------------------- */
async function getJson(path) {
  try {
    const r = await fetch(`${API}${path}`);
    if (!r.ok) throw new Error(r.statusText);
    return await r.json();
  } catch (err) {
    console.warn("fetch failed", path, err);
    return null;
  }
}

/* ----- Router ------------------------------------------- */
const pageLoaders = {
  overview: loadDashboard,
  trades: loadTrades,
  announcements: loadAnnouncements,
  monitor: loadMonitor,
};

/**
 * Activate a dashboard page with a slide-up + fade transition.
 *
 * Flow:
 *  1. Identify the currently-active page; if it differs from the target,
 *     tag it with `.is-leaving` so its CSS exit animation plays (~110ms).
 *  2. After the exit animation completes, remove `.active` from the
 *     outgoing page and add it to the incoming page — the entering
 *     CSS animation (+ staggered children) then plays (~240ms).
 *  3. Sidebar nav `.active` highlight updates in lockstep with the
 *     swap so the indicator never lags the surface.
 *  4. Honours prefers-reduced-motion via the stylesheet (zero-duration
 *     animations); JS still routes correctly.
 */
function activatePage(route) {
  // Route may include a query string (e.g. "trades?set=is")
  const page = route.split("?")[0];
  const targetSection = document.getElementById(`page-${page}`);
  const currentSection = document.querySelector(".page.active");

  // Update sidebar nav highlight immediately so it reflects intent.
  document.querySelectorAll("#nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.route === page);
  });

  // No transition needed: first navigation, or same page
  if (!currentSection || currentSection === targetSection) {
    document.querySelectorAll(".page").forEach((p) => {
      p.classList.toggle("active", p === targetSection);
      p.classList.remove("is-leaving");
    });
    const loader = pageLoaders[page];
    if (loader) loader();
    return;
  }

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const exitMs = reduced ? 0 : 110;

  currentSection.classList.add("is-leaving");
  currentSection.classList.remove("active");

  setTimeout(() => {
    currentSection.classList.remove("is-leaving");
    document.querySelectorAll(".page").forEach((p) => {
      p.classList.toggle("active", p === targetSection);
    });
    const loader = pageLoaders[page];
    if (loader) loader();
  }, exitMs);
}

// Reload current page when hash query changes (e.g. IS/OOS toggle)
window.addEventListener("hashchange", () => {
  const hash = (location.hash || "#overview").slice(1);
  activatePage(hash);
});

function initRouter() {
  document.querySelectorAll("#nav a").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const route = a.dataset.route;
      history.replaceState(null, "", `#${route}`);
      activatePage(route);
      if (window.innerWidth <= 768) {
        document.getElementById("sidebar").classList.remove("open");
      }
    });
  });
  const hash = (location.hash || "#overview").slice(1);
  activatePage(hash);
}

/* ----- KPI card helper ---------------------------------- */
function kpiCard(label, value, sub, klass = "") {
  const el = document.createElement("div");
  el.className = "kpi";
  el.innerHTML = `
    <div class="label">${label}</div>
    <div class="value ${klass}">${value}</div>
    <div class="sub">${sub || ""}</div>
  `;
  return el;
}

/**
 * Populate the dashboard topbar with OUT-OF-SAMPLE headline metrics so the
 * indicator strip matches the thesis evaluation surface (17 trades / +12.95%
 * / 5.02 PF / 0.832 Sharpe) and does NOT regress to in-sample calibration
 * stats (which would mis-represent the "live" evidence the page shows).
 *
 * /bot/state is still consulted only for git_head + manifest timestamp
 * (footer provenance). It is no longer the source of headline numbers.
 */
async function loadStatusBar() {
  const [state, oos] = await Promise.all([
    getJson("/bot/state").catch(() => null),
    getJson("/oos").catch(() => null),
  ]);

  const s = oos?.summary || {};

  const setText = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  };
  const setColored = (id, value, signed) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = value;
    const v = parseFloat(String(value).replace(/[+%\s]/g, ""));
    el.className = "value " + (signed && !Number.isNaN(v)
      ? (v > 0 ? "pos" : v < 0 ? "neg" : "")
      : "");
  };

  setColored(
    "all-time-return",
    s.total_return_pct != null ? fmtPct(s.total_return_pct) : "—",
    true,
  );
  setText("total-trades", s.n_trades ?? "—");
  setText(
    "topbar-wr",
    s.win_rate != null ? `${s.win_rate.toFixed(1)}%` : "—",
  );
  setText(
    "topbar-pf",
    s.profit_factor != null ? s.profit_factor.toFixed(2) : "—",
  );

  // Footer provenance (git head, manifest time) still comes from /bot/state.
  if (state) {
    const gh = document.getElementById("git-head");
    if (gh) gh.textContent = shortHash(state.git_head);
    const mt = document.getElementById("manifest-time");
    if (mt) {
      mt.textContent = state.manifest_generated_at
        ? `manifest: ${new Date(state.manifest_generated_at).toISOString().slice(0, 10)}`
        : "manifest: —";
    }
  }
}

/* =========================================================
   PAGE: DASHBOARD
   ========================================================= */
/**
 * Render the Overview page entirely from the OUT-OF-SAMPLE result so every
 * surface on this page tells the same story (17 trades / +12.95% / 5.02 PF
 * / 0.832 Sharpe / 1.31% MDD). The legacy /bot/state endpoint still mirrors
 * the IS m0 backtest — using it here would mis-represent the page as a
 * live-trading dashboard.
 */
async function loadDashboard() {
  const [oos, anns] = await Promise.all([
    getJson("/oos"),
    getJson("/announcements/recent"),
  ]);

  const s = oos?.summary || {};
  // OOS equity curve lives inside the /oos response; the legacy /equity
  // endpoint mirrors the IS (m0) backtest and would mis-represent the
  // chart on this page.
  const equity = (oos?.equity_curve || []).map((p) => ({
    date: (p.timestamp || "").slice(0, 10) || `t${p.trade_id}`,
    timestamp: p.timestamp,
    equity: p.equity,
  }));

  // Derived equity values from the OOS summary
  const start = s.initial_equity ?? 10000;
  const end = s.final_equity ?? start;

  // KPI cards (all values now OOS-sourced)
  const wrap = document.getElementById("overview-kpis");
  wrap.innerHTML = "";
  wrap.appendChild(kpiCard("Final equity",   fmtUsd(end),
                            `start ${fmtUsd(start)}`));
  wrap.appendChild(kpiCard("Total return",   fmtPct(s.total_return_pct),
                            `${s.n_trades ?? 0} trades · OOS`,
                            colorOf(s.total_return_pct)));
  wrap.appendChild(kpiCard("Win rate",
                            `${(s.win_rate ?? 0).toFixed(1)}%`,
                            `${winLossSplit(s)} · wins / losses`));
  wrap.appendChild(kpiCard("Profit factor",
                            (s.profit_factor ?? 0).toFixed(2),
                            "gross W ÷ |gross L|"));

  // Equity curve — sourced from oos.equity_curve, not /api/equity (legacy IS)
  renderEquityCurve(equity);

  // Exit breakdown — OOS exits
  renderExitBreakdown(s.by_exit_reason || {});

  // Announcement feed
  renderDashboardAnnouncements(anns || []);

  // OOS summary card (still uses the full oos object)
  renderOosSummary(oos);

  // Category breakdown — OOS categories
  renderCategoryBreakdown(s.by_category || {});
}

/** Format "W / L" split from an OOS summary if available. */
function winLossSplit(s) {
  if (!s || !s.n_trades || s.win_rate == null) return "—";
  const wins = Math.round((s.win_rate / 100) * s.n_trades);
  const losses = s.n_trades - wins;
  return `${wins}W / ${losses}L`;
}

/**
 * Render the equity curve using the bespoke (Intentional Minimalism) theme:
 *  - single accent colour (burnt orange) for the line
 *  - linear soft gradient fill (15% → 0%) to suggest area without competing
 *    with the foreground line
 *  - hairline grid only on the Y axis (the X axis loses its grid entirely
 *    because time-density is already implied by point spacing)
 *  - monospace tabular tick labels for numeric continuity with KPI cards
 *  - tooltip is a minimal mono callout, not the Chart.js default rounded box
 */
function renderEquityCurve(points) {
  const ctx = document.getElementById("equityChart");
  if (!ctx) return;
  if (ctx.chart) ctx.chart.destroy();
  if (!points.length) return;

  // Pull live tokens from the document so a future light-mode toggle re-themes
  // the chart without code changes.
  const root = getComputedStyle(document.documentElement);
  const accent = root.getPropertyValue("--lv2-accent").trim() || "#FF6B35";
  const ink = root.getPropertyValue("--lv2-ink").trim() || "#F4F4F0";
  const rule = root.getPropertyValue("--lv2-rule").trim() || "rgba(244,244,240,0.08)";
  const faint = root.getPropertyValue("--lv2-ink-faint").trim() || "rgba(244,244,240,0.32)";
  const muted = root.getPropertyValue("--lv2-ink-muted").trim() || "rgba(244,244,240,0.58)";
  const mono = '"JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace';

  // Build a smooth top-to-bottom gradient for the fill. Re-created on each
  // render so it survives canvas resizes (Chart.js requirement).
  const canvas = ctx.getContext ? ctx : ctx.canvas;
  const c2d = canvas.getContext ? canvas.getContext("2d") : null;
  let gradient = null;
  if (c2d) {
    gradient = c2d.createLinearGradient(0, 0, 0, ctx.offsetHeight || 280);
    gradient.addColorStop(0, "rgba(255, 107, 53, 0.18)");
    gradient.addColorStop(1, "rgba(255, 107, 53, 0.00)");
  }

  ctx.chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: points.map((p) => p.date || p.timestamp || ""),
      datasets: [{
        label: "Equity",
        data: points.map((p) => p.equity),
        borderColor: accent,
        backgroundColor: gradient || "rgba(255, 107, 53, 0.10)",
        borderWidth: 1.4,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBackgroundColor: ink,
        pointHoverBorderColor: accent,
        pointHoverBorderWidth: 2,
        tension: 0.28,
        fill: true,
        capBezierPoints: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(10, 10, 10, 0.96)",
          borderColor: rule,
          borderWidth: 1,
          titleColor: muted,
          titleFont: { family: mono, size: 10, weight: "400" },
          titleSpacing: 2,
          bodyColor: ink,
          bodyFont: { family: mono, size: 13, weight: "500" },
          padding: 12,
          cornerRadius: 1,
          displayColors: false,
          callbacks: {
            title: (items) => (items[0]?.label || "").toUpperCase(),
            label: (c) => `  $${Math.round(c.parsed.y).toLocaleString()}`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false, drawBorder: false },
          ticks: {
            color: faint,
            font: { family: mono, size: 10 },
            maxTicksLimit: 6,
            maxRotation: 0,
            autoSkipPadding: 18,
          },
          border: { color: rule },
        },
        y: {
          grid: { color: rule, drawBorder: false, lineWidth: 1 },
          ticks: {
            color: faint,
            font: { family: mono, size: 10 },
            padding: 8,
            callback: (v) => `${(v / 1000).toFixed(1)}k`,
          },
          border: { display: false },
        },
      },
    },
  });
}

function renderExitBreakdown(exits) {
  const wrap = document.getElementById("exit-breakdown");
  if (!exits || !Object.keys(exits).length) {
    wrap.innerHTML = `<div class="muted-block">No exit data.</div>`;
    return;
  }
  wrap.innerHTML = Object.entries(exits)
    .map(([reason, d]) => `
      <div class="stat-row">
        <span class="k">
          <span class="badge ${exitBadge(reason)}">${exitShort(reason)}</span>
          <strong style="margin-left:8px">${exitLabel(reason)}</strong>
          <span class="muted" style="margin-left:8px">${d.n} trades</span>
        </span>
        <span class="v ${colorOf(d.mean_return)}">${(d.mean_return * 100).toFixed(2)}% avg</span>
      </div>`)
    .join("");
}

/**
 * Editorial-style Recent Announcements render.
 *
 * Visual decisions:
 *  - Date column: monospace (continuity with KPI/Numbers tabular sets)
 *  - Asset column: monospace + medium weight (a "ticker" reads as code)
 *  - Title column: body sans-serif, single-line truncate with native title-tip
 *  - Decision column: outlined badge, semantic colour (BUY → pos, SELL → neg,
 *    SKIP → muted) — no filled green/red rectangles, which fight the
 *    monochrome restraint of the rest of the surface
 *  - Reason column: muted body text
 *
 * Counter chip in the card header summarises the three populations.
 */
function renderDashboardAnnouncements(anns) {
  const tbody = document.querySelector("#dash-ann-table tbody");
  const hint = document.getElementById("dash-ann-count");
  if (!tbody) return;

  if (!anns.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="muted" style="padding:2rem;text-align:center">No announcements.</td></tr>`;
    if (hint) hint.textContent = "0 events";
    return;
  }

  const buys = anns.filter(a => a.decision === "BUY").length;
  const sells = anns.filter(a => a.decision === "SELL").length;
  const skips = anns.filter(a => a.decision === "SKIP").length;
  if (hint) {
    hint.textContent = `${buys} buy · ${sells} sell · ${skips} skip`;
  }

  const badge = (d) => {
    const cls = {
      BUY:  "badge-pos",
      SELL: "badge-neg",
      SKIP: "badge-muted",
    }[d] || "badge-muted";
    const glyph = { BUY: "↗", SELL: "↘", SKIP: "—" }[d] || "·";
    return `<span class="badge ${cls}">${glyph}&nbsp;${d}</span>`;
  };

  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]
  ));

  tbody.innerHTML = anns.map((a) => {
    const dt = fmtTime(a.time);
    const asset = a.asset || "—";
    const title = esc(a.title || "");
    return `
    <tr>
      <td class="num" style="white-space:nowrap;color:var(--lv2-ink-muted)">${dt}</td>
      <td><strong>${esc(asset)}</strong></td>
      <td class="muted" style="max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${title}">${title}</td>
      <td>${badge(a.decision)}</td>
      <td class="muted" style="font-size:0.85rem">${esc(a.reason)}</td>
    </tr>`;
  }).join("");
}

function renderOosSummary(oos) {
  const wrap = document.getElementById("oos-summary");
  if (!oos || !oos.summary) {
    wrap.innerHTML = `<div class="muted-block">No OOS data.</div>`;
    return;
  }
  const s = oos.summary;
  const w = oos.window || {};
  document.getElementById("oos-window").textContent = `${w.oos_start || "?"} → ${w.oos_end || "?"}`;

  const verdict = s.n_trades === 0 ? "No trades"
    : (s.sharpe_per_trade || 0) > 0 ? "POSITIVE edge" : "NEGATIVE";
  const verdictCls = (s.sharpe_per_trade || 0) > 0 ? "pos" : "neg";

  wrap.innerHTML = `
    <div class="stat-row"><span class="k">Trades</span><span class="v">${s.n_trades}</span></div>
    <div class="stat-row"><span class="k">Total return</span><span class="v ${colorOf(s.total_return_pct)}">${fmtPct(s.total_return_pct)}</span></div>
    <div class="stat-row"><span class="k">Win rate</span><span class="v">${s.win_rate?.toFixed(1) || "—"}%</span></div>
    <div class="stat-row"><span class="k">Profit factor</span><span class="v">${s.profit_factor?.toFixed(2) || "—"}</span></div>
    <div class="stat-row"><span class="k">Sharpe / trade</span><span class="v">${s.sharpe_per_trade?.toFixed(3) || "—"}</span></div>
    <div class="stat-row" style="margin-top:8px;border-top:1px solid #262C3A;padding-top:8px">
      <span class="k">Verdict</span>
      <span class="v ${verdictCls}" style="font-weight:700">${verdict}</span>
    </div>`;
}

function renderCategoryBreakdown(cats) {
  const wrap = document.getElementById("category-breakdown");
  if (!cats || !Object.keys(cats).length) {
    wrap.innerHTML = `<div class="muted-block">No category data.</div>`;
    return;
  }
  wrap.innerHTML = Object.entries(cats)
    .sort((a, b) => b[1].total_pnl - a[1].total_pnl)
    .map(([cat, d]) => `
      <div class="stat-row">
        <span class="k">
          <strong>${categoryLabel(cat)}</strong>
          <span class="muted" style="margin-left:8px">${d.n} trades</span>
        </span>
        <span class="v">
          <span class="${colorOf(d.mean_return)}">${(d.mean_return * 100).toFixed(2)}% avg</span>
          &nbsp;·&nbsp;<span class="${colorOf(d.total_pnl)}">${fmtUsdSigned(d.total_pnl)}</span>
        </span>
      </div>`)
    .join("");
}

/* =========================================================
   PAGE: TRADES
   ========================================================= */
// Trade History view — always out-of-sample (frozen M0).
async function loadTrades() {
  const setName = "oos";
  const endpoint = "/oos";

  const bt = (await getJson(endpoint)) || {};
  const trades = bt.trades || [];
  const s = bt.summary || {};

  const kpis = document.getElementById("trades-kpis");
  kpis.innerHTML = "";

  const wins = trades.filter((t) => (t.return_pct || 0) > 0).length;
  const losses = trades.length - wins;
  // OOS schema uses `pnl_net`; legacy/IS schema uses `pnl`
  const pnlOf = (t) => (t.pnl_net != null ? t.pnl_net : (t.pnl || 0));
  const totalPnl = trades.reduce((a, t) => a + pnlOf(t), 0);
  const best = trades.reduce((a, t) => Math.max(a, (t.return_pct || -1) * 100), -100);
  const worst = trades.reduce((a, t) => Math.min(a, (t.return_pct || 1) * 100), 100);

  const setLabel = "out-of-sample (frozen M0)";
  kpis.appendChild(kpiCard("Total Trades", fmtInt(trades.length), `${wins}W / ${losses}L · ${setLabel}`));
  kpis.appendChild(kpiCard("Win Rate", `${s.win_rate?.toFixed(1) || "—"}%`, ""));
  kpis.appendChild(kpiCard("Total P&L", fmtUsdSigned(totalPnl), "net of fees", colorOf(totalPnl)));
  kpis.appendChild(kpiCard("Best Trade", fmtPct(best), "", "pos"));
  kpis.appendChild(kpiCard("Worst Trade", fmtPct(worst), "", "neg"));

  document.getElementById("trades-count").textContent =
    `${trades.length} trades · ${setLabel}`;

  const tbody = document.querySelector("#trades-table tbody");
  if (!trades.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No trades.</td></tr>`;
    return;
  }

  // Running-equity reconstruction (neither IS nor OOS endpoints expose equity_after).
  const sortedAsc = [...trades].sort(
    (a, b) => (a.entry_time || "").localeCompare(b.entry_time || "")
  );
  let eq = s.initial_equity || 10000;
  const eqMap = new Map();
  for (const t of sortedAsc) {
    eq += pnlOf(t);
    eqMap.set(t.trade_id ?? `${t.symbol}-${t.entry_time}`, eq);
  }

  const sortedDesc = [...sortedAsc].reverse();
  tbody.innerHTML = sortedDesc.map((t) => {
    const ret = (t.return_pct || 0) * 100;
    const after = eqMap.get(t.trade_id ?? `${t.symbol}-${t.entry_time}`);
    return `
    <tr>
      <td class="num">${fmtTime(t.entry_time)}</td>
      <td><strong>${t.symbol}</strong></td>
      <td>${categoryLabel(t.category)}</td>
      <td><span class="badge ${exitBadge(t.exit_reason)}">${exitLabel(t.exit_reason)}</span></td>
      <td class="num ${colorOf(ret)}">${fmtPct(ret)}</td>
      <td class="num ${colorOf(pnlOf(t))}">${fmtUsdSigned(pnlOf(t))}</td>
      <td class="num">${fmtUsd(after)}</td>
    </tr>`;
  }).join("");
}

/* =========================================================
   LANDING ⇄ DASHBOARD — mechanical curtain transition
   ========================================================= */

/**
 * Plays a two-phase curtain animation around a synchronous DOM swap.
 *
 * Phase 1 ("covering"): a burnt-orange panel grows from the top of the
 *   viewport to fill the screen (~280ms, ease-in cubic-bezier).
 * Swap moment: the source element hides, the destination element shows,
 *   any per-surface initialisation runs (status bar, page loader).
 * Phase 2 ("lifting"): the panel collapses upward off the screen
 *   (~280ms, ease-out cubic-bezier with overshoot).
 *
 * Honours `prefers-reduced-motion: reduce` by short-circuiting both
 * phases — the DOM swap still happens, but no animation.
 */
function _runCurtainTransition(swap) {
  const curtain = document.getElementById("page-curtain");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (!curtain || reduced) {
    swap();
    return;
  }

  // Disable nav clicks during the dance to prevent half-state input.
  document.body.style.pointerEvents = "none";

  // Phase 1: cover
  curtain.style.pointerEvents = "auto";
  curtain.setAttribute("data-phase", "covering");

  const COVER_MS = 280;
  const LIFT_MS = 280;
  const SETTLE_HOLD = 40; // tiny gap between phases so swap is fully painted

  setTimeout(() => {
    // Swap happens while the curtain fully covers the viewport.
    swap();

    // Phase 2: lift
    requestAnimationFrame(() => {
      setTimeout(() => {
        curtain.setAttribute("data-phase", "lifting");
        setTimeout(() => {
          curtain.removeAttribute("data-phase");
          curtain.style.pointerEvents = "none";
          document.body.style.pointerEvents = "";
        }, LIFT_MS);
      }, SETTLE_HOLD);
    });
  }, COVER_MS);
}

/**
 * Settle animation on a freshly-revealed surface — gives a 1.008→1.0
 * scale + opacity nudge so the surface looks "placed", not "popped".
 */
function _settle(el) {
  if (!el) return;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced) return;
  el.classList.remove("lv2-settle");
  // Force reflow so the class re-application restarts the animation.
  void el.offsetWidth;
  el.classList.add("lv2-settle");
}

function enterDashboard() {
  _runCurtainTransition(() => {
    const landing = document.getElementById("landing");
    const dashboard = document.getElementById("dashboard");
    landing.style.display = "none";
    dashboard.style.display = "grid";
    history.replaceState(null, "", "#overview");
    activatePage("overview");
    loadStatusBar();
    _settle(dashboard);
  });
}

function exitDashboard() {
  _runCurtainTransition(() => {
    const landing = document.getElementById("landing");
    const dashboard = document.getElementById("dashboard");
    dashboard.style.display = "none";
    landing.style.display = "";
    history.replaceState(null, "", "/");
    _settle(landing);
    loadHeroStats();
  });
}

/**
 * Populate the landing hero numbers from the live OOS endpoint so the figures
 * never go stale relative to the backtest artifacts. Uses a small unit-aware
 * formatter so the "%" / no-unit decision is data-driven, not hardcoded.
 *
 * Edge cases handled:
 *  - API offline → leave the static HTML defaults in place (no spinner flash)
 *  - Missing field → element keeps its baseline content
 *  - Non-numeric value → silently ignored
 */
async function loadHeroStats() {
  const oos = await getJson("/oos").catch(() => null);
  if (!oos?.summary) return;
  const s = oos.summary;

  const set = (id, value, unit = "") => {
    const el = document.getElementById(id);
    if (!el || value == null || Number.isNaN(value)) return;
    const sign = value > 0 && id === "hero-return" ? "+" : "";
    el.innerHTML =
      `${sign}${value.toFixed(2)}` +
      (unit
        ? `<span style="font-size:0.45em;color:var(--lv2-ink-faint);margin-left:0.05em">${unit}</span>`
        : "");
  };

  set("hero-return", s.total_return_pct, "%");
  set("hero-wr", s.win_rate, "%");
  set("hero-pf", s.profit_factor, "");

  // Update the live "Win rate · N trades" subtitle if present
  const wrLabel = document.querySelector("[data-hero-wr-label]");
  if (wrLabel && s.n_trades != null) {
    wrLabel.textContent = `Win rate · ${s.n_trades} trades`;
  }
}

/* ----- Mobile menu ----- */
function initMenu() {
  const btn = document.getElementById("menu-btn");
  const sidebar = document.getElementById("sidebar");
  if (btn && sidebar) {
    btn.addEventListener("click", () => sidebar.classList.toggle("open"));
  }
}

/* ----- Boot --------------------------------------------- */
async function boot() {
  const hash = location.hash.slice(1).split("?")[0];  // strip query string
  const isDashboardRoute = ["overview", "trades", "announcements", "monitor"].includes(hash);

  if (isDashboardRoute) {
    document.getElementById("landing").style.display = "none";
    document.getElementById("dashboard").style.display = "grid";
    initRouter();
    initMenu();
    await loadStatusBar();
  } else {
    initRouter();
    initMenu();
    loadHeroStats();
  }
}

document.addEventListener("DOMContentLoaded", boot);

/* =========================================================
   PAGE: ANNOUNCEMENTS
   ========================================================= */
const _annState = { all: [], cat: "ALL", dec: "ALL", q: "" };

async function loadAnnouncements() {
  const data = (await getJson("/announcements/recent")) || [];
  _annState.all = data;

  // KPI cards
  const kpis = document.getElementById("ann-kpis");
  if (kpis) {
    kpis.innerHTML = "";
    const total = data.length;
    const buys  = data.filter(a => /BUY/i.test(a.decision)).length;
    const sells = data.filter(a => /SELL/i.test(a.decision)).length;
    const skips = data.filter(a => /SKIP/i.test(a.decision)).length;
    kpis.appendChild(kpiCard("Total", fmtInt(total), "announcements ingested"));
    kpis.appendChild(kpiCard("Buy signals", fmtInt(buys), "listing-spot triggers", "pos"));
    kpis.appendChild(kpiCard("Sell signals", fmtInt(sells), "delisting + monitoring", "neg"));
    kpis.appendChild(kpiCard("Skipped", fmtInt(skips), "no tradeable edge"));
  }

  // Filter chips — kept on outer scope so click handlers can re-render them.
  const cats = Array.from(new Set(data.map(a => a.category).filter(Boolean))).sort();
  const decs = Array.from(new Set(data.map(a => a.decision).filter(Boolean))).sort();
  const catValues = ["ALL", ...cats];
  const decValues = ["ALL", ...decs];
  const drawChips = () => {
    renderChips("ann-cat-chips", catValues, _annState.cat, (val) => {
      _annState.cat = val; drawChips(); renderAnnTable();
    });
    renderChips("ann-dec-chips", decValues, _annState.dec, (val) => {
      _annState.dec = val; drawChips(); renderAnnTable();
    });
  };
  drawChips();

  // Search input
  const search = document.getElementById("ann-search");
  if (search && !search.dataset.wired) {
    search.dataset.wired = "1";
    search.addEventListener("input", (e) => {
      _annState.q = e.target.value.toLowerCase();
      renderAnnTable();
    });
  }

  renderAnnTable();
}

function renderChips(containerId, values, active, onClick) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = values.map(v => `
    <button class="ann-chip ${v === active ? "is-active" : ""}" data-val="${v}">${v}</button>
  `).join("");
  el.querySelectorAll(".ann-chip").forEach(b => {
    b.addEventListener("click", () => onClick(b.dataset.val));
  });
}

function renderAnnTable() {
  const tbody = document.querySelector("#ann-table tbody");
  if (!tbody) return;
  const { all, cat, dec, q } = _annState;
  const filtered = all.filter(a => {
    if (cat !== "ALL" && a.category !== cat) return false;
    if (dec !== "ALL" && a.decision !== dec) return false;
    if (q && !(`${a.asset || ""} ${a.title || ""}`.toLowerCase().includes(q))) return false;
    return true;
  });
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="muted">No announcements match filters.</td></tr>`;
    return;
  }
  tbody.innerHTML = filtered.map(a => {
    const decClass = /BUY/i.test(a.decision) ? "is-pos"
                  : /SELL/i.test(a.decision) ? "is-neg"
                  : "is-skip";
    return `
      <tr>
        <td class="num">${fmtTime(a.time)}</td>
        <td><strong>${a.asset || "—"}</strong></td>
        <td><span class="ann-cat-tag">${a.category || "—"}</span></td>
        <td><span class="ann-dec ${decClass}">${a.decision || "—"}</span></td>
        <td class="ann-title">${a.title || "—"}</td>
        <td class="muted">${a.reason || ""}</td>
      </tr>
    `;
  }).join("");
}

/* =========================================================
   PAGE: LIVE MONITOR
   ========================================================= */
async function loadMonitor() {
  const s = (await getJson("/bot/state")) || {};

  // Top status bar
  const statusBar = document.getElementById("monitor-status-bar");
  if (statusBar) {
    const modeClr   = s.mode === "live" ? "is-pos" : "is-warn";
    const statusClr = s.status === "running" ? "is-pos" : "is-warn";
    statusBar.innerHTML = `
      <div class="mon-card">
        <div class="mon-card-grid">
          <div class="mon-stat">
            <span class="mon-stat-label">Mode</span>
            <span class="mon-stat-value ${modeClr}"><span class="mon-pulse"></span>${(s.mode || "—").toUpperCase()}</span>
          </div>
          <div class="mon-stat">
            <span class="mon-stat-label">Status</span>
            <span class="mon-stat-value ${statusClr}">${(s.status || "—").toUpperCase()}</span>
          </div>
          <div class="mon-stat">
            <span class="mon-stat-label">Data source</span>
            <span class="mon-stat-value mon-mono">${s.data_source || "—"}</span>
          </div>
          <div class="mon-stat">
            <span class="mon-stat-label">Started</span>
            <span class="mon-stat-value mon-mono">${s.started_at || "—"}</span>
          </div>
          <div class="mon-stat">
            <span class="mon-stat-label">Portfolio</span>
            <span class="mon-stat-value">${fmtUsd(s.portfolio_value_usdt)}</span>
          </div>
          <div class="mon-stat">
            <span class="mon-stat-label">All-time return</span>
            <span class="mon-stat-value ${(s.all_time_return_pct || 0) >= 0 ? "is-pos" : "is-neg"}">${fmtPct(s.all_time_return_pct)}</span>
          </div>
          <div class="mon-stat">
            <span class="mon-stat-label">Win rate</span>
            <span class="mon-stat-value">${(s.win_rate_pct ?? "—")}%</span>
          </div>
          <div class="mon-stat">
            <span class="mon-stat-label">Trades total</span>
            <span class="mon-stat-value">${fmtInt(s.n_trades_total)}</span>
          </div>
        </div>
      </div>
    `;
  }

  // Connections
  const connEl = document.getElementById("monitor-connections");
  if (connEl) {
    const conns = [
      { name: "MEXC",    state: s.mexc_connection },
      { name: "Binance", state: s.binance_connection },
    ];
    connEl.innerHTML = conns.map(c => {
      const ok = /connect|stream|polling|online/i.test(c.state || "");
      const cls = ok ? (c.state === "connected" ? "is-pos" : "is-warn") : "is-neg";
      return `
        <div class="mon-row">
          <span class="mon-row-label"><span class="mon-dot ${cls}"></span>${c.name}</span>
          <span class="mon-row-value ${cls}">${(c.state || "unknown").toUpperCase()}</span>
        </div>
      `;
    }).join("") + `
      <div class="mon-row">
        <span class="mon-row-label muted">Last announcement seen</span>
        <span class="mon-row-value mon-mono">${s.last_announcement_seen_at || "—"}</span>
      </div>
    `;
  }

  // Latency
  const latEl = document.getElementById("monitor-latency");
  if (latEl) {
    const cells = [
      { label: "Median", value: s.median_detection_latency_ms, color: "is-pos" },
      { label: "p95",    value: s.p95_detection_latency_ms,    color: "is-warn" },
      { label: "Max",    value: s.max_detection_latency_ms,    color: "is-neg" },
    ];
    latEl.innerHTML = `
      <div class="mon-lat-grid">
        ${cells.map(c => `
          <div class="mon-lat-cell">
            <span class="mon-lat-label">${c.label}</span>
            <span class="mon-lat-value ${c.color}">${c.value != null ? c.value + " ms" : "—"}</span>
          </div>
        `).join("")}
      </div>
    `;
  }

  // Open positions
  const posBody = document.querySelector("#monitor-positions tbody");
  const posCnt = document.getElementById("monitor-pos-count");
  const positions = s.open_positions || [];
  if (posCnt) posCnt.textContent = `${positions.length} open`;
  if (posBody) {
    if (!positions.length) {
      posBody.innerHTML = `<tr><td colspan="7" class="muted">No open positions. Bot is idle, waiting for the next announcement.</td></tr>`;
    } else {
      posBody.innerHTML = positions.map(p => `
        <tr>
          <td><strong>${p.symbol || "—"}</strong></td>
          <td>${p.venue || "—"}</td>
          <td class="num">${fmtTime(p.entry_time)}</td>
          <td class="num">${p.entry_price ?? "—"}</td>
          <td class="num is-pos">${p.tp_price ?? "—"}</td>
          <td class="num is-neg">${p.sl_price ?? "—"}</td>
          <td class="num mon-mono">${fmtTime(p.time_stop_at)}</td>
        </tr>
      `).join("");
    }
  }

  // By category
  const catEl = document.getElementById("monitor-by-cat");
  if (catEl) {
    const byCat = s.by_category || {};
    const rows = Object.entries(byCat);
    if (!rows.length) {
      catEl.innerHTML = `<p class="muted">No data.</p>`;
    } else {
      catEl.innerHTML = rows.map(([k, v]) => `
        <div class="mon-row">
          <span class="mon-row-label">${k.replace(/_/g, " ")}</span>
          <span class="mon-row-value">
            <span class="muted" style="margin-right:10px">${v.n}× · WR ${(v.win_rate * 100).toFixed(1)}%</span>
            <span class="${v.total_pnl >= 0 ? "is-pos" : "is-neg"}">${fmtUsdSigned(v.total_pnl)}</span>
          </span>
        </div>
      `).join("");
    }
  }

  // By exit reason
  const exitEl = document.getElementById("monitor-by-exit");
  if (exitEl) {
    const byExit = s.by_exit_reason || {};
    const rows = Object.entries(byExit);
    if (!rows.length) {
      exitEl.innerHTML = `<p class="muted">No data.</p>`;
    } else {
      exitEl.innerHTML = rows.map(([k, v]) => {
        const mean = (v.mean_return * 100);
        return `
          <div class="mon-row">
            <span class="mon-row-label">${k.replace(/_/g, " ")}</span>
            <span class="mon-row-value">
              <span class="muted" style="margin-right:10px">${v.n}×</span>
              <span class="${mean >= 0 ? "is-pos" : "is-neg"}">${fmtPct(mean)}</span>
            </span>
          </div>
        `;
      }).join("");
    }
  }
}
