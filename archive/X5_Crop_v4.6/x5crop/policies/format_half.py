from __future__ import annotations

from .base import FULL, PARTIAL
from .registry import get_detection_policy

FORMAT_ID = "half"

POLICY_ROLES = {
    FULL: "half_frame_full_strip_with_geometry_support",
    PARTIAL: "half_frame_partial_strip",
}

POLICY_NOTES = {
    FULL: ("half full can use stable grid or wide geometry support without borrowing 120 dark-band gates",),
    PARTIAL: ("partial safe extra frames are allowed without 120-66 wide dark-band assumptions",),
}


def full_policy():
    return get_detection_policy(FORMAT_ID, FULL)


def partial_policy():
    return get_detection_policy(FORMAT_ID, PARTIAL)
