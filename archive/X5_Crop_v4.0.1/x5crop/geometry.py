from __future__ import annotations

from .common import *
from .evidence import *

def infer_layout(width: int, height: int) -> str:
    return "horizontal" if width >= height else "vertical"


def work_gray(gray: np.ndarray, layout: str) -> np.ndarray:
    return gray if layout == "horizontal" else np.ascontiguousarray(gray.T)


def make_analysis_cache(gray: np.ndarray, layout: str) -> AnalysisCache:
    gray_work = work_gray(gray, layout)
    content_evidence = make_content_evidence_gray(gray_work)
    return AnalysisCache(
        layout=layout,
        gray_work=gray_work,
        content_evidence_work=content_evidence,
        content_evidence_float_work=content_evidence.astype(np.float32) / 255.0,
    )


def box_cache_key(box: Box) -> tuple[int, int, int, int]:
    return (int(box.left), int(box.top), int(box.right), int(box.bottom))


def format_box_cache_key(format_name: str, box: Box) -> tuple[str, int, int, int, int]:
    return (str(format_name), int(box.left), int(box.top), int(box.right), int(box.bottom))


def crop_work_outer(gray_work: np.ndarray, outer: Box) -> np.ndarray:
    if not outer.valid():
        return gray_work
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    return crop if crop.size else gray_work


def cached_separator_profile(cache: Optional[AnalysisCache], gray_work: np.ndarray, outer: Box, format_name: str = "135") -> np.ndarray:
    if cache is None:
        return separator_profile(crop_work_outer(gray_work, outer), format_name)
    key = format_box_cache_key(format_name, outer)
    profile = cache.separator_profiles.get(key)
    if profile is None:
        profile = separator_profile(crop_work_outer(cache.gray_work, outer), format_name)
        cache.separator_profiles[key] = profile
    return profile


def cached_enhanced_separator_profile(cache: Optional[AnalysisCache], gray_work: np.ndarray, outer: Box, format_name: str = "135") -> np.ndarray:
    if cache is None:
        crop = crop_work_outer(gray_work, outer)
        return separator_profile(make_separator_evidence_gray(crop), format_name)
    key = format_box_cache_key(format_name, outer)
    profile = cache.enhanced_separator_profiles.get(key)
    if profile is None:
        crop = crop_work_outer(cache.gray_work, outer)
        profile = separator_profile(make_separator_evidence_gray(crop), format_name)
        cache.enhanced_separator_profiles[key] = profile
    return profile


def cached_separator_evidence_crop(cache: Optional[AnalysisCache], gray_work: np.ndarray, outer: Box) -> np.ndarray:
    if cache is None:
        return make_separator_evidence_gray(crop_work_outer(gray_work, outer))
    key = box_cache_key(outer)
    evidence = cache.separator_evidence_crops.get(key)
    if evidence is None:
        evidence = make_separator_evidence_gray(crop_work_outer(cache.gray_work, outer))
        cache.separator_evidence_crops[key] = evidence
    return evidence


def cached_edge_refine_profiles(
    cache: Optional[AnalysisCache],
    crop: np.ndarray,
    outer: Box,
    format_name: str = "135",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if cache is None:
        return edge_refine_profiles(crop, format_name)
    key = format_box_cache_key(format_name, outer)
    profiles = cache.edge_refine_profiles.get(key)
    if profiles is None:
        profiles = edge_refine_profiles(crop_work_outer(cache.gray_work, outer), format_name)
        cache.edge_refine_profiles[key] = profiles
    return profiles


def map_work_box(box: Box, layout: str, width: int, height: int) -> Box:
    if layout == "horizontal":
        return box.clamp(width, height)
    return Box(box.top, box.left, box.bottom, box.right).clamp(width, height)


def original_box_to_work(box: Box, layout: str, width: int, height: int) -> Box:
    if layout == "horizontal":
        return box.clamp(width, height)
    return Box(box.top, box.left, box.bottom, box.right).clamp(height, width)


def apply_edge_bleed_protection(detection: Detection, config: Config, image_w: int, image_h: int) -> None:
    if detection.strip_mode != "full" or detection.count <= 1 or len(detection.frames) != detection.count:
        return
    outer_work = original_box_to_work(detection.outer, detection.layout, image_w, image_h)
    frames_work = [original_box_to_work(frame, detection.layout, image_w, image_h) for frame in detection.frames]
    if not outer_work.valid() or any(not frame.valid() for frame in frames_work):
        return

    work_w = image_w if detection.layout == "horizontal" else image_h
    nominal = float(outer_work.width) / float(max(1, detection.count))
    edge_guard = max(70.0, min(120.0, nominal * 0.0150))
    changed: list[str] = []

    first_target = max(0, outer_work.left - int(config.bleed_x))
    if frames_work[0].left > first_target + edge_guard:
        frames_work[0] = Box(first_target, frames_work[0].top, frames_work[0].right, frames_work[0].bottom)
        changed.append("first")

    last_target = min(work_w, outer_work.right + int(config.bleed_x))
    if frames_work[-1].right < last_target - edge_guard:
        frames_work[-1] = Box(frames_work[-1].left, frames_work[-1].top, last_target, frames_work[-1].bottom)
        changed.append("last")

    if not changed or any(not frame.valid() for frame in frames_work):
        return

    detection.frames = [map_work_box(frame, detection.layout, image_w, image_h) for frame in frames_work]
    detection.detail["edge_bleed_protection"] = {
        "used": True,
        "pinned": changed,
        "edge_guard": edge_guard,
        "long_axis_bleed": int(config.bleed_x),
        "edge_guard_basis": "nominal_frame_width_ratio",
    }


def detection_geometry_config(config: Config) -> Config:
    return replace(
        config,
        bleed_x=0,
        bleed_y=0,
    )


def detection_has_overlap_bleed_risk(detection: Detection) -> bool:
    lucky = detection.detail.get("lucky_pass_risk_score")
    if isinstance(lucky, dict):
        if bool(lucky.get("risk", False)):
            return True
        counts = lucky.get("overlap_risk_counts")
        if isinstance(counts, dict):
            if int(counts.get("strong", 0) or 0) > 0 or int(counts.get("medium", 0) or 0) > 0:
                return True

    diagnostics = detection.detail.get("diagnostics_v3_6")
    if isinstance(diagnostics, dict):
        summary = diagnostics.get("summary")
        if isinstance(summary, dict):
            if int(summary.get("overlap_like_model_gaps", 0) or 0) > 0:
                return True
            counts = summary.get("overlap_risk_counts")
            if isinstance(counts, dict):
                if int(counts.get("strong", 0) or 0) > 0 or int(counts.get("medium", 0) or 0) > 0:
                    return True
    return False


def output_bleed_config_for_detection(config: Config, detection: Detection) -> Config:
    if not detection_has_overlap_bleed_risk(detection):
        return config
    target_bleed_x = max(int(config.bleed_x), 50)
    if target_bleed_x == int(config.bleed_x):
        return config
    return replace(config, bleed_x=target_bleed_x)


def apply_output_bleed(detection: Detection, detection_config: Config, output_config: Config, image_w: int, image_h: int) -> None:
    if int(detection_config.bleed_x) == int(output_config.bleed_x) and int(detection_config.bleed_y) == int(output_config.bleed_y):
        return
    frames_work = [original_box_to_work(frame, detection.layout, image_w, image_h) for frame in detection.frames]
    work_w = image_w if detection.layout == "horizontal" else image_h
    work_h = image_h if detection.layout == "horizontal" else image_w
    adjusted_work: list[Box] = []
    for frame in frames_work:
        raw = Box(
            frame.left + int(detection_config.bleed_x),
            frame.top + int(detection_config.bleed_y),
            frame.right - int(detection_config.bleed_x),
            frame.bottom - int(detection_config.bleed_y),
        )
        if not raw.valid():
            return
        adjusted_work.append(raw.expand(int(output_config.bleed_x), int(output_config.bleed_y), work_w, work_h))
    detection.frames = [map_work_box(frame, detection.layout, image_w, image_h) for frame in adjusted_work]
    detection.detail["output_bleed"] = {
        "used": True,
        "detection_long_axis_bleed": int(detection_config.bleed_x),
        "detection_short_axis_bleed": int(detection_config.bleed_y),
        "output_long_axis_bleed": int(output_config.bleed_x),
        "output_short_axis_bleed": int(output_config.bleed_y),
        "overlap_risk_long_axis_bleed": bool(detection_has_overlap_bleed_risk(detection)),
    }


def reapply_cached_output_bleed(detection: Detection, config: Config, image_w: int, image_h: int) -> None:
    output_bleed = detection.detail.get("output_bleed")
    if not isinstance(output_bleed, dict):
        return
    try:
        cached_x = int(output_bleed.get("output_long_axis_bleed", config.bleed_x))
        cached_y = int(output_bleed.get("output_short_axis_bleed", config.bleed_y))
    except (TypeError, ValueError):
        return
    if cached_x == int(config.bleed_x) and cached_y == int(config.bleed_y):
        return
    cached_config = replace(config, bleed_x=cached_x, bleed_y=cached_y)
    apply_output_bleed(detection, cached_config, config, image_w, image_h)
    detection.detail["reused_output_bleed_adjustment"] = {
        "from_long_axis_bleed": int(cached_x),
        "from_short_axis_bleed": int(cached_y),
        "to_long_axis_bleed": int(config.bleed_x),
        "to_short_axis_bleed": int(config.bleed_y),
    }


def apply_approved_geometry_polish(detection: Detection, gray: np.ndarray, config: Config, status: str) -> None:
    if status != "approved_auto" or detection.strip_mode != "full" or len(detection.frames) != detection.count:
        return
    if detection.review_reasons:
        return
    gray_work = work_gray(gray, detection.layout)
    h, w = gray_work.shape
    outer = original_box_to_work(detection.outer, detection.layout, gray.shape[1], gray.shape[0])
    frames = [original_box_to_work(frame, detection.layout, gray.shape[1], gray.shape[0]) for frame in detection.frames]
    if not outer.valid() or any(not frame.valid() for frame in frames):
        return

    original_outer = outer
    changes: dict[str, Any] = {}
    tuning = format_tuning(detection.film_format)

    long_limit = clamp_int((outer.width / float(max(1, detection.count))) * tuning.approved_polish_long_limit_ratio, tuning.approved_polish_long_limit_min, tuning.approved_polish_long_limit_max)
    band_top = outer.top + int(round(outer.height * 0.12))
    band_bottom = outer.bottom - int(round(outer.height * 0.12))
    if band_bottom <= band_top:
        band_top, band_bottom = outer.top, outer.bottom

    def side_extension(side: str) -> int:
        if side == "left":
            lo, hi = max(0, outer.left - long_limit), outer.left
        else:
            lo, hi = outer.right, min(w, outer.right + long_limit)
        if hi <= lo:
            return 0
        strip = gray_work[band_top:band_bottom, lo:hi]
        if strip.size == 0:
            return 0
        col_content = (strip < 242).mean(axis=0)
        if side == "left":
            active = np.where(col_content > 0.018)[0]
            return int(hi - (lo + int(active[0]))) if active.size else 0
        active = np.where(col_content > 0.018)[0]
        return int(int(active[-1]) + 1) if active.size else 0

    pitch = float(outer.width) / float(max(1, detection.count))
    min_long_ext = clamp_int(pitch * tuning.approved_polish_min_ext_ratio, tuning.approved_polish_min_ext_min, tuning.approved_polish_min_ext_max)
    left_ext = side_extension("left")
    right_ext = side_extension("right")
    left_ext = left_ext if left_ext >= min_long_ext else 0
    right_ext = right_ext if right_ext >= min_long_ext else 0
    if 0 < left_ext <= long_limit:
        outer = Box(max(0, outer.left - left_ext), outer.top, outer.right, outer.bottom)
        frames[0] = Box(outer.left, frames[0].top, frames[0].right, frames[0].bottom)
    if 0 < right_ext <= long_limit:
        outer = Box(outer.left, outer.top, min(w, outer.right + right_ext), outer.bottom)
        frames[-1] = Box(frames[-1].left, frames[-1].top, outer.right, frames[-1].bottom)
    if left_ext or right_ext:
        changes["long_axis_expand"] = {
            "left": int(left_ext),
            "right": int(right_ext),
            "limit": int(long_limit),
            "minimum": int(min_long_ext),
        }

    if not changes or not outer.valid() or any(not frame.valid() for frame in frames):
        return
    detection.detail["geometry_polish"] = {
        "used": True,
        "original_outer": asdict(original_outer),
        "polished_outer": asdict(outer),
        **changes,
    }
    detection.outer = map_work_box(outer, detection.layout, gray.shape[1], gray.shape[0])
    detection.frames = [map_work_box(frame, detection.layout, gray.shape[1], gray.shape[0]) for frame in frames]


def smooth_1d(values: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window))
    if window <= 1:
        return values.astype(np.float32, copy=False)
    kernel = np.ones(window, dtype=np.float32) / float(window)
    return np.convolve(values.astype(np.float32), kernel, mode="same")


