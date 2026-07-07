from __future__ import annotations

from typing import Any

from ..policies.runtime.separator import SeparatorPolicy


WIDTH_AWARE_GAP_PROFILE = "width_aware"


def width_aware_gap_profile_detail(separator: SeparatorPolicy) -> dict[str, Any]:
    return {
        "used": True,
        "profile": WIDTH_AWARE_GAP_PROFILE,
        "standard_profile": True,
        "theoretical_separator_width": separator.width_profile.mode != "off",
        "observed_width_profile": separator.width_profile.mode != "off",
    }


__all__ = [
    "WIDTH_AWARE_GAP_PROFILE",
    "width_aware_gap_profile_detail",
]
