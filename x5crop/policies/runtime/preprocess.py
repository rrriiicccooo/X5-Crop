from __future__ import annotations

from dataclasses import dataclass, field

from ...image.deskew_parameters import DeskewParameters
from ...image.evidence import (
    ContentEvidenceImageParameters,
    DeskewFallbackEvidenceParameters,
    SeparatorEvidenceImageParameters,
)
from ...image.gray import BaseGrayParameters
from ...units import ScanCalibrationTrustParameters


@dataclass(frozen=True)
class RuntimePreprocessPolicy:
    base_gray: BaseGrayParameters = field(default_factory=BaseGrayParameters)
    deskew: DeskewParameters = field(default_factory=DeskewParameters)
    deskew_fallback_evidence: DeskewFallbackEvidenceParameters = field(default_factory=DeskewFallbackEvidenceParameters)
    separator_evidence_image: SeparatorEvidenceImageParameters = field(default_factory=SeparatorEvidenceImageParameters)
    content_evidence_image: ContentEvidenceImageParameters = field(default_factory=ContentEvidenceImageParameters)
    scan_calibration_trust: ScanCalibrationTrustParameters = field(default_factory=ScanCalibrationTrustParameters)


__all__ = [
    "RuntimePreprocessPolicy",
]
