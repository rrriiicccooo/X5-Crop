"""Detection pipeline entry points.

The V4 compatibility build routes these calls to ``x5crop.core``. Future V4
work can move the implementation into this package without changing callers.
"""

from ..core import choose_detection_v2, detect_candidate_for_count


def detect_image(*args, **kwargs):
    """Run the current detection pipeline and return a Detection object."""

    return choose_detection_v2(*args, **kwargs)


__all__ = ["detect_candidate_for_count", "detect_image"]
