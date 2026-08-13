"""Source/lane direction proposals before joint chain selection."""

from __future__ import annotations

from statistics import median

from ...domain import FiniteInterval
from ..output_geometry import observed_strip_angle_estimate_degrees
from .chain_proposals import (
    CrossAxisProposal,
    LaneObservationInput,
    SequenceChainProposal,
)
from .interval_math import common, intersect
from .output_model import SharedStripDirection
from .physical_identity import physical_fact_id

def conditional_fit_and_full(
    fit_values: tuple[FiniteInterval, ...],
    full_values: tuple[FiniteInterval, ...],
) -> tuple[FiniteInterval, FiniteInterval] | None:
    """Keep the robust center as preference inside the full safety domain."""

    full = common(full_values)
    if full is None:
        return None
    fit = common(fit_values)
    if fit is not None:
        fit = intersect(fit, full)
    return (full if fit is None else fit), full


def direction_class_key(direction: SharedStripDirection) -> tuple[object, ...]:
    return (
        direction.canonical_angle_degrees.hex(),
        direction.full_angle_interval_degrees.minimum.hex(),
        direction.full_angle_interval_degrees.maximum.hex(),
        tuple(map(str, direction.selected_observation_ids)),
    )




def physical_bound_direction_classes(
    cross_proposals: tuple[CrossAxisProposal, ...],
) -> tuple[SharedStripDirection, ...]:
    """Keep one direction proposal for each physical cross-axis proposal.

    Direction is conditional on the top/bottom evidence that will participate
    in the complete chain.  Pooling every overlapping raw line first lets an
    unrelated internal line narrow the direction of a different, otherwise
    valid top/bottom pair.  Equal observation sets are deduplicated, but no
    other cross proposal lends direction authority before the joint solve.
    """

    directions: list[SharedStripDirection] = []
    for proposal in cross_proposals:
        observations = proposal.raw_observations
        common_direction = common(
            tuple(item.angle_interval_degrees for item in observations)
        )
        # Two visible limits can establish one common lane direction without
        # proving that their separation equals the camera-aperture H.  Height
        # calibration and direction compatibility are independent physical
        # authorities; coupling them creates duplicate top-only/bottom-only
        # placements for the same two-sided observation.
        direction_groups = (
            (observations,)
            if len(observations) == 2 and common_direction is not None
            else tuple((observation,) for observation in observations)
        )
        for group in direction_groups:
            identities = tuple(
                sorted(
                    (item.observation_id for item in group),
                    key=str,
                )
            )
            # Deskew owns one representative lane direction.  Two visible
            # safety limits with incompatible local angles remain alternative
            # direction proposals; sequence evidence participates in the
            # complete-chain solve instead of consuming their average.
            direction_family = (
                group[0].angle_interval_degrees
                if len(group) == 1
                else common_direction
            )
            if direction_family is None:
                raise AssertionError(
                    "paired direction group requires a common interval"
                )
            canonical = observed_strip_angle_estimate_degrees(group)
            canonical = min(
                direction_family.maximum,
                max(direction_family.minimum, canonical),
            )
            directions.append(
                SharedStripDirection(
                    direction_id=physical_fact_id(
                        "cross-proposal-direction",
                        *(str(identity) for identity in identities),
                        direction_family.minimum,
                        direction_family.maximum,
                        canonical,
                    ),
                    selected_observation_ids=identities,
                    full_angle_interval_degrees=direction_family,
                    canonical_angle_degrees=canonical,
                )
            )
    unique = {item.direction_id: item for item in directions}
    return tuple(sorted(unique.values(), key=direction_class_key))


def joint_chain_direction(
    lane: LaneObservationInput,
    seed: SequenceChainProposal,
    cross_direction: SharedStripDirection,
) -> SharedStripDirection:
    """Bind cross and role-bound sequence direction into one lane family.

    Local separator edges and top/bottom segments may differ slightly because
    the physical strip can bend.  Their union therefore defines a direction
    *family*, not an exact common line.  The canonical deskew direction is the
    median of the finite independent observations; this is a robust location
    identity, not a weighted score and cannot change any boundary role.
    """

    run_ids = {
        item.run_id
        for item in (*seed.role_proposals, *seed.local_advance_proposals)
    }
    sequence_edges = tuple(
        sorted(
            (
                edge
                for edge in lane.sequence_edges
                if edge.run_id in run_ids
                and edge.canonical_direction_degrees is not None
                and edge.fit_direction_interval_degrees is not None
                and edge.full_direction_interval_degrees is not None
            ),
            key=lambda item: str(item.observation_id),
        )
    )
    # A directly paired top/bottom family already owns the lane's long-edge
    # direction.  Sequence edges are the normal family: repeated compatible
    # edges may reject an impossible pair, but they must not translate or
    # widen an already established long-edge direction.  Otherwise different
    # start/end hypotheses manufacture different deskew transforms for the
    # same top/bottom observation pair.
    direct_cross_pair = len(cross_direction.selected_observation_ids) == 2
    # One sequence edge cannot establish a lane direction independently.  It
    # remains position evidence and the cross family retains direction owner.
    if len(sequence_edges) < 2:
        return cross_direction
    # A shared direction is a repeated compatible family, not the hull of
    # every role-bound line.  A separator/content line with another slope can
    # still locate its start/end boundary, but it cannot expand the lane's
    # global direction by several degrees.  Keep only sequence edges whose
    # complete measured interval admits the cross direction, then require two
    # compatible direct edges before they may participate in the shared
    # direction.  This is the physical "common direction with small local
    # bend" relation; incompatible edges remain local position observations.
    compatible_edges = tuple(
        edge
        for edge in sequence_edges
        if intersect(
            cross_direction.full_angle_interval_degrees,
            edge.full_direction_interval_degrees,
        )
        is not None
    )
    if direct_cross_pair:
        if len(compatible_edges) < 2:
            raise ValueError(
                "direct cross pair contradicts repeated sequence direction"
            )
        return cross_direction
    if len(compatible_edges) < 2:
        return cross_direction
    fit_support = tuple(
        edge
        for edge in compatible_edges
        if intersect(
            cross_direction.full_angle_interval_degrees,
            edge.fit_direction_interval_degrees,
        )
        is not None
    )
    retained_edges = fit_support if len(fit_support) >= 2 else compatible_edges
    full_family = common(
        (
            cross_direction.full_angle_interval_degrees,
            *(edge.full_direction_interval_degrees for edge in retained_edges),
        )
    )
    if full_family is None:
        return cross_direction
    canonical = float(
        median(
            (
                cross_direction.canonical_angle_degrees,
                *(
                    float(edge.canonical_direction_degrees)
                    for edge in retained_edges
                ),
            )
        )
    )
    canonical = min(full_family.maximum, max(full_family.minimum, canonical))
    identities = tuple(
        sorted(
            {
                *cross_direction.selected_observation_ids,
                *(edge.observation_id for edge in retained_edges),
            },
            key=str,
        )
    )
    return SharedStripDirection(
        direction_id=physical_fact_id(
            "joint-chain-direction",
            *(str(identity) for identity in identities),
            full_family.minimum,
            full_family.maximum,
            canonical,
        ),
        selected_observation_ids=identities,
        full_angle_interval_degrees=full_family,
        canonical_angle_degrees=canonical,
    )
