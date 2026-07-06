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
    if (btn.dataset.tab === "launch") { renderLaunchGroups(); renderProfileDropdown(); }
    if (btn.dataset.tab === "settings") renderSettingsProfiles();
  };
});

function tagClass(id) {
  if (id.startsWith("S"))  return "tag tag-g";
  if (id.startsWith("G0")) return "tag tag-n";
  if (id.startsWith("G2")) return "tag tag-g";
  if (id.startsWith("G4") || id.startsWith("G5")) return "tag tag-r";
  if (id.startsWith("G6") || id.startsWith("G8")) return "tag tag-v";
  return "tag tag-a";
}
function groupColor(id) {
  if (id.startsWith("G8")) return "#1f7a8c";
  if (id.startsWith("G0")) return "#8c959f";
  if (id.startsWith("G2")) return "#0969da";
  if (id.startsWith("G4") || id.startsWith("G5")) return "#cf222e";
  if (id.startsWith("G6")) return "#1a7f37";
  if (id.startsWith("S"))  return "#0969da";
  return "#57606a";
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
  } catch (e) {}
}
setInterval(refreshLive, 3000); refreshLive();

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
    tr.innerHTML = `<td><span class="${tagClass(g.id)}">${g.id}</span></td><td>${g.name}</td>
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
  const cols = ["G0","G1","G2","G3","G4","G5","G6","G7","G8","S3","S5"].filter(g=>gids.has(g));
  let html = `<thead><tr><th>组 \\ run</th>`;
  for (const tag of checked) {
    const r = data[tag]; if (!r) continue;
    html += `<th><div class="cth-tag">${tag}</div><div class="cth-meta">${r.model||""} · ${(r.pi_test||{}).n_keys||""}×${(r.pi_test||{}).updates_per_key||""}</div><div class="cth-base">基线 ${((r.baseline_acc||0)*100).toFixed(1)}%</div></th>`;
  }
  html += "</tr></thead><tbody>";
  for (const gid of cols) {
    let row = `<tr><td><span class="${tagClass(gid)}">${gid}</span></td>`;
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
      <div class="profile-detail"><span class="muted">api_key</span><code>${p.api_key}</code></div>`;
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
  };
  if (!body.name || !body.base_url || !body.api_key) {
    $("p-msg").textContent = "name / base_url / api_key 不能为空"; return;
  }
  $("p-msg").textContent = "保存中…";
  try {
    const r = await fetchJSON("/api/profiles", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
    $("p-msg").textContent = r.ok ? `已保存「${r.name}」` : (`失败:${r.error}`);
    if (r.ok) { $("p-name").value = $("p-baseurl").value = $("p-apikey").value = $("p-model").value = ""; renderSettingsProfiles(); }
  } catch (e) { $("p-msg").textContent = `错误:${e.message}`; }
};

// ====================== 启动 ======================
let groupInfo = [];
async function renderLaunchGroups() {
  if (!groupInfo.length) groupInfo = (await fetchJSON("/api/groups")).groups;
  const box = $("launch-groups"); box.innerHTML = "";
  for (const g of groupInfo) {
    const lbl = document.createElement("label"); lbl.className = "group-item";
    const checked = (g.id === "G0") ? "checked" : "";
    lbl.innerHTML = `
      <input type="checkbox" value="${g.id}" ${checked}>
      <div class="group-item-body">
        <div class="group-item-head"><span class="${tagClass(g.id)}">${g.id}</span><span class="group-item-name">${g.name}</span></div>
        <div class="group-item-desc">${g.desc}</div>
      </div>`;
    box.appendChild(lbl);
  }
}

$("launch-btn").onclick = async () => {
  const groups = [...document.querySelectorAll("#launch-groups input:checked")].map(e=>e.value);
  if (!groups.includes("G0")) groups.unshift("G0");
  const body = {
    profile: $("f-profile").value,
    groups,
    n_keys: +$("f-nkeys").value || undefined,
    updates_per_key: +$("f-updates").value || undefined,
    n_trials: +$("f-trials").value || undefined,
    k_repeats: +$("f-krepeats").value || undefined,
  };
  $("launch-msg").textContent = "启动中…";
  try {
    const r = await fetchJSON("/api/launch", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
    if (r.launched) {
      $("launch-msg").textContent = `已启动[${r.profile} / ${r.model}]:${r.groups.join(", ")}`;
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
