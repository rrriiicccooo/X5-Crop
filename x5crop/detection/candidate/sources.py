from __future__ import annotations

from dataclasses import asdict
from typing import Optional

import numpy as np

from ...runtime_config import RuntimeConfig
from ...domain import Detection
from ...formats import FormatSpec
from ...geometry.layout import work_gray
from ...policies.registry import get_detection_policy
from ...policies.runtime_policy import DetectionPolicy
from ...runtime import AnalysisCache
from ..evidence.content_evidence import content_evidence_detail
from ..outer.proposal.base import unique_outer_candidates
from ..outer.proposal.plan import (
    outer_candidate_strategy,
    outer_proposal_candidates,
    separator_full_width_outer_proposal_candidates,
    wide_separator_outer_proposal_candidates,
)
from .build import build_detection_for_outer
from .counts import raw_detection_rank
from .partial_holder import partial_safe_frame_content_detail, partial_safe_leading_content_detail
from .wide_separator_retry import should_try_wide_separator_candidates
from .wide_separator_selection import select_full_wide_separator_candidate
from .source_policy import separator_full_width_can_compete, separator_outer_gap_max_width_override


def detect_candidate_for_count(
    gray: np.ndarray,
    config: RuntimeConfig,
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
    separator_full_width_mode = policy.outer.separator_full_width
    should_try_separator_full_width = (
        separator_full_width_mode == "always"
        or (
            separator_full_width_mode == "conditional"
            and (regular_best is None or separator_full_width_can_compete(regular_best, gray, policy))
        )
    )
    if should_try_separator_full_width:
        separator_full_width_candidates = separator_full_width_outer_proposal_candidates(
            gray_work,
            outer_candidates,
            fmt,
            count,
            strip_mode,
            cache,
            policy,
        )
        for candidate in separator_full_width_candidates:
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
        outer_candidates = unique_outer_candidates([*outer_candidates, *separator_full_width_candidates])
    current_best_for_wide = max(candidates, key=lambda d: raw_detection_rank(d, config.confidence_threshold)) if candidates else None
    should_try_wide_separator = should_try_wide_separator_candidates(
        policy,
        strip_mode,
        count,
        fmt,
        candidates,
        current_best_for_wide,
    )
    wide_separator_candidates = (
        wide_separator_outer_proposal_candidates(
            gray_work,
            outer_candidates,
            fmt,
            count,
            strip_mode,
            cache,
            policy,
        )
        if should_try_wide_separator
        else []
    )
    if wide_separator_candidates:
        for candidate in wide_separator_candidates:
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
        outer_candidates = unique_outer_candidates([*outer_candidates, *wide_separator_candidates])
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
    full_wide_separator_best = select_full_wide_separator_candidate(
        gray,
        candidates,
        best,
        config.confidence_threshold,
        cache,
        policy,
    )
    if full_wide_separator_best is not None:
        best = full_wide_separator_best
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
    config: RuntimeConfig,
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