def runs_from_mask(mask: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: Optional[int] = None
    for i, flag in enumerate(mask.astype(bool)):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def bbox_from_mask(mask: np.ndarray, min_row_fraction: float = 0.01, min_col_fraction: float = 0.01) -> Optional[Box]:
    if mask.size == 0:
        return None
    row_has = mask.mean(axis=1) >= min_row_fraction
    col_has = mask.mean(axis=0) >= min_col_fraction
    rows = np.flatnonzero(row_has)
    cols = np.flatnonzero(col_has)
    if rows.size == 0 or cols.size == 0:
        return None
    return Box(int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)


def first_content_index(border_mask: np.ndarray, min_run: int) -> int:
    if border_mask.size == 0:
        return 0
    content = ~border_mask.astype(bool)
    runs = runs_from_mask(content)
    for start, end in runs:
        if end - start >= min_run:
            return int(start)
    candidates = np.flatnonzero(content)
    return int(candidates[0]) if candidates.size else 0


def detect_outer(gray: np.ndarray, format_name: str = "135") -> Box:
    tuning = format_tuning(format_name)
    h, w = gray.shape
    not_white = gray < tuning.outer_bw_not_white_threshold
    dark = gray < tuning.outer_bw_dark_threshold
    mask = not_white | dark
    box = bbox_from_mask(mask, min_row_fraction=tuning.outer_bw_min_fraction, min_col_fraction=tuning.outer_bw_min_fraction)
    if (
        box is None
        or box.width < max(tuning.outer_min_width_px, w * tuning.outer_bw_min_width_ratio)
        or box.height < max(tuning.outer_min_height_px, h * tuning.outer_bw_min_height_ratio)
    ):
        return Box(0, 0, w, h)

    margin_x = max(tuning.outer_bw_margin_min, int(round(w * tuning.outer_bw_margin_ratio)))
    margin_y = max(tuning.outer_bw_margin_min, int(round(h * tuning.outer_bw_margin_ratio)))
    return box.expand(margin_x, margin_y, w, h)


def detect_outer_white_x(gray: np.ndarray, format_name: str = "135") -> Box:
    tuning = format_tuning(format_name)
    h, w = gray.shape
    min_run_y = clamp_int(h * tuning.outer_white_run_ratio, tuning.outer_white_run_min, tuning.outer_white_run_max)
    min_run_x = clamp_int(w * tuning.outer_white_run_ratio, tuning.outer_white_run_min, tuning.outer_white_run_max)
    y_background = (gray <= tuning.outer_white_dark_threshold) | (gray >= tuning.outer_white_light_threshold)
    x_background = gray >= tuning.outer_white_light_threshold
    row_border = y_background.mean(axis=1) >= tuning.outer_white_border_ratio
    col_border = x_background.mean(axis=0) >= tuning.outer_white_border_ratio
    top = first_content_index(row_border, min_run_y)
    bottom = h - first_content_index(row_border[::-1], min_run_y)
    left = first_content_index(col_border, min_run_x)
    right = w - first_content_index(col_border[::-1], min_run_x)
    margin_x = max(tuning.outer_white_margin_min, int(round(w * tuning.outer_white_margin_ratio)))
    margin_y = max(tuning.outer_white_margin_min, int(round(h * tuning.outer_white_margin_ratio)))
    box = Box(left, top, right, bottom).expand(margin_x, margin_y, w, h)
    if (
        not box.valid()
        or box.width < max(tuning.outer_min_width_px, w * tuning.outer_white_min_width_ratio)
        or box.height < max(tuning.outer_min_height_px, h * tuning.outer_white_min_height_ratio)
    ):
        return Box(0, 0, w, h)
    return box


def unique_outer_candidates(candidates: Iterable[OuterCandidate]) -> list[OuterCandidate]:
    seen: set[tuple[int, int, int, int]] = set()
    out: list[OuterCandidate] = []
    for candidate in candidates:
        box = candidate.box
        key = (box.left, box.top, box.right, box.bottom)
        if key in seen or not box.valid():
            continue
        seen.add(key)
        out.append(candidate)
    return out


def detect_outer_candidates(gray: np.ndarray, format_name: str = "135") -> list[OuterCandidate]:
    tuning = format_tuning(format_name)
    h, w = gray.shape
    bw = detect_outer(gray, format_name)
    white_x = detect_outer_white_x(gray, format_name)
    candidates = [OuterCandidate("bw", bw)]
    if white_x.valid():
        max_reasonable = max(float(bw.width) * tuning.outer_white_x_width_multiplier, float(bw.width) + w * tuning.outer_white_x_extra_ratio)
        if white_x.width >= bw.width and white_x.width <= max_reasonable:
            candidates.append(OuterCandidate("white_x", white_x))
    for profile in tuning.outer_mask_profiles:
        mask = np.ones_like(gray, dtype=bool)
        if profile.low is not None:
            mask &= gray > int(profile.low)
        if profile.high is not None:
            mask &= gray < int(profile.high)
        box = bbox_from_mask(mask, min_row_fraction=profile.min_row_fraction, min_col_fraction=profile.min_col_fraction)
        if box is None:
            continue
        if box.width < max(tuning.outer_min_width_px, w * tuning.outer_min_width_ratio) or box.height < max(tuning.outer_min_height_px, h * tuning.outer_min_height_ratio):
            continue
        candidates.append(OuterCandidate(profile.name, box.expand(max(tuning.outer_bw_margin_min, int(w * tuning.outer_mask_expand_ratio)), max(tuning.outer_bw_margin_min, int(h * tuning.outer_mask_expand_ratio)), w, h)))
    unique = unique_outer_candidates(candidates)
    canvas_area = float(w * h)
    non_full = [
        candidate for candidate in unique
        if (candidate.box.width * candidate.box.height) / max(1.0, canvas_area) <= tuning.outer_candidate_max_area
    ]
    if non_full:
        return non_full
    return unique or [OuterCandidate("full_canvas", Box(0, 0, w, h))]


def separator_profile(crop: np.ndarray, format_name: str = "135") -> np.ndarray:
    tuning = format_tuning(format_name)
    h, w = crop.shape
    if h <= 0 or w <= 0:
        return np.zeros(0, dtype=np.float32)
    y0 = max(0, min(h - 1, int(round(h * tuning.separator_profile_top_ratio))))
    y1 = max(y0 + 1, min(h, int(round(h * tuning.separator_profile_bottom_ratio))))
    middle = crop[y0:y1, :]
    middle_f = middle.astype(np.float32, copy=False)

    profiles: list[np.ndarray] = []
    segments = max(1, int(tuning.separator_profile_segments))
    for i in range(segments):
        sy0 = int(round(i * middle.shape[0] / segments))
        sy1 = int(round((i + 1) * middle.shape[0] / segments))
        if sy1 <= sy0:
            continue
        part = middle[sy0:sy1, :]
        black = (part <= tuning.separator_profile_dark_threshold).mean(axis=0).astype(np.float32)
        white = (part >= tuning.separator_profile_light_threshold).mean(axis=0).astype(np.float32)
        profiles.append(np.maximum(black, white))
    if not profiles:
        profiles.append(((middle <= tuning.separator_profile_dark_threshold) | (middle >= tuning.separator_profile_light_threshold)).mean(axis=0).astype(np.float32))

    stack = np.stack(profiles, axis=0)
    average_extreme = stack.mean(axis=0).astype(np.float32)
    vertical_consistency = np.percentile(stack, tuning.separator_profile_consistency_percentile, axis=0).astype(np.float32)
    extreme_score = tuning.separator_profile_average_weight * average_extreme + tuning.separator_profile_consistency_weight * vertical_consistency

    col_std = middle_f.std(axis=0)
    uniform_score = 1.0 - np.clip(col_std / tuning.separator_profile_std_norm, 0.0, 1.0)
    col_mean = middle_f.mean(axis=0)
    dark_soft = np.clip((tuning.separator_profile_dark_soft_mean - col_mean) / tuning.separator_profile_dark_soft_mean, 0.0, 1.0)
    light_soft = np.clip((col_mean - tuning.separator_profile_light_soft_mean) / tuning.separator_profile_light_soft_span, 0.0, 1.0)
    soft_score = np.maximum(dark_soft, light_soft) * uniform_score * tuning.separator_profile_soft_weight

    gradient = np.abs(np.diff(middle_f, axis=1, prepend=middle_f[:, :1])).mean(axis=0) / 255.0
    score = np.maximum(extreme_score * (tuning.separator_profile_uniform_base + tuning.separator_profile_uniform_weight * uniform_score), soft_score)
    score = np.maximum(score, np.clip(gradient, 0.0, 1.0) * tuning.separator_profile_gradient_weight)
    return smooth_1d(score.astype(np.float32), max(tuning.separator_profile_smooth_min, int(round(w * tuning.separator_profile_smooth_ratio))))


def normalize_profile(profile: np.ndarray, high_percentile: float = 99.0) -> np.ndarray:
    profile = profile.astype(np.float32, copy=False)
    if profile.size == 0:
        return profile
    hi = float(np.percentile(profile, high_percentile))
    if hi <= 1e-6:
        return np.zeros_like(profile, dtype=np.float32)
    return np.clip(profile / hi, 0.0, 1.0).astype(np.float32)


def edge_refine_profiles(crop: np.ndarray, format_name: str = "135") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    tuning = format_tuning(format_name)
    h, w = crop.shape
    if h <= 0 or w <= 1:
        zeros = np.zeros(w, dtype=np.float32)
        return zeros, zeros, zeros
    y0 = max(0, min(h - 1, int(round(h * tuning.edge_refine_top_ratio))))
    y1 = max(y0 + 1, min(h, int(round(h * tuning.edge_refine_bottom_ratio))))
    middle = crop[y0:y1, :]
    if middle.size == 0:
        zeros = np.zeros(w, dtype=np.float32)
        return zeros, zeros, zeros
    middle_i16 = middle.astype(np.int16, copy=False)
    diff_x = np.abs(np.diff(middle_i16, axis=1)).astype(np.float32)
    edge = np.zeros(w, dtype=np.float32)
    if diff_x.shape[1] > 0:
        raw = tuning.edge_refine_mean_weight * diff_x.mean(axis=0) + tuning.edge_refine_p75_weight * np.percentile(diff_x, 75, axis=0)
        edge[1:] = raw
        edge = normalize_profile(smooth_1d(edge, max(tuning.edge_refine_smooth_min, int(round(w * tuning.edge_refine_smooth_ratio)))), tuning.edge_refine_high_percentile)
    background = ((middle <= tuning.edge_refine_background_dark_threshold) | (middle >= tuning.edge_refine_background_light_threshold)).mean(axis=0).astype(np.float32)
    col_std = middle.astype(np.float32, copy=False).std(axis=0)
    if middle.shape[0] > 1:
        diff_y = np.abs(np.diff(middle_i16, axis=0)).astype(np.float32)
        y_edge = diff_y.mean(axis=0)
    else:
        y_edge = np.zeros(w, dtype=np.float32)
    activity = normalize_profile(col_std + tuning.edge_refine_y_edge_weight * y_edge, tuning.edge_refine_activity_percentile)
    return edge, background, activity


def local_edge_peaks(profile: np.ndarray, lo: int, hi: int, min_strength: float) -> list[int]:
    width = len(profile)
    lo = max(0, min(int(lo), width))
    hi = max(lo, min(int(hi), width))
    if hi <= lo:
        return []
    local = profile[lo:hi]
    if local.size == 0:
        return []
    threshold = max(float(min_strength), float(np.percentile(local, 84)))
    peaks: list[int] = []
    for start, end in runs_from_mask(local >= threshold):
        if end <= start:
            continue
        peak = lo + start + int(np.argmax(local[start:end]))
        if float(profile[peak]) >= min_strength:
            peaks.append(int(peak))
    deduped: list[int] = []
    for peak in sorted(peaks):
        if not deduped or peak - deduped[-1] > 2:
            deduped.append(peak)
        elif profile[peak] > profile[deduped[-1]]:
            deduped[-1] = peak
    return deduped


def interval_mean(profile: np.ndarray, start: int, end: int) -> float:
    start = max(0, min(int(start), len(profile)))
    end = max(start, min(int(end), len(profile)))
    if end <= start:
        return 0.0
    return float(profile[start:end].mean())


def edge_pair_params_for_format(format_name: str) -> EdgePairParams:
    if format_name in {"135", "135-dual"}:
        return EdgePairParams(0.080, 0.004, 0.050, 0.42, 0.62, 0.0, 0.0, 1.0, 0.0)
    if format_name == "half":
        return EdgePairParams(0.090, 0.003, 0.060, 0.46, 0.66, 1.05, 0.70, 0.95, 0.040)
    if format_name == "xpan":
        return EdgePairParams(0.060, 0.002, 0.035, 0.45, 0.64, 1.03, 0.70, 0.95, 0.035)
    if format_name == "120-645":
        return EdgePairParams(0.075, 0.001, 0.055, 0.32, 0.20, 0.58, 0.50, 0.95, 0.035)
    if format_name in {"120-66", "120-67"}:
        return EdgePairParams(0.100, 0.001, 0.080, 0.24, 0.02, 0.28, 0.30, 0.95, 0.030)
    return EdgePairParams(0.070, 0.003, 0.040, 0.45, 0.64, 1.05, 0.70, 0.95, 0.040)


def edge_pair_can_replace_hard_gap(gap: Gap, edge_gap: Gap, pitch: float, params: EdgePairParams) -> bool:
    delta = abs(edge_gap.center - gap.center)
    if params.max_hard_shift_ratio <= 0.0:
        return delta <= max(clamp_float(pitch * 0.001, 4.0, 20.0), edge_gap.width)
    shift_limit = max(edge_gap.width * 2.0, clamp_float(pitch * params.max_hard_shift_ratio, 15.0, 220.0))
    if delta > shift_limit:
        return False
    min_quality = max(params.min_quality_for_hard_gap, gap.score * params.hard_gap_quality_ratio)
    if edge_gap.score >= min_quality:
        return True
    return delta <= max(4.0, edge_gap.width * 1.5)


def refine_gaps_by_edge_pairs(
    crop: np.ndarray,
    gaps: list[Gap],
    count: int,
    format_name: str,
    cache: Optional[AnalysisCache] = None,
    outer: Optional[Box] = None,
) -> tuple[list[Gap], dict[str, Any]]:
    h, w = crop.shape
    if count <= 1 or w <= 1 or not gaps:
        return gaps, {"used": False, "reason": "empty"}
    edge, background, _activity = cached_edge_refine_profiles(cache, crop, outer, format_name) if outer is not None else edge_refine_profiles(crop, format_name)
    pitch = w / float(max(1, count))
    params = edge_pair_params_for_format(format_name)
    window = clamp_int(pitch * params.window_ratio, 8, 520)
    min_gutter = clamp_int(pitch * params.min_gutter_ratio, 2, 40)
    max_gutter = max(min_gutter + 1, clamp_int(pitch * params.max_gutter_ratio, 8, 420))
    refined: list[Gap] = []
    accepted: list[dict[str, Any]] = []
    rejected = 0
    for gap in gaps:
        x0 = int(round(gap.center))
        lo = max(1, x0 - window)
        hi = min(w - 1, x0 + window)
        peaks = local_edge_peaks(edge, lo, hi, params.min_strength)
        candidates: list[tuple[float, float, float, int, int]] = []
        for i, a in enumerate(peaks):
            for b in peaks[i + 1:]:
                gutter_w = b - a
                if gutter_w < min_gutter or gutter_w > max_gutter:
                    continue
                center = (a + b) / 2.0
                if abs(center - x0) > window:
                    continue
                bg_between = interval_mean(background, a, b + 1)
                if bg_between < params.min_background:
                    continue
                strength = (float(edge[a]) + float(edge[b])) / 2.0
                quality = strength + 0.6 * bg_between
                distance = abs(center - x0) / max(1.0, pitch)
                candidates.append((distance, -quality, -bg_between, int(a), int(b)))
        if not candidates:
            refined.append(gap)
            rejected += 1
            continue
        _distance, neg_quality, _neg_bg, a, b = sorted(candidates)[0]
        center = (a + b) / 2.0
        edge_gap = Gap(gap.index, float(center), float(-neg_quality), "edge-pair", float(a), float(b + 1))
        if gap.method not in HARD_GAP_METHODS and edge_gap.score < params.min_quality_for_model_gap:
            refined.append(gap)
            rejected += 1
            continue
        if gap.method in {"detected", "enhanced-detected", "wide-separator"} and not edge_pair_can_replace_hard_gap(gap, edge_gap, pitch, params):
            refined.append(gap)
            rejected += 1
            continue
        refined.append(edge_gap)
        accepted.append(
            {
                "index": int(gap.index),
                "center": float(edge_gap.center),
                "width": float(edge_gap.width),
                "score": float(edge_gap.score),
                "replaced_method": gap.method,
            }
        )
    return refined, {
        "used": True,
        "format": format_name,
        "params": asdict(params),
        "accepted": accepted,
        "accepted_count": len(accepted),
        "rejected_count": rejected,
    }


def find_gap(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    format_name: str = "135",
    max_width_ratio_override: Optional[float] = None,
) -> Gap:
    tuning = format_tuning(format_name)
    radius = clamp_int(pitch * tuning.gap_radius_ratio, tuning.gap_radius_min, tuning.gap_radius_max)
    lo = max(1, int(round(expected)) - radius)
    hi = min(len(profile) - 1, int(round(expected)) + radius + 1)
    if hi <= lo:
        return Gap(index, float(expected), 0.0, "equal")
    local = profile[lo:hi]
    local_max = float(local.max()) if local.size else 0.0
    min_score = tuning.gap_min_score
    if local.size == 0 or local_max < min_score:
        return Gap(index, float(expected), local_max, "equal")

    normal_max_gap_w = clamp_int(pitch * tuning.gap_max_width_ratio, tuning.gap_max_width_min, tuning.gap_max_width_max)
    max_width_ratio = tuning.gap_max_width_ratio if max_width_ratio_override is None else max_width_ratio_override
    max_gap_w = clamp_int(pitch * max_width_ratio, tuning.gap_max_width_min, tuning.gap_max_width_max)
    min_gap_w = clamp_int(pitch * tuning.gap_min_width_ratio, tuning.gap_min_width_min, tuning.gap_min_width_max)
    guard_w = clamp_int(pitch * tuning.gap_guard_ratio, tuning.gap_guard_min, tuning.gap_guard_max)
    peak_threshold = max(min_score, local_max * tuning.gap_peak_multiplier)
    band_threshold = max(min_score * 0.86, local_max * tuning.gap_band_multiplier)
    candidates: list[tuple[float, float, float, float, float, float, str]] = []

    for run_start, run_end in runs_from_mask(local >= peak_threshold):
        band_start, band_end = run_start, run_end
        while band_start > 0 and local[band_start - 1] >= band_threshold and (band_end - (band_start - 1)) <= max_gap_w:
            band_start -= 1
        while band_end < len(local) and local[band_end] >= band_threshold and ((band_end + 1) - band_start) <= max_gap_w:
            band_end += 1
        band_width = band_end - band_start
        if band_width < min_gap_w or band_width > max_gap_w:
            continue

        left_guard = local[max(0, band_start - guard_w):band_start]
        right_guard = local[band_end:min(len(local), band_end + guard_w)]
        if left_guard.size == 0 or right_guard.size == 0:
            continue
        mean_score = float(local[band_start:band_end].mean())
        side_score = max(float(left_guard.mean()), float(right_guard.mean()))
        prominence = mean_score - side_score
        if prominence < 0.08 and mean_score < 0.95:
            continue
        method = "detected"
        if max_width_ratio_override is not None and band_width > normal_max_gap_w:
            if mean_score < tuning.wide_gap_min_mean or prominence < tuning.wide_gap_min_prominence:
                continue
            method = "wide-separator"

        center = float(lo + (band_start + band_end - 1) / 2.0)
        start = float(lo + band_start)
        end = float(lo + band_end)
        distance = abs(center - expected) / max(1.0, pitch)
        quality = mean_score + 0.8 * prominence
        candidates.append((distance, -quality, -mean_score, center, start, end, method))

    if candidates:
        _, neg_quality, _, center, start, end, method = sorted(candidates)[0]
        return Gap(index, center, float(-neg_quality), method, start, end)

    return Gap(index, float(expected), local_max, "equal")


def constrain_gap_to_geometry(gap: Gap, expected: float, pitch: float, strip_mode: str, format_name: str = "135") -> Gap:
    if gap.method not in HARD_GAP_METHODS:
        return Gap(gap.index, float(expected), gap.score, "equal")
    tuning = format_tuning(format_name)
    max_shift = clamp_float(
        pitch * (tuning.constrain_full_shift_ratio if strip_mode == "full" else tuning.constrain_partial_shift_ratio),
        tuning.constrain_shift_min,
        tuning.constrain_shift_max,
    )
    shift = max(-max_shift, min(max_shift, gap.center - expected))
    center = float(expected + shift)
    method = gap.method
    if gap.start is not None and gap.end is not None:
        delta = center - float(gap.center)
        start = float(gap.start + delta)
        end = float(gap.end + delta)
    else:
        start = None
        end = None
    return Gap(gap.index, center, gap.score, method, start, end)


def light_hard_gap_trust(
    gap: Gap,
    pitch: float,
    *,
    predicted: Optional[float] = None,
    profile: Optional[np.ndarray] = None,
    gray_work: Optional[np.ndarray] = None,
    outer: Optional[Box] = None,
    format_name: str = "135",
) -> tuple[str, dict[str, Any]]:
    if gap.method not in HARD_GAP_METHODS or pitch <= 0:
        return "not_hard_gap", {"reason": "not_hard_gap"}
    tuning = format_tuning(format_name)
    width_ratio = float(gap.width) / max(1.0, float(pitch))
    detail: dict[str, Any] = {
        "width_ratio": float(width_ratio),
        "score": float(gap.score),
    }
    if profile is not None:
        nearby = nearby_separator_replacement(profile, gap, pitch, format_name)
        if nearby is not None:
            detail["nearby_separator_candidate"] = nearby
            return "nearby_separator_conflict", detail
    if predicted is not None:
        model_delta_ratio = abs(float(gap.center) - float(predicted)) / max(1.0, float(pitch))
        detail["model_delta_ratio"] = float(model_delta_ratio)
        if model_delta_ratio >= tuning.hard_trust_model_delta_ratio and (width_ratio < tuning.hard_trust_geometry_width_ratio or gap.score < tuning.hard_trust_model_conflict_score):
            return "geometry_conflict", detail
    if gray_work is not None and outer is not None and gap.start is not None and gap.end is not None:
        start = int(round(outer.left + min(gap.start, gap.end)))
        end = int(round(outer.left + max(gap.start, gap.end)))
        start = max(outer.left, min(outer.right, start))
        end = max(start + 1, min(outer.right, end))
        guard = clamp_int(max(float(end - start), pitch * tuning.hard_trust_guard_ratio), tuning.hard_trust_guard_min, tuning.hard_trust_guard_max)
        left_start = max(outer.left, start - guard)
        right_end = min(outer.right, end + guard)
        core = gray_work[outer.top:outer.bottom, start:end]
        left = gray_work[outer.top:outer.bottom, left_start:start]
        right = gray_work[outer.top:outer.bottom, end:right_end]
        if core.size:
            core_mean = float(core.mean())
            core_content = float((core < tuning.hard_trust_core_content_threshold).mean())
            core_dark = float((core < tuning.hard_trust_core_dark_threshold).mean())
            core_activity = float(core.std() / 255.0)
            left_content = float((left < tuning.hard_trust_core_content_threshold).mean()) if left.size else 0.0
            right_content = float((right < tuning.hard_trust_core_content_threshold).mean()) if right.size else 0.0
            continuity = min(core_content, min(left_content, right_content))
            dark_separator_like = core_mean <= tuning.hard_trust_dark_mean_max and core_dark >= tuning.hard_trust_dark_fraction_min and core_activity <= tuning.hard_trust_dark_activity_max
            weak_dark_gap = core_mean >= tuning.hard_trust_weak_mean_min and core_content >= tuning.hard_trust_weak_content_min
            narrow_hard = 0.0 < gap.width <= clamp_float(pitch * tuning.hard_trust_narrow_ratio, tuning.hard_trust_narrow_min, tuning.hard_trust_narrow_max)
            detail["signals"] = {
                "core_mean": core_mean,
                "core_content": core_content,
                "core_dark": core_dark,
                "core_activity": core_activity,
                "continuity": continuity,
            }
            if width_ratio < tuning.hard_trust_frame_border_width_ratio and dark_separator_like:
                return "suspect_frame_border", detail
            if narrow_hard and ((continuity >= tuning.hard_trust_continuity_min and core_activity >= tuning.hard_trust_activity_min) or weak_dark_gap):
                return "suspect_internal_edge", detail
    if gap.score >= tuning.hard_trust_strong_min_score and tuning.hard_trust_strong_width_min <= width_ratio <= tuning.hard_trust_strong_width_max:
        return "strong_separator", detail
    if gap.score >= tuning.hard_trust_narrow_ok_score and tuning.hard_trust_narrow_ok_width_min <= width_ratio < tuning.hard_trust_narrow_ok_width_max:
        return "narrow_but_ok", detail
    return "weak_or_ambiguous_separator", detail


def gap_width_cv(gaps: list[Gap], origin: float, pitch: float, count: int) -> float:
    if count <= 1:
        return 0.0
    cuts = [float(origin)] + [float(gap.center) for gap in gaps] + [float(origin + pitch * count)]
    widths = np.diff(np.array(cuts, dtype=np.float64))
    if widths.size != count or np.any(widths <= 1):
        return 1.0
    return float(widths.std() / max(1.0, widths.mean()))


def local_gap_geometry_error(gaps: list[Gap], gap_index: int, origin: float, pitch: float, count: int) -> float:
    if count <= 1 or gap_index < 1 or gap_index >= count:
        return 0.0
    cuts = [float(origin)] + [float(gap.center) for gap in gaps] + [float(origin + pitch * count)]
    left_w = cuts[gap_index] - cuts[gap_index - 1]
    right_w = cuts[gap_index + 1] - cuts[gap_index]
    if left_w <= 1 or right_w <= 1:
        return float("inf")
    return abs(left_w - pitch) + abs(right_w - pitch)


def nearby_separator_replacement(
    profile: np.ndarray,
    gap: Gap,
    pitch: float,
    format_name: str = "135",
) -> Optional[dict[str, Any]]:
    if gap.method not in HARD_GAP_METHODS or pitch <= 0 or gap.start is None or gap.end is None:
        return None
    tuning = format_tuning(format_name)
    center = int(round(gap.center))
    current_start = max(0, min(len(profile), int(round(min(gap.start, gap.end)))))
    current_end = max(current_start + 1, min(len(profile), int(round(max(gap.start, gap.end)))))
    window = clamp_int(pitch * tuning.nearby_window_ratio, tuning.nearby_window_min, tuning.nearby_window_max)
    exclude = max(tuning.nearby_exclude_min, clamp_int(max(float(current_end - current_start), pitch * tuning.nearby_exclude_ratio), tuning.nearby_exclude_min, tuning.nearby_exclude_max))
    lo = max(0, center - window)
    hi = min(len(profile), center + window + 1)
    if hi <= lo:
        return None
    current_score = interval_mean(profile, current_start, current_end)
    threshold = max(0.22, float(np.percentile(profile[lo:hi], 82)))
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
        distance = candidate_center - gap.center
        if abs(distance) > clamp_float(pitch * tuning.nearby_distance_ratio, float(tuning.nearby_window_min), float(tuning.nearby_window_max)):
            continue
        candidates.append(
            {
                "center": float(candidate_center),
                "start": int(abs_start),
                "end": int(abs_end),
                "width_px": int(width),
                "score": float(score),
                "distance_px": float(distance),
            }
        )
    candidates.sort(key=lambda item: (float(item["score"]), -abs(float(item["distance_px"]))), reverse=True)
    best = candidates[0] if candidates else None
    if not best:
        return None
    stronger = float(best["score"]) >= max(current_score + tuning.nearby_score_add, current_score * tuning.nearby_score_multiplier)
    if not stronger:
        return None
    return {
        "searched": True,
        "window_px": int(window),
        "current_profile_score": float(current_score),
        "candidate_count": len(candidates),
        "stronger_found": True,
        "best": best,
    }


def apply_nearby_separator_corrections(
    profile: np.ndarray,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    count: int,
    strip_mode: str,
    fmt_name: str,
) -> tuple[list[Gap], dict[str, Any]]:
    if fmt_name != "135" or strip_mode != "full" or count <= 1 or len(gaps) != count - 1:
        return gaps, {"used": False, "reason": "not_applicable"}
    if profile.size == 0:
        return gaps, {"used": False, "reason": "empty_profile"}
    tuning = format_tuning(fmt_name)
    original_cv = gap_width_cv(gaps, origin, pitch, count)
    corrected = list(gaps)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for pos, gap in enumerate(list(corrected)):
        replacement = nearby_separator_replacement(profile, gap, pitch, fmt_name)
        if replacement is None:
            continue
        best = replacement["best"]
        proposed_gap = Gap(
            gap.index,
            float(best["center"]),
            float(best["score"]),
            gap.method,
            float(best["start"]),
            float(best["end"]),
            gap.lane_box,
        )
        proposed = list(corrected)
        proposed[pos] = proposed_gap
        if any(b.center <= a.center for a, b in zip(proposed[:-1], proposed[1:])):
            rejected.append({"index": int(gap.index), "reason": "non_monotonic", "candidate": best})
            continue
        before_local = local_gap_geometry_error(corrected, gap.index, origin, pitch, count)
        after_local = local_gap_geometry_error(proposed, gap.index, origin, pitch, count)
        before_cv = gap_width_cv(corrected, origin, pitch, count)
        after_cv = gap_width_cv(proposed, origin, pitch, count)
        local_gain = before_local - after_local
        cv_gain = before_cv - after_cv
        local_ok = local_gain >= clamp_float(pitch * tuning.nearby_local_gain_ratio, tuning.nearby_local_gain_min, tuning.nearby_local_gain_max)
        cv_ok = after_cv <= before_cv + 0.0015 and after_cv <= original_cv + 0.0015
        if not (local_ok and cv_ok):
            rejected.append(
                {
                    "index": int(gap.index),
                    "reason": "geometry_not_better",
                    "candidate": best,
                    "before_local_error": float(before_local),
                    "after_local_error": float(after_local),
                    "before_width_cv": float(before_cv),
                    "after_width_cv": float(after_cv),
                }
            )
            continue
        corrected = proposed
        accepted.append(
            {
                "index": int(gap.index),
                "from_center": float(gap.center),
                "to_center": float(proposed_gap.center),
                "delta_px": float(proposed_gap.center - gap.center),
                "from_score": float(gap.score),
                "to_score": float(proposed_gap.score),
                "from_method": gap.method,
                "to_method": proposed_gap.method,
                "before_local_error": float(before_local),
                "after_local_error": float(after_local),
                "before_width_cv": float(before_cv),
                "after_width_cv": float(after_cv),
                "nearby_separator_candidate": replacement,
            }
        )
    return corrected, {
        "used": True,
        "accepted": accepted,
        "accepted_count": len(accepted),
        "rejected": rejected[:8],
        "rejected_count": len(rejected),
        "original_width_cv": float(original_cv),
        "final_width_cv": float(gap_width_cv(corrected, origin, pitch, count)),
        "confidence_cap_required": bool(accepted),
    }


def apply_robust_grid(
    gaps: list[Gap],
    origin: float,
    pitch: float,
    strip_mode: str,
    format_name: str = "135",
    profile: Optional[np.ndarray] = None,
    gray_work: Optional[np.ndarray] = None,
    outer: Optional[Box] = None,
) -> tuple[list[Gap], dict[str, Any]]:
    if not gaps:
        return gaps, {"grid_used": False}
    tuning = format_tuning(format_name)
    constrained = [constrain_gap_to_geometry(gap, origin + pitch * gap.index, pitch, strip_mode, format_name) for gap in gaps]
    reliable = [gap for gap in constrained if gap.method in HARD_GAP_METHODS and gap.score >= tuning.robust_reliable_min_score]
    if len(reliable) < tuning.robust_min_reliable:
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable)}
    best: Optional[tuple[int, float, float, float]] = None
    for a_i, a in enumerate(reliable):
        for b in reliable[a_i + 1:]:
            dk = b.index - a.index
            if dk == 0:
                continue
            cand_pitch = (b.center - a.center) / float(dk)
            if cand_pitch <= pitch * tuning.robust_pitch_min_ratio or cand_pitch >= pitch * tuning.robust_pitch_max_ratio:
                continue
            cand_origin = a.center - cand_pitch * a.index
            residuals = [abs(g.center - (cand_origin + cand_pitch * g.index)) for g in reliable]
            tolerance = clamp_float(
                pitch * (tuning.robust_full_tolerance_ratio if strip_mode == "full" else tuning.robust_partial_tolerance_ratio),
                tuning.robust_tolerance_min,
                tuning.robust_tolerance_max,
            )
            inliers = sum(1 for value in residuals if value <= tolerance)
            median_residual = float(np.median(np.array(residuals, dtype=np.float64))) if residuals else 0.0
            rank = (inliers, -median_residual, -abs(cand_pitch - pitch), cand_pitch)
            if best is None or rank > (best[0], -best[3], -abs(best[1] - pitch), best[1]):
                best = (inliers, float(cand_pitch), float(cand_origin), median_residual)
    if best is None:
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable), "grid_rejected": "no_pair_model"}
    inlier_count, fit_pitch, fit_origin, median_residual = best
    if inlier_count < tuning.robust_min_reliable:
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable), "grid_rejected": "too_few_inliers"}
    if median_residual > clamp_float(pitch * tuning.robust_reject_residual_ratio, tuning.robust_tolerance_min, tuning.robust_tolerance_max):
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable), "grid_rejected": "high_residual", "grid_residual": median_residual}
    max_shift = clamp_float(
        pitch * (tuning.robust_full_shift_ratio if strip_mode == "full" else tuning.robust_partial_shift_ratio),
        tuning.robust_shift_min,
        tuning.robust_shift_max,
    )
    hard_protection_residual_threshold = clamp_float(pitch * tuning.robust_hard_protect_ratio, tuning.robust_hard_protect_min, tuning.robust_hard_protect_max)
    allow_hard_protection = median_residual > hard_protection_residual_threshold
    adjusted: list[Gap] = []
    protected_hard: list[dict[str, Any]] = []
    overridden_hard: list[dict[str, Any]] = []
    for gap in constrained:
        predicted = float(fit_origin + fit_pitch * gap.index)
        theoretical = float(origin + pitch * gap.index)
        predicted = max(theoretical - max_shift, min(theoretical + max_shift, predicted))
        trust, trust_detail = light_hard_gap_trust(
            gap,
            pitch,
            predicted=predicted,
            profile=profile,
            gray_work=gray_work,
            outer=outer,
            format_name=format_name,
        )
        if gap.method in HARD_GAP_METHODS and abs(gap.center - predicted) <= clamp_float(pitch * tuning.robust_hard_keep_ratio, tuning.robust_hard_keep_min, tuning.robust_hard_keep_max):
            adjusted.append(gap)
        elif allow_hard_protection and trust == "strong_separator":
            adjusted.append(gap)
            protected_hard.append(
                {
                    "index": int(gap.index),
                    "method": gap.method,
                    "center": float(gap.center),
                    "predicted": float(predicted),
                    "delta_px": float(gap.center - predicted),
                    "width_px": float(gap.width),
                    "score": float(gap.score),
                    "trust": trust,
                    "trust_detail": trust_detail,
                }
            )
        else:
            if gap.method in HARD_GAP_METHODS:
                overridden_hard.append(
                    {
                        "index": int(gap.index),
                        "method": gap.method,
                        "center": float(gap.center),
                        "predicted": float(predicted),
                        "delta_px": float(gap.center - predicted),
                        "width_px": float(gap.width),
                        "score": float(gap.score),
                        "trust": trust,
                        "trust_detail": trust_detail,
                    }
                )
            adjusted.append(Gap(gap.index, predicted, gap.score, "grid"))
    return adjusted, {
        "grid_used": True,
        "reliable_gaps": len(reliable),
        "grid_inliers": int(inlier_count),
        "grid_pitch": float(fit_pitch),
        "grid_origin": float(fit_origin),
        "grid_residual": median_residual,
        "hard_protection_residual_threshold": float(hard_protection_residual_threshold),
        "hard_protection_allowed": bool(allow_hard_protection),
        "protected_hard_gaps": protected_hard,
        "overridden_hard_gaps": overridden_hard,
    }


