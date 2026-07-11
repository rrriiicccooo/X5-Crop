from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, TYPE_CHECKING

from ...domain import SeparatorBandObservation
from ...gap_methods import is_hard_gap_method
from ...geometry.gap_geometry import (
    measured_photo_widths_from_gap_edges,
    separator_widths,
    width_cv,
)
from ...geometry.separator_band import SeparatorBand
from ...units import ScanCalibration
from ..evidence.state import EvidenceState

if TYPE_CHECKING:
    from ...formats import FormatPhysicalSpec
    from ..geometry import CandidateGeometry


@dataclass(frozen=True)
class PhotoSizeConsistency:
    used: bool
    reason: str
    photo_widths: tuple[float, ...] = ()
    separator_widths: tuple[float, ...] = ()
    photo_width_cv: float | None = None
    separator_width_cv: float | None = None
    mean_photo_width_error_ratio: float | None = None
    max_photo_width_error_ratio: float | None = None

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

def frame_dimension_evidence(
    geometry: CandidateGeometry,
    physical_spec: FormatPhysicalSpec,
    calibration: ScanCalibration,
    *,
    separator_observations: tuple[SeparatorBandObservation, ...],
    maximum_photo_width_cv: float,
    maximum_dimension_error_ratio: float,
) -> FrameDimensionEvidence:
    nominal = physical_spec.nominal_frame_size_mm
    target_photo_width = (
        float(geometry.visible_sequence_span.box.height)
        * float(physical_spec.horizontal_content_aspect)
    )
    consistency = photo_size_consistency_from_gap_edges(
        list(separator_observations),
        geometry.origin,
        geometry.pitch,
        geometry.count,
        target_photo_width=target_photo_width,
    )
    long_axis_ppm = calibration.px_per_mm(
        "x" if geometry.layout == "horizontal" else "y"
    )
    short_axis_ppm = calibration.px_per_mm(
        "y" if geometry.layout == "horizontal" else "x"
    )
    observed_width_mm = None
    observed_height_mm = None
    observed_aspect = (
        float(geometry.visible_sequence_span.box.width)
        / max(1.0, float(geometry.visible_sequence_span.box.height))
    )
    aspect_error_ratio = abs(
        observed_aspect - float(physical_spec.horizontal_content_aspect)
    ) / max(1e-6, float(physical_spec.horizontal_content_aspect))
    calibration_used = bool(
        calibration.trusted
        and long_axis_ppm is not None
        and short_axis_ppm is not None
    )
    if calibration_used:
        observed_width_mm = float(geometry.visible_sequence_span.box.width) / float(
            long_axis_ppm
        )
        observed_height_mm = float(geometry.visible_sequence_span.box.height) / float(
            short_axis_ppm
        )
    dimension_errors: list[float] = []
    if geometry.count == 1:
        dimension_errors.append(aspect_error_ratio)
        if calibration_used:
            dimension_errors.extend((
                abs(float(observed_width_mm) - float(nominal.width_mm))
                / max(1e-6, float(nominal.width_mm)),
                abs(float(observed_height_mm) - float(nominal.height_mm))
                / max(1e-6, float(nominal.height_mm)),
            ))
    elif consistency.max_photo_width_error_ratio is not None:
        dimension_errors.append(
            float(consistency.max_photo_width_error_ratio)
        )
    maximum_error = max(dimension_errors) if dimension_errors else None

    width_contradicted = bool(
        consistency.photo_width_cv is not None
        and float(consistency.photo_width_cv) > float(maximum_photo_width_cv)
    )
    dimension_contradicted = bool(
        maximum_error is not None
        and maximum_error > float(maximum_dimension_error_ratio)
    )
    if width_contradicted:
        state = EvidenceState.CONTRADICTED
        reason = "photo_widths_inconsistent"
    elif dimension_contradicted:
        state = EvidenceState.CONTRADICTED
        reason = "physical_frame_dimensions_contradicted"
    elif geometry.count == 1 and calibration_used:
        state = EvidenceState.SUPPORTED
        reason = "single_frame_dimensions_supported_by_calibration"
    elif geometry.count == 1:
        state = EvidenceState.SUPPORTED
        reason = "single_frame_aspect_supported"
    elif consistency.used:
        state = EvidenceState.SUPPORTED
        reason = "photo_widths_consistent"
    else:
        state = EvidenceState.UNAVAILABLE
        reason = consistency.reason
    return FrameDimensionEvidence(
        state=state,
        reason=reason,
        nominal_width_mm=float(nominal.width_mm),
        nominal_height_mm=float(nominal.height_mm),
        nominal_aspect=float(physical_spec.horizontal_content_aspect),
        photo_widths_px=tuple(consistency.photo_widths),
        photo_width_cv=consistency.photo_width_cv,
        separator_widths_px=tuple(consistency.separator_widths),
        separator_width_cv=consistency.separator_width_cv,
        observed_width_mm=observed_width_mm,
        observed_height_mm=observed_height_mm,
        observed_aspect=observed_aspect,
        aspect_error_ratio=aspect_error_ratio,
        maximum_dimension_error_ratio=maximum_error,
        calibration_used=calibration_used,
    )

