from __future__ import annotations

from dataclasses import dataclass

from ..configuration.grid import frame_grid_search_prior
from ..configuration.model import DetectionConfiguration
from ..domain import EvidenceState
from .candidate.assessment.candidate_gate import candidate_gate_assessment
from .candidate.assessment.model import CandidateGateAssessment
from .grid.model import LaneGridSelection, ProtectedCropEnvelope
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
    lane_selections: tuple[LaneGridSelection, ...]
    protected_envelopes_by_lane: tuple[
        tuple[ProtectedCropEnvelope, ...], ...
    ]
    transform_assessment: OutputTransformAssessment
    selected_count: int | None
    gate: CandidateGateAssessment

    def __post_init__(self) -> None:
        if len(self.lane_selections) != len(
            self.protected_envelopes_by_lane
        ):
            raise ValueError("candidate lane selection/protection order disagrees")
        selected = tuple(
            selection.selected_proposal
            for selection in self.lane_selections
        )
        if self.selected_count is not None:
            if any(item is None for item in selected):
                raise ValueError("selected count requires every canonical lane")
            if self.selected_count != sum(
                item.count for item in selected if item is not None
            ):
                raise ValueError("selected count must sum canonical lane counts")
        if self.gate.passed and self.selected_count is None:
            raise ValueError(
                "a passing candidate Gate requires a selected output"
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


def _maximum_lane_count(
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration,
    lane,
) -> int:
    profile = lane.scan_canvas.selected_profile
    if profile is None:
        return 0
    if configuration.physical_spec.layout.kind == "dual_lane":
        parent_capacity = next(
            (
                fit.maximum_frame_count
                for fit in profile.format_fits
                if fit.format_id == configuration.physical_spec.format_id
            ),
            0,
        )
        return parent_capacity // configuration.physical_spec.layout.lane_count
    return next(
        (
            fit.maximum_frame_count
            for fit in profile.format_fits
            if fit.format_id == lane_configuration.physical_spec.format_id
        ),
        0,
    )


def choose_detection(
    workspace: DetectionWorkspace,
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration | None,
) -> BoundedSafeCropCandidate:
    effective_lane_configuration = lane_configuration or configuration
    lane_selections: list[LaneGridSelection] = []
    protected_by_lane: list[tuple[ProtectedCropEnvelope, ...]] = []
    for lane, separator_field in zip(
        workspace.source_core.lanes,
        workspace.separator_fields,
        strict=True,
    ):
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
            effective_lane_configuration.count_request,
            effective_lane_configuration.physical_spec.aperture_components,
            priors,
            _maximum_lane_count(
                configuration,
                effective_lane_configuration,
                lane,
            ),
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
    selected_count = (
        sum(
            item.selected_proposal.count
            for item in lane_selections
            if item.selected_proposal is not None
        )
        if all_selected
        else None
    )
    selected_proposals = tuple(
        item.selected_proposal
        for item in lane_selections
        if item.selected_proposal is not None
    )
    protection_state = (
        EvidenceState.SUPPORTED
        if all_selected
        and all(
            len(protected) == proposal.count
            for protected, proposal in zip(
                protected_by_lane,
                selected_proposals,
                strict=True,
            )
        )
        else EvidenceState.UNAVAILABLE
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
        frame_count_state=_aggregate_state(
            tuple(item.frame_count_state for item in lane_selections)
        ),
        slot_ordinal_state=_aggregate_state(
            tuple(item.ordinal_state for item in selected_proposals)
        ),
        slot_ownership_state=_aggregate_state(
            tuple(item.ownership_state for item in selected_proposals)
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
        lane_selections=tuple(lane_selections),
        protected_envelopes_by_lane=tuple(protected_by_lane),
        transform_assessment=transform,
        selected_count=selected_count,
        gate=gate,
    )
