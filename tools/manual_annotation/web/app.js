"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const ROTATION_STEP_DEGREES = 0.01;
const FIT_REVIEW_CROSS_FRACTION = 0.94;
const token = new URLSearchParams(window.location.search).get("token") || "";

const elements = Object.fromEntries([
  "progressText", "searchInput", "formatFilter", "stateFilter", "sourceList",
  "nextButton", "sampleTitle", "stateBadge", "sourceFacts", "saveStatus",
  "undoButton", "redoButton", "resetViewButton", "taskTabs", "taskReviewed",
  "confirmButton", "canvasStage", "annotationSvg", "sourceImage", "polygonLayer",
  "lineLayer", "handleLayer", "cursorCoordinate", "loupeSvg", "loupeImage",
  "loupeCard", "loupeWrap", "loupeTitle", "maximizeLoupeButton", "loupeHelp", "loupeLineLayer",
  "loupeCrossX", "loupeCrossY", "loupeEmpty", "selectedLineLabel",
  "lineCoordinates", "diagnostics", "confirmDialog", "confirmTitle",
  "finalConfirmButton", "toast"
].map((id) => [id, document.getElementById(id)]));

const stateLabels = {
  not_prepared: "未准备",
  machine_proposal: "机器预标",
  human_adjusted: "已人工调整",
  user_confirmed: "用户已确认"
};

let indexData = null;
let currentItem = null;
let currentRecord = null;
let activeTaskId = null;
let selectedLineId = null;
let selectedEndpoint = null;
let saveTimer = null;
let savePromise = null;
let dirty = false;
let editGeneration = 0;
let history = [];
let future = [];
let viewBox = null;
let drag = null;
let loupeAbort = null;
let loupeUrl = null;
let loupeTimer = null;
let lastPointer = null;
let loupeMaximized = false;
let loupeResizeTimer = null;
let toastTimer = null;

async function api(path, options = {}) {
  const headers = {"X-X5-Token": token, ...(options.headers || {})};
  if (options.method && options.method !== "GET") {
    headers["Content-Type"] = "application/json";
    headers["X-X5-Write"] = "1";
  }
  const response = await fetch(path, {...options, headers, cache: "no-store"});
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try { message = (await response.json()).error || message; } catch (_) { /* no-op */ }
    throw new Error(message);
  }
  return response;
}

function showToast(message, error = false) {
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", error);
  elements.toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => elements.toast.classList.remove("visible"), 2800);
}

function setSaveStatus(text, tone = "normal") {
  elements.saveStatus.textContent = text;
  elements.saveStatus.style.color = tone === "error" ? "#ff7e8b" : tone === "ok" ? "#78e6b3" : "";
}

function sourceLabel(item) {
  return item.tasks.map((task) => task.sample_id).join(" / ");
}

function countsLabel(item) {
  return item.tasks.map((task) => task.count).join("/");
}

function renderIndex() {
  if (!indexData) return;
  const confirmed = indexData.states.user_confirmed || 0;
  const adjusted = indexData.states.human_adjusted || 0;
  elements.progressText.textContent = `${confirmed}/${indexData.total_unique_sources} 已确认 · ${adjusted} 已调整`;
  const query = elements.searchInput.value.trim().toLowerCase();
  const state = elements.stateFilter.value;
  const format = elements.formatFilter.value;
  elements.sourceList.replaceChildren();
  const items = indexData.items.filter((item) => {
    const matchesSearch = !query || sourceLabel(item).toLowerCase().includes(query) || item.source_sha256.includes(query);
    const matchesFormat = format === "all" || item.format_id === format;
    const matchesState = state === "all"
      || (state === "unfinished" && item.state !== "user_confirmed")
      || item.state === state;
    return matchesSearch && matchesFormat && matchesState;
  });
  for (const item of items) {
    const button = document.createElement("button");
    button.className = `source-item${currentItem?.source_sha256 === item.source_sha256 ? " active" : ""}`;
    button.dataset.sha = item.source_sha256;
    button.innerHTML = `
      <span class="state-dot ${item.state}"></span>
      <span class="source-name"><strong>${escapeHtml(sourceLabel(item))}</strong><small>${escapeHtml(item.format_id)} · ${item.source_sha256.slice(0, 10)}</small></span>
      <span class="source-count">count ${escapeHtml(countsLabel(item))}</span>`;
    button.addEventListener("click", () => openSource(item));
    elements.sourceList.appendChild(button);
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[character]);
}

async function loadIndex() {
  const response = await api("/api/index");
  indexData = await response.json();
  const formats = [...new Set(indexData.items.map((item) => item.format_id))].sort();
  for (const format of formats) {
    const option = document.createElement("option");
    option.value = format;
    option.textContent = format;
    elements.formatFilter.appendChild(option);
  }
  renderIndex();
  const initial = indexData.items.find((item) => item.state !== "user_confirmed" && item.prepared)
    || indexData.items.find((item) => item.prepared);
  if (initial) await openSource(initial);
}

