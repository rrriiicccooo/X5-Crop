from __future__ import annotations

from dataclasses import asdict
from typing import Optional

import numpy as np

from ..config import Config
from ..domain import Detection
from ..formats import FormatSpec
from ..geometry.boxes import original_box_to_work
from ..geometry.layout import work_gray
from ..geometry.outer_boxes import unique_outer_candidates
from ..policies.runtime_policy import DetectionPolicy
from ..policies.registry import get_detection_policy
from ..runtime import AnalysisCache
from .candidate_decision import apply_candidate_decision_policy
from .candidate_build import build_detection_for_outer
from .candidates import raw_detection_rank
from .content import content_detection_for_count, content_evidence_detail
from .outer import (
    outer_candidate_strategy,
    outer_proposal_candidates,
    separator_dark_band_outer_candidates,
    separator_geometry_outer_candidates,
)
from .partial_holder import (
    partial_safe_frame_content_detail,
    partial_safe_leading_content_detail,
    partial_safe_wide_like_gap_detail,
)
from .scoring import detail_float
from .selection import is_partial_safe_auto_candidate


def select_full_dark_band_candidate(
    gray: np.ndarray,
    candidates: list[Detection],
    current_best: Detection,
    threshold: float,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> Optional[Detection]:
    dark_band = policy.outer.dark_band_outer
    if (
        dark_band.mode == "off"
        or not dark_band.full_selection_enabled
        or current_best.strip_mode not in dark_band.full_selection_strip_modes
        or (
            dark_band.full_selection_requires_required_count
            and current_best.count != dark_band.required_count
        )
    ):
        return None
    dark_candidates = [
        detection
        for detection in candidates
        if str(detection.detail.get("outer_candidate_strategy", "")) == "dark_band_outer"
    ]
    if not dark_candidates:
        return None

    current_content = content_evidence_detail(gray, current_best, cache, policy.content)
    current_support = str(current_content.get("support", ""))
    current_reasons = set(current_best.review_reasons)
    current_needs_help = (
        current_best.confidence < threshold
        or current_support in set(dark_band.full_selection_help_supports)
        or bool(current_reasons.intersection(dark_band.full_selection_help_reasons))
    )
    if dark_band.full_selection_requires_help and not current_needs_help:
        return None

    scored: list[tuple[tuple[int, int, float, float, float], Detection]] = []
    for detection in dark_candidates:
        content_detail = content_evidence_detail(gray, detection, cache, policy.content)
        support = str(content_detail.get("support", ""))
        if support != dark_band.full_selection_required_support:
            continue
        hard_gaps = sum(1 for gap in detection.gaps if gap.method != "equal")
        equal_gaps = int(detection.detail.get("equal_gaps", 0) or 0)
        if hard_gaps < max(1, detection.count - 1):
            continue
        if equal_gaps > 0 and not dark_band.full_selection_allow_equal_gaps:
            continue
        width_cv = detail_float(detection.detail, "width_cv", 1.0)
        median_coverage = detail_float(content_detail, "median_coverage", 0.0)
        scored.append(
            (
                (
                    1 if detection.confidence >= threshold else 0,
                    hard_gaps,
                    median_coverage,
                    float(detection.confidence),
                    -width_cv,
                ),
                detection,
            )
        )
    if not scored:
        return None
    return max(scored, key=lambda item: item[0])[1]


def separator_geometry_can_compete(
    detection: Detection,
    gray: np.ndarray,
    policy: DetectionPolicy,
) -> bool:
    competition = policy.candidate_run.separator_geometry_competition
    if not competition.enabled:
        return False
    outer_candidate_strategy = str(detection.detail.get("outer_candidate_strategy", ""))
    frames = [original_box_to_work(frame, detection.layout, gray.shape[1], gray.shape[0]) for frame in detection.frames]
    aspects = [
        frame.width / max(1.0, float(frame.height))
        for frame in frames
        if frame.valid() and frame.height > 0
    ]
    if not aspects:
        return False
    median_aspect = float(np.median(np.array(aspects, dtype=np.float32)))
    if (
        outer_candidate_strategy in competition.content_outer_max_median_aspect_strategies
        and detection.strip_mode in competition.content_outer_max_median_aspect_strip_modes
    ):
        return median_aspect <= competition.content_outer_max_median_aspect
    return median_aspect >= competition.general_min_median_aspect


def fallback_outer_proposals_enabled(policy: DetectionPolicy) -> bool:
    fallback = policy.candidate_run.fallback
    if not fallback.use_outer_proposals:
        return False
    strategies = set(fallback.strategies)
    return bool(
        (policy.outer.separator_first == "fallback" and "separator_outer" in strategies)
        or (policy.outer.edge_anchor == "fallback" and "edge_anchor_outer" in strategies)
        or (policy.outer.separator_geometry == "fallback" and "separator_geometry_outer" in strategies)
    )


def should_try_equal_first_before_wide_retry(
    policy: DetectionPolicy,
    strip_mode: str,
    count: int,
    fmt: FormatSpec,
) -> bool:
    retry_policy = policy.candidate_run.equal_first_before_wide_retry
    if not retry_policy.enabled:
        return False
    if retry_policy.requires_wide_geometry_support and not policy.separator.geometry_support.wide_geometry.enabled:
        return False
    if strip_mode not in retry_policy.strip_modes:
        return False
    if retry_policy.requires_default_count and count != fmt.default_count:
        return False
    return True


def separator_outer_gap_max_width_override(
    policy: DetectionPolicy,
    current_override: Optional[float] = None,
) -> Optional[float]:
    if current_override is not None:
        return current_override
    override = policy.outer.separator_gap_search_max_width_ratio
    if override > policy.separator.gap_search.max_width_ratio:
        return override
    return None


def has_partial_safe_wide_like_candidate(
    candidates: list[Detection],
    fmt: FormatSpec,
    policy: DetectionPolicy,
) -> bool:
    for detection in candidates:
        candidate_wide_like = partial_safe_wide_like_gap_detail(detection, fmt, policy)
        if (
            bool(candidate_wide_like.get("used", False))
            and int(candidate_wide_like.get("wide_like_gaps", 0) or 0)
            >= int(candidate_wide_like.get("min_wide_like_gaps", 0) or 0)
            and int(detection.detail.get("equal_gaps", 0) or 0) == 0
        ):
            return True
    return False


def partial_dark_band_retry_needed(
    current_best: Detection,
    candidates: list[Detection],
    fmt: FormatSpec,
    policy: DetectionPolicy,
) -> bool:
    retry_policy = policy.candidate_run.dark_band_retry
    if (
        not retry_policy.try_partial_when_no_safe_wide_like_candidate
        or has_partial_safe_wide_like_candidate(candidates, fmt, policy)
    ):
        return False
    wide_like_detail = partial_safe_wide_like_gap_detail(current_best, fmt, policy)
    equal_gaps = int(current_best.detail.get("equal_gaps", 0) or 0)
    insufficient_wide_like = (
        bool(wide_like_detail.get("used", False))
        and int(wide_like_detail.get("wide_like_gaps", 0) or 0)
        < int(wide_like_detail.get("min_wide_like_gaps", 0) or 0)
    )
    return (
        retry_policy.partial_retry_on_equal_gaps
        and equal_gaps > 0
    ) or (
        retry_policy.partial_retry_on_insufficient_wide_like_gaps
        and insufficient_wide_like
    )


def should_try_dark_band_candidates(
    policy: DetectionPolicy,
    strip_mode: str,
    count: int,
    fmt: FormatSpec,
    candidates: list[Detection],
    current_best: Optional[Detection],
) -> bool:
    if policy.outer.dark_band == "off":
        return False
    retry_policy = policy.candidate_run.dark_band_retry
    if strip_mode in retry_policy.partial_retry_strip_modes:
        return current_best is not None and partial_dark_band_retry_needed(current_best, candidates, fmt, policy)
    if strip_mode in retry_policy.full_retry_strip_modes:
        if not retry_policy.try_full_default_count:
            return False
        if retry_policy.full_retry_requires_default_count and count != fmt.default_count:
            return False
        return True
    return False


def detect_candidate_for_count(
    gray: np.ndarray,
    config: Config,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
    gap_max_width_ratio_override: Optional[float] = None,
    policy: Optional[DetectionPolicy] = None,
) -> Detection:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    outer_candidates = outer_proposal_candidates(
        gray_work,
        fmt,
        count,
        strip_mode,
        cache,
        policy=policy,
    )
    candidates: list[Detection] = []
    for candidate in outer_candidates:
        candidate_gap_override = gap_max_width_ratio_override
        if candidate.strategy == "separator_outer":
            candidate_gap_override = separator_outer_gap_max_width_override(policy, candidate_gap_override)
        detection = build_detection_for_outer(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            candidate.box,
            offset_fraction,
            candidate.name,
            candidate.strategy,
            cache=cache,
            gap_max_width_ratio_override=candidate_gap_override,
            policy=policy,
        )
        candidates.append(detection)
    regular_best = max(candidates, key=lambda d: raw_detection_rank(d, config.confidence_threshold)) if candidates else None
    separator_geometry_mode = policy.outer.separator_geometry
    should_try_separator_geometry = (
        separator_geometry_mode == "always"
        or (
            separator_geometry_mode == "conditional"
            and (regular_best is None or separator_geometry_can_compete(regular_best, gray, policy))
        )
    )
    if should_try_separator_geometry:
        separator_geometry_candidates = separator_geometry_outer_candidates(
            gray_work,
            outer_candidates,
            fmt,
            count,
            strip_mode,
            cache,
            policy,
        )
        for candidate in separator_geometry_candidates:
            candidate_gap_override = separator_outer_gap_max_width_override(policy, gap_max_width_ratio_override)
            candidates.append(
                build_detection_for_outer(
                    gray,
                    config,
                    fmt,
                    count,
                    strip_mode,
                    candidate.box,
                    offset_fraction,
                    candidate.name,
                    candidate.strategy,
                    cache=cache,
                    gap_max_width_ratio_override=candidate_gap_override,
                    policy=policy,
                )
            )
        outer_candidates = unique_outer_candidates([*outer_candidates, *separator_geometry_candidates])
    current_best_for_dark = max(candidates, key=lambda d: raw_detection_rank(d, config.confidence_threshold)) if candidates else None
    should_try_dark_band = should_try_dark_band_candidates(
        policy,
        strip_mode,
        count,
        fmt,
        candidates,
        current_best_for_dark,
    )
    separator_dark_band_candidates = (
        separator_dark_band_outer_candidates(
            gray_work,
            outer_candidates,
            fmt,
            count,
            strip_mode,
            policy,
        )
        if should_try_dark_band
        else []
    )
    if separator_dark_band_candidates:
        for candidate in separator_dark_band_candidates:
            candidate_gap_override = separator_outer_gap_max_width_override(policy, gap_max_width_ratio_override)
            candidates.append(
                build_detection_for_outer(
                    gray,
                    config,
                    fmt,
                    count,
                    strip_mode,
                    candidate.box,
                    offset_fraction,
                    candidate.name,
                    candidate.strategy,
                    cache=cache,
                    gap_max_width_ratio_override=candidate_gap_override,
                    policy=policy,
                )
            )
        outer_candidates = unique_outer_candidates([*outer_candidates, *separator_dark_band_candidates])
    best_candidates = candidates
    if (
        policy.partial_holder.safe_extra_frames
        and policy.partial_holder.checks_leading_content
        and strip_mode in policy.partial_holder.safe_extra_frames_strip_modes
        and len(candidates) > 1
    ):
        non_cutting_candidates: list[Detection] = []
        for detection in candidates:
            if str(detection.detail.get("outer_candidate_strategy", "")) != "content_outer":
                non_cutting_candidates.append(detection)
                continue
            leading_content = partial_safe_leading_content_detail(gray, detection, fmt, cache, policy)
            frame_content = partial_safe_frame_content_detail(
                content_evidence_detail(gray, detection, cache, policy.content),
                detection,
                fmt,
                policy,
            )
            if (
                (not bool(leading_content.get("used", False)) or bool(leading_content.get("ok", True)))
                and (not bool(frame_content.get("used", False)) or bool(frame_content.get("ok", True)))
            ):
                non_cutting_candidates.append(detection)
        if non_cutting_candidates:
            best_candidates = non_cutting_candidates
    best = max(best_candidates, key=lambda d: raw_detection_rank(d, config.confidence_threshold))
    full_dark_band_best = select_full_dark_band_candidate(
        gray,
        candidates,
        best,
        config.confidence_threshold,
        cache,
        policy,
    )
    if full_dark_band_best is not None:
        best = full_dark_band_best
    areas = [candidate.box.width * candidate.box.height for candidate in outer_candidates if candidate.box.valid()]
    if areas:
        best.detail["outer_candidate_count"] = len(outer_candidates)
        best.detail["outer_area_spread_ratio"] = (max(areas) - min(areas)) / max(1.0, float(max(areas)))
        best.detail["outer_candidates"] = [
            {"name": candidate.name, "strategy": outer_candidate_strategy(candidate), "box": asdict(candidate.box)}
            for candidate in outer_candidates
        ]
    return best


def detect_fallback_outer_proposal_candidate_for_count(
    gray: np.ndarray,
    config: Config,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
) -> Optional[Detection]:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    outer_candidates = outer_proposal_candidates(
        gray_work,
        fmt,
        count,
        strip_mode,
        cache,
        fallback_only=True,
        policy=policy,
    )
    if not outer_candidates:
        return None

    candidates: list[Detection] = []
    for candidate in outer_candidates:
        candidate_gap_override = separator_outer_gap_max_width_override(policy)
        candidates.append(
            build_detection_for_outer(
                gray,
                config,
                fmt,
                count,
                strip_mode,
                candidate.box,
                offset_fraction,
                candidate.name,
                candidate.strategy,
                cache=cache,
                gap_max_width_ratio_override=candidate_gap_override,
                policy=policy,
            )
        )
    best = max(candidates, key=lambda d: raw_detection_rank(d, config.confidence_threshold))
    areas = [candidate.box.width * candidate.box.height for candidate in outer_candidates if candidate.box.valid()]
    if areas:
        best.detail["outer_candidate_count"] = len(outer_candidates)
        best.detail["outer_area_spread_ratio"] = (max(areas) - min(areas)) / max(1.0, float(max(areas)))
        best.detail["outer_candidates"] = [
            {"name": candidate.name, "strategy": outer_candidate_strategy(candidate), "box": asdict(candidate.box)}
            for candidate in outer_candidates
        ]
    return best


def calibrated_candidates_for_count(
    gray: np.ndarray,
    config: Config,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    offset: float,
    cache: AnalysisCache,
    policy: Optional[DetectionPolicy] = None,
) -> tuple[list[Detection], bool]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    content_policy = policy.candidate_run.content_candidate
    candidates: list[Detection] = []
    stop_after_this_count = False
    wide_retry_allowed = bool(policy.separator.wide_retry)
    wide_retry_max_width_ratio = policy.separator.wide_retry_max_width_ratio
    wide_retry_has_room = wide_retry_max_width_ratio > policy.separator.gap_search.max_width_ratio
    equal_first_before_wide_retry = (
        should_try_equal_first_before_wide_retry(policy, strip_mode, count, fmt)
        and wide_retry_allowed
        and wide_retry_has_room
    )
    separator = detect_candidate_for_count(gray, config, fmt, count, strip_mode, offset, cache, policy=policy)
    separator_candidate = apply_candidate_decision_policy(gray, separator, config, fmt, "separator", cache, policy=policy)
    candidates.append(separator_candidate)
    separator_gate_candidate = separator_candidate
    separator_auto_gate = bool(
        separator_candidate.detail.get("candidate_decision", {}).get("auto_gate", False)
    )
    if (
        not separator_auto_gate
        and wide_retry_allowed
        and wide_retry_has_room
    ):
        wide_separator = detect_candidate_for_count(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset,
            cache,
            gap_max_width_ratio_override=wide_retry_max_width_ratio,
            policy=policy,
        )
        wide_candidate = apply_candidate_decision_policy(gray, wide_separator, config, fmt, "separator", cache, policy=policy)
        wide_candidate.detail["wide_gap_retry"] = {
            "used": True,
            "base_gap_max_width_ratio": float(policy.separator.gap_search.max_width_ratio),
            "retry_gap_max_width_ratio": float(wide_retry_max_width_ratio),
        }
        if equal_first_before_wide_retry:
            wide_candidate.detail["wide_gap_retry"]["equal_first_before_wide_retry"] = True
        candidates.append(wide_candidate)
        if bool(wide_candidate.detail.get("candidate_decision", {}).get("auto_gate", False)):
            separator_auto_gate = True
            separator_gate_candidate = wide_candidate
    if (
        not separator_auto_gate
        and fallback_outer_proposals_enabled(policy)
    ):
        fallback_proposal = detect_fallback_outer_proposal_candidate_for_count(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset,
            cache,
            policy=policy,
        )
        if fallback_proposal is not None:
            fallback_candidate = apply_candidate_decision_policy(gray, fallback_proposal, config, fmt, "separator", cache, policy=policy)
            fallback_candidate.detail["outer_proposal_fallback_retry"] = {
                "used": True,
                "separator_first_mode": policy.outer.separator_first,
                "long_axis_edge_anchor_mode": policy.outer.edge_anchor,
                "separator_geometry_mode": policy.outer.separator_geometry,
                "strategies": list(policy.candidate_run.fallback.strategies),
            }
            candidates.append(fallback_candidate)
            fallback_auto_gate = bool(
                fallback_candidate.detail.get("candidate_decision", {}).get("auto_gate", False)
            )
            if fallback_auto_gate:
                separator_auto_gate = True
                separator_gate_candidate = fallback_candidate
    partial_safe_auto = is_partial_safe_auto_candidate(separator_gate_candidate, config.confidence_threshold)
    if partial_safe_auto and policy.candidate_run.partial_stop.stop_after_safe_auto:
        stop_after_this_count = True
    if (
        content_policy.skip_after_separator_auto
        and strip_mode in content_policy.separator_auto_skip_strip_modes
        and separator_auto_gate
        and separator_gate_candidate.confidence >= config.confidence_threshold
    ):
        separator_gate_candidate.detail["content_candidate_skipped"] = content_policy.separator_auto_skip_reason
        return candidates, stop_after_this_count
    if (
        policy.candidate_run.partial_stop.skip_content_after_safe_auto
        and strip_mode in policy.candidate_run.partial_stop.skip_content_after_safe_auto_strip_modes
        and partial_safe_auto
    ):
        separator_gate_candidate.detail["content_candidate_skipped"] = (
            policy.candidate_run.partial_stop.skip_content_after_safe_auto_reason
        )
        return candidates, stop_after_this_count
    if not content_policy.enabled:
        separator_gate_candidate.detail["content_candidate_skipped"] = content_policy.disabled_skip_reason
        return candidates, stop_after_this_count
    content = content_detection_for_count(
        gray,
        config,
        fmt,
        count,
        strip_mode,
        offset,
        cache,
        policy.content,
    )
    if content is not None:
        candidates.append(apply_candidate_decision_policy(gray, content, config, fmt, "content", cache, policy=policy))
    return candidates, stop_after_this_count
