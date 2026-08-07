from __future__ import annotations

from dataclasses import dataclass
import math

from ...configuration.model import DetectionConfiguration, FrameCountMode
from ...domain import Box, EvidenceState, FiniteInterval
from ..gate_checks import GateGap, TypedAssessment
from ..output_geometry import (
    OutputTransformAssessment,
    SharedStripDirectionResolution,
    output_transform_assessment,
)
from ..source_core import SourceLaneEvidence
from .corridors import (
    build_sequence_anchor_discovery_domain,
    build_top_bottom_search_corridors,
    combined_frame_measurement_intervals,
    frame_physical_pixel_intervals,
    registered_lane_measurement_queries,
    source_lane_box,
)
from .measurement import measure_registered_queries, track_side_transition_regions
from .model import (
    BoundaryAxis,
    DirectUseBudgetAssessment,
    OutputSlotIdentity,
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryObservation,
    PhotoBoundaryTransition,
    ResolvedOutputSlots,
    SafeCropEnvelope,
    SequenceAnchorDiscoveryDomain,
    SharedStripDirection,
    SideTransitionRegion,
)
from .output import direct_use_budget_assessment, safe_crop_envelope_from_placements
from .protection import minimum_guard_spec
from .template_first import (
    build_lane_template_proposal,
    materialize_source_placements,
    shared_source_direction_classes,
)
from .template_model import (
    FormatPlacement,
    ProvisionalHeightTemplate,
    TemplateLaneInput,
    TemplateLaneProposal,
    TemplateWorkReceipt,
)
from .template_profiles import (
    BasicAxisProfile,
    cross_profile_from_regions,
    sequence_profile_from_regions,
)


@dataclass(frozen=True)
class LaneFormatPlacementReconstruction:
    lane_id: str
    anchor_domain: SequenceAnchorDiscoveryDomain
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...]
    side_transition_regions: tuple[SideTransitionRegion, ...]
    sequence_profile: BasicAxisProfile
    cross_profile: BasicAxisProfile
    raw_top_bottom_observations: tuple[PhotoBoundaryObservation, ...]
    provisional_height_templates: tuple[ProvisionalHeightTemplate, ...]
    direction_classes: tuple[SharedStripDirection, ...]
    retained_placements: tuple[FormatPlacement, ...]
    canonical_placement: FormatPlacement | None
    safe_crop_envelopes: tuple[SafeCropEnvelope, ...]
    direct_use_budget_assessments: tuple[DirectUseBudgetAssessment, ...]
    work: TemplateWorkReceipt

    def __post_init__(self) -> None:
        if not self.lane_id or self.anchor_domain.lane_id != self.lane_id:
            raise ValueError("lane format placement lacks authority")
        if (self.canonical_placement is None) != (not self.retained_placements):
            raise ValueError("canonical placement and retained set disagree")
        if self.canonical_placement is not None and (
            self.canonical_placement not in self.retained_placements
        ):
            raise ValueError("canonical placement is not retained")
        if self.safe_crop_envelopes and (
            self.canonical_placement is None
            or len(self.safe_crop_envelopes)
            != self.canonical_placement.output_slot_count
        ):
            raise ValueError("lane outputs do not cover every format slot")


@dataclass(frozen=True)
class PhotoGeometryDetectionResult:
    resolved_output_slots: ResolvedOutputSlots | None
    lane_reconstructions: tuple[LaneFormatPlacementReconstruction, ...]
    output_slot_identities: tuple[OutputSlotIdentity, ...]
    transform_assessment: OutputTransformAssessment
    assessment_facts: dict[str, TypedAssessment]

    def __post_init__(self) -> None:
        if self.resolved_output_slots is not None and (
            len(self.output_slot_identities)
            != self.resolved_output_slots.output_slot_count
        ):
            raise ValueError("resolved output slots require exact identities")

    @property
    def safe_crop_envelopes(self) -> tuple[SafeCropEnvelope, ...]:
        return tuple(
            geometry
            for lane in self.lane_reconstructions
            for geometry in lane.safe_crop_envelopes
        )

    @property
    def direct_use_budget_assessments(
        self,
    ) -> tuple[DirectUseBudgetAssessment, ...]:
        return tuple(
            assessment
            for lane in self.lane_reconstructions
            for assessment in lane.direct_use_budget_assessments
        )


