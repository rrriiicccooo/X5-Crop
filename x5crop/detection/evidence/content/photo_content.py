from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import TYPE_CHECKING

import numpy as np

from ....cache import (
    MeasurementCache,
    ThresholdedMeasurementRegionKey,
)
from ....cache.content_statistics import ContentColumnStatistics
from ....configuration.content import ContentConfiguration, ContentEvidenceParameters
from ....domain import BoundarySide, Box, EvidenceState
from ....image.evidence import activation_mask
from ....utils import runs_from_mask
from .activation import cached_content_evidence_threshold, sample_supports_content

if TYPE_CHECKING:
    from ...physical.model import PhotoSequenceSolution


@dataclass(frozen=True)
class PhotoBoundaryContentTrace:
    side: BoundarySide
    boundary_parallel_runs: tuple[tuple[int, int], ...]
    minimum_crossing_tracks: int

    def __post_init__(self) -> None:
        if not isinstance(self.side, BoundarySide):
            raise TypeError("photo boundary content trace requires a typed side")
        if self.side not in {BoundarySide.LEADING, BoundarySide.TRAILING}:
            raise ValueError("photo content traces only describe inter-photo edges")
        if not self.boundary_parallel_runs:
            raise ValueError("photo boundary content trace requires measured runs")
        if self.minimum_crossing_tracks <= 0:
            raise ValueError("photo boundary content trace requires positive support")
        previous_end: int | None = None
        for start, end in self.boundary_parallel_runs:
            if start < 0 or end <= start:
                raise ValueError("photo boundary content runs require positive extent")
            if previous_end is not None and start < previous_end:
                raise ValueError("photo boundary content runs must be ordered")
            previous_end = end


@dataclass(frozen=True)
class PhotoContentObservation:
    photo_index: int
    mean: float
    coverage: float
    content_present: bool
    boundary_traces: tuple[PhotoBoundaryContentTrace, ...]

    def __post_init__(self) -> None:
        if self.photo_index <= 0:
            raise ValueError("photo content observation requires a photo index")
        sides = tuple(trace.side for trace in self.boundary_traces)
        if len(sides) != len(set(sides)):
            raise ValueError("photo content observation requires unique boundary traces")


@dataclass(frozen=True)
class PhotoContentEvidence:
    threshold: float | None
    observations: tuple[PhotoContentObservation, ...]
    unavailable_reason: str | None = None
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)
    median_mean: float | None = field(init=False)
    median_coverage: float | None = field(init=False)

    def __post_init__(self) -> None:
        if self.observations:
            if self.threshold is None or self.unavailable_reason is not None:
                raise ValueError(
                    "photo content observations require a threshold without an unavailable reason"
                )
            state = (
                EvidenceState.SUPPORTED
                if any(item.content_present for item in self.observations)
                else EvidenceState.UNAVAILABLE
            )
            reason = (
                "content_observed"
                if state == EvidenceState.SUPPORTED
                else "content_not_observed"
            )
            median_mean = float(
                np.median(np.asarray([item.mean for item in self.observations]))
            )
            median_coverage = float(
                np.median(
                    np.asarray([item.coverage for item in self.observations])
                )
            )
        else:
            if not self.unavailable_reason:
                raise ValueError(
                    "photo content without observations requires an unavailable reason"
                )
            state = EvidenceState.UNAVAILABLE
            reason = self.unavailable_reason
            median_mean = None
            median_coverage = None
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "median_mean", median_mean)
        object.__setattr__(self, "median_coverage", median_coverage)

    @property
    def support_available(self) -> bool:
        return self.state == EvidenceState.SUPPORTED


