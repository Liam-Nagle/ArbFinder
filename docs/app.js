(() => {
  const REFRESH_INTERVAL = 30_000;
  const LS_API_KEY = "arbfinder_api_url";

  let allOpportunities = [];
  let lastStatus = null;
  let refreshTimer = null;

  // Persists manual odds edits across auto-refreshes: Map<oppId, number[]>
  const oddsOverrides = new Map();

  // ---------- API URL ----------
  function getApiBase() {
    return localStorage.getItem(LS_API_KEY) || "";
  }
  function saveApiBase(url) {
    localStorage.setItem(LS_API_KEY, url.trim().replace(/\/$/, ""));
  }

  // ---------- Fetch ----------
  async function fetchData() {
    const resp = await fetch(`${getApiBase()}/api/opportunities`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }

  // ---------- Arb math ----------
  function recalculate(odds, bankroll) {
    const impliedSum = odds.reduce((s, o) => s + 1 / o, 0);
    const arbPct = (1 - impliedSum) * 100;
    const guaranteedReturn = bankroll / impliedSum;
    const profit = guaranteedReturn - bankroll;
    const stakes = odds.map(o => bankroll * (1 / o) / impliedSum);
    return { arbPct, profit, guaranteedReturn, stakes };
  }

  // ---------- Render helpers ----------
  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function categoryTag(cat) {
    return `<span class="category-tag ${cat}">${cat}</span>`;
  }

  function renderArbPct(pct) {
    if (pct < 0) return `<span class="arb-pct negative">${pct.toFixed(2)}%</span>`;
    const cls = pct < 2 ? "arb-pct low" : "arb-pct";
    return `<span class="${cls}">${pct.toFixed(2)}%</span>`;
  }

  function renderProfit(profit, totalStake) {
    if (profit < 0) {
      return `<span class="profit negative">-£${Math.abs(profit).toFixed(2)}</span>
              <small class="no-arb-hint">No arb at these odds</small>`;
    }
    return `<span class="profit">£${profit.toFixed(2)}</span>
            <small style="color:var(--text-muted)">/ £${totalStake.toFixed(0)} stake</small>`;
  }

  function formatTime(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function legsHtml(opp, displayOdds, displayStakes) {
    const isEdited = oddsOverrides.has(opp.id);
    const legs = opp.legs.map((leg, i) => `
      <div class="leg">
        <span class="leg-exchange">${escHtml(leg.exchange)}</span>
        <span class="leg-outcome">${escHtml(leg.outcome)}</span>
        <input class="leg-odds-input"
               type="number" step="0.001" min="1.001"
               value="${displayOdds[i].toFixed(3)}"
               data-original="${leg.odds}"
               data-leg-idx="${i}"
               title="Edit odds">
        <span class="leg-stake">£${displayStakes[i].toFixed(2)}</span>
        <a href="${escHtml(leg.market_url)}" target="_blank" rel="noopener">↗</a>
      </div>`).join("");

    const resetBtn = isEdited
      ? `<button class="reset-odds-btn" title="Restore fetched odds">↺ Reset</button>`
      : "";

    return `<div class="legs">${legs}${resetBtn}</div>`;
  }

  // ---------- Per-row recalculation ----------
  function recalcRow(row, opp) {
    const inputs = [...row.querySelectorAll(".leg-odds-input")];
    const odds = inputs.map((inp, i) => {
      const v = parseFloat(inp.value);
      return (v > 1) ? v : opp.legs[i].odds;
    });

    const { arbPct, profit, stakes } = recalculate(odds, opp.total_stake);

    row.querySelector(".arb-cell").innerHTML = renderArbPct(arbPct);
    row.querySelector(".profit-cell").innerHTML = renderProfit(profit, opp.total_stake);

    row.querySelectorAll(".leg-stake").forEach((el, i) => {
      el.textContent = `£${stakes[i].toFixed(2)}`;
    });

    const isEdited = odds.some((o, i) => Math.abs(o - opp.legs[i].odds) > 0.0001);
    row.classList.toggle("edited", isEdited);

    const existingReset = row.querySelector(".reset-odds-btn");
    if (isEdited && !existingReset) {
      row.querySelector(".legs").insertAdjacentHTML(
        "beforeend",
        `<button class="reset-odds-btn" title="Restore fetched odds">↺ Reset</button>`
      );
    } else if (!isEdited && existingReset) {
      existingReset.remove();
    }
  }

  // ---------- Filter ----------
  function applyFilters(opportunities) {
    const minArb = parseFloat(document.getElementById("filterMinArb").value) || 0;
    const category = document.getElementById("filterCategory").value;
    const exchange = document.getElementById("filterExchange").value;

    return opportunities.filter(opp => {
      const effectiveArb = oddsOverrides.has(opp.id)
        ? recalculate(oddsOverrides.get(opp.id), opp.total_stake).arbPct
        : opp.arb_percent;
      if (effectiveArb < minArb) return false;
      if (category && opp.category !== category) return false;
      if (exchange && !opp.legs.some(l => l.exchange === exchange)) return false;
      return true;
    });
  }

  function populateExchangeFilter(opportunities) {
    const sel = document.getElementById("filterExchange");
    const current = sel.value;
    const exchanges = [...new Set(opportunities.flatMap(o => o.legs.map(l => l.exchange)))].sort();
    while (sel.options.length > 1) sel.remove(1);
    exchanges.forEach(ex => {
      const opt = document.createElement("option");
      opt.value = ex;
      opt.textContent = ex;
      sel.appendChild(opt);
    });
    if (exchanges.includes(current)) sel.value = current;
  }

  // ---------- Render ----------
  function render(opportunities, status) {
    // Stats
    document.getElementById("statCount").textContent = opportunities.length;
    const best = opportunities[0]?.arb_percent;
    document.getElementById("statBest").textContent = best != null ? `${best.toFixed(2)}%` : "—";
    document.getElementById("statUpdated").textContent = formatTime(status?.last_updated);

    // Exchange badges
    const badgeContainer = document.getElementById("exchangeStatuses");
    badgeContainer.innerHTML = "";
    const wrapper = document.createElement("div");
    wrapper.className = "exchange-badges";
    for (const [name, info] of Object.entries(status?.exchange_status || {})) {
      const badge = document.createElement("span");
      badge.className = `badge ${info.status === "ok" ? "ok" : "error"}`;
      badge.title = info.status === "ok"
        ? `${info.market_count} markets${info.cached ? " (cached)" : ""}`
        : info.error || "error";
      badge.textContent = name;
      wrapper.appendChild(badge);
    }
    badgeContainer.appendChild(wrapper);

    const loading = document.getElementById("loadingState");
    const empty   = document.getElementById("emptyState");
    const table   = document.getElementById("arbTable");
    const body    = document.getElementById("arbBody");

    loading.classList.add("hidden");

    const filtered = applyFilters(opportunities);

    if (filtered.length === 0) {
      empty.classList.remove("hidden");
      table.classList.add("hidden");
      return;
    }

    empty.classList.add("hidden");
    table.classList.remove("hidden");

    body.innerHTML = filtered.map(opp => {
      const overrideOdds = oddsOverrides.get(opp.id);
      let displayOdds, displayStakes, displayArbPct, displayProfit;

      if (overrideOdds) {
        const calc = recalculate(overrideOdds, opp.total_stake);
        displayOdds   = overrideOdds;
        displayStakes = calc.stakes;
        displayArbPct = calc.arbPct;
        displayProfit = calc.profit;
      } else {
        displayOdds   = opp.legs.map(l => l.odds);
        displayStakes = opp.legs.map(l => l.stake);
        displayArbPct = opp.arb_percent;
        displayProfit = opp.guaranteed_profit;
      }

      return `
        <tr data-opp-id="${opp.id}"${overrideOdds ? ' class="edited"' : ''}>
          <td><div class="market-title" title="${escHtml(opp.title)}">${escHtml(opp.title)}</div></td>
          <td>${categoryTag(opp.category)}</td>
          <td class="arb-cell">${renderArbPct(displayArbPct)}</td>
          <td class="profit-cell">${renderProfit(displayProfit, opp.total_stake)}</td>
          <td>${legsHtml(opp, displayOdds, displayStakes)}</td>
          <td class="found-at">${formatTime(opp.found_at)}</td>
        </tr>`;
    }).join("");
  }

  // ---------- Event delegation (table) ----------
  document.getElementById("arbBody").addEventListener("input", e => {
    if (!e.target.classList.contains("leg-odds-input")) return;
    const row = e.target.closest("tr");
    const opp = allOpportunities.find(o => o.id === row.dataset.oppId);
    if (!opp) return;

    const inputs = [...row.querySelectorAll(".leg-odds-input")];
    const odds = inputs.map((inp, i) => {
      const v = parseFloat(inp.value);
      return (v > 1) ? v : opp.legs[i].odds;
    });
    oddsOverrides.set(opp.id, odds);
    recalcRow(row, opp);
  });

  document.getElementById("arbBody").addEventListener("click", e => {
    if (!e.target.classList.contains("reset-odds-btn")) return;
    const row = e.target.closest("tr");
    const opp = allOpportunities.find(o => o.id === row.dataset.oppId);
    if (!opp) return;

    oddsOverrides.delete(opp.id);
    row.querySelectorAll(".leg-odds-input").forEach((inp, i) => {
      inp.value = opp.legs[i].odds.toFixed(3);
    });
    recalcRow(row, opp);
  });

  // ---------- Load ----------
  async function load() {
    document.getElementById("loadingState").classList.remove("hidden");
    document.getElementById("emptyState").classList.add("hidden");
    document.getElementById("arbTable").classList.add("hidden");

    try {
      const data = await fetchData();
      allOpportunities = data.opportunities || [];
      lastStatus = data.status;
      populateExchangeFilter(allOpportunities);
      render(allOpportunities, lastStatus);
    } catch (err) {
      document.getElementById("loadingState").classList.add("hidden");
      document.getElementById("emptyState").classList.remove("hidden");
      document.getElementById("emptyState").querySelector("p:first-of-type").textContent =
        `Error: ${err.message}. Check the API URL in settings.`;
    }

    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(load, REFRESH_INTERVAL);
  }

  // ---------- Settings ----------
  document.getElementById("settingsBtn").addEventListener("click", () => {
    const panel = document.getElementById("settingsPanel");
    panel.classList.toggle("hidden");
    if (!panel.classList.contains("hidden")) {
      document.getElementById("apiUrlInput").value = getApiBase();
    }
  });
  document.getElementById("saveSettings").addEventListener("click", () => {
    saveApiBase(document.getElementById("apiUrlInput").value);
    document.getElementById("settingsPanel").classList.add("hidden");
    load();
  });
  document.getElementById("closeSettings").addEventListener("click", () => {
    document.getElementById("settingsPanel").classList.add("hidden");
  });

  // ---------- Filter listeners ----------
  ["filterMinArb", "filterCategory", "filterExchange"].forEach(id => {
    document.getElementById(id).addEventListener("change", () => {
      if (allOpportunities.length) render(allOpportunities, lastStatus);
    });
  });

  document.getElementById("refreshBtn").addEventListener("click", () => {
    clearTimeout(refreshTimer);
    load();
  });

  // ---------- Boot ----------
  load();
})();
