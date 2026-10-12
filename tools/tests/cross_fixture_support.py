from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tools.tests.template_test_support import placement_direction
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_cross import (
    calibrate_source_frame_height,
    fit_template_cross,
)
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossEvidence,
    CrossFailureKind,
    CrossFitStatus,
    CrossHeightInferenceBasis,
    CrossHeightProjectionBasis,
    CrossLineProjectionBasis,
    CrossLongitudinalProjectionBasis,
    CrossLongitudinalProjectionFailureKind,
    CrossPairSupportMode,
    CrossRetainedProposalBasis,
    CrossWinnerBasis,
    CrossRoleBinding,
    TemplateCrossInput,
    TemplateCrossInput as _TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_aspect_ratio_model import (
    ApertureAspectRatioAuthority,
    ApertureAspectRatioFailureKind,
)
from x5crop.detection.photo_geometry.output_model import OutputBoundaryUse
from x5crop.detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC
from x5crop.detection.photo_geometry.trace_support import (
    source_spanning_continuous_trace_support,
)
from x5crop.formats import FramePhysicalSpec



from tools.tests.template_test_support import (
    cross_binding as binding,
    cross_template as template,
)

def _interval(value: FiniteInterval | float) -> FiniteInterval:
    return value if isinstance(value, FiniteInterval) else FiniteInterval.exact(value)


def _supported_aspect_ratio(
    height: FiniteInterval | float,
) -> ApertureAspectRatioAuthority:
    interval = _interval(height)
    return ApertureAspectRatioAuthority(
        authority_id="test-aspect-ratio",
        state=EvidenceState.SUPPORTED,
        calibration_id="test-aspect-ratio-calibration",
        axis_guard_calibration_id="test-axis-guard-calibration",
        raw_width_over_height=PositiveInterval.exact(1.0),
        guarded_width_over_height=PositiveInterval.exact(1.0),
        width_guard_mm=0.1,
        height_guard_mm=0.1,
        width_guard_ratio=0.01,
        height_guard_ratio=0.01,
        scale_height_over_width=PositiveInterval.exact(1.0),
        source_width_px=interval,
        inferred_height_px=interval,
        effective_height_px=interval,
        canonical_height_px=interval.center,
        width_observation_ids=tuple(
            ObservationId(f"test-width:{index}") for index in range(4)
        ),
        failure_kind=None,
        failure_detail=None,
    )


def aspect_input(**values) -> _TemplateCrossInput:
    height = values.get("fixed_height_px")
    if height is None:
        template_spec = values["template"]
        height = template_spec.frame_height_px
    values["aperture_aspect_ratio_authority"] = _supported_aspect_ratio(height)
    return _TemplateCrossInput(**values)

from tools.tests.photo_geometry_support import make_native_test_field
from x5crop.detection.photo_geometry.broad_material_association import associate_registered_broad_material

import ast
import math
from dataclasses import fields, replace
from pathlib import Path
import unittest

import numpy as np

from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.evidence.scan_canvas import observe_scan_canvas
from x5crop.detection.photo_geometry.coarse_strip_support import (
    _coarse_short_trace_lattices,
    _measure_coarse_short_trace_lattice,
    _long_axis_search_support,
    _sparse_positions,
    CoarseAxisSupport,
    CoarseStripSupport,
    CoarseStripSupportReceipt,
    CoarseSupportAuthority,
    observe_coarse_strip_support,
    registered_coarse_support_queries,
)
from x5crop.detection.photo_geometry.coarse_enclosing_model import (
    CoarseEnclosingMeasurementBasis,
    CoarseEnclosingResolution,
    CoarseEnclosingResolutionFailureKind,
    CoarseEnclosingTrack,
    CoarseSupportSide,
)
from x5crop.detection.photo_geometry.coarse_enclosing_support import (
    _fit_track,
    _shared_tracks,
    observe_coarse_short_axis_tracks,
    observe_coarse_broad_side_facts,
)
from tools.tests.photo_geometry_support import make_side_measurement_set
from tools.tests.template_runtime_test_support import prepared_template_lane
from x5crop.report.read_models import typed_read_model
from x5crop.detection.photo_geometry.broad_material_transition_measurement import (
    measure_broad_material_transitions,
)
from x5crop.detection.photo_geometry.corridors import (
    build_sequence_anchor_discovery_domain,
    build_top_bottom_search_corridors,
)
from x5crop.detection.photo_geometry.lane_preparation import (
    _coarse_enclosing_binding,
    _enclosing_support_for_canonical_height,
    _shared_direction_from_coarse,
)
from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    BoundaryRole,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    QueryPurpose,
)
from x5crop.detection.photo_geometry.registered_transition_measurement import (
    TraceMeasurement,
    measure_trace,
    trace_storage_bytes,
)
from x5crop.detection.photo_geometry.template_measurement_plan import (
    compile_template_measurement_plan,
)
from x5crop.detection.photo_geometry.template_model import (
    template_role_refinement_radius_px,
)
from x5crop.detection.photo_geometry.template_runtime_model import RegisteredTemplateLane
from x5crop.detection.source_core import (
    SourceLaneEvidence,
    SourceStripValidationDomain,
)
from x5crop.domain import Box, EvidenceState, FiniteInterval, ObservationId, PositiveInterval