async function openSource(item) {
  if (!item.prepared) {
    showToast("该样片尚未生成本地预标，请先运行 prepare。", true);
    return;
  }
  try {
    await flushSave();
    setLoupeMaximized(false, false);
    setSaveStatus("正在打开…");
    const response = await api(`/api/record/${encodeURIComponent(item.source_sha256)}`);
    currentItem = item;
    currentRecord = await response.json();
    activeTaskId = currentRecord.tasks[0].task_id;
    selectedLineId = null;
    selectedEndpoint = null;
    history = [];
    future = [];
    dirty = false;
    editGeneration = 0;
    const extent = currentRecord.source.canonical_extent;
    lastPointer = [extent.width / 2, extent.height / 2];
    elements.cursorCoordinate.textContent = `x ${lastPointer[0].toFixed(1)} · y ${lastPointer[1].toFixed(1)}`;
    elements.loupeWrap.classList.remove("ready");
    resetView();
    renderRecord();
    scheduleLoupe(lastPointer);
    setSaveStatus("已保存", "ok");
    renderIndex();
  } catch (error) {
    setSaveStatus("打开失败", "error");
    showToast(error.message, true);
  }
}

function renderRecord() {
  if (!currentRecord) return;
  const extent = currentRecord.source.canonical_extent;
  elements.canvasStage.classList.remove("empty");
  elements.annotationSvg.setAttribute("viewBox", viewBoxString());
  elements.sourceImage.setAttribute("x", "0");
  elements.sourceImage.setAttribute("y", "0");
  elements.sourceImage.setAttribute("width", extent.width);
  elements.sourceImage.setAttribute("height", extent.height);
  elements.sourceImage.setAttribute("href", `/api/preview/${encodeURIComponent(currentRecord.source.sha256)}?token=${encodeURIComponent(token)}`);
  elements.sampleTitle.textContent = currentRecord.tasks.map((task) => task.sample_id).join(" / ");
  elements.stateBadge.textContent = stateLabels[currentRecord.state] || currentRecord.state;
  elements.stateBadge.className = `badge ${currentRecord.state}`;
  elements.sourceFacts.textContent = `${currentRecord.format_id} · raw ${currentRecord.source.raw_extent.width}×${currentRecord.source.raw_extent.height} · Orientation ${currentRecord.source.orientation_mapping.original_tag} · revision ${currentRecord.revision}`;
  renderTaskTabs();
  renderGeometry();
  renderDiagnostics();
  updateControls();
}

function renderTaskTabs() {
  elements.taskTabs.replaceChildren();
  for (const task of currentRecord.tasks) {
    const button = document.createElement("button");
    button.className = `task-tab${task.task_id === activeTaskId ? " active" : ""}${currentRecord.reviewed_task_ids.includes(task.task_id) ? " reviewed" : ""}`;
    button.textContent = `${task.sample_id} · count ${task.count}`;
    button.addEventListener("click", () => {
      activeTaskId = task.task_id;
      selectedLineId = null;
      selectedEndpoint = null;
      renderTaskTabs();
      renderGeometry();
      renderDiagnostics();
      updateControls();
    });
    elements.taskTabs.appendChild(button);
  }
}

function activeTask() {
  return currentRecord?.tasks.find((task) => task.task_id === activeTaskId) || null;
}

function allLines() {
  return currentRecord ? [...currentRecord.shared_edges, ...currentRecord.boundary_pool] : [];
}

function taskBoundaryIds(task) {
  return task ? task.slots.flatMap((slot) => [slot.start_boundary_id, slot.end_boundary_id]) : [];
}

function lineById(identity) {
  return allLines().find((line) => line.line_id === identity) || null;
}

function intersection(first, second) {
  const [[x1, y1], [x2, y2]] = first.points_display;
  const [[x3, y3], [x4, y4]] = second.points_display;
  const denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
  if (Math.abs(denominator) < 1e-9) return null;
  const a = x1 * y2 - y1 * x2;
  const b = x3 * y4 - y3 * x4;
  return [
    (a * (x3 - x4) - (x1 - x2) * b) / denominator,
    (a * (y3 - y4) - (y1 - y2) * b) / denominator
  ];
}

function taskPolygons(task) {
  const pool = new Map(currentRecord.boundary_pool.map((line) => [line.line_id, line]));
  const low = currentRecord.shared_edges[0];
  const high = currentRecord.shared_edges[1];
  const polygons = [];
  for (const slot of task.slots) {
    const start = pool.get(slot.start_boundary_id);
    const stop = pool.get(slot.end_boundary_id);
    const polygon = currentRecord.strip_axis_display === "horizontal"
      ? [intersection(low, start), intersection(low, stop), intersection(high, stop), intersection(high, start)]
      : [intersection(low, start), intersection(high, start), intersection(high, stop), intersection(low, stop)];
    if (polygon.every(Boolean)) polygons.push(polygon);
  }
  return polygons;
}

function svgElement(name, attributes = {}) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

function activeLineEntries() {
  const task = activeTask();
  const taskIds = taskBoundaryIds(task);
  const used = new Set(taskIds);
  return [
    ...currentRecord.shared_edges.map((line, index) => ({
      line,
      family: "shared",
      label: index === 0 ? "共享边 A" : "共享边 B",
      active: true
    })),
    ...currentRecord.boundary_pool.map((line) => {
      const positions = taskIds.flatMap((identity, position) => identity === line.line_id ? [position] : []);
      const label = positions.length
        ? positions.map((position) => `${Math.floor(position / 2) + 1}${position % 2 ? "R" : "L"}`).join("/")
        : line.line_id;
      return {line, family: "boundary", label, active: used.has(line.line_id)};
    })
  ];
}

