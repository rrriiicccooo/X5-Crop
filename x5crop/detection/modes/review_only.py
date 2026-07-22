from __future__ import annotations

from ..candidate.model import BuiltCandidate
from ..candidate.plan.model import CountHypothesis, CountHypothesisSource
from ..candidate.proposal.sequence import frame_sequence_search_scope
from ..context import DetectionContext
from ..physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    ReviewOnlyContainment,
    SequenceResiduals,
)
from ..physical.frame_dimensions import frame_dimension_priors
from ..evidence.content.regions import cached_content_region_observation
from ...domain import Box


def unresolved_dual_lane_candidate(
    context: DetectionContext,
    diagnostic: str,
) -> BuiltCandidate:
    physical_spec = context.configuration.physical_spec
    if physical_spec.layout.kind != "dual_lane":
        raise ValueError("unresolved dual-lane geometry requires dual-lane input")
    if not diagnostic:
        raise ValueError("unresolved dual-lane geometry requires a diagnostic")
    scope = frame_sequence_search_scope(
        context.workspace.measurement_cache,
        context.configuration.boundary_path,
        cached_content_region_observation(
            context.workspace.measurement_cache,
            Box(
                0,
                0,
                context.workspace.measurement_cache.gray_work.shape[1],
                context.workspace.measurement_cache.gray_work.shape[0],
            ),
            context.configuration.content,
        ),
    )
    count = physical_spec.strip.default_count
    dimensions = frame_dimension_priors(
        physical_spec,
    )[0]
    return BuiltCandidate(
        geometry=ReviewOnlyContainment(
            format_id=physical_spec.format_id,
            layout=context.request.layout,
            strip_mode=context.request.strip_mode,
            count=count,
            holder_safety=scope.holder_safety,
            frame_dimension_prior=dimensions,
            residuals=SequenceResiduals(None, 0.0),
            assignment_consensus=BoundaryAssignmentConsensus(
                AssignmentConsensusOutcome.NOT_APPLICABLE,
                0,
                (),
            ),
            sequence_provenance=scope.provenance,
            raw_boundary_paths=scope.raw_boundary_paths,
        ),
        count_hypothesis=CountHypothesis(
            count=count,
            strip_mode=context.request.strip_mode,
            source=CountHypothesisSource.MODE_CONTRACT,
        ),
        build_diagnostics=(diagnostic, "automatic_processing_not_supported"),
    )