from x5crop.detection.photo_geometry.template_coarse_sides import register_coarse_side_facts, coarse_enclosing_binding
from x5crop.detection.photo_geometry.template_cross_support import fit_enclosing_support, support_permission_view, SupportFitStatus


def _cross_side_competition(measurement, plan, sharp_support=None):
    reference = 1159.5
    facts = observe_coarse_broad_side_facts(measurement,
        aggregate_interval_px=FiniteInterval(30.5, 294.5),
        expected_height_px=plan.template_spec.frame_height_px,
        reference_trace_px=reference)
    top, bottom, work = register_coarse_side_facts(facts, remaining_bound=512)
    if sharp_support is not None:
        pair_id = "test:sharp-pair"
        top = (coarse_enclosing_binding(sharp_support.minimum_track, BoundaryRole.TOP, pair_id=pair_id), *top)
        bottom = (coarse_enclosing_binding(sharp_support.maximum_track, BoundaryRole.BOTTOM, pair_id=pair_id), *bottom)
    height = FiniteInterval(plan.template_spec.frame_height_px.minimum, plan.template_spec.frame_height_px.maximum)
    pool = fit_enclosing_support(template=plan.template_spec, fixed_height=height,
        canonical_height_px=height.center, reference_trace_px=reference,
        top_bindings=top, bottom_bindings=bottom,
        registered_trace_coordinates_px=measurement.query.trace_positions_px,
        longitudinal_support_domain_groups_px=(), minimum_shared_trace_support=3,
        maximum_evaluated_candidates=4096)
    return facts, work, support_permission_view(pool, canonical_only=True)


def _unavailable_enclosing_resolution() -> CoarseEnclosingResolution:
    return CoarseEnclosingResolution(
        state=EvidenceState.UNAVAILABLE,
        candidates=(),
        selected_candidate=None,
        failure_kind=(
            CoarseEnclosingResolutionFailureKind.PAIR_UNAVAILABLE
        ),
    )


def _lane(
    *,
    layout: str = "horizontal",
    long_extent: int = 2320,
    short_extent: int = 322,
) -> tuple[SourceLaneEvidence, object]:
    configuration = get_detection_configuration("135")
    canvas = observe_scan_canvas(
        long_extent,
        short_extent,
        layout,
        configuration.scan_canvas,
    )
    lane = SourceLaneEvidence(
        SourceStripValidationDomain(
            "lane:0",
            Box(0, 0, long_extent, short_extent),
            "x" if layout == "horizontal" else "y",
            "135_standard",
        ),
        canvas,
    )
    scales = canvas.axis_scales
    assert scales is not None
    plan = compile_template_measurement_plan(
        format_spec=configuration.physical_spec,
        frame_spec=configuration.physical_spec.frame,
        count=6,
        full_count=6,
        holder_full_count=6,
        lane_authority=lane.domain,
        layout=layout,
        scale_authority=scales,
    )
    return lane, plan


# Native coarse fixture: raw native/material evidence plus the resolved cross record.
from copy import deepcopy
from x5crop.detection.photo_geometry.template_registration import project_cross_solver_bindings
from x5crop.detection.photo_geometry.lane_preparation import _shared_direction_from_coarse

