from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .....domain import Box


@dataclass(frozen=True)
class OuterCorrectionProposal:
    box: Box
    name: str
    strategy: str
    source_reason: str
    original_outer_work_box: Any
    preserve_gap_search_profile: bool = False
    suppress_outer_mismatch: bool = False
    detail: dict[str, Any] = field(default_factory=dict)
