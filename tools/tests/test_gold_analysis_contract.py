from __future__ import annotations

import json
import unittest

from tools.regression.accuracy import GOLD_COHORT_PATH
from tools.regression.gold_analysis import (
    line_axis_position,
    optimization_stage_index,
    sequence_boundary_diagnostics,
)


class GoldAnalysisContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = {
            row["sample_id"]: row
            for row in (
                json.loads(line)
                for line in GOLD_COHORT_PATH.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            )
        }

    def test_stage_index_is_gold_only_and_keeps_irregular_nominal_separate(
        self,
    ) -> None:
        core = optimization_stage_index(self.records["S001"])
        irregular = optimization_stage_index(self.records["S098"])

        self.assertEqual(core["stage"], "stage1_core_nominal")
        self.assertEqual(core["reasons"], [])
        self.assertEqual(irregular["stage"], "stage2_harder_nominal")
        self.assertIn("gold_lattice_residual_over_2_percent", irregular["reasons"])

    def test_sequence_diagnostic_separates_binding_from_observation(self) -> None:
        geometry = self.records["S001"]["confirmed_geometry"]
        pool = {line["line_id"]: line for line in geometry["boundary_pool"]}
        first = geometry["slots"][0]["reference_geometry"]
        trace = (
            float(geometry["coordinate_system"]["canonical_extent"]["height"])
            - 1.0
        ) / 2.0
        start = line_axis_position(
            geometry,
            pool[first["start_boundary_id"]],
            axis="sequence",
            reference_trace_px=trace,
        )
        end = line_axis_position(
            geometry,
            pool[first["end_boundary_id"]],
            axis="sequence",
            reference_trace_px=trace,
        )

        def observation(identity: str, role: str, position: float) -> dict[str, object]:
            return {
                "observation_id": identity,
                "reference_trace_px": trace,
                "canonical_position_px": position,
                "full_position_interval_px": {
                    "minimum": position - 0.5,
                    "maximum": position + 0.5,
                },
                "qualified_anchor_roles": [role],
            }

        role_ids: list[str | None] = [None] * (2 * int(geometry["count"]))
        role_ids[0] = "start-observation"
        positions = [0.0] * len(role_ids)
        positions[0] = start
        positions[1] = end
        lane = {
            "observations": {
                "sequence_edges": [
                    observation("start-observation", "start", start),
                    observation("unbound-end-observation", "end", end),
                ]
            },
            "phase_competition": {
                "status": "resolved",
                "best": {
                    "role_observation_ids": role_ids,
                    "canonical_role_positions_px": positions,
                },
            },
        }

        diagnostics = sequence_boundary_diagnostics(
            geometry,
            lane,
            placement_state="supported",
        )

        self.assertEqual(diagnostics[0]["diagnostic_class"], "observed_and_bound")
        self.assertEqual(diagnostics[1]["diagnostic_class"], "observed_but_unbound")
        self.assertEqual(
            diagnostics[2]["diagnostic_class"],
            "template_inferred_without_gold_observation",
        )
        self.assertTrue(all(item["resolution"] == "resolved" for item in diagnostics))


if __name__ == "__main__":
    unittest.main()
