"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const ROTATION_STEP_DEGREES = 0.01;
const FIT_REVIEW_CROSS_FRACTION = 0.94;
const FRAME_COLOR_COUNT = 12;
const token = new URLSearchParams(window.location.search).get("token") || "";

const lineBasisLabels = {
  unclassified: "尚未分类",
  directly_visible: "直接可见边界",
  visible_content_limit: "可见内容极限",
  human_width_estimate: "按同源可见 frame width 估计（完全不阻断）",
  unresolved_red_stroke: "未解决的红线"
};

const editableLineReviewBases = new Set([
  "unclassified",
  "directly_visible",
  "visible_content_limit",
  "human_width_estimate"
]);

const slotKindLabels = {
  image: "正常照片",
  blank_exposure: "空曝光（无人工几何）",
  partial_exposure: "残缺曝光",
  source_truncated: "源截断",
  unknown: "未知"
};

const adjacencyKindLabels = {
  separator: "正常",
  contact: "接触",
  overlap: "重叠",
  not_applicable: "不适用（空 slot）"
};

const evaluationReasonLabels = {
  required_boundary_basis_missing: "必要边界依据未完成",
  shared_edges_lack_direct_visibility: "共享上下边缘缺少直接可见依据",
  no_direct_sequence_anchor: "没有直接可见的长轴定位边",
  clustered_non_direct_boundaries: "一个 Frame 两侧均非直接可见，且其它 Frame 仍有非直接边界",
  non_direct_boundary_count_threshold: "非直接可见边界数量达到 challenge 阈值",
  two_sided_floating_partial_sequence: "两侧浮动的短片条缺少双端直接 outer",
  unknown_required_frame: "存在未知必需 Frame",
  contact_adjacency: "存在接触 Frame",
  overlap_adjacency: "存在叠片 Frame",
  source_truncation_not_geometrically_established: "源截断几何尚未成立",
  count_outside_fixed_template_contract: "count 超出当前固定模板合同"
};

const salienceClassificationLabels = {
  not_applicable: "不适用",
  production_edge_matched: "生产测量已匹配",
  no_matched_production_edge: "生产测量未匹配",
  not_measurable_at_source_boundary: "贴近 TIFF 边缘，无法双侧测量"
};

const salienceReviewLabels = {
  unreviewed: "未人工结论",
  confirmed_low: "已确认机器低显著度",
  confirmed_not_low: "已确认并非低显著度"
};

