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
    if (btn.dataset.tab === "launch") { renderTaskComposer(); renderProfileDropdown(); }
    if (btn.dataset.tab === "settings") renderSettingsProfiles();
  };
});

function groupColor(id) {
  const g = groupInfo.find(x => x.id === id);
  return (g && g.color) || "#57606a";
}
function badge(id) {
  return `<span class="tag tag-dyn" style="--c:${groupColor(id)}">${id}</span>`;
}
function reColor(re) {
  if (re === null || re === undefined || isNaN(re)) return "var(--muted)";
  if (re >= 0.2) return "var(--green)";
  if (re >= 0.05) return "var(--amber)";
  return "var(--red)";
}

// ====================== 实时 ======================
async function refreshLive() {
  try {
    const s = await fetchJSON("/api/status");
    const pill = $("status-pill"), stxt = $("status-text");
    pill.classList.toggle("on", s.running); pill.classList.toggle("off", !s.running);
    stxt.textContent = s.running ? "运行中" : "空闲";
    $("live-state").textContent  = s.running ? "运行中" : "空闲";
    $("live-group").textContent  = s.current_group || "—";
    $("live-progress").textContent = s.records_total != null ? `${s.records_done}/${s.records_total}` : `${s.records_done}`;
    $("live-tag").textContent = s.latest_run || "—";
    $("live-log").textContent = s.log_tail || "（暂无日志）";
    $("live-log").scrollTop = $("live-log").scrollHeight;
    const fsb = $("force-stop-btn"); if (fsb) fsb.disabled = !s.running;
  } catch (e) {}
}
setInterval(refreshLive, 3000); refreshLive();

$("force-stop-btn").onclick = async () => {
  if (!confirm("强制停止运行中的进程并删除其 run 目录?此操作不可撤销。")) return;
  $("force-stop-msg").textContent = "处理中…";
  try {
    const r = await fetchJSON("/api/force-stop", {method: "POST"});
    const parts = [];
    if (r.killed && r.killed.length) parts.push(`已杀进程 ${r.killed.join(", ")}`);
    if (r.deleted) parts.push(`已删除 ${r.deleted}`);
    if (!parts.length) parts.push("没有运行中的进程或未完成目录");
    $("force-stop-msg").textContent = parts.join(" · ");
    refreshLive();
  } catch (e) { $("force-stop-msg").textContent = `错误:${e.message}`; }
};

