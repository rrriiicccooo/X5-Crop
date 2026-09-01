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
    UNSUPPORTED_DUAL_COUNT = "unsupported_dual_count"
    COMPLETE_PLACEMENT_UNAVAILABLE = "complete_placement_unavailable"
    PRODUCER_BOUND_EXCEEDED = "producer_bound_exceeded"
    SOURCE_SCAN_GEOMETRY_UNAVAILABLE = "source_scan_geometry_unavailable"
    PLACEMENT_UNRESOLVED = "placement_unresolved"
    PHASE_ANCHOR_UNAVAILABLE = "phase_anchor_unavailable"
    GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE = (
        "global_lattice_authority_unavailable"
    )
    CALIBRATED_NOMINAL_GRID_AUTHORITY_UNAVAILABLE = (
        "calibrated_nominal_grid_authority_unavailable"
    )
    NOMINAL_GRID_PHASE_ANCHOR_UNAVAILABLE = (
        "nominal_grid_phase_anchor_unavailable"
    )
    ADJACENCY_OBSERVATION_COVERAGE_INCOMPLETE = (
        "adjacency_observation_coverage_incomplete"
    )
    NOMINAL_GRID_COMPLETE_FRAME_UNOBSERVED = (
        "nominal_grid_complete_frame_unobserved"
    )
    DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE = (
        "direct_role_binding_authority_unavailable"
    )
    DIRECT_ROLE_APERTURE_DOMAIN_UNAVAILABLE = (
        "direct_role_aperture_domain_unavailable"
    )
    SEPARATOR_MATERIAL_CONFLICT = "separator_material_conflict"
    OUTER_FRAME_OBSERVATION_AUTHORITY_UNAVAILABLE = (
        "outer_frame_observation_authority_unavailable"
    )
    SOURCE_FRAME_WIDTH_CONFLICT = "source_frame_width_conflict"
    PHASE_TEMPLATE_MISMATCH = "phase_template_mismatch"
    PHASE_PLACEMENT_AMBIGUOUS = "phase_placement_ambiguous"
    CROSS_AUTHORITY_UNAVAILABLE = "cross_authority_unavailable"
    APERTURE_ASPECT_RATIO_AUTHORITY_UNAVAILABLE = (
        "aperture_aspect_ratio_authority_unavailable"
    )
    APERTURE_ASPECT_RATIO_PHYSICAL_PRIOR_CONFLICT = (
        "aperture_aspect_ratio_physical_prior_conflict"
    )
    APERTURE_ASPECT_RATIO_DIRECT_CONFLICT = (
        "aperture_aspect_ratio_direct_conflict"
    )
    APERTURE_ASPECT_RATIO_BUDGET_EXHAUSTED = (
        "aperture_aspect_ratio_budget_exhausted"
    )
    SHARED_AUTHORITY_UNAVAILABLE = "shared_authority_unavailable"
    CONTENT_VETO_REJECTED = "content_veto_rejected"
    ADJACENCY_RELATION_UNRESOLVED = "adjacency_relation_unresolved"
    ADJACENCY_CONTINUITY_UNRESOLVED = (
        "adjacency_continuity_unresolved"
    )
    ADJACENCY_TOPOLOGY_UNRESOLVED = "adjacency_topology_unresolved"
    DUAL_LANE_NOT_FILLED = "dual_lane_not_filled"
    DUAL_LANE_FILL_UNRESOLVED = "dual_lane_fill_unresolved"
    SOURCE_LANE_AUTHORITY_INVALID = "source_lane_authority_invalid"
    OUTPUT_FOOTPRINT_UNAVAILABLE = "output_footprint_unavailable"
    DIRECT_USE_BUDGET_EXCEEDED = "direct_use_budget_exceeded"
    DIRECT_USE_BUDGET_UNAVAILABLE = "direct_use_budget_unavailable"


class FailureRecovery(str, Enum):
    USER_ACTION = "user_action"
    REMEASURE = "remeasure"
    UNRECOVERABLE = "unrecoverable"


