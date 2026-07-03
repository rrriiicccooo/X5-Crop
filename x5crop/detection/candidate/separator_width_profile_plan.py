from __future__ import annotations

from ...formats import FormatSpec
from ...policies.runtime_policy import DetectionPolicy


def should_include_separator_width_profile_candidates(
    policy: DetectionPolicy,
    strip_mode: str,
    count: int,
    fmt: FormatSpec,
    explicit_count: bool,
) -> bool:
    if not policy.separator.separator_width_profile_enabled:
        return False
    family = policy.outer.proposal.geometry.separator.width_profile_family
    if not family.available_for(strip_mode, explicit_count):
        return False
    if policy.outer.proposal.geometry.separator.width_profile.mode == "off":
        return False
    profile = policy.candidate_plan.separator_width_profile
    if strip_mode in profile.partial_strip_modes:
        return bool(profile.include_partial_candidates)
    if strip_mode in profile.full_strip_modes:
        if not profile.include_full_default_count:
            return False
        if profile.full_requires_default_count and count != fmt.default_count:
            return False
        return True
    return False


__all__ = ["should_include_separator_width_profile_candidates"]
