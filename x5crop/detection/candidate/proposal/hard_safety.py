from __future__ import annotations

from ....constants import CANDIDATE_SOURCE_HARD_SAFETY
from ....domain import Box, MeasurementProvenance
from ....geometry.boxes import map_work_box
from ....geometry.frame_fit import frame_boxes_from_gaps
from ....geometry.model_gaps import equal_model_gap
from ...context import DetectionContext
from ...physical.spans import FilmSpan, HolderSpan
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
    separators = tuple(
        equal_model_gap(index, pitch * index, 0.0)
        for index in range(1, count)
    )
    work_frames = tuple(
        frame_boxes_from_gaps(
            span,
            list(separators),
            count,
            work_width,
            work_height,
            0,
            0,
            origin=0.0,
            pitch=pitch,
        )
    )
    source_height, source_width = context.source_gray.shape
    image_frames = tuple(
        map_work_box(
            frame,
            context.request.layout,
            source_width,
            source_height,
        )
        for frame in work_frames
    )
    hypothesis = CountHypothesis(
        count=count,
        strip_mode=context.request.strip_mode,
        offsets=(0.0,),
        placement_source="full_canvas_equal_partition",
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
            film_span=FilmSpan(span),
            work_frames=work_frames,
            image_outer=map_work_box(
                span,
                context.request.layout,
                source_width,
                source_height,
            ),
            image_frames=image_frames,
            separators=separators,
            origin=0.0,
            pitch=pitch,
            offset_fraction=0.0,
            source=CANDIDATE_SOURCE_HARD_SAFETY,
            automatic_processing_supported=False,
            contract="review_only_safety_geometry",
            outer_proposal_name="full_canvas_safety",
            outer_proposal_strategy="safety_outer",
            outer_provenance=MeasurementProvenance(
                root_measurement="safety_geometry_model",
                source="full_canvas_safety",
                dependencies=("canvas", "count"),
            ),
        ),
        count_hypothesis=hypothesis,
        build_diagnostics=(
            "no_physical_candidate",
            "automatic_processing_not_supported",
        ),
    )
