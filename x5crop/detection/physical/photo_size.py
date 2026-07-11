from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import TYPE_CHECKING

from ...domain import FrameDimensionEstimate, MeasurementProvenance
from ...formats import FormatPhysicalSpec
from ...policies.parameters.separator import FrameDimensionEstimateParameters
from ...units import ScanCalibration
from x5crop.domain import EvidenceState
from .boundary import HolderOcclusionEvidence
from x5crop.domain import PixelInterval, VisibleSequenceSpan

if TYPE_CHECKING:
    from ..evidence.separator_continuity import SeparatorContinuityEvidence
    from ..geometry import CandidateGeometry


def _width_cv(values: tuple[float, ...]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    if mean <= 0.0:
        return None
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return (variance ** 0.5) / mean


@dataclass(frozen=True)
class FrameDimensionEvidence:
    state: EvidenceState
    reason: str
    nominal_width_mm: float
    nominal_height_mm: float
    nominal_aspect: float
    photo_widths_px: tuple[float, ...]
    photo_width_cv: float | None
    separator_widths_px: tuple[float, ...]
    separator_width_cv: float | None
    observed_width_mm: float | None
    observed_height_mm: float | None
    observed_aspect: float | None
    aspect_error_ratio: float | None
    maximum_dimension_error_ratio: float | None
    calibration_used: bool


def frame_dimension_estimate(
    span: VisibleSequenceSpan,
    physical_spec: FormatPhysicalSpec,
    calibration: ScanCalibration,
    parameters: FrameDimensionEstimateParameters,
    *,
    layout: str,
) -> FrameDimensionEstimate:
    nominal = physical_spec.nominal_frame_size_mm
    short_axis = float(span.box.height)
    aspect_width = short_axis * float(physical_spec.horizontal_content_aspect)
    long_ppm = calibration.px_per_mm("x" if layout == "horizontal" else "y")
    short_ppm = calibration.px_per_mm("y" if layout == "horizontal" else "x")
    calibrated = bool(
        calibration.trusted
        and long_ppm is not None
        and short_ppm is not None
        and long_ppm > 0.0
        and short_ppm > 0.0
    )
    width = float(nominal.width_mm) * float(long_ppm) if calibrated else aspect_width
    height = float(nominal.height_mm) * float(short_ppm) if calibrated else short_axis
    tolerance = max(0.0, float(parameters.relative_tolerance))
    return FrameDimensionEstimate(
        width_px=PixelInterval(
            max(1.0, width * (1.0 - tolerance)),
            max(1.0, width * (1.0 + tolerance)),
        ),
        height_px=PixelInterval(
            max(1.0, height * (1.0 - tolerance)),
            max(1.0, height * (1.0 + tolerance)),
        ),
        source="scan_calibration" if calibrated else "short_axis_aspect",
        provenance=MeasurementProvenance(
            root_measurement=(
                "scan_calibration" if calibrated else "physical_frame_aspect"
            ),
            source="frame_dimension_estimate",
            dependencies=(
                "format_physical_spec",
                "scan_calibration" if calibrated else "short_axis_boundaries",
            ),
        ),
    )


def _continuity_supported(
    continuity: SeparatorContinuityEvidence,
    start: float,
    end: float,
) -> bool:
    return any(
        record.start == start
        and record.end == end
        and record.state == EvidenceState.SUPPORTED
        for record in continuity.records
    )


def _photo_widths(
    geometry: CandidateGeometry,
    continuity: SeparatorContinuityEvidence,
    holder_occlusion: HolderOcclusionEvidence,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    assignments = tuple(
        sorted(
            (
                assignment
                for assignment in geometry.separator_assignments
                if assignment.used_for_boundary and assignment.independent
                and _continuity_supported(
                    continuity,
                    assignment.observation.start,
                    assignment.observation.end,
                )
            ),
            key=lambda assignment: assignment.boundary_index,
        )
    )
    if len(assignments) != max(0, geometry.count - 1):
        return (), tuple(
            assignment.observation.width for assignment in assignments
        )
    span = geometry.visible_sequence_span.box
    widths: list[float] = []
    if assignments:
        if holder_occlusion.leading.state != EvidenceState.SUPPORTED:
            widths.append(assignments[0].observation.start - float(span.left))
        widths.extend(
            right.observation.start - left.observation.end
            for left, right in zip(assignments[:-1], assignments[1:])
        )
        if holder_occlusion.trailing.state != EvidenceState.SUPPORTED:
            widths.append(float(span.right) - assignments[-1].observation.end)
    elif geometry.count == 1:
        width = float(span.width)
        if holder_occlusion.leading.state == EvidenceState.SUPPORTED:
            width += holder_occlusion.leading.hidden_width_px.midpoint
        if holder_occlusion.trailing.state == EvidenceState.SUPPORTED:
            width += holder_occlusion.trailing.hidden_width_px.midpoint
        widths.append(width)
    return (
        tuple(width for width in widths if width > 0.0),
        tuple(assignment.observation.width for assignment in assignments),
    )


def frame_dimension_evidence(
    geometry: CandidateGeometry,
    physical_spec: FormatPhysicalSpec,
    calibration: ScanCalibration,
    continuity: SeparatorContinuityEvidence,
    holder_occlusion: HolderOcclusionEvidence,
    *,
    maximum_photo_width_cv: float,
    maximum_dimension_error_ratio: float,
) -> FrameDimensionEvidence:
    nominal = physical_spec.nominal_frame_size_mm
    photo_widths, separator_widths = _photo_widths(
        geometry,
        continuity,
        holder_occlusion,
    )
    target = geometry.frame_dimension_estimate.width_px.midpoint
    photo_cv = _width_cv(photo_widths)
    separator_cv = _width_cv(separator_widths)
    errors = tuple(
        abs(width - target) / max(1.0, target) for width in photo_widths
    )
    maximum_error = max(errors) if errors else None
    observed_width = median(photo_widths) if photo_widths else None
    observed_height = float(geometry.visible_sequence_span.box.height)
    observed_aspect = (
        float(observed_width) / max(1.0, observed_height)
        if observed_width is not None
        else None
    )
    nominal_aspect = float(physical_spec.horizontal_content_aspect)
    aspect_error = (
        abs(observed_aspect - nominal_aspect) / max(1e-6, nominal_aspect)
        if observed_aspect is not None
        else None
    )
    long_ppm = calibration.px_per_mm(
        "x" if geometry.layout == "horizontal" else "y"
    )
    short_ppm = calibration.px_per_mm(
        "y" if geometry.layout == "horizontal" else "x"
    )
    calibration_used = bool(
        calibration.trusted
        and long_ppm is not None
        and short_ppm is not None
        and long_ppm > 0.0
        and short_ppm > 0.0
    )
    boundary_by_side = {
        observation.side: observation
        for observation in geometry.boundary_observations
    }
    short_axis_boundaries_supported = all(
        side in boundary_by_side
        and boundary_by_side[side].kind != "canvas_clip"
        for side in ("top", "bottom")
    )
    physical_dimension_model_supported = bool(
        calibration_used
        or (
            geometry.frame_dimension_estimate.source == "short_axis_aspect"
            and short_axis_boundaries_supported
        )
    )
    observed_width_mm = (
        float(observed_width) / float(long_ppm)
        if calibration_used and observed_width is not None
        else None
    )
    observed_height_mm = (
        observed_height / float(short_ppm) if calibration_used else None
    )
    if photo_cv is not None and photo_cv > float(maximum_photo_width_cv):
        state = EvidenceState.CONTRADICTED
        reason = "photo_widths_inconsistent"
    elif maximum_error is not None and maximum_error > float(
        maximum_dimension_error_ratio
    ):
        state = EvidenceState.CONTRADICTED
        reason = "physical_frame_dimensions_contradicted"
    elif photo_widths:
        state = EvidenceState.SUPPORTED
        reason = "photo_dimensions_supported"
    elif physical_dimension_model_supported:
        state = EvidenceState.SUPPORTED
        reason = (
            "calibrated_frame_dimensions_supported"
            if calibration_used
            else "physical_aspect_dimensions_supported"
        )
    else:
        state = EvidenceState.UNAVAILABLE
        reason = "independent_photo_edge_measurements_unavailable"
    return FrameDimensionEvidence(
        state,
        reason,
        float(nominal.width_mm),
        float(nominal.height_mm),
        nominal_aspect,
        tuple(float(width) for width in photo_widths),
        photo_cv,
        tuple(float(width) for width in separator_widths),
        separator_cv,
        observed_width_mm,
        observed_height_mm,
        observed_aspect,
        aspect_error,
        maximum_error,
        calibration_used,
    )
