from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import Box, EvidenceState, FiniteInterval, ObservationId
from ..evidence.separator import (
    SeparatorCorridorObservation,
    SeparatorObservationWorkStatistics,
)


P_MAX = 6
O_MAX = 2
K_MAX = 3
G_MAX = 3

DOMINANCE_DIMENSION_CODES = (
    "endpoint_support",
    "two_sided_slot_balance",
    "observed_boundary_balance",
    "internal_corridor_observed_support",
    "content_assignment_and_authority",
)
DOMINANCE_PARTICIPATING_CODES = frozenset(
    {
        "two_sided_slot_balance",
        "observed_boundary_balance",
        "content_assignment_and_authority",
    }
)


class PlacementSeedKind(str, Enum):
    OBSERVED_START = "observed_start"
    OBSERVED_END = "observed_end"
    FULL_LEADING = "full_leading"
    FULL_TRAILING = "full_trailing"
    CENTERED = "centered"


class GridCandidateKind(str, Enum):
    OBSERVED_EDGE_PAIR = "observed_edge_pair"
    OBSERVED_ONE_SIDED = "observed_one_sided"
    MODEL_ONLY = "model_only"


class GridAnchorClass(str, Enum):
    ZERO = "0"
    ONE = "1"
    TWO_PLUS = "2+"


class SlotInteraction(str, Enum):
    SEPARATED = "separated"
    CONTACT = "contact"
    OVERLAP = "overlap"
    NOT_APPLICABLE = "not_applicable"


class DominanceRelation(str, Enum):
    LEFT_DOMINATES = "left_dominates"
    RIGHT_DOMINATES = "right_dominates"
    EQUIVALENT = "equivalent"
    INCOMPARABLE = "incomparable"


class DominanceDimensionRelation(str, Enum):
    LEFT_BETTER = "left_better"
    RIGHT_BETTER = "right_better"
    EQUIVALENT = "equivalent"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class PlacementSeed:
    seed_id: str
    kind: PlacementSeedKind
    origin_px: FiniteInterval
    scalar_ordering_score: float
    source_line_id: ObservationId | None

    def __post_init__(self) -> None:
        if (
            not self.seed_id
            or not isinstance(self.kind, PlacementSeedKind)
            or not math.isfinite(self.scalar_ordering_score)
        ):
            raise ValueError("placement seed is invalid")
        observed = self.kind in {
            PlacementSeedKind.OBSERVED_START,
            PlacementSeedKind.OBSERVED_END,
        }
        if observed != (self.source_line_id is not None):
            raise ValueError("observed placement seeds require one source line")


@dataclass(frozen=True)
class GridCorridorCandidate:
    corridor_index: int
    kind: GridCandidateKind
    previous_photo_end_px: FiniteInterval
    next_photo_start_px: FiniteInterval
    observation: SeparatorCorridorObservation | None
    residual_mm: float

    def __post_init__(self) -> None:
        if (
            self.corridor_index <= 0
            or not isinstance(self.kind, GridCandidateKind)
            or not math.isfinite(self.residual_mm)
            or self.residual_mm < 0.0
        ):
            raise ValueError("Grid corridor candidate is invalid")
        if (
            self.kind == GridCandidateKind.MODEL_ONLY
        ) != (self.observation is None):
            raise ValueError("only model-only corridors omit observations")


@dataclass(frozen=True)
class FrameSlot:
    lane_id: str
    lane_ordinal: int
    start_px: FiniteInterval
    end_px: FiniteInterval
    appearance_state: EvidenceState
    previous_interaction: SlotInteraction
    next_interaction: SlotInteraction

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or self.lane_ordinal <= 0
            or self.end_px.minimum <= self.start_px.maximum
            or not isinstance(self.appearance_state, EvidenceState)
            or not isinstance(self.previous_interaction, SlotInteraction)
            or not isinstance(self.next_interaction, SlotInteraction)
        ):
            raise ValueError("frame slot geometry is invalid")
        if self.lane_ordinal == 1 and (
            self.previous_interaction != SlotInteraction.NOT_APPLICABLE
        ):
            raise ValueError("first slot has no previous interaction")


@dataclass(frozen=True)
class SafeCropEnvelope:
    lane_id: str
    lane_ordinal: int
    work_box: Box
    provenance: str

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or self.lane_ordinal <= 0
            or not self.work_box.valid()
            or self.provenance
            not in {
                "observed_and_model_outward_union",
                "model_outward_union",
            }
        ):
            raise ValueError("safe crop envelope is invalid")


