from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil, floor, isfinite

from ...domain import (
    BoundarySide,
    EvidenceState,
    InterFrameBoundaryReference,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    InterFrameSpacingKind,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
)
from ...image.content import ContentRegionObservation
from . import frame_sequence_measurements as measurement_facts
from .model import (
    BoundaryAnchor,
    BoundaryRoleAuthority,
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
        if self.observation.width_px.minimum <= 0.0:
            raise ValueError("separator binding requires positive observed width")
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
    left_inference_signature: tuple[int, ...],
    left_roles: dict[tuple[int, BoundarySide], ResolvedFrameBoundary],
    right_inference_signature: tuple[int, ...],
    right_roles: dict[tuple[int, BoundarySide], ResolvedFrameBoundary],
) -> bool:
    if left_inference_signature != right_inference_signature:
        return False
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
    physical_facts_by_identity = {
        id(build): (
            _sequence_inference_signature(build),
            _internal_boundary_role_map(build),
        )
        for build in builds
    }
    independently_supported = tuple(
        build
        for build in builds
        if build.objectives.supported_separator_count
        or physical_facts_by_identity[id(build)][1]
    )
    if not independently_supported:
        return builds
    builds = independently_supported
    minimum_uncorroborated_overlap = min(
        build.objectives.uncorroborated_overlap_extent_px for build in builds
    )
    builds = tuple(
        build
        for build in builds
        if build.objectives.uncorroborated_overlap_extent_px
        == minimum_uncorroborated_overlap
    )
    builds = tuple(
        build
        for build in builds
        if not any(
            other is not build
            and _boundary_role_map_strictly_dominates(
                *physical_facts_by_identity[id(other)],
                *physical_facts_by_identity[id(build)],
            )
            for other in builds
        )
    )
    strongest_separator_support = max(
        build.objectives.supported_separator_count for build in builds
    )
    physically_anchored = tuple(
        build
        for build in builds
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


def assignment_consensus_builds(
    builds: tuple[SequenceBuild, ...],
) -> tuple[SequenceBuild, ...]:
    if not builds:
        raise ValueError("assignment consensus requires sequence builds")
    independently_supported = tuple(
        build for build in builds if _build_has_independent_boundary_support(build)
    )
    groups: dict[
        tuple[tuple[int, ObservationId], ...],
        list[SequenceBuild],
    ] = {}
    for build in independently_supported or builds:
        topology = tuple(
            (
                binding.boundary_index,
                binding.observation.provenance.observation_id,
            )
            for binding in build.separator_bindings
        )
        groups.setdefault(topology, []).append(build)
    return tuple(
        preferred
        for group in groups.values()
        for preferred in physically_preferred_builds(tuple(group))
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


def resolve_edge_constraint(
    frame_index: int,
    side: BoundarySide,
    constraint: measurement_facts.EdgeConstraint,
) -> tuple[ResolvedFrameBoundary, FrameEdgeAssignment | None]:
    observation = constraint.path or constraint.separator
    observed = constraint.basis in {
        FrameBoundarySource.GRAY_PATH_OBSERVATION,
        FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
    }
    anchor = (
        BoundaryAnchor(
            observation=observation,
            physical_role=side,
            role_state=constraint.state,
            role_authority=(
                BoundaryRoleAuthority.DIRECT_MEASUREMENT
                if constraint.state == EvidenceState.SUPPORTED
                else BoundaryRoleAuthority.UNAVAILABLE
            ),
            role_provenance=constraint.provenance,
        )
        if observed and observation is not None
        else None
    )
    resolution = ResolvedFrameBoundary(
        position=constraint.position,
        source=constraint.basis,
        geometry_state=constraint.geometry_state,
        boundary_anchor=anchor,
        inference_provenance=(None if anchor is not None else constraint.provenance),
    )
    if constraint.path is None:
        return resolution, None
    return (
        resolution,
        FrameEdgeAssignment(
            frame_index=frame_index,
            side=side,
            observation=constraint.path,
            resolution=resolution,
        ),
    )

def spacing_from_frame_edges(
    boundary_index: int,
    trailing: ResolvedFrameBoundary,
    leading: ResolvedFrameBoundary,
    *,
    separator_observation_supported: bool = True,
) -> InterFrameSpacing:
    trailing_provenance = trailing.measurement_provenance
    leading_provenance = leading.measurement_provenance
    same_observation = bool(
        trailing.boundary_anchor is not None
        and leading.boundary_anchor is not None
        and trailing_provenance.observation_id
        == leading_provenance.observation_id
    )
    shared_photo_edge = bool(
        same_observation
        and trailing.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
        and leading.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
        and boundary_role_is_independent_physical_measurement(trailing)
        and boundary_role_is_independent_physical_measurement(leading)
    )
    signed_width = (
        PixelInterval.exact(0.0)
        if shared_photo_edge
        else leading.position.minus(trailing.position)
    )
    measured_separator = bool(
        separator_observation_supported
        and
        signed_width.minimum > 0.0
        and same_observation
        and trailing.source == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        and leading.source == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
    )
    measured_contact = bool(
        shared_photo_edge
        or (
            signed_width.minimum == 0.0
            and signed_width.maximum == 0.0
            and same_observation
        )
    )
    distinct_observed_edges = bool(
        boundary_role_is_independent_physical_measurement(trailing)
        and boundary_role_is_independent_physical_measurement(leading)
        and trailing_provenance.observation_id
        != leading_provenance.observation_id
    )
    observed = bool(
        boundary_role_is_independent_physical_measurement(trailing)
        and boundary_role_is_independent_physical_measurement(leading)
        and (
            measured_separator
            or measured_contact
            or distinct_observed_edges
        )
    )
    root_measurement = (
        MeasurementIdentity.PHOTO_EDGES
        if observed
        else MeasurementIdentity.FRAME_GEOMETRY
    )
    provenance_inputs = (
        trailing_provenance,
        leading_provenance,
        *(
            (
                trailing.role_provenance,
                leading.role_provenance,
            )
            if observed
            else ()
        ),
    )
    provenance = MeasurementProvenance(
        root_measurement=root_measurement,
        observation_id=ObservationId(
            f"inter_frame_spacing:{root_measurement.value}:{boundary_index}:"
            f"{trailing_provenance.observation_id}:"
            f"{leading_provenance.observation_id}"
        ),
        dependencies=tuple(
            sorted(
                {
                    dependency
                    for input_provenance in provenance_inputs
                    if input_provenance is not None
                    for dependency in (
                        input_provenance.root_measurement,
                        *input_provenance.dependencies,
                    )
                    if dependency != root_measurement
                },
                key=lambda item: item.value,
            )
        ),
        description=(
            "measured inter-frame spacing"
            if observed
            else "inter-frame spacing hypothesis"
        ),
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    trailing_provenance.observation_id,
                    leading_provenance.observation_id,
                )
            )
        ),
    )
    return InterFrameSpacing(
        boundary=InterFrameBoundaryReference(None, boundary_index),
        signed_width_px=signed_width,
        provenance=provenance,
        basis=(
            InterFrameSpacingBasis.OBSERVED
            if observed
            else InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
        ),
    )

