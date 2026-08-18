"""Register candidate-independent measurements for one template lane."""

from __future__ import annotations

from dataclasses import replace
import math

from ...configuration.model import DetectionConfiguration, ResolvedSlotCount
from ...domain import FiniteInterval, ObservationId
from ..source_core import SourceLaneEvidence
from .axis_layout import axis_interval, coordinate_count, source_axes
from .corridors import (
    build_sequence_anchor_discovery_domain,
    build_top_bottom_search_corridors,
    registered_lane_measurement_queries,
    source_lane_box,
)
from .coarse_strip_support import observe_coarse_strip_support
from .measurement_model import (
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryTransition,
)
from .observation_types import BasicAxisProfile
from .observations import build_sequence_observations
from .output_model import ResolvedOutputSlots
from .profile_adapters import cross_profile_from_regions, sequence_profile_from_regions
from .registered_measurement import measure_registered_queries
from .sequence_edge_families import merge_sequence_edge_families
from .template_evidence import template_evidence_use_ledger
from .template_alignment_diagnostic import enforce_template_alignment
from .template_runtime_model import (
    PreparedTemplateLane,
    RegisteredTemplateLane,
    TemplateMeasurementWorkReceipt,
)
from .template_measurement_plan import compile_template_measurement_plan
from .template_registration import (
    register_cross_evidence,
    register_template_local_cross_refinements,
    short_axis_center_authority,
    template_spec_from_physical_authority,
)
from .template_cross import fit_template_cross
from .template_cross_model import TemplateCrossInput
from .template_phase import (
    account_prior_phase_fit,
    fit_template_phase,
    fit_template_phase_with_local_advance,
)
from .template_phase_model import (
    PhaseFailureKind,
    PhaseFitResult,
    PhaseFitStatus,
    TemplatePhaseInput,
)
from .template_pitch import calibrate_template_source_pitch
from .source_geometry import SourceScanGeometry
from .transition_tracking import track_side_transition_regions


def _canonical_height_from_shared_scale(
    source_geometry: SourceScanGeometry,
) -> float:
    """Project a directly calibrated source scale onto fixed format H.

    Width and height retain separate tolerance intervals, but the scan has one
    pixel/mm scale.  Once direct frame-width spans calibrate that scale, the
    fixed template supplies the normal-path canonical height.  Cross pixels
    still validate and locate the midpoint; they do not resize the format.
    """

    height = source_geometry.height_state.extent_projection_px()
    observed_scale = source_geometry.width_state.observed_normalized_extent
    if observed_scale is None:
        return height.center
    canonical = (
        observed_scale.center
        * source_geometry.frame_spec.frame_height_mm
    )
    return min(height.maximum, max(height.minimum, canonical))


