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
  const cols = spec.columns || [];
  const col = cols.find(c => c.key === key);
  const label = col ? col.label : key;
  const idx = sortQueue.findIndex(s => s.key === key);
  if (shift) {
    if (idx >= 0) {
      if (sortQueue[idx].dir > 0) sortQueue[idx].dir = -1;
      else sortQueue.splice(idx, 1);
    } else { sortQueue.push({key, label, dir: 1}); }
  } else {
    if (idx === 0) {
      if (sortQueue[0].dir > 0) sortQueue[0].dir = -1;
      else sortQueue.shift();
    } else if (idx > 0) {
      const [item] = sortQueue.splice(idx, 1); sortQueue.unshift(item);
    } else { sortQueue.unshift({key, label, dir: 1}); }
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
let filterText = "", hiddenCols = new Set();
function renderSortBar() {
  const bar = $("toolbar"), chips = $("sort-chips"), toggles = $("col-toggles");
  if (!bar || !chips) return;
  bar.style.display = "";
  // 排序下拉
  const sel = $("sort-key-select");
  if (sel) {
    const cols = spec.columns || [];
    sel.innerHTML = '<option value="">+ 排序关键字</option>' + cols.map(c =>
      `<option value="${c.key}">${c.label} (${c.key})</option>`
    ).join("");
    sel.onchange = () => { if (sel.value) { toggleSort(sel.value); sel.value = ""; } };
  }
  chips.innerHTML = sortQueue.map((s, i) =>
    `<span class="chip sort-chip" onclick="toggleSort('${s.key}',true)" title="反转">${s.label||s.key} ${s.dir>0?'▲':'▼'} ${i===0?'(主)':''}</span>`
  ).join(" ") || '<span class="muted small">(下拉添加排序)</span>';
  // 列显隐开关
  const cols = spec.columns || [];
  toggles.innerHTML = cols.map(c =>
    `<label class="col-toggle" title="显示/隐藏 ${c.label}"><input type="checkbox" ${hiddenCols.has(c.key)?'':'checked'} onchange="toggleCol('${c.key}',this.checked)">${c.label}</label>`
  ).join("");
}
function toggleCol(key, show) { if (show) hiddenCols.delete(key); else hiddenCols.add(key); renderAll(); }
function renderAll() { renderSortBar(); renderTable(_curItems); renderCharts(_curItems); }
function filteredItems() {
  let items = _curItems || [];
  if (filterText) {
    const q = filterText.toLowerCase();
    items = items.filter(g => g.id.toLowerCase().includes(q));
  }
  return multiSort(items);
}

function exportCSV() {
  if (!_curItems.length) return;
  const cols = spec.columns || [{ key: "accuracy", label: "指标", fmt: ".3f" }];
  const sorted = multiSort(_curItems);
  const vc = cols.filter(c => !hiddenCols.has(c.key));
  const header = ["条件", ...vc.map(c => c.label)].join(",");
  const rows = sorted.map(g =>
    [g.id, ...vc.map(c => {
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
  sortQueue = []; $("toolbar") && ($("toolbar").style.display = "none");
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
    updates: g.updates ?? null,
    d_prime: g.d_prime ?? null, hit_rate: g.hit_rate ?? null,
    false_alarm: g.false_alarm ?? null, direction_tag: g.direction_tag ?? null,
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
  window._runSummary = s;
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
  const summary = window._runSummary || {};
  $("kpi-row").innerHTML = kpis.map(k => {
    // baseline_acc 优先从 summary 顶层读
    let val = null;
    if (k.data_key === "accuracy" && k.aggregate === "first" && summary.baseline_acc != null) {
      val = summary.baseline_acc;
    } else {
      let vals = items.map(g => g[k.data_key]).filter(v => v != null);
      if (k.exclude_g0) {
        const nonG0 = items.filter(g => g.id !== "G0").map(g => g[k.data_key]).filter(v => v != null);
        if (nonG0.length) vals = nonG0;
      }
      val = k.aggregate === "max" ? (vals.length ? Math.max(...vals) : null)
        : k.aggregate === "mean" ? (vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null)
        : k.aggregate === "sum" ? (vals.length ? vals.reduce((a, b) => a + b, 0) : null)
        : vals[0];
    }
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
  const advSpecs = chartSpecs.filter(c => ["line-series","line-series-grid","heatmap","surface3d","grouped-bar-grid"].includes(c.chart_type));

  // 清空容器
  $("sweep-charts").innerHTML = "";
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

  // sweep 数据 (>多个 condition 含 updates 维度) 跳过 basic bar chart, 只看 line-series/heatmap
  const isSweep = items.length > 10 && items.some(g => g.updates != null);
  for (const c of basicSpecs) {
    if (isSweep) continue;  // sweep数据bar图无意义
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
      if (c.chart_type === "line-series-grid") renderLineSeriesGrid(c, items);
      if (c.chart_type === "heatmap") renderHeatmap(c, items);
      if (c.chart_type === "surface3d") renderSurface3D(c, items);
      if (c.chart_type === "grouped-bar-grid") renderGroupedBarGrid(c, items);
    } catch(e) {
      console.error('chart render failed:', c.chart_id, e);
      // 在页面上也显示错误
      const errDiv = document.createElement("div");
      errDiv.className = "chart-card";
      errDiv.innerHTML = `<header><h3>${c.title}</h3></header><p class=\"muted small\" style=\"color:var(--red);padding:16px\">渲染失败: ${e.message}</p>`;
      $("sweep-charts").appendChild(errDiv);
    }
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
  $("sweep-charts").appendChild(container);

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
  $("sweep-charts").appendChild(container);
}

function renderLineSeriesGrid(c, items) {
  const sk = c.series_key || "strategy";
  const xk = c.x_key || "updates";
  const spk = c.split_key || "position";
  const dk = c.data_key || "accuracy";

  const parsed = items.map(g => ({ ...g, _p: _parseCondId(g.id) }));
  const valid = parsed.filter(g => g._p[xk] !== 0);
  if (!valid.length) return;

  // 按 split_key 分组
  const groups = {};
  for (const g of valid) {
    const sp = g._p[spk] || "?";
    if (!groups[sp]) groups[sp] = [];
    groups[sp].push(g);
  }
  const splits = Object.keys(groups).sort();

  // 容器: 标题 + 子图网格
  const container = document.createElement("div");
  container.className = "chart-card";
  const inner = document.createElement("div");
  inner.className = "line-grid";
  inner.style.cssText = "display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:16px;padding:16px;";

  // 所有 series 颜色统一
  const allSeries = [...new Set(valid.map(g => g._p[sk]))];
  const colors = {};
  allSeries.forEach((s, i) => colors[s] = `hsl(${i*360/allSeries.length},65%,50%)`);

  splits.forEach(sp => {
    const sub = document.createElement("div");
    sub.style.cssText = "display:flex;flex-direction:column;min-height:280px;";
    sub.innerHTML = `<h4 style="font-size:12px;color:#656d76;margin:0 0 8px;font-weight:600">位置 ${sp}% (尾部剩余)</h4><div style="flex:1;position:relative;min-height:240px;"><canvas></canvas></div>`;
    inner.appendChild(sub);
    const ctx = sub.querySelector("canvas");

    const gs = groups[sp];
    const bySeries = {};
    gs.forEach(g => {
      const s = g._p[sk];
      if (!bySeries[s]) bySeries[s] = [];
      bySeries[s].push({ x: g._p[xk], y: g[dk] ?? 0 });
    });
    Object.values(bySeries).forEach(arr => arr.sort((a,b)=>a.x-b.x));
    const xs = [...new Set(gs.map(g=>g._p[xk]))].sort((a,b)=>a-b);
    const datasets = Object.keys(bySeries).map(s => ({
      label: s, data: bySeries[s].map(p=>p.y),
      borderColor: colors[s], backgroundColor: colors[s]+"22",
      borderWidth: 2, pointRadius: 4, tension: 0.15,
    }));
    charts[`${c.chart_id}_${sp}`] = new Chart(ctx, {
      type: "line", data: { labels: xs, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position:"bottom", labels: { color:"#424a53", font:{size:11}, boxWidth:14, boxHeight:14, padding:8 } } },
        scales: { x: { ticks:{color:"#57606a",font:{size:11}} }, y: { beginAtZero:false, ticks:{color:"#57606a",font:{size:11}} } }
      }
    });
  });

  container.innerHTML = `<header><h3>${c.title}</h3></header>`;
  container.appendChild(inner);
  $("sweep-charts").appendChild(container);
}

function _uniqueVals(items, key) { return [...new Set(items.map(g => g._p[key]))].sort((a,b)=>a-b); }

function renderGroupedBarGrid(c, items) {
  const dk = c.data_key || "accuracy";
  const sk = c.series_key || "strategy";
  const xk = c.x_key || "position";
  const spk = c.split_key || "updates";

  const parsed = items.map(g => ({ ...g, _p: _parseCondId(g.id) }));
  const valid = parsed.filter(g => g._p.updates !== 0);
  if (!valid.length) return;

  // 按 split_key 分组
  const splits = {};
  for (const g of valid) {
    const sp = g._p[spk];
    if (!splits[sp]) splits[sp] = [];
    splits[sp].push(g);
  }
  const splitKeys = Object.keys(splits).sort((a,b)=>+a-+b);

  // 所有 series + x 颜色统一
  const allSeries = [...new Set(valid.map(g => g._p[sk]))];
  const colors = {};
  allSeries.forEach((s, i) => colors[s] = `hsl(${i*360/allSeries.length},60%,55%)`);
  const allX = [...new Set(valid.map(g => g._p[xk]))].sort();

  const container = document.createElement("div");
  container.className = "chart-card";
  container.innerHTML = `<header><h3>${c.title}</h3></header>`;
  const inner = document.createElement("div");
  inner.style.cssText = "display:grid;grid-template-columns:repeat(auto-fit,minmax(440px,1fr));gap:16px;padding:16px;";

  splitKeys.forEach(sp => {
    const sub = document.createElement("div");
    sub.style.cssText = "display:flex;flex-direction:column;min-height:320px;";
    sub.innerHTML = `<h4 style="font-size:12px;color:#656d76;margin:0 0 8px;font-weight:600">${spk} = ${sp}</h4><div style="flex:1;position:relative;min-height:280px;"><canvas></canvas></div>`;
    inner.appendChild(sub);
    const ctx = sub.querySelector("canvas");

    const gs = splits[sp];
    // datasets = 每个 series 一组柱, 横轴 = x 值
    const datasets = allSeries.map(s => {
      const data = allX.map(xv => {
        const f = gs.find(g => g._p[sk]===s && g._p[xk]===xv);
        return f ? (f[dk] ?? 0) : 0;
      });
      return {
        label: s, data,
        backgroundColor: colors[s] + "cc", borderColor: colors[s],
        borderWidth: 1, borderRadius: 3,
      };
    });
    charts[`${c.chart_id}_${sp}`] = new Chart(ctx, {
      type: "bar", data: { labels: allX, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position:"bottom", labels:{color:"#424a53",font:{size:11},boxWidth:14,boxHeight:14,padding:8} } },
        scales: {
          x: { title:{display:true,text:c.x_label||xk,color:"#656d76"}, ticks:{color:"#57606a",font:{size:10}} },
          y: { beginAtZero:true, max:1, title:{display:true,text:c.y_label||dk,color:"#656d76"}, ticks:{color:"#57606a",font:{size:10},callback:v=>(v*100)+"%"} }
        }
      }
    });
  });

  container.appendChild(inner);
  $("sweep-charts").appendChild(container);
}

function renderSurface3D(c, items) {
  const xk = c.x_key || "updates";
  const yk = c.y_key || "position";
  const dk = c.data_key || "accuracy";
  const sk = c.series_key || "strategy";

  const parsed = items.map(g => ({ ...g, _p: _parseCondId(g.id) }));
  const valid = parsed.filter(g => g._p[xk] !== 0 && g._p[yk]);
  if (!valid.length || typeof Plotly === "undefined") return;
  const xs = _uniqueVals(valid, xk);
  const ys = _uniqueVals(valid, yk);
  // 3D 曲面至少需要 X≥2 且 Y≥2
  if (xs.length < 2 || ys.length < 2) {
    const container = document.createElement("div");
    container.className = "chart-card";
    container.innerHTML = `<header><h3>${c.title}</h3></header><p class=\"muted small\" style=\"padding:16px\">3D曲面需要X≥2且Y≥2维数据。当前Y=\"${yk}\"仅有${ys.length}个值(${ys.join(',')})。跑完位置扫描后自动激活。</p>`;
    $("sweep-charts").appendChild(container);
    return;
  }

  // 所有策略叠加在一个 3D 场景, 用不同颜色区分
  const byStrat = {};
  for (const g of valid) {
    const s = g._p[sk] || "?";
    if (!byStrat[s]) byStrat[s] = [];
    byStrat[s].push(g);
  }

  const traces = [];
  Object.keys(byStrat).forEach((s, si) => {
    const pts = byStrat[s];
    const xsAll = [...new Set(pts.map(p => p._p[xk]))].sort((a,b)=>a-b);
    const ysAll = [...new Set(pts.map(p => p._p[yk]))].sort();
    const z = ysAll.map(yv =>
      xsAll.map(xv => {
        const f = pts.find(p => p._p[xk]===xv && p._p[yk]===yv);
        return f ? (f[dk] ?? 0) : null;
      })
    );
    traces.push({
      type: "surface", x: xsAll, y: ysAll, z,
      name: s, opacity: 0.85,
      colorscale: [[0, `hsl(${si*60},65%,50%)`], [1, `hsl(${si*60},65%,70%)`]],
      showscale: false,
      contours: { z: { show: true, usecolormap: true, project: { z: true } } },
    });
  });

  const layout = {
    scene: {
      xaxis: { title: c.x_label || xk },
      yaxis: { title: c.y_label || yk },
      zaxis: { title: dk },
      camera: { eye: { x: 1.8, y: -1.8, z: 1.0 } },
    },
    legend: { x: 0, y: 1, font: { size: 11 } },
    margin: { l: 0, r: 0, t: 30, b: 0 },
    height: 520,
  };

  const container = document.createElement("div");
  container.className = "chart-card";
  const divId = `plotly-${c.chart_id}`;
  container.innerHTML = `<header><h3>${c.title}</h3><span class="muted small">X=${c.x_label||xk} Y=${c.y_label||yk} Z=${dk}, 颜色=策略</span></header><div id="${divId}"></div>`;
  $("sweep-charts").appendChild(container);
  Plotly.newPlot(divId, traces, layout, { responsive: true, displayModeBar: true });
}

// ═══════════════════════════════════════════════════════
// Builder: 表格 (从 ColumnSpec, 带排序 + 导出)
// ═══════════════════════════════════════════════════════
function renderTable(items) {
  const cols = spec.columns || [{ key: "accuracy", label: "指标", fmt: ".3f" }];
  filterText = $("filter-input")?.value || "";
  const sorted = filteredItems(); _curItems = items;
  const visibleCols = (spec.columns || []).filter(c => !hiddenCols.has(c.key));
  $("table-title").innerHTML = `详情 <button class="sm" onclick="exportCSV()" title="导出 CSV">⬇ 导出</button>`;
  const thead = $("detail-table").querySelector("thead");
  thead.innerHTML = "<tr><th>条件</th>" + visibleCols.map(c =>
    `<th class="sortable">${c.label}${sortIndicatorHTML(c.key)}</th>`
  ).join("") + "</tr>";
  const tbody = $("detail-table").querySelector("tbody"); tbody.innerHTML = "";
  for (const g of sorted) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${g.id}</td>` + visibleCols.map(c => `<td class="num">${fmtV(g[c.key], c.fmt)}</td>`).join("");
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
  try { const s = await api(`/api/status?module=${selMod}`); const d = $("status-pill"), t = $("status-text"); d.classList.toggle("on", s.running); d.classList.toggle("off", !s.running); t.textContent = s.running ? "运行中" : "空闲"; $("live-state").textContent = s.running ? "运行中" : "空闲"; $("live-group").textContent = s.current_group || "—"; $("live-progress").textContent = s.records_total ? `${s.records_done}/${s.records_total}` : `${s.records_done || 0}`; $("live-tag").textContent = s.latest_run || "—"; $("live-log").textContent = s.log_tail || "（暂无日志）"; $("live-log").scrollTop = $("live-log").scrollHeight;     const myRunning = (s.running_modules || []).includes(selMod);
    $("force-stop-btn").disabled = !myRunning;
    $("launch-btn") && ($("launch-btn").disabled = myRunning); } catch (e) { }
}, 3000);

$("force-stop-btn").onclick = async () => {
  if (!confirm("强制停止并删除当前 run?")) return;
  try { const r = await api(`/api/force-stop?module=${selMod}`, { method: "POST" }); $("force-stop-msg").textContent = r.killed?.length ? `已停止 ${selMod}` : "无运行进程"; } catch (e) { }
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
