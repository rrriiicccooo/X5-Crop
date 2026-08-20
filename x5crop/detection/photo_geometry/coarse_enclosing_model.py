"""Canonical source-wide direction and enclosing-support records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import FiniteInterval, ObservationId
from .model import SPATIAL_SUPPORT_REGION_COUNT


class CoarseSupportSide(str, Enum):
    MINIMUM = "minimum"
    MAXIMUM = "maximum"


@dataclass(frozen=True)
class CoarseSharedDirection:
    """Source-wide straight direction from paired role-free endpoints."""

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
    observation_id: ObservationId
    reference_trace_px: float
    canonical_position_px: float
    fit_position_interval_px: FiniteInterval
    full_position_interval_px: FiniteInterval
    trace_coordinates_px: tuple[int, ...]
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


__all__ = [
    "CoarseEnclosingSupport",
    "CoarseEnclosingTrack",
    "CoarseSharedDirection",
    "CoarseSupportSide",
]
