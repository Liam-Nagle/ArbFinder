(() => {
  const REFRESH_INTERVAL = 30_000;
  const LS_API_KEY = "arbfinder_api_url";

  let allOpportunities = [];
  let refreshTimer = null;

  // ---------- API URL ----------
  function getApiBase() {
    return localStorage.getItem(LS_API_KEY) || "";
  }

  function saveApiBase(url) {
    localStorage.setItem(LS_API_KEY, url.trim().replace(/\/$/, ""));
  }

  // ---------- Fetch ----------
  async function fetchData() {
    const base = getApiBase();
    const url = `${base}/api/opportunities`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }

  // ---------- Render helpers ----------
  function categoryTag(cat) {
    return `<span class="category-tag ${cat}">${cat}</span>`;
  }

  function arbPct(pct) {
    const cls = pct < 2 ? "arb-pct low" : "arb-pct";
    return `<span class="${cls}">${pct.toFixed(2)}%</span>`;
  }

  function formatProfit(profit, currency = "£") {
    return `<span class="profit">${currency}${profit.toFixed(2)}</span>`;
  }

  function formatTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function legsHtml(legs) {
    return `<div class="legs">${legs.map(leg => `
      <div class="leg">
        <span class="leg-exchange">${escHtml(leg.exchange)}</span>
        <span class="leg-outcome">${escHtml(leg.outcome)}</span>
        <span class="leg-odds">@ ${leg.odds.toFixed(3)}</span>
        <span class="leg-stake">£${leg.stake.toFixed(2)}</span>
        <a href="${escHtml(leg.market_url)}" target="_blank" rel="noopener">↗</a>
      </div>`).join("")}
    </div>`;
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ---------- Filter ----------
  function applyFilters(opportunities) {
    const minArb = parseFloat(document.getElementById("filterMinArb").value) || 0;
    const category = document.getElementById("filterCategory").value;
    const exchange = document.getElementById("filterExchange").value;

    return opportunities.filter(opp => {
      if (opp.arb_percent < minArb) return false;
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
    // Stats bar
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
      badge.className = `badge ${info.status}`;
      badge.title = info.status === "ok"
        ? `${info.market_count} markets`
        : info.error || "error";
      badge.textContent = name;
      wrapper.appendChild(badge);
    }
    badgeContainer.appendChild(wrapper);

    const loading = document.getElementById("loadingState");
    const empty = document.getElementById("emptyState");
    const table = document.getElementById("arbTable");
    const body = document.getElementById("arbBody");

    loading.classList.add("hidden");

    const filtered = applyFilters(opportunities);

    if (filtered.length === 0) {
      empty.classList.remove("hidden");
      table.classList.add("hidden");
      return;
    }

    empty.classList.add("hidden");
    table.classList.remove("hidden");

    body.innerHTML = filtered.map(opp => `
      <tr>
        <td><div class="market-title" title="${escHtml(opp.title)}">${escHtml(opp.title)}</div></td>
        <td>${categoryTag(opp.category)}</td>
        <td>${arbPct(opp.arb_percent)}</td>
        <td>${formatProfit(opp.guaranteed_profit)} <small style="color:var(--text-muted)">/ £${opp.total_stake.toFixed(0)} stake</small></td>
        <td>${legsHtml(opp.legs)}</td>
        <td class="found-at">${formatTime(opp.found_at)}</td>
      </tr>
    `).join("");
  }

  // ---------- Load ----------
  async function load() {
    document.getElementById("loadingState").classList.remove("hidden");
    document.getElementById("emptyState").classList.add("hidden");
    document.getElementById("arbTable").classList.add("hidden");

    try {
      const data = await fetchData();
      allOpportunities = data.opportunities || [];
      populateExchangeFilter(allOpportunities);
      render(allOpportunities, data.status);
    } catch (err) {
      document.getElementById("loadingState").classList.add("hidden");
      document.getElementById("emptyState").classList.remove("hidden");
      document.getElementById("emptyState").querySelector("p:first-of-type").textContent =
        `Error: ${err.message}. Check the API URL in settings.`;
    }

    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(load, REFRESH_INTERVAL);
  }

  // ---------- Settings panel ----------
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
      if (allOpportunities.length) render(allOpportunities, null);
    });
  });

  // ---------- Refresh button ----------
  document.getElementById("refreshBtn").addEventListener("click", () => {
    clearTimeout(refreshTimer);
    load();
  });

  // ---------- Boot ----------
  load();
})();
