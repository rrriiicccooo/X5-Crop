"""Necessary line states of one independently connected native Sequence edge."""
from dataclasses import dataclass
from functools import cached_property

from ...domain import FiniteInterval, ObservationId
from .line_observations import PhysicalLineRegion


@dataclass(frozen=True)
class SequenceConnectionConstraint:
    observation_id: ObservationId
    query_id: str
    original_transition_ids: tuple[ObservationId, ...]
    original_physical_line_region: PhysicalLineRegion
    trace_coordinates_px: tuple[int, ...]
    trace_position_intervals_px: tuple[FiniteInterval, ...]
    position_protection_interval_px: FiniteInterval

    def __post_init__(self):
        if (not isinstance(self.observation_id, ObservationId) or not self.query_id
                or not self.original_transition_ids or len(set(self.original_transition_ids)) != len(self.original_transition_ids)
                or not isinstance(self.original_physical_line_region, PhysicalLineRegion)
                or len(self.trace_coordinates_px) < 2
                or tuple(sorted(set(self.trace_coordinates_px))) != self.trace_coordinates_px
                or any(type(t) is not int for t in self.trace_coordinates_px)
                or any(b != a+1 for a,b in zip(self.trace_coordinates_px,self.trace_coordinates_px[1:]))
                or len(self.trace_coordinates_px) != len(self.trace_position_intervals_px)
                or any(not isinstance(p,FiniteInterval) for p in self.trace_position_intervals_px)
                or not isinstance(self.position_protection_interval_px,FiniteInterval)):
            raise ValueError("Sequence connection lost its complete original native span")

    @cached_property
    def physical_line_region(self):
        from .robust_line_fit import _clip_line_region
        original = self.original_physical_line_region
        vertices = original.vertices
        for trace, interval in zip(self.trace_coordinates_px,self.trace_position_intervals_px,strict=True):
            distance = trace-original.reference_trace_px
            vertices = _clip_line_region(vertices,1.,distance,interval.maximum)
            vertices = _clip_line_region(vertices,-1.,-distance,-interval.minimum)
            if not vertices:
                raise ValueError("Sequence connection has no common native line state")
        return PhysicalLineRegion(original.reference_trace_px,vertices)

    @cached_property
    def raw_position_interval_px(self):
        return FiniteInterval(min(p.minimum for p in self.trace_position_intervals_px),
                              max(p.maximum for p in self.trace_position_intervals_px))


@dataclass(frozen=True)
class SequenceConnectionWork:
    value_visit_bound: int = 0
    pixel_query_count: int = 0
    retained_bytes: int = 0
    peak_temporary_bytes: int = 0
    persistent_input_bytes: int = 0
    bound_exceeded: bool = False

    def __post_init__(self):
        if (any(type(v) is not int or v < 0 for v in (self.value_visit_bound,self.pixel_query_count,
                self.retained_bytes,self.peak_temporary_bytes,self.persistent_input_bytes))
                or type(self.bound_exceeded) is not bool or self.retained_bytes > self.peak_temporary_bytes):
            raise ValueError("Sequence connection lost its complete work reservation")


@dataclass(frozen=True)
class SequenceConnectionBudget:
    maximum_value_visits: int
    maximum_temporary_bytes: int
    persistent_input_bytes: int

    def __post_init__(self):
        if any(type(v) is not int or v < 0 for v in (
                self.maximum_value_visits,self.maximum_temporary_bytes,self.persistent_input_bytes)):
            raise ValueError("Sequence connection requires its frozen remaining source pool")
