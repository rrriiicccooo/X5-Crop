from __future__ import annotations

from typing import Any

import numpy as np

from ....cache import AnalysisCache
from ....domain import DetectionCandidate
from ....formats import FormatPhysicalSpec
from ....policies.runtime.policy import DetectionPolicy
from ....run_config import RunConfig
from ...guidance.content_model import content_candidate_proposal_for_count
from ...guidance.content_separator import content_guided_separator_seed_for_count
from ..build.content import build_content_candidate
from ..assessment.count_hypothesis import (
    CountHypothesisEvaluation,
    physical_count_resolution,
)
from ..assessment.source_batch import assess_source_candidates
from .source_candidates import (
    SeparatorOuterCandidatePlan,
    build_separator_candidate_for_outer,
    content_guided_separator_candidate_from_seed,
    separator_extension_outer_plan,
    separator_primary_outer_plan,
)
from ..plan.count_hypotheses import CountHypothesis
from .budget import attach_execution_budget_to_candidates
from ..assessment.reliability import candidate_is_reliable_for_execution_budget, candidate_reliability_detail
from .source_policy import separator_full_width_can_compete
from ..selection.choose import is_partial_occupancy_candidate, select_source_candidate


def _assess_separator_outer_plan(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    offset: float,
    cache: AnalysisCache,
    policy: DetectionPolicy,
    plan: SeparatorOuterCandidatePlan,
    existing_candidates: tuple[DetectionCandidate, ...],
) -> list[DetectionCandidate]:
    assessed: list[DetectionCandidate] = []
    for cohort in plan.cohorts:
        for outer_candidate in cohort.candidates:
            detection = build_separator_candidate_for_outer(
                gray,
                config,
                fmt,
                count,
                strip_mode,
                offset,
                cache,
                policy,
                outer_candidate,
                plan=plan,
                gap_max_width_ratio_override=None,
            )
            assessed.extend(
                assess_source_candidates(
                    gray,
                    (detection,),
                    config,
                    fmt,
                    "separator",
                    cache,
                    policy,
                )
            )
        selected = select_source_candidate([*existing_candidates, *assessed])
        if candidate_is_reliable_for_execution_budget(selected):
            return assessed
    return assessed


