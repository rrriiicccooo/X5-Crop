from __future__ import annotations

import unittest

from x5crop.image.deskew import DeskewAngleMeasurement, LineFitMeasurement
import x5crop.runtime.deskew as runtime_deskew


def _measurement(
    *,
    reason: str | None = None,
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
        angle_degrees=0.05 if reason is None else 0.0,
        reason=reason,
        top_fit=fit(top),
        bottom_fit=fit(bottom),
    )


class DeskewMeasurementContractTest(unittest.TestCase):
    def test_measurement_types_reject_impossible_states(self) -> None:
        for factory in (
            lambda: LineFitMeasurement(float("nan"), 4, 1.0),
            lambda: LineFitMeasurement(0.0, 0, 1.0),
            lambda: LineFitMeasurement(0.0, 4, -1.0),
            lambda: DeskewAngleMeasurement(0.05, None, None, None),
            lambda: DeskewAngleMeasurement(0.05, "not_enough_points", None, None),
        ):
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_measurement_preference_uses_physical_fit_facts(self) -> None:
        preference = getattr(runtime_deskew, "_deskew_measurement_preference")
        invalid = _measurement(reason="not_enough_points")
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
