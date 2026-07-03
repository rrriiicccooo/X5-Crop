from __future__ import annotations

from typing import Any, Optional

from ....domain import Detection
from ....formats import FormatSpec
from ....policies.registry import get_detection_policy
from ....runtime import AnalysisCache
from ....runtime_config import RuntimeConfig
from ...candidate.corrected_outer import CorrectedOuterCandidateInput
from ...evidence.outer_alignment import corrected_outer_from_alignment


def content_containment_correction_proposal(
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    alignment: dict[str, Any],
    cache: AnalysisCache,
) -> Optional[CorrectedOuterCandidateInput]:
    del config, cache
    if detection.strip_mode != "full":
        return None
    policy = get_detection_policy(fmt.name, detection.strip_mode)
    corrected_outer = corrected_outer_from_alignment(alignment, detection.count, policy)
    if corrected_outer is None:
        return None
    return CorrectedOuterCandidateInput(
        box=corrected_outer,
        name="content_containment_outer",
        strategy="content_containment_correction",
        source_reason=str(alignment.get("reason", "")),
        original_outer_work_box=alignment.get("outer_work_box"),
        preserve_wide_retry=True,
        detail={
            "source_edge_hard_anchors": bool(alignment.get("edge_hard_anchors", False)),
            "source_white_edge_slack": bool(alignment.get("white_edge_slack", False)),
            "content_work_box": alignment.get("content_work_box"),
        },
    )


__all__ = ["content_containment_correction_proposal"]
