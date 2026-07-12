from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...cache import MeasurementCache
from ...domain import Box, EvidenceState
from ...policies.parameters.content import ContentEvidenceParameters
from ..guidance.content_crop_envelope import measured_content_span

if TYPE_CHECKING:
    from ..physical.model import SequenceSolution


@dataclass(frozen=True)
class SequenceContentAlignmentEvidence:
    state: EvidenceState
    reason: str
    visible_sequence_span: Box
    content_span: Box | None
    content_measurement_sources: tuple[str, ...]
    confirmed_undercrop_sides: tuple[str, ...]
    unconfirmed_undercrop_sides: tuple[str, ...]
    overcontains_long_axis: bool
    overcontains_short_axis: bool
    leading_slack_px: int
    trailing_slack_px: int
    top_slack_px: int
    bottom_slack_px: int
    border_tonal_fraction: tuple[tuple[str, float], ...]


def sequence_content_alignment_evidence(
    geometry: SequenceSolution,
    cache: MeasurementCache,
    parameters: ContentEvidenceParameters,
) -> SequenceContentAlignmentEvidence:
    if cache.layout != geometry.layout:
        raise ValueError("sequence alignment requires matching measurement cache")
    height, width = cache.gray_work.shape
    sequence = geometry.visible_sequence_span.box.clamp(width, height)
    content = measured_content_span(
        cache.content_evidence_float_work,
        parameters,
    )
    if not sequence.valid() or content is None or not content.valid():
        return SequenceContentAlignmentEvidence(
            EvidenceState.UNAVAILABLE,
            "content_span_unavailable",
            sequence,
            content,
            (),
            (),
            (),
            False,
            False,
            0,
            0,
            0,
            0,
            (),
        )
    outside = tuple(
        side
        for side, present in (
            ("leading", content.left < sequence.left),
            ("trailing", content.right > sequence.right),
            ("top", content.top < sequence.top),
            ("bottom", content.bottom > sequence.bottom),
        )
        if present
    )
    leading_slack = max(0, content.left - sequence.left)
    trailing_slack = max(0, sequence.right - content.right)
    top_slack = max(0, content.top - sequence.top)
    bottom_slack = max(0, sequence.bottom - content.bottom)
    return SequenceContentAlignmentEvidence(
        state=(EvidenceState.UNAVAILABLE if outside else EvidenceState.SUPPORTED),
        reason=(
            "content_measurement_conflicts_with_sequence"
            if outside
            else "content_inside_visible_sequence"
        ),
        visible_sequence_span=sequence,
        content_span=content,
        content_measurement_sources=("adaptive_content_consensus",),
        confirmed_undercrop_sides=(),
        unconfirmed_undercrop_sides=outside,
        overcontains_long_axis=bool(leading_slack or trailing_slack),
        overcontains_short_axis=bool(top_slack or bottom_slack),
        leading_slack_px=leading_slack,
        trailing_slack_px=trailing_slack,
        top_slack_px=top_slack,
        bottom_slack_px=bottom_slack,
        border_tonal_fraction=(),
    )
