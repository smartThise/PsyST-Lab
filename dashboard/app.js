// PsyST Lab · 模块驱动薄壳
const $ = id => document.getElementById(id);
const fmt = (x, d = 3) => (x == null || isNaN(x)) ? "—" : Number(x).toFixed(d);
const pct = x => (x == null || isNaN(x)) ? "—" : (Number(x) * 100).toFixed(1) + "%";
const fmtV = (v, f) => { if (v == null) return "—"; if (f === "pct") return pct(v); if (f === "d") return Math.round(v); if (f === "str") return v; return fmt(v); };
async function api(url, opts) { const r = await fetch(url, { cache: "no-store", ...opts }); if (!r.ok) throw Error(r.status); return r.json(); }

// ═══════════════════════════════════════════════════════
// 状态
// ═══════════════════════════════════════════════════════
let selMod = "pi_release", spec = {}, groupInfo = [], allMods = [], runs = [];
let charts = {}, dragState = null, composerTasks = [], selectedFeature = null;
// 多关键字排序队列
let sortQueue = [];  // [{key, dir: 1|-1}], 第一项=第一关键字
let _curItems = [];

function toggleSort(key, shift) {
  const idx = sortQueue.findIndex(s => s.key === key);
  if (shift) {
    if (idx >= 0) {
      if (sortQueue[idx].dir > 0) sortQueue[idx].dir = -1;
      else sortQueue.splice(idx, 1);
    } else { sortQueue.push({key, dir: 1}); }
  } else {
    if (idx === 0) {
      if (sortQueue[0].dir > 0) sortQueue[0].dir = -1;
      else sortQueue.shift();
    } else if (idx > 0) {
      const [item] = sortQueue.splice(idx, 1); sortQueue.unshift(item);
    } else { sortQueue.unshift({key, dir: 1}); }
  }
  renderAll();
}
function multiSort(items) {
  if (!sortQueue.length) return items;
  return [...items].sort((a, b) => {
    for (const {key, dir} of sortQueue) {
      const va = a[key], vb = b[key];
      if (va == null && vb == null) continue;
      if (va == null) return -dir; if (vb == null) return dir;
      let cmp = 0;
      if (typeof va === 'string') cmp = va.localeCompare(String(vb));
      else cmp = va - vb;
      if (cmp !== 0) return dir * cmp;
    }
    return 0;
  });
}
function sortIndicatorHTML(key) {
  const idx = sortQueue.findIndex(s => s.key === key);
  if (idx < 0) return "";
  return `<span class="sort-idx">${idx+1}${sortQueue[idx].dir>0?'▲':'▼'}</span>`;
}
function renderSortBar() {
  const bar = $("sort-bar"), chips = $("sort-chips");
  if (!bar || !chips) return;
  if (!sortQueue.length) { bar.style.display = "none"; return; }
  bar.style.display = "";
  chips.innerHTML = sortQueue.map((s, i) =>
    `<span class="chip sort-chip" onclick="toggleSort('${s.key}',true)" title="点击反转, Shift+点击添加">${s.key} ${s.dir>0?'▲':'▼'} ${i===0?'(主)':''}</span>`
  ).join(" ");
}
function renderAll() { renderSortBar(); renderTable(_curItems); renderCharts(_curItems); }

function exportCSV() {
  if (!_curItems.length) return;
  const cols = spec.columns || [{ key: "accuracy", label: "指标", fmt: ".3f" }];
  const sorted = multiSort(_curItems);
  const header = ["条件", ...cols.map(c => c.label)].join(",");
  const rows = sorted.map(g =>
    [g.id, ...cols.map(c => {
      const v = g[c.key]; if (v == null) return "";
      if (c.fmt === "pct") return (v * 100).toFixed(1) + "%";
      if (c.fmt === "d") return Math.round(v);
      return typeof v === "number" ? v.toFixed(3) : String(v);
    })].join(",")
  );
  const csv = "﻿" + [header, ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = `${selMod}_${new Date().toISOString().slice(0,10)}.csv`; a.click();
}

// ═══════════════════════════════════════════════════════
// 初始化 — 加载模块
// ═══════════════════════════════════════════════════════
async function init() {
  allMods = await api("/api/modules");
  if (!allMods.length) return;
  const s = $("mod-sel");
  s.innerHTML = allMods.map(m => `<option value="${m.id}" ${m.id===selMod?"selected":""}>${m.name}</option>`).join("");
  s.onchange = async () => { selMod = s.value; await switchMod(); };
  await switchMod();
}

async function switchMod() {
  spec = await api(`/api/spec/${selMod}`);
  groupInfo = spec.launch?.features || [];
  sortQueue = []; $("sort-bar").style.display = "none";
  $("footer-module").textContent = selMod;
  loadRuns();
  loadProfiles();
}

// ═══════════════════════════════════════════════════════
// Tab 切换
// ═══════════════════════════════════════════════════════
document.querySelectorAll(".tab").forEach(b => b.onclick = () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  b.classList.add("active");
  $(`tab-${b.dataset.tab}`).classList.add("active");
  if (b.dataset.tab === "compare") renderCompare();
  if (b.dataset.tab === "launch") renderLaunch();
  if (b.dataset.tab === "settings") renderSettings();
});

