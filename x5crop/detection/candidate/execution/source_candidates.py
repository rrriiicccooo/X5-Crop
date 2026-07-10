from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np

from ....constants import CANDIDATE_SOURCE_SEPARATOR
from ....cache import AnalysisCache
from ....domain import DetectionCandidate, OuterCandidate
from ....formats import FormatPhysicalSpec
from ....geometry.layout import work_gray
from ....policies.runtime.policy import DetectionPolicy
from ....run_config import RunConfig
from ...guidance.content_separator import ContentGuidedSeparatorSeedResult
from ...physical.outer.common import unique_outer_candidates
from ...physical.outer.separator import (
    FULL_WIDTH_SEPARATOR_OUTER,
    separator_derived_outer_candidates,
)
from ...physical.separator.proposal import separator_gap_search_detail
from ..proposal.outer import (
    outer_proposal_candidates,
    separator_sequence_rank,
)
from .source_policy import separator_outer_gap_max_width_override
from ..build.detection import build_detection_geometry_for_outer, enrich_detection_geometry_evidence


@dataclass(frozen=True)
class OuterCandidateCohort:
    name: str
    candidates: tuple[OuterCandidate, ...]


@dataclass(frozen=True)
class SeparatorOuterCandidatePlan:
    cohorts: tuple[OuterCandidateCohort, ...]
    comparison_candidates: tuple[OuterCandidate, ...]
    detail: dict


def _attach_holder_reference(
    detection: DetectionCandidate,
    outer_candidates: list[OuterCandidate],
) -> None:
    holder_candidates = [
        candidate.box
        for candidate in outer_candidates
        if candidate.box.valid()
        and candidate.strategy == "base_outer"
    ]
    if holder_candidates:
        holder_outer = max(holder_candidates, key=lambda box: box.width * box.height)
        detection.detail["holder_reference_outer_box"] = asdict(holder_outer)


