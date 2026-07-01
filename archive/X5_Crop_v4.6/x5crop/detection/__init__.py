"""Detection core interfaces."""

from .models import Box, Detection, Gap, OuterCandidate
from .context import DetectionContext, detection_policy_for
from .pipeline import detect_candidate_for_count, detect_image
from .postprocess import finalize_detection_decision
from .schema import report_schema_for_detection

__all__ = [
    "Box",
    "DetectionContext",
    "Detection",
    "Gap",
    "OuterCandidate",
    "detect_candidate_for_count",
    "detect_image",
    "detection_policy_for",
    "finalize_detection_decision",
    "report_schema_for_detection",
]
