"""Register candidate-independent measurements for one template lane."""

from __future__ import annotations

from dataclasses import replace
import math

from ...configuration.model import DetectionConfiguration, ResolvedSlotCount
from ...domain import FiniteInterval
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
from .coarse_enclosing_model import (
    CoarseEnclosingTrack,
    CoarseSharedDirection,
)
from .measurement_model import (
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementSet,
    SequenceTransitionObservation,
)
from .model import BoundaryRole, QueryPurpose
from .observations import build_sequence_edge_observations
from .cross_height_edge_support import resolve_cross_height_edge_support
from .output_model import ResolvedOutputSlots, SharedStripDirection
from .profile_adapters import cross_profile_from_regions, sequence_profile_from_regions
from .registered_measurement import measure_registered_queries
from .sequence_edge_families import merge_sequence_edge_families
from .separator_observations import build_format_separator_bands
from .observation_types import BoundaryEdgeMeasurementBasis
from .template_evidence import template_evidence_use_ledger
from .template_frame_width import calibrate_source_frame_width
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
    register_cross_evidence,
    register_template_local_cross_refinements,
    template_spec_from_physical_authority,
)
from .template_cross import (
    calibrate_source_frame_height,
    fit_template_cross,
)
from .template_cross_model import CrossRoleBinding, TemplateCrossInput
from .template_phase import (
    account_prior_phase_fit,
    fit_template_phase,
    fit_template_phase_with_local_advance,
)
from .template_phase_model import (
    GlobalLatticeAuthorityEvidence,
    PhaseFailureKind,
    PhaseFitResult,
    PhaseFitStatus,
    TemplatePhaseInput,
)
from .template_pitch import (
    calibrate_template_source_pitch,
    close_separator_phase_hypothesis,
)
from .template_placement import resolved_sequence_support_domains_px
from .source_geometry import SourceScanGeometry
from .transition_tracking import (
    track_cross_height_transition_regions,
    track_side_transition_regions,
)


