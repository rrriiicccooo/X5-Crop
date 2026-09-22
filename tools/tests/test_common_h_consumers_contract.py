from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.test_common_output_contract import translated_h
from tools.tests.test_content_veto_contract import make_observation
from tools.tests.test_template_output_contract import _lane, _placement
from x5crop.domain import Box, FiniteInterval
from x5crop.detection.photo_geometry.content_topology import (
    build_content_topology_index,
)
from x5crop.detection.photo_geometry.content_veto import content_veto_assessment
from x5crop.detection.photo_geometry.content_veto_model import ContentVetoReason
from x5crop.detection.photo_geometry.template_common_output import (
    materialize_common_h_output,
)
from x5crop.detection.photo_geometry.template_holder_fill import (
    photo_group_outer_from_selected_placement,
)
from tools.regression.gold_analysis import _selected_native_placement


class CommonHConsumersContractTest(unittest.TestCase):
    @staticmethod
    def _common_output():
        first = _placement()
        second = translated_h(first, 5)
        common = materialize_common_h_output(
            (first, second),
            ((0, 1), (1, 0)),
            lane=_lane(),
            layout="horizontal",
        )
        if common.failure is not None:
            raise AssertionError("common fixture unexpectedly failed")
        return first, second, common

    def test_content_veto_uses_common_id_and_required_polygons(self) -> None:
        _first, _second, common = self._common_output()
        assessment = content_veto_assessment(
            common,
            tuple(output.required_source_footprint for output in common.output_footprints),
            build_content_topology_index(
                make_observation(Box(120, 5, 130, 10)),
                layout="horizontal",
            ),
        )

        self.assertEqual(assessment.placement_id, common.placement_id)
        with self.assertRaisesRegex(ValueError, "actual common output"):
            content_veto_assessment(
                common,
                (((0.0, 0.0), (500.0, 0.0), (500.0, 400.0), (0.0, 400.0)),),
                build_content_topology_index(make_observation(Box(120, 5, 130, 10)), layout="horizontal"),
            )
        self.assertEqual(
            {item.reason for item in assessment.facts},
            {ContentVetoReason.SLOT_CONTENT_CROPPED_IN},
        )

    def test_holder_outer_conservatively_covers_every_common_member(self) -> None:
        first, second, common = self._common_output()
        frame = second.frames[0]
        second = replace(
            second,
            frames=(
                replace(
                    frame,
                    start=replace(
                        frame.start,
                        canonical_position_px=122.5,
                        full_position_interval_px=FiniteInterval(120.0, 125.0),
                    ),
                    end=replace(
                        frame.end,
                        canonical_position_px=222.5,
                        full_position_interval_px=FiniteInterval(220.0, 225.0),
                    ),
                ),
            ),
        )
        common = replace(common, placements=(first, second))
        first_outer = photo_group_outer_from_selected_placement(first)
        second_outer = photo_group_outer_from_selected_placement(second)
        outer = photo_group_outer_from_selected_placement(common)

        self.assertEqual(outer.placement_id, common.placement_id)
        self.assertNotEqual(outer.placement_id, first.placement_id)
        self.assertEqual(
            outer.lower_px,
            FiniteInterval(
                min(first_outer.lower_px.minimum, second_outer.lower_px.minimum),
                max(first_outer.lower_px.maximum, second_outer.lower_px.maximum),
            ),
        )
        self.assertEqual(
            outer.upper_px,
            FiniteInterval(
                min(first_outer.upper_px.minimum, second_outer.upper_px.minimum),
                max(first_outer.upper_px.maximum, second_outer.upper_px.maximum),
            ),
        )
        for member in (first_outer, second_outer):
            self.assertLessEqual(outer.lower_px.minimum, member.lower_px.minimum)
            self.assertGreaterEqual(outer.lower_px.maximum, member.lower_px.maximum)
            self.assertLessEqual(outer.upper_px.minimum, member.upper_px.minimum)
            self.assertGreaterEqual(outer.upper_px.maximum, member.upper_px.maximum)

    def test_gold_native_line_resolution_with_common_id_is_not_primary(self) -> None:
        common = {
            "placement_id": "common-h-output:1",
            "failure": None,
            "output_footprints": [{"geometry_id": "common-geometry:1"}],
        }
        lane = {
            "placement_competition": {
                "selected_placement_id": common["placement_id"],
                "placements": [{"placement_id": "primary"}],
            },
            "common_h_output": common,
        }
        self.assertIsNone(_selected_native_placement(lane))

        lane["placement_competition"]["selected_placement_id"] = "primary"
        self.assertEqual(
            _selected_native_placement(lane),
            lane["placement_competition"]["placements"][0],
        )

        lane["placement_competition"]["selected_placement_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "not unique"):
            _selected_native_placement(lane)

    def test_gold_common_id_requires_complete_common_output(self) -> None:
        lane = {
            "placement_competition": {
                "selected_placement_id": "common-h-output:1",
                "placements": [{"placement_id": "primary"}],
            },
            "common_h_output": {
                "placement_id": "common-h-output:1",
                "failure": {"gap": "output_footprint_unavailable"},
                "output_footprints": [],
            },
        }
        with self.assertRaisesRegex(ValueError, "incomplete"):
            _selected_native_placement(lane)


if __name__ == "__main__":
    unittest.main()
