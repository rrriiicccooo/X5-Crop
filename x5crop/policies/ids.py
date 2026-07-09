from __future__ import annotations

REPORT_SCHEMA_VERSION = "v4_9_policy_schema_2"

_POLICY_ID_STEMS = {
    "135": "standard_strip",
    "135-dual": "dual_lane_strip",
    "half": "dense_half_frame_strip",
    "xpan": "panoramic_strip",
    "120-645": "medium_rectangle_strip",
    "120-66": "medium_square_strip",
    "120-67": "medium_wide_strip",
}


def policy_id_stem_for(format_id: str) -> str:
    return _POLICY_ID_STEMS.get(format_id, "unknown_strip")


def detection_policy_id_for(format_id: str, strip_mode: str) -> str:
    return f"detection_policy_{policy_id_stem_for(format_id)}_{strip_mode}"


def decision_policy_id_for(format_id: str, strip_mode: str) -> str:
    return f"evidence_guarded_{policy_id_stem_for(format_id)}_{strip_mode}"


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "decision_policy_id_for",
    "detection_policy_id_for",
    "policy_id_stem_for",
]
