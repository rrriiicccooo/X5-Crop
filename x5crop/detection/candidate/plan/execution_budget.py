from __future__ import annotations

from typing import Any

from ....domain import DetectionCandidate
from ....policies.runtime.policy import DetectionPolicy


def separator_extension_families(
    policy: DetectionPolicy,
    strip_mode: str,
    explicit_count: bool,
) -> list[str]:
    separator_policy = policy.outer.proposal.geometry.separator
    families: list[str] = []
    if separator_policy.full_width.available_for(strip_mode, explicit_count):
        families.append("separator_full_width")
    if policy.candidate_plan.content_guided_separator.available_for(strip_mode):
        families.append("content_guided_separator")
    return families


def set_execution_budget_detail(
    detection: DetectionCandidate,
    *,
    primary_reliability: dict[str, Any],
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


def attach_execution_budget_to_candidates(
    candidates: list[DetectionCandidate],
    *,
    primary_reliability: dict[str, Any],
    expanded_after_primary: bool,
    extension_families: list[str],
    skipped_reason: str | None = None,
) -> None:
    for candidate in candidates:
        set_execution_budget_detail(
            candidate,
            primary_reliability=primary_reliability,
            expanded_after_primary=expanded_after_primary,
            extension_families=extension_families,
            skipped_reason=skipped_reason,
        )


__all__ = [
    "attach_execution_budget_to_candidates",
    "separator_extension_families",
    "set_execution_budget_detail",
]
