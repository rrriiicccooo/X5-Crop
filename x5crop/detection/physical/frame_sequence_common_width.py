from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...domain import (
    BoundarySide,
    EvidenceState,
    FrameDimensionPrior,
    HolderBoundaryObservation,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from . import frame_sequence_measurements as measurements
from .frame_dimensions import MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS
from .model import (
    CommonFrameWidthResolution,
    FrameBoundarySource,
    FrameSlot,
    FrameWidthMeasurementConstraint,
    FrameWidthPhysicalScaleConstraint,
    PhotoHeightEvidence,
    ResolvedFrameBoundary,
    boundary_role_is_independent_physical_measurement,
)


STRICT_MAJORITY_DIVISOR = 2


@dataclass(frozen=True)
class CommonWidthHypothesis:
    width_px: PixelInterval
    boundary_anchors: tuple[ObservationId, ...]
    contributor_count: int

    def __post_init__(self) -> None:
        if self.width_px.minimum < measurements.MINIMUM_POSITIVE_PIXEL_EXTENT:
            raise ValueError("common-width hypothesis must be positive")
        if self.contributor_count < MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
            raise ValueError("common-width hypothesis requires independent slots")
        if not self.boundary_anchors:
            raise ValueError("common-width hypothesis requires measured anchors")


@dataclass(frozen=True)
class RecurringBoundaryWidthHypothesis:
    width_px: PixelInterval
    contributor_count: int

    def __post_init__(self) -> None:
        if self.width_px.minimum < measurements.MINIMUM_POSITIVE_PIXEL_EXTENT:
            raise ValueError("recurring boundary width must be positive")
        if self.contributor_count < MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
            raise ValueError("recurring boundary width requires repeated slots")


@dataclass(frozen=True)
class DimensionPlacementHypothesis:
    width_px: PixelInterval
    boundary_anchors: tuple[ObservationId, ...]
    repeated_slot_count: int = 0

    def __post_init__(self) -> None:
        if self.width_px.minimum < measurements.MINIMUM_POSITIVE_PIXEL_EXTENT:
            raise ValueError("dimension placement hypothesis must be positive")
        if self.repeated_slot_count < 0:
            raise ValueError("repeated slot count cannot be negative")


def width_satisfies_physical_scale(
    width: PixelInterval,
    constraint: FrameWidthPhysicalScaleConstraint | None,
) -> bool:
    return constraint is None or width.intersects(constraint.width_px)


def dimension_placement_hypotheses(
    measured_widths: tuple[CommonWidthHypothesis, ...],
    recurring_widths: tuple[RecurringBoundaryWidthHypothesis, ...],
    search_hints: tuple[PixelInterval, ...],
    physical_scale_constraint: FrameWidthPhysicalScaleConstraint | None,
) -> tuple[DimensionPlacementHypothesis, ...]:
    measured = tuple(
        DimensionPlacementHypothesis(
            hypothesis.width_px,
            hypothesis.boundary_anchors,
            hypothesis.contributor_count,
        )
        for hypothesis in measured_widths
    )
    recurring = tuple(
        DimensionPlacementHypothesis(
            hypothesis.width_px,
            (),
            hypothesis.contributor_count,
        )
        for hypothesis in non_dominated_recurring_width_hypotheses(
            recurring_widths
        )
    )
    hints = tuple(DimensionPlacementHypothesis(width, ()) for width in search_hints)
    by_width: dict[PixelInterval, DimensionPlacementHypothesis] = {}
    for hypothesis in (*measured, *recurring, *hints):
        if not width_satisfies_physical_scale(
            hypothesis.width_px,
            physical_scale_constraint,
        ):
            continue
        existing = by_width.get(hypothesis.width_px)
        if existing is None:
            by_width[hypothesis.width_px] = hypothesis
            continue
        by_width[hypothesis.width_px] = DimensionPlacementHypothesis(
            hypothesis.width_px,
            existing.boundary_anchors or hypothesis.boundary_anchors,
            max(existing.repeated_slot_count, hypothesis.repeated_slot_count),
        )
    return tuple(by_width.values())


def non_dominated_recurring_width_hypotheses(
    hypotheses: tuple[RecurringBoundaryWidthHypothesis, ...],
) -> tuple[RecurringBoundaryWidthHypothesis, ...]:
    ranked = tuple(
        sorted(
            hypotheses,
            key=lambda item: (
                -item.contributor_count,
                item.width_px.maximum - item.width_px.minimum,
                item.width_px.midpoint,
            ),
        )
    )
    selected: list[RecurringBoundaryWidthHypothesis] = []
    for hypothesis in ranked:
        uncertainty = hypothesis.width_px.maximum - hypothesis.width_px.minimum
        if any(
            existing.contributor_count >= hypothesis.contributor_count
            and hypothesis.width_px.minimum <= existing.width_px.minimum
            and existing.width_px.maximum <= hypothesis.width_px.maximum
            and existing.width_px.maximum - existing.width_px.minimum <= uncertainty
            for existing in selected
        ):
            continue
        selected.append(hypothesis)
    return tuple(selected)


def strict_majority_width_consensus(
    intervals: tuple[PixelInterval, ...],
) -> tuple[PixelInterval, int] | None:
    if not intervals:
        return None
    contributor_indexes = measurements.largest_strict_intersection_indexes(
        intervals,
        len(intervals) // STRICT_MAJORITY_DIVISOR + 1,
    )
    if not contributor_indexes:
        return None
    contributors = tuple(intervals[index] for index in contributor_indexes)
    return measurements.interval_envelope(contributors), len(contributors)


def non_dominated_width_hypotheses(
    hypotheses: tuple[CommonWidthHypothesis, ...],
) -> tuple[CommonWidthHypothesis, ...]:
    ranked = tuple(
        sorted(
            hypotheses,
            key=lambda item: (
                -item.contributor_count,
                item.width_px.maximum - item.width_px.minimum,
                item.width_px.midpoint,
                item.boundary_anchors,
            ),
        )
    )
    selected: list[CommonWidthHypothesis] = []
    for hypothesis in ranked:
        uncertainty = hypothesis.width_px.maximum - hypothesis.width_px.minimum
        if any(
            existing.width_px.intersects(hypothesis.width_px)
            and existing.contributor_count >= hypothesis.contributor_count
            and (
                (
                    existing.width_px.minimum <= hypothesis.width_px.minimum
                    and existing.width_px.maximum >= hypothesis.width_px.maximum
                )
                or existing.width_px.maximum - existing.width_px.minimum
                <= uncertainty
            )
            for existing in selected
        ):
            continue
        selected.append(hypothesis)
    return tuple(selected)


def role_supported_frame_constraint(
    constraint: measurements.MeasuredFrameConstraint,
) -> bool:
    return bool(
        all(
            edge.basis
            in {
                FrameBoundarySource.GRAY_PATH_OBSERVATION,
                FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
            }
            for edge in (constraint.leading, constraint.trailing)
        )
        and all(
            edge.state == EvidenceState.SUPPORTED
            for edge in (constraint.leading, constraint.trailing)
        )
    )


def measured_constraint_common_width(
    constraints: tuple[measurements.MeasuredFrameConstraint, ...],
    count: int,
) -> PixelInterval | None:
    if not constraints or count < len(constraints):
        raise ValueError("measured constraint sequence must fit its frame count")
    contributor_indexes = measurements.largest_measurement_compatible_interval_indexes(
        tuple(constraint.width_px for constraint in constraints),
        MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS,
    )
    if not contributor_indexes:
        return None
    shared = measurements.interval_envelope(
        tuple(constraints[index].width_px for index in contributor_indexes)
    )
    contributor_set = set(contributor_indexes)
    for index, constraint in enumerate(constraints):
        if index in contributor_set or all(
            measurements.measurement_intervals_are_compatible(
                constraint.width_px,
                constraints[contributor_index].width_px,
            )
            for contributor_index in contributor_indexes
        ):
            continue
        leading_clip = bool(
            index == 0
            and constraint.leading_holder_clip_supported
            and constraint.width_px.maximum < shared.minimum
        )
        trailing_clip = bool(
            index == count - 1
            and len(constraints) == count
            and constraint.trailing_holder_clip_supported
            and constraint.width_px.maximum < shared.minimum
        )
        if not leading_clip and not trailing_clip:
            return None
    return shared


def recurring_boundary_width_hypotheses(
    edges: tuple[measurements.EdgeConstraint, ...],
) -> tuple[RecurringBoundaryWidthHypothesis, ...]:
    ordered_edges = tuple(
        sorted(
            edges,
            key=lambda edge: (
                edge.position.midpoint,
                edge.position.minimum,
                edge.position.maximum,
                edge.provenance.observation_id,
            ),
        )
    )
    samples: list[
        tuple[
            PixelInterval,
            measurements.EdgeConstraint,
            measurements.EdgeConstraint,
        ]
    ] = []
    for left_index, left in enumerate(ordered_edges):
        for right in ordered_edges[left_index + 1 :]:
            if right.position.minimum <= left.position.maximum:
                continue
            width = right.position.minus(left.position)
            if width.minimum < measurements.MINIMUM_POSITIVE_PIXEL_EXTENT:
                continue
            samples.append((width, left, right))
    samples.sort(
        key=lambda item: (
            item[0].midpoint,
            item[0].maximum - item[0].minimum,
            item[1].position.midpoint,
            item[2].position.midpoint,
        )
    )

    grouped: list[
        tuple[
            PixelInterval,
            list[
                tuple[
                    PixelInterval,
                    measurements.EdgeConstraint,
                    measurements.EdgeConstraint,
                ]
            ],
        ]
    ] = []
    for sample in samples:
        width = sample[0]
        if grouped:
            shared = grouped[-1][0].intersection(width)
            if shared is not None:
                grouped_samples = grouped[-1][1]
                grouped_samples.append(sample)
                grouped[-1] = (shared, grouped_samples)
                continue
        grouped.append((width, [sample]))

    candidates: dict[PixelInterval, RecurringBoundaryWidthHypothesis] = {}
    for _, group in grouped:
        contributors: list[
            tuple[
                PixelInterval,
                measurements.EdgeConstraint,
                measurements.EdgeConstraint,
            ]
        ] = []
        for sample in sorted(
            group,
            key=lambda item: (
                item[2].position.maximum,
                item[1].position.minimum,
                item[1].provenance.observation_id,
                item[2].provenance.observation_id,
            ),
        ):
            if (
                contributors
                and sample[1].position.minimum
                < contributors[-1][2].position.maximum
            ):
                continue
            contributors.append(sample)
        if len(contributors) < MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
            continue
        shared = PixelInterval.common_intersection(
            tuple(sample[0] for sample in contributors)
        )
        if shared is None:
            continue
        hypothesis = RecurringBoundaryWidthHypothesis(shared, len(contributors))
        existing = candidates.get(shared)
        if existing is None or hypothesis.contributor_count > existing.contributor_count:
            candidates[shared] = hypothesis
    return tuple(
        sorted(
            candidates.values(),
            key=lambda hypothesis: (
                -hypothesis.contributor_count,
                hypothesis.width_px.maximum - hypothesis.width_px.minimum,
                hypothesis.width_px.midpoint,
            ),
        )
    )


def width_compatibility_matrix(
    constraints: tuple[measurements.MeasuredFrameConstraint, ...],
    coordinates: tuple[float, ...],
) -> np.ndarray:
    if not constraints or not coordinates:
        return np.zeros((len(coordinates), len(constraints)), dtype=bool)
    minima = np.fromiter(
        (constraint.width_px.minimum for constraint in constraints),
        dtype=np.float64,
        count=len(constraints),
    )
    maxima = np.fromiter(
        (constraint.width_px.maximum for constraint in constraints),
        dtype=np.float64,
        count=len(constraints),
    )
    candidate_coordinates = np.asarray(coordinates, dtype=np.float64)
    return (
        (candidate_coordinates[:, np.newaxis] >= minima[np.newaxis, :])
        & (candidate_coordinates[:, np.newaxis] <= maxima[np.newaxis, :])
    )


def repeated_width_contributor_sets(
    constraints: tuple[measurements.MeasuredFrameConstraint, ...],
    minimum_contributors: int,
) -> tuple[
    tuple[PixelInterval, tuple[measurements.MeasuredFrameConstraint, ...]], ...
]:
    if minimum_contributors < MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
        raise ValueError("repeated width search requires multiple contributors")
    coordinates = tuple(
        dict.fromkeys(
            coordinate
            for constraint in constraints
            for coordinate in (
                constraint.width_px.minimum,
                constraint.width_px.midpoint,
                constraint.width_px.maximum,
            )
        )
    )
    ordered_constraints = tuple(
        sorted(
            constraints,
            key=lambda item: (
                item.trailing.position.maximum,
                item.leading.position.minimum,
                item.leading.provenance.observation_id,
                item.trailing.provenance.observation_id,
            ),
        )
    )
    compatibility_matrix = width_compatibility_matrix(
        ordered_constraints,
        coordinates,
    )
    candidates: dict[
        tuple[float, float],
        tuple[PixelInterval, tuple[measurements.MeasuredFrameConstraint, ...]],
    ] = {}
    for coordinate, compatibility in zip(
        coordinates,
        compatibility_matrix,
        strict=True,
    ):
        contributors: list[measurements.MeasuredFrameConstraint] = []
        for index in np.flatnonzero(compatibility):
            constraint = ordered_constraints[int(index)]
            if contributors and (
                constraint.leading.position.minimum
                < contributors[-1].trailing.position.maximum
            ):
                continue
            contributors.append(constraint)
        if len(contributors) < minimum_contributors:
            continue
        shared = PixelInterval.common_intersection(
            tuple(constraint.width_px for constraint in contributors)
        )
        if shared is None:
            continue
        key = (shared.minimum, shared.maximum)
        existing = candidates.get(key)
        if existing is None or len(contributors) > len(existing[1]):
            candidates[key] = (shared, tuple(contributors))
    return tuple(
        sorted(
            candidates.values(),
            key=lambda item: (
                -len(item[1]),
                item[0].maximum - item[0].minimum,
                item[0].midpoint,
                tuple(
                    boundary.provenance.observation_id
                    for constraint in item[1]
                    for boundary in (constraint.leading, constraint.trailing)
                ),
            ),
        )
    )


def measured_width_hypotheses(
    constraints: tuple[measurements.MeasuredFrameConstraint, ...],
) -> tuple[CommonWidthHypothesis, ...]:
    measured = tuple(
        constraint
        for constraint in constraints
        if role_supported_frame_constraint(constraint)
    )
    return tuple(
        CommonWidthHypothesis(
            width_px=width,
            boundary_anchors=tuple(
                dict.fromkeys(
                    boundary.provenance.observation_id
                    for constraint in contributors
                    for boundary in (constraint.leading, constraint.trailing)
                )
            ),
            contributor_count=len(contributors),
        )
        for width, contributors in repeated_width_contributor_sets(
            measured,
            MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS,
        )
    )


def frame_width_physical_scale_constraint(
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> FrameWidthPhysicalScaleConstraint | None:
    if (
        photo_height_evidence.state != EvidenceState.SUPPORTED
        or photo_height_evidence.height_px is None
    ):
        return None
    photo_inputs = {
        photo_height_evidence.provenance.root_measurement,
        *photo_height_evidence.provenance.dependencies,
    }
    if (
        MeasurementIdentity.FRAME_GEOMETRY in photo_inputs
        or not {
            MeasurementIdentity.PHOTO_EDGES,
            MeasurementIdentity.BOUNDARY_PATHS,
        }.intersection(photo_inputs)
    ):
        return None
    dependencies = tuple(
        sorted(
            {
                *photo_inputs,
                dimensions.provenance.root_measurement,
                *dimensions.provenance.dependencies,
            }
            - {
                MeasurementIdentity.FRAME_DIMENSIONS,
                MeasurementIdentity.FRAME_GEOMETRY,
            },
            key=lambda item: item.value,
        )
    )
    return FrameWidthPhysicalScaleConstraint(
        width_px=photo_height_evidence.height_px.scaled(dimensions.aspect),
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
            observation_id=ObservationId(
                "frame_width_physical_scale:"
                f"{photo_height_evidence.provenance.observation_id}:"
                f"{dimensions.provenance.observation_id}"
            ),
            dependencies=dependencies,
            description="independent photo-height and physical-aspect width constraint",
            boundary_anchors=photo_height_evidence.provenance.boundary_anchors,
        ),
    )


def constraint_has_scale_independent_internal_anchor(
    constraint: FrameWidthMeasurementConstraint,
    slot_count: int,
) -> bool:
    return bool(
        (
            constraint.frame_index > 1
            and boundary_role_is_independent_physical_measurement(
                constraint.leading
            )
        )
        or (
            constraint.frame_index < slot_count
            and boundary_role_is_independent_physical_measurement(
                constraint.trailing
            )
        )
    )


def boundary_role_can_contribute_to_width_geometry(
    boundary: ResolvedFrameBoundary,
) -> bool:
    provenance = boundary.role_provenance
    return bool(
        boundary.independently_observed
        and provenance is not None
        and provenance.root_measurement != MeasurementIdentity.FRAME_DIMENSIONS
        and MeasurementIdentity.FRAME_DIMENSIONS not in provenance.dependencies
    )


def resolve_common_frame_width(
    slots: tuple[FrameSlot, ...],
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> CommonFrameWidthResolution:
    all_measured_constraints = tuple(
        FrameWidthMeasurementConstraint(slot.index, slot.leading, slot.trailing)
        for slot in slots
        if not slot.sequence_inferred
        and slot.leading.position_independently_observed
        and slot.trailing.position_independently_observed
        and slot.leading.role_state == EvidenceState.SUPPORTED
        and slot.trailing.role_state == EvidenceState.SUPPORTED
        and not (
            slot.index == 1
            and slot.leading.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
            and measurements.boundary_matches_holder(
                slot.leading,
                holder_boundaries.get(BoundarySide.LEADING),
            )
        )
        and not (
            slot.index == len(slots)
            and slot.trailing.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
            and measurements.boundary_matches_holder(
                slot.trailing,
                holder_boundaries.get(BoundarySide.TRAILING),
            )
        )
        and all(
            boundary.role_provenance is not None
            for boundary in (slot.leading, slot.trailing)
        )
    )
    geometry_constraints = tuple(
        constraint
        for constraint in all_measured_constraints
        if all(
            boundary_role_can_contribute_to_width_geometry(boundary)
            for boundary in (constraint.leading, constraint.trailing)
        )
    )
    contributor_indexes = measurements.largest_measurement_compatible_interval_indexes(
        tuple(constraint.width_px for constraint in geometry_constraints),
        MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS,
    )
    measured_constraints = tuple(
        geometry_constraints[index] for index in contributor_indexes
    )
    if not measured_constraints and len(geometry_constraints) == 1:
        measured_constraints = geometry_constraints
    scale_constraint = frame_width_physical_scale_constraint(
        photo_height_evidence,
        dimensions,
    )
    shared: PixelInterval | None = None
    contributors: tuple[FrameWidthMeasurementConstraint, ...] = ()
    used_scale: FrameWidthPhysicalScaleConstraint | None = None
    if len(measured_constraints) >= MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
        shared = measurements.interval_envelope(
            tuple(constraint.width_px for constraint in measured_constraints)
        )
        contributors = measured_constraints
    elif (
        len(measured_constraints) == 1
        and scale_constraint is not None
        and constraint_has_scale_independent_internal_anchor(
            measured_constraints[0],
            len(slots),
        )
    ):
        shared = PixelInterval.common_intersection(
            (
                measured_constraints[0].width_px,
                scale_constraint.width_px,
            )
        )
        if shared is not None:
            contributors = measured_constraints
            used_scale = scale_constraint
    elif scale_constraint is not None:
        scale_corroborated_constraints = tuple(
            constraint
            for constraint in all_measured_constraints
            if constraint.width_px.intersects(scale_constraint.width_px)
            and constraint_has_scale_independent_internal_anchor(
                constraint,
                len(slots),
            )
        )
        scale_corroborated_width = PixelInterval.common_intersection(
            (
                *(
                    constraint.width_px
                    for constraint in scale_corroborated_constraints
                ),
                scale_constraint.width_px,
            )
        )
        if scale_corroborated_width is not None and scale_corroborated_constraints:
            shared = scale_corroborated_width
            contributors = scale_corroborated_constraints
            used_scale = scale_constraint
    anchors = tuple(
        boundary.measurement_provenance.observation_id
        for constraint in contributors
        for boundary in (constraint.leading, constraint.trailing)
    )
    role_inputs = tuple(
        boundary.role_provenance
        for constraint in contributors
        for boundary in (constraint.leading, constraint.trailing)
        if boundary.role_provenance is not None
    )
    provenance_dependencies = {
        dependency
        for constraint in contributors
        for boundary in (constraint.leading, constraint.trailing)
        for input_provenance in (
            boundary.measurement_provenance,
            boundary.role_provenance,
        )
        if input_provenance is not None
        for dependency in (
            input_provenance.root_measurement,
            *input_provenance.dependencies,
        )
        if dependency
        not in {
            MeasurementIdentity.FRAME_DIMENSIONS,
            MeasurementIdentity.FRAME_GEOMETRY,
        }
    }
    if used_scale is not None:
        provenance_dependencies.update(
            dependency
            for dependency in (
                used_scale.provenance.root_measurement,
                *used_scale.provenance.dependencies,
            )
            if dependency
            not in {
                MeasurementIdentity.FRAME_DIMENSIONS,
                MeasurementIdentity.FRAME_GEOMETRY,
            }
        )
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
        observation_id=ObservationId(
            "common_frame_width:"
            + ":".join(
                map(str, (item.frame_index for item in contributors) or (0,))
            )
        ),
        dependencies=tuple(
            sorted(provenance_dependencies, key=lambda item: item.value)
        ),
        description=(
            "common frame width from independently observed complete slots"
            if used_scale is None
            else "common frame width from one observed slot and independent scale"
        ),
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    *anchors,
                    *(
                        anchor
                        for role_provenance in role_inputs
                        for anchor in role_provenance.boundary_anchors
                    ),
                    *(
                        ()
                        if used_scale is None
                        else used_scale.provenance.boundary_anchors
                    ),
                )
            )
        ),
    )
    return CommonFrameWidthResolution(
        width_px=shared,
        constraints=contributors,
        physical_scale_constraint=used_scale,
        state=(
            EvidenceState.SUPPORTED
            if shared is not None
            else EvidenceState.UNAVAILABLE
        ),
        provenance=provenance,
    )


