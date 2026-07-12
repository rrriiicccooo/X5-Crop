from __future__ import annotations

from dataclasses import replace

import numpy as np

from ...domain import Box, CropEnvelope, SequenceHypothesis
from ...configuration.content import ContentEvidenceParameters
from ...image.evidence import adaptive_activation_threshold


def measured_content_span(
    evidence: np.ndarray,
    parameters: ContentEvidenceParameters,
) -> Box | None:
    if evidence.ndim != 2 or not evidence.size:
        return None
    threshold = adaptive_activation_threshold(
        evidence,
        parameters.activation_percentile,
        parameters.minimum_evidence_range,
    )
    if threshold is None:
        return None
    active = evidence >= threshold
    if int(np.count_nonzero(active)) < int(parameters.minimum_active_pixels):
        return None
    rows, columns = np.nonzero(active)
    if not rows.size:
        return None
    return Box(
        int(columns.min()),
        int(rows.min()),
        int(columns.max()) + 1,
        int(rows.max()) + 1,
    )


def expand_crop_envelopes_for_content(
    evidence: np.ndarray,
    hypotheses: list[SequenceHypothesis],
    parameters: ContentEvidenceParameters,
) -> list[SequenceHypothesis]:
    content = measured_content_span(evidence, parameters)
    if content is None:
        return list(hypotheses)
    height, width = evidence.shape
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