// ═══════════════════════════════════════════════════════
// 数据兼容
// ═══════════════════════════════════════════════════════
function _n(items) {
  return (items || []).map(g => ({
    id: g.condition_id || g.id || "?",
    name: g.condition_name || g.name || g.id || "?",
    accuracy: g.accuracy ?? null, re: g.re ?? null, cp: g.cp ?? null,
    robustness_delta: g.robustness_delta ?? null, n_calls: g.n || g.n_calls || 0,
    rpi: g.rpi ?? null, lag1_corr: g.lag1_corr ?? null,
    assimilation_score: g.assimilation_score ?? null,
    mean_accuracy: g.mean_accuracy ?? null,
    direction_tag: g.direction_tag ?? null,
  }));
}

// ═══════════════════════════════════════════════════════
// 结果 — Run 列表
// ═══════════════════════════════════════════════════════
async function loadRuns() {
  runs = (await api("/api/runs")).filter(r => r.module_id === selMod);
  const sel = $("run-select"), empty = $("results-empty"), content = $("results-content");
  sel.innerHTML = "";
  if (!runs.length) { empty.classList.remove("hidden"); content.classList.add("hidden"); return; }
  empty.classList.add("hidden"); content.classList.remove("hidden");
  runs.forEach((r, i) => { const o = document.createElement("option"); o.value = i; o.textContent = `${r.tag} · ${r.model}`; sel.appendChild(o); });
  sel.onchange = () => loadRun(+sel.value);
  if (runs.length) loadRun(0);
}

async function loadRun(idx) {
  const r = runs[idx]; if (!r) return;
  const s = await api(`/api/run/${r.run_dir}`);
  const items = _n(s.conditions || s.groups || []);
  $("meta-model").textContent = `模型:${s.model || "?"}`;
  $("meta-pi").textContent = s.pi_test ? `PI:${s.pi_test.n_keys}×${s.pi_test.updates_per_key}` : (s.module_name || selMod);
  $("meta-calls").textContent = `${items.reduce((a, g) => a + (g.n_calls || 0), 0)} 次调用`;
  _curItems = items; sortQueue = [];
  try { renderKpis(items); } catch(e) { console.warn('KPI render error', e); }
  try { renderCharts(items); } catch(e) { console.warn('Charts render error', e); }
  try { renderTable(items); } catch(e) { console.warn('Table render error', e); }
}

// ═══════════════════════════════════════════════════════
// Builder: KPI 卡片 (从 KPISpec)
// ═══════════════════════════════════════════════════════
function renderKpis(items) {
  const kpis = spec.kpis || [];
  $("kpi-row").innerHTML = kpis.map(k => {
    let vals = items.map(g => g[k.data_key]).filter(v => v != null);
    if (k.exclude_g0) {
      const nonG0 = items.filter(g => g.id !== "G0").map(g => g[k.data_key]).filter(v => v != null);
      if (nonG0.length) vals = nonG0;
    }
    const val = k.aggregate === "max" ? (vals.length ? Math.max(...vals) : null)
      : k.aggregate === "mean" ? (vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null)
      : k.aggregate === "sum" ? (vals.length ? vals.reduce((a, b) => a + b, 0) : null)
      : vals[0];
    return `<div class="kpi ${k.accent ? 'accent' : ''}"><span class="label">${k.label}</span><span class="value">${fmtV(val, k.fmt)}</span></div>`;
  }).join("");
}

// ═══════════════════════════════════════════════════════
// Builder: 图表 (从 ChartSpec, 保留美丽 Chart.js 配置)
// ═══════════════════════════════════════════════════════
const LIGHT = {
  grid: "rgba(31,35,40,0.08)", tick: "#57606a",
  tooltip: { backgroundColor: "#fff", borderColor: "#d0d7de", borderWidth: 1, titleColor: "#1f2328", bodyColor: "#424a53", boxPadding: 4, cornerRadius: 6 }
};

function _parseCondId(cid) {
  // "G2+G8s_u400_p2.5" → {strategy, updates, position}
  // "G0_u12_p75x50x2.5"  → same
  // fallback: return cid as strategy
  const m = cid.match(/^(.+)_u(\d+)_p(.+)$/);
  if (!m) return { strategy: cid, updates: 0, position: "" };
  return { strategy: m[1], updates: parseInt(m[2]), position: m[3] };
}

