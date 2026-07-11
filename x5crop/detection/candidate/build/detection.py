from __future__ import annotations

import numpy as np

from ....domain import Box, MeasurementProvenance
from ....formats import FormatPhysicalSpec
from ....geometry.boxes import map_work_box
from ....geometry.frame_fit import frame_boxes_from_gaps
from ....policies.runtime.separator import SeparatorPolicy
from ....cache import MeasurementCache
from ....units import ScanCalibration
from ...context import DetectionRequest
from ...physical.spans import FilmSpan, HolderSpan
from ...physical.separator.hints import SeparatorGapHintSet
from ..model import BuiltCandidate
from ..plan.count_hypotheses import CountHypothesis
from ...geometry import CandidateGeometry
from .separator_gaps import (
    SeparatorGapBuildResult,
    apply_nearby_separator_lifecycle,
    build_primary_separator_gaps_for_outer,
)


def build_detection_geometry_for_outer(
    gray: np.ndarray,
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    outer: Box,
    offset_fraction: float,
    holder_span: HolderSpan,
    source: str,
    automatic_processing_supported: bool,
    contract: str | None,
    count_hypothesis: CountHypothesis | None,
    outer_candidate_name: str,
    outer_candidate_strategy: str,
    outer_provenance: MeasurementProvenance,
    scan_calibration: ScanCalibration,
    gap_max_width_ratio_override: float | None,
    separator_gap_hints: SeparatorGapHintSet | None,
    mode_diagnostics: tuple[str, ...],
    *,
    cache: MeasurementCache,
    separator_policy: SeparatorPolicy,
) -> BuiltCandidate:
    h, w = gray.shape
    if cache.layout != request.layout:
        raise ValueError("candidate build requires matching analysis cache")
    gray_work = cache.gray_work
    wh, ww = gray_work.shape
    separator_gaps = _build_separator_gap_lifecycle(
        gray_work,
        fmt,
        count,
        strip_mode,
        outer,
        offset_fraction,
        cache,
        gap_max_width_ratio_override,
        separator_policy,
        scan_calibration,
        "x" if request.layout == "horizontal" else "y",
        explicit_count=bool(request.requested_count is not None),
        gap_hints=separator_gap_hints,
    )
    outer = separator_gaps.outer
    origin = separator_gaps.origin
    pitch = separator_gaps.pitch
    gaps = separator_gaps.gaps
    boxes_work = frame_boxes_from_gaps(
        outer,
        gaps,
        count,
        ww,
        wh,
        0,
        0,
        origin=origin,
        pitch=pitch,
    )
    boxes = tuple(map_work_box(box, request.layout, w, h) for box in boxes_work)
    outer_original = map_work_box(outer, request.layout, w, h)
    return BuiltCandidate(
        geometry=CandidateGeometry(
            format_id=fmt.format_id,
            layout=request.layout,
            strip_mode=strip_mode,
            count=int(count),
            holder_span=holder_span,
            film_span=FilmSpan(outer),
            work_frames=tuple(boxes_work),
            image_outer=outer_original,
            image_frames=boxes,
            separators=tuple(gaps),
            origin=float(origin),
            pitch=float(pitch),
            offset_fraction=float(offset_fraction),
            source=source,
            automatic_processing_supported=automatic_processing_supported,
            contract=contract,
            outer_proposal_name=outer_candidate_name,
            outer_proposal_strategy=outer_candidate_strategy,
            outer_provenance=outer_provenance,
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
