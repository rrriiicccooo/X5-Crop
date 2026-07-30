from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import Box, EvidenceState, FiniteInterval
from ..evidence.separator import (
    SeparatorCorridorObservation,
    SeparatorObservationWorkStatistics,
)


P_MAX = 6
O_MAX = 2
K_MAX = 3


class PlacementSeedKind(str, Enum):
    FULL_LEADING = "full_leading"
    FULL_TRAILING = "full_trailing"
    CENTERED = "centered"
    POSITIVE_CONTENT = "positive_content"


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


class GridOmissionScope(str, Enum):
    PLACEMENT_SEED = "placement_seed"
    OBSERVED_CORRIDOR = "observed_corridor"
    DP_FRONTIER = "dp_frontier"


@dataclass(frozen=True)
class ResolvedOutputSlots:
    lane_output_slot_counts: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.lane_output_slot_counts or any(
            value <= 0 for value in self.lane_output_slot_counts
        ):
            raise ValueError(
                "resolved output slots require one positive count per lane"
            )

    @property
    def output_slot_count(self) -> int:
        return sum(self.lane_output_slot_counts)


@dataclass(frozen=True)
class OutputSlotIdentity:
    global_output_ordinal: int
    lane_id: str
    lane_ordinal: int

    def __post_init__(self) -> None:
        if (
            self.global_output_ordinal <= 0
            or not self.lane_id
            or self.lane_ordinal <= 0
        ):
            raise ValueError("output slot identity is invalid")


@dataclass(frozen=True)
class PlacementSeed:
    seed_id: str
    kind: PlacementSeedKind
    origin_px: FiniteInterval
    scalar_ordering_score: float
    provenance: str

    def __post_init__(self) -> None:
        if (
            not self.seed_id
            or not isinstance(self.kind, PlacementSeedKind)
            or not math.isfinite(self.scalar_ordering_score)
            or self.provenance
            not in {
                "full_margin_model",
                "blank_center_model",
                "positive_content_placement",
            }
        ):
            raise ValueError("placement seed is invalid")
        if (
            self.kind == PlacementSeedKind.POSITIVE_CONTENT
        ) != (self.provenance == "positive_content_placement"):
            raise ValueError("placement seed provenance disagrees with its kind")


