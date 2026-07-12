from __future__ import annotations

from dataclasses import dataclass, field
import math
from statistics import median
from typing import TYPE_CHECKING

from ...domain import (
    FrameDimensionPrior,
    FrameDimensionPriorSource,
    MeasurementIdentity,
    MeasurementProvenance,
)
from ...formats import FormatPhysicalSpec
from ...geometry.layout import is_horizontal_layout
from ...units import ScanCalibration
from x5crop.domain import EvidenceState
from x5crop.domain import PixelInterval, VisibleSequenceSpan

if TYPE_CHECKING:
    from .model import PhotoInterval, SequenceSolution


def width_coefficient_of_variation(
    values: tuple[float, ...],
) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    if mean <= 0.0:
        return None
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return (variance ** 0.5) / mean


@dataclass(frozen=True)
class FrameDimensionEvidence:
    frame_width_mm: float
    frame_height_mm: float
    frame_width_prior_px: PixelInterval
    photo_width_intervals_px: tuple[PixelInterval, ...]
    separator_widths_px: tuple[float, ...]
    observed_width_mm: float | None
    observed_height_mm: float | None
    observed_aspect: float | None
    aspect_error_ratio: float | None
    calibration_used: bool
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)
    frame_aspect: float = field(init=False)
    photo_widths_px: tuple[float, ...] = field(init=False)
    photo_width_cv: float | None = field(init=False)
    separator_width_cv: float | None = field(init=False)
    dimension_residual_max: float | None = field(init=False)

    def __post_init__(self) -> None:
        if min(self.frame_width_mm, self.frame_height_mm) <= 0.0:
            raise ValueError("physical frame dimensions must be positive")
        if self.frame_width_prior_px.minimum <= 0.0:
            raise ValueError("frame width prior must be positive")
        photo_widths = tuple(
            interval.midpoint for interval in self.photo_width_intervals_px
        )
        if any(
            not math.isfinite(value) or value <= 0.0
            for value in (*photo_widths, *self.separator_widths_px)
        ):
            raise ValueError("measured frame and separator widths must be positive")
        contradicted = any(
            not interval.intersects(self.frame_width_prior_px)
            for interval in self.photo_width_intervals_px
        )
        state = (
            EvidenceState.CONTRADICTED
            if contradicted
            else EvidenceState.SUPPORTED
            if photo_widths
            else EvidenceState.UNAVAILABLE
        )
        reason = (
            "physical_frame_dimensions_contradicted"
            if contradicted
            else "photo_dimensions_supported"
            if photo_widths
            else "independent_photo_edge_measurements_unavailable"
        )
        frame_aspect = self.frame_width_mm / self.frame_height_mm
        dimension_residual = (
            max(
                abs(width - self.frame_width_prior_px.midpoint)
                / max(1.0, self.frame_width_prior_px.midpoint)
                for width in photo_widths
            )
            if photo_widths
            else None
        )
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "frame_aspect", frame_aspect)
        object.__setattr__(self, "photo_widths_px", photo_widths)
        object.__setattr__(
            self,
            "photo_width_cv",
            width_coefficient_of_variation(photo_widths),
        )
        object.__setattr__(
            self,
            "separator_width_cv",
            width_coefficient_of_variation(self.separator_widths_px),
        )
        object.__setattr__(self, "dimension_residual_max", dimension_residual)
        optional_nonnegative = (
            self.observed_width_mm,
            self.observed_height_mm,
            self.observed_aspect,
            self.aspect_error_ratio,
            dimension_residual,
        )
        if any(
            value is not None and (not math.isfinite(value) or value < 0.0)
            for value in optional_nonnegative
        ):
            raise ValueError("frame dimension measurements must be finite and non-negative")
        if self.observed_aspect is not None:
            expected_error = (
                abs(self.observed_aspect - frame_aspect)
                / frame_aspect
            )
            if self.aspect_error_ratio != expected_error:
                raise ValueError("frame aspect error must derive from measured aspect")
        if self.calibration_used:
            if self.observed_height_mm is None or (
                photo_widths and self.observed_width_mm is None
            ):
                raise ValueError("calibrated dimensions require millimeter measurements")
        elif self.observed_width_mm is not None or self.observed_height_mm is not None:
            raise ValueError("millimeter dimensions require trusted calibration")


