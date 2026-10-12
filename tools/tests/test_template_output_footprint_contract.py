from __future__ import annotations

import ast
from dataclasses import replace
import inspect
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from x5crop.domain import (
    Box,
    EvidenceState,
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
    WorkspaceExtent,
    ObservationId,
    PositiveInterval,
)
from x5crop.formats import (
    DEVELOPMENT_GOLD_CALIBRATION_COHORT_SHA256,
    EnclosingSupportApertureCalibrationSpec,
)
from x5crop.formats.scan_canvas import ScanCanvasPhysicalSpec
from x5crop.detection.gate_checks import GateGap
from x5crop.detection.evidence.scan_canvas import (
    CanvasAxisScaleIntervals,
    ScanCanvasEvidence,
    ScanCanvasOutcome,
    ScanCanvasProfileMatch,
)
from x5crop.detection.photo_geometry.model import (
    AuthoritySide,
    BoundaryAxis,
    BoundaryRole,
)
from x5crop.detection.photo_geometry.output_model import (
    FootprintSaturationKind,
    fixed_output_rectangle,
    OutputBoundaryUse,
    sampling_authority_bounds,
)
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossFit,
    CrossFitStatus,
    CrossHeightProjectionBasis,
    CrossLineProjectionBasis,
    EnclosingSupportPair,
)
from x5crop.detection.photo_geometry.template_gate import build_template_gate
from x5crop.detection.photo_geometry.template_holder_fill import HolderFillState
from x5crop.detection.photo_geometry.source_geometry import SourceFixedOutputSize
from x5crop.detection.photo_geometry.template_phase_model import PhaseFitStatus
from x5crop.detection.photo_geometry.template_nominal_grid_authority import (
    assess_calibrated_nominal_grid_authority,
)
from x5crop.detection.photo_geometry.template_output import (
    _aperture_binding_positions,
    _enclosing_support_aperture_risk,
    _footprint,
    _frame_boundary_residuals,
    _line_outward_expansion_px,
    _saturation_facts,
    _state_footprint,
    output_footprint_from_template_placement,
    template_direct_use_budget_assessment,
)
from x5crop.detection.photo_geometry.template_feasible_geometry import (
    JointFrameState,
    _shared_slope_polygon_vertices,
    _support_cross_vertices,
    project_format_placement,
)
from x5crop.geometry.convex import clip_convex_polygon_to_bounds, convex_hull
from x5crop.detection.photo_geometry.template_enclosing_support_aperture import (
    derive_enclosing_support_aperture_authority,
    unavailable_enclosing_support_aperture_authority,
)
from x5crop.detection.photo_geometry.template_placement import (
    resolved_cross_support_domains_px,
)
from x5crop.detection.photo_geometry.line_observations import PhysicalLineRegion, SourceCoordinateLine
from x5crop.detection.photo_geometry.template_model import (
    ContactRelation,
    OverlapRelation,
    SequenceRoleLineEvidence,
)
from x5crop.detection.source_core import (
    SourceLaneEvidence,
    SourceStripValidationDomain,
)
from tools.tests.template_test_support import (
    placement_binding as _binding,
    placement_compose as _compose,
    placement_cross as _cross,
    placement_direction as _direction,
    placement_sequence as _sequence,
    placement_template as _template,
)

from tools.tests.output_fixture_support import (
    _contact_placement,
    _enclosing_support_placement,
    _lane,
    _overlap_placement,
    _placement,
    _selected_output_gate_fact,
)