def find_enhanced_gap(profile: np.ndarray, expected: float, pitch: float, index: int, format_name: str = "135") -> Gap:
    tuning = format_tuning(format_name)
    gap = find_gap(profile, expected, pitch, index, format_name)
    if gap.method != "detected":
        return gap
    if gap.score < 0.34:
        return Gap(index, float(expected), gap.score, "equal")
    if gap.start is None or gap.end is None:
        return Gap(index, float(expected), gap.score, "equal")
    width = abs(float(gap.end) - float(gap.start))
    if width <= 0 or width > clamp_float(pitch * tuning.enhanced_max_width_ratio, tuning.enhanced_max_width_min, tuning.enhanced_max_width_max):
        return Gap(index, float(expected), gap.score, "equal")
    if abs(gap.center - expected) > clamp_float(pitch * tuning.enhanced_shift_ratio, tuning.enhanced_shift_min, tuning.enhanced_shift_max):
        return Gap(index, float(expected), gap.score, "equal")
    return Gap(index, gap.center, gap.score, "enhanced-detected", gap.start, gap.end)


def merge_enhanced_separator_gaps(
    gray_work: np.ndarray,
    outer: Box,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    strip_mode: str,
    format_name: str = "135",
    cache: Optional[AnalysisCache] = None,
) -> tuple[list[Gap], dict[str, Any]]:
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0 or outer.width <= 0 or outer.height <= 0:
        return gaps, {"used": False, "reason": "empty_outer"}
    profile = cached_enhanced_separator_profile(cache, gray_work, outer, format_name)
    merged: list[Gap] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for gap in gaps:
        if gap.method in HARD_GAP_METHODS:
            merged.append(gap)
            continue
        expected = origin + pitch * gap.index
        enhanced = find_enhanced_gap(profile, expected, pitch, gap.index, format_name)
        if enhanced.method == "enhanced-detected":
            merged.append(enhanced)
            accepted.append(
                {
                    "index": int(gap.index),
                    "center": float(enhanced.center),
                    "score": float(enhanced.score),
                    "replaced_method": gap.method,
                }
            )
        else:
            merged.append(gap)
            rejected.append(
                {
                    "index": int(gap.index),
                    "score": float(enhanced.score),
                    "method": enhanced.method,
                    "kept_method": gap.method,
                }
            )
    constrained = [
        constrain_gap_to_geometry(gap, origin + pitch * gap.index, pitch, strip_mode, format_name)
        if gap.method == "enhanced-detected" else gap
        for gap in merged
    ]
    return constrained, {
        "used": True,
        "accepted": accepted,
        "rejected": rejected[:8],
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
    }


