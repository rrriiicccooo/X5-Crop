from __future__ import annotations

from ....domain import (
    Box,
    CropEnvelope,
    HolderSpan,
    MeasurementIdentity,
    MeasurementProvenance,
    VisibleSequenceSpan,
)
from ...context import DetectionContext
from ...physical.boundary import canvas_boundary_paths
from ...physical.photo_size import frame_dimension_priors
from ...physical.sequence_solver import (
    SequenceSolveUnavailable,
    solve_frame_sequence,
)
from ..model import BuiltCandidate
from ..plan.count_hypotheses import CountHypothesis, CountHypothesisSource
from ...physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    ReviewOnlyGeometry,
    SequenceResiduals,
    SequenceSolution,
)


def hard_safety_candidate(
    context: DetectionContext,
    count: int,
) -> BuiltCandidate:
    physical_spec = context.configuration.physical_spec
    work_height, work_width = context.measurement_cache.gray_work.shape
    if count <= 0:
        raise ValueError("hard-safety candidate count must be positive")
    count = int(count)
    if count not in physical_spec.allowed_counts:
        raise ValueError("hard-safety candidate count must be physically allowed")
    span = Box(0, 0, work_width, work_height)
    visible_span = VisibleSequenceSpan(span)
    dimensions = frame_dimension_priors(
        visible_span,
        physical_spec,
        context.scan_calibration,
        layout=context.request.layout,
    )[0]
    boundary_paths = canvas_boundary_paths(
        work_width,
        work_height,
    )
    solver_budget = (
        context.configuration.candidate_plan.sequence_solver
        .maximum_assignment_evaluations
    )
    solved = solve_frame_sequence(
        (),
        (),
        visible_span,
        count,
        dimensions,
        boundary_paths,
        solver_budget,
        edge_texture_limit=context.measurement_cache.image_statistics.edge_texture_limit,
    )
    context.execution_statistics.record_assignment_evaluations(
        solved.assignment_evaluations
    )
    hypothesis = CountHypothesis(
        count=count,
        strip_mode=context.request.strip_mode,
        source=CountHypothesisSource.HARD_SAFETY,
    )
    if isinstance(solved, SequenceSolveUnavailable):
        return BuiltCandidate(
            geometry=ReviewOnlyGeometry(
                format_id=physical_spec.format_id,
                layout=context.request.layout,
                strip_mode=context.request.strip_mode,
                count=count,
                holder_span=HolderSpan(span),
                visible_sequence_span=visible_span,
                crop_envelope=CropEnvelope(span),
                frame_dimension_prior=dimensions,
                residuals=SequenceResiduals(None, None, 0.0),
                assignment_consensus=BoundaryAssignmentConsensus(
                    AssignmentConsensusOutcome.COMPONENT_UNRESOLVED,
                    1,
                    (),
                ),
                sequence_provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.SAFETY_GEOMETRY_MODEL,
                    source="unresolved_full_canvas_safety",
                    dependencies=(
                        MeasurementIdentity.CANVAS,
                        MeasurementIdentity.COUNT,
                    ),
                ),
                boundary_paths=boundary_paths,
            ),
            count_hypothesis=hypothesis,
            build_diagnostics=(solved.reason.value,),
        )
    return BuiltCandidate(
        geometry=SequenceSolution(
            format_id=physical_spec.format_id,
            layout=context.request.layout,
            strip_mode=context.request.strip_mode,
            count=count,
            holder_span=HolderSpan(span),
            visible_sequence_span=visible_span,
            crop_envelope=CropEnvelope(span),
            photo_intervals=solved.photo_intervals,
            frames=solved.frames,
            separator_observations=(),
            separator_assignments=(),
            frame_boundaries=solved.boundaries,
            inter_frame_spacings=solved.relations,
            holder_occlusion=solved.holder_occlusion,
            frame_dimension_prior=dimensions,
            residuals=solved.residuals,
            assignment_consensus=solved.assignment_consensus,
            search_budget_exhausted=solved.search_budget_exhausted,
            automatic_processing_supported=False,
            sequence_provenance=MeasurementProvenance(
                root_measurement=MeasurementIdentity.SAFETY_GEOMETRY_MODEL,
                source="full_canvas_safety",
                dependencies=(
                    MeasurementIdentity.CANVAS,
                    MeasurementIdentity.COUNT,
                ),
            ),
            boundary_paths=boundary_paths,
        ),
        count_hypothesis=hypothesis,
        build_diagnostics=(
            "no_physical_candidate",
            "automatic_processing_not_supported",
        ),
    )
