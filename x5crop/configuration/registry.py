from __future__ import annotations

from functools import lru_cache

from ..formats import FORMAT_CHOICES, FormatPhysicalSpec, format_spec
from ..strip_modes import FULL, PARTIAL, STRIP_MODES
from .candidate import CandidatePlanParameters
from .content import ContentConfiguration
from .diagnostics import DiagnosticsConfiguration
from .model import DetectionConfiguration
from .preprocess import PreprocessConfiguration
from .separator import SeparatorConfiguration


def _detector_kind(spec: FormatPhysicalSpec, strip_mode: str) -> str:
    if spec.physical_layout == "dual_lane" and strip_mode == FULL:
        return "dual_lane"
    if spec.physical_layout == "dual_lane" and strip_mode == PARTIAL:
        return "review_only"
    return "standard_strip"


@lru_cache(maxsize=None)
def get_detection_configuration(
    format_id: str,
    strip_mode: str,
) -> DetectionConfiguration:
    if strip_mode not in STRIP_MODES:
        raise ValueError(f"Unsupported strip mode: {strip_mode}")
    if format_id not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format: {format_id}")
    spec = format_spec(format_id)
    return DetectionConfiguration(
        physical_spec=spec,
        strip_mode=strip_mode,
        preprocess=PreprocessConfiguration(),
        detector_kind=_detector_kind(spec, strip_mode),
        separator=SeparatorConfiguration(),
        content=ContentConfiguration(),
        candidate_plan=CandidatePlanParameters(),
        diagnostics=DiagnosticsConfiguration(),
    )
