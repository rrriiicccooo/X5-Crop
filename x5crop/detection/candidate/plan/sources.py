from __future__ import annotations

from dataclasses import asdict
from typing import Optional

import numpy as np

from ....domain import Detection
from ....formats import FormatSpec
from ....geometry.layout import work_gray
from ....policies.registry import get_detection_policy
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....runtime.config import RuntimeConfig
from ...evidence.content_evidence import content_evidence_detail
from ..proposal.outer.plan import (
    merge_outer_proposal_candidates,
    outer_candidate_strategy,
    outer_proposal_candidates,
    separator_full_width_outer_proposal_candidates,
    separator_width_profile_outer_proposal_candidates,
)
from ...gap_profiles import (
    BROAD_WIDTH_GAP_PROFILE,
    STANDARD_GAP_PROFILE,
    broad_width_gap_profile_detail,
    is_broad_width_gap_profile,
)
from ..build.detection import build_detection_for_outer
from .counts import raw_detection_rank
from ..assessment.partial_holder import partial_safe_frame_content_detail, partial_safe_leading_content_detail
from .separator_width_profile import should_include_separator_width_profile_candidates
from ..selection.separator_width_profile import select_full_separator_width_profile_candidate
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
    include_late_outer: bool = True,
    include_auxiliary_outer: bool = True,
) -> Detection:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    explicit_count = bool(config.count_override is not None)
    outer_candidates = outer_proposal_candidates(
        gray_work,
        fmt,
        count,
        strip_mode,
        cache,
        policy=policy,
        explicit_count=explicit_count,
    )
    candidates: list[Detection] = []

    def append_detections_for_outer_candidates(
        proposal_candidates,
        gap_override: Optional[float],
        gap_profile: str,
    ) -> None:
        for candidate in proposal_candidates:
            candidate_gap_override = gap_override
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
                gap_search_profile=gap_profile,
                policy=policy,
            )
            if is_broad_width_gap_profile(gap_profile):
                gap_profile_detail = broad_width_gap_profile_detail(policy, candidate_gap_override)
                detection.detail["gap_search_profile"] = gap_profile_detail
                detection.detail["separator_width_profile"] = gap_profile_detail
            candidates.append(detection)

    append_detections_for_outer_candidates(outer_candidates, gap_max_width_ratio_override, STANDARD_GAP_PROFILE)
    regular_best = max(candidates, key=lambda d: raw_detection_rank(d, config.confidence_threshold)) if candidates else None
    separator_full_width_family = policy.outer.proposal.geometry.separator.full_width
    separator_full_width_mode = separator_full_width_family.mode
    should_try_separator_full_width = (
        include_late_outer
        and separator_full_width_family.available_for(strip_mode, explicit_count)
        and (
            separator_full_width_mode == "always"
            or (
                separator_full_width_mode == "conditional"
                and (regular_best is None or separator_full_width_can_compete(regular_best, gray, policy))
            )
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
            explicit_count=explicit_count,
        )
        append_detections_for_outer_candidates(
            separator_full_width_candidates,
            gap_max_width_ratio_override,
            STANDARD_GAP_PROFILE,
        )
        outer_candidates = merge_outer_proposal_candidates([*outer_candidates, *separator_full_width_candidates])
    separator_width_profile_eligible = should_include_separator_width_profile_candidates(
        policy,
        strip_mode,
        count,
        fmt,
        explicit_count,
    )
    should_include_separator_width_profile = include_auxiliary_outer and separator_width_profile_eligible
    separator_width_profile_candidates = (
        separator_width_profile_outer_proposal_candidates(
            gray_work,
            outer_candidates,
            fmt,
            count,
            strip_mode,
            cache,
            policy,
            explicit_count=explicit_count,
        )
        if should_include_separator_width_profile
        else []
    )
    separator_width_profile_gap_override = (
        policy.separator.separator_width_profile_max_width_ratio
        if (
            gap_max_width_ratio_override is None
            and should_include_separator_width_profile
            and policy.separator.separator_width_profile_max_width_ratio > policy.separator.gap_search.max_width_ratio
        )
        else None
    )
    if separator_width_profile_gap_override is not None:
        append_detections_for_outer_candidates(
            outer_candidates,
            separator_width_profile_gap_override,
            BROAD_WIDTH_GAP_PROFILE,
        )
    if separator_width_profile_candidates:
        append_detections_for_outer_candidates(
            separator_width_profile_candidates,
            separator_width_profile_gap_override or gap_max_width_ratio_override,
            BROAD_WIDTH_GAP_PROFILE,
        )
        outer_candidates = merge_outer_proposal_candidates([*outer_candidates, *separator_width_profile_candidates])
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
    full_separator_width_profile_best = select_full_separator_width_profile_candidate(
        gray,
        candidates,
        best,
        config.confidence_threshold,
        cache,
        policy,
    )
    if full_separator_width_profile_best is not None:
        best = full_separator_width_profile_best
    areas = [candidate.box.width * candidate.box.height for candidate in outer_candidates if candidate.box.valid()]
    if areas:
        best.detail["outer_candidate_count"] = len(outer_candidates)
        best.detail["outer_area_spread_ratio"] = (max(areas) - min(areas)) / max(1.0, float(max(areas)))
        best.detail["outer_candidates"] = [
            {"name": candidate.name, "strategy": outer_candidate_strategy(candidate), "box": asdict(candidate.box)}
            for candidate in outer_candidates
        ]
    gap_profiles = [STANDARD_GAP_PROFILE]
    if should_include_separator_width_profile:
        gap_profiles.append(BROAD_WIDTH_GAP_PROFILE)
    best.detail["candidate_plan"] = {
        "source": "separator",
        "count_explicit": bool(explicit_count),
        "outer_execution_stage": (
            "complete"
            if include_late_outer and include_auxiliary_outer
            else "primary"
        ),
        "late_outer_enabled": bool(include_late_outer),
        "auxiliary_outer_enabled": bool(include_auxiliary_outer),
        "gap_profiles": gap_profiles,
        "gap_search_profiles": gap_profiles,
        "outer_candidate_count": int(len(outer_candidates)),
        "separator_full_width_eligible": bool(separator_full_width_family.available_for(strip_mode, explicit_count)),
        "separator_full_width_included": bool(should_try_separator_full_width),
        "broad_width_gap_profile_eligible": bool(separator_width_profile_eligible),
        "broad_width_gap_profile_included": bool(should_include_separator_width_profile),
        "separator_width_profile_eligible": bool(separator_width_profile_eligible),
        "separator_width_profile_included": bool(should_include_separator_width_profile),
    }
    return best


def detect_safety_outer_proposal_candidate_for_count(
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
        safety_only=True,
        policy=policy,
        explicit_count=bool(config.count_override is not None),
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
    best.detail["candidate_plan"] = {
        "source": "safety_candidate",
        "gap_profiles": [STANDARD_GAP_PROFILE],
        "gap_search_profiles": [STANDARD_GAP_PROFILE],
        "outer_candidate_count": int(len(outer_candidates)),
        "review_only": True,
    }
    return best
