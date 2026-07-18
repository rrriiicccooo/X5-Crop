from __future__ import annotations

from dataclasses import dataclass

from ...domain import (
    InterFrameSpacing,
    InterFrameSpacingBasis,
    InterFrameSpacingKind,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
    PixelInterval,
)
from ...image.content import ContentRegionObservation
from . import frame_sequence_candidates as sequence_candidates
from . import frame_sequence_common_width as width_resolution
from . import frame_sequence_measurements as measurement_facts
from .model import (
    BoundaryAssignmentConsensus,
    CommonFrameWidthResolution,
    ContentExtentConstraint,
    FrameBoundarySource,
    FrameEdgeAssignment,
    FrameSlot,
    FrameWidthSearchHint,
    HolderSpanScaleHint,
    IndexedAnchorDistanceConstraint,
    PhotoHeightEvidence,
    ResolvedFrameBoundary,
    SeparatorBandAssignment,
    SequenceResiduals,
    SharedShortAxisSafetySpan,
    boundary_role_is_independent_physical_measurement,
)


@dataclass(frozen=True)
class FrameSequenceSolveResult:
    shared_short_axis: SharedShortAxisSafetySpan
    photo_height_evidence: PhotoHeightEvidence
    frame_width_search_hint: FrameWidthSearchHint
    holder_span_scale_hint: HolderSpanScaleHint
    content_extent_constraint: ContentExtentConstraint
    indexed_anchor_distance_constraints: tuple[IndexedAnchorDistanceConstraint, ...]
    frame_slots: tuple[FrameSlot, ...]
    long_axis_assignments: tuple[FrameEdgeAssignment, ...]
    separator_assignments: tuple[SeparatorBandAssignment, ...]
    inter_frame_spacings: tuple[InterFrameSpacing, ...]
    common_frame_width: CommonFrameWidthResolution
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    search_outcome: PhysicalSearchOutcome
    assignment_evaluations: int

    def __post_init__(self) -> None:
        if self.assignment_evaluations < 0:
            raise ValueError("assignment evaluation count cannot be negative")
        if PhysicalSearchFact.SOLUTION_FOUND not in self.search_outcome.facts:
            raise ValueError("frame sequence result requires a found solution")
        if not self.frame_slots:
            raise ValueError("frame sequence result requires frame slots")
        if not sequence_candidates.frame_slots_are_strictly_monotonic(self.frame_slots):
            raise ValueError("frame sequence result requires monotonic slots")


@dataclass(frozen=True)
class FrameSequenceSolveFailure:
    search_outcome: PhysicalSearchOutcome
    assignment_evaluations: int

    def __post_init__(self) -> None:
        if self.assignment_evaluations < 0:
            raise ValueError("assignment evaluation count cannot be negative")
        if PhysicalSearchFact.SOLUTION_FOUND in self.search_outcome.facts:
            raise ValueError("frame sequence failure cannot contain a solution")


def content_extent_constraint(
    visible_content: ContentRegionObservation,
) -> ContentExtentConstraint:
    return ContentExtentConstraint(
        long_axis_extent_px=PixelInterval(
            float(visible_content.region.left),
            float(visible_content.region.right),
        ),
        reliable_runs_px=tuple(
            PixelInterval(float(start), float(end))
            for start, end in visible_content.reliable_runs
        ),
        position_uncertainty_px=visible_content.position_uncertainty_px,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.CONTENT_EVIDENCE_IMAGE,
            observation_id=ObservationId("content_extent_constraint"),
            dependencies=(MeasurementIdentity.GRAY_WORK,),
            description="count-independent visible-content extent constraint",
        ),
    )


def indexed_anchor_distance_constraints(
    assignments: tuple[SeparatorBandAssignment, ...],
    spacings: tuple[InterFrameSpacing, ...],
    frame_width: PixelInterval,
) -> tuple[IndexedAnchorDistanceConstraint, ...]:
    by_boundary = {
        spacing.boundary.boundary_index: spacing for spacing in spacings
    }
    ordered = tuple(
        sorted(assignments, key=lambda item: item.boundary_index)
    )
    constraints: list[IndexedAnchorDistanceConstraint] = []
    for first, second in zip(ordered, ordered[1:]):
        if second.boundary_index <= first.boundary_index:
            raise ValueError("indexed separator assignments must be unique")
        intermediate_spacing = PixelInterval.exact(0.0)
        spacing_complete = True
        for boundary_index in range(
            first.boundary_index + 1,
            second.boundary_index,
        ):
            spacing = by_boundary.get(boundary_index)
            if spacing is None:
                spacing_complete = False
                break
            intermediate_spacing = intermediate_spacing.plus(
                spacing.signed_width_px
            )
        if not spacing_complete:
            continue
        anchor_span = second.preceding_trailing_edge.position.minus(
            first.following_leading_edge.position
        )
        frame_index_distance = second.boundary_index - first.boundary_index
        implied_frame_width = anchor_span.minus(
            intermediate_spacing
        ).scaled(1.0 / float(frame_index_distance))
        if (
            implied_frame_width.minimum <= 0.0
            or not measurement_facts.measurement_intervals_are_compatible(
                implied_frame_width,
                frame_width,
            )
            or first.observation.provenance.observation_id
            == second.observation.provenance.observation_id
        ):
            continue
        constraints.append(
            IndexedAnchorDistanceConstraint(
                first_boundary_index=first.boundary_index,
                second_boundary_index=second.boundary_index,
                anchor_span_px=anchor_span,
                intermediate_spacing_px=intermediate_spacing,
                implied_frame_width_px=implied_frame_width,
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
                    observation_id=ObservationId(
                        "indexed_anchor_distance:"
                        f"{first.boundary_index}:{second.boundary_index}:"
                        f"{first.observation.provenance.observation_id}:"
                        f"{second.observation.provenance.observation_id}"
                    ),
                    dependencies=(
                        MeasurementIdentity.SEPARATOR_PROFILE,
                        MeasurementIdentity.FRAME_DIMENSIONS,
                    ),
                    description=(
                        "candidate-indexed separator anchors with retained "
                        "intermediate spacing"
                    ),
                    boundary_anchors=(
                        first.observation.provenance.observation_id,
                        second.observation.provenance.observation_id,
                    ),
                ),
            )
        )
    return tuple(constraints)


