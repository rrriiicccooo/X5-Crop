from __future__ import annotations

from dataclasses import dataclass

from ...formats import FormatPhysicalSpec
from ..identity import detection_policy_id_for
from ..parameters.candidate import CandidatePlanParameters
from ..parameters.exposure_overlap import ExposureOverlapEvidenceParameters
from ..parameters.finalization import ApprovedGeometryAdjustmentParameters
from ..parameters.scoring import SelectionConsensusParameters
from .candidate import ScoringPolicy
from .content import ContentPolicy
from .diagnostics import RuntimeDiagnosticsPolicy
from .outer import OuterPolicy
from .output import OutputPolicy
from .preprocess import RuntimePreprocessPolicy
from .separator import SeparatorPolicy


@dataclass(frozen=True)
class DetectionPolicy:
    physical_spec: FormatPhysicalSpec
    strip_mode: str
    preprocess: RuntimePreprocessPolicy
    detector_kind: str
    partial_count_offsets: tuple[float, ...]
    outer: OuterPolicy
    separator: SeparatorPolicy
    content: ContentPolicy
    scoring: ScoringPolicy
    candidate_selection: SelectionConsensusParameters
    candidate_plan: CandidatePlanParameters
    exposure_overlap_evidence: ExposureOverlapEvidenceParameters
    approved_geometry_adjustment: ApprovedGeometryAdjustmentParameters
    output: OutputPolicy
    diagnostics: RuntimeDiagnosticsPolicy

    @property
    def policy_id(self) -> str:
        return detection_policy_id_for(
            self.physical_spec.format_id,
            self.strip_mode,
        )
