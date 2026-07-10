from __future__ import annotations

import numpy as np

from ....constants import CANDIDATE_SOURCE_SAFETY
from ....cache import AnalysisCache
from ....domain import DetectionCandidate
from ....formats import FormatPhysicalSpec
from ....policies.runtime.policy import DetectionPolicy
from ....run_config import RunConfig
from ...guidance.content_model import content_detection_for_count
from ..assessment.count_hypothesis import CountHypothesisEvaluation
from ..assessment.safety import apply_safety_candidate_assessment
from ..assessment.source_batch import assess_source_candidates
from .source_candidates import (
    content_guided_separator_candidate_for_count,
    safety_outer_proposal_candidates_for_count,
    separator_source_candidates_for_count,
)
from ..plan.count_hypotheses import CountHypothesis
from ..plan.execution_budget import (
    attach_execution_budget_to_candidates,
    separator_extension_families,
    set_execution_budget_detail,
)
from ..plan.reliability import candidate_is_reliable_for_execution_budget, candidate_reliability_detail
from ..plan.source_policy import safety_candidate_outer_proposals_enabled, separator_full_width_can_compete
from ..selection.choose import is_partial_edge_safety_candidate, select_source_candidate


def _assessed_candidates_for_offset(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    offset: float,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> tuple[list[DetectionCandidate], bool]:
    content_policy = policy.candidate_plan.content_candidate
    candidates: list[DetectionCandidate] = []
    stop_after_this_count = False
    explicit_count = bool(config.requested_count is not None)
    extension_families = separator_extension_families(policy, strip_mode, explicit_count)

    primary_batch = separator_source_candidates_for_count(
        gray,
        config,
        fmt,
        count,
        strip_mode,
        offset,
        cache,
        policy=policy,
        include_extension_outer=False,
        include_supplemental_outer=False,
    )
    primary_candidates = assess_source_candidates(
        gray,
        primary_batch.detections,
        config,
        fmt,
        "separator",
        cache,
        policy,
    )
    if not primary_candidates:
        return candidates, stop_after_this_count

    primary_separator = select_source_candidate(primary_candidates, config.confidence_threshold)
    primary_reliability = candidate_reliability_detail(
        primary_separator,
        config.confidence_threshold,
        policy,
    )
    primary_reliable = candidate_is_reliable_for_execution_budget(
        primary_separator,
        config.confidence_threshold,
        policy,
    )
    primary_can_skip_extensions = (
        primary_reliable
        or not extension_families
        or (
            "separator_full_width" in extension_families
            and not separator_full_width_can_compete(primary_separator, gray, policy)
            and "content_guided_separator" not in extension_families
        )
    )
    if primary_can_skip_extensions:
        separator_candidates = primary_candidates
        separator_candidate = primary_separator
        skipped_reason = "reliable_primary" if primary_reliable else "no_extension_families"
        attach_execution_budget_to_candidates(
            separator_candidates,
            primary_reliability=primary_reliability,
            expanded_after_primary=False,
            extension_families=extension_families,
            skipped_reason=skipped_reason,
        )
    else:
        expanded_batch = separator_source_candidates_for_count(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset,
            cache,
            policy=policy,
        )
        separator_candidates = assess_source_candidates(
            gray,
            expanded_batch.detections,
            config,
            fmt,
            "separator",
            cache,
            policy,
        )
        if not separator_candidates:
            separator_candidates = primary_candidates
        separator_candidate = select_source_candidate(separator_candidates, config.confidence_threshold)
        attach_execution_budget_to_candidates(
            separator_candidates,
            primary_reliability=primary_reliability,
            expanded_after_primary=True,
            extension_families=extension_families,
        )
        if "content_guided_separator" in extension_families:
            content_guided_separator, guidance_detail = content_guided_separator_candidate_for_count(
                gray,
                config,
                fmt,
                count,
                strip_mode,
                offset,
                cache,
                policy=policy,
            )
            if content_guided_separator is None:
                separator_candidate.detail.setdefault("candidate_plan", {})[
                    "content_guided_separator"
                ] = guidance_detail
            else:
                content_guided_candidate = assess_source_candidates(
                    gray,
                    (content_guided_separator,),
                    config,
                    fmt,
                    "separator",
                    cache,
                    policy,
                )[0]
                set_execution_budget_detail(
                    content_guided_candidate,
                    primary_reliability=primary_reliability,
                    expanded_after_primary=True,
                    extension_families=extension_families,
                )
                separator_candidates.append(content_guided_candidate)

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
    if safety_candidate_outer_proposals_enabled(policy):
        safety_batch = safety_outer_proposal_candidates_for_count(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset,
            cache,
            policy=policy,
        )
        safety_candidates = assess_source_candidates(
            gray,
            safety_batch.detections,
            config,
            fmt,
            CANDIDATE_SOURCE_SAFETY,
            cache,
            policy,
        )
        for safety_candidate in safety_candidates:
            apply_safety_candidate_assessment(
                safety_candidate,
                confidence_threshold=config.confidence_threshold,
                policy=policy,
            )
        candidates.extend(safety_candidates)
    partial_edge_safety_candidate = is_partial_edge_safety_candidate(
        separator_support_candidate,
        config.confidence_threshold,
    )
    if partial_edge_safety_candidate and policy.candidate_plan.partial_stop.stop_after_safe_candidate:
        stop_after_this_count = True
    if (
        content_policy.skip_after_reliable_separator_candidate
        and strip_mode in content_policy.reliable_separator_candidate_skip_strip_modes
        and separator_candidate_passed
        and separator_support_candidate.confidence >= config.confidence_threshold
    ):
        separator_support_candidate.detail["content_candidate_skipped"] = (
            content_policy.reliable_separator_candidate_skip_reason
        )
        return candidates, stop_after_this_count
    if (
        policy.candidate_plan.partial_stop.skip_content_after_safe_candidate
        and strip_mode in policy.candidate_plan.partial_stop.skip_content_after_safe_candidate_strip_modes
        and partial_edge_safety_candidate
    ):
        separator_support_candidate.detail["content_candidate_skipped"] = (
            policy.candidate_plan.partial_stop.skip_content_after_safe_candidate_reason
        )
        return candidates, stop_after_this_count
    if not content_policy.enabled:
        separator_support_candidate.detail["content_candidate_skipped"] = content_policy.disabled_skip_reason
        return candidates, stop_after_this_count
    content = content_detection_for_count(
        gray,
        config,
        fmt,
        count,
        strip_mode,
        offset,
        cache,
        content_policy=policy.content,
    )
    if content is not None:
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
    return candidates, stop_after_this_count


def evaluate_count_hypothesis(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    hypothesis: CountHypothesis,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> CountHypothesisEvaluation:
    candidates: list[DetectionCandidate] = []
    supporting_offsets: list[float] = []
    for offset in hypothesis.offsets:
        offset_candidates, supported = _assessed_candidates_for_offset(
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
        if supported:
            supporting_offsets.append(float(offset))
    return CountHypothesisEvaluation(
        hypothesis=hypothesis,
        candidates=tuple(candidates),
        search_satisfied=bool(supporting_offsets),
        supporting_offsets=tuple(supporting_offsets),
    )


__all__ = [
    "evaluate_count_hypothesis",
]
