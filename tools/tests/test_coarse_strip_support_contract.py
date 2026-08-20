from __future__ import annotations

import ast
from pathlib import Path
import unittest

import numpy as np

from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.evidence.scan_canvas import observe_scan_canvas
from x5crop.detection.photo_geometry.coarse_strip_support import (
    CoarseAxisSupport,
    CoarseStripSupport,
    CoarseStripSupportReceipt,
    CoarseSupportAuthority,
    observe_coarse_strip_support,
    registered_coarse_support_queries,
)
from x5crop.detection.photo_geometry.corridors import (
    build_sequence_anchor_discovery_domain,
    build_top_bottom_search_corridors,
)
from x5crop.detection.photo_geometry.lane_preparation import (
    _enclosing_support_for_canonical_height,
    _shared_direction_from_coarse,
)
from x5crop.detection.photo_geometry.model import BoundaryAxis, QueryPurpose
from x5crop.detection.photo_geometry.registered_measurement import (
    make_photo_boundary_measurement_field,
)
from x5crop.detection.photo_geometry.template_measurement_plan import (
    compile_template_measurement_plan,
)
from x5crop.detection.source_core import (
    SourceLaneEvidence,
    SourceStripValidationDomain,
)
from x5crop.domain import Box, FiniteInterval, ObservationId


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