def _photo_width_error_ratios(
    widths: Sequence[float],
    target_photo_width: float | None,
) -> tuple[float | None, float | None]:
    if not widths or target_photo_width is None or target_photo_width <= 1.0:
        return None, None
    ratios = [
        abs(float(width) - float(target_photo_width)) / max(1.0, float(target_photo_width))
        for width in widths
    ]
    return float(sum(ratios) / len(ratios)), float(max(ratios))


def photo_size_consistency_from_gap_edges(
    gaps: list[SeparatorBandObservation],
    origin: float,
    pitch: float,
    count: int,
    *,
    target_photo_width: float | None = None,
) -> PhotoSizeConsistency:
    if count <= 0 or pitch <= 0.0:
        return PhotoSizeConsistency(False, "invalid_count_or_pitch")
    if count == 1:
        return PhotoSizeConsistency(
            False,
            "single_frame_requires_independent_boundaries",
        )
    hard_gaps = [gap for gap in gaps if is_hard_gap_method(gap.method)]
    photo_widths = measured_photo_widths_from_gap_edges(
        hard_gaps,
        origin,
        pitch,
        count,
    )
    if photo_widths is None:
        return PhotoSizeConsistency(
            False,
            "insufficient_edge_bounded_photo_measurements",
            separator_widths=tuple(separator_widths(hard_gaps)),
            separator_width_cv=width_cv(separator_widths(hard_gaps)),
        )
    separator_values = tuple(separator_widths(hard_gaps))
    mean_error, max_error = _photo_width_error_ratios(photo_widths, target_photo_width)
    return PhotoSizeConsistency(
        True,
        "ok",
        photo_widths=tuple(float(width) for width in photo_widths),
        separator_widths=separator_values,
        photo_width_cv=width_cv(photo_widths),
        separator_width_cv=width_cv(separator_values),
        mean_photo_width_error_ratio=mean_error,
        max_photo_width_error_ratio=max_error,
    )


def photo_size_consistency_from_separator_bands(
    bands: Sequence[SeparatorBand],
    *,
    target_photo_width: float,
) -> PhotoSizeConsistency:
    if len(bands) < 2:
        return PhotoSizeConsistency(
            False,
            "too_few_separator_bands",
            separator_widths=tuple(float(band.width) for band in bands),
        )
    photo_widths: list[float] = []
    previous = bands[0]
    for band in bands[1:]:
        width = float(band.start) - float(previous.end)
        if width <= 1.0:
            return PhotoSizeConsistency(
                False,
                "non_positive_photo_interval",
                separator_widths=tuple(float(item.width) for item in bands),
            )
        photo_widths.append(width)
        previous = band
    separator_values = tuple(float(band.width) for band in bands)
    mean_error, max_error = _photo_width_error_ratios(photo_widths, target_photo_width)
    return PhotoSizeConsistency(
        True,
        "ok",
        photo_widths=tuple(photo_widths),
        separator_widths=separator_values,
        photo_width_cv=width_cv(photo_widths),
        separator_width_cv=width_cv(separator_values),
        mean_photo_width_error_ratio=mean_error,
        max_photo_width_error_ratio=max_error,
    )
