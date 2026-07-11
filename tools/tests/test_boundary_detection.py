from __future__ import annotations

import unittest

import numpy as np

from x5crop.detection.guidance.content_crop_envelope import (
    expand_crop_envelopes_for_content,
)
from x5crop.detection.physical.boundary_detection import boundary_observation_groups
from x5crop.detection.physical.sequence import base_sequence_span_candidates
from x5crop.domain import (
    Box,
    CropEnvelope,
    MeasurementProvenance,
    SequenceHypothesis,
    VisibleSequenceSpan,
)
from x5crop.geometry.detection_parameters import BoundaryDetectionParameters
from x5crop.policies.parameters.sequence import SequenceContentAlignmentParameters


def _parameters() -> BoundaryDetectionParameters:
    return BoundaryDetectionParameters(
        white_run_ratio=0.01,
        white_run_min=2,
        white_run_max=8,
        white_margin_ratio=0.0,
        white_margin_min=0,
    )


class BoundaryDetectionTests(unittest.TestCase):
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

    def test_sequence_hypothesis_carries_four_side_boundary_provenance(self) -> None:
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

    def test_no_white_holder_observation_is_invented_without_edge_white(self) -> None:
        gray = np.full((120, 240), 80, dtype=np.uint8)
        groups = dict(boundary_observation_groups(gray, _parameters()))
        self.assertEqual(groups["white_holder"], ())

    def test_uniform_canvas_has_no_invented_pixel_transition(self) -> None:
        for value in (0, 255):
            with self.subTest(value=value):
                gray = np.full((120, 240), value, dtype=np.uint8)
                groups = dict(boundary_observation_groups(gray, _parameters()))
                self.assertEqual(groups["tonal"], ())
                self.assertEqual(groups["texture"], ())
                proposals = base_sequence_span_candidates(gray, _parameters())
                self.assertEqual([item.name for item in proposals], ["full_canvas"])

    def test_content_expands_crop_envelope_without_changing_sequence_geometry(self) -> None:
        gray = np.full((100, 200), 255, dtype=np.uint8)
        gray[10:90, 10:190] = 80
        physical_box = Box(20, 20, 180, 80)
        physical = SequenceHypothesis(
            name="physical_sequence",
            visible_sequence_span=VisibleSequenceSpan(physical_box),
            crop_envelope=CropEnvelope(physical_box),
            strategy="boundary_led",
            provenance=MeasurementProvenance(
                "holder_boundary_profile",
                "synthetic",
                ("gray_work",),
            ),
            boundary_observations=(),
        )
        expanded = expand_crop_envelopes_for_content(
            gray,
            [physical],
            SequenceContentAlignmentParameters(
                content_bbox_thresholds=(200,),
                content_bbox_min_row_fraction=0.01,
                content_bbox_min_col_fraction=0.01,
            ),
        )[0]
        self.assertEqual(expanded.visible_sequence_span, physical.visible_sequence_span)
        self.assertEqual(expanded.crop_envelope.box, Box(10, 10, 190, 90))
        self.assertEqual(expanded.provenance, physical.provenance)


if __name__ == "__main__":
    unittest.main()
