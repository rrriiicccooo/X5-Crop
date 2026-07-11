from __future__ import annotations

import unittest

import numpy as np

from x5crop.detection.physical.outer.base import base_sequence_span_candidates
from x5crop.detection.physical.outer.side_boundary import (
    boundary_observation_groups,
)
from x5crop.geometry.detection_parameters import OuterBoxDetectionParameters


def _parameters() -> OuterBoxDetectionParameters:
    return OuterBoxDetectionParameters(
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
        results = boundary_observation_groups(gray, _parameters())
        self.assertEqual(
            tuple(name for name, _observations in results),
            (
                "white_holder",
                "tonal",
                "texture",
                "full_canvas",
            ),
        )
        self.assertTrue(all(len(observations) == 4 for _name, observations in results))

    def test_each_side_has_an_explicit_boundary_model(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120
        _name, observations = boundary_observation_groups(gray, _parameters())[0]
        self.assertEqual(
            {observation.side for observation in observations},
            {"leading", "trailing", "top", "bottom"},
        )
        self.assertTrue(all(observation.kind for observation in observations))

    def test_base_proposal_carries_two_side_boundary_provenance(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120
        proposals = base_sequence_span_candidates(gray, _parameters())
        measured = [
            proposal
            for proposal in proposals
            if proposal.provenance.boundary_anchors
        ]
        self.assertTrue(measured)
        self.assertTrue(
            all(
                set(proposal.provenance.boundary_anchors)
                == {"leading", "trailing", "top", "bottom"}
                for proposal in measured
            )
        )

    def test_full_canvas_is_preserved_as_safe_overcontain_proposal(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        proposals = base_sequence_span_candidates(gray, _parameters())
        full_canvas = next(item for item in proposals if item.name == "full_canvas")
        self.assertEqual(
            (
                full_canvas.crop_envelope.box.left,
                full_canvas.crop_envelope.box.top,
                full_canvas.crop_envelope.box.right,
                full_canvas.crop_envelope.box.bottom,
            ),
            (0, 0, 240, 120),
        )


if __name__ == "__main__":
    unittest.main()
