from __future__ import annotations

from dataclasses import replace
import hashlib

from ...domain import (
    BoundarySide,
    EvidenceState,
    HolderBoundaryObservation,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)
from . import frame_sequence_candidates as sequence_candidates
from . import frame_sequence_measurements as measurement_facts
from .frame_dimensions import MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS
from .model import (
    BoundaryRoleAuthority,
    CommonFrameWidthResolution,
    FrameBoundarySource,
    FrameSlot,
    FrameWidthPhysicalScaleConstraint,
    ResolvedFrameBoundary,
    boundary_role_is_independent_physical_measurement,
)


def _slot_can_contribute_repeated_width_measurement(
    slot: FrameSlot,
    slot_count: int,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> bool:
    if slot.sequence_inferred or slot.index in {1, slot_count}:
        return False
    if any(
        boundary.source
        not in {
            FrameBoundarySource.GRAY_PATH_OBSERVATION,
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        }
        or boundary.boundary_anchor is None
        or not boundary.position_independently_observed
        for boundary in (slot.leading, slot.trailing)
    ):
        return False
    if any(
        boundary.source == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        and not boundary.independently_observed
        for boundary in (slot.leading, slot.trailing)
    ):
        return False
    if (
        slot.index == 1
        and measurement_facts.boundary_matches_holder(
            slot.leading,
            holder_boundaries.get(BoundarySide.LEADING),
        )
    ) or (
        slot.index == slot_count
        and measurement_facts.boundary_matches_holder(
            slot.trailing,
            holder_boundaries.get(BoundarySide.TRAILING),
        )
    ):
        return False
    return slot.width_px.minimum >= measurement_facts.MINIMUM_POSITIVE_PIXEL_EXTENT

def _repeated_width_role_provenance(
    slot_index: int,
    side: BoundarySide,
    contributors: tuple[FrameSlot, ...],
) -> MeasurementProvenance:
    measurements = tuple(
        candidate.measurement_provenance
        for slot in contributors
        for candidate in (slot.leading, slot.trailing)
    )
    anchors = tuple(
        dict.fromkeys(
            provenance.observation_id
            for provenance in measurements
        )
    )
    dependencies = tuple(
        sorted(
            {
                MeasurementIdentity.FRAME_WIDTH_PATTERN,
                *(
                    dependency
                    for provenance in measurements
                    for dependency in (
                        provenance.root_measurement,
                        *provenance.dependencies,
                    )
                    if dependency
                    not in {
                        MeasurementIdentity.FRAME_DIMENSIONS,
                        MeasurementIdentity.FRAME_GEOMETRY,
                    }
                ),
            },
            key=lambda item: item.value,
        )
    )
    digest = hashlib.sha256(
        "\x1f".join(map(str, anchors)).encode("utf-8")
    ).hexdigest()
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(
            f"repeated_frame_width_photo_edge:{slot_index}:{side.value}:{digest}"
        ),
        dependencies=dependencies,
        description=(
            "photo-edge role corroborated by repeated complete frame-width "
            "measurements"
        ),
        boundary_anchors=anchors,
    )

