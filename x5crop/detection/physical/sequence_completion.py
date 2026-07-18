from __future__ import annotations

import hashlib

from ...domain import (
    BoundarySide,
    EvidenceState,
    HolderSafetyEnvelope,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    InterFrameSpacingKind,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from .model import (
    SequenceSlotPosition,
    SequenceInferredSlotGeometry,
    BoundaryGeometryState,
    CommonFrameWidthResolution,
    FrameContentOccupancy,
    FrameSlot,
    FrameBoundarySource,
    ResolvedFrameBoundary,
)
from .frame_dimensions import MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS


def measured_sequence_supports_slot_inference(
    real_slots: tuple[FrameSlot, ...],
    spacings: tuple[InterFrameSpacing, ...],
    common_width: CommonFrameWidthResolution,
) -> bool:
    if (
        not real_slots
        or len(spacings) != len(real_slots) - 1
        or common_width.state != EvidenceState.SUPPORTED
        or common_width.width_px is None
        or any(
            slot.sequence_inferred
            or not slot.leading.geometry_resolved
            or not slot.trailing.geometry_resolved
            or not (
                slot.leading.independently_observed
                or slot.trailing.independently_observed
            )
            for slot in real_slots
        )
    ):
        return False
    nominal_slot_sized_gap_count = 0
    for spacing in spacings:
        if spacing.basis != InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS:
            continue
        if spacing.kind == InterFrameSpacingKind.OVERLAP:
            return False
        if spacing.signed_width_px.maximum < common_width.width_px.minimum:
            continue
        if spacing.signed_width_px.minimum < common_width.width_px.minimum:
            return False
        nominal_slot_sized_gap_count += 1
        if nominal_slot_sized_gap_count > 1:
            return False
    return True


def _common_width_is_independently_supported(
    real_slots: tuple[FrameSlot, ...],
    common_width: CommonFrameWidthResolution,
) -> bool:
    if (
        common_width.state != EvidenceState.SUPPORTED
        or not common_width.constraints
        or (
            len(common_width.constraints)
            < MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS
            and common_width.physical_scale_constraint is None
        )
    ):
        return False
    by_index = {slot.index: slot for slot in real_slots}
    assert common_width.width_px is not None
    constraints_match_slots = all(
        (slot := by_index.get(constraint.frame_index)) is not None
        and constraint.leading == slot.leading
        and constraint.trailing == slot.trailing
        and not slot.sequence_inferred
        and slot.width_px.intersects(common_width.width_px)
        for constraint in common_width.constraints
    )
    if not constraints_match_slots:
        return False
    if len(common_width.constraints) >= MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
        return all(
            constraint.leading.independently_observed
            and constraint.trailing.independently_observed
            for constraint in common_width.constraints
        )
    if common_width.physical_scale_constraint is None:
        return False
    constraint = common_width.constraints[0]
    return bool(
        constraint.leading.position_independently_observed
        and constraint.trailing.position_independently_observed
        and constraint.leading.role_state == EvidenceState.SUPPORTED
        and constraint.trailing.role_state == EvidenceState.SUPPORTED
        and (
            constraint.leading.independently_observed
            or constraint.trailing.independently_observed
        )
    )


def _boundary_can_anchor_slot_inference(
    boundary: ResolvedFrameBoundary,
) -> bool:
    return bool(
        boundary.position_independently_observed
        and boundary.role_state == EvidenceState.SUPPORTED
    )


def _sequence_geometry_provenance(
    frame_index: int,
    position: SequenceSlotPosition,
    inputs: tuple[MeasurementProvenance, ...],
) -> MeasurementProvenance:
    unique_inputs = tuple(dict.fromkeys(inputs))
    dependencies = tuple(
        sorted(
            {
                dependency
                for item in unique_inputs
                for dependency in (item.root_measurement, *item.dependencies)
                if dependency != MeasurementIdentity.FRAME_GEOMETRY
            },
            key=lambda item: item.value,
        )
    )
    anchors = tuple(
        dict.fromkeys(
            anchor
            for item in unique_inputs
            for anchor in (item.observation_id, *item.boundary_anchors)
        )
    )
    digest = hashlib.sha256(
        "\x1f".join(
            (
                str(frame_index),
                position.value,
                *(str(item.observation_id) for item in unique_inputs),
            )
        ).encode("utf-8")
    ).hexdigest()
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        observation_id=ObservationId(f"sequence_inferred_slot:{digest}"),
        dependencies=dependencies,
        description="frame slot geometry inferred from the unique full sequence",
        boundary_anchors=anchors,
    )