@dataclass(frozen=True)
class ProtectedCropEnvelope:
    lane_id: str
    lane_ordinal: int
    safe_work_box: Box
    protected_work_box: Box
    saturated_sides: tuple[str, ...]
    long_axis_protection_mm: float
    short_axis_protection_mm: float

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or self.lane_ordinal <= 0
            or not self.safe_work_box.valid()
            or not self.protected_work_box.valid()
            or self.long_axis_protection_mm <= 0.0
            or self.short_axis_protection_mm <= 0.0
            or any(
                side not in {"left", "top", "right", "bottom"}
                for side in self.saturated_sides
            )
            or len(set(self.saturated_sides)) != len(self.saturated_sides)
        ):
            raise ValueError("protected crop envelope is invalid")
        if (
            self.protected_work_box.left > self.safe_work_box.left
            or self.protected_work_box.top > self.safe_work_box.top
            or self.protected_work_box.right < self.safe_work_box.right
            or self.protected_work_box.bottom < self.safe_work_box.bottom
        ):
            raise ValueError("fixed protection cannot shrink a safe envelope")


@dataclass(frozen=True)
class FrameGridWorkStatistics:
    lane_id: str
    component_id: str
    count: int
    seed_count: int
    observed_candidate_count: int
    model_candidate_count: int
    candidate_builds: int
    dp_states: int
    dp_transitions: int
    state_upper: int
    transition_upper: int
    retained_proposal_count: int
    search_incomplete: bool
    budget_exhausted: bool
    omitted_outcome_risk: bool

    def __post_init__(self) -> None:
        counts = (
            self.count,
            self.seed_count,
            self.observed_candidate_count,
            self.model_candidate_count,
            self.candidate_builds,
            self.dp_states,
            self.dp_transitions,
            self.state_upper,
            self.transition_upper,
            self.retained_proposal_count,
        )
        if any(value < 0 for value in counts) or self.count <= 0:
            raise ValueError("Grid work statistics cannot be negative")
        if (
            self.seed_count > P_MAX
            or self.dp_states > self.state_upper
            or self.dp_transitions > self.transition_upper
        ):
            raise ValueError("Grid work exceeded a structural upper bound")
        if self.budget_exhausted and not self.search_incomplete:
            raise ValueError("budget exhaustion must remain diagnostic incomplete")
        if self.omitted_outcome_risk and not self.search_incomplete:
            raise ValueError(
                "omitted outcome risk requires a structurally incomplete search"
            )

    @staticmethod
    def state_limit(count: int) -> int:
        return P_MAX * K_MAX * max(0, count - 1)

    @staticmethod
    def transition_limit(count: int) -> int:
        if count <= 1:
            return 0
        return P_MAX * (K_MAX + K_MAX * K_MAX * max(0, count - 2))


@dataclass(frozen=True)
class FrameGridProposal:
    proposal_id: str
    lane_id: str
    component_id: str
    count: int
    seed: PlacementSeed
    corridor_candidates: tuple[GridCorridorCandidate, ...]
    anchor_class: GridAnchorClass
    slots: tuple[FrameSlot, ...]
    safe_envelopes: tuple[SafeCropEnvelope, ...]
    observed_boundary_count: int
    two_sided_slot_count: int
    endpoint_support_count: int
    model_only_boundary_count: int
    residual_mm: float
    scalar_ordering_score: float
    geometry_state: EvidenceState
    ordinal_state: EvidenceState
    ownership_state: EvidenceState
    containment_state: EvidenceState

    def __post_init__(self) -> None:
        if (
            not self.proposal_id
            or not self.lane_id
            or not self.component_id
            or self.count <= 0
            or len(self.slots) != self.count
            or len(self.safe_envelopes) != self.count
            or len(self.corridor_candidates) != max(0, self.count - 1)
            or tuple(slot.lane_ordinal for slot in self.slots)
            != tuple(range(1, self.count + 1))
            or tuple(item.lane_ordinal for item in self.safe_envelopes)
            != tuple(range(1, self.count + 1))
            or self.observed_boundary_count < 0
            or self.two_sided_slot_count < 0
            or self.endpoint_support_count not in {0, 1, 2}
            or self.model_only_boundary_count < 0
            or not math.isfinite(self.residual_mm)
            or self.residual_mm < 0.0
            or not math.isfinite(self.scalar_ordering_score)
        ):
            raise ValueError("frame Grid proposal is invalid")
        if self.count == 1:
            if self.anchor_class != GridAnchorClass.ZERO:
                raise ValueError("count-one internal corridor is not applicable")
        else:
            observed = sum(
                candidate.kind != GridCandidateKind.MODEL_ONLY
                for candidate in self.corridor_candidates
            )
            expected_anchor = (
                GridAnchorClass.ZERO
                if observed == 0
                else GridAnchorClass.ONE
                if observed == 1
                else GridAnchorClass.TWO_PLUS
            )
            if self.anchor_class != expected_anchor:
                raise ValueError("proposal anchor class disagrees with corridors")

    @property
    def dominance_dimensions(
        self,
    ) -> tuple[int | tuple[int, int] | None, ...]:
        return (
            self.endpoint_support_count,
            (
                2 * self.two_sided_slot_count - self.count,
                self.two_sided_slot_count,
            ),
            self.observed_boundary_count - self.model_only_boundary_count,
            (
                None
                if self.count == 1
                else sum(
                    candidate.kind != GridCandidateKind.MODEL_ONLY
                    for candidate in self.corridor_candidates
                )
            ),
            int(
                self.ordinal_state != EvidenceState.CONTRADICTED
                and self.ownership_state != EvidenceState.CONTRADICTED
                and self.containment_state != EvidenceState.CONTRADICTED
                and self.geometry_state != EvidenceState.CONTRADICTED
            ),
        )


