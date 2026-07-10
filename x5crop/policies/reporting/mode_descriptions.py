from __future__ import annotations

from ...formats import FormatPhysicalSpec
from ...formats.traits import runtime_traits_for_spec
from ..runtime.base import FULL


def mode_role_for_spec(spec: FormatPhysicalSpec, strip_mode: str) -> str:
    mode = "full" if strip_mode == FULL else "partial"
    if spec.physical_layout == "dual_lane":
        posture = "isolated_detector" if mode == "full" else "review_only"
        return f"{mode}_dual_lane_{posture}"
    traits = runtime_traits_for_spec(spec)
    density = "dense" if traits.geometry_support_profile == "stable_dense_grid" else spec.family
    width = (
        "separator_width_profile"
        if traits.separator_width_profile == "broad"
        else "standard_separator_width"
    )
    edge = "edge_safety" if mode == "partial" else "geometry_content_alignment"
    return f"{mode}_{density}_{width}_{edge}"


def mode_notes_for_spec(spec: FormatPhysicalSpec, strip_mode: str) -> tuple[str, ...]:
    if spec.physical_layout == "dual_lane" and strip_mode != FULL:
        return ("dual-lane partial scans are review-only until a physical detector contract is defined",)
    notes = [
        "format traits provide physical facts and tolerances; they do not own algorithm branches",
    ]
    traits = runtime_traits_for_spec(spec)
    if traits.separator_width_profile == "broad":
        notes.append(
            "separator width profile evidence accepts measured broad bands without treating darkness as a format fact"
        )
    if strip_mode != FULL:
        notes.append("partial mode requires partial edge safety and may include empty holder frames")
    if traits.geometry_support_profile == "stable_dense_grid":
        notes.append("stable dense geometry can support separator evidence when content and photo-width evidence agree")
    return tuple(notes)


__all__ = ["mode_notes_for_spec", "mode_role_for_spec"]
