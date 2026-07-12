from __future__ import annotations

from ....cache import MeasurementCache
from ....cache.separator import cached_separator_profile
from ....constants import CANDIDATE_SOURCE_FRAME_SEQUENCE
from ....domain import Box, HolderSpan, SequenceHypothesis
from ....formats import FormatPhysicalSpec
from ....policies.runtime.separator import SeparatorPolicy
from ....units import ScanCalibration
from ...context import DetectionRequest
from ...geometry import CandidateGeometry
from ...physical.boundary import (
    HolderOcclusionEvidence,
    holder_occlusion_for_sequence,
)
from ...physical.photo_size import frame_dimension_estimate
from ...physical.separator.assignment import (
    boundary_position_constraint,
    build_frame_boundaries,
    frames_from_boundaries,
)
from ...physical.separator.observations import (
    measure_focused_separator_band,
    measure_separator_bands,
)
from ..model import BuiltCandidate
from ..plan.count_hypotheses import CountHypothesis


def _separator_measurement_corridor(
    holder_span: HolderSpan,
    crop_envelope: CropEnvelope,
) -> Box:
    holder = holder_span.box
    crop = crop_envelope.box
    corridor = Box(
        holder.left,
        max(holder.top, crop.top),
        holder.right,
        min(holder.bottom, crop.bottom),
    )
    return corridor if corridor.valid() else holder


def build_frame_sequence_geometry(
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count_hypothesis: CountHypothesis,
    sequence_hypothesis: SequenceHypothesis,
    scan_calibration: ScanCalibration,
    *,
    cache: MeasurementCache,
    separator_policy: SeparatorPolicy,
) -> BuiltCandidate:
    if cache.layout != request.layout:
        raise ValueError("candidate build requires matching measurement cache")
    count = max(1, int(count_hypothesis.count))
    height, width = cache.gray_work.shape
    holder_span = HolderSpan(Box(0, 0, width, height))
    visible_sequence_span = sequence_hypothesis.visible_sequence_span
    corridor = _separator_measurement_corridor(
        holder_span,
        sequence_hypothesis.crop_envelope,
    )
    profile = cached_separator_profile(
        cache,
        corridor,
        separator_policy.profile,
    )
    observations = measure_separator_bands(
        profile,
        corridor_start=float(corridor.left),
        parameters=separator_policy.observation,
    )
    dimensions = frame_dimension_estimate(
        visible_sequence_span,
        fmt,
        scan_calibration,
        separator_policy.frame_dimension_estimate,
        layout=request.layout,
    )
    provisional = build_frame_boundaries(
        observations,
        (),
        visible_sequence_span,
        count,
        dimensions,
        HolderOcclusionEvidence.unavailable(),
    )
    holder_occlusion = holder_occlusion_for_sequence(
        sequence_hypothesis.boundary_observations,
        visible_sequence_span,
        provisional.boundaries,
        dimensions.width_px,
    )
    focused_observations = tuple(
        (boundary_index, observation)
        for boundary_index in range(1, count)
        if (
            observation := measure_focused_separator_band(
                profile,
                boundary_position_constraint(
                    visible_sequence_span,
                    boundary_index,
                    count,
                    dimensions,
                    holder_occlusion,
                ).position,
                corridor_start=float(corridor.left),
                parameters=separator_policy.observation,
            )
        )
        is not None
    )
    boundary_result = build_frame_boundaries(
        observations,
        focused_observations,
        visible_sequence_span,
        count,
        dimensions,
        holder_occlusion,
    )
    frames = frames_from_boundaries(
        visible_sequence_span,
        boundary_result.boundaries,
        count,
    )
    return BuiltCandidate(
        geometry=CandidateGeometry(
            format_id=fmt.format_id,
            layout=request.layout,
            strip_mode=count_hypothesis.strip_mode,
            count=count,
            holder_span=holder_span,
            visible_sequence_span=visible_sequence_span,
            crop_envelope=sequence_hypothesis.crop_envelope,
            frames=frames,
            separator_observations=observations,
            separator_assignments=boundary_result.assignments,
            frame_boundaries=boundary_result.boundaries,
            frame_dimension_estimate=dimensions,
            source=CANDIDATE_SOURCE_FRAME_SEQUENCE,
            automatic_processing_supported=True,
            sequence_hypothesis_name=sequence_hypothesis.name,
            sequence_hypothesis_strategy=sequence_hypothesis.strategy,
            sequence_provenance=sequence_hypothesis.provenance,
            boundary_observations=sequence_hypothesis.boundary_observations,
        ),
        count_hypothesis=count_hypothesis,
        build_diagnostics=(),
    )