function renderGeometry() {
  elements.polygonLayer.replaceChildren();
  elements.lineLayer.replaceChildren();
  elements.handleLayer.replaceChildren();
  if (!currentRecord) return;
  const task = activeTask();
  taskPolygons(task).forEach((points, index) => {
    const polygon = svgElement("polygon", {
      points: points.map((point) => `${point[0]},${point[1]}`).join(" "),
      class: "frame-polygon"
    });
    const title = svgElement("title");
    title.textContent = `照片 ${index + 1} · ${task.slots[index].slot_kind}`;
    polygon.appendChild(title);
    elements.polygonLayer.appendChild(polygon);
  });

  const entries = activeLineEntries();
  entries.sort((left, right) => (
    Number(left.line.line_id === selectedLineId) -
    Number(right.line.line_id === selectedLineId)
  ));
  for (const entry of entries) {
    const [first, second] = entry.line.points_display;
    const selected = entry.line.line_id === selectedLineId;
    const classes = ["annotation-line", entry.family];
    if (!entry.active) classes.push("inactive");
    if (selected) {
      classes.push("selected");
      elements.lineLayer.appendChild(svgElement("line", {
        x1: first[0], y1: first[1], x2: second[0], y2: second[1],
        class: "annotation-selection-halo"
      }));
    }
    const node = svgElement("line", {
      x1: first[0], y1: first[1], x2: second[0], y2: second[1],
      class: classes.join(" "), "data-line-id": entry.line.line_id
    });
    node.addEventListener("pointerdown", (event) => startLineDrag(event, entry.line.line_id));
    node.addEventListener("click", (event) => { event.stopPropagation(); selectLine(entry.line.line_id, null); });
    elements.lineLayer.appendChild(node);
    if (entry.active) {
      const middle = [(first[0] + second[0]) / 2, (first[1] + second[1]) / 2];
      const label = svgElement("text", {x: middle[0] + 5, y: middle[1] - 5, class: "line-label"});
      label.textContent = entry.label;
      elements.lineLayer.appendChild(label);
    }
  }
  renderHandles();
  renderSelectedLine();
}

function renderHandles() {
  elements.handleLayer.replaceChildren();
  const line = lineById(selectedLineId);
  if (!line) return;
  line.points_display.forEach((point, endpoint) => {
    const handle = svgElement("circle", {
      cx: point[0], cy: point[1], r: 6,
      class: `endpoint${selectedEndpoint === endpoint ? " active" : ""}`,
      "data-endpoint": endpoint
    });
    handle.addEventListener("pointerdown", (event) => startEndpointDrag(event, line.line_id, endpoint));
    handle.addEventListener("click", (event) => { event.stopPropagation(); selectLine(line.line_id, endpoint); });
    elements.handleLayer.appendChild(handle);
  });
}

function renderSelectedLine() {
  const line = lineById(selectedLineId);
  if (!line) {
    elements.selectedLineLabel.textContent = "未选择";
    elements.lineCoordinates.querySelectorAll("code").forEach((node) => node.textContent = "—");
    renderLoupeLines();
    return;
  }
  elements.selectedLineLabel.textContent = `${line.line_id} · ${line.review_basis} · ${line.origin}`;
  const codes = elements.lineCoordinates.querySelectorAll("code");
  line.points_display.forEach((point, index) => {
    codes[index].textContent = `x ${point[0].toFixed(2)} · y ${point[1].toFixed(2)}`;
  });
  renderLoupeLines();
}

function renderDiagnostics() {
  elements.diagnostics.replaceChildren();
  if (!currentRecord) return;
  const taskFit = currentRecord.diagnostics.task_fits?.[activeTaskId];
  const reviewContext = currentRecord.diagnostics.review_context || {};
  const taskContext = reviewContext.tasks?.[activeTaskId] || {};
  const redImport = currentRecord.diagnostics.red_markup_import;
  const redTask = redImport?.task_assignments?.[activeTaskId];
  const slotSummary = activeTask()?.slots
    .filter((slot) => slot.slot_kind !== "image")
    .map((slot) => `${slot.ordinal}:${slot.slot_kind}`)
    .join(" / ") || "全部 image";
  const adjacencySummary = activeTask()?.adjacencies
    .filter((adjacency) => adjacency.kind !== "separator")
    .map((adjacency) => `${adjacency.left_ordinal}-${adjacency.right_ordinal}:${adjacency.kind}`)
    .join(" / ") || "全部 separator";
  const rows = [
    ["来源", currentRecord.origin],
    ["胶片极性", reviewContext.film_polarity ? `${reviewContext.film_polarity}（仅校准分层）` : "未记录"],
    ["坐标", "raw TIFF pixel centers"],
    ["预标版本", currentRecord.diagnostics.proposal_revision || currentRecord.diagnostics.legacy_algorithm_revision || "legacy confirmed"],
    ["共享边 MAD", (currentRecord.diagnostics.shared_fit_mad_analysis_px || []).map((value) => Number(value).toFixed(2)).join(" / ") || "已确认旧基线"],
    ["模板分数", taskFit ? Number(taskFit.template_score).toFixed(3) : "—"],
    ["结构标签", taskContext.case_tags?.join(" / ") || "常规"],
    ["Slot 语义", slotSummary],
    ["相邻关系", adjacencySummary],
    ["人工备注", taskContext.notes?.join("；") || "无"],
    ["待重点检查", currentRecord.diagnostics.unresolved?.length ? `${currentRecord.diagnostics.unresolved.length} 项` : "无额外提示"],
    ["权限", currentRecord.state === "user_confirmed" ? "用户确认" : "仅 proposal"]
  ];
  if (redImport) {
    rows.splice(1, 0, ["红线草稿", `${redImport.applied_shared_edge_count}/${redImport.detected_shared_edge_count} 条共享边已采用 · ${redImport.detected_boundary_count} 条长轴边`]);
    rows.splice(2, 0, ["机器补线", redTask?.machine_retained_role_indices?.length ? `角色 ${redTask.machine_retained_role_indices.join(", ")}` : "无"]);
    rows.splice(3, 0, ["机器共享边", redImport.machine_retained_shared_edge_indices?.length ? `边 ${redImport.machine_retained_shared_edge_indices.join(", ")}` : "无"]);
  }
  for (const [name, value] of rows) {
    const term = document.createElement("dt"); term.textContent = name;
    const detail = document.createElement("dd"); detail.textContent = value;
    elements.diagnostics.append(term, detail);
  }
}