const elements = Object.fromEntries([
  "progressText", "searchInput", "formatFilter", "stateFilter", "roleFilter", "sourceList",
  "nextButton", "sampleTitle", "stateBadge", "sourceFacts", "saveStatus",
  "undoButton", "redoButton", "resetViewButton", "sourceReferenceSummary", "sourceReviewed",
  "confirmButton", "canvasStage", "annotationSvg", "sourceImage", "polygonLayer",
  "lineLayer", "cursorCoordinate", "loupeSvg", "loupeImage",
  "loupeCard", "loupeWrap", "loupeTitle", "loupeSelectionLabel", "maximizeLoupeButton", "loupeHelp",
  "loupePolygonLayer", "loupeLineLayer",
  "loupeCrossX", "loupeCrossY", "loupeEmpty", "selectedLineLabel",
  "lineCoordinates", "lineReviewBasisSelect", "frameSelect", "frameSlotKindSelect",
  "machineSaliencePanel", "machineSalienceLabel", "machineSalienceEvidence",
  "machineSalienceReviewSelect",
  "batchSelectionSummary", "selectUnclassifiedLinesButton", "selectAllLinesButton",
  "clearLineSelectionButton", "batchLineList", "batchReviewBasisSelect",
  "applyBatchReviewBasisButton", "frameAssignmentSummary", "adjacencyList", "diagnostics",
  "confirmDialog", "confirmTitle", "finalConfirmButton", "toast"
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
let selectedLineId = null;
let selectedFrameKey = null;
let batchSelectedLineIds = new Set();
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
let fullHeightReviewVisited = false;
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

function lineUseLabel(line) {
  const uses = line.uses || [];
  if (line.family === "shared") {
    return uses.includes("short_low") ? "共享边 A" : "共享边 B";
  }
  return uses.join(" / ").replaceAll(".start", " start").replaceAll(".end", " end");
}

function basisAttentionText(summary) {
  if (!summary) return "尚未准备或等待保存";
  if (summary.status === "all_directly_visible") return "全部线均为直接可见边界";
  const lines = summary.attention_lines.map((line) => (
    `${line.line_id}（${lineUseLabel(line)}：${lineBasisLabels[line.review_basis] || line.review_basis}）`
  ));
  const conditions = (summary.source_conditions || []).map((condition) => (
    `${condition.task_id}#${condition.ordinal}（${slotKindLabels[condition.slot_kind] || condition.slot_kind}）`
  ));
  return [...lines, ...conditions].join("；") || "无非直接可见依据";
}

function evaluationRoleText(summary) {
  if (!summary) return "评测角色保存后重新计算";
  const taskRoles = summary.tasks || [];
  const mixed = new Set(taskRoles.map((task) => task.cohort_role)).size > 1;
  if (!mixed) return summary.source_role;
  return `${summary.source_role}（${taskRoles.map((task) => `${task.sample_id}:${task.cohort_role}`).join(" / ")}）`;
}

function challengeReasonText(summary) {
  if (!summary) return "保存后重新计算";
  const challenged = (summary.tasks || []).filter((task) => task.cohort_role === "challenge");
  return challenged.map((task) => {
    const reasons = task.reasons.map((reason) => {
      const label = evaluationReasonLabels[reason] || reason;
      if (reason === "clustered_non_direct_boundaries") {
        const frames = task.clustered_non_direct_frame_ordinals || [];
        return `${label}（Frame ${frames.join("、")}）`;
      }
      if (reason === "non_direct_boundary_count_threshold") {
        return `${label}（${task.non_direct_boundary_count}/${task.non_direct_boundary_challenge_threshold} 条）`;
      }
      return label;
    });
    return `${task.sample_id}:${reasons.join("、")}`;
  }).join(" / ") || "无";
}

function renderIndex() {
  if (!indexData) return;
  const confirmed = indexData.states.user_confirmed || 0;
  const needsClassification = indexData.basis_states?.needs_classification || 0;
  const nonDirect = indexData.basis_states?.has_non_direct_basis || 0;
  const direct = indexData.basis_states?.all_directly_visible || 0;
  const nominal = indexData.evaluation_roles?.nominal || 0;
  const challenge = indexData.evaluation_roles?.challenge || 0;
  const salience = indexData.machine_salience || {};
  const salienceTotal = salience.high_confidence_proposal_line_count || 0;
  const saliencePending = salience.pending_proposal_line_count || 0;
  const salienceReviewed = salienceTotal - saliencePending;
  elements.progressText.textContent = `${confirmed}/${indexData.total_unique_sources} 已确认 · 机器低显著 ${salienceReviewed}/${salienceTotal} 已审 · ${needsClassification} 待分类 · ${nonDirect} 非直接 · ${direct} 全直接 · ${nominal} nominal · ${challenge} challenge`;
  const query = elements.searchInput.value.trim().toLowerCase();
  const state = elements.stateFilter.value;
  const format = elements.formatFilter.value;
  const role = elements.roleFilter.value;
  elements.nextButton.textContent = state.startsWith("salience_")
    ? "下一张显著度审阅"
    : "下一张未完成";
  elements.sourceList.replaceChildren();
  const items = indexData.items.filter((item) => {
    const matchesSearch = !query || sourceLabel(item).toLowerCase().includes(query) || item.source_sha256.includes(query);
    const matchesFormat = format === "all" || item.format_id === format;
    const basisStatus = item.line_basis_summary?.status;
    const frameStatus = item.frame_state_summary?.status;
    const refinement = item.refinement_summary;
    const itemSalience = item.machine_salience_summary || {};
    const sourceRole = item.evaluation_role_summary?.source_role;
    const matchesState = state === "all"
      || (state === "unfinished" && item.state !== "user_confirmed")
      || (state === "basis_attention" && ["needs_classification", "has_non_direct_basis"].includes(basisStatus))
      || (state === "all_directly_visible" && basisStatus === "all_directly_visible")
      || (state === "all_frames_normal" && frameStatus === "all_frames_normal")
      || (state === "has_non_normal_frames" && frameStatus === "has_non_normal_frames")
      || (state === "refinement_moved" && refinement?.moved_line_count > 0)
      || (state === "refinement_retained" && refinement && refinement.moved_line_count === 0)
      || (state === "salience_pending" && itemSalience.pending_proposal_line_count > 0)
      || (state === "salience_recall_unreviewed" && itemSalience.pending_recall_line_count > 0)
      || (state === "salience_confirmed_low" && itemSalience.confirmed_low_line_count > 0)
      || (state === "salience_confirmed_not_low" && itemSalience.confirmed_not_low_line_count > 0)
      || item.state === state;
    const matchesRole = role === "all" || sourceRole === role;
    return matchesSearch && matchesFormat && matchesState && matchesRole;
  });
  for (const item of items) {
    const button = document.createElement("button");
    button.className = `source-item${currentItem?.source_sha256 === item.source_sha256 ? " active" : ""}`;
    button.dataset.sha = item.source_sha256;
    const basisText = basisAttentionText(item.line_basis_summary);
    const roleText = evaluationRoleText(item.evaluation_role_summary);
    const roleClass = ["nominal", "challenge"].includes(item.evaluation_role_summary?.source_role)
      ? item.evaluation_role_summary.source_role
      : "pending";
    const pendingSalience = item.machine_salience_summary?.pending_proposal_line_count || 0;
    const confirmedLow = item.machine_salience_summary?.confirmed_low_line_count || 0;
    const salienceText = pendingSalience
      ? `低显著候选 ${pendingSalience}`
      : (confirmedLow ? `已确认低显著 ${confirmedLow}` : "");
    button.title = `${roleText} · ${challengeReasonText(item.evaluation_role_summary)} · ${basisText}`;
    button.innerHTML = `
      <span class="state-dot ${item.state}"></span>
      <span class="source-name"><strong>${escapeHtml(sourceLabel(item))}</strong><small>${escapeHtml(item.format_id)} · ${item.source_sha256.slice(0, 10)}</small><small>${escapeHtml(roleText)}</small><small>${escapeHtml(basisText)}</small>${salienceText ? `<small class="salience-source-note">${escapeHtml(salienceText)}</small>` : ""}</span>
      <span class="source-tail"><span class="source-role ${roleClass}">${escapeHtml(roleClass === "pending" ? "待计算" : roleClass)}</span><span class="source-count">count ${escapeHtml(countsLabel(item))}</span></span>`;
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
  const initial = indexData.items.find((item) => item.machine_salience_summary?.pending_proposal_line_count > 0 && item.prepared)
    || indexData.items.find((item) => item.state !== "user_confirmed" && item.prepared)
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
    selectedLineId = firstSalienceLineId(elements.stateFilter.value);
    selectedFrameKey = null;
    batchSelectedLineIds = new Set();
    elements.batchReviewBasisSelect.value = "";
    history = [];
    future = [];
    dirty = false;
    editGeneration = 0;
    const extent = currentRecord.source.canonical_extent;
    const selected = lineById(selectedLineId);
    lastPointer = selected
      ? [
          (selected.points_display[0][0] + selected.points_display[1][0]) / 2,
          (selected.points_display[0][1] + selected.points_display[1][1]) / 2
        ]
      : [extent.width / 2, extent.height / 2];
    fullHeightReviewVisited = false;
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
  renderReferenceSummary();
  renderGeometry();
  renderBatchClassification();
  renderFrameControls();
  renderAdjacencyRelations();
  renderDiagnostics();
  updateControls();
}

function sourceIsReviewed() {
  return Boolean(
    currentRecord
    && currentRecord.tasks.every((task) => currentRecord.reviewed_task_ids.includes(task.task_id))
  );
}

function renderReferenceSummary() {
  elements.sourceReferenceSummary.replaceChildren();
  if (!currentRecord) return;
  const label = document.createElement("strong");
  label.textContent = "共享 source reference";
  const detail = document.createElement("span");
  const basisSummary = currentRecord.line_basis_summary;
  detail.textContent = `${currentRecord.tasks.map((task) => task.sample_id).join(" / ")} · count ${currentRecord.tasks.map((task) => task.count).join("/")} · ${evaluationRoleText(currentRecord.evaluation_role_summary)} · ${basisAttentionText(basisSummary)}`;
  elements.sourceReferenceSummary.append(label, detail);
  elements.sourceReferenceSummary.classList.toggle("reviewed", sourceIsReviewed());
}

function allLines() {
  return currentRecord ? [...currentRecord.shared_edges, ...currentRecord.boundary_pool] : [];
}

function lineById(identity) {
  return allLines().find((line) => line.line_id === identity) || null;
}

function salienceMatchesFilter(fact, filter) {
  if (!fact?.eligible) return false;
  if (filter === "salience_pending") {
    return fact.high_confidence_proposal && fact.review_status === "unreviewed";
  }
  if (filter === "salience_recall_unreviewed") {
    return fact.recall_candidate && fact.review_status === "unreviewed";
  }
  if (filter === "salience_confirmed_low") return fact.review_status === "confirmed_low";
  if (filter === "salience_confirmed_not_low") return fact.review_status === "confirmed_not_low";
  return false;
}

function firstSalienceLineId(filter) {
  if (!filter.startsWith("salience_") || !currentRecord) return null;
  return currentRecord.boundary_pool.find((line) => (
    salienceMatchesFilter(line.machine_salience, filter)
  ))?.line_id || null;
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

function polygonForReference(reference) {
  const pool = new Map(currentRecord.boundary_pool.map((line) => [line.line_id, line]));
  const low = currentRecord.shared_edges[0];
  const high = currentRecord.shared_edges[1];
  const start = pool.get(reference.start_boundary_id);
  const stop = pool.get(reference.end_boundary_id);
  if (!start || !stop) return null;
  const polygon = currentRecord.strip_axis_display === "horizontal"
    ? [intersection(low, start), intersection(low, stop), intersection(high, stop), intersection(high, start)]
    : [intersection(low, start), intersection(high, start), intersection(high, stop), intersection(low, stop)];
  return polygon.every(Boolean) ? polygon : null;
}

function clipPolygonToSourceRaster(polygon) {
  const width = currentRecord.source.canonical_extent.width;
  const height = currentRecord.source.canonical_extent.height;
  const bounds = [
    [0, -0.5, true],
    [0, width - 0.5, false],
    [1, -0.5, true],
    [1, height - 0.5, false]
  ];
  let clipped = polygon.map((point) => [...point]);
  for (const [axis, boundary, keepGreater] of bounds) {
    if (!clipped.length) break;
    const output = [];
    let previous = clipped[clipped.length - 1];
    let previousInside = keepGreater ? previous[axis] >= boundary : previous[axis] <= boundary;
    for (const current of clipped) {
      const currentInside = keepGreater ? current[axis] >= boundary : current[axis] <= boundary;
      if (currentInside !== previousInside) {
        const fraction = (boundary - previous[axis]) / (current[axis] - previous[axis]);
        const intersectionPoint = [
          previous[0] + fraction * (current[0] - previous[0]),
          previous[1] + fraction * (current[1] - previous[1])
        ];
        intersectionPoint[axis] = boundary;
        output.push(intersectionPoint);
      }
      if (currentInside) output.push([...current]);
      previous = current;
      previousInside = currentInside;
    }
    clipped = output;
  }
  return clipped;
}

function sourcePhysicalFrames() {
  if (!currentRecord) return [];
  const byPair = new Map();
  for (const task of currentRecord.tasks) {
    for (const slot of task.slots) {
      const reference = slot.reference_geometry;
      if (reference?.kind !== "boundary_pair") continue;
      const key = `${reference.start_boundary_id}/${reference.end_boundary_id}`;
      if (!byPair.has(key)) {
        byPair.set(key, {
          key,
          reference,
          assignments: []
        });
      }
      byPair.get(key).assignments.push({
        taskId: task.task_id,
        sampleId: task.sample_id,
        count: task.count,
        ordinal: slot.ordinal,
        slotKind: slot.slot_kind
      });
    }
  }
  const longIndex = currentRecord.strip_axis_display === "horizontal" ? 0 : 1;
  return [...byPair.values()].map((frame) => {
    const physicalPoints = polygonForReference(frame.reference);
    const slotKind = frame.assignments[0]?.slotKind;
    const position = physicalPoints
      ? physicalPoints.reduce((sum, point) => sum + point[longIndex] / physicalPoints.length, 0)
      : Number.POSITIVE_INFINITY;
    return {...frame, physicalPoints, position, slotKind};
  }).sort((left, right) => left.position - right.position)
    .map((frame, index) => ({...frame, sourceOrdinal: index + 1}));
}

function sourceReferenceFrames() {
  return sourcePhysicalFrames().map((frame) => ({
    ...frame,
    points: frame.physicalPoints && frame.slotKind === "source_truncated"
      ? clipPolygonToSourceRaster(frame.physicalPoints)
      : frame.physicalPoints
  })).filter((frame) => frame.points?.length >= 3);
}

function pointInsideSourceRaster(point) {
  const extent = currentRecord.source.canonical_extent;
  return (
    Number.isFinite(point[0])
    && Number.isFinite(point[1])
    && point[0] >= -0.5
    && point[0] <= extent.width - 0.5
    && point[1] >= -0.5
    && point[1] <= extent.height - 0.5
  );
}

function polygonArea(points) {
  if (!points?.length) return 0;
  return points.reduce((total, point, index) => {
    const next = points[(index + 1) % points.length];
    return total + point[0] * next[1] - next[0] * point[1];
  }, 0) / 2;
}

function frameGeometryIssues() {
  const invalid = [];
  const pendingSourceTruncation = [];
  for (const frame of sourcePhysicalFrames()) {
    const physical = frame.physicalPoints;
    const assignments = frame.assignments;
    if (!physical || physical.length < 3 || polygonArea(physical) < 4) {
      invalid.push(...assignments.map((item) => ({...item, reason: "invalid_polygon"})));
      continue;
    }
    const leavesSource = physical.some((point) => !pointInsideSourceRaster(point));
    const sourceTruncated = assignments.filter((item) => item.slotKind === "source_truncated");
    const ordinary = assignments.filter((item) => item.slotKind !== "source_truncated");
    if (leavesSource && ordinary.length) {
      invalid.push(...ordinary.map((item) => ({...item, reason: "ordinary_leaves_source"})));
    }
    if (!leavesSource && sourceTruncated.length) {
      pendingSourceTruncation.push(...sourceTruncated);
    }
    if (leavesSource && sourceTruncated.length) {
      const clipped = clipPolygonToSourceRaster(physical);
      if (clipped.length < 3 || polygonArea(clipped) < 4) {
        invalid.push(...sourceTruncated.map((item) => ({...item, reason: "no_source_intersection"})));
      }
    }
  }
  return {invalid, pendingSourceTruncation};
}

function frameIssueLabels(items) {
  return [...new Set(items.map((item) => `${item.sampleId}#${item.ordinal}`))].join(" / ");
}

function frameGeometryBlockingMessage(issues = frameGeometryIssues()) {
  const ordinary = issues.invalid.filter((item) => item.reason === "ordinary_leaves_source");
  if (ordinary.length) {
    return `${frameIssueLabels(ordinary)} 不是源截断，不能越出 TIFF。已停止在最后一个可保存的位置。`;
  }
  const missing = issues.invalid.filter((item) => item.reason === "no_source_intersection");
  if (missing.length) {
    return `${frameIssueLabels(missing)} 与 TIFF 已没有可用交集。已停止在最后一个可保存的位置。`;
  }
  if (issues.invalid.length) {
    return `${frameIssueLabels(issues.invalid)} 的边界无法形成有效 Frame。已停止在最后一个可保存的位置。`;
  }
  return null;
}

function syncLocalFrameStateSummary() {
  if (!currentRecord) return;
  const nonNormalSlots = currentRecord.tasks.flatMap((task) => task.slots
    .filter((slot) => slot.slot_kind !== "image")
    .map((slot) => ({task_id: task.task_id, ordinal: slot.ordinal, slot_kind: slot.slot_kind}))
  );
  const pending = frameGeometryIssues().pendingSourceTruncation.map((item) => ({
    task_id: item.taskId,
    ordinal: item.ordinal
  }));
  currentRecord.frame_state_summary = {
    status: nonNormalSlots.length ? "has_non_normal_frames" : "all_frames_normal",
    all_frames_normal: nonNormalSlots.length === 0,
    non_normal_slot_count: nonNormalSlots.length,
    non_normal_slots: nonNormalSlots,
    pending_source_truncated_geometry_count: pending.length,
    pending_source_truncated_geometry: pending
  };
}

function applyConstrainedLinePoints(line, points) {
  const before = line.points_display.map((point) => [...point]);
  line.points_display = points.map((point) => [...point]);
  const issues = frameGeometryIssues();
  const message = frameGeometryBlockingMessage(issues);
  if (message) {
    line.points_display = before;
    return {accepted: false, message};
  }
  syncLocalFrameStateSummary();
  return {accepted: true, message: null};
}

function canonicalSourceTask() {
  if (!currentRecord?.tasks?.length) return null;
  const canonicalTaskId = currentRecord.diagnostics?.source_reference_mapping?.canonical_task_id;
  return currentRecord.tasks.find((task) => task.task_id === canonicalTaskId)
    || [...currentRecord.tasks].sort((left, right) => (
      right.count - left.count || left.task_id.localeCompare(right.task_id)
    ))[0];
}

function boundaryAxisPosition(line) {
  const [[x1, y1], [x2, y2]] = line.points_display;
  if (currentRecord.strip_axis_display === "horizontal") {
    const reference = 0.5 * (currentRecord.source.canonical_extent.height - 1);
    return x1 + (x2 - x1) * (reference - y1) / (y2 - y1);
  }
  const reference = 0.5 * (currentRecord.source.canonical_extent.width - 1);
  return y1 + (y2 - y1) * (reference - x1) / (x2 - x1);
}

function derivedAdjacenciesForTask(task) {
  const pool = new Map(currentRecord.boundary_pool.map((line) => [line.line_id, line]));
  return task.adjacencies.map((adjacency, index) => {
    const left = task.slots[index].reference_geometry;
    const right = task.slots[index + 1].reference_geometry;
    let kind = "not_applicable";
    if (left?.kind === "boundary_pair" && right?.kind === "boundary_pair") {
      if (left.end_boundary_id === right.start_boundary_id) {
        kind = "contact";
      } else {
        const leftEnd = pool.get(left.end_boundary_id);
        const rightStart = pool.get(right.start_boundary_id);
        kind = leftEnd && rightStart && boundaryAxisPosition(leftEnd) > boundaryAxisPosition(rightStart)
          ? "overlap"
          : "separator";
      }
    }
    return {...adjacency, kind};
  });
}

function renderAdjacencyRelations() {
  elements.adjacencyList.replaceChildren();
  const task = canonicalSourceTask();
  const adjacencies = task ? derivedAdjacenciesForTask(task) : [];
  if (!adjacencies.length) {
    const empty = document.createElement("p");
    empty.className = "adjacency-empty";
    empty.textContent = "此 source 只有一个 Frame，没有相邻关系。";
    elements.adjacencyList.appendChild(empty);
    return;
  }
  for (const adjacency of adjacencies) {
    const row = document.createElement("div");
    row.className = "adjacency-row";
    const pair = document.createElement("span");
    pair.textContent = `Frame ${adjacency.left_ordinal}–${adjacency.right_ordinal}`;
    const kind = document.createElement("strong");
    kind.className = `adjacency-kind ${adjacency.kind}`;
    kind.textContent = adjacencyKindLabels[adjacency.kind] || adjacency.kind;
    row.append(pair, kind);
    elements.adjacencyList.appendChild(row);
  }
}

function sourceBoundaryRoles() {
  return sourcePhysicalFrames().flatMap((frame) => [
    {identity: frame.reference.start_boundary_id, ordinal: frame.sourceOrdinal, role: "start"},
    {identity: frame.reference.end_boundary_id, ordinal: frame.sourceOrdinal, role: "end"}
  ]);
}

function svgElement(name, attributes = {}) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

function frameColorClass(sourceOrdinal) {
  return `frame-color-${((sourceOrdinal - 1) % FRAME_COLOR_COUNT) + 1}`;
}

function activeLineEntries() {
  const sourceRoles = sourceBoundaryRoles();
  const used = new Set(sourceRoles.map((entry) => entry.identity));
  return [
    ...currentRecord.shared_edges.map((line, index) => ({
      line,
      family: "shared",
      label: index === 0 ? "共享边 A" : "共享边 B",
      active: true,
      role: "shared"
    })),
    ...currentRecord.boundary_pool.map((line) => {
      const assignments = sourceRoles.filter((entry) => entry.identity === line.line_id);
      const roles = new Set(assignments.map((entry) => entry.role));
      const role = roles.size === 2 ? "start-end" : (roles.values().next().value || "unused");
      const label = assignments.length
        ? assignments.map((entry) => `${entry.ordinal}${entry.role === "end" ? "E" : "S"}`).join("/")
        : line.line_id;
      return {
        line,
        family: "boundary",
        label,
        active: used.has(line.line_id) || line.review_basis === "unresolved_red_stroke",
        role
      };
    })
  ];
}

function roleLabel(entry) {
  return ({
    shared: "共享边",
    start: "start",
    end: "end",
    "start-end": "start/end 接触边",
    unused: "未用于 source reference"
  })[entry?.role] || "未分类";
}

function batchLineEntries() {
  return currentRecord ? activeLineEntries().filter((entry) => entry.active) : [];
}

function updateBatchSelectionSummary(entries = batchLineEntries()) {
  const activeIds = new Set(entries.map((entry) => entry.line.line_id));
  const selectedCount = [...batchSelectedLineIds]
    .filter((identity) => activeIds.has(identity)).length;
  elements.batchSelectionSummary.textContent = `${selectedCount} / ${entries.length} 条`;
}

function renderBatchClassification() {
  const entries = batchLineEntries();
  const activeIds = new Set(entries.map((entry) => entry.line.line_id));
  batchSelectedLineIds = new Set(
    [...batchSelectedLineIds].filter((identity) => activeIds.has(identity))
  );
  elements.batchLineList.replaceChildren();
  if (!entries.length) {
    const empty = document.createElement("span");
    empty.className = "batch-line-empty";
    empty.textContent = "没有可分类的活动线";
    elements.batchLineList.appendChild(empty);
    updateBatchSelectionSummary(entries);
    return;
  }
  const immutable = currentRecord.state === "user_confirmed";
  for (const entry of entries) {
    const identity = entry.line.line_id;
    const selected = batchSelectedLineIds.has(identity);
    const row = document.createElement("label");
    row.className = `batch-line-row${selected ? " selected" : ""}`;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selected;
    checkbox.disabled = immutable;
    checkbox.setAttribute("aria-label", `选择 ${entry.label}`);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) batchSelectedLineIds.add(identity);
      else batchSelectedLineIds.delete(identity);
      row.classList.toggle("selected", checkbox.checked);
      updateBatchSelectionSummary(entries);
      updateControls();
    });

    const role = document.createElement("span");
    role.className = `batch-line-role ${entry.role}`;
    role.setAttribute("aria-hidden", "true");

    const description = document.createElement("span");
    description.className = "batch-line-description";
    const name = document.createElement("strong");
    name.textContent = entry.label;
    const basis = document.createElement("small");
    const salience = entry.line.machine_salience;
    const salienceTag = salience?.review_status === "confirmed_low"
      ? " · 已确认机器低显著"
      : (salience?.high_confidence_proposal ? " · ◇低显著候选" : "");
    basis.textContent = `${identity} · ${lineBasisLabels[entry.line.review_basis] || entry.line.review_basis}${salienceTag}`;
    description.append(name, basis);
    row.append(checkbox, role, description);
    elements.batchLineList.appendChild(row);
  }
  updateBatchSelectionSummary(entries);
}

function selectBatchLines(predicate) {
  if (!currentRecord || currentRecord.state === "user_confirmed") return;
  batchSelectedLineIds = new Set(
    batchLineEntries()
      .filter(predicate)
      .map((entry) => entry.line.line_id)
  );
  renderBatchClassification();
  updateControls();
}

function applyBatchReviewBasis() {
  if (!currentRecord || currentRecord.state === "user_confirmed") return;
  const next = elements.batchReviewBasisSelect.value;
  if (!editableLineReviewBases.has(next)) {
    showToast("请先选择统一的边界依据。", true);
    return;
  }
  const targets = batchLineEntries().filter(
    (entry) => batchSelectedLineIds.has(entry.line.line_id)
  );
  if (!targets.length) {
    showToast("请先选择至少一条线。", true);
    return;
  }
  const changed = targets.filter((entry) => entry.line.review_basis !== next);
  if (!changed.length) {
    elements.batchReviewBasisSelect.value = "";
    updateControls();
    showToast("所选线已经使用该边界依据。", false);
    return;
  }
  pushHistory();
  for (const entry of changed) entry.line.review_basis = next;
  currentRecord.line_basis_summary = null;
  markDirty();
  elements.batchReviewBasisSelect.value = "";
  renderGeometry();
  renderBatchClassification();
  renderReferenceSummary();
  renderDiagnostics();
  updateControls();
  showToast(`已批量分类 ${changed.length} 条线。`, false);
}

function visibleStrokeVariants(entry, selected) {
  return entry.family === "boundary" && entry.role === "start-end" && !selected
    ? ["contact-start", "contact-end"]
    : [null];
}

function salienceMarkerClass(fact, prefix = "") {
  if (!fact?.eligible) return null;
  if (fact.review_status === "confirmed_low") return `${prefix}machine-salience-marker confirmed-low`;
  if (fact.review_status === "confirmed_not_low") return `${prefix}machine-salience-marker confirmed-not-low`;
  if (fact.high_confidence_proposal) return `${prefix}machine-salience-marker proposed-low`;
  return null;
}

function renderGeometry() {
  elements.polygonLayer.replaceChildren();
  elements.lineLayer.replaceChildren();
  if (!currentRecord) return;
  sourceReferenceFrames().forEach((frame) => {
    const polygon = svgElement("polygon", {
      points: frame.points.map((point) => `${point[0]},${point[1]}`).join(" "),
      class: `frame-polygon ${frameColorClass(frame.sourceOrdinal)}`,
      "data-frame-ordinal": frame.sourceOrdinal
    });
    const title = svgElement("title");
    const assignments = frame.assignments.map((item) => `${item.sampleId}#${item.ordinal}`).join(" / ");
    title.textContent = `Frame ${frame.sourceOrdinal} · ${assignments}${frame.slotKind === "source_truncated" ? " · 源截断：显示 TIFF 内可用交集" : ""}`;
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
    if (selected) {
      elements.lineLayer.appendChild(svgElement("line", {
        x1: first[0], y1: first[1], x2: second[0], y2: second[1],
        class: "annotation-selection-halo"
      }));
    }
    const salienceClass = salienceMarkerClass(entry.line.machine_salience);
    if (salienceClass) {
      elements.lineLayer.appendChild(svgElement("line", {
        x1: first[0], y1: first[1], x2: second[0], y2: second[1],
        class: salienceClass
      }));
    }
    for (const variant of visibleStrokeVariants(entry, selected)) {
      const classes = ["annotation-line", entry.family, entry.role];
      if (!entry.active) classes.push("inactive");
      if (entry.line.review_basis === "human_width_estimate") classes.push("estimated");
      if (["unclassified", "unresolved_red_stroke"].includes(entry.line.review_basis)) classes.push("unclassified");
      if (selected) classes.push("selected");
      if (variant) classes.push(variant);
      const node = svgElement("line", {
        x1: first[0], y1: first[1], x2: second[0], y2: second[1],
        class: classes.join(" "), "data-line-id": entry.line.line_id
      });
      node.addEventListener("pointerdown", (event) => startLineDrag(event, entry.line.line_id));
      node.addEventListener("click", (event) => { event.stopPropagation(); selectLine(entry.line.line_id); });
      elements.lineLayer.appendChild(node);
    }
    if (entry.active) {
      const middle = [(first[0] + second[0]) / 2, (first[1] + second[1]) / 2];
      const label = svgElement("text", {x: middle[0] + 5, y: middle[1] - 5, class: "line-label"});
      const prefix = entry.line.review_basis === "human_width_estimate"
        ? "≈"
        : (["unclassified", "unresolved_red_stroke"].includes(entry.line.review_basis) ? "?" : "");
      const saliencePrefix = entry.line.machine_salience?.high_confidence_proposal ? "◇" : "";
      label.textContent = `${saliencePrefix}${prefix}${entry.label}`;
      elements.lineLayer.appendChild(label);
    }
  }
  renderSelectedLine();
}

function renderSelectedLine() {
  const line = lineById(selectedLineId);
  const entry = line ? activeLineEntries().find((item) => item.line.line_id === line.line_id) : null;
  elements.loupeSelectionLabel.textContent = line
    ? `${line.line_id} · ${roleLabel(entry)} · ${lineBasisLabels[line.review_basis] || line.review_basis}`
    : "未选线";
  elements.loupeSelectionLabel.classList.toggle("active", Boolean(line));
  if (!line) {
    elements.selectedLineLabel.textContent = "未选择";
    elements.lineReviewBasisSelect.value = "";
    elements.lineCoordinates.querySelectorAll("code").forEach((node) => node.textContent = "—");
    elements.machineSalienceLabel.textContent = "选择一条 start/end";
    elements.machineSalienceEvidence.textContent = "只统计直接可见、且不是接触共用边的 start/end。";
    elements.machineSalienceReviewSelect.value = "unreviewed";
    elements.machineSaliencePanel.className = "machine-salience-panel";
    renderLoupeGeometry();
    return;
  }
  const basisLabel = lineBasisLabels[line.review_basis] || line.review_basis;
  const refinement = currentRecord.diagnostics?.refinement?.lines?.[line.line_id];
  const refinementLabel = refinement
    ? ` · 精修${String(refinement.decision).startsWith("moved_to_") ? "已移动" : "保留"} · ${refinement.human_review_status || "pending"}`
    : "";
  elements.selectedLineLabel.textContent = `${line.line_id} · ${roleLabel(entry)} · ${basisLabel} · ${line.origin}${refinementLabel}`;
  elements.lineReviewBasisSelect.value = line.review_basis;
  const codes = elements.lineCoordinates.querySelectorAll("code");
  line.points_display.forEach((point, index) => {
    codes[index].textContent = `x ${point[0].toFixed(2)} · y ${point[1].toFixed(2)}`;
  });
  renderMachineSalience(line);
  renderLoupeGeometry();
}

function renderMachineSalience(line) {
  const fact = line.machine_salience;
  elements.machineSaliencePanel.className = "machine-salience-panel";
  if (!fact) {
    elements.machineSalienceLabel.textContent = "尚未分析或几何已变化";
    elements.machineSalienceEvidence.textContent = "重新运行本地显著度统计后才能审阅；黄金线不受影响。";
    elements.machineSalienceReviewSelect.value = "unreviewed";
    return;
  }
  elements.machineSalienceReviewSelect.value = fact.review_status;
  if (!fact.eligible) {
    const reasons = {
      shared_start_end_contact_boundary: "接触共用边没有唯一的照片侧与 separator 侧",
      not_directly_visible: "不是直接可见边界",
      not_referenced_by_frame: "未被 Frame 引用",
      ambiguous_physical_role: "物理角色不唯一"
    };
    elements.machineSalienceLabel.textContent = "不适用";
    elements.machineSalienceEvidence.textContent = reasons[fact.not_applicable_reason] || fact.not_applicable_reason;
    elements.machineSaliencePanel.classList.add("not-applicable");
    return;
  }
  const classification = salienceClassificationLabels[fact.machine_classification]
    || fact.machine_classification;
  const review = salienceReviewLabels[fact.review_status] || fact.review_status;
  const proposal = fact.high_confidence_proposal
    ? "高置信机器候选"
    : (fact.recall_candidate ? "宽召回线索" : classification);
  elements.machineSalienceLabel.textContent = `${proposal} · ${review}`;
  if (fact.high_confidence_proposal) elements.machineSaliencePanel.classList.add("proposed-low");
  if (fact.review_status === "confirmed_low") elements.machineSaliencePanel.classList.add("confirmed-low");
  if (fact.review_status === "confirmed_not_low") elements.machineSaliencePanel.classList.add("confirmed-not-low");
  const measurement = fact.measurement || {};
  const metrics = measurement.side_metrics || {};
  const q75 = (name) => Number(metrics[name]?.q75).toFixed(2);
  elements.machineSalienceEvidence.textContent = (
    fact.machine_classification === "not_measurable_at_source_boundary"
      ? "线旁无法在 TIFF 内取得完整双侧像素窗，因此不判为低显著。"
      : `${classification} · 合格局部强边 ${measurement.qualified_region_count ?? "—"} · 匹配 ${measurement.matched_region_count ?? "—"} · tone Δ q75 ${q75("tone_difference_codes")} · texture Δ q75 ${q75("texture_difference_codes")} · 画面内纹理 q75 ${q75("inside_texture_codes")}`
  );
}

function renderFrameControls() {
  const frames = sourcePhysicalFrames();
  elements.frameSelect.replaceChildren();
  if (!frames.length) {
    selectedFrameKey = null;
    elements.frameAssignmentSummary.textContent = "无有界 Frame";
    elements.frameSlotKindSelect.value = "image";
    return;
  }
  if (!frames.some((frame) => frame.key === selectedFrameKey)) {
    selectedFrameKey = frames[0].key;
  }
  for (const frame of frames) {
    const kind = frame.assignments[0].slotKind;
    const assignments = frame.assignments
      .map((item) => `${item.sampleId}#${item.ordinal}`)
      .join(" / ");
    const option = document.createElement("option");
    option.value = frame.key;
    option.textContent = `Frame ${frame.sourceOrdinal} · ${assignments} · ${slotKindLabels[kind] || kind}`;
    elements.frameSelect.appendChild(option);
  }
  elements.frameSelect.value = selectedFrameKey;
  const selected = frames.find((frame) => frame.key === selectedFrameKey);
  const kinds = new Set(selected.assignments.map((item) => item.slotKind));
  const kind = kinds.size === 1 ? selected.assignments[0].slotKind : "unknown";
  elements.frameSlotKindSelect.value = kind;
  elements.frameAssignmentSummary.textContent = selected.assignments
    .map((item) => `${item.sampleId}#${item.ordinal}`)
    .join(" / ");
}

function renderDiagnostics() {
  elements.diagnostics.replaceChildren();
  if (!currentRecord) return;
  const reviewContext = currentRecord.diagnostics.review_context || {};
  const redImport = currentRecord.diagnostics.red_markup_import;
  const refinement = currentRecord.diagnostics.refinement;
  const taskContexts = reviewContext.tasks || {};
  const taskSummary = currentRecord.tasks
    .map((task) => `${task.sample_id}:${task.count}`)
    .join(" / ");
  const templateSummary = currentRecord.tasks.map((task) => {
    const fit = currentRecord.diagnostics.task_fits?.[task.task_id];
    return `${task.sample_id}:${fit ? Number(fit.template_score).toFixed(3) : "—"}`;
  }).join(" / ");
  const caseTags = [...new Set(currentRecord.tasks.flatMap(
    (task) => taskContexts[task.task_id]?.case_tags || []
  ))];
  const slotSummary = currentRecord.tasks.flatMap((task) => task.slots
    .filter((slot) => slot.slot_kind !== "image")
    .map((slot) => `${task.sample_id} ${slot.ordinal}:${slot.slot_kind}`)
  ).join(" / ") || "全部 image";
  const noReferenceSummary = currentRecord.tasks.flatMap((task) => task.slots
    .filter((slot) => slot.reference_geometry?.kind === "not_applicable")
    .map((slot) => `${task.sample_id} ${slot.ordinal}:${slot.slot_kind}`)
  ).join(" / ") || "无";
  const adjacencySummary = currentRecord.tasks.flatMap((task) => derivedAdjacenciesForTask(task)
    .filter((adjacency) => adjacency.kind !== "separator")
    .map((adjacency) => `${task.sample_id} ${adjacency.left_ordinal}-${adjacency.right_ordinal}:${adjacencyKindLabels[adjacency.kind] || adjacency.kind}`)
  ).join(" / ") || "全部正常";
  const notes = [...new Set(currentRecord.tasks.flatMap(
    (task) => taskContexts[task.task_id]?.notes || []
  ))];
  const machineLines = currentRecord.tasks.flatMap((task) => {
    const retained = redImport?.task_assignments?.[task.task_id]?.machine_retained_role_indices || [];
    return retained.length ? [`${task.sample_id}:角色 ${retained.join(", ")}`] : [];
  });
  const basisSummary = currentRecord.line_basis_summary;
  const evaluationSummary = currentRecord.evaluation_role_summary;
  const pendingSourceTruncation = (
    currentRecord.frame_state_summary?.pending_source_truncated_geometry || []
  );
  const sourceTruncationSummary = pendingSourceTruncation.length
    ? `待放置：${pendingSourceTruncation.map((item) => `${item.task_id}#${item.ordinal}`).join(" / ")}`
    : slotSummary.includes("source_truncated")
      ? "物理 Frame 已越出 TIFF；显示 TIFF 内交集"
      : "不适用";
  const basisStateLabel = ({
    needs_classification: "仍有线未分类",
    has_non_direct_basis: "含非直接可见边界",
    all_directly_visible: "全部为直接可见边界"
  })[basisSummary?.status] || "保存后重新分类";
  const rows = [
    ["来源", currentRecord.origin],
    ["count 任务", `${taskSummary}（共享一套 source reference）`],
    ["胶片极性", reviewContext.film_polarity ? `${reviewContext.film_polarity}（仅校准分层）` : "未记录"],
    ["坐标", "raw TIFF pixel centers"],
    ["预标版本", currentRecord.diagnostics.proposal_revision || "人工保留草稿"],
    ["精修版本", refinement?.refinement_revision || "尚未精修"],
    ["精修结果", refinement ? `${refinement.moved_line_count} 条移动 · ${refinement.retained_line_count} 条保留 · ${refinement.human_review_state || "pending"}` : "尚未生成"],
    ["共享边 MAD", (currentRecord.diagnostics.shared_fit_mad_analysis_px || []).map((value) => Number(value).toFixed(2)).join(" / ") || "未记录"],
    ["模板分数", templateSummary],
    ["结构标签", caseTags.join(" / ") || "常规"],
    ["Slot 语义", slotSummary],
    ["源截断几何", sourceTruncationSummary],
    ["无需人工 reference", noReferenceSummary],
    ["相邻关系", adjacencySummary],
    ["人工备注", notes.join("；") || "无"],
    ["评测角色", evaluationRoleText(evaluationSummary)],
    ["Challenge 依据", challengeReasonText(evaluationSummary)],
    ["依据分类", basisStateLabel],
    ["需关注的线", basisAttentionText(basisSummary)],
    ["机器提案提示（不阻断）", currentRecord.diagnostics.unresolved?.length ? `${currentRecord.diagnostics.unresolved.length} 项` : "无"],
    ["权限", currentRecord.state === "user_confirmed" ? "用户确认" : "仅 proposal"]
  ];
  const selectedRefinement = selectedLineId
    ? refinement?.lines?.[selectedLineId]
    : null;
  if (selectedRefinement) {
    const delta = selectedRefinement.endpoint_delta_px || [0, 0];
    rows.splice(3, 0, [
      "当前线精修",
      `${selectedRefinement.decision} · ${selectedRefinement.reason} · 端点 Δ ${Number(delta[0]).toFixed(2)} / ${Number(delta[1]).toFixed(2)} px · ${selectedRefinement.human_review_status || "pending"}`
    ]);
  }
  if (redImport) {
    rows.splice(1, 0, ["红线草稿", `${redImport.applied_shared_edge_count}/${redImport.detected_shared_edge_count} 条共享边已采用 · ${redImport.detected_boundary_count} 条长轴边`]);
    rows.splice(2, 0, ["机器补线", machineLines.join(" / ") || "无"]);
    rows.splice(3, 0, ["机器共享边", redImport.machine_retained_shared_edge_indices?.length ? `边 ${redImport.machine_retained_shared_edge_indices.join(", ")}` : "无"]);
  }
  for (const [name, value] of rows) {
    const term = document.createElement("dt"); term.textContent = name;
    const detail = document.createElement("dd"); detail.textContent = value;
    elements.diagnostics.append(term, detail);
  }
}

function updateControls() {
  const immutable = currentRecord?.state === "user_confirmed";
  const allReviewed = sourceIsReviewed();
  const basisComplete = Boolean(currentRecord?.line_basis_summary?.classification_complete);
  const sourceTruncationReady = (
    currentRecord?.frame_state_summary?.pending_source_truncated_geometry_count === 0
  );
  elements.sourceReviewed.disabled = (
    !currentRecord || immutable || !basisComplete || !sourceTruncationReady
  );
  elements.sourceReviewed.checked = allReviewed;
  elements.confirmButton.disabled = (
    !currentRecord
    || immutable
    || !basisComplete
    || !sourceTruncationReady
    || !allReviewed
    || dirty
  );
  elements.undoButton.disabled = immutable || history.length === 0;
  elements.redoButton.disabled = immutable || future.length === 0;
  elements.maximizeLoupeButton.disabled = !currentRecord || !lastPointer;
  const selectedEntry = selectedLineId
    ? activeLineEntries().find((entry) => entry.line.line_id === selectedLineId)
    : null;
  elements.lineReviewBasisSelect.disabled = immutable || !selectedEntry;
  const selectedSalience = selectedEntry?.line.machine_salience;
  elements.machineSalienceReviewSelect.disabled = !(
    selectedSalience?.eligible
    && Number.isInteger(currentRecord?.machine_salience_review?.review_revision)
  );
  const batchEntries = batchLineEntries();
  const activeBatchIds = new Set(batchEntries.map((entry) => entry.line.line_id));
  const selectedBatchCount = [...batchSelectedLineIds]
    .filter((identity) => activeBatchIds.has(identity)).length;
  const hasPendingLines = batchEntries.some((entry) => (
    ["unclassified", "unresolved_red_stroke"].includes(entry.line.review_basis)
  ));
  elements.selectUnclassifiedLinesButton.disabled = immutable || !hasPendingLines;
  elements.selectAllLinesButton.disabled = immutable || batchEntries.length === 0;
  elements.clearLineSelectionButton.disabled = immutable || selectedBatchCount === 0;
  elements.batchReviewBasisSelect.disabled = immutable || selectedBatchCount === 0;
  elements.applyBatchReviewBasisButton.disabled = (
    immutable
    || selectedBatchCount === 0
    || !editableLineReviewBases.has(elements.batchReviewBasisSelect.value)
  );
  elements.batchLineList.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    checkbox.disabled = immutable;
  });
  elements.frameSelect.disabled = !currentRecord || sourcePhysicalFrames().length === 0;
  elements.frameSlotKindSelect.disabled = immutable || !selectedFrameKey;
  document.querySelectorAll("[data-nudge],[data-rotate]").forEach((button) => button.disabled = immutable || !selectedLineId);
}