@dataclass(frozen=True)
class _PreparedLane:
    lane: SourceLaneEvidence
    layout: str
    output_slot_count: int
    measurement_slot_count: int
    width_axis: BoundaryAxis
    height_axis: BoundaryAxis
    width_authority_px: FiniteInterval
    height_authority_px: FiniteInterval
    anchor_domain: SequenceAnchorDiscoveryDomain
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...]
    side_regions: tuple[SideTransitionRegion, ...]
    top_regions: tuple[SideTransitionRegion, ...]
    bottom_regions: tuple[SideTransitionRegion, ...]
    transition_by_id: dict[str, PhotoBoundaryTransition]
    sequence_profile: BasicAxisProfile
    cross_profile: BasicAxisProfile
    proposal: TemplateLaneProposal


def _profile_capacity(
    configuration: DetectionConfiguration,
    lane: SourceLaneEvidence,
) -> int:
    profile = lane.scan_canvas.selected_profile
    if profile is None:
        return 0
    return configuration.physical_spec.maximum_frame_count(profile.profile_id) or 0


def _lane_measurement_capacity(
    configuration: DetectionConfiguration,
    lanes: tuple[SourceLaneEvidence, ...],
    lane: SourceLaneEvidence,
) -> int:
    capacity = _profile_capacity(configuration, lane)
    if configuration.physical_spec.layout.kind == "dual_lane":
        if not lanes or capacity % len(lanes):
            return 0
        return capacity // len(lanes)
    return capacity