def final_inter_frame_spacings(
    slots: tuple[FrameSlot, ...],
    assignments: tuple[SeparatorBandAssignment, ...],
    common_width: CommonFrameWidthResolution,
) -> tuple[InterFrameSpacing, ...]:
    assigned_boundaries = {item.boundary_index for item in assignments}
    return tuple(
        _corroborate_overlap_from_independent_sequence_constraints(
            sequence_candidates.spacing_from_frame_edges(
                boundary_index,
                left.trailing,
                right.leading,
                separator_observation_supported=(
                    boundary_index in assigned_boundaries
                ),
            ),
            left,
            right,
            common_width,
        )
        for boundary_index, (left, right) in enumerate(
            zip(slots, slots[1:]),
            start=1,
        )
    )


def _inferred_overlap_geometry(
    left: FrameSlot,
    right: FrameSlot,
    frame_width: PixelInterval,
) -> tuple[
    ResolvedFrameBoundary,
    ResolvedFrameBoundary,
    PixelInterval,
] | None:
    if (
        left.trailing.source == FrameBoundarySource.DIMENSION_CONSTRAINED
        and boundary_role_is_independent_physical_measurement(left.leading)
        and boundary_role_is_independent_physical_measurement(right.leading)
    ):
        expected = left.leading.position.plus(frame_width)
        if (
            expected.minimum <= left.trailing.position.minimum
            and left.trailing.position.maximum <= expected.maximum
        ):
            return (
                left.leading,
                right.leading,
                right.leading.position.minus(expected),
            )
    if (
        right.leading.source == FrameBoundarySource.DIMENSION_CONSTRAINED
        and boundary_role_is_independent_physical_measurement(right.trailing)
        and boundary_role_is_independent_physical_measurement(left.trailing)
    ):
        expected = right.trailing.position.minus(frame_width)
        if (
            expected.minimum <= right.leading.position.minimum
            and right.leading.position.maximum <= expected.maximum
        ):
            return (
                right.trailing,
                left.trailing,
                expected.minus(left.trailing.position),
            )
    return None


def _corroborate_overlap_from_independent_sequence_constraints(
    spacing: InterFrameSpacing,
    left: FrameSlot,
    right: FrameSlot,
    common_width: CommonFrameWidthResolution,
) -> InterFrameSpacing:
    if (
        spacing.basis != InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
        or spacing.kind != InterFrameSpacingKind.OVERLAP
    ):
        return spacing
    independent_width = width_resolution.target_independent_common_width(
        common_width,
        left.index,
        right.index,
    )
    if independent_width is None:
        return spacing
    width_px, contributors = independent_width
    geometry = _inferred_overlap_geometry(left, right, width_px)
    if geometry is None:
        return spacing
    positional_anchor, measured_overlap_edge, forced_spacing = geometry
    if forced_spacing.maximum >= 0.0:
        return spacing
    inputs = tuple(
        boundary
        for constraint in contributors
        for boundary in (constraint.leading, constraint.trailing)
    )
    dependencies = tuple(
        sorted(
            {
                dependency
                for boundary in (
                    positional_anchor,
                    measured_overlap_edge,
                    *inputs,
                )
                for provenance in (
                    boundary.measurement_provenance,
                    boundary.role_provenance,
                )
                if provenance is not None
                for dependency in (
                    provenance.root_measurement,
                    *provenance.dependencies,
                )
                if dependency
                not in {
                    MeasurementIdentity.FRAME_DIMENSIONS,
                    MeasurementIdentity.FRAME_GEOMETRY,
                    MeasurementIdentity.FRAME_WIDTH_PATTERN,
                }
            },
            key=lambda item: item.value,
        )
    )
    boundary_anchors = tuple(
        dict.fromkeys(
            boundary.measurement_provenance.observation_id
            for boundary in (
                positional_anchor,
                measured_overlap_edge,
                *inputs,
            )
        )
    )
    return InterFrameSpacing(
        boundary=spacing.boundary,
        signed_width_px=spacing.signed_width_px,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
            observation_id=ObservationId(
                "sequence_corroborated_overlap:"
                f"{spacing.boundary.boundary_index}:"
                + ":".join(str(item.frame_index) for item in contributors)
            ),
            dependencies=dependencies,
            description=(
                "target-independent frame-width measurements require overlap"
            ),
            boundary_anchors=boundary_anchors,
        ),
        basis=InterFrameSpacingBasis.CORROBORATED_OVERLAP,
    )
