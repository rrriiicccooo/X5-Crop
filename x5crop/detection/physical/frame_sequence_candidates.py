from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor, isfinite

from ...domain import (
    BoundarySide,
    InterFrameSpacing,
    PixelInterval,
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
)
from ...image.content import ContentRegionObservation
from .model import (
    FrameBoundarySource,
    FrameEdgeAssignment,
    FrameSlot,
    ResolvedFrameBoundary,
    SequenceResiduals,
    SharedShortAxisSafetySpan,
    boundary_role_is_independent_physical_measurement,
)


@dataclass(frozen=True)
class SequenceBuildObjectives:
    uncorroborated_overlap_extent_px: float
    unexplained_spacing_extent_px: float
    supported_separator_count: int
    internal_boundary_measurement_quality: float
    dimension_residual: float
    external_boundary_measurement_quality: float
    boundary_uncertainty_ratio: float
    frame_width_hint_residual: float = 0.0
    uncorroborated_contact_count: int = 0
    inferred_boundary_count: int = 0

    def __post_init__(self) -> None:
        measurements = (
            self.uncorroborated_overlap_extent_px,
            self.unexplained_spacing_extent_px,
            self.internal_boundary_measurement_quality,
            self.dimension_residual,
            self.external_boundary_measurement_quality,
            self.boundary_uncertainty_ratio,
            self.frame_width_hint_residual,
        )
        if any(not isfinite(value) or value < 0.0 for value in measurements):
            raise ValueError("sequence build objectives must be finite and non-negative")
        if self.supported_separator_count < 0:
            raise ValueError("supported separator count cannot be negative")
        if self.uncorroborated_contact_count < 0:
            raise ValueError("uncorroborated contact count cannot be negative")
        if self.inferred_boundary_count < 0:
            raise ValueError("inferred boundary count cannot be negative")

    def dominance_axes(self) -> tuple[float, ...]:
        return (
            -self.uncorroborated_overlap_extent_px,
            -self.unexplained_spacing_extent_px,
            self.supported_separator_count,
            -self.dimension_residual,
            -self.boundary_uncertainty_ratio,
            -float(self.uncorroborated_contact_count),
        )

    def dominates(self, other: SequenceBuildObjectives) -> bool:
        left = self.dominance_axes()
        right = other.dominance_axes()
        return all(a >= b for a, b in zip(left, right, strict=True)) and any(
            a > b for a, b in zip(left, right, strict=True)
        )


@dataclass(frozen=True)
class SeparatorBandBinding:
    boundary_index: int
    observation: SeparatorBandObservation
    cross_axis_measurement: SeparatorCrossAxisMeasurement
    preceding_trailing_edge: ResolvedFrameBoundary
    following_leading_edge: ResolvedFrameBoundary

    def __post_init__(self) -> None:
        if self.boundary_index <= 0:
            raise ValueError("separator binding boundary index must be positive")
        if (
            self.cross_axis_measurement.observation_id
            != self.observation.provenance.observation_id
            or not self.cross_axis_measurement.complete_separator_supported
        ):
            raise ValueError("separator binding requires its cross-axis measurement")
        if (
            self.preceding_trailing_edge.position != self.observation.leading_edge
            or self.following_leading_edge.position
            != self.observation.trailing_edge
        ):
            raise ValueError("separator binding must preserve both observed band edges")


@dataclass(frozen=True)
class SequenceBuild:
    slots: tuple[FrameSlot, ...]
    long_axis_assignments: tuple[FrameEdgeAssignment, ...]
    separator_bindings: tuple[SeparatorBandBinding, ...]
    spacings: tuple[InterFrameSpacing, ...]
    frame_width_px: PixelInterval
    short_axis: SharedShortAxisSafetySpan
    residuals: SequenceResiduals
    objectives: SequenceBuildObjectives


def frame_slots_are_strictly_monotonic(
    slots: tuple[FrameSlot, ...],
) -> bool:
    return bool(
        slots
        and all(
            right.leading.position.minimum > left.leading.position.maximum
            and right.trailing.position.minimum > left.trailing.position.maximum
            for left, right in zip(slots, slots[1:])
        )
    )


def _boundaries_share_one_placement(
    boundaries: tuple[ResolvedFrameBoundary, ...],
) -> bool:
    if PixelInterval.common_intersection(
        tuple(boundary.position for boundary in boundaries)
    ) is not None:
        return True
    return all(
        boundary.source == FrameBoundarySource.DIMENSION_CONSTRAINED
        and not boundary.independently_observed
        for boundary in boundaries
    )


def conflicting_internal_frame_indexes(
    builds: tuple[SequenceBuild, ...],
) -> tuple[int, ...]:
    reference = builds[0]
    has_internal_geometry = len(reference.slots) > 1
    conflicts: list[int] = []
    for frame_index in range(1, len(reference.slots) + 1):
        slots = tuple(build.slots[frame_index - 1] for build in builds)
        if all(slot.sequence_inferred for slot in slots):
            continue
        sides = tuple(
            side
            for side in (BoundarySide.LEADING, BoundarySide.TRAILING)
            if not (
                (
                    has_internal_geometry
                    and frame_index == 1
                    and side == BoundarySide.LEADING
                    and all(not slot.sequence_inferred for slot in slots)
                )
                or (
                    has_internal_geometry
                    and frame_index == len(reference.slots)
                    and side == BoundarySide.TRAILING
                    and all(not slot.sequence_inferred for slot in slots)
                )
            )
        )
        if any(
            not _boundaries_share_one_placement(
                tuple(
                    slot.leading
                    if side == BoundarySide.LEADING
                    else slot.trailing
                    for slot in slots
                )
            )
            for side in sides
        ):
            conflicts.append(frame_index)
    return tuple(conflicts)


