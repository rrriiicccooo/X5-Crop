from __future__ import annotations

from typing import Any

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
    "source_core",
    "candidate_gate",
    "decision",
    "output",
    "analysis_identity",
    "core_facts_sha256",
)


def validate_current_report_record(record: dict[str, Any]) -> None:
    if tuple(record) != CURRENT_REPORT_SECTIONS:
        raise ValueError("current report sections are incomplete or out of order")
    if (
        record["schema_id"] != REPORT_SCHEMA_ID
        or record["schema_revision"] != REPORT_SCHEMA_REVISION
    ):
        raise ValueError("report does not use the current-only schema")
    decision = record["decision"]
    if decision["status"] != "needs_review":
        raise ValueError("source-core baseline must remain needs_review")
    reasons = tuple(decision["final_review_reasons"])
    if not reasons or any(reason not in FINAL_REVIEW_REASONS for reason in reasons):
        raise ValueError("decision reasons are not current typed reasons")
    output = record["output"]
    finalization = output["finalization"]
    if (
        finalization["frame_export_eligible"]
        or finalization["final_boxes"]
        or output["output_files"]
    ):
        raise ValueError("unavailable Grid cannot finalize frame TIFFs")
    source_core = record["source_core"]
    if (
        source_core["frame_grid"]["outcome"]
        != "no_independent_phase_authority"
        or source_core["photo_containment"]["outcome"]
        != "not_applicable_frame_grid_unavailable"
        or source_core["visual_deskew_outcome"]
        != "not_applicable_core_unavailable"
    ):
        raise ValueError("source-core downstream outcomes are inconsistent")
    if record["core_facts_sha256"] != core_facts_sha256(record):
        raise ValueError("core facts hash does not match the record")