def should_run_enhanced_separator_analysis(analysis: str, gaps: list[Gap], count: int, format_name: str = "135") -> bool:
    tuning = format_tuning(format_name)
    if analysis == "off":
        return False
    if analysis == "always":
        return True
    expected = max(0, count - 1)
    if expected <= 0:
        return False
    hard = [gap for gap in gaps if gap.method in HARD_GAP_METHODS]
    model_only = [gap for gap in gaps if gap.method in {"equal", "grid"}]
    low_score_hard = any(gap.score < tuning.enhanced_auto_low_score for gap in hard)
    return len(hard) < expected or bool(model_only) or low_score_hard


def frame_boxes_from_gaps(
    outer: Box,
    gaps: list[Gap],
    count: int,
    image_w: int,
    image_h: int,
    bleed_x: int,
    bleed_y: int,
    origin: float = 0.0,
    pitch: Optional[float] = None,
    apply_geometry_fit: bool = True,
    geometry_policy: Optional["FrameFitPolicy"] = None,
) -> list[Box]:
    if pitch is None:
        cuts = [float(outer.left)] + [gap.center + outer.left for gap in gaps] + [float(outer.right)]
    else:
        cuts = [outer.left + origin] + [outer.left + gap.center for gap in gaps] + [outer.left + origin + pitch * count]
    if apply_geometry_fit:
        cuts = fit_cuts_by_geometry(cuts, outer, count, pitch, geometry_policy)
    boxes: list[Box] = []
    for left, right in zip(cuts[:-1], cuts[1:]):
        box = Box(int(round(left)), outer.top, int(round(right)), outer.bottom)
        boxes.append(box.expand(bleed_x, bleed_y, image_w, image_h))
    return boxes[:count]


