from __future__ import annotations

from .base import FULL, PARTIAL
from .registry import get_detection_policy

FORMAT_ID = "135-dual"

POLICY_ROLES = {
    FULL: "dedicated_dual_lane_full_strip",
    PARTIAL: "unsupported_dual_lane_partial",
}

POLICY_NOTES = {
    FULL: ("dual-lane detection is intentionally separate from normal strip policies",),
    PARTIAL: ("partial dual-lane scans stay review-only until real samples define a policy",),
}


def full_policy():
    return get_detection_policy(FORMAT_ID, FULL)


def partial_policy():
    return get_detection_policy(FORMAT_ID, PARTIAL)
