from __future__ import annotations

from dataclasses import replace

from ...domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    FrameDimensionPrior,
    FrameSequenceSearchScope,
    GrayBoundaryPathObservation,
    HolderBoundaryObservation,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from . import frame_sequence_boundary_roles as boundary_roles
from . import frame_sequence_candidates as sequence_candidates
from . import frame_sequence_common_width as width_resolution
from . import frame_sequence_measurements as measurement_facts
from .model import (
    BoundaryGeometryState,
    CommonFrameWidthResolution,
    FrameEdgeAssignment,
    FrameBoundarySource,
    FrameSlot,
    PhotoHeightEvidence,
    ResolvedFrameBoundary,
)


def holder_boundaries(
    search_scope: FrameSequenceSearchScope,
) -> dict[BoundarySide, HolderBoundaryObservation]:
    return {
        boundary.side: boundary
        for boundary in search_scope.holder_safety.boundaries
    }


def _common_width_dimension_provenance(
    frame_index: int,
    side: BoundarySide,
    anchor: ResolvedFrameBoundary,
    common_width: CommonFrameWidthResolution,
) -> MeasurementProvenance:
    dependencies = tuple(
        sorted(
            {
                anchor.measurement_provenance.root_measurement,
                *anchor.measurement_provenance.dependencies,
                common_width.provenance.root_measurement,
                *common_width.provenance.dependencies,
            }
            - {MeasurementIdentity.FRAME_GEOMETRY},
            key=lambda item: item.value,
        )
    )
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        observation_id=ObservationId(
            "common_width_dimension_boundary:"
            f"{frame_index}:{side.value}:"
            f"{anchor.measurement_provenance.observation_id}:"
            f"{common_width.provenance.observation_id}"
        ),
        dependencies=dependencies,
        description="frame boundary resolved from a positional anchor and common width",
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    anchor.measurement_provenance.observation_id,
                    *common_width.provenance.boundary_anchors,
                )
            )
        ),
    )


def _resolved_dimension_boundary(
    frame_index: int,
    side: BoundarySide,
    boundary: ResolvedFrameBoundary,
    anchor: ResolvedFrameBoundary,
    common_width: CommonFrameWidthResolution,
    holder_boundary: HolderBoundaryObservation | None,
) -> ResolvedFrameBoundary:
    unproven_observation_assignment = bool(
        boundary.source
        in {
            FrameBoundarySource.GRAY_PATH_OBSERVATION,
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        }
        and boundary.role_state == EvidenceState.UNAVAILABLE
    )
    dimension_candidate = bool(
        boundary.source == FrameBoundarySource.DIMENSION_CONSTRAINED
        or unproven_observation_assignment
    )
    if (
        not dimension_candidate
        or common_width.state != EvidenceState.SUPPORTED
        or common_width.width_px is None
        or not anchor.geometry_resolved
    ):
        return boundary
    if unproven_observation_assignment and measurement_facts.boundary_matches_holder(
        boundary,
        holder_boundary,
    ):
        return boundary
    expected = (
        anchor.position.minus(common_width.width_px)
        if side == BoundarySide.LEADING
        else anchor.position.plus(common_width.width_px)
    )
    if (
        unproven_observation_assignment
        and boundary.position.intersects(expected)
    ):
        return boundary
    resolved_position = boundary.position.intersection(expected)
    if resolved_position is None and unproven_observation_assignment:
        resolved_position = expected
    if resolved_position is None:
        return boundary
    return ResolvedFrameBoundary(
        position=resolved_position,
        source=FrameBoundarySource.DIMENSION_CONSTRAINED,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=None,
        inference_provenance=_common_width_dimension_provenance(
            frame_index,
            side,
            anchor,
            common_width,
        ),
    )


