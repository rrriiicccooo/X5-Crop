from __future__ import annotations

from typing import Any

import numpy as np

from ....constants import CANDIDATE_SOURCE_HARD_SAFETY
from ....domain import Detection
from ....formats import FormatSpec
from ....policies.runtime.policy import DetectionPolicy
from ....policies.runtime.outer import OuterCorrectionFamilyPolicy
from ....cache import AnalysisCache
from ....runtime.config import RuntimeConfig
from ...evidence.content.frame_support import content_evidence_detail
from ...evidence.outer_alignment import outer_content_alignment_detail
from .corrected_outer import build_assessed_corrected_outer_candidate
from ..plan.reliability import candidate_is_reliable_for_execution_budget, candidate_reliability_detail
from ...physical.outer.correction.content_containment import content_containment_correction_proposal
from ...physical.outer.correction.geometry import geometry_consistency_correction_proposal, geometry_consistency_model_detail


def _candidate_assessment_detail(detection: Detection) -> dict[str, Any]:
    assessment = detection.detail.get("candidate_assessment", {})
    return dict(assessment) if isinstance(assessment, dict) else {}


def _candidate_is_separator_assessed(detection: Detection) -> bool:
    return _candidate_assessment_detail(detection).get("source") == "separator"


def _candidate_separator_support_ok(detection: Detection) -> bool:
    hard_detail = _candidate_assessment_detail(detection).get("separator_support", {})
    return isinstance(hard_detail, dict) and bool(hard_detail.get("ok", False))


def _correction_skip_reason(
    name: str,
    family: OuterCorrectionFamilyPolicy,
    detection: Detection,
    explicit_count: bool,
) -> str | None:
    if family.mode == "off":
        return "mode_off"
    if detection.strip_mode not in family.strip_modes:
        return "strip_mode_not_enabled"
    if detection.strip_mode == "partial" and family.requires_explicit_count_for_partial and not explicit_count:
        return "partial_requires_explicit_count"
    if family.requires_separator_assessment and not _candidate_is_separator_assessed(detection):
        return "requires_separator_assessment"
    if name == "short_axis_geometry" and not _candidate_separator_support_ok(detection):
        return "requires_separator_support"
    return None


def _correction_family_eligible_for_candidate(
    name: str,
    family: OuterCorrectionFamilyPolicy,
    detection: Detection,
    explicit_count: bool,
) -> bool:
    return _correction_skip_reason(name, family, detection, explicit_count) is None


def _outer_correction_plan_detail(
    detection: Detection,
    policy: DetectionPolicy,
    explicit_count: bool,
) -> dict[str, Any]:
    correction = policy.outer.correction
    families = {
        "long_axis_geometry": correction.geometry_consistency.long_axis.family,
        "short_axis_geometry": correction.geometry_consistency.short_axis.family,
        "content_containment": correction.content_containment.family,
    }
    eligible = [
        name
        for name, family in families.items()
        if _correction_family_eligible_for_candidate(name, family, detection, explicit_count)
    ]
    skipped = {
        name: reason
        for name, family in families.items()
        if (reason := _correction_skip_reason(name, family, detection, explicit_count)) is not None
    }
    return {
        "count_explicit": bool(explicit_count),
        "eligibility_owner": "candidate.extension",
        "eligible_families": eligible,
        "skipped_reasons": skipped,
    }


def _outer_correction_budget_reason(
    *,
    skip_after_reliable_selection: bool,
    reliable_selection: bool,
    outer_alignment_ok: bool,
) -> str:
    if not skip_after_reliable_selection:
        return "skip_after_reliable_selection_disabled"
    if not reliable_selection:
        return "selection_not_reliable"
    if not outer_alignment_ok:
        return "outer_alignment_conflict"
    return "reliable_selection"