def _calibrated_width_geometry(
    source_geometry: SourceScanGeometry,
    phase: PhaseFitResult,
    sequence_edges,
    *,
    holder_span_px: FiniteInterval,
) -> SourceScanGeometry:
    """Conservatively narrow W after one unique placement is established.

    Each directly bound frame contributes one physical span.  Real scans and
    straight-line annotation can differ slightly across the strip, so all
    compatible spans are retained in one hull; they are never averaged or
    reduced to the prettiest intersecting subset.  W calibration therefore
    cannot discard a direct endpoint or select between placements.
    """

    fit = phase.best
    if phase.status != PhaseFitStatus.RESOLVED or fit is None:
        return source_geometry
    by_id = {item.observation_id: item for item in sequence_edges}
    physical = source_geometry.width_state.extent_projection_px()
    spans: list[
        tuple[int, FiniteInterval, tuple[ObservationId, ObservationId]]
    ] = []
    for ordinal in range(fit.template.count):
        start_id, end_id = fit.role_observation_ids[2 * ordinal : 2 * ordinal + 2]
        if start_id is None or end_id is None:
            continue
        start = by_id[start_id].fit_position_interval_px
        end = by_id[end_id].fit_position_interval_px
        if fit.template.direction > 0:
            measured = FiniteInterval(
                end.minimum - start.maximum,
                end.maximum - start.minimum,
            )
        else:
            measured = FiniteInterval(
                start.minimum - end.maximum,
                start.maximum - end.minimum,
            )
        minimum = max(measured.minimum, physical.minimum)
        maximum = min(measured.maximum, physical.maximum)
        if maximum >= minimum:
            spans.append(
                (
                    ordinal,
                    FiniteInterval(minimum, maximum),
                    (start_id, end_id),
                )
            )
    if len(spans) < 2:
        return source_geometry
    ordinals = tuple(item[0] for item in spans)
    if not any(right == left + 1 for left, right in zip(ordinals, ordinals[1:])):
        return source_geometry
    observed = FiniteInterval(
        min(item[1].minimum for item in spans),
        max(item[1].maximum for item in spans),
    )
    full_span_minimum = (
        observed.minimum
        + fit.pitch_fit.pitch_interval_px.minimum
        * max(0, fit.template.count - 1)
    )
    if full_span_minimum > holder_span_px.width * 1.04:
        return source_geometry
    identities = tuple(
        dict.fromkeys(
            identity
            for _ordinal, _interval, pair in spans
            for identity in pair
        )
    )
    width_state = source_geometry.width_state.intersect_observed_extent(
        observed,
        observation_ids=identities,
    )
    return SourceScanGeometry.from_axis_states(
        source_geometry.frame_spec,
        width_state,
        source_geometry.height_state,
    )


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
    transition_by_id: dict[str, PhotoBoundaryTransition] = {
        str(item.transition_id): item
        for measurement_set in measurement_sets
        for item in measurement_set.transitions
    }
    side_regions = _physical_transition_regions(
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
    sequence_profile = sequence_profile_from_regions(
        side_regions,
        coordinate_count=coordinate_count(width_authority),
        transition_by_id=transition_by_id,
    )
    sequence_profile = merge_sequence_edge_families(
        sequence_profile,
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
    sequence_edges, separator_bands = build_sequence_observations(
        sequence_profile,
        transition_by_id,
        field,
        width_axis,
        scales.width_axis_px_per_mm,
        reference_trace_px=height_authority.center,
        frame_width_px=measurement_plan.template_spec.frame_width_px,
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
        coarse_outer_interval_px=coarse_support.long_axis.direct_interval_px,
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
    pitch_lattice_hypothesis_count = (
        pitch_calibration.lattice_hypothesis_count
    )
    pitch_lattice_bound_exceeded = pitch_calibration.bound_exceeded
    template = pitch_calibration.template
    base_phase = fit_template_phase(
        sequence_edges,
        template,
        separator_bands=separator_bands,
        scale_px_per_mm=scales.width_axis_px_per_mm,
        holder_span_px=width_authority,
        phase_authority_px=pitch_calibration.phase_authority_px,
        coarse_outer_interval_px=coarse_support.long_axis.direct_interval_px,
    )
    source_geometry = _calibrated_width_geometry(
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
    pitch_lattice_hypothesis_count += (
        pitch_calibration.lattice_hypothesis_count
    )
    pitch_lattice_bound_exceeded = (
        pitch_lattice_bound_exceeded or pitch_calibration.bound_exceeded
    )
    template = pitch_calibration.template
    # Rebind the already-registered observations once, then interpret local
    # residuals. No selected-placement query or new pixel read is introduced.
    phase_search_authority = (
        None
        if (
            base_phase.status != PhaseFitStatus.RESOLVED
            or base_phase.best is None
        )
        else base_phase.best.phase_lattice_fit.absolute_phase_interval_px
    )
    phase_input = TemplatePhaseInput(
        observations=sequence_edges,
        separator_bands=separator_bands,
        template=template,
        scale_px_per_mm=scales.width_axis_px_per_mm,
        holder_span_px=width_authority,
        phase_authority_px=phase_search_authority,
        coarse_outer_interval_px=coarse_support.long_axis.direct_interval_px,
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
    else:
        phase = enforce_template_alignment(
            phase,
            sequence_edges,
            separator_bands,
        )
    longitudinal_support_domains_px = (
        ()
        if phase.best is None
        else tuple(
            sorted(
                (
                    FiniteInterval(
                        min(
                            phase.best.canonical_role_positions_px[index],
                            phase.best.canonical_role_positions_px[index + 1],
                        ),
                        max(
                            phase.best.canonical_role_positions_px[index],
                            phase.best.canonical_role_positions_px[index + 1],
                        ),
                    )
                    for index in range(
                        0,
                        len(phase.best.canonical_role_positions_px),
                        2,
                    )
                ),
                key=lambda item: item.minimum,
            )
        )
    )
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
    cross = register_template_local_cross_refinements(
        cross,
        top_measurement=precision_measurement_sets[0],
        bottom_measurement=precision_measurement_sets[1],
        width_axis=width_axis,
        height_axis=height_axis,
        height_scale_px_per_mm=scales.height_axis_px_per_mm,
        lane_reference_trace_px=width_authority.center,
        fixed_height_px=source_geometry.height_state.extent_projection_px(),
        canonical_height_px=_canonical_height_from_shared_scale(source_geometry),
        longitudinal_support_domains_px=longitudinal_support_domains_px,
        maximum_bindings=measurement_plan.cross_bounds.max_fitted_observations,
    )
    cross_input = TemplateCrossInput(
        template=template,
        fixed_height_px=source_geometry.height_state.extent_projection_px(),
        canonical_fixed_height_px=(
            _canonical_height_from_shared_scale(source_geometry)
        ),
        holder_short_axis_center_px=short_axis_center_authority(
            height_authority,
            scales.height_axis_px_per_mm,
        ),
        coarse_outer_interval_px=(
            coarse_support.short_axis.direct_interval_px
        ),
        lane_reference_trace_px=width_authority.center,
        registered_trace_coordinates_px=precision_measurement_sets[
            0
        ].query.trace_positions_px,
        longitudinal_support_domains_px=longitudinal_support_domains_px,
        top_bindings=cross.top_bindings,
        bottom_bindings=cross.bottom_bindings,
        boundary_axis=height_axis,
        maximum_registered_runs=measurement_plan.cross_bounds.max_registered_runs,
        maximum_fitted_observations=measurement_plan.cross_bounds.max_fitted_observations,
        maximum_compatible_pairs=measurement_plan.cross_bounds.max_compatible_pairs,
        maximum_evaluated_fits=measurement_plan.cross_bounds.max_evaluated_fits,
    )
    cross_competition = fit_template_cross(cross_input)
    registered_values = dict(registered.__dict__)
    registered_values["top_cross_bindings"] = cross.top_bindings
    registered_values["bottom_cross_bindings"] = cross.bottom_bindings
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
        ),
    )


__all__ = [
    "lane_measurement_capacity",
    "prepare_template_lane",
    "resolve_output_slots",
]