def uncorroborated_overlap_extent(
    spacings: tuple[InterFrameSpacing, ...],
) -> float:
    return sum(
        max(0.0, -spacing.signed_width_px.maximum)
        for spacing in spacings
        if spacing.basis == InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
    )

def unexplained_spacing_extent(
    spacings: tuple[InterFrameSpacing, ...],
) -> float:
    return sum(
        max(0.0, spacing.signed_width_px.minimum)
        for spacing in spacings
        if spacing.basis == InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
    )

def uncorroborated_contact_count(
    spacings: tuple[InterFrameSpacing, ...],
) -> int:
    return sum(
        spacing.kind == InterFrameSpacingKind.CONTACT
        and spacing.basis == InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
        for spacing in spacings
    )

def inferred_boundary_count(slots: tuple[FrameSlot, ...]) -> int:
    observed_sources = {
        FrameBoundarySource.GRAY_PATH_OBSERVATION,
        FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
    }
    return sum(
        boundary.source not in observed_sources
        for slot in slots
        for boundary in (slot.leading, slot.trailing)
    )

def long_axis_assignments_for_slots(
    assignments: tuple[FrameEdgeAssignment, ...],
    slots: tuple[FrameSlot, ...],
) -> tuple[FrameEdgeAssignment, ...]:
    boundaries = {
        (slot.index, side): boundary
        for slot in slots
        for side, boundary in (
            (BoundarySide.LEADING, slot.leading),
            (BoundarySide.TRAILING, slot.trailing),
        )
    }
    retained: list[FrameEdgeAssignment] = []
    for assignment in assignments:
        boundary = boundaries[(assignment.frame_index, assignment.side)]
        if (
            boundary.source != FrameBoundarySource.GRAY_PATH_OBSERVATION
            or boundary.boundary_anchor is None
            or boundary.boundary_anchor.observation != assignment.observation
        ):
            continue
        retained.append(replace(assignment, resolution=boundary))
    return tuple(retained)

def bindings_for_resolved_slots(
    bindings: tuple[SeparatorBandBinding, ...],
    slots: tuple[FrameSlot, ...],
) -> tuple[SeparatorBandBinding, ...]:
    resolved: list[SeparatorBandBinding] = []
    for binding in bindings:
        trailing = slots[binding.boundary_index - 1].trailing
        leading = slots[binding.boundary_index].leading
        if (
            trailing.source != FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
            or leading.source != FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
            or trailing.measurement_provenance != binding.observation.provenance
            or leading.measurement_provenance != binding.observation.provenance
        ):
            continue
        resolved.append(
            replace(
                binding,
                preceding_trailing_edge=trailing,
                following_leading_edge=leading,
            )
        )
    return tuple(resolved)

def rebuild_sequence_build(
    build: SequenceBuild,
    slots: tuple[FrameSlot, ...],
) -> SequenceBuild:
    long_axis_assignments = long_axis_assignments_for_slots(
        build.long_axis_assignments,
        slots,
    )
    separator_bindings = bindings_for_resolved_slots(
        build.separator_bindings,
        slots,
    )
    spacings = tuple(
        spacing_from_frame_edges(index, left.trailing, right.leading)
        for index, (left, right) in enumerate(zip(slots, slots[1:]), start=1)
    )
    return replace(
        build,
        slots=slots,
        long_axis_assignments=long_axis_assignments,
        separator_bindings=separator_bindings,
        spacings=spacings,
        objectives=replace(
            build.objectives,
            uncorroborated_overlap_extent_px=uncorroborated_overlap_extent(spacings),
            unexplained_spacing_extent_px=unexplained_spacing_extent(spacings),
            supported_separator_count=len(separator_bindings),
            internal_boundary_measurement_quality=float(
                sum(
                    boundary.independently_observed
                    for left, right in zip(slots, slots[1:])
                    for boundary in (left.trailing, right.leading)
                )
            ),
            external_boundary_measurement_quality=float(
                slots[0].leading.independently_observed
                + slots[-1].trailing.independently_observed
            ),
            inferred_boundary_count=inferred_boundary_count(slots),
        ),
    )
