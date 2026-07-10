from __future__ import annotations

from ...formats import FormatPhysicalSpec
from ..runtime.base import FULL


def mode_role_for_spec(spec: FormatPhysicalSpec, strip_mode: str) -> str:
    mode = "full" if strip_mode == FULL else "partial"
    if spec.physical_layout == "dual_lane":
        posture = "isolated_detector" if mode == "full" else "review_only"
        return f"{mode}_dual_lane_{posture}"
    density = "dense" if spec.frame_geometry_profile == "dense_half" else spec.family
    edge = "edge_safety" if mode == "partial" else "geometry_content_alignment"
    return f"{mode}_{density}_observed_separator_width_{edge}"


def mode_notes_for_spec(spec: FormatPhysicalSpec, strip_mode: str) -> tuple[str, ...]:
    if spec.physical_layout == "dual_lane" and strip_mode != FULL:
        return ("dual-lane partial scans are review-only until a physical detector contract is defined",)
    notes = [
        "format traits provide physical facts and tolerances; they do not own algorithm branches",
    ]
    notes.append(
        "observed separator width evidence accepts narrower and broader bands without treating width or darkness as a format fact"
    )
    if strip_mode != FULL:
        notes.append("partial mode requires partial edge safety and may include empty holder frames")
    if spec.frame_geometry_profile == "dense_half":
        notes.append("stable dense geometry can support separator evidence when content and photo-width evidence agree")
    return tuple(notes)
