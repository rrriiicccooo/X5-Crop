from __future__ import annotations

from dataclasses import dataclass, field
import math

from ...domain import (
    EvidenceState,
    FrameDimensionPrior,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from ...formats import FormatSpec
from .model import FrameSequenceSolution


MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS = 2


def width_coefficient_of_variation(
    values: tuple[float, ...],
) -> float | None:
    if len(values) < MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
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
    common_width_px: PixelInterval | None
    measured_width_intervals_px: tuple[PixelInterval, ...]
    separator_widths_px: tuple[float, ...]
    common_width_state: EvidenceState
    observed_aspect: float | None
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)
    frame_aspect: float = field(init=False)
    aspect_error_ratio: float | None = field(init=False)
    measured_widths_px: tuple[float, ...] = field(init=False)
    frame_width_cv: float | None = field(init=False)
    separator_width_cv: float | None = field(init=False)
    dimension_residual_max: float | None = field(init=False)

    def __post_init__(self) -> None:
        if min(self.frame_width_mm, self.frame_height_mm) <= 0.0:
            raise ValueError("physical frame dimensions must be positive")
        if not isinstance(self.common_width_state, EvidenceState):
            raise TypeError("common frame width requires a typed evidence state")
        if self.common_width_state == EvidenceState.SUPPORTED:
            if self.common_width_px is None or self.common_width_px.minimum <= 0.0:
                raise ValueError("supported common frame width must be positive")
        elif self.common_width_px is not None:
            raise ValueError("unresolved common frame width cannot claim a value")
        measured_widths = tuple(
            interval.midpoint for interval in self.measured_width_intervals_px
        )
        if any(
            not math.isfinite(value) or value <= 0.0
            for value in (*measured_widths, *self.separator_widths_px)
        ):
            raise ValueError("measured frame and separator widths must be positive")
        width_contradiction = bool(
            self.common_width_px is not None
            and any(
                not interval.intersects(self.common_width_px)
                for interval in self.measured_width_intervals_px
            )
        )
        frame_aspect = self.frame_width_mm / self.frame_height_mm
        aspect_error_ratio = (
            abs(self.observed_aspect - frame_aspect) / frame_aspect
            if self.observed_aspect is not None
            else None
        )
        if width_contradiction:
            state = EvidenceState.CONTRADICTED
            reason = "common_frame_width_contradicted"
        elif self.common_width_state == EvidenceState.SUPPORTED:
            state = EvidenceState.SUPPORTED
            reason = "common_frame_width_supported"
        else:
            state = EvidenceState.UNAVAILABLE
            reason = "common_frame_width_unavailable"
        residual = (
            max(
                abs(width - self.common_width_px.midpoint)
                / self.common_width_px.midpoint
                for width in measured_widths
            )
            if measured_widths and self.common_width_px is not None
            else None
        )
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "frame_aspect", frame_aspect)
        object.__setattr__(self, "aspect_error_ratio", aspect_error_ratio)
        object.__setattr__(self, "measured_widths_px", measured_widths)
        object.__setattr__(
            self,
            "frame_width_cv",
            width_coefficient_of_variation(measured_widths),
        )
        object.__setattr__(
            self,
            "separator_width_cv",
            width_coefficient_of_variation(self.separator_widths_px),
        )
        object.__setattr__(self, "dimension_residual_max", residual)
        if any(
            value is not None and (not math.isfinite(value) or value < 0.0)
            for value in (self.observed_aspect, aspect_error_ratio, residual)
        ):
            raise ValueError("frame dimension measurements must be finite and non-negative")


def frame_dimension_priors(
    physical_spec: FormatSpec,
) -> tuple[FrameDimensionPrior, ...]:
    options = tuple(
        (float(option.width_mm), float(option.height_mm))
        for option in physical_spec.frame.frame_size_mm_options
    )
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
        observation_id=ObservationId("frame_dimension_prior"),
        dependencies=(MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
        description="physical frame dimension prior",
    )
    priors: list[FrameDimensionPrior] = []
    seen_sizes: set[tuple[float, float]] = set()
    for width_mm, height_mm in options:
        if (width_mm, height_mm) in seen_sizes:
            continue
        seen_sizes.add((width_mm, height_mm))
        priors.append(FrameDimensionPrior((width_mm, height_mm), provenance))
    return tuple(priors)


def frame_dimension_search_priors(
    physical_spec: FormatSpec,
) -> tuple[FrameDimensionPrior, ...]:
    priors = frame_dimension_priors(physical_spec)
    selected: list[FrameDimensionPrior] = []
    seen_aspects: set[float] = set()
    for prior in priors:
        if prior.aspect in seen_aspects:
            continue
        seen_aspects.add(prior.aspect)
        selected.append(prior)
    return tuple(selected)


def frame_dimension_evidence(
    geometry: FrameSequenceSolution,
) -> FrameDimensionEvidence:
    frame_width_mm, frame_height_mm = geometry.frame_dimension_prior.frame_size_mm
    common_width = geometry.common_frame_width
    measured_intervals = tuple(
        constraint.width_px for constraint in common_width.constraints
    )
    observed_aspect = (
        common_width.width_px.midpoint / geometry.shared_short_axis.height_px.midpoint
        if common_width.state == EvidenceState.SUPPORTED
        and geometry.shared_short_axis.supports_safe_crop
        else None
    )
    return FrameDimensionEvidence(
        frame_width_mm=float(frame_width_mm),
        frame_height_mm=float(frame_height_mm),
        common_width_px=common_width.width_px,
        measured_width_intervals_px=measured_intervals,
        separator_widths_px=tuple(
            float(assignment.observation.width_px.midpoint)
            for assignment in sorted(
                geometry.separator_assignments,
                key=lambda assignment: assignment.boundary_index,
            )
        ),
        common_width_state=common_width.state,
        observed_aspect=observed_aspect,
    )


def frame_dimension_measurements_match_geometry(
    geometry: FrameSequenceSolution,
    evidence: FrameDimensionEvidence,
) -> bool:
    return bool(
        evidence.common_width_px == geometry.common_frame_width.width_px
        and evidence.common_width_state == geometry.common_frame_width.state
        and evidence.measured_width_intervals_px
        == tuple(
            constraint.width_px
            for constraint in geometry.common_frame_width.constraints
        )
        and evidence.separator_widths_px
        == tuple(
            float(assignment.observation.width_px.midpoint)
            for assignment in sorted(
                geometry.separator_assignments,
                key=lambda assignment: assignment.boundary_index,
            )
        )
    )
