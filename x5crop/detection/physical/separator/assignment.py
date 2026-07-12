from __future__ import annotations

from ....domain import (
    BoundaryPositionConstraint,
    DimensionConstrainedBoundary,
    FrameBoundary,
    FrameBoundarySource,
    FrameDimensionPrior,
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
    SeparatorAssignment,
    SeparatorBandObservation,
    SeparatorWidthConstraint,
    VisibleSequenceSpan,
)
from ..boundary import HolderOcclusionConstraint


BOUNDARY_ADJACENT_FRAME_COUNT = 2.0


def assign_observation_to_boundary(
    boundary_index: int,
    observation: SeparatorBandObservation,
    position_constraint: BoundaryPositionConstraint,
    width_constraint: SeparatorWidthConstraint,
) -> SeparatorAssignment:
    return SeparatorAssignment(
        boundary_index=int(boundary_index),
        observation=observation,
        position_constraint=position_constraint,
        width_constraint=width_constraint,
        used_for_boundary=False,
    )


def frame_boundary_from_assignment(
    assignment: SeparatorAssignment,
) -> FrameBoundary:
    if not assignment.used_for_boundary:
        raise ValueError("frame boundary requires a selected separator assignment")
    return FrameBoundary(
        boundary_index=assignment.boundary_index,
        position=PixelInterval.exact(assignment.observation.center),
        source=FrameBoundarySource.OBSERVED_SEPARATOR,
        provenance=assignment.observation.provenance,
        assignment=assignment,
    )


def dimension_constrained_boundary(
    boundary_index: int,
    position: PixelInterval,
    provenance: MeasurementProvenance,
    assignment: SeparatorAssignment | None = None,
) -> FrameBoundary:
    constraint = DimensionConstrainedBoundary(
        boundary_index=int(boundary_index),
        position=position,
        provenance=provenance,
        focused_observation=(
            assignment.observation if assignment is not None else None
        ),
    )
    return FrameBoundary(
        boundary_index=int(boundary_index),
        position=position,
        source=FrameBoundarySource.DIMENSION_CONSTRAINED,
        provenance=provenance,
        assignment=assignment,
        dimension_constraint=constraint,
    )


def boundary_position_constraint(
    span: VisibleSequenceSpan,
    boundary_index: int,
    count: int,
    dimensions: FrameDimensionPrior,
    holder_occlusion: HolderOcclusionConstraint,
) -> BoundaryPositionConstraint:
    if not 0 < boundary_index < count:
        raise ValueError("frame boundary index must be internal to the sequence")
    leading = PixelInterval.exact(float(span.box.left)).plus(
        dimensions.width_px.scaled(float(boundary_index))
    ).minus(holder_occlusion.leading_hidden_width_px)
    trailing = PixelInterval.exact(float(span.box.right)).minus(
        dimensions.width_px.scaled(float(count - boundary_index))
    ).plus(holder_occlusion.trailing_hidden_width_px)
    minimum = max(
        float(span.box.left),
        min(leading.minimum, trailing.minimum),
    )
    maximum = min(
        float(span.box.right),
        max(leading.maximum, trailing.maximum),
    )
    if maximum < minimum:
        raise ValueError("boundary position constraints do not intersect sequence span")
    position = PixelInterval(minimum, maximum)
    return BoundaryPositionConstraint(
        boundary_index=int(boundary_index),
        position=position,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
            source="boundary_position_constraint",
            dependencies=(
                dimensions.provenance.root_measurement,
                MeasurementIdentity.SEQUENCE_BOUNDARIES,
                MeasurementIdentity.HOLDER_OCCLUSION,
            ),
        ),
    )


def separator_width_constraint(
    span: VisibleSequenceSpan,
    boundary_index: int,
    count: int,
    dimensions: FrameDimensionPrior,
    holder_occlusion: HolderOcclusionConstraint,
) -> SeparatorWidthConstraint:
    if not 0 < boundary_index < count:
        raise ValueError("separator width constraint index must be internal")
    occlusion = holder_occlusion.combined_hidden_width_px
    available_anchor_span = PixelInterval.exact(float(span.box.width)).plus(
        occlusion
    )
    maximum_width = (
        available_anchor_span.maximum
        - BOUNDARY_ADJACENT_FRAME_COUNT * dimensions.width_px.minimum
    )
    return SeparatorWidthConstraint(
        boundary_index=int(boundary_index),
        width=PixelInterval(0.0, max(0.0, maximum_width)),
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
            source="separator_width_constraint",
            dependencies=(
                dimensions.provenance.root_measurement,
                MeasurementIdentity.SEQUENCE_BOUNDARIES,
                MeasurementIdentity.HOLDER_OCCLUSION,
            ),
        ),
    )
