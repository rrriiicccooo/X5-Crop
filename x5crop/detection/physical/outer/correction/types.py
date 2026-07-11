from __future__ import annotations

from dataclasses import dataclass

from ...spans import CropEnvelope, VisibleSequenceSpan


@dataclass(frozen=True)
class SequenceAdjustmentHypothesis:
    visible_sequence_span: VisibleSequenceSpan
    crop_envelope: CropEnvelope
    family: str
    reason: str