function renderCharts(items) {
  Object.values(charts).forEach(c => c?.destroy()); charts = {};
  const sorted = multiSort(items);
  const chartSpecs = (spec.charts || []).filter(c => c.chart_type !== "kpi" && c.chart_type !== "table");
  const basicSpecs = chartSpecs.filter(c => c.chart_type !== "line-series" && c.chart_type !== "heatmap");
  const advSpecs = chartSpecs.filter(c => ["line-series","heatmap","surface3d"].includes(c.chart_type));

  // 基础图表 (bar, scatter) canvas 容器
  $("chart-grid").innerHTML = basicSpecs.map(c =>
    `<div class="chart-card"><header><h3>${c.title}</h3><span class="sort-hint" onclick="toggleSort('${c.data_key}');return false">按${c.data_key}排序</span></header><canvas id="ch-${c.chart_id}" height="120"></canvas></div>`
  ).join("");

  const labels = sorted.map(g => g.id);
  const colors = labels.map((_, i) => `hsl(${i * 360 / Math.max(labels.length,1)}, 60%, 55%)`);
  const scales = {
    x: { ticks: { color: LIGHT.tick, font: { size: 12 } }, grid: { display: false }, border: { color: "#d0d7de" } },
    y: { beginAtZero: true, ticks: { color: LIGHT.tick }, grid: { color: LIGHT.grid }, border: { display: false } }
  };
  const legend = { labels: { color: "#424a53", font: { size: 12 }, boxWidth: 12, boxHeight: 12 } };

  for (const c of basicSpecs) {
    const ctx = $(`ch-${c.chart_id}`); if (!ctx) continue;
    const vals = sorted.map(g => g[c.data_key] ?? 0);
    const ds = [{
      label: c.y_label || c.data_key, data: vals,
      backgroundColor: colors.map(co => co + "44"), borderColor: colors,
      borderWidth: 1.5, borderRadius: 3
    }];
    charts[c.chart_id] = new Chart(ctx, {
      type: c.chart_type || "bar", data: { labels, datasets: ds },
      options: { responsive: true, plugins: { legend, tooltip: LIGHT.tooltip }, scales }
    });
  }

  // 高级图表: line-series + heatmap + surface3d (各自 try/catch 防阻断)
  for (const c of advSpecs) {
    try {
      if (c.chart_type === "line-series") renderLineSeries(c, items);
      if (c.chart_type === "heatmap") renderHeatmap(c, items);
      if (c.chart_type === "surface3d") renderSurface3D(c, items);
    } catch(e) { console.warn('chart render failed:', c.chart_id, e); }
  }
}

function renderLineSeries(c, items) {
  const sk = c.series_key || "strategy";
  const xk = c.x_key || "updates";
  const dk = c.data_key || "accuracy";

  const parsed = items.map(g => ({ ...g, _p: _parseCondId(g.id) }));
  const valid = parsed.filter(g => g._p[xk] !== 0);
  if (!valid.length) return;  // 非扫参数据, 跳过

  // 按 series 分组, 每组按 x 排序
  const groups = {};
  for (const g of valid) {
    const s = g._p[sk] || "?";
    if (!groups[s]) groups[s] = [];
    groups[s].push({ x: g._p[xk], y: g[dk] ?? 0 });
  }
  for (const s of Object.keys(groups)) groups[s].sort((a, b) => a.x - b.x);

  const seriesNames = Object.keys(groups);
  const colors = seriesNames.map((_, i) => `hsl(${i * 360 / seriesNames.length}, 60%, 55%)`);

  const container = document.createElement("div");
  container.className = "chart-card";
  container.innerHTML = `<header><h3>${c.title}</h3></header><canvas id="ch-${c.chart_id}" height="120"></canvas>`;
  $("chart-grid").appendChild(container);

  const ctx = $(`ch-${c.chart_id}`); if (!ctx) return;
  const datasets = seriesNames.map((s, i) => ({
    label: s, data: groups[s].map(p => p.y),
    borderColor: colors[i], backgroundColor: colors[i] + "22",
    borderWidth: 2, pointRadius: 3, tension: 0.1,
  }));
  const allX = [...new Set(valid.map(g => g._p[xk]))].sort((a,b) => a-b);
  charts[c.chart_id] = new Chart(ctx, {
    type: "line",
    data: { labels: allX, datasets },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: "#424a53", font: { size: 11 }, boxWidth: 12 } }, tooltip: LIGHT.tooltip },
      scales: {
        x: { title: { display: !!c.x_label, text: c.x_label }, ticks: { color: LIGHT.tick } },
        y: { beginAtZero: false, title: { display: !!c.y_label, text: c.y_label }, ticks: { color: LIGHT.tick } }
      }
    }
  });
}

