from __future__ import annotations

from dataclasses import replace
import inspect
import math
import unittest

from tools.tests.template_test_support import (
    placement_binding as _binding,
    placement_compose as _compose,
    placement_cross as _cross,
    placement_direction as _direction,
    placement_sequence as _sequence,
    placement_template as _template,
)
from x5crop.domain import FiniteInterval, ObservationId, PositiveInterval
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole
from x5crop.detection.photo_geometry.output_model import (
    OutputBoundaryUse,
    SharedStripDirection,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossFit,
)
from x5crop.detection.photo_geometry.template_model import (
    PhaseLatticeAuthority,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_placement import (
    compose_format_placement,
    resolved_sequence_support_domains_px,
)


class TemplatePlacementContractTest(unittest.TestCase):
    def test_three_region_direction_does_not_create_a_frame_axis(self) -> None:
        template = _template(1)
        cross = _cross(template, direction=_direction(0.15))
        top, bottom = cross.direct_bindings
        top = replace(
            top,
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=FiniteInterval(-0.02, 0.02),
            full_direction_interval_degrees=FiniteInterval(-0.50, 0.50),
            observed_direction_interval_degrees=FiniteInterval(-0.50, 0.50),
        )
        bottom = replace(
            bottom,
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=FiniteInterval(-0.02, 0.02),
            full_direction_interval_degrees=FiniteInterval(-0.40, 0.60),
            observed_direction_interval_degrees=FiniteInterval(-0.40, 0.60),
        )
        cross_direction = replace(
            cross.selected_direction,
            full_angle_interval_degrees=FiniteInterval(-0.50, 0.60),
            observed_angle_interval_degrees=FiniteInterval(-0.50, 0.60),
            canonical_angle_degrees=0.15,
        )
        cross = replace(
            cross,
            direct_bindings=(top, bottom),
            selected_direction=cross_direction,
            independent_support_region_count=3,
        )

        placement = _compose(template, _sequence(template), cross)

        self.assertFalse(hasattr(placement, "direction"))
        self.assertEqual(
            placement.frames[0].canonical_source_polygon,
            ((100.0, 10.0), (200.0, 10.0), (200.0, 250.0), (100.0, 250.0)),
        )

    def test_shared_direction_cannot_change_boundary_local_geometry(
        self,
    ) -> None:
        template = _template(1)
        sequence = _sequence(template)
        cross = _cross(template, direction=_direction(0.20))
        top, bottom = cross.direct_bindings
        top = replace(
            top,
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=FiniteInterval(-0.05, 0.05),
            full_direction_interval_degrees=FiniteInterval(-0.50, 0.20),
            observed_direction_interval_degrees=FiniteInterval(-0.50, 0.20),
        )
        bottom = replace(
            bottom,
            canonical_direction_degrees=0.40,
            fit_direction_interval_degrees=FiniteInterval(0.35, 0.45),
            full_direction_interval_degrees=FiniteInterval(0.20, 0.60),
            observed_direction_interval_degrees=FiniteInterval(0.20, 0.60),
        )
        cross_direction = replace(
            cross.selected_direction,
            full_angle_interval_degrees=FiniteInterval(-0.50, 0.60),
            observed_angle_interval_degrees=FiniteInterval(-0.50, 0.60),
            canonical_angle_degrees=0.20,
        )
        cross = replace(
            cross,
            direct_bindings=(top, bottom),
            selected_direction=cross_direction,
            independent_support_region_count=2,
            longitudinal_support_domain_count=2,
            role_authorized_pair_support_domain_count=2,
        )
        baseline = _compose(template, sequence, cross)
        placement = _compose(
            template,
            sequence,
            replace(cross, selected_direction=_direction(-0.15)),
        )

        self.assertNotIn(
            "sequence_observations",
            inspect.signature(compose_format_placement).parameters,
        )
        self.assertFalse(hasattr(placement, "direction"))
        self.assertEqual(placement.frames[0].top.line.normal_x, 0.0)
        self.assertEqual(placement.frames[0].top.line.normal_y, 1.0)
        self.assertEqual(placement.frames[0].bottom.line.normal_x, 0.0)
        self.assertEqual(placement.frames[0].bottom.line.normal_y, 1.0)
        self.assertEqual(placement.frames[0].start.line.normal_x, 1.0)
        self.assertEqual(placement.frames[0].start.line.normal_y, 0.0)
        self.assertEqual(placement.frames, baseline.frames)

    def test_three_direct_frames_preserve_ids_and_polygon(self) -> None:
        template = _template()
        placement = _compose(template, _sequence(template), _cross(template, direction=_direction()))
        self.assertEqual(placement.output_slot_count, 3)
        self.assertEqual(tuple(frame.lane_ordinal for frame in placement.frames), (1, 2, 3))
        self.assertTrue(all(abs(frame.canonical_source_polygon[1][0] - frame.canonical_source_polygon[0][0]) > 0 for frame in placement.frames))
        self.assertEqual(placement.frames[0].start.position_observation_ids, (ObservationId("sequence:0"),))

    def test_missing_sequence_role_uses_fixed_width_inference(self) -> None:
        template = _template(1)
        placement = _compose(template, _sequence(template, missing=(1,)), _cross(template, direction=_direction()))
        end = placement.frames[0].end
        self.assertEqual(end.position_source.value, "inferred_sequence")
        self.assertEqual(end.named_position_inference, "end_from_observed_start_and_fixed_template_width")
        self.assertEqual(end.position_observation_ids, (ObservationId("sequence:0"),))
        self.assertAlmostEqual(end.canonical_position_px, 200.0)

    def test_cross_single_side_uses_fixed_height_inference(self) -> None:
        template = _template(1)
        placement = _compose(
            template,
            _sequence(template),
            _cross(template, one_sided=True, direction=_direction()),
        )
        self.assertEqual(placement.frames[0].bottom.position_source.value, "inferred_opposite_edge")
        self.assertIn("fixed_template_height", placement.frames[0].bottom.named_position_inference or "")
        self.assertEqual(placement.frames[0].bottom.position_observation_ids, (ObservationId("cross:top"),))

    def test_fixed_dimensions_and_ordinals_are_consistent(self) -> None:
        template = _template()
        placement = _compose(template, _sequence(template), _cross(template, direction=_direction()))
        for ordinal, frame in enumerate(placement.frames):
            self.assertEqual(frame.lane_ordinal, ordinal + 1)
            self.assertAlmostEqual(frame.end.canonical_position_px - frame.start.canonical_position_px, 100.0)
            self.assertAlmostEqual(frame.bottom.canonical_position_px - frame.top.canonical_position_px, 240.0)

    def test_direct_edges_consume_the_fit_uncertainty_once(self) -> None:
        template = TemplateSpec(
            template_id="placement-interval-test",
            frame_width_px=FiniteInterval(96.0, 104.0),
            pitch_px=FiniteInterval(116.0, 124.0),
            frame_height_px=FiniteInterval(232.0, 248.0),
            count=1,
            phase_lattice_authority=PhaseLatticeAuthority(
                period_px=FiniteInterval(116.0, 124.0),
                cycle_origin_px=0.0,
                minimum_slot_offset=-1,
                maximum_slot_offset=20,
            ),
        )
        sequence = _sequence(template)
        top = _binding(BoundaryRole.TOP, "top", 10.0)
        bottom = _binding(BoundaryRole.BOTTOM, "bottom", 250.0)
        cross = CrossFit(
            template_id=template.template_id,
            lane_reference_trace_px=150.0,
            fixed_height_px=FiniteInterval(232.0, 248.0),
            top_canonical_px=10.0,
            bottom_canonical_px=250.0,
            top_fit_interval_px=FiniteInterval.exact(10.0),
            bottom_fit_interval_px=FiniteInterval.exact(250.0),
            top_full_interval_px=FiniteInterval.exact(10.0),
            bottom_full_interval_px=FiniteInterval.exact(250.0),
            direct_bindings=(top, bottom),
            inferred_bindings=(),
            selected_direction=_direction(),
            direct_pair=True,
            shared_trace_support_count=3,
            continuous_support_fraction=1.0,
            residual_sum_px=0.0,
            boundary_use=OutputBoundaryUse.APERTURE_PAIR,
        )
        frame = _compose(template, sequence, cross).frames[0]
        self.assertEqual(frame.start.full_position_interval_px, FiniteInterval.exact(100.0))
        self.assertEqual(frame.end.full_position_interval_px, FiniteInterval.exact(200.0))
        self.assertEqual(frame.top.full_position_interval_px, FiniteInterval.exact(10.0))
        self.assertEqual(frame.bottom.full_position_interval_px, FiniteInterval.exact(250.0))

    def test_direct_edges_keep_native_positions_instead_of_grid_positions(self) -> None:
        template = replace(
            _template(1),
            frame_width_px=FiniteInterval(96.0, 104.0),
        )
        sequence = _sequence(template)
        cross = _cross(template, direction=_direction())
        model_placement = _compose(template, sequence, cross)
        bindings = list(sequence.role_bindings)
        assert bindings[0] is not None and bindings[1] is not None
        bindings[0] = replace(
            bindings[0],
            canonical_position_px=102.0,
            fit_position_interval_px=FiniteInterval(101.5, 102.5),
            full_position_interval_px=FiniteInterval(101.5, 102.5),
        )
        bindings[1] = replace(
            bindings[1],
            canonical_position_px=201.0,
            fit_position_interval_px=FiniteInterval(200.5, 201.5),
            full_position_interval_px=FiniteInterval(200.5, 201.5),
        )
        sequence = replace(
            sequence,
            role_bindings=tuple(bindings),
        )

        placement = _compose(
            template,
            sequence,
            cross,
        )

        self.assertEqual(sequence.model_role_positions_px, (100.0, 200.0))
        self.assertEqual(placement.frames[0].start.canonical_position_px, 102.0)
        self.assertEqual(placement.frames[0].end.canonical_position_px, 201.0)
        self.assertEqual(
            resolved_sequence_support_domains_px(sequence),
            (FiniteInterval(102.0, 201.0),),
        )
        self.assertNotEqual(placement.placement_id, model_placement.placement_id)

    def test_single_direct_edge_projects_source_width_from_native_position(self) -> None:
        template = replace(
            _template(1),
            frame_width_px=FiniteInterval(96.0, 104.0),
        )
        sequence = _sequence(template, missing=(1,))
        bindings = list(sequence.role_bindings)
        assert bindings[0] is not None
        bindings[0] = replace(
            bindings[0],
            canonical_position_px=102.0,
            fit_position_interval_px=FiniteInterval(101.5, 102.5),
            full_position_interval_px=FiniteInterval(101.5, 102.5),
        )
        sequence = replace(
            sequence,
            role_bindings=tuple(bindings),
        )

        frame = _compose(
            template,
            sequence,
            _cross(template, direction=_direction()),
        ).frames[0]

        self.assertEqual(frame.start.canonical_position_px, 102.0)
        self.assertEqual(frame.end.canonical_position_px, 202.0)
        self.assertEqual(
            frame.end.full_position_interval_px,
            FiniteInterval(197.5, 206.5),
        )
        self.assertEqual(
            resolved_sequence_support_domains_px(sequence),
            (FiniteInterval(102.0, 202.0),),
        )

    def test_sloped_cross_evidence_does_not_reanchor_output_boundary(self) -> None:
        template = _template(1)
        cross = _cross(
            template,
            direction=_direction(-0.15),
            lane_reference=100.0,
        )
        top, bottom = cross.direct_bindings
        top = replace(
            top,
            canonical_direction_degrees=0.2,
            fit_direction_interval_degrees=FiniteInterval(0.18, 0.22),
            full_direction_interval_degrees=FiniteInterval(0.16, 0.24),
            observed_direction_interval_degrees=FiniteInterval(0.16, 0.24),
        )
        cross = replace(cross, direct_bindings=(top, bottom))
        placement = _compose(template, _sequence(template), cross)
        top = placement.frames[0].top
        self.assertEqual(top.canonical_position_px, 10.0)
        self.assertEqual(top.full_position_interval_px, FiniteInterval.exact(10.0))
        self.assertEqual(top.line.normal_x, 0.0)
        self.assertEqual(top.line.normal_y, 1.0)
        self.assertEqual(placement.frames[0].start.line.normal_x, 1.0)
        self.assertEqual(placement.frames[0].start.line.normal_y, 0.0)

    def test_aperture_offset_projects_only_inside_direct_trace_support(self) -> None:
        template = _template(2)
        cross = _cross(
            template,
            direction=_direction(0.1),
            lane_reference=150.0,
        )
        top, bottom = cross.direct_bindings
        supported = tuple(
            replace(
                binding,
                trace_coordinates_px=(100, 150, 300),
                canonical_direction_degrees=0.1,
            )
            for binding in (top, bottom)
        )
        placement = _compose(
            template,
            _sequence(template),
            replace(cross, direct_bindings=supported),
        )
        expected_shift = math.tan(math.radians(0.1)) * 120.0

        self.assertAlmostEqual(
            placement.frames[1].top.canonical_position_px,
            10.0 + expected_shift,
        )
        self.assertAlmostEqual(
            placement.frames[1].bottom.canonical_position_px
            - placement.frames[1].top.canonical_position_px,
            240.0,
        )
        self.assertEqual(placement.frames[1].top.line.normal_x, 0.0)
        self.assertEqual(placement.frames[1].top.line.normal_y, 1.0)

        unsupported = tuple(
            replace(binding, trace_coordinates_px=(100, 150, 200))
            for binding in supported
        )
        unprojected = _compose(
            template,
            _sequence(template),
            replace(cross, direct_bindings=unsupported),
        )
        self.assertEqual(
            unprojected.frames[1].top.canonical_position_px,
            10.0,
        )

    def test_cross_local_direction_is_not_a_placement_property(self) -> None:
        template = _template(1)
        lane_direction = _direction(0.05)
        shared = SharedStripDirection(
            direction_id="direction:source-shared",
            selected_observation_ids=(
                *lane_direction.selected_observation_ids,
                ObservationId("cross:other-lane"),
            ),
            full_angle_interval_degrees=FiniteInterval(-0.1, 0.2),
            observed_angle_interval_degrees=FiniteInterval(-0.1, 0.2),
            canonical_angle_degrees=0.08,
        )
        placement = _compose(
            template,
            _sequence(template),
            _cross(template, direction=shared),
        )
        self.assertFalse(hasattr(placement, "direction"))
        self.assertFalse(hasattr(placement.frames[0].top, "direction_reference_id"))

    def test_resolved_cross_local_direction_is_not_blocked_by_sequence_direction_conflict(
        self,
    ) -> None:
        template = _template(1)
        sequence = _sequence(template)
        cross = _cross(template, direction=_direction())
        top, bottom = cross.direct_bindings
        top = replace(
            top,
            canonical_direction_degrees=-0.15,
            fit_direction_interval_degrees=FiniteInterval(-0.18, -0.12),
            full_direction_interval_degrees=FiniteInterval(-0.20, -0.10),
            observed_direction_interval_degrees=FiniteInterval(-0.20, -0.10),
        )
        bottom = replace(
            bottom,
            canonical_direction_degrees=0.05,
            fit_direction_interval_degrees=FiniteInterval(0.02, 0.08),
            full_direction_interval_degrees=FiniteInterval(0.00, 0.10),
            observed_direction_interval_degrees=FiniteInterval(0.00, 0.10),
        )
        local_direction = SharedStripDirection(
            direction_id="direction:local-cross",
            selected_observation_ids=(top.observation_id, bottom.observation_id),
            full_angle_interval_degrees=FiniteInterval(-0.20, 0.10),
            observed_angle_interval_degrees=FiniteInterval(-0.20, 0.10),
            canonical_angle_degrees=-0.05,
        )
        cross = replace(
            cross,
            direct_bindings=(top, bottom),
            selected_direction=local_direction,
            independent_support_region_count=2,
            longitudinal_support_domain_count=2,
            role_authorized_pair_support_domain_count=2,
        )
        placement = _compose(
            template,
            sequence,
            cross,
        )

        self.assertFalse(hasattr(placement, "direction"))
        self.assertTrue(
            all(
                frame.top.line.normal_x == 0.0
                and frame.top.line.normal_y == 1.0
                and frame.bottom.line.normal_x == 0.0
                and frame.bottom.line.normal_y == 1.0
                and frame.start.line.normal_x == 1.0
                and frame.start.line.normal_y == 0.0
                and frame.end.line.normal_x == 1.0
                and frame.end.line.normal_y == 0.0
                for frame in placement.frames
            )
        )

    def test_missing_cross_direction_is_allowed_but_geometry_contradiction_is_rejected(self) -> None:
        template = _template(1)
        placement = _compose(
            template,
            _sequence(template),
            _cross(template, direction=None),
        )
        self.assertFalse(hasattr(placement, "direction"))
        good_spec = FramePhysicalSpec(36.0, 24.0, 2.0)
        bad_spec = FramePhysicalSpec(35.0, 24.0, 2.0)
        source = SourceScanGeometry.create(
            good_spec,
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )
        with self.assertRaises(ValueError):
            compose_format_placement(
                lane_id="lane:test",
                frame_spec=bad_spec,
                source_scan_geometry=source,
                sequence_fit=_sequence(template),
                cross_fit=_cross(template, direction=_direction()),
                width_axis=BoundaryAxis.X,
                height_axis=BoundaryAxis.Y,
                width_authority_px=FiniteInterval(0.0, 500.0),
                height_authority_px=FiniteInterval(0.0, 400.0),
            )

if __name__ == "__main__":
    unittest.main()
