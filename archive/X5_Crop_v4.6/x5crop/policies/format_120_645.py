from __future__ import annotations

from .base import FULL, PARTIAL
from .registry import get_detection_policy

FORMAT_ID = "120-645"

POLICY_ROLES = {
    FULL: "120_645_full_strip",
    PARTIAL: "120_645_partial_strip",
}

POLICY_NOTES = {
    FULL: ("120-645 uses the shared 120 separator policy without 120-66 dark-band gates",),
    PARTIAL: ("120-645 partial uses the shared conservative partial policy",),
}


def full_policy():
    return get_detection_policy(FORMAT_ID, FULL)


def partial_policy():
    return get_detection_policy(FORMAT_ID, PARTIAL)
