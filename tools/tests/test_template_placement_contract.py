from __future__ import annotations

import ast
import math
from pathlib import Path
import unittest

from x5crop.domain import FiniteInterval, ObservationId, PositiveInterval
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole
from x5crop.detection.photo_geometry.output_model import SharedStripDirection
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_cross import (
    CrossEvidence,
    CrossFit,
    CrossRoleBinding,
)
from x5crop.detection.photo_geometry.template_model import (
    PhaseAuthority,
    PitchFit,
    SequenceFit,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_placement import (
    FormatPlacement,
    compose_format_placement,
)


def _template(count: int = 3) -> TemplateSpec:
    return TemplateSpec(
        template_id="placement-test",
        frame_width_px=100.0,
        pitch_px=120.0,
        frame_height_px=240.0,
        count=count,
        phase_authority=PhaseAuthority.FULL_CENTERED,
    )


def _sequence(template: TemplateSpec, *, missing: tuple[int, ...] = ()) -> SequenceFit:
    positions = tuple(
        value
        for ordinal in range(template.count)
        for value in (100.0 + ordinal * 120.0, 200.0 + ordinal * 120.0)
    )
    ids = tuple(
        None if index in missing else ObservationId(f"sequence:{index}")
        for index in range(2 * template.count)
    )
    matched = tuple(index for index in range(2 * template.count) if index not in missing)
    return SequenceFit(
        template=template,
        phase_interval_px=FiniteInterval.exact(100.0),
        canonical_phase_px=100.0,
        pitch_fit=PitchFit(
            frame_width_px=template.frame_width_px,
            gap_interval_px=20.0,
            pitch_interval_px=template.pitch_px,
            canonical_frame_width_px=100.0,
            canonical_pitch_px=120.0,
            observation_ids=tuple(item for item in ids if item is not None),
        ),
        canonical_role_positions_px=positions,
        role_positions_px=tuple(FiniteInterval.exact(value) for value in positions),
        role_observation_ids=ids,
        matched_role_indices=matched,
        inferred_role_indices=tuple(missing),
        direct_observation_ids=tuple(item for item in ids if item is not None),
        support_count=len(matched),
        direct_support_fraction=float(len(matched)),
        polarity_match_count=len(matched),
    )


def _direction(angle: float = 0.0) -> SharedStripDirection:
    return SharedStripDirection(
        direction_id="direction:test",
        selected_observation_ids=(ObservationId("cross:top"), ObservationId("cross:bottom")),
        full_angle_interval_degrees=FiniteInterval(-0.2, 0.2),
        canonical_angle_degrees=angle,
    )


def _binding(role: BoundaryRole, name: str, coordinate: float) -> CrossRoleBinding:
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
        full_direction_interval_degrees=FiniteInterval(-0.2, 0.2),
    )


def _cross(
    template: TemplateSpec,
    *,
    one_sided: bool = False,
    direction: SharedStripDirection | None = None,
    lane_reference: float = 150.0,
) -> CrossFit:
    top = _binding(BoundaryRole.TOP, "top", 10.0)
    bottom = _binding(BoundaryRole.BOTTOM, "bottom", 250.0)
    inferred = (
        CrossRoleBinding(
            role=BoundaryRole.BOTTOM,
            run_id="inferred:top:bottom",
            observation_id=top.observation_id,
            coordinate_interval_px=FiniteInterval.exact(250.0),
            fit_interval_px=FiniteInterval.exact(250.0),
            full_interval_px=FiniteInterval.exact(250.0),
            trace_coordinates_px=top.trace_coordinates_px,
            evidence=CrossEvidence.FIXED_HEIGHT_INFERRED,
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
        center_compatible=True,
    )


def _compose(
    template: TemplateSpec,
    sequence: SequenceFit,
    cross: CrossFit,
    *,
    direction: SharedStripDirection | None = None,
    frame_spec: FramePhysicalSpec | None = None,
) -> FormatPlacement:
    spec = frame_spec or FramePhysicalSpec(36.0, 24.0, 2.0)
    source = SourceScanGeometry.create(
        spec,
        width_scale_px_per_mm=PositiveInterval.exact(10.0),
        height_scale_px_per_mm=PositiveInterval.exact(10.0),
    )
    return compose_format_placement(
        lane_id="lane:test",
        frame_spec=spec,
        source_scan_geometry=source,
        sequence_fit=sequence,
        cross_fit=cross,
        width_axis=BoundaryAxis.X,
        height_axis=BoundaryAxis.Y,
        width_authority_px=FiniteInterval(0.0, 500.0),
        height_authority_px=FiniteInterval(0.0, 400.0),
        direction=direction,
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
