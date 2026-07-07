from __future__ import annotations

from dataclasses import asdict
from typing import Optional

import numpy as np

from ....constants import CANDIDATE_SOURCE_SAFETY, CANDIDATE_SOURCE_SEPARATOR
from ....domain import Detection, OuterCandidate
from ....formats import FormatSpec
from ....geometry.layout import work_gray
from ....policies.registry import get_detection_policy
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....runtime.config import RuntimeConfig
from ...evidence.content.frame_support import content_evidence_detail
from ...guidance.content_separator import content_guided_separator_seed_for_count
from .outer_proposals import (
    merge_outer_proposal_candidates,
    outer_candidate_strategy,
    outer_proposal_candidates,
    separator_full_width_outer_proposal_candidates,
)
from ...gap_profiles import WIDTH_AWARE_GAP_PROFILE, width_aware_gap_profile_detail
from ..build.detection import build_detection_for_outer
from ..assessment.base_scoring import apply_base_detection_scoring
from .counts import raw_detection_rank
from ..assessment.partial_holder import partial_safe_frame_content_detail, partial_safe_leading_content_detail
from .source_policy import separator_full_width_can_compete, separator_outer_gap_max_width_override


def _outer_candidate_report_detail(candidate: OuterCandidate) -> dict:
    detail = {
        "name": candidate.name,
        "strategy": outer_candidate_strategy(candidate),
        "box": asdict(candidate.box),
    }
    if candidate.detail:
        detail["proposal_detail"] = dict(candidate.detail)
    return detail


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
    include_extension_outer: bool = True,
    include_supplemental_outer: bool = True,
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
                outer_candidate_detail=candidate.detail,
                cache=cache,
                gap_max_width_ratio_override=candidate_gap_override,
                gap_search_profile=gap_profile,
                policy=policy,
            )
            detection = apply_base_detection_scoring(
                gray_work,
                detection,
                config,
                fmt,
                policy,
            )
            gap_profile_detail = width_aware_gap_profile_detail(policy.separator)
            detection.detail["gap_search_profile"] = gap_profile_detail
            candidates.append(detection)

    append_detections_for_outer_candidates(outer_candidates, gap_max_width_ratio_override, WIDTH_AWARE_GAP_PROFILE)
    regular_best = max(candidates, key=lambda d: raw_detection_rank(d, config.confidence_threshold)) if candidates else None
    separator_full_width_family = policy.outer.proposal.geometry.separator.full_width
    separator_full_width_mode = separator_full_width_family.mode
    should_try_separator_full_width = (
        include_extension_outer
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
            WIDTH_AWARE_GAP_PROFILE,
        )
        outer_candidates = merge_outer_proposal_candidates([*outer_candidates, *separator_full_width_candidates])
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
    areas = [candidate.box.width * candidate.box.height for candidate in outer_candidates if candidate.box.valid()]
    if areas:
        best.detail["outer_candidate_count"] = len(outer_candidates)
        best.detail["outer_area_spread_ratio"] = (max(areas) - min(areas)) / max(1.0, float(max(areas)))
        best.detail["outer_candidates"] = [
            _outer_candidate_report_detail(candidate)
            for candidate in outer_candidates
        ]
    best.detail["candidate_plan"] = {
        "source": "separator",
        "count_explicit": bool(explicit_count),
        "outer_execution_stage": (
            "complete"
            if include_extension_outer and include_supplemental_outer
            else "primary"
        ),
        "extension_outer_enabled": bool(include_extension_outer),
        "supplemental_outer_enabled": bool(include_supplemental_outer),
        "gap_search_profiles": [WIDTH_AWARE_GAP_PROFILE],
        "outer_candidate_count": int(len(outer_candidates)),
        "separator_full_width_eligible": bool(separator_full_width_family.available_for(strip_mode, explicit_count)),
        "separator_full_width_included": bool(should_try_separator_full_width),
        "width_aware_proposal": True,
    }
    return best


def detect_content_guided_separator_candidate_for_count(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
) -> tuple[Optional[Detection], dict]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    guidance_policy = policy.candidate_plan.content_guided_separator
    seed_result = content_guided_separator_seed_for_count(
        gray,
        config,
        fmt,
        count,
        strip_mode,
        offset_fraction,
        cache,
        policy.content,
        guidance_policy,
    )
    if seed_result.seed is None:
        return None, seed_result.detail

    detection = build_detection_for_outer(
        gray,
        config,
        fmt,
        count,
        strip_mode,
        seed_result.seed.outer,
        offset_fraction,
        "content_guided_separator",
        "content_guided_separator_outer",
        outer_candidate_detail={
            "family": "content_guided_separator",
            "content_guidance": seed_result.seed.detail,
        },
        cache=cache,
        allow_outer_refine=False,
        gap_search_profile=WIDTH_AWARE_GAP_PROFILE,
        separator_gap_hints=seed_result.seed.gap_hints,
        policy=policy,
    )
    gap_profile_detail = width_aware_gap_profile_detail(policy.separator)
    detection.detail["gap_search_profile"] = gap_profile_detail
    detection.detail["candidate_source"] = CANDIDATE_SOURCE_SEPARATOR
    detection.detail["content_guided_separator"] = seed_result.seed.detail
    detection.detail["candidate_plan"] = {
        "source": "content_guided_separator",
        "source_candidate": "separator",
        "proposal_family": "content_guided_separator",
        "content_seeded": True,
        "evidence_contract": "separator_evidence_required",
        "gap_search_profiles": [WIDTH_AWARE_GAP_PROFILE],
        "content_guidance": seed_result.seed.gap_hints.summary(),
    }
    return detection, seed_result.detail


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
            outer_candidate_detail=candidate.detail,
            cache=cache,
            gap_max_width_ratio_override=candidate_gap_override,
            policy=policy,
        )
        candidates.append(apply_base_detection_scoring(gray_work, detection, config, fmt, policy))
    best = max(candidates, key=lambda d: raw_detection_rank(d, config.confidence_threshold))
    areas = [candidate.box.width * candidate.box.height for candidate in outer_candidates if candidate.box.valid()]
    if areas:
        best.detail["outer_candidate_count"] = len(outer_candidates)
        best.detail["outer_area_spread_ratio"] = (max(areas) - min(areas)) / max(1.0, float(max(areas)))
        best.detail["outer_candidates"] = [
            _outer_candidate_report_detail(candidate)
            for candidate in outer_candidates
        ]
    best.detail["candidate_plan"] = {
        "source": CANDIDATE_SOURCE_SAFETY,
        "gap_search_profiles": [WIDTH_AWARE_GAP_PROFILE],
        "outer_candidate_count": int(len(outer_candidates)),
        "auto_pass_eligible": False,
    }
    return best
