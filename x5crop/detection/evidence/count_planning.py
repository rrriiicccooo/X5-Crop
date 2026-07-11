from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from ...cache import MeasurementCache
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
from ...units import ScanCalibration
from ..physical.outer.base import base_outer_candidates
from ..physical.outer.separator_bands import collect_separator_outer_bands


@dataclass(frozen=True)
class CountPlanningEvidence:
    source_outer: Box | None
    observed_bands: tuple[SeparatorBand, ...]
    placement_offsets: tuple[tuple[int, tuple[float, ...]], ...]

    @classmethod
    def unavailable(cls) -> "CountPlanningEvidence":
        return cls(None, (), ())

    def offsets_for_count(self, count: int) -> tuple[float, ...]:
        return next(
            (offsets for candidate_count, offsets in self.placement_offsets if candidate_count == count),
            (),
        )

@dataclass(frozen=True)
class CountPlacementEvidence:
    offsets: tuple[float, ...]
    source: str


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
    frame_width: float,
    allowed_counts: tuple[int, ...],
) -> tuple[tuple[int, tuple[float, ...]], ...]:
    if outer_width <= 0.0 or frame_width <= 0.0:
        return ()
    placements: list[tuple[int, tuple[float, ...]]] = []
    for count in allowed_counts:
        if count <= 1:
            continue
        expected_gaps = count - 1
        if len(bands) < expected_gaps:
            continue
        offsets: list[float] = []
        for start in range(len(bands) - expected_gaps + 1):
            window = bands[start : start + expected_gaps]
            film_start = float(window[0].start) - float(frame_width)
            film_end = float(window[-1].end) + float(frame_width)
            film_span = film_end - film_start
            available = float(outer_width) - film_span
            if (
                film_start < 0.0
                or film_end > float(outer_width)
                or available < 0.0
            ):
                continue
            offset = 0.0 if available == 0.0 else round(film_start / available, 4)
            if offset not in offsets:
                offsets.append(offset)
        if offsets:
            placements.append((int(count), tuple(offsets)))
    return tuple(placements)


def count_planning_evidence(
    gray_work: np.ndarray,
    fmt: FormatPhysicalSpec,
    cache: MeasurementCache,
    *,
    outer_parameters: OuterBoxDetectionParameters,
    separator_profile_parameters: SeparatorProfileParameters,
    gap_search_parameters: GapSearchParameters,
    separator_band_parameters: SeparatorOuterBandParameters,
    calibration: ScanCalibration,
    long_axis: str,
) -> CountPlanningEvidence:
    base_candidates = base_outer_candidates(gray_work, outer_parameters)
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
        outer,
        separator_profile_parameters,
    )
    hard_collection = collect_separator_outer_bands(
        profile,
        float(outer.height),
        float(outer.width),
        separator_band_parameters,
        gap_search_parameters,
        calibration,
        long_axis,
    )
    hard_bands = _merged_separator_bands(list(hard_collection.bands), [])
    return CountPlanningEvidence(
        source_outer=outer,
        observed_bands=tuple(hard_bands),
        placement_offsets=_placement_offsets(
            hard_bands,
            float(outer.width),
            float(outer.height) * float(fmt.horizontal_content_aspect),
            tuple(int(count) for count in fmt.allowed_counts),
        ),
    )


def supplemental_count_placement_evidence(
    fmt: FormatPhysicalSpec,
    count: int,
    cache: MeasurementCache,
    planning_evidence: CountPlanningEvidence,
    *,
    width_profile_parameters: SeparatorWidthProfileSearchParameters,
    calibration: ScanCalibration,
    long_axis: str,
) -> CountPlacementEvidence:
    outer = planning_evidence.source_outer
    if outer is None or not outer.valid() or count <= 1:
        return CountPlacementEvidence(
            (),
            "unavailable",
        )
    width_profile = cached_separator_width_profile(
        cache,
        outer,
        width_profile_parameters,
    )
    width_collection = collect_separator_width_bands(
        width_profile,
        float(outer.height),
        float(outer.width),
        width_profile_parameters,
        calibration,
        long_axis,
    )
    observed_bands = _merged_separator_bands(
        list(planning_evidence.observed_bands),
        list(width_collection.bands),
    )
    placements = _placement_offsets(
        observed_bands,
        float(outer.width),
        float(outer.height) * float(fmt.horizontal_content_aspect),
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
        offsets,
        "observed_separator_width",
    )