def resolve_output_slots(
    configuration: DetectionConfiguration,
    lanes: tuple[SourceLaneEvidence, ...],
) -> ResolvedOutputSlots | None:
    if not lanes:
        return None
    request = configuration.count_request
    if configuration.physical_spec.layout.kind == "dual_lane":
        capacity = _profile_capacity(configuration, lanes[0])
        requested = request.authoritative_count
        if (
            requested is None
            or requested != capacity
            or requested % len(lanes)
        ):
            return None
        return ResolvedOutputSlots(
            tuple(requested // len(lanes) for _lane in lanes)
        )
    capacity = _profile_capacity(configuration, lanes[0])
    requested = (
        capacity
        if request.mode == FrameCountMode.AUTO
        else request.authoritative_count
    )
    if requested is None or requested <= 0 or requested > capacity:
        return None
    return ResolvedOutputSlots((requested,))


def _source_axes(layout: str) -> tuple[BoundaryAxis, BoundaryAxis]:
    if layout == "horizontal":
        return BoundaryAxis.X, BoundaryAxis.Y
    if layout == "vertical":
        return BoundaryAxis.Y, BoundaryAxis.X
    raise ValueError(f"unsupported source layout: {layout}")


def _axis_interval(box: Box, axis: BoundaryAxis) -> FiniteInterval:
    return (
        FiniteInterval(float(box.left), float(box.right - 1))
        if axis == BoundaryAxis.X
        else FiniteInterval(float(box.top), float(box.bottom - 1))
    )


def _coordinate_count(interval: FiniteInterval) -> int:
    return max(1, int(math.floor(interval.maximum) - math.ceil(interval.minimum) + 1))


def _prepare_lane(
    field: PhotoBoundaryMeasurementField,
    lane: SourceLaneEvidence,
    *,
    layout: str,
    output_slot_count: int,
    measurement_slot_count: int,
    configuration: DetectionConfiguration,
) -> _PreparedLane:
    width_axis, height_axis = _source_axes(layout)
    authority = source_lane_box(lane, layout)
    width_authority = _axis_interval(authority, width_axis)
    height_authority = _axis_interval(authority, height_axis)
    scales = lane.scan_canvas.axis_scales
    component_pixels = tuple(
        frame_physical_pixel_intervals(
            component,
            scales.width_axis_px_per_mm,
            scales.height_axis_px_per_mm,
        )
        for component in configuration.physical_spec.frame_components
    )
    combined_pixels = combined_frame_measurement_intervals(component_pixels)
    top_corridor, bottom_corridor = build_top_bottom_search_corridors(
        lane,
        layout=layout,
        aperture_pixels=combined_pixels,
    )
    anchor_domain = build_sequence_anchor_discovery_domain(
        lane,
        layout=layout,
        authoritative_sequence_length=measurement_slot_count,
        aperture_pixels=combined_pixels,
    )
    queries = registered_lane_measurement_queries(
        lane,
        layout=layout,
        aperture_pixels=combined_pixels,
        top_corridor=top_corridor,
        bottom_corridor=bottom_corridor,
        anchor_domain=anchor_domain,
    )
    measurement_sets = measure_registered_queries(field, queries)
    transition_by_id = {
        str(transition.transition_id): transition
        for measurement_set in measurement_sets
        for transition in measurement_set.transitions
    }
    side_regions = track_side_transition_regions(
        measurement_sets[2:],
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
    )
    top_regions = track_side_transition_regions(
        (measurement_sets[0],),
        reference_trace_px=width_authority.center,
        boundary_axis_scale_px_per_mm=scales.height_axis_px_per_mm,
    )
    bottom_regions = track_side_transition_regions(
        (measurement_sets[1],),
        reference_trace_px=width_authority.center,
        boundary_axis_scale_px_per_mm=scales.height_axis_px_per_mm,
    )
    sequence_profile = sequence_profile_from_regions(
        side_regions,
        coordinate_count=_coordinate_count(width_authority),
        transition_by_id=transition_by_id,
    )
    cross_profile = cross_profile_from_regions(
        top_regions,
        bottom_regions,
        coordinate_count=_coordinate_count(height_authority),
        transition_by_id=transition_by_id,
    )
    lane_input = TemplateLaneInput(
        lane_id=lane.domain.lane_id,
        output_slot_count=output_slot_count,
        measurement_slot_count=measurement_slot_count,
        width_axis=width_axis,
        height_axis=height_axis,
        width_authority_px=width_authority,
        height_authority_px=height_authority,
        width_scale_px_per_mm=scales.width_axis_px_per_mm,
        height_scale_px_per_mm=scales.height_axis_px_per_mm,
        sequence_profile=sequence_profile,
        cross_profile=cross_profile,
        sequence_measurement_sets=measurement_sets[2:],
        top_measurement_set=measurement_sets[0],
        bottom_measurement_set=measurement_sets[1],
        transition_by_id=transition_by_id,
    )
    proposal = build_lane_template_proposal(
        lane_input,
        configuration.physical_spec.frame_components,
    )
    return _PreparedLane(
        lane=lane,
        layout=layout,
        output_slot_count=output_slot_count,
        measurement_slot_count=measurement_slot_count,
        width_axis=width_axis,
        height_axis=height_axis,
        width_authority_px=width_authority,
        height_authority_px=height_authority,
        anchor_domain=anchor_domain,
        measurement_sets=measurement_sets,
        side_regions=side_regions,
        top_regions=top_regions,
        bottom_regions=bottom_regions,
        transition_by_id=transition_by_id,
        sequence_profile=sequence_profile,
        cross_profile=cross_profile,
        proposal=proposal,
    )


def _supported() -> TypedAssessment:
    return TypedAssessment(EvidenceState.SUPPORTED, None)


def _unavailable(gap: GateGap) -> TypedAssessment:
    return TypedAssessment(EvidenceState.UNAVAILABLE, gap)


def _contradicted(gap: GateGap) -> TypedAssessment:
    return TypedAssessment(EvidenceState.CONTRADICTED, gap)


def _empty_transform(
    field: PhotoBoundaryMeasurementField,
    layout: str,
    gap: str,
) -> OutputTransformAssessment:
    return output_transform_assessment(
        SharedStripDirectionResolution(
            direction=None,
            state=EvidenceState.UNAVAILABLE,
            named_gap=gap,
        ),
        layout=layout,
        source_width=field.source_extent.width,
        source_height=field.source_extent.height,
    )


def _output_slot_identities(
    lanes: tuple[SourceLaneEvidence, ...],
    resolved: ResolvedOutputSlots,
) -> tuple[OutputSlotIdentity, ...]:
    identities: list[OutputSlotIdentity] = []
    for lane, count in zip(lanes, resolved.lane_output_slot_counts, strict=True):
        for ordinal in range(1, count + 1):
            identities.append(
                OutputSlotIdentity(
                    global_output_ordinal=len(identities) + 1,
                    lane_id=lane.domain.lane_id,
                    lane_ordinal=ordinal,
                )
            )
    return tuple(identities)


def _work_receipt(
    prepared: _PreparedLane,
    placements: tuple[FormatPlacement, ...],
    *,
    enhanced_query_count: int = 0,
    proposal: TemplateLaneProposal | None = None,
) -> TemplateWorkReceipt:
    active_proposal = prepared.proposal if proposal is None else proposal
    active_sequence_profile = active_proposal.lane.sequence_profile
    grouping = tuple(
        component.grouping_work
        for component in active_proposal.components
    )
    group_count = sum(
        len(component.phase_groups)
        for component in active_proposal.components
    )
    profile_query_ids = {
        prepared.transition_by_id[str(identity)].query_id
        for profile in (active_sequence_profile, prepared.cross_profile)
        for run in profile.runs
        for identity in run.transition_ids
    }
    completed_measurement_count = sum(
        item.coverage.complete for item in prepared.measurement_sets
    )
    receipt = TemplateWorkReceipt(
        measurement_query_count=len(prepared.measurement_sets),
        pixel_query_count=sum(
            item.coverage.pixel_query_count for item in prepared.measurement_sets
        ),
        basic_profile_coordinate_count=(
            active_sequence_profile.coordinate_count
            + prepared.cross_profile.coordinate_count
        ),
        basic_profile_run_count=(
            len(active_sequence_profile.runs)
            + len(prepared.cross_profile.runs)
        ),
        phase_vote_count=sum(
            len(component.phase_votes)
            for component in active_proposal.components
        ),
        template_group_count=group_count,
        template_role_lookup_count=sum(
            item.template_role_lookup_count for item in grouping
        ),
        template_role_match_count=sum(
            item.template_role_match_count for item in grouping
        ),
        local_relation_evaluation_count=(
            group_count * max(0, prepared.output_slot_count - 1)
        ),
        enhanced_query_count=enhanced_query_count,
        materialized_frame_geometry_count=sum(
            len(item.canonical.frames) for item in placements
        ),
        shared_measurement_reuse_count=(
            completed_measurement_count + len(profile_query_ids)
        ),
        domain_pixels=(
            prepared.lane.domain.work_box.width
            * prepared.lane.domain.work_box.height
        ),
        peak_temporary_bytes=max(
            (item.coverage.peak_temporary_bytes for item in prepared.measurement_sets),
            default=0,
        ),
    )
    if active_proposal.components:
        receipt.validate_bounds(
            ordered_role_count=prepared.output_slot_count * 2,
            slot_count=prepared.output_slot_count,
            registered_enhanced_query_count=sum(
                len(component.enhanced_phase_queries)
                + len(component.registered_sequence_role_queries)
                for component in active_proposal.components
            ),
        )
    return receipt


def _empty_reconstruction(prepared: _PreparedLane) -> LaneFormatPlacementReconstruction:
    return LaneFormatPlacementReconstruction(
        lane_id=prepared.lane.domain.lane_id,
        anchor_domain=prepared.anchor_domain,
        measurement_sets=prepared.measurement_sets,
        side_transition_regions=prepared.side_regions,
        sequence_profile=prepared.sequence_profile,
        cross_profile=prepared.cross_profile,
        raw_top_bottom_observations=(
            prepared.proposal.raw_top_bottom_observations
        ),
        provisional_height_templates=tuple(
            template
            for component in prepared.proposal.components
            for template in component.height_templates
        ),
        direction_classes=prepared.proposal.direction_classes,
        retained_placements=(),
        canonical_placement=None,
        safe_crop_envelopes=(),
        direct_use_budget_assessments=(),
        work=_work_receipt(prepared, ()),
    )


def _unresolved_facts(direction_gap: GateGap) -> dict[str, TypedAssessment]:
    return {
        "scan_canvas_authority": _supported(),
        "output_slot_count": _supported(),
        "format_placement": _unavailable(GateGap.FORMAT_PLACEMENT_UNAVAILABLE),
        "shared_strip_direction": _unavailable(direction_gap),
        "source_frame_geometry": _unavailable(
            GateGap.SOURCE_FRAME_GEOMETRY_UNAVAILABLE
        ),
        "slot_ordinal_assignment": _unavailable(
            GateGap.SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED
        ),
        "source_lane_authority": _unavailable(
            GateGap.SOURCE_LANE_AUTHORITY_INVALID
        ),
        "placement_set_containment": _unavailable(
            GateGap.PLACEMENT_SET_CONTAINMENT_UNAVAILABLE
        ),
        "direct_use_budget": _unavailable(GateGap.DIRECT_USE_BUDGET_UNAVAILABLE),
        "output_transform": _unavailable(GateGap.OUTPUT_TRANSFORM_UNAVAILABLE),
    }


def reconstruct_photo_geometry(
    field: PhotoBoundaryMeasurementField,
    lanes: tuple[SourceLaneEvidence, ...],
    *,
    layout: str,
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration | None,
) -> PhotoGeometryDetectionResult:
    del lane_configuration
    resolved = resolve_output_slots(configuration, lanes)
    if resolved is None:
        transform = _empty_transform(field, layout, "output_slot_count_unavailable")
        facts = _unresolved_facts(GateGap.SHARED_STRIP_DIRECTION_UNAVAILABLE)
        facts["scan_canvas_authority"] = (
            _supported()
            if lanes
            else _unavailable(GateGap.SCAN_CANVAS_AUTHORITY_UNAVAILABLE)
        )
        facts["output_slot_count"] = _unavailable(
            GateGap.OUTPUT_SLOT_COUNT_UNAVAILABLE
        )
        return PhotoGeometryDetectionResult(None, (), (), transform, facts)

    prepared = tuple(
        _prepare_lane(
            field,
            lane,
            layout=layout,
            output_slot_count=count,
            measurement_slot_count=_lane_measurement_capacity(
                configuration,
                lanes,
                lane,
            ),
            configuration=configuration,
        )
        for lane, count in zip(
            lanes,
            resolved.lane_output_slot_counts,
            strict=True,
        )
    )
    source_directions = shared_source_direction_classes(
        tuple(item.proposal for item in prepared)
    )
    if len(source_directions) != 1:
        gap = (
            GateGap.SHARED_STRIP_DIRECTION_UNAVAILABLE
            if not source_directions
            else GateGap.SHARED_STRIP_DIRECTION_NONUNIQUE
        )
        transform = _empty_transform(field, layout, gap.value)
        return PhotoGeometryDetectionResult(
            resolved_output_slots=resolved,
            lane_reconstructions=tuple(
                _empty_reconstruction(item) for item in prepared
            ),
            output_slot_identities=_output_slot_identities(lanes, resolved),
            transform_assessment=transform,
            assessment_facts=_unresolved_facts(gap),
        )

    direction = source_directions[0]
    direction_resolution = SharedStripDirectionResolution(
        direction=direction,
        state=EvidenceState.SUPPORTED,
        named_gap=None,
    )
    transform = output_transform_assessment(
        direction_resolution,
        layout=layout,
        source_width=field.source_extent.width,
        source_height=field.source_extent.height,
    )
    materialization = materialize_source_placements(
        tuple(item.proposal for item in prepared),
        direction,
    )
    placements_by_lane = materialization.placements_by_lane
    complete = (
        len(placements_by_lane) == len(prepared)
        and all(placements_by_lane)
    )
    reconstructions: list[LaneFormatPlacementReconstruction] = []
    all_budgets: list[DirectUseBudgetAssessment] = []
    lane_authority_valid = True
    containment_valid = True
    for prepared_lane, placements, enhanced_query_count, refined_proposal in zip(
        prepared,
        placements_by_lane if complete else tuple(() for _item in prepared),
        materialization.enhanced_query_counts_by_lane,
        materialization.lane_proposals,
        strict=True,
    ):
        canonical = (
            min(placements, key=lambda item: item.canonical.canonical_rank)
            if placements
            else None
        )
        geometries: list[SafeCropEnvelope] = []
        budgets: list[DirectUseBudgetAssessment] = []
        if canonical is not None and transform.transform is not None:
            for ordinal in range(1, canonical.output_slot_count + 1):
                try:
                    geometry = safe_crop_envelope_from_placements(
                        placements,
                        canonical,
                        lane=prepared_lane.lane,
                        lane_ordinal=ordinal,
                        layout=layout,
                        minimum_guard=minimum_guard_spec(
                            configuration.physical_spec.format_id
                        ),
                        transform=transform.transform,
                    )
                    budget = direct_use_budget_assessment(
                        placements,
                        geometry,
                        transform.transform,
                    )
                except ValueError:
                    lane_authority_valid = False
                    containment_valid = False
                    geometries.clear()
                    budgets.clear()
                    break
                geometries.append(geometry)
                budgets.append(budget)
        all_budgets.extend(budgets)
        reconstructions.append(
            LaneFormatPlacementReconstruction(
                lane_id=prepared_lane.lane.domain.lane_id,
                anchor_domain=prepared_lane.anchor_domain,
                measurement_sets=prepared_lane.measurement_sets,
                side_transition_regions=prepared_lane.side_regions,
                sequence_profile=refined_proposal.lane.sequence_profile,
                cross_profile=prepared_lane.cross_profile,
                raw_top_bottom_observations=(
                    refined_proposal.raw_top_bottom_observations
                ),
                provisional_height_templates=tuple(
                    template
                    for component in refined_proposal.components
                    for template in component.height_templates
                ),
                direction_classes=source_directions,
                retained_placements=placements,
                canonical_placement=canonical,
                safe_crop_envelopes=tuple(geometries),
                direct_use_budget_assessments=tuple(budgets),
                work=_work_receipt(
                    prepared_lane,
                    placements,
                    enhanced_query_count=enhanced_query_count,
                    proposal=refined_proposal,
                ),
            )
        )
    output_geometry_complete = (
        complete
        and sum(
            len(item.safe_crop_envelopes)
            for item in reconstructions
        )
        == resolved.output_slot_count
    )
    budget_state = (
        _contradicted(GateGap.DIRECT_USE_BUDGET_EXCEEDED)
        if any(item.state == EvidenceState.CONTRADICTED for item in all_budgets)
        else _supported()
        if (
            output_geometry_complete
            and len(all_budgets) == resolved.output_slot_count
            and all(item.state == EvidenceState.SUPPORTED for item in all_budgets)
        )
        else _unavailable(GateGap.DIRECT_USE_BUDGET_UNAVAILABLE)
    )
    facts = {
        "scan_canvas_authority": _supported(),
        "output_slot_count": _supported(),
        "format_placement": (
            _supported()
            if complete
            else _unavailable(GateGap.FORMAT_PLACEMENT_UNAVAILABLE)
        ),
        "shared_strip_direction": _supported(),
        "source_frame_geometry": (
            _supported()
            if complete
            else _unavailable(GateGap.SOURCE_FRAME_GEOMETRY_UNAVAILABLE)
        ),
        "slot_ordinal_assignment": (
            _supported()
            if complete
            else _unavailable(GateGap.SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED)
        ),
        "source_lane_authority": (
            _supported()
            if complete and lane_authority_valid
            else _contradicted(GateGap.SOURCE_LANE_AUTHORITY_INVALID)
        ),
        "placement_set_containment": (
            _supported()
            if output_geometry_complete and containment_valid
            else _unavailable(GateGap.PLACEMENT_SET_CONTAINMENT_UNAVAILABLE)
        ),
        "direct_use_budget": budget_state,
        "output_transform": (
            _supported()
            if transform.state == EvidenceState.SUPPORTED
            else _unavailable(GateGap.OUTPUT_TRANSFORM_UNAVAILABLE)
        ),
    }
    return PhotoGeometryDetectionResult(
        resolved_output_slots=resolved,
        lane_reconstructions=tuple(reconstructions),
        output_slot_identities=_output_slot_identities(lanes, resolved),
        transform_assessment=transform,
        assessment_facts=facts,
    )
