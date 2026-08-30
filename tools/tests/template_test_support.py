"""Canonical typed fixtures shared by template contract tests."""

from __future__ import annotations

from dataclasses import replace
import math

from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    BoundaryRole,
    QueryPurpose,
)
from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeMeasurementBasis,
    BoundaryEdgeObservation,
    SeparatorBandObservation,
    SeparatorMaterialPolarity,
    SeparatorMaterialRegionObservation,
    SeparatorMaterialRegionState,
)
from x5crop.detection.photo_geometry.output_model import (
    OutputBoundaryUse,
    SharedStripDirection,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossEvidence,
    CrossFit,
    CrossRoleBinding,
)
from x5crop.detection.photo_geometry.template_model import (
    PhaseLatticeAuthority,
    PhaseLatticeFit,
    PitchFit,
    SequenceFit,
    SequenceBindingUse,
    SequenceRoleBinding,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_placement import (
    FormatPlacement,
    compose_format_placement,
)
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from x5crop.formats import FramePhysicalSpec


def phase_edge(
    name: str,
    coordinate: float,
    *,
    support_fraction: float = 1.0,
) -> BoundaryEdgeObservation:
    identity = ObservationId(name)
    interval = FiniteInterval(coordinate - 0.2, coordinate + 0.2)
    return BoundaryEdgeObservation(
        observation_id=identity,
        run_id=f"run:{name}",
        discovery_interval_px=interval,
        reference_trace_px=10.0,
        canonical_position_px=coordinate,
        fit_position_interval_px=interval,
        full_position_interval_px=interval,
        transition_ids=(ObservationId(f"transition:{name}"),),
        trace_coordinates_px=(0, 10, 20),
        polarity=1,
        support_fraction=support_fraction,
        continuous_support_fraction=support_fraction,
        fit_residual_px=0.0,
        canonical_direction_degrees=None,
        fit_direction_interval_degrees=None,
        full_direction_interval_degrees=None,
        measurement_basis=BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        qualified_anchor_roles=(BoundaryRole.START, BoundaryRole.END),
    )


def transformed_phase_edge(
    observation: BoundaryEdgeObservation,
    *,
    scale: float = 1.0,
    offset: float = 0.0,
) -> BoundaryEdgeObservation:
    def interval(value: FiniteInterval) -> FiniteInterval:
        return FiniteInterval(
            value.minimum * scale + offset,
            value.maximum * scale + offset,
        )

    return replace(
        observation,
        discovery_interval_px=interval(observation.discovery_interval_px),
        reference_trace_px=observation.reference_trace_px * scale,
        canonical_position_px=(
            observation.canonical_position_px * scale + offset
        ),
        fit_position_interval_px=interval(
            observation.fit_position_interval_px
        ),
        full_position_interval_px=interval(
            observation.full_position_interval_px
        ),
        trace_coordinates_px=tuple(
            int(round(value * scale))
            for value in observation.trace_coordinates_px
        ),
        fit_residual_px=observation.fit_residual_px * scale,
    )


def phase_template(count: int) -> TemplateSpec:
    return TemplateSpec(
        template_id="test-template",
        frame_width_px=100.0,
        pitch_px=120.0,
        count=count,
        phase_lattice_authority=PhaseLatticeAuthority(
            period_px=120.0,
            cycle_origin_px=0.0,
            minimum_slot_offset=-1,
            maximum_slot_offset=20,
        ),
        nominal_gap_px=20.0,
    )


def phase_separator(
    name: str,
    left: BoundaryEdgeObservation,
    right: BoundaryEdgeObservation,
    gap: FiniteInterval,
    *,
    region_count: int = 3,
    material_polarity: SeparatorMaterialPolarity = (
        SeparatorMaterialPolarity.DARK
    ),
) -> SeparatorBandObservation:
    material = tuple(
        SeparatorMaterialRegionObservation(
            region_index=index,
            sample_count=3,
            material_contrast_interval=FiniteInterval(2.0, 3.0),
            core_texture_interval=FiniteInterval(0.5, 0.75),
            state=SeparatorMaterialRegionState.SUPPORTED,
        )
        for index in range(region_count)
    )
    return SeparatorBandObservation(
        observation_id=ObservationId(name),
        left_edge_observation_id=left.observation_id,
        right_edge_observation_id=right.observation_id,
        left_run_id=left.run_id,
        right_run_id=right.run_id,
        material_polarity=material_polarity,
        gap_interval_px=gap,
        transition_ids=(
            ObservationId(f"transition:{name}:left"),
            ObservationId(f"transition:{name}:right"),
        ),
        material_support_region_count=region_count,
        continuous_support_fraction=1.0,
        material_contrast=2.5,
        material_contrast_interval=FiniteInterval(2.0, 3.0),
        core_texture=0.625,
        core_texture_interval=FiniteInterval(0.5, 0.75),
        material_regions=material,
    )


def phase_sequence_measurement(
    name: str,
    ownership_interval_px: FiniteInterval,
    *,
    trace_positions_px: tuple[int, ...] = (0, 10, 20),
    complete: bool = True,
) -> PhotoBoundaryMeasurementSet:
    """Create one pre-registered sequence-window coverage fixture."""

    query_id = f"query:{name}"
    query = PhotoBoundaryMeasurementQuery(
        query_id=query_id,
        registration_index=0,
        lane_id="lane:test",
        purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
        boundary_axis=BoundaryAxis.X,
        trace_positions_px=trace_positions_px,
        search_intervals_px=tuple(
            ownership_interval_px for _trace in trace_positions_px
        ),
        transition_ownership_intervals_px=tuple(
            ownership_interval_px for _trace in trace_positions_px
        ),
        expected_support_px=100.0,
        boundary_axis_scale_px_per_mm=PositiveInterval.exact(10.0),
        trace_axis_scale_px_per_mm=PositiveInterval.exact(10.0),
        measurement_halo_px=1,
        registration_provenance_ids=(f"intent:{name}",),
    )
    coordinate_count = len(trace_positions_px) * max(
        0,
        int(math.floor(ownership_interval_px.maximum))
        - int(math.ceil(ownership_interval_px.minimum))
        + 1,
    )
    coverage = PhotoBoundaryCoverageReceipt(
        query_id=query_id,
        registered_trace_count=len(trace_positions_px),
        completed_trace_count=(len(trace_positions_px) if complete else 0),
        registered_coordinate_count=coordinate_count,
        completed_coordinate_count=(coordinate_count if complete else 0),
        pixel_query_count=(coordinate_count if complete else 0),
        streaming_block_count=(1 if complete else 0),
        peak_temporary_bytes=0,
        complete=complete,
    )
    return PhotoBoundaryMeasurementSet(
        query=query,
        state=(EvidenceState.SUPPORTED if complete else EvidenceState.UNAVAILABLE),
        transitions=(),
        cross_height_transitions=(),
        coverage=coverage,
    )


def cross_template(count: int = 1) -> TemplateSpec:
    return TemplateSpec(
        template_id="cross-test",
        frame_width_px=100.0,
        pitch_px=120.0,
        frame_height_px=240.0,
        count=count,
        phase_lattice_authority=PhaseLatticeAuthority(
            period_px=120.0,
            cycle_origin_px=0.0,
            minimum_slot_offset=-1,
            maximum_slot_offset=20,
        ),
    )


def cross_binding(
    role: BoundaryRole,
    name: str,
    coordinate: float,
    *,
    traces: tuple[int, ...] = (0, 50, 100),
    residual: float = 0.0,
    support: float = 1.0,
    continuous: float = 1.0,
    angle: float | None = 0.0,
    angle_interval: FiniteInterval | None = FiniteInterval(-0.2, 0.2),
    full_angle_interval: FiniteInterval | None = None,
    independent_regions: int = 3,
    source_spanning: bool = True,
    role_authorized: bool = True,
    enclosing_pair_id: str | None = None,
) -> CrossRoleBinding:
    coordinate_interval = FiniteInterval.exact(coordinate)
    return CrossRoleBinding(
        role=role,
        run_id=f"run:{name}",
        observation_id=ObservationId(f"observation:{name}"),
        coordinate_interval_px=coordinate_interval,
        trace_coordinates_px=traces,
        support_fraction=support,
        continuous_support_fraction=continuous,
        fit_residual_px=residual,
        fit_interval_px=coordinate_interval,
        full_interval_px=coordinate_interval,
        canonical_direction_degrees=angle,
        fit_direction_interval_degrees=angle_interval,
        full_direction_interval_degrees=(
            angle_interval
            if full_angle_interval is None
            else full_angle_interval
        ),
        independent_support_region_count=independent_regions,
        source_spanning_continuous=source_spanning,
        role_authorized=role_authorized,
        enclosing_pair_id=enclosing_pair_id,
        trace_position_intervals_px=(
            tuple(FiniteInterval.exact(coordinate) for _ in traces)
            if enclosing_pair_id is not None
            else ()
        ),
    )


def placement_template(count: int = 3) -> TemplateSpec:
    return TemplateSpec(
        template_id="placement-test",
        frame_width_px=100.0,
        pitch_px=120.0,
        frame_height_px=240.0,
        count=count,
        phase_lattice_authority=PhaseLatticeAuthority(
            period_px=120.0,
            cycle_origin_px=0.0,
            minimum_slot_offset=-1,
            maximum_slot_offset=20,
        ),
    )


def placement_sequence(
    template: TemplateSpec,
    *,
    missing: tuple[int, ...] = (),
) -> SequenceFit:
    width = (
        template.frame_width_px.minimum + template.frame_width_px.maximum
    ) / 2.0
    pitch = (template.pitch_px.minimum + template.pitch_px.maximum) / 2.0
    positions = tuple(
        value
        for ordinal in range(template.count)
        for value in (
            100.0 + ordinal * pitch,
            100.0 + ordinal * pitch + width,
        )
    )
    ids = tuple(
        None if index in missing else ObservationId(f"sequence:{index}")
        for index in range(2 * template.count)
    )
    bindings = tuple(
        None
        if identity is None
        else SequenceRoleBinding(
            use=SequenceBindingUse.PHASE_ANCHOR,
            observation_id=identity,
            independent_support_id=identity,
            canonical_position_px=positions[index],
            fit_position_interval_px=FiniteInterval.exact(positions[index]),
            full_position_interval_px=FiniteInterval.exact(positions[index]),
            line_evidence=None,
        )
        for index, identity in enumerate(ids)
    )
    phase_support_count = len(
        {
            (index + 1) // 2
            for index, binding in enumerate(bindings)
            if binding is not None
        }
    )
    return SequenceFit(
        template=template,
        phase_lattice_fit=PhaseLatticeFit(
            authority=template.phase_lattice_authority,
            cycle_phase_interval_px=FiniteInterval.exact(100.0),
            canonical_cycle_phase_px=100.0,
            integer_slot_offset=0,
            canonical_period_px=pitch,
            absolute_phase_interval_px=FiniteInterval.exact(100.0),
            canonical_absolute_phase_px=100.0,
            direction=1,
        ),
        pitch_fit=PitchFit(
            frame_width_px=template.frame_width_px,
            gap_interval_px=template.gap_prior_px,
            pitch_interval_px=template.pitch_px,
            canonical_frame_width_px=width,
            canonical_pitch_px=pitch,
            observation_ids=tuple(item for item in ids if item is not None),
        ),
        model_role_positions_px=positions,
        model_role_intervals_px=tuple(
            FiniteInterval.exact(value) for value in positions
        ),
        model_full_role_intervals_px=tuple(
            FiniteInterval.exact(value) for value in positions
        ),
        role_bindings=bindings,
        phase_support_coverage=float(phase_support_count),
    )


def placement_direction(angle: float = 0.0) -> SharedStripDirection:
    return SharedStripDirection(
        direction_id="direction:test",
        selected_observation_ids=(
            ObservationId("cross:top"),
            ObservationId("cross:bottom"),
        ),
        full_angle_interval_degrees=FiniteInterval(-0.2, 0.2),
        observed_angle_interval_degrees=FiniteInterval(-0.2, 0.2),
        canonical_angle_degrees=angle,
    )


def placement_binding(
    role: BoundaryRole,
    name: str,
    coordinate: float,
) -> CrossRoleBinding:
    exact = FiniteInterval.exact(coordinate)
    return CrossRoleBinding(
        role=role,
        run_id=f"run:{name}",
        observation_id=ObservationId(f"cross:{name}"),
        coordinate_interval_px=exact,
        fit_interval_px=exact,
        full_interval_px=exact,
        trace_coordinates_px=(0, 50, 100),
        canonical_direction_degrees=0.0,
        fit_direction_interval_degrees=FiniteInterval(-0.2, 0.2),
        full_direction_interval_degrees=FiniteInterval(-0.2, 0.2),
    )


def placement_cross(
    template: TemplateSpec,
    *,
    one_sided: bool = False,
    direction: SharedStripDirection | None = None,
    lane_reference: float = 150.0,
) -> CrossFit:
    top = placement_binding(BoundaryRole.TOP, "top", 10.0)
    bottom = placement_binding(BoundaryRole.BOTTOM, "bottom", 250.0)
    inferred = (
        CrossRoleBinding(
            role=BoundaryRole.BOTTOM,
            run_id="inferred:top:bottom",
            observation_id=top.observation_id,
            coordinate_interval_px=FiniteInterval.exact(250.0),
            fit_interval_px=FiniteInterval.exact(250.0),
            full_interval_px=FiniteInterval.exact(250.0),
            trace_coordinates_px=top.trace_coordinates_px,
            evidence=CrossEvidence.ASPECT_RATIO_HEIGHT_INFERRED,
            source_observation_ids=(top.observation_id,),
        ),
    ) if one_sided else ()
    return CrossFit(
        template_id=template.template_id,
        lane_reference_trace_px=lane_reference,
        fixed_height_px=FiniteInterval.exact(240.0),
        top_canonical_px=10.0,
        bottom_canonical_px=250.0,
        top_fit_interval_px=FiniteInterval.exact(10.0),
        bottom_fit_interval_px=FiniteInterval.exact(250.0),
        top_full_interval_px=FiniteInterval.exact(10.0),
        bottom_full_interval_px=FiniteInterval.exact(250.0),
        direct_bindings=(top,) if one_sided else (top, bottom),
        inferred_bindings=inferred,
        selected_direction=direction,
        direct_pair=not one_sided,
        shared_trace_support_count=3,
        continuous_support_fraction=1.0,
        residual_sum_px=0.0,
        boundary_use=OutputBoundaryUse.APERTURE_PAIR,
    )


def placement_compose(
    template: TemplateSpec,
    sequence: SequenceFit,
    cross: CrossFit,
    *,
    frame_spec: FramePhysicalSpec | None = None,
    lane_id: str = "lane:test",
) -> FormatPlacement:
    spec = frame_spec or FramePhysicalSpec(36.0, 24.0, 2.0)
    source = SourceScanGeometry.create(
        spec,
        width_scale_px_per_mm=PositiveInterval.exact(10.0),
        height_scale_px_per_mm=PositiveInterval.exact(10.0),
    )
    return compose_format_placement(
        lane_id=lane_id,
        frame_spec=spec,
        source_scan_geometry=source,
        sequence_fit=sequence,
        cross_fit=cross,
        width_axis=BoundaryAxis.X,
        height_axis=BoundaryAxis.Y,
        width_authority_px=FiniteInterval(
            0.0,
            max(sequence.model_role_positions_px) + 100.0,
        ),
        height_authority_px=FiniteInterval(0.0, 400.0),
    )


__all__ = [
    "cross_binding",
    "cross_template",
    "phase_edge",
    "phase_separator",
    "phase_template",
    "placement_binding",
    "placement_compose",
    "placement_cross",
    "placement_direction",
    "placement_sequence",
    "placement_template",
    "transformed_phase_edge",
]