function geometrySnapshot() {
  return {
    shared_edges: currentRecord.shared_edges.map((line) => ({
      line_id: line.line_id,
      points_display: line.points_display.map((point) => [...point]),
      review_basis: line.review_basis
    })),
    boundary_pool: currentRecord.boundary_pool.map((line) => ({
      line_id: line.line_id,
      points_display: line.points_display.map((point) => [...point]),
      review_basis: line.review_basis
    })),
    slot_kinds: currentRecord.tasks.flatMap((task) => task.slots.map((slot) => ({
      task_id: task.task_id,
      ordinal: slot.ordinal,
      slot_kind: slot.slot_kind
    })))
  };
}

function applySnapshot(snapshot) {
  replaceGeometryFromSnapshot(snapshot);
  markDirty();
  renderGeometry();
  renderBatchClassification();
  renderFrameControls();
  renderAdjacencyRelations();
  renderDiagnostics();
  updateControls();
}

function replaceGeometryFromSnapshot(snapshot) {
  const incoming = new Map([...snapshot.shared_edges, ...snapshot.boundary_pool].map((line) => [line.line_id, line]));
  allLines().forEach((line) => {
    const replacement = incoming.get(line.line_id);
    line.points_display = replacement.points_display.map((point) => [...point]);
    line.review_basis = replacement.review_basis;
  });
  const incomingSlotKinds = new Map(
    snapshot.slot_kinds.map((slot) => [`${slot.task_id}/${slot.ordinal}`, slot.slot_kind])
  );
  currentRecord.tasks.forEach((task) => task.slots.forEach((slot) => {
    slot.slot_kind = incomingSlotKinds.get(`${task.task_id}/${slot.ordinal}`);
  }));
  currentRecord.line_basis_summary = null;
  syncLocalFrameStateSummary();
}

