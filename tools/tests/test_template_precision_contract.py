from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import unittest

from tools.tests.test_template_measurement_plan_contract import _plan
from tools.tests.test_template_placement_contract import (
    _compose,
    _cross,
    _direction,
    _sequence,
)
from x5crop.detection.photo_geometry.template_precision import (
    PrecisionComponent,
    template_precision_ledger,
)
from x5crop.domain import FiniteInterval


class TemplatePrecisionContractTest(unittest.TestCase):
    def test_selected_uncertainty_is_attributed_without_becoming_a_gate(self) -> None:
        plan = _plan()
        sequence = _sequence(plan.template_spec)
        phase = sequence.phase_lattice_fit
        sequence = replace(
            sequence,
            phase_lattice_fit=replace(
                phase,
                cycle_phase_interval_px=FiniteInterval(98.0, 102.0),
                absolute_phase_interval_px=FiniteInterval(98.0, 102.0),
            ),
        )
        placement = _compose(
            plan.template_spec,
            sequence,
            _cross(plan.template_spec, direction=_direction()),
            direction=_direction(),
            lane_id=plan.lane_id,
        )

        ledger = template_precision_ledger(placement, plan)

        self.assertEqual(
            tuple(item.component for item in ledger.contributions),
            tuple(PrecisionComponent),
        )
        self.assertAlmostEqual(
            ledger.total_sequence_px,
            sum(item.sequence_px for item in ledger.contributions),
        )
        for item in ledger.contributions:
            self.assertAlmostEqual(
                item.conditional_sequence_limit_px,
                ledger.sequence_limit_px
                - ledger.total_sequence_px
                + item.sequence_px,
            )

        gate_source = (
            Path(__file__).parents[2]
            / "x5crop/detection/photo_geometry/template_gate.py"
        ).read_text(encoding="utf-8")
        imports = {
            alias.name
            for node in ast.walk(ast.parse(gate_source))
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in getattr(node, "names", ())
        }
        self.assertNotIn("TemplatePrecisionLedger", imports)
        self.assertNotIn("template_precision_ledger", imports)

    def test_narrower_phase_interval_cannot_increase_precision_uncertainty(self) -> None:
        plan = _plan()
        sequence = _sequence(plan.template_spec)

        def ledger(radius: float):
            phase = sequence.phase_lattice_fit
            fitted = replace(
                sequence,
                phase_lattice_fit=replace(
                    phase,
                    cycle_phase_interval_px=FiniteInterval(
                        phase.canonical_cycle_phase_px - radius,
                        phase.canonical_cycle_phase_px + radius,
                    ),
                    absolute_phase_interval_px=FiniteInterval(
                        phase.canonical_absolute_phase_px - radius,
                        phase.canonical_absolute_phase_px + radius,
                    ),
                ),
            )
            placement = _compose(
                plan.template_spec,
                fitted,
                _cross(plan.template_spec, direction=_direction()),
                direction=_direction(),
                lane_id=plan.lane_id,
            )
            return template_precision_ledger(placement, plan)

        self.assertLessEqual(
            ledger(1.0).total_sequence_px,
            ledger(3.0).total_sequence_px,
        )


if __name__ == "__main__":
    unittest.main()
