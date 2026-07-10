from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.base import PARTIAL
from ..runtime.candidate import (
    PartialHolderPolicy,
)


def partial_holder_policy(
    detector_kind: str,
    strip_mode: str,
    params: FormatParameters,
) -> PartialHolderPolicy:
    holder = params.candidate.partial_holder
    content_evidence = params.content.content_evidence
    partial_edge_safety_enabled = bool(
        strip_mode == PARTIAL and detector_kind != "review_only"
    )
    return PartialHolderPolicy(
        enabled=partial_edge_safety_enabled,
        parameters=holder,
        max_frame_aspect_error=float(content_evidence.aspect_ok_max),
    )
