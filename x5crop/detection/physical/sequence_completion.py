from __future__ import annotations

from dataclasses import replace
import hashlib

from ...domain import (
    Box,
    BoundarySide,
    EvidenceState,
    FrameDimensionPrior,
    FrameSequenceSearchScope,
    HolderSafetyEnvelope,
    HolderBoundaryObservation,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    InterFrameSpacingKind,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from ...image.content import ContentRegionObservation
from ...strip_modes import FULL
from . import frame_sequence_candidate_resolution as candidate_resolution
from . import frame_sequence_candidates as sequence_candidates
from . import frame_sequence_common_width as width_resolution
from . import frame_sequence_measurements as measurement_facts
from .model import (
    SequenceSlotPosition,
    SequenceInferredSlotGeometry,
    BoundaryGeometryState,
    CommonFrameWidthResolution,
    FrameEdgeAssignment,
    FrameEdgeOcclusionInference,
    FrameContentOccupancy,
    FrameSlot,
    FrameBoundarySource,
    ResolvedFrameBoundary,
    PhotoHeightEvidence,
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


def _occlusion_provenance(
    side: BoundarySide,
    holder_boundary: HolderBoundaryObservation,
    common_width: CommonFrameWidthResolution,
) -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        observation_id=ObservationId(f"holder_occlusion_inference:{side.value}"),
        dependencies=(
            MeasurementIdentity.BOUNDARY_PATHS,
            MeasurementIdentity.FRAME_DIMENSIONS,
        ),
        description="frame endpoint inferred from holder contact and common frame width",
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    holder_boundary.provenance.observation_id,
                    *common_width.provenance.boundary_anchors,
                )
            )
        ),
    )


def apply_edge_occlusion_inference(
    slots: tuple[FrameSlot, ...],
    assignments: tuple[FrameEdgeAssignment, ...],
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    common_width: CommonFrameWidthResolution,
    strip_mode: str,
) -> tuple[tuple[FrameSlot, ...], tuple[FrameEdgeAssignment, ...]]:
    if strip_mode != FULL or common_width.state != EvidenceState.SUPPORTED:
        return slots, assignments
    assert common_width.width_px is not None
    updated = list(slots)
    removed: set[tuple[int, BoundarySide]] = set()
    for index, side in ((0, BoundarySide.LEADING), (len(slots) - 1, BoundarySide.TRAILING)):
        slot = updated[index]
        if slot.sequence_inferred:
            continue
        visible_boundary = slot.leading if side == BoundarySide.LEADING else slot.trailing
        opposite_boundary = (
            slot.trailing if side == BoundarySide.LEADING else slot.leading
        )
        holder_boundary = holder_boundaries.get(side)
        if not measurement_facts.boundary_matches_holder(visible_boundary, holder_boundary):
            continue
        if not opposite_boundary.independently_observed:
            continue
        if slot.width_px.maximum >= common_width.width_px.minimum:
            continue
        assert holder_boundary is not None
        inferred = (
            slot.trailing.position.minus(common_width.width_px)
            if side == BoundarySide.LEADING
            else slot.leading.position.plus(common_width.width_px)
        )
        if side == BoundarySide.LEADING:
            if inferred.maximum >= visible_boundary.position.minimum:
                continue
            hidden_width = visible_boundary.position.minus(inferred)
        else:
            if inferred.minimum <= visible_boundary.position.maximum:
                continue
            hidden_width = inferred.minus(visible_boundary.position)
        provenance = _occlusion_provenance(side, holder_boundary, common_width)
        inferred_boundary = ResolvedFrameBoundary(
            position=inferred,
            source=FrameBoundarySource.HOLDER_OCCLUSION_INFERENCE,
            geometry_state=BoundaryGeometryState.RESOLVED,
            boundary_anchor=None,
            inference_provenance=provenance,
        )
        updated[index] = replace(
            slot,
            leading=(inferred_boundary if side == BoundarySide.LEADING else slot.leading),
            trailing=(inferred_boundary if side == BoundarySide.TRAILING else slot.trailing),
            edge_occlusion=FrameEdgeOcclusionInference(
                side=side,
                hidden_width_px=hidden_width,
                holder_boundary_provenance=holder_boundary.provenance,
            ),
        )
        removed.add((slot.index, side))
    return (
        tuple(updated),
        tuple(
            assignment
            for assignment in assignments
            if (assignment.frame_index, assignment.side) not in removed
        ),
    )