class MinimumMissingFact(str, Enum):
    FORMAT_COMPATIBILITY = "format_compatibility"
    COUNT_AUTHORITY = "count_authority"
    COMPLETE_SCAN_CANVAS = "complete_scan_canvas"
    ABSOLUTE_PHASE_ANCHOR = "absolute_phase_anchor"
    GLOBAL_LATTICE_AUTHORITY = "global_lattice_authority"
    CALIBRATED_NOMINAL_GRID_AUTHORITY = (
        "calibrated_nominal_grid_authority"
    )
    ADJACENCY_OBSERVATION_COVERAGE = "adjacency_observation_coverage"
    DIRECT_ROLE_BINDING_AUTHORITY = "direct_role_binding_authority"
    DIRECT_APERTURE_DOMAIN = "direct_aperture_domain"
    SEPARATOR_MATERIAL_AUTHORITY = "separator_material_authority"
    OUTER_FRAME_OBSERVATION_AUTHORITY = "outer_frame_observation_authority"
    PITCH_CLOSURE = "pitch_closure"
    CROSS_POSITION = "cross_position"
    APERTURE_ASPECT_RATIO_AUTHORITY = "aperture_aspect_ratio_authority"
    REGISTERED_QUERY_COVERAGE = "registered_query_coverage"
    ADJACENCY_RELATION = "adjacency_relation"
    ADJACENCY_CONTINUITY = "adjacency_continuity"
    ADJACENCY_TOPOLOGY = "adjacency_topology"
    UNIQUE_PLACEMENT = "unique_placement"
    CONTENT_SAFE_PLACEMENT = "content_safe_placement"
    DIRECT_USE_PRECISION = "direct_use_precision"
    SOURCE_PHYSICAL_COMPATIBILITY = "source_physical_compatibility"
    FILLED_DUAL_LAYOUT = "filled_dual_layout"


class RecoveryAction(str, Enum):
    CHECK_FORMAT = "check_format"
    CHECK_COUNT = "check_count"
    INCLUDE_COMPLETE_HOLDER = "include_complete_holder"
    RERUN_MEASUREMENT = "rerun_measurement"
    OPEN_DEBUG_ANALYSIS = "open_debug_analysis"
    REVIEW_PLACEMENT = "review_placement"
    RESCAN_SOURCE = "rescan_source"


@dataclass(frozen=True)
class DetectionFailureFact:
    gap: GateGap
    recovery: FailureRecovery
    minimum_missing_fact: MinimumMissingFact
    recommended_action: RecoveryAction
    detail: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.gap, GateGap)
            or not isinstance(self.recovery, FailureRecovery)
            or not isinstance(self.minimum_missing_fact, MinimumMissingFact)
            or not isinstance(self.recommended_action, RecoveryAction)
            or not self.detail
        ):
            raise ValueError("detection failure fact is incomplete")