def build_separator_candidate_for_outer(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
    candidate: OuterCandidate,
    *,
    plan: SeparatorOuterCandidatePlan,
    gap_max_width_ratio_override: Optional[float],
) -> DetectionCandidate:
    candidate_gap_override = gap_max_width_ratio_override
    if candidate.strategy == "separator_outer":
        candidate_gap_override = separator_outer_gap_max_width_override(policy, candidate_gap_override)
    detection = build_detection_geometry_for_outer(
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
    detection = enrich_detection_geometry_evidence(gray, detection, config, fmt, cache, policy=policy)
    detection.detail["separator_gap_search"] = separator_gap_search_detail(
        policy.separator.width_profile
    )
    _attach_holder_reference(
        detection,
        list(plan.comparison_candidates),
    )
    detection.detail["candidate_plan"] = dict(plan.detail)
    return detection


def _outer_candidate_plan(
    outer_candidates: list[OuterCandidate],
    comparison_candidates: list[OuterCandidate],
    detail: dict,
    *,
    physical_primary_candidate_count: int,
) -> SeparatorOuterCandidatePlan:
    separator = [candidate for candidate in outer_candidates if candidate.strategy == "separator_outer"]
    primary_count = max(1, int(physical_primary_candidate_count))
    base = [candidate for candidate in outer_candidates if candidate.strategy == "base_outer"]
    guidance = [
        candidate
        for candidate in outer_candidates
        if candidate.strategy not in {"separator_outer", "base_outer"}
    ]
    cohorts = (
        OuterCandidateCohort("separator_geometry_primary", tuple(separator[:primary_count])),
        OuterCandidateCohort("base_geometry_primary", tuple(base[:primary_count])),
        OuterCandidateCohort("separator_geometry_secondary", tuple(separator[primary_count:])),
        OuterCandidateCohort("base_geometry_secondary", tuple(base[primary_count:])),
        OuterCandidateCohort("content_guidance_primary", tuple(guidance[:primary_count])),
        OuterCandidateCohort("content_guidance_secondary", tuple(guidance[primary_count:])),
    )
    active_cohorts = tuple(cohort for cohort in cohorts if cohort.candidates)
    detail = {
        **detail,
        "outer_candidate_cohorts": [
            {"name": cohort.name, "candidate_count": len(cohort.candidates)}
            for cohort in active_cohorts
        ],
    }
    return SeparatorOuterCandidatePlan(
        cohorts=active_cohorts,
        comparison_candidates=tuple(comparison_candidates),
        detail=detail,
    )


def separator_primary_outer_plan(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    *,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> SeparatorOuterCandidatePlan:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    explicit_count = bool(config.requested_count is not None)
    outer_candidates = outer_proposal_candidates(
        gray_work,
        fmt,
        count,
        strip_mode,
        cache,
        policy=policy,
        explicit_count=explicit_count,
    )
    detail = {
        "source": CANDIDATE_SOURCE_SEPARATOR,
        "count_explicit": bool(explicit_count),
        "outer_execution_stage": "primary",
        "separator_gap_search": separator_gap_search_detail(
            policy.separator.width_profile
        ),
        "outer_candidate_count": int(len(outer_candidates)),
        "separator_full_width_included": False,
        "width_aware_proposal": True,
    }
    return _outer_candidate_plan(
        outer_candidates,
        outer_candidates,
        detail,
        physical_primary_candidate_count=(
            policy.candidate_plan.execution_budget.physical_primary_candidate_count
        ),
    )


def separator_extension_outer_plan(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    *,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
    primary_outer_candidates: tuple[OuterCandidate, ...],
) -> SeparatorOuterCandidatePlan:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    explicit_count = bool(config.requested_count is not None)
    family = policy.outer.proposal.geometry.separator.full_width
    eligible = bool(
        family.available_for(strip_mode, explicit_count)
        and family.mode in {"always", "conditional"}
    )
    extension_outer_candidates: list[OuterCandidate] = []
    if eligible:
        proposed = separator_derived_outer_candidates(
            gray_work,
            list(primary_outer_candidates),
            fmt,
            count,
            strip_mode,
            cache,
            separator_geometry_policy=policy.outer.proposal.geometry.separator,
            separator_policy=policy.separator,
            outer_scopes=(FULL_WIDTH_SEPARATOR_OUTER,),
            explicit_count=explicit_count,
            sequence_ranker=separator_sequence_rank,
        )
        primary_boxes = {candidate.box for candidate in primary_outer_candidates}
        extension_outer_candidates = [
            candidate for candidate in proposed if candidate.box not in primary_boxes
        ]
    all_outer_candidates = unique_outer_candidates(
        [*primary_outer_candidates, *extension_outer_candidates]
    )
    detail = {
        "source": CANDIDATE_SOURCE_SEPARATOR,
        "count_explicit": bool(explicit_count),
        "outer_execution_stage": "extension",
        "separator_gap_search": separator_gap_search_detail(policy.separator.width_profile),
        "outer_candidate_count": int(len(extension_outer_candidates)),
        "separator_full_width_eligible": eligible,
        "separator_full_width_included": bool(extension_outer_candidates),
        "width_aware_proposal": True,
    }
    return _outer_candidate_plan(
        extension_outer_candidates,
        all_outer_candidates,
        detail,
        physical_primary_candidate_count=(
            policy.candidate_plan.execution_budget.physical_primary_candidate_count
        ),
    )


def content_guided_separator_candidate_from_seed(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    *,
    seed_result: ContentGuidedSeparatorSeedResult,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> DetectionCandidate:
    if seed_result.seed is None:
        raise ValueError("content-guided separator candidate requires a seed")

    detection = build_detection_geometry_for_outer(
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
        separator_gap_hints=seed_result.seed.gap_hints,
        policy=policy,
    )
    detection = enrich_detection_geometry_evidence(gray, detection, config, fmt, cache, policy=policy)
    detection.detail["separator_gap_search"] = separator_gap_search_detail(
        policy.separator.width_profile
    )
    detection.detail["candidate_source"] = CANDIDATE_SOURCE_SEPARATOR
    detection.detail["content_guided_separator"] = seed_result.seed.detail
    detection.detail["candidate_plan"] = {
        "source": "content_guided_separator",
        "source_candidate": CANDIDATE_SOURCE_SEPARATOR,
        "proposal_family": "content_guided_separator",
        "content_seeded": True,
        "evidence_contract": "separator_evidence_required",
        "separator_gap_search": separator_gap_search_detail(
            policy.separator.width_profile
        ),
        "content_guidance": seed_result.seed.gap_hints.summary(),
    }
    return detection