def _coarse_enclosing_binding(
    track: CoarseEnclosingTrack,
    role: BoundaryRole,
    *,
    pair_id: str,
) -> CrossRoleBinding:
    """Expose a geometric support side without granting aperture authority."""

    return CrossRoleBinding(
        role=role,
        run_id=f"coarse-enclosing:{track.observation_id}",
        observation_id=track.observation_id,
        coordinate_interval_px=track.full_position_interval_px,
        trace_coordinates_px=track.trace_coordinates_px,
        support_fraction=1.0,
        continuous_support_fraction=1.0,
        fit_residual_px=track.fit_residual_px,
        fit_interval_px=track.fit_position_interval_px,
        full_interval_px=track.full_position_interval_px,
        canonical_direction_degrees=track.canonical_direction_degrees,
        fit_direction_interval_degrees=(
            track.fit_direction_interval_degrees
        ),
        full_direction_interval_degrees=(
            track.full_direction_interval_degrees
        ),
        observed_direction_interval_degrees=(
            track.observed_direction_interval_degrees
        ),
        trace_position_intervals_px=track.trace_position_intervals_px,
        independent_support_region_count=(
            track.independent_support_region_count
        ),
        source_spanning_continuous=track.source_spanning_continuous,
        role_authorized=False,
        enclosing_pair_id=pair_id,
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
        registered_query_count=len(all_queries),
        trace_position_count=sum(
            len(query.trace_positions_px) for query in all_queries
        ),
        coordinate_sample_count=sum(
            max(1, int(math.ceil(interval.width)) + 1)
            for query in all_queries
            for interval in query.search_intervals_px
        ),
    )
    precision_measurement_sets = measure_registered_queries(
        field,
        queries,
        registration_start=len(coarse_measurement_sets),
    )
    measurement_sets = (*coarse_measurement_sets, *precision_measurement_sets)
    transition_by_id: dict[str, SequenceTransitionObservation] = {
        str(item.transition_id): item
        for measurement_set in measurement_sets
        for item in (
            *measurement_set.transitions,
            *measurement_set.cross_height_transitions,
        )
    }
    side_regions = _physical_transition_regions(
        precision_measurement_sets[2:],
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
    )
    cross_height_regions = _physical_cross_height_regions(
        precision_measurement_sets[2:],
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
    )
    top_regions = _physical_transition_regions(
        (precision_measurement_sets[0],),
        reference_trace_px=width_authority.center,
        boundary_axis_scale_px_per_mm=scales.height_axis_px_per_mm,
        minimum_independent_support_regions=1,
    )
    bottom_regions = _physical_transition_regions(
        (precision_measurement_sets[1],),
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
    cross_profile = cross_profile_from_regions(
        top_regions,
        bottom_regions,
        coordinate_count=coordinate_count(height_authority),
        transition_by_id=transition_by_id,
    )
    direct_sequence_edges = build_sequence_edge_observations(
        direct_sequence_profile,
        transition_by_id,
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
        measurement_basis=BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
    )
    cross_height_edges = build_sequence_edge_observations(
        cross_height_profile,
        transition_by_id,
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
        measurement_basis=(
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE
        ),
    )
    (
        sequence_edges,
        cross_height_edge_resolutions,
    ) = resolve_cross_height_edge_support(
        direct_sequence_edges,
        cross_height_edges,
        transition_by_id,
        registered_trace_lattice=(
            precision_measurement_sets[2].query.trace_positions_px
        ),
    )
    sequence_profile = direct_sequence_profile
    separator_bands = build_format_separator_bands(
        sequence_profile,
        sequence_edges,
        transition_by_id,
        field,
        width_axis,
        measurement_plan.template_spec.frame_width_px,
    )
    coverage = tuple(item.coverage for item in measurement_sets)
    work = TemplateMeasurementWorkReceipt(
        measurement_query_count=len(coverage),
        pixel_query_count=sum(item.pixel_query_count for item in coverage),
        completed_query_count=sum(item.complete for item in coverage),
        peak_temporary_bytes=max(
            (item.peak_temporary_bytes for item in coverage), default=0
        ),
        coverage_receipts=coverage,
    )
    measurement_plan.validate_measurement_receipt(
        pixel_query_count=work.pixel_query_count,
        peak_temporary_bytes=work.peak_temporary_bytes,
    )
    registered = RegisteredTemplateLane(
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
        top_regions=top_regions,
        bottom_regions=bottom_regions,
        transition_by_id=transition_by_id,
        sequence_profile=sequence_profile,
        cross_profile=cross_profile,
        sequence_edges=sequence_edges,
        separator_bands=separator_bands,
        top_cross_bindings=(),
        bottom_cross_bindings=(),
        raw_cross_observations=(),
        measurement_work=work,
        measurement_plan=measurement_plan,
    )
    template = measurement_plan.template_spec
    provisional_phase = fit_template_phase(
        sequence_edges,
        template,
        separator_bands=separator_bands,
        scale_px_per_mm=scales.width_axis_px_per_mm,
        holder_span_px=width_authority,
    )
    # The broad provisional template only brings direct material bands into a
    # finite neighbourhood. Once two independent separator locations establish
    # one source pitch, that measured pitch must replace the format gap seed
    # before the narrowed-W template is rebound. Requiring the nominal gap to
    # survive first would make the template prove the measurement it is meant
    # only to locate.
    pitch_calibration = calibrate_template_source_pitch(
        template,
        provisional_phase,
        sequence_edges,
        separator_bands,
        holder_span_px=width_authority,
        max_lattice_hypotheses=measurement_plan.phase_bounds.max_hypotheses,
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
            sequence_edges,
            template,
            separator_bands=separator_bands,
            scale_px_per_mm=scales.width_axis_px_per_mm,
            holder_span_px=width_authority,
            phase_authority_px=base_phase_hypothesis,
        )
    )
    base_phase_authority = pitch_calibration.phase_authority_px
    if proposed_base_phase is not None:
        base_phase_authority = close_separator_phase_hypothesis(
            pitch_calibration,
            proposed_base_phase,
        )
    if proposed_base_phase is not None and base_phase_authority is not None:
        base_phase = proposed_base_phase
    else:
        base_phase = fit_template_phase(
            sequence_edges,
            template,
            separator_bands=separator_bands,
            scale_px_per_mm=scales.width_axis_px_per_mm,
            holder_span_px=width_authority,
            phase_authority_px=base_phase_authority,
        )
        if proposed_base_phase is not None:
            base_phase = account_prior_phase_fit(
                base_phase,
                proposed_base_phase,
            )
    source_geometry = calibrate_source_frame_width(
        source_geometry,
        base_phase,
        sequence_edges,
        holder_span_px=width_authority,
    )
    template = template_spec_from_physical_authority(
        frame_spec=configuration.physical_spec.frame,
        source_geometry=source_geometry,
        width_scale_px_per_mm=scales.width_axis_px_per_mm,
        count=output_slot_count,
        phase_lattice_authority=template.phase_lattice_authority,
        template_id=measurement_plan.template_spec.template_id,
    )
    pitch_calibration = calibrate_template_source_pitch(
        template,
        base_phase,
        sequence_edges,
        separator_bands,
        holder_span_px=width_authority,
        refine_from_bound_roles=True,
        max_lattice_hypotheses=measurement_plan.phase_bounds.max_hypotheses,
    )
    registered_pitch_authority_ids = tuple(
        dict.fromkeys(
            (
                *registered_pitch_authority_ids,
                *pitch_calibration.pitch_observation_ids,
            )
        )
    )
    pitch_lattice_hypothesis_count += (
        pitch_calibration.lattice_hypothesis_count
    )
    pitch_lattice_bound_exceeded = (
        pitch_lattice_bound_exceeded or pitch_calibration.bound_exceeded
    )
    template = pitch_calibration.template
    # Rebind the already-registered observations once, then interpret local
    # residuals. No selected-placement query or new pixel read is introduced.
    # A provisional role binding may calibrate continuous W/pitch, but it
    # cannot authorize its own ordinal mapping.  A two-band separator phase
    # hypothesis becomes authority only after a complete legal fit binds
    # another independent direct support; otherwise all bounded role-compatible
    # mappings remain in competition.
    phase_search_authority = close_separator_phase_hypothesis(
        pitch_calibration,
        base_phase,
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
                        else base_phase.best.independent_support_ids
                    ),
                )
            )
        )
    )
    phase_input = TemplatePhaseInput(
        observations=sequence_edges,
        separator_bands=separator_bands,
        template=template,
        scale_px_per_mm=scales.width_axis_px_per_mm,
        holder_span_px=width_authority,
        phase_authority_px=phase_search_authority,
        sequence_measurement_sets=tuple(
            item
            for item in measurement_sets
            if item.query.purpose == QueryPurpose.SEQUENCE_ANCHOR_WINDOW
        ),
        global_lattice_evidence=GlobalLatticeAuthorityEvidence(
            phase_observation_ids=phase_authority_observation_ids,
            frame_width_observation_ids=(
                source_geometry.width_state.observation_ids
            ),
            pitch_observation_ids=registered_pitch_authority_ids,
        ),
    )
    phase = fit_template_phase_with_local_advance(phase_input)
    phase = account_prior_phase_fit(phase, base_phase)
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
    if pitch_lattice_bound_exceeded:
        phase = replace(
            phase,
            best=None,
            runner_up=None,
            status=PhaseFitStatus.BOUND_EXCEEDED,
            ambiguity_reason="separator lattice hypothesis bound exceeded",
            failure_kind=PhaseFailureKind.HYPOTHESIS_BOUND_EXCEEDED,
            winner_basis=None,
        )
    longitudinal_support_domains_px = ()
    if phase.status == PhaseFitStatus.RESOLVED and phase.best is not None:
        domains = tuple(
            sorted(
                resolved_sequence_support_domains_px(phase.best),
                key=lambda item: item.minimum,
            )
        )
        if any(
            left.maximum > right.minimum
            for left, right in zip(domains, domains[1:])
        ):
            phase = replace(
                phase,
                status=PhaseFitStatus.UNRESOLVED,
                ambiguity_reason=(
                    "realized frame domains overlap after direct binding"
                ),
                failure_kind=PhaseFailureKind.FIXED_TEMPLATE_MISMATCH,
                winner_basis=None,
            )
        else:
            longitudinal_support_domains_px = domains
    cross = register_cross_evidence(
        profile=cross_profile,
        top_measurement=precision_measurement_sets[0],
        bottom_measurement=precision_measurement_sets[1],
        width_axis=width_axis,
        height_axis=height_axis,
        height_scale_px_per_mm=scales.height_axis_px_per_mm,
        lane_reference_trace_px=width_authority.center,
        maximum_runs=measurement_plan.cross_bounds.max_registered_runs,
    )
    fixed_height = source_geometry.height_state.extent_projection_px()
    canonical_height = fixed_height.center
    cross = register_template_local_cross_refinements(
        cross,
        top_measurement=precision_measurement_sets[0],
        bottom_measurement=precision_measurement_sets[1],
        width_axis=width_axis,
        height_axis=height_axis,
        height_scale_px_per_mm=scales.height_axis_px_per_mm,
        lane_reference_trace_px=width_authority.center,
        fixed_height_px=fixed_height,
        canonical_height_px=canonical_height,
        longitudinal_support_domains_px=longitudinal_support_domains_px,
        maximum_bindings=measurement_plan.cross_bounds.max_fitted_observations,
    )
    # Coarse measurement happens before sequence scale calibration. Direction
    # remains direct evidence, but boundary use is classified against final H.
    enclosing = _enclosing_support_for_canonical_height(
        coarse_support.enclosing_support,
        canonical_height,
    )
    enclosing_pair_id = (
        ""
        if enclosing is None
        else (
            "coarse-enclosing-pair:"
            f"{enclosing.minimum_track.observation_id}:"
            f"{enclosing.maximum_track.observation_id}"
        )
    )
    coarse_top = (
        ()
        if enclosing is None
        else (
            _coarse_enclosing_binding(
                enclosing.minimum_track,
                BoundaryRole.TOP,
                pair_id=enclosing_pair_id,
            ),
        )
    )
    coarse_bottom = (
        ()
        if enclosing is None
        else (
            _coarse_enclosing_binding(
                enclosing.maximum_track,
                BoundaryRole.BOTTOM,
                pair_id=enclosing_pair_id,
            ),
        )
    )
    top_bindings = (*cross.top_bindings, *coarse_top)
    bottom_bindings = (*cross.bottom_bindings, *coarse_bottom)
    source_direction = _shared_direction_from_coarse(
        coarse_support.shared_direction
    )
    aperture_aspect_ratio = derive_aperture_aspect_ratio_authority(
        source_geometry
    )
    cross_input = TemplateCrossInput(
        template=template,
        fixed_height_px=fixed_height,
        canonical_fixed_height_px=canonical_height,
        lane_reference_trace_px=width_authority.center,
        source_direction=source_direction,
        registered_trace_coordinates_px=precision_measurement_sets[
            0
        ].query.trace_positions_px,
        longitudinal_support_domains_px=longitudinal_support_domains_px,
        top_bindings=top_bindings,
        bottom_bindings=bottom_bindings,
        boundary_axis=height_axis,
        maximum_registered_runs=measurement_plan.cross_bounds.max_registered_runs,
        maximum_fitted_observations=measurement_plan.cross_bounds.max_fitted_observations,
        maximum_compatible_pairs=measurement_plan.cross_bounds.max_compatible_pairs,
        maximum_evaluated_fits=measurement_plan.cross_bounds.max_evaluated_fits,
        registered_run_count=cross.registered_run_count,
        fitted_observation_count=cross.fitted_observation_count,
        aperture_aspect_ratio_authority=aperture_aspect_ratio,
    )
    cross_competition = fit_template_cross(cross_input)
    source_geometry = apply_inferred_aperture_height(
        source_geometry,
        cross_competition.aperture_aspect_ratio_authority,
    )
    source_geometry = calibrate_source_frame_height(
        source_geometry,
        cross_competition,
    )
    registered_values = dict(registered.__dict__)
    registered_values["top_cross_bindings"] = top_bindings
    registered_values["bottom_cross_bindings"] = bottom_bindings
    registered_values["raw_cross_observations"] = cross.observations
    return PreparedTemplateLane(
        **registered_values,
        template_spec=template,
        source_scan_geometry=source_geometry,
        phase_input=phase_input,
        cross_input=cross_input,
        phase_competition=phase,
        cross_competition=cross_competition,
        evidence_use_ledger=template_evidence_use_ledger(
            sequence_edges,
            separator_bands,
            cross.observations,
            phase,
            cross_competition,
            cross_height_edge_resolutions,
        ),
    )
