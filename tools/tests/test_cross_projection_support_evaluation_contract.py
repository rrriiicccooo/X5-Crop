"""Cross projection support checks remain short-circuited without changing authority."""

from dataclasses import replace
import random
from unittest.mock import patch
import unittest

from tools.tests.template_test_support import cross_binding
from x5crop.domain import EvidenceState, FiniteInterval
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_cross_candidates import _direct_candidate
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossLongitudinalProjectionBasis,
    CrossRoleBinding,
)
from x5crop.detection.photo_geometry.template_cross_longitudinal import CrossBindingDomainCoverage
import x5crop.detection.photo_geometry.template_cross_longitudinal as longitudinal_owner
import x5crop.detection.photo_geometry.template_cross_candidates as candidates_owner


def support_domains() -> tuple[tuple[FiniteInterval, ...], ...]:
    return ((
        FiniteInterval(0.0, 20.0),
        FiniteInterval(40.0, 60.0),
        FiniteInterval(80.0, 100.0),
    ),)


def direct_pair(*, top_spanning: bool, bottom_spanning: bool,
                top_traces: tuple[int, ...] = (0, 40, 80),
                bottom_traces: tuple[int, ...] = (0, 40, 80)):
    top = cross_binding(
        BoundaryRole.TOP,
        "top",
        100.0,
        traces=top_traces,
        source_spanning=top_spanning,
    )
    bottom = cross_binding(
        BoundaryRole.BOTTOM,
        "bottom",
        340.0,
        traces=bottom_traces,
        source_spanning=bottom_spanning,
    )
    assert isinstance(top, CrossRoleBinding)
    assert isinstance(bottom, CrossRoleBinding)
    return top, bottom


