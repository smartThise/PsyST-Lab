// PI-Release dashboard frontend
const $ = (id) => document.getElementById(id);
const fmt = (x, d = 3) => (x === null || x === undefined || isNaN(x)) ? "—" : Number(x).toFixed(d);
const pct = (x) => (x === null || x === undefined || isNaN(x)) ? "—" : (Number(x) * 100).toFixed(1) + "%";

let charts = {};

async function fetchJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

function groupColor(id) {
  if (id.startsWith("G0")) return "#8b949e";
  if (id.startsWith("G2")) return "#38bdf8";
  if (id.startsWith("G4") || id.startsWith("G5")) return "#f87171";
  if (id.startsWith("G6")) return "#a78bfa";
  if (id.startsWith("S")) return "#2dd4bf";
  return "#4ade80";
}

function reColor(re) {
  if (re === null || re === undefined || isNaN(re)) return "var(--muted)";
  if (re >= 0.5) return "var(--green)";
  if (re >= 0.2) return "var(--amber)";
  return "var(--red)";
}

function tagClass(id) {
  if (id.startsWith("S")) return "tag tag-g";
  if (id.startsWith("G0")) return "tag tag-n";
  if (id.startsWith("G2")) return "tag tag-g";
  if (id.startsWith("G4") || id.startsWith("G5")) return "tag tag-r";
  return "tag tag-a";
}

// ---------- run list ----------
async function loadRuns(selectTag) {
  const runs = await fetchJSON("/api/runs");
  const sel = $("run-select");
  sel.innerHTML = "";
  if (!runs.length) {
    $("empty").classList.remove("hidden");
    $("content").classList.add("hidden");
    return;
  }
  $("empty").classList.add("hidden");
  $("content").classList.remove("hidden");
  for (const r of runs) {
    const opt = document.createElement("option");
    opt.value = r.tag;
    opt.textContent = `${r.tag}  ·  ${r.model}  ·  ${(r.baseline_acc * 100).toFixed(1)}% baseline  ·  ${r.n_groups} groups`;
    sel.appendChild(opt);
  }
  if (selectTag && runs.find(r => r.tag === selectTag)) {
    sel.value = selectTag;
  }
  sel.onchange = () => loadRun(sel.value);
  if (sel.value) loadRun(sel.value);
}

// ---------- single run ----------
async function loadRun(tag) {
  if (!tag) return;
  const [summary, records] = await Promise.all([
    fetchJSON(`/api/run/${tag}`),
    fetchJSON(`/api/run/${tag}/results`),
  ]);
  renderMeta(summary, records);
  renderKPIs(summary);
  renderCharts(summary);
  renderDetailTable(summary);
  renderRecordsTable(records);
}

function renderMeta(s, records) {
  const pi = s.pi_test || {};
  const ev = s.eval || {};
  $("meta-model").textContent  = `model: ${s.model}`;
  $("meta-pi").textContent     = `PI: ${pi.n_keys} keys × ${pi.updates_per_key} updates`;
  $("meta-eval").textContent   = `eval: k=${ev.k_repeats}, ${pi.n_trials} trials`;
  $("meta-calls").textContent  = `${records.length} records`;
}

function renderKPIs(s) {
  const groups = s.groups || [];
  const baseline = s.baseline_acc ?? 0;
  const withRE = groups.filter(g => g.id !== "G0");
  const best = withRE.reduce((a, b) => ((b.re || 0) > (a?.re || 0) ? b : a), null);

  $("kpi-baseline").textContent = pct(baseline);
  $("kpi-best-re").textContent = best ? fmt(best.re) : "—";
  $("kpi-best-group").textContent = best ? best.id : "—";

  const cps = groups.filter(g => g.cp !== null && g.cp !== undefined).map(g => g.cp);
  const meanCP = cps.length ? cps.reduce((a, b) => a + b, 0) / cps.length : null;
  $("kpi-cp").textContent = meanCP !== null ? pct(meanCP) : "—";
}

