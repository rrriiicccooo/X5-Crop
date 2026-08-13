"""Build finite top/bottom proposals from measured physical edge families."""

from __future__ import annotations

from ...domain import FiniteInterval
from .boundary_fitting import fit_format_bound_boundary_observation
from .chain_proposals import CrossAxisProposal, LaneObservationInput
from .cross_edge_families import merged_cross_edge_families
from .cross_edge_projection import format_bound_opposite_run, inlier_profile_run
from .cross_pairing import (
    CrossEdgeFamily,
    pair_cross_edge_families,
)
from .interval_math import intersect, subtract
from .line_observations import PhotoBoundaryObservation
from .model import BoundaryRole
from .observation_types import ProfileRun
from .physical_identity import physical_fact_id
from .source_geometry import SourceScanGeometry, centered_short_axis_authority_px


def build_cross_axis_proposals(
    lane: LaneObservationInput,
    geometry: SourceScanGeometry,
    *,
    support_interval_px: FiniteInterval | None = None,
) -> tuple[CrossAxisProposal, ...]:
    broad_height = geometry.height_state.extent_projection_px()
    centered = centered_short_axis_authority_px(
        lane.height_authority_px,
        lane.height_scale_px_per_mm,
    )
    centered_origin = FiniteInterval(
        centered.minimum - broad_height.maximum / 2.0,
        centered.maximum - broad_height.minimum / 2.0,
    )
    fit_cache: dict[
        tuple[BoundaryRole, str],
        PhotoBoundaryObservation | None,
    ] = {}
    fitted: dict[
        BoundaryRole,
        list[tuple[ProfileRun, PhotoBoundaryObservation, FiniteInterval]],
    ] = {BoundaryRole.TOP: [], BoundaryRole.BOTTOM: []}
    for role, measurement_set in (
        (BoundaryRole.TOP, lane.top_measurement_set),
        (BoundaryRole.BOTTOM, lane.bottom_measurement_set),
    ):
        for run in lane.cross_profile.runs:
            if (
                run.role_hint != role
                or not (run.pair_qualified or run.anchor_qualified_for(role))
            ):
                continue
            key = (role, run.run_id)
            if key not in fit_cache:
                fit_cache[key] = fit_format_bound_boundary_observation(
                    measurement_set,
                    transition_ids=run.transition_ids,
                    role=role,
                    source_axis_long=lane.width_axis,
                    boundary_axis_scale_px_per_mm=(
                        lane.height_scale_px_per_mm
                    ),
                    support_interval_px=support_interval_px,
                    minimum_independent_support_regions=1,
                )
            observation = fit_cache[key]
            if observation is None:
                continue
            inlier_run = inlier_profile_run(
                lane,
                run,
                observation,
                measurement_set,
                support_interval_px,
            )
            origin = (
                inlier_run.coordinate_interval_px
                if role == BoundaryRole.TOP
                else subtract(inlier_run.coordinate_interval_px, broad_height)
            )
            fitted[role].append((inlier_run, observation, origin))
    for role in fitted:
        fitted[role] = merged_cross_edge_families(
            lane,
            geometry,
            role,
            fitted[role],
            support_interval_px,
        )

    # A format-guided local query may reveal a real opposite edge that the
    # broad corridor grouping missed.  Once measured, it is a
    # candidate-independent observation; the top that suggested the query
    # cannot own its later physical role.
    for known_role, target_role, target_measurement in (
        (
            BoundaryRole.TOP,
            BoundaryRole.BOTTOM,
            lane.bottom_measurement_set,
        ),
        (
            BoundaryRole.BOTTOM,
            BoundaryRole.TOP,
            lane.top_measurement_set,
        ),
    ):
        refined: list[CrossEdgeFamily] = []
        for known in tuple(fitted[known_role]):
            target_run = format_bound_opposite_run(
                lane,
                geometry,
                known[1],
                known_role,
                support_interval_px,
            )
            if target_run is None:
                continue
            target_observation = fit_format_bound_boundary_observation(
                target_measurement,
                transition_ids=target_run.transition_ids,
                role=target_role,
                source_axis_long=lane.width_axis,
                boundary_axis_scale_px_per_mm=lane.height_scale_px_per_mm,
                support_interval_px=support_interval_px,
            )
            if target_observation is None:
                continue
            target_run = inlier_profile_run(
                lane,
                target_run,
                target_observation,
                target_measurement,
                support_interval_px,
            )
            refined.append(
                (
                    target_run,
                    target_observation,
                    (
                        target_run.coordinate_interval_px
                        if target_role == BoundaryRole.TOP
                        else subtract(
                            target_run.coordinate_interval_px,
                            broad_height,
                        )
                    ),
                )
            )
        by_observation_id = {
            str(item[1].observation_id): item
            for item in (*fitted[target_role], *refined)
        }
        fitted[target_role] = sorted(
            by_observation_id.values(),
            key=lambda item: (item[2].center, item[0].run_id),
        )

    cross_proposals: list[CrossAxisProposal] = []
    for top in fitted[BoundaryRole.TOP]:
        for bottom in fitted[BoundaryRole.BOTTOM]:
            cross_proposals.extend(
                pair_cross_edge_families(
                    lane,
                    geometry,
                    top,
                    bottom,
                    centered_origin,
                )
            )
    for values in fitted.values():
        for run, observation, origin in values:
            if not (
                run.anchor_qualified_for(run.role_hint) or run.pair_qualified
            ):
                continue
            legal_origin = intersect(origin, centered_origin)
            if legal_origin is None:
                continue
            cross_proposals.append(
                CrossAxisProposal(
                    cross_proposal_id=physical_fact_id(
                        "provisional-height-cross_proposal",
                        geometry.frame_spec.frame_spec_id,
                        run.run_id,
                    ),
                    frame_spec_id=geometry.frame_spec.frame_spec_id,
                    origin_interval_px=legal_origin,
                    observed_runs=(run,),
                    raw_observations=(observation,),
                    direct_height_span_validated=False,
                )
            )
    unique = {item.cross_proposal_id: item for item in cross_proposals}
    return tuple(unique[key] for key in sorted(unique))
