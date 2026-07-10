from __future__ import annotations

from typing import Any, Optional

from .....domain import Box
from .....domain import DetectionCandidate
from .....policies.runtime.outer import ContentContainmentCorrectionPolicy
from .....utils import box_from_dict, clamp_int
from .constraints import correction_axes_allowed
from .types import OuterCorrectionProposal


def corrected_outer_from_alignment(
    alignment: dict[str, Any],
    count: int,
    content_containment_policy: ContentContainmentCorrectionPolicy,
) -> Optional[Box]:
    if not bool(alignment.get("used", False)) or bool(alignment.get("ok", True)):
        return None
    try:
        outer = box_from_dict(alignment["outer_work_box"])
        content = box_from_dict(alignment["content_work_box"])
    except Exception:
        return None
    if not outer.valid() or not content.valid():
        return None

    pitch = float(outer.width) / float(max(1, count))
    alignment_margin_x = clamp_int(
        pitch * content_containment_policy.margin_x_ratio,
        content_containment_policy.margin_x_min,
        content_containment_policy.margin_x_max,
    )
    alignment_margin_y = clamp_int(
        float(outer.height) * content_containment_policy.margin_y_ratio,
        content_containment_policy.margin_y_min,
        content_containment_policy.margin_y_max,
    )
    long_margin_cap = clamp_int(
        pitch * content_containment_policy.long_margin_cap_ratio,
        content_containment_policy.long_margin_cap_min,
        content_containment_policy.long_margin_cap_max,
    )
    short_margin_cap = clamp_int(
        float(outer.height) * content_containment_policy.short_margin_cap_ratio,
        content_containment_policy.short_margin_cap_min,
        content_containment_policy.short_margin_cap_max,
    )
    long_margin = max(
        alignment_margin_x,
        min(
            long_margin_cap,
            int(round(pitch * content_containment_policy.long_margin_ratio)),
        ),
    )
    short_margin = max(
        alignment_margin_y,
        min(
            short_margin_cap,
            int(round(float(outer.height) * content_containment_policy.short_margin_ratio)),
        ),
    )
    left, top, right, bottom = outer.left, outer.top, outer.right, outer.bottom

    if int(alignment.get("long_slack_left", 0)) > 0:
        left = max(outer.left, content.left - long_margin)
    if int(alignment.get("long_slack_right", 0)) > 0:
        right = min(outer.right, content.right + long_margin)
    if int(alignment.get("short_slack_top", 0)) > 0 and str(alignment.get("reason", "")) == "outer_short_axis_excess":
        top = max(outer.top, content.top - short_margin)
    if int(alignment.get("short_slack_bottom", 0)) > 0 and str(alignment.get("reason", "")) == "outer_short_axis_excess":
        bottom = min(outer.bottom, content.bottom + short_margin)

    corrected = Box(left, top, right, bottom)
    if not corrected.valid():
        return None
    if corrected.width < max(
        int(content_containment_policy.min_corrected_width_px),
        int(round(outer.width * content_containment_policy.min_corrected_size_ratio)),
    ):
        return None
    if corrected.height < max(
        int(content_containment_policy.min_corrected_height_px),
        int(round(outer.height * content_containment_policy.min_corrected_size_ratio)),
    ):
        return None
    if corrected == outer:
        return None
    return corrected


def content_containment_correction_proposal(
    detection: DetectionCandidate,
    alignment: dict[str, Any],
    eligible_families: set[str],
    content_containment_policy: ContentContainmentCorrectionPolicy,
) -> Optional[OuterCorrectionProposal]:
    if "content_containment" not in eligible_families:
        return None
    family = content_containment_policy.family
    corrected_outer = corrected_outer_from_alignment(
        alignment,
        detection.count,
        content_containment_policy,
    )
    if corrected_outer is None:
        return None
    try:
        original_outer = box_from_dict(alignment["outer_work_box"])
    except Exception:
        return None
    if not correction_axes_allowed(family, original_outer, corrected_outer):
        return None
    return OuterCorrectionProposal(
        box=corrected_outer,
        name="content_containment_outer",
        strategy="content_containment_correction",
        source_reason=str(alignment.get("reason", "")),
        original_outer_work_box=alignment.get("outer_work_box"),
        preserve_gap_search_profile=True,
        detail={
            "source_edge_hard_anchors": bool(alignment.get("edge_hard_anchors", False)),
            "source_white_edge_slack": bool(alignment.get("white_edge_slack", False)),
            "content_work_box": alignment.get("content_work_box"),
        },
    )
