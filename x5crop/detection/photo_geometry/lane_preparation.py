"""Register candidate-independent measurements for one template lane."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

from ...configuration.model import DetectionConfiguration, ResolvedSlotCount
from ...domain import WorkspaceExtent
from ...formats import OUTPUT_PROTECTION_SPEC
from ..source_core import SourceLaneEvidence
from .axis_layout import axis_interval, coordinate_count, source_axes
from .corridors import (
    build_sequence_anchor_discovery_domain,
    build_top_bottom_search_corridors,
    registered_lane_measurement_queries,
    source_lane_box,
)
from .coarse_strip_support import observe_coarse_strip_support
from .template_coarse_sides import (
    coarse_enclosing_binding as _coarse_enclosing_binding,
    register_coarse_side_facts,
)
from .exterior_region_measurement import measure_exterior_region
from .coarse_enclosing_model import CoarseSharedDirection
from .measurement_model import (
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementSet,
    SequenceTransitionObservation,
)
from .model import BoundaryRole, QueryPurpose
from .observations import build_sequence_edge_observations
from .aggregate_edge_support import (
    placement_sequence_edges_with_material_support,
    resolve_aggregate_edge_support,
    resolve_aggregate_separator_support,
)
from .outer_material import observe_outer_material_boundaries
from .output_model import ResolvedOutputSlots, SharedStripDirection
from .profile_adapters import cross_profile_from_regions, sequence_profile_from_regions
from .registered_measurement import measure_registered_queries
from .sequence_edge_families import merge_sequence_edge_families
from .separator_observations import build_format_separator_bands
from .observation_types import (
    BoundaryEdgeMeasurementBasis,
    SeparatorBandMeasurementBasis,
)
from .template_evidence import template_evidence_use_ledger
from .template_direct_role_authority import intrinsic_direct_role_authority_bases
from .template_frame_width import (
    SourceFrameWidthAuthority,
    apply_placement_source_frame_width,
    calibrate_source_frame_width,
)
from .template_aspect_ratio import (
    apply_inferred_aperture_height,
    derive_aperture_aspect_ratio_authority,
)
from .template_runtime_model import (
    PreparedTemplateLane,
    RegisteredTemplateLane,
    TemplateMeasurementWorkReceipt,
)
from .template_measurement_plan import compile_template_measurement_plan
from .template_registration import (
    RegisteredCrossEvidence,
    project_cross_solver_bindings,
    register_cross_evidence,
    register_template_local_cross_refinements,
)
from .template_cross import calibrate_source_frame_height, fit_template_cross
from .template_common_output import CompleteCrossHeightCalibration, complete_cross_height_calibration
from .template_cross_model import TemplateCrossInput, CrossFitCompetition, CrossRoleBinding
from .template_contact import observe_contact_edges
from .template_overlap import observe_overlap_edge_pairs
from .template_model import (
    SequenceFit,
    TemplateSpec,
    SourceFrameWidthAuthorityBasis,
    template_role_refinement_radius_px,
)
from .template_phase import (
    account_prior_phase_fit,
    finalize_template_phase_candidate,
    fit_template_phase_candidate_with_adjacency_relations,
)
from .template_phase_competition import fit_template_phase
from .template_phase_refinement import refine_template_phase_with_source_frame_width
from .template_phase_model import (
    GlobalLatticeAuthorityEvidence,
    PhaseFailureKind,
    PhaseFitStatus,
    PhaseFitResult,
    TemplatePhaseCandidateCompetition,
    TemplatePhaseInput,
)
from .template_source_domain import PhaseSourceDomain
from .template_pitch import (
    TemplatePitchCalibration,
    calibrate_template_source_pitch,
    close_separator_phase_hypothesis,
    resolve_separator_pitch_hypothesis,
)
from .template_placement import (
    resolved_cross_support_domains_px,
    retained_cross_support_domain_groups_px,
    review_cross_support_domain_groups_px,
)
from .source_geometry import SourceScanGeometry
from .transition_tracking import (
    track_broad_material_transition_regions,
    track_cross_height_transition_regions,
    track_side_transition_regions,
)



def _shared_direction_from_coarse(
    direction: CoarseSharedDirection | None,
) -> SharedStripDirection | None:
    if direction is None:
        return None
    return SharedStripDirection(
        direction_id=direction.direction_id,
        selected_observation_ids=direction.observation_ids,
        full_angle_interval_degrees=(
            direction.full_direction_interval_degrees
        ),
        observed_angle_interval_degrees=(
            direction.observed_direction_interval_degrees
        ),
        canonical_angle_degrees=direction.canonical_direction_degrees,
    )


def _enclosing_support_for_canonical_height(
    enclosing,
    canonical_height_px: float,
):
    """Keep coarse output support only when final fixed H authorizes it."""

    if not math.isfinite(canonical_height_px) or canonical_height_px <= 0.0:
        raise ValueError("canonical fixed height must be positive")
    if enclosing is None:
        return None
    span = enclosing.observed_span_px
    if (
        span.minimum <= canonical_height_px
        or span.maximum
        > (
            OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
            * canonical_height_px
        )
    ):
        return None
    return enclosing


@dataclass(frozen=True)
class TemplateCrossContext:
    """One sequence interpretation's own H, registration and Cross result."""

    source_scan_geometry: SourceScanGeometry
    cross_input: TemplateCrossInput
    registration: RegisteredCrossEvidence
    competition: CrossFitCompetition
    top_bindings: tuple[CrossRoleBinding, ...]
    bottom_bindings: tuple[CrossRoleBinding, ...]
    initial_source_scan_geometry: SourceScanGeometry
    source_frame_width_authority: SourceFrameWidthAuthority
    source_width_fit: SequenceFit | None
    independent_member_context: bool
    phase_competition: PhaseFitResult
    complete_height_calibration: CompleteCrossHeightCalibration | None = None

    def __post_init__(self) -> None:
        if (self.independent_member_context and self.source_frame_width_authority.state.value == "supported"
                and (self.source_width_fit is None
                     or not self.source_frame_width_authority.matches_placement(self.source_width_fit))):
            raise ValueError("Cross context borrowed another member's W")
        initial = self.initial_source_scan_geometry
        if (self.cross_input.fixed_height_px != initial.height_state.extent_projection_px()
                or self.cross_input.canonical_fixed_height_px != initial.height_state.extent_projection_px().center):
            raise ValueError("Cross context lost its independent initial H")
        expected = calibrate_source_frame_height(apply_inferred_aperture_height(
            initial, self.competition.aperture_aspect_ratio_authority), self.competition)
        if self.complete_height_calibration is not None:
            if self.independent_member_context:
                raise ValueError("an independent phase member cannot calibrate another competition's H")
            proof = complete_cross_height_calibration(expected, phase=self.phase_competition,
                cross=self.competition, registration=self.registration.work_receipt,
                observations=self.registration.observations, cross_input=self.cross_input)
            if proof != self.complete_height_calibration:
                raise ValueError("Cross context lost its complete alternative height proof")
            expected = proof.source_geometry
        if replace(expected, geometry_id=self.source_scan_geometry.geometry_id) != self.source_scan_geometry:
            raise ValueError("Cross context H does not follow its own Cross authority")


