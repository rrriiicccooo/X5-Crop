from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    phase_sequence_measurement,
    phase_template,
    placement_sequence,
)
from x5crop.detection.photo_geometry.template_adjacency_coverage import (
    AdjacencyCoveragePreparation,
    AdjacencyCoverageState,
    assess_adjacency_observation_coverage,
)
from x5crop.domain import FiniteInterval


class AdjacencyCoveragePreparationContractTest(unittest.TestCase):
    @staticmethod
    def _fixture():
        fit = placement_sequence(phase_template(3))
        measurements = (
            phase_sequence_measurement(
                "shared",
                FiniteInterval(0.0, 500.0),
            ),
        )
        return fit, measurements

    def test_observed_ordinals_change_only_normal_flag(self):
        fit, measurements = self._fixture()
        preparation = AdjacencyCoveragePreparation(
            measurements,
            fit.template,
        )
        first = assess_adjacency_observation_coverage(
            fit,
            measurements,
            directly_observed_ordinals=(1,),
            input_preparation=preparation,
        )
        second = assess_adjacency_observation_coverage(
            fit,
            measurements,
            directly_observed_ordinals=(2,),
            input_preparation=preparation,
        )
        self.assertEqual(
            tuple(item.trace_coverage for item in first),
            tuple(item.trace_coverage for item in second),
        )
        self.assertEqual(
            tuple(item.covering_query_ids for item in first),
            tuple(item.covering_query_ids for item in second),
        )
        self.assertEqual(
            tuple(item.normal_inference_required for item in first),
            (False, True),
        )
        self.assertEqual(
            tuple(item.normal_inference_required for item in second),
            (True, False),
        )
        self.assertEqual(preparation.lookup_count, 4)
        self.assertEqual(preparation.preparation_count, 2)

    def test_same_query_id_with_changed_ownership_or_completion_rejects_preparation(self):
        fit, measurements = self._fixture()
        preparation = AdjacencyCoveragePreparation(measurements, fit.template)
        changed_ownership = (
            phase_sequence_measurement(
                "shared",
                FiniteInterval(0.0, 499.0),
            ),
        )
        changed_completion = (
            phase_sequence_measurement(
                "shared",
                FiniteInterval(0.0, 500.0),
                complete=False,
            ),
        )
        for changed in (changed_ownership, changed_completion):
            with self.subTest(changed=changed), self.assertRaisesRegex(
                ValueError,
                "different template or registered queries",
            ):
                assess_adjacency_observation_coverage(
                    fit,
                    changed,
                    directly_observed_ordinals=(),
                    input_preparation=preparation,
                )
        self.assertEqual(preparation.lookup_count, 0)
        self.assertEqual(preparation.preparation_count, 0)

    def test_incomplete_extra_trace_counts_but_cannot_be_covered(self):
        fit, _measurements = self._fixture()
        complete = phase_sequence_measurement(
            "complete",
            FiniteInterval(0.0, 500.0),
            trace_positions_px=(0, 10, 20),
        )
        incomplete_extra_trace = phase_sequence_measurement(
            "incomplete-extra",
            FiniteInterval(0.0, 500.0),
            trace_positions_px=(30,),
            complete=False,
        )
        measurements = (complete, incomplete_extra_trace)
        preparation = AdjacencyCoveragePreparation(measurements, fit.template)
        coverage = assess_adjacency_observation_coverage(
            fit,
            measurements,
            directly_observed_ordinals=(),
            input_preparation=preparation,
        )
        for item in coverage:
            with self.subTest(relation_ordinal=item.relation_ordinal):
                self.assertEqual(item.required_trace_count, 4)
                self.assertEqual(item.covered_trace_count, 3)
                self.assertEqual(item.state, AdjacencyCoverageState.INCOMPLETE)
                self.assertEqual(
                    tuple(trace.trace_position_px for trace in item.trace_coverage),
                    (0, 10, 20, 30),
                )
                self.assertFalse(item.trace_coverage[-1].complete)
                self.assertEqual(item.trace_coverage[-1].covered_coordinate_count, 0)

    def test_full_corridor_change_recomputes_only_new_required_interval(self):
        fit, measurements = self._fixture()
        preparation = AdjacencyCoveragePreparation(measurements, fit.template)
        original = assess_adjacency_observation_coverage(
            fit,
            measurements,
            directly_observed_ordinals=(),
            input_preparation=preparation,
        )
        widened_full_intervals = list(fit.model_full_role_intervals_px)
        widened_full_intervals[2] = FiniteInterval(219.0, 221.0)
        changed_fit = replace(
            fit,
            model_full_role_intervals_px=tuple(widened_full_intervals),
        )
        self.assertIs(changed_fit.template, fit.template)
        changed = assess_adjacency_observation_coverage(
            changed_fit,
            measurements,
            directly_observed_ordinals=(),
            input_preparation=preparation,
        )
        self.assertEqual(original[0].required_interval_px, FiniteInterval(200.0, 220.0))
        self.assertEqual(changed[0].required_interval_px, FiniteInterval(200.0, 221.0))
        self.assertEqual(original[1], changed[1])
        self.assertEqual(preparation.lookup_count, 4)
        self.assertEqual(preparation.preparation_count, 3)

        reused = assess_adjacency_observation_coverage(
            changed_fit,
            measurements,
            directly_observed_ordinals=(),
            input_preparation=preparation,
        )
        self.assertEqual(reused, changed)
        self.assertEqual(preparation.lookup_count, 6)
        self.assertEqual(preparation.preparation_count, 3)

    def test_capacity_full_returns_fresh_equivalent_without_retaining_new_corridor(self):
        fit, measurements = self._fixture()
        preparation = AdjacencyCoveragePreparation(measurements, fit.template)
        maximum = preparation.maximum_corridors
        for index in range(maximum):
            preparation.for_interval(FiniteInterval(float(index), float(index)))
        self.assertEqual(len(preparation._corridors), maximum)
        self.assertEqual(preparation.lookup_count, maximum)
        self.assertEqual(preparation.preparation_count, maximum)

        expected = assess_adjacency_observation_coverage(
            fit,
            measurements,
            directly_observed_ordinals=(),
        )
        actual = assess_adjacency_observation_coverage(
            fit,
            measurements,
            directly_observed_ordinals=(),
            input_preparation=preparation,
        )
        self.assertEqual(actual, expected)
        self.assertEqual(preparation.lookup_count, maximum + 2)
        self.assertEqual(preparation.preparation_count, maximum + 2)
        self.assertEqual(len(preparation._corridors), maximum)

        repeated = assess_adjacency_observation_coverage(
            fit,
            measurements,
            directly_observed_ordinals=(),
            input_preparation=preparation,
        )
        self.assertEqual(repeated, expected)
        self.assertEqual(preparation.lookup_count, maximum + 4)
        self.assertEqual(preparation.preparation_count, maximum + 4)

    def test_different_template_rejects_preparation(self):
        fit, measurements = self._fixture()
        preparation = AdjacencyCoveragePreparation(measurements, fit.template)
        different_fit = placement_sequence(phase_template(4))
        with self.assertRaisesRegex(
            ValueError,
            "different template or registered queries",
        ):
            assess_adjacency_observation_coverage(
                different_fit,
                measurements,
                directly_observed_ordinals=(),
                input_preparation=preparation,
            )
        self.assertEqual(preparation.lookup_count, 0)
        self.assertEqual(preparation.preparation_count, 0)


if __name__ == "__main__":
    unittest.main()