def _slot_has_observed_content(
    slot: FrameSlot,
    visible_content: ContentRegionObservation,
) -> bool:
    return visible_content.reliable_content_intersects(slot.visible_long_axis)


def annotate_frame_content_occupancy(
    slots: tuple[FrameSlot, ...],
    visible_content: ContentRegionObservation,
) -> tuple[FrameSlot, ...]:
    return tuple(
        replace(
            slot,
            content_occupancy=(
                FrameContentOccupancy.CONTENT_OBSERVED
                if _slot_has_observed_content(slot, visible_content)
                else FrameContentOccupancy.UNAVAILABLE
            ),
        )
        for slot in slots
    )


def _shifted_frame_index(frame_index: int, insertion_index: int) -> int:
    return frame_index + 1 if frame_index >= insertion_index else frame_index


def _shifted_separator_boundary_index(
    boundary_index: int,
    insertion_index: int,
) -> int | None:
    broken_boundary = insertion_index - 1
    if 1 < insertion_index and boundary_index == broken_boundary:
        return None
    return boundary_index + 1 if boundary_index >= insertion_index else boundary_index


def _build_with_inserted_slot(
    build: sequence_candidates.SequenceBuild,
    inserted_slot: FrameSlot,
    holder: Box,
) -> sequence_candidates.SequenceBuild:
    insertion_index = inserted_slot.index
    inserted_slot_count = 1
    slots = tuple(
        (
            inserted_slot
            if frame_index == insertion_index
            else replace(
                build.slots[
                    frame_index
                    - 1
                    - (
                        inserted_slot_count
                        if frame_index > insertion_index
                        else 0
                    )
                ],
                index=frame_index,
            )
        )
        for frame_index in range(
            1,
            len(build.slots) + inserted_slot_count + 1,
        )
    )
    long_axis_assignments = tuple(
        replace(
            assignment,
            frame_index=_shifted_frame_index(
                assignment.frame_index,
                insertion_index,
            ),
        )
        for assignment in build.long_axis_assignments
    )
    separator_bindings = tuple(
        replace(assignment, boundary_index=shifted)
        for assignment in build.separator_bindings
        if (
            shifted := _shifted_separator_boundary_index(
                assignment.boundary_index,
                insertion_index,
            )
        )
        is not None
    )
    spacings = tuple(
        sequence_candidates.spacing_from_frame_edges(
            boundary_index,
            left.trailing,
            right.leading,
        )
        for boundary_index, (left, right) in enumerate(
            zip(slots, slots[1:]),
            start=1,
        )
    )
    added_uncertainty = (
        inserted_slot.leading.position.maximum
        - inserted_slot.leading.position.minimum
        + inserted_slot.trailing.position.maximum
        - inserted_slot.trailing.position.minimum
    ) / max(
        measurement_facts.MINIMUM_POSITIVE_PIXEL_EXTENT,
        float(holder.width + holder.height),
    )
    residuals = replace(
        build.residuals,
        boundary_uncertainty=(
            build.residuals.boundary_uncertainty + added_uncertainty
        ),
    )
    return sequence_candidates.SequenceBuild(
        slots=slots,
        long_axis_assignments=long_axis_assignments,
        separator_bindings=separator_bindings,
        spacings=spacings,
        frame_width_px=build.frame_width_px,
        short_axis=build.short_axis,
        residuals=residuals,
        objectives=replace(
            build.objectives,
            uncorroborated_overlap_extent_px=sequence_candidates.uncorroborated_overlap_extent(
                spacings
            ),
            unexplained_spacing_extent_px=sequence_candidates.unexplained_spacing_extent(spacings),
            supported_separator_count=len(separator_bindings),
            boundary_uncertainty_ratio=(
                build.objectives.boundary_uncertainty_ratio + added_uncertainty
            ),
        ),
    )


