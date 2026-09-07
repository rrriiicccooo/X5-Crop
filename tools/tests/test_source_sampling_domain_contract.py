from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
import unittest

import numpy as np

from tools.regression.gold_geometry import _contains_polygon
from tools.regression.report_validation import (
    _validate_finalization,
    validate_output_footprint_authority,
)
from tools.tests.affine_tiff_support import sampling_footprint, make_deskew_observation
from x5crop.detection.final.deskew import assess_output_deskew
from x5crop.domain import Box, WorkspaceExtent
from x5crop.detection.photo_geometry.model import AuthoritySide
from x5crop.detection.photo_geometry.output_model import (
    FootprintSaturationKind,
    footprint_outside_authority_sides,
    footprint_overflow_px,
    sampling_authority_bounds,
    source_boundary_sides,
)
from x5crop.detection.photo_geometry.template_output import _saturation_facts
from x5crop.geometry.affine import AffineCoordinateTransform
from x5crop.geometry.convex import (
    clip_convex_polygon_to_bounds,
    convex_hull,
    mapped_half_open_box,
)
from x5crop.image.transforms import sample_affine_roi
from x5crop.io.orientation import orientation_mapping
from x5crop.report.read_models import typed_read_model


def rectangle(left, top, right, bottom):
    return ((left, top), (right, top), (right, bottom), (left, bottom))


