from __future__ import annotations

from ..common import *
from ..evidence import *
from ..geometry import *
from ..detection.pipeline import *

def preview_gray(gray: np.ndarray, max_side: int = 1800) -> tuple[np.ndarray, float]:
    h, w = gray.shape
    scale = min(1.0, float(max_side) / float(max(h, w)))
    if scale < 1.0:
        step = max(1, int(math.ceil(1.0 / scale)))
        small = gray[::step, ::step]
        actual_scale = float(small.shape[1]) / float(w)
    else:
        small = gray
        actual_scale = 1.0
    rgb = np.repeat(small[..., None], 3, axis=2).astype(np.uint8, copy=False)
    return rgb, actual_scale


def cached_preview_gray(cache: Optional[AnalysisCache], key: str, gray: np.ndarray, max_side: int = 1800) -> tuple[np.ndarray, float]:
    if cache is None:
        return preview_gray(gray, max_side)
    cache_key = (str(key), int(max_side))
    cached = cache.preview_rgb_cache.get(cache_key)
    if cached is None:
        rgb, scale = preview_gray(gray, max_side)
        cache.preview_rgb_cache[cache_key] = (rgb.copy(), float(scale))
        return rgb, scale
    rgb, scale = cached
    return rgb.copy(), float(scale)


def cached_labeled_preview_gray(cache: Optional[AnalysisCache], key: str, label: str, gray: np.ndarray, max_side: int = 1800) -> tuple[np.ndarray, float]:
    if cache is None:
        rgb, scale = preview_gray(gray, max_side)
        return add_panel_label(rgb, label), scale
    cache_key = (str(key), str(label), int(max_side))
    cached = cache.panel_label_cache.get(cache_key)
    if cached is None:
        rgb, scale = cached_preview_gray(cache, key, gray, max_side)
        labeled = add_panel_label(rgb, label)
        cache.panel_label_cache[cache_key] = labeled.copy()
        return labeled, scale
    preview = cache.preview_rgb_cache.get((str(key), int(max_side)))
    scale = float(preview[1]) if preview is not None else 1.0
    return cached.copy(), float(scale)


def draw_preview_rect(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], thickness: int = 2) -> None:
    h, w = rgb.shape[:2]
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    if right <= left or bottom <= top:
        return
    t = max(1, int(thickness))
    rgb[top:min(bottom, top + t), left:right] = color
    rgb[max(top, bottom - t):bottom, left:right] = color
    rgb[top:bottom, left:min(right, left + t)] = color
    rgb[top:bottom, max(left, right - t):right] = color


FRAME_FILL_COLORS = (
    (30, 144, 255),
    (255, 120, 40),
    (80, 200, 120),
    (210, 90, 255),
    (255, 210, 40),
    (40, 210, 220),
    (255, 90, 120),
    (150, 170, 255),
)


def fill_preview_rect(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], alpha: float = 0.24) -> None:
    h, w = rgb.shape[:2]
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    if right <= left or bottom <= top:
        return
    overlay = np.array(color, dtype=np.float32)
    region = rgb[top:bottom, left:right].astype(np.float32, copy=False)
    rgb[top:bottom, left:right] = np.clip(region * (1.0 - alpha) + overlay * alpha, 0, 255).astype(np.uint8)