def target_independent_common_width(
    common_width: CommonFrameWidthResolution,
    left_frame_index: int,
    right_frame_index: int,
) -> tuple[PixelInterval, tuple[FrameWidthMeasurementConstraint, ...]] | None:
    if common_width.state != EvidenceState.SUPPORTED:
        return None
    eligible = tuple(
        constraint
        for constraint in common_width.constraints
        if constraint.frame_index not in {left_frame_index, right_frame_index}
        and all(
            boundary_role_is_independent_physical_measurement(boundary)
            for boundary in (constraint.leading, constraint.trailing)
        )
    )
    contributor_indexes = measurements.largest_measurement_compatible_interval_indexes(
        tuple(constraint.width_px for constraint in eligible),
        MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS,
    )
    if not contributor_indexes:
        return None
    contributors = tuple(eligible[index] for index in contributor_indexes)
    return (
        measurements.interval_envelope(
            tuple(constraint.width_px for constraint in contributors)
        ),
        contributors,
    )


def slots_do_not_contradict_supported_common_width(
    slots: tuple[FrameSlot, ...],
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    common_width: CommonFrameWidthResolution,
) -> bool:
    if common_width.state != EvidenceState.SUPPORTED:
        return False
    assert common_width.width_px is not None
    last_index = len(slots) - 1
    for slot_index, slot in enumerate(slots):
        if slot.width_px.intersects(common_width.width_px):
            continue
        clipped_side = (
            BoundarySide.LEADING
            if slot_index == 0
            else BoundarySide.TRAILING
            if slot_index == last_index
            else None
        )
        if clipped_side is None or slot.width_px.maximum >= common_width.width_px.minimum:
            return False
        visible_boundary = (
            slot.leading if clipped_side == BoundarySide.LEADING else slot.trailing
        )
        if not measurements.boundary_matches_holder(
            visible_boundary,
            holder_boundaries.get(clipped_side),
        ):
            return False
        opposite_boundary = (
            slot.trailing if clipped_side == BoundarySide.LEADING else slot.leading
        )
        if not opposite_boundary.independently_observed:
            return False
    return True


def common_width_has_independent_measurement_basis(
    common_width: CommonFrameWidthResolution,
) -> bool:
    if common_width.state != EvidenceState.SUPPORTED:
        return False
    independent_constraints = tuple(
        constraint
        for constraint in common_width.constraints
        if all(
            boundary_role_is_independent_physical_measurement(boundary)
            for boundary in (constraint.leading, constraint.trailing)
        )
    )
    return bool(
        len(independent_constraints) >= MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS
        or (
            common_width.physical_scale_constraint is not None
            and independent_constraints
        )
    )
