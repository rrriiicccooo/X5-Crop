"""Direct top/bottom measurement relations inside the cross axis."""

from __future__ import annotations

from .chains import CompleteFormatChain
from .model import BoundaryRole


def _interval_gap(left, right) -> float:
    return max(
        0.0,
        left.minimum - right.maximum,
        right.minimum - left.maximum,
    )


def cross_measurements_strictly_dominate(
    left_placement_ids: tuple[str, ...],
    right_placement_ids: tuple[str, ...],
    placements_by_id: dict[str, CompleteFormatChain],
) -> bool:
    """Compare cross measurements after direct authority has tied.

    Independent front/middle/back regions are direct evidence.  Once two
    observations have the same finite region authority, raw trace count and
    support length must not become extra votes.  A smaller reported uncertainty
    is not positive evidence either; it only controls the eventual safe
    envelope.  Componentwise smaller line-fit residual is the remaining
    measurement-quality relation.
    """

    if len(left_placement_ids) != len(right_placement_ids):
        return False
    direction_consistency_pairs: list[tuple[float, float]] = []
    role_consistency_pairs: list[tuple[float, float]] = []
    lane_observations: list[
        tuple[dict[BoundaryRole, object], dict[BoundaryRole, object]]
    ] = []
    for left_id, right_id in zip(
        left_placement_ids,
        right_placement_ids,
        strict=True,
    ):
        left_by_role = {
            item.role: item.observation
            for item in placements_by_id[left_id].cross.evidence
        }
        right_by_role = {
            item.role: item.observation
            for item in placements_by_id[right_id].cross.evidence
        }
        if set(left_by_role) != set(right_by_role):
            return False
        lane_observations.append((left_by_role, right_by_role))
        if {BoundaryRole.TOP, BoundaryRole.BOTTOM} <= set(left_by_role):
            direction_consistency_pairs.append(
                (
                    _interval_gap(
                        left_by_role[BoundaryRole.TOP]
                        .fit_angle_interval_degrees,
                        left_by_role[BoundaryRole.BOTTOM]
                        .fit_angle_interval_degrees,
                    ),
                    _interval_gap(
                        right_by_role[BoundaryRole.TOP]
                        .fit_angle_interval_degrees,
                        right_by_role[BoundaryRole.BOTTOM]
                        .fit_angle_interval_degrees,
                    ),
                )
            )
        for role in sorted(left_by_role, key=lambda item: item.value):
            left_observation = left_by_role[role]
            right_observation = right_by_role[role]
            left_role_consistency = (
                left_observation.left_background_preference_fraction
                if role == BoundaryRole.TOP
                else left_observation.right_background_preference_fraction
            )
            right_role_consistency = (
                right_observation.left_background_preference_fraction
                if role == BoundaryRole.TOP
                else right_observation.right_background_preference_fraction
            )
            # Top and bottom are both required cross-axis authorities.  Keep
            # their material-role relations as separate dimensions: a very
            # convincing bottom cannot compensate for a weaker top, and a
            # lower fit residual cannot compensate for either one.
            role_consistency_pairs.append(
                (left_role_consistency, right_role_consistency)
            )
    # Top and bottom are opposite sides of the same fixed-format rectangle.
    # A pair whose directly fitted direction intervals are closer is therefore
    # physically stronger before either edge's material appearance is
    # considered.  Keep lanes componentwise: a straighter lane cannot pay for
    # a weaker one, and no numeric tolerance or weighted score is introduced.
    if any(left > right for left, right in direction_consistency_pairs):
        return False
    if any(left < right for left, right in direction_consistency_pairs):
        return True

    if any(left < right for left, right in role_consistency_pairs):
        return False
    if any(left > right for left, right in role_consistency_pairs):
        # Role consistency answers the prior physical question: does each
        # proposed outer side look like holder/film background while its inner
        # side looks like photograph material?  Once it differs without a
        # trade-off, lower-level fit quality cannot reverse that authority.
        return True

    strict = False
    for left_by_role, right_by_role in lane_observations:
        for role in sorted(left_by_role, key=lambda item: item.value):
            left_observation = left_by_role[role]
            right_observation = right_by_role[role]
            if left_observation.observation_id == right_observation.observation_id:
                continue
            left_regions = left_observation.independent_support_region_count
            right_regions = right_observation.independent_support_region_count
            if left_regions < right_regions:
                return False
            if left_regions > right_regions:
                strict = True
                continue
            if left_observation.fit_residual_px > right_observation.fit_residual_px:
                return False
            strict = strict or (
                left_observation.fit_residual_px
                < right_observation.fit_residual_px
            )
    return strict


