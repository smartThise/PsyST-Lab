// PI 释放实验 · 仪表盘前端
const $ = (id) => document.getElementById(id);
const fmt = (x, d = 3) => (x === null || x === undefined || isNaN(x)) ? "—" : Number(x).toFixed(d);
const pct = (x) => (x === null || x === undefined || isNaN(x)) ? "—" : (Number(x) * 100).toFixed(1) + "%";

let charts = {};

async function fetchJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// 各组配色(浅底友好)
function groupColor(id) {
  if (id.startsWith("G0")) return "#8c959f";   // 基线:灰
  if (id.startsWith("G1")) return "#636c76";
  if (id.startsWith("G2")) return "#0969da";   // Mock-QA(论文赢家):蓝
  if (id.startsWith("G3")) return "#8250df";   // 句法断崖:紫
  if (id.startsWith("G4")) return "#cf222e";   // glitch:红(最大未知数)
  if (id.startsWith("G5")) return "#bf8700";   // unicode:琥珀
  if (id.startsWith("G6")) return "#1a7f37";   // 自生成:绿
  if (id.startsWith("G7")) return "#0550ae";
  if (id.startsWith("S"))  return "#0969da";   // 堆叠:蓝(强调)
  return "#57606a";
}

function reColor(re) {
  if (re === null || re === undefined || isNaN(re)) return "var(--muted)";
  if (re >= 0.5) return "var(--green)";
  if (re >= 0.2) return "var(--amber)";
  return "var(--red)";
}

function cpColor(cp) {
  if (cp === null || cp === undefined || isNaN(cp)) return "var(--muted)";
  return cp > 0.5 ? "var(--green)" : "var(--red)";
}

function tagClass(id) {
  if (id.startsWith("S"))  return "tag tag-g";
  if (id.startsWith("G0")) return "tag tag-n";
  if (id.startsWith("G2")) return "tag tag-g";
  if (id.startsWith("G4") || id.startsWith("G5")) return "tag tag-r";
  if (id.startsWith("G6")) return "tag tag-v";
  return "tag tag-a";
}

// ---------- 运行列表 ----------
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
    opt.textContent = `${r.tag} · ${r.model} · 基线 ${(r.baseline_acc * 100).toFixed(1)}% · ${r.n_groups} 组`;
    sel.appendChild(opt);
  }
  if (selectTag && runs.find(r => r.tag === selectTag)) sel.value = selectTag;
  sel.onchange = () => loadRun(sel.value);
  if (sel.value) loadRun(sel.value);
}

// ---------- 单次运行 ----------
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
  $("meta-model").textContent = `模型:${s.model}`;
  $("meta-pi").textContent    = `PI 设置:${pi.n_keys} key × ${pi.updates_per_key} 次更新`;
  $("meta-eval").textContent  = `评估:k=${ev.k_repeats} × ${pi.n_trials} 试次`;
  $("meta-calls").textContent = `${records.length} 条记录`;
}

function renderKPIs(s) {
  const groups = s.groups || [];
  const baseline = s.baseline_acc ?? 0;
  const withRE = groups.filter(g => g.id !== "G0");
  const best = withRE.reduce((a, b) => ((b.re || 0) > (a?.re || 0) ? b : a), null);

  $("kpi-baseline").textContent    = pct(baseline);
  $("kpi-best-re").textContent     = best ? fmt(best.re) : "—";
  $("kpi-best-group").textContent  = best ? best.id : "—";

  const cps = groups.filter(g => g.cp !== null && g.cp !== undefined).map(g => g.cp);
  const meanCP = cps.length ? cps.reduce((a, b) => a + b, 0) / cps.length : null;
  $("kpi-cp").textContent = meanCP !== null ? pct(meanCP) : "—";
}

function destroyCharts() {
  Object.values(charts).forEach(c => c?.destroy());
  charts = {};
}

// Chart.js 浅色主题公共配置
const LIGHT = {
  grid:    "rgba(31,35,40,0.08)",
  tick:    "#57606a",
  tooltip: {
    backgroundColor: "#ffffff",
    borderColor: "#d0d7de",
    borderWidth: 1,
    titleColor: "#1f2328",
    bodyColor: "#424a53",
    boxPadding: 4,
    cornerRadius: 6,
  },
};

function renderCharts(s) {
  destroyCharts();
  const groups = (s.groups || []).slice();
  const labels = groups.map(g => g.id);
  const scales = {
    x: { ticks: { color: LIGHT.tick, font: { size: 12 } }, grid: { display: false }, border: { color: "#d0d7de" } },
    y: {
      beginAtZero: true, max: 1,
      ticks: { color: LIGHT.tick, callback: v => (v * 100) + "%" },
      grid: { color: LIGHT.grid },
      border: { display: false },
    },
  };
  const legendCfg = { labels: { color: "#424a53", font: { size: 12 }, boxWidth: 12, boxHeight: 12 } };

  // ---- 主图:准确率 + 释放效率 ----
  const ctx1 = $("chart-main").getContext("2d");
  charts.main = new Chart(ctx1, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "准确率",
          data: groups.map(g => g.accuracy ?? 0),
          backgroundColor: groups.map(g => groupColor(g.id) + "22"),
          borderColor: groups.map(g => groupColor(g.id)),
          borderWidth: 1.5,
          borderRadius: 3,
        },
        {
          label: "释放效率 RE",
          data: groups.map(g => g.re ?? 0),
          backgroundColor: groups.map(g => groupColor(g.id)),
          borderRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: legendCfg, tooltip: LIGHT.tooltip },
      scales,
    },
  });

  // ---- 副图:CP + 鲁棒性 ----
  const ctx2 = $("chart-cp").getContext("2d");
  charts.cp = new Chart(ctx2, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "上下文保全率 CP",
          data: groups.map(g => g.cp ?? 0),
          backgroundColor: groups.map(g =>
            (g.cp === null || g.cp === undefined) ? "#eaeef2"
            : (g.cp > 0.5 ? "#dafbe1" : "#ffebe9")),
          borderColor: groups.map(g =>
            (g.cp === null || g.cp === undefined) ? "#d9dee4"
            : (g.cp > 0.5 ? "#1a7f37" : "#cf222e")),
          borderWidth: 1.2,
          borderRadius: 3,
        },
        {
          label: "鲁棒性Δ(越小越脆弱)",
          data: groups.map(g => g.robustness_delta ?? 0),
          backgroundColor: "#fff8c5",
          borderColor: "#bf8700",
          borderWidth: 1.2,
          borderRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: legendCfg, tooltip: LIGHT.tooltip },
      scales,
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
      <td class="num" style="color:${reColor(g.re)};font-weight:600">${fmt(g.re)}</td>
      <td class="num" style="color:${cpColor(g.cp)}">${pct(g.cp)}</td>
      <td class="num">${fmt(g.robustness_delta)}</td>
      <td class="num">${g.n_calls ?? "—"}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderRecordsTable(records) {
  $("records-count").textContent = `共 ${records.length} 条(展示最近 200 条)`;
  const tbody = $("records-table").querySelector("tbody");
  tbody.innerHTML = "";
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

// ---------- 启动 ----------
$("refresh").onclick = () => {
  const cur = $("run-select").value;
  loadRuns(cur);
};
loadRuns();
