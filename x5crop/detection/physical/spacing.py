from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import EvidenceState, PixelInterval, sum_pixel_intervals
from .boundary import HolderOcclusionEvidence


SPACING_KINDS = frozenset({"separator", "contact", "overlap", "unresolved"})


@dataclass(frozen=True)
class InterFrameSpacingEvidence:
    index: int
    state: EvidenceState
    kind: str
    signed_width_px: PixelInterval
    reason: str
    lane_index: int | None = None

    def __post_init__(self) -> None:
        if self.index <= 0:
            raise ValueError("inter-frame spacing index must be positive")
        if self.kind not in SPACING_KINDS:
            raise ValueError(f"unsupported spacing kind: {self.kind}")
        if self.lane_index is not None and self.lane_index <= 0:
            raise ValueError("lane index must be positive")


@dataclass(frozen=True)
class SequenceConservationEvidence:
    state: EvidenceState
    reason: str
    visible_length_px: PixelInterval
    holder_occlusion_px: PixelInterval
    frame_total_px: PixelInterval
    spacing_total_px: PixelInterval
    physical_sequence_px: PixelInterval


def _spacing_kind(interval: PixelInterval) -> str:
    if interval.minimum > 0.0:
        return "separator"
    if interval.maximum < 0.0:
        return "overlap"
    if interval.minimum == 0.0 and interval.maximum == 0.0:
        return "contact"
    return "unresolved"


def inter_frame_spacing_evidence(
    index: int,
    signed_width_px: PixelInterval,
) -> InterFrameSpacingEvidence:
    kind = _spacing_kind(signed_width_px)
    return InterFrameSpacingEvidence(
        index=index,
        state=(
            EvidenceState.UNAVAILABLE
            if kind == "unresolved"
            else EvidenceState.SUPPORTED
        ),
        kind=kind,
        signed_width_px=signed_width_px,
        reason=f"{kind}_spacing",
    )


def sequence_conservation_evidence(
    *,
    visible_length_px: PixelInterval,
    count: int,
    frame_width_px: PixelInterval,
    spacings: tuple[InterFrameSpacingEvidence, ...],
    holder_occlusion: HolderOcclusionEvidence,
) -> SequenceConservationEvidence:
    if count <= 0 or len(spacings) != max(0, count - 1):
        return SequenceConservationEvidence(
            EvidenceState.UNAVAILABLE,
            "count_or_spacing_sequence_incomplete",
            visible_length_px,
            PixelInterval.zero(),
            PixelInterval.zero(),
            PixelInterval.zero(),
            PixelInterval.zero(),
        )
    if any(spacing.state == EvidenceState.CONTRADICTED for spacing in spacings):
        return SequenceConservationEvidence(
            EvidenceState.CONTRADICTED,
            "inter_frame_spacing_equation_contradicted",
            visible_length_px,
            PixelInterval.zero(),
            frame_width_px.scaled(float(count)),
            sum_pixel_intervals(tuple(item.signed_width_px for item in spacings)),
            PixelInterval.zero(),
        )
    if any(spacing.state == EvidenceState.UNAVAILABLE for spacing in spacings):
        return SequenceConservationEvidence(
            EvidenceState.UNAVAILABLE,
            "signed_spacing_unresolved",
            visible_length_px,
            PixelInterval.zero(),
            frame_width_px.scaled(float(count)),
            sum_pixel_intervals(tuple(item.signed_width_px for item in spacings)),
            PixelInterval.zero(),
        )
    occlusion = holder_occlusion.leading.hidden_width_px.plus(
        holder_occlusion.trailing.hidden_width_px
    )
    frame_total = frame_width_px.scaled(float(count))
    spacing_total = sum_pixel_intervals(
        tuple(item.signed_width_px for item in spacings)
    )
    observed_physical = visible_length_px.plus(occlusion)
    modeled_physical = frame_total.plus(spacing_total)
    supported = observed_physical.intersects(modeled_physical)
    return SequenceConservationEvidence(
        EvidenceState.SUPPORTED if supported else EvidenceState.CONTRADICTED,
        "frame_sequence_conserved" if supported else "frame_sequence_not_conserved",
        visible_length_px,
        occlusion,
        frame_total,
        spacing_total,
        modeled_physical,
    )
