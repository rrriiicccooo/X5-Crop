from __future__ import annotations

from .....domain import Box, Detection
from .....policies.runtime_outer import OuterCorrectionFamilyPolicy


def correction_family_available(
    family: OuterCorrectionFamilyPolicy,
    detection: Detection,
    explicit_count: bool,
) -> bool:
    if not family.available_for(detection.strip_mode, explicit_count):
        return False
    if family.requires_separator_assessment:
        assessment = detection.detail.get("candidate_assessment", {})
        if not isinstance(assessment, dict) or assessment.get("source") != "separator":
            return False
    return True


def correction_axes_allowed(
    family: OuterCorrectionFamilyPolicy,
    original: Box,
    corrected: Box,
) -> bool:
    changed_axes: set[str] = set()
    if corrected.left != original.left or corrected.right != original.right:
        changed_axes.add("long")
    if corrected.top != original.top or corrected.bottom != original.bottom:
        changed_axes.add("short")
    allowed = set(family.allowed_axes)
    return bool(changed_axes) and changed_axes.issubset(allowed)


__all__ = ["correction_axes_allowed", "correction_family_available"]
