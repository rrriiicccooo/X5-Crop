from __future__ import annotations

import unittest

from tools.tests.frame_slot_solver_support import scope
from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.evidence.holder_occupancy import (
    HolderOccupancyEvidence,
    HolderOccupancyState,
    StripCompletenessEvidence,
    holder_occupancy_evidence,
)
from x5crop.detection.evidence.frame_coverage import FrameCoverageEvidence
from x5crop.detection.physical.frame_dimensions import FrameDimensionEvidence
from x5crop.domain import (
    BoundarySide,
    Box,
    ContainmentFallback,
    EvidenceState,
    HolderSafetyEnvelope,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from x5crop.formats import FORMATS


def _dimensions(state: EvidenceState) -> FrameDimensionEvidence:
    return FrameDimensionEvidence(
        56.0,
        56.0,
        PixelInterval.exact(100.0) if state == EvidenceState.SUPPORTED else None,
        (PixelInterval.exact(100.0), PixelInterval.exact(100.0)),
        (10.0,),
        state,
        1.0,
    )


def _holder_safety(box: Box) -> HolderSafetyEnvelope:
    return scope(
        width=box.right,
        height=box.bottom,
        leading=float(box.left),
        trailing=float(box.right),
        top=float(box.top),
        bottom=float(box.bottom),
        holder_sides=tuple(BoundarySide),
    ).holder_safety


class HolderOccupancyTest(unittest.TestCase):
    def test_underfilled_complete_strip_is_a_trait_not_a_format_branch(self) -> None:
        for format_id, expected in (
            ("120-66", True),
            ("xpan", True),
            ("135", False),
            ("half", False),
            ("120-645", False),
            ("120-67", False),
        ):
            with self.subTest(format_id=format_id):
                self.assertEqual(
                    FORMATS[format_id].strip.complete_strip_can_be_underfilled,
                    expected,
                )

    def test_holder_slack_is_occupancy_detail_not_frame_dimension_evidence(self) -> None:
        completeness = StripCompletenessEvidence(3, 3, 3, 2, 0)
        occupancy = HolderOccupancyEvidence(
            completeness,
            True,
            EvidenceState.SUPPORTED,
            EvidenceState.SUPPORTED,
            True,
            _holder_safety(Box(0, 0, 500, 100)),
            PixelInterval.exact(50.0),
            PixelInterval.exact(400.0),
        )

        self.assertTrue(occupancy.complete_underfilled_strip)
        self.assertEqual(occupancy.occupancy_state, HolderOccupancyState.UNDERFILLED)
        self.assertEqual(occupancy.leading_slack_px, PixelInterval.exact(50.0))
        self.assertEqual(occupancy.trailing_slack_px, PixelInterval.exact(100.0))
        self.assertNotIn("slack", FrameDimensionEvidence.__dataclass_fields__)

    def test_intersecting_boundary_intervals_mean_filled(self) -> None:
        occupancy = HolderOccupancyEvidence(
            StripCompletenessEvidence(3, 3, 3, 2, 0),
            True,
            EvidenceState.SUPPORTED,
            EvidenceState.SUPPORTED,
            True,
            _holder_safety(Box(0, 0, 500, 100)),
            PixelInterval(0.0, 2.0),
            PixelInterval(498.0, 500.0),
        )

        self.assertEqual(occupancy.occupancy_state, HolderOccupancyState.FILLED)
        self.assertFalse(occupancy.complete_underfilled_strip)

    def test_missing_holder_boundary_keeps_occupancy_unavailable(self) -> None:
        occupancy = HolderOccupancyEvidence(
            StripCompletenessEvidence(3, 3, 3, 2, 0),
            True,
            EvidenceState.SUPPORTED,
            EvidenceState.SUPPORTED,
            True,
            HolderSafetyEnvelope(
                (),
                ContainmentFallback(
                    Box(0, 0, 500, 100),
                    MeasurementProvenance(
                        MeasurementIdentity.CANVAS,
                        ObservationId("holder_occupancy_containment"),
                        (),
                        "holder occupancy test containment",
                    ),
                ),
            ),
            PixelInterval.exact(50.0),
            PixelInterval.exact(400.0),
        )

        self.assertEqual(occupancy.occupancy_state, HolderOccupancyState.UNAVAILABLE)
        self.assertIsNone(occupancy.leading_slack_px)
        self.assertIsNone(occupancy.trailing_slack_px)

    def test_underfill_cannot_override_content_or_dimension_contradiction(self) -> None:
        completeness = StripCompletenessEvidence(3, 3, 3, 2, 0)
        for coverage_state, dimension_state in (
            (EvidenceState.CONTRADICTED, EvidenceState.SUPPORTED),
            (EvidenceState.SUPPORTED, EvidenceState.CONTRADICTED),
        ):
            occupancy = HolderOccupancyEvidence(
                completeness,
                True,
                coverage_state,
                dimension_state,
                True,
                _holder_safety(Box(0, 0, 500, 100)),
                PixelInterval.exact(50.0),
                PixelInterval.exact(400.0),
            )
            self.assertFalse(occupancy.complete_underfilled_strip)

    def test_geometry_blank_slot_still_counts_toward_full_sequence(self) -> None:
        completeness = StripCompletenessEvidence(
            count=4,
            nominal_count=4,
            valid_frame_slot_count=4,
            resolved_internal_boundary_count=3,
            independent_separator_count=0,
        )

        self.assertTrue(completeness.frame_count_complete)
        self.assertTrue(completeness.frame_sequence_complete)

    def test_holder_occupancy_uses_frame_slots_not_content_run_count(self) -> None:
        geometry = candidate_fixture().geometry
        coverage = FrameCoverageEvidence(
            (0, 310),
            ((0, 150), (160, 310)),
            ((10, 40), (60, 90), (170, 300)),
            0,
        )

        occupancy = holder_occupancy_evidence(
            count=geometry.count,
            holder_safety=geometry.holder_safety,
            frame_slots=geometry.frame_slots,
            separator_assignments=geometry.separator_assignments,
            physical_spec=FORMATS["135"],
            content_support_available=True,
            frame_coverage=coverage,
            frame_dimensions=_dimensions(EvidenceState.SUPPORTED),
        )

        self.assertEqual(occupancy.strip_completeness.count, 2)
        self.assertNotEqual(
            occupancy.strip_completeness.count,
            len(coverage.content_runs),
        )


if __name__ == "__main__":
    unittest.main()