def draw_preview_line(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], thickness: int = 2) -> None:
    h, w = rgb.shape[:2]
    x = max(0, min(w - 1, int(round(box.left * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    if bottom <= top:
        return
    t = max(1, int(thickness))
    rgb[top:bottom, max(0, x - t // 2):min(w, x + (t + 1) // 2)] = color


def draw_preview_hline(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], thickness: int = 2) -> None:
    h, w = rgb.shape[:2]
    y = max(0, min(h - 1, int(round(box.top * scale))))
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    if right <= left:
        return
    t = max(1, int(thickness))
    rgb[max(0, y - t // 2):min(h, y + (t + 1) // 2), left:right] = color


def draw_preview_mark(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], thickness: int = 2) -> None:
    if box.width > 1 or box.height > 1:
        draw_preview_rect(rgb, box, scale, color, thickness)
    else:
        draw_preview_line(rgb, box, scale, color, thickness)


def gap_mark_box(detection: Detection, gap: Gap) -> Optional[Box]:
    work_outer_raw = gap.lane_box if isinstance(gap.lane_box, dict) else detection.detail.get("work_outer")
    if not isinstance(work_outer_raw, dict):
        return None
    try:
        work_outer = Box(
            int(work_outer_raw["left"]),
            int(work_outer_raw["top"]),
            int(work_outer_raw["right"]),
            int(work_outer_raw["bottom"]),
        )
    except Exception:
        return None
    if gap.method in HARD_GAP_METHODS and gap.start is not None and gap.end is not None:
        start = int(round(work_outer.left + min(gap.start, gap.end)))
        end = int(round(work_outer.left + max(gap.start, gap.end)))
        if end <= start:
            end = start + 1
        if detection.layout == "horizontal":
            return Box(start, work_outer.top, end, work_outer.bottom)
        return Box(work_outer.top, start, work_outer.bottom, end)

    x = int(round(work_outer.left + gap.center))
    if detection.layout == "horizontal":
        return Box(x, work_outer.top, x + 1, work_outer.bottom)
    return Box(work_outer.top, x, work_outer.bottom, x + 1)


def gap_tick_boxes(detection: Detection, gap: Gap) -> list[Box]:
    work_outer_raw = gap.lane_box if isinstance(gap.lane_box, dict) else detection.detail.get("work_outer")
    if not isinstance(work_outer_raw, dict):
        return []
    try:
        work_outer = Box(
            int(work_outer_raw["left"]),
            int(work_outer_raw["top"]),
            int(work_outer_raw["right"]),
            int(work_outer_raw["bottom"]),
        )
    except Exception:
        return []
    tick = max(20, int(round((work_outer.height if detection.layout == "horizontal" else work_outer.width) * 0.12)))
    if detection.layout == "horizontal":
        x = int(round(work_outer.left + gap.center))
        return [
            Box(x, work_outer.top, x + 1, min(work_outer.bottom, work_outer.top + tick)),
            Box(x, max(work_outer.top, work_outer.bottom - tick), x + 1, work_outer.bottom),
        ]
    y = int(round(work_outer.left + gap.center))
    return [
        Box(work_outer.top, y, min(work_outer.bottom, work_outer.top + tick), y + 1),
        Box(max(work_outer.top, work_outer.bottom - tick), y, work_outer.bottom, y + 1),
    ]


def gap_work_outer(detection: Detection, gap: Gap) -> Optional[Box]:
    work_outer_raw = gap.lane_box if isinstance(gap.lane_box, dict) else detection.detail.get("work_outer")
    if not isinstance(work_outer_raw, dict):
        return None
    try:
        return Box(
            int(work_outer_raw["left"]),
            int(work_outer_raw["top"]),
            int(work_outer_raw["right"]),
            int(work_outer_raw["bottom"]),
        )
    except Exception:
        return None


def nearby_separator_candidate_detail(
    gray_work: np.ndarray,
    work_outer: Box,
    gap: Gap,
    pitch: float,
    start: int,
    end: int,
    format_name: str = "135",
    cache: Optional[AnalysisCache] = None,
) -> dict[str, Any]:
    if gap.method not in HARD_GAP_METHODS or pitch <= 0:
        return {"searched": False, "reason": "not_hard_gap"}
    tuning = format_tuning(format_name)
    cache_key: Optional[tuple[Any, ...]] = None
    if cache is not None:
        cache_key = (
            str(format_name),
            box_cache_key(work_outer),
            int(gap.index),
            str(gap.method),
            round(float(gap.center), 4),
            round(float(gap.score), 6),
            None if gap.start is None else round(float(gap.start), 4),
            None if gap.end is None else round(float(gap.end), 4),
            round(float(pitch), 4),
            int(start),
            int(end),
        )
        cached = cache.nearby_separator_details.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)
    crop = gray_work[work_outer.top:work_outer.bottom, work_outer.left:work_outer.right]
    if crop.size == 0:
        return {"searched": False, "reason": "empty_outer"}
    profile = cached_separator_profile(cache, gray_work, work_outer, format_name)
    if profile.size == 0:
        return {"searched": False, "reason": "empty_profile"}

    center = int(round(gap.center))
    current_start = max(0, min(len(profile), int(round(start - work_outer.left))))
    current_end = max(current_start + 1, min(len(profile), int(round(end - work_outer.left))))
    window = clamp_int(pitch * tuning.nearby_window_ratio, tuning.nearby_window_min, tuning.nearby_window_max)
    exclude = max(tuning.nearby_exclude_min, clamp_int(max(float(current_end - current_start), pitch * tuning.nearby_exclude_ratio), tuning.nearby_exclude_min, tuning.nearby_exclude_max))
    lo = max(0, center - window)
    hi = min(len(profile), center + window + 1)
    current_score = interval_mean(profile, current_start, current_end)
    threshold = max(0.22, float(np.percentile(profile[lo:hi], 82)) if hi > lo else 0.22)
    candidates: list[dict[str, Any]] = []
    for run_start, run_end in runs_from_mask(profile[lo:hi] >= threshold):
        abs_start = lo + run_start
        abs_end = lo + run_end
        if abs_end <= abs_start:
            continue
        if abs_start < current_end + exclude and abs_end > current_start - exclude:
            continue
        width = abs_end - abs_start
        if width > clamp_int(pitch * tuning.nearby_max_width_ratio, tuning.nearby_max_width_min, tuning.nearby_max_width_max):
            continue
        score = interval_mean(profile, abs_start, abs_end)
        candidate_center = (abs_start + abs_end - 1) / 2.0
        candidates.append(
            {
                "center": float(candidate_center),
                "absolute_center": float(work_outer.left + candidate_center),
                "start": int(abs_start),
                "end": int(abs_end),
                "width_px": int(width),
                "score": float(score),
                "distance_px": float(candidate_center - gap.center),
            }
        )
    candidates.sort(key=lambda item: (float(item["score"]), -abs(float(item["distance_px"]))), reverse=True)
    best = candidates[0] if candidates else None
    stronger = bool(best and float(best["score"]) >= max(current_score + tuning.nearby_detail_score_add, current_score * tuning.nearby_detail_score_multiplier))
    detail = {
        "searched": True,
        "window_px": int(window),
        "current_profile_score": float(current_score),
        "candidate_count": len(candidates),
        "stronger_found": stronger,
        "best": best,
    }
    if cache_key is not None and cache is not None:
        cache.nearby_separator_details[cache_key] = copy.deepcopy(detail)
    return detail


def gap_diagnostic_record(gray_work: np.ndarray, detection: Detection, gap: Gap, cache: Optional[AnalysisCache] = None) -> dict[str, Any]:
    tuning = format_tuning(detection.film_format)
    work_outer = gap_work_outer(detection, gap)
    pitch = float(detection.detail.get("pitch", 0.0) or 0.0)
    origin = float(detection.detail.get("origin", 0.0) or 0.0)
    expected = origin + pitch * float(gap.index) if pitch > 0 else float(gap.center)
    role = "separator_evidence" if gap.method in HARD_GAP_METHODS else "geometry_model"
    record: dict[str, Any] = {
        "index": int(gap.index),
        "method": gap.method,
        "role": role,
        "used_for_decision": True,
        "diagnostic_only": True,
        "center": float(gap.center),
        "expected_center": float(expected),
        "model_delta_px": float(gap.center - expected),
        "score": float(gap.score),
        "width_px": float(gap.width),
        "hard_trust": "not_hard_gap",
        "overlap_like": False,
        "overlap_risk": "none",
        "signals": {},
    }
    if work_outer is None or not work_outer.valid() or pitch <= 0:
        record["signals"] = {"available": False}
        return record

    work_outer = work_outer.clamp(gray_work.shape[1], gray_work.shape[0])
    if not work_outer.valid():
        record["signals"] = {"available": False}
        return record

    if gap.start is not None and gap.end is not None:
        start = int(round(work_outer.left + min(gap.start, gap.end)))
        end = int(round(work_outer.left + max(gap.start, gap.end)))
    else:
        half = clamp_int(pitch * tuning.nearby_exclude_ratio, 2, 80)
        center = int(round(work_outer.left + gap.center))
        start, end = center - half, center + half + 1
    start = max(work_outer.left, min(work_outer.right, start))
    end = max(start + 1, min(work_outer.right, end))
    guard = clamp_int(max(float(end - start), pitch * tuning.hard_trust_guard_ratio), tuning.hard_trust_guard_min, tuning.hard_trust_guard_max)
    left_start = max(work_outer.left, start - guard)
    right_end = min(work_outer.right, end + guard)
    core = gray_work[work_outer.top:work_outer.bottom, start:end]
    left = gray_work[work_outer.top:work_outer.bottom, left_start:start]
    right = gray_work[work_outer.top:work_outer.bottom, end:right_end]
    if core.size == 0:
        record["signals"] = {"available": False}
        return record

    core_mean = float(core.mean())
    core_content = float((core < tuning.hard_trust_core_content_threshold).mean())
    core_dark = float((core < tuning.hard_trust_core_dark_threshold).mean())
    core_activity = float(core.std() / 255.0)
    left_content = float((left < tuning.hard_trust_core_content_threshold).mean()) if left.size else 0.0
    right_content = float((right < tuning.hard_trust_core_content_threshold).mean()) if right.size else 0.0
    side_content = min(left_content, right_content)
    side_balance = abs(left_content - right_content)
    continuity = min(core_content, side_content)
    nearby = nearby_separator_candidate_detail(gray_work, work_outer, gap, pitch, start, end, detection.film_format, cache)
    record["signals"] = {
        "available": True,
        "core_mean": core_mean,
        "core_content": core_content,
        "core_dark": core_dark,
        "core_activity": core_activity,
        "left_content": left_content,
        "right_content": right_content,
        "side_content": side_content,
        "side_balance": side_balance,
        "continuity": continuity,
        "window": {"start": int(start), "end": int(end), "guard": int(guard)},
    }
    record["nearby_separator_candidate"] = nearby

    narrow_hard = gap.method in HARD_GAP_METHODS and 0.0 < gap.width <= clamp_float(pitch * tuning.hard_trust_narrow_ratio, tuning.hard_trust_narrow_min, tuning.hard_trust_narrow_max)
    width_ratio = float(gap.width) / max(1.0, float(pitch))
    model_delta_ratio = abs(float(gap.center - expected)) / max(1.0, float(pitch))
    content_continuous = continuity >= tuning.hard_trust_continuity_min and core_activity >= tuning.hard_trust_activity_min
    dark_separator_like = core_mean <= tuning.hard_trust_dark_mean_max and core_dark >= tuning.hard_trust_dark_fraction_min and core_activity <= tuning.hard_trust_dark_activity_max
    weak_dark_gap = core_mean >= tuning.hard_trust_weak_mean_min and core_content >= tuning.hard_trust_weak_content_min
    if gap.method in HARD_GAP_METHODS:
        if bool(nearby.get("stronger_found", False)):
            record["hard_trust"] = "nearby_separator_conflict"
        elif model_delta_ratio >= tuning.hard_trust_model_delta_ratio and (width_ratio < tuning.hard_trust_geometry_width_ratio or gap.score < tuning.hard_trust_model_conflict_score):
            record["hard_trust"] = "geometry_conflict"
        elif width_ratio < tuning.hard_trust_frame_border_width_ratio and dark_separator_like:
            record["hard_trust"] = "suspect_frame_border"
        elif narrow_hard and (content_continuous or weak_dark_gap):
            record["hard_trust"] = "suspect_internal_edge"
        elif narrow_hard:
            record["hard_trust"] = "narrow_but_ok"
        elif dark_separator_like or core_content <= tuning.hard_trust_strong_core_content_max or gap.score >= tuning.hard_trust_strong_min_score:
            record["hard_trust"] = "strong_separator"
        else:
            record["hard_trust"] = "weak_or_ambiguous_separator"
    elif gap.method in MODEL_GAP_METHODS:
        if dark_separator_like:
            overlap_risk = "none"
        elif continuity >= tuning.diagnostic_overlap_strong_continuity and core_activity >= tuning.diagnostic_overlap_strong_activity and core_mean >= tuning.diagnostic_overlap_mean_min:
            overlap_risk = "strong"
        elif continuity >= tuning.diagnostic_overlap_medium_continuity and core_activity >= tuning.diagnostic_overlap_medium_activity and core_mean >= tuning.diagnostic_overlap_mean_min:
            overlap_risk = "medium"
        elif continuity >= tuning.diagnostic_overlap_weak_continuity and core_activity >= tuning.diagnostic_overlap_weak_activity and core_mean >= tuning.diagnostic_overlap_mean_min:
            overlap_risk = "weak"
        else:
            overlap_risk = "none"
        record["overlap_risk"] = overlap_risk
        record["overlap_like"] = overlap_risk in {"medium", "strong"}
    return record


def attach_read_only_diagnostics(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> None:
    gray_work = cache.gray_work if cache is not None and cache.layout == detection.layout else work_gray(gray, detection.layout)
    gap_records = [gap_diagnostic_record(gray_work, detection, gap, cache) for gap in detection.gaps]
    hard_counts: dict[str, int] = {}
    for record in gap_records:
        trust = str(record.get("hard_trust", "not_hard_gap"))
        hard_counts[trust] = hard_counts.get(trust, 0) + 1
    overlap_count = sum(1 for record in gap_records if bool(record.get("overlap_like", False)))
    overlap_risk_counts: dict[str, int] = {}
    for record in gap_records:
        risk = str(record.get("overlap_risk", "none"))
        overlap_risk_counts[risk] = overlap_risk_counts.get(risk, 0) + 1
    strong_hard = int(hard_counts.get("strong_separator", 0))
    suspicious_hard = sum(
        int(hard_counts.get(name, 0))
        for name in ("suspect_internal_edge", "suspect_frame_border", "nearby_separator_conflict", "geometry_conflict")
    )
    strong_overlap_models = int(overlap_risk_counts.get("strong", 0))
    single_anchor_pass_risk = (
        format_tuning(detection.film_format).lucky_pass_risk_enabled
        and detection.strip_mode == "full"
        and (
            (strong_hard <= 1 and (suspicious_hard >= 1 or strong_overlap_models >= 1))
            or (strong_hard <= 2 and suspicious_hard >= 1 and strong_overlap_models >= 1)
        )
    )
    method_roles = {
        "detected": "separator_evidence",
        "edge-pair": "separator_evidence",
        "enhanced-detected": "separator_evidence_enhanced",
        "grid": "geometry_model",
        "equal": "geometry_model",
        "content": "content_model",
    }
    detection.detail["diagnostics"] = {
        "version": VERSION,
        "diagnostic_only": True,
        "changes_output": False,
        "changes_confidence": False,
        "changes_pass_review": False,
        "purpose": "observe hard-gap trust, model-gap overlap risk, and evidence/model roles without changing crop output",
        "method_roles": method_roles,
        "gap_diagnostics": gap_records,
        "summary": {
            "gap_count": len(gap_records),
            "hard_trust_counts": hard_counts,
            "overlap_like_model_gaps": int(overlap_count),
            "overlap_risk_counts": overlap_risk_counts,
            "suspect_hard_gaps": int(hard_counts.get("suspect_internal_edge", 0)),
            "suspicious_hard_gaps": int(suspicious_hard),
            "strong_hard_gaps": int(strong_hard),
            "single_anchor_pass_risk": bool(single_anchor_pass_risk),
        },
    }


def overlap_bleed_risk_detail(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> dict[str, Any]:
    if not detection.gaps:
        return {"used": False, "risk": False, "reason": "no_gaps"}
    gray_work = cache.gray_work if cache is not None and cache.layout == detection.layout else work_gray(gray, detection.layout)
    gap_records = [gap_diagnostic_record(gray_work, detection, gap, cache) for gap in detection.gaps]
    overlap_risk_counts: dict[str, int] = {}
    for record in gap_records:
        risk = str(record.get("overlap_risk", "none"))
        overlap_risk_counts[risk] = overlap_risk_counts.get(risk, 0) + 1
    risk = int(overlap_risk_counts.get("strong", 0)) > 0 or int(overlap_risk_counts.get("medium", 0)) > 0
    return {
        "used": True,
        "risk": bool(risk),
        "reason": "diagnostic_overlap_risk" if risk else "no_medium_or_strong_overlap_risk",
        "overlap_risk_counts": overlap_risk_counts,
        "gap_diagnostics": gap_records,
        "gap_count": len(gap_records),
    }


def lucky_pass_risk_score_detail(
    gray: np.ndarray,
    detection: Detection,
    threshold: float,
    cache: Optional[AnalysisCache] = None,
) -> dict[str, Any]:
    tuning = format_tuning(detection.film_format)
    fmt = FORMATS.get(detection.film_format, FORMATS["135"])
    if (
        not tuning.lucky_pass_risk_enabled
        or detection.strip_mode != "full"
        or detection.count != fmt.default_count
        or detection.confidence < threshold
    ):
        return {"used": False, "reason": "not_applicable"}
    analysis_cache = cache if cache is not None and cache.layout == detection.layout else make_analysis_cache(gray, detection.layout)
    gray_work = analysis_cache.gray_work
    gap_records = [gap_diagnostic_record(gray_work, detection, gap, analysis_cache) for gap in detection.gaps]
    hard_counts: dict[str, int] = {}
    overlap_risk_counts: dict[str, int] = {}
    for record in gap_records:
        trust = str(record.get("hard_trust", "not_hard_gap"))
        hard_counts[trust] = hard_counts.get(trust, 0) + 1
        risk = str(record.get("overlap_risk", "none"))
        overlap_risk_counts[risk] = overlap_risk_counts.get(risk, 0) + 1
    strong_hard = int(hard_counts.get("strong_separator", 0))
    suspicious_hard = sum(
        int(hard_counts.get(name, 0))
        for name in ("suspect_internal_edge", "suspect_frame_border", "nearby_separator_conflict", "geometry_conflict")
    )
    strong_overlap_models = int(overlap_risk_counts.get("strong", 0))
    grid_or_equal = sum(1 for gap in detection.gaps if gap.method in {"grid", "equal"})
    width_cv = float(detection.detail.get("width_cv", 0.0) or 0.0)
    components: dict[str, float] = {}
    if grid_or_equal >= tuning.lucky_model_gap_support_min:
        components["model_gap_support"] = tuning.lucky_model_gap_support_weight
    elif grid_or_equal == 1:
        components["minor_model_gap_support"] = tuning.lucky_minor_model_gap_support_weight
    if strong_hard <= tuning.lucky_limited_strong_hard_max:
        components["limited_strong_hard_evidence"] = tuning.lucky_limited_strong_hard_weight
    if strong_hard <= tuning.lucky_very_limited_strong_hard_max:
        components["very_limited_strong_hard_evidence"] = tuning.lucky_very_limited_strong_hard_weight
    if suspicious_hard >= 1:
        components["suspicious_hard_gap"] = tuning.lucky_suspicious_hard_weight
    if strong_overlap_models >= 1:
        components["strong_overlap_model_gap"] = tuning.lucky_strong_overlap_weight
    if grid_or_equal >= tuning.lucky_model_gap_support_min and suspicious_hard >= 1 and strong_overlap_models >= 1:
        components["model_suspicion_overlap_combo"] = tuning.lucky_combo_weight
    if width_cv >= tuning.lucky_unstable_width_cv:
        components["unstable_widths"] = tuning.lucky_unstable_width_weight
    elif width_cv >= tuning.lucky_mild_width_cv:
        components["mild_width_instability"] = tuning.lucky_mild_width_weight
    if strong_hard >= tuning.lucky_strong_hard_credit_min:
        components["strong_hard_evidence_credit"] = tuning.lucky_strong_hard_credit
    if width_cv < tuning.lucky_stable_width_cv and grid_or_equal >= tuning.lucky_stable_model_gap_min:
        components["stable_global_geometry_credit"] = tuning.lucky_stable_geometry_credit
    risk_score = max(0.0, min(1.0, sum(components.values())))
    risk_threshold = tuning.lucky_risk_threshold
    risk = risk_score >= risk_threshold
    return {
        "used": True,
        "risk": bool(risk),
        "reason": "lucky_pass_risk" if risk else "ok",
        "risk_score": float(risk_score),
        "risk_threshold": float(risk_threshold),
        "components": components,
        "hard_trust_counts": hard_counts,
        "overlap_risk_counts": overlap_risk_counts,
        "strong_hard_gaps": int(strong_hard),
        "suspicious_hard_gaps": int(suspicious_hard),
        "strong_overlap_model_gaps": int(strong_overlap_models),
        "model_gap_count": int(grid_or_equal),
        "width_cv": float(width_cv),
    }


def debug_status_parts(detection: Detection, threshold: float) -> tuple[str, str, tuple[int, int, int]]:
    passed = detection.confidence >= threshold
    status = "PASS" if passed else "REVIEW"
    op = ">=" if passed else "<"
    detail = f"confidence {detection.confidence:.3f} {op} threshold {threshold:.3f}"
    if detection.review_reasons:
        detail += " | " + ",".join(detection.review_reasons[:3])
    color = (40, 180, 90) if passed else (230, 80, 70)
    return status, detail, color


def draw_large_status(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, color: tuple[int, int, int]) -> tuple[int, int]:
    x, y = xy
    offsets = ((0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2))
    for dx, dy in offsets:
        draw.text((x + dx, y + dy), text, fill=color)
    try:
        bbox = draw.textbbox((x, y), text)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
    except Exception:
        width = len(text) * 8
        height = 12
    return width + 3, height + 3


def add_status_bar(rgb: np.ndarray, detection: Detection, threshold: float) -> np.ndarray:
    status, detail, color = debug_status_parts(detection, threshold)
    detail = f"{SCRIPT_NAME} {VERSION} | {detail}"
    bar_h = 48
    h, w = rgb.shape[:2]
    panel = np.full((h + bar_h, w, 3), 18, dtype=np.uint8)
    panel[bar_h:, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, w - 1, bar_h - 1), outline=color, width=2)
    status_w, _ = draw_large_status(draw, (12, 10), status, color)
    draw.text((12 + status_w + 14, 17), detail, fill=(245, 245, 245))
    return np.asarray(image)


def write_debug_preview(gray: np.ndarray, detection: Detection, output_path: Path, threshold: float, cache: Optional[AnalysisCache] = None) -> None:
    rgb = add_status_bar(make_debug_preview_rgb(gray, detection, cache), detection, threshold)
    write_rgb_jpeg(rgb, output_path)


def make_debug_preview_rgb(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    rgb, scale = cached_preview_gray(cache, "original_gray", gray)
    for index, box in enumerate(detection.frames):
        color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
        fill_preview_rect(rgb, box, scale, color, 0.26)
        draw_preview_rect(rgb, box, scale, color, 1)
    draw_preview_rect(rgb, detection.outer, scale, (0, 255, 0), 3)
    return rgb


def draw_gap_overlay(rgb: np.ndarray, detection: Detection, scale: float) -> None:
    tuning = format_tuning(detection.film_format)
    gap_colors = {
        "detected": (255, 0, 0),
        "edge-pair": (255, 0, 0),
        "wide-separator": (255, 70, 70),
        "enhanced-detected": (255, 140, 0),
        "grid": (255, 220, 30),
        "equal": (190, 80, 255),
    }
    pitch = float(detection.detail.get("pitch", 0.0) or 0.0)
    detected_centers = [gap.center for gap in detection.gaps if gap.method in HARD_GAP_METHODS]
    overlap_tolerance = clamp_float(
        pitch * tuning.debug_gap_overlap_tolerance_ratio,
        tuning.debug_gap_overlap_tolerance_min,
        tuning.debug_gap_overlap_tolerance_max,
    )
    for gap in detection.gaps:
        if gap.method not in HARD_GAP_METHODS:
            continue
        mark = gap_mark_box(detection, gap)
        if mark is not None:
            draw_preview_mark(rgb, mark, scale, gap_colors.get(gap.method, (255, 255, 255)), tuning.debug_gap_hard_line_width)
    for gap in detection.gaps:
        if gap.method in HARD_GAP_METHODS:
            continue
        if any(abs(gap.center - center) <= overlap_tolerance for center in detected_centers):
            continue
        color = gap_colors.get(gap.method, (255, 255, 255))
        for tick in gap_tick_boxes(detection, gap):
            if detection.layout == "horizontal":
                draw_preview_line(rgb, tick, scale, color, tuning.debug_gap_model_line_width)
            else:
                draw_preview_hline(rgb, tick, scale, color, tuning.debug_gap_model_line_width)
    draw_gap_diagnostic_overlay(rgb, detection, scale)


def draw_gap_diagnostic_overlay(rgb: np.ndarray, detection: Detection, scale: float) -> None:
    tuning = format_tuning(detection.film_format)
    diagnostics = detection.detail.get("diagnostics")
    records: Any = None
    if isinstance(diagnostics, dict):
        records = diagnostics.get("gap_diagnostics", [])
    if not isinstance(records, list):
        overlap_bleed = detection.detail.get("overlap_bleed_risk")
        if isinstance(overlap_bleed, dict):
            records = overlap_bleed.get("gap_diagnostics", [])
    if not isinstance(records, list):
        return
    gaps_by_index = {gap.index: gap for gap in detection.gaps}
    for record in records:
        if not isinstance(record, dict):
            continue
        gap = gaps_by_index.get(int(record.get("index", -1)))
        if gap is None:
            continue
        color: Optional[tuple[int, int, int]] = None
        if record.get("hard_trust") in {
            "suspect_internal_edge",
            "suspect_frame_border",
            "nearby_separator_conflict",
            "geometry_conflict",
        }:
            color = (255, 0, 220)
        elif str(record.get("overlap_risk", "none")) in {"medium", "strong"}:
            color = (0, 220, 255)
        if color is None:
            continue
        for tick in gap_tick_boxes(detection, gap):
            if detection.layout == "horizontal":
                draw_preview_line(rgb, tick, scale, color, tuning.debug_gap_diagnostic_line_width)
            else:
                draw_preview_hline(rgb, tick, scale, color, tuning.debug_gap_diagnostic_line_width)


def work_evidence_to_original_shape(evidence_work: np.ndarray, gray: np.ndarray, layout: str) -> np.ndarray:
    patch = evidence_work if layout == "horizontal" else evidence_work.T
    if patch.shape == gray.shape:
        return patch.astype(np.uint8, copy=False)
    out = np.full(gray.shape, 235, dtype=np.uint8)
    ph = min(out.shape[0], patch.shape[0])
    pw = min(out.shape[1], patch.shape[1])
    if ph > 0 and pw > 0:
        out[:ph, :pw] = patch[:ph, :pw]
    return out


def draw_evidence_context_overlay(rgb: np.ndarray, detection: Detection, scale: float, include_frames: bool = False) -> None:
    draw_preview_rect(rgb, detection.outer, scale, (0, 255, 0), 2)
    if include_frames:
        for index, box in enumerate(detection.frames):
            color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
            draw_preview_rect(rgb, box, scale, color, 1)


def make_separator_evidence_debug_gray(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    if cache is not None and cache.layout == detection.layout:
        full_work = Box(0, 0, cache.gray_work.shape[1], cache.gray_work.shape[0])
        evidence = cached_separator_evidence_crop(cache, cache.gray_work, full_work)
        if evidence.size:
            return work_evidence_to_original_shape(evidence, gray, detection.layout)
    return make_separator_evidence_gray(gray)


def make_separator_evidence_debug_rgb(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    evidence = make_separator_evidence_debug_gray(gray, detection, cache)
    rgb, scale = cached_preview_gray(cache, "separator_evidence_full", evidence)
    draw_evidence_context_overlay(rgb, detection, scale)
    draw_gap_overlay(rgb, detection, scale)
    return rgb


def make_content_evidence_debug_gray(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    if cache is not None and cache.layout == detection.layout:
        return work_evidence_to_original_shape(cache.content_evidence_work, gray, detection.layout)
    return make_content_evidence_gray(gray)


def make_content_evidence_debug_rgb(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    evidence = make_content_evidence_debug_gray(gray, detection, cache)
    rgb, scale = cached_preview_gray(cache, "content_evidence_full", evidence)
    draw_evidence_context_overlay(rgb, detection, scale, include_frames=True)
    return rgb


def write_rgb_jpeg(rgb: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(np.ascontiguousarray(rgb), mode="RGB")
    image.save(output_path, format="JPEG", quality=92, optimize=True)


def add_panel_label(rgb: np.ndarray, label: str) -> np.ndarray:
    label_h = 34
    h, w = rgb.shape[:2]
    panel = np.full((h + label_h, w, 3), 18, dtype=np.uint8)
    panel[label_h:, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.text((12, 9), label, fill=(245, 245, 245))
    return np.asarray(image)


def make_debug_analysis_panel(gray: np.ndarray, detection: Detection, threshold: float, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    base_rgb, _ = cached_labeled_preview_gray(cache, "original_gray", "Original gray", gray)
    debug_rgb = add_panel_label(make_debug_preview_rgb(gray, detection, cache), "Debug boxes")
    evidence_rgb = make_separator_evidence_debug_rgb(gray, detection, cache)
    evidence_rgb = add_panel_label(evidence_rgb, "Separator evidence (magenta=suspect hard diag, cyan=overlap diag)")
    content_rgb = make_content_evidence_debug_rgb(gray, detection, cache)
    content_rgb = add_panel_label(content_rgb, "Content evidence")
    panels = [base_rgb, debug_rgb, evidence_rgb, content_rgb]
    gap = 12
    if gray.shape[1] >= gray.shape[0]:
        max_w = max(panel.shape[1] for panel in panels)
        total_h = sum(panel.shape[0] for panel in panels) + gap * (len(panels) - 1)
        canvas = np.full((total_h, max_w, 3), 32, dtype=np.uint8)
        y = 0
        for panel in panels:
            h, w = panel.shape[:2]
            canvas[y:y + h, :w] = panel
            y += h + gap
    else:
        max_h = max(panel.shape[0] for panel in panels)
        total_w = sum(panel.shape[1] for panel in panels) + gap * (len(panels) - 1)
        canvas = np.full((max_h, total_w, 3), 32, dtype=np.uint8)
        x = 0
        for panel in panels:
            h, w = panel.shape[:2]
            canvas[:h, x:x + w] = panel
            x += w + gap
    return add_status_bar(canvas, detection, threshold)


def write_debug_analysis(
    gray: np.ndarray,
    detection: Detection,
    output_dir: Path,
    stem: str,
    threshold: float,
    cache: Optional[AnalysisCache] = None,
) -> list[str]:
    analysis_dir = output_dir / "_debug_analysis"
    panel_path = analysis_dir / f"{stem}_debug_analysis.jpg"
    write_rgb_jpeg(make_debug_analysis_panel(gray, detection, threshold, cache), panel_path)
    return [str(panel_path)]


LOSSLESS_COMPRESSIONS = {"NONE", "LZW", "ADOBE_DEFLATE", "DEFLATE", "ZSTD"}
