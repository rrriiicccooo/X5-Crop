from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ....cache import MeasurementCache
from ....domain import Box
from ....policies.parameters.content import ContentEvidenceParameters
from ...geometry import CandidateGeometry
from ..state import EvidenceState
from .frame_support import FrameContentEvidence


@dataclass(frozen=True)
class HolderTextureRegion:
    name: str
    box: Box
    mean: float
    coverage: float
    texture: float

@dataclass(frozen=True)
class HolderTextureEvidence:
    state: EvidenceState
    reason: str
    regions: tuple[HolderTextureRegion, ...]
    content_holder_mean_contrast: float | None
    content_holder_coverage_contrast: float | None

def holder_texture_evidence(
    geometry: CandidateGeometry,
    cache: MeasurementCache,
    frame_content: FrameContentEvidence,
    parameters: ContentEvidenceParameters,
) -> HolderTextureEvidence:
    if cache.layout != geometry.layout or frame_content.threshold is None:
        return HolderTextureEvidence(
            EvidenceState.UNAVAILABLE,
            "content_measurement_unavailable",
            (),
            None,
            None,
        )
    holder = geometry.holder_span.box.clamp(
        cache.gray_work.shape[1],
        cache.gray_work.shape[0],
    )
    film = geometry.film_span.box.clamp(
        cache.gray_work.shape[1],
        cache.gray_work.shape[0],
    )
    boxes = (
        ("leading_holder_slack", Box(holder.left, holder.top, film.left, holder.bottom)),
        ("trailing_holder_slack", Box(film.right, holder.top, holder.right, holder.bottom)),
    )
    regions: list[HolderTextureRegion] = []
    for name, box in boxes:
        if not box.valid():
            continue
        sample = cache.content_evidence_float_work[
            box.top : box.bottom,
            box.left : box.right,
        ]
        if not sample.size:
            continue
        regions.append(
            HolderTextureRegion(
                name=name,
                box=box,
                mean=float(sample.mean()),
                coverage=float((sample >= frame_content.threshold).mean()),
                texture=float(sample.std()),
            )
        )
    if not regions:
        return HolderTextureEvidence(
            EvidenceState.NOT_APPLICABLE,
            "no_holder_slack",
            (),
            None,
            None,
        )
    holder_mean = float(np.median([region.mean for region in regions]))
    holder_coverage = float(np.median([region.coverage for region in regions]))
    holder_low = all(
        region.mean < float(parameters.present_mean_min)
        and region.coverage < float(parameters.present_coverage_min)
        for region in regions
    )
    content_mean = frame_content.median_mean
    content_coverage = frame_content.median_coverage
    return HolderTextureEvidence(
        state=(
            EvidenceState.SUPPORTED
            if holder_low
            else EvidenceState.CONTRADICTED
        ),
        reason=(
            "holder_slack_low_texture"
            if holder_low
            else "content_like_signal_in_holder_slack"
        ),
        regions=tuple(regions),
        content_holder_mean_contrast=(
            None if content_mean is None else float(content_mean - holder_mean)
        ),
        content_holder_coverage_contrast=(
            None
            if content_coverage is None
            else float(content_coverage - holder_coverage)
        ),
    )
