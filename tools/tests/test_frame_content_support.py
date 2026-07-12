from __future__ import annotations

from dataclasses import replace
import unittest

import numpy as np

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.cache import MeasurementCache
from x5crop.detection.evidence.content.frame_support import frame_content_evidence
from x5crop.detection.evidence.sequence_content_alignment import sequence_content_alignment_evidence
from x5crop.domain import EvidenceState
from x5crop.domain import VisibleSequenceSpan
from x5crop.domain import Box
from x5crop.configuration.registry import get_detection_configuration
from x5crop.image.statistics import ImageMeasurementStatisticsParameters, image_measurement_statistics


def _cache(gray: np.ndarray) -> MeasurementCache:
    evidence = (gray < 225).astype(np.uint8) * 255
    return MeasurementCache(
        "horizontal",
        gray,
        evidence,
        evidence.astype(np.float32) / 255.0,
        image_measurement_statistics(gray, ImageMeasurementStatisticsParameters()),
    )


class FrameContentSupportTest(unittest.TestCase):
    def test_empty_frame_does_not_claim_content_damage(self) -> None:
        candidate = candidate_fixture()
        gray = np.full((100, 200), 255, dtype=np.uint8)
        gray[10:90, 110:190] = 0
        evidence = frame_content_evidence(
            candidate.geometry,
            _cache(gray),
            get_detection_configuration("135", "full").content,
        )
        self.assertNotEqual(evidence.state, EvidenceState.CONTRADICTED)
        self.assertFalse(evidence.observations[0].content_present)
        self.assertTrue(evidence.observations[1].content_present)

    def test_low_content_is_unavailable_not_contradicted(self) -> None:
        candidate = candidate_fixture()
        gray = np.full((100, 200), 255, dtype=np.uint8)
        evidence = frame_content_evidence(
            candidate.geometry,
            _cache(gray),
            get_detection_configuration("135", "full").content,
        )
        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)

    def test_sequence_overcontainment_is_allowed(self) -> None:
        candidate = candidate_fixture()
        gray = np.full((120, 900), 255, dtype=np.uint8)
        gray[20:100, 220:680] = 0
        geometry = replace(
            candidate.geometry,
            visible_sequence_span=VisibleSequenceSpan(Box(0, 0, 900, 120)),
        )
        alignment = sequence_content_alignment_evidence(
            geometry,
            _cache(gray),
            get_detection_configuration("120-645", "full").content.evidence,
        )
        self.assertNotEqual(alignment.state, EvidenceState.CONTRADICTED)
        self.assertTrue(alignment.overcontains_long_axis)

    def test_global_content_span_alone_does_not_confirm_undercrop(self) -> None:
        candidate = candidate_fixture()
        gray = np.full((120, 900), 255, dtype=np.uint8)
        gray[20:100, 50:850] = 0
        geometry = replace(
            candidate.geometry,
            visible_sequence_span=VisibleSequenceSpan(Box(250, 0, 650, 120)),
        )
        alignment = sequence_content_alignment_evidence(
            geometry,
            _cache(gray),
            get_detection_configuration("120-645", "full").content.evidence,
        )
        self.assertEqual(alignment.state, EvidenceState.UNAVAILABLE)
        self.assertFalse(alignment.confirmed_undercrop_sides)
        self.assertTrue(alignment.unconfirmed_undercrop_sides)


if __name__ == "__main__":
    unittest.main()
