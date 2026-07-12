from __future__ import annotations

from dataclasses import replace
import unittest

import numpy as np

from tools.tests.physical_gate_support import (
    candidate_evidence_fixture,
    candidate_fixture,
)
from x5crop.cache import MeasurementCache
from x5crop.detection.candidate.model import content_preservation_state
from x5crop.detection.evidence.content.frame_support import frame_content_evidence
from x5crop.detection.evidence.content.frame_support import _sample_supports_content
from x5crop.detection.evidence.sequence_content_alignment import sequence_content_alignment_evidence
from x5crop.domain import (
    Box,
    CropEnvelope,
    EvidenceState,
    HolderSpan,
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
    VisibleSequenceSpan,
)
from x5crop.detection.physical.model import PhotoInterval
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


def _single_frame_geometry(box: Box):
    geometry = candidate_fixture().geometry
    provenance = MeasurementProvenance(
        MeasurementIdentity.PHOTO_EDGES,
        "content_alignment_fixture",
        (MeasurementIdentity.GRAY_WORK,),
    )
    return replace(
        geometry,
        count=1,
        holder_span=HolderSpan(box),
        visible_sequence_span=VisibleSequenceSpan(box),
        crop_envelope=CropEnvelope(box),
        photo_intervals=(
            PhotoInterval(
                1,
                PixelInterval.exact(float(box.left)),
                PixelInterval.exact(float(box.right)),
                provenance,
                provenance,
                True,
                True,
            ),
        ),
        frames=(box,),
        separator_observations=(),
        separator_assignments=(),
        frame_boundaries=(),
        inter_frame_spacings=(),
    )


class FrameContentSupportTest(unittest.TestCase):
    def test_undersized_sample_cannot_satisfy_minimum_content_support(self) -> None:
        sample = np.ones((1, 1), dtype=np.float32)
        self.assertFalse(
            _sample_supports_content(
                sample,
                threshold=0.5,
                minimum_active_pixels=16,
            )
        )

    def test_content_span_conflict_prevents_supported_preservation(self) -> None:
        evidence = candidate_evidence_fixture()
        alignment = replace(
            evidence.sequence_content_alignment,
            content_span=Box(10, -10, 190, 90),
        )
        state = content_preservation_state(
            evidence.frame_coverage,
            alignment,
            evidence.partial_edge_safety,
        )
        self.assertEqual(state, EvidenceState.UNAVAILABLE)

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
        gray = np.full((120, 900), 255, dtype=np.uint8)
        gray[20:100, 220:680] = 0
        geometry = _single_frame_geometry(Box(0, 0, 900, 120))
        alignment = sequence_content_alignment_evidence(
            geometry,
            _cache(gray),
            get_detection_configuration("120-645", "full").content.evidence,
        )
        self.assertNotEqual(alignment.state, EvidenceState.CONTRADICTED)
        self.assertTrue(alignment.overcontains_long_axis)

    def test_global_content_span_alone_does_not_confirm_undercrop(self) -> None:
        gray = np.full((120, 900), 255, dtype=np.uint8)
        gray[20:100, 50:850] = 0
        geometry = _single_frame_geometry(Box(250, 0, 650, 120))
        alignment = sequence_content_alignment_evidence(
            geometry,
            _cache(gray),
            get_detection_configuration("120-645", "full").content.evidence,
        )
        self.assertEqual(alignment.state, EvidenceState.UNAVAILABLE)
        self.assertTrue(alignment.content_outside_sides)


if __name__ == "__main__":
    unittest.main()
