from __future__ import annotations

from typing import Any, Optional

from .....domain import Detection
from .....formats import FormatSpec
from .....policies.registry import get_detection_policy
from .....cache import AnalysisCache
from .....runtime.config import RuntimeConfig
from .....utils import box_from_dict
from ....evidence.outer_alignment import corrected_outer_from_alignment
from .constraints import correction_axes_allowed
from .types import OuterCorrectionProposal


def content_containment_correction_proposal(
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    alignment: dict[str, Any],
    cache: AnalysisCache,
    eligible_families: set[str],
) -> Optional[OuterCorrectionProposal]:
    del config, cache
    if "content_containment" not in eligible_families:
        return None
    policy = get_detection_policy(fmt.name, detection.strip_mode)
    family = policy.outer.correction.content_containment.family
    corrected_outer = corrected_outer_from_alignment(alignment, detection.count, policy)
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
        preserve_separator_width_profile=True,
        detail={
            "source_edge_hard_anchors": bool(alignment.get("edge_hard_anchors", False)),
            "source_white_edge_slack": bool(alignment.get("white_edge_slack", False)),
            "content_work_box": alignment.get("content_work_box"),
        },
    )


__all__ = ["content_containment_correction_proposal"]