def _resolved_sequence_boundary(
    position: PixelInterval,
    provenance: MeasurementProvenance,
) -> ResolvedFrameBoundary:
    return ResolvedFrameBoundary(
        position=position,
        source=FrameBoundarySource.SEQUENCE_INFERENCE,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=None,
        inference_provenance=provenance,
    )


def infer_sequence_frame_slot(
    real_slots: tuple[FrameSlot, ...],
    *,
    insertion_index: int,
    common_width: CommonFrameWidthResolution,
    holder_safety: HolderSafetyEnvelope,
) -> FrameSlot | None:
    """Infer one missing slot geometry without assigning content identity."""

    if (
        not real_slots
        or not 1 <= insertion_index <= len(real_slots) + 1
        or any(
            slot.sequence_inferred
            or not slot.leading.geometry_resolved
            or not slot.trailing.geometry_resolved
            for slot in real_slots
        )
        or not _common_width_is_independently_supported(real_slots, common_width)
    ):
        return None

    width = common_width.width_px
    assert width is not None
    holder_axis = PixelInterval(
        float(holder_safety.box.left),
        float(holder_safety.box.right),
    )
    inputs: tuple[MeasurementProvenance | None, ...]

    if insertion_index == 1:
        position = SequenceSlotPosition.LEADING
        right = real_slots[0].leading
        holder_boundary = holder_safety.boundary(BoundarySide.LEADING)
        if holder_boundary is None or not _boundary_can_anchor_slot_inference(right):
            return None
        safe_start = max(holder_axis.minimum, holder_boundary.position.minimum)
        safe_end = right.position.minimum
        inputs = (
            common_width.provenance,
            holder_boundary.provenance,
            right.role_provenance,
        )
        if safe_end - safe_start < width.minimum:
            return None
        supported_width_maximum = min(
            width.maximum,
            safe_end - safe_start,
        )
        leading = PixelInterval(
            safe_end - supported_width_maximum,
            safe_end - width.minimum,
        )
        trailing = PixelInterval.exact(safe_end)
    elif insertion_index == len(real_slots) + 1:
        position = SequenceSlotPosition.TRAILING
        left = real_slots[-1].trailing
        holder_boundary = holder_safety.boundary(BoundarySide.TRAILING)
        if holder_boundary is None or not _boundary_can_anchor_slot_inference(left):
            return None
        safe_start = left.position.maximum
        safe_end = min(holder_axis.maximum, holder_boundary.position.maximum)
        inputs = (
            common_width.provenance,
            left.role_provenance,
            holder_boundary.provenance,
        )
        if safe_end - safe_start < width.minimum:
            return None
        leading = PixelInterval.exact(safe_start)
        trailing = PixelInterval(
            safe_start + width.minimum,
            safe_start
            + min(
                width.maximum,
                safe_end - safe_start,
            ),
        )
    else:
        position = SequenceSlotPosition.INTERIOR
        right_slot_index = insertion_index - 1
        left = real_slots[right_slot_index - 1].trailing
        right = real_slots[right_slot_index].leading
        if not _boundary_can_anchor_slot_inference(
            left
        ) or not _boundary_can_anchor_slot_inference(right):
            return None
        safe_start = left.position.maximum
        safe_end = right.position.minimum
        inputs = (
            common_width.provenance,
            left.role_provenance,
            right.role_provenance,
        )
        if safe_end - safe_start < width.minimum:
            return None
        leading = PixelInterval(
            safe_start,
            safe_end - width.minimum,
        )
        trailing = PixelInterval(
            safe_start + width.minimum,
            safe_end,
        )

    if any(item is None for item in inputs):
        return None
    typed_inputs = tuple(item for item in inputs if item is not None)
    safe_output = PixelInterval(safe_start, safe_end)
    if (
        safe_output.maximum <= safe_output.minimum
        or leading.maximum >= trailing.minimum
    ):
        return None

    provenance = _sequence_geometry_provenance(
        insertion_index,
        position,
        typed_inputs,
    )
    nominal_interval = PixelInterval(leading.minimum, trailing.maximum)
    inference = SequenceInferredSlotGeometry(
        frame_index=insertion_index,
        position=position,
        nominal_interval=nominal_interval,
        safe_output_interval=safe_output,
        common_width_px=width,
        inference_inputs=typed_inputs,
        geometry_state=BoundaryGeometryState.RESOLVED,
        measurement_state=EvidenceState.UNAVAILABLE,
        provenance=provenance,
    )
    return FrameSlot(
        index=insertion_index,
        visible_long_axis=nominal_interval,
        leading=_resolved_sequence_boundary(leading, provenance),
        trailing=_resolved_sequence_boundary(trailing, provenance),
        content_occupancy=FrameContentOccupancy.UNAVAILABLE,
        edge_occlusion=None,
        sequence_inference=inference,
    )
