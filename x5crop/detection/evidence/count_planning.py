from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...cache.outer import cached_base_outer_candidates
from ...cache.separator import cached_separator_profile, cached_separator_width_profile
from ...domain import Box
from ...formats import FormatPhysicalSpec
from ...geometry.detection_parameters import (
    GapSearchParameters,
    OuterBoxDetectionParameters,
    SeparatorProfileParameters,
    SeparatorWidthProfileSearchParameters,
)
from ...geometry.separator_band import SeparatorBand
from ...geometry.separator_width_profile import collect_separator_width_bands
from ...policies.parameters.outer import SeparatorOuterBandParameters
from ..physical.outer.base import base_outer_candidates
from ..physical.outer.separator_bands import collect_separator_outer_bands


@dataclass(frozen=True)
class CountPlanningEvidence:
    supported_count: int | None
    source_outer: Box | None
    hard_bands: tuple[SeparatorBand, ...]
    placement_offsets: tuple[tuple[int, tuple[float, ...]], ...]
    detail: dict[str, Any]

    @classmethod
    def unavailable(cls) -> "CountPlanningEvidence":
        return cls(None, None, (), (), {"used": False, "reason": "unavailable"})

    @property
    def hard_separator_count(self) -> int:
        return len(self.hard_bands)

    @property
    def observed_separator_centers(self) -> tuple[float, ...]:
        return tuple(float(band.center) for band in self.hard_bands)

    def offsets_for_count(self, count: int) -> tuple[float, ...]:
        return next(
            (offsets for candidate_count, offsets in self.placement_offsets if candidate_count == count),
            (),
        )

    def report_detail(self) -> dict[str, Any]:
        return {
            "supported_count": self.supported_count,
            "hard_separator_count": int(self.hard_separator_count),
            "observed_separator_centers": [
                float(center) for center in self.observed_separator_centers
            ],
            "placement_offsets": {
                str(count): [float(offset) for offset in offsets]
                for count, offsets in self.placement_offsets
            },
            **self.detail,
        }


@dataclass(frozen=True)
class CountPlacementEvidence:
    count: int
    offsets: tuple[float, ...]
    source: str
    detail: dict[str, Any]


def _merged_separator_bands(
    hard_bands: list[SeparatorBand],
    width_bands: list[SeparatorBand],
) -> list[SeparatorBand]:
    merged: list[SeparatorBand] = []
    ordered = [
        *sorted(hard_bands, key=lambda band: float(band.score), reverse=True),
        *sorted(width_bands, key=lambda band: float(band.score), reverse=True),
    ]
    for band in ordered:
        if any(
            min(float(existing.end), float(band.end))
            > max(float(existing.start), float(band.start))
            or abs(float(existing.center) - float(band.center))
            <= max(float(existing.width), float(band.width)) * 0.5
            for existing in merged
        ):
            continue
        merged.append(band)
    return sorted(merged, key=lambda item: item.center)


def _placement_offsets(
    bands: list[SeparatorBand],
    outer_width: float,
    default_count: int,
    allowed_counts: tuple[int, ...],
) -> tuple[tuple[int, tuple[float, ...]], ...]:
    pitch = float(outer_width) / float(max(1, default_count))
    placements: list[tuple[int, tuple[float, ...]]] = []
    for count in allowed_counts:
        if count >= default_count or count <= 1:
            continue
        expected_gaps = count - 1
        max_origin = float(outer_width) - pitch * float(count)
        if max_origin <= 0.0 or len(bands) < expected_gaps:
            continue
        offsets: list[float] = []
        for start in range(len(bands) - expected_gaps + 1):
            window = bands[start : start + expected_gaps]
            origins = [
                float(band.center) - pitch * float(index)
                for index, band in enumerate(window, start=1)
            ]
            origin = float(np.median(np.asarray(origins, dtype=np.float32)))
            if origin < 0.0 or origin > max_origin:
                continue
            offset = round(origin / max_origin, 4)
            if offset not in offsets:
                offsets.append(offset)
        if offsets:
            placements.append((int(count), tuple(offsets)))
    return tuple(placements)


def count_planning_evidence(
    gray_work: np.ndarray,
    fmt: FormatPhysicalSpec,
    cache: AnalysisCache,
    *,
    outer_parameters: OuterBoxDetectionParameters,
    separator_profile_parameters: SeparatorProfileParameters,
    gap_search_parameters: GapSearchParameters,
    separator_band_parameters: SeparatorOuterBandParameters,
) -> CountPlanningEvidence:
    base_candidates = cached_base_outer_candidates(
        cache,
        outer_parameters,
        lambda: base_outer_candidates(gray_work, outer_parameters),
    )
    valid_candidates = [candidate for candidate in base_candidates if candidate.box.valid()]
    if not valid_candidates:
        return CountPlanningEvidence.unavailable()
    source = max(
        valid_candidates,
        key=lambda candidate: candidate.box.width * candidate.box.height,
    )
    outer = source.box
    profile = cached_separator_profile(
        cache,
        gray_work,
        outer,
        separator_profile_parameters,
    )
    hard_collection = collect_separator_outer_bands(
        profile,
        float(outer.height),
        float(outer.width),
        separator_band_parameters,
        gap_search_parameters,
    )
    hard_bands = _merged_separator_bands(list(hard_collection.bands), [])
    inferred_count = len(hard_bands) + 1 if hard_bands else None
    supported_count = (
        int(inferred_count)
        if inferred_count is not None and inferred_count in fmt.allowed_counts
        else None
    )
    return CountPlanningEvidence(
        supported_count=supported_count,
        source_outer=outer,
        hard_bands=tuple(hard_bands),
        placement_offsets=_placement_offsets(
            hard_bands,
            float(outer.width),
            int(fmt.default_count),
            tuple(int(count) for count in fmt.allowed_counts),
        ),
        detail={
            "used": True,
            "source": "hard_separator_bands",
            "source_outer": {
                "left": int(outer.left),
                "top": int(outer.top),
                "right": int(outer.right),
                "bottom": int(outer.bottom),
            },
            "hard_separator_centers": [float(band.center) for band in hard_bands],
            "placement_evidence_stage": "hard_separator_only",
        },
    )


def supplemental_count_placement_evidence(
    gray_work: np.ndarray,
    fmt: FormatPhysicalSpec,
    count: int,
    cache: AnalysisCache,
    planning_evidence: CountPlanningEvidence,
    *,
    width_profile_parameters: SeparatorWidthProfileSearchParameters,
) -> CountPlacementEvidence:
    outer = planning_evidence.source_outer
    if outer is None or not outer.valid() or count <= 1:
        return CountPlacementEvidence(
            int(count),
            (),
            "unavailable",
            {"used": False, "reason": "missing_outer_or_nonseparable_count"},
        )
    width_profile = cached_separator_width_profile(
        cache,
        gray_work,
        outer,
        width_profile_parameters,
    )
    width_collection = collect_separator_width_bands(
        width_profile,
        float(outer.height),
        float(outer.width),
        width_profile_parameters,
    )
    observed_bands = _merged_separator_bands(
        list(planning_evidence.hard_bands),
        list(width_collection.bands),
    )
    placements = _placement_offsets(
        observed_bands,
        float(outer.width),
        int(fmt.default_count),
        (int(count),),
    )
    offsets = next(
        (
            values
            for candidate_count, values in placements
            if candidate_count == count
        ),
        (),
    )
    return CountPlacementEvidence(
        int(count),
        offsets,
        "observed_separator_width",
        {
            "used": bool(offsets),
            "role": "placement_guidance_only",
            "width_measurement_band_count": int(len(width_collection.bands)),
        },
    )
