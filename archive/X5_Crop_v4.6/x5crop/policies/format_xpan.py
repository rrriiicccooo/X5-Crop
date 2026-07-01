from __future__ import annotations

from .base import FULL, PARTIAL
from .registry import get_detection_policy

FORMAT_ID = "xpan"

POLICY_ROLES = {
    FULL: "xpan_full_strip",
    PARTIAL: "xpan_partial_strip",
}

POLICY_NOTES = {
    FULL: ("xpan full remains conservative and separator-driven",),
    PARTIAL: ("partial xpan may include the default count but still needs separator/content/geometry gates",),
}


def full_policy():
    return get_detection_policy(FORMAT_ID, FULL)


def partial_policy():
    return get_detection_policy(FORMAT_ID, PARTIAL)
