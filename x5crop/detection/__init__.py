"""Detection core interfaces."""

from ..domain import Box, Detection, Gap, OuterCandidate
from .context import DetectionContext, detection_policy_for
from .candidate_run import detect_candidate_for_count
from .pipeline import detect_image
from .finalizer import finalize_detection

__all__ = [
    "Box",
    "DetectionContext",
    "Detection",
    "Gap",
    "OuterCandidate",
    "detect_candidate_for_count",
    "detect_image",
    "detection_policy_for",
    "finalize_detection",
]