function pushHistory(snapshot = geometrySnapshot()) {
  history.push(snapshot);
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
  currentRecord.evaluation_role_summary = null;
  editGeneration += 1;
  if (!wasDirty) {
    currentRecord.reviewed_task_ids = [];
    renderReferenceSummary();
  }
  setSaveStatus("有未保存修改");
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNow, 450);
  if (loupeMaximized && lastPointer && currentRecord.shared_edges.some((line) => line.line_id === selectedLineId)) {
    scheduleLoupe(lastPointer);
  }
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
    target.line_basis_summary = currentRecord.line_basis_summary;
    target.frame_state_summary = currentRecord.frame_state_summary;
    target.evaluation_role_summary = currentRecord.evaluation_role_summary;
    target.machine_salience_summary = currentRecord.machine_salience_review?.source_summary;
    target.refinement_summary = currentRecord.diagnostics?.refinement
      ? {
          refinement_revision: currentRecord.diagnostics.refinement.refinement_revision,
          moved_line_count: currentRecord.diagnostics.refinement.moved_line_count,
          retained_line_count: currentRecord.diagnostics.refinement.retained_line_count,
          moved_line_ids: currentRecord.diagnostics.refinement.moved_line_ids
        }
      : null;
  }
  currentItem.line_basis_summary = currentRecord.line_basis_summary;
  currentItem.frame_state_summary = currentRecord.frame_state_summary;
  currentItem.evaluation_role_summary = currentRecord.evaluation_role_summary;
  currentItem.machine_salience_summary = currentRecord.machine_salience_review?.source_summary;
  indexData.states = {};
  for (const item of indexData.items) indexData.states[item.state] = (indexData.states[item.state] || 0) + 1;
  indexData.basis_states = {};
  for (const item of indexData.items) {
    const basisStatus = item.line_basis_summary?.status;
    if (basisStatus) indexData.basis_states[basisStatus] = (indexData.basis_states[basisStatus] || 0) + 1;
  }
  indexData.frame_states = {};
  for (const item of indexData.items) {
    const frameStatus = item.frame_state_summary?.status;
    if (frameStatus) indexData.frame_states[frameStatus] = (indexData.frame_states[frameStatus] || 0) + 1;
  }
  indexData.evaluation_roles = {};
  for (const item of indexData.items) {
    const sourceRole = item.evaluation_role_summary?.source_role;
    if (sourceRole) indexData.evaluation_roles[sourceRole] = (indexData.evaluation_roles[sourceRole] || 0) + 1;
  }
  renderIndex();
}

