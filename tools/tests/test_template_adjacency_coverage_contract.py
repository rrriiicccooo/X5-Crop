from __future__ import annotations

import unittest

from tools.tests.template_test_support import (
    phase_sequence_measurement,
    phase_template,
    placement_sequence,
)
from x5crop.detection.photo_geometry.template_adjacency_coverage import (
    AdjacencyCoverageState,
    assess_adjacency_observation_coverage,
)
from x5crop.domain import FiniteInterval


class TemplateAdjacencyCoverageContractTests(unittest.TestCase):
    def test_adjacent_integer_ownership_ranges_form_complete_coverage(self) -> None:
        fit = placement_sequence(phase_template(2))

        coverage = assess_adjacency_observation_coverage(
            fit,
            (
                phase_sequence_measurement("left", FiniteInterval(0.0, 209.0)),
                phase_sequence_measurement("right", FiniteInterval(210.0, 500.0)),
            ),
            directly_observed_ordinals=(),
        )

        self.assertEqual(coverage[0].state, AdjacencyCoverageState.COMPLETE)
        self.assertTrue(all(item.complete for item in coverage[0].trace_coverage))

    def test_missing_integer_coordinate_keeps_coverage_incomplete(self) -> None:
        fit = placement_sequence(phase_template(2))

        coverage = assess_adjacency_observation_coverage(
            fit,
            (
                phase_sequence_measurement("left", FiniteInterval(0.0, 208.0)),
                phase_sequence_measurement("right", FiniteInterval(210.0, 500.0)),
            ),
            directly_observed_ordinals=(),
        )

        self.assertEqual(coverage[0].state, AdjacencyCoverageState.INCOMPLETE)
        self.assertTrue(
            all(
                item.covered_coordinate_count
                == item.required_coordinate_count - 1
                for item in coverage[0].trace_coverage
            )
        )


if __name__ == "__main__":
    unittest.main()