class CoarseStripSupportContractTest(unittest.TestCase):
    @staticmethod
    def _observed_support(
        pixels: np.ndarray,
        *,
        layout: str = "horizontal",
    ) -> CoarseStripSupport:
        long_extent = pixels.shape[1] if layout == "horizontal" else pixels.shape[0]
        short_extent = pixels.shape[0] if layout == "horizontal" else pixels.shape[1]
        lane, plan = _lane(
            layout=layout,
            long_extent=long_extent,
            short_extent=short_extent,
        )
        support, _ = observe_coarse_strip_support(
            make_photo_boundary_measurement_field(pixels, layout),
            lane,
            layout=layout,
            measurement_plan=plan,
        )
        return support

    def test_blank_pixels_keep_one_conservative_path(self) -> None:
        lane, plan = _lane()
        field = make_photo_boundary_measurement_field(
            np.zeros((322, 2320), dtype=np.uint8),
            "horizontal",
        )

        support, measurements = observe_coarse_strip_support(
            field,
            lane,
            layout="horizontal",
            measurement_plan=plan,
        )

        self.assertEqual(len(measurements), 2)
        self.assertEqual(
            tuple(item.query.purpose for item in measurements),
            (QueryPurpose.COARSE_STRIP_LONG, QueryPurpose.COARSE_STRIP_SHORT),
        )
        self.assertEqual(
            support.long_axis.authority,
            CoarseSupportAuthority.HOLDER_CONSERVATIVE,
        )
        self.assertEqual(
            support.short_axis.authority,
            CoarseSupportAuthority.HOLDER_CONSERVATIVE,
        )
        self.assertEqual(support.long_axis.interval_px, FiniteInterval(0.0, 2319.0))
        self.assertEqual(support.short_axis.interval_px, FiniteInterval(0.0, 321.0))

    def test_vertical_queries_map_canonical_axes_once(self) -> None:
        lane, plan = _lane(
            layout="vertical",
            long_extent=9899,
            short_extent=1375,
        )
        long_query, short_query = registered_coarse_support_queries(
            lane,
            layout="vertical",
            measurement_plan=plan,
        )

        self.assertEqual(long_query.boundary_axis, BoundaryAxis.Y)
        self.assertEqual(short_query.boundary_axis, BoundaryAxis.X)
        self.assertTrue(all(trace < 1375 for trace in long_query.trace_positions_px))
        self.assertTrue(all(trace < 9899 for trace in short_query.trace_positions_px))
        self.assertEqual(long_query.search_intervals_px[0], FiniteInterval(0.0, 9898.0))
        self.assertEqual(short_query.search_intervals_px[0], FiniteInterval(0.0, 1374.0))

    def test_coarse_support_only_localizes_registered_precision_work(self) -> None:
        lane, plan = _lane()
        support = CoarseStripSupport(
            "lane:0",
            CoarseAxisSupport(
                FiniteInterval(100.0, 2200.0),
                FiniteInterval(300.0, 2000.0),
                CoarseSupportAuthority.PIXEL_OBSERVED,
                (ObservationId("coarse:long"),),
            ),
            CoarseAxisSupport(
                FiniteInterval(20.0, 300.0),
                None,
                CoarseSupportAuthority.HOLDER_CONSERVATIVE,
                (),
            ),
            None,
            None,
            CoarseStripSupportReceipt(2, 2, 2, 2, 1, 2, 2),
        )

        domain = build_sequence_anchor_discovery_domain(
            lane,
            layout="horizontal",
            measurement_plan=plan,
            coarse_support=support,
        )
        top, bottom = build_top_bottom_search_corridors(
            lane,
            layout="horizontal",
            measurement_plan=plan,
            coarse_support=support,
        )

        self.assertEqual(domain.support_interval_px, support.long_axis.interval_px)
        self.assertTrue(
            all(100.0 <= trace <= 2200.0 for trace in top.trace_positions_px)
        )
        self.assertEqual(top.trace_positions_px, bottom.trace_positions_px)

    def test_role_free_material_region_localizes_the_whole_strip(self) -> None:
        lane, plan = _lane()
        pixels = np.full((322, 2320), 255, dtype=np.uint8)
        pixels[35:290, 260:2060] = 80
        field = make_photo_boundary_measurement_field(pixels, "horizontal")

        support, measurements = observe_coarse_strip_support(
            field,
            lane,
            layout="horizontal",
            measurement_plan=plan,
        )

        self.assertEqual(
            support.long_axis.authority,
            CoarseSupportAuthority.PIXEL_OBSERVED,
        )
        assert support.long_axis.direct_interval_px is not None
        self.assertLessEqual(
            support.long_axis.direct_interval_px.minimum,
            270.0,
        )
        self.assertGreaterEqual(
            support.long_axis.direct_interval_px.maximum,
            2050.0,
        )
        self.assertTrue(all(not item.transitions for item in measurements))
        self.assertEqual(support.receipt.aggregate_profile_count, 2)
        self.assertLess(
            support.receipt.pixel_query_count,
            pixels.size,
        )

    def test_coarse_short_axis_compiles_one_direct_enclosing_track(self) -> None:
        pixels = np.full((322, 2320), 255, dtype=np.uint8)
        pixels[35:290, 260:2060] = 80

        support = self._observed_support(pixels)

        self.assertIsNotNone(support.shared_direction)
        self.assertIsNotNone(support.enclosing_support)
        assert support.enclosing_support is not None
        self.assertEqual(
            support.enclosing_support.minimum_track.trace_coordinates_px,
            (573, 1162, 1751),
        )
        self.assertEqual(
            support.enclosing_support.minimum_track.trace_coordinates_px,
            support.enclosing_support.maximum_track.trace_coordinates_px,
        )

    def test_isolated_trace_outlier_cannot_move_the_source_wide_track(self) -> None:
        pixels = np.full((322, 2320), 255, dtype=np.uint8)
        pixels[35:290, 260:2060] = 80
        outlier = pixels.copy()
        outlier[5:290, 0:40] = 80

        original = self._observed_support(pixels)
        changed = self._observed_support(outlier)

        assert original.enclosing_support is not None
        assert changed.enclosing_support is not None
        self.assertEqual(
            changed.enclosing_support.minimum_track.canonical_position_px,
            original.enclosing_support.minimum_track.canonical_position_px,
        )
        self.assertEqual(
            changed.enclosing_support.minimum_track.trace_coordinates_px,
            original.enclosing_support.minimum_track.trace_coordinates_px,
        )

    def test_final_fixed_height_can_drop_support_without_losing_direction(self) -> None:
        pixels = np.full((322, 2320), 255, dtype=np.uint8)
        pixels[35:290, 260:2060] = 80
        support = self._observed_support(pixels)
        assert support.enclosing_support is not None
        assert support.shared_direction is not None

        self.assertIsNone(
            _enclosing_support_for_canonical_height(
                support.enclosing_support,
                250.0,
            )
        )
        converted = _shared_direction_from_coarse(support.shared_direction)
        assert converted is not None
        self.assertEqual(
            converted.direction_id,
            support.shared_direction.direction_id,
        )

    def test_brightness_and_contrast_do_not_move_coarse_support(self) -> None:
        pixels = np.full((322, 2320), 235, dtype=np.uint8)
        pixels[35:290, 260:2060] = 75
        transformed = np.rint(pixels.astype(np.float32) * 0.65 + 25.0).astype(
            np.uint8
        )

        original = self._observed_support(pixels)
        adjusted = self._observed_support(transformed)

        self.assertEqual(
            original.long_axis.direct_interval_px,
            adjusted.long_axis.direct_interval_px,
        )
        self.assertEqual(
            original.short_axis.direct_interval_px,
            adjusted.short_axis.direct_interval_px,
        )

    def test_flip_and_axis_transpose_preserve_the_same_physical_support(self) -> None:
        pixels = np.full((322, 2320), 255, dtype=np.uint8)
        pixels[35:290, 260:2060] = 80
        original = self._observed_support(pixels)
        flipped = self._observed_support(np.fliplr(pixels))
        vertical = self._observed_support(pixels.T, layout="vertical")
        assert original.long_axis.direct_interval_px is not None
        assert flipped.long_axis.direct_interval_px is not None

        expected_flip = FiniteInterval(
            2319.0 - original.long_axis.direct_interval_px.maximum,
            2319.0 - original.long_axis.direct_interval_px.minimum,
        )
        self.assertLessEqual(
            abs(
                flipped.long_axis.direct_interval_px.minimum
                - expected_flip.minimum
            ),
            1.0,
        )
        self.assertLessEqual(
            abs(
                flipped.long_axis.direct_interval_px.maximum
                - expected_flip.maximum
            ),
            1.0,
        )
        self.assertEqual(
            vertical.long_axis.direct_interval_px,
            original.long_axis.direct_interval_px,
        )
        self.assertEqual(
            vertical.short_axis.direct_interval_px,
            original.short_axis.direct_interval_px,
        )

    def test_uniform_border_translates_support_without_changing_its_span(self) -> None:
        pixels = np.full((322, 2320), 255, dtype=np.uint8)
        pixels[35:290, 260:2060] = 80
        bordered = np.full((322, 2420), 255, dtype=np.uint8)
        bordered[:, 100:] = pixels

        original = self._observed_support(pixels)
        shifted = self._observed_support(bordered)
        assert original.long_axis.direct_interval_px is not None
        assert shifted.long_axis.direct_interval_px is not None

        self.assertEqual(
            shifted.long_axis.direct_interval_px.width,
            original.long_axis.direct_interval_px.width,
        )
        self.assertEqual(
            shifted.long_axis.direct_interval_px.minimum,
            original.long_axis.direct_interval_px.minimum + 100.0,
        )

    def test_support_module_cannot_assign_template_roles_or_geometry(self) -> None:
        path = (
            Path(__file__).parents[2]
            / "x5crop/detection/photo_geometry/coarse_strip_support.py"
        )
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = tuple(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        )
        self.assertFalse(
            any(
                token in name
                for name in imported
                for token in ("template_phase", "template_cross", "template_placement")
            )
        )
        self.assertFalse(hasattr(CoarseStripSupport, "role"))


if __name__ == "__main__":
    unittest.main()