function selectLine(identity) {
  selectedLineId = identity;
  renderGeometry();
  renderDiagnostics();
  updateControls();
}

function changeLineReviewBasis() {
  const line = lineById(selectedLineId);
  if (!line || currentRecord.state === "user_confirmed") return;
  const next = elements.lineReviewBasisSelect.value;
  if (line.review_basis === next) return;
  pushHistory();
  line.review_basis = next;
  currentRecord.line_basis_summary = null;
  markDirty();
  renderGeometry();
  renderBatchClassification();
  renderReferenceSummary();
  renderDiagnostics();
  updateControls();
}

async function changeMachineSalienceReview() {
  const line = lineById(selectedLineId);
  const fact = line?.machine_salience;
  if (!currentRecord || !fact?.eligible) return;
  const next = elements.machineSalienceReviewSelect.value;
  if (fact.review_status === next) return;
  elements.machineSalienceReviewSelect.disabled = true;
  try {
    await flushSave();
    const response = await api(`/api/machine-salience/${encodeURIComponent(currentRecord.source.sha256)}`, {
      method: "POST",
      body: JSON.stringify({
        expected_review_revision: currentRecord.machine_salience_review.review_revision,
        line_id: line.line_id,
        review_status: next
      })
    });
    const result = await response.json();
    currentRecord = result.record;
    indexData = result.index;
    currentItem = indexData.items.find((item) => item.source_sha256 === currentRecord.source.sha256) || currentItem;
    setSaveStatus("机器显著度审阅已保存", "ok");
    renderRecord();
    renderIndex();
  } catch (error) {
    elements.machineSalienceReviewSelect.value = fact.review_status;
    showToast(error.message, true);
    updateControls();
  }
}