def external_endpoint_alternatives(
    builds: tuple[SequenceBuild, ...],
) -> bool:
    if (
        len(builds) <= 1
        or any(
            build.slots[0].sequence_inferred
            or build.slots[-1].sequence_inferred
            for build in builds
        )
    ):
        return False
    return any(
        PixelInterval.common_intersection(
            tuple(
                (
                    build.slots[0].leading.position
                    if side == BoundarySide.LEADING
                    else build.slots[-1].trailing.position
                )
                for build in builds
            )
        )
        is None
        for side in (BoundarySide.LEADING, BoundarySide.TRAILING)
    )


def _sequence_inference_signature(build: SequenceBuild) -> tuple[int, ...]:
    return (
        tuple(slot.index for slot in build.slots if slot.sequence_inferred)
        if len(build.slots) > 1
        else ()
    )


def _internal_boundary_role_map(
    build: SequenceBuild,
) -> dict[tuple[int, BoundarySide], ResolvedFrameBoundary]:
    roles: dict[tuple[int, BoundarySide], ResolvedFrameBoundary] = {}
    for left, right in zip(build.slots, build.slots[1:]):
        if boundary_role_is_independent_physical_measurement(left.trailing):
            roles[(left.index, BoundarySide.TRAILING)] = left.trailing
        if boundary_role_is_independent_physical_measurement(right.leading):
            roles[(right.index, BoundarySide.LEADING)] = right.leading
    return roles


def _boundary_role_map_strictly_dominates(
    left: SequenceBuild,
    right: SequenceBuild,
) -> bool:
    if _sequence_inference_signature(left) != _sequence_inference_signature(right):
        return False
    left_roles = _internal_boundary_role_map(left)
    right_roles = _internal_boundary_role_map(right)
    return bool(
        left_roles.keys() > right_roles.keys()
        and all(
            left_roles[key].position.intersects(boundary.position)
            for key, boundary in right_roles.items()
        )
    )


def _build_has_independent_boundary_support(build: SequenceBuild) -> bool:
    return bool(
        build.objectives.supported_separator_count
        or _internal_boundary_role_map(build)
    )


def physically_preferred_builds(
    builds: tuple[SequenceBuild, ...],
) -> tuple[SequenceBuild, ...]:
    if not builds:
        raise ValueError("physical sequence ranking requires builds")
    independently_supported = tuple(
        build for build in builds if _build_has_independent_boundary_support(build)
    )
    if not independently_supported:
        return builds
    builds = independently_supported
    builds = tuple(
        build
        for build in builds
        if not any(
            other is not build
            and _boundary_role_map_strictly_dominates(other, build)
            for other in builds
        )
    )
    minimum_uncorroborated_overlap = min(
        build.objectives.uncorroborated_overlap_extent_px for build in builds
    )
    non_overlapping = tuple(
        build
        for build in builds
        if build.objectives.uncorroborated_overlap_extent_px
        == minimum_uncorroborated_overlap
    )
    strongest_separator_support = max(
        build.objectives.supported_separator_count for build in non_overlapping
    )
    physically_anchored = tuple(
        build
        for build in non_overlapping
        if build.objectives.supported_separator_count
        == strongest_separator_support
    )
    return tuple(
        build
        for build in physically_anchored
        if not any(
            other is not build
            and other.objectives.dominates(build.objectives)
            for other in physically_anchored
        )
    )


def representative_build(builds: tuple[SequenceBuild, ...]) -> SequenceBuild:
    if not builds:
        raise ValueError("representative sequence requires physical builds")
    return max(
        builds,
        key=lambda build: (
            _build_has_independent_boundary_support(build),
            -build.objectives.uncorroborated_overlap_extent_px,
            -build.objectives.uncorroborated_contact_count,
            build.objectives.supported_separator_count,
            build.objectives.internal_boundary_measurement_quality,
            build.objectives.external_boundary_measurement_quality,
            -build.objectives.inferred_boundary_count,
            -build.objectives.unexplained_spacing_extent_px,
            -build.objectives.dimension_residual,
            -build.objectives.frame_width_hint_residual,
            -build.objectives.boundary_uncertainty_ratio,
            tuple(
                -edge.position.midpoint
                for slot in build.slots
                for edge in (slot.leading, slot.trailing)
            ),
        ),
    )


def build_preserves_visible_content(
    build: SequenceBuild,
    visible_content: ContentRegionObservation,
) -> bool:
    if not build.slots:
        return False
    sequence_interval = (
        max(
            visible_content.region.left,
            int(floor(build.slots[0].leading.position.minimum)),
        ),
        min(
            visible_content.region.right,
            int(ceil(build.slots[-1].trailing.position.maximum)),
        ),
    )
    if sequence_interval[1] <= sequence_interval[0]:
        return False
    return not visible_content.uncovered_by((sequence_interval,))
