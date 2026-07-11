from __future__ import annotations

from dataclasses import dataclass

from ..parameters.content import (
    ContentEvidenceParameters,
    ContentProfileParameters,
    ContentSupportParameters,
)


@dataclass(frozen=True)
class ContentPolicy:
    evidence: ContentEvidenceParameters
    profile: ContentProfileParameters
    support: ContentSupportParameters
