"""Role-free source-wide track geometry and enclosing-support records.

These records may prove local cross geometry but never own a placement axis or
cosmetic output deskew.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .model import SPATIAL_SUPPORT_REGION_COUNT


class CoarseSupportSide(str, Enum):
    MINIMUM = "minimum"
    MAXIMUM = "maximum"


class CoarseEnclosingMeasurementBasis(str, Enum):
    """Pixel observation family that closed one role-free support pair."""

    SHARP_TRANSITION = "sharp_transition"
    BROAD_MATERIAL = "broad_material"


class CoarseEnclosingResolutionFailureKind(str, Enum):
    """Why registered short-axis pixels did not yield one support pair."""

    AGGREGATE_SUPPORT_UNAVAILABLE = "aggregate_support_unavailable"
    PAIR_UNAVAILABLE = "pair_unavailable"
    NON_EQUIVALENT_PAIR_CANDIDATES = (
        "non_equivalent_pair_candidates"
    )


@dataclass(frozen=True)
class CoarseEnclosingCandidateFact:
    """One complete role-free pair from a single observation family."""

    measurement_basis: CoarseEnclosingMeasurementBasis
    minimum_track_observation_id: ObservationId
    maximum_track_observation_id: ObservationId

    def __post_init__(self) -> None:
        if (
            not isinstance(
                self.measurement_basis,
                CoarseEnclosingMeasurementBasis,
            )
            or not isinstance(
                self.minimum_track_observation_id,
                ObservationId,
            )
            or not isinstance(
                self.maximum_track_observation_id,
                ObservationId,
            )
            or self.minimum_track_observation_id
            == self.maximum_track_observation_id
        ):
            raise ValueError("coarse enclosing candidate fact is invalid")


@dataclass(frozen=True)
class CoarseEnclosingResolution:
    """Typed result of the sole sharp/broad support-pair competition."""

    state: EvidenceState
    candidates: tuple[CoarseEnclosingCandidateFact, ...]
    selected_candidate: CoarseEnclosingCandidateFact | None
    failure_kind: CoarseEnclosingResolutionFailureKind | None

    def __post_init__(self) -> None:
        if (
            self.state
            not in {
                EvidenceState.SUPPORTED,
                EvidenceState.UNAVAILABLE,
                EvidenceState.CONTRADICTED,
            }
            or tuple(
                sorted(
                    self.candidates,
                    key=lambda item: item.measurement_basis.value,
                )
            )
            != self.candidates
            or len(
                {
                    item.measurement_basis
                    for item in self.candidates
                }
            )
            != len(self.candidates)
        ):
            raise ValueError("coarse enclosing resolution is invalid")
        supported = self.state == EvidenceState.SUPPORTED
        if supported != (self.selected_candidate is not None):
            raise ValueError(
                "coarse enclosing selected candidate disagrees with state"
            )
        if supported and (
            self.failure_kind is not None
            or self.selected_candidate not in self.candidates
            or len(self.candidates) not in {1, 2}
            or (
                len(self.candidates) == 2
                and self.selected_candidate.measurement_basis
                != CoarseEnclosingMeasurementBasis.SHARP_TRANSITION
            )
        ):
            raise ValueError("supported coarse enclosing resolution is invalid")
        if not supported and not isinstance(
            self.failure_kind,
            CoarseEnclosingResolutionFailureKind,
        ):
            raise ValueError("failed coarse enclosing resolution needs a kind")
        if (
            self.state == EvidenceState.CONTRADICTED
        ) != (
            self.failure_kind
            == CoarseEnclosingResolutionFailureKind
            .NON_EQUIVALENT_PAIR_CANDIDATES
        ):
            raise ValueError("coarse enclosing contradiction is inconsistent")
        if self.state == EvidenceState.UNAVAILABLE and self.candidates:
            raise ValueError("unavailable enclosing resolution has candidates")
        if self.state == EvidenceState.CONTRADICTED and len(self.candidates) != 2:
            raise ValueError("enclosing contradiction requires two candidates")


@dataclass(frozen=True)
class CoarseSharedDirection:
    """Source-wide track direction from paired role-free endpoints."""

    direction_id: str
    observation_ids: tuple[ObservationId, ...]
    canonical_direction_degrees: float
    fit_direction_interval_degrees: FiniteInterval
    full_direction_interval_degrees: FiniteInterval
    observed_direction_interval_degrees: FiniteInterval
    trace_coordinates_px: tuple[int, ...]

    def __post_init__(self) -> None:
        if (
            not self.direction_id
            or len(self.observation_ids) != 2
            or len(set(self.observation_ids)) != 2
            or tuple(sorted(set(self.trace_coordinates_px)))
            != self.trace_coordinates_px
            or not self.fit_direction_interval_degrees.contains(
                self.canonical_direction_degrees,
                epsilon=1.0e-9,
            )
            or not self.full_direction_interval_degrees.contains(
                self.fit_direction_interval_degrees.minimum,
                epsilon=1.0e-9,
            )
            or not self.full_direction_interval_degrees.contains(
                self.fit_direction_interval_degrees.maximum,
                epsilon=1.0e-9,
            )
            or not self.observed_direction_interval_degrees.contains(
                self.full_direction_interval_degrees.minimum,
                epsilon=1.0e-9,
            )
            or not self.observed_direction_interval_degrees.contains(
                self.full_direction_interval_degrees.maximum,
                epsilon=1.0e-9,
            )
        ):
            raise ValueError("coarse shared direction is invalid")


@dataclass(frozen=True)
class CoarseEnclosingTrack:
    """One role-free physical side track in short-axis coordinates."""

    side: CoarseSupportSide
    measurement_basis: CoarseEnclosingMeasurementBasis
    observation_id: ObservationId
    reference_trace_px: float
    canonical_position_px: float
    fit_position_interval_px: FiniteInterval
    full_position_interval_px: FiniteInterval
    trace_coordinates_px: tuple[int, ...]
    support_trace_coordinates_px: tuple[int, ...]
    canonical_direction_degrees: float
    fit_direction_interval_degrees: FiniteInterval
    full_direction_interval_degrees: FiniteInterval
    observed_direction_interval_degrees: FiniteInterval
    trace_position_intervals_px: tuple[FiniteInterval, ...]
    fit_residual_px: float
    independent_support_region_count: int
    source_spanning_continuous: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.side, CoarseSupportSide)
            or not isinstance(
                self.measurement_basis,
                CoarseEnclosingMeasurementBasis,
            )
            or not math.isfinite(self.reference_trace_px)
            or not self.fit_position_interval_px.contains(
                self.canonical_position_px,
                epsilon=1.0e-9,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.minimum,
                epsilon=1.0e-9,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.maximum,
                epsilon=1.0e-9,
            )
            or tuple(sorted(set(self.trace_coordinates_px)))
            != self.trace_coordinates_px
            or tuple(sorted(set(self.support_trace_coordinates_px)))
            != self.support_trace_coordinates_px
            or not set(self.trace_coordinates_px).issubset(
                self.support_trace_coordinates_px
            )
            or len(self.trace_position_intervals_px)
            != len(self.trace_coordinates_px)
            or self.independent_support_region_count
            != SPATIAL_SUPPORT_REGION_COUNT
            or not self.source_spanning_continuous
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or not self.fit_direction_interval_degrees.contains(
                self.canonical_direction_degrees,
                epsilon=1.0e-9,
            )
            or not self.full_direction_interval_degrees.contains(
                self.fit_direction_interval_degrees.minimum,
                epsilon=1.0e-9,
            )
            or not self.full_direction_interval_degrees.contains(
                self.fit_direction_interval_degrees.maximum,
                epsilon=1.0e-9,
            )
            or not self.observed_direction_interval_degrees.contains(
                self.full_direction_interval_degrees.minimum,
                epsilon=1.0e-9,
            )
            or not self.observed_direction_interval_degrees.contains(
                self.full_direction_interval_degrees.maximum,
                epsilon=1.0e-9,
            )
        ):
            raise ValueError("coarse enclosing track is invalid")


@dataclass(frozen=True)
class CoarseEnclosingSupport:
    """One directly observed outer rectangle, distinct from the aperture."""

    minimum_track: CoarseEnclosingTrack
    maximum_track: CoarseEnclosingTrack
    observed_span_px: FiniteInterval
    evaluated_trace_count: int

    def __post_init__(self) -> None:
        if (
            self.minimum_track.side != CoarseSupportSide.MINIMUM
            or self.maximum_track.side != CoarseSupportSide.MAXIMUM
            or self.minimum_track.measurement_basis
            != self.maximum_track.measurement_basis
            or self.minimum_track.trace_coordinates_px
            != self.maximum_track.trace_coordinates_px
            or self.minimum_track.canonical_direction_degrees
            != self.maximum_track.canonical_direction_degrees
            or self.minimum_track.fit_direction_interval_degrees
            != self.maximum_track.fit_direction_interval_degrees
            or self.minimum_track.full_direction_interval_degrees
            != self.maximum_track.full_direction_interval_degrees
            or self.observed_span_px
            != FiniteInterval(
                self.maximum_track.full_position_interval_px.minimum
                - self.minimum_track.full_position_interval_px.maximum,
                self.maximum_track.full_position_interval_px.maximum
                - self.minimum_track.full_position_interval_px.minimum,
            )
            or self.observed_span_px.minimum <= 0.0
            or self.evaluated_trace_count
            < len(self.minimum_track.trace_coordinates_px)
        ):
            raise ValueError("coarse enclosing support is invalid")