@dataclass(frozen=True)
class FrameCountDominanceDimension:
    code: str
    left_value: int | tuple[int, int] | None
    right_value: int | tuple[int, int] | None
    relation: DominanceDimensionRelation
    participates_in_dominance: bool

    def __post_init__(self) -> None:
        if self.code not in DOMINANCE_DIMENSION_CODES:
            raise ValueError("unknown count-dominance dimension")
        not_applicable = (
            self.left_value is None or self.right_value is None
        )
        if not_applicable != (
            self.relation == DominanceDimensionRelation.NOT_APPLICABLE
        ):
            raise ValueError(
                "count-dominance applicability and relation disagree"
            )
        if self.participates_in_dominance != (
            self.code in DOMINANCE_PARTICIPATING_CODES
        ):
            raise ValueError(
                "current dominance participation policy is not canonical"
            )


@dataclass(frozen=True)
class FrameCountDominanceAssessment:
    left_proposal_id: str
    right_proposal_id: str
    equality_interval_mm: float
    dimensions: tuple[FrameCountDominanceDimension, ...]
    residual_relation: str
    relation: DominanceRelation

    def __post_init__(self) -> None:
        if (
            not self.left_proposal_id
            or not self.right_proposal_id
            or self.left_proposal_id == self.right_proposal_id
            or self.equality_interval_mm <= 0.0
            or tuple(item.code for item in self.dimensions)
            != DOMINANCE_DIMENSION_CODES
            or self.residual_relation not in {
                "left_better",
                "right_better",
                "equal_interval",
            }
            or not isinstance(self.relation, DominanceRelation)
        ):
            raise ValueError("count dominance assessment is invalid")


@dataclass(frozen=True)
class LaneGridSelection:
    lane_id: str
    count_candidates: tuple[int, ...]
    proposals_by_count: tuple[FrameGridProposal, ...]
    dominance_assessments: tuple[FrameCountDominanceAssessment, ...]
    retained_global_proposals: tuple[FrameGridProposal, ...]
    selected_proposal: FrameGridProposal | None
    work_by_count_component: tuple[FrameGridWorkStatistics, ...]
    separator_work_by_component: tuple[
        SeparatorObservationWorkStatistics, ...
    ]
    grid_search_coverage_state: EvidenceState
    frame_count_state: EvidenceState
    selection_reason: str
    global_truncated: bool
    omitted_outcome_risk: bool

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or not self.count_candidates
            or tuple(sorted(set(self.count_candidates))) != self.count_candidates
            or len(self.retained_global_proposals) > G_MAX
            or (
                not self.separator_work_by_component
                and self.selection_reason != "no_valid_proposal"
            )
            or self.selection_reason not in {
                "fixed_or_explicit",
                "unique_non_dominated_count",
                "non_dominated_count_competition",
                "no_valid_proposal",
            }
        ):
            raise ValueError("lane Grid selection is invalid")
        if self.selected_proposal is not None and (
            self.selected_proposal not in self.retained_global_proposals
        ):
            raise ValueError("selected proposal must be globally retained")
        if (
            self.selection_reason
            in {"fixed_or_explicit", "unique_non_dominated_count"}
        ) != (self.selected_proposal is not None):
            raise ValueError("lane selection reason and selected proposal disagree")
        if self.omitted_outcome_risk and (
            self.grid_search_coverage_state != EvidenceState.CONTRADICTED
        ):
            raise ValueError("outcome-changing omissions must block coverage")
