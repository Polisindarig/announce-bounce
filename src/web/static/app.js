/* =========================================================
   Announce & Bounce — Dashboard (real backtest data)
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
  const sign = n > 0 ? "+" : n < 0 ? "" : "";
  return sign + fmtUsd(n, dp);
};

const fmtInt = (v) =>
  v == null ? "—" : Number(v).toLocaleString("en-US");

const fmtTime = (iso) => {
  if (!iso) return "—";
  const s = String(iso);
  return s.replace("T", " ").slice(0, 16);
};

const shortHash = (h) => (h ? String(h).slice(0, 8) : "—");
const colorOf = (v) => (v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "");

/* ----- Human-readable labels ---------------------------- */
const categoryLabel = (c) => ({
  LISTING_SPOT: "Spot Listing",
  LISTING_FUTURES: "Futures Listing",
  LAUNCHPOOL_LAUNCHPAD: "Launchpool",
  STAKING_EARN: "Staking / Earn",
  HODLER_AIRDROP: "HODLer Airdrop",
  AIRDROP: "Airdrop",
  DELISTING: "Delisting",
  MAINTENANCE_SUSPENSION: "Maintenance",
  SECURITY_INCIDENT: "Security",
  REGULATORY: "Regulatory",
  FORK_UPGRADE: "Fork / Upgrade",
  PARTNERSHIP_INTEGRATION: "Partnership",
  OTHER: "Other",
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
  overview: loadOverview,
  backtest: loadBacktest,
  research: loadResearch,
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

  const mexcDot = document.getElementById("mexc-dot");
  mexcDot.className = "dot dot-green";
  document.getElementById("mexc-status").textContent = "connected";

  document.getElementById("sharpe-val").textContent =
    state.sharpe_per_trade != null ? state.sharpe_per_trade.toFixed(3) : "—";

  document.getElementById("git-head").textContent = shortHash(state.git_head);
  document.getElementById("manifest-time").textContent = state.manifest_generated_at
    ? `manifest: ${new Date(state.manifest_generated_at).toISOString().slice(0, 10)}`
    : "manifest: —";
}

/* =========================================================
   PAGE: OVERVIEW
   ========================================================= */
async function loadOverview() {
  const state = (await getJson("/bot/state")) || {};
  const equity = (await getJson("/equity")) || [];

  // KPI cards
  const wrap = document.getElementById("overview-kpis");
  wrap.innerHTML = "";

  wrap.appendChild(kpiCard(
    "Final equity", fmtUsd(state.portfolio_value_usdt),
    `start ${fmtUsd(state.starting_capital_usdt)}`, ""
  ));
  wrap.appendChild(kpiCard(
    "Total return", fmtPct(state.all_time_return_pct),
    "backtest", colorOf(state.all_time_return_pct)
  ));
  wrap.appendChild(kpiCard(
    "Win rate", `${(state.win_rate_pct ?? 0).toFixed(1)}%`,
    `${state.n_trades_total ?? 0} trades`, ""
  ));
  wrap.appendChild(kpiCard(
    "Profit factor", (state.profit_factor ?? 0).toFixed(2),
    "gross wins / gross losses", ""
  ));
  wrap.appendChild(kpiCard(
    "Sharpe / trade", (state.sharpe_per_trade ?? 0).toFixed(3),
    "mean return / std", ""
  ));
  wrap.appendChild(kpiCard(
    "Max drawdown", `${(state.max_drawdown_pct ?? 0).toFixed(2)}%`,
    "peak-to-trough", "neg"
  ));

  // Equity curve
  renderEquityCurve(equity);

  // Category breakdown
  renderCategoryBreakdown(state.by_category || {});

  // Exit breakdown
  renderExitBreakdown(state.by_exit_reason || {});

  // OOS summary
  const oos = await getJson("/oos");
  renderOosSummary(oos);
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
          &nbsp;·&nbsp;${(d.win_rate * 100).toFixed(0)}% win
          &nbsp;·&nbsp;<span class="${colorOf(d.total_pnl)}">${fmtUsdSigned(d.total_pnl)}</span>
        </span>
      </div>`)
    .join("");
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

/* =========================================================
   PAGE: BACKTEST
   ========================================================= */
async function loadBacktest() {
  const [bt, oos, rob] = await Promise.all([
    getJson("/backtest/m0"),
    getJson("/oos"),
    getJson("/latency/scenarios"),
  ]);

  // KPIs — M0 vs OOS comparison
  const kpis = document.getElementById("bt-kpis");
  kpis.innerHTML = "";
  const s = bt?.summary || {};
  const os = oos?.summary || {};

  kpis.appendChild(kpiCard("IS trades", fmtInt(s.n_trades), "full sample", ""));
  kpis.appendChild(kpiCard("IS return", fmtPct(s.total_return_pct), "in-sample", colorOf(s.total_return_pct)));
  kpis.appendChild(kpiCard("IS Sharpe", (s.sharpe_per_trade || 0).toFixed(3), "per trade", ""));
  kpis.appendChild(kpiCard("OOS trades", fmtInt(os.n_trades), oos?.window?.oos_start + " →", ""));
  kpis.appendChild(kpiCard("OOS return", fmtPct(os.total_return_pct), "out-of-sample", colorOf(os.total_return_pct)));
  kpis.appendChild(kpiCard("OOS PF", (os.profit_factor || 0).toFixed(2), "profit factor", ""));

  // Robustness table
  const scenarios = rob?.scenarios || [];
  const tbody = document.querySelector("#robustness-table tbody");
  if (!scenarios.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No robustness data.</td></tr>`;
  } else {
    document.getElementById("rob-note").textContent = rob.note ? rob.note.slice(0, 80) : "latency stress tests";
    tbody.innerHTML = scenarios.map((sc) => `
      <tr>
        <td>${sc.latency_seconds}s</td>
        <td class="num">${sc.n_trades}</td>
        <td class="num ${colorOf(sc.total_return_pct)}">${fmtPct(sc.total_return_pct)}</td>
        <td class="num">${sc.win_rate?.toFixed(1) || "—"}%</td>
        <td class="num">${sc.profit_factor?.toFixed(2) || "—"}</td>
        <td class="num">${sc.sharpe_per_trade?.toFixed(3) || "—"}</td>
        <td class="num">${sc.max_drawdown_pct?.toFixed(2) || "—"}%</td>
      </tr>`).join("");
  }

  // Fee sensitivity table
  const feeScenarios = rob?.fee_scenarios || [];
  const feeTbody = document.querySelector("#fee-table tbody");
  if (!feeScenarios.length) {
    feeTbody.innerHTML = `<tr><td colspan="5" class="muted">No fee data.</td></tr>`;
  } else {
    feeTbody.innerHTML = feeScenarios.map((sc) => `
      <tr>
        <td>${sc.fee_per_leg_pct?.toFixed(2) || "—"}%</td>
        <td class="num">${sc.n_trades}</td>
        <td class="num ${colorOf(sc.total_return_pct)}">${fmtPct(sc.total_return_pct)}</td>
        <td class="num">${sc.win_rate?.toFixed(1) || "—"}%</td>
        <td class="num">${sc.profit_factor?.toFixed(2) || "—"}</td>
      </tr>`).join("");
  }

  // Slippage sensitivity table
  const slipScenarios = rob?.slippage_scenarios || [];
  const slipTbody = document.querySelector("#slippage-table tbody");
  if (!slipScenarios.length) {
    slipTbody.innerHTML = `<tr><td colspan="5" class="muted">No slippage data.</td></tr>`;
  } else {
    slipTbody.innerHTML = slipScenarios.map((sc) => `
      <tr>
        <td>${sc.slippage_bps} bps</td>
        <td class="num">${sc.n_trades}</td>
        <td class="num ${colorOf(sc.total_return_pct)}">${fmtPct(sc.total_return_pct)}</td>
        <td class="num">${sc.win_rate?.toFixed(1) || "—"}%</td>
        <td class="num">${sc.profit_factor?.toFixed(2) || "—"}</td>
      </tr>`).join("");
  }

  // OOS trades
  const oosTradesEl = document.querySelector("#oos-trades-table tbody");
  const oosTrades = oos?.trades || [];
  document.getElementById("oos-trades-hint").textContent = `${oosTrades.length} trades`;
  if (!oosTrades.length) {
    oosTradesEl.innerHTML = `<tr><td colspan="7" class="muted">No OOS trades.</td></tr>`;
  } else {
    oosTradesEl.innerHTML = oosTrades.map((t) => {
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
      </tr>`;
    }).join("");
  }
}

/* =========================================================
   PAGE: RESEARCH
   ========================================================= */
async function loadResearch() {
  const [sentiment, eventStudy, listingSpot] = await Promise.all([
    getJson("/sentiment"),
    getJson("/event-study"),
    getJson("/event-study/listing-spot"),
  ]);

  // Sentiment stats
  const sentWrap = document.getElementById("sentiment-stats");
  if (!sentiment || !sentiment.categories) {
    sentWrap.innerHTML = `<div class="muted-block">No sentiment data.</div>`;
  } else {
    const cats = sentiment.categories;
    const total = sentiment.total_announcements || 0;
    sentWrap.innerHTML = `
      <div class="stat-row"><span class="k">Total analyzed</span><span class="v">${fmtInt(total)}</span></div>
      <div class="stat-row"><span class="k">Primary model</span><span class="v">CryptoBERT (ElKulako)</span></div>
      <div class="stat-row"><span class="k">Secondary model</span><span class="v">FinBERT (ProsusAI)</span></div>
      <div class="stat-row"><span class="k">M0 vs M1 finding</span><span class="v muted">M0 = M1 (sentiment adds no value for Tier 1)</span></div>
    `;

    // Sentiment chart
    renderSentimentChart(cats);
  }

  // TP/SL calibration — show frozen params from decision engine
  const calWrap = document.getElementById("calibration-stats");
  const cal = eventStudy?.tp_sl_calibration;
  if (!cal) {
    calWrap.innerHTML = `<div class="muted-block">No calibration data.</div>`;
  } else {
    // Show which categories have calibration data and their horizon stats
    const rows = Object.entries(cal).map(([cat, horizons]) => {
      const hKeys = Object.keys(horizons).slice(0, 3);
      const detail = hKeys.map(h => {
        const d = horizons[h];
        return `${h}: ${d.n || "—"} events`;
      }).join(", ");
      return `
      <div class="stat-row">
        <span class="k"><strong>${categoryLabel(cat)}</strong></span>
        <span class="v muted">${detail}</span>
      </div>`;
    }).join("");
    calWrap.innerHTML = `
      ${rows}
      <div class="stat-row" style="margin-top:8px;border-top:1px solid #262C3A;padding-top:8px">
        <span class="k">Method</span>
        <span class="v muted">p70 MFE (TP) / p30 MAE (SL), clamped</span>
      </div>`;
  }

  // LISTING_SPOT MEXC
  const lsWrap = document.getElementById("listing-spot-stats");
  if (!listingSpot || !Object.keys(listingSpot).length) {
    lsWrap.innerHTML = `<div class="muted-block">No LISTING_SPOT event study data.</div>`;
  } else {
    const mp = listingSpot.manual_verified_pump || {};
    const nManual = listingSpot.n_manual_events || mp.n || "—";
    const nKline = listingSpot.n_kline_events || "—";
    lsWrap.innerHTML = `
      <div class="stat-row"><span class="k">Verified pumps (manual)</span><span class="v">${nManual}</span></div>
      <div class="stat-row"><span class="k">MEXC kline-matched</span><span class="v">${nKline}</span></div>
      <div class="stat-row"><span class="k">Mean pump</span><span class="v pos">${mp.mean != null ? (mp.mean * 100).toFixed(1) + "%" : "—"}</span></div>
      <div class="stat-row"><span class="k">Median pump</span><span class="v pos">${mp.median != null ? (mp.median * 100).toFixed(1) + "%" : "—"}</span></div>
      <div class="stat-row"><span class="k">Execution venue</span><span class="v">MEXC (pre-listed)</span></div>
      <div class="stat-row"><span class="k">Rationale</span><span class="v muted">${listingSpot.rationale || "Coin not yet on Binance at announcement"}</span></div>
    `;
  }
}

function renderSentimentChart(cats) {
  const ctx = document.getElementById("sentimentChart");
  if (!ctx) return;
  if (ctx.chart) ctx.chart.destroy();

  const labels = [];
  const bullish = [];
  const neutral = [];
  const bearish = [];

  for (const [cat, d] of Object.entries(cats)) {
    if (!d.cryptobert) continue;
    labels.push(categoryLabel(cat));
    bullish.push(d.cryptobert.bullish_pct || 0);
    neutral.push(d.cryptobert.neutral_pct || 0);
    bearish.push(d.cryptobert.bearish_pct || 0);
  }

  ctx.chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Bullish %", data: bullish, backgroundColor: "#30A46C" },
        { label: "Neutral %", data: neutral, backgroundColor: "#5A6178" },
        { label: "Bearish %", data: bearish, backgroundColor: "#E5484D" },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#A1A7B5" } },
      },
      scales: {
        x: {
          stacked: true,
          grid: { color: "#262C3A" },
          ticks: { color: "#5A6178", font: { size: 10 }, maxRotation: 45 },
        },
        y: {
          stacked: true,
          grid: { color: "#262C3A" },
          ticks: { color: "#5A6178", callback: (v) => v + "%" },
          max: 100,
        },
      },
    },
  });
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

  kpis.appendChild(kpiCard("Total trades", fmtInt(trades.length), "backtest"));
  kpis.appendChild(kpiCard("Win rate", `${s.win_rate?.toFixed(1) || "—"}%`, `${wins}W / ${losses}L`));
  kpis.appendChild(kpiCard("Total P&L", fmtUsdSigned(totalPnl), "net of fees", colorOf(totalPnl)));
  kpis.appendChild(kpiCard("Best trade", fmtPct(best), "single trade peak", "pos"));
  kpis.appendChild(kpiCard("Worst trade", fmtPct(worst), "single trade trough", "neg"));
  kpis.appendChild(kpiCard("Avg duration", `${s.avg_duration_min?.toFixed(0) || "—"} min`, "per trade"));

  document.getElementById("trades-count").textContent = `${trades.length} trades`;

  const tbody = document.querySelector("#trades-table tbody");
  if (!trades.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="muted">No trades.</td></tr>`;
    return;
  }

  // Sort newest first
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

/* ----- Mobile menu -------------------------------------- */
function initMenu() {
  const btn = document.getElementById("menu-btn");
  const sidebar = document.getElementById("sidebar");
  if (!btn || !sidebar) return;
  btn.addEventListener("click", () => sidebar.classList.toggle("open"));
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

/* ----- Landing mobile menu ----- */
function initLandingMenu() {
  const btn = document.getElementById("landing-menu-btn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const links = document.querySelector(".nav-links");
    if (links) links.classList.toggle("mobile-open");
  });
}

/* ----- Boot --------------------------------------------- */
async function boot() {
  const hash = location.hash.slice(1);
  const isDashboardRoute = ["overview", "backtest", "research", "trades", "system", "settings"].includes(hash);

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
    initLandingMenu();
  }
}

document.addEventListener("DOMContentLoaded", boot);