def prepare_template_cross_context(
    registered: RegisteredTemplateLane,
    base: RegisteredCrossEvidence,
    *,
    template: TemplateSpec,
    phase: PhaseFitResult,
    source_geometry: SourceScanGeometry,
    source_frame_width_authority: SourceFrameWidthAuthority,
    sequence_fits: tuple[SequenceFit, ...] | None = None,
    coarse_geometry_preparation=None,
) -> TemplateCrossContext:
    """Compile the same canonical Cross path for each supplied role mapping.

    Only the candidate-independent base registration is reusable. Local H
    windows, longitudinal domains, coarse classification and aspect authority
    are rebuilt from this interpretation's own W and initial source H.
    """

    if sequence_fits is None:
        domains = ()
        try:
            domains = retained_cross_support_domain_groups_px(phase)
        except ValueError as error:
            if phase.status == PhaseFitStatus.RESOLVED:
                phase = replace(phase, status=PhaseFitStatus.UNRESOLVED,
                    ambiguity_reason=str(error), failure_kind=PhaseFailureKind.FIXED_TEMPLATE_MISMATCH,
                    winner_basis=None)
    else:
        domains = tuple(resolved_cross_support_domains_px(fit) for fit in sequence_fits)
    top_measurement = next(item for item in registered.measurement_sets
                           if item.query.purpose == QueryPurpose.TOP_CORRIDOR)
    bottom_measurement = next(item for item in registered.measurement_sets
                              if item.query.purpose == QueryPurpose.BOTTOM_CORRIDOR)
    scales = registered.lane.scan_canvas.axis_scales
    if scales is None:
        raise ValueError("Cross context requires scan-canvas axis scales")
    fixed_height = source_geometry.height_state.extent_projection_px()
    canonical_height = fixed_height.center
    cross = register_template_local_cross_refinements(
        base, top_measurement=top_measurement, bottom_measurement=bottom_measurement,
        width_axis=registered.width_axis, height_axis=registered.height_axis,
        height_scale_px_per_mm=scales.height_axis_px_per_mm,
        lane_reference_trace_px=registered.width_authority_px.center,
        fixed_height_px=fixed_height, canonical_height_px=canonical_height,
        longitudinal_support_domain_groups_px=domains,
    )
    enclosing = _enclosing_support_for_canonical_height(
        registered.coarse_support.enclosing_support, canonical_height,
    )
    pair_id = "" if enclosing is None else (
        f"coarse-enclosing-pair:{enclosing.minimum_track.observation_id}:"
        f"{enclosing.maximum_track.observation_id}"
    )
    coarse_top = () if enclosing is None else (
        _coarse_enclosing_binding(enclosing.minimum_track, BoundaryRole.TOP, pair_id=pair_id),
    )
    coarse_bottom = () if enclosing is None else (
        _coarse_enclosing_binding(enclosing.maximum_track, BoundaryRole.BOTTOM, pair_id=pair_id),
    )
    fitted_count = len(project_cross_solver_bindings((
        *cross.top_bindings, *cross.bottom_bindings, *coarse_top, *coarse_bottom,
    )))
    plan = registered.measurement_plan
    native_top, native_bottom, coarse_registration = register_coarse_side_facts(
        registered.coarse_support.enclosing_side_facts,
        remaining_bound=max(0, plan.cross_bounds.max_fitted_observations - fitted_count),
        geometry_preparation=coarse_geometry_preparation,
    )
    top_bindings = (*cross.top_bindings, *coarse_top, *native_top)
    bottom_bindings = (*cross.bottom_bindings, *coarse_bottom, *native_bottom)
    solver_top = project_cross_solver_bindings(top_bindings)
    solver_bottom = project_cross_solver_bindings(bottom_bindings)
    inputs = TemplateCrossInput(
        template=template, fixed_height_px=fixed_height,
        canonical_fixed_height_px=canonical_height,
        lane_reference_trace_px=registered.width_authority_px.center,
        source_direction=_shared_direction_from_coarse(registered.coarse_support.shared_direction),
        registered_trace_coordinates_px=top_measurement.query.trace_positions_px,
        longitudinal_support_domain_groups_px=domains,
        review_support_domain_groups_px=review_cross_support_domain_groups_px(phase),
        top_bindings=solver_top, bottom_bindings=solver_bottom,
        boundary_axis=registered.height_axis,
        maximum_registered_runs_per_role=plan.cross_bounds.max_registered_runs_per_role,
        maximum_fitted_observations=plan.cross_bounds.max_fitted_observations,
        maximum_compatible_pairs=plan.cross_bounds.max_compatible_pairs,
        maximum_evaluated_fits=plan.cross_bounds.max_evaluated_fits,
        registered_top_run_count=cross.registered_top_run_count,
        registered_bottom_run_count=cross.registered_bottom_run_count,
        fitted_observation_count=len(solver_top) + len(solver_bottom),
        coarse_side_registration=coarse_registration,
        aperture_aspect_ratio_authority=derive_aperture_aspect_ratio_authority(
            source_geometry, source_frame_width_authority,
        ),
    )
    initial_source = source_geometry
    competition = fit_template_cross(inputs, coarse_geometry_preparation=coarse_geometry_preparation)
    source_geometry = apply_inferred_aperture_height(
        source_geometry, competition.aperture_aspect_ratio_authority,
    )
    source_geometry = calibrate_source_frame_height(source_geometry, competition)
    height_calibration = None if sequence_fits is not None else complete_cross_height_calibration(
        source_geometry, phase=phase, cross=competition, registration=cross.work_receipt,
        observations=cross.observations, cross_input=inputs)
    if height_calibration is not None:
        source_geometry = height_calibration.source_geometry
    return TemplateCrossContext(source_geometry, inputs, cross, competition,
                                top_bindings, bottom_bindings, initial_source,
                                source_frame_width_authority, phase.best, sequence_fits is not None, phase,
                                height_calibration)


