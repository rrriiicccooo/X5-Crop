from __future__ import annotations

import unittest

from x5crop.image.deskew import (
    DeskewAngleMeasurement,
    DeskewMeasurementOutcome,
    LineFitMeasurement,
)
import x5crop.runtime.deskew as runtime_deskew


def _measurement(
    *,
    outcome: DeskewMeasurementOutcome = DeskewMeasurementOutcome.MEASURED,
    top: tuple[int, float] | None = None,
    bottom: tuple[int, float] | None = None,
) -> DeskewAngleMeasurement:
    def fit(value: tuple[int, float] | None) -> LineFitMeasurement | None:
        if value is None:
            return None
        return LineFitMeasurement(
            slope=0.001,
            inliers=value[0],
            median_residual=value[1],
        )

    return DeskewAngleMeasurement(
        outcome=outcome,
        angle_degrees=(
            0.05 if outcome == DeskewMeasurementOutcome.MEASURED else 0.0
        ),
        top_fit=fit(top),
        bottom_fit=fit(bottom),
    )


class DeskewMeasurementContractTest(unittest.TestCase):
    def test_measurement_outcome_is_typed_not_a_free_reason(self) -> None:
        self.assertNotIn("reason", DeskewAngleMeasurement.__dataclass_fields__)

    def test_measurement_types_reject_impossible_states(self) -> None:
        for factory in (
            lambda: LineFitMeasurement(float("nan"), 4, 1.0),
            lambda: LineFitMeasurement(0.0, 0, 1.0),
            lambda: LineFitMeasurement(0.0, 4, -1.0),
            lambda: DeskewAngleMeasurement(
                DeskewMeasurementOutcome.MEASURED,
                0.05,
                None,
                None,
            ),
            lambda: DeskewAngleMeasurement(
                DeskewMeasurementOutcome.INSUFFICIENT_EDGE_POINTS,
                0.05,
                None,
                None,
            ),
        ):
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_measurement_preference_uses_physical_fit_facts(self) -> None:
        preference = getattr(runtime_deskew, "_deskew_measurement_preference")
        invalid = _measurement(
            outcome=DeskewMeasurementOutcome.INSUFFICIENT_EDGE_POINTS
        )
        one_edge = _measurement(top=(8, 1.0))
        two_edges = _measurement(top=(8, 1.0), bottom=(7, 1.2))
        more_inliers = _measurement(top=(9, 1.0), bottom=(8, 1.2))
        lower_residual = _measurement(top=(9, 0.5), bottom=(8, 0.8))

        self.assertGreater(preference(one_edge), preference(invalid))
        self.assertGreater(preference(two_edges), preference(one_edge))
        self.assertGreater(preference(more_inliers), preference(two_edges))
        self.assertGreater(preference(lower_residual), preference(more_inliers))


if __name__ == "__main__":
    unittest.main()