function destroyCharts() {
  Object.values(charts).forEach(c => c?.destroy());
  charts = {};
}

function renderCharts(s) {
  destroyCharts();
  const groups = (s.groups || []).slice();
  const labels = groups.map(g => g.id);
  const baseTooltip = {
    backgroundColor: "#0b0f17",
    borderColor: "#232c3b",
    borderWidth: 1,
    titleColor: "#e6edf3",
    bodyColor: "#e6edf3",
  };

  // ---- main: accuracy + RE ----
  const ctx1 = $("chart-main").getContext("2d");
  charts.main = new Chart(ctx1, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Accuracy",
          data: groups.map(g => g.accuracy ?? 0),
          backgroundColor: groups.map(g => groupColor(g.id) + "55"),
          borderColor: groups.map(g => groupColor(g.id)),
          borderWidth: 1.5,
          borderRadius: 4,
        },
        {
          label: "Release Efficiency (RE)",
          data: groups.map(g => g.re ?? 0),
          backgroundColor: groups.map(g => groupColor(g.id)),
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: "#e6edf3" } }, tooltip: baseTooltip },
      scales: {
        x: { ticks: { color: "#8b949e" }, grid: { color: "#232c3b33" } },
        y: { beginAtZero: true, max: 1, ticks: { color: "#8b949e", callback: v => (v * 100) + "%" }, grid: { color: "#232c3b33" } },
      },
    },
  });

  // ---- cp + robustness ----
  const ctx2 = $("chart-cp").getContext("2d");
  charts.cp = new Chart(ctx2, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Context Preservation (CP)",
          data: groups.map(g => g.cp ?? 0),
          backgroundColor: groups.map(g => (g.cp === null || g.cp === undefined) ? "#232c3b" : (g.cp > 0.5 ? "#4ade80" : "#f87171")),
          borderRadius: 4,
        },
        {
          label: "Robustness Δ (lower = more fragile)",
          data: groups.map(g => g.robustness_delta ?? 0),
          backgroundColor: "#fbbf24",
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: "#e6edf3" } }, tooltip: baseTooltip },
      scales: {
        x: { ticks: { color: "#8b949e" }, grid: { color: "#232c3b33" } },
        y: { beginAtZero: true, max: 1, ticks: { color: "#8b949e", callback: v => (v * 100) + "%" }, grid: { color: "#232c3b33" } },
      },
    },
  });
}

function renderDetailTable(s) {
  const tbody = $("detail-table").querySelector("tbody");
  tbody.innerHTML = "";
  for (const g of (s.groups || [])) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="${tagClass(g.id)}">${g.id}</span></td>
      <td>${g.name}</td>
      <td class="num">${pct(g.accuracy)}</td>
      <td class="num" style="color:${reColor(g.re)}">${fmt(g.re)}</td>
      <td class="num" style="color:${(g.cp ?? 0) > 0.5 ? "var(--green)" : "var(--red)"}">${pct(g.cp)}</td>
      <td class="num">${fmt(g.robustness_delta)}</td>
      <td class="num">${g.n_calls ?? "—"}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderRecordsTable(records) {
  $("records-count").textContent = `${records.length} rows`;
  const tbody = $("records-table").querySelector("tbody");
  tbody.innerHTML = "";
  // show most recent first, cap to 200 for perf
  const rows = records.slice(-200).reverse();
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="${tagClass(r.group)}">${r.group}</span></td>
      <td class="num">${r.trial_seed ?? "—"}</td>
      <td class="num">${pct(r.accuracy)}</td>
      <td class="num">${r.cp === undefined ? "—" : pct(r.cp)}</td>
      <td class="num">${r.robustness_delta === undefined ? "—" : fmt(r.robustness_delta)}</td>
      <td class="num">${r.n_calls ?? "—"}</td>
    `;
    tbody.appendChild(tr);
  }
}

// ---------- boot ----------
$("refresh").onclick = () => {
  const cur = $("run-select").value;
  loadRuns(cur);
};
loadRuns();
