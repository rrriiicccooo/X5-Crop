from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np

from ....constants import CANDIDATE_SOURCE_SAFETY, CANDIDATE_SOURCE_SEPARATOR
from ....cache import AnalysisCache
from ....domain import Detection, OuterCandidate
from ....formats import FormatSpec
from ....geometry.layout import work_gray
from ....policies.runtime.policy import DetectionPolicy
from ....runtime.config import RuntimeConfig
from ...gap_profiles import WIDTH_AWARE_GAP_PROFILE, width_aware_gap_profile_detail
from ...guidance.content_separator import content_guided_separator_seed_for_count
from ..plan.outer_proposals import (
    merge_outer_proposal_candidates,
    outer_candidate_strategy,
    outer_proposal_candidates,
    separator_full_width_outer_proposal_candidates,
)
from ..plan.source_policy import separator_outer_gap_max_width_override
from .detection import build_detection_for_outer


@dataclass(frozen=True)
class SourceCandidateBatch:
    detections: tuple[Detection, ...]
    outer_candidates: tuple[OuterCandidate, ...]
    detail: dict


def _outer_candidate_report_detail(candidate: OuterCandidate) -> dict:
    detail = {
        "name": candidate.name,
        "strategy": outer_candidate_strategy(candidate),
        "box": asdict(candidate.box),
    }
    if candidate.detail:
        detail["proposal_detail"] = dict(candidate.detail)
    return detail


def _attach_outer_candidate_summary(
    detection: Detection,
    outer_candidates: list[OuterCandidate],
) -> None:
    areas = [candidate.box.width * candidate.box.height for candidate in outer_candidates if candidate.box.valid()]
    if not areas:
        return
    detection.detail["outer_candidate_count"] = len(outer_candidates)
    detection.detail["outer_area_spread_ratio"] = (max(areas) - min(areas)) / max(1.0, float(max(areas)))
    detection.detail["outer_candidates"] = [
        _outer_candidate_report_detail(candidate)
        for candidate in outer_candidates
    ]


def _build_detection_for_outer_candidate(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
    candidate: OuterCandidate,
    *,
    gap_max_width_ratio_override: Optional[float],
    gap_search_profile: str,
) -> Detection:
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
        outer_candidate_detail=candidate.detail,
        cache=cache,
        gap_max_width_ratio_override=candidate_gap_override,
        gap_search_profile=gap_search_profile,
        policy=policy,
    )
    detection.detail["gap_search_profile"] = width_aware_gap_profile_detail(policy.separator)
    return detection


def separator_source_candidates_for_count(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
    *,
    gap_max_width_ratio_override: Optional[float] = None,
    policy: DetectionPolicy,
    include_extension_outer: bool = True,
    include_supplemental_outer: bool = True,
) -> SourceCandidateBatch:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
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
    detections = [
        _build_detection_for_outer_candidate(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset_fraction,
            cache,
            policy,
            candidate,
            gap_max_width_ratio_override=gap_max_width_ratio_override,
            gap_search_profile=WIDTH_AWARE_GAP_PROFILE,
        )
        for candidate in outer_candidates
    ]

    separator_full_width_family = policy.outer.proposal.geometry.separator.full_width
    separator_full_width_mode = separator_full_width_family.mode
    include_full_width = (
        include_extension_outer
        and separator_full_width_family.available_for(strip_mode, explicit_count)
        and separator_full_width_mode in {"always", "conditional"}
    )
    if include_full_width:
        separator_full_width_candidates = separator_full_width_outer_proposal_candidates(
            gray_work,
            outer_candidates,
            fmt,
            count,
            strip_mode,
            cache,
            policy=policy,
            explicit_count=explicit_count,
        )
        detections.extend(
            _build_detection_for_outer_candidate(
                gray,
                config,
                fmt,
                count,
                strip_mode,
                offset_fraction,
                cache,
                policy,
                candidate,
                gap_max_width_ratio_override=gap_max_width_ratio_override,
                gap_search_profile=WIDTH_AWARE_GAP_PROFILE,
            )
            for candidate in separator_full_width_candidates
        )
        outer_candidates = merge_outer_proposal_candidates([*outer_candidates, *separator_full_width_candidates])

    detail = {
        "source": CANDIDATE_SOURCE_SEPARATOR,
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
        "separator_full_width_included": bool(include_full_width),
        "width_aware_proposal": True,
    }
    for detection in detections:
        _attach_outer_candidate_summary(detection, outer_candidates)
        detection.detail["candidate_plan"] = dict(detail)
    return SourceCandidateBatch(tuple(detections), tuple(outer_candidates), detail)


def content_guided_separator_candidate_for_count(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
    *,
    policy: DetectionPolicy,
) -> tuple[Optional[Detection], dict]:
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
    detection.detail["gap_search_profile"] = width_aware_gap_profile_detail(policy.separator)
    detection.detail["candidate_source"] = CANDIDATE_SOURCE_SEPARATOR
    detection.detail["content_guided_separator"] = seed_result.seed.detail
    detection.detail["candidate_plan"] = {
        "source": "content_guided_separator",
        "source_candidate": CANDIDATE_SOURCE_SEPARATOR,
        "proposal_family": "content_guided_separator",
        "content_seeded": True,
        "evidence_contract": "separator_evidence_required",
        "gap_search_profiles": [WIDTH_AWARE_GAP_PROFILE],
        "content_guidance": seed_result.seed.gap_hints.summary(),
    }
    return detection, seed_result.detail


def safety_outer_proposal_candidates_for_count(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
    *,
    policy: DetectionPolicy,
) -> SourceCandidateBatch:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
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
    detections = [
        _build_detection_for_outer_candidate(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset_fraction,
            cache,
            policy,
            candidate,
            gap_max_width_ratio_override=separator_outer_gap_max_width_override(policy),
            gap_search_profile=WIDTH_AWARE_GAP_PROFILE,
        )
        for candidate in outer_candidates
    ]
    detail = {
        "source": CANDIDATE_SOURCE_SAFETY,
        "gap_search_profiles": [WIDTH_AWARE_GAP_PROFILE],
        "outer_candidate_count": int(len(outer_candidates)),
        "candidate_gate_eligible": False,
    }
    for detection in detections:
        _attach_outer_candidate_summary(detection, outer_candidates)
        detection.detail["candidate_plan"] = dict(detail)
    return SourceCandidateBatch(tuple(detections), tuple(outer_candidates), detail)


__all__ = [
    "SourceCandidateBatch",
    "content_guided_separator_candidate_for_count",
    "safety_outer_proposal_candidates_for_count",
    "separator_source_candidates_for_count",
]
