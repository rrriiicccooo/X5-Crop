"""Resolve one source direction from independent template-bound evidence."""

from __future__ import annotations

import math
from statistics import median

from ...domain import FiniteInterval
from ...run_local_identity import run_local_id
from .interval_math import hull, intersect as _intersect
from .observation_types import BoundaryEdgeObservation
from .output_model import OutputBoundaryUse, SharedStripDirection
from .template_cross_model import CrossEvidence, CrossFit
from .template_model import SequenceFit
from .model import SPATIAL_SUPPORT_REGION_COUNT
from .trace_support import PIXEL_CENTER_HALF_EXTENT_PX


def _sequence_direction_groups(
    sequence_fit: SequenceFit,
    observations: tuple[BoundaryEdgeObservation, ...],
) -> tuple[
    tuple[float, FiniteInterval, FiniteInterval, tuple],
    ...,
]:
    """Return one direction fact per independent physical sequence position.

    The two sides of one separator are one physical structure.  They improve
    that separator's direction interval but never become two independent
    votes.  The outer start/end boundaries each remain their own position.
    """

    by_id = {item.observation_id: item for item in observations}
    role_ids = sequence_fit.role_observation_ids
    role_groups = [(0,)]
    role_groups.extend(
        (end_index, end_index + 1)
        for end_index in range(1, len(role_ids) - 1, 2)
    )
    if len(role_ids) > 1:
        role_groups.append((len(role_ids) - 1,))
    result = []
    for indices in role_groups:
        values = tuple(
            by_id[role_ids[index]]
            for index in indices
            if role_ids[index] is not None
            and role_ids[index] in by_id
            and by_id[role_ids[index]].canonical_direction_degrees is not None
            and by_id[role_ids[index]].fit_direction_interval_degrees is not None
        )
        if not values:
            continue
        canonical = float(median(
            float(item.canonical_direction_degrees) for item in values
        ))
        fit_interval = FiniteInterval(
            min(item.fit_direction_interval_degrees.minimum for item in values),
            max(item.fit_direction_interval_degrees.maximum for item in values),
        )
        quantization = max(
            math.degrees(
                math.atan(
                    PIXEL_CENTER_HALF_EXTENT_PX
                    / max(
                        1,
                        item.trace_coordinates_px[-1]
                        - item.trace_coordinates_px[0],
                    )
                )
            )
            for item in values
        )
        result.append(
            (
                canonical,
                fit_interval,
                FiniteInterval(
                    fit_interval.minimum - quantization,
                    fit_interval.maximum + quantization,
                ),
                tuple(item.observation_id for item in values),
            )
        )
    return tuple(result)


