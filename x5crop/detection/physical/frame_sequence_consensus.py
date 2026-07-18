from __future__ import annotations

from dataclasses import replace
import hashlib

from ...domain import (
    BoundarySide,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from . import frame_sequence_candidates as sequence_candidates
from .model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    BoundaryGeometryState,
    FrameBoundarySource,
    FrameEdgeAssignment,
    FrameSlot,
    ResolvedFrameBoundary,
)


def _assignment_consensus(
    builds: tuple[sequence_candidates.SequenceBuild, ...],
) -> BoundaryAssignmentConsensus:
    conflicting = sequence_candidates.conflicting_internal_frame_indexes(builds)
    if conflicting:
        outcome = AssignmentConsensusOutcome.DISAGREED
    elif len(builds) == 1:
        outcome = AssignmentConsensusOutcome.UNCONTESTED
    elif sequence_candidates.external_endpoint_alternatives(builds):
        outcome = AssignmentConsensusOutcome.EXTERNAL_SAFETY_ENVELOPE
    else:
        outcome = AssignmentConsensusOutcome.AGREED
    return BoundaryAssignmentConsensus(outcome, len(builds), conflicting)

def sequence_assignment_consensus(
    preferred_builds: tuple[sequence_candidates.SequenceBuild, ...],
) -> BoundaryAssignmentConsensus:
    inferred_signatures = tuple(
        frozenset(
            slot.index
            for slot in build.slots
            if slot.sequence_inferred
        )
        for build in preferred_builds
    )
    if len(set(inferred_signatures)) > 1:
        inferred_positions = set().union(*inferred_signatures)
        common_positions = set(inferred_signatures[0]).intersection(
            *inferred_signatures[1:]
        )
        return BoundaryAssignmentConsensus(
            AssignmentConsensusOutcome.DISAGREED,
            len(preferred_builds),
            tuple(sorted(inferred_positions - common_positions)),
        )
    return _assignment_consensus(preferred_builds)

def _external_safety_provenance(
    side: BoundarySide,
    boundaries: tuple[ResolvedFrameBoundary, ...],
) -> MeasurementProvenance:
    inputs = tuple(
        dict.fromkeys(
            (
                *(boundary.measurement_provenance for boundary in boundaries),
                *(
                    boundary.role_provenance
                    for boundary in boundaries
                    if boundary.role_provenance is not None
                ),
            )
        )
    )
    dependencies = tuple(
        sorted(
            {
                dependency
                for item in inputs
                for dependency in (item.root_measurement, *item.dependencies)
                if dependency != MeasurementIdentity.FRAME_GEOMETRY
            },
            key=lambda item: item.value,
        )
    )
    anchors = tuple(
        dict.fromkeys(
            anchor
            for item in inputs
            for anchor in (item.observation_id, *item.boundary_anchors)
        )
    )
    digest = hashlib.sha256(
        "\x1f".join(
            (
                side.value,
                *(
                    f"{boundary.position.minimum:.12g}:"
                    f"{boundary.position.maximum:.12g}:"
                    f"{boundary.measurement_provenance.observation_id}"
                    for boundary in boundaries
                ),
            )
        ).encode("utf-8")
    ).hexdigest()
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        observation_id=ObservationId(f"external_safety_envelope:{digest}"),
        dependencies=dependencies,
        description=(
            "conservative external crop boundary spanning physically equivalent "
            "endpoint observations"
        ),
        boundary_anchors=anchors,
    )

def internal_geometry_uncertainty_boundary(
    side: BoundarySide,
    boundaries: tuple[ResolvedFrameBoundary, ...],
) -> ResolvedFrameBoundary:
    if side not in {BoundarySide.LEADING, BoundarySide.TRAILING}:
        raise ValueError("internal geometry uncertainty requires a long-axis side")
    if not boundaries or any(
        boundary.source != FrameBoundarySource.DIMENSION_CONSTRAINED
        or boundary.independently_observed
        for boundary in boundaries
    ):
        raise ValueError(
            "internal geometry uncertainty can combine only dimension constraints"
        )
    inputs = tuple(
        dict.fromkeys(boundary.measurement_provenance for boundary in boundaries)
    )
    dependencies = tuple(
        sorted(
            {
                dependency
                for item in inputs
                for dependency in (item.root_measurement, *item.dependencies)
                if dependency != MeasurementIdentity.FRAME_GEOMETRY
            },
            key=lambda item: item.value,
        )
    )
    anchors = tuple(
        dict.fromkeys(
            anchor
            for item in inputs
            for anchor in (item.observation_id, *item.boundary_anchors)
        )
    )
    digest = hashlib.sha256(
        "\x1f".join(
            (
                side.value,
                *(
                    f"{boundary.position.minimum:.12g}:"
                    f"{boundary.position.maximum:.12g}:"
                    f"{boundary.measurement_provenance.observation_id}"
                    for boundary in boundaries
                ),
            )
        ).encode("utf-8")
    ).hexdigest()
    return ResolvedFrameBoundary(
        position=PixelInterval(
            min(boundary.position.minimum for boundary in boundaries),
            max(boundary.position.maximum for boundary in boundaries),
        ),
        source=FrameBoundarySource.DIMENSION_CONSTRAINED,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=None,
        inference_provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
            observation_id=ObservationId(
                f"internal_geometry_uncertainty:{side.value}:{digest}"
            ),
            dependencies=dependencies,
            description=(
                "conservative internal boundary interval across equivalent "
                "dimension-constrained sequence solutions"
            ),
            boundary_anchors=anchors,
        ),
    )

