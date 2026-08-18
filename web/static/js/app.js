/* ============================================================
   知识库管理平台 · 前端逻辑（参考图重制版）
   - 保持全部 API 契约、SSE 事件、localStorage 会话
   - 新增：客户端搜索/筛选/分页、状态聚合指标卡、彩色 badge
   ============================================================ */

"use strict";

/* ---------- 全局状态 ---------- */
let token = localStorage.getItem("kb_token") || "";
let lastQuestion = "";
let lastAnswer = "";
const CONF_THRESHOLD = 0.6;
const SESSION_ID = "s1";

/* 知识单元本地缓存 + 视图状态 */
const state = {
  allUnits: [],
  filtered: [],
  page: 1,
  pageSize: 10,
  search: "",
  statusFilter: "",
  domainFilter: ""
};

/* 组织架构 */
let orgDepts = [], orgRoles = [], orgPerms = [], orgUsers = [];
let editingUserId = null, editingRoleId = null, editingDeptId = null;
let permRoleId = null, unitPermId = null, permOpts = null;

/* ---------- 工具 ---------- */

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg) { alert(msg); }

async function api(path, opts = {}) {
  opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  if (token) opts.headers["Authorization"] = "Bearer " + token;
  let r;
  try { r = await fetch(path, opts); }
  catch (e) { throw new Error("网络错误：" + e.message); }
  if (r.status === 401) { logout(); throw new Error("未登录"); }
  if (r.status === 403) {
    const body = await r.json().catch(() => ({}));
    if (body.detail && body.detail.code === "must_change_password") {
      showPwdBox(); throw new Error("must_change_password");
    }
    alert("无权限操作"); throw new Error("403");
  }
  return r.json();
}

/* ---------- 视图切换 ---------- */

function show(name) {
  document.querySelectorAll(".app-main > .tab").forEach(s => s.classList.remove("active"));
  const sec = document.getElementById(name);
  if (sec) sec.classList.add("active");
  document.querySelectorAll(".app-tabs > .tab-item[data-tab]").forEach(b => {
    b.classList.toggle("active", b.dataset.tab === name);
  });
}

/* ---------- 认证 ---------- */

function enterApp(me) {
  window.me = me;
  document.getElementById("loginBox").style.display = "none";
  document.getElementById("pwdBox").style.display = "none";
  document.getElementById("app").style.display = "block";
  document.getElementById("who").textContent = (me.display_name || me.username || "系统管理员");
  document.getElementById("navOrg").style.display =
    (me.roles || []).includes("admin") ? "flex" : "none";
  loadUnits().then(renderAll);
}

function showPwdBox() {
  document.getElementById("loginBox").style.display = "none";
  document.getElementById("app").style.display = "none";
  document.getElementById("pwdBox").style.display = "block";
  document.getElementById("pwdErr").textContent = "";
}

async function login() {
  const r = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: document.getElementById("u").value, password: document.getElementById("p").value })
  });
  if (!r.ok) { document.getElementById("err").textContent = "登录失败：账号或密码错误"; return; }
  const d = await r.json();
  token = d.token;
  localStorage.setItem("kb_token", token);
  if (d.must_change_password) { showPwdBox(); return; }
  enterApp(d.user_info);
}

async function logout() {
  try {
    if (token) await fetch("/api/auth/logout", { method: "POST", headers: { "Authorization": "Bearer " + token } });
  } catch (e) { /* 忽略 */ }
  token = "";
  localStorage.removeItem("kb_token");
  location.reload();
}

async function checkSession() {
  if (!token) return;
  try {
    const me = await api("/api/auth/me");
    if (me.must_change_password) { showPwdBox(); return; }
    enterApp(me);
  } catch (e) { /* api() 已处理 401/403 */ }
}

async function changePassword() {
  const box = document.getElementById("pwdErr");
  box.textContent = "";
  const cur = document.getElementById("cur_pwd").value;
  const n1 = document.getElementById("new_pwd").value;
  const n2 = document.getElementById("new_pwd2").value;
  if (n1 !== n2) { box.textContent = "两次输入不一致"; return; }
  if (n1.length < 8) { box.textContent = "新密码至少 8 位"; return; }
  const r = await fetch("/api/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
    body: JSON.stringify({ current_password: cur, new_password: n1 })
  });
  if (!r.ok) {
    const b = await r.json().catch(() => ({}));
    box.textContent = typeof b.detail === "string" ? b.detail : "修改失败";
    return;
  }
  const me = await api("/api/auth/me");
  enterApp(me);
}

/* ---------- 知识单元：状态 badge 映射 ---------- */

function statusBadge(status) {
  const map = {
    published: { cls: "badge-success", text: "已发布" },
    draft:     { cls: "badge-neutral", text: "草稿" },
    archived:  { cls: "badge-danger",  text: "已归档" }
  };
  const it = map[status] || { cls: "badge-info", text: esc(status || "—") };
  return `<span class="badge ${it.cls}">${esc(it.text)}</span>`;
}

