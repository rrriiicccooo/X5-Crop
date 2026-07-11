from __future__ import annotations

from dataclasses import replace
import unittest

import numpy as np

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.cache import MeasurementCache
from x5crop.detection.evidence.content.frame_support import frame_content_evidence
from x5crop.detection.evidence.outer_alignment import outer_content_alignment_evidence
from x5crop.detection.evidence.state import EvidenceState
from x5crop.detection.physical.spans import FilmSpan
from x5crop.domain import Box
from x5crop.policies.registry import get_detection_policy


def _cache(gray: np.ndarray) -> MeasurementCache:
    evidence = (gray < 225).astype(np.uint8) * 255
    return MeasurementCache(
        "horizontal",
        gray,
        evidence,
        evidence.astype(np.float32) / 255.0,
    )


class FrameContentSupportTest(unittest.TestCase):
    def test_empty_frame_does_not_claim_content_damage(self) -> None:
        candidate = candidate_fixture()
        gray = np.full((100, 200), 255, dtype=np.uint8)
        gray[10:90, 110:190] = 0
        evidence = frame_content_evidence(
            candidate.geometry,
            _cache(gray),
            get_detection_policy("135", "full").content,
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
            get_detection_policy("135", "full").content,
        )
        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)

    def test_outer_overcontainment_is_allowed(self) -> None:
        candidate = candidate_fixture()
        gray = np.full((120, 900), 255, dtype=np.uint8)
        gray[20:100, 220:680] = 0
        geometry = replace(
            candidate.geometry,
            film_span=FilmSpan(Box(0, 0, 900, 120)),
        )
        alignment = outer_content_alignment_evidence(
            geometry,
            _cache(gray),
            get_detection_policy("120-645", "full").outer.alignment_evidence,
        )
        self.assertNotEqual(alignment.state, EvidenceState.CONTRADICTED)
        self.assertTrue(alignment.overcontains_long_axis)

    def test_confirmed_outer_undercrop_is_integrity_failure(self) -> None:
        candidate = candidate_fixture()
        gray = np.full((120, 900), 255, dtype=np.uint8)
        gray[20:100, 50:850] = 0
        geometry = replace(
            candidate.geometry,
            film_span=FilmSpan(Box(250, 0, 650, 120)),
        )
        alignment = outer_content_alignment_evidence(
            geometry,
            _cache(gray),
            get_detection_policy("120-645", "full").outer.alignment_evidence,
        )
        self.assertEqual(alignment.state, EvidenceState.CONTRADICTED)
        self.assertTrue(alignment.confirmed_undercrop)


if __name__ == "__main__":
    unittest.main()