def outer_correction_candidate_extensions(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> list[Detection]:
    if detection.detail.get("candidate_source") == CANDIDATE_SOURCE_HARD_SAFETY:
        return []
    if not bool(policy.candidate_plan.outer_correction_extension.enabled):
        return []
    explicit_count = bool(config.count_override is not None)
    correction_plan = _outer_correction_plan_detail(detection, policy, explicit_count)
    detection.detail["outer_correction_candidate_plan"] = correction_plan
    if not correction_plan["eligible_families"]:
        return []

    content_detail = content_evidence_detail(
        gray,
        detection,
        cache,
        content_policy=policy.content,
    )
    detection.detail["content_evidence"] = content_detail
    outer_alignment = (
        outer_content_alignment_detail(gray, detection, cache, policy=policy)
        if policy.decision.align_outer_to_content
        else {"used": False, "reason": policy.decision.outer_alignment_disabled_reason}
    )
    detection.detail["outer_content_alignment"] = outer_alignment
    reliable_selection = candidate_is_reliable_for_execution_budget(detection, config.confidence_threshold, policy)
    outer_alignment_ok = (not bool(outer_alignment.get("used", False))) or bool(outer_alignment.get("ok", True))
    skip_after_reliable_selection = bool(
        policy.candidate_plan.execution_budget.skip_outer_correction_after_reliable_selection
    )
    correction_plan["reliable_selection"] = bool(reliable_selection)
    correction_plan["outer_alignment_ok"] = bool(outer_alignment_ok)
    budget_reason = _outer_correction_budget_reason(
        skip_after_reliable_selection=skip_after_reliable_selection,
        reliable_selection=bool(reliable_selection),
        outer_alignment_ok=bool(outer_alignment_ok),
    )
    should_skip_correction = skip_after_reliable_selection and reliable_selection and outer_alignment_ok
    correction_plan["execution_budget"] = {
        "stage": "selected_candidate",
        "action": "skip_outer_correction_candidates" if should_skip_correction else "run_outer_correction_candidates",
        "reason": budget_reason,
        "reliable_selection": bool(reliable_selection),
        "outer_alignment_ok": bool(outer_alignment_ok),
    }
    if should_skip_correction:
        correction_plan["skipped_due_to_reliable_selection"] = True
        correction_plan["reliability"] = candidate_reliability_detail(
            detection,
            config.confidence_threshold,
            policy,
        )
        correction_plan["skipped_reasons"] = {
            **correction_plan.get("skipped_reasons", {}),
            "outer_correction_candidate": "reliable_selection",
        }
        return []

    extensions: list[Detection] = []
    proposal = geometry_consistency_correction_proposal(
        gray,
        config,
        fmt,
        detection,
        content_detail,
        outer_alignment,
        cache,
        set(correction_plan["eligible_families"]),
        policy,
    )
    if proposal is not None:
        reassessed = build_assessed_corrected_outer_candidate(gray, config, fmt, detection, proposal, cache, policy)
        if "source_geometry_consistency" in proposal.detail:
            reassessed_geometry = geometry_consistency_model_detail(gray, reassessed, config, fmt, cache)
            reassessed.detail["geometry_consistency_model"] = reassessed_geometry
            reassessed.detail["outer_correction"]["reassessed_geometry_consistency"] = reassessed_geometry
        reassessed.detail["candidate_plan"] = {
            "source": "outer_correction_candidate",
            "extension_of": detection.detail.get("candidate_plan", {}),
            "outer_correction": {
                **correction_plan,
                "attempted_family": f"{proposal.detail.get('correction_kind', 'unknown')}_geometry",
                "correction_order": "geometry_consistency",
            },
        }
        extensions.append(reassessed)
        return extensions

    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        proposal = content_containment_correction_proposal(
            config,
            fmt,
            detection,
            outer_alignment,
            cache,
            set(correction_plan["eligible_families"]),
            policy,
        )
        if proposal is not None:
            reassessed = build_assessed_corrected_outer_candidate(gray, config, fmt, detection, proposal, cache, policy)
            reassessed.detail["candidate_plan"] = {
                "source": "outer_correction_candidate",
                "extension_of": detection.detail.get("candidate_plan", {}),
                "outer_correction": {
                    **correction_plan,
                    "attempted_family": "content_containment",
                    "correction_order": "content_containment",
                },
            }
            extensions.append(reassessed)
            return extensions
        detection.detail["outer_correction"] = {
            "used": False,
            "reason": "no_valid_content_containment_correction",
        }

    return extensions


__all__ = ["outer_correction_candidate_extensions"]
