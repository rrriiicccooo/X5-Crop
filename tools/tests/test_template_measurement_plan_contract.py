from __future__ import annotations

import unittest

from x5crop.domain import Box, PositiveInterval
from x5crop.formats import FORMATS, FramePhysicalSpec, format_spec
from x5crop.detection.evidence.scan_canvas import CanvasAxisScaleIntervals
from x5crop.detection.photo_geometry.template_measurement_plan import (
    compile_template_measurement_plan,
)
from x5crop.detection.photo_geometry.template_measurement_plan_model import (
    MeasurementIntentKind,
    MeasurementUnit,
)
from x5crop.detection.source_core import SourceStripValidationDomain


def _authorities(
    format_id: str,
    *,
    scale: float = 10.0,
    box: Box = Box(0, 0, 3600, 2400),
    lane_id: str = "lane:0",
) -> tuple[FramePhysicalSpec, SourceStripValidationDomain, CanvasAxisScaleIntervals]:
    spec = format_spec(format_id)
    profile_id = spec.scan_canvas_fits[0].profile_id
    domain = SourceStripValidationDomain(
        lane_id=lane_id,
        work_box=box,
        source_axis_long="x",
        authority_profile_id=profile_id,
    )
    scales = CanvasAxisScaleIntervals(
        holder_profile_id=profile_id,
        width_axis_px_per_mm=PositiveInterval.exact(scale),
        height_axis_px_per_mm=PositiveInterval.exact(scale),
        source_width_axis="x",
        source_height_axis="y",
    )
    return spec.frame, domain, scales


def _plan(
    format_id: str = "135",
    *,
    count: int = 6,
    full_count: int = 6,
    scale: float = 10.0,
    box: Box = Box(0, 0, 3600, 2400),
):
    spec = format_spec(format_id)
    frame, domain, scales = _authorities(
        format_id,
        scale=scale,
        box=box,
    )
    return compile_template_measurement_plan(
        format_spec=spec,
        frame_spec=frame,
        count=count,
        full_count=full_count,
        holder_full_count=full_count,
        lane_authority=domain,
        layout="horizontal",
        scale_authority=scales,
    )


