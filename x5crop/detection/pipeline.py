from __future__ import annotations

from dataclasses import dataclass

from ..configuration.grid import frame_grid_search_prior
from ..configuration.model import DetectionConfiguration, FrameCountMode
from ..domain import EvidenceState
from .candidate.assessment.candidate_gate import candidate_gate_assessment
from .candidate.assessment.model import CandidateGateAssessment
from .grid.model import (
    LaneGridSelection,
    OutputSlotIdentity,
    ProtectedCropEnvelope,
    ResolvedOutputSlots,
)
from .grid.search import search_lane_grid
from .output_geometry import (
    OutputTransformAssessment,
    typed_identity_transform_assessment,
)
from .protection import (
    apply_fixed_output_protection,
    output_protection_spec,
)
from .source_core import SourceCoreEvidence
from .workspace import DetectionWorkspace


@dataclass(frozen=True)
class BoundedSafeCropCandidate:
    source_core: SourceCoreEvidence
    resolved_output_slots: ResolvedOutputSlots | None
    lane_selections: tuple[LaneGridSelection, ...]
    protected_envelopes_by_lane: tuple[
        tuple[ProtectedCropEnvelope, ...], ...
    ]
    transform_assessment: OutputTransformAssessment
    gate: CandidateGateAssessment

    def __post_init__(self) -> None:
        if len(self.lane_selections) != len(
            self.protected_envelopes_by_lane
        ):
            raise ValueError("candidate lane selection/protection order disagrees")
        if self.resolved_output_slots is not None and (
            len(self.resolved_output_slots.lane_output_slot_counts)
            != len(self.source_core.lanes)
        ):
            raise ValueError(
                "resolved output slots must follow canonical source lanes"
            )
        if self.gate.passed and self.resolved_output_slots is None:
            raise ValueError(
                "a passing candidate Gate requires a selected output"
            )

    @property
    def output_slot_identities(self) -> tuple[OutputSlotIdentity, ...]:
        if self.resolved_output_slots is None:
            return ()
        identities: list[OutputSlotIdentity] = []
        global_ordinal = 1
        for lane, lane_count in zip(
            self.source_core.lanes,
            self.resolved_output_slots.lane_output_slot_counts,
            strict=True,
        ):
            for lane_ordinal in range(1, lane_count + 1):
                identities.append(
                    OutputSlotIdentity(
                        global_output_ordinal=global_ordinal,
                        lane_id=lane.domain.lane_id,
                        lane_ordinal=lane_ordinal,
                    )
                )
                global_ordinal += 1
        return tuple(identities)

    @property
    def output_slot_count(self) -> int | None:
        return (
            None
            if self.resolved_output_slots is None
            else self.resolved_output_slots.output_slot_count
        )


def _aggregate_state(
    states: tuple[EvidenceState, ...],
    *,
    empty: EvidenceState = EvidenceState.UNAVAILABLE,
) -> EvidenceState:
    if not states:
        return empty
    if any(state == EvidenceState.CONTRADICTED for state in states):
        return EvidenceState.CONTRADICTED
    if all(state == EvidenceState.SUPPORTED for state in states):
        return EvidenceState.SUPPORTED
    if all(state == EvidenceState.NOT_APPLICABLE for state in states):
        return EvidenceState.NOT_APPLICABLE
    return EvidenceState.UNAVAILABLE


def _profile_capacity(
    configuration: DetectionConfiguration,
    lane,
) -> int:
    profile = lane.scan_canvas.selected_profile
    if profile is None:
        return 0
    return next(
        (
            fit.maximum_frame_count
            for fit in profile.format_fits
            if fit.format_id == configuration.physical_spec.format_id
        ),
        0,
    )


def _resolve_output_slots(
    configuration: DetectionConfiguration,
    source_core: SourceCoreEvidence,
) -> ResolvedOutputSlots | None:
    if not source_core.lanes:
        return None
    request = configuration.count_request
    if configuration.physical_spec.layout.kind == "dual_lane":
        parent_capacity = _profile_capacity(
            configuration,
            source_core.lanes[0],
        )
        requested = request.authoritative_count
        if (
            requested is None
            or requested != parent_capacity
            or requested % len(source_core.lanes)
        ):
            return None
        lane_count = requested // len(source_core.lanes)
        return ResolvedOutputSlots(
            tuple(lane_count for _lane in source_core.lanes)
        )
    capacity = _profile_capacity(
        configuration,
        source_core.lanes[0],
    )
    if capacity <= 0:
        return None
    count = (
        capacity
        if request.mode == FrameCountMode.AUTO
        else request.authoritative_count
    )
    if count is None or count <= 0 or count > capacity:
        return None
    return ResolvedOutputSlots((count,))


