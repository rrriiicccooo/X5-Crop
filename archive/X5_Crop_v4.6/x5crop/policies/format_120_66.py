from __future__ import annotations

from .base import FULL, PARTIAL
from .registry import get_detection_policy

FORMAT_ID = "120-66"

POLICY_ROLES = {
    FULL: "square_120_full_strip_dark_band_aware",
    PARTIAL: "square_120_partial_strip_dark_band_safe_extra_frames",
}

POLICY_NOTES = {
    FULL: (
        "dark-band outer candidates may compete, but full mode does not inherit partial extra-holder tolerance",
    ),
    PARTIAL: (
        "dark-band outer candidates must still pass separator/content/geometry gates",
        "safe extra holder frames require wide-like separator evidence and stable frame content",
    ),
}


def full_policy():
    return get_detection_policy(FORMAT_ID, FULL)


def partial_policy():
    return get_detection_policy(FORMAT_ID, PARTIAL)
