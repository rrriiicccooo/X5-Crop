from __future__ import annotations

from dataclasses import dataclass

from ...formats import FormatPhysicalSpec
from ..identity import detection_policy_id_for
from ..parameters.candidate import CandidatePlanParameters
from ..parameters.output import OverlapBleedParameters
from ..parameters.sequence import SequenceParameters
from .content import ContentPolicy
from .diagnostics import RuntimeDiagnosticsPolicy
from .preprocess import RuntimePreprocessPolicy
from .separator import SeparatorPolicy


@dataclass(frozen=True)
class DetectionPolicy:
    physical_spec: FormatPhysicalSpec
    strip_mode: str
    preprocess: RuntimePreprocessPolicy
    detector_kind: str
    sequence: SequenceParameters
    separator: SeparatorPolicy
    content: ContentPolicy
    candidate_plan: CandidatePlanParameters
    output: OverlapBleedParameters
    diagnostics: RuntimeDiagnosticsPolicy

    @property
    def policy_id(self) -> str:
        return detection_policy_id_for(
            self.physical_spec.format_id,
            self.strip_mode,
        )
