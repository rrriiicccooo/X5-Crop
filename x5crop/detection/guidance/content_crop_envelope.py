from __future__ import annotations

from dataclasses import replace

import numpy as np

from ...domain import Box, CropEnvelope, SequenceHypothesis
from ...policies.parameters.sequence import SequenceContentAlignmentParameters
from ...utils import bbox_from_mask


def _measured_content_span(
    gray_work: np.ndarray,
    parameters: SequenceContentAlignmentParameters,
) -> Box | None:
    observations = tuple(
        box
        for threshold in parameters.content_bbox_thresholds
        if (
            box := bbox_from_mask(
                gray_work < int(threshold),
                min_row_fraction=float(parameters.content_bbox_min_row_fraction),
                min_col_fraction=float(parameters.content_bbox_min_col_fraction),
            )
        )
        is not None
        and box.valid()
    )
    if not observations:
        return None
    return Box(
        min(box.left for box in observations),
        min(box.top for box in observations),
        max(box.right for box in observations),
        max(box.bottom for box in observations),
    )


def expand_crop_envelopes_for_content(
    gray_work: np.ndarray,
    hypotheses: list[SequenceHypothesis],
    parameters: SequenceContentAlignmentParameters,
) -> list[SequenceHypothesis]:
    content = _measured_content_span(gray_work, parameters)
    if content is None:
        return list(hypotheses)
    height, width = gray_work.shape
    expanded: list[SequenceHypothesis] = []
    for hypothesis in hypotheses:
        envelope = hypothesis.crop_envelope.box
        box = Box(
            min(envelope.left, content.left),
            min(envelope.top, content.top),
            max(envelope.right, content.right),
            max(envelope.bottom, content.bottom),
        ).clamp(width, height)
        expanded.append(
            hypothesis
            if box == envelope
            else replace(hypothesis, crop_envelope=CropEnvelope(box))
        )
    return expanded
