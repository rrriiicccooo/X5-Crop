from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from x5crop.domain import EvidenceState


class GateStage(str, Enum):
    CANDIDATE = "candidate"
    DECISION = "decision"


class GateGap(str, Enum):
    SCAN_CANVAS_AUTHORITY_UNAVAILABLE = "scan_canvas_authority_unavailable"
    HOLDER_FULL_COUNT_UNRESOLVED = "holder_full_count_unresolved"
    HOLDER_IDENTITY_UNRESOLVED = "holder_identity_unresolved"
    OUTPUT_SLOT_COUNT_UNAVAILABLE = "output_slot_count_unavailable"
    FORMAT_PLACEMENT_UNAVAILABLE = "format_placement_unavailable"
    SHARED_STRIP_DIRECTION_UNAVAILABLE = "shared_strip_direction_unavailable"
    SHARED_STRIP_DIRECTION_NONUNIQUE = "shared_strip_direction_nonunique"
    SOURCE_FRAME_GEOMETRY_UNAVAILABLE = "source_frame_geometry_unavailable"
    SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED = "slot_ordinal_assignment_unresolved"
    SOURCE_LANE_AUTHORITY_INVALID = "source_lane_authority_invalid"
    PLACEMENT_SET_CONTAINMENT_UNAVAILABLE = (
        "placement_set_containment_unavailable"
    )
    DIRECT_USE_BUDGET_EXCEEDED = "direct_use_budget_exceeded"
    DIRECT_USE_BUDGET_UNAVAILABLE = "direct_use_budget_unavailable"
    OUTPUT_TRANSFORM_UNAVAILABLE = "output_transform_unavailable"


@dataclass(frozen=True)
class TypedAssessment:
    state: EvidenceState
    gap: GateGap | None

    def __post_init__(self) -> None:
        if not isinstance(self.state, EvidenceState):
            raise TypeError("typed assessment requires an evidence state")
        if (self.state == EvidenceState.SUPPORTED) != (self.gap is None):
            raise ValueError("supported assessment alone has no named gap")


@dataclass(frozen=True)
class GateCheck:
    code: str
    stage: GateStage
    state: EvidenceState
    gap: GateGap | None = None
    final_review_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("gate check code must not be empty")
        if not isinstance(self.stage, GateStage):
            raise TypeError("gate check requires a typed stage")
        if (self.state == EvidenceState.SUPPORTED) != (self.gap is None):
            raise ValueError("gate check state and typed gap disagree")
        if self.stage == GateStage.CANDIDATE:
            if self.final_review_reason is not None:
                raise ValueError("candidate gate checks cannot own final reasons")
        elif self.stage == GateStage.DECISION:
            if self.state == EvidenceState.SUPPORTED:
                if self.final_review_reason is not None:
                    raise ValueError("supported decision checks have no reason")
            elif not self.final_review_reason:
                raise ValueError("blocking decision checks require a reason")

    @property
    def blocks(self) -> bool:
        return self.state != EvidenceState.SUPPORTED