def fit_cuts_by_geometry(cuts: list[float], outer: Box, count: int, pitch: Optional[float], policy: Optional["FrameFitPolicy"] = None) -> list[float]:
    if len(cuts) != count + 1 or count <= 1:
        return cuts
    policy = policy or FrameFitPolicy(name="default", edge_evidence=False, geometry_fallback=True)
    widths = np.diff(np.array(cuts, dtype=np.float64))
    if widths.size != count or np.any(widths <= 1):
        return cuts
    width_cv = float(widths.std() / max(1.0, widths.mean()))
    target = float(np.median(widths))
    if pitch is not None and policy.geometry_pitch_min_ratio <= target / max(1.0, float(pitch)) <= policy.geometry_pitch_max_ratio:
        target = float(pitch)
    if width_cv <= policy.geometry_noop_width_cv:
        return cuts

    centers = (np.array(cuts[:-1], dtype=np.float64) + np.array(cuts[1:], dtype=np.float64)) / 2.0
    starts = centers - (np.arange(count, dtype=np.float64) + 0.5) * target
    start = float(np.median(starts))
    start = max(float(outer.left), min(float(outer.right) - target * count, start))
    fitted = [start + target * i for i in range(count + 1)]
    outer_tolerance = clamp_float(
        target * policy.geometry_outer_tolerance_ratio,
        policy.geometry_outer_tolerance_min,
        policy.geometry_outer_tolerance_max,
    )
    if fitted[0] < outer.left - outer_tolerance or fitted[-1] > outer.right + outer_tolerance:
        return cuts
    if len(fitted) != len(cuts) or any(b <= a for a, b in zip(fitted[:-1], fitted[1:])):
        return cuts
    return fitted


