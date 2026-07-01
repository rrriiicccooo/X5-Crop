from __future__ import annotations

from .base import FULL, PARTIAL
from .registry import get_detection_policy

FORMAT_ID = "120-67"

POLICY_ROLES = {
    FULL: "120_67_full_strip_wide_separator_retry",
    PARTIAL: "120_67_partial_strip",
}

POLICY_NOTES = {
    FULL: ("120-67 full can use wide separator retry and tight short-axis correction",),
    PARTIAL: ("120-67 partial uses shared 120 partial policy and does not enable 120-66 dark-band gates",),
}


def full_policy():
    return get_detection_policy(FORMAT_ID, FULL)


def partial_policy():
    return get_detection_policy(FORMAT_ID, PARTIAL)
