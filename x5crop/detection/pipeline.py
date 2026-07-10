from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..runtime.config import RuntimeConfig
from ..domain import DetectionCandidate
from ..formats import FormatPhysicalSpec
from ..cache.analysis import make_analysis_cache
from ..policies.runtime.bundle import DetectionPolicyBundle
from ..policies.runtime.policy import DetectionPolicy
from ..cache import AnalysisCache
from .candidate.execution.count_hypothesis import evaluate_count_hypothesis
from .candidate.plan.count_hypotheses import count_hypothesis_plan
from .modes.dual_lane import choose_dual_lane_detection
from .modes.review_only import review_only_detection
from .candidate.proposal.safety import hard_safety_detection
from .candidate.selection.choose import select_detection_candidate
from .candidate.selection.count_hypothesis import count_selection_detail
from .candidate.extension.outer_correction import outer_correction_candidate_extensions


@dataclass(frozen=True)
class CandidatePipelineResult:
    candidate: DetectionCandidate
    policy: DetectionPolicy


def _attach_runtime_policy_detail(detection: DetectionCandidate, policy) -> None:
    detection.detail["runtime_policy_detail"] = policy.report_detail()


def choose_detection(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatPhysicalSpec,
    policy_bundle: DetectionPolicyBundle,
    cache: Optional[AnalysisCache] = None,
) -> CandidatePipelineResult:
    candidates: list[DetectionCandidate] = []
    policy = policy_bundle.policy_for(fmt.name, config.strip_mode)
    cache = (
        cache
        if cache is not None and cache.layout == config.layout
        else make_analysis_cache(gray, config.layout, policy.preprocess.content_evidence_image)
    )
    if policy.detector.kind == "dual_lane":
        candidate = choose_dual_lane_detection(gray, config, cache, policy, policy_bundle)
        _attach_runtime_policy_detail(candidate, policy)
        return CandidatePipelineResult(candidate=candidate, policy=policy)
    if policy.detector.kind == "review_only":
        candidate = review_only_detection(gray, config, fmt, policy)
        _attach_runtime_policy_detail(candidate, policy)
        return CandidatePipelineResult(candidate=candidate, policy=policy)
    count_plan = count_hypothesis_plan(
        strip_mode=config.strip_mode,
        requested_count=config.requested_count,
        fmt=fmt,
        policy=policy.count_hypotheses,
    )
    count_evaluations = []
    for hypothesis in count_plan.hypotheses:
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
        if count_plan.automatic and evaluation.search_satisfied:
            break

    if not candidates:
        candidate = hard_safety_detection(gray, config, fmt, count_plan.fallback_count)
        candidate.detail["count_selection"] = count_selection_detail(
            candidate,
            count_plan,
            count_evaluations,
        )
        _attach_runtime_policy_detail(candidate, policy)
        return CandidatePipelineResult(candidate=candidate, policy=policy)

    provisional = select_detection_candidate(
        candidates,
        fmt,
        config.confidence_threshold,
        policy.candidate_selection,
    )
    extension_policy = policy_bundle.policy_for(provisional.film_format, provisional.strip_mode)
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
        selected_candidate.film_format,
        selected_candidate.strip_mode,
    )
    selected_candidate.detail["count_selection"] = count_selection_detail(
        selected_candidate,
        count_plan,
        count_evaluations,
    )
    _attach_runtime_policy_detail(selected_candidate, selected_policy)
    return CandidatePipelineResult(candidate=selected_candidate, policy=selected_policy)
