from __future__ import annotations

from dataclasses import replace

from ...domain import (
    BoundarySide,
    EvidenceState,
    FrameDimensionPrior,
    FrameSequenceSearchScope,
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
            },
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
