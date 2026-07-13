from __future__ import annotations

from ..candidate.model import BuiltCandidate
from ..candidate.plan.count_hypotheses import CountHypothesis, CountHypothesisSource
from ..candidate.proposal.sequence import photo_sequence_search_scope
from ..context import DetectionContext
from ..physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    ReviewOnlyContainment,
    SequenceResiduals,
)
from ..physical.photo_size import frame_dimension_priors


def unresolved_dual_lane_candidate(
    context: DetectionContext,
    diagnostic: str,
) -> BuiltCandidate:
    physical_spec = context.configuration.physical_spec
    if physical_spec.physical_layout != "dual_lane":
        raise ValueError("unresolved dual-lane geometry requires dual-lane input")
    if not diagnostic:
        raise ValueError("unresolved dual-lane geometry requires a diagnostic")
    scope = photo_sequence_search_scope(
        context.measurement_cache,
        context.configuration.boundary_path,
    )
    count = physical_spec.default_count
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