def sequence_completed_builds(
    real_frame_builds: tuple[sequence_candidates.SequenceBuild, ...],
    search_scope: FrameSequenceSearchScope,
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> tuple[sequence_candidates.SequenceBuild, ...]:
    inferred: list[sequence_candidates.SequenceBuild] = []
    holder_boundaries = candidate_resolution.holder_boundaries(search_scope)
    for build in real_frame_builds:
        build, common_width = candidate_resolution.resolve_build_physical_boundaries(
            build,
            holder_boundaries,
            photo_height_evidence,
            dimensions,
        )
        if common_width.state != EvidenceState.SUPPORTED:
            continue
        if not measured_sequence_supports_slot_inference(
            build.slots,
            build.spacings,
            common_width,
        ):
            continue
        sequence_inferred_slot_count = 1
        for insertion_index in range(
            1,
            len(build.slots) + sequence_inferred_slot_count + 1,
        ):
            inferred_slot = infer_sequence_frame_slot(
                build.slots,
                insertion_index=insertion_index,
                common_width=common_width,
                holder_safety=search_scope.holder_safety,
            )
            if inferred_slot is not None:
                inferred.append(
                    _build_with_inserted_slot(
                        build,
                        inferred_slot,
                        search_scope.holder_safety.box,
                    )
                )
    return tuple(inferred)


def build_supports_resolved_nominal_slots(
    build: sequence_candidates.SequenceBuild,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> bool:
    resolved_build, common_width = candidate_resolution.resolve_build_physical_boundaries(
        build,
        holder_boundaries,
        photo_height_evidence,
        dimensions,
    )
    resolved_slots = resolved_build.slots
    return bool(
        sequence_candidates.frame_slots_are_strictly_monotonic(resolved_slots)
        and resolved_build.objectives.uncorroborated_overlap_extent_px == 0.0
        and all(
            slot.leading.geometry_state == BoundaryGeometryState.RESOLVED
            and slot.trailing.geometry_state == BoundaryGeometryState.RESOLVED
            for slot in resolved_slots
        )
        and width_resolution.slots_do_not_contradict_supported_common_width(
            resolved_slots,
            holder_boundaries,
            common_width,
        )
        and _full_sequence_endpoint_slack_is_sub_frame(
            resolved_slots,
            holder_boundaries,
            common_width,
        )
    )


def _full_sequence_endpoint_slack_is_sub_frame(
    slots: tuple[FrameSlot, ...],
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    common_width: CommonFrameWidthResolution,
) -> bool:
    if common_width.state != EvidenceState.SUPPORTED or common_width.width_px is None:
        return False
    return _endpoint_slack_is_sub_frame(
        slots,
        holder_boundaries,
        common_width.width_px,
    )


def _endpoint_slack_is_sub_frame(
    slots: tuple[FrameSlot, ...],
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    frame_width: PixelInterval,
) -> bool:
    leading_holder = holder_boundaries.get(BoundarySide.LEADING)
    if leading_holder is not None:
        leading_slack = slots[0].leading.position.minus(leading_holder.position)
        if leading_slack.minimum >= frame_width.minimum:
            return False
    trailing_holder = holder_boundaries.get(BoundarySide.TRAILING)
    if trailing_holder is not None:
        trailing_slack = trailing_holder.position.minus(slots[-1].trailing.position)
        if trailing_slack.minimum >= frame_width.minimum:
            return False
    return True


def build_satisfies_full_endpoint_extent(
    build: sequence_candidates.SequenceBuild,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> bool:
    resolved_build, common_width = candidate_resolution.resolve_build_physical_boundaries(
        build,
        holder_boundaries,
        photo_height_evidence,
        dimensions,
    )
    frame_width = (
        common_width.width_px
        if common_width.state == EvidenceState.SUPPORTED
        and common_width.width_px is not None
        else PixelInterval.exact(
            max(slot.width_px.maximum for slot in build.slots)
        )
    )
    return _endpoint_slack_is_sub_frame(
        resolved_build.slots,
        holder_boundaries,
        frame_width,
    )


def build_does_not_contradict_common_width(
    build: sequence_candidates.SequenceBuild,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> bool:
    resolved_build, common_width = candidate_resolution.resolve_build_physical_boundaries(
        build,
        holder_boundaries,
        photo_height_evidence,
        dimensions,
    )
    resolved_slots = resolved_build.slots
    return bool(
        sequence_candidates.frame_slots_are_strictly_monotonic(resolved_slots)
        and (
            common_width.state != EvidenceState.SUPPORTED
            or width_resolution.slots_do_not_contradict_supported_common_width(
                resolved_slots,
                holder_boundaries,
                common_width,
            )
        )
    )


def _slot_has_non_holder_boundary_observation(
    slot: FrameSlot,
    slot_index: int,
    last_index: int,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> bool:
    observed_boundary_count = 0
    for side, boundary in (
        (BoundarySide.LEADING, slot.leading),
        (BoundarySide.TRAILING, slot.trailing),
    ):
        if boundary.boundary_anchor is None:
            continue
        external_holder_boundary = (
            slot_index == 0 and side == BoundarySide.LEADING
        ) or (
            slot_index == last_index and side == BoundarySide.TRAILING
        )
        if external_holder_boundary and measurement_facts.boundary_matches_holder(
            boundary,
            holder_boundaries.get(side),
        ):
            continue
        if boundary.independently_observed:
            return True
        observed_boundary_count += 1
    return observed_boundary_count == measurement_facts.INTERVAL_ENDPOINT_COUNT


def _unexcluded_sequence_inference_indexes(
    build: sequence_candidates.SequenceBuild,
    visible_content: ContentRegionObservation,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> tuple[int, ...]:
    last_index = len(build.slots) - 1
    unresolved: list[int] = []
    for slot_index, slot in enumerate(build.slots):
        if (
            not slot.sequence_inferred
            and not _slot_has_non_holder_boundary_observation(
                slot,
                slot_index,
                last_index,
                holder_boundaries,
            )
            and not visible_content.reliable_content_intersects(
                slot.visible_long_axis
            )
        ):
            unresolved.append(slot_index)
    return tuple(unresolved)


def infer_unique_slot_in_direct_nominal_build(
    build: sequence_candidates.SequenceBuild,
    visible_content: ContentRegionObservation,
    search_scope: FrameSequenceSearchScope,
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> sequence_candidates.SequenceBuild:
    holder_boundaries = candidate_resolution.holder_boundaries(search_scope)
    resolved_build, common_width = candidate_resolution.resolve_build_physical_boundaries(
        build,
        holder_boundaries,
        photo_height_evidence,
        dimensions,
    )
    inference_indexes = _unexcluded_sequence_inference_indexes(
        resolved_build,
        visible_content,
        holder_boundaries,
    )
    if len(inference_indexes) != 1:
        return build
    slot_index = inference_indexes[0]
    existing_slot = resolved_build.slots[slot_index]
    real_slots = tuple(
        slot
        for index, slot in enumerate(resolved_build.slots)
        if index != slot_index
    )
    inferred_slot = infer_sequence_frame_slot(
        real_slots,
        insertion_index=existing_slot.index,
        common_width=common_width,
        holder_safety=search_scope.holder_safety,
    )
    if (
        inferred_slot is None
        or not inferred_slot.nominal_long_axis.intersects(
            existing_slot.nominal_long_axis
        )
    ):
        return build
    slots = tuple(
        inferred_slot if index == slot_index else slot
        for index, slot in enumerate(resolved_build.slots)
    )
    return sequence_candidates.rebuild_sequence_build(resolved_build, slots)


def direct_nominal_geometry_is_complete(
    builds: tuple[sequence_candidates.SequenceBuild, ...],
    visible_content: ContentRegionObservation,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> bool:
    if not builds:
        return False
    preserving = tuple(
        build
        for build in builds
        if sequence_candidates.build_preserves_visible_content(build, visible_content)
    )
    preferred = sequence_candidates.physically_preferred_builds(
        preserving or builds
    )
    return any(
        build_supports_resolved_nominal_slots(
            build,
            holder_boundaries,
            photo_height_evidence,
            dimensions,
        )
        and not _unexcluded_sequence_inference_indexes(
            build,
            visible_content,
            holder_boundaries,
        )
        for build in preferred
    )


def preferred_direct_common_width_is_supported(
    builds: tuple[sequence_candidates.SequenceBuild, ...],
    visible_content: ContentRegionObservation,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> bool:
    if not builds:
        return False
    preserving = tuple(
        build
        for build in builds
        if sequence_candidates.build_preserves_visible_content(build, visible_content)
    )
    preferred = sequence_candidates.physically_preferred_builds(preserving or builds)
    return any(
        width_resolution.common_width_has_independent_measurement_basis(
            candidate_resolution.resolve_build_physical_boundaries(
                build,
                holder_boundaries,
                photo_height_evidence,
                dimensions,
            )[1]
        )
        for build in preferred
    )


def build_has_geometry_only_slot(build: sequence_candidates.SequenceBuild) -> bool:
    return any(
        not any(
            boundary.independently_observed
            for boundary in (slot.leading, slot.trailing)
        )
        for slot in build.slots
    )
