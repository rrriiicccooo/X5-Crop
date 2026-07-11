from __future__ import annotations

import unittest

from x5crop.detection.evidence.state import EvidenceState
from x5crop.detection.physical.boundary import (
    BoundaryObservation,
    HolderOcclusionEvidence,
    holder_occlusion_evidence,
)
from x5crop.detection.physical.intervals import PixelInterval
from x5crop.detection.physical.spacing import (
    derive_inter_frame_spacing,
    inter_frame_spacing_evidence,
    sequence_conservation_evidence,
)
from x5crop.domain import MeasurementProvenance


class FrameSequenceGeometryContractTests(unittest.TestCase):
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
