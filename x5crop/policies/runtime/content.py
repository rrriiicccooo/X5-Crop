from __future__ import annotations

from dataclasses import dataclass

from ..parameters.content import (
    ContentEvidenceParameters,
    ContentProfileParameters,
)


@dataclass(frozen=True)
class ContentPolicy:
    evidence: ContentEvidenceParameters
    profile: ContentProfileParameters