def frame_edge_weight(gap: Gap) -> float:
    if gap.width <= 0:
        return 0.0
    if gap.method == "edge-pair":
        return max(0.0, min(1.8, gap.score)) * 1.20
    if gap.method == "detected":
        return max(0.0, min(1.5, gap.score))
    if gap.method == "enhanced-detected":
        return max(0.0, min(1.2, gap.score)) * 0.70
    return 0.0


def relative_ranges_from_gaps(outer: Box, gaps: list[Gap], count: int) -> list[tuple[float, float]]:
    cuts = [0.0] + [float(gap.center) for gap in gaps] + [float(outer.width)]
    return [(left, right) for left, right in zip(cuts[:-1], cuts[1:])]


def box_list_from_relative_ranges(
    outer: Box,
    ranges: list[tuple[float, float]],
    image_w: int,
    image_h: int,
    bleed_x: int,
    bleed_y: int,
) -> list[Box]:
    out: list[Box] = []
    for left, right in ranges:
        box = Box(outer.left + int(round(left)), outer.top, outer.left + int(round(right)), outer.bottom)
        out.append(box.expand(bleed_x, bleed_y, image_w, image_h))
    return out


@dataclass(frozen=True)
class FrameFitPolicy:
    name: str
    edge_evidence: bool
    geometry_fallback: bool
    min_edge_samples: int = 2
    nominal_min_ratio: float = 0.72
    nominal_max_ratio: float = 1.10
    inlier_tolerance_ratio: float = 0.035
    min_inlier_tolerance_px: float = 3.0
    geometry_pitch_min_ratio: float = 0.85
    geometry_pitch_max_ratio: float = 1.15
    geometry_noop_width_cv: float = 0.006
    geometry_outer_tolerance_ratio: float = 0.0
    geometry_outer_tolerance_min: float = 1.0
    geometry_outer_tolerance_max: float = 1.0
    edge_candidate_weight_with_edges: float = 0.18
    edge_candidate_weight_without_edges: float = 1.0
    edge_adjust_tolerance_ratio: float = 0.0
    edge_adjust_tolerance_min: float = 1.0
    edge_adjust_tolerance_max: float = 1.0