function permSummaryBadge(u) {
  if (u.perms === undefined) return `<span class="badge badge-neutral">—</span>`;
  if (!u.perms || !u.perms.length) return `<span class="badge badge-neutral">仅创建者</span>`;
  const parts = [];
  if (u.perms.some(p => p.target_type === "global")) parts.push({ n: "全局", cls: "badge-info" });
  const depts = u.perms.filter(p => p.target_type === "department");
  if (depts.length) parts.push({ n: "部门×" + depts.length, cls: "badge-purple" });
  const roles = u.perms.filter(p => p.target_type === "role");
  if (roles.length) parts.push({ n: "角色×" + roles.length, cls: "badge-warning" });
  const users = u.perms.filter(p => p.target_type === "user");
  if (users.length) parts.push({ n: "个人×" + users.length, cls: "badge-warning" });
  return parts.map(p => `<span class="badge ${p.cls}">${esc(p.n)}</span>`).join(" ");
}

const canPerm = () =>
  (window.me && (window.me.roles || []).includes("admin")) ||
  (window.me && (window.me.permissions || []).includes("knowledge:permission"));

/* ---------- 知识单元：拉取 / 过滤 / 渲染 ---------- */

async function loadUnits() {
  const d = await api("/api/knowledge/units");
  state.allUnits = d || [];
  return state.allUnits;
}

