from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ....cache import MeasurementCache
from ....domain import Box
from ...physical.model import SequenceSolution
from x5crop.domain import EvidenceState
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
    geometry: SequenceSolution,
    cache: MeasurementCache,
    frame_content: FrameContentEvidence,
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
    film = geometry.visible_sequence_span.box.clamp(
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
    content_mean = frame_content.median_mean
    content_coverage = frame_content.median_coverage
    if content_mean is None or content_coverage is None:
        state = EvidenceState.UNAVAILABLE
        reason = "frame_content_reference_unavailable"
    else:
        holder_not_more_active = all(
            region.mean <= float(content_mean)
            and region.coverage <= float(content_coverage)
            for region in regions
        )
        holder_distinct = any(
            region.mean < float(content_mean)
            or region.coverage < float(content_coverage)
            for region in regions
        )
        if holder_not_more_active and holder_distinct:
            state = EvidenceState.SUPPORTED
            reason = "holder_slack_lower_content_than_frames"
        elif holder_not_more_active:
            state = EvidenceState.UNAVAILABLE
            reason = "holder_and_frame_content_indistinguishable"
        else:
            state = EvidenceState.CONTRADICTED
            reason = "content_like_signal_in_holder_slack"
    return HolderTextureEvidence(
        state=state,
        reason=reason,
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
