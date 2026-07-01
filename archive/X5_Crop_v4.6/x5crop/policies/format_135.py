from __future__ import annotations

from .base import FULL, PARTIAL
from .registry import get_detection_policy

FORMAT_ID = "135"

POLICY_ROLES = {
    FULL: "stable_full_strip_baseline",
    PARTIAL: "conservative_partial_strip",
}

POLICY_NOTES = {
    FULL: ("preserve current 135 behavior unless sample-based regression approves a change",),
    PARTIAL: ("content evidence validates partial strips but cannot auto-pass alone",),
}


def full_policy():
    return get_detection_policy(FORMAT_ID, FULL)


def partial_policy():
    return get_detection_policy(FORMAT_ID, PARTIAL)