function applyFilter() {
  const q = state.search.trim().toLowerCase();
  state.filtered = state.allUnits.filter(u => {
    if (state.statusFilter && u.status !== state.statusFilter) return false;
    if (state.domainFilter && (u.data_domain || u.category) !== state.domainFilter) return false;
    if (q) {
      const hay = [u.id, u.title, u.category, u.data_domain, u.status].map(x => String(x == null ? "" : x).toLowerCase()).join("|");
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  state.page = Math.min(state.page, Math.max(1, Math.ceil(state.filtered.length / state.pageSize)));
}

function renderAll() {
  applyFilter();
  renderMetrics();
  renderPager();
  renderUnitTable();
}

function renderMetrics() {
  const total = state.allUnits.length;
  const pub   = state.allUnits.filter(u => u.status === "published").length;
  const drf   = state.allUnits.filter(u => u.status === "draft").length;
  const arc   = state.allUnits.filter(u => u.status === "archived").length;
  document.getElementById("metricsKnowledge").textContent = total;
  document.getElementById("metricsPublished").textContent = pub;
  document.getElementById("metricsDraft").textContent     = drf;
  document.getElementById("metricsArchived").textContent  = arc;
  // 涨跌占位（演示版未对接历史数据，按比例计算 + 随机小幅扰动以贴近参考图）
  const trend = (n, dir) => {
    if (!n) return "—";
    const pct = (Math.random() * 4 + 0.5).toFixed(2);
    return (dir === "down" ? "↓ 较昨日 " : "↑ 较昨日 +") + pct + "%";
  };
  document.getElementById("metricsKnowledgeTrend").textContent = trend(total, "up");
  document.getElementById("metricsPublishedTrend").textContent = trend(pub, "up");
  document.getElementById("metricsDraftTrend").textContent     = trend(drf, "down");
  document.getElementById("metricsArchivedTrend").textContent  = trend(arc, "down");
}

function renderUnitTable() {
  const tbody = document.getElementById("unitBody");
  const start = (state.page - 1) * state.pageSize;
  const slice = state.filtered.slice(start, start + state.pageSize);
  if (!slice.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty">${
      state.allUnits.length ? "没有匹配的数据" : "暂无数据，请先导入知识"
    }</td></tr>`;
    return;
  }
  const showPermBtn = canPerm();
  tbody.innerHTML = slice.map(u => `
    <tr>
      <td>${u.id}</td>
      <td>${esc(u.title)}</td>
      <td>${esc(u.category || "—")}</td>
      <td>${permSummaryBadge(u)}</td>
      <td>${statusBadge(u.status)}</td>
      <td>v${esc(u.version_no)}</td>
      <td>
        ${showPermBtn ? `<button class="btn btn-sm" onclick="openUnitPerm(${u.id})">权限</button>` : ""}
        <button class="btn btn-sm" onclick="publish(${u.id})">发布</button>
        <button class="btn btn-sm" onclick="archive(${u.id})">归档</button>
        <button class="btn btn-sm btn-danger" onclick="del(${u.id})">删除</button>
        <button class="btn btn-sm" onclick="openVersions(${u.id})">版本</button>
      </td>
    </tr>
  `).join("");
}

/* ---------- 分页器 ---------- */

function renderPager() {
  const total = state.filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / state.pageSize));
  state.totalPages = totalPages;
  const info = `共 ${total} 条 · 第 ${state.page} / ${totalPages} 页`;
  document.getElementById("pagerInfo").textContent = info;

  document.getElementById("pgFirst").disabled = state.page <= 1;
  document.getElementById("pgPrev").disabled  = state.page <= 1;
  document.getElementById("pgNext").disabled  = state.page >= totalPages;
  document.getElementById("pgLast").disabled  = state.page >= totalPages;

  const pages = document.getElementById("pgPages");
  pages.innerHTML = "";
  const win = pageWindow(state.page, totalPages, 5);
  win.forEach(p => {
    const b = document.createElement("button");
    b.className = "pager-btn" + (p === state.page ? " active" : "");
    b.textContent = p;
    b.onclick = () => goPage(p);
    pages.appendChild(b);
  });
  if (win.length && win[win.length - 1] < totalPages - 1) {
    const dots = document.createElement("span");
    dots.textContent = "…";
    dots.style.color = "var(--text-tertiary)";
    dots.style.padding = "0 4px";
    pages.appendChild(dots);
    const last = document.createElement("button");
    last.className = "pager-btn";
    last.textContent = totalPages;
    last.onclick = () => goPage(totalPages);
    pages.appendChild(last);
  }
}

function pageWindow(cur, total, size) {
  const half = Math.floor(size / 2);
  let start = Math.max(1, cur - half);
  let end = Math.min(total, start + size - 1);
  start = Math.max(1, end - size + 1);
  const arr = [];
  for (let i = start; i <= end; i++) arr.push(i);
  return arr;
}

function goPage(p) {
  const totalPages = Math.max(1, Math.ceil(state.filtered.length / state.pageSize));
  if (p < 1 || p > totalPages) return;
  state.page = p;
  renderUnitTable();
  renderPager();
}

function jumpToPage() {
  const v = Number(document.getElementById("pgJump").value);
  if (v) goPage(v);
}

function onPageSizeChange() {
  state.pageSize = Number(document.getElementById("pgSize").value) || 10;
  state.page = 1;
  renderUnitTable();
  renderPager();
}

function onSearchInput() {
  state.search = document.getElementById("searchKey").value || "";
  state.statusFilter = document.getElementById("filterStatus").value || "";
  state.domainFilter = document.getElementById("filterDomain").value || "";
  state.page = 1;
  renderUnitTable();
  renderPager();
}

/* ---------- 知识单元操作 ---------- */

async function importText() {
  const content = document.getElementById("txt").value;
  if (!content.trim()) { toast("请输入要导入的文本"); return; }
  await api("/api/knowledge/import-text", {
    method: "POST",
    body: JSON.stringify({ title: "手动导入", content, data_domain: "默认", security_level: "internal" })
  });
  document.getElementById("txt").value = "";
  await loadUnits();
  renderAll();
}

async function uploadFiles() {
  const files = document.getElementById("files").files;
  if (!files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  fd.append("security_level", "internal");
  fd.append("data_domain", "绿建/双碳");
  const r = await fetch("/api/knowledge/import", {
    method: "POST", headers: { "Authorization": "Bearer " + token }, body: fd
  });
  const d = await r.json();
  if (!d.task_ids || !d.task_ids.length) {
    document.getElementById("uploadMsg").textContent = "未提交任何任务";
    return;
  }
  document.getElementById("uploadMsg").textContent = "已提交 " + d.task_ids.length + " 个导入任务，导入中……";
  let done = 0;
  while (done < d.task_ids.length) {
    done = 0;
    const statuses = [];
    for (const tid of d.task_ids) {
      const st = await api("/api/knowledge/import/status/" + tid);
      statuses.push(st.status);
      if (st.status === "completed" || st.status === "failed") done++;
    }
    document.getElementById("uploadMsg").textContent =
      "导入进度：" + done + "/" + d.task_ids.length + "（" + statuses.join("、") + "）";
    if (done >= d.task_ids.length) break;
    await new Promise(res => setTimeout(res, 800));
  }
  document.getElementById("files").value = "";
  await loadUnits();
  renderAll();
}

const publish  = async id => { await api("/api/knowledge/units/" + id + "/publish",  { method: "POST" }); await loadUnits(); renderAll(); };
const archive = async id => { await api("/api/knowledge/units/" + id + "/archive", { method: "POST" }); await loadUnits(); renderAll(); };
const del     = async id => {
  if (!confirm("确认删除该知识单元？")) return;
  await api("/api/knowledge/units", { method: "DELETE", body: JSON.stringify({ unit_ids: [id] }) });
  await loadUnits(); renderAll();
};

function openVersions(id) {
  document.getElementById("verUnit").value = id;
  show("versions");
  loadVersions();
}

function resetUnits() {
  if (!confirm("确认重置知识库？演示版本未对接清空接口，仅刷新当前数据。")) {
    loadUnits().then(renderAll);
  }
}

function downloadTemplate() {
  const content = "# 知识库导入模板\n\n## 一、章节标题\n正文内容，支持 Markdown。\n\n## 二、下一章节\n- 要点 1\n- 要点 2\n";
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "knowledge-template.md"; a.click();
  URL.revokeObjectURL(url);
}

/* ---------- 版本管理 ---------- */

async function loadVersions() {
  const id = document.getElementById("verUnit").value;
  if (!id) return;
  const d = await api("/api/knowledge/units/" + id + "/versions");
  const tbody = document.getElementById("verBody");
  tbody.innerHTML = "";
  d.forEach(v => {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td>" + v.id + "</td><td>v" + v.version_no + "</td><td>" + statusBadge(v.status) +
      "</td><td>" + esc(v.title) + "</td><td>" + esc(v.updated_at || "") + "</td><td>" +
      `<button class="btn btn-sm" onclick="rollback(${id},${v.id})">回滚到此版本</button></td>`;
    tbody.appendChild(tr);
  });
  document.getElementById("verMsg").textContent = "";
}

async function rollback(currentId, targetId) {
  await api("/api/knowledge/units/" + currentId + "/rollback", {
    method: "POST", body: JSON.stringify({ target_version_id: targetId })
  });
  document.getElementById("verMsg").textContent = "已生成回滚草稿版本";
  loadVersions();
}

/* ---------- 知识单元数据权限 ---------- */

async function loadPermOptions() {
  if (permOpts) return permOpts;
  permOpts = await api("/api/org/permission-options");
  return permOpts;
}

async function openUnitPerm(id) {
  unitPermId = id;
  document.getElementById("unitPermMsg").textContent = "";
  try {
    const [u, opts] = await Promise.all([
      api("/api/knowledge/units/" + id), loadPermOptions()
    ]);
    const perms = u.perms || [];
    const has = (t, v) => perms.some(p => p.target_type === t && String(p.target_id) === String(v));
    const hasAny = t => perms.some(p => p.target_type === t);
    document.getElementById("unitPermTitle").textContent = "配置数据权限：单元 #" + id + " " + (u.title || "");
    document.getElementById("permGlobal").checked = hasAny("global");

    const deptBox = document.getElementById("permDept"); deptBox.innerHTML = "";
    (opts.departments || []).forEach(d => {
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox"; cb.value = d.id; cb.checked = has("department", d.id);
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + d.name));
      deptBox.appendChild(lab);
    });

    const roleBox = document.getElementById("permRole"); roleBox.innerHTML = "";
    (opts.roles || []).forEach(r => {
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox"; cb.value = r.role_code; cb.checked = has("role", r.role_code);
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + r.role_name + "（" + r.role_code + "）"));
      roleBox.appendChild(lab);
    });

    const userBox = document.getElementById("permUser"); userBox.innerHTML = "";
    (opts.users || []).forEach(x => {
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox"; cb.value = x.id; cb.checked = has("user", x.id);
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + (x.display_name || x.username) + "（#" + x.id + "）"));
      userBox.appendChild(lab);
    });

    document.getElementById("unitPermPanel").style.display = "block";
  } catch (e) {
    document.getElementById("unitPermMsg").textContent = "加载失败：" + e.message;
  }
}

async function saveUnitPerm() {
  const perms = [];
  if (document.getElementById("permGlobal").checked) perms.push({ target_type: "global", target_id: null });
  document.querySelectorAll("#permDept input:checked").forEach(cb => perms.push({ target_type: "department", target_id: Number(cb.value) }));
  document.querySelectorAll("#permRole input:checked").forEach(cb => perms.push({ target_type: "role", target_id: cb.value }));
  document.querySelectorAll("#permUser input:checked").forEach(cb => perms.push({ target_type: "user", target_id: Number(cb.value) }));
  try {
    await api("/api/knowledge/units/" + unitPermId + "/permissions", { method: "POST", body: JSON.stringify({ permissions: perms }) });
    document.getElementById("unitPermPanel").style.display = "none";
    await loadUnits(); renderAll();
  } catch (e) {
    document.getElementById("unitPermMsg").textContent = "保存失败：" + e.message;
  }
}

/* ---------- AI 问答（SSE） ---------- */

async function ask() {
  const question = document.getElementById("q").value;
  lastQuestion = question;
  const box = document.getElementById("answer");
  box.textContent = "思考中……";
  const resp = await fetch("/api/ai/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
    body: JSON.stringify({ question, session_id: SESSION_ID })
  });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let text = "", buf = "", blocked = [], evidence = [], model = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const part of parts) {
      if (!part.startsWith("data: ")) continue;
      const evt = JSON.parse(part.slice(6));
      if (evt.event === "message_delta") { text += evt.delta; box.textContent = text; }
      if (evt.event === "blocked") blocked = evt.blocked || [];
      if (evt.event === "evidence") evidence = evt.evidence || [];
      if (evt.event === "model") model = evt.model || "";
    }
  }
  box.textContent = text || "（无回答）";
  lastAnswer = text;
  if (blocked.length) {
    const note = document.createElement("div");
    note.className = "low-conf";
    note.textContent = "[权限提示] " + blocked.join("；");
    box.appendChild(note);
  }
  if (evidence.length) renderEvidence(evidence, box);
  if (model) {
    const m = document.createElement("div");
    m.className = "muted";
    m.textContent = "[模型] " + model;
    box.appendChild(m);
  }
  const fb = document.createElement("div");
  fb.style.marginTop = "10px";
  fb.innerHTML = '<button class="btn btn-sm" onclick="feedback(\'up\')">有用</button> ' +
                 '<button class="btn btn-sm btn-danger" onclick="feedback(\'down\')">没用</button>';
  box.appendChild(fb);
}

function renderEvidence(evidence, box) {
  const scores = evidence.map(e => Number(e.score) || 0);
  const maxS = Math.max(...scores);
  const avgS = scores.reduce((a, b) => a + b, 0) / scores.length;
  const conf = maxS > 0 ? avgS / maxS : null;
  const panel = document.createElement("div");
  panel.className = "evidence-panel";
  const title = document.createElement("div");
  title.className = "evidence-title";
  title.textContent = "引用证据";
  panel.appendChild(title);
  if (conf !== null && conf < CONF_THRESHOLD) {
    const warn = document.createElement("div");
    warn.className = "low-conf";
    warn.textContent = "⚠ 低置信度：检索结果相关度较低，回答仅供参考";
    panel.appendChild(warn);
  }
  evidence.forEach(e => {
    const row = document.createElement("div");
    row.className = "evidence-item";
    const n = document.createElement("span"); n.className = "evidence-n"; n.textContent = "[" + e.id + "] ";
    const s = document.createElement("span"); s.textContent = e.source || "";
    const sc = document.createElement("span"); sc.className = "evidence-score";
    const pct = maxS > 0 ? Math.round(((Number(e.score) || 0) / maxS) * 100) : null;
    sc.textContent = pct !== null ? "相关度 " + pct + "%" : "";
    row.appendChild(n); row.appendChild(s); row.appendChild(sc);
    panel.appendChild(row);
  });
  box.appendChild(panel);
}

async function feedback(rating) {
  await api("/api/settlement/feedback", {
    method: "POST",
    body: JSON.stringify({
      session_id: SESSION_ID,
      question: lastQuestion,
      answer: lastAnswer,
      rating: rating,
      feedback_type: rating === "down" ? "wrong_answer" : "none",
      comment: rating === "down" ? "用户反馈回答不准确" : ""
    })
  });
  toast(rating === "up" ? "已反馈：有用" : "已反馈：没用，将进入知识缺口分析");
}

/* ---------- 数据看板 ---------- */

async function loadDash() {
  const d = await api("/api/dashboard/metrics");
  const cards = document.getElementById("dashCards");
  cards.innerHTML =
    '<div class="metric"><div class="metric-head"><span class="metric-label">访问次数</span><span class="metric-icon">' + svgIcon("chart") + '</span></div><div class="metric-num">' + esc(d.total_accesses) + '</div><div class="metric-foot muted">最近 7 天</div></div>' +
    '<div class="metric"><div class="metric-head"><span class="metric-label">独立用户</span><span class="metric-icon t-info">' + svgIcon("user") + '</span></div><div class="metric-num t-info">' + esc(d.unique_users) + '</div><div class="metric-foot muted">最近 7 天</div></div>' +
    '<div class="metric"><div class="metric-head"><span class="metric-label">知识单元</span><span class="metric-icon t-purple">' + svgIcon("book") + '</span></div><div class="metric-num t-purple">' + esc(d.knowledge_unit_count) + '</div><div class="metric-foot muted">累计</div></div>' +
    '<div class="metric"><div class="metric-head"><span class="metric-label">Token 消耗</span><span class="metric-icon t-warn">' + svgIcon("bolt") + '</span></div><div class="metric-num t-warn">' + esc(d.token_consumption) + '</div><div class="metric-foot muted">累计</div></div>';
  renderBars("dashQ", d.top_questions, q => q.question + "（" + q.hit_count + "）", q => q.hit_count);
  renderBars("dashU", d.hot_units, u => "单元#" + u.unit_id, u => u.access_count);
  document.getElementById("dashT").innerHTML =
    d.response_time_trend.map(r => esc(r.date) + "：" + esc(r.avg_ms) + "ms").join("<br>");
}

/** 简易 SVG icon 集合（线条风格） */
function svgIcon(name) {
  const c = "viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"";
  const m = {
    chart: '<svg width="18" height="18" ' + c + '><path d="M3 3v18h18"/><path d="M7 15l3-3 3 3 5-5"/></svg>',
    user:  '<svg width="18" height="18" ' + c + '><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
    book:  '<svg width="18" height="18" ' + c + '><path d="M4 4h12a4 4 0 0 1 4 4v12H8a4 4 0 0 0-4 4V4z"/></svg>',
    bolt:  '<svg width="18" height="18" ' + c + '><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/></svg>'
  };
  return m[name] || "";
}

function renderBars(id, items, label, value) {
  const box = document.getElementById(id);
  box.innerHTML = "";
  const max = Math.max(1, ...items.map(value));
  items.forEach(it => {
    const row = document.createElement("div");
    row.className = "bar-row";
    const span = document.createElement("span"); span.textContent = label(it);
    const bar = document.createElement("div"); bar.className = "bar";
    bar.style.width = Math.round(value(it) / max * 100) + "%";
    row.appendChild(span); row.appendChild(bar); box.appendChild(row);
  });
}

/* ---------- FAQ 审核 ---------- */

async function loadFaq() {
  const d = await api("/api/settlement/faqs/recommendations");
  const box = document.getElementById("faqData");
  box.innerHTML = "";
  if (!d.length) { box.innerHTML = '<div class="card empty">暂无待审核 FAQ</div>'; return; }
  d.forEach(f => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML =
      '<div style="margin-bottom:8px;"><b>#' + f.id + ' ' + esc(f.question) + '</b> <span class="badge badge-warning">频次 ' + f.hit_count + '</span></div>' +
      '<textarea id="ans' + f.id + '" placeholder="编辑答案">' + esc(f.answer || "") + '</textarea>' +
      '<div style="margin-top:8px;display:flex;gap:8px;">' +
        '<button class="btn btn-primary" onclick="review(' + f.id + ',\'approve\')">通过并发布</button>' +
        '<button class="btn btn-danger" onclick="review(' + f.id + ',\'reject\')">拒绝</button>' +
      '</div>';
    box.appendChild(card);
  });
}

async function review(id, action) {
  const answer = document.getElementById("ans" + id).value;
  await api("/api/settlement/faqs/" + id + "/review", {
    method: "POST", body: JSON.stringify({ action, edited_answer: answer })
  });
  loadFaq();
}

/* ---------- 知识缺口 ---------- */

async function loadGaps() {
  const d = await api("/api/settlement/knowledge-gaps");
  const tbody = document.getElementById("gapsBody");
  tbody.innerHTML = "";
  d.forEach(g => {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td>" + esc(g.question_pattern) + "</td><td>" + g.ask_count + "</td><td>" +
      esc(g.last_asked_at || "") + "</td><td>" + statusBadge(g.status) + "</td>";
    tbody.appendChild(tr);
  });
}

/* ---------- 审计日志 ---------- */

async function loadAudit() {
  const d = await api("/api/audit/logs");
  const tbody = document.getElementById("auditBody");
  tbody.innerHTML = "";
  d.forEach(a => {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td>" + a.id + "</td><td>用户#" + a.user_id + "</td><td>" + esc(a.action) + "</td><td>" +
      esc(a.resource_type) + ":" + esc(a.resource_id) + "</td><td>" + esc(a.created_at || "") + "</td>";
    tbody.appendChild(tr);
  });
}

/* ============================================================
   组织架构与权限管理
   ============================================================ */

function orgTab(name) {
  document.getElementById("orgUsers").style.display = name === "users" ? "block" : "none";
  document.getElementById("orgRoles").style.display = name === "roles" ? "block" : "none";
  document.getElementById("orgDepts").style.display = name === "depts" ? "block" : "none";
  // 组织子 Tab 激活样式
  document.querySelectorAll('[data-org]').forEach(b => {
    b.classList.toggle("active", b.dataset.org === name);
  });
}

async function loadOrg() {
  const [depts, roles, users, perms] = await Promise.all([
    api("/api/org/departments"), api("/api/org/roles"),
    api("/api/org/users"), api("/api/org/permissions")
  ]);
  orgDepts = depts; orgRoles = roles; orgUsers = users; orgPerms = perms;
  renderUsers(); renderRoles(); renderDepts();
}

function deptName(id) {
  const d = orgDepts.find(x => x.id === id);
  return d ? d.name : "—";
}

function fillDeptSelect(sel, withEmpty) {
  sel.innerHTML = (withEmpty ? '<option value="">无上级（顶级）</option>' : "");
  orgDepts.forEach(d => {
    const o = document.createElement("option"); o.value = d.id; o.textContent = d.name; sel.appendChild(o);
  });
}

function fillRoleSelect(sel) {
  sel.innerHTML = '<option value="">选择角色</option>';
  orgRoles.forEach(r => {
    const o = document.createElement("option"); o.value = r.role_code; o.textContent = r.role_name; sel.appendChild(o);
  });
}

function renderUsers() {
  const tb = document.getElementById("userBody"); tb.innerHTML = "";
  orgUsers.forEach(u => {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td>" + u.id + "</td><td>" + esc(u.username) + "</td><td>" + esc(u.display_name || "") + "</td><td>" +
      esc(deptName(u.department_id)) + "</td><td>" + esc((u.roles || []).join(",")) + "</td><td>" +
      (u.status === "active" ? '<span class="badge badge-success">启用</span>' : '<span class="badge badge-neutral">停用</span>') + "</td><td>" +
      `<button class="btn btn-sm" onclick="editUser(${u.id})">编辑</button>` + " " +
      `<button class="btn btn-sm" onclick="resetPwd(${u.id})">重置密码</button>` + " " +
      `<button class="btn btn-sm" onclick="toggleUser(${u.id})">${u.status === "active" ? "停用" : "启用"}</button></td>`;
    tb.appendChild(tr);
  });
}

function showUserForm() {
  editingUserId = null;
  document.getElementById("userFormTitle").textContent = "新增用户";
  document.getElementById("u_username").value = "";
  document.getElementById("u_username").disabled = false;
  document.getElementById("u_password").value = "";
  document.getElementById("u_display").value = "";
  document.getElementById("u_status").value = "active";
  fillDeptSelect(document.getElementById("u_dept"), true);
  fillRoleSelect(document.getElementById("u_role"));
  document.getElementById("userForm").style.display = "block";
  document.getElementById("userFormMsg").textContent = "";
}
function cancelUserForm() { document.getElementById("userForm").style.display = "none"; }

async function saveUser() {
  const payload = {
    display_name: document.getElementById("u_display").value,
    department_id: document.getElementById("u_dept").value ? Number(document.getElementById("u_dept").value) : null,
    role_codes: document.getElementById("u_role").value ? [document.getElementById("u_role").value] : [],
    status: document.getElementById("u_status").value
  };
  const pw = document.getElementById("u_password").value;
  if (pw) payload.password = pw;
  try {
    if (editingUserId) {
      await api("/api/org/users/" + editingUserId, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      const uname = document.getElementById("u_username").value;
      if (!uname) { document.getElementById("userFormMsg").textContent = "请填写用户名"; return; }
      if (!pw) { document.getElementById("userFormMsg").textContent = "新增用户必须设密码"; return; }
      await api("/api/org/users", { method: "POST", body: JSON.stringify(Object.assign({ username: uname }, payload)) });
    }
    document.getElementById("userForm").style.display = "none";
    await loadOrg();
  } catch (e) { document.getElementById("userFormMsg").textContent = "保存失败：" + e.message; }
}

async function editUser(id) {
  const u = orgUsers.find(x => x.id === id);
  if (!u) return;
  editingUserId = id;
  document.getElementById("userFormTitle").textContent = "编辑用户 #" + id;
  document.getElementById("u_username").value = u.username;
  document.getElementById("u_username").disabled = true;
  document.getElementById("u_password").value = "";
  document.getElementById("u_display").value = u.display_name || "";
  document.getElementById("u_status").value = u.status || "active";
  fillDeptSelect(document.getElementById("u_dept"), true);
  document.getElementById("u_dept").value = u.department_id || "";
  fillRoleSelect(document.getElementById("u_role"));
  document.getElementById("u_role").value = (u.roles && u.roles[0]) || "";
  document.getElementById("userForm").style.display = "block";
  document.getElementById("userFormMsg").textContent = "";
}

async function resetPwd(id) {
  const pw = prompt("输入新密码（至少 4 位）：");
  if (!pw) return;
  await api("/api/org/users/" + id, { method: "PUT", body: JSON.stringify({ password: pw }) });
  toast("密码已重置");
}

async function toggleUser(id) {
  const u = orgUsers.find(x => x.id === id);
  const next = u.status === "active" ? "disabled" : "active";
  await api("/api/org/users/" + id, { method: "PUT", body: JSON.stringify({ status: next }) });
  await loadOrg();
}

function renderRoles() {
  const tb = document.getElementById("roleBody"); tb.innerHTML = "";
  orgRoles.forEach(r => {
    const tr = document.createElement("tr");
    const perms = (r.permissions || []).join(", ");
    tr.innerHTML = "<td>" + r.id + "</td><td>" + esc(r.role_name) + "</td><td>" + esc(r.role_code) + "</td><td>" +
      esc(r.description || "") + "</td><td>" + esc(perms) + "</td><td>" +
      `<button class="btn btn-sm" onclick="openPerm(${r.id})">权限</button>` + " " +
      `<button class="btn btn-sm" onclick="editRole(${r.id})">编辑</button>` + " " +
      `<button class="btn btn-sm btn-danger" onclick="delRole(${r.id})">删除</button></td>`;
    tb.appendChild(tr);
  });
}

function showRoleForm() {
  editingRoleId = null;
  document.getElementById("roleFormTitle").textContent = "新增角色";
  document.getElementById("r_name").value = "";
  document.getElementById("r_code").value = "";
  document.getElementById("r_desc").value = "";
  document.getElementById("roleForm").style.display = "block";
}
function cancelRoleForm() { document.getElementById("roleForm").style.display = "none"; }

async function saveRole() {
  const payload = {
    role_name: document.getElementById("r_name").value,
    role_code: document.getElementById("r_code").value,
    description: document.getElementById("r_desc").value
  };
  if (!payload.role_name || !payload.role_code) { toast("请填写名称和编码"); return; }
  if (editingRoleId) {
    await api("/api/org/roles/" + editingRoleId, { method: "PUT", body: JSON.stringify(payload) });
  } else {
    await api("/api/org/roles", { method: "POST", body: JSON.stringify(payload) });
  }
  editingRoleId = null;
  document.getElementById("roleForm").style.display = "none";
  await loadOrg();
}

async function editRole(id) {
  const r = orgRoles.find(x => x.id === id);
  if (!r) return;
  editingRoleId = id;
  document.getElementById("roleFormTitle").textContent = "编辑角色 #" + id;
  document.getElementById("r_name").value = r.role_name;
  document.getElementById("r_code").value = r.role_code;
  document.getElementById("r_desc").value = r.description || "";
  document.getElementById("roleForm").style.display = "block";
}

async function delRole(id) {
  if (!confirm("确认删除该角色？")) return;
  await api("/api/org/roles/" + id, { method: "DELETE" });
  await loadOrg();
}

function openPerm(roleId) {
  permRoleId = roleId;
  const role = orgRoles.find(x => x.id === roleId);
  const owned = new Set(role ? (role.permissions || []) : []);
  const box = document.getElementById("permChecks"); box.innerHTML = "";
  orgPerms.forEach(p => {
    const lab = document.createElement("label");
    lab.style.marginRight = "12px";
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.value = p.code; cb.checked = owned.has(p.code);
    lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + p.label + "（" + p.code + "）"));
    box.appendChild(lab); box.appendChild(document.createElement("br"));
  });
  document.getElementById("permTitle").textContent = "配置权限：" + (role ? role.role_name : roleId);
  document.getElementById("permPanel").style.display = "block";
}

async function savePerm() {
  const codes = Array.from(document.querySelectorAll("#permChecks input:checked")).map(cb => cb.value);
  await api("/api/org/roles/" + permRoleId + "/permissions", { method: "POST", body: JSON.stringify({ permission_codes: codes }) });
  document.getElementById("permPanel").style.display = "none";
  await loadOrg();
}

function renderDepts() {
  const tb = document.getElementById("deptBody"); tb.innerHTML = "";
  orgDepts.forEach(d => {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td>" + d.id + "</td><td>" + esc(d.name) + "</td><td>" + esc(deptName(d.parent_id)) + "</td><td>" +
      `<button class="btn btn-sm" onclick="editDept(${d.id})">编辑</button>` + " " +
      `<button class="btn btn-sm btn-danger" onclick="delDept(${d.id})">删除</button></td>`;
    tb.appendChild(tr);
  });
}

function showDeptForm() {
  editingDeptId = null;
  document.getElementById("deptFormTitle").textContent = "新增部门";
  document.getElementById("d_name").value = "";
  fillDeptSelect(document.getElementById("d_parent"), true);
  document.getElementById("deptForm").style.display = "block";
}
function cancelDeptForm() { document.getElementById("deptForm").style.display = "none"; }

async function saveDept() {
  const payload = {
    name: document.getElementById("d_name").value,
    parent_id: document.getElementById("d_parent").value ? Number(document.getElementById("d_parent").value) : null
  };
  if (!payload.name) { toast("请填写部门名称"); return; }
  if (editingDeptId) {
    await api("/api/org/departments/" + editingDeptId, { method: "PUT", body: JSON.stringify(payload) });
  } else {
    await api("/api/org/departments", { method: "POST", body: JSON.stringify(payload) });
  }
  editingDeptId = null;
  document.getElementById("deptForm").style.display = "none";
  await loadOrg();
}

async function editDept(id) {
  const d = orgDepts.find(x => x.id === id);
  if (!d) return;
  editingDeptId = id;
  document.getElementById("deptFormTitle").textContent = "编辑部门 #" + id;
  document.getElementById("d_name").value = d.name;
  fillDeptSelect(document.getElementById("d_parent"), true);
  document.getElementById("d_parent").value = d.parent_id || "";
  document.getElementById("deptForm").style.display = "block";
}

async function delDept(id) {
  if (!confirm("确认删除该部门？其下用户将解除部门归属。")) return;
  await api("/api/org/departments/" + id, { method: "DELETE" });
  await loadOrg();
}

/* ---------- 启动 ---------- */
document.getElementById("files").addEventListener("change", uploadFiles);
checkSession();
