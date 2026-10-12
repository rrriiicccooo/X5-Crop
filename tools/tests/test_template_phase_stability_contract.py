from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.tests.template_test_support import (
    phase_edge as edge,
    phase_sequence_measurement,
    phase_separator as separator,
    phase_template as template,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_model import (
    GlobalLatticeAuthorityEvidence,
    PhaseFailureKind,
    PhaseFitStatus,
    TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_stability import (
    AnchorDependencyEffect,
    leave_one_anchor_out_phase_stability,
)
from x5crop.domain import FiniteInterval


class TemplatePhaseStabilityContractTest(unittest.TestCase):
    def test_leave_one_anchor_out_is_bounded_and_reports_dependency(self) -> None:
        observations = tuple(
            edge(f"stable:{index}", coordinate)
            for index, coordinate in enumerate((40.0, 140.0, 160.0, 260.0))
        )
        compiled = template(2)
        result = fit_template_phase(observations, compiled)
        assert result.best is not None
        analysis = leave_one_anchor_out_phase_stability(
            result,
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=compiled,
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(compiled),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "bounded-stability",
                        FiniteInterval(0.0, 400.0),
                    ),
                ),
            ),
        )
        self.assertEqual(
            analysis.receipt.refit_count,
            len(analysis.dependencies),
        )

    def test_stability_removes_both_sides_of_one_separator_atom(self) -> None:
        start = edge("start", 40.0)
        left = replace(edge("separator-left", 140.0), polarity=-1)
        right = replace(edge("separator-right", 160.0), polarity=1)
        end = replace(edge("end", 260.0), polarity=-1)
        band = separator("separator-band", left, right, FiniteInterval(19.0, 21.0))
        observations = (start, left, right, end)
        compiled = template(2)
        result = fit_template_phase(
            observations,
            compiled,
            separator_bands=(band,),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)

        analysis = leave_one_anchor_out_phase_stability(
            result,
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(band,),
                template=compiled,
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(compiled),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "separator-stability",
                        FiniteInterval(0.0, 400.0),
                    ),
                ),
                global_lattice_evidence=GlobalLatticeAuthorityEvidence(
                    pitch_observation_ids=(band.observation_id,),
                ),
            ),
        )

        separator_dependency = next(
            item
            for item in analysis.dependencies
            if set(item.observation_ids)
            == {left.observation_id, right.observation_id}
        )
        self.assertEqual(
            separator_dependency.support_atom_id,
            band.observation_id,
        )
        self.assertLessEqual(analysis.receipt.refit_count, 4)
        self.assertTrue(
            all(
                item.effect in tuple(AnchorDependencyEffect)
                for item in analysis.dependencies
            )
        )

    def test_stability_never_reuses_selected_source_width(self) -> None:
        observations = tuple(
            edge(f"selected-width:{index}", coordinate)
            for index, coordinate in enumerate((40.0, 140.0, 160.0, 260.0))
        )
        compiled = template(2)
        result = fit_template_phase(observations, compiled)
        phase_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(),
            template=compiled,
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(compiled),
            scale_px_per_mm=None,
            holder_span_px=None,
            phase_authority_px=None,
            global_lattice_evidence=GlobalLatticeAuthorityEvidence(
                frame_width_observation_ids=tuple(
                    item.observation_id for item in observations
                ),
            ),
        )
        refit_inputs = []

        def capture_refit(candidate_input):
            refit_inputs.append(candidate_input)
            return replace(
                result,
                best=None,
                runner_up=None,
                status=PhaseFitStatus.UNRESOLVED,
                ambiguity_reason="test refit remains unresolved",
                failure_kind=PhaseFailureKind.GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE,
                winner_basis=None,
            )

        with patch(
            "x5crop.detection.photo_geometry.template_stability."
            "fit_template_phase_with_adjacency_relations",
            side_effect=capture_refit,
        ):
            leave_one_anchor_out_phase_stability(result, phase_input)

        self.assertTrue(refit_inputs)
        self.assertTrue(
            all(
                not item.global_lattice_evidence.frame_width_observation_ids
                for item in refit_inputs
            )
        )

    def test_leave_one_anchor_out_reports_discrete_slot_jump(self) -> None:
        observations = (edge("jump:start", 40.0), edge("jump:end", 140.0))
        compiled = template(1)
        result = fit_template_phase(observations, compiled)

        analysis = leave_one_anchor_out_phase_stability(
            result,
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=compiled,
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(compiled),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
            ),
        )

        self.assertEqual(
            tuple(item.effect for item in analysis.dependencies),
            (
                AnchorDependencyEffect.UNRESOLVED_WITHOUT_ANCHOR,
                AnchorDependencyEffect.UNRESOLVED_WITHOUT_ANCHOR,
            ),
        )

    def test_leave_one_anchor_out_reports_lost_unknown_closure(self) -> None:
        coordinates = (
            36.149664229248124,
            135.74929537674714,
            167.9303173681674,
            259.52421612035914,
        )
        observations = tuple(
            edge(f"continuous:{index}", coordinate)
            for index, coordinate in enumerate(coordinates)
        )
        compiled = template(2)
        result = fit_template_phase(observations, compiled)

        analysis = leave_one_anchor_out_phase_stability(
            result,
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=compiled,
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(compiled),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "continuous-stability",
                        FiniteInterval(0.0, 400.0),
                    ),
                ),
            ),
        )

        self.assertTrue(
            all(
                item.effect
                == AnchorDependencyEffect.UNRESOLVED_WITHOUT_ANCHOR
                for item in analysis.dependencies
            )
        )


if __name__ == "__main__":
    unittest.main()
