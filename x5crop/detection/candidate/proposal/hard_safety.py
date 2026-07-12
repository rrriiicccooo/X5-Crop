from __future__ import annotations

from ....constants import CANDIDATE_SOURCE_HARD_SAFETY
from ....domain import Box, MeasurementProvenance
from ...context import DetectionContext
from ...physical.boundary import canvas_boundary_observations
from ...physical.boundary import HolderOcclusionEvidence
from ...physical.photo_size import frame_dimension_prior
from ...physical.sequence_solver import solve_frame_sequence
from x5crop.domain import CropEnvelope, HolderSpan, VisibleSequenceSpan
from ..model import BuiltCandidate
from ..plan.count_hypotheses import CountHypothesis
from ...physical.model import SequenceSolution


def hard_safety_candidate(
    context: DetectionContext,
    count: int,
) -> BuiltCandidate:
    physical_spec = context.configuration.physical_spec
    work_height, work_width = context.measurement_cache.gray_work.shape
    count = max(1, int(count))
    span = Box(0, 0, work_width, work_height)
    visible_span = VisibleSequenceSpan(span)
    dimensions = frame_dimension_prior(
        visible_span,
        physical_spec,
        context.scan_calibration,
        layout=context.request.layout,
    )
    holder_occlusion = HolderOcclusionEvidence.unavailable()
    boundary_observations = canvas_boundary_observations(
        work_width,
        work_height,
    )
    solved = solve_frame_sequence(
        (),
        (),
        visible_span,
        count,
        dimensions,
        holder_occlusion,
        boundary_observations,
        context.configuration.candidate_plan.sequence_solver.maximum_assignment_evaluations,
    )
    hypothesis = CountHypothesis(
        count=count,
        strip_mode=context.request.strip_mode,
        source="hard_safety",
        allowed_by_physical_spec=count in physical_spec.allowed_counts,
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
            holder_occlusion=holder_occlusion,
            frame_dimension_prior=dimensions,
            residuals=solved.residuals,
            search_budget_exhausted=solved.search_budget_exhausted,
            source=CANDIDATE_SOURCE_HARD_SAFETY,
            automatic_processing_supported=False,
            sequence_hypothesis_name="full_canvas_safety",
            sequence_hypothesis_strategy="safety_canvas",
            sequence_provenance=MeasurementProvenance(
                root_measurement="safety_geometry_model",
                source="full_canvas_safety",
                dependencies=("canvas", "count"),
            ),
            boundary_observations=boundary_observations,
        ),
        count_hypothesis=hypothesis,
        build_diagnostics=(
            "no_physical_candidate",
            "automatic_processing_not_supported",
        ),
    )