def failure_fact(
    gap: GateGap,
    *,
    detail: str | None = None,
) -> DetectionFailureFact:
    """Create one canonical recovery fact for a typed geometry gap."""

    recovery, missing, action = {
        GateGap.SCAN_CANVAS_AUTHORITY_UNAVAILABLE: (
            FailureRecovery.USER_ACTION,
            MinimumMissingFact.COMPLETE_SCAN_CANVAS,
            RecoveryAction.INCLUDE_COMPLETE_HOLDER,
        ),
        GateGap.HOLDER_FULL_COUNT_UNRESOLVED: (
            FailureRecovery.USER_ACTION,
            MinimumMissingFact.FORMAT_COMPATIBILITY,
            RecoveryAction.CHECK_FORMAT,
        ),
        GateGap.HOLDER_IDENTITY_UNRESOLVED: (
            FailureRecovery.USER_ACTION,
            MinimumMissingFact.COMPLETE_SCAN_CANVAS,
            RecoveryAction.INCLUDE_COMPLETE_HOLDER,
        ),
        GateGap.OUTPUT_SLOT_COUNT_UNAVAILABLE: (
            FailureRecovery.USER_ACTION,
            MinimumMissingFact.COUNT_AUTHORITY,
            RecoveryAction.CHECK_COUNT,
        ),
        GateGap.UNSUPPORTED_DUAL_COUNT: (
            FailureRecovery.USER_ACTION,
            MinimumMissingFact.COUNT_AUTHORITY,
            RecoveryAction.CHECK_COUNT,
        ),
        GateGap.PRODUCER_BOUND_EXCEEDED: (
            FailureRecovery.REMEASURE,
            MinimumMissingFact.REGISTERED_QUERY_COVERAGE,
            RecoveryAction.RERUN_MEASUREMENT,
        ),
        GateGap.COMPLETE_PLACEMENT_UNAVAILABLE: (
            FailureRecovery.REMEASURE,
            MinimumMissingFact.UNIQUE_PLACEMENT,
            RecoveryAction.OPEN_DEBUG_ANALYSIS,
        ),
        GateGap.SOURCE_SCAN_GEOMETRY_UNAVAILABLE: (
            FailureRecovery.REMEASURE,
            MinimumMissingFact.SOURCE_PHYSICAL_COMPATIBILITY,
            RecoveryAction.RERUN_MEASUREMENT,
        ),
        GateGap.PHASE_ANCHOR_UNAVAILABLE: (
            FailureRecovery.REMEASURE,
            MinimumMissingFact.ABSOLUTE_PHASE_ANCHOR,
            RecoveryAction.RERUN_MEASUREMENT,
        ),
        GateGap.GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE: (
            FailureRecovery.REMEASURE,
            MinimumMissingFact.GLOBAL_LATTICE_AUTHORITY,
            RecoveryAction.OPEN_DEBUG_ANALYSIS,
        ),
        GateGap.CALIBRATED_NOMINAL_GRID_AUTHORITY_UNAVAILABLE: (
            FailureRecovery.REMEASURE,
            MinimumMissingFact.CALIBRATED_NOMINAL_GRID_AUTHORITY,
            RecoveryAction.OPEN_DEBUG_ANALYSIS,
        ),
        GateGap.NOMINAL_GRID_PHASE_ANCHOR_UNAVAILABLE: (
            FailureRecovery.REMEASURE,
            MinimumMissingFact.ABSOLUTE_PHASE_ANCHOR,
            RecoveryAction.RERUN_MEASUREMENT,
        ),
        GateGap.ADJACENCY_OBSERVATION_COVERAGE_INCOMPLETE: (
            FailureRecovery.REMEASURE,
            MinimumMissingFact.ADJACENCY_OBSERVATION_COVERAGE,
            RecoveryAction.OPEN_DEBUG_ANALYSIS,
        ),
        GateGap.NOMINAL_GRID_COMPLETE_FRAME_UNOBSERVED: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.DIRECT_ROLE_BINDING_AUTHORITY,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.DIRECT_ROLE_BINDING_AUTHORITY,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.DIRECT_ROLE_APERTURE_DOMAIN_UNAVAILABLE: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.DIRECT_APERTURE_DOMAIN,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.SEPARATOR_MATERIAL_CONFLICT: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.SEPARATOR_MATERIAL_AUTHORITY,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.OUTER_FRAME_OBSERVATION_AUTHORITY_UNAVAILABLE: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.OUTER_FRAME_OBSERVATION_AUTHORITY,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.SOURCE_FRAME_WIDTH_CONFLICT: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.SOURCE_PHYSICAL_COMPATIBILITY,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.PHASE_TEMPLATE_MISMATCH: (
            FailureRecovery.REMEASURE,
            MinimumMissingFact.PITCH_CLOSURE,
            RecoveryAction.OPEN_DEBUG_ANALYSIS,
        ),
        GateGap.PHASE_PLACEMENT_AMBIGUOUS: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.UNIQUE_PLACEMENT,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.CROSS_AUTHORITY_UNAVAILABLE: (
            FailureRecovery.REMEASURE,
            MinimumMissingFact.CROSS_POSITION,
            RecoveryAction.RERUN_MEASUREMENT,
        ),
        GateGap.APERTURE_ASPECT_RATIO_AUTHORITY_UNAVAILABLE: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.APERTURE_ASPECT_RATIO_AUTHORITY,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.APERTURE_ASPECT_RATIO_PHYSICAL_PRIOR_CONFLICT: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.SOURCE_PHYSICAL_COMPATIBILITY,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.APERTURE_ASPECT_RATIO_DIRECT_CONFLICT: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.SOURCE_PHYSICAL_COMPATIBILITY,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.APERTURE_ASPECT_RATIO_BUDGET_EXHAUSTED: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.DIRECT_USE_PRECISION,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.SHARED_AUTHORITY_UNAVAILABLE: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.SOURCE_PHYSICAL_COMPATIBILITY,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.ADJACENCY_RELATION_UNRESOLVED: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.ADJACENCY_RELATION,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.ADJACENCY_CONTINUITY_UNRESOLVED: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.ADJACENCY_CONTINUITY,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.ADJACENCY_TOPOLOGY_UNRESOLVED: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.ADJACENCY_TOPOLOGY,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.DUAL_LANE_NOT_FILLED: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.FILLED_DUAL_LAYOUT,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.DUAL_LANE_FILL_UNRESOLVED: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.FILLED_DUAL_LAYOUT,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.CONTENT_VETO_REJECTED: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.CONTENT_SAFE_PLACEMENT,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.DIRECT_USE_BUDGET_EXCEEDED: (
            FailureRecovery.REMEASURE,
            MinimumMissingFact.DIRECT_USE_PRECISION,
            RecoveryAction.RERUN_MEASUREMENT,
        ),
        GateGap.PLACEMENT_UNRESOLVED: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.UNIQUE_PLACEMENT,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.SOURCE_LANE_AUTHORITY_INVALID: (
            FailureRecovery.USER_ACTION,
            MinimumMissingFact.COMPLETE_SCAN_CANVAS,
            RecoveryAction.INCLUDE_COMPLETE_HOLDER,
        ),
        GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE: (
            FailureRecovery.UNRECOVERABLE,
            MinimumMissingFact.DIRECT_USE_PRECISION,
            RecoveryAction.REVIEW_PLACEMENT,
        ),
        GateGap.DIRECT_USE_BUDGET_UNAVAILABLE: (
            FailureRecovery.REMEASURE,
            MinimumMissingFact.DIRECT_USE_PRECISION,
            RecoveryAction.RERUN_MEASUREMENT,
        ),
    }[gap]
    return DetectionFailureFact(
        gap=gap,
        recovery=recovery,
        minimum_missing_fact=missing,
        recommended_action=action,
        detail=detail or gap.value,
    )