function renderHeatmap(c, items) {
  const xk = c.x_key || "updates";
  const yk = c.y_key || "position";
  const dk = c.data_key || "accuracy";

  const parsed = items.map(g => ({ ...g, _p: _parseCondId(g.id) }));
  const valid = parsed.filter(g => g._p[xk] !== 0 && g._p[yk]);
  if (!valid.length) return;
  const xs = [...new Set(valid.map(g => g._p[xk]))].sort((a,b) => a-b);
  const ys = [...new Set(valid.map(g => g._p[yk]))].sort();

  // 生成二维矩阵
  let html = `<table class="heatmap"><thead><tr><th></th>`;
  for (const x of xs) html += `<th>${x}</th>`;
  html += `</tr></thead><tbody>`;
  for (const yv of ys) {
    html += `<tr><th>${yv}</th>`;
    for (const xv of xs) {
      const found = valid.find(g => g._p[xk] === xv && g._p[yk] === yv);
      const val = found ? (found[dk] ?? 0) : null;
      const color = val != null ? `hsl(${120 * val}, 50%, ${30 + 40 * (1-val)}%)` : "#eee";
      html += `<td style="background:${color}" title="${xv},${yv}: ${val!=null?(val*100).toFixed(1)+'%':'—'}">${val!=null?(val*100).toFixed(0):''}</td>`;
    }
    html += `</tr>`;
  }
  html += `</tbody></table>`;

  const container = document.createElement("div");
  container.className = "chart-card";
  container.innerHTML = `<header><h3>${c.title}</h3></header>${html}`;
  $("chart-grid").appendChild(container);
}

function renderSurface3D(c, items) {
  const xk = c.x_key || "updates";
  const yk = c.y_key || "position";
  const dk = c.data_key || "accuracy";
  const sk = c.series_key || "strategy";

  const parsed = items.map(g => ({ ...g, _p: _parseCondId(g.id) }));
  const valid = parsed.filter(g => g._p[xk] !== 0 && g._p[yk]);
  if (!valid.length || typeof Plotly === "undefined") return;  // 无扫参数据或 Plotly 未加载, 不渲染空壳

  // 按 strategy 分组, 每个策略一个曲面
  const byStrat = {};
  for (const g of valid) {
    const s = g._p[sk] || "?";
    if (!byStrat[s]) byStrat[s] = [];
    byStrat[s].push(g);
  }

  const strategyKeys = Object.keys(byStrat);
  // 限制显示数量避免太密
  const showStrats = strategyKeys.slice(0, 9);

  // 构建 Plotly 子图 grid
  const n = showStrats.length;
  const cols = Math.min(3, n);
  const rows = Math.ceil(n / cols);

  const subplots = [];
  for (const s of showStrats) {
    const pts = byStrat[s];
    const xsAll = [...new Set(pts.map(p => p._p[xk]))].sort((a,b)=>a-b);
    const ysAll = [...new Set(pts.map(p => p._p[yk]))].sort();
    const z = ysAll.map(yv =>
      xsAll.map(xv => {
        const f = pts.find(p => p._p[xk]===xv && p._p[yk]===yv);
        return f ? (f[dk] ?? 0) : null;
      })
    );
    subplots.push({
      type: "surface",
      x: xsAll, y: ysAll, z,
      colorscale: "Viridis",
      name: s,
      colorbar: { title: dk },
      contours: { z: { show: true, usecolormap: true, project: { z: true } } },
    });
  }

  const traces = [];
  for (let i = 0; i < subplots.length; i++) {
    const sp = subplots[i];
    traces.push({
      ...sp,
      scene: `scene${i}`,
      xaxis: `x${i+1}`, yaxis: `y${i+1}`,
    });
  }

  const layout = {
    grid: { rows, columns: cols, pattern: "independent" },
    title: c.title,
    ...Object.fromEntries(traces.map((_, i) => [
      `scene${i}`,
      { xaxis_title: c.x_label, yaxis_title: c.y_label, zaxis_title: dk,
        camera: { eye: { x: 1.5, y: -1.5, z: 1.2 } } }
    ])),
    height: rows * 350,
  };

  const container = document.createElement("div");
  container.className = "chart-card";
  const divId = `plotly-${c.chart_id}`;
  container.innerHTML = `<header><h3>${c.title}</h3><span class="muted small">每个策略一个3D曲面: X=${c.x_label} Y=${c.y_label} Z=${dk}</span></header><div id="${divId}"></div>`;
  $("chart-grid").appendChild(container);
  Plotly.newPlot(divId, traces, layout, { responsive: true, displayModeBar: false });
}

