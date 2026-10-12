from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import unittest

from tools.regression.report_validation import (
    _cross_review_support_domains_from_phase_report,
    _cross_support_domains_from_phase_report,
)
from tools.tests.template_test_support import (
    cross_binding,
    cross_template,
    placement_direction,
    placement_sequence,
    placement_template,
)
from tools.tests.cross_fixture_support import aspect_input
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossFailureKind,
    CrossFitStatus,
    CrossLongitudinalProjectionFailureKind,
    CrossRetainedProposalBasis,
    TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_phase_model import PhaseFitStatus
from x5crop.detection.photo_geometry.template_placement import review_cross_support_domain_groups_px
from x5crop.report.read_models import typed_read_model


DOMAINS = (FiniteInterval(100, 200), FiniteInterval(300, 400), FiniteInterval(500, 600))


def fixture() -> TemplateCrossInput:
    def binding(role, name, coordinate, traces, **kwargs):
        return cross_binding(role, name, coordinate, traces=traces,
                             source_spanning=False, **kwargs)

    return aspect_input(
        template=cross_template(count=3), fixed_height_px=FiniteInterval(236, 244),
        source_direction=placement_direction(),
        review_support_domain_groups_px=(DOMAINS,),
        top_bindings=(
            binding(BoundaryRole.TOP, "local-top", 100, (0, 10), independent_regions=2),
            binding(BoundaryRole.TOP, "complete-top", 110, (110, 310, 510), role_authorized=False),
        ),
        bottom_bindings=(
            binding(BoundaryRole.BOTTOM, "local-bottom", 342, (90, 100), independent_regions=2),
            binding(BoundaryRole.BOTTOM, "complete-bottom", 354, (120, 320, 520), role_authorized=False),
        ),
    )