# A check is evaluated only after every fact it consumes is supported.  This
# is a causal execution graph, not a list of extra reasons.  Debug views may
# still show the underlying authority facts, but Gate reports only the first
# physical reason that stopped the production path.
GATE_CHECK_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "source_scan_geometry": (
        "scan_canvas_authority",
        "observation_completeness",
    ),
    "complete_placement": (
        "output_slot_count",
        "observation_completeness",
        "source_scan_geometry",
        "producer_coverage",
    ),
    "content_protection": ("complete_placement",),
    "selected_placement": (
        "complete_placement",
        "content_protection",
        "adjacency_relation_authority",
    ),
    "dual_lane_fill": ("selected_placement",),
    "selected_output_footprint": (
        "selected_placement",
        "dual_lane_fill",
        "source_lane_authority",
    ),
    "calibrated_nominal_grid_authority": (
        "selected_output_footprint",
    ),
    "direct_use_budget": (
        "selected_output_footprint",
        "calibrated_nominal_grid_authority",
    ),
}


@dataclass(frozen=True)
class TypedAssessment:
    state: EvidenceState
    gap: GateGap | None
    failure: DetectionFailureFact | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, EvidenceState):
            raise TypeError("typed assessment requires an evidence state")
        if (self.state == EvidenceState.SUPPORTED) != (self.gap is None):
            raise ValueError("supported assessment alone has no named gap")
        if self.gap is None:
            if self.failure is not None:
                raise ValueError("supported assessment cannot carry failure")
        elif self.failure is None:
            object.__setattr__(self, "failure", failure_fact(self.gap))
        elif self.failure.gap != self.gap:
            raise ValueError("assessment failure and gap disagree")


@dataclass(frozen=True)
class GateCheck:
    code: str
    stage: GateStage
    state: EvidenceState
    gap: GateGap | None = None
    final_review_reason: str | None = None
    evaluated: bool = True
    failure: DetectionFailureFact | None = None

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
                or self.failure is not None
            ):
                raise ValueError(
                    "unevaluated gate checks carry no gap or final reason"
                )
            return
        if (self.state == EvidenceState.SUPPORTED) != (self.gap is None):
            raise ValueError("gate check state and typed gap disagree")
        if self.gap is None:
            if self.failure is not None:
                raise ValueError("supported gate check cannot carry failure")
        elif self.failure is None:
            object.__setattr__(self, "failure", failure_fact(self.gap))
        elif self.failure.gap != self.gap:
            raise ValueError("gate failure and gap disagree")
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