// ═══════════════════════════════════════════════════════
// Builder: 表格 (从 ColumnSpec, 带排序 + 导出)
// ═══════════════════════════════════════════════════════
function renderTable(items) {
  const cols = spec.columns || [{ key: "accuracy", label: "指标", fmt: ".3f" }];
  const sorted = multiSort(items); _curItems = items;
  $("table-title").innerHTML = `详情 <button class="sm" onclick="exportCSV()" title="导出 CSV">⬇ 导出</button>`;
  const thead = $("detail-table").querySelector("thead");
  thead.innerHTML = "<tr><th>条件</th>" + cols.map(c =>
    `<th class="sortable" onclick="toggleSort('${c.key}')" onauxclick="toggleSort('${c.key}',true);return false" title="点击排序(Shift+点击=多关键字)">${c.label}${sortIndicatorHTML(c.key)}</th>`
  ).join("") + "</tr>";
  const tbody = $("detail-table").querySelector("tbody"); tbody.innerHTML = "";
  for (const g of sorted) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${g.id}</td>` + cols.map(c => `<td class="num">${fmtV(g[c.key], c.fmt)}</td>`).join("");
    tbody.appendChild(tr);
  }
  renderSortBar();
}

// ═══════════════════════════════════════════════════════
// Builder: 启动面板
// ═══════════════════════════════════════════════════════
async function renderLaunch() {
  const composer = spec.launch?.composer || "checklist";
  const extra = spec.launch?.extra_params || [];
  const desc = spec.launch?.description || "";
  const descEl = $("launch-desc"); if (descEl) descEl.textContent = desc;

  // 隐藏 PI-specific 旧字段, 渲染泛用 extra_params
  const formGrid = document.querySelector(".form-grid-5");
  if (formGrid) formGrid.innerHTML = extra.map(p => {
    const itype = p.type === "str" ? "text" : "number";
    const def = p.default != null ? p.default : (itype === "number" ? 1 : "");
    return `<label>${p.label}<input id="f-${p.key}" type="${itype}" value="${def}"></label>`;
  }).join("");

  // Profile dropdown
  try {
    const profs = (await api("/api/profiles")).profiles || [];
    const sel = $("f-profile"); if (sel) sel.innerHTML = profs.map(p => `<option>${p.name}</option>`).join("");
  } catch (e) { }

  if (composer === "drag") {
    renderTaskComposer();
  } else {
    renderChecklistPicker();
  }

  // Launch button
  $("launch-btn").onclick = async () => {
    const body = { profile: $("f-profile")?.value || "", module_id: selMod };
    if (composer === "drag") {
      const tasks = composerTasks.map(t => ({ features: t.features.filter(f => f), ...(t.name ? { name: t.name } : {}) }));
      if (!tasks.length) tasks.push({ features: [] });
      body.tasks = tasks;
    } else {
      const checked = [...document.querySelectorAll("#launch-conds input:checked")].map(c => c.value);
      if (!checked.length) { $("launch-msg").textContent = "请选择至少一个条件"; return; }
      body.conditions = checked;
    }
    extra.forEach(p => { const v = $(`f-${p.key}`)?.value; if (v) body[p.key] = p.type === "str" ? v : +v; });
    $("launch-msg").textContent = "启动中…";
    try {
      const r = await api("/api/launch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      $("launch-msg").textContent = r.launched ? `已启动! ${r.module_id || ""}` : `失败:${r.error}`;
      document.querySelector('.tab[data-tab="live"]')?.click();
    } catch (e) { $("launch-msg").textContent = `错误:${e.message}`; }
  };
}

// ═══════════════════════════════════════════════════════
// ═══════════════════════════════════════════════════════
// Grouped checklist (模块 params 驱动, 分组+描述从条件自带)
// ═══════════════════════════════════════════════════════
function toggleMode(mode, val) {
  document.querySelectorAll('.cond-row input').forEach(c => {
    const id = c.value;
    const isRating = id.endsWith('_rating');
    if (mode === 'rating' && isRating) c.checked = val;
    if (mode === 'recall' && !isRating) c.checked = val;
  });
}

async function renderChecklistPicker() {
  const composer = document.getElementById("task-composer");
  if (composer) composer.style.display = "none";
  $("add-task") && ($("add-task").style.display = "none");

  const conds = await api(`/api/groups?module=${selMod}`);
  const list = conds.conditions || [];

  // 按 group 字段分组 (模块提供, 不拆 ID)
  const groups = {};
  for (const c of list) {
    const gid = c.group || c.id;
    if (!groups[gid]) groups[gid] = { gid, label: c.group_label || gid, rpi: c.rpi_expected, conds: [] };
    groups[gid].conds.push(c);
  }
  const pairs = Object.values(groups).sort((a, b) => (b.rpi || 0) - (a.rpi || 0));

  // 操作栏
  let html = `<div class="checklist-bar">
    <button class="sm" onclick="document.querySelectorAll('.cond-row input').forEach(c=>c.checked=true)">全选</button>
    <button class="sm" onclick="document.querySelectorAll('.cond-row input').forEach(c=>c.checked=false)">清空</button>
    <button class="sm" onclick="toggleMode('recall',true)">全选 Recall</button>
    <button class="sm" onclick="toggleMode('rating',true)">全选 Rating</button>
  </div>`;

  html += `<div class="checklist-groups">`;
  for (const g of pairs) {
    html += `<div class="cond-row">
      <div class="cond-pair-info">
        <span class="cond-pair-label">${g.label}</span>
        ${g.rpi != null ? `<span class="cond-rpi muted">人类RPI ${g.rpi.toFixed(2)}</span>` : ""}
      </div>
      <span class="cond-chips">`;
    for (const c of g.conds) {
      html += `<label class="cond-chip" title="${c.desc || c.name}">
        <input type="checkbox" value="${c.id}"> ${c.name}</label>`;
    }
    html += `</span></div>`;
  }
  html += `</div>`;

  let grid = $("launch-conds");
  if (!grid) {
    grid = document.createElement("div"); grid.id = "launch-conds";
    grid.className = "cond-grid";
    const form = document.querySelector(".form-groups") || $("tab-launch");
    form?.appendChild(grid);
  }
  grid.innerHTML = html;
}

// ═══════════════════════════════════════════════════════
// Task Composer (drag-and-drop — for "drag" composer)
// ═══════════════════════════════════════════════════════
function chipColor(g) { return g.color || "#57606a"; }
function groupColor(id) { const g = groupInfo.find(x => x.id === id); return (g && g.color) || "#57606a"; }
function badge(id) { return `<span class="tag tag-dyn" style="--c:${groupColor(id)}">${id}</span>`; }
function reColor(re) { if (re == null || isNaN(re)) return "var(--muted)"; if (re >= 0.2) return "var(--green)"; if (re >= 0.05) return "var(--amber)"; return "var(--red)"; }

function renderTaskComposer() {
  const composer = document.getElementById("task-composer");
  if (composer) composer.style.display = "";
  $("add-task") && ($("add-task").style.display = "");
  const grid = $("launch-conds"); if (grid) grid.innerHTML = "";

  composerTasks = [{ features: [], name: "" }];
  renderPalette(); renderTaskList();
}

function renderPalette() {
  const pal = $("palette"); if (!pal) return;
  pal.innerHTML = "";
  for (const g of groupInfo) {
    if (!g.composable) continue;
    const chip = document.createElement("span");
    chip.className = "chip chip-drag";
    chip.style.setProperty("--c", chipColor(g));
    chip.draggable = true;
    chip.textContent = g.id;
    chip.title = "点击看说明 / 拖入任务";
    chip.ondragstart = e => { dragState = { source: "palette", feature: g.id }; e.dataTransfer.effectAllowed = "copy"; };
    chip.ondragend = () => { dragState = null; };
    chip.onclick = () => { selectedFeature = (selectedFeature === g.id) ? null : g.id; renderPaletteDetail(); };
    pal.appendChild(chip);
  }
}

function renderPaletteDetail() {
  const box = $("palette-detail"); if (!box) return;
  if (!selectedFeature) { box.innerHTML = `<span class="muted small">点击 feature 看说明, 或拖入任务框。</span>`; return; }
  const g = groupInfo.find(x => x.id === selectedFeature);
  if (!g) return;
  box.innerHTML = `<div class="palette-detail-head"><span class="chip" style="--c:${chipColor(g)}">${g.id}</span><span class="palette-detail-name">${g.name}</span></div><div class="palette-detail-desc">${g.desc || ""}</div>`;
}

function renderTaskList() {
  const list = $("task-list"); if (!list) return;
  list.innerHTML = "";
  composerTasks.forEach((task, ti) => {
    const card = document.createElement("div"); card.className = "task-card";
    const head = document.createElement("div"); head.className = "task-head";
    const tid = task.features.length ? task.features.join("+") : "G0";
    const idSpan = document.createElement("span"); idSpan.className = "task-id"; idSpan.textContent = tid;
    const nameIn = document.createElement("input"); nameIn.className = "task-name"; nameIn.placeholder = "任务名"; nameIn.value = task.name || "";
    nameIn.oninput = e => { task.name = e.target.value; };
    head.appendChild(idSpan); head.appendChild(nameIn);
    if (composerTasks.length > 1) { const rm = document.createElement("button"); rm.className = "ghost tiny"; rm.textContent = "删除"; rm.onclick = () => { composerTasks.splice(ti, 1); renderTaskList(); }; head.appendChild(rm); }
    card.appendChild(head);
    const row = document.createElement("div"); row.className = "task-chips";
    row.ondragover = e => { e.preventDefault(); row.classList.add("drag-over"); };
    row.ondragleave = e => { if (!row.contains(e.relatedTarget)) row.classList.remove("drag-over"); };
    row.ondrop = e => {
      e.preventDefault(); row.classList.remove("drag-over");
      if (!dragState) return;
      if (dragState.source === "palette") { task.features.push(dragState.feature); }
      else if (dragState.source === "task") {
        const fromTi = dragState.taskId, fromIdx = dragState.idx;
        let dropIdx = task.features.length;
        const overChip = e.target.closest(".chip-in-task");
        if (overChip) { const chips = [...row.querySelectorAll(".chip-in-task")]; let idx = chips.indexOf(overChip); const r = overChip.getBoundingClientRect(); if (e.clientX > r.left + r.width / 2) idx++; dropIdx = idx; }
        composerTasks[fromTi].features.splice(fromIdx, 1);
        if (fromTi === ti && fromIdx < dropIdx) dropIdx--;
        task.features.splice(dropIdx, 0, dragState.feature);
      }
      dragState = null; renderTaskList();
    };
    if (!task.features.length) { const ph = document.createElement("span"); ph.className = "muted small task-empty"; ph.textContent = "空任务 = 基线。拖 feature 进来组合。"; row.appendChild(ph); }
    else { task.features.forEach((fid, idx) => { const g = groupInfo.find(x => x.id === fid) || { id: fid }; const chip = document.createElement("span"); chip.className = "chip chip-in-task"; chip.style.setProperty("--c", chipColor(g)); chip.draggable = true; chip.textContent = fid; chip.ondragstart = e => { dragState = { source: "task", taskId: ti, idx, feature: fid }; e.dataTransfer.effectAllowed = "move"; }; chip.ondragend = () => { dragState = null; }; const x = document.createElement("span"); x.className = "chip-x"; x.textContent = "×"; x.title = "移除"; x.onclick = e => { e.stopPropagation(); task.features.splice(idx, 1); renderTaskList(); }; chip.appendChild(x); row.appendChild(chip); }); }
    card.appendChild(row); list.appendChild(card);
  });
}
$("add-task") && ($("add-task").onclick = () => { composerTasks.push({ features: [], name: "" }); renderTaskList(); });

// ═══════════════════════════════════════════════════════
// 对比
// ═══════════════════════════════════════════════════════
async function renderCompare() { renderComparePicker(); renderCompareTable(); }
async function renderComparePicker() {
  const cr = (await api("/api/runs")).filter(r => r.module_id === selMod);
  const pk = $("compare-picker"); pk.innerHTML = "";
  if (!cr.length) { pk.innerHTML = '<p class="muted small">暂无 run。</p>'; return; }
  cr.forEach(r => {
    const lbl = document.createElement("label"); lbl.className = "picker-item";
    lbl.innerHTML = `<input type="checkbox" data-rundir="${r.run_dir}"><span class="picker-tag">${r.tag}</span><span class="picker-meta">${r.model} · ${r.n_conditions||0}条件</span>`;
    lbl.querySelector("input").onchange = renderCompareTable;
    pk.appendChild(lbl);
  });
}
async function exportCompareCSV() {
  const table = $("compare-table");
  const rows = table.querySelectorAll("tr");
  if (!rows.length) return;
  let csv = "";
  rows.forEach(row => {
    const cells = row.querySelectorAll("th, td");
    csv += [...cells].map(c => `"${c.textContent.replace(/"/g,'""').trim()}"`).join(",") + "\n";
  });
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = `compare_${selMod}_${new Date().toISOString().slice(0,10)}.csv`; a.click();
}