function changeFrameSelection() {
  selectedFrameKey = elements.frameSelect.value || null;
  renderFrameControls();
  updateControls();
}

function changeFrameSlotKind() {
  if (!currentRecord || currentRecord.state === "user_confirmed" || !selectedFrameKey) return;
  const frame = sourcePhysicalFrames().find((item) => item.key === selectedFrameKey);
  if (!frame) return;
  const next = elements.frameSlotKindSelect.value;
  if (frame.assignments.every((item) => item.slotKind === next)) return;
  const snapshot = geometrySnapshot();
  const previousLineBasisSummary = currentRecord.line_basis_summary;
  const previousFrameStateSummary = currentRecord.frame_state_summary;
  pushHistory();
  const taskById = new Map(currentRecord.tasks.map((task) => [task.task_id, task]));
  for (const assignment of frame.assignments) {
    taskById.get(assignment.taskId).slots[assignment.ordinal - 1].slot_kind = next;
  }
  const blockingMessage = frameGeometryBlockingMessage();
  if (blockingMessage) {
    replaceGeometryFromSnapshot(snapshot);
    currentRecord.line_basis_summary = previousLineBasisSummary;
    currentRecord.frame_state_summary = previousFrameStateSummary;
    history.pop();
    renderGeometry();
    renderFrameControls();
    renderDiagnostics();
    updateControls();
    showToast(blockingMessage, true);
    return;
  }
  currentRecord.line_basis_summary = null;
  syncLocalFrameStateSummary();
  markDirty();
  renderGeometry();
  renderReferenceSummary();
  renderFrameControls();
  renderAdjacencyRelations();
  renderDiagnostics();
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

function clampEditableLinePoint(point) {
  const extent = currentRecord.source.canonical_extent;
  const margin = Math.max(64, Math.min(extent.width, extent.height));
  return [
    Math.max(-margin, Math.min(extent.width - 1 + margin, point[0])),
    Math.max(-margin, Math.min(extent.height - 1 + margin, point[1]))
  ];
}

function startLineDrag(event, identity) {
  if (currentRecord.state === "user_confirmed") return;
  event.preventDefault(); event.stopPropagation();
  selectLine(identity);
  pushHistory();
  const line = lineById(identity);
  const start = screenToSvg(event);
  const [[x1, y1], [x2, y2]] = line.points_display;
  const length = Math.hypot(x2 - x1, y2 - y1) || 1;
  drag = {mode: "line", identity, start, original: line.points_display.map((point) => [...point]), normal: [-(y2 - y1) / length, (x2 - x1) / length], blockingMessage: null, changed: false};
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
  const delta = [point.x - drag.start.x, point.y - drag.start.y];
  const amount = delta[0] * drag.normal[0] + delta[1] * drag.normal[1];
  const candidate = drag.original.map((original) => clampEditableLinePoint([
    original[0] + amount * drag.normal[0],
    original[1] + amount * drag.normal[1]
  ]));
  const result = applyConstrainedLinePoints(line, candidate);
  drag.blockingMessage = result.message;
  if (!result.accepted) {
    return;
  }
  drag.changed = true;
  markDirty();
  renderGeometry();
  renderAdjacencyRelations();
  renderDiagnostics();
  updateControls();
}

function finishDrag(event) {
  const blockingMessage = drag?.blockingMessage;
  const discardUnusedHistory = Boolean(drag?.mode === "line" && !drag.changed);
  if (drag) {
    try { elements.annotationSvg.releasePointerCapture(event.pointerId); } catch (_) { /* no-op */ }
  }
  drag = null;
  if (discardUnusedHistory && history.length) {
    history.pop();
    updateControls();
  }
  if (blockingMessage) showToast(blockingMessage, true);
}

function startPan(event) {
  if (!currentRecord || event.target.closest(".annotation-line")) return;
  selectedLineId = null;
  renderGeometry();
  drag = {mode: "pan", clientX: event.clientX, clientY: event.clientY, viewBox: {...viewBox}};
  elements.annotationSvg.setPointerCapture(event.pointerId);
}

function nudge(dx, dy, multiplier = 1) {
  const line = lineById(selectedLineId);
  if (!line || currentRecord.state === "user_confirmed") return;
  const snapshot = geometrySnapshot();
  const candidate = line.points_display.map((point) => clampEditableLinePoint([
    point[0] + dx * multiplier,
    point[1] + dy * multiplier
  ]));
  const result = applyConstrainedLinePoints(line, candidate);
  if (!result.accepted) {
    updateControls();
    showToast(result.message, true);
    return;
  }
  pushHistory(snapshot);
  markDirty(); renderGeometry(); renderAdjacencyRelations(); renderDiagnostics(); updateControls();
}

function rotateSelectedLine(direction, multiplier = 1) {
  const line = lineById(selectedLineId);
  if (!line || currentRecord.state === "user_confirmed") return;
  const angle = direction * ROTATION_STEP_DEGREES * multiplier * Math.PI / 180;
  const [first, second] = line.points_display;
  const snapshot = geometrySnapshot();
  const pivot = [(first[0] + second[0]) / 2, (first[1] + second[1]) / 2];
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  const rotated = line.points_display.map((point) => {
    const dx = point[0] - pivot[0];
    const dy = point[1] - pivot[1];
    return [
      pivot[0] + dx * cosine - dy * sine,
      pivot[1] + dx * sine + dy * cosine
    ];
  });
  const result = applyConstrainedLinePoints(line, rotated.map(clampEditableLinePoint));
  if (!result.accepted) {
    updateControls();
    showToast(result.message, true);
    return;
  }
  pushHistory(snapshot);
  markDirty(); renderGeometry(); renderAdjacencyRelations(); renderDiagnostics(); updateControls();
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

function fullHeightStartPoint() {
  const extent = currentRecord.source.canonical_extent;
  const horizontal = currentRecord.strip_axis_display === "horizontal";
  const seed = horizontal
    ? [0, extent.height / 2]
    : [extent.width / 2, 0];
  const fitted = fitReviewGeometry(seed, renderedTileSize());
  return horizontal
    ? [Math.floor(fitted.sourceWidth / 2), fitted.center[1]]
    : [fitted.center[0], Math.floor(fitted.sourceHeight / 2)];
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
  if (next && !fullHeightReviewVisited) {
    lastPointer = fullHeightStartPoint();
    fullHeightReviewVisited = true;
  }
  elements.maximizeLoupeButton.setAttribute("aria-pressed", String(next));
  elements.loupeTitle.textContent = next ? "完整高度审阅" : "1:1 原生像素检查";
  elements.loupeSvg.setAttribute("aria-label", next ? "胶片完整高度审阅图" : "原生像素局部图");
  elements.maximizeLoupeButton.textContent = next ? "退出审阅" : "完整高度审阅";
  elements.maximizeLoupeButton.title = next ? "退出完整高度审阅（F 或 Esc）" : "完整高度审阅（F）";
  elements.loupeHelp.textContent = next
    ? "共享短轴 H 占可用高度约 94%。洋红=start，橙色=end，双色虚线=start/end 接触边；彩色轮廓=各个有内容 reference 的 Frame，空曝光 slot 不画边界。点击线后直接用方向键平移整线或用 [ ] 绕中点旋转；正常 Frame 将被阻止越出 TIFF。点击空白处沿胶片长轴移动。按 F 或 Esc 退出。"
    : "局部图直接来自原 TIFF 像素。用它检查线是否安全贴合物理边缘；按 F 进入完整高度审阅。";
  renderLoupeGeometry();
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
    renderLoupeGeometry();
  } catch (error) {
    if (error.name !== "AbortError") showToast(error.message, true);
  }
}

function selectLoupeLine(event, identity) {
  event.preventDefault();
  event.stopPropagation();
  selectLine(identity);
  elements.loupeSvg.focus({preventScroll: true});
}

function renderLoupeGeometry() {
  elements.loupePolygonLayer.replaceChildren();
  elements.loupeLineLayer.replaceChildren();
  if (!currentRecord) return;
  const view = elements.loupeSvg.viewBox.baseVal;
  const bounds = elements.loupeSvg.getBoundingClientRect();
  const viewScale = Math.max(
    view.width / Math.max(1, bounds.width),
    view.height / Math.max(1, bounds.height)
  );
  if (loupeMaximized) {
    const labelScale = viewScale;
    sourceReferenceFrames().forEach((frame) => {
      const polygon = svgElement("polygon", {
        points: frame.points.map((point) => `${point[0]},${point[1]}`).join(" "),
        class: `loupe-frame-polygon ${frameColorClass(frame.sourceOrdinal)}`,
        "data-frame-ordinal": frame.sourceOrdinal
      });
      const title = svgElement("title");
      title.textContent = `Frame ${frame.sourceOrdinal} · ${frame.assignments.map((item) => `${item.sampleId}#${item.ordinal}`).join(" / ")}${frame.slotKind === "source_truncated" ? " · 源截断：显示 TIFF 内可用交集" : ""}`;
      polygon.appendChild(title);
      elements.loupePolygonLayer.appendChild(polygon);
      const center = frame.points.reduce(
        (total, point) => [total[0] + point[0] / frame.points.length, total[1] + point[1] / frame.points.length],
        [0, 0]
      );
      const label = svgElement("text", {
        x: center[0], y: center[1],
        class: "loupe-frame-label",
        "font-size": Math.max(1, 13 * labelScale),
        "stroke-width": Math.max(0.5, 3 * labelScale)
      });
      label.textContent = `Frame ${frame.sourceOrdinal}`;
      elements.loupePolygonLayer.appendChild(label);
    });
  }
  const entries = activeLineEntries().filter((item) => item.active);
  entries.sort((left, right) => (
    Number(left.line.line_id === selectedLineId) -
    Number(right.line.line_id === selectedLineId)
  ));
  for (const entry of entries) {
    const [first, second] = entry.line.points_display;
    const selected = entry.line.line_id === selectedLineId;
    const hitTarget = svgElement("line", {
      x1: first[0], y1: first[1], x2: second[0], y2: second[1],
      class: "loupe-line-hit-target", "data-line-id": entry.line.line_id
    });
    hitTarget.addEventListener("click", (event) => selectLoupeLine(event, entry.line.line_id));
    elements.loupeLineLayer.appendChild(hitTarget);
    if (selected) {
      elements.loupeLineLayer.appendChild(svgElement("line", {
        x1: first[0], y1: first[1], x2: second[0], y2: second[1],
        class: "loupe-selection-halo"
      }));
    }
    const salienceClass = salienceMarkerClass(
      entry.line.machine_salience,
      "loupe-"
    );
    if (salienceClass) {
      elements.loupeLineLayer.appendChild(svgElement("line", {
        x1: first[0], y1: first[1], x2: second[0], y2: second[1],
        class: salienceClass
      }));
    }
    for (const variant of visibleStrokeVariants(entry, selected)) {
      const classes = ["loupe-annotation-line", entry.family, entry.role];
      if (entry.line.review_basis === "human_width_estimate") classes.push("estimated");
      if (["unclassified", "unresolved_red_stroke"].includes(entry.line.review_basis)) classes.push("unclassified");
      if (selected) classes.push("selected");
      if (variant) classes.push(variant);
      const visibleLine = svgElement("line", {
        x1: first[0], y1: first[1], x2: second[0], y2: second[1],
        class: classes.join(" "), "data-line-id": entry.line.line_id
      });
      visibleLine.addEventListener("click", (event) => selectLoupeLine(event, entry.line.line_id));
      elements.loupeLineLayer.appendChild(visibleLine);
    }
  }
}

async function toggleSourceReview() {
  if (!currentRecord || currentRecord.state === "user_confirmed") return;
  try {
    await flushSave();
    const response = await api(`/api/review/${encodeURIComponent(currentRecord.source.sha256)}`, {
      method: "POST",
      body: JSON.stringify({expected_revision: currentRecord.revision, reviewed: elements.sourceReviewed.checked})
    });
    currentRecord = await response.json();
    setSaveStatus("审核状态已保存", "ok");
    renderRecord(); updateIndexItemState(currentRecord.state);
  } catch (error) {
    elements.sourceReviewed.checked = !elements.sourceReviewed.checked;
    showToast(error.message, true);
  }
}

function openConfirmation() {
  if (!currentRecord) return;
  elements.confirmTitle.textContent = `确认 ${currentRecord.tasks.map((task) => task.sample_id).join(" / ")} 的黄金基线`;
  elements.finalConfirmButton.disabled = false;
  elements.confirmDialog.showModal();
}

async function finalConfirmation(event) {
  event.preventDefault();
  try {
    elements.finalConfirmButton.disabled = true;
    const response = await api(`/api/confirm/${encodeURIComponent(currentRecord.source.sha256)}`, {
      method: "POST", body: JSON.stringify({expected_revision: currentRecord.revision})
    });
    currentRecord = await response.json();
    elements.confirmDialog.close();
    setSaveStatus("黄金基线已冻结", "ok");
    showToast("已写入用户确认的本地黄金基线。", false);
    renderRecord(); updateIndexItemState(currentRecord.state);
    await nextUnfinished();
  } catch (error) {
    elements.finalConfirmButton.disabled = false;
    showToast(error.message, true);
  }
}

async function nextUnfinished() {
  const items = indexData?.items || [];
  if (!items.length) return;
  const position = items.findIndex((item) => item.source_sha256 === currentItem?.source_sha256);
  const state = elements.stateFilter.value;
  const saliencePredicate = (item) => {
    const summary = item.machine_salience_summary || {};
    if (state === "salience_pending") return summary.pending_proposal_line_count > 0;
    if (state === "salience_recall_unreviewed") return summary.pending_recall_line_count > 0;
    if (state === "salience_confirmed_low") return summary.confirmed_low_line_count > 0;
    if (state === "salience_confirmed_not_low") return summary.confirmed_not_low_line_count > 0;
    return false;
  };
  for (let offset = 1; offset <= items.length; offset += 1) {
    const candidate = items[(position + offset) % items.length];
    if (
      candidate.prepared
      && (
        state.startsWith("salience_")
          ? saliencePredicate(candidate)
          : candidate.state !== "user_confirmed"
      )
    ) {
      await openSource(candidate);
      return;
    }
  }
  showToast(
    state.startsWith("salience_")
      ? "当前显著度筛选没有其它 source。"
      : "所有已准备样片都已确认。",
    false
  );
}

elements.searchInput.addEventListener("input", renderIndex);
elements.formatFilter.addEventListener("change", renderIndex);
elements.stateFilter.addEventListener("change", renderIndex);
elements.roleFilter.addEventListener("change", renderIndex);
elements.nextButton.addEventListener("click", nextUnfinished);
elements.sourceReviewed.addEventListener("change", toggleSourceReview);
elements.confirmButton.addEventListener("click", openConfirmation);
elements.finalConfirmButton.addEventListener("click", finalConfirmation);
elements.undoButton.addEventListener("click", undo);
elements.redoButton.addEventListener("click", redo);
elements.resetViewButton.addEventListener("click", resetView);
elements.maximizeLoupeButton.addEventListener("click", () => setLoupeMaximized(!loupeMaximized));
elements.lineReviewBasisSelect.addEventListener("change", changeLineReviewBasis);
elements.machineSalienceReviewSelect.addEventListener("change", changeMachineSalienceReview);
elements.selectUnclassifiedLinesButton.addEventListener("click", () => selectBatchLines(
  (entry) => ["unclassified", "unresolved_red_stroke"].includes(entry.line.review_basis)
));
elements.selectAllLinesButton.addEventListener("click", () => selectBatchLines(() => true));
elements.clearLineSelectionButton.addEventListener("click", () => selectBatchLines(() => false));
elements.batchReviewBasisSelect.addEventListener("change", updateControls);
elements.applyBatchReviewBasisButton.addEventListener("click", applyBatchReviewBasis);
elements.frameSelect.addEventListener("change", changeFrameSelection);
elements.frameSlotKindSelect.addEventListener("change", changeFrameSlotKind);
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