def minimum_safe_cross_pair_relation(
    left_placement_ids: tuple[str, ...],
    right_placement_ids: tuple[str, ...],
    placements_by_id: dict[str, CompleteFormatChain],
) -> int | None:
    """Compare two interpretations of one legal fixed-H cross placement.

    Short-axis centering is a hard placement authority upstream.  It is not a
    score and must not choose between displaced top/bottom explanations here.
    Once two candidates belong to the same format/scale *and direct-cross
    evidence tier*, and their boundary uncertainty intervals describe a common
    fixed-H placement, the existing placement with the smaller safe short-axis
    span in every frame is the minimum safe pair.  A direct top+bottom pair is
    therefore never discarded in favour of a single edge plus an inferred
    opposite boundary.  The relation chooses an existing placement and never
    splices boundaries, averages candidates, or trades short-axis safety
    against sequence evidence.  Candidates using the same direct cross
    observations are equal on this axis; sequence evidence may still resolve
    their joint direction.
    """

    if len(left_placement_ids) != len(right_placement_ids):
        return None
    left_not_wider = True
    right_not_wider = True
    left_strict = False
    right_strict = False
    for left_id, right_id in zip(
        left_placement_ids,
        right_placement_ids,
        strict=True,
    ):
        left_placement = placements_by_id[left_id]
        right_placement = placements_by_id[right_id]
        left_geometry = left_placement.source_scan_geometry
        right_geometry = right_placement.source_scan_geometry
        if (
            left_geometry.frame_spec != right_geometry.frame_spec
            or left_geometry.height_state.scale_authority
            != right_geometry.height_state.scale_authority
            or left_geometry.height_state.factor_authority
            != right_geometry.height_state.factor_authority
        ):
            return None
        left_cross = left_placement.cross
        right_cross = right_placement.cross
        if not (
            len(left_cross.top_full_positions_px)
            == len(right_cross.top_full_positions_px)
            == len(left_cross.bottom_full_positions_px)
            == len(right_cross.bottom_full_positions_px)
        ):
            return None
        left_evidence = {
            item.role: item.observation.observation_id
            for item in left_cross.evidence
        }
        right_evidence = {
            item.role: item.observation.observation_id
            for item in right_cross.evidence
        }
        if not set(left_evidence) <= {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
            return None
        if not set(right_evidence) <= {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
            return None
        if (
            set(left_evidence) != set(right_evidence)
            or left_cross.direct_height_span_validated
            != right_cross.direct_height_span_validated
        ):
            return None
        if left_evidence == right_evidence:
            continue
        shared_top = (
            BoundaryRole.TOP in left_evidence
            and left_evidence.get(BoundaryRole.TOP)
            == right_evidence.get(BoundaryRole.TOP)
        )
        shared_bottom = (
            BoundaryRole.BOTTOM in left_evidence
            and left_evidence.get(BoundaryRole.BOTTOM)
            == right_evidence.get(BoundaryRole.BOTTOM)
        )
        if not (shared_top or shared_bottom):
            # Two wholly different top/bottom pairs are different physical
            # placements.  Broad direction uncertainty may make their
            # projected intervals overlap, but that cannot turn them into
            # minimum-safe variants of one another.
            return None
        for left_top, right_top, left_bottom, right_bottom in zip(
            left_cross.top_full_positions_px,
            right_cross.top_full_positions_px,
            left_cross.bottom_full_positions_px,
            right_cross.bottom_full_positions_px,
            strict=True,
        ):
            if shared_top:
                left_span = left_bottom.maximum
                right_span = right_bottom.maximum
            elif shared_bottom:
                left_span = -left_top.minimum
                right_span = -right_top.minimum
            else:
                raise AssertionError("cross variants require a shared edge")
            if left_span > right_span:
                left_not_wider = False
            if right_span > left_span:
                right_not_wider = False
            left_strict = left_strict or left_span < right_span
            right_strict = right_strict or right_span < left_span
    if left_not_wider and left_strict:
        return 1
    if right_not_wider and right_strict:
        return -1
    if left_not_wider and right_not_wider:
        return 0
    return None
