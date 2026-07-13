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
    ObservationId,
)
from ...formats import FormatPhysicalSpec
from ...geometry.layout import is_horizontal_layout
from ...units import ScanCalibrationResolution
from x5crop.domain import EvidenceState
from x5crop.domain import PixelInterval

if TYPE_CHECKING:
    from .model import PhotoSequenceSolution
    from ...domain import PhotoAperture


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
            raise ValueError("millimeter dimensions require supported calibration")


def frame_dimension_priors(
    physical_spec: FormatPhysicalSpec,
    calibration: ScanCalibrationResolution,
    *,
    layout: str,
) -> tuple[FrameDimensionPrior, ...]:
    horizontal = is_horizontal_layout(layout)
    options = tuple(
        (float(option.width_mm), float(option.height_mm))
        for option in physical_spec.frame_size_mm_options
    )
    long_ppm = calibration.px_per_mm("x" if horizontal else "y")
    short_ppm = calibration.px_per_mm("y" if horizontal else "x")
    calibrated = bool(
        calibration.fully_supported
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
        observation_id=ObservationId("frame_dimension_prior"),
        dependencies=(
            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
            *(
                (MeasurementIdentity.SCAN_CALIBRATION,)
                if calibrated
                else ()
            ),
        ),
        description="physical frame dimension prior",
    )
    priors: list[FrameDimensionPrior] = []
    seen_sizes: set[tuple[float, float]] = set()
    for width_mm, height_mm in options:
        if (width_mm, height_mm) in seen_sizes:
            continue
        seen_sizes.add((width_mm, height_mm))
        priors.append(
            FrameDimensionPrior(
                frame_size_mm=(width_mm, height_mm),
                source=(
                    FrameDimensionPriorSource.SCAN_CALIBRATION
                    if calibrated
                    else FrameDimensionPriorSource.PHYSICAL_ASPECT
                ),
                provenance=provenance,
                calibrated_width_px=(
                    PixelInterval.exact(width_mm * float(long_ppm))
                    if calibrated
                    else None
                ),
                calibrated_height_px=(
                    PixelInterval.exact(height_mm * float(short_ppm))
                    if calibrated
                    else None
                ),
            )
        )
    return tuple(priors)


def _photo_widths(
    geometry: PhotoSequenceSolution,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    assignments = tuple(
        sorted(
            geometry.separator_assignments,
            key=lambda assignment: assignment.boundary_index,
        )
    )
    widths = [
        aperture.trailing.position.minus(aperture.leading.position).midpoint
        for aperture in dimension_photo_apertures(geometry)
    ]
    return (
        tuple(width for width in widths if width > 0.0),
        tuple(assignment.observation.width for assignment in assignments),
    )


def dimension_photo_apertures(
    geometry: PhotoSequenceSolution,
) -> tuple[PhotoAperture, ...]:
    width_prior = geometry.photo_width_constraint_px
    return tuple(
        aperture
        for aperture in geometry.photo_apertures
        if aperture.leading.independently_observed
        and aperture.trailing.independently_observed
        and (
            1 < aperture.index < geometry.count
            or aperture.trailing.position.minus(aperture.leading.position).intersects(
                width_prior
            )
        )
    )


def frame_dimension_evidence(
    geometry: PhotoSequenceSolution,
    calibration: ScanCalibrationResolution,
) -> FrameDimensionEvidence:
    horizontal = is_horizontal_layout(geometry.layout)
    frame_width_mm, frame_height_mm = geometry.frame_dimension_prior.frame_size_mm
    photo_widths, separator_widths = _photo_widths(
        geometry,
    )
    observed_width = median(photo_widths) if photo_widths else None
    measured_heights = tuple(
        aperture.bottom.position.minus(aperture.top.position).midpoint
        for aperture in geometry.photo_apertures
        if aperture.top.independently_observed
        and aperture.bottom.independently_observed
    )
    observed_height = median(measured_heights) if measured_heights else None
    observed_aspect = (
        float(observed_width) / observed_height
        if observed_width is not None and observed_height is not None
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
        calibration.fully_supported
        and long_ppm is not None
        and short_ppm is not None
        and long_ppm > 0.0
        and short_ppm > 0.0
        and observed_height is not None
    )
    observed_width_mm = (
        float(observed_width) / float(long_ppm)
        if calibration_used and observed_width is not None
        else None
    )
    observed_height_mm = (
        observed_height / float(short_ppm)
        if calibration_used and observed_height is not None
        else None
    )
    observed_intervals = tuple(
        aperture.trailing.position.minus(aperture.leading.position)
        for aperture in dimension_photo_apertures(geometry)
    )
    return FrameDimensionEvidence(
        frame_width_mm=float(frame_width_mm),
        frame_height_mm=float(frame_height_mm),
        frame_width_prior_px=geometry.photo_width_constraint_px,
        photo_width_intervals_px=observed_intervals,
        separator_widths_px=tuple(float(width) for width in separator_widths),
        observed_width_mm=observed_width_mm,
        observed_height_mm=observed_height_mm,
        observed_aspect=observed_aspect,
        aspect_error_ratio=aspect_error,
        calibration_used=calibration_used,
    )


def frame_dimension_measurements_match_geometry(
    geometry: PhotoSequenceSolution,
    evidence: FrameDimensionEvidence,
) -> bool:
    _, separator_widths = _photo_widths(geometry)
    observed_intervals = tuple(
        aperture.trailing.position.minus(aperture.leading.position)
        for aperture in dimension_photo_apertures(geometry)
    )
    return bool(
        evidence.photo_width_intervals_px == observed_intervals
        and evidence.separator_widths_px
        == tuple(float(width) for width in separator_widths)
    )
