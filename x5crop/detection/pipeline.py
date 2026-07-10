from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..run_config import RunConfig
from ..domain import DetectionCandidate
from ..formats import FormatPhysicalSpec
from ..policies.runtime.bundle import DetectionPolicyBundle
from ..policies.runtime.policy import DetectionPolicy
from ..cache import AnalysisCache
from .candidate.execution.count_hypothesis import evaluate_count_hypothesis
from .candidate.execution.count_placement import resolve_automatic_count_placement
from .candidate.plan.count_hypotheses import count_hypothesis_plan
from .modes.dual_lane import choose_dual_lane_detection
from .modes.review_only import review_only_detection
from .candidate.proposal.hard_safety import hard_safety_detection
from .candidate.selection.choose import select_detection_candidate
from .candidate.selection.count_hypothesis import count_selection_detail
from .evidence.count_planning import CountPlanningEvidence, count_planning_evidence
from .candidate.extension.outer_correction import outer_correction_candidate_extensions


@dataclass(frozen=True)
class CandidatePipelineResult:
    candidate: DetectionCandidate
    policy: DetectionPolicy


def choose_detection(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    policy_bundle: DetectionPolicyBundle,
    cache: AnalysisCache,
) -> CandidatePipelineResult:
    candidates: list[DetectionCandidate] = []
    policy = policy_bundle.policy_for(fmt.format_id, config.strip_mode)
    if cache.layout != config.layout:
        raise ValueError("Analysis cache layout does not match runtime layout")
    if policy.detector_kind == "dual_lane":
        candidate = choose_dual_lane_detection(gray, config, cache, policy, policy_bundle)
        candidate = select_detection_candidate(
            [candidate],
            fmt,
            config.confidence_threshold,
            policy.candidate_selection,
        )
        return CandidatePipelineResult(candidate=candidate, policy=policy)
    if policy.detector_kind == "review_only":
        candidate = review_only_detection(gray, config, fmt)
        candidate = select_detection_candidate(
            [candidate],
            fmt,
            config.confidence_threshold,
            policy.candidate_selection,
        )
        return CandidatePipelineResult(candidate=candidate, policy=policy)
    planning_evidence = (
        count_planning_evidence(
            cache.gray_work,
            fmt,
            cache,
            outer_parameters=policy.outer.proposal.base,
            separator_profile_parameters=policy.separator.profile,
            gap_search_parameters=policy.separator.gap_search,
            separator_band_parameters=policy.outer.proposal.geometry.separator.band,
        )
        if config.strip_mode == "partial" and config.requested_count is None
        else CountPlanningEvidence.unavailable()
    )
    count_plan = count_hypothesis_plan(
        strip_mode=config.strip_mode,
        requested_count=config.requested_count,
        fmt=fmt,
        partial_offsets=policy.partial_count_offsets,
        planning_evidence=planning_evidence,
    )
    count_evaluations = []
    for hypothesis in count_plan.hypotheses:
        count_plan, hypothesis = resolve_automatic_count_placement(
            count_plan,
            hypothesis,
            cache,
            fmt,
            policy,
        )
        evaluation = evaluate_count_hypothesis(
            gray,
            config,
            fmt,
            hypothesis,
            cache,
            policy,
        )
        count_evaluations.append(evaluation)
        candidates.extend(evaluation.candidates)
        if count_plan.automatic and evaluation.count_resolved:
            break

    if not candidates:
        candidate = hard_safety_detection(
            gray,
            config,
            fmt,
            count_plan.hard_safety_count,
            policy.frame_fit,
        )
        candidate.detail["count_selection"] = count_selection_detail(
            candidate,
            count_plan,
            count_evaluations,
        )
        return CandidatePipelineResult(candidate=candidate, policy=policy)

    provisional = select_detection_candidate(
        candidates,
        fmt,
        config.confidence_threshold,
        policy.candidate_selection,
    )
    extension_policy = policy_bundle.policy_for(provisional.format_id, provisional.strip_mode)
    extension_candidates = outer_correction_candidate_extensions(
        gray,
        config,
        fmt,
        provisional,
        cache,
        extension_policy,
    )
    if extension_candidates:
        candidates.extend(extension_candidates)
    selected_candidate = select_detection_candidate(
        candidates,
        fmt,
        config.confidence_threshold,
        extension_policy.candidate_selection,
    )
    selected_policy = policy_bundle.policy_for(
        selected_candidate.format_id,
        selected_candidate.strip_mode,
    )
    selected_candidate.detail["count_selection"] = count_selection_detail(
        selected_candidate,
        count_plan,
        count_evaluations,
    )
    return CandidatePipelineResult(candidate=selected_candidate, policy=selected_policy)
