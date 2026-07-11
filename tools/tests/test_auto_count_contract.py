from __future__ import annotations

from pathlib import Path
from inspect import signature
import unittest

from x5crop.detection.candidate.plan.count_hypotheses import count_hypothesis_plan
from x5crop.detection.candidate.selection.model import GeometryResolution
from x5crop.formats import format_spec


class AutoCountContractTest(unittest.TestCase):
    def _plan(self, format_id: str, requested_count: int | None = None):
        return count_hypothesis_plan(
            strip_mode="partial",
            requested_count=requested_count,
            fmt=format_spec(format_id),
        )

    def test_partial_auto_searches_largest_count_first(self) -> None:
        self.assertEqual(
            [item.count for item in self._plan("135").hypotheses],
            [5, 4, 3, 2, 1],
        )

    def test_only_complete_underfilled_formats_include_nominal_count(self) -> None:
        for format_id in ("xpan", "120-66"):
            plan = self._plan(format_id)
            self.assertEqual(plan.hypotheses[0].count, format_spec(format_id).default_count)
        for format_id in ("135", "half", "120-645", "120-67"):
            counts = tuple(item.count for item in self._plan(format_id).hypotheses)
            self.assertNotIn(format_spec(format_id).default_count, counts)

    def test_requested_count_is_one_nonautomatic_hypothesis(self) -> None:
        plan = self._plan("135", 3)
        self.assertFalse(plan.automatic)
        self.assertEqual(tuple(item.count for item in plan.hypotheses), (3,))

    def test_invalid_requested_count_is_assembly_error(self) -> None:
        with self.assertRaises(ValueError):
            self._plan("120-66", 4)

    def test_count_plan_does_not_consume_pixel_measurements(self) -> None:
        self.assertNotIn("planning_evidence", signature(count_hypothesis_plan).parameters)

    def test_count_hypothesis_has_no_offset_grid(self) -> None:
        fields = self._plan("135").hypotheses[0].__dataclass_fields__
        self.assertNotIn("offsets", fields)
        self.assertNotIn("placement_source", fields)

    def test_early_stop_reads_geometry_resolution_only(self) -> None:
        root = Path(__file__).resolve().parents[2]
        pipeline = (root / "x5crop/detection/pipeline.py").read_text()
        evaluation = (
            root / "x5crop/detection/candidate/execution/model.py"
        ).read_text()
        self.assertIn("evaluation.geometry_resolved", pipeline)
        self.assertIn("selection.geometry_resolution.supported", evaluation)
        for forbidden in ("candidate_is_reliable", "candidate_gate.passed", ".confidence"):
            self.assertNotIn(forbidden, pipeline)

    def test_geometry_resolution_names_resolved_alternatives(self) -> None:
        fields = GeometryResolution.__dataclass_fields__
        self.assertIn("alternative_geometries_resolved", fields)


if __name__ == "__main__":
    unittest.main()
