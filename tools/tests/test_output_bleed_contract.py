from __future__ import annotations

from dataclasses import dataclass
import unittest
from unittest.mock import patch

import numpy as np

from x5crop.domain import Box, FinalDetection, Gap
from x5crop.detection.evidence.output_overlap import output_overlap_evidence_detail
from x5crop.output.bleed import (
    AxisBleedParameters,
    detection_has_output_overlap_evidence,
    output_bleed_parameters_for_detection,
)
from x5crop.policies.runtime.output_evidence import OutputOverlapEvidencePolicy


@dataclass(frozen=True)
class _OutputPolicy:
    detection_long_axis_bleed: int = 20
    detection_short_axis_bleed: int = 10
    output_overlap_long_axis_bleed_capacity: int = 50


def _detection(detail: dict) -> FinalDetection:
    return FinalDetection(
        film_format="135",
        layout="horizontal",
        strip_mode="full",
        count=1,
        outer=Box(0, 0, 100, 60),
        frames=[Box(0, 0, 100, 60)],
        gaps=[],
        confidence=0.95,
        detail=detail,
        status="approved_auto",
        final_review_reasons=[],
    )


class OutputBleedContractTest(unittest.TestCase):
    def test_output_overlap_evidence_requires_sufficient_available_bleed(self) -> None:
        detection = _detection({})
        detection.gaps = [Gap(1, 50.0, 0.5, "grid")]
        record = {
            "output_overlap_class": "medium",
            "width_px": 0.0,
            "signals": {"window": {"start": 10, "end": 50}},
        }

        with patch(
            "x5crop.detection.evidence.output_overlap.gap_diagnostic_record",
            return_value=record,
        ):
            protected = output_overlap_evidence_detail(
                np.zeros((80, 120), dtype=np.uint8),
                detection,
                separator_policy=None,
                nearby_policy=None,
                output_overlap_policy=OutputOverlapEvidencePolicy(enabled=True),
                available_output_bleed_px=20,
            )
            unresolved = output_overlap_evidence_detail(
                np.zeros((80, 120), dtype=np.uint8),
                detection,
                separator_policy=None,
                nearby_policy=None,
                output_overlap_policy=OutputOverlapEvidencePolicy(enabled=True),
                available_output_bleed_px=19,
            )

        self.assertEqual(protected["required_output_bleed_px"], 20)
        self.assertEqual(protected["available_output_bleed_px"], 20)
        self.assertTrue(protected["output_overlap_protected_by_bleed"])
        self.assertFalse(protected["output_overlap_unresolved"])
        self.assertEqual(unresolved["required_output_bleed_px"], 20)
        self.assertEqual(unresolved["available_output_bleed_px"], 19)
        self.assertFalse(unresolved["output_overlap_protected_by_bleed"])
        self.assertTrue(unresolved["output_overlap_unresolved"])

    def test_protected_output_overlap_increases_long_axis_bleed(self) -> None:
        detection = _detection(
            {
                "output_overlap_evidence": {
                    "used": True,
                    "output_overlap_detected": True,
                    "output_overlap_protected_by_bleed": True,
                    "output_overlap_unresolved": False,
                    "required_output_bleed_px": 36,
                }
            }
        )

        self.assertTrue(detection_has_output_overlap_evidence(detection))
        self.assertEqual(
            output_bleed_parameters_for_detection(
                AxisBleedParameters(long_axis=20, short_axis=10),
                detection,
                _OutputPolicy(),
            ),
            AxisBleedParameters(long_axis=36, short_axis=10),
        )

    def test_boolean_overlap_protection_without_required_bleed_is_not_enough(self) -> None:
        detection = _detection(
            {
                "output_overlap_evidence": {
                    "used": True,
                    "output_overlap_detected": True,
                    "output_overlap_protected_by_bleed": True,
                    "output_overlap_unresolved": False,
                }
            }
        )

        self.assertFalse(detection_has_output_overlap_evidence(detection))
        self.assertEqual(
            output_bleed_parameters_for_detection(
                AxisBleedParameters(long_axis=20, short_axis=10),
                detection,
                _OutputPolicy(),
            ),
            AxisBleedParameters(long_axis=20, short_axis=10),
        )

    def test_unresolved_output_overlap_does_not_claim_bleed_protection(self) -> None:
        detection = _detection(
            {
                "output_overlap_evidence": {
                    "used": True,
                    "output_overlap_detected": True,
                    "output_overlap_protected_by_bleed": False,
                    "output_overlap_unresolved": True,
                }
            }
        )

        self.assertFalse(detection_has_output_overlap_evidence(detection))
        self.assertEqual(
            output_bleed_parameters_for_detection(
                AxisBleedParameters(long_axis=20, short_axis=10),
                detection,
                _OutputPolicy(),
            ),
            AxisBleedParameters(long_axis=20, short_axis=10),
        )

    def test_diagnostics_summary_does_not_drive_output_bleed(self) -> None:
        detection = _detection(
            {
                "diagnostics": {
                    "summary": {
                        "output_overlap_like_model_gaps": 2,
                        "output_overlap_counts": {"medium": 2},
                    }
                }
            }
        )

        self.assertFalse(detection_has_output_overlap_evidence(detection))
        self.assertEqual(
            output_bleed_parameters_for_detection(
                AxisBleedParameters(long_axis=20, short_axis=10),
                detection,
                _OutputPolicy(),
            ),
            AxisBleedParameters(long_axis=20, short_axis=10),
        )


if __name__ == "__main__":
    unittest.main()
