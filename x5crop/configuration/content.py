from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import (
    require_percentile,
    require_positive,
)


@dataclass(frozen=True)
class ContentEvidenceParameters:
    activation_percentile: float = 70.0
    minimum_evidence_range: float = 1e-6
    minimum_active_pixels: int = 16
    maximum_percentile_samples: int = 1_000_000
    maximum_streaming_block_pixels: int = 1_048_576

    def __post_init__(self) -> None:
        require_percentile(
            "content activation percentile",
            self.activation_percentile,
        )
        require_positive("content evidence range", self.minimum_evidence_range)
        require_positive("content active pixel count", self.minimum_active_pixels)
        require_positive(
            "content percentile sample budget",
            self.maximum_percentile_samples,
        )
        require_positive(
            "content streaming block pixel budget",
            self.maximum_streaming_block_pixels,
        )


@dataclass(frozen=True)
class ContentConfiguration:
    evidence: ContentEvidenceParameters = field(
        default_factory=ContentEvidenceParameters
    )
