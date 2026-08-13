"""Independent authority dimensions for fixed-format placement selection."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import ObservationId


@dataclass(frozen=True)
class SequenceAuthorityVector:
    complete_direct_chain_count: int
    direct_separator_band_count: int
    independent_separator_support_region_count: int
    direct_outer_boundary_count: int
    normal_completion_authorized_count: int
    local_advance_authorized_count: int
    filled_holder_centering_authorized_count: int
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if (
            min(
                self.complete_direct_chain_count,
                self.direct_separator_band_count,
                self.independent_separator_support_region_count,
                self.direct_outer_boundary_count,
                self.normal_completion_authorized_count,
                self.local_advance_authorized_count,
                self.filled_holder_centering_authorized_count,
            )
            < 0
            or len(set(self.observation_ids)) != len(self.observation_ids)
        ):
            raise ValueError("sequence authority vector is invalid")

    @property
    def components(self) -> tuple[int, ...]:
        return (
            self.complete_direct_chain_count,
            self.direct_separator_band_count,
            self.independent_separator_support_region_count,
            self.direct_outer_boundary_count,
            self.normal_completion_authorized_count,
            self.local_advance_authorized_count,
            self.filled_holder_centering_authorized_count,
        )


@dataclass(frozen=True)
class CrossAuthorityVector:
    fixed_height_placement_authorized_count: int
    complete_top_bottom_pair_count: int
    direct_height_span_validated_count: int
    common_top_bottom_direction_count: int
    source_spanning_boundary_family_count: int
    direct_boundary_family_count: int
    independent_support_region_count: int
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if (
            min(
                self.fixed_height_placement_authorized_count,
                self.complete_top_bottom_pair_count,
                self.direct_height_span_validated_count,
                self.common_top_bottom_direction_count,
                self.source_spanning_boundary_family_count,
                self.direct_boundary_family_count,
                self.independent_support_region_count,
            )
            < 0
            or len(set(self.observation_ids)) != len(self.observation_ids)
        ):
            raise ValueError("cross authority vector is invalid")

    @property
    def components(self) -> tuple[int, ...]:
        return (
            self.fixed_height_placement_authorized_count,
            self.complete_top_bottom_pair_count,
            self.direct_height_span_validated_count,
            self.common_top_bottom_direction_count,
            self.source_spanning_boundary_family_count,
            self.direct_boundary_family_count,
            self.independent_support_region_count,
        )


@dataclass(frozen=True)
class SharedAuthorityVector:
    source_scale_compatible: bool
    direction_bound_lane_count: int
    source_lane_authority_bound_count: int
    content_veto_passed_lane_count: int

    def __post_init__(self) -> None:
        if (
            not self.source_scale_compatible
            or self.direction_bound_lane_count < 0
            or self.source_lane_authority_bound_count < 0
            or self.content_veto_passed_lane_count < 0
        ):
            raise ValueError("shared authority vector is invalid")

    @property
    def components(self) -> tuple[int, ...]:
        return (
            int(self.source_scale_compatible),
            self.direction_bound_lane_count,
            self.source_lane_authority_bound_count,
            self.content_veto_passed_lane_count,
        )


def componentwise_authority_relation(
    left: tuple[int, ...],
    right: tuple[int, ...],
) -> int | None:
    """Compare one authority axis without compensation.

    Returns ``1`` when left is not weaker in any component and stronger in at
    least one, ``-1`` for the reverse, ``0`` for equality, and ``None`` when
    each side is stronger in a different component.
    """

    if len(left) != len(right) or not left:
        raise ValueError("authority vectors require the same non-empty shape")
    if left == right:
        return 0
    left_not_weaker = all(
        left_value >= right_value
        for left_value, right_value in zip(left, right, strict=True)
    )
    right_not_weaker = all(
        right_value >= left_value
        for left_value, right_value in zip(left, right, strict=True)
    )
    if left_not_weaker:
        return 1
    if right_not_weaker:
        return -1
    return None


def tiered_authority_relation(
    left: tuple[int, ...],
    right: tuple[int, ...],
) -> int:
    """Compare ordered evidence tiers within one physical axis.

    Higher-tier authority is considered before lower-tier support quantity.
    This prevents an extra weak region from compensating for a missing direct
    pair or physical height validation.  It does not compare
    sequence against cross; source selection keeps those axes independent.
    """

    if len(left) != len(right) or not left:
        raise ValueError("authority vectors require the same non-empty shape")
    for left_value, right_value in zip(left, right, strict=True):
        if left_value > right_value:
            return 1
        if left_value < right_value:
            return -1
    return 0
