from __future__ import annotations

from dataclasses import dataclass

from ...image.evidence import ContentEvidenceImageParameters
from ..parameters.content import (
    ContentCandidateParameters,
    ContentEvidenceParameters,
    ContentMaskParameters,
    ContentProfileParameters,
    ContentSupportParameters,
)


@dataclass(frozen=True)
class ContentPolicy:
    evidence_image: ContentEvidenceImageParameters
    evidence: ContentEvidenceParameters
    profile: ContentProfileParameters
    mask: ContentMaskParameters
    candidate: ContentCandidateParameters
    support: ContentSupportParameters
