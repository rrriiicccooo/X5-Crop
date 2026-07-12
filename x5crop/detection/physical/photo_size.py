from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import TYPE_CHECKING

from ...domain import FrameDimensionPrior, MeasurementProvenance
from ...formats import FormatPhysicalSpec
from ...units import ScanCalibration
from x5crop.domain import EvidenceState
from x5crop.domain import PixelInterval, VisibleSequenceSpan

if TYPE_CHECKING:
    from ..evidence.separator_continuity import SeparatorContinuityEvidence
    from .model import SequenceSolution


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
    dimension_residual_max: float | None
    calibration_used: bool


def frame_dimension_prior(
    span: VisibleSequenceSpan,
    physical_spec: FormatPhysicalSpec,
    calibration: ScanCalibration,
    *,
    layout: str,
) -> FrameDimensionPrior:
    short_axis = float(span.box.height)
    options = tuple(
        (float(option.width_mm), float(option.height_mm))
        for option in physical_spec.frame_size_mm_options
    )
    long_ppm = calibration.px_per_mm("x" if layout == "horizontal" else "y")
    short_ppm = calibration.px_per_mm("y" if layout == "horizontal" else "x")
    calibrated = bool(
        calibration.trusted
        and long_ppm is not None
        and short_ppm is not None
        and long_ppm > 0.0
        and short_ppm > 0.0
    )
    if calibrated:
        widths = tuple(width_mm * float(long_ppm) for width_mm, _ in options)
        heights = tuple(height_mm * float(short_ppm) for _, height_mm in options)
    else:
        widths = tuple(
            short_axis * width_mm / height_mm for width_mm, height_mm in options
        )
        heights = (short_axis,)
    return FrameDimensionPrior(
        width_px=PixelInterval(min(widths), max(widths)),
        height_px=PixelInterval(min(heights), max(heights)),
        frame_size_options_mm=options,
        source="scan_calibration" if calibrated else "short_axis_aspect",
        provenance=MeasurementProvenance(
            root_measurement=(
                "scan_calibration" if calibrated else "physical_frame_aspect"
            ),
            source="frame_dimension_prior",
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
    geometry: SequenceSolution,
    continuity: SeparatorContinuityEvidence,
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
    widths = [
        interval.width_px.midpoint
        for interval in geometry.photo_intervals
        if interval.independently_observed
    ]
    return (
        tuple(width for width in widths if width > 0.0),
        tuple(assignment.observation.width for assignment in assignments),
    )


def frame_dimension_evidence(
    geometry: SequenceSolution,
    physical_spec: FormatPhysicalSpec,
    calibration: ScanCalibration,
    continuity: SeparatorContinuityEvidence,
) -> FrameDimensionEvidence:
    nominal = physical_spec.nominal_frame_size_mm
    photo_widths, separator_widths = _photo_widths(
        geometry,
        continuity,
    )
    target = geometry.frame_dimension_prior.width_px.midpoint
    photo_cv = _width_cv(photo_widths)
    separator_cv = _width_cv(separator_widths)
    errors = tuple(
        abs(width - target) / target for width in photo_widths
    )
    maximum_error = max(errors) if errors else None
    observed_width = median(photo_widths) if photo_widths else None
    observed_height = float(geometry.visible_sequence_span.box.height)
    observed_aspect = (
        float(observed_width) / observed_height
        if observed_width is not None
        else None
    )
    nominal_aspect = float(physical_spec.horizontal_content_aspect)
    aspect_error = (
        abs(observed_aspect - nominal_aspect) / nominal_aspect
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
    observed_width_mm = (
        float(observed_width) / float(long_ppm)
        if calibration_used and observed_width is not None
        else None
    )
    observed_height_mm = (
        observed_height / float(short_ppm) if calibration_used else None
    )
    observed_intervals = tuple(
        interval.width_px
        for interval in geometry.photo_intervals
        if interval.independently_observed
    )
    if any(
        not interval.intersects(geometry.frame_dimension_prior.width_px)
        for interval in observed_intervals
    ):
        state = EvidenceState.CONTRADICTED
        reason = "physical_frame_dimensions_contradicted"
    elif photo_widths:
        state = EvidenceState.SUPPORTED
        reason = "photo_dimensions_supported"
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
