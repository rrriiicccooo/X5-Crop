"""Merge local short-axis observations into finite physical edge families."""

from __future__ import annotations

from itertools import combinations

from ...domain import FiniteInterval, ObservationId
from .boundary_fitting import fit_format_bound_boundary_observation
from .chain_proposals import LaneObservationInput
from .cross_edge_projection import (
    line_boundary_coordinate,
    observation_coordinate_interval,
)
from .interval_math import subtract
from .model import (
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
)
from .measurement_model import PhotoBoundaryMeasurementSet
from .line_observations import PhotoBoundaryObservation
from .observation_types import ProfileRun
from .physical_identity import physical_fact_id
from .source_geometry import SourceScanGeometry
from .trace_support import PIXEL_CENTER_HALF_EXTENT_PX


def _observation_supports_fitted_family(
    lane: LaneObservationInput,
    measurement_set: PhotoBoundaryMeasurementSet,
    member: PhotoBoundaryObservation,
    fitted_family: PhotoBoundaryObservation,
    support_interval_px: FiniteInterval | None,
) -> bool:
    member_ids = {str(identity) for identity in member.transition_ids}
    selected_ids = {str(identity) for identity in fitted_family.transition_ids}
    supporting_traces = tuple(
        transition.trace_coordinate_px
        for transition in measurement_set.transitions
        if str(transition.transition_id) in member_ids & selected_ids
        and (
            support_interval_px is None
            or support_interval_px.contains(
                float(transition.trace_coordinate_px),
                epsilon=PIXEL_CENTER_HALF_EXTENT_PX,
            )
        )
        and transition.physical_position_interval_px.contains(
            line_boundary_coordinate(
                fitted_family,
                boundary_axis=lane.height_axis,
                trace_coordinate_px=float(transition.trace_coordinate_px),
            ),
            epsilon=(
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.inlier_minimum_threshold_mm
                * lane.height_scale_px_per_mm.maximum
            ),
        )
    )
    return len(set(supporting_traces)) >= 2


def merged_cross_edge_families(
    lane: LaneObservationInput,
    geometry: SourceScanGeometry,
    role: BoundaryRole,
    values: list[tuple[ProfileRun, PhotoBoundaryObservation, FiniteInterval]],
    support_interval_px: FiniteInterval | None,
) -> list[tuple[ProfileRun, PhotoBoundaryObservation, FiniteInterval]]:
    """Merge observations only when their complete union fits one edge."""

    if len(values) < 2:
        return values
    measurement_set = (
        lane.top_measurement_set
        if role == BoundaryRole.TOP
        else lane.bottom_measurement_set
    )
    fit_cache: dict[tuple[str, ...], PhotoBoundaryObservation | None] = {}

    def fit_members(indices: tuple[int, ...]) -> PhotoBoundaryObservation | None:
        identities = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    str(identity)
                    for index in indices
                    for identity in values[index][1].transition_ids
                }
            )
        )
        key = tuple(map(str, identities))
        if key not in fit_cache:
            fit_cache[key] = fit_format_bound_boundary_observation(
                measurement_set,
                transition_ids=identities,
                role=role,
                source_axis_long=lane.width_axis,
                boundary_axis_scale_px_per_mm=lane.height_scale_px_per_mm,
                support_interval_px=support_interval_px,
            )
        candidate = fit_cache[key]
        if (
            candidate is None
            or {str(identity) for identity in candidate.transition_ids}
            != {str(identity) for identity in identities}
            or not all(
                _observation_supports_fitted_family(
                    lane,
                    measurement_set,
                    values[index][1],
                    candidate,
                    support_interval_px,
                )
                for index in indices
            )
        ):
            return None
        return candidate

    mergeable = {
        pair
        for pair in combinations(range(len(values)), 2)
        if fit_members(pair) is not None
    }
    components: list[tuple[int, ...]] = []
    remaining = set(range(len(values)))
    while remaining:
        frontier = [min(remaining)]
        component: set[int] = set()
        while frontier:
            member = frontier.pop()
            if member in component:
                continue
            component.add(member)
            frontier.extend(
                candidate
                for candidate in remaining
                if (member, candidate) in mergeable
                or (candidate, member) in mergeable
            )
        remaining.difference_update(component)
        components.append(tuple(sorted(component)))

    merged: list[tuple[ProfileRun, PhotoBoundaryObservation, FiniteInterval]] = []
    broad_height = geometry.height_state.extent_projection_px()
    for component in components:
        member_identity_sets = {
            index: {
                str(identity) for identity in values[index][1].transition_ids
            }
            for index in component
        }
        superset_members = tuple(
            index
            for index in component
            if all(
                member_identity_sets[other] <= member_identity_sets[index]
                for other in component
            )
        )
        # A connected but jointly inconsistent graph is ambiguous.  Preserve
        # every original observation rather than greedily selecting one
        # mergeable neighbour by order and suppressing a competing edge.
        observation = (
            values[superset_members[0]][1]
            if len(superset_members) == 1
            else fit_members(component)
        )
        if observation is None:
            merged.extend(values[index] for index in component)
            continue
        transitions = tuple(
            lane.transition_by_id[str(identity)]
            for identity in observation.transition_ids
        )
        queried = tuple(
            trace
            for trace in measurement_set.query.trace_positions_px
            if support_interval_px is None
            or support_interval_px.contains(
                float(trace), epsilon=PIXEL_CENTER_HALF_EXTENT_PX
            )
        )
        traces = tuple(
            sorted({item.trace_coordinate_px for item in transitions})
        )
        run = ProfileRun(
            run_id=physical_fact_id(
                "cross-edge-family",
                role.value,
                observation.observation_id,
            ),
            coordinate_interval_px=observation_coordinate_interval(
                observation,
                boundary_axis=lane.height_axis,
                trace_coordinate_px=lane.width_authority_px.center,
            ),
            transition_ids=observation.transition_ids,
            trace_coordinates_px=traces,
            role_hint=role,
            qualified_anchor_roles=(role,),
            support_fraction=len(traces) / len(queried),
            continuous_support_fraction=observation.continuous_support_fraction,
            fit_residual_px=observation.fit_residual_px,
            evidence_strength=sum(
                item.gradient_z + max(item.tone_z, item.texture_z)
                for item in transitions
            )
            / len(transitions),
            pair_qualified=True,
        )
        origin = (
            run.coordinate_interval_px
            if role == BoundaryRole.TOP
            else subtract(run.coordinate_interval_px, broad_height)
        )
        merged.append((run, observation, origin))
    by_observation_id: dict[
        str,
        tuple[ProfileRun, PhotoBoundaryObservation, FiniteInterval],
    ] = {}
    for item in merged:
        if (
            item[1].independent_support_region_count
            < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
        ):
            continue
        by_observation_id.setdefault(str(item[1].observation_id), item)
    return sorted(
        by_observation_id.values(),
        key=lambda item: (item[2].center, item[0].run_id),
    )
