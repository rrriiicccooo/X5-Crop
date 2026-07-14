from __future__ import annotations

from ....domain import (
    PhotoSequenceSearchScope,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
)
from ...context import DetectionContext
from ...physical.photo_size import frame_dimension_priors
from ..model import BuiltCandidate
from ..plan.model import CountHypothesis, CountHypothesisSource
from ...physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    ReviewOnlyContainment,
    SequenceResiduals,
)


def hard_safety_candidate(
    context: DetectionContext,
    count: int,
    search_scope: PhotoSequenceSearchScope,
    *,
    physical_search: PhysicalSearchOutcome,
) -> BuiltCandidate:
    physical_spec = context.configuration.physical_spec
    if count <= 0:
        raise ValueError("hard-safety candidate count must be positive")
    count = int(count)
    if count not in physical_spec.allowed_counts:
        raise ValueError("hard-safety candidate count must be physically allowed")
    dimensions = frame_dimension_priors(
        physical_spec,
    )[0]
    return BuiltCandidate(
        geometry=ReviewOnlyContainment(
            format_id=physical_spec.format_id,
            layout=context.request.layout,
            strip_mode=context.request.strip_mode,
            count=count,
            holder_span=search_scope.holder_span,
            containment_fallback=search_scope.containment_fallback,
            frame_dimension_prior=dimensions,
            residuals=SequenceResiduals(None, 0.0),
            assignment_consensus=BoundaryAssignmentConsensus(
                AssignmentConsensusOutcome.COMPONENT_UNRESOLVED,
                1,
                (),
            ),
            sequence_provenance=search_scope.provenance,
            raw_boundary_paths=search_scope.raw_boundary_paths,
        ),
        count_hypothesis=CountHypothesis(
            count=count,
            strip_mode=context.request.strip_mode,
            source=CountHypothesisSource.HARD_SAFETY,
        ),
        build_diagnostics=(
            "photo_aperture_geometry_unresolved",
            *(
                ("search_budget_exhausted",)
                if PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED
                in physical_search.facts
                else ()
            ),
            "automatic_processing_not_supported",
        ),
    )
