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
  system: loadSystem,
};

function activatePage(route) {
  document.querySelectorAll(".page").forEach((p) => {
    p.classList.toggle("active", p.id === `page-${route}`);
  });
  document.querySelectorAll("#nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.route === route);
  });
  const loader = pageLoaders[route];
  if (loader) loader();
}

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

/* ----- Status bar --------------------------------------- */
async function loadStatusBar() {
  const state = await getJson("/bot/state");
  if (!state) return;

  const botStatus = document.getElementById("bot-status");
  const botDot = document.getElementById("bot-dot");
  botStatus.textContent = state.status || "stopped";
  botDot.className = "dot " + (state.status === "backtest" ? "dot-amber" : "dot-gray");

  document.getElementById("all-time-return").textContent = fmtPct(state.all_time_return_pct);
  document.getElementById("all-time-return").className = "value " + colorOf(state.all_time_return_pct);
  document.getElementById("total-trades").textContent = state.n_trades_total || "—";

  document.getElementById("sharpe-val").textContent =
    state.sharpe_per_trade != null ? state.sharpe_per_trade.toFixed(3) : "—";

  document.getElementById("git-head").textContent = shortHash(state.git_head);
  document.getElementById("manifest-time").textContent = state.manifest_generated_at
    ? `manifest: ${new Date(state.manifest_generated_at).toISOString().slice(0, 10)}`
    : "manifest: —";
}

/* =========================================================
   PAGE: DASHBOARD
   ========================================================= */
async function loadDashboard() {
  const [state, equity, oos, anns] = await Promise.all([
    getJson("/bot/state"),
    getJson("/equity"),
    getJson("/oos"),
    getJson("/announcements/recent"),
  ]);

  const s = state || {};

  // KPI cards
  const wrap = document.getElementById("overview-kpis");
  wrap.innerHTML = "";
  wrap.appendChild(kpiCard("Portfolio", fmtUsd(s.portfolio_value_usdt), `start ${fmtUsd(s.starting_capital_usdt)}`));
  wrap.appendChild(kpiCard("Total Return", fmtPct(s.all_time_return_pct), `${s.n_trades_total ?? 0} trades`, colorOf(s.all_time_return_pct)));
  wrap.appendChild(kpiCard("Win Rate", `${(s.win_rate_pct ?? 0).toFixed(1)}%`, "wins / total"));
  wrap.appendChild(kpiCard("Profit Factor", (s.profit_factor ?? 0).toFixed(2), "gross W / gross L"));
  wrap.appendChild(kpiCard("Sharpe / Trade", (s.sharpe_per_trade ?? 0).toFixed(3), "mean / std"));
  wrap.appendChild(kpiCard("Max Drawdown", `${(s.max_drawdown_pct ?? 0).toFixed(2)}%`, "peak-to-trough", "neg"));

  // Equity curve
  renderEquityCurve(equity || []);

  // Exit breakdown
  renderExitBreakdown(s.by_exit_reason || {});

  // Announcement feed
  renderDashboardAnnouncements(anns || []);

  // OOS summary
  renderOosSummary(oos);

  // Category breakdown
  renderCategoryBreakdown(s.by_category || {});
}

