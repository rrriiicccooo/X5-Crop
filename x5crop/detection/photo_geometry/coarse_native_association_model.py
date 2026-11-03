"""Independent original-peak links and their necessary line constraints."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
import math

from ...domain import FiniteInterval, ObservationId
from .coarse_enclosing_model import CoarseEnclosingTrack, CoarseSupportSide
from .line_observations import PhotoBoundaryObservation, PhysicalLineRegion
from .measurement_model import PhotoBoundaryCoverageReceipt, PhotoBoundaryMeasurementQuery, PhotoBoundaryTransition
from .model import BoundaryRole, PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .trace_support import source_spanning_continuous_trace_support
from .transition_peak_source import TransitionPeakGroupSource, same_transition_peak
from .robust_line_fit import _clip_line_region


class CoarseNativeAssociationUnavailable(ValueError):
    """Independent continuity or a common necessary physical line is absent."""


@dataclass(frozen=True)
class CoarseNativeAssociationWork:
    value_visit_bound: int
    retained_bytes: int
    peak_temporary_bytes: int
    bound_exceeded: bool

    def __post_init__(self) -> None:
        if (any(type(value) is not int or value < 0 for value in (
                self.value_visit_bound, self.retained_bytes, self.peak_temporary_bytes))
                or type(self.bound_exceeded) is not bool
                or self.peak_temporary_bytes < self.retained_bytes
                or self.bound_exceeded and self.retained_bytes):
            raise ValueError("native association lost its bounded work receipt")


@dataclass(frozen=True)
class OriginalPeakCorrespondence:
    coarse_transition: PhotoBoundaryTransition
    native_transition: PhotoBoundaryTransition
    coarse_group: TransitionPeakGroupSource
    native_group: TransitionPeakGroupSource

    def __post_init__(self) -> None:
        coarse, native = self.coarse_transition, self.native_transition
        if (coarse.peak_source is None or native.peak_source is None
                or coarse.trace_coordinate_px != native.trace_coordinate_px
                or coarse.polarity != native.polarity
                or not same_transition_peak(coarse.peak_source, self.coarse_group,
                                            native.peak_source, self.native_group)):
            raise ValueError("coarse/native link changed its complete original peak")


@dataclass(frozen=True)
class NativeLineAlternative:
    kind: str
    identity: str
    role: BoundaryRole
    transition_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if (self.kind not in {"observation", "atom", "family", "membership"}
                or not self.identity or self.role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
                or not self.transition_ids
                or any(not isinstance(item, ObservationId) for item in self.transition_ids)
                or tuple(sorted(set(self.transition_ids), key=str)) != self.transition_ids):
            raise ValueError("native continuation must retain its complete raw union")


@dataclass(frozen=True)
class CoarseNativeLineConstraint:
    association_id: str
    coarse_observation_id: ObservationId
    native_observation_id: ObservationId
    role: BoundaryRole
    trace_coordinates_px: tuple[int, ...]
    trace_position_intervals_px: tuple[FiniteInterval, ...]
    observed_direction_interval_degrees: FiniteInterval
    physical_line_region: PhysicalLineRegion

    def __post_init__(self) -> None:
        if (not self.association_id
                or not isinstance(self.coarse_observation_id, ObservationId)
                or not isinstance(self.native_observation_id, ObservationId)
                or self.role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
                or len(self.trace_coordinates_px) < 3
                or tuple(sorted(set(self.trace_coordinates_px))) != self.trace_coordinates_px
                or len(self.trace_coordinates_px) != len(self.trace_position_intervals_px)
                or any(not isinstance(item, FiniteInterval) for item in self.trace_position_intervals_px)
                or not isinstance(self.observed_direction_interval_degrees, FiniteInterval)
                or not isinstance(self.physical_line_region, PhysicalLineRegion)):
            raise ValueError("associated line lost its independent physical constraints")


@dataclass(frozen=True)
class CoarseNativeLineAssociation:
    """A canonical continuous native line common to every retained continuation.

    This proves additional necessary support constraints. It does not replace
    the coarse observation, grant an aperture role, or select an interpretation.
    The complete base universe and query ledger are re-bound in development
    validation; ordinary reports retain these frozen successful proof inputs.
    """

    coarse_track: CoarseEnclosingTrack
    native_observation: PhotoBoundaryObservation
    native_query: PhotoBoundaryMeasurementQuery
    correspondences: tuple[OriginalPeakCorrespondence, ...]
    alternatives: tuple[NativeLineAlternative, ...]
    native_query_contexts: tuple[PhotoBoundaryMeasurementQuery, ...]
    native_query_coverage: tuple[PhotoBoundaryCoverageReceipt, ...]
    native_trace_peak_inventory: tuple[PhotoBoundaryTransition, ...]

    def __post_init__(self) -> None:
        track, native = self.coarse_track, self.native_observation
        role = BoundaryRole.TOP if track.side == CoarseSupportSide.MINIMUM else BoundaryRole.BOTTOM
        preference = (native.left_background_preference_fraction if role == BoundaryRole.TOP
                      else native.right_background_preference_fraction)
        if (tuple(query.purpose.value for query in self.native_query_contexts) != ("top_corridor", "bottom_corridor")
                or len(self.native_query_coverage) != 2 or self.native_query not in self.native_query_contexts
                or any(query.lane_id != self.native_query.lane_id or coverage.query_id != query.query_id
                       or not coverage.complete for query, coverage in
                       zip(self.native_query_contexts, self.native_query_coverage, strict=True))):
            raise ValueError("native association requires both complete original corridor contexts")
        queries = {query.query_id: query for query in self.native_query_contexts}
        if (len({point.transition_id for point in self.native_trace_peak_inventory}) != len(self.native_trace_peak_inventory)
                or any(point.query_id not in queries or point.trace_coordinate_px not in track.trace_coordinates_px
                       or point.trace_ordinal >= len(queries[point.query_id].trace_positions_px)
                       or queries[point.query_id].trace_positions_px[point.trace_ordinal] != point.trace_coordinate_px
                       for point in self.native_trace_peak_inventory)):
            raise ValueError("native association changed its original cross-corridor peak inventory")
        for link in self.correspondences:
            peak = link.coarse_transition.peak_source
            assert peak is not None
            possible = tuple(point for point in self.native_trace_peak_inventory
                if point.trace_coordinate_px == link.coarse_transition.trace_coordinate_px
                and point.physical_position_interval_px.contains(float(peak.source_coordinate_px)))
            if possible != (link.native_transition,):
                raise CoarseNativeAssociationUnavailable("another corridor peak may name the same coarse source peak")
        if (native.role != role or native.independent_support_region_count < 3
                or preference <= 0.5 or not native.source_spanning_continuous
                or native.physical_line_region is None
                or not source_spanning_continuous_trace_support(
                    self.native_query.trace_positions_px, native.trace_coordinates_px,
                    spec=PHOTO_BOUNDARY_MEASUREMENT_SPEC)
                or tuple(item.coarse_transition for item in self.correspondences) != track.retained_transitions
                or not self.correspondences
                or self.native_query.purpose.value != ("top_corridor" if role == BoundaryRole.TOP else "bottom_corridor")
                or track.trace_coordinates_px[0] < native.trace_coordinates_px[0]
                or track.trace_coordinates_px[-1] > native.trace_coordinates_px[-1]):
            raise CoarseNativeAssociationUnavailable("native association requires independently continuous original support")
        native_ids = frozenset(native.transition_ids)
        mapped = frozenset(item.native_transition.transition_id for item in self.correspondences)
        positions = dict(zip(native.trace_coordinates_px, native.trace_position_intervals_px, strict=True))
        if (len(mapped) != len(self.correspondences) or not mapped.issubset(native_ids)
                or any(positions.get(item.native_transition.trace_coordinate_px)
                       != item.native_transition.physical_position_interval_px for item in self.correspondences)
                or any(item.native_transition.query_id != self.native_query.query_id
                       or item.native_transition.trace_ordinal >= len(self.native_query.trace_positions_px)
                       or self.native_query.trace_positions_px[item.native_transition.trace_ordinal]
                          != item.native_transition.trace_coordinate_px for item in self.correspondences)
                or len({(item.kind, item.identity) for item in self.alternatives}) != len(self.alternatives)
                or not any(item.kind == "observation" and item.identity == str(native.observation_id)
                           and frozenset(item.transition_ids) == native_ids for item in self.alternatives)):
            raise ValueError("native association changed its registered raw inputs")
        if any(mapped.issubset(item.transition_ids) and not native_ids.issubset(item.transition_ids)
               for item in self.alternatives):
            raise CoarseNativeAssociationUnavailable("an alternative continuation lacks the complete necessary line")

    @cached_property
    def constraint(self) -> CoarseNativeLineConstraint:
        native = self.native_observation
        assert native.physical_line_region is not None
        track = self.coarse_track
        low, high = track.full_position_interval_px.minimum, track.full_position_interval_px.maximum
        slopes = tuple(math.tan(math.radians(angle)) for angle in (
            track.full_direction_interval_degrees.minimum, track.full_direction_interval_degrees.maximum))
        vertices = tuple(dict.fromkeys(((low, slopes[0]), (high, slopes[0]),
                                        (high, slopes[1]), (low, slopes[1]))))
        representative_slope = math.tan(math.radians(track.canonical_direction_degrees))
        residual = max((max(interval.minimum - (track.full_position_interval_px.center
                           + representative_slope * (trace - track.reference_trace_px)),
                           track.full_position_interval_px.center
                           + representative_slope * (trace - track.reference_trace_px) - interval.maximum, 0.0)
                        for trace, interval in zip(track.trace_coordinates_px, track.trace_position_intervals_px, strict=True)),
                       default=0.0)
        for traces, intervals, allowance in (
            (track.trace_coordinates_px, track.trace_position_intervals_px, residual),
            (native.trace_coordinates_px, native.trace_position_intervals_px, 0.0),
        ):
            for trace, interval in zip(traces, intervals, strict=True):
                distance = float(trace) - track.reference_trace_px
                vertices = _clip_line_region(vertices, 1.0, distance, interval.maximum + allowance)
                vertices = _clip_line_region(vertices, -1.0, -distance, allowance - interval.minimum)
        if not vertices:
            raise CoarseNativeAssociationUnavailable("independent native support has no same-state coarse line")
        return CoarseNativeLineConstraint(
            association_id=f"coarse-native:{self.coarse_track.observation_id}:{native.observation_id}",
            coarse_observation_id=self.coarse_track.observation_id,
            native_observation_id=native.observation_id,
            role=native.role,
            trace_coordinates_px=native.trace_coordinates_px,
            trace_position_intervals_px=native.trace_position_intervals_px,
            observed_direction_interval_degrees=native.angle_interval_degrees,
            physical_line_region=PhysicalLineRegion(track.reference_trace_px, vertices),
        )
