from __future__ import annotations

from ...formats import FormatPhysicalSpec
from ...image.evidence import (
    ContentEvidenceImageParameters,
    DeskewFallbackEvidenceParameters,
    SeparatorEvidenceImageParameters,
)
from ...image.gray import BaseGrayParameters
from ...image.statistics import ImageMeasurementStatisticsParameters
from ..parameters.aggregate import FormatParameters
from ...strip_modes import FULL, PARTIAL
from .separator import separator_policy
from ..runtime.content import ContentPolicy
from ..runtime.diagnostics import RuntimeDiagnosticsPolicy
from ..runtime.policy import DetectionPolicy
from ..runtime.preprocess import RuntimePreprocessPolicy


def _detector_kind(spec: FormatPhysicalSpec, strip_mode: str) -> str:
    if spec.physical_layout == "dual_lane" and strip_mode == FULL:
        return "dual_lane"
    if spec.physical_layout == "dual_lane" and strip_mode == PARTIAL:
        return "review_only"
    return "standard_strip"


def build_detection_policy(
    spec: FormatPhysicalSpec,
    params: FormatParameters,
    strip_mode: str,
) -> DetectionPolicy:
    detector_kind = _detector_kind(spec, strip_mode)
    preprocess = RuntimePreprocessPolicy(
        base_gray=BaseGrayParameters(),
        deskew=params.preprocess.deskew,
        deskew_fallback_evidence=DeskewFallbackEvidenceParameters(),
        separator_evidence_image=SeparatorEvidenceImageParameters(),
        content_evidence_image=ContentEvidenceImageParameters(),
        image_statistics=ImageMeasurementStatisticsParameters(),
    )
    separator = separator_policy(params)
    return DetectionPolicy(
        physical_spec=spec,
        strip_mode=strip_mode,
        preprocess=preprocess,
        detector_kind=detector_kind,
        separator=separator,
        content=ContentPolicy(
            evidence=params.content.content_evidence,
            profile=params.content.content_profile,
        ),
        candidate_plan=params.candidate.candidate_plan,
        diagnostics=RuntimeDiagnosticsPolicy(
            separator_overlay=params.diagnostics.separator_overlay,
        ),
    )
