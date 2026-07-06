// PI 释放实验 · 控制台前端
const $ = (id) => document.getElementById(id);
const fmt = (x, d = 3) => (x === null || x === undefined || isNaN(x)) ? "—" : Number(x).toFixed(d);
const pct = (x) => (x === null || x === undefined || isNaN(x)) ? "—" : (Number(x) * 100).toFixed(1) + "%";

async function fetchJSON(url, opts) {
  const r = await fetch(url, { cache: "no-store", ...opts });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

// ---------- tabs ----------
document.querySelectorAll(".tab").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    $(`tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "compare") renderComparePicker();
    if (btn.dataset.tab === "launch") renderLaunchGroups();
  };
});

// ---------- group color ----------
function groupColor(id) {
  if (id.startsWith("G0")) return "#8c959f";
  if (id.startsWith("G1")) return "#636c76";
  if (id.startsWith("G2")) return "#0969da";
  if (id.startsWith("G3")) return "#8250df";
  if (id.startsWith("G4")) return "#cf222e";
  if (id.startsWith("G5")) return "#bf8700";
  if (id.startsWith("G6")) return "#1a7f37";
  if (id.startsWith("G7")) return "#0550ae";
  if (id.startsWith("G8")) return "#1f7a8c";
  if (id.startsWith("S"))  return "#0969da";
  return "#57606a";
}
function tagClass(id) {
  if (id.startsWith("S"))  return "tag tag-g";
  if (id.startsWith("G0")) return "tag tag-n";
  if (id.startsWith("G2")) return "tag tag-g";
  if (id.startsWith("G4") || id.startsWith("G5")) return "tag tag-r";
  if (id.startsWith("G6") || id.startsWith("G8")) return "tag tag-v";
  return "tag tag-a";
}
function reColor(re) {
  if (re === null || re === undefined || isNaN(re)) return "var(--muted)";
  if (re >= 0.5) return "var(--green)";
  if (re >= 0.2) return "var(--amber)";
  if (re >= 0.05) return "var(--amber)";
  return "var(--red)";
}

// ====================== 实时 ======================
let liveTimer = null;
async function refreshLive() {
  try {
    const s = await fetchJSON("/api/status");
    const pill = $("status-pill"), stxt = $("status-text");
    if (s.running) {
      pill.classList.add("on"); pill.classList.remove("off");
      stxt.textContent = "运行中";
    } else {
      pill.classList.add("off"); pill.classList.remove("on");
      stxt.textContent = "空闲";
    }
    $("live-state").textContent  = s.running ? "运行中" : "空闲";
    $("live-group").textContent  = s.current_group || "—";
    const tot = s.records_total;
    $("live-progress").textContent = tot ? `${s.records_done}/${tot}` : `${s.records_done}`;
    $("live-tag").textContent = s.latest_run || "—";
    $("live-log").textContent = s.log_tail || "（暂无日志）";
    $("live-log").scrollTop = $("live-log").scrollHeight;
  } catch (e) { /* ignore */ }
}
liveTimer = setInterval(refreshLive, 3000);
refreshLive();

// ====================== 结果 ======================
let charts = {};
async function loadRunsList() {
  const runs = await fetchJSON("/api/runs");
  const sel = $("run-select");
  sel.innerHTML = "";
  if (!runs.length) {
    $("results-empty").classList.remove("hidden");
    $("results-content").classList.add("hidden");
    return;
  }
  $("results-empty").classList.add("hidden");
  $("results-content").classList.remove("hidden");
  for (const r of runs) {
    const o = document.createElement("option");
    o.value = r.tag;
    const pi = r.pi_test || {};
    o.textContent = `${r.tag} · ${r.model} · ${(r.baseline_acc*100).toFixed(1)}% · ${pi.n_keys||"?"}×${pi.updates_per_key||"?"}`;
    sel.appendChild(o);
  }
  sel.onchange = () => loadRun(sel.value);
  if (sel.value) loadRun(sel.value);
}

async function loadRun(tag) {
  if (!tag) return;
  const s = await fetchJSON(`/api/run/${tag}`);
  $("meta-model").textContent = `模型:${s.model}`;
  $("meta-pi").textContent    = `PI:${s.pi_test.n_keys}×${s.pi_test.updates_per_key},${s.pi_test.n_trials}试次`;
  $("meta-calls").textContent = `${sum(s.groups, g=>g.n_calls||0)} 次调用`;
  renderKPIs(s);
  renderCharts(s);
  renderDetail(s);
}
function sum(arr, f) { return arr.reduce((a,b)=>a+(f?f(b):b),0); }

function renderKPIs(s) {
  const groups = s.groups || [];
  const baseline = s.baseline_acc ?? 0;
  const withRE = groups.filter(g => g.id !== "G0");
  const best = withRE.reduce((a, b) => ((b.re||0) > (a?.re||0) ? b : a), null);
  $("kpi-baseline").textContent = pct(baseline);
  $("kpi-best-re").textContent = best ? fmt(best.re) : "—";
  $("kpi-best-group").textContent = best ? best.id : "—";
  const cps = groups.map(g=>g.cp).filter(x=>x!==null&&x!==undefined);
  $("kpi-cp").textContent = cps.length ? pct(cps.reduce((a,b)=>a+b,0)/cps.length) : "—";
}

const LIGHT = {
  grid: "rgba(31,35,40,0.08)", tick: "#57606a",
  tooltip: { backgroundColor:"#fff", borderColor:"#d0d7de", borderWidth:1, titleColor:"#1f2328", bodyColor:"#424a53", boxPadding:4, cornerRadius:6 },
};
function renderCharts(s) {
  Object.values(charts).forEach(c => c?.destroy()); charts = {};
  const groups = s.groups || [];
  const labels = groups.map(g => g.id);
  const scales = {
    x: { ticks:{color:LIGHT.tick,font:{size:12}}, grid:{display:false}, border:{color:"#d0d7de"} },
    y: { beginAtZero:true, max:1, ticks:{color:LIGHT.tick,callback:v=>(v*100)+"%"}, grid:{color:LIGHT.grid}, border:{display:false} },
  };
  const legend = { labels:{color:"#424a53",font:{size:12},boxWidth:12,boxHeight:12} };
  charts.main = new Chart($("chart-main").getContext("2d"), {
    type: "bar",
    data: { labels, datasets: [
      { label:"准确率", data:groups.map(g=>g.accuracy??0),
        backgroundColor:groups.map(g=>groupColor(g.id)+"22"), borderColor:groups.map(g=>groupColor(g.id)), borderWidth:1.5, borderRadius:3 },
      { label:"RE", data:groups.map(g=>g.re??0), backgroundColor:groups.map(g=>groupColor(g.id)), borderRadius:3 },
    ]},
    options:{ responsive:true, plugins:{legend,tooltip:LIGHT.tooltip}, scales }
  });
  charts.cp = new Chart($("chart-cp").getContext("2d"), {
    type:"bar",
    data:{ labels, datasets:[
      { label:"CP", data:groups.map(g=>g.cp??0),
        backgroundColor:groups.map(g=>(g.cp>0.5?"#dafbe1":"#ffebe9")),
        borderColor:groups.map(g=>(g.cp>0.5?"#1a7f37":"#cf222e")), borderWidth:1.2, borderRadius:3 },
      { label:"鲁棒性Δ", data:groups.map(g=>g.robustness_delta??0), backgroundColor:"#fff8c5", borderColor:"#bf8700", borderWidth:1.2, borderRadius:3 },
    ]},
    options:{ responsive:true, plugins:{legend,tooltip:LIGHT.tooltip}, scales }
  });
}
function renderDetail(s) {
  const tb = $("detail-table").querySelector("tbody"); tb.innerHTML = "";
  for (const g of (s.groups||[])) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><span class="${tagClass(g.id)}">${g.id}</span></td>
      <td>${g.name}</td>
      <td class="num">${pct(g.accuracy)}</td>
      <td class="num" style="color:${reColor(g.re)};font-weight:600">${fmt(g.re)}</td>
      <td class="num">${pct(g.cp)}</td>
      <td class="num">${fmt(g.robustness_delta)}</td>
      <td class="num">${g.n_calls||"—"}</td>`;
    tb.appendChild(tr);
  }
}

