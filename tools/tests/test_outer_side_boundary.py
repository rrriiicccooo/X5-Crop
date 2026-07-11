from __future__ import annotations

import unittest

import numpy as np

from x5crop.detection.physical.outer.base import base_outer_candidates
from x5crop.detection.physical.outer.side_boundary import (
    side_boundary_outer_proposals,
)
from x5crop.geometry.detection_parameters import OuterBoxDetectionParameters


def _parameters() -> OuterBoxDetectionParameters:
    return OuterBoxDetectionParameters(
        white_border_ratio=0.95,
        white_run_ratio=0.01,
        white_run_min=2,
        white_run_max=8,
        white_margin_ratio=0.0,
        white_margin_min=0,
    )


class OuterSideBoundaryTests(unittest.TestCase):
    def test_white_tonal_texture_and_mixed_models_are_proposed(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120
        gray[20:24, 40:200] = 0
        results = side_boundary_outer_proposals(gray, _parameters())
        self.assertEqual(
            tuple(result.reason for result in results),
            (
                "white_holder_boundary",
                "tonal_boundary",
                "texture_boundary",
                "mixed_safe_overcontain",
            ),
        )
        self.assertTrue(any(result.box is not None for result in results))

    def test_each_side_has_an_explicit_boundary_model(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120
        result = side_boundary_outer_proposals(gray, _parameters())[0]
        self.assertEqual(
            {side.side for side in result.sides},
            {"left", "right", "top", "bottom"},
        )
        self.assertTrue(all(side.boundary_model for side in result.sides))

    def test_base_proposal_carries_two_side_boundary_provenance(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120
        proposals = base_outer_candidates(gray, _parameters())
        measured = [
            proposal
            for proposal in proposals
            if proposal.provenance.boundary_anchors
        ]
        self.assertTrue(measured)
        self.assertTrue(
            all(
                set(proposal.provenance.boundary_anchors)
                == {"left", "right", "top", "bottom"}
                for proposal in measured
            )
        )

    def test_full_canvas_is_preserved_as_safe_overcontain_proposal(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        proposals = base_outer_candidates(gray, _parameters())
        full_canvas = next(item for item in proposals if item.name == "full_canvas")
        self.assertEqual(
            (full_canvas.box.left, full_canvas.box.top, full_canvas.box.right, full_canvas.box.bottom),
            (0, 0, 240, 120),
        )


if __name__ == "__main__":
    unittest.main()
