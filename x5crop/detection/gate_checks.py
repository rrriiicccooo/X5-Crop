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
    COMPLETE_CHAIN_UNAVAILABLE = "complete_chain_unavailable"
    PRODUCER_BOUND_EXCEEDED = "producer_bound_exceeded"
    SHARED_STRIP_DIRECTION_UNAVAILABLE = "shared_strip_direction_unavailable"
    SHARED_STRIP_DIRECTION_NONUNIQUE = "shared_strip_direction_nonunique"
    SOURCE_SCAN_GEOMETRY_UNAVAILABLE = "source_scan_geometry_unavailable"
    PLACEMENT_UNRESOLVED = "placement_unresolved"
    SEQUENCE_AUTHORITY_UNAVAILABLE = "sequence_authority_unavailable"
    CROSS_AUTHORITY_UNAVAILABLE = "cross_authority_unavailable"
    SHARED_AUTHORITY_UNAVAILABLE = "shared_authority_unavailable"
    CONTENT_VETO_REJECTED = "content_veto_rejected"
    LOCAL_ADVANCE_UNRESOLVED = "local_advance_unresolved"
    SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED = "slot_ordinal_assignment_unresolved"
    SOURCE_LANE_AUTHORITY_INVALID = "source_lane_authority_invalid"
    SELECTED_PLACEMENT_CONTAINMENT_UNAVAILABLE = (
        "selected_placement_containment_unavailable"
    )
    DIRECT_USE_BUDGET_EXCEEDED = "direct_use_budget_exceeded"
    DIRECT_USE_BUDGET_UNAVAILABLE = "direct_use_budget_unavailable"
    OUTPUT_TRANSFORM_UNAVAILABLE = "output_transform_unavailable"


# A check is evaluated only after every fact it consumes is supported.  This
# is a causal execution graph, not a list of extra reasons.  Debug views may
# still show the underlying authority facts, but Gate reports only the first
# physical reason that stopped the production path.
GATE_CHECK_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "source_scan_geometry": (
        "scan_canvas_authority",
        "observation_completeness",
    ),
    "complete_chain": (
        "output_slot_count",
        "observation_completeness",
        "source_scan_geometry",
        "producer_coverage",
    ),
    "content_protection": ("complete_chain",),
    "selected_placement": (
        "complete_chain",
        "content_protection",
        "local_advance_authority",
    ),
    "shared_strip_direction": (
        "source_scan_geometry",
        "selected_placement",
    ),
    "sequence_authority": ("selected_placement",),
    "cross_authority": ("selected_placement",),
    "shared_authority": ("selected_placement",),
    "slot_ordinal_assignment": ("complete_chain",),
    "selected_only_envelope": (
        "selected_placement",
        "source_lane_authority",
    ),
    "direct_use_budget": ("selected_only_envelope",),
    "transform_sampling": (
        "selected_placement",
        "source_lane_authority",
    ),
}


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
    evaluated: bool = True

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("gate check code must not be empty")
        if not isinstance(self.stage, GateStage):
            raise TypeError("gate check requires a typed stage")
        if not self.evaluated:
            if (
                self.state != EvidenceState.UNAVAILABLE
                or self.gap is not None
                or self.final_review_reason is not None
            ):
                raise ValueError(
                    "unevaluated gate checks carry no gap or final reason"
                )
            return
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
        return self.evaluated and self.state != EvidenceState.SUPPORTED