function renderEquityCurve(points) {
  const ctx = document.getElementById("equityChart");
  if (!ctx) return;
  if (ctx.chart) ctx.chart.destroy();
  if (!points.length) return;

  ctx.chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: points.map((p) => p.date || p.timestamp || ""),
      datasets: [{
        label: "Equity",
        data: points.map((p) => p.equity),
        borderColor: "#3E63DD",
        backgroundColor: "rgba(62, 99, 221, 0.10)",
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.25,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => `Equity: $${Math.round(c.parsed.y).toLocaleString()}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: "#262C3A" },
          ticks: { color: "#5A6178", font: { size: 10 }, maxTicksLimit: 8 },
        },
        y: {
          grid: { color: "#262C3A" },
          ticks: {
            color: "#5A6178",
            font: { size: 11 },
            callback: (v) => `$${(v / 1000).toFixed(1)}k`,
          },
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

function renderDashboardAnnouncements(anns) {
  const tbody = document.querySelector("#dash-ann-table tbody");
  const hint = document.getElementById("dash-ann-count");
  if (!anns.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="muted">No announcements.</td></tr>`;
    return;
  }

  const buys = anns.filter(a => a.decision === "BUY").length;
  const skips = anns.filter(a => a.decision === "SKIP").length;
  if (hint) hint.textContent = `${buys} traded · ${skips} skipped`;

  const decBadge = (d) => ({
    BUY: "badge-buy",
    SELL: "badge-sell",
    SKIP: "badge-skip",
    WATCH: "badge-info",
  })[d] || "badge-skip";

  tbody.innerHTML = anns.map((a) => `
    <tr>
      <td class="num">${fmtTime(a.time)}</td>
      <td><strong>${a.asset}</strong></td>
      <td class="muted" style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${a.title}">${a.title}</td>
      <td><span class="badge ${decBadge(a.decision)}">${a.decision}</span></td>
      <td class="muted">${a.reason}</td>
    </tr>`).join("");
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
async function loadTrades() {
  const bt = (await getJson("/backtest/m0")) || {};
  const trades = bt.trades || [];
  const s = bt.summary || {};

  const kpis = document.getElementById("trades-kpis");
  kpis.innerHTML = "";

  const wins = trades.filter((t) => (t.return_pct || 0) > 0).length;
  const losses = trades.length - wins;
  const totalPnl = trades.reduce((a, t) => a + (t.pnl || 0), 0);
  const best = trades.reduce((a, t) => Math.max(a, (t.return_pct || -1) * 100), -100);
  const worst = trades.reduce((a, t) => Math.min(a, (t.return_pct || 1) * 100), 100);

  kpis.appendChild(kpiCard("Total Trades", fmtInt(trades.length), `${wins}W / ${losses}L`));
  kpis.appendChild(kpiCard("Win Rate", `${s.win_rate?.toFixed(1) || "—"}%`, ""));
  kpis.appendChild(kpiCard("Total P&L", fmtUsdSigned(totalPnl), "net of fees", colorOf(totalPnl)));
  kpis.appendChild(kpiCard("Best Trade", fmtPct(best), "", "pos"));
  kpis.appendChild(kpiCard("Worst Trade", fmtPct(worst), "", "neg"));
  kpis.appendChild(kpiCard("Avg Duration", `${s.avg_duration_min?.toFixed(0) || "—"} min`, ""));

  document.getElementById("trades-count").textContent = `${trades.length} trades`;

  const tbody = document.querySelector("#trades-table tbody");
  if (!trades.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="muted">No trades.</td></tr>`;
    return;
  }

  const sorted = [...trades].sort((a, b) => (b.entry_time || "").localeCompare(a.entry_time || ""));
  tbody.innerHTML = sorted.map((t) => {
    const ret = (t.return_pct || 0) * 100;
    return `
    <tr>
      <td class="num">${fmtTime(t.entry_time)}</td>
      <td><strong>${t.symbol}</strong></td>
      <td>${categoryLabel(t.category)}</td>
      <td><span class="badge ${exitBadge(t.exit_reason)}">${exitLabel(t.exit_reason)}</span></td>
      <td class="num ${colorOf(ret)}">${fmtPct(ret)}</td>
      <td class="num ${colorOf(t.pnl)}">${fmtUsdSigned(t.pnl)}</td>
      <td class="num muted">${t.duration_min?.toFixed(0) || "—"}m</td>
      <td class="num">${fmtUsd(t.equity_after)}</td>
    </tr>`;
  }).join("");
}

/* =========================================================
   PAGE: SYSTEM
   ========================================================= */
async function loadSystem() {
  const state = (await getJson("/bot/state")) || {};

  document.getElementById("lat-p50").textContent =
    state.median_detection_latency_ms != null
      ? `${(state.median_detection_latency_ms / 1000).toFixed(2)} s`
      : "—";
  document.getElementById("lat-p95").textContent =
    state.p95_detection_latency_ms != null
      ? `${(state.p95_detection_latency_ms / 1000).toFixed(2)} s`
      : "—";
  document.getElementById("lat-max").textContent =
    state.max_detection_latency_ms != null
      ? `${(state.max_detection_latency_ms / 1000).toFixed(2)} s`
      : "—";
}

/* =========================================================
   LANDING / DASHBOARD toggle
   ========================================================= */
function enterDashboard() {
  document.getElementById("landing").style.display = "none";
  document.getElementById("dashboard").style.display = "grid";
  history.replaceState(null, "", "#overview");
  activatePage("overview");
  loadStatusBar();
}

function exitDashboard() {
  document.getElementById("dashboard").style.display = "none";
  document.getElementById("landing").style.display = "";
  history.replaceState(null, "", "/");
}

async function loadHeroStats() {
  const [state, oos] = await Promise.all([
    getJson("/bot/state"),
    getJson("/oos"),
  ]);
  if (oos?.summary) {
    const s = oos.summary;
    const wrEl = document.getElementById("hero-wr");
    if (wrEl && s.win_rate != null) wrEl.textContent = s.win_rate.toFixed(0) + "%";
    const pfEl = document.getElementById("hero-pf");
    if (pfEl && s.profit_factor != null) pfEl.textContent = s.profit_factor.toFixed(2);
  }
  if (state) {
    const trEl = document.getElementById("hero-trades");
    if (trEl && state.n_trades_total != null) trEl.textContent = state.n_trades_total;
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
  const hash = location.hash.slice(1);
  const isDashboardRoute = ["overview", "trades", "system"].includes(hash);

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