// ====================== 对比 ======================
let compareRuns = [];
async function renderComparePicker() {
  if (!compareRuns.length) {
    compareRuns = await fetchJSON("/api/runs");
  }
  const pk = $("compare-picker"); pk.innerHTML = "";
  if (!compareRuns.length) {
    pk.innerHTML = '<p class="muted small">暂无 run。</p>'; return;
  }
  for (const r of compareRuns) {
    const pi = r.pi_test || {};
    const id = `cmp-${r.tag}`;
    const lbl = document.createElement("label"); lbl.className = "picker-item";
    lbl.innerHTML = `<input type="checkbox" id="${id}" data-tag="${r.tag}">
      <span class="picker-tag">${r.tag}</span>
      <span class="picker-meta">${r.model} · ${pi.n_keys||"?"}×${pi.updates_per_key||"?"} · 基线 ${(r.baseline_acc*100).toFixed(1)}%</span>`;
    lbl.querySelector("input").onchange = renderCompare;
    pk.appendChild(lbl);
  }
}

async function renderCompare() {
  const checked = [...document.querySelectorAll("#compare-picker input:checked")].map(e => e.dataset.tag);
  const table = $("compare-table");
  if (checked.length === 0) { table.innerHTML = '<caption class="muted">勾选上方 run 生成对比</caption>'; return; }
  const data = await fetchJSON(`/api/compare?tags=${encodeURIComponent(checked.join(","))}`);
  const showRE = $("compare-re").checked;
  // collect union of group ids
  const gids = new Set();
  Object.values(data).forEach(r => Object.keys(r.groups).forEach(g => gids.add(g)));
  const cols = ["G0","G1","G2","G3","G4","G5","G6","G7","G8","S3","S5"].filter(g => gids.has(g));

  let head = `<thead><tr><th>组 \\ run</th>`;
  for (const tag of checked) {
    const r = data[tag]; if (!r) continue;
    head += `<th><div class="cth-tag">${tag}</div><div class="cth-meta">${r.model||""} · ${(r.pi_test||{}).n_keys||""}×${(r.pi_test||{}).updates_per_key||""}</div><div class="cth-base">基线 ${(r.baseline_acc*100).toFixed(1)}%</div></th>`;
  }
  head += "</tr></thead><tbody>";
  for (const gid of cols) {
    let row = `<tr><td><span class="${tagClass(gid)}">${gid}</span></td>`;
    for (const tag of checked) {
      const r = data[tag]; const g = r?.groups?.[gid];
      if (!g) { row += `<td class="num muted">—</td>`; continue; }
      const val = showRE ? (g.re ?? 0) : (g.accuracy ?? 0);
      const base = showRE ? 0.5 : 0.3;
      const color = (g.accuracy===null||g.accuracy===undefined) ? "var(--muted)"
        : (val >= base*1.5 ? "var(--green)" : val < base*0.5 ? "var(--red)" : "var(--text-2)");
      row += `<td class="num" style="color:${color};font-weight:600">${showRE?fmt(g.re):pct(g.accuracy)}</td>`;
    }
    row += "</tr>";
    head += row;
  }
  head += "</tbody>";
  table.innerHTML = head;
}

