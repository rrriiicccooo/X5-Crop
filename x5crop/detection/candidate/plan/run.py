from __future__ import annotations

from typing import Optional

import numpy as np

from ....domain import Detection
from ....formats import FormatSpec
from ....policies.registry import get_detection_policy
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....runtime.config import RuntimeConfig
from ...guidance.content_model import content_detection_for_count
from ..assessment.candidate import apply_candidate_assessment_policy
from .reliability import candidate_is_reliable_for_execution_budget, candidate_reliability_detail
from ..selection.choose import is_partial_safe_auto_candidate
from .source_policy import safety_candidate_outer_proposals_enabled
from .sources import (
    detect_candidate_for_count,
    detect_content_guided_separator_candidate_for_count,
    detect_safety_outer_proposal_candidate_for_count,
)


def _separator_extension_families(
    policy: DetectionPolicy,
    strip_mode: str,
    count: int,
    fmt: FormatSpec,
    explicit_count: bool,
) -> list[str]:
    separator_policy = policy.outer.proposal.geometry.separator
    families: list[str] = []
    if separator_policy.full_width.available_for(strip_mode, explicit_count):
        families.append("separator_full_width")
    if policy.candidate_plan.content_guided_separator.available_for(strip_mode):
        families.append("content_guided_separator")
    return families


def _set_execution_budget_detail(
    detection: Detection,
    *,
    primary_reliability: dict,
    expanded_after_primary: bool,
    extension_families: list[str],
    skipped_reason: str | None = None,
) -> None:
    plan = detection.detail.setdefault("candidate_plan", {})
    if not isinstance(plan, dict):
        plan = {}
        detection.detail["candidate_plan"] = plan
    expanded = bool(expanded_after_primary)
    primary_reliable = bool(primary_reliability.get("reliable", False))
    action = "run_extension_candidates" if expanded else "skip_extension_candidates"
    reason = "primary_not_reliable" if expanded else (skipped_reason or "no_extension_families")
    detail = {
        "stage": "expanded_after_primary" if expanded else "primary_only",
        "action": action,
        "reason": reason,
        "primary_reliable": primary_reliable,
        "primary_reliability": primary_reliability,
        "expanded_after_primary": expanded,
        "extension_families": list(extension_families),
    }
    if skipped_reason is not None:
        detail["skipped_extension_families"] = list(extension_families)
        detail["skipped_reason"] = skipped_reason
    plan["execution_budget"] = detail


