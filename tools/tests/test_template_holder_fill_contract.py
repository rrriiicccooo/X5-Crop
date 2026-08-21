from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import unittest

from x5crop.domain import Box, FiniteInterval
from x5crop.detection.photo_geometry.model import BoundaryAxis
from x5crop.detection.photo_geometry.template_holder_fill import (
    HolderFillSideRelation,
    HolderFillState,
    LaneLongAxisAuthority,
    assess_holder_fill_state,
    photo_group_outer_from_selected_placement,
)
from tools.tests.template_test_support import (
    placement_compose as _compose,
    placement_cross as _cross,
    placement_direction as _direction,
    placement_sequence as _sequence,
    placement_template as _template,
)


def _placement():
    template = _template(1)
    direction = _direction()
    return _compose(
        template,
        _sequence(template),
        _cross(template, direction=direction),
        lane_id="lane:fill",
    )


def _assessment(
    *,
    lane: FiniteInterval,
    lower: FiniteInterval,
    upper: FiniteInterval,
    width: FiniteInterval,
):
    placement = _placement()
    outer = replace(
        photo_group_outer_from_selected_placement(placement),
        lower_px=lower,
        upper_px=upper,
        frame_width_px=width,
    )
    authority = LaneLongAxisAuthority(
        placement.lane_id,
        placement.width_axis,
        lane,
    )
    return assess_holder_fill_state(outer, authority)


class TemplateHolderFillContractTest(unittest.TestCase):
    def test_photo_group_outer_is_derived_from_selected_placement(self) -> None:
        placement = _placement()
        outer = photo_group_outer_from_selected_placement(placement)
        self.assertEqual(outer.placement_id, placement.placement_id)
        self.assertEqual(
            outer.lower_px,
            placement.frames[0].start.full_position_interval_px,
        )
        self.assertEqual(
            outer.upper_px,
            placement.frames[-1].end.full_position_interval_px,
        )
        self.assertEqual(
            outer.frame_width_px,
            placement.source_scan_geometry.width_state.extent_projection_px(),
        )

    def test_either_side_that_fits_w_is_not_filled(self) -> None:
        assessment = _assessment(
            lane=FiniteInterval(0.0, 300.0),
            lower=FiniteInterval.exact(100.0),
            upper=FiniteInterval.exact(250.0),
            width=FiniteInterval.exact(100.0),
        )
        self.assertEqual(assessment.state, HolderFillState.NOT_FILLED)
        self.assertEqual(assessment.lower.relation, HolderFillSideRelation.FITS)
        self.assertEqual(
            assessment.upper.relation,
            HolderFillSideRelation.DOES_NOT_FIT,
        )

    def test_neither_side_that_fits_w_is_filled(self) -> None:
        assessment = _assessment(
            lane=FiniteInterval(0.0, 300.0),
            lower=FiniteInterval.exact(120.0),
            upper=FiniteInterval.exact(180.0),
            width=FiniteInterval.exact(150.0),
        )
        self.assertEqual(assessment.state, HolderFillState.FILLED)

    def test_threshold_interval_is_unresolved(self) -> None:
        assessment = _assessment(
            lane=FiniteInterval(0.0, 300.0),
            lower=FiniteInterval(95.0, 105.0),
            upper=FiniteInterval(195.0, 205.0),
            width=FiniteInterval.exact(100.0),
        )
        self.assertEqual(assessment.state, HolderFillState.UNRESOLVED)

    def test_box_projection_is_explicit_for_both_axes(self) -> None:
        horizontal = LaneLongAxisAuthority.from_box(
            "lane:x", BoundaryAxis.X, Box(10, 20, 310, 120)
        )
        vertical = LaneLongAxisAuthority.from_box(
            "lane:y", BoundaryAxis.Y, Box(10, 20, 310, 120)
        )
        self.assertEqual(horizontal.interval_px, FiniteInterval(10.0, 310.0))
        self.assertEqual(vertical.interval_px, FiniteInterval(20.0, 120.0))

    def test_authorities_must_match_selected_lane_and_axis(self) -> None:
        placement = _placement()
        outer = photo_group_outer_from_selected_placement(placement)
        with self.assertRaises(ValueError):
            assess_holder_fill_state(
                outer,
                LaneLongAxisAuthority(
                    "lane:other",
                    placement.width_axis,
                    FiniteInterval(0.0, 1000.0),
                ),
            )

    def test_module_cannot_import_search_or_selection(self) -> None:
        source = (
            Path(__file__).parents[2]
            / "x5crop/detection/photo_geometry/template_holder_fill.py"
        ).read_text(encoding="utf-8")
        modules = tuple(
            node.module or ""
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom)
        )
        self.assertFalse(
            any(
                token in module
                for token in ("template_phase", "template_cross", "template_selection")
                for module in modules
            )
        )


if __name__ == "__main__":
    unittest.main()
