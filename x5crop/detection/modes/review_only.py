from __future__ import annotations

from ...domain import (
    Box,
    CropEnvelope,
    HolderSpan,
    MeasurementIdentity,
    MeasurementProvenance,
    VisibleSequenceSpan,
)
from ..candidate.model import BuiltCandidate
from ..candidate.plan.count_hypotheses import CountHypothesis, CountHypothesisSource
from ..context import DetectionContext
from ..physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    ReviewOnlyGeometry,
    SequenceResiduals,
)
from ..physical.boundary import canvas_boundary_paths
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
    height, width = context.measurement_cache.gray_work.shape
    span = Box(0, 0, width, height)
    count = physical_spec.default_count
    visible_span = VisibleSequenceSpan(span)
    dimensions = frame_dimension_priors(
        visible_span,
        physical_spec,
        context.scan_calibration,
        layout=context.request.layout,
    )[0]
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
                AssignmentConsensusOutcome.NOT_APPLICABLE,
                0,
                (),
            ),
            sequence_provenance=MeasurementProvenance(
                root_measurement=MeasurementIdentity.REVIEW_ONLY_MODE,
                source="review_only_canvas",
                dependencies=(MeasurementIdentity.CANVAS,),
            ),
            boundary_paths=canvas_boundary_paths(width, height),
        ),
        count_hypothesis=CountHypothesis(
            count=count,
            strip_mode=context.request.strip_mode,
            source=CountHypothesisSource.MODE_CONTRACT,
        ),
        build_diagnostics=(
            diagnostic,
            "automatic_processing_not_supported",
        ),
    )