async function renderCompareTable() {
  const checked = [...document.querySelectorAll("#compare-picker input:checked")].map(e => e.dataset.rundir);
  const table = $("compare-table");
  if (!checked.length) { table.innerHTML = '<caption class="muted">勾选上方 run 生成对比</caption>'; return; }
  const data = await api(`/api/compare?tags=${encodeURIComponent(checked.join(","))}`);
  if (!Object.keys(data).length) { table.innerHTML = '<caption class="muted">无法加载对比数据</caption>'; return; }
  const showRE = $("compare-re")?.checked;
  // 收集所有 group id
  const gids = new Set();
  Object.values(data).forEach(r => Object.keys(r.groups || {}).forEach(g => gids.add(g)));
  const cols = groupInfo.length ? groupInfo.map(g => g.id).filter(g => gids.has(g)) : [...gids].sort();
  [...gids].sort().forEach(g => { if (!cols.includes(g)) cols.push(g); });
  // 表头
  let html = `<thead><tr><th>组 \\ run</th>`;
  for (const key of checked) {
    const r = data[key]; if (!r) continue;
    const tagShort = (r.tag || key).slice(-16);
    const acc = r.baseline_acc != null ? `<br>基线 ${(r.baseline_acc*100).toFixed(1)}%` : "";
    html += `<th><div class="cth-tag">${tagShort}</div><div class="cth-meta">${r.model||""}${acc}</div></th>`;
  }
  html += "</tr></thead><tbody>";
  // 表体
  for (const gid of cols) {
    let row = `<tr><td>${badge(gid)}</td>`;
    for (const key of checked) {
      const g = data[key]?.groups?.[gid];
      if (!g) { row += `<td class="num muted">—</td>`; continue; }
      const val = showRE ? (g.re ?? 0) : (g.accuracy ?? 0);
      const color = val >= 0.5 ? "var(--green)" : val < 0.2 ? "var(--red)" : "var(--text-2)";
      row += `<td class="num" style="color:${color};font-weight:600">${showRE ? fmt(g.re) : pct(g.accuracy)}</td>`;
    }
    html += row + "</tr>";
  }
  table.innerHTML = html + "</tbody>";
}

