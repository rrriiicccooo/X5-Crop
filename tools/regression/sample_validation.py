"""Evaluate current reports against independent real-sample authorities."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from tools.regression.frame_slot_reference import (
    FrameSlotReference,
    ReferenceValidationOutcome,
    compare_report_to_reference,
    load_current_report_rows,
    load_frame_slot_references,
)
from tools.regression.sample_expectations import (
    DecisionExpectation,
    ObservationProofExpectation,
    SampleExpectation,
    discover_sample_paths,
    load_sample_expectations,
    validate_sample_dataset,
)
from tools.regression.sample_identity import canonical_sample_source
from x5crop.report.validation import validate_current_report_record


class SampleContractOutcome(str, Enum):
    CONFORMING = "conforming"
    CAPABILITY_GAP = "capability_gap"
    EVIDENCE_CONTRACT_CONFLICT = "evidence_contract_conflict"
    VIOLATION = "violation"


class SampleContractReason(str, Enum):
    CURRENT_REPORT_MISSING = "current_report_missing"
    CURRENT_REPORT_INVALID = "current_report_invalid"
    REPORT_SOURCE_MISMATCH = "report_source_mismatch"
    MANUAL_REFERENCE_MISSING = "manual_reference_missing"
    MANUAL_REFERENCE_UNEXPECTED = "manual_reference_unexpected"
    MANUAL_REFERENCE_IDENTITY_MISMATCH = "manual_reference_identity_mismatch"
    RESOLVED_GEOMETRY_OUTSIDE_REFERENCE = (
        "resolved_geometry_outside_reference"
    )
    UNRESOLVED_GEOMETRY_EXPORT_ELIGIBLE = (
        "unresolved_geometry_export_eligible"
    )
    PROOF_UNAVAILABLE_BUT_GEOMETRY_RESOLVED = (
        "proof_unavailable_but_geometry_resolved"
    )
    REVIEW_REQUIRED_NOT_REVIEW = "review_required_not_review"
    REVIEW_REQUIRED_EXPORT_ELIGIBLE = "review_required_export_eligible"
    PASS_REQUIRED_NOT_APPROVED = "pass_required_not_approved"
    PASS_TARGET_EXCEEDS_PROOF_EXPECTATION = (
        "pass_target_exceeds_proof_expectation"
    )


@dataclass(frozen=True)
class SampleContractResult:
    source: str
    outcome: SampleContractOutcome
    reasons: tuple[SampleContractReason, ...]
    reference_violations: tuple[str, ...] = ()


def _violation(
    source: str,
    *reasons: SampleContractReason,
    reference_violations: tuple[str, ...] = (),
) -> SampleContractResult:
    return SampleContractResult(
        source,
        SampleContractOutcome.VIOLATION,
        tuple(dict.fromkeys(reasons)),
        reference_violations,
    )


def _reference_contract_reason(
    expectation: SampleExpectation,
    reference: FrameSlotReference | None,
    workspace_root: Path,
) -> SampleContractReason | None:
    if expectation.geometry_reference is None:
        return (
            SampleContractReason.MANUAL_REFERENCE_UNEXPECTED
            if reference is not None
            else None
        )
    if reference is None:
        return SampleContractReason.MANUAL_REFERENCE_MISSING
    if canonical_sample_source(
        reference.source, workspace_root
    ) != canonical_sample_source(expectation.geometry_reference, workspace_root):
        return SampleContractReason.MANUAL_REFERENCE_IDENTITY_MISMATCH
    return None


def evaluate_sample_contract(
    expectation: SampleExpectation,
    reference: FrameSlotReference | None,
    report: dict[str, Any] | None,
    *,
    workspace_root: Path | None = None,
) -> SampleContractResult:
    """Compare one current report with manual geometry, proof, and decision truth."""

    root = Path.cwd() if workspace_root is None else workspace_root
    reference_reason = _reference_contract_reason(expectation, reference, root)
    if reference_reason is not None:
        return _violation(expectation.source, reference_reason)
    if report is None:
        return _violation(
            expectation.source,
            SampleContractReason.CURRENT_REPORT_MISSING,
        )
    try:
        validate_current_report_record(report)
    except (TypeError, ValueError):
        return _violation(
            expectation.source,
            SampleContractReason.CURRENT_REPORT_INVALID,
        )
    if canonical_sample_source(
        report["source"], root
    ) != canonical_sample_source(expectation.source, root):
        return _violation(
            expectation.source,
            SampleContractReason.REPORT_SOURCE_MISMATCH,
        )

    resolution_supported = (
        report["selection"]["geometry_resolution"]["state"] == "supported"
    )
    export_eligible = bool(
        report["output"]["export_eligibility"]["frame_export_eligible"]
    )
    status = report["decision"]["status"]
    violations: list[SampleContractReason] = []
    reference_violations: tuple[str, ...] = ()

    if not resolution_supported and export_eligible:
        violations.append(
            SampleContractReason.UNRESOLVED_GEOMETRY_EXPORT_ELIGIBLE
        )
    if reference is not None:
        reference_result = compare_report_to_reference(
            report,
            reference,
            workspace_root=root,
        )
        if reference_result.outcome == ReferenceValidationOutcome.VIOLATED:
            violations.append(
                SampleContractReason.RESOLVED_GEOMETRY_OUTSIDE_REFERENCE
            )
            reference_violations = reference_result.violations
    if (
        expectation.observation_proof_expectation
        == ObservationProofExpectation.INDEPENDENT_PROOF_UNAVAILABLE
        and resolution_supported
    ):
        violations.append(
            SampleContractReason.PROOF_UNAVAILABLE_BUT_GEOMETRY_RESOLVED
        )

    decision_expectation = expectation.automatic_decision_expectation
    if decision_expectation == DecisionExpectation.REVIEW_REQUIRED:
        if status != "needs_review":
            violations.append(SampleContractReason.REVIEW_REQUIRED_NOT_REVIEW)
        if export_eligible:
            violations.append(
                SampleContractReason.REVIEW_REQUIRED_EXPORT_ELIGIBLE
            )
    if violations:
        return _violation(
            expectation.source,
            *violations,
            reference_violations=reference_violations,
        )

    if decision_expectation == DecisionExpectation.PASS_REQUIRED:
        if (
            expectation.observation_proof_expectation
            == ObservationProofExpectation.INDEPENDENT_PROOF_UNAVAILABLE
        ):
            return SampleContractResult(
                expectation.source,
                SampleContractOutcome.EVIDENCE_CONTRACT_CONFLICT,
                (
                    SampleContractReason.PASS_TARGET_EXCEEDS_PROOF_EXPECTATION,
                ),
            )
        if status != "approved_auto":
            return SampleContractResult(
                expectation.source,
                SampleContractOutcome.CAPABILITY_GAP,
                (SampleContractReason.PASS_REQUIRED_NOT_APPROVED,),
            )

    return SampleContractResult(
        expectation.source,
        SampleContractOutcome.CONFORMING,
        (),
    )


def _unique_by_source(
    records: Iterable[Any],
    workspace_root: Path,
) -> dict[Path, Any]:
    by_source: dict[Path, Any] = {}
    for record in records:
        source = canonical_sample_source(record.source, workspace_root)
        if source in by_source:
            raise ValueError("sample contract sources must be unique")
        by_source[source] = record
    return by_source


def evaluate_sample_dataset(
    expectations: tuple[SampleExpectation, ...],
    references: tuple[FrameSlotReference, ...],
    reports: Iterable[dict[str, Any]],
    *,
    workspace_root: Path | None = None,
) -> tuple[SampleContractResult, ...]:
    root = Path.cwd() if workspace_root is None else workspace_root
    expectation_by_source = _unique_by_source(expectations, root)
    reference_by_source = _unique_by_source(references, root)
    required_references = {
        canonical_sample_source(expectation.geometry_reference, root)
        for expectation in expectations
        if expectation.geometry_reference is not None
    }
    if set(reference_by_source) != required_references:
        raise ValueError("manual references must match sample expectations exactly")

    report_by_source: dict[Path, dict[str, Any]] = {}
    for report in reports:
        source_value = report.get("source") if isinstance(report, dict) else None
        if not isinstance(source_value, str) or not source_value:
            raise ValueError("current report requires a source identity")
        source = canonical_sample_source(source_value, root)
        if source in report_by_source:
            raise ValueError("current report sources must be unique")
        report_by_source[source] = report
    extra_reports = set(report_by_source) - set(expectation_by_source)
    if extra_reports:
        raise ValueError("current reports contain samples outside expectations")

    results: list[SampleContractResult] = []
    for expectation in expectations:
        source = canonical_sample_source(expectation.source, root)
        reference = (
            reference_by_source[
                canonical_sample_source(expectation.geometry_reference, root)
            ]
            if expectation.geometry_reference is not None
            else None
        )
        results.append(
            evaluate_sample_contract(
                expectation,
                reference,
                report_by_source.get(source),
                workspace_root=root,
            )
        )
    return tuple(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate current reports against real-sample contracts."
    )
    parser.add_argument("expectations", type=Path)
    parser.add_argument("references", type=Path)
    parser.add_argument("sample_root", type=Path)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    expectations = load_sample_expectations(args.expectations)
    references = load_frame_slot_references(args.references)
    validate_sample_dataset(
        expectations,
        references,
        discover_sample_paths(args.sample_root),
        workspace_root=args.workspace_root,
    )
    report_by_source = load_current_report_rows(
        args.reports,
        workspace_root=args.workspace_root,
    )
    results = evaluate_sample_dataset(
        expectations,
        references,
        report_by_source.values(),
        workspace_root=args.workspace_root,
    )
    for result in results:
        if result.outcome == SampleContractOutcome.CONFORMING:
            continue
        reasons = ",".join(reason.value for reason in result.reasons)
        print(f"{result.outcome.value}: {result.source}: {reasons}")
        for violation in result.reference_violations:
            print(f"  {violation}")
    counts = Counter(result.outcome.value for result in results)
    summary = " ".join(
        f"{outcome.value}={counts[outcome.value]}"
        for outcome in SampleContractOutcome
    )
    print(f"samples={len(results)} {summary}")
    return int(any(result.outcome != SampleContractOutcome.CONFORMING for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