def frame_fit_policy(fmt: FilmFormat, strip_mode: str) -> FrameFitPolicy:
    if strip_mode != "full":
        return FrameFitPolicy(name=f"{fmt.name}-partial", edge_evidence=False, geometry_fallback=True)
    if fmt.name == "135-dual":
        return FrameFitPolicy(name="135-dual-lane", edge_evidence=False, geometry_fallback=True)
    if fmt.name == "135":
        return FrameFitPolicy(
            name="135",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.72,
            nominal_max_ratio=1.10,
            inlier_tolerance_ratio=0.035,
        )
    if fmt.name == "half":
        return FrameFitPolicy(
            name="half",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=4,
            nominal_min_ratio=0.78,
            nominal_max_ratio=1.08,
            inlier_tolerance_ratio=0.030,
        )
    if fmt.name == "xpan":
        return FrameFitPolicy(
            name="xpan",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.70,
            nominal_max_ratio=1.12,
            inlier_tolerance_ratio=0.035,
        )
    if fmt.name == "120-645":
        return FrameFitPolicy(
            name="120-645",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.70,
            nominal_max_ratio=1.15,
            inlier_tolerance_ratio=0.040,
        )
    if fmt.name in {"120-66", "120-67"}:
        return FrameFitPolicy(
            name=fmt.name,
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.65,
            nominal_max_ratio=1.20,
            inlier_tolerance_ratio=0.045,
        )
    return FrameFitPolicy(name=fmt.name, edge_evidence=True, geometry_fallback=True)