function updateControls() {
  const task = activeTask();
  const immutable = currentRecord?.state === "user_confirmed";
  elements.taskReviewed.disabled = !task || immutable;
  elements.taskReviewed.checked = Boolean(task && currentRecord.reviewed_task_ids.includes(task.task_id));
  const allReviewed = currentRecord && currentRecord.tasks.every((item) => currentRecord.reviewed_task_ids.includes(item.task_id));
  elements.confirmButton.disabled = !currentRecord || immutable || !allReviewed || dirty;
  elements.undoButton.disabled = immutable || history.length === 0;
  elements.redoButton.disabled = immutable || future.length === 0;
  elements.maximizeLoupeButton.disabled = !currentRecord || !lastPointer;
  elements.annotationSvg.style.pointerEvents = immutable ? "auto" : "auto";
  document.querySelectorAll("[data-nudge],[data-rotate]").forEach((button) => button.disabled = immutable || !selectedLineId);
}

function geometrySnapshot() {
  return {
    shared_edges: currentRecord.shared_edges.map((line) => ({line_id: line.line_id, points_display: line.points_display.map((point) => [...point])})),
    boundary_pool: currentRecord.boundary_pool.map((line) => ({line_id: line.line_id, points_display: line.points_display.map((point) => [...point])}))
  };
}

function applySnapshot(snapshot) {
  replaceGeometryFromSnapshot(snapshot);
  markDirty();
  renderGeometry();
  updateControls();
}

function replaceGeometryFromSnapshot(snapshot) {
  const incoming = new Map([...snapshot.shared_edges, ...snapshot.boundary_pool].map((line) => [line.line_id, line.points_display]));
  allLines().forEach((line) => { line.points_display = incoming.get(line.line_id).map((point) => [...point]); });
}

function pushHistory() {
  history.push(geometrySnapshot());
  if (history.length > 80) history.shift();
  future = [];
  updateControls();
}

function undo() {
  if (!history.length || currentRecord?.state === "user_confirmed") return;
  future.push(geometrySnapshot());
  applySnapshot(history.pop());
}

function redo() {
  if (!future.length || currentRecord?.state === "user_confirmed") return;
  history.push(geometrySnapshot());
  applySnapshot(future.pop());
}

function markDirty() {
  if (currentRecord?.state === "user_confirmed") return;
  const wasDirty = dirty;
  dirty = true;
  editGeneration += 1;
  if (!wasDirty) {
    currentRecord.reviewed_task_ids = [];
    renderTaskTabs();
  }
  setSaveStatus("有未保存修改");
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNow, 450);
}

async function saveNow() {
  clearTimeout(saveTimer);
  if (savePromise) {
    await savePromise;
    return;
  }
  if (!dirty || !currentRecord || currentRecord.state === "user_confirmed") return;
  const generation = editGeneration;
  const payload = {expected_revision: currentRecord.revision, ...geometrySnapshot()};
  dirty = false;
  setSaveStatus("正在保存…");
  let needsFollowup = false;
  const request = api(`/api/geometry/${encodeURIComponent(currentRecord.source.sha256)}`, {
    method: "PATCH", body: JSON.stringify(payload)
  }).then((response) => response.json()).then((record) => {
    if (editGeneration === generation) {
      currentRecord = record;
      setSaveStatus("已保存", "ok");
    } else {
      const pending = geometrySnapshot();
      currentRecord = record;
      replaceGeometryFromSnapshot(pending);
      dirty = true;
      needsFollowup = true;
      setSaveStatus("有后续修改待保存");
    }
    renderRecord();
    updateIndexItemState(record.state);
  }).catch((error) => {
    dirty = true;
    setSaveStatus("保存失败", "error");
    showToast(error.message, true);
  });
  savePromise = request;
  await request;
  if (savePromise === request) savePromise = null;
  if (needsFollowup) {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, 80);
  }
}

async function flushSave() {
  if (dirty) await saveNow();
  if (savePromise) await savePromise;
  if (dirty) await saveNow();
  if (dirty) throw new Error("当前修改未能保存，不能切换样片。");
}

