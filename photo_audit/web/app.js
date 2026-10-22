"use strict";
const $ = (id) => document.getElementById(id);
// Retain only the session token in this tab, so an accessibility anchor cannot lose it.
const fragment = location.hash.slice(1);
let token = /^[\w-]{40,80}$/.test(fragment) ? fragment : "";
try {
  if (token) sessionStorage.setItem("photo-audit-token", token);
  else token = sessionStorage.getItem("photo-audit-token") || "";
} catch { /* Fragment-only access still works if browser storage is unavailable. */ }
document.querySelector(".brand").href = "/#" + token;
let jobId = null, pollTimer = null, kind = "missing", page = 0, requestNumber = 0;
let busy = false, selecting = false, initializing = true;
const number = (value) => new Intl.NumberFormat("zh-CN").format(value || 0);
const descriptions = {
  missing: "来源中的这些不同内容，在已读取的目标文件里没有找到。若扫描未完成，需补扫后再判断。",
  duplicates: "每组文件的完整内容一致。来源和目标分别统计；重复副本不会自动删除。",
  issues: "这里列出格式检查异常，以及读取失败、跳过和未完成项。格式异常仍需人工检查原因。",
  extras: "这些不同内容只在已读取的目标中找到。它们可能是新照片，也可能是编辑或压缩后的版本。"
};
function showError(message) { $("error").hidden = !message; $("error").textContent = message || ""; }
async function api(path, data) {
  const options = { headers: { "X-Photo-Audit-Token": token } };
  if (data !== undefined) { options.method = "POST"; options.headers["Content-Type"] = "application/json"; options.body = JSON.stringify(data); }
  let response;
  try { response = await fetch(path, options); }
  catch { throw new Error("无法连接本机服务，请确认启动窗口仍在运行，再刷新页面。"); }
  if (!response.ok) { const problem = await response.json(); throw new Error(problem.error || "请求失败"); }
  return response;
}
function setBusy(value) {
  busy = value;
  $("cancel").hidden = !value; $("cancel").disabled = false;
  $("progress-panel").hidden = !value;
  updateControls();
}
function updateControls() {
  const locked = busy || selecting || initializing || !token;
  for (const id of ["start", "demo", "source", "target", "download-html", "download-json"]) $(id).disabled = locked;
  for (const button of document.querySelectorAll(".pick-button")) button.disabled = locked;
}
function cleanPath(value) {
  value = value.trim();
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
  return value;
}
async function start() {
  if (busy || selecting || initializing) return;
  showError("");
  const source = cleanPath($("source").value), target = cleanPath($("target").value);
  if (!source || !target) { showError("请填写来源和目标的完整路径，或先使用自制样本。"); return; }
  setBusy(true); clearTimeout(pollTimer); requestNumber += 1;
  $("progress-title").textContent = "正在准备核对…"; $("progress-path").textContent = "";
  try {
    const result = await (await api("/api/jobs", {source, target})).json();
    jobId = result.id; $("results").hidden = true; $("empty").hidden = true; poll();
  } catch (error) { setBusy(false); showError(error.message); $("empty").hidden = !$("results").hidden; }
}
async function poll() {
  try {
    const result = await (await api(`/api/jobs/${jobId}`)).json();
    if (result.state === "running") {
      const p = result.progress;
      $("progress-title").textContent = `正在核对${p.side === "target" ? "目标" : "来源"} · 已读取 ${number(p.files)} 个文件`;
      $("progress-path").textContent = p.path || "";
      pollTimer = setTimeout(poll, 600); return;
    }
    setBusy(false);
    if (result.state === "error") throw new Error(result.error || "核对失败");
    renderSummary(result); await selectTab(result.summary.scan_complete ? "missing" : "issues"); $("result-title").focus();
  } catch (error) { setBusy(false); showError(error.message); }
}
function renderSummary(result) {
  const s = result.summary;
  $("results").hidden = false;
  $("result-title").textContent = !s.scan_complete ? "扫描未完成，请先查看未完成项" : (s.missing_unique || s.issue_count ? "核对完成，有些地方需要再看一眼。" : "核对完成，目标已找到来源中的不同内容。");
  $("result-description").textContent = s.scan_complete ? "以下结果针对本次读取到的本地文件，具体检查范围见下方说明。" : "以下仅为部分结果，不能据此判断照片已经搬全。";
  $("result-paths").textContent = `本报告来源：${result.source}　｜　目标：${result.target}`;
  $("m-source").textContent = number(s.source_unique);
  $("m-source-detail").textContent = `来自 ${number(s.source_files)} 个媒体文件`;
  $("m-matched").textContent = number(s.matched_unique);
  $("m-missing").textContent = number(s.missing_unique);
  $("m-duplicates").textContent = number(s.duplicate_groups);
  $("m-duplicates-detail").textContent = `两端共 ${number(s.duplicate_copies)} 份重复副本`;
  $("m-issues").textContent = number(s.issue_count);
  for (const [name, value] of Object.entries({missing:s.missing_unique, duplicates:s.duplicate_groups, issues:s.issue_count, extras:s.extra_unique})) $("count-" + name).textContent = number(value);
  const integrity = s.integrity;
  const decoded = (integrity.source.first_frame_decoded || 0) + (integrity.target.first_frame_decoded || 0);
  $("coverage-summary").textContent = `图片解码能力：${result.scope.image_decoder}。两端共 ${number(decoded)} 个文件通过支持格式的校验及首帧解码；其余文件请查看 JSON 报告中的 validation 字段。视频未做全程解码。`;
  const a = result.source_stats, b = result.target_stats;
  $("ignored-summary").textContent = `来源忽略 ${number(a.ignored)} 个非媒体条目，跳过 ${number(a.skipped)} 项；目标忽略 ${number(b.ignored)} 个非媒体条目，跳过 ${number(b.skipped)} 项。忽略项包括元数据 JSON 和不支持的扩展名。`;
}
async function selectTab(nextKind) {
  kind = nextKind; page = 0;
  for (const button of document.querySelectorAll(".tab")) {
    const selected = button.dataset.kind === kind;
    button.classList.toggle("active", selected); button.setAttribute("aria-selected", String(selected)); button.tabIndex = selected ? 0 : -1;
  }
  $("items-panel").setAttribute("aria-labelledby", "tab-" + kind);
  $("list-description").textContent = descriptions[kind];
  await loadItems();
}
function element(tag, text, cls) {
  const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node;
}
async function loadItems() {
  const ticket = ++requestNumber;
  $("items").replaceChildren(element("p", "正在读取列表…", "empty-list"));
  try {
    const result = await (await api(`/api/jobs/${jobId}/items?kind=${kind}&page=${page}`)).json();
    if (ticket !== requestNumber) return;
    const fragment = document.createDocumentFragment();
    if (!result.items.length) fragment.append(element("div", kind === "issues" ? "本次检查范围内，没有记录异常或未完成项。" : "这一类没有记录。", "empty-list"));
    for (const item of result.items) {
      const row = element("article", undefined, "item"), content = element("div");
      if (kind === "issues") {
        content.append(element("h3", item.message), element("p", item.path, "path"), element("small", `${item.side === "source" ? "来源" : "目标"} · ${item.code}`));
        row.append(content, element("span", item.incomplete ? "未完成" : "需检查", "badge"));
      } else {
        const title = kind === "duplicates" ? `${item.files[0].name} · ${item.files.length} 个副本` : item.files[0].name;
        content.append(element("h3", title));
        for (const file of item.files) content.append(element("p", file.path, "path"));
        content.append(element("small", `SHA-256 ${item.sha256.slice(0, 20)}… · ${number(item.files[0].size)} 字节`));
        const label = kind === "duplicates" ? (item.side === "source" ? "来源重复" : "目标重复") : kind === "missing" ? "待找" : "目标独有";
        row.append(content, element("span", label, "badge"));
      }
      fragment.append(row);
    }
    $("items").replaceChildren(fragment);
    $("pagination").hidden = result.total <= 50;
    $("prev").disabled = page === 0; $("next").disabled = (page + 1) * 50 >= result.total;
    $("page-label").textContent = `${page + 1} / ${Math.max(1, Math.ceil(result.total / 50))} 页`;
  } catch (error) { if (ticket === requestNumber) showError(error.message); }
}
async function download(extension) {
  try {
    const response = await api(`/api/jobs/${jobId}/report.${extension}`);
    const blob = await response.blob(), url = URL.createObjectURL(blob);
    const a = element("a"); a.href = url; a.download = `photo-audit-report.${extension}`; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (error) { showError(error.message); }
}
$("start").addEventListener("click", start);
$("demo").addEventListener("click", async () => {
  if (busy || selecting || initializing) return;
  showError(""); $("demo").disabled = true;
  try { const data = await (await api("/api/demo", {})).json(); $("source").value = data.source; $("target").value = data.target; await start(); }
  catch (error) { showError(error.message); }
  finally { updateControls(); }
});
for (const button of document.querySelectorAll(".pick-button")) {
  button.addEventListener("click", async () => {
    if (busy || selecting || initializing) return;
    selecting = true; updateControls(); showError("");
    $("path-help").textContent = "请在系统选择窗口中完成选择；取消后会保留原路径。";
    try {
      const selected = await (await api("/api/pick", {kind:button.dataset.kind,initial_directory:cleanPath($(button.dataset.input).value)})).json();
      if (!selected.cancelled) $(button.dataset.input).value = selected.path;
    } catch (error) { showError(error.message); }
    finally {
      selecting = false; updateControls();
      $("path-help").textContent = "也可粘贴路径。macOS：在访达中按住 Option，右键复制路径。";
    }
  });
}
$("cancel").addEventListener("click", async () => {
  $("cancel").disabled = true;
  try { await api(`/api/jobs/${jobId}/cancel`, {}); }
  catch (error) { showError(error.message); $("cancel").disabled = false; }
});
for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => selectTab(tab.dataset.kind));
  tab.addEventListener("keydown", (event) => {
    const tabs = [...document.querySelectorAll(".tab")], index = tabs.indexOf(tab);
    const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
    if (next !== null) { event.preventDefault(); tabs[next].focus(); selectTab(tabs[next].dataset.kind); }
  });
}
$("prev").addEventListener("click", () => { if (page > 0) { page -= 1; loadItems(); } });
$("next").addEventListener("click", () => { page += 1; loadItems(); });
$("download-html").addEventListener("click", () => download("html"));
$("download-json").addEventListener("click", () => download("json"));
async function initialize() {
  updateControls();
  if (!token) {
    showError("请通过启动脚本打开本工具，使用终端给出的完整本机地址。");
    initializing = false; updateControls(); return;
  }
  try {
    const session = await (await api("/api/session")).json();
    $("version").textContent = "v" + session.version;
    for (const actions of document.querySelectorAll(".pick-actions")) actions.hidden = !session.native_picker;
    if (session.latest) {
      jobId = session.latest.id;
      $("source").value = session.latest.source; $("target").value = session.latest.target;
      $("empty").hidden = true;
      if (session.latest.state === "running") setBusy(true);
      await poll();
    }
  } catch (error) { showError(error.message); }
  finally { initializing = false; updateControls(); }
}
initialize();
