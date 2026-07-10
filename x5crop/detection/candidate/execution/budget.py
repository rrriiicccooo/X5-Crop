from __future__ import annotations

from typing import Any

from ....domain import DetectionCandidate
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