function updateIndexItemState(state) {
  if (!currentItem || !indexData) return;
  currentItem.state = state;
  const target = indexData.items.find((item) => item.source_sha256 === currentItem.source_sha256);
  if (target) {
    target.state = state;
    target.reviewed_task_ids = [...currentRecord.reviewed_task_ids];
  }
  indexData.states = {};
  for (const item of indexData.items) indexData.states[item.state] = (indexData.states[item.state] || 0) + 1;
  renderIndex();
}

function selectLine(identity, endpoint = null) {
  selectedLineId = identity;
  selectedEndpoint = endpoint;
  renderGeometry();
  updateControls();
}

function screenToSvg(event) {
  const point = elements.annotationSvg.createSVGPoint();
  point.x = event.clientX; point.y = event.clientY;
  return point.matrixTransform(elements.annotationSvg.getScreenCTM().inverse());
}

function clampPoint(point) {
  const extent = currentRecord.source.canonical_extent;
  return [Math.max(0, Math.min(extent.width - 1, point[0])), Math.max(0, Math.min(extent.height - 1, point[1]))];
}

function startLineDrag(event, identity) {
  if (currentRecord.state === "user_confirmed") return;
  event.preventDefault(); event.stopPropagation();
  selectLine(identity, null);
  pushHistory();
  const line = lineById(identity);
  const start = screenToSvg(event);
  const [[x1, y1], [x2, y2]] = line.points_display;
  const length = Math.hypot(x2 - x1, y2 - y1) || 1;
  drag = {mode: "line", identity, start, original: line.points_display.map((point) => [...point]), normal: [-(y2 - y1) / length, (x2 - x1) / length]};
  elements.annotationSvg.setPointerCapture(event.pointerId);
}

function startEndpointDrag(event, identity, endpoint) {
  if (currentRecord.state === "user_confirmed") return;
  event.preventDefault(); event.stopPropagation();
  selectLine(identity, endpoint);
  pushHistory();
  drag = {mode: "endpoint", identity, endpoint};
  elements.annotationSvg.setPointerCapture(event.pointerId);
}

function handlePointerMove(event) {
  if (!currentRecord) return;
  const point = screenToSvg(event);
  lastPointer = clampPoint([point.x, point.y]);
  elements.cursorCoordinate.textContent = `x ${lastPointer[0].toFixed(1)} · y ${lastPointer[1].toFixed(1)}`;
  scheduleLoupe(lastPointer);
  if (!drag) return;
  if (drag.mode === "pan") {
    const extent = currentRecord.source.canonical_extent;
    const dx = (event.clientX - drag.clientX) * drag.viewBox.width / elements.annotationSvg.clientWidth;
    const dy = (event.clientY - drag.clientY) * drag.viewBox.height / elements.annotationSvg.clientHeight;
    viewBox = constrainViewBox({x: drag.viewBox.x - dx, y: drag.viewBox.y - dy, width: drag.viewBox.width, height: drag.viewBox.height}, extent);
    elements.annotationSvg.setAttribute("viewBox", viewBoxString());
    return;
  }
  const line = lineById(drag.identity);
  if (drag.mode === "endpoint") {
    line.points_display[drag.endpoint] = clampPoint([point.x, point.y]);
  } else {
    const delta = [point.x - drag.start.x, point.y - drag.start.y];
    const amount = delta[0] * drag.normal[0] + delta[1] * drag.normal[1];
    line.points_display = drag.original.map((original) => clampPoint([original[0] + amount * drag.normal[0], original[1] + amount * drag.normal[1]]));
  }
  markDirty();
  renderGeometry();
  updateControls();
}

function finishDrag(event) {
  if (drag) {
    try { elements.annotationSvg.releasePointerCapture(event.pointerId); } catch (_) { /* no-op */ }
  }
  drag = null;
}

function startPan(event) {
  if (!currentRecord || event.target.closest(".annotation-line,.endpoint")) return;
  selectedLineId = null; selectedEndpoint = null;
  renderGeometry();
  drag = {mode: "pan", clientX: event.clientX, clientY: event.clientY, viewBox: {...viewBox}};
  elements.annotationSvg.setPointerCapture(event.pointerId);
}

function nudge(dx, dy, multiplier = 1) {
  const line = lineById(selectedLineId);
  if (!line || currentRecord.state === "user_confirmed") return;
  pushHistory();
  if (selectedEndpoint !== null) {
    const point = line.points_display[selectedEndpoint];
    line.points_display[selectedEndpoint] = clampPoint([point[0] + dx * multiplier, point[1] + dy * multiplier]);
  } else {
    line.points_display = line.points_display.map((point) => clampPoint([point[0] + dx * multiplier, point[1] + dy * multiplier]));
  }
  markDirty(); renderGeometry(); updateControls();
}

function rotateSelectedLine(direction, multiplier = 1) {
  const line = lineById(selectedLineId);
  if (!line || currentRecord.state === "user_confirmed") return;
  const angle = direction * ROTATION_STEP_DEGREES * multiplier * Math.PI / 180;
  const [first, second] = line.points_display;
  const pivot = selectedEndpoint === null
    ? [(first[0] + second[0]) / 2, (first[1] + second[1]) / 2]
    : [...line.points_display[selectedEndpoint]];
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  const rotated = line.points_display.map((point, index) => {
    if (index === selectedEndpoint) return [...pivot];
    const dx = point[0] - pivot[0];
    const dy = point[1] - pivot[1];
    return [
      pivot[0] + dx * cosine - dy * sine,
      pivot[1] + dx * sine + dy * cosine
    ];
  });
  pushHistory();
  line.points_display = rotated;
  markDirty(); renderGeometry(); updateControls();
}

