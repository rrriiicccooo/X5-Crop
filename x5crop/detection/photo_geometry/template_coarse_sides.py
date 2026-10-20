"""Register complete coarse side paths inside the Cross observation budget."""
from __future__ import annotations

from dataclasses import replace

from .coarse_enclosing_model import (CoarseEnclosingSideFact, CoarseEnclosingTrack,
    CoarseSideRegistrationReceipt, CoarseSupportSide, CoarseEnclosingMeasurementBasis)
from .coarse_enclosing_support import (
    _fit_track, _broad_trace_transition, prepare_coarse_enclosing_geometry,
    classify_coarse_enclosing_geometry,
)
from .model import BoundaryRole
from .template_cross_model import CrossRoleBinding


class CoarsePairGeometryPreparation:
    """Bounded raw geometry owned by one complete-member reconstruction."""
    maximum_entries = 256

    def __init__(self):
        self._geometry = {}
        self.lookup_count = 0
        self.preparation_count = 0
        self.retained_bytes = 0

    @staticmethod
    def entry_bytes(left, right):
        return 4096 + 1024 * (len(left.observations) + len(right.observations))

    @classmethod
    def reserve_bytes(cls, facts):
        minimum = tuple(fact for fact in facts if fact.side == CoarseSupportSide.MINIMUM)
        maximum = tuple(fact for fact in facts if fact.side == CoarseSupportSide.MAXIMUM)
        entries = min(cls.maximum_entries, len(minimum) * len(maximum))
        traces = (max((len(fact.observations) for fact in minimum), default=0)
                  + max((len(fact.observations) for fact in maximum), default=0))
        return entries * (4096 + 1024 * traces)

    def prepare(self, left, right, minimum_track, maximum_track, reference_trace_px):
        self.lookup_count += 1
        key = left, right, minimum_track, maximum_track, reference_trace_px
        if key in self._geometry:
            return self._geometry[key]
        self.preparation_count += 1
        geometry = prepare_coarse_enclosing_geometry(left.query,
            minimum_track=minimum_track, maximum_track=maximum_track,
            minimum_transitions=tuple(_broad_trace_transition(left.query, observation=item) for item in left.observations),
            maximum_transitions=tuple(_broad_trace_transition(right.query, observation=item) for item in right.observations),
            reference_trace_px=reference_trace_px)
        if len(self._geometry) < self.maximum_entries:
            self._geometry[key] = geometry
            self.retained_bytes += self.entry_bytes(left, right)
        return geometry

def coarse_enclosing_binding(
    track: CoarseEnclosingTrack,
    role: BoundaryRole,
    *,
    pair_id: str | None = None,
    side_fact: CoarseEnclosingSideFact | None = None,
) -> CrossRoleBinding:
    """Expose a geometric support side without granting aperture authority."""

    return CrossRoleBinding(
        role=role,
        run_id=f"coarse-enclosing:{track.observation_id}",
        observation_id=track.observation_id,
        coordinate_interval_px=track.full_position_interval_px,
        trace_coordinates_px=track.trace_coordinates_px,
        support_fraction=1.0,
        continuous_support_fraction=1.0,
        fit_residual_px=track.fit_residual_px,
        fit_interval_px=track.fit_position_interval_px,
        full_interval_px=track.full_position_interval_px,
        canonical_direction_degrees=track.canonical_direction_degrees,
        fit_direction_interval_degrees=(
            track.fit_direction_interval_degrees
        ),
        full_direction_interval_degrees=(
            track.full_direction_interval_degrees
        ),
        observed_direction_interval_degrees=(
            track.observed_direction_interval_degrees
        ),
        trace_position_intervals_px=track.trace_position_intervals_px,
        independent_support_region_count=(
            track.independent_support_region_count
        ),
        source_spanning_continuous=track.source_spanning_continuous,
        role_authorized=False,
        enclosing_pair_id=pair_id,
        coarse_side_fact=side_fact,
        coarse_side_track=track if side_fact is not None else None,
    )


def register_coarse_side_facts(facts, *, remaining_bound):
    if len(facts) > remaining_bound:
        return (), (), CoarseSideRegistrationReceipt(len(facts), 0, 0, remaining_bound)
    top, bottom = [], []
    for fact in facts:
        transitions = tuple(_broad_trace_transition(fact.query, observation=item)
                            for item in fact.observations)
        track = _fit_track(fact.query, side=fact.side,
            measurement_basis=CoarseEnclosingMeasurementBasis.BROAD_MATERIAL,
            transitions=transitions, reference_trace_px=fact.reference_trace_px)
        if track is None:
            continue
        role = BoundaryRole.TOP if fact.side == CoarseSupportSide.MINIMUM else BoundaryRole.BOTTOM
        binding = coarse_enclosing_binding(track, role, side_fact=fact)
        (top if role == BoundaryRole.TOP else bottom).append(binding)
    return tuple(top), tuple(bottom), CoarseSideRegistrationReceipt(
        len(facts), len(facts), len(top) + len(bottom), remaining_bound)


def close_coarse_side_bindings(top, bottom, *, fixed_height, reference_trace_px,
                              geometry_preparation=None):
    left, right = top.coarse_side_fact, bottom.coarse_side_fact
    if (left is None or right is None or left.query != right.query
            or left.side != CoarseSupportSide.MINIMUM or right.side != CoarseSupportSide.MAXIMUM
            or left.reference_trace_px != reference_trace_px or right.reference_trace_px != reference_trace_px):
        return None
    if geometry_preparation is None:
        geometry = prepare_coarse_enclosing_geometry(left.query,
            minimum_track=top.coarse_side_track, maximum_track=bottom.coarse_side_track,
            minimum_transitions=tuple(_broad_trace_transition(left.query, observation=item) for item in left.observations),
            maximum_transitions=tuple(_broad_trace_transition(right.query, observation=item) for item in right.observations),
            reference_trace_px=reference_trace_px)
    else:
        geometry = geometry_preparation.prepare(left, right, top.coarse_side_track,
                                                bottom.coarse_side_track, reference_trace_px)
    direction, support = classify_coarse_enclosing_geometry(geometry, fixed_height)
    if support is None:
        return None
    pair_id = f"coarse-enclosing-pair:{top.observation_id}:{bottom.observation_id}"
    # Pair-specific geometry retains the original side fact and pre-fit track.
    # It is validated by replaying this proof, not by overwriting registration.
    closed_top = replace(coarse_enclosing_binding(support.minimum_track, BoundaryRole.TOP,
        pair_id=pair_id, side_fact=left), coarse_side_track=top.coarse_side_track)
    closed_bottom = replace(coarse_enclosing_binding(support.maximum_track, BoundaryRole.BOTTOM,
        pair_id=pair_id, side_fact=right), coarse_side_track=bottom.coarse_side_track)
    return closed_top, closed_bottom
