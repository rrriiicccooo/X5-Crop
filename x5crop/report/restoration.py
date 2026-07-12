from __future__ import annotations

from typing import Any

from ..detection.decision.model import DecisionGateAssessment, FinalDetection
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..detection.gate_checks import GateCheck
from ..domain import (
    AxisBleedParameters,
    Box,
    CropEnvelope,
    EvidenceState,
    FrameBoundaryReference,
)
from ..output.model import (
    BoundaryOverlapProtection,
    FrameBleedPlan,
    FrameSideBleed,
    OutputGeometry,
)
from ..units import ScanCalibration
from .validation import current_report_record_errors


def _box(value: dict[str, Any]) -> Box:
    return Box(
        int(value["left"]),
        int(value["top"]),
        int(value["right"]),
        int(value["bottom"]),
    )


def _output_geometry(value: dict[str, Any]) -> OutputGeometry:
    return OutputGeometry(
        crop_envelope=CropEnvelope(_box(value["crop_envelope"])),
        frames=tuple(_box(frame) for frame in value["frame_boxes"]),
    )


def _decision_gate(value: dict[str, Any]) -> DecisionGateAssessment:
    return DecisionGateAssessment(
        checks=tuple(
            GateCheck(
                code=str(check["code"]),
                stage=str(check["stage"]),
                state=EvidenceState(str(check["state"])),
                consequence=str(check["consequence"]),
                final_review_reason=(
                    None
                    if check["final_review_reason"] is None
                    else str(check["final_review_reason"])
                ),
            )
            for check in value["checks"]
        )
    )


def _frame_bleed_plan(value: dict[str, Any]) -> FrameBleedPlan:
    def boundary_reference(item: dict[str, Any]) -> FrameBoundaryReference:
        return FrameBoundaryReference(
            None if item["lane_index"] is None else int(item["lane_index"]),
            int(item["boundary_index"]),
        )

    user = value["user_bleed"]
    return FrameBleedPlan(
        user_bleed=AxisBleedParameters(
            int(user["long_axis"]), int(user["short_axis"])
        ),
        frame_sides=tuple(
            FrameSideBleed(
                int(item["frame_index"]),
                int(item["leading_px"]),
                int(item["trailing_px"]),
                int(item["short_axis_px"]),
            )
            for item in value["frame_sides"]
        ),
        overlap_protection=tuple(
            BoundaryOverlapProtection(
                boundary_reference(item["boundary"]),
                int(item["left_frame_index"]),
                int(item["right_frame_index"]),
                int(item["required_px"]),
                int(item["left_trailing_available_px"]),
                int(item["right_leading_available_px"]),
                str(item["provenance"]),
            )
            for item in value["overlap_protection"]
        ),
        unresolved_overlap_boundaries=tuple(
            boundary_reference(item)
            for item in value["unresolved_overlap_boundaries"]
        ),
        feasible=bool(value["feasible"]),
        reason=str(value["reason"]),
    )


def _scan_calibration(value: dict[str, Any]) -> ScanCalibration:
    return ScanCalibration(
        x_px_per_mm=(
            None if value["x_px_per_mm"] is None else float(value["x_px_per_mm"])
        ),
        y_px_per_mm=(
            None if value["y_px_per_mm"] is None else float(value["y_px_per_mm"])
        ),
        source=str(value["source"]),
        trusted=bool(value["trusted"]),
        warnings=tuple(str(item) for item in value["warnings"]),
    )


def transform_geometry_from_record(
    record: dict[str, Any],
) -> TransformGeometryEvidence:
    value = record["diagnostics"]["transform_geometry"]
    return TransformGeometryEvidence(
        state=EvidenceState(str(value["state"])),
        applied=bool(value["applied"]),
        estimated_angle_degrees=float(value["estimated_angle_degrees"]),
        applied_angle_degrees=float(value["applied_angle_degrees"]),
        reason=str(value["reason"]),
        span_px=None if value["span_px"] is None else float(value["span_px"]),
        span_threshold_px=(
            None
            if value["span_threshold_px"] is None
            else float(value["span_threshold_px"])
        ),
    )


def final_detection_from_record(record: dict[str, Any]) -> FinalDetection:
    errors = current_report_record_errors(record)
    if errors:
        raise ValueError("invalid current report record: " + ",".join(errors))
    selection = record["selection"]
    selected = selection["candidates"][int(selection["selected_rank"]) - 1]
    geometry = selected["candidate_geometry"]
    decision = record["decision"]
    output = record["output"]
    return FinalDetection(
        format_id=str(geometry["format_id"]),
        layout=str(geometry["layout"]),
        strip_mode=str(geometry["strip_mode"]),
        count=int(geometry["count"]),
        decision_gate=_decision_gate(decision["gate"]),
        decision_geometry=_output_geometry(output["decision_geometry"]),
        output_geometry=_output_geometry(output["final_geometry"]),
        frame_bleed_plan=_frame_bleed_plan(output["frame_bleed_plan"]),
        scan_calibration=_scan_calibration(
            record["input"]["scan_calibration"]
        ),
        diagnostics=tuple(str(item) for item in record["diagnostics"]["detection"]),
    )
