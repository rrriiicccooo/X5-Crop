from __future__ import annotations

from pathlib import Path
import unittest

from x5crop.detection.candidate.plan.count_hypotheses import count_hypothesis_plan
from x5crop.detection.candidate.selection.model import GeometryResolution
from x5crop.detection.evidence.count_planning import (
    CountPlanningEvidence,
    _placement_offsets,
)
from x5crop.formats import format_spec
from x5crop.geometry.separator_band import SeparatorBand
from x5crop.policies.registry import get_detection_policy


class AutoCountContractTest(unittest.TestCase):
    def _plan(self, format_id: str, requested_count: int | None = None):
        fmt = format_spec(format_id)
        policy = get_detection_policy(format_id, "partial")
        return count_hypothesis_plan(
            strip_mode="partial",
            requested_count=requested_count,
            fmt=fmt,
            partial_offsets=policy.partial_count_offsets,
            planning_evidence=CountPlanningEvidence.unavailable(),
        )

    def test_partial_auto_searches_largest_count_first(self) -> None:
        self.assertEqual(
            [item.count for item in self._plan("135").hypotheses],
            [5, 4, 3, 2, 1],
        )

    def test_only_complete_underfilled_formats_include_nominal_count(self) -> None:
        self.assertEqual(
            [item.count for item in self._plan("xpan").hypotheses],
            [3, 2, 1],
        )
        self.assertEqual(
            [item.count for item in self._plan("120-66").hypotheses],
            [3, 2, 1],
        )
        self.assertNotIn(
            format_spec("135").default_count,
            [item.count for item in self._plan("135").hypotheses],
        )

    def test_nominal_underfilled_count_has_one_placement(self) -> None:
        for format_id in ("xpan", "120-66"):
            hypothesis = self._plan(format_id).hypotheses[0]
            self.assertEqual(hypothesis.offsets, (0.0,))
            self.assertEqual(hypothesis.placement_source, "offset_not_applicable")

    def test_requested_count_is_single_nonautomatic_hypothesis(self) -> None:
        plan = self._plan("135", 3)
        self.assertFalse(plan.automatic)
        self.assertEqual(tuple(item.count for item in plan.hypotheses), (3,))

    def test_invalid_requested_count_is_assembly_error(self) -> None:
        with self.assertRaises(ValueError):
            self._plan("120-66", 4)

    def test_observed_separator_bands_only_change_placement(self) -> None:
        fmt = format_spec("135")
        policy = get_detection_policy("135", "partial")
        evidence = CountPlanningEvidence(
            source_outer=None,
            observed_bands=(SeparatorBand(90, 110, 100, 20, 1.0),),
            placement_offsets=((3, (0.37,)),),
        )
        plan = count_hypothesis_plan(
            strip_mode="partial",
            requested_count=None,
            fmt=fmt,
            partial_offsets=policy.partial_count_offsets,
            planning_evidence=evidence,
        )
        self.assertEqual([item.count for item in plan.hypotheses], [5, 4, 3, 2, 1])
        self.assertEqual(next(item for item in plan.hypotheses if item.count == 3).offsets, (0.37,))

    def test_single_frame_has_no_fixed_offset_grid(self) -> None:
        hypothesis = self._plan("135").hypotheses[-1]
        self.assertEqual(hypothesis.count, 1)
        self.assertEqual(hypothesis.offsets, ())

    def test_separator_placement_uses_photo_edges_not_equal_holder_pitch(self) -> None:
        placements = _placement_offsets(
            [
                SeparatorBand(120, 130, 125, 10, 1.0),
                SeparatorBand(230, 250, 240, 20, 1.0),
            ],
            outer_width=400.0,
            frame_width=100.0,
            allowed_counts=(3,),
        )

        self.assertEqual(placements, ((3, (0.2857,)),))

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

    def test_geometry_resolution_names_resolved_alternatives_not_exhaustive_execution(self) -> None:
        fields = GeometryResolution.__dataclass_fields__
        self.assertIn("alternative_geometries_resolved", fields)
        self.assertNotIn("distinct_geometries_evaluated", fields)


if __name__ == "__main__":
    unittest.main()