def lane_template_direction(
    sequence_fit: SequenceFit,
    sequence_observations: tuple[BoundaryEdgeObservation, ...],
    cross_fit: CrossFit,
) -> SharedStripDirection:
    """Close shared direction from cross compatibility and sequence positions.

    Cross evidence still owns top/bottom placement.  At least two independent
    template-bound sequence positions may additionally estimate the one shared
    strip direction.  This is a continuous fit, never a placement vote.
    """

    cross_direction = cross_fit.selected_direction
    if cross_direction is None:
        raise ValueError("lane direction requires direct cross evidence")
    local_refinements = tuple(
        item
        for item in cross_fit.direct_bindings
        if item.evidence == CrossEvidence.TEMPLATE_LOCAL_REFINEMENT
    )
    direction_anchors = tuple(
        item
        for item in cross_fit.direct_bindings
        if item.evidence != CrossEvidence.TEMPLATE_LOCAL_REFINEMENT
        and item.canonical_direction_degrees is not None
        and item.full_direction_interval_degrees is not None
    )
    if len(local_refinements) == 1 and len(direction_anchors) == 1:
        # Whole-to-local refinement has asymmetric authority.  The source-wide
        # direct side owns deskew; the template-projected local opposite side
        # only closes cross offset and fixed H.  Letting the local fit move or
        # narrow source direction would extrapolate a local fragment over the
        # complete strip and can cut the far-end corner.
        anchor = direction_anchors[0]
        assert anchor.full_direction_interval_degrees is not None
        assert anchor.canonical_direction_degrees is not None
        return SharedStripDirection(
            direction_id=run_local_id(
                "template-lane-direction",
                str(anchor.observation_id),
                "source-wide-anchor",
            ),
            # Keep the local observation in the provenance closure because it
            # directly proved compatibility, while the interval and canonical
            # value remain owned solely by the source-wide anchor.
            selected_observation_ids=(
                cross_direction.selected_observation_ids
            ),
            full_angle_interval_degrees=(
                anchor.full_direction_interval_degrees
            ),
            observed_angle_interval_degrees=hull(
                (
                    anchor.full_direction_interval_degrees,
                    *(
                        item.full_direction_interval_degrees
                        for item in cross_fit.direct_bindings
                        if item.full_direction_interval_degrees is not None
                    ),
                ),
            ),
            canonical_angle_degrees=float(
                anchor.canonical_direction_degrees
            ),
        )
    direct_fit_intervals = tuple(
        item.fit_direction_interval_degrees
        for item in cross_fit.direct_bindings
        if item.fit_direction_interval_degrees is not None
    )
    direct_fit_common = None
    if direct_fit_intervals:
        direct_fit_common = direct_fit_intervals[0]
        for interval in direct_fit_intervals[1:]:
            direct_fit_common = _intersect(direct_fit_common, interval)
            if direct_fit_common is None:
                break
    groups = _sequence_direction_groups(sequence_fit, sequence_observations)
    sequence_interval = None
    sequence_observed_interval = None
    sequence_identities: tuple = ()
    if len(groups) >= 2:
        sequence_interval = FiniteInterval(
            float(median(item[1].minimum for item in groups)),
            float(median(item[1].maximum for item in groups)),
        )
        sequence_observed_interval = FiniteInterval(
            float(median(item[2].minimum for item in groups)),
            float(median(item[2].maximum for item in groups)),
        )
        sequence_identities = tuple(
            identity for item in groups for identity in item[3]
        )
    if any(
        item.source_spanning_continuous and item.role_authorized
        for item in cross_fit.direct_bindings
    ):
        return cross_direction
    # Two role-authorized sides that close the fixed aperture across every
    # independent longitudinal region already form a source-wide direction
    # observation.  Separator directions are then validation only: a dark or
    # locally irregular divider must not overturn the directly observed outer
    # pair.  This is the bounded whole-strip path used before local refinement.
    if (
        cross_fit.direct_pair
        and cross_fit.independent_support_region_count
        == SPATIAL_SUPPORT_REGION_COUNT
    ):
        # An enclosing pair is itself the selected output support.  Its full
        # directly measured direction interval therefore belongs to safety;
        # reducing it to the statistical fit hull can cut a support-aligned
        # corner.  Aperture pairs keep the narrower local-fit hull below.
        if cross_fit.boundary_use == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR:
            if sequence_observed_interval is None:
                return cross_direction
            identities = tuple(
                dict.fromkeys(
                    (
                        *cross_direction.selected_observation_ids,
                        *sequence_identities,
                    )
                )
            )
            return SharedStripDirection(
                direction_id=run_local_id(
                    "template-lane-direction",
                    cross_direction.direction_id,
                    *(str(identity) for identity in identities),
                ),
                selected_observation_ids=identities,
                full_angle_interval_degrees=(
                    cross_direction.full_angle_interval_degrees
                ),
                observed_angle_interval_degrees=hull(
                    (
                        cross_direction.observed_angle_interval_degrees,
                        sequence_observed_interval,
                    )
                ),
                canonical_angle_degrees=(
                    cross_direction.canonical_angle_degrees
                ),
            )
        if len(direct_fit_intervals) != 2:
            return cross_direction
        straight_residual = FiniteInterval(
            min(item.minimum for item in direct_fit_intervals),
            max(item.maximum for item in direct_fit_intervals),
        )
        canonical = min(
            straight_residual.maximum,
            max(
                straight_residual.minimum,
                cross_direction.canonical_angle_degrees,
            ),
        )
        return SharedStripDirection(
            direction_id=run_local_id(
                "template-lane-direction",
                cross_direction.direction_id,
                "three-region-straight-residual",
            ),
            selected_observation_ids=(
                cross_direction.selected_observation_ids
            ),
            full_angle_interval_degrees=straight_residual,
            observed_angle_interval_degrees=hull(
                (
                    cross_direction.observed_angle_interval_degrees,
                    straight_residual,
                )
            ),
            canonical_angle_degrees=canonical,
        )
    if len(cross_fit.direct_bindings) != 2:
        return cross_direction
    if sequence_interval is None or sequence_observed_interval is None:
        return cross_direction
    if direct_fit_common is not None:
        # Two role-authorized local sides establish one common direction, and
        # independent sequence positions prove that this local closure belongs
        # to the source-wide strip.  Retain each side's statistical fit hull;
        # the much broader fragment extrapolation intervals no longer become
        # source-wide selected-output uncertainty.
        if _intersect(sequence_interval, direct_fit_common) is None:
            return cross_direction
        fit_hull = FiniteInterval(
            min(item.minimum for item in direct_fit_intervals),
            max(item.maximum for item in direct_fit_intervals),
        )
        # The common interval proved that one shared straight direction is
        # feasible.  For selected-output safety retain the complete statistical
        # fit hull of both directly observed sides; intersecting it back down
        # to the common sliver would discard the measured end-to-end departure.
        common = fit_hull
        canonical = min(
            common.maximum,
            max(common.minimum, cross_direction.canonical_angle_degrees),
        )
        identities = tuple(
            dict.fromkeys(
                (
                    *cross_direction.selected_observation_ids,
                    *sequence_identities,
                )
            )
        )
        return SharedStripDirection(
            direction_id=run_local_id(
                "template-lane-direction",
                cross_direction.direction_id,
                *(str(identity) for identity in identities),
            ),
            selected_observation_ids=identities,
            full_angle_interval_degrees=common,
            observed_angle_interval_degrees=hull(
                (
                    cross_direction.observed_angle_interval_degrees,
                    sequence_observed_interval,
                    common,
                )
            ),
            canonical_angle_degrees=canonical,
        )
    if _intersect(
        sequence_interval,
        cross_direction.full_angle_interval_degrees,
    ) is None:
        raise ValueError("sequence and cross direction evidence are incompatible")
    # Cross fragments locate top/bottom.  When their local statistical fits do
    # not share a direction, independent sequence positions own the one global
    # deskew interval.  Cross departures remain observed residuals; turning
    # their hull into a possible rotation of the complete source creates
    # impossible far-end corners and oversized output envelopes.
    common = sequence_interval
    canonical = min(
        common.maximum,
        max(common.minimum, float(median(item[0] for item in groups))),
    )
    identities = tuple(
        dict.fromkeys(
            (
                *cross_direction.selected_observation_ids,
                *sequence_identities,
            )
        )
    )
    return SharedStripDirection(
        direction_id=run_local_id(
            "template-lane-direction",
            cross_direction.direction_id,
            *(str(identity) for identity in identities),
        ),
        selected_observation_ids=identities,
        full_angle_interval_degrees=common,
        observed_angle_interval_degrees=hull(
            (
                cross_direction.observed_angle_interval_degrees,
                sequence_observed_interval,
                common,
            )
        ),
        canonical_angle_degrees=canonical,
    )


def shared_template_direction(
    directions: tuple[SharedStripDirection, ...],
) -> SharedStripDirection:
    if not directions:
        raise ValueError("shared template direction requires direct lane evidence")
    minimum = max(item.full_angle_interval_degrees.minimum for item in directions)
    maximum = min(item.full_angle_interval_degrees.maximum for item in directions)
    if minimum > maximum:
        raise ValueError("lane direction observations have no common interval")
    identities = tuple(
        sorted(
            {
                identity
                for direction in directions
                for identity in direction.selected_observation_ids
            },
            key=str,
        )
    )
    canonical = min(
        maximum,
        max(
            minimum,
            sum(item.canonical_angle_degrees for item in directions)
            / len(directions),
        ),
    )
    return SharedStripDirection(
        direction_id=run_local_id(
            "template-source-direction",
            *(item.direction_id for item in directions),
            *(str(identity) for identity in identities),
        ),
        selected_observation_ids=identities,
        full_angle_interval_degrees=FiniteInterval(minimum, maximum),
        observed_angle_interval_degrees=hull(
            tuple(item.observed_angle_interval_degrees for item in directions)
        ),
        canonical_angle_degrees=canonical,
    )


__all__ = ["lane_template_direction", "shared_template_direction"]
