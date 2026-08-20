from __future__ import annotations

import ast
import math
from pathlib import Path
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
)


class TemplatePlacementContractTest(unittest.TestCase):
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
        placement = _compose(template, _sequence(template), _cross(template, one_sided=True), direction=_direction())
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
            center_compatible=True,
            boundary_use=OutputBoundaryUse.APERTURE_PAIR,
        )
        frame = _compose(template, sequence, cross).frames[0]
        self.assertEqual(frame.start.full_position_interval_px, FiniteInterval.exact(100.0))
        self.assertEqual(frame.end.full_position_interval_px, FiniteInterval.exact(200.0))
        self.assertEqual(frame.top.full_position_interval_px, FiniteInterval.exact(10.0))
        self.assertEqual(frame.bottom.full_position_interval_px, FiniteInterval.exact(250.0))

    def test_sloped_cross_line_is_reanchored_at_each_frame_trace(self) -> None:
        template = _template(1)
        placement = _compose(template, _sequence(template), _cross(template, direction=_direction(0.2), lane_reference=100.0))
        top = placement.frames[0].top
        angle = math.radians(0.2)
        normal_x, normal_y = -math.sin(angle), math.cos(angle)
        source_trace = 100.0
        source_position = 10.0
        offset = normal_x * source_trace + normal_y * source_position
        frame_trace = top.reference_trace_px
        expected = (offset - normal_x * frame_trace) / normal_y
        self.assertAlmostEqual(top.canonical_position_px, expected, places=8)
        expected_states = tuple(
            source_position
            + math.tan(math.radians(state_angle))
            * (frame_trace - source_trace)
            for state_angle in (-0.2, 0.2)
        )
        self.assertAlmostEqual(
            top.full_position_interval_px.minimum,
            min(expected_states),
            places=8,
        )
        self.assertAlmostEqual(
            top.full_position_interval_px.maximum,
            max(expected_states),
            places=8,
        )

    def test_source_shared_direction_can_cover_lane_direction(self) -> None:
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
            _cross(template, direction=lane_direction),
            direction=shared,
        )
        self.assertEqual(placement.direction, shared)
        self.assertEqual(
            placement.frames[0].top.direction_reference_id,
            shared.direction_id,
        )

    def test_no_direction_and_contradiction_are_rejected(self) -> None:
        template = _template(1)
        with self.assertRaises(ValueError):
            _compose(template, _sequence(template), _cross(template, direction=None))
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

    def test_source_has_no_legacy_imports(self) -> None:
        path = Path(__file__).parents[2] / "x5crop/detection/photo_geometry/template_placement.py"
        tree = ast.parse(path.read_text())
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        names = [alias.name for node in imports for alias in getattr(node, "names", ())]
        self.assertFalse(any(any(token in name for token in ("chains", "materialization", "selection", "cache")) for name in names))


if __name__ == "__main__":
    unittest.main()