class TemplateMeasurementPlanContractTest(unittest.TestCase):
    def test_format_dimensions_are_data_not_format_specific_branches(self) -> None:
        one_thirty_five = _plan()
        half = _plan(
            "half",
            count=12,
            full_count=12,
        )
        one_twenty = _plan(
            "120-66",
            count=3,
            full_count=3,
        )
        self.assertNotEqual(
            one_thirty_five.template_spec.frame_width_px,
            half.template_spec.frame_width_px,
        )
        self.assertNotEqual(
            half.template_spec.frame_height_px,
            one_twenty.template_spec.frame_height_px,
        )
        self.assertEqual(len(one_thirty_five.query_intents), 8)
        self.assertEqual(len(half.query_intents), 8)
        self.assertEqual(len(one_twenty.query_intents), 8)

    def test_explicit_count_never_adds_center_phase_authority(self) -> None:
        plan = _plan()
        self.assertFalse(hasattr(plan, "phase_authority"))
        self.assertFalse(hasattr(plan, "normal_path_stop_facts"))
        shorter = _plan(count=5, full_count=6)
        self.assertEqual(shorter.template_spec.count, 5)

    def test_query_intents_are_complete_and_pre_registered(self) -> None:
        plan = _plan()
        self.assertEqual(
            tuple(item.registration_index for item in plan.query_intents),
            tuple(range(8)),
        )
        self.assertEqual(
            tuple(item.kind for item in plan.query_intents),
            (
                MeasurementIntentKind.COARSE_LONG_SUPPORT,
                MeasurementIntentKind.COARSE_SHORT_SUPPORT,
                MeasurementIntentKind.OUTER_SEQUENCE_ANCHOR,
                MeasurementIntentKind.EARLY_SEQUENCE_ANCHOR,
                MeasurementIntentKind.MIDDLE_SEQUENCE_ANCHOR,
                MeasurementIntentKind.LATE_SEQUENCE_ANCHOR,
                MeasurementIntentKind.TOP,
                MeasurementIntentKind.BOTTOM,
            ),
        )
        self.assertTrue(
            all(item.trace_unit == MeasurementUnit.LANE_RATIO for item in plan.query_intents)
        )
        self.assertTrue(
            all(item.search_margin_mm.minimum > 0.0 for item in plan.query_intents)
        )

    def test_compiled_and_executed_work_stays_inside_plan_bounds(self) -> None:
        plan = _plan()
        self.assertGreater(plan.work_bounds.max_work_units, 0)
        self.assertGreater(plan.cross_bounds.max_evaluated_fits, 0)
        self.assertGreater(plan.pixel_bounds.max_registered_queries, len(plan.query_intents))
        plan.validate_execution(
            registered_query_count=3,
            trace_position_count=100,
            coordinate_sample_count=1000,
        )
        with self.assertRaisesRegex(ValueError, "registered-query"):
            plan.validate_execution(
                registered_query_count=plan.pixel_bounds.max_registered_queries + 1,
                trace_position_count=100,
                coordinate_sample_count=1000,
            )

    def test_same_input_identity_is_stable(self) -> None:
        left = _plan()
        right = _plan()
        self.assertEqual(left.physical_identity, right.physical_identity)
        self.assertEqual(left.plan_identity, right.plan_identity)
        self.assertEqual(left.query_intents, right.query_intents)

    def test_format_catalog_is_immutable(self) -> None:
        with self.assertRaises(TypeError):
            FORMATS["new-format"] = format_spec("135")  # type: ignore[index]

    def test_output_precision_budget_is_not_a_measurement_authority(self) -> None:
        plan = _plan()
        self.assertFalse(hasattr(plan, "precision_budget"))
        self.assertNotEqual(
            plan.projected_queries.top_core_intervals_px,
            plan.projected_queries.top_measurement_intervals_px,
        )

    def test_scale_transform_keeps_physical_plan_but_updates_pixel_projection(self) -> None:
        base = _plan(scale=10.0, box=Box(0, 0, 3600, 2400))
        doubled = _plan(scale=20.0, box=Box(0, 0, 7200, 4800))
        self.assertEqual(base.physical_identity, doubled.physical_identity)
        self.assertEqual(base.plan_identity, doubled.plan_identity)
        self.assertEqual(base.query_intents, doubled.query_intents)
        self.assertEqual(base.template_spec.template_id, doubled.template_spec.template_id)
        self.assertNotEqual(
            base.template_spec.frame_width_px,
            doubled.template_spec.frame_width_px,
        )
        self.assertNotEqual(
            base.pixel_bounds.max_coordinate_samples,
            doubled.pixel_bounds.max_coordinate_samples,
        )

    def test_vertical_projection_uses_canonical_work_extents_once(self) -> None:
        spec = format_spec("120-66")
        profile_id = spec.scan_canvas_fits[0].profile_id
        domain = SourceStripValidationDomain(
            lane_id="lane:0",
            work_box=Box(0, 0, 9899, 2797),
            source_axis_long="y",
            authority_profile_id=profile_id,
        )
        scales = CanvasAxisScaleIntervals(
            holder_profile_id=profile_id,
            width_axis_px_per_mm=PositiveInterval.exact(44.0),
            height_axis_px_per_mm=PositiveInterval.exact(44.0),
            source_width_axis="y",
            source_height_axis="x",
        )
        plan = compile_template_measurement_plan(
            format_spec=spec,
            frame_spec=spec.frame,
            count=3,
            full_count=3,
            holder_full_count=3,
            lane_authority=domain,
            layout="vertical",
            scale_authority=scales,
        )
        projected = plan.projected_queries
        self.assertEqual(projected.long_extent_px, 9899)
        self.assertGreater(
            plan.template_spec.phase_lattice_authority.maximum_slot_offset,
            3,
        )
        self.assertLess(max(projected.cross_trace_positions_px), 9899)
        self.assertLess(max(projected.sequence_trace_positions_px), 2797)
        self.assertTrue(
            all(
                interval.maximum <= 2796
                for interval in projected.top_measurement_intervals_px
                + projected.bottom_measurement_intervals_px
            )
        )

    def test_source_and_scale_authority_must_match(self) -> None:
        frame, domain, scales = _authorities("135")
        foreign_frame, _foreign_domain, _foreign_scales = _authorities("half")
        with self.assertRaises(ValueError):
            compile_template_measurement_plan(
                format_spec=format_spec("135"),
                frame_spec=foreign_frame,
                count=6,
                full_count=6,
                holder_full_count=6,
                lane_authority=domain,
                layout="horizontal",
                scale_authority=scales,
            )
        foreign_scales = CanvasAxisScaleIntervals(
            holder_profile_id="foreign-profile",
            width_axis_px_per_mm=scales.width_axis_px_per_mm,
            height_axis_px_per_mm=scales.height_axis_px_per_mm,
            source_width_axis="x",
            source_height_axis="y",
        )
        with self.assertRaises(ValueError):
            compile_template_measurement_plan(
                format_spec=format_spec("135"),
                frame_spec=frame,
                count=6,
                full_count=6,
                holder_full_count=6,
                lane_authority=domain,
                layout="horizontal",
                scale_authority=foreign_scales,
            )

    def test_dual_lane_count_is_compiled_from_format_layout(self) -> None:
        spec = format_spec("135-dual")
        frame, domain, scales = _authorities("135-dual")
        plan = compile_template_measurement_plan(
            format_spec=spec,
            frame_spec=frame,
            count=6,
            full_count=6,
            holder_full_count=12,
            lane_authority=domain,
            layout="horizontal",
            scale_authority=scales,
        )
        self.assertEqual(plan.template_spec.count, 6)
        self.assertEqual(plan.holder_full_count, 12)

if __name__ == "__main__":
    unittest.main()
