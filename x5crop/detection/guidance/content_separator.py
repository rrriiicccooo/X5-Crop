from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

import numpy as np

from ...cache import AnalysisCache
from ...domain import Box
from ...formats import FormatPhysicalSpec
from ...geometry.layout import work_gray
from ...policies.runtime.candidate import ContentGuidedSeparatorCandidatePolicy
from ...policies.runtime.content import ContentPolicy
from ...run_config import RunConfig
from ..evidence.content.regions import (
    CONTENT_BBOX_HINT_ROLE,
    CONTENT_RUN_HINT_ROLE,
    content_mask_region_detail,
    content_region_runs,
    select_content_runs,
)
from .content_model import (
    content_candidate_outer_from_mask,
    content_candidate_raw_frame_boxes,
    content_signal_arrays_for_candidate,
)
from ..physical.separator.hints import SeparatorGapHint, SeparatorGapHintSet


CONTENT_GUIDED_SEPARATOR_FAMILY = "content_guided_separator"
CONTENT_GUIDED_SEPARATOR_ROLE = "content_guided_separator_search"
CONTENT_REGION_HINT_SOURCE = "content_region_hints"


@dataclass(frozen=True)
class ContentGuidedSeparatorSeed:
    outer: Box
    gap_hints: SeparatorGapHintSet
    detail: dict[str, Any]


@dataclass(frozen=True)
class ContentGuidedSeparatorSeedResult:
    seed: Optional[ContentGuidedSeparatorSeed]
    detail: dict[str, Any]


def _skip_detail(reason: str, **extra: Any) -> ContentGuidedSeparatorSeedResult:
    return ContentGuidedSeparatorSeedResult(
        seed=None,
        detail={
            "used": False,
            "proposal_family": CONTENT_GUIDED_SEPARATOR_FAMILY,
            "reason": reason,
            **extra,
        },
    )


def _content_gap_hints_from_runs(
    selected_runs: list[tuple[int, int]],
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
                center=center,
                source_start=float(left_run[1] - outer.left),
                source_end=float(right_run[0] - outer.left),
            )
        )
    return tuple(hints)


def content_guided_separator_seed_for_count(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float,
    cache: Optional[AnalysisCache],
    content_policy: ContentPolicy,
    guidance_policy: ContentGuidedSeparatorCandidatePolicy,
) -> ContentGuidedSeparatorSeedResult:
    if count <= 1:
        return _skip_detail("count_has_no_internal_separators", count=int(count))
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    evidence, evidence_float, signal_source = content_signal_arrays_for_candidate(
        gray_work,
        cache,
        config.layout,
        content_policy,
    )
    mask_detail = content_mask_region_detail(
        evidence_float,
        gray_work.shape,
        fmt,
        cache,
        content_policy=content_policy,
    )
    outer = content_candidate_outer_from_mask(mask_detail, gray_work.shape, content_policy.mask)
    if outer is None:
        return _skip_detail(
            "no_content_outer",
            signal_source=signal_source,
            mask_detail=mask_detail,
        )

    expected_aspect = float(fmt.horizontal_content_aspect)
    if expected_aspect <= 0:
        return _skip_detail(
            "missing_expected_content_aspect",
            format_id=fmt.format_id,
        )

    runs, run_detail = content_region_runs(
        evidence,
        outer,
        count,
        fmt.format_id,
        cache,
        content_policy=content_policy,
    )
    selected_runs = select_content_runs(runs, count)
    if len(selected_runs) != count:
        return _skip_detail(
            "content_run_count_not_exact",
            signal_source=signal_source,
            outer=asdict(outer),
            selected_run_count=len(selected_runs),
            required_count=int(count),
            run_detail=run_detail,
        )

    frame_h = max(1.0, float(outer.height))
    expected_w = max(content_policy.candidate.expected_width_min_px, frame_h * expected_aspect)
    raw_boxes, placement = content_candidate_raw_frame_boxes(
        outer,
        selected_runs,
        count=count,
        default_count=fmt.default_count,
        strip_mode=strip_mode,
        offset_fraction=offset_fraction,
        expected_width=expected_w,
        work_shape=gray_work.shape,
    )
    raw_boxes = [box for box in raw_boxes if box.valid()]
    if len(raw_boxes) != count:
        return _skip_detail(
            "content_frame_hint_count_mismatch",
            signal_source=signal_source,
            outer=asdict(outer),
            selected_run_count=len(selected_runs),
            raw_box_count=len(raw_boxes),
            required_count=int(count),
            placement=placement,
        )

    gap_hints = _content_gap_hints_from_runs(selected_runs, outer)
    if len(gap_hints) != count - 1:
        return _skip_detail(
            "content_gap_hint_count_mismatch",
            signal_source=signal_source,
            outer=asdict(outer),
            hint_count=len(gap_hints),
            expected_gap_count=int(count - 1),
        )

    hint_set = SeparatorGapHintSet(
        source=CONTENT_REGION_HINT_SOURCE,
        role=CONTENT_GUIDED_SEPARATOR_ROLE,
        hints=gap_hints,
        max_offset_ratio=float(guidance_policy.max_hint_offset_ratio),
        max_offset_min=int(guidance_policy.max_hint_offset_min),
        max_offset_max=int(guidance_policy.max_hint_offset_max),
        detail={
            "proposal_family": CONTENT_GUIDED_SEPARATOR_FAMILY,
            "region_roles": {
                "bbox": CONTENT_BBOX_HINT_ROLE,
                "runs": CONTENT_RUN_HINT_ROLE,
            },
        },
    )
    detail = {
        "used": True,
        "proposal_family": CONTENT_GUIDED_SEPARATOR_FAMILY,
        "proposal_role": CONTENT_GUIDED_SEPARATOR_ROLE,
        "evidence_contract": "separator_evidence_required",
        "signal_source": signal_source,
        "outer": asdict(outer),
        "expected_frame_aspect": expected_aspect,
        "expected_frame_width": expected_w,
        "placement": placement,
        "mask_threshold": mask_detail.get("mask_threshold"),
        "mask_percentiles": mask_detail.get("mask_percentiles", {}),
        "selected_run_count": len(selected_runs),
        "required_count": int(count),
        "raw_boxes": [asdict(box) for box in raw_boxes],
        "run_detail": run_detail,
        "gap_hints": hint_set.summary(),
    }
    return ContentGuidedSeparatorSeedResult(
        seed=ContentGuidedSeparatorSeed(outer=outer, gap_hints=hint_set, detail=detail),
        detail=detail,
    )
