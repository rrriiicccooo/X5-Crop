from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from ....cache import (
    MeasurementCache,
    MeasurementRegionKey,
    ThresholdedMeasurementRegionKey,
)
from ....cache.content_statistics import ContentColumnStatistics
from ....domain import Box
from ....configuration.content import ContentEvidenceParameters
from ....configuration.content import ContentConfiguration
from ....image.evidence import adaptive_activation_threshold
from x5crop.domain import EvidenceState

if TYPE_CHECKING:
    from ...physical.model import SequenceSolution


def content_evidence_threshold(
    evidence_float: np.ndarray,
    parameters: ContentEvidenceParameters,
) -> float | None:
    return adaptive_activation_threshold(
        evidence_float,
        parameters.activation_percentile,
        parameters.minimum_evidence_range,
        parameters.maximum_percentile_samples,
    )


@dataclass(frozen=True)
class FrameContentObservation:
    index: int
    mean: float
    coverage: float
    content_present: bool
    boundary_contact_sides: tuple[str, ...]


@dataclass(frozen=True)
class FrameContentEvidence:
    threshold: float | None
    observations: tuple[FrameContentObservation, ...]
    unavailable_reason: str | None = None
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)
    median_mean: float | None = field(init=False)
    median_coverage: float | None = field(init=False)

    def __post_init__(self) -> None:
        if self.observations:
            if self.threshold is None or self.unavailable_reason is not None:
                raise ValueError(
                    "frame content observations require a threshold without an unavailable reason"
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
                    "frame content without observations requires an unavailable reason"
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


def _cached_content_evidence_threshold(
    cache: MeasurementCache,
    evidence: np.ndarray,
    sequence_box: Box,
    parameters: ContentEvidenceParameters,
) -> float | None:
    key = MeasurementRegionKey(parameters, sequence_box)
    found = key in cache.content_evidence_thresholds
    cache.lookup_statistics.record_lookup(found=found)
    if not found:
        cache.content_evidence_thresholds[key] = content_evidence_threshold(
            evidence,
            parameters,
        )
    return cache.content_evidence_thresholds[key]


def _boundary_contact_sides(
    crop: np.ndarray,
    threshold: float,
    parameters: ContentEvidenceParameters,
) -> tuple[str, ...]:
    band = max(
        int(parameters.boundary_band_min_px),
        int(round(min(crop.shape) * float(parameters.boundary_band_ratio))),
    )
    band_y = min(crop.shape[0], band)
    band_x = min(crop.shape[1], band)
    samples = {
        "left": crop[:, :band_x],
        "right": crop[:, crop.shape[1] - band_x :],
        "top": crop[:band_y, :],
        "bottom": crop[crop.shape[0] - band_y :, :],
    }
    return tuple(
        side
        for side, sample in samples.items()
        if _sample_supports_content(
            sample,
            threshold,
            parameters.minimum_active_pixels,
        )
    )


def _sample_supports_content(
    sample: np.ndarray,
    threshold: float,
    minimum_active_pixels: int,
) -> bool:
    required = int(minimum_active_pixels)
    return bool(
        sample.size >= required
        and int(np.count_nonzero(sample >= threshold)) >= required
    )


def frame_content_evidence(
    geometry: SequenceSolution,
    cache: MeasurementCache,
    configuration: ContentConfiguration,
) -> FrameContentEvidence:
    if cache.layout != geometry.layout:
        raise ValueError("content evidence requires matching analysis cache")
    sequence_box = geometry.visible_sequence_span.box.clamp(
        cache.gray_work.shape[1],
        cache.gray_work.shape[0],
    )
    if not sequence_box.valid():
        return FrameContentEvidence(
            None,
            (),
            "invalid_visible_sequence_span",
        )
    evidence = cache.content_evidence_float_work[
        sequence_box.top : sequence_box.bottom,
        sequence_box.left : sequence_box.right,
    ]
    if not evidence.size:
        return FrameContentEvidence(
            None,
            (),
            "empty_visible_sequence_span",
        )
    parameters = configuration.evidence
    threshold = _cached_content_evidence_threshold(
        cache,
        evidence,
        sequence_box,
        parameters,
    )
    if threshold is None:
        return FrameContentEvidence(
            None,
            (),
            "content_evidence_has_no_dynamic_range",
        )
    statistics_key = ThresholdedMeasurementRegionKey(
        parameters,
        sequence_box,
        float(threshold),
    )
    found = statistics_key in cache.content_column_statistics
    cache.lookup_statistics.record_lookup(found=found)
    if not found:
        cache.content_column_statistics[statistics_key] = (
            ContentColumnStatistics.from_evidence(evidence, threshold)
        )
    statistics = cache.content_column_statistics[statistics_key]

    observations: list[FrameContentObservation] = []
    for index, frame in enumerate(geometry.frames, start=1):
        absolute = frame.clamp(
            cache.gray_work.shape[1],
            cache.gray_work.shape[0],
        )
        relative = Box(
            max(0, absolute.left - sequence_box.left),
            max(0, absolute.top - sequence_box.top),
            min(sequence_box.width, absolute.right - sequence_box.left),
            min(sequence_box.height, absolute.bottom - sequence_box.top),
        )
        if not relative.valid():
            continue
        crop = evidence[
            relative.top : relative.bottom,
            relative.left : relative.right,
        ]
        if not crop.size:
            continue
        if relative.top == 0 and relative.bottom == sequence_box.height:
            mean, coverage = statistics.interval(relative.left, relative.right)
        else:
            mean = float(crop.mean())
            coverage = float((crop >= threshold).mean())
        content_present = _sample_supports_content(
            crop,
            threshold,
            parameters.minimum_active_pixels,
        )
        observations.append(
            FrameContentObservation(
                index=index,
                mean=float(mean),
                coverage=float(coverage),
                content_present=content_present,
                boundary_contact_sides=_boundary_contact_sides(
                    crop,
                    threshold,
                    parameters,
                ),
            )
        )

    return FrameContentEvidence(
        threshold=float(threshold),
        observations=tuple(observations),
        unavailable_reason=None if observations else "no_valid_frames",
    )