// ====================== 结果 ======================
let charts = {};
async function loadRunsList() {
  const runs = await fetchJSON("/api/runs");
  const sel = $("run-select"); sel.innerHTML = "";
  if (!runs.length) { $("results-empty").classList.remove("hidden"); $("results-content").classList.add("hidden"); return; }
  $("results-empty").classList.add("hidden"); $("results-content").classList.remove("hidden");
  for (const r of runs) {
    const o = document.createElement("option"); o.value = r.tag;
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
  $("meta-pi").textContent = `PI:${s.pi_test.n_keys}×${s.pi_test.updates_per_key},${s.pi_test.n_trials}试次`;
  $("meta-calls").textContent = `${s.groups.reduce((a,g)=>a+(g.n_calls||0),0)} 次调用`;
  renderKPIs(s); renderCharts(s); renderDetail(s);
}
function renderKPIs(s) {
  const groups = s.groups || [];
  const baseline = s.baseline_acc ?? 0;
  const best = groups.filter(g=>g.id!=="G0").reduce((a,b)=>((b.re||0)>(a?.re||0)?b:a), null);
  $("kpi-baseline").textContent = pct(baseline);
  $("kpi-best-re").textContent = best ? fmt(best.re) : "—";
  $("kpi-best-group").textContent = best ? best.id : "—";
  const cps = groups.map(g=>g.cp).filter(x=>x!==null&&x!==undefined);
  $("kpi-cp").textContent = cps.length ? pct(cps.reduce((a,b)=>a+b,0)/cps.length) : "—";
}
const LIGHT = { grid:"rgba(31,35,40,0.08)", tick:"#57606a",
  tooltip:{backgroundColor:"#fff",borderColor:"#d0d7de",borderWidth:1,titleColor:"#1f2328",bodyColor:"#424a53",boxPadding:4,cornerRadius:6}};
function renderCharts(s) {
  Object.values(charts).forEach(c=>c?.destroy()); charts = {};
  const groups = s.groups || []; const labels = groups.map(g=>g.id);
  const scales = { x:{ticks:{color:LIGHT.tick,font:{size:12}},grid:{display:false},border:{color:"#d0d7de"}},
    y:{beginAtZero:true,max:1,ticks:{color:LIGHT.tick,callback:v=>(v*100)+"%"},grid:{color:LIGHT.grid},border:{display:false}}};
  const legend = {labels:{color:"#424a53",font:{size:12},boxWidth:12,boxHeight:12}};
  charts.main = new Chart($("chart-main").getContext("2d"), {type:"bar",data:{labels,datasets:[
    {label:"准确率",data:groups.map(g=>g.accuracy??0),backgroundColor:groups.map(g=>groupColor(g.id)+"22"),borderColor:groups.map(g=>groupColor(g.id)),borderWidth:1.5,borderRadius:3},
    {label:"RE",data:groups.map(g=>g.re??0),backgroundColor:groups.map(g=>groupColor(g.id)),borderRadius:3},
  ]},options:{responsive:true,plugins:{legend,tooltip:LIGHT.tooltip},scales}});
  charts.cp = new Chart($("chart-cp").getContext("2d"), {type:"bar",data:{labels,datasets:[
    {label:"CP",data:groups.map(g=>g.cp??0),backgroundColor:groups.map(g=>(g.cp>0.5?"#dafbe1":"#ffebe9")),borderColor:groups.map(g=>(g.cp>0.5?"#1a7f37":"#cf222e")),borderWidth:1.2,borderRadius:3},
    {label:"鲁棒性Δ",data:groups.map(g=>g.robustness_delta??0),backgroundColor:"#fff8c5",borderColor:"#bf8700",borderWidth:1.2,borderRadius:3},
  ]},options:{responsive:true,plugins:{legend,tooltip:LIGHT.tooltip},scales}});
}
function renderDetail(s) {
  const tb = $("detail-table").querySelector("tbody"); tb.innerHTML="";
  for (const g of (s.groups||[])) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${badge(g.id)}</td><td>${g.name}</td>
      <td class="num">${pct(g.accuracy)}</td>
      <td class="num" style="color:${reColor(g.re)};font-weight:600">${fmt(g.re)}</td>
      <td class="num">${pct(g.cp)}</td><td class="num">${fmt(g.robustness_delta)}</td><td class="num">${g.n_calls||"—"}</td>`;
    tb.appendChild(tr);
  }
}

// ====================== 对比 ======================
let compareRuns = [];
async function renderComparePicker() {
  if (!compareRuns.length) compareRuns = await fetchJSON("/api/runs");
  const pk = $("compare-picker"); pk.innerHTML = "";
  if (!compareRuns.length) { pk.innerHTML = '<p class="muted small">暂无 run。</p>'; return; }
  for (const r of compareRuns) {
    const pi = r.pi_test || {};
    const lbl = document.createElement("label"); lbl.className = "picker-item";
    lbl.innerHTML = `<input type="checkbox" data-tag="${r.tag}">
      <span class="picker-tag">${r.tag}</span>
      <span class="picker-meta">${r.model} · ${pi.n_keys||"?"}×${pi.updates_per_key||"?"} · 基线 ${(r.baseline_acc*100).toFixed(1)}%</span>`;
    lbl.querySelector("input").onchange = renderCompare;
    pk.appendChild(lbl);
  }
}
async function renderCompare() {
  const checked = [...document.querySelectorAll("#compare-picker input:checked")].map(e=>e.dataset.tag);
  const table = $("compare-table");
  if (!checked.length) { table.innerHTML = '<caption class="muted">勾选上方 run 生成对比</caption>'; return; }
  const data = await fetchJSON(`/api/compare?tags=${encodeURIComponent(checked.join(","))}`);
  const showRE = $("compare-re").checked;
  const gids = new Set();
  Object.values(data).forEach(r=>Object.keys(r.groups).forEach(g=>gids.add(g)));
  // rows = package group order (dynamic, includes G9+) ∩ present, then any leftover
  if (!groupInfo.length) groupInfo = (await fetchJSON("/api/groups")).groups;
  const cols = groupInfo.map(g=>g.id).filter(g=>gids.has(g));
  for (const g of [...gids].sort()) if (!cols.includes(g)) cols.push(g);
  let html = `<thead><tr><th>组 \\ run</th>`;
  for (const tag of checked) {
    const r = data[tag]; if (!r) continue;
    html += `<th><div class="cth-tag">${tag}</div><div class="cth-meta">${r.model||""} · ${(r.pi_test||{}).n_keys||""}×${(r.pi_test||{}).updates_per_key||""}</div><div class="cth-base">基线 ${((r.baseline_acc||0)*100).toFixed(1)}%</div></th>`;
  }
  html += "</tr></thead><tbody>";
  for (const gid of cols) {
    let row = `<tr><td>${badge(gid)}</td>`;
    for (const tag of checked) {
      const g = data[tag]?.groups?.[gid];
      if (!g) { row += `<td class="num muted">—</td>`; continue; }
      const val = showRE ? (g.re ?? 0) : (g.accuracy ?? 0);
      const color = val>=0.5?"var(--green)":val<0.2?"var(--red)":"var(--text-2)";
      row += `<td class="num" style="color:${color};font-weight:600">${showRE?fmt(g.re):pct(g.accuracy)}</td>`;
    }
    html += row + "</tr>";
  }
  table.innerHTML = html + "</tbody>";
}
$("compare-re").onchange = renderCompare;

// ====================== profiles ======================
let profiles = [];
async function loadProfiles() {
  const r = await fetchJSON("/api/profiles");
  profiles = r.profiles || [];
  return profiles;
}

async function renderProfileDropdown() {
  if (!profiles.length) await loadProfiles();
  const sel = $("f-profile"); sel.innerHTML = "";
  if (!profiles.length) {
    sel.innerHTML = "<option>（先在「设置」加一个配置）</option>";
    $("f-profile-info").textContent = "";
    return;
  }
  for (const p of profiles) {
    const o = document.createElement("option");
    o.value = p.name;
    o.textContent = `${p.name} · ${p.model} · ${p.api_key}`;
    sel.appendChild(o);
  }
  sel.onchange = () => {
    const p = profiles.find(x=>x.name===sel.value);
    $("f-profile-info").textContent = p ? `${p.base_url} · model=${p.model}` : "";
  };
  sel.onchange();
}

async function renderSettingsProfiles() {
  await loadProfiles();
  const box = $("settings-profiles"); box.innerHTML = "";
  if (!profiles.length) {
    box.innerHTML = '<p class="muted small">还没有保存的配置。在下方添加一个。</p>'; return;
  }
  for (const p of profiles) {
    const card = document.createElement("div"); card.className = "profile-card";
    card.innerHTML = `
      <div class="profile-head">
        <span class="profile-name">${p.name}</span>
        <button class="link-btn" data-del="${p.name}">删除</button>
      </div>
      <div class="profile-detail"><span class="muted">base_url</span><code>${p.base_url}</code></div>
      <div class="profile-detail"><span class="muted">model</span><code>${p.model}</code></div>
      <div class="profile-detail"><span class="muted">api_key</span><code>${p.api_key}</code></div>
      ${fmtExtra(p.extra_body) ? `<div class="profile-detail"><span class="muted">额外参数</span><code>${fmtExtra(p.extra_body)}</code></div>` : ""}`;
    card.querySelector("[data-del]").onclick = async () => {
      await fetch(`/api/profiles?name=${encodeURIComponent(p.name)}`, {method:"DELETE"});
      $("p-msg").textContent = `已删除 ${p.name}`;
      renderSettingsProfiles();
    };
    box.appendChild(card);
  }
}

$("p-save").onclick = async () => {
  const body = {
    name: $("p-name").value.trim(),
    base_url: $("p-baseurl").value.trim(),
    api_key: $("p-apikey").value.trim(),
    model: $("p-model").value.trim(),
    extra_body: $("p-extra").value,
  };
  if (!body.name || !body.base_url || !body.api_key) {
    $("p-msg").textContent = "name / base_url / api_key 不能为空"; return;
  }
  $("p-msg").textContent = "保存中…";
  try {
    const r = await fetchJSON("/api/profiles", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
    $("p-msg").textContent = r.ok ? `已保存「${r.name}」` : (`失败:${r.error}`);
    if (r.ok) { $("p-name").value = $("p-baseurl").value = $("p-apikey").value = $("p-model").value = $("p-extra").value = ""; renderSettingsProfiles(); }
  } catch (e) { $("p-msg").textContent = `错误:${e.message}`; }
};

function fmtExtra(eb) {
  if (!eb || typeof eb !== "object" || Object.keys(eb).length === 0) return null;
  // render nested dict as "key: sub: val" style lines
  const lines = [];
  for (const [k, v] of Object.entries(eb)) {
    if (v && typeof v === "object") {
      for (const [k2, v2] of Object.entries(v)) lines.push(`${k}.${k2}: ${v2}`);
    } else {
      lines.push(`${k}: ${v}`);
    }
  }
  return lines.join(" · ");
}

// ====================== 启动 ======================
let groupInfo = [];
// ---------- task composer (launch) ----------
// A task = ordered feature list (empty = baseline). Drag features from the
// palette into a task card; drag chips within/across cards to reorder.
let composerTasks = [{ features: ["G2"], name: "" }];
let dragState = null;  // {source: "palette"|"task", taskId?, idx?, feature}

async function renderTaskComposer() {
  if (!groupInfo.length) {
    try { groupInfo = (await fetchJSON("/api/groups")).groups || []; } catch {}
  }
  renderPalette();
  renderPaletteDetail();
  renderTaskList();
}

function chipColor(g) { return (g && g.color) ? g.color : "#57606a"; }

let selectedFeature = null;

function renderPalette() {
  const pal = $("palette"); if (!pal) return;
  pal.innerHTML = "";
  const feats = groupInfo.filter(g => g.id !== "G0");  // G0 = empty task, not draggable
  for (const g of feats) {
    const chip = document.createElement("span");
    chip.className = "chip chip-drag" + (g.position === "end" ? " chip-end" : "")
                   + (selectedFeature === g.id ? " chip-selected" : "");
    chip.style.setProperty("--c", chipColor(g));
    chip.draggable = true;
    chip.textContent = g.id;
    chip.title = "点击查看说明 / 拖到任务框";
    chip.ondragstart = (e) => { dragState = { source: "palette", feature: g.id }; e.dataTransfer.effectAllowed = "copy"; };
    chip.ondragend = () => { dragState = null; };
    chip.onclick = () => {
      selectedFeature = (selectedFeature === g.id) ? null : g.id;
      renderPalette();
      renderPaletteDetail();
    };
    pal.appendChild(chip);
  }
}

function renderPaletteDetail() {
  const box = $("palette-detail"); if (!box) return;
  if (!selectedFeature) {
    box.innerHTML = `<span class="muted small">点击上方 feature 查看说明,或直接拖到任务框。</span>`;
    return;
  }
  const g = groupInfo.find(x => x.id === selectedFeature);
  if (!g) { box.innerHTML = ""; return; }
  const posLabel = g.position === "end" ? "末尾注入" : "流中段注入";
  box.innerHTML = `
    <div class="palette-detail-head">
      <span class="chip" style="--c:${chipColor(g)}">${g.id}</span>
      <span class="palette-detail-name">${g.name}</span>
      <span class="palette-detail-pos muted small">${posLabel}</span>
    </div>
    <div class="palette-detail-desc">${g.desc || "(无说明)"}</div>`;
}

function renderTaskList() {
  const list = $("task-list"); if (!list) return;
  list.innerHTML = "";
  composerTasks.forEach((task, ti) => {
    const card = document.createElement("div");
    card.className = "task-card";

    const head = document.createElement("div");
    head.className = "task-head";
    const tid = task.features.length ? task.features.join("+") : "G0";
    const idSpan = document.createElement("span");
    idSpan.className = "task-id"; idSpan.textContent = tid;
    const nameIn = document.createElement("input");
    nameIn.className = "task-name"; nameIn.placeholder = "任务名(可选)";
    nameIn.value = task.name || "";
    nameIn.oninput = (e) => { task.name = e.target.value; };
    head.appendChild(idSpan); head.appendChild(nameIn);
    if (composerTasks.length > 1) {
      const rm = document.createElement("button");
      rm.className = "ghost tiny"; rm.textContent = "删除";
      rm.onclick = () => { composerTasks.splice(ti, 1); renderTaskList(); };
      head.appendChild(rm);
    }
    card.appendChild(head);

    const row = document.createElement("div");
    row.className = "task-chips";
    row.ondragover = (e) => { e.preventDefault(); row.classList.add("drag-over"); };
    row.ondragleave = (e) => { if (!row.contains(e.relatedTarget)) row.classList.remove("drag-over"); };
    row.ondrop = (e) => {
      e.preventDefault(); row.classList.remove("drag-over");
      if (!dragState) return;
      if (dragState.source === "palette") {
        task.features.push(dragState.feature);
      } else if (dragState.source === "task") {
        const fromTi = dragState.taskId, fromIdx = dragState.idx;
        let dropIdx = task.features.length;
        const overChip = e.target.closest(".chip-in-task");
        if (overChip) {
          const chips = [...row.querySelectorAll(".chip-in-task")];
          let idx = chips.indexOf(overChip);
          const r = overChip.getBoundingClientRect();
          if (e.clientX > r.left + r.width / 2) idx++;  // past midpoint -> insert after
          dropIdx = idx;
        }
        composerTasks[fromTi].features.splice(fromIdx, 1);
        if (fromTi === ti && fromIdx < dropIdx) dropIdx--;
        task.features.splice(dropIdx, 0, dragState.feature);
      }
      dragState = null;
      renderTaskList();
    };

    if (task.features.length === 0) {
      const ph = document.createElement("span");
      ph.className = "muted small task-empty";
      ph.textContent = "空任务 = 基线(无干预)。拖 feature 进来组合。";
      row.appendChild(ph);
    } else {
      task.features.forEach((fid, idx) => {
        const g = groupInfo.find(x => x.id === fid) || { id: fid };
        const chip = document.createElement("span");
        chip.className = "chip chip-in-task" + (g.position === "end" ? " chip-end" : "");
        chip.style.setProperty("--c", chipColor(g));
        chip.draggable = true;
        chip.textContent = fid;
        chip.ondragstart = (e) => { dragState = { source: "task", taskId: ti, idx, feature: fid }; e.dataTransfer.effectAllowed = "move"; };
        chip.ondragend = () => { dragState = null; };
        const x = document.createElement("span");
        x.className = "chip-x"; x.textContent = "×"; x.title = "移除";
        x.onclick = (e) => { e.stopPropagation(); task.features.splice(idx, 1); renderTaskList(); };
        chip.appendChild(x);
        row.appendChild(chip);
      });
    }
    card.appendChild(row);
    list.appendChild(card);
  });
}

$("add-task").onclick = () => { composerTasks.push({ features: [], name: "" }); renderTaskList(); };

$("launch-btn").onclick = async () => {
  // send composed tasks; drop empties, but if that leaves nothing, send a baseline-only run
  const sendTasks = composerTasks
    .map(t => ({ features: t.features.filter(f => f), name: t.name }))
    .filter(t => t.features.length > 0);
  if (sendTasks.length === 0) sendTasks.push({ features: [], name: "baseline" });
  const body = {
    profile: $("f-profile").value,
    tasks: sendTasks.map(t => ({ features: t.features, ...(t.name ? { name: t.name } : {}) })),
    n_keys: +$("f-nkeys").value || undefined,
    updates_per_key: +$("f-updates").value || undefined,
    n_trials: +$("f-trials").value || undefined,
    k_repeats: +$("f-krepeats").value || undefined,
  };
  $("launch-msg").textContent = "启动中…";
  try {
    const r = await fetchJSON("/api/launch", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
    if (r.launched) {
      $("launch-msg").textContent = `已启动 [${r.profile} / ${r.model}]:${(r.groups||[]).join(", ")}`;
      document.querySelector('.tab[data-tab="live"]').click();
      refreshLive();
    } else { $("launch-msg").textContent = `失败:${r.error}`; }
  } catch (e) { $("launch-msg").textContent = `错误:${e.message}`; }
};

setInterval(async () => {
  try {
    const s = await fetchJSON("/api/status");
    $("launch-warn").textContent = s.running ? "⚠ 已有 run 在跑,启动会被拒绝" : "";
    $("launch-btn").disabled = s.running;
  } catch {}
}, 3000);

// init
loadRunsList();
loadProfiles();
fetchJSON("/api/groups").then(r => { groupInfo = r.groups || []; }).catch(() => {});