def corroborate_build_roles_from_repeated_frame_width(
    build: sequence_candidates.SequenceBuild,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> sequence_candidates.SequenceBuild:
    candidates = tuple(
        slot
        for slot in build.slots
        if _slot_can_contribute_repeated_width_measurement(
            slot,
            len(build.slots),
            holder_boundaries,
        )
    )
    contributor_indexes = measurement_facts.largest_measurement_compatible_interval_indexes(
        tuple(slot.width_px for slot in candidates),
        MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS,
    )
    if not contributor_indexes:
        return build
    contributors = tuple(candidates[index] for index in contributor_indexes)
    contributor_slot_indexes = {slot.index for slot in contributors}
    slots: list[FrameSlot] = []
    for slot in build.slots:
        if slot.index not in contributor_slot_indexes:
            slots.append(slot)
            continue
        boundaries: dict[BoundarySide, ResolvedFrameBoundary] = {}
        for side, boundary in (
            (BoundarySide.LEADING, slot.leading),
            (BoundarySide.TRAILING, slot.trailing),
        ):
            if boundary.boundary_anchor is None:
                raise ValueError("repeated frame-width role requires raw boundaries")
            if boundary.independently_observed:
                boundaries[side] = boundary
                continue
            boundaries[side] = replace(
                boundary,
                boundary_anchor=replace(
                    boundary.boundary_anchor,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=BoundaryRoleAuthority.MEASUREMENT_CORROBORATED,
                    role_provenance=_repeated_width_role_provenance(
                        slot.index,
                        side,
                        contributors,
                    ),
                ),
            )
        slots.append(
            replace(
                slot,
                leading=boundaries[BoundarySide.LEADING],
                trailing=boundaries[BoundarySide.TRAILING],
            )
        )
    return sequence_candidates.rebuild_sequence_build(build, tuple(slots))

def _physical_scale_corroborated_role_provenance(
    boundary: ResolvedFrameBoundary,
    opposite: ResolvedFrameBoundary,
    side: BoundarySide,
    scale_constraint: FrameWidthPhysicalScaleConstraint,
) -> MeasurementProvenance:
    opposite_role = opposite.role_provenance
    assert opposite_role is not None
    measurement = boundary.measurement_provenance
    dependencies = tuple(
        sorted(
            {
                measurement.root_measurement,
                *measurement.dependencies,
                opposite.measurement_provenance.root_measurement,
                *opposite.measurement_provenance.dependencies,
                opposite_role.root_measurement,
                *opposite_role.dependencies,
                scale_constraint.provenance.root_measurement,
                *scale_constraint.provenance.dependencies,
            }
            - {MeasurementIdentity.FRAME_GEOMETRY},
            key=lambda item: item.value,
        )
    )
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(
            "physical_scale_corroborated_photo_edge:"
            f"{side.value}:{measurement.observation_id}:"
            f"{opposite.measurement_provenance.observation_id}:"
            f"{scale_constraint.provenance.observation_id}"
        ),
        dependencies=dependencies,
        description=(
            "measured gray boundary corroborated as a photo edge by an "
            "independent internal anchor and physical frame scale"
        ),
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    measurement.observation_id,
                    opposite.measurement_provenance.observation_id,
                    *opposite_role.boundary_anchors,
                    *scale_constraint.provenance.boundary_anchors,
                )
            )
        ),
    )

def _corroborate_boundary_role_from_physical_scale(
    boundary: ResolvedFrameBoundary,
    opposite: ResolvedFrameBoundary,
    side: BoundarySide,
    scale_constraint: FrameWidthPhysicalScaleConstraint | None,
    *,
    opposite_is_internal: bool,
) -> ResolvedFrameBoundary:
    opposite_role = opposite.role_provenance
    if (
        scale_constraint is None
        or not opposite_is_internal
        or boundary.source
        not in {
            FrameBoundarySource.GRAY_PATH_OBSERVATION,
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        }
        or boundary.boundary_anchor is None
        or boundary.role_state == EvidenceState.SUPPORTED
        or not boundary_role_is_independent_physical_measurement(opposite)
        or opposite_role is None
    ):
        return boundary
    expected = (
        opposite.position.minus(scale_constraint.width_px)
        if side == BoundarySide.LEADING
        else opposite.position.plus(scale_constraint.width_px)
    )
    if not boundary.position.intersects(expected):
        return boundary
    return replace(
        boundary,
        boundary_anchor=replace(
            boundary.boundary_anchor,
            role_state=EvidenceState.SUPPORTED,
            role_authority=BoundaryRoleAuthority.GEOMETRY_CORROBORATED,
            role_provenance=_physical_scale_corroborated_role_provenance(
                boundary,
                opposite,
                side,
                scale_constraint,
            ),
        ),
    )

