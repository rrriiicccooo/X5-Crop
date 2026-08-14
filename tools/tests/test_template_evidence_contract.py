from __future__ import annotations

import unittest

from tools.tests.test_template_phase_contract import edge, template
from x5crop.detection.photo_geometry.template_cross import (
    TemplateCrossInput,
    fit_template_cross,
)
from x5crop.detection.photo_geometry.template_evidence import (
    EvidenceUse,
    PhysicalUnknown,
    template_evidence_use_ledger,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase


class TemplateEvidenceContractTest(unittest.TestCase):
    def test_sequence_observations_have_one_fit_or_validation_owner(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (40.0, 140.0, 160.0, 260.0, 900.0)
            )
        )
        spec = template(2)
        phase = fit_template_phase(observations, spec)
        cross = fit_template_cross(
            TemplateCrossInput(template=spec, fixed_height_px=240.0)
        )

        ledger = template_evidence_use_ledger(
            observations,
            (),
            (),
            phase,
            cross,
        )

        self.assertEqual(len(ledger), len(observations))
        self.assertEqual(
            len({item.observation_id for item in ledger}),
            len(ledger),
        )
        fitted = tuple(item for item in ledger if item.use == EvidenceUse.FIT)
        self.assertEqual(fitted[0].physical_owner, PhysicalUnknown.PHASE)
        self.assertTrue(
            all(
                item.physical_owner == PhysicalUnknown.PITCH
                for item in fitted[1:]
            )
        )
        self.assertEqual(ledger[-1].use, EvidenceUse.VALIDATION)

    def test_duplicate_physical_identity_cannot_be_counted_twice(self) -> None:
        observation = edge("edge:duplicate", 40.0)
        spec = template(1)
        phase = fit_template_phase((observation,), spec)
        cross = fit_template_cross(
            TemplateCrossInput(template=spec, fixed_height_px=240.0)
        )

        with self.assertRaisesRegex(ValueError, "multiple template uses"):
            template_evidence_use_ledger(
                (observation, observation),
                (),
                (),
                phase,
                cross,
            )


if __name__ == "__main__":
    unittest.main()
