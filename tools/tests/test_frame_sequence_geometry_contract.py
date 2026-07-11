from __future__ import annotations

import unittest
from dataclasses import fields
from pathlib import Path

from x5crop.detection.evidence.state import EvidenceState
from x5crop.detection.physical.boundary import (
    BoundaryObservation,
    HolderOcclusionEvidence,
    visible_sequence_and_crop_envelope,
    holder_occlusion_evidence,
)
from x5crop.detection.physical.intervals import PixelInterval
from x5crop.detection.physical.spacing import (
    derive_inter_frame_spacing,
    inter_frame_spacing_evidence,
    sequence_conservation_evidence,
)
from x5crop.domain import MeasurementProvenance
from x5crop.domain import Box
from x5crop.detection.geometry import CandidateGeometry
from x5crop.detection.physical.spans import CropEnvelope, VisibleSequenceSpan


ROOT = Path(__file__).resolve().parents[2]


class FrameSequenceGeometryContractTests(unittest.TestCase):
    def test_boundary_uncertainty_separates_visible_span_and_crop_envelope(self) -> None:
        provenance = MeasurementProvenance(
            "holder_boundary_profile",
            "synthetic",
            ("gray_work",),
        )
        observations = (
            BoundaryObservation("leading", PixelInterval(9.0, 11.0), "white_holder_transition", provenance),
            BoundaryObservation("trailing", PixelInterval(189.0, 191.0), "white_holder_transition", provenance),
            BoundaryObservation("top", PixelInterval(4.0, 6.0), "tonal_transition", provenance),
            BoundaryObservation("bottom", PixelInterval(94.0, 96.0), "tonal_transition", provenance),
        )
        visible, envelope = visible_sequence_and_crop_envelope(
            observations,
            canvas_width=200,
            canvas_height=100,
        )
        self.assertEqual(visible, VisibleSequenceSpan(Box(10, 5, 190, 95)))
        self.assertEqual(envelope, CropEnvelope(Box(9, 4, 191, 96)))

    def test_candidate_geometry_has_distinct_sequence_and_crop_fields(self) -> None:
        names = {field.name for field in fields(CandidateGeometry)}
        self.assertIn("visible_sequence_span", names)
        self.assertIn("crop_envelope", names)
        self.assertNotIn("film" + "_span", names)
        self.assertNotIn("image_crop_envelope", names)

    def test_active_source_has_no_generic_outer_or_film_span_identity(self) -> None:
        active = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "x5crop").rglob("*.py")
        )
        self.assertNotIn("Film" + "Span", active)
        self.assertNotIn("Outer" + "Proposal", active)

    def test_irregular_positive_spacing_satisfies_sequence_conservation(self) -> None:
        evidence = sequence_conservation_evidence(
            visible_length_px=PixelInterval.exact(315.0),
            count=3,
            frame_width_px=PixelInterval.exact(100.0),
            spacings=(
                inter_frame_spacing_evidence(1, PixelInterval.exact(5.0)),
                inter_frame_spacing_evidence(2, PixelInterval.exact(10.0)),
            ),
            holder_occlusion=HolderOcclusionEvidence.not_applicable(),
        )
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_overlap_can_balance_positive_separator_width(self) -> None:
        evidence = sequence_conservation_evidence(
            visible_length_px=PixelInterval.exact(302.0),
            count=3,
            frame_width_px=PixelInterval.exact(100.0),
            spacings=(
                inter_frame_spacing_evidence(1, PixelInterval.exact(5.0)),
                inter_frame_spacing_evidence(2, PixelInterval.exact(-3.0)),
            ),
            holder_occlusion=HolderOcclusionEvidence.not_applicable(),
        )
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_leading_holder_occlusion_explains_short_visible_edge_frame(self) -> None:
        boundary = BoundaryObservation(
            side="leading",
            position=PixelInterval.exact(20.0),
            kind="white_holder_transition",
            provenance=MeasurementProvenance(
                "holder_boundary_profile",
                "white_holder_transition",
                ("gray_work",),
                ("leading",),
            ),
        )
        evidence = holder_occlusion_evidence(
            leading_boundary=boundary,
            trailing_boundary=None,
            leading_visible_frame_width=PixelInterval.exact(94.0),
            trailing_visible_frame_width=None,
            frame_width_px=PixelInterval.exact(100.0),
        )
        self.assertEqual(evidence.leading.state, EvidenceState.SUPPORTED)
        self.assertEqual(evidence.leading.hidden_width_px, PixelInterval.exact(6.0))

    def test_internal_spacing_uses_two_physical_frame_widths(self) -> None:
        evidence = derive_inter_frame_spacing(
            index=2,
            anchor_span_px=PixelInterval.exact(212.0),
            frame_width_px=PixelInterval.exact(100.0),
            edge_occlusion_px=PixelInterval.zero(),
        )
        self.assertEqual(evidence.kind, "separator")
        self.assertEqual(evidence.signed_width_px, PixelInterval.exact(12.0))


if __name__ == "__main__":
    unittest.main()
