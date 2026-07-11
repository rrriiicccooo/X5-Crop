from __future__ import annotations

import numpy as np

from ....domain import Box, MeasurementProvenance
from ....formats import FormatPhysicalSpec
from ....geometry.frame_fit import frame_boxes_from_gaps
from ....policies.runtime.separator import SeparatorPolicy
from ....cache import MeasurementCache
from ....units import ScanCalibration
from ...context import DetectionRequest
from ...physical.boundary import BoundaryObservation
from ...physical.spans import CropEnvelope, HolderSpan, VisibleSequenceSpan
from ...physical.separator.hints import SeparatorGapHintSet
from ..model import BuiltCandidate
from ..plan.count_hypotheses import CountHypothesis
from ...geometry import CandidateGeometry
from .separator_gaps import (
    SeparatorGapBuildResult,
    apply_nearby_separator_lifecycle,
    build_primary_separator_gaps_for_outer,
)


def build_candidate_geometry(
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    visible_sequence_span: VisibleSequenceSpan,
    crop_envelope: CropEnvelope,
    offset_fraction: float,
    holder_span: HolderSpan,
    source: str,
    automatic_processing_supported: bool,
    contract: str | None,
    count_hypothesis: CountHypothesis | None,
    span_candidate_name: str,
    span_candidate_strategy: str,
    sequence_provenance: MeasurementProvenance,
    boundary_observations: tuple[BoundaryObservation, ...],
    scan_calibration: ScanCalibration,
    gap_max_width_ratio_override: float | None,
    separator_gap_hints: SeparatorGapHintSet | None,
    mode_diagnostics: tuple[str, ...],
    *,
    cache: MeasurementCache,
    separator_policy: SeparatorPolicy,
) -> BuiltCandidate:
    if cache.layout != request.layout:
        raise ValueError("candidate build requires matching analysis cache")
    gray_work = cache.gray_work
    wh, ww = gray_work.shape
    sequence_box = visible_sequence_span.box
    separator_gaps = _build_separator_gap_lifecycle(
        gray_work,
        fmt,
        count,
        strip_mode,
        sequence_box,
        offset_fraction,
        cache,
        gap_max_width_ratio_override,
        separator_policy,
        scan_calibration,
        "x" if request.layout == "horizontal" else "y",
        explicit_count=bool(request.requested_count is not None),
        gap_hints=separator_gap_hints,
    )
    sequence_box = separator_gaps.outer
    origin = separator_gaps.origin
    pitch = separator_gaps.pitch
    gaps = separator_gaps.gaps
    boxes_work = frame_boxes_from_gaps(
        sequence_box,
        gaps,
        count,
        ww,
        wh,
        0,
        0,
        origin=origin,
        pitch=pitch,
    )
    return BuiltCandidate(
        geometry=CandidateGeometry(
            format_id=fmt.format_id,
            layout=request.layout,
            strip_mode=strip_mode,
            count=int(count),
            holder_span=holder_span,
            visible_sequence_span=VisibleSequenceSpan(sequence_box),
            crop_envelope=crop_envelope,
            frames=tuple(boxes_work),
            separators=tuple(gaps),
            origin=float(origin),
            pitch=float(pitch),
            offset_fraction=float(offset_fraction),
            source=source,
            automatic_processing_supported=automatic_processing_supported,
            contract=contract,
            sequence_hypothesis_name=span_candidate_name,
            sequence_hypothesis_strategy=span_candidate_strategy,
            sequence_provenance=sequence_provenance,
            boundary_observations=boundary_observations,
        ),
        count_hypothesis=count_hypothesis,
        build_diagnostics=tuple(mode_diagnostics),
    )


def _build_separator_gap_lifecycle(
    gray_work: np.ndarray,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    outer: Box,
    offset_fraction: float,
    cache: MeasurementCache,
    gap_max_width_ratio_override: float | None,
    separator_policy: SeparatorPolicy,
    calibration: ScanCalibration,
    long_axis: str,
    *,
    explicit_count: bool,
    gap_hints: SeparatorGapHintSet | None = None,
) -> SeparatorGapBuildResult:
    separator_gaps = build_primary_separator_gaps_for_outer(
        gray_work,
        fmt,
        count,
        strip_mode,
        outer,
        offset_fraction,
        cache,
        gap_max_width_ratio_override,
        separator_policy,
        calibration,
        long_axis,
        explicit_count=explicit_count,
        gap_hints=gap_hints,
    )
    return apply_nearby_separator_lifecycle(
        count,
        strip_mode,
        separator_gaps,
        separator_policy,
        explicit_count=explicit_count,
    )