def _assessed_candidates_for_offset(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    offset: float,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> list[DetectionCandidate]:
    candidates: list[DetectionCandidate] = []
    explicit_count = bool(config.requested_count is not None)
    full_width_family = policy.outer.proposal.geometry.separator.full_width
    available_physical_families = (
        ["separator_full_width"]
        if full_width_family.available_for(strip_mode, explicit_count)
        else []
    )

    primary_plan = separator_primary_outer_plan(
        gray,
        config,
        fmt,
        count,
        strip_mode,
        cache=cache,
        policy=policy,
    )
    primary_candidates = _assess_separator_outer_plan(
        gray,
        config,
        fmt,
        count,
        strip_mode,
        offset,
        cache,
        policy,
        primary_plan,
        (),
    )
    if not primary_candidates:
        return candidates

    primary_separator = select_source_candidate(primary_candidates)
    primary_reliability = candidate_reliability_detail(primary_separator)
    primary_reliable = candidate_is_reliable_for_execution_budget(primary_separator)
    extension_families: list[str] = []
    separator_candidates = list(primary_candidates)
    separator_candidate = primary_separator
    if not primary_reliable:
        if (
            "separator_full_width" in available_physical_families
            and separator_full_width_can_compete(primary_separator, gray, policy)
        ):
            extension_families.append("separator_full_width")
        if "separator_full_width" in extension_families:
            extension_plan = separator_extension_outer_plan(
                gray,
                config,
                fmt,
                count,
                strip_mode,
                cache=cache,
                policy=policy,
                primary_outer_candidates=primary_plan.comparison_candidates,
            )
            separator_candidates.extend(
                _assess_separator_outer_plan(
                    gray,
                    config,
                    fmt,
                    count,
                    strip_mode,
                    offset,
                    cache,
                    policy,
                    extension_plan,
                    tuple(separator_candidates),
                )
            )
            separator_candidate = select_source_candidate(separator_candidates)
        extension_reliable = candidate_is_reliable_for_execution_budget(separator_candidate)
        if not extension_reliable:
            guidance_seed = content_guided_separator_seed_for_count(
                gray,
                config,
                fmt,
                count,
                strip_mode,
                offset,
                cache,
                policy.content,
                policy.candidate_plan.content_guided_separator,
            )
            if guidance_seed.seed is not None:
                extension_families.append("content_guided_separator")
                content_guided_separator = content_guided_separator_candidate_from_seed(
                    gray,
                    config,
                    fmt,
                    count,
                    strip_mode,
                    offset,
                    seed_result=guidance_seed,
                    cache=cache,
                    policy=policy,
                )
                separator_candidates.extend(
                    assess_source_candidates(
                        gray,
                        (content_guided_separator,),
                        config,
                        fmt,
                        "separator",
                        cache,
                        policy,
                    )
                )
                separator_candidate = select_source_candidate(separator_candidates)

    expanded = bool(extension_families)
    if expanded:
        attach_execution_budget_to_candidates(
            separator_candidates,
            primary_reliability=primary_reliability,
            expanded_after_primary=True,
            extension_families=extension_families,
        )
    else:
        attach_execution_budget_to_candidates(
            separator_candidates,
            primary_reliability=primary_reliability,
            expanded_after_primary=False,
            extension_families=available_physical_families,
            skipped_reason=(
                "reliable_primary"
                if primary_reliable
                else "no_applicable_extension_families"
            ),
        )

    candidates.extend(separator_candidates)
    separator_support_candidate = separator_candidate
    separator_assessment = separator_candidate.detail.get("candidate_assessment", {})
    separator_assessment = (
        dict(separator_assessment) if isinstance(separator_assessment, dict) else {}
    )
    separator_candidate_gate = separator_assessment.get("candidate_gate")
    separator_candidate_gate = (
        dict(separator_candidate_gate) if isinstance(separator_candidate_gate, dict) else {}
    )
    separator_candidate_passed = bool(separator_candidate_gate.get("passed", False))
    if is_partial_occupancy_candidate(separator_support_candidate):
        return candidates
    if (
        strip_mode == "full"
        and separator_candidate_passed
    ):
        return candidates
    content_proposal = content_candidate_proposal_for_count(
        gray,
        config.layout,
        fmt,
        count,
        strip_mode,
        offset,
        cache=cache,
        content_policy=policy.content,
    )
    if content_proposal is not None:
        content = build_content_candidate(
            content_proposal,
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset,
        )
        candidates.extend(
            assess_source_candidates(
                gray,
                (content,),
                config,
                fmt,
                "content",
                cache,
                policy,
            )
        )
    return candidates


def evaluate_count_hypothesis(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    hypothesis: CountHypothesis,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> CountHypothesisEvaluation:
    candidates: list[DetectionCandidate] = []
    resolved_offsets: list[float] = []
    count_resolved = False
    placement_resolved = False
    candidate_auto_ready = False
    resolution_checks: list[dict[str, Any]] = []
    for offset in hypothesis.offsets:
        offset_candidates = _assessed_candidates_for_offset(
            gray,
            config,
            fmt,
            hypothesis.count,
            hypothesis.strip_mode,
            offset,
            cache,
            policy,
        )
        candidates.extend(offset_candidates)
        for candidate in offset_candidates:
            plan_detail = candidate.detail.setdefault("candidate_plan", {})
            if isinstance(plan_detail, dict):
                plan_detail["count_hypothesis"] = hypothesis.report_detail()
        if not offset_candidates:
            continue
        selected = select_source_candidate(offset_candidates)
        resolution = physical_count_resolution(selected, hypothesis)
        resolution_checks.append(
            {"offset": float(offset), **resolution.report_detail()}
        )
        count_resolved = count_resolved or resolution.count_resolved
        placement_resolved = placement_resolved or resolution.placement_resolved
        candidate_auto_ready = candidate_auto_ready or candidate_is_reliable_for_execution_budget(selected)
        if resolution.placement_resolved:
            resolved_offsets.append(float(offset))
        if resolution.placement_resolved or candidate_auto_ready:
            break
    return CountHypothesisEvaluation(
        hypothesis=hypothesis,
        candidates=tuple(candidates),
        count_resolved=bool(count_resolved),
        placement_resolved=bool(placement_resolved),
        candidate_auto_ready=bool(candidate_auto_ready),
        resolved_offsets=tuple(resolved_offsets),
        resolution_checks=tuple(resolution_checks),
    )
