from __future__ import annotations

from dataclasses import dataclass

from ..parameters.content import (
    ContentEvidenceParameters,
    ContentMaskParameters,
    ContentProfileParameters,
    ContentSupportParameters,
)


@dataclass(frozen=True)
class ContentPolicy:
    evidence: ContentEvidenceParameters
    profile: ContentProfileParameters
    mask: ContentMaskParameters
    support: ContentSupportParameters
