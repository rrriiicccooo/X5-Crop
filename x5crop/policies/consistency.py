from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..formats import FORMAT_CHOICES, STRIP_CHOICES
from .decision.contract import DetectionDecisionContract, decision_contract_for_policy
from .ids import decision_policy_id_for
from .registry import get_detection_policy
from .runtime.policy import DetectionPolicy


@dataclass(frozen=True)
class PolicyConsistencyIssue:
    format_id: str
    strip_mode: str
    field: str
    runtime_value: object
    decision_value: object

    def message(self) -> str:
        return (
            f"{self.format_id}/{self.strip_mode} {self.field}: "
            f"runtime={self.runtime_value!r} decision={self.decision_value!r}"
        )


def _issue(
    policy: DetectionPolicy,
    contract: DetectionDecisionContract,
    field: str,
    runtime_value: object,
    decision_value: object,
) -> PolicyConsistencyIssue | None:
    if runtime_value == decision_value:
        return None
    return PolicyConsistencyIssue(
        policy.format_id,
        policy.strip_mode,
        field,
        runtime_value,
        decision_value,
    )


def consistency_issues_for_policy(policy: DetectionPolicy) -> list[PolicyConsistencyIssue]:
    contract = decision_contract_for_policy(policy)
    checks: list[tuple[str, object, object]] = [
        ("decision.policy_id", decision_policy_id_for(policy.format_id, policy.strip_mode), contract.policy_id),
        ("schema_id", policy.report.schema_id, contract.schema_id),
        ("schema_revision", policy.report.schema_revision, contract.schema_revision),
        ("format_id", policy.format_id, contract.format.format_id.value),
        ("strip_mode", policy.strip_mode, contract.mode.mode),
        (
            "decision.confidence_threshold_default",
            policy.scoring.confidence_threshold_default,
            contract.decision.confidence_threshold_default,
        ),
        (
            "decision.review_confidence_cap",
            policy.candidate_selection.confidence_cap,
            contract.decision.review_confidence_cap,
        ),
        (
            "decision.content_aspect_conflict_cap",
            policy.decision.content_aspect_conflict_cap,
            contract.decision.content_aspect_conflict_cap,
        ),
        (
            "decision.content_low_confidence_cap",
            policy.decision.content_low_confidence_cap,
            contract.decision.content_low_confidence_cap,
        ),
        (
            "decision.outer_mismatch_cap",
            policy.decision.outer_mismatch_cap,
            contract.decision.outer_mismatch_cap,
        ),
        (
            "evidence.allow_geometry_supported_separator",
            bool(policy.separator.geometry_support_modes),
            contract.evidence.allow_geometry_supported_separator,
        ),
        (
            "evidence.partial_requires_safe_edge",
            policy.strip_mode == "partial",
            contract.evidence.partial_requires_safe_edge,
        ),
    ]
    return [
        issue
        for field, runtime_value, decision_value in checks
        if (issue := _issue(policy, contract, field, runtime_value, decision_value)) is not None
    ]


def all_policy_consistency_issues() -> list[PolicyConsistencyIssue]:
    issues: list[PolicyConsistencyIssue] = []
    for format_id in FORMAT_CHOICES:
        for strip_mode in STRIP_CHOICES:
            issues.extend(consistency_issues_for_policy(get_detection_policy(format_id, strip_mode)))
    return issues


def assert_policy_consistency() -> None:
    issues = all_policy_consistency_issues()
    if issues:
        messages = "\n".join(issue.message() for issue in issues)
        raise AssertionError(f"Policy consistency check failed:\n{messages}")


def main(argv: Iterable[str] | None = None) -> int:
    _ = list(argv or ())
    issues = all_policy_consistency_issues()
    if issues:
        print("Policy consistency check failed:")
        for issue in issues:
            print(issue.message())
        return 1
    print(f"Policy consistency check passed for {len(FORMAT_CHOICES) * len(STRIP_CHOICES)} format/mode pairs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "PolicyConsistencyIssue",
    "all_policy_consistency_issues",
    "assert_policy_consistency",
    "consistency_issues_for_policy",
    "main",
]