class SourceSamplingDomainContractTest(unittest.TestCase):
    def test_source_cell_intersection_keeps_every_identity_sample(self) -> None:
        extent = WorkspaceExtent(7, 5)
        authority = Box(0, 0, 7, 5)
        requested = rectangle(-2.0, -3.0, 9.0, 8.0)
        bounds = sampling_authority_bounds(authority, extent)
        self.assertEqual(bounds, (-0.5, -0.5, 6.5, 4.5))
        required = clip_convex_polygon_to_bounds(requested, bounds)
        self.assertEqual(required, rectangle(-0.5, -0.5, 6.5, 4.5))
        output = replace(
            sampling_footprint(authority, extent),
            mandatory_source_footprint=requested,
            requested_source_footprint=requested,
            required_source_footprint=required,
            saturation_facts=_saturation_facts(requested, requested, authority, extent),
        )
        validate_output_footprint_authority(
            typed_read_model(output), expected_source_extent=extent
        )
        transform = AffineCoordinateTransform.identity(7, 5)
        box = mapped_half_open_box(required, transform.map_point)
        self.assertEqual(box, authority)
        pixels = np.arange(7 * 5 * 3, dtype=np.uint16).reshape(5, 7, 3)
        sampled = sample_affine_roi(pixels, transform, box, sampling_authority_box=authority)
        np.testing.assert_array_equal(sampled, pixels)
        self.assertTrue(_contains_polygon(required, required))
        self.assertFalse(_contains_polygon(rectangle(0.0, 0.0, 6.0, 4.0), required))

    def test_half_cell_is_available_but_true_overflow_remains_explicit(self) -> None:
        extent = WorkspaceExtent(7, 5)
        authority = Box(0, 0, 7, 5)
        inside = rectangle(-0.25, 1.0, 5.0, 3.0)
        self.assertEqual(footprint_outside_authority_sides(inside, authority, extent), ())
        self.assertEqual(_saturation_facts(inside, inside, authority, extent), ())
        self.assertEqual(
            clip_convex_polygon_to_bounds(inside, sampling_authority_bounds(authority, extent)),
            inside,
        )
        outside = rectangle(-0.75, 1.0, 5.0, 3.0)
        facts = _saturation_facts(outside, inside, authority, extent)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].kind, FootprintSaturationKind.SOURCE_BOUNDARY_OPTIONAL_BLEED)
        self.assertEqual(facts[0].requested_overflow_px, 0.25)
        self.assertEqual(facts[0].mandatory_overflow_px, 0.0)

    def test_internal_lane_side_keeps_its_original_limit(self) -> None:
        extent = WorkspaceExtent(9, 7)
        lane = Box(2, 1, 9, 5)
        self.assertEqual(source_boundary_sides(lane, extent), (AuthoritySide.RIGHT,))
        self.assertEqual(sampling_authority_bounds(lane, extent), (2.0, 1.0, 8.5, 4.0))
        requested = rectangle(1.75, 2.0, 8.25, 3.0)
        self.assertEqual(footprint_outside_authority_sides(requested, lane, extent), (AuthoritySide.LEFT,))
        self.assertEqual(footprint_overflow_px(requested, lane, AuthoritySide.LEFT, extent), 0.25)
        facts = _saturation_facts(requested, requested, lane, extent)
        self.assertEqual(facts[0].kind, FootprintSaturationKind.LANE_BOUNDARY_JOINT_PROTECTION)
        self.assertFalse(facts[0].source_boundary)

    def test_physical_polygon_not_raster_aabb_owns_accuracy(self) -> None:
        required = rectangle(0.0, 0.0, 2.75, 3.0)
        confirmed = rectangle(0.0, 0.0, 3.0, 3.0)
        self.assertFalse(_contains_polygon(required, confirmed))
        box = mapped_half_open_box(required, lambda x, y: (x, y))
        cells = rectangle(box.left - 0.5, box.top - 0.5, box.right - 0.5, box.bottom - 0.5)
        self.assertTrue(_contains_polygon(cells, confirmed))
        self.assertEqual(required[1][0], 2.75)

    def test_slanted_source_intersection_does_not_expand_internal_edge(self) -> None:
        requested = ((-1.0, -1.0), (4.0, 1.0), (4.0, 3.0), (-1.0, 3.0))
        required = clip_convex_polygon_to_bounds(requested, (-0.5, -0.5, 6.5, 4.5))
        self.assertTrue(_contains_polygon(requested, required))
        intersection = max(x for x, y in required if y == -0.5)
        self.assertAlmostEqual(intersection, 0.25)
        self.assertEqual(max(x for x, _ in required), 4.0)
        self.assertFalse(_contains_polygon(required, rectangle(0.0, 0.0, 4.25, 2.0)))

    def test_orientation_maps_whole_source_cells_exactly_once(self) -> None:
        raw = rectangle(-0.5, -0.5, 6.5, 4.5)
        for tag in range(1, 9):
            with self.subTest(tag=tag):
                mapping = orientation_mapping(tag, 7, 5)
                mapped = convex_hull(tuple(mapping.map_raw_point(*point) for point in raw))
                expected = rectangle(-0.5, -0.5, mapping.canonical_width - 0.5, mapping.canonical_height - 0.5)
                self.assertEqual(mapped, expected)

    def test_rotated_cell_envelopes_stay_within_output_raster(self) -> None:
        authority = Box(0, 0, 7, 5)
        polygon = rectangle(-0.5, -0.5, 6.5, 4.5)
        pixels = np.arange(7 * 5 * 3, dtype=np.uint16).reshape(5, 7, 3)
        for angle in (-45.0, -0.2, 0.2, 45.0):
            with self.subTest(angle=angle):
                transform = AffineCoordinateTransform.expanded_rotation(7, 5, angle)
                box = mapped_half_open_box(polygon, transform.map_point)
                self.assertGreaterEqual(min(box.left, box.top), 0)
                self.assertLessEqual(box.right, transform.output_extent.width)
                self.assertLessEqual(box.bottom, transform.output_extent.height)
                whole = sample_affine_roi(
                    pixels, transform,
                    Box(0, 0, transform.output_extent.width, transform.output_extent.height),
                    sampling_authority_box=authority,
                )
                roi = sample_affine_roi(pixels, transform, box, sampling_authority_box=authority)
                np.testing.assert_array_equal(roi, whole[box.top:box.bottom, box.left:box.right])

    def test_cell_cover_rounding_at_half_integer_edges(self) -> None:
        for polygon, expected in (
            (rectangle(-0.5, -0.5, 6.5, 4.5), Box(0, 0, 7, 5)),
            (rectangle(1.0, 1.0, 5.0, 3.0), Box(1, 1, 6, 4)),
            (rectangle(1.75, 1.75, 5.75, 3.75), Box(2, 2, 7, 5)),
            (rectangle(1.5, 1.5, 5.5, 3.5), Box(2, 2, 6, 4)),
        ):
            self.assertEqual(mapped_half_open_box(polygon, lambda x, y: (x, y)), expected)

    def test_report_cannot_self_declare_a_different_source_extent(self) -> None:
        extent = WorkspaceExtent(7, 5)
        output = typed_read_model(sampling_footprint(Box(0, 0, 7, 5), extent))
        for width in (6, 8):
            output["source_extent"]["width"] = width
            with self.subTest(width=width), self.assertRaisesRegex(ValueError, "source extent"):
                validate_output_footprint_authority(output, expected_source_extent=extent)

    def test_final_report_reuses_selected_polygon_and_recomputes_sample_box(self) -> None:
        extent = WorkspaceExtent(7, 5)
        output = typed_read_model(sampling_footprint(Box(0, 0, 7, 5), extent))
        deskew = assess_output_deskew(
            make_deskew_observation(0.0), layout="horizontal", source_width=7, source_height=5
        )
        report = {
            "decision": {"status": "approved_auto"},
            "photo_geometry": {
                "resolved_output_slots": {"lane_output_slot_counts": [1]},
                "output_slot_count": 1,
                "slot_identities": [{"lane_id": "lane:0", "lane_ordinal": 1}],
                "lanes": [{"output_footprints": [output]}],
            },
            "output": {
                "output_files": [], "review_copy": None,
                "tiff_fidelity": {"validation": "not_created"},
                "finalization": {
                    "output_footprints": [deepcopy(output)],
                    "final_boxes": [typed_read_model(Box(0, 0, 7, 5))],
                    "deskew_assessment": typed_read_model(deskew),
                    "frame_export_requested": False,
                    "frame_export_eligible": True,
                    "frame_export_performed": False,
                    "official_tiff_count": 0,
                },
            },
        }
        _validate_finalization(report, extent)
        changed_polygon = deepcopy(report)
        final_output = changed_polygon["output"]["finalization"]["output_footprints"][0]
        # Another self-consistent crop cannot replace the approved selection.
        for field in ("mandatory_source_footprint", "requested_source_footprint", "required_source_footprint"):
            final_output[field] = [list(point) for point in rectangle(0.0, 0.0, 5.0, 4.0)]
        with self.assertRaisesRegex(ValueError, "changed selected"):
            _validate_finalization(changed_polygon, extent)
        changed_box = deepcopy(report)
        changed_box["output"]["finalization"]["final_boxes"][0]["left"] = 1
        with self.assertRaisesRegex(ValueError, "boxes disagree"):
            _validate_finalization(changed_box, extent)


if __name__ == "__main__":
    unittest.main()
