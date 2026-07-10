from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...cache.outer import cached_base_outer_candidates
from ...cache.separator import cached_separator_profile, cached_separator_width_profile
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
    hard_separator_count: int
    observed_separator_centers: tuple[float, ...]
    placement_offsets: tuple[tuple[int, tuple[float, ...]], ...]
    detail: dict[str, Any]

    @classmethod
    def unavailable(cls) -> "CountPlanningEvidence":
        return cls(None, 0, (), (), {"used": False, "reason": "unavailable"})

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


def _merged_separator_bands(
    hard_bands: list[SeparatorBand],
    width_bands: list[SeparatorBand],
) -> list[SeparatorBand]:
    merged = sorted(hard_bands, key=lambda band: band.center)
    for band in sorted(width_bands, key=lambda item: item.center):
        if any(
            abs(float(existing.center) - float(band.center))
            <= max(float(existing.width), float(band.width)) * 0.5
            for existing in merged
        ):
            continue
        merged.append(band)
        merged.sort(key=lambda item: item.center)
    return merged


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
    width_profile_parameters: SeparatorWidthProfileSearchParameters,
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
    hard_bands = sorted(hard_collection.bands, key=lambda band: band.center)
    observed_bands = _merged_separator_bands(hard_bands, list(width_collection.bands))
    inferred_count = len(hard_bands) + 1 if hard_bands else None
    supported_count = (
        int(inferred_count)
        if inferred_count is not None and inferred_count in fmt.allowed_counts
        else None
    )
    return CountPlanningEvidence(
        supported_count=supported_count,
        hard_separator_count=len(hard_bands),
        observed_separator_centers=tuple(float(band.center) for band in observed_bands),
        placement_offsets=_placement_offsets(
            observed_bands,
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
            "width_measurement_band_count": int(len(width_collection.bands)),
        },
    )