@dataclass(frozen=True)
class GridCorridorCandidate:
    candidate_id: str
    source_candidate_ids: tuple[str, ...]
    corridor_index: int
    kind: GridCandidateKind
    previous_photo_end_px: FiniteInterval
    next_photo_start_px: FiniteInterval
    observation: SeparatorCorridorObservation | None
    residual_mm: float

    def __post_init__(self) -> None:
        if (
            not self.candidate_id
            or not self.source_candidate_ids
            or tuple(sorted(set(self.source_candidate_ids)))
            != self.source_candidate_ids
            or self.corridor_index <= 0
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
        if (
            self.lane_ordinal == 1
            and self.previous_interaction != SlotInteraction.NOT_APPLICABLE
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
class GridOmittedAlternative:
    alternative_id: str
    absorbing_equivalence_class_id: str | None

    def __post_init__(self) -> None:
        if not self.alternative_id:
            raise ValueError("omitted alternative requires a stable identity")

    @property
    def absorbed(self) -> bool:
        return self.absorbing_equivalence_class_id is not None


@dataclass(frozen=True)
class GridOmissionSummary:
    scope_id: str
    scope: GridOmissionScope
    lane_id: str
    component_id: str
    seed_id: str | None
    corridor_ordinal: int | None
    discovered_count: int
    retained_count: int
    omitted_alternatives: tuple[GridOmittedAlternative, ...]

    def __post_init__(self) -> None:
        if (
            not self.scope_id
            or not isinstance(self.scope, GridOmissionScope)
            or not self.lane_id
            or not self.component_id
            or self.discovered_count < 0
            or self.retained_count < 0
            or self.retained_count > self.discovered_count
            or len(self.omitted_alternatives)
            != self.discovered_count - self.retained_count
        ):
            raise ValueError("Grid omission summary is invalid")
        if self.scope == GridOmissionScope.PLACEMENT_SEED:
            if self.seed_id is not None or self.corridor_ordinal is not None:
                raise ValueError(
                    "placement-seed scope cannot claim one retained seed"
                )
        elif self.seed_id is None:
            raise ValueError("corridor/frontier scope requires a seed identity")
        if (
            self.scope == GridOmissionScope.OBSERVED_CORRIDOR
            and (self.corridor_ordinal is None or self.corridor_ordinal <= 0)
        ):
            raise ValueError("observed-corridor scope requires an ordinal")
        if (
            self.scope == GridOmissionScope.DP_FRONTIER
            and (self.corridor_ordinal is None or self.corridor_ordinal <= 0)
        ):
            raise ValueError("DP-frontier scope requires an ordinal")
        alternative_ids = tuple(
            item.alternative_id for item in self.omitted_alternatives
        )
        if len(set(alternative_ids)) != len(alternative_ids):
            raise ValueError("omitted alternative identities must be unique")

    @property
    def omitted_count(self) -> int:
        return len(self.omitted_alternatives)

    @property
    def absorbed_count(self) -> int:
        return sum(item.absorbed for item in self.omitted_alternatives)

    @property
    def unresolved_outcome_count(self) -> int:
        return self.omitted_count - self.absorbed_count


@dataclass(frozen=True)
class FrameGridWorkStatistics:
    lane_id: str
    component_id: str
    output_slot_count: int
    seed_count: int
    observed_candidate_count: int
    model_candidate_count: int
    candidate_builds: int
    dp_states: int
    dp_transitions: int
    state_upper: int
    transition_upper: int
    retained_proposal_count: int
    omission_summaries: tuple[GridOmissionSummary, ...]
    budget_exhausted: bool

    def __post_init__(self) -> None:
        counts = (
            self.output_slot_count,
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
        if any(value < 0 for value in counts) or self.output_slot_count <= 0:
            raise ValueError("Grid work statistics cannot be negative")
        if (
            self.seed_count > P_MAX
            or self.dp_states > self.state_upper
            or self.dp_transitions > self.transition_upper
        ):
            raise ValueError("Grid work exceeded a structural upper bound")
        if any(
            summary.lane_id != self.lane_id
            or summary.component_id != self.component_id
            for summary in self.omission_summaries
        ):
            raise ValueError("Grid work owns only its omission scopes")

    @property
    def search_incomplete(self) -> bool:
        return self.budget_exhausted or any(
            summary.omitted_count for summary in self.omission_summaries
        )

    @property
    def omitted_outcome_risk(self) -> bool:
        return self.budget_exhausted or any(
            summary.unresolved_outcome_count
            for summary in self.omission_summaries
        )

    @staticmethod
    def state_limit(output_slot_count: int) -> int:
        return P_MAX * K_MAX * max(0, output_slot_count - 1)

    @staticmethod
    def transition_limit(output_slot_count: int) -> int:
        if output_slot_count <= 1:
            return 0
        return P_MAX * (
            K_MAX + K_MAX * K_MAX * max(0, output_slot_count - 2)
        )


@dataclass(frozen=True)
class FrameGridProposal:
    proposal_id: str
    lane_id: str
    component_id: str
    output_slot_count: int
    seed: PlacementSeed
    corridor_candidates: tuple[GridCorridorCandidate, ...]
    anchor_class: GridAnchorClass
    slots: tuple[FrameSlot, ...]
    safe_envelopes: tuple[SafeCropEnvelope, ...]
    content_assignment_signature: tuple[tuple[str, int], ...]
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
            or self.output_slot_count <= 0
            or len(self.slots) != self.output_slot_count
            or len(self.safe_envelopes) != self.output_slot_count
            or len(self.corridor_candidates)
            != max(0, self.output_slot_count - 1)
            or tuple(slot.lane_ordinal for slot in self.slots)
            != tuple(range(1, self.output_slot_count + 1))
            or tuple(item.lane_ordinal for item in self.safe_envelopes)
            != tuple(range(1, self.output_slot_count + 1))
            or self.observed_boundary_count < 0
            or self.two_sided_slot_count < 0
            or self.endpoint_support_count not in {0, 1, 2}
            or self.model_only_boundary_count < 0
            or not math.isfinite(self.residual_mm)
            or self.residual_mm < 0.0
            or not math.isfinite(self.scalar_ordering_score)
        ):
            raise ValueError("frame Grid proposal is invalid")
        if self.output_slot_count == 1:
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


@dataclass(frozen=True)
class FrameGridEquivalenceClass:
    equivalence_class_id: str
    member_proposal_ids: tuple[str, ...]
    merged_proposal: FrameGridProposal

    def __post_init__(self) -> None:
        if (
            not self.equivalence_class_id
            or not self.member_proposal_ids
            or tuple(sorted(set(self.member_proposal_ids)))
            != self.member_proposal_ids
            or self.merged_proposal.proposal_id
            not in {
                self.equivalence_class_id,
                *self.member_proposal_ids,
            }
        ):
            raise ValueError("Grid equivalence class is invalid")


@dataclass(frozen=True)
class LaneGridSelection:
    lane_id: str
    proposal_classes: tuple[FrameGridEquivalenceClass, ...]
    selected_proposal: FrameGridProposal | None
    work_by_component: tuple[FrameGridWorkStatistics, ...]
    separator_work_by_component: tuple[
        SeparatorObservationWorkStatistics, ...
    ]
    grid_search_coverage_state: EvidenceState
    ordinal_state: EvidenceState
    ownership_state: EvidenceState
    selection_reason: str

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or (
                not self.separator_work_by_component
                and self.selection_reason != "no_valid_proposal"
            )
            or self.selection_reason
            not in {
                "unique_output_equivalence_class",
                "non_equivalent_alternatives",
                "omitted_outcome_unresolved",
                "no_valid_proposal",
            }
        ):
            raise ValueError("lane Grid selection is invalid")
        class_ids = tuple(
            item.equivalence_class_id for item in self.proposal_classes
        )
        if len(set(class_ids)) != len(class_ids):
            raise ValueError("Grid equivalence class identities must be unique")
        selected_classes = tuple(
            item
            for item in self.proposal_classes
            if item.merged_proposal is self.selected_proposal
        )
        if (self.selected_proposal is not None) != (len(selected_classes) == 1):
            raise ValueError(
                "selected proposal must be the unique selected equivalence class"
            )
        if (
            self.selection_reason == "unique_output_equivalence_class"
        ) != (self.selected_proposal is not None):
            raise ValueError("lane selection reason and proposal disagree")
        if self.omitted_outcome_risk and (
            self.grid_search_coverage_state != EvidenceState.CONTRADICTED
        ):
            raise ValueError("outcome-changing omissions must block coverage")

    @property
    def omission_summaries(self) -> tuple[GridOmissionSummary, ...]:
        return tuple(
            summary
            for work in self.work_by_component
            for summary in work.omission_summaries
        )

    @property
    def omitted_outcome_risk(self) -> bool:
        return any(item.omitted_outcome_risk for item in self.work_by_component)
