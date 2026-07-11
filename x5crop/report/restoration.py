from __future__ import annotations

from typing import Any

from ..detection.decision.model import DecisionGateAssessment, FinalDetection
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..detection.gate_checks import GateCheck
from ..domain import (
    AxisBleedParameters,
    Box,
    CropEnvelope,
    DimensionConstrainedBoundary,
    EvidenceState,
    FrameBoundary,
    MeasurementProvenance,
    OutputBleedPlan,
    PixelInterval,
    SeparatorAssignment,
    SeparatorBandObservation,
    VisibleSequenceSpan,
)
from ..output.model import OutputGeometry
from ..units import ScanCalibration
from .validation import current_report_record_errors


def _box(value: dict[str, Any]) -> Box:
    return Box(
        int(value["left"]),
        int(value["top"]),
        int(value["right"]),
        int(value["bottom"]),
    )


def _interval(value: dict[str, Any]) -> PixelInterval:
    return PixelInterval(float(value["minimum"]), float(value["maximum"]))


def _provenance(value: dict[str, Any]) -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=str(value["root_measurement"]),
        source=str(value["source"]),
        dependencies=tuple(str(item) for item in value["dependencies"]),
        boundary_anchors=tuple(str(item) for item in value["boundary_anchors"]),
    )


def _observation(value: dict[str, Any]) -> SeparatorBandObservation:
    return SeparatorBandObservation(
        start=float(value["start"]),
        end=float(value["end"]),
        center=float(value["center"]),
        score=float(value["score"]),
        provenance=_provenance(value["provenance"]),
        lane_box=None if value["lane_box"] is None else _box(value["lane_box"]),
        continuity=(
            None if value["continuity"] is None else float(value["continuity"])
        ),
        tonal_evidence=(
            None
            if value["tonal_evidence"] is None
            else float(value["tonal_evidence"])
        ),
    )


def _assignment(value: dict[str, Any]) -> SeparatorAssignment:
    return SeparatorAssignment(
        boundary_index=int(value["boundary_index"]),
        observation=_observation(value["observation"]),
        allowed_interval=_interval(value["allowed_interval"]),
        state=EvidenceState(str(value["state"])),
        geometry_dependent=bool(value["geometry_dependent"]),
        used_for_boundary=bool(value["used_for_boundary"]),
        reason=str(value["reason"]),
    )


def _frame_boundary(value: dict[str, Any]) -> FrameBoundary:
    assignment = (
        None if value["assignment"] is None else _assignment(value["assignment"])
    )
    constraint_value = value["dimension_constraint"]
    constraint = (
        None
        if constraint_value is None
        else DimensionConstrainedBoundary(
            boundary_index=int(constraint_value["boundary_index"]),
            position=_interval(constraint_value["position"]),
            provenance=_provenance(constraint_value["provenance"]),
            focused_observation=(
                None
                if constraint_value["focused_observation"] is None
                else _observation(constraint_value["focused_observation"])
            ),
        )
    )
    return FrameBoundary(
        boundary_index=int(value["boundary_index"]),
        position=_interval(value["position"]),
        source=str(value["source"]),
        provenance=_provenance(value["provenance"]),
        assignment=assignment,
        dimension_constraint=constraint,
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


def _output_bleed(value: dict[str, Any]) -> OutputBleedPlan:
    user = value["user_bleed"]
    effective = value["effective_bleed"]
    return OutputBleedPlan(
        user_bleed=AxisBleedParameters(
            int(user["long_axis"]), int(user["short_axis"])
        ),
        effective_bleed=AxisBleedParameters(
            int(effective["long_axis"]), int(effective["short_axis"])
        ),
        overlap_detected=bool(value["overlap_detected"]),
        overlap_required_long_axis_bleed_px=int(
            value["overlap_required_long_axis_bleed_px"]
        ),
        long_axis_bleed_capacity_px=int(value["long_axis_bleed_capacity_px"]),
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
    return FinalDetection(
        format_id=str(record["format_id"]),
        layout=str(record["layout"]),
        strip_mode=str(record["strip_mode"]),
        count=int(record["count"]),
        confidence=float(record["confidence"]),
        visible_sequence_span=VisibleSequenceSpan(
            _box(record["visible_sequence_span"]["box"])
        ),
        crop_envelope=CropEnvelope(_box(record["crop_envelope"]["box"])),
        decision_gate=_decision_gate(record["decision_gate"]),
        decision_geometry=_output_geometry(record["decision_geometry"]),
        output_geometry=_output_geometry(record["output_geometry"]),
        separator_observations=tuple(
            _observation(item) for item in record["separator_observations"]
        ),
        separator_assignments=tuple(
            _assignment(item) for item in record["separator_assignments"]
        ),
        frame_boundaries=tuple(
            _frame_boundary(item) for item in record["frame_boundaries"]
        ),
        output_bleed_plan=_output_bleed(record["output"]["bleed_plan"]),
        scan_calibration=_scan_calibration(record["scan_calibration"]),
        diagnostics=tuple(str(item) for item in record["diagnostics"]["detection"]),
        selection=None,
    )
