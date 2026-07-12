from __future__ import annotations

from ...domain import (
    Box,
    CropEnvelope,
    EvidenceState,
    HolderSpan,
    MeasurementIdentity,
    MeasurementProvenance,
    VisibleSequenceSpan,
)
from ..candidate.model import BuiltCandidate
from ..candidate.plan.count_hypotheses import CountHypothesis, CountHypothesisSource
from ..context import DetectionContext
from ..physical.model import (
    BoundaryAssignmentConsensus,
    ReviewOnlyGeometry,
    SequenceResiduals,
)
from ..physical.boundary import canvas_boundary_observations
from ..physical.photo_size import frame_dimension_priors


def review_only_candidate(context: DetectionContext) -> BuiltCandidate:
    physical_spec = context.configuration.physical_spec
    if (
        physical_spec.physical_layout != "dual_lane"
        or context.request.strip_mode != "partial"
    ):
        raise ValueError("review-only mode requires dual-lane partial input")
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
                EvidenceState.NOT_APPLICABLE,
                "review_only_geometry_has_no_assignments",
                0,
                (),
            ),
            sequence_hypothesis_name="review_only_canvas",
            sequence_hypothesis_strategy="review_only_canvas",
            sequence_provenance=MeasurementProvenance(
                root_measurement=MeasurementIdentity.REVIEW_ONLY_MODE,
                source="review_only_canvas",
                dependencies=(MeasurementIdentity.CANVAS,),
            ),
            boundary_observations=canvas_boundary_observations(width, height),
        ),
        count_hypothesis=CountHypothesis(
            count=count,
            strip_mode=context.request.strip_mode,
            source=CountHypothesisSource.MODE_CONTRACT,
        ),
        build_diagnostics=(
            "dual_lane_partial_not_supported",
            "automatic_processing_not_supported",
        ),
    )
