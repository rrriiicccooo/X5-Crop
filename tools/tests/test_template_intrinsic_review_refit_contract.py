from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.tests.template_test_support import (
    phase_edge,
    phase_template,
    placement_sequence,
    unavailable_nominal_grid_prior,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleAuthorityFact,
    DirectRoleBindingAuthority,
)
from x5crop.detection.photo_geometry.template_model import (
    SeparatorRelation,
    SeparatorRelationKind,
    SequenceBindingUse,
)
from x5crop.detection.photo_geometry.template_phase_candidates import _BoundFit
from x5crop.detection.photo_geometry.template_phase_model import (
    NativeEndpointPhaseDiagnostic,
    NativeEndpointSelectionBasis,
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectionOutcome,
    TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_intrinsic_review_refit import (
    IntrinsicPhaseRefitFailureKind,
    IntrinsicPhaseReviewDiagnostic,
    build_intrinsic_phase_refit,
)


class IntrinsicPhaseReviewRefitContractTests(unittest.TestCase):
    @staticmethod
    def _unsafe_fit_replace(fit, **changes):
        """Make deliberately malformed owner output for typed-failure tests."""

        result = object.__new__(type(fit))
        for field_name in fit.__dataclass_fields__:
            object.__setattr__(
                result,
                field_name,
                changes.get(field_name, getattr(fit, field_name)),
            )
        return result

    def _fixture(
        self,
        *,
        contradicted: bool = True,
        local_role: int | None = None,
        all_intrinsic: bool = False,
    ):
        template = phase_template(3)
        fit = placement_sequence(template)
        observations = tuple(
            phase_edge(str(binding.observation_id), binding.canonical_position_px)
            for binding in fit.role_bindings
            if binding is not None
        )
        intrinsic_roles = set(range(6)) if all_intrinsic else {0, 1, 3, 5}
        facts: list[DirectRoleAuthorityFact] = []
        for role_index, binding in enumerate(fit.role_bindings):
            assert binding is not None
            intrinsic = role_index in intrinsic_roles
            bases = (
                (DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,)
                if intrinsic
                else (DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR,)
            )
            is_contradicted = contradicted and role_index == 3
            state = (
                EvidenceState.CONTRADICTED
                if is_contradicted
                else EvidenceState.SUPPORTED
            )
            conflicts = (
                (ObservationId("material-conflict:3"),)
                if is_contradicted
                else ()
            )
            facts.append(
                DirectRoleAuthorityFact(
                    role_index=role_index,
                    lane_ordinal=role_index // 2 + 1,
                    role=(
                        BoundaryRole.START
                        if role_index % 2 == 0
                        else BoundaryRole.END
                    ),
                    observation_id=binding.observation_id,
                    evidence_group_id=binding.evidence_group_id,
                    independent_support_region_count=3 if intrinsic else 2,
                    bases=bases,
                    blocking_material_conflict_ids=conflicts,
                    state=state,
                    trace_coordinates_px=() if intrinsic else (1, 2),
                )
            )
        if local_role is not None:
            fit = replace(
                fit,
                role_bindings=tuple(
                    replace(binding, use=SequenceBindingUse.LOCAL_REFINEMENT)
                    if index == local_role and binding is not None
                    else binding
                    for index, binding in enumerate(fit.role_bindings)
                ),
            )
        authority_state = (
            EvidenceState.CONTRADICTED
            if contradicted
            else EvidenceState.SUPPORTED
        )
        authority = DirectRoleBindingAuthority(
            state=authority_state,
            facts=tuple(facts),
            unsupported_role_indices=(3,) if contradicted else (),
            reason="fixed contradiction" if contradicted else None,
        )
        projection = PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=(
                PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION
                if contradicted
                else PhaseCandidateProjectionOutcome.REFIT_UNAVAILABLE
            ),
            basis=None,
            projected_out_bindings=(),
            retained_direct_constraint_rank=0 if contradicted else 3,
            reason="preserved fixed projection failure",
        )
        diagnostic = NativeEndpointPhaseDiagnostic(
            fit=fit,
            projection=projection,
            residual_compatible=True,
            terminal_role_indices=(0, 1, 4, 5) if all_intrinsic else (0, 1, 5),
            selection_basis=NativeEndpointSelectionBasis.INTRINSIC_TERMINAL,
        )
        phase_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(),
            template=template,
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template),
            scale_px_per_mm=None,
            holder_span_px=None,
            phase_authority_px=None,
        )
        return phase_input, diagnostic

    def test_replays_one_seed_and_preserves_contradicted_outer_ledger(self):
        phase_input, original = self._fixture()
        authority_before = original.projection.input_direct_role_authority
        projection_before = original.projection
        fit_before = original.fit

        from x5crop.detection.photo_geometry import template_phase_candidates

        real_fit_seed = template_phase_candidates._fit_seed
        with patch.object(
            template_phase_candidates,
            "_fit_seed",
            side_effect=real_fit_seed,
        ) as fitter:
            result = build_intrinsic_phase_refit(phase_input, original)

        self.assertIsNone(result.failure)
        fitter.assert_called_once()
        self.assertIsInstance(result.diagnostic, IntrinsicPhaseReviewDiagnostic)
        self.assertEqual(result.work.fit_seed_call_count, 1)
        self.assertEqual(
            result.diagnostic.retained_intrinsic_bindings,
            tuple(
                (index, binding.observation_id)
                for index, binding in enumerate(original.fit.role_bindings)
                if binding is not None and index in {0, 1, 3, 5}
            ),
        )
        contradicted = authority_before.facts[3]
        self.assertEqual(contradicted.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            result.diagnostic.original_diagnostic.projection,
            projection_before,
        )
        self.assertEqual(original.fit, fit_before)
        self.assertIs(result.original_diagnostic, original)

    def test_supported_nonintrinsic_and_local_intrinsic_are_validation_only(self):
        phase_input, original = self._fixture(contradicted=False, local_role=3)
        result = build_intrinsic_phase_refit(phase_input, original)
        self.assertIsNone(result.failure)
        assert result.diagnostic is not None
        identities = result.diagnostic.retained_intrinsic_bindings
        self.assertNotIn((3, ObservationId("sequence:3")), identities)
        validation = {
            (fact.role_index, fact.observation_id)
            for fact in result.diagnostic.validation_only_facts
        }
        self.assertIn((2, ObservationId("sequence:2")), validation)
        self.assertIn((4, ObservationId("sequence:4")), validation)
        self.assertIn((3, ObservationId("sequence:3")), validation)
        self.assertEqual(
            result.diagnostic.fit.binding_observation_ids,
            (
                ObservationId("sequence:0"),
                ObservationId("sequence:1"),
                None,
                None,
                None,
                ObservationId("sequence:5"),
            ),
        )

    def test_missing_relation_fails_before_seed_without_deleting_relation(self):
        phase_input, original = self._fixture()
        relation = SeparatorRelation(
            relation_ordinal=1,
            kind=SeparatorRelationKind.NORMAL,
            delta_interval_px=FiniteInterval.exact(0.0),
            canonical_delta_px=0.0,
            separator_band_observation_id=ObservationId("separator:1"),
            end_edge_observation_id=ObservationId("sequence:1"),
            next_start_edge_observation_id=ObservationId("sequence:2"),
            signed_gap_interval_px=FiniteInterval.exact(20.0),
            canonical_signed_gap_px=20.0,
        )
        relation_fit = self._unsafe_fit_replace(
            original.fit,
            adjacency_relations=(relation,),
        )
        relation_original = replace(original, fit=relation_fit)
        # The constructor still validates the complete role/fact mapping; the
        # missing intrinsic relation identity is rejected by the builder.
        with patch(
            "x5crop.detection.photo_geometry.template_intrinsic_review_refit._phase_candidates._fit_seed"
        ) as fitter:
            result = build_intrinsic_phase_refit(phase_input, relation_original)
        self.assertEqual(
            result.failure.kind,
            IntrinsicPhaseRefitFailureKind.RELATION_IDENTITY_UNAVAILABLE,
        )
        fitter.assert_not_called()
        self.assertEqual(relation_original.fit.adjacency_relations, (relation,))

    def test_none_fit_and_changed_slot_are_typed_failures_with_one_call(self):
        phase_input, original = self._fixture()
        with patch(
            "x5crop.detection.photo_geometry.template_intrinsic_review_refit._phase_candidates._fit_seed",
            return_value=None,
        ) as fitter:
            result = build_intrinsic_phase_refit(phase_input, original)
        self.assertEqual(result.failure.kind, IntrinsicPhaseRefitFailureKind.FIT_UNAVAILABLE)
        self.assertEqual(result.work.fit_seed_call_count, 1)
        fitter.assert_called_once()

        successful = build_intrinsic_phase_refit(phase_input, original)
        self.assertIsNone(successful.failure)
        assert successful.diagnostic is not None
        changed_lattice = replace(
            successful.diagnostic.fit.phase_lattice_fit,
            integer_slot_offset=1,
            canonical_absolute_phase_px=220.0,
            absolute_phase_interval_px=FiniteInterval.exact(220.0),
        )
        changed_fit = replace(
            successful.diagnostic.fit,
            phase_lattice_fit=changed_lattice,
        )
        with patch(
            "x5crop.detection.photo_geometry.template_intrinsic_review_refit._phase_candidates._fit_seed",
            return_value=_BoundFit(changed_fit, True),
        ):
            changed = build_intrinsic_phase_refit(phase_input, original)
        self.assertEqual(changed.failure.kind, IntrinsicPhaseRefitFailureKind.FIT_SLOT_CHANGED)

        with patch(
            "x5crop.detection.photo_geometry.template_intrinsic_review_refit._phase_candidates._fit_seed",
            return_value=_BoundFit(successful.diagnostic.fit, False),
        ):
            incompatible = build_intrinsic_phase_refit(phase_input, original)
        self.assertIsNone(incompatible.failure)
        self.assertFalse(incompatible.diagnostic.residual_compatible)

    def test_full_interval_counterevidence_is_retained_without_center_comparison(self):
        phase_input, original = self._fixture(contradicted=False)
        success = build_intrinsic_phase_refit(phase_input, original)
        self.assertIsNone(success.failure)
        assert success.diagnostic is not None
        proposal = success.diagnostic.fit
        full_intervals = tuple(
            FiniteInterval(900.0, 901.0) if index == 4 else interval
            for index, interval in enumerate(proposal.model_full_role_intervals_px)
        )
        fit_intervals = tuple(
            FiniteInterval(900.0, 901.0) if index == 4 else interval
            for index, interval in enumerate(proposal.model_role_intervals_px)
        )
        far_model = self._unsafe_fit_replace(
            proposal,
            model_role_intervals_px=fit_intervals,
            model_full_role_intervals_px=full_intervals,
        )
        # A role-4 observation remains an original validation fact.  Its old
        # full interval is compared against the new model envelope, even when
        # a center-only comparison would have hidden the disjoint interval.
        with patch(
            "x5crop.detection.photo_geometry.template_intrinsic_review_refit._phase_candidates._fit_seed",
            return_value=_BoundFit(far_model, True),
        ):
            result = build_intrinsic_phase_refit(phase_input, original)
        self.assertIsNone(result.failure)
        assert result.diagnostic is not None
        self.assertEqual(
            tuple(fact.role_index for fact in result.diagnostic.validation_conflicts),
            (4,),
        )
        with self.assertRaises(ValueError):
            replace(result.diagnostic, validation_conflicts=())

    def test_receipt_and_diagnostic_tampering_are_rejected(self):
        phase_input, original = self._fixture()
        result = build_intrinsic_phase_refit(phase_input, original)
        self.assertIsNone(result.failure)
        with self.assertRaises(ValueError):
            replace(result.work, fit_seed_call_count=2)
        assert result.diagnostic is not None
        with self.assertRaises(ValueError):
            replace(
                result.diagnostic,
                retained_intrinsic_bindings=(
                    (0, ObservationId("sequence:0")),
                ),
            )

        rehydrated = IntrinsicPhaseReviewDiagnostic(
            original_diagnostic=result.diagnostic.original_diagnostic,
            fit=result.diagnostic.fit,
            residual_compatible=result.diagnostic.residual_compatible,
            retained_intrinsic_bindings=result.diagnostic.retained_intrinsic_bindings,
            validation_only_facts=result.diagnostic.validation_only_facts,
            validation_conflicts=result.diagnostic.validation_conflicts,
        )
        self.assertEqual(rehydrated, result.diagnostic)

    def test_no_validation_only_bindings_stops_without_refit(self):
        phase_input, original = self._fixture(
            contradicted=False,
            all_intrinsic=True,
        )
        with patch(
            "x5crop.detection.photo_geometry.template_intrinsic_review_refit._phase_candidates._fit_seed"
        ) as fitter:
            result = build_intrinsic_phase_refit(phase_input, original)
        self.assertEqual(
            result.failure.kind,
            IntrinsicPhaseRefitFailureKind.NO_VALIDATION_ONLY_BINDINGS,
        )
        self.assertEqual(result.work.fit_seed_call_count, 0)
        fitter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
