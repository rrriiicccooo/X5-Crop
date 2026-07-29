from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.regression.performance import (
    MEASURED_RUN_COUNT,
    PerformanceTiming,
    ProductionPerformanceResult,
)


def _timing(label: str, seconds_per_input: float, outputs: int) -> PerformanceTiming:
    return PerformanceTiming(
        label=label,
        wall_seconds=seconds_per_input * 24,
        input_count=24,
        completed_inputs=24,
        frame_output_count=outputs,
    )


class PerformanceCertificationContractTest(unittest.TestCase):
    def _result(
        self,
        seconds_per_input: float,
        outputs: int,
        *,
        detector_only: bool,
    ) -> ProductionPerformanceResult:
        root = Path(tempfile.gettempdir()) / "x5crop-contract-performance"
        return ProductionPerformanceResult(
            cold=_timing("cold", seconds_per_input, outputs),
            measured=tuple(
                _timing(f"measured-{index}", seconds_per_input, outputs)
                for index in range(1, MEASURED_RUN_COUNT + 1)
            ),
            output_root=root,
            detector_only=detector_only,
        )

    def test_detector_diagnostic_requires_strict_headroom(self) -> None:
        under = self._result(4.999, 0, detector_only=True)
        exact = self._result(5.0, 0, detector_only=True)
        self.assertTrue(under.passed)
        self.assertEqual(under.certification_status, "diagnostic_only")
        self.assertFalse(exact.passed)
        self.assertEqual(exact.certification_status, "failed")

    def test_real_tiff_contract_cannot_pass_without_outputs(self) -> None:
        result = self._result(4.0, 0, detector_only=False)
        self.assertFalse(result.passed)
        self.assertEqual(result.certification_status, "not_certified")

    def test_real_tiff_contract_requires_outputs_and_includes_limit(self) -> None:
        result = self._result(5.0, 24, detector_only=False)
        self.assertTrue(result.passed)
        self.assertEqual(result.certification_status, "certified")


if __name__ == "__main__":
    unittest.main()