def native_coarse_fixture():
    lane, plan = _lane()
    pixels = np.full((322, 2320), 255, dtype=np.uint8)
    pixels[35:290, 260:2060] = 80
    coarse, measurements = observe_coarse_strip_support(
        make_native_test_field(pixels, "horizontal"),
        lane, layout="horizontal", measurement_plan=plan,
    )
    support = coarse.enclosing_support
    pair_id = (
        f"coarse-enclosing-pair:{support.minimum_track.observation_id}:"
        f"{support.maximum_track.observation_id}"
    )
    top = (coarse_enclosing_binding(support.minimum_track, BoundaryRole.TOP, pair_id=pair_id),)
    bottom = (coarse_enclosing_binding(support.maximum_track, BoundaryRole.BOTTOM, pair_id=pair_id),)
    native_top, native_bottom, work = register_coarse_side_facts(
        coarse.enclosing_side_facts, remaining_bound=510
    )
    top, bottom = (*top, *native_top), (*bottom, *native_bottom)
    height = plan.template_spec.frame_height_px
    solver_top, solver_bottom = project_cross_solver_bindings(top), project_cross_solver_bindings(bottom)
    inputs = TemplateCrossInput(
        template=plan.template_spec,
        source_direction=_shared_direction_from_coarse(coarse.shared_direction),
        fixed_height_px=FiniteInterval(height.minimum, height.maximum),
        lane_reference_trace_px=1159.5,
        top_bindings=solver_top,
        bottom_bindings=solver_bottom,
        registered_trace_coordinates_px=measurements[1].query.trace_positions_px,
        registered_top_run_count=0,
        registered_bottom_run_count=0,
        fitted_observation_count=len(top) + len(bottom),
        coarse_side_registration=work,
        maximum_fitted_observations=512,
        maximum_registered_runs_per_role=512,
    )
    competition = fit_template_cross(inputs)
    record = {
        "lane_id": lane.domain.lane_id,
        "template_spec": typed_read_model(plan.template_spec),
        "search": {"coarse_strip_support": typed_read_model(coarse)},
        "cross_input": typed_read_model(inputs),
        "cross_competition": typed_read_model(competition),
    }
    queries = typed_read_model(measurements)
    top_query = deepcopy(queries[1]["query"])
    top_query.update(query_id="fixture:top", purpose="top_corridor")
    queries.append({"query": top_query})
    return (
        coarse,
        inputs,
        competition,
        record,
        queries,
        {str(item.observation_id): typed_read_model(item) for item in (*top, *bottom)},
        [{"domain": typed_read_model(lane.domain)}],
    )


# Registration fixtures are shared by registration and local-refinement contracts.
def registration_top_anchor() -> CrossRoleBinding:
    return CrossRoleBinding(
        role=BoundaryRole.TOP,
        run_id="top:source-wide",
        observation_id=ObservationId("top:source-wide"),
        coordinate_interval_px=FiniteInterval(19.5, 20.5),
        trace_coordinates_px=(0, 10, 20, 30, 40, 50),
        support_fraction=1.0,
        continuous_support_fraction=1.0,
        fit_residual_px=0.0,
        canonical_direction_degrees=0.0,
        fit_direction_interval_degrees=FiniteInterval(-0.05, 0.05),
        full_direction_interval_degrees=FiniteInterval(-0.1, 0.1),
        independent_support_region_count=3,
        source_spanning_continuous=True,
        role_authorized=True,
    )

def registration_bottom_measurement(
    coordinates_by_trace: tuple[tuple[float, ...], ...],
):
    measurement = make_side_measurement_set(coordinates_by_trace)
    return replace(
        measurement,
        transitions=tuple(
            replace(
                item,
                left_texture_mean=5.0,
                right_texture_mean=1.0,
            )
            for item in measurement.transitions
        ),
    )

from dataclasses import replace
import itertools
import math
import unittest

from scipy.optimize import linprog

from x5crop.domain import FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_family_membership import (
    MembershipAtom, MembershipFitBudget, MembershipReceipt, MembershipState,
    MembershipTransition, enumerate_membership_scope, new_membership_groups,
)


def _problem(groups, anchors, intervals=None):
    intervals = intervals or {}
    atoms = tuple(MembershipAtom(ObservationId(name), tuple(ObservationId(f'{name}:{trace}') for trace in traces),
                                 2 if name in anchors else 1) for name, traces in groups.items())
    raw = tuple(MembershipTransition(ObservationId(f'{name}:{trace}'), float(trace),
                                     FiniteInterval(*intervals.get((name, trace), (-1, 1))))
                for name, traces in groups.items() for trace in traces)
    return dict(parent_family_id='parent', role=BoundaryRole.TOP, atoms=atoms, transitions=raw,
                query_trace_positions_px=tuple(sorted({int(point.trace_coordinate_px) for point in raw})),
                scale_px_per_mm=1.0, remaining_visits=4096)