def corroborate_build_roles_from_physical_scale(
    build: sequence_candidates.SequenceBuild,
    scale_constraint: FrameWidthPhysicalScaleConstraint | None,
) -> sequence_candidates.SequenceBuild:
    original = build.slots
    count = len(original)
    slots = tuple(
        replace(
            slot,
            leading=_corroborate_boundary_role_from_physical_scale(
                slot.leading,
                slot.trailing,
                BoundarySide.LEADING,
                scale_constraint,
                opposite_is_internal=slot.index < count,
            ),
            trailing=_corroborate_boundary_role_from_physical_scale(
                slot.trailing,
                slot.leading,
                BoundarySide.TRAILING,
                scale_constraint,
                opposite_is_internal=slot.index > 1,
            ),
        )
        for slot in original
    )
    return build if slots == original else sequence_candidates.rebuild_sequence_build(build, slots)

def _dimension_corroborated_role_provenance(
    boundary: ResolvedFrameBoundary,
    opposite: ResolvedFrameBoundary,
    side: BoundarySide,
    common_width: CommonFrameWidthResolution,
) -> MeasurementProvenance:
    measurement = boundary.measurement_provenance
    opposite_role = opposite.role_provenance
    assert opposite_role is not None
    dependencies = tuple(
        sorted(
            {
                measurement.root_measurement,
                common_width.provenance.root_measurement,
                *common_width.provenance.dependencies,
                opposite_role.root_measurement,
                *opposite_role.dependencies,
            }
            - {MeasurementIdentity.FRAME_GEOMETRY},
            key=lambda item: item.value,
        )
    )
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(
            "dimension_corroborated_photo_edge:"
            f"{side.value}:{measurement.observation_id}:"
            f"{common_width.provenance.observation_id}"
        ),
        dependencies=dependencies,
        description=(
            "measured gray boundary corroborated as a photo edge by independent "
            "common frame width"
        ),
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    measurement.observation_id,
                    opposite.measurement_provenance.observation_id,
                    *common_width.provenance.boundary_anchors,
                )
            )
        ),
    )

def _corroborate_boundary_role_from_common_width(
    boundary: ResolvedFrameBoundary,
    opposite: ResolvedFrameBoundary,
    side: BoundarySide,
    common_width: CommonFrameWidthResolution,
) -> ResolvedFrameBoundary:
    if (
        boundary.source
        not in {
            FrameBoundarySource.GRAY_PATH_OBSERVATION,
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        }
        or boundary.boundary_anchor is None
        or boundary.role_state == EvidenceState.SUPPORTED
        or not opposite.independently_observed
        or common_width.state != EvidenceState.SUPPORTED
        or common_width.width_px is None
    ):
        return boundary
    expected = (
        opposite.position.minus(common_width.width_px)
        if side == BoundarySide.LEADING
        else opposite.position.plus(common_width.width_px)
    )
    if not boundary.position.intersects(expected):
        return boundary
    return replace(
        boundary,
        boundary_anchor=replace(
            boundary.boundary_anchor,
            role_state=EvidenceState.SUPPORTED,
            role_authority=BoundaryRoleAuthority.GEOMETRY_CORROBORATED,
            role_provenance=_dimension_corroborated_role_provenance(
                boundary,
                opposite,
                side,
                common_width,
            ),
        ),
    )