class TemplateOutputFootprintContractTest(unittest.TestCase):
    def test_selected_placement_produces_supported_output_footprint(self) -> None:
            placement = _placement()
            output = output_footprint_from_template_placement(
                placement,
                project_format_placement(placement),
                lane=_lane(),
                lane_ordinal=1,
                layout="horizontal",
            )
            self.assertEqual(
                output.envelope.canonical_source_footprint,
                placement.frames[0].canonical_source_polygon,
            )
            self.assertFalse(output.saturation_facts)
            self.assertEqual(output.required_source_footprint, output.requested_source_footprint)
            self.assertAlmostEqual(
                output.requested_source_footprint[1][0]
                - output.requested_source_footprint[0][0],
                output.fixed_size.output_width_px,
            )
            assessment = template_direct_use_budget_assessment(
                placement,
                output,
            )
            self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
            self.assertEqual(
                tuple(item.role for item in assessment.edge_assessments),
                (
                    BoundaryRole.START,
                    BoundaryRole.END,
                    BoundaryRole.TOP,
                    BoundaryRole.BOTTOM,
                ),
            )
            self.assertEqual(
                tuple(assessment.edge_assessments[0].__dataclass_fields__),
                ("role", "required_extent_px", "available_extent_px", "within_limit"),
            )
            self.assertEqual(
                tuple(assessment.__dataclass_fields__),
                ("geometry_id", "boundary_use", "edge_assessments", "state"),
            )
            self.assertEqual(assessment.geometry_id, output.geometry_id)

    def test_source_fixed_size_is_stable_when_physical_residuals_change(self) -> None:
            base_placement = _contact_placement()
            base = output_footprint_from_template_placement(
                base_placement,
                project_format_placement(base_placement),
                lane=_lane(),
                lane_ordinal=1,
                layout="horizontal",
            )
            residual = _contact_placement(shared_direction_uncertainty_degrees=10.0)
            changed = output_footprint_from_template_placement(
                residual,
                project_format_placement(residual),
                lane=_lane(),
                lane_ordinal=1,
                layout="horizontal",
            )
            self.assertEqual(base.fixed_size, changed.fixed_size)
            self.assertEqual(base.fixed_size.source_geometry_id, changed.fixed_size.source_geometry_id)
            self.assertEqual(
                tuple(base.fixed_size.__dataclass_fields__),
                ("source_geometry_id", "frame_width_px", "frame_height_px", "margin_ratio_per_side"),
            )
            self.assertEqual(base.fixed_size.margin_ratio_per_side, 0.05)
            self.assertEqual(base.width_axis, BoundaryAxis.X)
            self.assertEqual(base.sequence_direction, 1)
            self.assertNotEqual(base.boundary_protections, changed.boundary_protections)
            for output in (base, changed):
                self.assertAlmostEqual(
                    max(x for x, _ in output.requested_source_footprint)
                    - min(x for x, _ in output.requested_source_footprint),
                    output.fixed_size.output_width_px,
                )
                self.assertAlmostEqual(
                    max(y for _, y in output.requested_source_footprint)
                    - min(y for _, y in output.requested_source_footprint),
                    output.fixed_size.output_height_px,
                )

    def test_source_clipping_preserves_requested_fixed_size(self) -> None:
            placement = _placement()
            small_lane = _lane()
            small_lane = replace(
                small_lane,
                domain=replace(small_lane.domain, work_box=Box(0, 0, 500, 80)),
                scan_canvas=replace(small_lane.scan_canvas, observed_short_axis_px=80),
            )
            output = output_footprint_from_template_placement(
                placement,
                project_format_placement(placement),
                lane=small_lane,
                lane_ordinal=1,
                layout="horizontal",
            )
            self.assertAlmostEqual(
                max(y for _, y in output.requested_source_footprint)
                - min(y for _, y in output.requested_source_footprint),
                output.fixed_size.output_height_px,
            )
            self.assertEqual(min(x for x, _ in output.required_source_footprint), -.5)
            self.assertAlmostEqual(max(x for x, _ in output.required_source_footprint),
                                   -.5 + output.fixed_size.output_width_px)
            self.assertEqual((min(y for _, y in output.required_source_footprint),
                              max(y for _, y in output.required_source_footprint)), (-.5, 79.5))
            self.assertIn(AuthoritySide.BOTTOM, tuple(
                item.authority_side for item in output.saturation_facts
            ))

    def test_mandatory_lane_overflow_is_explicit_and_never_clipped(self) -> None:
            placement = _placement()
            lane = _lane()
            lane = replace(
                lane,
                domain=replace(lane.domain, work_box=Box(0, 20, 500, 400)),
            )
            output = output_footprint_from_template_placement(
                placement,
                project_format_placement(placement),
                lane=lane,
                lane_ordinal=1,
                layout="horizontal",
            )
            self.assertIn(
                AuthoritySide.TOP,
                tuple(item.authority_side for item in output.saturation_facts),
            )
            top = next(
                item
                for item in output.saturation_facts
                if item.authority_side == AuthoritySide.TOP
            )
            self.assertEqual(
                top.kind,
                FootprintSaturationKind.LANE_BOUNDARY_JOINT_PROTECTION,
            )
            self.assertGreater(top.mandatory_overflow_px, 0.0)
            self.assertFalse(output.source_authority_supported)
            self.assertEqual(
                output.required_source_footprint,
                output.requested_source_footprint,
            )
            self.assertLess(
                min(point[1] for point in output.required_source_footprint),
                float(lane.domain.work_box.top),
            )
            self.assertFalse(hasattr(output, "mapped_output_box"))
            assessment = template_direct_use_budget_assessment(
                placement,
                output,
            )
            self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
            self.assertTrue(all(item.within_limit for item in assessment.edge_assessments))
            gate_fact = _selected_output_gate_fact(output, assessment)
            self.assertEqual(gate_fact.state, EvidenceState.CONTRADICTED)
            self.assertEqual(
                gate_fact.failure.detail,
                "top:lane_boundary_joint_protection",
            )

    def test_true_source_edge_clips_only_unavailable_optional_content(self) -> None:
            placement = _placement()
            lane = _lane()
            lane = replace(
                lane,
                domain=replace(lane.domain, work_box=Box(0, 0, 500, 253)),
                scan_canvas=replace(lane.scan_canvas, observed_short_axis_px=253),
            )

            output = output_footprint_from_template_placement(
                placement,
                project_format_placement(placement),
                lane=lane,
                lane_ordinal=1,
                layout="horizontal",
            )

            self.assertIn(
                AuthoritySide.BOTTOM,
                tuple(item.authority_side for item in output.saturation_facts),
            )
            saturation = next(
                item for item in output.saturation_facts
                if item.authority_side == AuthoritySide.BOTTOM
            )
            self.assertEqual(
                saturation.kind,
                FootprintSaturationKind.SOURCE_BOUNDARY_OPTIONAL_BLEED,
            )
            self.assertEqual(saturation.mandatory_overflow_px, 0.0)
            self.assertGreater(saturation.requested_overflow_px, 0.0)
            self.assertTrue(output.source_authority_supported)
            self.assertLessEqual(
                max(point[1] for point in output.mandatory_source_footprint),
                252.0,
            )
            self.assertGreater(
                max(point[1] for point in output.requested_source_footprint),
                252.0,
            )
            self.assertEqual(
                max(point[1] for point in output.required_source_footprint),
                252.5,
            )
            gate_fact = _selected_output_gate_fact(
                output,
                template_direct_use_budget_assessment(placement, output),
            )
            self.assertEqual(gate_fact.state, EvidenceState.SUPPORTED)

    def test_true_source_edge_keeps_mandatory_overflow_visible(self) -> None:
            placement = _placement()
            lane = _lane()
            lane = replace(
                lane,
                domain=replace(lane.domain, work_box=Box(0, 0, 500, 251)),
                scan_canvas=replace(lane.scan_canvas, observed_short_axis_px=251),
            )

            output = output_footprint_from_template_placement(
                placement,
                project_format_placement(placement),
                lane=lane,
                lane_ordinal=1,
                layout="horizontal",
            )

            self.assertIn(
                AuthoritySide.BOTTOM,
                tuple(item.authority_side for item in output.saturation_facts),
            )
            saturation = next(
                item for item in output.saturation_facts
                if item.authority_side == AuthoritySide.BOTTOM
            )
            self.assertEqual(
                saturation.kind,
                FootprintSaturationKind.SOURCE_BOUNDARY_JOINT_PROTECTION,
            )
            self.assertGreater(saturation.mandatory_overflow_px, 0.0)
            self.assertTrue(output.source_authority_supported)
            self.assertGreater(
                max(point[1] for point in output.requested_source_footprint),
                250.0,
            )
            self.assertEqual(
                max(point[1] for point in output.required_source_footprint),
                250.5,
            )
            gate_fact = _selected_output_gate_fact(
                output,
                template_direct_use_budget_assessment(placement, output),
            )
            self.assertEqual(gate_fact.state, EvidenceState.SUPPORTED)

    def test_internal_lane_edge_cannot_clip_mandatory_content(self) -> None:
            placement = _placement()
            lane = _lane()
            lane = replace(
                lane,
                domain=replace(lane.domain, work_box=Box(0, 0, 500, 253)),
            )

            output = output_footprint_from_template_placement(
                placement,
                project_format_placement(placement),
                lane=lane,
                lane_ordinal=1,
                layout="horizontal",
            )

            self.assertIn(
                FootprintSaturationKind.LANE_BOUNDARY_OPTIONAL_BLEED,
                tuple(item.kind for item in output.saturation_facts),
            )
            self.assertIn(
                AuthoritySide.BOTTOM,
                tuple(item.authority_side for item in output.saturation_facts),
            )
            self.assertFalse(output.source_authority_supported)
            self.assertEqual(
                output.required_source_footprint,
                output.requested_source_footprint,
            )
            gate_fact = _selected_output_gate_fact(
                output,
                template_direct_use_budget_assessment(placement, output),
            )
            self.assertEqual(gate_fact.state, EvidenceState.CONTRADICTED)
            self.assertEqual(
                gate_fact.failure.detail,
                "bottom:lane_boundary_optional_bleed",
            )

    def test_source_footprint_is_safe_without_output_transform(self) -> None:
            placement = _placement()
            output = output_footprint_from_template_placement(
                placement,
                project_format_placement(placement),
                lane=_lane(),
                lane_ordinal=1,
                layout="horizontal",
            )

            self.assertFalse(output.saturation_facts)
            self.assertEqual(output.required_source_footprint, output.requested_source_footprint)
            self.assertFalse(hasattr(output, "sampling_source_footprint"))
            self.assertFalse(hasattr(output, "mapped_output_box"))

    def test_mandatory_content_that_cannot_fit_keeps_fixed_proposal_for_review(self) -> None:
            placement = _placement()
            top, bottom = placement.cross_fit.direct_bindings
            top = replace(
                top,
                coordinate_interval_px=FiniteInterval.exact(-20.0),
                fit_interval_px=FiniteInterval.exact(-20.0),
                full_interval_px=FiniteInterval.exact(-20.0),
            )
            bottom = replace(
                bottom,
                coordinate_interval_px=FiniteInterval.exact(250.0),
                fit_interval_px=FiniteInterval.exact(250.0),
                full_interval_px=FiniteInterval.exact(250.0),
            )
            cross = replace(
                placement.cross_fit,
                fixed_height_px=FiniteInterval.exact(270.0),
                top_canonical_px=-20.0,
                bottom_canonical_px=250.0,
                top_fit_interval_px=FiniteInterval.exact(-20.0),
                bottom_fit_interval_px=FiniteInterval.exact(250.0),
                top_full_interval_px=FiniteInterval.exact(-20.0),
                bottom_full_interval_px=FiniteInterval.exact(250.0),
                direct_bindings=(top, bottom),
            )
            placement = replace(placement, cross_fit=cross)
            output = output_footprint_from_template_placement(
                placement,
                project_format_placement(placement),
                lane=_lane(),
                lane_ordinal=1,
                layout="horizontal",
            )
            assessment = template_direct_use_budget_assessment(placement, output)
            self.assertEqual(assessment.state, EvidenceState.CONTRADICTED)
            self.assertAlmostEqual(
                output.requested_source_footprint[1][0]
                - output.requested_source_footprint[0][0],
                output.fixed_size.output_width_px,
            )
            self.assertAlmostEqual(
                output.requested_source_footprint[2][1]
                - output.requested_source_footprint[1][1],
                output.fixed_size.output_height_px,
            )
            bottom = next(
                item
                for item in assessment.edge_assessments
                if item.role == BoundaryRole.BOTTOM
            )
            self.assertFalse(bottom.within_limit)

    def test_uncontainable_axis_keeps_fitted_position_and_full_protection(self) -> None:
            placement = _placement()
            original = output_footprint_from_template_placement(
                placement,
                project_format_placement(placement),
                lane=_lane(),
                lane_ordinal=1,
                layout="horizontal",
            )
            canonical = original.envelope.canonical_source_footprint
            center = (
                (min(x for x, _ in canonical) + max(x for x, _ in canonical)) / 2.0,
                (min(y for _, y in canonical) + max(y for _, y in canonical)) / 2.0,
            )
            # Asymmetric uncertainty extends far past one side of the fitted
            # photograph. It is a failed protection budget, not a new position.
            mandatory = convex_hull(((0.0, 100.0), (400.0, 100.0),
                                     (400.0, 200.0), (0.0, 200.0)))
            extent = WorkspaceExtent(1000, 1000)
            requested = fixed_output_rectangle(
                original.fixed_size, original.width_axis, mandatory, extent,
                preferred_center=center,
            )
            authority = Box(0, 0, 1000, 1000)
            saturation = _saturation_facts(requested, mandatory, authority, extent)
            required = clip_convex_polygon_to_bounds(
                requested, sampling_authority_bounds(authority, extent),
            ) if saturation else requested
            output = replace(
                original,
                mandatory_source_footprint=mandatory,
                requested_source_footprint=requested,
                required_source_footprint=required,
                sampling_authority_box=authority,
                source_extent=extent,
                saturation_facts=saturation,
            )

            self.assertAlmostEqual(
                (min(x for x, _ in requested) + max(x for x, _ in requested)) / 2.0,
                center[0],
            )
            self.assertEqual(output.mandatory_source_footprint, mandatory)
            self.assertEqual(
                template_direct_use_budget_assessment(placement, output).state,
                EvidenceState.CONTRADICTED,
            )