function resetView() {
  if (!currentRecord) { viewBox = null; return; }
  const extent = currentRecord.source.canonical_extent;
  viewBox = {x: 0, y: 0, width: extent.width, height: extent.height};
  elements.annotationSvg.setAttribute("viewBox", viewBoxString());
}

function viewBoxString() {
  if (!viewBox && currentRecord) resetView();
  return viewBox ? `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}` : "0 0 1 1";
}

function constrainViewBox(box, extent) {
  const width = Math.min(extent.width, Math.max(extent.width / 16, box.width));
  const height = Math.min(extent.height, Math.max(extent.height / 16, box.height));
  return {
    x: Math.max(0, Math.min(extent.width - width, box.x)),
    y: Math.max(0, Math.min(extent.height - height, box.y)),
    width, height
  };
}

function zoomAt(event) {
  if (!currentRecord) return;
  event.preventDefault();
  const point = screenToSvg(event);
  const factor = event.deltaY < 0 ? 0.82 : 1.22;
  const extent = currentRecord.source.canonical_extent;
  const next = {
    x: point.x - (point.x - viewBox.x) * factor,
    y: point.y - (point.y - viewBox.y) * factor,
    width: viewBox.width * factor,
    height: viewBox.height * factor
  };
  viewBox = constrainViewBox(next, extent);
  elements.annotationSvg.setAttribute("viewBox", viewBoxString());
}

function scheduleLoupe(point) {
  clearTimeout(loupeTimer);
  loupeTimer = setTimeout(() => loadLoupe(point), 110);
}

function renderedTileSize() {
  const bounds = elements.loupeWrap.getBoundingClientRect();
  const maximum = Number(indexData?.tile_max_render_dimension) || 768;
  return {
    width: Math.max(64, Math.min(maximum, Math.round(bounds.width || 512))),
    height: Math.max(64, Math.min(maximum, Math.round(bounds.height || bounds.width || 512)))
  };
}

function sharedCrossCoordinate(line, longPosition) {
  const [[x1, y1], [x2, y2]] = line.points_display;
  if (currentRecord.strip_axis_display === "horizontal") {
    if (Math.abs(x2 - x1) < 1.0e-9) return (y1 + y2) / 2;
    return y1 + (longPosition - x1) * (y2 - y1) / (x2 - x1);
  }
  if (Math.abs(y2 - y1) < 1.0e-9) return (x1 + x2) / 2;
  return x1 + (longPosition - y1) * (x2 - x1) / (y2 - y1);
}

function fitReviewGeometry(point, render) {
  const extent = currentRecord.source.canonical_extent;
  const horizontal = currentRecord.strip_axis_display === "horizontal";
  const longPosition = horizontal ? point[0] : point[1];
  const first = sharedCrossCoordinate(currentRecord.shared_edges[0], longPosition);
  const second = sharedCrossCoordinate(currentRecord.shared_edges[1], longPosition);
  const sharedSpan = Math.max(64, Math.abs(second - first));
  const center = horizontal
    ? clampPoint([longPosition, (first + second) / 2])
    : clampPoint([(first + second) / 2, longPosition]);
  const sourceCross = sharedSpan / FIT_REVIEW_CROSS_FRACTION;
  let sourceWidth = horizontal
    ? sourceCross * render.width / render.height
    : sourceCross;
  let sourceHeight = horizontal
    ? sourceCross
    : sourceCross * render.height / render.width;
  const maximumDimension = Number(indexData?.tile_max_source_dimension) || 8192;
  const maximumPixels = Number(indexData?.tile_max_source_pixels) || 16_000_000;
  const factor = Math.min(
    1,
    extent.width / sourceWidth,
    extent.height / sourceHeight,
    maximumDimension / sourceWidth,
    maximumDimension / sourceHeight,
    Math.sqrt(maximumPixels / (sourceWidth * sourceHeight))
  );
  sourceWidth = Math.max(64, Math.round(sourceWidth * factor));
  sourceHeight = Math.max(64, Math.round(sourceHeight * factor));
  return {center, sourceWidth, sourceHeight};
}

function tileRequest(point) {
  const render = renderedTileSize();
  if (!loupeMaximized) {
    return {
      center: clampPoint(point),
      sourceWidth: render.width,
      sourceHeight: render.height,
      renderWidth: render.width,
      renderHeight: render.height
    };
  }
  const fitted = fitReviewGeometry(point, render);
  return {
    ...fitted,
    renderWidth: render.width,
    renderHeight: render.height
  };
}

function setLoupeMaximized(maximized, reload = true) {
  const next = Boolean(maximized && currentRecord && lastPointer);
  if (loupeMaximized === next) return;
  loupeMaximized = next;
  document.body.classList.toggle("loupe-maximized", next);
  elements.maximizeLoupeButton.setAttribute("aria-pressed", String(next));
  elements.loupeTitle.textContent = next ? "完整高度审阅" : "1:1 原生像素检查";
  elements.loupeSvg.setAttribute("aria-label", next ? "胶片完整高度审阅图" : "原生像素局部图");
  elements.maximizeLoupeButton.textContent = next ? "退出审阅" : "完整高度审阅";
  elements.maximizeLoupeButton.title = next ? "退出完整高度审阅（F 或 Esc）" : "完整高度审阅（F）";
  elements.loupeHelp.textContent = next
    ? "共享短轴 H 占可用高度约 94%；点击图内位置可沿胶片长轴移动。按 F 或 Esc 退出。"
    : "局部图直接来自原 TIFF 像素。用它检查线是否安全贴合物理边缘；按 F 进入完整高度审阅。";
  if (reload && lastPointer) requestAnimationFrame(() => loadLoupe(lastPointer));
}

