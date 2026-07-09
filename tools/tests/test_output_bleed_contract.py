from __future__ import annotations

from dataclasses import dataclass
import unittest

from x5crop.domain import Box, Detection
from x5crop.output.bleed import (
    AxisBleedParameters,
    detection_has_output_overlap_evidence,
    output_bleed_parameters_for_detection,
)


@dataclass(frozen=True)
class _OutputPolicy:
    detection_long_axis_bleed: int = 20
    detection_short_axis_bleed: int = 10
    output_overlap_long_axis_bleed: int = 50


def _detection(detail: dict) -> Detection:
    return Detection(
        film_format="135",
        layout="horizontal",
        strip_mode="full",
        count=1,
        outer=Box(0, 0, 100, 60),
        frames=[Box(0, 0, 100, 60)],
        gaps=[],
        confidence=0.95,
        final_review_reasons=[],
        detail=detail,
    )


class OutputBleedContractTest(unittest.TestCase):
    def test_protected_output_overlap_increases_long_axis_bleed(self) -> None:
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

        self.assertTrue(detection_has_output_overlap_evidence(detection))
        self.assertEqual(
            output_bleed_parameters_for_detection(
                AxisBleedParameters(long_axis=20, short_axis=10),
                detection,
                _OutputPolicy(),
            ),
            AxisBleedParameters(long_axis=50, short_axis=10),
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
