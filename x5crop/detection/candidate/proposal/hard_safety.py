from __future__ import annotations

from ...context import DetectionContext
from ...physical.photo_size import frame_dimension_priors
from ..model import BuiltCandidate
from ..plan.count_hypotheses import CountHypothesis, CountHypothesisSource
from .sequence import photo_sequence_search_scope
from ...physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    ReviewOnlyContainment,
    SequenceResiduals,
)


def hard_safety_candidate(
    context: DetectionContext,
    count: int,
) -> BuiltCandidate:
    physical_spec = context.configuration.physical_spec
    if count <= 0:
        raise ValueError("hard-safety candidate count must be positive")
    count = int(count)
    if count not in physical_spec.allowed_counts:
        raise ValueError("hard-safety candidate count must be physically allowed")
    scope = photo_sequence_search_scope(
        context.measurement_cache,
        context.configuration.boundary_path,
    )
    dimensions = frame_dimension_priors(
        physical_spec,
        context.scan_calibration,
        layout=context.request.layout,
    )[0]
    return BuiltCandidate(
        geometry=ReviewOnlyContainment(
            format_id=physical_spec.format_id,
            layout=context.request.layout,
            strip_mode=context.request.strip_mode,
            count=count,
            holder_span=scope.holder_span,
            containment_fallback=scope.containment_fallback,
            frame_dimension_prior=dimensions,
            residuals=SequenceResiduals(None, None, 0.0),
            assignment_consensus=BoundaryAssignmentConsensus(
                AssignmentConsensusOutcome.COMPONENT_UNRESOLVED,
                1,
                (),
            ),
            sequence_provenance=scope.provenance,
            raw_boundary_paths=scope.raw_boundary_paths,
        ),
        count_hypothesis=CountHypothesis(
            count=count,
            strip_mode=context.request.strip_mode,
            source=CountHypothesisSource.HARD_SAFETY,
        ),
        build_diagnostics=(
            "photo_aperture_geometry_unresolved",
            "automatic_processing_not_supported",
        ),
    )