function recenterLoupe(event) {
  if (!loupeMaximized || !currentRecord || !elements.loupeWrap.classList.contains("ready")) return;
  const matrix = elements.loupeSvg.getScreenCTM();
  if (!matrix) return;
  const point = elements.loupeSvg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  const sourcePoint = point.matrixTransform(matrix.inverse());
  lastPointer = fitReviewGeometry(
    [sourcePoint.x, sourcePoint.y],
    renderedTileSize()
  ).center;
  elements.cursorCoordinate.textContent = `x ${lastPointer[0].toFixed(1)} · y ${lastPointer[1].toFixed(1)}`;
  scheduleLoupe(lastPointer);
}

async function loadLoupe(point) {
  if (!currentRecord) return;
  if (loupeAbort) loupeAbort.abort();
  loupeAbort = new AbortController();
  try {
    const request = tileRequest(point);
    lastPointer = request.center;
    elements.cursorCoordinate.textContent = `x ${lastPointer[0].toFixed(1)} · y ${lastPointer[1].toFixed(1)}`;
    const query = new URLSearchParams({
      x: String(request.center[0]),
      y: String(request.center[1]),
      source_width: String(request.sourceWidth),
      source_height: String(request.sourceHeight),
      render_width: String(request.renderWidth),
      render_height: String(request.renderHeight)
    });
    const response = await api(`/api/tile/${encodeURIComponent(currentRecord.source.sha256)}?${query}`, {signal: loupeAbort.signal});
    const extent = {
      left: Number(response.headers.get("X-X5-Tile-Left")),
      top: Number(response.headers.get("X-X5-Tile-Top")),
      width: Number(response.headers.get("X-X5-Tile-Width")),
      height: Number(response.headers.get("X-X5-Tile-Height"))
    };
    const blob = await response.blob();
    if (loupeUrl) URL.revokeObjectURL(loupeUrl);
    loupeUrl = URL.createObjectURL(blob);
    elements.loupeSvg.setAttribute("viewBox", `${extent.left} ${extent.top} ${extent.width} ${extent.height}`);
    elements.loupeImage.setAttribute("href", loupeUrl);
    elements.loupeImage.setAttribute("x", extent.left);
    elements.loupeImage.setAttribute("y", extent.top);
    elements.loupeImage.setAttribute("width", extent.width);
    elements.loupeImage.setAttribute("height", extent.height);
    elements.loupeCrossX.setAttribute("x1", extent.left); elements.loupeCrossX.setAttribute("x2", extent.left + extent.width);
    elements.loupeCrossX.setAttribute("y1", request.center[1]); elements.loupeCrossX.setAttribute("y2", request.center[1]);
    elements.loupeCrossY.setAttribute("x1", request.center[0]); elements.loupeCrossY.setAttribute("x2", request.center[0]);
    elements.loupeCrossY.setAttribute("y1", extent.top); elements.loupeCrossY.setAttribute("y2", extent.top + extent.height);
    elements.loupeWrap.classList.add("ready");
    renderLoupeLines();
  } catch (error) {
    if (error.name !== "AbortError") showToast(error.message, true);
  }
}

function renderLoupeLines() {
  elements.loupeLineLayer.replaceChildren();
  if (!currentRecord) return;
  const entries = activeLineEntries().filter((item) => item.active);
  entries.sort((left, right) => (
    Number(left.line.line_id === selectedLineId) -
    Number(right.line.line_id === selectedLineId)
  ));
  for (const entry of entries) {
    const [first, second] = entry.line.points_display;
    const selected = entry.line.line_id === selectedLineId;
    const classes = ["loupe-annotation-line", entry.family];
    if (selected) {
      classes.push("selected");
      elements.loupeLineLayer.appendChild(svgElement("line", {
        x1: first[0], y1: first[1], x2: second[0], y2: second[1],
        class: "loupe-selection-halo"
      }));
    }
    elements.loupeLineLayer.appendChild(svgElement("line", {
      x1: first[0], y1: first[1], x2: second[0], y2: second[1],
      class: classes.join(" "), "data-line-id": entry.line.line_id
    }));
  }
}

async function toggleTaskReview() {
  const task = activeTask();
  if (!task || currentRecord.state === "user_confirmed") return;
  try {
    await flushSave();
    const response = await api(`/api/review/${encodeURIComponent(currentRecord.source.sha256)}`, {
      method: "POST",
      body: JSON.stringify({expected_revision: currentRecord.revision, task_id: task.task_id, reviewed: elements.taskReviewed.checked})
    });
    currentRecord = await response.json();
    setSaveStatus("审核状态已保存", "ok");
    renderRecord(); updateIndexItemState(currentRecord.state);
  } catch (error) {
    elements.taskReviewed.checked = !elements.taskReviewed.checked;
    showToast(error.message, true);
  }
}

