from __future__ import annotations

from typing import Any

from ..detection.final.finalize import finalize_detection
from ..detection.final.model import FinalDetection, FinalizationPlan
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..domain import (
    Box,
    CropEnvelope,
    EvidenceState,
    FrameBoundaryReference,
)
from ..output.model import (
    AxisBleedParameters,
    BoundaryOverlapProtection,
    FrameBleedPlan,
    FrameSideBleed,
    OutputGeometry,
)
from .validation import (
    current_report_record_errors,
    decision_gate_from_read_model,
)


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
        frame_output_bounds=tuple(
            _box(item) for item in value["frame_output_bounds"]
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


def transform_geometry_from_record(
    record: dict[str, Any],
) -> TransformGeometryEvidence:
    value = record["input"]["transform_geometry"]
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
    decision = record["decision"]
    output = record["output"]
    plan_value = output["finalization_plan"]
    finalization_plan = FinalizationPlan(
        layout=str(plan_value["layout"]),
        image_width=int(plan_value["image_width"]),
        image_height=int(plan_value["image_height"]),
        decision_geometry=_output_geometry(plan_value["decision_geometry"]),
        frame_bleed_plan=_frame_bleed_plan(plan_value["frame_bleed_plan"]),
    )
    detection = finalize_detection(
        decision_gate_from_read_model(decision["gate"]),
        finalization_plan,
    )
    if detection.output_geometry != _output_geometry(output["final_geometry"]):
        raise ValueError("cached final geometry does not match finalization plan")
    return detection
