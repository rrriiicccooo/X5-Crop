from __future__ import annotations

from typing import Any

from ..detection.decision.model import DecisionGateAssessment, FinalDetection
from ..detection.evidence.state import EvidenceState
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..detection.gate_checks import GateCheck
from ..domain import (
    AxisBleedParameters,
    Box,
    MeasurementProvenance,
    OutputProtectionPlan,
    SeparatorBandObservation,
)
from ..output.model import OutputGeometry
from ..units import ScanCalibration
from .validation import current_report_record_errors


def _box_from_record(value: dict[str, Any]) -> Box:
    return Box(
        int(value["left"]),
        int(value["top"]),
        int(value["right"]),
        int(value["bottom"]),
    )


def _geometry_from_record(value: dict[str, Any]) -> OutputGeometry:
    return OutputGeometry(
        outer=_box_from_record(value["outer_box"]),
        frames=tuple(_box_from_record(frame) for frame in value["frame_boxes"]),
    )


def _gate_check_from_record(value: dict[str, Any]) -> GateCheck:
    return GateCheck(
        code=str(value["code"]),
        stage=str(value["stage"]),
        state=EvidenceState(str(value["state"])),
        consequence=str(value["consequence"]),
        final_review_reason=(
            None
            if value["final_review_reason"] is None
            else str(value["final_review_reason"])
        ),
    )


def _decision_gate_from_record(value: dict[str, Any]) -> DecisionGateAssessment:
    return DecisionGateAssessment(
        checks=tuple(_gate_check_from_record(check) for check in value["checks"]),
    )


def _separator_observation_from_record(
    value: dict[str, Any],
) -> SeparatorBandObservation:
    provenance = value["provenance"]
    lane_box = value["lane_box"]
    return SeparatorBandObservation(
        index=int(value["index"]),
        center=float(value["center"]),
        score=float(value["score"]),
        method=str(value["method"]),
        provenance=MeasurementProvenance(
            root_measurement=str(provenance["root_measurement"]),
            source=str(provenance["source"]),
            dependencies=tuple(
                str(item) for item in provenance["dependencies"]
            ),
            boundary_anchors=tuple(
                str(item) for item in provenance["boundary_anchors"]
            ),
        ),
        start=(None if value["start"] is None else float(value["start"])),
        end=(None if value["end"] is None else float(value["end"])),
        lane_box=(None if lane_box is None else _box_from_record(lane_box)),
        continuity=(
            None if value["continuity"] is None else float(value["continuity"])
        ),
        tonal_evidence=(
            None
            if value["tonal_evidence"] is None
            else float(value["tonal_evidence"])
        ),
    )


def _output_protection_from_record(
    value: dict[str, Any],
) -> OutputProtectionPlan:
    base = value["base_bleed"]
    output = value["output_bleed"]
    return OutputProtectionPlan(
        base_bleed=AxisBleedParameters(
            int(base["long_axis"]),
            int(base["short_axis"]),
        ),
        output_bleed=AxisBleedParameters(
            int(output["long_axis"]),
            int(output["short_axis"]),
        ),
        exposure_overlap_detected=bool(value["exposure_overlap_detected"]),
        required_long_axis_bleed_px=int(value["required_long_axis_bleed_px"]),
        available_long_axis_bleed_px=int(value["available_long_axis_bleed_px"]),
        feasible=bool(value["feasible"]),
        reason=str(value["reason"]),
    )


def _scan_calibration_from_record(value: dict[str, Any]) -> ScanCalibration:
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
        span_px=(None if value["span_px"] is None else float(value["span_px"])),
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
        work_film_span=_box_from_record(record["film_span"]),
        pitch=float(record["pitch"]),
        decision_gate=_decision_gate_from_record(record["decision_gate"]),
        decision_geometry=_geometry_from_record(record["decision_geometry"]),
        output_geometry=_geometry_from_record(record["output_geometry"]),
        separator_observations=tuple(
            _separator_observation_from_record(observation)
            for observation in record["separator_observations"]
        ),
        output_protection=_output_protection_from_record(
            record["output"]["protection_plan"]
        ),
        scan_calibration=_scan_calibration_from_record(
            record["scan_calibration"]
        ),
        diagnostics=tuple(
            str(item) for item in record["diagnostics"]["detection"]
        ),
        trace=None,
    )
