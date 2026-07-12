from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...cache import MeasurementCache
from ...domain import Box, EvidenceState
from ...configuration.content import ContentEvidenceParameters
from ..guidance.content_crop_envelope import measured_content_span

if TYPE_CHECKING:
    from ..physical.model import SequenceSolution


@dataclass(frozen=True)
class SequenceContentAlignmentEvidence:
    visible_sequence_span: Box
    content_span: Box | None
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)
    content_outside_sides: tuple[str, ...] = field(init=False)
    overcontains_long_axis: bool = field(init=False)
    overcontains_short_axis: bool = field(init=False)
    leading_slack_px: int = field(init=False)
    trailing_slack_px: int = field(init=False)
    top_slack_px: int = field(init=False)
    bottom_slack_px: int = field(init=False)

    def __post_init__(self) -> None:
        sequence = self.visible_sequence_span
        content = self.content_span
        if not sequence.valid() or content is None or not content.valid():
            state = EvidenceState.UNAVAILABLE
            reason = "content_span_unavailable"
            outside: tuple[str, ...] = ()
            leading_slack = trailing_slack = top_slack = bottom_slack = 0
        else:
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
            state = (
                EvidenceState.UNAVAILABLE
                if outside
                else EvidenceState.SUPPORTED
            )
            reason = (
                "content_measurement_conflicts_with_sequence"
                if outside
                else "content_inside_visible_sequence"
            )
            leading_slack = max(0, content.left - sequence.left)
            trailing_slack = max(0, sequence.right - content.right)
            top_slack = max(0, content.top - sequence.top)
            bottom_slack = max(0, sequence.bottom - content.bottom)

        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "content_outside_sides", outside)
        object.__setattr__(
            self,
            "overcontains_long_axis",
            bool(leading_slack or trailing_slack),
        )
        object.__setattr__(
            self,
            "overcontains_short_axis",
            bool(top_slack or bottom_slack),
        )
        object.__setattr__(self, "leading_slack_px", leading_slack)
        object.__setattr__(self, "trailing_slack_px", trailing_slack)
        object.__setattr__(self, "top_slack_px", top_slack)
        object.__setattr__(self, "bottom_slack_px", bottom_slack)


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
    return SequenceContentAlignmentEvidence(sequence, content)