def fit_boxes_by_edge_evidence(
    outer: Box,
    gaps: list[Gap],
    count: int,
    image_w: int,
    image_h: int,
    bleed_x: int,
    bleed_y: int,
    policy: FrameFitPolicy,
) -> tuple[Optional[list[Box]], dict[str, Any]]:
    if not policy.edge_evidence:
        return None, {"used": False, "reason": "edge_evidence_disabled"}
    if count <= 1 or len(gaps) != count - 1 or outer.width <= 1:
        return None, {"used": False, "reason": "not_applicable"}
    left_edges: list[Optional[tuple[float, float]]] = [None] * count
    right_edges: list[Optional[tuple[float, float]]] = [None] * count
    for i, gap in enumerate(gaps):
        weight = frame_edge_weight(gap)
        if weight <= 0 or gap.start is None or gap.end is None:
            continue
        right_edges[i] = (float(gap.start), weight)
        left_edges[i + 1] = (float(gap.end), weight)

    nominal = outer.width / float(count)
    samples: list[tuple[int, float]] = []
    for i, (left, right) in enumerate(zip(left_edges, right_edges), 1):
        if left is None or right is None:
            continue
        width = float(right[0]) - float(left[0])
        if nominal * policy.nominal_min_ratio <= width <= nominal * policy.nominal_max_ratio:
            samples.append((i, width))
    if len(samples) < policy.min_edge_samples:
        return None, {"used": False, "reason": "too_few_edge_samples", "sample_count": len(samples)}

    widths = np.array([width for _, width in samples], dtype=np.float64)
    target = float(np.median(widths))
    tol = max(policy.min_inlier_tolerance_px, target * policy.inlier_tolerance_ratio)
    inliers = [(i, width) for i, width in samples if abs(width - target) <= tol]
    if len(inliers) < policy.min_edge_samples:
        return None, {"used": False, "reason": "edge_samples_disagree", "sample_count": len(samples)}
    target = float(np.median(np.array([width for _, width in inliers], dtype=np.float64)))
    if not (nominal * policy.nominal_min_ratio <= target <= nominal * policy.nominal_max_ratio):
        return None, {"used": False, "reason": "target_width_out_of_range", "target_width": target}

    base_ranges = relative_ranges_from_gaps(outer, gaps, count)
    max_left = max(0.0, float(outer.width) - target)
    fitted: list[tuple[float, float]] = []
    adjusted: list[int] = []
    for i, (base_left, base_right) in enumerate(base_ranges):
        candidates: list[tuple[float, float]] = []
        if left_edges[i] is not None:
            candidates.append((float(left_edges[i][0]), float(left_edges[i][1])))
        if right_edges[i] is not None:
            candidates.append((float(right_edges[i][0]) - target, float(right_edges[i][1])))
        weak_boundary = any(
            0 <= gi < len(gaps) and gaps[gi].method in {"equal", "grid"}
            for gi in (i - 1, i)
        )
        base_width = float(base_right) - float(base_left)
        if not candidates and not weak_boundary and abs(base_width - target) <= tol:
            fitted.append((base_left, base_right))
            continue
        base_left_from_center = (float(base_left) + float(base_right) - target) / 2.0
        candidates.append((base_left_from_center, policy.edge_candidate_weight_with_edges if candidates else policy.edge_candidate_weight_without_edges))
        new_left = weighted_median(candidates)
        new_left = min(max(0.0, new_left), max_left)
        new_right = new_left + target
        adjust_tolerance = clamp_float(
            target * policy.edge_adjust_tolerance_ratio,
            policy.edge_adjust_tolerance_min,
            policy.edge_adjust_tolerance_max,
        )
        if abs(new_left - base_left) > adjust_tolerance or abs(new_right - base_right) > adjust_tolerance:
            adjusted.append(i + 1)
        fitted.append((new_left, new_right))
    if not adjusted:
        return None, {
            "used": False,
            "reason": "no_adjustment_needed",
            "target_width": target,
            "sample_indices": [i for i, _ in inliers],
        }
    return box_list_from_relative_ranges(outer, fitted, image_w, image_h, bleed_x, bleed_y), {
        "used": True,
        "method": "edge_evidence",
        "target_width": target,
        "sample_indices": [i for i, _ in inliers],
        "sample_widths": [float(width) for _, width in inliers],
        "adjusted_indices": adjusted,
    }


def fit_frame_boxes_from_gaps(
    outer: Box,
    gaps: list[Gap],
    count: int,
    image_w: int,
    image_h: int,
    bleed_x: int,
    bleed_y: int,
    fmt: FilmFormat,
    strip_mode: str,
    origin: float = 0.0,
    pitch: Optional[float] = None,
) -> tuple[list[Box], dict[str, Any]]:
    policy = frame_fit_policy(fmt, strip_mode)
    base_boxes = frame_boxes_from_gaps(
        outer,
        gaps,
        count,
        image_w,
        image_h,
        bleed_x,
        bleed_y,
        origin=origin,
        pitch=pitch,
        apply_geometry_fit=policy.geometry_fallback,
        geometry_policy=policy,
    )
    fitted_boxes, detail = fit_boxes_by_edge_evidence(
        outer,
        gaps,
        count,
        image_w,
        image_h,
        bleed_x,
        bleed_y,
        policy,
    )
    detail = dict(detail)
    detail["policy"] = {
        "name": policy.name,
        "edge_evidence": bool(policy.edge_evidence),
        "geometry_fallback": bool(policy.geometry_fallback),
        "min_edge_samples": int(policy.min_edge_samples),
        "nominal_min_ratio": float(policy.nominal_min_ratio),
        "nominal_max_ratio": float(policy.nominal_max_ratio),
        "inlier_tolerance_ratio": float(policy.inlier_tolerance_ratio),
        "min_inlier_tolerance_px": float(policy.min_inlier_tolerance_px),
        "geometry_pitch_min_ratio": float(policy.geometry_pitch_min_ratio),
        "geometry_pitch_max_ratio": float(policy.geometry_pitch_max_ratio),
        "geometry_noop_width_cv": float(policy.geometry_noop_width_cv),
        "geometry_outer_tolerance_ratio": float(policy.geometry_outer_tolerance_ratio),
        "geometry_outer_tolerance_min": float(policy.geometry_outer_tolerance_min),
        "geometry_outer_tolerance_max": float(policy.geometry_outer_tolerance_max),
        "edge_candidate_weight_with_edges": float(policy.edge_candidate_weight_with_edges),
        "edge_candidate_weight_without_edges": float(policy.edge_candidate_weight_without_edges),
        "edge_adjust_tolerance_ratio": float(policy.edge_adjust_tolerance_ratio),
        "edge_adjust_tolerance_min": float(policy.edge_adjust_tolerance_min),
        "edge_adjust_tolerance_max": float(policy.edge_adjust_tolerance_max),
    }
    if fitted_boxes is not None:
        return fitted_boxes, detail
    detail.setdefault("method", "geometry_fallback" if policy.geometry_fallback else "raw_gaps")
    return base_boxes, detail


def weighted_median(candidates: list[tuple[float, float]]) -> float:
    ordered = sorted((float(value), max(0.0, float(weight))) for value, weight in candidates)
    if not ordered:
        return 0.0
    total = sum(weight for _, weight in ordered)
    if total <= 0:
        return float(np.median(np.array([value for value, _ in ordered], dtype=np.float64)))
    acc = 0.0
    for value, weight in ordered:
        acc += weight
        if acc >= total / 2.0:
            return value
    return ordered[-1][0]