// compare-re checkbox change
$("compare-re").onchange = renderCompare;

// ====================== 启动 ======================
let knownGroups = [];
async function renderLaunchGroups() {
  if (!knownGroups.length) {
    const r = await fetchJSON("/api/groups");
    knownGroups = r.groups;
  }
  const box = $("launch-groups"); box.innerHTML = "";
  for (const g of knownGroups) {
    const lbl = document.createElement("label"); lbl.className = "gc-item";
    const checked = (g === "G0") ? "checked" : "";
    lbl.innerHTML = `<input type="checkbox" value="${g}" ${checked}><span class="${tagClass(g)}">${g}</span>`;
    box.appendChild(lbl);
  }
}

$("launch-btn").onclick = async () => {
  const groups = [...document.querySelectorAll("#launch-groups input:checked")].map(e => e.value);
  if (!groups.includes("G0")) groups.unshift("G0");
  const body = {
    model: $("f-model").value.trim() || undefined,
    groups,
    n_keys: +$("f-nkeys").value || undefined,
    updates_per_key: +$("f-updates").value || undefined,
    n_trials: +$("f-trials").value || undefined,
    k_repeats: +$("f-krepeats").value || undefined,
  };
  $("launch-msg").textContent = "启动中…";
  try {
    const r = await fetchJSON("/api/launch", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body),
    });
    if (r.launched) {
      $("launch-msg").textContent = `已启动:${r.groups.join(", ")}`;
      // switch to live tab
      document.querySelector('.tab[data-tab="live"]').click();
      refreshLive();
    } else {
      $("launch-msg").textContent = `失败:${r.error}`;
    }
  } catch (e) { $("launch-msg").textContent = `错误:${e.message}`; }
};

// poll launch-warn (is something already running?)
setInterval(async () => {
  try {
    const s = await fetchJSON("/api/status");
    $("launch-warn").textContent = s.running ? "⚠ 已有 run 在跑,启动会被拒绝" : "";
    $("launch-btn").disabled = s.running;
  } catch {}
}, 3000);

// init
loadRunsList();
