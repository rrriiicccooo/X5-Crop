from __future__ import annotations

from .....domain import Box
from .....policies.runtime.outer import OuterCorrectionFamilyPolicy


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