def _profile_capacity(
    configuration: DetectionConfiguration,
    lane: SourceLaneEvidence,
) -> int:
    profile = lane.scan_canvas.selected_profile
    if profile is None:
        return 0
    return configuration.physical_spec.holder_full_count(profile.profile_id) or 0


def lane_measurement_capacity(
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
    resolved_slot_count: ResolvedSlotCount | None,
) -> ResolvedOutputSlots | None:
    if not lanes or resolved_slot_count is None:
        return None
    requested = resolved_slot_count.output_count
    if configuration.physical_spec.layout.kind == "dual_lane":
        capacity = _profile_capacity(configuration, lanes[0])
        if requested != capacity or requested % len(lanes):
            return None
        return ResolvedOutputSlots(tuple(requested // len(lanes) for _lane in lanes))
    capacity = _profile_capacity(configuration, lanes[0])
    if requested <= 0 or requested > capacity:
        return None
    return ResolvedOutputSlots((requested,))


def _physical_transition_regions(
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    reference_trace_px: float,
    boundary_axis_scale_px_per_mm,
    minimum_independent_support_regions: int = 2,
):
    retained = {}
    for measurement_set in measurement_sets:
        values = track_side_transition_regions(
            (measurement_set,),
            reference_trace_px=reference_trace_px,
            boundary_axis_scale_px_per_mm=boundary_axis_scale_px_per_mm,
            minimum_independent_support_regions=(
                minimum_independent_support_regions
            ),
        )
        retained.update({item.region_id: item for item in values})
    return tuple(
        sorted(
            retained.values(),
            key=lambda item: (
                item.position_interval_px.center,
                item.region_id,
            ),
        )
    )


def _physical_cross_height_regions(
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    reference_trace_px: float,
    boundary_axis_scale_px_per_mm,
):
    retained = {}
    for measurement_set in measurement_sets:
        values = track_cross_height_transition_regions(
            (measurement_set,),
            reference_trace_px=reference_trace_px,
            boundary_axis_scale_px_per_mm=boundary_axis_scale_px_per_mm,
        )
        retained.update({item.region_id: item for item in values})
    return tuple(
        sorted(
            retained.values(),
            key=lambda item: (
                item.position_interval_px.center,
                item.region_id,
            ),
        )
    )


def _physical_broad_material_regions(
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    reference_trace_px: float,
    boundary_axis_scale_px_per_mm,
):
    retained = {}
    for measurement_set in measurement_sets:
        values = track_broad_material_transition_regions(
            (measurement_set,),
            reference_trace_px=reference_trace_px,
            boundary_axis_scale_px_per_mm=boundary_axis_scale_px_per_mm,
        )
        retained.update({item.region_id: item for item in values})
    return tuple(
        sorted(
            retained.values(),
            key=lambda item: (
                item.position_interval_px.center,
                item.region_id,
            ),
        )
    )


def _phase_source_domain(
    field: PhotoBoundaryMeasurementField,
    lane: SourceLaneEvidence,
    *,
    layout: str,
) -> PhaseSourceDomain:
    if not isinstance(field, PhotoBoundaryMeasurementField):
        raise TypeError("phase source domain requires the canonical measurement field")
    width_axis = source_axes(layout)[0]
    scales = lane.scan_canvas.axis_scales
    if (
        field.layout != layout
        or lane.domain.source_axis_long != width_axis.value
        or scales is None
        or scales.source_width_axis != width_axis.value
    ):
        raise ValueError("phase source domain axis differs from its registered lane")
    long_axis = lane.scan_canvas.observed_long_axis_px
    short_axis = lane.scan_canvas.observed_short_axis_px
    canvas_extent = (
        WorkspaceExtent(long_axis, short_axis)
        if layout == "horizontal"
        else WorkspaceExtent(short_axis, long_axis)
    )
    if canvas_extent != field.source_extent:
        raise ValueError("phase scan canvas differs from the canonical TIFF extent")
    return PhaseSourceDomain(
        lane_id=lane.domain.lane_id,
        sampling_authority_box=source_lane_box(lane, layout),
        source_extent=field.source_extent,
        width_axis=width_axis,
    )


def prepare_template_lane(
    field: PhotoBoundaryMeasurementField,
    lane: SourceLaneEvidence,
    *,
    layout: str,
    output_slot_count: int,
    measurement_slot_count: int,
    configuration: DetectionConfiguration,
) -> PreparedTemplateLane:
    """Measure every finite corridor once before fitting any template."""

    width_axis, height_axis = source_axes(layout)
    authority = source_lane_box(lane, layout)
    width_authority = axis_interval(authority, width_axis)
    height_authority = axis_interval(authority, height_axis)
    phase_source_domain = _phase_source_domain(field, lane, layout=layout)
    scales = lane.scan_canvas.axis_scales
    if scales is None:
        raise ValueError("template registration requires scan-canvas scales")
    source_geometry = SourceScanGeometry.create(
        configuration.physical_spec.frame,
        width_scale_px_per_mm=scales.width_axis_px_per_mm,
        height_scale_px_per_mm=scales.height_axis_px_per_mm,
    )
    holder_full_count = _profile_capacity(configuration, lane)
    measurement_plan = compile_template_measurement_plan(
        format_spec=configuration.physical_spec,
        frame_spec=configuration.physical_spec.frame,
        count=output_slot_count,
        full_count=measurement_slot_count,
        holder_full_count=holder_full_count,
        lane_authority=lane.domain,
        layout=layout,
        scale_authority=scales,
    )
    measurement_plan.validate_measurement_receipt(
        pixel_query_count=measurement_plan.exterior_region_query.expected_pixel_work,
        peak_temporary_bytes=measurement_plan.exterior_region_query.temporary_buffer_bound,
    )
    # Complete and release dense pixel buffers before sparse baseline buffers
    # exist. Only scalar prefix/provenance records remain in the lane ledger.
    exterior_region_measurement = measure_exterior_region(field, measurement_plan.exterior_region_query)
    coarse_support, coarse_measurement_sets = observe_coarse_strip_support(
        field,
        lane,
        layout=layout,
        measurement_plan=measurement_plan,
    )
    top_corridor, bottom_corridor = build_top_bottom_search_corridors(
        lane,
        layout=layout,
        measurement_plan=measurement_plan,
        coarse_support=coarse_support,
    )
    anchor_domain = build_sequence_anchor_discovery_domain(
        lane,
        layout=layout,
        measurement_plan=measurement_plan,
        coarse_support=coarse_support,
    )
    queries = registered_lane_measurement_queries(
        lane,
        layout=layout,
        top_corridor=top_corridor,
        bottom_corridor=bottom_corridor,
        anchor_domain=anchor_domain,
        measurement_plan=measurement_plan,
        registration_start=len(coarse_measurement_sets),
    )
    all_queries = tuple(
        item.query for item in coarse_measurement_sets
    ) + queries
    measurement_plan.validate_execution(
        registered_query_count=len(all_queries) + 1,
        trace_position_count=sum(
            len(query.trace_positions_px) for query in all_queries
        ) + exterior_region_measurement.work.registered_trace_count,
        coordinate_sample_count=sum(
            max(1, int(math.ceil(interval.width)) + 1)
            for query in all_queries
            for interval in query.search_intervals_px
        ) + exterior_region_measurement.work.coordinate_sample_count,
    )
    precision_measurement_sets = measure_registered_queries(
        field,
        queries,
        registration_start=len(coarse_measurement_sets),
    )
    measurement_sets = (*coarse_measurement_sets, *precision_measurement_sets)
    (top_measurement,) = tuple(
        item for item in precision_measurement_sets
        if item.query.purpose == QueryPurpose.TOP_CORRIDOR
    )
    (bottom_measurement,) = tuple(
        item for item in precision_measurement_sets
        if item.query.purpose == QueryPurpose.BOTTOM_CORRIDOR
    )
    (sequence_baseline,) = tuple(
        item for item in precision_measurement_sets
        if item.query.purpose == QueryPurpose.SEQUENCE_BASELINE
    )
    sequence_measurement_sets = tuple(
        item for item in precision_measurement_sets
        if item.query.purpose == QueryPurpose.SEQUENCE_ANCHOR_WINDOW
    )
    transition_by_id: dict[str, SequenceTransitionObservation] = {
        str(item.transition_id): item
        for measurement_set in measurement_sets
        for item in (
            *measurement_set.transitions,
            *measurement_set.cross_height_transitions,
            *measurement_set.broad_material_transitions,
        )
    }
    side_regions = _physical_transition_regions(
        sequence_measurement_sets,
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
    )
    cross_height_regions = _physical_cross_height_regions(
        sequence_measurement_sets,
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
    )
    broad_material_regions = _physical_broad_material_regions(
        sequence_measurement_sets,
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
    )
    top_regions = _physical_transition_regions(
        (top_measurement,),
        reference_trace_px=width_authority.center,
        boundary_axis_scale_px_per_mm=scales.height_axis_px_per_mm,
        minimum_independent_support_regions=1,
    )
    bottom_regions = _physical_transition_regions(
        (bottom_measurement,),
        reference_trace_px=width_authority.center,
        boundary_axis_scale_px_per_mm=scales.height_axis_px_per_mm,
        minimum_independent_support_regions=1,
    )
    direct_sequence_profile = sequence_profile_from_regions(
        side_regions,
        coordinate_count=coordinate_count(width_authority),
        transition_by_id=transition_by_id,
    )
    direct_sequence_profile = merge_sequence_edge_families(
        direct_sequence_profile,
        transition_by_id,
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
    )
    cross_height_profile = sequence_profile_from_regions(
        cross_height_regions,
        coordinate_count=coordinate_count(width_authority),
        transition_by_id=transition_by_id,
    )
    cross_height_profile = merge_sequence_edge_families(
        cross_height_profile,
        transition_by_id,
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
    )
    broad_material_profile = sequence_profile_from_regions(
        broad_material_regions,
        coordinate_count=coordinate_count(width_authority),
        transition_by_id=transition_by_id,
    )
    broad_material_profile = merge_sequence_edge_families(
        broad_material_profile,
        transition_by_id,
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
    )
    cross_profile = cross_profile_from_regions(
        top_regions,
        bottom_regions,
        coordinate_count=coordinate_count(height_authority),
        transition_by_id=transition_by_id,
    )
    direct_sequence_edges = build_sequence_edge_observations(
        direct_sequence_profile,
        transition_by_id,
        queried_trace_coordinates_px=direct_sequence_profile.trace_coordinates_px,
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
        measurement_basis=BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
    )
    cross_height_edges = build_sequence_edge_observations(
        cross_height_profile,
        transition_by_id,
        queried_trace_coordinates_px=cross_height_profile.trace_coordinates_px,
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
        measurement_basis=(
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE
        ),
    )
    broad_material_edges = build_sequence_edge_observations(
        broad_material_profile,
        transition_by_id,
        queried_trace_coordinates_px=sequence_baseline.query.trace_positions_px,
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
        measurement_basis=(
            BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_TRACE
        ),
    )
    direct_separator_bands = build_format_separator_bands(
        direct_sequence_profile,
        direct_sequence_edges,
        transition_by_id,
        field,
        width_axis,
        measurement_plan.template_spec.frame_width_px,
        measurement_basis=SeparatorBandMeasurementBasis.DIRECT_TRACE,
    )
    cross_height_separator_bands = build_format_separator_bands(
        cross_height_profile,
        cross_height_edges,
        transition_by_id,
        field,
        width_axis,
        measurement_plan.template_spec.frame_width_px,
        measurement_basis=(
            SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE
        ),
    )
    broad_material_separator_bands = build_format_separator_bands(
        broad_material_profile,
        broad_material_edges,
        transition_by_id,
        field,
        width_axis,
        measurement_plan.template_spec.frame_width_px,
        measurement_basis=(
            SeparatorBandMeasurementBasis.BROAD_MATERIAL_TRACE
        ),
    )
    (
        resolved_sequence_edges,
        cross_height_edge_resolutions,
    ) = resolve_aggregate_edge_support(
        direct_sequence_edges,
        cross_height_edges,
        transition_by_id,
        registered_trace_lattice=(
            sequence_baseline.query.trace_positions_px
        ),
        aggregate_basis=(
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE
        ),
        bind_direct_edge=True,
    )
    (
        resolved_sequence_edges,
        broad_material_edge_resolutions,
    ) = resolve_aggregate_edge_support(
        resolved_sequence_edges,
        broad_material_edges,
        transition_by_id,
        registered_trace_lattice=(
            sequence_baseline.query.trace_positions_px
        ),
        aggregate_basis=(
            BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_TRACE
        ),
        bind_direct_edge=False,
    )
    sequence_profile = direct_sequence_profile
    projected_cross_height_separator_bands = (
        resolve_aggregate_separator_support(
            cross_height_separator_bands,
            cross_height_edge_resolutions,
            resolved_sequence_edges,
            direct_separator_bands,
            aggregate_basis=(
                SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            ),
        )
    )
    projected_broad_material_separator_bands = (
        resolve_aggregate_separator_support(
            broad_material_separator_bands,
            broad_material_edge_resolutions,
            resolved_sequence_edges,
            (
                *direct_separator_bands,
                *projected_cross_height_separator_bands,
            ),
            aggregate_basis=(
                SeparatorBandMeasurementBasis.BROAD_MATERIAL_TRACE
            ),
        )
    )
    separator_bands = tuple(
        sorted(
            (
                *direct_separator_bands,
                *projected_cross_height_separator_bands,
                *projected_broad_material_separator_bands,
            ),
            key=lambda item: str(item.observation_id),
        )
    )
    intrinsic_authority_edge_ids = frozenset(
        intrinsic_direct_role_authority_bases(
            resolved_sequence_edges,
            sequence_measurement_sets,
        )
    )
    raw_material_bands = (*direct_separator_bands, *cross_height_separator_bands,
                          *broad_material_separator_bands)
    observed_outer_material_boundaries = observe_outer_material_boundaries(
        raw_material_bands,
        (
            *cross_height_edge_resolutions,
            *broad_material_edge_resolutions,
        ),
        resolved_sequence_edges,
        direction=measurement_plan.template_spec.direction,
        intrinsic_authority_edge_ids=intrinsic_authority_edge_ids,
        maximum_material_width_px=(
            measurement_plan.template_spec.gap_prior_px.maximum
        ),
    )
    topology_sequence_edges = (
        placement_sequence_edges_with_material_support(
            resolved_sequence_edges,
            (
                *projected_cross_height_separator_bands,
                *projected_broad_material_separator_bands,
            ),
            (),
        )
    )
    placement_sequence_edges = (
        placement_sequence_edges_with_material_support(
            resolved_sequence_edges,
            (
                *projected_cross_height_separator_bands,
                *projected_broad_material_separator_bands,
            ),
            observed_outer_material_boundaries,
        )
    )
    placement_sequence_edge_ids = frozenset(
        item.observation_id for item in placement_sequence_edges
    )
    outer_material_boundaries = tuple(
        observation
        for observation in observed_outer_material_boundaries
        if {
            observation.boundary_edge_observation_id,
            observation.exterior_edge_observation_id,
        }.issubset(placement_sequence_edge_ids)
    )
    coverage = tuple(item.coverage for item in measurement_sets)
    work = TemplateMeasurementWorkReceipt(
        measurement_query_count=len(coverage) + 1,
        pixel_query_count=sum(item.pixel_query_count for item in coverage) + exterior_region_measurement.work.pixel_query_count,
        completed_query_count=sum(item.complete for item in coverage) + 1,
        peak_temporary_bytes=max(
            exterior_region_measurement.work.peak_temporary_bytes,
            *(item.peak_temporary_bytes for item in coverage),
        ),
        coverage_receipts=coverage,
        exterior_work=exterior_region_measurement.work,
    )
    measurement_plan.validate_measurement_receipt(
        pixel_query_count=work.pixel_query_count,
        peak_temporary_bytes=work.peak_temporary_bytes,
    )
    registered = RegisteredTemplateLane(
        exterior_region_measurement=exterior_region_measurement,
        lane=lane,
        layout=layout,
        output_slot_count=output_slot_count,
        measurement_slot_count=measurement_slot_count,
        width_axis=width_axis,
        height_axis=height_axis,
        width_authority_px=width_authority,
        height_authority_px=height_authority,
        coarse_support=coarse_support,
        anchor_domain=anchor_domain,
        measurement_sets=measurement_sets,
        side_regions=side_regions,
        cross_height_regions=cross_height_regions,
        cross_height_edges=cross_height_edges,
        cross_height_edge_resolutions=(
            cross_height_edge_resolutions
        ),
        broad_material_regions=broad_material_regions,
        broad_material_edges=broad_material_edges,
        broad_material_edge_resolutions=(
            broad_material_edge_resolutions
        ),
        top_regions=top_regions,
        bottom_regions=bottom_regions,
        transition_by_id=transition_by_id,
        sequence_profile=sequence_profile,
        cross_height_profile=cross_height_profile,
        broad_material_profile=broad_material_profile,
        cross_profile=cross_profile,
        sequence_edges=placement_sequence_edges,
        separator_bands=separator_bands,
        raw_material_bands=raw_material_bands,
        outer_material_boundaries=outer_material_boundaries,
        top_cross_bindings=(),
        bottom_cross_bindings=(),
        raw_cross_observations=(),
        cross_boundary_family_resolutions=(),
        measurement_work=work,
        measurement_plan=measurement_plan,
    )
    template = measurement_plan.template_spec
    provisional_phase = fit_template_phase(
        placement_sequence_edges,
        template,
        separator_bands=separator_bands,
        outer_material_boundaries=outer_material_boundaries,
        scale_px_per_mm=scales.width_axis_px_per_mm,
        holder_span_px=width_authority,
        source_domain=phase_source_domain,
    )
    # The broad template locates material bands. Test the proposed short-strip
    # pitch in its own compiled neighbourhood before committing it; an
    # independent closure must survive typed coordinate-authority projection.
    # A raw resolved fit can still depend entirely on unavailable weak edges.
    pitch_calibration = (
        TemplatePitchCalibration(template, None, None, (), (), 0, False)
        if provisional_phase.status == PhaseFitStatus.BOUND_EXCEEDED
        else calibrate_template_source_pitch(
            template,
            provisional_phase,
            placement_sequence_edges,
            separator_bands,
            holder_span_px=width_authority,
            max_lattice_hypotheses=measurement_plan.phase_bounds.max_hypotheses,
        )
    )
    registered_pitch_authority_ids = pitch_calibration.pitch_observation_ids
    pitch_lattice_hypothesis_count = (
        pitch_calibration.lattice_hypothesis_count
    )
    pitch_lattice_bound_exceeded = pitch_calibration.bound_exceeded
    template = pitch_calibration.template
    base_phase_hypothesis = pitch_calibration.phase_hypothesis_px
    proposed_base_phase = (
        None
        if base_phase_hypothesis is None
        else fit_template_phase(
            placement_sequence_edges,
            template,
            separator_bands=separator_bands,
            outer_material_boundaries=outer_material_boundaries,
            scale_px_per_mm=scales.width_axis_px_per_mm,
            holder_span_px=width_authority,
            source_domain=phase_source_domain,
            phase_authority_px=base_phase_hypothesis,
            sequence_measurement_sets=sequence_measurement_sets,
            calibrated_nominal_grid_prior=(
                measurement_plan.calibrated_nominal_grid_prior
            ),
        )
    )
    base_phase_authority = pitch_calibration.phase_authority_px
    if proposed_base_phase is not None:
        base_phase_authority = close_separator_phase_hypothesis(
            pitch_calibration,
            proposed_base_phase,
        )
        pitch_calibration = resolve_separator_pitch_hypothesis(
            pitch_calibration,
            proposed_base_phase,
            original_template=measurement_plan.template_spec,
        )
        template = pitch_calibration.template
        registered_pitch_authority_ids = pitch_calibration.pitch_observation_ids
    unclosed_separator_pitch_hypothesis = pitch_calibration.pitch_hypothesis_withheld
    if provisional_phase.status == PhaseFitStatus.BOUND_EXCEEDED:
        base_phase = provisional_phase
    elif proposed_base_phase is not None and (
        base_phase_authority is not None
        or proposed_base_phase.status == PhaseFitStatus.BOUND_EXCEEDED
    ):
        base_phase = proposed_base_phase
    else:
        base_phase = fit_template_phase(
            placement_sequence_edges,
            template,
            separator_bands=separator_bands,
            outer_material_boundaries=outer_material_boundaries,
            scale_px_per_mm=scales.width_axis_px_per_mm,
            holder_span_px=width_authority,
            source_domain=phase_source_domain,
            phase_authority_px=base_phase_authority,
        )
        if proposed_base_phase is not None:
            base_phase = account_prior_phase_fit(
                base_phase,
                proposed_base_phase,
            )
    # Source pitch comes only from candidate-independent separator positions.
    # The common-W prior already belongs to this primary template. Native
    # pair measurements tighten its retained model below without recompiling
    # the search space or letting an inferred role delete its own runner.
    # Measuring local W does not require global rank or remote coverage;
    # those remain placement-consumption and eligibility assessments.
    phase_search_authority = (
        None
        if unclosed_separator_pitch_hypothesis
        else close_separator_phase_hypothesis(pitch_calibration, base_phase)
    )
    phase_authority_observation_ids = (
        ()
        if phase_search_authority is None
        else tuple(
            dict.fromkeys(
                (
                    *pitch_calibration.direct_separator_ids,
                    *(
                        ()
                        if base_phase.best is None
                        else base_phase.best.evidence_group_ids
                    ),
                )
            )
        )
    )
    contact_edge_observations = observe_contact_edges(
        topology_sequence_edges,
        separator_bands,
        sequence_measurement_sets,
    )
    overlap_edge_pair_observations = observe_overlap_edge_pairs(
        topology_sequence_edges,
        separator_bands,
        sequence_measurement_sets,
        direction=template.direction,
        maximum_overlap_px=template_role_refinement_radius_px(
            template.pitch_px.maximum
        ),
    )
    phase_input = TemplatePhaseInput(
        observations=placement_sequence_edges,
        separator_bands=separator_bands,
        template=template,
        scale_px_per_mm=scales.width_axis_px_per_mm,
        holder_span_px=width_authority,
        source_domain=phase_source_domain,
        phase_authority_px=phase_search_authority,
        calibrated_nominal_grid_prior=(
            measurement_plan.calibrated_nominal_grid_prior
        ),
        outer_material_boundaries=outer_material_boundaries,
        contact_edge_observations=contact_edge_observations,
        overlap_edge_pair_observations=overlap_edge_pair_observations,
        sequence_measurement_sets=sequence_measurement_sets,
        global_lattice_evidence=GlobalLatticeAuthorityEvidence(
            phase_observation_ids=phase_authority_observation_ids,
            frame_width_observation_ids=(),
            pitch_observation_ids=registered_pitch_authority_ids,
        ),
    )
    # A producer bound is terminal even when a fresh fit could stay inside
    # the aggregate receipt limit. Do not restart competition after it.
    phase_candidate = (
        TemplatePhaseCandidateCompetition(base_phase, ())
        if base_phase.status == PhaseFitStatus.BOUND_EXCEEDED
        else fit_template_phase_candidate_with_adjacency_relations(phase_input)
    )
    if pitch_lattice_bound_exceeded:
        phase_candidate = replace(
            phase_candidate,
            result=replace(
                phase_candidate.result,
                best=None,
                runner_up=None,
                status=PhaseFitStatus.BOUND_EXCEEDED,
                _native_phase_retention=None,
                _source_clipped_phase_retention=None,
                ambiguity_reason=(
                    "separator lattice hypothesis bound exceeded"
                ),
                failure_kind=PhaseFailureKind.HYPOTHESIS_BOUND_EXCEEDED,
                winner_basis=None,
                best_phase_candidate_authority_projection=None,
                runner_phase_candidate_authority_projection=None,
                global_lattice_authority=None,
                calibrated_nominal_grid_evidence=None,
                adjacency_observation_coverage=(),
                direct_role_binding_authority=None,
                outer_frame_observation_authority=None,
            ),
        )
    source_geometry, source_frame_width_authority = (
        calibrate_source_frame_width(
            source_geometry,
            phase_candidate.result,
            placement_sequence_edges,
        )
    )
    selected_width_phase = apply_placement_source_frame_width(
        phase_candidate.result,
        source_frame_width_authority,
    )
    selected_width_phase = refine_template_phase_with_source_frame_width(
        selected_width_phase,
        source_frame_width_authority,
        placement_sequence_edges,
        separator_bands,
        phase_input.sequence_measurement_sets,
    )
    phase_candidate = replace(
        phase_candidate,
        result=selected_width_phase,
    )
    phase_input = replace(
        phase_input,
        global_lattice_evidence=replace(
            phase_input.global_lattice_evidence,
            frame_width_observation_ids=(
                source_frame_width_authority.observation_ids
                if source_frame_width_authority.basis
                == SourceFrameWidthAuthorityBasis
                .INDEPENDENT_COMPLETE_FRAMES
                else ()
            ),
        ),
    )
    phase = finalize_template_phase_candidate(
        phase_candidate,
        phase_input,
        source_frame_width_authority=source_frame_width_authority,
    )
    if (
        unclosed_separator_pitch_hypothesis
        and phase.status != PhaseFitStatus.BOUND_EXCEEDED
    ):
        phase = replace(
            phase,
            status=(
                PhaseFitStatus.UNRESOLVED
                if phase.status == PhaseFitStatus.RESOLVED else phase.status
            ),
            failure_kind=(
                PhaseFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED
                if phase.status == PhaseFitStatus.RESOLVED else phase.failure_kind
            ),
            ambiguity_reason=(
                ("" if phase.ambiguity_reason is None else phase.ambiguity_reason + "; ")
                + "two-separator pitch hypothesis lacks independent ordinal "
                "and phase closure: "
                + ", ".join(map(str, pitch_calibration.direct_separator_ids))
            ),
            winner_basis=None,
        )
    if base_phase.status != PhaseFitStatus.BOUND_EXCEEDED:
        phase = account_prior_phase_fit(phase, base_phase)
    if base_phase is not provisional_phase:
        phase = account_prior_phase_fit(phase, provisional_phase)
    phase = replace(
        phase,
        receipt=replace(
            phase.receipt,
            separator_lattice_hypothesis_count=(
                pitch_lattice_hypothesis_count
            ),
        ),
    )
    cross = register_cross_evidence(
        profile=cross_profile,
        top_measurement=top_measurement,
        bottom_measurement=bottom_measurement,
        width_axis=width_axis,
        height_axis=height_axis,
        height_scale_px_per_mm=scales.height_axis_px_per_mm,
        lane_reference_trace_px=width_authority.center,
        maximum_runs_per_role=(
            measurement_plan.cross_bounds.max_registered_runs_per_role
        ),
    )
    base_cross = cross
    context = prepare_template_cross_context(
        registered, base_cross, template=template, phase=phase,
        source_geometry=source_geometry,
        source_frame_width_authority=source_frame_width_authority,
    )
    source_geometry = context.source_scan_geometry
    phase = context.phase_competition
    cross_input = context.cross_input
    cross_competition = context.competition
    cross = context.registration
    top_bindings = context.top_bindings
    bottom_bindings = context.bottom_bindings
    registered_values = dict(registered.__dict__)
    registered_values["top_cross_bindings"] = top_bindings
    registered_values["bottom_cross_bindings"] = bottom_bindings
    registered_values["raw_cross_observations"] = cross.observations
    registered_values["cross_boundary_family_resolutions"] = (
        cross.family_resolutions
    )
    return PreparedTemplateLane(
        **registered_values,
        cross_registration_work=cross.work_receipt,
        base_cross_registration=base_cross,
        complete_height_calibration=context.complete_height_calibration,
        template_spec=template,
        source_scan_geometry=source_geometry,
        source_frame_width_authority=source_frame_width_authority,
        phase_input=phase_input,
        cross_input=cross_input,
        phase_competition=phase,
        cross_competition=cross_competition,
        evidence_use_ledger=template_evidence_use_ledger(
            placement_sequence_edges,
            separator_bands,
            outer_material_boundaries,
            cross.observations,
            phase,
            cross_competition,
            (
                *cross_height_edge_resolutions,
                *broad_material_edge_resolutions,
            ),
        ),
    )
