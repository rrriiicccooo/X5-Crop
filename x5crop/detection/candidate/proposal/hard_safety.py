from __future__ import annotations

from ....constants import CANDIDATE_SOURCE_HARD_SAFETY
from ....domain import Box, MeasurementProvenance
from ...context import DetectionContext
from ...physical.boundary import canvas_boundary_observations
from ...physical.spans import CropEnvelope, HolderSpan, VisibleSequenceSpan
from ..model import BuiltCandidate
from ..plan.count_hypotheses import CountHypothesis
from ...geometry import CandidateGeometry


def hard_safety_candidate(
    context: DetectionContext,
    count: int,
) -> BuiltCandidate:
    physical_spec = context.policy.physical_spec
    work_height, work_width = context.measurement_cache.gray_work.shape
    count = max(1, int(count))
    span = Box(0, 0, work_width, work_height)
    pitch = float(work_width) / float(count)
    frames = tuple(
        Box(
            int(round(pitch * index)),
            0,
            int(round(pitch * (index + 1))),
            work_height,
        )
        for index in range(count)
    )
    hypothesis = CountHypothesis(
        count=count,
        strip_mode=context.request.strip_mode,
        offsets=(0.0,),
        placement_source="full_canvas_safety_partition",
        source="hard_safety",
        allowed_by_physical_spec=count in physical_spec.allowed_counts,
    )
    return BuiltCandidate(
        geometry=CandidateGeometry(
            format_id=physical_spec.format_id,
            layout=context.request.layout,
            strip_mode=context.request.strip_mode,
            count=count,
            holder_span=HolderSpan(span),
            visible_sequence_span=VisibleSequenceSpan(span),
            crop_envelope=CropEnvelope(span),
            frames=frames,
            separators=(),
            origin=0.0,
            pitch=pitch,
            offset_fraction=0.0,
            source=CANDIDATE_SOURCE_HARD_SAFETY,
            automatic_processing_supported=False,
            contract="review_only_safety_geometry",
            sequence_hypothesis_name="full_canvas_safety",
            sequence_hypothesis_strategy="safety_canvas",
            sequence_provenance=MeasurementProvenance(
                root_measurement="safety_geometry_model",
                source="full_canvas_safety",
                dependencies=("canvas", "count"),
            ),
            boundary_observations=canvas_boundary_observations(
                work_width,
                work_height,
            ),
        ),
        count_hypothesis=hypothesis,
        build_diagnostics=(
            "no_physical_candidate",
            "automatic_processing_not_supported",
        ),
    )
