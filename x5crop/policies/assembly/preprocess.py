from __future__ import annotations

from ...image.evidence import (
    ContentEvidenceImageParameters,
    DeskewFallbackEvidenceParameters,
    SeparatorEvidenceImageParameters,
)
from ...image.gray import BaseGrayParameters
from ..parameters.aggregate import FormatParameters
from ..runtime.preprocess import RuntimePreprocessPolicy


def preprocess_policy(params: FormatParameters) -> RuntimePreprocessPolicy:
    return RuntimePreprocessPolicy(
        base_gray=BaseGrayParameters(),
        deskew=params.deskew,
        deskew_fallback_evidence=DeskewFallbackEvidenceParameters(),
        separator_evidence_image=SeparatorEvidenceImageParameters(),
        content_evidence_image=ContentEvidenceImageParameters(),
    )


__all__ = [
    "preprocess_policy",
]