// ═══════════════════════════════════════════════════════
// 实时 / 设置 (保留)
// ═══════════════════════════════════════════════════════
setInterval(async () => {
  try { const s = await api(`/api/status?module=${selMod}`); const d = $("status-pill"), t = $("status-text"); d.classList.toggle("on", s.running); d.classList.toggle("off", !s.running); t.textContent = s.running ? "运行中" : "空闲"; $("live-state").textContent = s.running ? "运行中" : "空闲"; $("live-group").textContent = s.current_group || "—"; $("live-progress").textContent = s.records_total ? `${s.records_done}/${s.records_total}` : `${s.records_done || 0}`; $("live-tag").textContent = s.latest_run || "—"; $("live-log").textContent = s.log_tail || "（暂无日志）"; $("live-log").scrollTop = $("live-log").scrollHeight; $("force-stop-btn").disabled = !s.running; $("launch-btn") && ($("launch-btn").disabled = s.running); } catch (e) { }
}, 3000);

$("force-stop-btn").onclick = async () => {
  if (!confirm("强制停止并删除当前 run?")) return;
  try { const r = await api("/api/force-stop", { method: "POST" }); $("force-stop-msg").textContent = r.killed?.length ? `已停止` : "无运行进程"; } catch (e) { }
};

let profiles = [];
async function loadProfiles() { try { profiles = (await api("/api/profiles")).profiles || []; } catch (e) { } }
function renderSettings() {
  loadProfiles();
  $("settings-profiles").innerHTML = profiles.map((p, i) => `<div class="profile-row">
    <span><b>${p.name}</b> · ${p.base_url||"?"} · ${p.model||"?"}</span>
    <span class="profile-acts">
      <button class="sm" onclick="fillProfileByIdx(${i})" title="载入编辑">✎</button>
      <button class="sm" onclick="deleteProfile('${p.name}')" title="删除">✕</button>
    </span>
  </div>`).join("");
}
function fillProfileByIdx(i) {
  const p = profiles[i]; if (!p) return;
  $("p-name").value = p.name || ""; $("p-baseurl").value = p.base_url || "";
  $("p-apikey").value = p.api_key || ""; $("p-model").value = p.model || "";
  try { $("p-extra").value = typeof p.extra_body === "string" ? p.extra_body : JSON.stringify(p.extra_body||{}, null, 2); } catch(e) { $("p-extra").value = ""; }
  $("p-msg").textContent = "已载入,修改后点保存";
}
async function deleteProfile(name) {
  if (!confirm(`删除配置 "${name}"?`)) return;
  try { await api(`/api/profiles?name=${encodeURIComponent(name)}`, {method:"DELETE"}); $("p-msg").textContent = `已删除 ${name}`; loadProfiles(); renderSettings(); }
  catch(e) { $("p-msg").textContent = `删除失败:${e}`; }
}
$("p-save").onclick = async () => {
  try {
    let eb = $("p-extra").value.trim();
    if (eb) { try { eb = JSON.parse(eb); } catch { /* keep as string */ } }
    else eb = null;
    const body = { name: $("p-name").value, base_url: $("p-baseurl").value, api_key: $("p-apikey").value, model: $("p-model").value };
    if (eb) body.extra_body = eb;
    await api("/api/profiles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    $("p-msg").textContent = "已保存"; loadProfiles(); renderSettings();
  } catch (e) { $("p-msg").textContent = `错误:${e}`; }
};

// ═══════════════════════════════════════════════════════
// 启动
// ═══════════════════════════════════════════════════════
init();
