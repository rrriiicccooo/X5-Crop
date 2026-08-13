"""Pair independently measured short-axis edge families."""

from __future__ import annotations

from ...domain import FiniteInterval
from .chain_proposals import CrossAxisProposal, LaneObservationInput
from .interval_math import intersect, subtract
from .line_observations import PhotoBoundaryObservation
from .model import MINIMUM_INDEPENDENT_SUPPORT_REGIONS
from .observation_types import ProfileRun
from .physical_identity import physical_fact_id
from .source_geometry import SourceScanGeometry
from .trace_support import shared_independent_trace_support_count


CrossEdgeFamily = tuple[
    ProfileRun,
    PhotoBoundaryObservation,
    FiniteInterval,
]


def pair_cross_edge_families(
    lane: LaneObservationInput,
    geometry: SourceScanGeometry,
    top: CrossEdgeFamily,
    bottom: CrossEdgeFamily,
    centered_origin: FiniteInterval,
) -> tuple[CrossAxisProposal, ...]:
    """Return every role allowed by one measured top/bottom family pair."""

    if top[0].coordinate_interval_px.center >= bottom[0].coordinate_interval_px.center:
        return ()
    broad_height = geometry.height_state.extent_projection_px()
    top_origin = intersect(top[2], centered_origin)
    bottom_origin = intersect(bottom[2], centered_origin)
    common_origin = (
        None
        if top_origin is None or bottom_origin is None
        else intersect(top_origin, bottom_origin)
    )
    common_support = intersect(
        top[1].line.support_projection_px,
        bottom[1].line.support_projection_px,
    )
    common_direction = intersect(
        top[1].angle_interval_degrees,
        bottom[1].angle_interval_degrees,
    )
    shared_support_regions = shared_independent_trace_support_count(
        tuple(
            sorted(
                set(lane.top_measurement_set.query.trace_positions_px)
                | set(lane.bottom_measurement_set.query.trace_positions_px)
            )
        ),
        top[0].trace_coordinates_px,
        bottom[0].trace_coordinates_px,
    )
    observed_span = subtract(
        bottom[0].coordinate_interval_px,
        top[0].coordinate_interval_px,
    )
    # The 3% direct-use budget belongs exclusively to the final Gate.  It is
    # not observation or proposal authority.  A provisional pair is physical
    # here only when each measured side can independently bound the same
    # centred fixed-H frame; the final selected-only envelope decides later
    # whether the retained uncertainty is directly usable.
    two_sided_safe = (
        common_support is not None
        and common_direction is not None
        and top_origin is not None
        and bottom_origin is not None
    )
    if not two_sided_safe:
        return ()
    height_validated = (
        common_direction is not None
        and shared_support_regions >= MINIMUM_INDEPENDENT_SUPPORT_REGIONS
        and intersect(observed_span, broad_height) is not None
    )
    proposals: list[CrossAxisProposal] = []
    if not height_validated:
        proposals.append(
            CrossAxisProposal(
                cross_proposal_id=physical_fact_id(
                    "provisional-height-cross_proposal",
                    geometry.frame_spec.frame_spec_id,
                    top[0].run_id,
                    bottom[0].run_id,
                    "two-sided-safety",
                ),
                frame_spec_id=geometry.frame_spec.frame_spec_id,
                origin_interval_px=centered_origin,
                observed_runs=(top[0], bottom[0]),
                raw_observations=(top[1], bottom[1]),
                direct_height_span_validated=False,
            )
        )
    if height_validated and common_origin is not None:
        proposals.append(
            CrossAxisProposal(
                cross_proposal_id=physical_fact_id(
                    "provisional-height-cross_proposal",
                    geometry.frame_spec.frame_spec_id,
                    top[0].run_id,
                    bottom[0].run_id,
                    "height-span",
                ),
                frame_spec_id=geometry.frame_spec.frame_spec_id,
                origin_interval_px=common_origin,
                observed_runs=(top[0], bottom[0]),
                raw_observations=(top[1], bottom[1]),
                direct_height_span_validated=True,
            )
        )
    return tuple(proposals)
