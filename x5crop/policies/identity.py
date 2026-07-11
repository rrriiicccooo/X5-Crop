from __future__ import annotations


def detection_policy_id_for(format_id: str, strip_mode: str) -> str:
    return f"detection:{format_id}:{strip_mode}"