class CrossReviewContextContractTest(unittest.TestCase):
    def test_complete_context_changes_review_geometry_without_projection_permission(self):
        inputs = fixture()
        old = fit_template_cross(replace(inputs, review_support_domain_groups_px=()))
        result = fit_template_cross(inputs)
        self.assertEqual(old.best.direct_provenance_ids, (ObservationId("observation:local-top"),))
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(result.failure_kind, old.failure_kind)
        self.assertEqual(result.failure_kind, CrossFailureKind.PAIR_SUPPORT_UNAVAILABLE)
        self.assertIsNone(result.winner_basis)
        self.assertEqual(result.retained_proposal_basis,
                         CrossRetainedProposalBasis.CALIBRATED_HEIGHT_FROM_COMPLETE_REVIEW_SUPPORT)
        for fit, name in ((result.best, "complete-top"), (result.runner_up, "complete-bottom")):
            self.assertEqual(fit.direct_provenance_ids, (ObservationId(f"observation:{name}"),))
            self.assertFalse(fit.direct_bindings[0].role_authorized)
            self.assertEqual(fit.longitudinal_projection_authority.state, EvidenceState.UNAVAILABLE)
            self.assertEqual(fit.longitudinal_projection_authority.failure_kind,
                             CrossLongitudinalProjectionFailureKind.TEMPLATE_DOMAINS_UNAVAILABLE)
        self.assertEqual(result.receipt.compatible_pair_count, old.receipt.compatible_pair_count)
        self.assertEqual(result.receipt.evaluated_fit_count, old.receipt.evaluated_fit_count)

    def test_missing_one_frame_in_either_candidate_cannot_activate_context(self):
        inputs = fixture()
        original = fit_template_cross(replace(inputs, review_support_domain_groups_px=()))
        for context in (
            (DOMAINS, (DOMAINS[0], DOMAINS[1], FiniteInterval(700, 800))),
            ((DOMAINS[0], FiniteInterval(350, 450), DOMAINS[2]),),
        ):
            with self.subTest(context=context):
                self.assertEqual(fit_template_cross(replace(inputs, review_support_domain_groups_px=context)), original)

    def test_context_does_not_union_different_bindings(self):
        inputs = fixture()
        split = replace(inputs,
            top_bindings=(inputs.top_bindings[0], replace(inputs.top_bindings[1], trace_coordinates_px=(110, 310),
                trace_position_intervals_px=())),
            bottom_bindings=(inputs.bottom_bindings[0], replace(inputs.bottom_bindings[1], trace_coordinates_px=(510,),
                trace_position_intervals_px=())))
        self.assertEqual(fit_template_cross(split), fit_template_cross(replace(split, review_support_domain_groups_px=())))

    def test_complete_authorized_role_wins_tie_even_with_two_original_regions(self):
        inputs = fixture()
        authorized = replace(inputs.top_bindings[1], run_id="authorized-complete",
            observation_id=ObservationId("observation:authorized-complete"), role_authorized=True,
            independent_support_region_count=2, coordinate_interval_px=FiniteInterval.exact(120),
            fit_interval_px=FiniteInterval.exact(120), full_interval_px=FiniteInterval.exact(120),
            trace_position_intervals_px=())
        result = fit_template_cross(replace(inputs, top_bindings=(*inputs.top_bindings, authorized)))
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(result.best.direct_provenance_ids, (authorized.observation_id,))
        self.assertTrue(result.best.direct_bindings[0].role_authorized)
        self.assertFalse(result.runner_up.direct_bindings[0].role_authorized)
        self.assertEqual(result.retained_proposal_basis,
                         CrossRetainedProposalBasis.CALIBRATED_HEIGHT_FROM_COMPLETE_REVIEW_SUPPORT)

    def test_missing_direction_and_enclosing_binding_preserve_original_proposal(self):
        inputs = fixture()
        for change in (
            dict(canonical_direction_degrees=None, fit_direction_interval_degrees=None,
                 full_direction_interval_degrees=None, observed_direction_interval_degrees=None),
            dict(enclosing_pair_id="support:complete"),
            dict(independent_support_region_count=2),
        ):
            changed = replace(inputs, source_direction=None,
                top_bindings=(inputs.top_bindings[0], replace(inputs.top_bindings[1], **change)),
                bottom_bindings=(inputs.bottom_bindings[0], replace(inputs.bottom_bindings[1], **change)))
            with self.subTest(change=change):
                self.assertEqual(fit_template_cross(changed),
                                 fit_template_cross(replace(changed, review_support_domain_groups_px=())))

    def test_original_evaluated_fit_bound_still_blocks_retention(self):
        result = fit_template_cross(replace(fixture(), maximum_evaluated_fits=1))
        self.assertEqual(result.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertEqual(result.failure_kind, CrossFailureKind.EVALUATED_FIT_BOUND_EXCEEDED)
        self.assertIsNone(result.best)
        self.assertIsNone(result.retained_proposal_basis)

    def test_complete_review_hypothesis_does_not_replace_a_direct_pair(self):
        inputs = fixture()
        for source_spanning in (False, True):
            top = cross_binding(BoundaryRole.TOP, "pair-top", 100, traces=(0, 10, 20),
                                source_spanning=source_spanning)
            bottom = cross_binding(BoundaryRole.BOTTOM, "pair-bottom", 340, traces=(0, 10, 20),
                                   source_spanning=source_spanning)
            changed = replace(inputs, top_bindings=(top, inputs.top_bindings[1]),
                              bottom_bindings=(bottom, inputs.bottom_bindings[1]))
            with self.subTest(source_spanning=source_spanning):
                result = fit_template_cross(changed)
                self.assertEqual(result, fit_template_cross(replace(changed, review_support_domain_groups_px=())))
                self.assertTrue(result.best.direct_pair)
                if source_spanning:
                    self.assertEqual(result.status, CrossFitStatus.RESOLVED)

    def test_unresolved_context_replay_is_independent_and_all_or_nothing(self):
        fit = placement_sequence(placement_template(2), missing=(1, 2))
        phase = SimpleNamespace(best=fit, runner_up=None, status=PhaseFitStatus.UNRESOLVED)
        groups = review_cross_support_domain_groups_px(phase)
        record = dict(best=typed_read_model(fit), runner_up=None, status="unresolved",
                      failure_kind="adjacency_topology_unresolved")
        self.assertEqual(_cross_review_support_domains_from_phase_report(record), typed_read_model(groups))
        self.assertEqual(_cross_support_domains_from_phase_report(record), [])
        record["runner_up"] = deepcopy(record["best"])
        record["runner_up"]["role_bindings"][3]["canonical_position_px"] = 205.0
        self.assertEqual(_cross_review_support_domains_from_phase_report(record), [])
        self.assertEqual(review_cross_support_domain_groups_px(replace_phase(phase, status=PhaseFitStatus.BOUND_EXCEEDED)), ())
        for domains in ((DOMAINS,) * 3, (DOMAINS[:2],), ((DOMAINS[1], DOMAINS[0], DOMAINS[2]),)):
            with self.subTest(domains=domains), self.assertRaisesRegex(ValueError, "review support domains"):
                replace(fixture(), review_support_domain_groups_px=domains)


def replace_phase(phase, **values):
    return SimpleNamespace(**{**vars(phase), **values})
