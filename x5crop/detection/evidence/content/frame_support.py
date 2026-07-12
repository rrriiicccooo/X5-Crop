from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from ....cache import MeasurementCache
from ....cache.content_statistics import ContentColumnStatistics
from ....domain import Box
from ....geometry.boxes import box_cache_key
from ....configuration.content import ContentEvidenceParameters
from ....configuration.content import ContentConfiguration
from ....image.evidence import adaptive_activation_threshold
from x5crop.domain import EvidenceState

if TYPE_CHECKING:
    from ...physical.model import SequenceSolution


CACHED_CONTENT_SIGNAL_COMPOSITE = (
    "cached_gradient+neighbor_texture+local_contrast+tonal_presence"
)


def content_evidence_threshold(
    evidence_float: np.ndarray,
    parameters: ContentEvidenceParameters,
) -> float | None:
    return adaptive_activation_threshold(
        evidence_float,
        parameters.activation_percentile,
        parameters.minimum_evidence_range,
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
    state: EvidenceState
    reason: str
    threshold: float | None
    median_mean: float | None
    median_coverage: float | None
    observations: tuple[FrameContentObservation, ...]
    composite: str

    @property
    def support_available(self) -> bool:
        return self.state == EvidenceState.SUPPORTED

    @property
    def boundary_contact_frame_indexes(self) -> tuple[int, ...]:
        return tuple(
            observation.index
            for observation in self.observations
            if observation.boundary_contact_sides
        )

def _cached_content_evidence_threshold(
    cache: MeasurementCache,
    evidence: np.ndarray,
    sequence_box: Box,
    parameters: ContentEvidenceParameters,
) -> float | None:
    key = (parameters, *box_cache_key(sequence_box))
    threshold = cache.content_evidence_thresholds.get(key)
    if threshold is None:
        threshold = content_evidence_threshold(evidence, parameters)
        cache.content_evidence_thresholds[key] = threshold
    return threshold


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
        if sample.size
        and int(np.count_nonzero(sample >= threshold))
        >= min(int(parameters.minimum_active_pixels), int(sample.size))
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
            EvidenceState.UNAVAILABLE,
            "invalid_visible_sequence_span",
            None,
            None,
            None,
            (),
            CACHED_CONTENT_SIGNAL_COMPOSITE,
        )
    evidence = cache.content_evidence_float_work[
        sequence_box.top : sequence_box.bottom,
        sequence_box.left : sequence_box.right,
    ]
    if not evidence.size:
        return FrameContentEvidence(
            EvidenceState.UNAVAILABLE,
            "empty_visible_sequence_span",
            None,
            None,
            None,
            (),
            CACHED_CONTENT_SIGNAL_COMPOSITE,
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
            EvidenceState.UNAVAILABLE,
            "content_evidence_has_no_dynamic_range",
            None,
            None,
            None,
            (),
            CACHED_CONTENT_SIGNAL_COMPOSITE,
        )
    statistics_key = (parameters, *box_cache_key(sequence_box), float(threshold))
    statistics = cache.content_column_statistics.get(statistics_key)
    if statistics is None:
        statistics = ContentColumnStatistics.from_evidence(evidence, threshold)
        cache.content_column_statistics[statistics_key] = statistics

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
        content_present = bool(
            int(np.count_nonzero(crop >= threshold))
            >= min(int(parameters.minimum_active_pixels), int(crop.size))
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

    if not observations:
        state = EvidenceState.UNAVAILABLE
        reason = "no_valid_frames"
        median_mean = None
        median_coverage = None
    else:
        median_mean = float(
            np.median(np.asarray([item.mean for item in observations]))
        )
        median_coverage = float(
            np.median(np.asarray([item.coverage for item in observations]))
        )
        if any(item.content_present for item in observations):
            state = EvidenceState.SUPPORTED
            reason = "content_observed"
        else:
            state = EvidenceState.UNAVAILABLE
            reason = "content_not_observed"
    return FrameContentEvidence(
        state=state,
        reason=reason,
        threshold=float(threshold),
        median_mean=median_mean,
        median_coverage=median_coverage,
        observations=tuple(observations),
        composite=CACHED_CONTENT_SIGNAL_COMPOSITE,
    )