def apply_internal_geometry_uncertainty(
    slots: tuple[FrameSlot, ...],
    assignments: tuple[FrameEdgeAssignment, ...],
    preferred_builds: tuple[sequence_candidates.SequenceBuild, ...],
) -> tuple[tuple[FrameSlot, ...], tuple[FrameEdgeAssignment, ...]] | None:
    if len(preferred_builds) <= 1:
        return slots, assignments
    updated = list(slots)
    replaced: set[tuple[int, BoundarySide]] = set()
    for offset, slot in enumerate(slots):
        sides = tuple(
            side
            for side in (BoundarySide.LEADING, BoundarySide.TRAILING)
            if not (
                (offset == 0 and side == BoundarySide.LEADING)
                or (
                    offset == len(slots) - 1
                    and side == BoundarySide.TRAILING
                )
            )
        )
        for side in sides:
            boundaries = tuple(
                (
                    build.slots[offset].leading
                    if side == BoundarySide.LEADING
                    else build.slots[offset].trailing
                )
                for build in preferred_builds
            )
            if PixelInterval.common_intersection(
                tuple(boundary.position for boundary in boundaries)
            ) is not None:
                continue
            if any(
                boundary.source != FrameBoundarySource.DIMENSION_CONSTRAINED
                or boundary.independently_observed
                for boundary in boundaries
            ):
                return None
            envelope = internal_geometry_uncertainty_boundary(side, boundaries)
            current = updated[offset]
            updated[offset] = replace(
                current,
                leading=(envelope if side == BoundarySide.LEADING else current.leading),
                trailing=(envelope if side == BoundarySide.TRAILING else current.trailing),
                visible_long_axis=PixelInterval(
                    (
                        envelope.position.minimum
                        if side == BoundarySide.LEADING
                        else current.visible_long_axis.minimum
                    ),
                    (
                        envelope.position.maximum
                        if side == BoundarySide.TRAILING
                        else current.visible_long_axis.maximum
                    ),
                ),
            )
            replaced.add((slot.index, side))
    result = tuple(updated)
    if not sequence_candidates.frame_slots_are_strictly_monotonic(result):
        return None
    return (
        result,
        tuple(
            assignment
            for assignment in assignments
            if (assignment.frame_index, assignment.side) not in replaced
        ),
    )

def external_safety_boundary(
    side: BoundarySide,
    boundaries: tuple[ResolvedFrameBoundary, ...],
    holder_safety: PixelInterval,
) -> ResolvedFrameBoundary | None:
    position = PixelInterval(
        min(boundary.position.minimum for boundary in boundaries),
        max(boundary.position.maximum for boundary in boundaries),
    ).intersection(holder_safety)
    if position is None:
        return None
    return ResolvedFrameBoundary(
        position=position,
        source=FrameBoundarySource.EXTERNAL_SAFETY_ENVELOPE,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=None,
        inference_provenance=_external_safety_provenance(side, boundaries),
    )

def apply_external_safety_envelope(
    slots: tuple[FrameSlot, ...],
    assignments: tuple[FrameEdgeAssignment, ...],
    preferred_builds: tuple[sequence_candidates.SequenceBuild, ...],
    consensus: BoundaryAssignmentConsensus,
    holder_safety: PixelInterval,
) -> tuple[tuple[FrameSlot, ...], tuple[FrameEdgeAssignment, ...]] | None:
    if (
        consensus.outcome != AssignmentConsensusOutcome.EXTERNAL_SAFETY_ENVELOPE
        or not slots
    ):
        return slots, assignments
    updated = list(slots)
    replaced: set[tuple[int, BoundarySide]] = set()
    for offset, side in (
        (0, BoundarySide.LEADING),
        (len(slots) - 1, BoundarySide.TRAILING),
    ):
        slot = updated[offset]
        if slot.sequence_inferred or slot.edge_occlusion is not None:
            continue
        boundaries = tuple(
            (
                build.slots[offset].leading
                if side == BoundarySide.LEADING
                else build.slots[offset].trailing
            )
            for build in preferred_builds
        )
        if PixelInterval.common_intersection(
            tuple(boundary.position for boundary in boundaries)
        ) is not None:
            continue
        safe_boundary = external_safety_boundary(
            side,
            boundaries,
            holder_safety,
        )
        if safe_boundary is None:
            return None
        updated[offset] = replace(
            slot,
            leading=(safe_boundary if side == BoundarySide.LEADING else slot.leading),
            trailing=(safe_boundary if side == BoundarySide.TRAILING else slot.trailing),
            visible_long_axis=PixelInterval(
                (
                    safe_boundary.position.minimum
                    if side == BoundarySide.LEADING
                    else slot.visible_long_axis.minimum
                ),
                (
                    safe_boundary.position.maximum
                    if side == BoundarySide.TRAILING
                    else slot.visible_long_axis.maximum
                ),
            ),
        )
        replaced.add((slot.index, side))
    return (
        tuple(updated),
        tuple(
            assignment
            for assignment in assignments
            if (assignment.frame_index, assignment.side) not in replaced
        ),
    )