class CrossProjectionSupportEvaluationContractTest(unittest.TestCase):
    def test_prepared_binding_coverage_preserves_each_complete_pair_proof(self):
        rng = random.Random(6215)
        groups = (support_domains()[0], (
            FiniteInterval(0.5, 20.5), FiniteInterval(40.5, 60.5), FiniteInterval(80.5, 100.5)))
        for _ in range(160):
            top, bottom = direct_pair(
                top_spanning=rng.choice((False, True)), bottom_spanning=rng.choice((False, True)),
                top_traces=tuple(sorted(rng.sample(range(0, 101, 10), rng.randrange(2, 12)))),
                bottom_traces=tuple(sorted(rng.sample(range(0, 101, 10), rng.randrange(2, 12)))))
            coverage = CrossBindingDomainCoverage((top, bottom), groups)
            inputs = dict(fixed_height=FiniteInterval.exact(240.0), canonical_height_px=240.0,
                          minimum_shared_trace_support=2, longitudinal_support_domain_groups_px=groups)
            expected = _direct_candidate(top, bottom, **inputs)
            with self.subTest(top=top.trace_coordinates_px, bottom=bottom.trace_coordinates_px):
                self.assertEqual(_direct_candidate(top, bottom, **inputs,
                    binding_domain_coverage=coverage), expected)
                # Pair direction and H remain live inputs after neutral coverage has been prepared.
                self.assertEqual(_direct_candidate(top, bottom, **{**inputs,
                    "fixed_height": FiniteInterval.exact(220.0)}, binding_domain_coverage=coverage),
                    _direct_candidate(top, bottom, **{**inputs, "fixed_height": FiniteInterval.exact(220.0)}))

    def test_coverage_reuse_keeps_original_bindings_and_each_domain_group(self):
        top, bottom = direct_pair(top_spanning=True, bottom_spanning=False,
                                  bottom_traces=(0, 40))
        groups = support_domains()
        coverage = CrossBindingDomainCoverage((top, bottom), groups)
        with patch.object(longitudinal_owner, "_ordered_finite_traces",
                          wraps=longitudinal_owner._ordered_finite_traces) as ordered:
            for _ in range(8):
                self.assertFalse(coverage.covers_all(bottom))
                self.assertTrue(coverage.covers_all(top))
            self.assertEqual(ordered.call_count, 2)
        with self.assertRaisesRegex(ValueError, "different bindings"):
            coverage.covers_all(replace(bottom, trace_coordinates_px=(0, 40, 80)))
        with self.assertRaisesRegex(ValueError, "different template domains"):
            _direct_candidate(top, bottom, fixed_height=FiniteInterval.exact(240.0),
                canonical_height_px=240.0, minimum_shared_trace_support=2,
                longitudinal_support_domain_groups_px=((FiniteInterval(0.0, 100.0),),),
                binding_domain_coverage=coverage)

    def test_covers_all_domains_is_checked_only_when_short_circuit_needs_it(self):
        expected = {
            (False, False): (0, CrossLongitudinalProjectionBasis.COMPLETE_TEMPLATE_DOMAINS),
            (True, False): (1, CrossLongitudinalProjectionBasis.SOURCE_SPANNING_CONTINUOUS),
            (False, True): (1, CrossLongitudinalProjectionBasis.SOURCE_SPANNING_CONTINUOUS),
            (True, True): (0, CrossLongitudinalProjectionBasis.SOURCE_SPANNING_CONTINUOUS),
        }
        for (top_spanning, bottom_spanning), (expected_calls, expected_basis) in expected.items():
            with self.subTest(top_spanning=top_spanning, bottom_spanning=bottom_spanning):
                top, bottom = direct_pair(
                    top_spanning=top_spanning,
                    bottom_spanning=bottom_spanning,
                )
                with patch.object(
                    candidates_owner,
                    "covers_all_template_domains",
                    wraps=candidates_owner.covers_all_template_domains,
                ) as covers_all:
                    candidate, failure = _direct_candidate(
                        top,
                        bottom,
                        fixed_height=FiniteInterval.exact(240.0),
                        canonical_height_px=240.0,
                        minimum_shared_trace_support=2,
                        longitudinal_support_domain_groups_px=support_domains(),
                    )
                self.assertIsNone(failure)
                assert candidate is not None
                self.assertEqual(covers_all.call_count, expected_calls)
                authority = candidate.longitudinal_projection_authority
                self.assertEqual(authority.state, EvidenceState.SUPPORTED)
                self.assertEqual(authority.basis, expected_basis)
                self.assertEqual(authority.supported_domain_ordinals_by_candidate, ((1, 2, 3),))
                expected_authority = candidates_owner.assess_cross_longitudinal_projection(
                    supporting_observation_ids=(top.observation_id, bottom.observation_id),
                    trace_coordinates_px=candidate.authority_trace_coordinates_px,
                    domain_groups=support_domains(),
                    source_spanning_continuous=(
                        top.source_spanning_continuous
                        and bottom.source_spanning_continuous
                    )
                    or (
                        top.source_spanning_continuous
                        and candidates_owner.covers_all_template_domains(
                            bottom.trace_coordinates_px, support_domains()
                        )
                    )
                    or (
                        bottom.source_spanning_continuous
                        and candidates_owner.covers_all_template_domains(
                            top.trace_coordinates_px, support_domains()
                        )
                    ),
                )
                self.assertEqual(authority, expected_authority)

    def test_single_spanning_side_without_full_opposite_coverage_stays_non_spanning(self):
        # The spanning top has all three domains, while the non-spanning
        # bottom is missing the third. The pair still has enough shared
        # traces for a real direct candidate, but cannot upgrade projection
        # authority to the source-spanning basis.
        top, bottom = direct_pair(
            top_spanning=True,
            bottom_spanning=False,
            top_traces=(0, 40, 80),
            bottom_traces=(0, 40),
        )
        with patch.object(
            candidates_owner,
            "assess_cross_longitudinal_projection",
            wraps=candidates_owner.assess_cross_longitudinal_projection,
        ) as assess_projection:
            candidate, failure = _direct_candidate(
                top,
                bottom,
                fixed_height=FiniteInterval.exact(240.0),
                canonical_height_px=240.0,
                minimum_shared_trace_support=2,
                longitudinal_support_domain_groups_px=support_domains(),
            )
        self.assertIsNone(failure)
        assert candidate is not None
        self.assertEqual(assess_projection.call_count, 1)
        self.assertFalse(
            assess_projection.call_args.kwargs["source_spanning_continuous"]
        )
        authority = candidate.longitudinal_projection_authority
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            authority.basis,
            CrossLongitudinalProjectionBasis.COMPLETE_TEMPLATE_DOMAINS,
        )
        self.assertEqual(authority.supported_domain_ordinals_by_candidate, ((1, 2, 3),))


if __name__ == "__main__":
    unittest.main()