def choose_detection(
    workspace: DetectionWorkspace,
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration | None,
) -> BoundedSafeCropCandidate:
    effective_lane_configuration = lane_configuration or configuration
    resolved_output_slots = _resolve_output_slots(
        configuration,
        workspace.source_core,
    )
    lane_selections: list[LaneGridSelection] = []
    protected_by_lane: list[tuple[ProtectedCropEnvelope, ...]] = []
    lane_counts = (
        ()
        if resolved_output_slots is None
        else resolved_output_slots.lane_output_slot_counts
    )
    lane_inputs = (
        ()
        if resolved_output_slots is None
        else zip(
            workspace.source_core.lanes,
            workspace.separator_fields,
            lane_counts,
            strict=True,
        )
    )
    for lane, separator_field, output_slot_count in lane_inputs:
        priors = tuple(
            frame_grid_search_prior(
                effective_lane_configuration.physical_spec.format_id,
                effective_lane_configuration.strip_mode,
                component.long_axis_mm,
            )
            for component in (
                effective_lane_configuration.physical_spec.aperture_components
            )
        )
        selection = search_lane_grid(
            lane,
            separator_field,
            output_slot_count,
            effective_lane_configuration.physical_spec.aperture_components,
            priors,
        )
        lane_selections.append(selection)
        proposal = selection.selected_proposal
        protected_by_lane.append(
            ()
            if proposal is None
            else apply_fixed_output_protection(
                lane,
                proposal.safe_envelopes,
                output_protection_spec(
                    effective_lane_configuration.physical_spec.format_id
                ),
            )
        )

    transform = typed_identity_transform_assessment(
        workspace.source_gray.shape[1],
        workspace.source_gray.shape[0],
    )
    all_selected = bool(lane_selections) and all(
        item.selected_proposal is not None for item in lane_selections
    )
    selected_proposals = tuple(
        item.selected_proposal
        for item in lane_selections
        if item.selected_proposal is not None
    )
    protection_state = (
        EvidenceState.NOT_APPLICABLE
        if resolved_output_slots is None
        else EvidenceState.SUPPORTED
        if all_selected
        and all(
            len(protected) == lane_count
            and proposal.output_slot_count == lane_count
            for protected, proposal, lane_count in zip(
                protected_by_lane,
                selected_proposals,
                resolved_output_slots.lane_output_slot_counts,
                strict=True,
            )
        )
        else EvidenceState.CONTRADICTED
    )
    output_slot_count_state = (
        EvidenceState.NOT_APPLICABLE
        if resolved_output_slots is None
        else EvidenceState.SUPPORTED
        if all_selected
        and all(
            proposal.output_slot_count == lane_count
            and len(proposal.slots) == lane_count
            for proposal, lane_count in zip(
                selected_proposals,
                resolved_output_slots.lane_output_slot_counts,
                strict=True,
            )
        )
        else EvidenceState.CONTRADICTED
    )
    gate = candidate_gate_assessment(
        scan_canvas_state=workspace.source_core.scan_canvas_state,
        source_content_state=workspace.source_core.content_state,
        grid_search_coverage_state=_aggregate_state(
            tuple(
                item.grid_search_coverage_state
                for item in lane_selections
            )
        ),
        output_slot_count_state=output_slot_count_state,
        slot_ordinal_state=_aggregate_state(
            tuple(item.ordinal_state for item in lane_selections)
        ),
        slot_ownership_state=_aggregate_state(
            tuple(item.ownership_state for item in lane_selections)
        ),
        known_content_containment_state=_aggregate_state(
            tuple(item.containment_state for item in selected_proposals)
        ),
        source_lane_geometry_state=_aggregate_state(
            tuple(item.geometry_state for item in selected_proposals)
        ),
        output_protection_state=protection_state,
        output_transform_state=transform.state,
    )
    return BoundedSafeCropCandidate(
        source_core=workspace.source_core,
        resolved_output_slots=resolved_output_slots,
        lane_selections=tuple(lane_selections),
        protected_envelopes_by_lane=tuple(protected_by_lane),
        transform_assessment=transform,
        gate=gate,
    )
