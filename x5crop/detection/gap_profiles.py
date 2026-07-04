from __future__ import annotations

from typing import Any, Optional

from ..policies.runtime_policy import DetectionPolicy


STANDARD_GAP_PROFILE = "standard"
BROAD_WIDTH_GAP_PROFILE = "broad_width"
LEGACY_SEPARATOR_WIDTH_PROFILE = "separator_width_profile"


def is_broad_width_gap_profile(profile: str) -> bool:
    return profile in {BROAD_WIDTH_GAP_PROFILE, LEGACY_SEPARATOR_WIDTH_PROFILE}


def broad_width_gap_profile_detail(
    policy: DetectionPolicy,
    gap_max_width_ratio: Optional[float],
    *,
    preserved_through_outer_correction_candidate: bool = False,
) -> dict[str, Any]:
    detail = {
        "used": True,
        "profile": BROAD_WIDTH_GAP_PROFILE,
        "base_gap_max_width_ratio": float(policy.separator.gap_search.max_width_ratio),
        "gap_max_width_ratio": float(
            gap_max_width_ratio
            if gap_max_width_ratio is not None
            else policy.separator.separator_width_profile_max_width_ratio
        ),
    }
    if preserved_through_outer_correction_candidate:
        detail["preserved_through_outer_correction_candidate"] = True
    return detail


__all__ = [
    "BROAD_WIDTH_GAP_PROFILE",
    "LEGACY_SEPARATOR_WIDTH_PROFILE",
    "STANDARD_GAP_PROFILE",
    "broad_width_gap_profile_detail",
    "is_broad_width_gap_profile",
]
