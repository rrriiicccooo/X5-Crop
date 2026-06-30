"""Detection core interfaces."""

from .models import Box, Detection, Gap, OuterCandidate
from .pipeline import detect_candidate_for_count, detect_image
from .postprocess import finalize_detection_decision

__all__ = [
    "Box",
    "Detection",
    "Gap",
    "OuterCandidate",
    "detect_candidate_for_count",
    "detect_image",
    "finalize_detection_decision",
]
