from __future__ import annotations

from ...cache import MeasurementCache
from ...domain import Box, MeasurementProvenance
from ...policies.parameters.candidate import ContentSeparatorGuidanceParameters
from ...policies.runtime.content import ContentPolicy
from ..context import DetectionRequest
from ..evidence.content.regions import (
    content_mask_region,
    content_region_runs,
    select_content_runs,
)
from ..physical.separator.hints import SeparatorGapHint, SeparatorGapHintSet

def _content_gap_hints_from_runs(
    selected_runs: tuple[tuple[int, int], ...],
    outer: Box,
) -> tuple[SeparatorGapHint, ...]:
    hints: list[SeparatorGapHint] = []
    for index in range(1, len(selected_runs)):
        left_run = selected_runs[index - 1]
        right_run = selected_runs[index]
        center = (float(left_run[1]) + float(right_run[0])) * 0.5 - float(outer.left)
        hints.append(
            SeparatorGapHint(
                index=index,
                work_center=center + float(outer.left),
                work_start=float(left_run[1]),
                work_end=float(right_run[0]),
            )
        )
    return tuple(hints)


def content_separator_guidance_for_count(
    request: DetectionRequest,
    count: int,
    cache: MeasurementCache,
    content_policy: ContentPolicy,
    guidance_policy: ContentSeparatorGuidanceParameters,
) -> SeparatorGapHintSet | None:
    if count <= 1:
        return None
    if cache.layout != request.layout:
        raise ValueError("measurement cache layout does not match content guidance")
    gray_work = cache.gray_work
    evidence = cache.content_evidence_work
    evidence_float = cache.content_evidence_float_work
    region = content_mask_region(
        evidence_float,
        gray_work.shape,
        cache,
        content_policy=content_policy,
    )
    if region is None or not region.valid():
        return None

    runs = content_region_runs(
        evidence,
        region,
        count,
        content_policy=content_policy,
    )
    selected_runs = select_content_runs(runs, count)
    if len(selected_runs) != count:
        return None

    gap_hints = _content_gap_hints_from_runs(selected_runs, region)
    if len(gap_hints) != count - 1:
        return None

    return SeparatorGapHintSet(
        hints=gap_hints,
        max_offset_ratio=float(guidance_policy.max_hint_offset_ratio),
        max_offset_min=int(guidance_policy.max_hint_offset_min),
        max_offset_max=int(guidance_policy.max_hint_offset_max),
        provenance=MeasurementProvenance(
            root_measurement="content_guidance",
            source="content_runs",
            dependencies=("content_evidence",),
        ),
    )