def _boundary_content_traces(
    crop: np.ndarray,
    cross_axis_offset: int,
    threshold: float,
    parameters: ContentEvidenceParameters,
) -> tuple[PhotoBoundaryContentTrace, ...]:
    band = max(
        int(parameters.boundary_band_min_px),
        int(round(min(crop.shape) * float(parameters.boundary_band_ratio))),
    )
    band_x = min(crop.shape[1], band)
    samples = {
        BoundarySide.LEADING: (crop[:, :band_x], cross_axis_offset),
        BoundarySide.TRAILING: (
            crop[:, crop.shape[1] - band_x :],
            cross_axis_offset,
        ),
    }
    minimum_tracks = max(
        1,
        int(math.ceil(math.sqrt(parameters.minimum_active_pixels))),
    )
    traces: list[PhotoBoundaryContentTrace] = []
    for side, (sample, coordinate_offset) in samples.items():
        if not sample_supports_content(
            sample,
            threshold,
            parameters.minimum_active_pixels,
        ):
            continue
        active = activation_mask(sample, threshold)
        normal_extent = active.shape[1]
        minimum_normal_support = min(normal_extent, minimum_tracks)
        parallel_support = (
            np.count_nonzero(active, axis=1) >= minimum_normal_support
        )
        runs = tuple(
            (coordinate_offset + start, coordinate_offset + end)
            for start, end in runs_from_mask(parallel_support)
            if end - start >= minimum_tracks
        )
        if runs:
            traces.append(
                PhotoBoundaryContentTrace(
                    side,
                    runs,
                    minimum_tracks,
                )
            )
    return tuple(traces)


def photo_content_evidence(
    geometry: PhotoSequenceSolution,
    cache: MeasurementCache,
    configuration: ContentConfiguration,
) -> PhotoContentEvidence:
    if cache.layout != geometry.layout:
        raise ValueError("content evidence requires matching analysis cache")
    aperture_union_box = geometry.photo_sequence_envelope.clamp(
        cache.gray_work.shape[1],
        cache.gray_work.shape[0],
    )
    if not aperture_union_box.valid():
        return PhotoContentEvidence(
            None,
            (),
            "invalid_photo_aperture_union",
        )
    evidence = cache.content_evidence_float_work[
        aperture_union_box.top : aperture_union_box.bottom,
        aperture_union_box.left : aperture_union_box.right,
    ]
    if not evidence.size:
        return PhotoContentEvidence(
            None,
            (),
            "empty_photo_aperture_union",
        )
    parameters = configuration.evidence
    threshold = cached_content_evidence_threshold(
        cache,
        aperture_union_box,
        parameters,
    )
    if threshold is None:
        return PhotoContentEvidence(
            None,
            (),
            "content_evidence_has_no_dynamic_range",
        )
    statistics_key = ThresholdedMeasurementRegionKey(
        parameters,
        aperture_union_box,
        float(threshold),
    )
    found = statistics_key in cache.content_column_statistics
    cache.lookup_statistics.record_lookup(found=found)
    if not found:
        cache.content_column_statistics[statistics_key] = (
            ContentColumnStatistics.from_evidence(evidence, threshold)
        )
    statistics = cache.content_column_statistics[statistics_key]

    observations: list[PhotoContentObservation] = []
    for envelope in geometry.frame_crop_envelopes:
        index = envelope.photo_index
        absolute = envelope.box.clamp(
            cache.gray_work.shape[1],
            cache.gray_work.shape[0],
        )
        relative = Box(
            max(0, absolute.left - aperture_union_box.left),
            max(0, absolute.top - aperture_union_box.top),
            min(aperture_union_box.width, absolute.right - aperture_union_box.left),
            min(aperture_union_box.height, absolute.bottom - aperture_union_box.top),
        )
        if not relative.valid():
            continue
        crop = evidence[
            relative.top : relative.bottom,
            relative.left : relative.right,
        ]
        if not crop.size:
            continue
        if relative.top == 0 and relative.bottom == aperture_union_box.height:
            mean, coverage = statistics.interval(relative.left, relative.right)
        else:
            mean = float(crop.mean())
            coverage = float((crop >= threshold).mean())
        content_present = sample_supports_content(
            crop,
            threshold,
            parameters.minimum_active_pixels,
        )
        observations.append(
            PhotoContentObservation(
                photo_index=index,
                mean=float(mean),
                coverage=float(coverage),
                content_present=content_present,
                boundary_traces=_boundary_content_traces(
                    crop,
                    absolute.top,
                    threshold,
                    parameters,
                ),
            )
        )

    return PhotoContentEvidence(
        threshold=float(threshold),
        observations=tuple(observations),
        unavailable_reason=None if observations else "no_valid_photo_apertures",
    )