def resolve_dimension_boundaries_from_common_width(
    slots: tuple[FrameSlot, ...],
    common_width: CommonFrameWidthResolution,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> tuple[FrameSlot, ...]:
    resolved: list[FrameSlot] = []
    for slot in slots:
        leading = _resolved_dimension_boundary(
            slot.index,
            BoundarySide.LEADING,
            slot.leading,
            slot.trailing,
            common_width,
            (
                holder_boundaries.get(BoundarySide.LEADING)
                if slot.index == 1
                else None
            ),
        )
        trailing = _resolved_dimension_boundary(
            slot.index,
            BoundarySide.TRAILING,
            slot.trailing,
            slot.leading,
            common_width,
            (
                holder_boundaries.get(BoundarySide.TRAILING)
                if slot.index == len(slots)
                else None
            ),
        )
        if trailing.position.minimum <= leading.position.maximum:
            resolved.append(slot)
            continue
        resolved.append(
            replace(
                slot,
                leading=leading,
                trailing=trailing,
                visible_long_axis=PixelInterval(
                    leading.position.minimum,
                    trailing.position.maximum,
                ),
            )
        )
    candidate = tuple(resolved)
    return (
        candidate
        if sequence_candidates.frame_slots_are_strictly_monotonic(candidate)
        else slots
    )


def resolve_build_dimension_boundaries(
    build: sequence_candidates.SequenceBuild,
    common_width: CommonFrameWidthResolution,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> sequence_candidates.SequenceBuild:
    slots = resolve_dimension_boundaries_from_common_width(
        build.slots,
        common_width,
        holder_boundaries,
    )
    if slots == build.slots:
        return build
    return sequence_candidates.rebuild_sequence_build(build, slots)


def resolve_build_physical_boundaries(
    build: sequence_candidates.SequenceBuild,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> tuple[sequence_candidates.SequenceBuild, CommonFrameWidthResolution]:
    resolved = boundary_roles.corroborate_build_roles_from_repeated_frame_width(
        build,
        holder_boundaries,
    )
    resolved = boundary_roles.corroborate_build_adjacent_boundary_roles(resolved)
    resolved = boundary_roles.corroborate_build_roles_from_physical_scale(
        resolved,
        width_resolution.frame_width_physical_scale_constraint(
            photo_height_evidence,
            dimensions,
        ),
    )
    common_width = width_resolution.resolve_common_frame_width(
        resolved.slots,
        holder_boundaries,
        photo_height_evidence,
        dimensions,
    )
    resolved = boundary_roles.corroborate_build_boundary_roles(resolved, common_width)
    common_width = width_resolution.resolve_common_frame_width(
        resolved.slots,
        holder_boundaries,
        photo_height_evidence,
        dimensions,
    )
    resolved = resolve_build_dimension_boundaries(
        resolved,
        common_width,
        holder_boundaries,
    )
    return resolved, common_width


def _boundary_path_assignment(
    build: sequence_candidates.SequenceBuild,
    slot_offset: int,
    side: BoundarySide,
    path: GrayBoundaryPathObservation,
    common_width: CommonFrameWidthResolution,
) -> tuple[tuple[FrameSlot, ...], FrameEdgeAssignment] | None:
    if (
        common_width.state != EvidenceState.SUPPORTED
        or common_width.width_px is None
        or path.axis != BoundaryAxis.LONG
        or not 0 <= slot_offset < len(build.slots)
    ):
        return None
    slot = build.slots[slot_offset]
    if slot.sequence_inferred:
        return None
    boundary = slot.leading if side == BoundarySide.LEADING else slot.trailing
    if boundary.source != FrameBoundarySource.DIMENSION_CONSTRAINED:
        return None
    if not measurement_facts.measurement_intervals_are_compatible(
        boundary.position,
        path.position,
    ):
        return None
    constraint = measurement_facts.EdgeConstraint(
        position=path.position,
        basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
        state=EvidenceState.UNAVAILABLE,
        geometry_state=BoundaryGeometryState.RESOLVED,
        provenance=path.provenance,
        path=path,
    )
    resolution, assignment = sequence_candidates.resolve_edge_constraint(slot.index, side, constraint)
    assert assignment is not None
    updated_slot = replace(
        slot,
        leading=(resolution if side == BoundarySide.LEADING else slot.leading),
        trailing=(resolution if side == BoundarySide.TRAILING else slot.trailing),
        visible_long_axis=PixelInterval(
            (
                resolution.position.minimum
                if side == BoundarySide.LEADING
                else slot.leading.position.minimum
            ),
            (
                resolution.position.maximum
                if side == BoundarySide.TRAILING
                else slot.trailing.position.maximum
            ),
        ),
    )
    if (
        not measurement_facts.measurement_intervals_are_compatible(
            updated_slot.width_px,
            common_width.width_px,
        )
        or updated_slot.trailing.position.minimum
        <= updated_slot.leading.position.maximum
    ):
        return None
    slots = list(build.slots)
    slots[slot_offset] = updated_slot
    resolved_slots = tuple(slots)
    if not sequence_candidates.frame_slots_are_strictly_monotonic(resolved_slots):
        return None
    return resolved_slots, assignment


def assign_unique_boundary_path_observations(
    build: sequence_candidates.SequenceBuild,
    common_width: CommonFrameWidthResolution,
    paths: tuple[GrayBoundaryPathObservation, ...],
) -> sequence_candidates.SequenceBuild:
    resolved = build
    remaining = tuple(
        path
        for path in paths
        if path.provenance.observation_id
        not in {
            assignment.observation.provenance.observation_id
            for assignment in build.long_axis_assignments
        }
    )
    while remaining:
        candidates: dict[
            tuple[int, BoundarySide],
            list[
                tuple[
                    GrayBoundaryPathObservation,
                    tuple[FrameSlot, ...],
                    FrameEdgeAssignment,
                ]
            ],
        ] = {}
        path_boundaries: dict[
            ObservationId,
            list[tuple[int, BoundarySide]],
        ] = {}
        for slot_offset in range(len(resolved.slots)):
            for side in (BoundarySide.LEADING, BoundarySide.TRAILING):
                key = slot_offset, side
                for path in remaining:
                    assignment = _boundary_path_assignment(
                        resolved,
                        slot_offset,
                        side,
                        path,
                        common_width,
                    )
                    if assignment is None:
                        continue
                    slots, edge_assignment = assignment
                    candidates.setdefault(key, []).append(
                        (path, slots, edge_assignment)
                    )
                    path_boundaries.setdefault(
                        path.provenance.observation_id,
                        [],
                    ).append(key)
        unique = tuple(
            items[0]
            for key, items in sorted(
                candidates.items(),
                key=lambda item: (item[0][0], item[0][1].value),
            )
            if len(items) == 1
            and len(
                path_boundaries[items[0][0].provenance.observation_id]
            )
            == 1
        )
        if not unique:
            break
        path, slots, assignment = unique[0]
        resolved = sequence_candidates.rebuild_sequence_build(
            replace(
                resolved,
                long_axis_assignments=(
                    *resolved.long_axis_assignments,
                    assignment,
                ),
            ),
            slots,
        )
        assigned_id = path.provenance.observation_id
        remaining = tuple(
            item
            for item in remaining
            if item.provenance.observation_id != assigned_id
        )
    return resolved