def frame_dimension_priors(
    span: VisibleSequenceSpan,
    physical_spec: FormatPhysicalSpec,
    calibration: ScanCalibration,
    *,
    layout: str,
) -> tuple[FrameDimensionPrior, ...]:
    horizontal = is_horizontal_layout(layout)
    short_axis = float(span.box.height)
    options = tuple(
        (float(option.width_mm), float(option.height_mm))
        for option in physical_spec.frame_size_mm_options
    )
    long_ppm = calibration.px_per_mm("x" if horizontal else "y")
    short_ppm = calibration.px_per_mm("y" if horizontal else "x")
    calibrated = bool(
        calibration.trusted
        and long_ppm is not None
        and short_ppm is not None
        and long_ppm > 0.0
        and short_ppm > 0.0
    )
    provenance = MeasurementProvenance(
        root_measurement=(
            MeasurementIdentity.SCAN_CALIBRATION
            if calibrated
            else MeasurementIdentity.PHYSICAL_FRAME_ASPECT
        ),
        source="frame_dimension_prior",
        dependencies=(
            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
            (
                MeasurementIdentity.SCAN_CALIBRATION
                if calibrated
                else MeasurementIdentity.SHORT_AXIS_BOUNDARIES
            ),
        ),
    )
    priors: list[FrameDimensionPrior] = []
    seen_pixel_sizes: set[tuple[PixelInterval, PixelInterval]] = set()
    for width_mm, height_mm in options:
        width_px = PixelInterval.exact(
            width_mm * float(long_ppm)
            if calibrated
            else short_axis * width_mm / height_mm
        )
        height_px = PixelInterval.exact(
            height_mm * float(short_ppm) if calibrated else short_axis
        )
        pixel_size = (width_px, height_px)
        if pixel_size in seen_pixel_sizes:
            continue
        seen_pixel_sizes.add(pixel_size)
        priors.append(
            FrameDimensionPrior(
                width_px=width_px,
                height_px=height_px,
                frame_size_mm=(width_mm, height_mm),
                source=(
                    FrameDimensionPriorSource.SCAN_CALIBRATION
                    if calibrated
                    else FrameDimensionPriorSource.SHORT_AXIS_ASPECT
                ),
                provenance=provenance,
            )
        )
    return tuple(priors)


def _photo_widths(
    geometry: SequenceSolution,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    assignments = tuple(
        sorted(
            (
                assignment
                for assignment in geometry.separator_assignments
                if assignment.used_for_boundary and assignment.independent
            ),
            key=lambda assignment: assignment.boundary_index,
        )
    )
    widths = [
        interval.width_px.midpoint
        for interval in _dimension_photo_intervals(geometry)
    ]
    return (
        tuple(width for width in widths if width > 0.0),
        tuple(assignment.observation.width for assignment in assignments),
    )


def _dimension_photo_intervals(
    geometry: SequenceSolution,
) -> tuple[PhotoInterval, ...]:
    leading_occluded = (
        geometry.holder_occlusion.leading.hidden_width_px.maximum > 0.0
    )
    trailing_occluded = (
        geometry.holder_occlusion.trailing.hidden_width_px.maximum > 0.0
    )
    return tuple(
        interval
        for interval in geometry.photo_intervals
        if interval.independently_observed
        and not (interval.index == 1 and leading_occluded)
        and not (interval.index == geometry.count and trailing_occluded)
    )


def frame_dimension_evidence(
    geometry: SequenceSolution,
    calibration: ScanCalibration,
) -> FrameDimensionEvidence:
    horizontal = is_horizontal_layout(geometry.layout)
    frame_width_mm, frame_height_mm = geometry.frame_dimension_prior.frame_size_mm
    photo_widths, separator_widths = _photo_widths(
        geometry,
    )
    observed_width = median(photo_widths) if photo_widths else None
    observed_height = float(geometry.visible_sequence_span.box.height)
    observed_aspect = (
        float(observed_width) / observed_height
        if observed_width is not None
        else None
    )
    frame_aspect = float(frame_width_mm) / float(frame_height_mm)
    aspect_error = (
        abs(observed_aspect - frame_aspect) / frame_aspect
        if observed_aspect is not None
        else None
    )
    long_ppm = calibration.px_per_mm(
        "x" if horizontal else "y"
    )
    short_ppm = calibration.px_per_mm(
        "y" if horizontal else "x"
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
        interval.width_px for interval in _dimension_photo_intervals(geometry)
    )
    return FrameDimensionEvidence(
        frame_width_mm=float(frame_width_mm),
        frame_height_mm=float(frame_height_mm),
        frame_width_prior_px=geometry.frame_dimension_prior.width_px,
        photo_width_intervals_px=observed_intervals,
        separator_widths_px=tuple(float(width) for width in separator_widths),
        observed_width_mm=observed_width_mm,
        observed_height_mm=observed_height_mm,
        observed_aspect=observed_aspect,
        aspect_error_ratio=aspect_error,
        calibration_used=calibration_used,
    )
