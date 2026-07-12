from __future__ import annotations

from dataclasses import dataclass

from ..formats import FormatPhysicalSpec
from .candidate import CandidatePlanParameters
from .content import ContentConfiguration
from .diagnostics import DiagnosticsConfiguration
from .preprocess import PreprocessConfiguration
from .separator import SeparatorConfiguration


@dataclass(frozen=True)
class DetectionConfiguration:
    physical_spec: FormatPhysicalSpec
    strip_mode: str
    preprocess: PreprocessConfiguration
    detector_kind: str
    separator: SeparatorConfiguration
    content: ContentConfiguration
    candidate_plan: CandidatePlanParameters
    diagnostics: DiagnosticsConfiguration

    @property
    def configuration_id(self) -> str:
        return (
            f"detection:{self.physical_spec.format_id}:{self.strip_mode}"
        )
