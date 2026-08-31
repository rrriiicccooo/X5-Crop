from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    phase_edge as edge,
    phase_template as template,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import (
    TemplateCrossInput,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_evidence import (
    EvidenceUse,
    PhysicalUnknown,
    template_evidence_use_ledger,
)
from x5crop.detection.photo_geometry.observation_types import (
    CrossHeightEdgeResolution,
    CrossHeightEdgeResolutionKind,
)
from x5crop.detection.photo_geometry.template_phase import (
    fit_template_phase,
    fit_template_phase_with_local_advance,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    TemplatePhaseInput,
)
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)


class TemplateEvidenceContractTest(unittest.TestCase):
    def test_local_boundary_is_not_reported_as_phase_or_pitch(self) -> None:
        direction = FiniteInterval.exact(0.0)
        start = replace(
            edge("phase:start", 100.0),
            qualified_anchor_roles=(BoundaryRole.START,),
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=direction,
            full_direction_interval_degrees=direction,
        )
        end = replace(
            edge("local:end", 201.0),
            qualified_anchor_roles=(BoundaryRole.END,),
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=direction,
            full_direction_interval_degrees=direction,
            fit_residual_px=20.0,
        )
        spec = replace(
            template(1),
            frame_width_px=PositiveInterval(98.0, 102.0),
        )
        phase = fit_template_phase_with_local_advance(
            TemplatePhaseInput(
                observations=(start, end),
                separator_bands=(),
                template=spec,
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(spec),
                scale_px_per_mm=PositiveInterval.exact(100.0),
                holder_span_px=None,
                phase_authority_px=FiniteInterval.exact(100.0),
            )
        )
        cross = fit_template_cross(
            TemplateCrossInput(template=spec, fixed_height_px=240.0)
        )

        ledger = template_evidence_use_ledger(
            (start, end),
            (),
            (),
            phase,
            cross,
            (),
        )

        by_id = {item.observation_id: item for item in ledger}
        self.assertEqual(
            by_id[ObservationId("phase:start")].physical_owner,
            PhysicalUnknown.PHASE,
        )
        self.assertEqual(
            by_id[ObservationId("local:end")].physical_owner,
            PhysicalUnknown.LOCAL_BOUNDARY,
        )

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
            (),
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
                (),
            )

    def test_bound_cross_height_support_has_one_validation_owner(self) -> None:
        observation = edge("edge:joint", 40.0)
        spec = template(1)
        phase = fit_template_phase((observation,), spec)
        cross = fit_template_cross(
            TemplateCrossInput(template=spec, fixed_height_px=240.0)
        )
        support_id = ObservationId("cross-height:support")

        ledger = template_evidence_use_ledger(
            (observation,),
            (),
            (),
            phase,
            cross,
            (
                CrossHeightEdgeResolution(
                    support_observation_id=support_id,
                    state=EvidenceState.SUPPORTED,
                    kind=CrossHeightEdgeResolutionKind.BOUND_DIRECT_EDGE,
                    compatible_direct_edge_ids=(observation.observation_id,),
                    final_edge_observation_id=observation.observation_id,
                    failure_kind=None,
                ),
            ),
        )

        support_fact = next(
            item for item in ledger if item.observation_id == support_id
        )
        self.assertEqual(support_fact.use, EvidenceUse.VALIDATION)
        self.assertEqual(
            support_fact.physical_owner,
            PhysicalUnknown.LOCAL_BOUNDARY,
        )


if __name__ == "__main__":
    unittest.main()