def calibrated_candidates_for_count(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    offset: float,
    cache: AnalysisCache,
    policy: Optional[DetectionPolicy] = None,
) -> tuple[list[Detection], bool]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    content_policy = policy.candidate_plan.content_candidate
    candidates: list[Detection] = []
    stop_after_this_count = False
    explicit_count = bool(config.count_override is not None)
    extension_families = _separator_extension_families(policy, strip_mode, count, fmt, explicit_count)
    primary_separator = detect_candidate_for_count(
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
    primary_candidate = apply_candidate_assessment_policy(
        gray,
        primary_separator,
        config,
        fmt,
        "separator",
        cache,
        policy=policy,
    )
    primary_reliability = candidate_reliability_detail(
        primary_candidate,
        config.confidence_threshold,
        policy,
    )
    if (
        extension_families
        and not candidate_is_reliable_for_execution_budget(primary_candidate, config.confidence_threshold, policy)
    ):
        separator = detect_candidate_for_count(gray, config, fmt, count, strip_mode, offset, cache, policy=policy)
        separator_candidate = apply_candidate_assessment_policy(
            gray,
            separator,
            config,
            fmt,
            "separator",
            cache,
            policy=policy,
        )
        _set_execution_budget_detail(
            separator_candidate,
            primary_reliability=primary_reliability,
            expanded_after_primary=True,
            extension_families=extension_families,
        )
        if "content_guided_separator" in extension_families:
            content_guided_separator, guidance_detail = detect_content_guided_separator_candidate_for_count(
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
                content_guided_candidate = apply_candidate_assessment_policy(
                    gray,
                    content_guided_separator,
                    config,
                    fmt,
                    "separator",
                    cache,
                    policy=policy,
                )
                content_guided_candidate.detail.setdefault("candidate_plan", {})[
                    "execution_budget"
                ] = {
                    "stage": "expanded_after_primary",
                    "action": "run_extension_candidates",
                    "reason": "primary_not_reliable",
                    "primary_reliable": bool(primary_reliability.get("reliable", False)),
                    "primary_reliability": primary_reliability,
                    "expanded_after_primary": True,
                    "extension_families": list(extension_families),
                }
                candidates.append(content_guided_candidate)
    else:
        separator_candidate = primary_candidate
        skipped_reason = "reliable_primary" if extension_families else "no_extension_families"
        _set_execution_budget_detail(
            separator_candidate,
            primary_reliability=primary_reliability,
            expanded_after_primary=False,
            extension_families=extension_families,
            skipped_reason=skipped_reason,
        )
    candidates.append(separator_candidate)
    separator_gate_candidate = separator_candidate
    separator_auto_gate = bool(
        separator_candidate.detail.get("candidate_assessment", {}).get("auto_gate", False)
    )
    if safety_candidate_outer_proposals_enabled(policy):
        safety_proposal = detect_safety_outer_proposal_candidate_for_count(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset,
            cache,
            policy=policy,
        )
        if safety_proposal is not None:
            safety_candidate = apply_candidate_assessment_policy(gray, safety_proposal, config, fmt, "separator", cache, policy=policy)
            safety_cap = policy.scoring.no_auto_cap_partial if strip_mode == "partial" else policy.scoring.no_auto_cap_full
            safety_candidate.confidence = min(
                safety_candidate.confidence,
                safety_cap,
                max(0.0, config.confidence_threshold - 0.01),
            )
            safety_candidate.review_reasons.append("safety_candidate_review_only")
            safety_candidate.review_reasons = sorted(set(safety_candidate.review_reasons))
            assessment = safety_candidate.detail.get("candidate_assessment", {})
            if isinstance(assessment, dict):
                assessment["auto_gate"] = False
                assessment["source"] = "safety_candidate"
            safety_candidate.detail["safety_candidate"] = {
                "used": True,
                "review_only": True,
                "separator_local_mode": policy.outer.proposal.geometry.separator.local.mode,
                "separator_full_width_mode": policy.outer.proposal.geometry.separator.full_width.mode,
                "strategies": list(policy.candidate_plan.safety_candidate.strategies),
            }
            candidates.append(safety_candidate)
    partial_safe_auto = is_partial_safe_auto_candidate(separator_gate_candidate, config.confidence_threshold)
    if partial_safe_auto and policy.candidate_plan.partial_stop.stop_after_safe_auto:
        stop_after_this_count = True
    if (
        content_policy.skip_after_separator_auto
        and strip_mode in content_policy.separator_auto_skip_strip_modes
        and separator_auto_gate
        and separator_gate_candidate.confidence >= config.confidence_threshold
    ):
        separator_gate_candidate.detail["content_candidate_skipped"] = content_policy.separator_auto_skip_reason
        return candidates, stop_after_this_count
    if (
        policy.candidate_plan.partial_stop.skip_content_after_safe_auto
        and strip_mode in policy.candidate_plan.partial_stop.skip_content_after_safe_auto_strip_modes
        and partial_safe_auto
    ):
        separator_gate_candidate.detail["content_candidate_skipped"] = (
            policy.candidate_plan.partial_stop.skip_content_after_safe_auto_reason
        )
        return candidates, stop_after_this_count
    if not content_policy.enabled:
        separator_gate_candidate.detail["content_candidate_skipped"] = content_policy.disabled_skip_reason
        return candidates, stop_after_this_count
    content = content_detection_for_count(
        gray,
        config,
        fmt,
        count,
        strip_mode,
        offset,
        cache,
        policy.content,
    )
    if content is not None:
        candidates.append(apply_candidate_assessment_policy(gray, content, config, fmt, "content", cache, policy=policy))
    return candidates, stop_after_this_count
