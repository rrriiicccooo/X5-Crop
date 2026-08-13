"""Componentwise sequence/cross/shared authority for source placements."""

from __future__ import annotations

from .axis_authority import (
    componentwise_authority_relation,
    tiered_authority_relation,
)
from .chains import CompleteFormatChain
from .cross_dominance import (
    cross_measurements_strictly_dominate,
    minimum_safe_cross_pair_relation,
)
from .placement_dominance import (
    minimum_safe_outer_boundary_relation,
)
from .sequence_dominance import (
    minimum_safe_separator_relation,
    separator_material_strictly_dominates,
)
from .source_selection_model import SourcePlacementCombination


def source_strictly_dominates(
    left: SourcePlacementCombination,
    right: SourcePlacementCombination,
    placements_by_id: dict[str, CompleteFormatChain],
) -> bool:
    """Require the left placement to be non-weaker on every authority axis."""

    if left.shared_scan_geometry != right.shared_scan_geometry:
        return False

    # A candidate may not win by ignoring a competing candidate's same-level
    # direct pixel observation.  Minimum-safe variants are normalized before
    # this authority relation, so no pairwise safety exception is allowed to
    # override the independent sequence/cross/shared ordering here.
    sequence_relation = tiered_authority_relation(
        left.sequence_authority.components,
        right.sequence_authority.components,
    )
    cross_relation = tiered_authority_relation(
        left.cross_authority.components,
        right.cross_authority.components,
    )
    shared_relation = componentwise_authority_relation(
        left.shared_authority.components,
        right.shared_authority.components,
    )
    relations = (sequence_relation, cross_relation, shared_relation)
    if any(value in {-1, None} for value in relations):
        return False
    unaccounted = set(right.direct_observation_ids) - set(
        left.accounted_observation_ids
    )
    if any(value == 1 for value in relations):
        # More authority on one tier still cannot erase a different direct
        # pixel observation.  The stronger placement must explicitly explain
        # that observation as its own boundary, an internal line, an outer
        # holder/film limit, or a contradiction before it may dominate.
        return not unaccounted

    if unaccounted:
        return False

    cross_left = cross_measurements_strictly_dominate(
        left.lane_placement_ids,
        right.lane_placement_ids,
        placements_by_id,
    )
    cross_right = cross_measurements_strictly_dominate(
        right.lane_placement_ids,
        left.lane_placement_ids,
        placements_by_id,
    )
    sequence_left = separator_material_strictly_dominates(
        left.lane_placement_ids,
        right.lane_placement_ids,
        placements_by_id,
    )
    sequence_right = separator_material_strictly_dominates(
        right.lane_placement_ids,
        left.lane_placement_ids,
        placements_by_id,
    )
    if (cross_left and sequence_right) or (cross_right and sequence_left):
        return False
    if cross_left or sequence_left:
        return True
    return False


def minimum_safe_source_variant_strictly_dominates(
    left: SourcePlacementCombination,
    right: SourcePlacementCombination,
    placements_by_id: dict[str, CompleteFormatChain],
) -> bool:
    """Choose an existing minimum-safe interpretation before authority voting.

    This relation is deliberately separate from evidence dominance.  Both
    physical axes must describe the same variant class; neither axis may be
    wider, and at least one must be strictly smaller.  A discarded direct
    observation is explained only by the axis on which the minimum-safe
    relation actually wins.
    """

    if left.shared_scan_geometry != right.shared_scan_geometry:
        return False
    if len(left.lane_placement_ids) != len(right.lane_placement_ids):
        return False
    for left_id, right_id in zip(
        left.lane_placement_ids,
        right.lane_placement_ids,
        strict=True,
    ):
        # Minimum-safe normalization may only choose between variants inside
        # the same source-scale and transform/direction class.  A smaller box
        # under another deskew transform is a different physical placement,
        # not a safer interpretation of this one.
        if (
            placements_by_id[left_id].lane_geometry.direction
            != placements_by_id[right_id].lane_geometry.direction
        ):
            return False

    separator_relation = minimum_safe_separator_relation(
        left.lane_placement_ids,
        right.lane_placement_ids,
        placements_by_id,
    )
    outer_relation = minimum_safe_outer_boundary_relation(
        left.lane_placement_ids,
        right.lane_placement_ids,
        placements_by_id,
    )
    if separator_relation is None or outer_relation is None:
        sequence_relation = None
    elif separator_relation in {-1, 1} and outer_relation == -separator_relation:
        sequence_relation = None
    else:
        sequence_relation = separator_relation or outer_relation
    cross_relation = minimum_safe_cross_pair_relation(
        left.lane_placement_ids,
        right.lane_placement_ids,
        placements_by_id,
    )
    relations = (sequence_relation, cross_relation)
    if any(value in {-1, None} for value in relations) or not any(
        value == 1 for value in relations
    ):
        return False
    explained = set()
    if sequence_relation == 1:
        explained.update(right.sequence_authority.observation_ids)
    if cross_relation == 1:
        explained.update(right.cross_authority.observation_ids)
    unaccounted = set(right.direct_observation_ids) - set(
        left.accounted_observation_ids
    )
    return unaccounted.issubset(explained)