def _adjacent_boundary_role_provenance(
    supported: ResolvedFrameBoundary,
    target: ResolvedFrameBoundary,
) -> MeasurementProvenance:
    supported_role = supported.role_provenance
    assert supported_role is not None
    target_measurement = target.measurement_provenance
    supported_measurement = supported.measurement_provenance
    dependencies = tuple(
        sorted(
            {
                target_measurement.root_measurement,
                *target_measurement.dependencies,
                supported_measurement.root_measurement,
                *supported_measurement.dependencies,
                supported_role.root_measurement,
                *supported_role.dependencies,
            }
            - {
                MeasurementIdentity.FRAME_DIMENSIONS,
                MeasurementIdentity.FRAME_GEOMETRY,
            },
            key=lambda item: item.value,
        )
    )
    anchors = tuple(
        dict.fromkeys(
            (
                target_measurement.observation_id,
                supported_measurement.observation_id,
                *supported_role.boundary_anchors,
            )
        )
    )
    digest = hashlib.sha256(
        "\x1f".join(map(str, anchors)).encode("utf-8")
    ).hexdigest()
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(
            f"adjacent_frame_edge_role:{digest}"
        ),
        dependencies=dependencies,
        description=(
            "photo-edge role corroborated by an independent coincident "
            "adjacent-frame measurement"
        ),
        boundary_anchors=anchors,
    )

def _corroborate_adjacent_boundary(
    target: ResolvedFrameBoundary,
    supported: ResolvedFrameBoundary,
) -> ResolvedFrameBoundary:
    supported_role = supported.role_provenance
    if (
        target.boundary_anchor is None
        or target.role_state == EvidenceState.SUPPORTED
        or not supported.independently_observed
        or supported_role is None
        or supported_role.root_measurement
        in {
            MeasurementIdentity.FRAME_DIMENSIONS,
            MeasurementIdentity.FRAME_GEOMETRY,
        }
        or any(
            dependency
            in {
                MeasurementIdentity.FRAME_DIMENSIONS,
                MeasurementIdentity.FRAME_GEOMETRY,
            }
            for dependency in supported_role.dependencies
        )
        or target.measurement_provenance.root_measurement
        == supported.measurement_provenance.root_measurement
        or target.measurement_provenance.observation_id
        == supported.measurement_provenance.observation_id
        or not target.position.intersects(supported.position)
    ):
        return target
    return replace(
        target,
        boundary_anchor=replace(
            target.boundary_anchor,
            role_state=EvidenceState.SUPPORTED,
            role_authority=BoundaryRoleAuthority.MEASUREMENT_CORROBORATED,
            role_provenance=_adjacent_boundary_role_provenance(
                supported,
                target,
            ),
        ),
    )

def corroborate_adjacent_boundary_pair(
    trailing: ResolvedFrameBoundary,
    leading: ResolvedFrameBoundary,
) -> tuple[ResolvedFrameBoundary, ResolvedFrameBoundary]:
    return (
        _corroborate_adjacent_boundary(trailing, leading),
        _corroborate_adjacent_boundary(leading, trailing),
    )

def corroborate_build_adjacent_boundary_roles(
    build: sequence_candidates.SequenceBuild,
) -> sequence_candidates.SequenceBuild:
    slots = list(build.slots)
    for index in range(len(slots) - 1):
        trailing, leading = corroborate_adjacent_boundary_pair(
            build.slots[index].trailing,
            build.slots[index + 1].leading,
        )
        slots[index] = replace(slots[index], trailing=trailing)
        slots[index + 1] = replace(slots[index + 1], leading=leading)
    resolved_slots = tuple(slots)
    return (
        build
        if resolved_slots == build.slots
        else sequence_candidates.rebuild_sequence_build(build, resolved_slots)
    )

def corroborate_build_boundary_roles(
    build: sequence_candidates.SequenceBuild,
    common_width: CommonFrameWidthResolution,
) -> sequence_candidates.SequenceBuild:
    original_slots = build.slots
    slots = tuple(
        replace(
            slot,
            leading=_corroborate_boundary_role_from_common_width(
                slot.leading,
                slot.trailing,
                BoundarySide.LEADING,
                common_width,
            ),
            trailing=_corroborate_boundary_role_from_common_width(
                slot.trailing,
                slot.leading,
                BoundarySide.TRAILING,
                common_width,
            ),
        )
        for slot in original_slots
    )
    return (
        build
        if slots == build.slots
        else sequence_candidates.rebuild_sequence_build(build, slots)
    )