function openConfirmation() {
  if (!currentRecord) return;
  elements.confirmTitle.textContent = `确认 ${currentRecord.tasks.map((task) => task.sample_id).join(" / ")} 的黄金基线`;
  document.querySelectorAll("[data-confirm-check]").forEach((input) => input.checked = false);
  elements.finalConfirmButton.disabled = true;
  elements.confirmDialog.showModal();
}

async function finalConfirmation(event) {
  event.preventDefault();
  const checklist = Object.fromEntries([...document.querySelectorAll("[data-confirm-check]")].map((input) => [input.dataset.confirmCheck, input.checked]));
  try {
    elements.finalConfirmButton.disabled = true;
    const response = await api(`/api/confirm/${encodeURIComponent(currentRecord.source.sha256)}`, {
      method: "POST", body: JSON.stringify({expected_revision: currentRecord.revision, checklist})
    });
    currentRecord = await response.json();
    elements.confirmDialog.close();
    setSaveStatus("黄金基线已冻结", "ok");
    showToast("已写入用户确认的本地黄金基线。", false);
    renderRecord(); updateIndexItemState(currentRecord.state);
  } catch (error) {
    elements.finalConfirmButton.disabled = false;
    showToast(error.message, true);
  }
}

function nextUnfinished() {
  if (!indexData) return;
  const unfinished = indexData.items.filter((item) => item.prepared && item.state !== "user_confirmed");
  if (!unfinished.length) { showToast("所有已准备样片都已确认。", false); return; }
  const position = unfinished.findIndex((item) => item.source_sha256 === currentItem?.source_sha256);
  openSource(unfinished[(position + 1) % unfinished.length]);
}

elements.searchInput.addEventListener("input", renderIndex);
elements.formatFilter.addEventListener("change", renderIndex);
elements.stateFilter.addEventListener("change", renderIndex);
elements.nextButton.addEventListener("click", nextUnfinished);
elements.taskReviewed.addEventListener("change", toggleTaskReview);
elements.confirmButton.addEventListener("click", openConfirmation);
elements.finalConfirmButton.addEventListener("click", finalConfirmation);
elements.undoButton.addEventListener("click", undo);
elements.redoButton.addEventListener("click", redo);
elements.resetViewButton.addEventListener("click", resetView);
elements.maximizeLoupeButton.addEventListener("click", () => setLoupeMaximized(!loupeMaximized));
elements.annotationSvg.addEventListener("pointerdown", startPan);
elements.annotationSvg.addEventListener("pointermove", handlePointerMove);
elements.annotationSvg.addEventListener("pointerup", finishDrag);
elements.annotationSvg.addEventListener("pointercancel", finishDrag);
elements.annotationSvg.addEventListener("wheel", zoomAt, {passive: false});
elements.loupeSvg.addEventListener("click", recenterLoupe);

document.querySelectorAll("[data-nudge]").forEach((button) => {
  button.addEventListener("click", (event) => {
    const [dx, dy] = button.dataset.nudge.split(",").map(Number);
    nudge(dx, dy, event.shiftKey ? 10 : 1);
    elements.annotationSvg.focus({preventScroll: true});
  });
});

document.querySelectorAll("[data-rotate]").forEach((button) => {
  button.addEventListener("click", (event) => {
    rotateSelectedLine(Number(button.dataset.rotate), event.shiftKey ? 10 : 1);
    elements.annotationSvg.focus({preventScroll: true});
  });
});

document.querySelectorAll("[data-confirm-check]").forEach((input) => {
  input.addEventListener("change", () => {
    elements.finalConfirmButton.disabled = ![...document.querySelectorAll("[data-confirm-check]")].every((item) => item.checked);
  });
});

document.addEventListener("keydown", (event) => {
  const modifier = event.metaKey || event.ctrlKey;
  if (modifier && event.key.toLowerCase() === "z") {
    event.preventDefault(); event.shiftKey ? redo() : undo(); return;
  }
  if (modifier || event.altKey) return;
  if (event.key === "Escape" && loupeMaximized) {
    event.preventDefault(); setLoupeMaximized(false); return;
  }
  if (event.key.toLowerCase() === "f" && !event.target.matches("input,select")) {
    event.preventDefault(); setLoupeMaximized(!loupeMaximized); return;
  }
  if (event.target.matches("input,select,button")) return;
  const multiplier = event.shiftKey ? 10 : 1;
  const directions = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
  const rotations = {BracketLeft: -1, BracketRight: 1};
  if (directions[event.key] && selectedLineId) {
    event.preventDefault(); nudge(...directions[event.key], multiplier);
  } else if (rotations[event.code] && selectedLineId) {
    event.preventDefault(); rotateSelectedLine(rotations[event.code], multiplier);
  } else if (event.key === "0") {
    event.preventDefault(); resetView();
  }
});

window.addEventListener("beforeunload", (event) => {
  if (dirty || savePromise) { event.preventDefault(); event.returnValue = ""; }
});

window.addEventListener("resize", () => {
  if (!lastPointer) return;
  clearTimeout(loupeResizeTimer);
  loupeResizeTimer = setTimeout(() => loadLoupe(lastPointer), 140);
});

if (!token) {
  showToast("缺少本地会话 token；请使用命令输出的完整地址。", true);
} else {
  loadIndex().catch((error) => showToast(error.message, true));
}
