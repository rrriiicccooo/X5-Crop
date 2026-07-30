from __future__ import annotations

from typing import Any

from ..detection.candidate.assessment.model import CANDIDATE_GATE_CHECK_CODES
from ..detection.decision.vocabulary import FINAL_REVIEW_REASONS
from .identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
    core_facts_sha256,
)


CURRENT_REPORT_SECTIONS = (
    "schema_id",
    "schema_revision",
    "script_version",
    "source",
    "input",
    "configuration",
    "measurement",
    "grid_selection",
    "candidate_gate",
    "decision",
    "output",
    "analysis_identity",
    "core_facts_sha256",
)


def _validate_gate(record: dict[str, Any], stage: str) -> None:
    checks = record.get("checks")
    if (
        not isinstance(checks, list)
        or tuple(item.get("code") for item in checks)
        != CANDIDATE_GATE_CHECK_CODES
        or any(item.get("stage") != stage for item in checks)
    ):
        raise ValueError(f"{stage} Gate is incomplete or out of order")


def validate_current_report_record(record: dict[str, Any]) -> None:
    if tuple(record) != CURRENT_REPORT_SECTIONS:
        raise ValueError("current report sections are incomplete or out of order")
    if (
        record["schema_id"] != REPORT_SCHEMA_ID
        or record["schema_revision"] != REPORT_SCHEMA_REVISION
    ):
        raise ValueError("report does not use the current-only schema")
    _validate_gate(record["candidate_gate"], "candidate")
    decision = record["decision"]
    _validate_gate(decision["gate"], "decision")
    status = decision.get("status")
    if status not in {"approved_auto", "needs_review"}:
        raise ValueError("decision status is not current")
    reasons = tuple(decision.get("final_review_reasons", ()))
    if any(reason not in FINAL_REVIEW_REASONS for reason in reasons):
        raise ValueError("decision reasons are not current typed reasons")
    if (status == "approved_auto") != (not reasons):
        raise ValueError("approved/review status and final reasons disagree")

    output = record["output"]
    finalization = output["finalization"]
    selected_count = finalization["selected_count"]
    final_boxes = finalization["final_boxes"]
    protected = finalization["protected_envelopes"]
    output_files = output["output_files"]
    diagnostics = bool(
        record["analysis_identity"]["runtime_configuration"]["diagnostics"]
    )
    if status == "approved_auto":
        if (
            not finalization["frame_export_eligible"]
            or not isinstance(selected_count, int)
            or selected_count <= 0
            or len(final_boxes) != selected_count
            or len(protected) != selected_count
        ):
            raise ValueError(
                "approved output must retain one final box per selected slot"
            )
        if diagnostics:
            if (
                finalization["frame_export_requested"]
                or finalization["frame_export_performed"]
                or output_files
                or output["tiff_fidelity"]["success_receipt"]
                != "not_requested_diagnostics"
                or output["tiff_fidelity"]["write_readback_validated"]
            ):
                raise ValueError(
                    "read-only diagnostics cannot claim frame TIFF output"
                )
        elif (
            not finalization["frame_export_requested"]
            or not finalization["frame_export_performed"]
            or len(output_files) != selected_count
            or output["tiff_fidelity"]["success_receipt"] != "validated"
            or not output["tiff_fidelity"]["write_readback_validated"]
        ):
            raise ValueError(
                "approved output must contain one validated TIFF per selected slot"
            )
    elif (
        finalization["frame_export_eligible"]
        or finalization["frame_export_performed"]
        or final_boxes
        or protected
        or output_files
        or output["tiff_fidelity"]["success_receipt"] != "not_created"
    ):
        raise ValueError("review output cannot claim successful frame export")
    if finalization["post_decision_mutation"]:
        raise ValueError("post-DecisionGate output mutation is forbidden")
    if (
        record["grid_selection"]["selected_count"] != selected_count
        or record["analysis_identity"]["output_identity"]["selected_count"]
        != selected_count
    ):
        raise ValueError("selected count identities disagree")
    if record["core_facts_sha256"] != core_facts_sha256(record):
        raise ValueError("core facts hash does not match the record")
