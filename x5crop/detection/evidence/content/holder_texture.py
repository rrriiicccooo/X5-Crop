from __future__ import annotations

from dataclasses import dataclass, field

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
    regions: tuple[HolderTextureRegion, ...]
    frame_content_mean: float | None
    frame_content_coverage: float | None
    measurement_unavailable_reason: str | None = None
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)
    content_holder_mean_contrast: float | None = field(init=False)
    content_holder_coverage_contrast: float | None = field(init=False)

    def __post_init__(self) -> None:
        if self.measurement_unavailable_reason is not None:
            if self.regions:
                raise ValueError(
                    "unavailable holder texture measurement cannot contain regions"
                )
            state = EvidenceState.UNAVAILABLE
            reason = self.measurement_unavailable_reason
            mean_contrast = None
            coverage_contrast = None
        elif not self.regions:
            state = EvidenceState.NOT_APPLICABLE
            reason = "no_holder_slack"
            mean_contrast = None
            coverage_contrast = None
        elif (
            self.frame_content_mean is None
            or self.frame_content_coverage is None
        ):
            state = EvidenceState.UNAVAILABLE
            reason = "frame_content_reference_unavailable"
            mean_contrast = None
            coverage_contrast = None
        else:
            holder_mean = float(
                np.median([region.mean for region in self.regions])
            )
            holder_coverage = float(
                np.median([region.coverage for region in self.regions])
            )
            content_mean = float(self.frame_content_mean)
            content_coverage = float(self.frame_content_coverage)
            holder_not_more_active = all(
                region.mean <= content_mean
                and region.coverage <= content_coverage
                for region in self.regions
            )
            holder_distinct = any(
                region.mean < content_mean
                or region.coverage < content_coverage
                for region in self.regions
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
            mean_contrast = content_mean - holder_mean
            coverage_contrast = content_coverage - holder_coverage
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(
            self,
            "content_holder_mean_contrast",
            mean_contrast,
        )
        object.__setattr__(
            self,
            "content_holder_coverage_contrast",
            coverage_contrast,
        )


def holder_texture_evidence(
    geometry: SequenceSolution,
    cache: MeasurementCache,
    frame_content: FrameContentEvidence,
) -> HolderTextureEvidence:
    if cache.layout != geometry.layout or frame_content.threshold is None:
        return HolderTextureEvidence(
            (),
            None,
            None,
            "content_measurement_unavailable",
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
    return HolderTextureEvidence(
        regions=tuple(regions),
        frame_content_mean=frame_content.median_mean,
        frame_content_coverage=frame_content.median_coverage,
    )
