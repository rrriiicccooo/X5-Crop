from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest

from tools.regression.report_validation import (
    _cross_support_domains_from_phase_report,
    _validate_cross_longitudinal_projection_authority,
    _validate_cross_longitudinal_projection_scope,
)
from tools.tests.template_test_support import (
    cross_binding,
    cross_template,
    placement_sequence,
    placement_template,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_cross_candidates import (
    _direct_candidate,
    _single_candidate,
)
from x5crop.detection.photo_geometry.template_cross_longitudinal import (
    assess_cross_longitudinal_projection,
    covers_all_template_domains,
)
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossHeightInferenceBasis,
    CrossFailureKind,
    CrossLongitudinalProjectionBasis as Basis,
    CrossLongitudinalProjectionFailureKind as Failure,
    CrossPairSupportMode,
    TemplateCrossInput,
)
from x5crop.report.read_models import typed_read_model


def domains(*starts: int) -> tuple[FiniteInterval, ...]:
    return tuple(FiniteInterval(float(start), float(start + 5)) for start in starts)


def assess(groups, traces, **kwargs):
    return assess_cross_longitudinal_projection(
        supporting_observation_ids=(ObservationId("cross:direct"),),
        trace_coordinates_px=traces,
        domain_groups=groups,
        source_spanning_continuous=False,
        **kwargs,
    )


class CrossLongitudinalContractTest(unittest.TestCase):
    def test_report_adapter_binds_each_fit_and_fails_all_groups_together(self) -> None:
        from x5crop.detection.photo_geometry.template_placement import (
            resolved_cross_support_domains_px,
        )

        fit = placement_sequence(placement_template(2), missing=(1, 2))
        best = typed_read_model(fit)
        runner = deepcopy(best)
        runner["role_bindings"][0]["canonical_position_px"] += 10.0
        phase = {
            "best": best,
            "runner_up": runner,
            "status": "ambiguous",
            "failure_kind": "discrete_phase_ambiguous",
        }
        groups = _cross_support_domains_from_phase_report(phase)
        self.assertEqual(groups[0], typed_read_model(resolved_cross_support_domains_px(fit)))
        self.assertEqual(groups[1], [
            {"minimum": 110.0, "maximum": 210.0},
            {"minimum": 220.0, "maximum": 320.0},
        ])
        self.assertNotEqual(groups[0], groups[1])
        self.assertEqual(_cross_support_domains_from_phase_report({
            **phase, "status": "resolved", "failure_kind": None,
        }), groups[:1])
        self.assertEqual(_cross_support_domains_from_phase_report({
            **phase, "status": "unresolved", "failure_kind": "fixed_template_mismatch",
        }), [])
        self.assertEqual(_cross_support_domains_from_phase_report({
            **phase, "runner_up": None,
        }), [])
        runner["role_bindings"][3]["canonical_position_px"] = 205.0
        self.assertEqual(_cross_support_domains_from_phase_report(phase), [])
        del runner["model_role_positions_px"]
        with self.assertRaisesRegex(ValueError, "candidate report is incomplete"):
            _cross_support_domains_from_phase_report(phase)

    def test_domain_compiler_preserves_native_inferred_and_overlap_geometry(self) -> None:
        from x5crop.detection.photo_geometry.template_placement import (
            compile_cross_support_domains_px,
        )

        def compile_domains(direction, model, direct, overlaps=()):
            return compile_cross_support_domains_px(
                count=2,
                direction=direction,
                frame_width_px=FiniteInterval(98.0, 102.0),
                canonical_frame_width_px=100.0,
                model_role_positions_px=model,
                direct_role_positions_px=direct,
                overlap_signed_gaps_px=overlaps,
            )

        self.assertEqual(
            compile_domains(1, (0.0, 100.0, 120.0, 220.0), (10.0, None, None, 240.0)),
            (FiniteInterval(10.0, 110.0), FiniteInterval(140.0, 240.0)),
        )
        self.assertEqual(
            compile_domains(-1, (240.0, 140.0, 120.0, 20.0), (230.0, None, None, 0.0)),
            (FiniteInterval(0.0, 100.0), FiniteInterval(130.0, 230.0)),
        )
        self.assertEqual(
            compile_domains(1, (0.0, 100.0, 120.0, 220.0), (0.0, None, None, None)),
            (FiniteInterval(0.0, 100.0), FiniteInterval(120.0, 220.0)),
        )
        with self.assertRaisesRegex(ValueError, "candidate coordinates"):
            compile_domains(1, (0.0, 100.0, 120.0, 220.0), (None,) * 4)
        for direction, positions in (
            (1, (0.0, 100.0, 90.0, 190.0)),
            (-1, (190.0, 90.0, 100.0, 0.0)),
        ):
            with self.subTest(direction=direction):
                self.assertEqual(
                    compile_domains(direction, positions, positions, ((1, -10.0),)),
                    (FiniteInterval(0.0, 95.0), FiniteInterval(95.0, 190.0)),
                )
                with self.assertRaisesRegex(ValueError, "explicit OverlapRelation"):
                    compile_domains(direction, positions, positions)
                with self.assertRaisesRegex(ValueError, "signed gap"):
                    compile_domains(direction, positions, positions, ((1, -9.0),))

    def test_candidates_must_not_union_their_missing_endpoints(self) -> None:
        groups = (domains(20, 40, 60, 80), domains(0, 20, 40, 60))
        authority = assess(groups, (22, 42, 62))
        self.assertEqual(authority.supported_domain_ordinals_by_candidate,
                         ((1, 2, 3), (2, 3, 4)))
        self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(authority.failure_kind, Failure.TEMPLATE_EXTENT_UNBRACKETED)
        self.assertFalse(authority.template_extent_bracketed)
        self.assertFalse(covers_all_template_domains((22, 42, 62), groups))
        _validate_cross_longitudinal_projection_authority(typed_read_model(authority))

    def test_each_bracket_can_use_different_middle_domains(self) -> None:
        groups = (domains(0, 20, 40, 60), domains(0, 40, 50, 60))
        authority = assess(groups, (2, 42, 62))
        self.assertEqual(authority.supported_domain_ordinals_by_candidate,
                         ((1, 3, 4), (1, 2, 4)))
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(authority.basis, Basis.BRACKETED_TEMPLATE_EXTENT)
        self.assertEqual(authority.template_domain_count, 4)
        self.assertEqual(authority.required_independent_domain_count, 3)
        _validate_cross_longitudinal_projection_authority(typed_read_model(authority))
        complete = assess(groups, (2, 42, 62), require_complete_template_domains=True)
        self.assertEqual(complete.failure_kind,
                         Failure.COMPLETE_TEMPLATE_DOMAIN_SUPPORT_UNAVAILABLE)

    def test_complete_support_is_per_group_not_interval_intersection(self) -> None:
        groups = (domains(0, 20, 40), domains(8, 28, 48))
        traces = (2, 10, 22, 30, 42, 50)
        self.assertTrue(covers_all_template_domains(traces, groups))
        authority = assess(groups, traces, require_complete_template_domains=True)
        self.assertEqual(authority.basis, Basis.COMPLETE_TEMPLATE_DOMAINS)
        self.assertEqual(authority.supported_domain_ordinals_by_candidate,
                         ((1, 2, 3), (1, 2, 3)))
        shifted = assess((groups[0], domains(9, 29, 49)), traces)
        self.assertNotEqual(authority.authority_id, shifted.authority_id)

    def test_groups_cannot_add_independent_votes_or_hide_invalid_domains(self) -> None:
        good = domains(0, 20, 40)
        invalid_groups = (
            (good,) * 3,
            (good, ()),
            (good, domains(0, 20)),
            (good, domains(20, 0, 40)),
            (good, domains(0, 3, 40)),
        )
        for groups in invalid_groups:
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                TemplateCrossInput(template=cross_template(count=3),
                                   longitudinal_support_domain_groups_px=groups)
        authority = assess((domains(0, 20, 40), domains(8, 28, 48)), (2, 10, 22, 30))
        self.assertEqual(authority.failure_kind,
                         Failure.INDEPENDENT_DOMAIN_SUPPORT_UNAVAILABLE)
        self.assertEqual(authority.required_independent_domain_count, 3)

    def test_shared_pair_cannot_count_candidate_domains_twice(self) -> None:
        groups = (domains(0, 20, 40, 60), domains(1, 21, 41, 61))
        top = cross_binding(BoundaryRole.TOP, "top", 100.0,
                            traces=(2, 22, 42), source_spanning=False)
        bottom = cross_binding(BoundaryRole.BOTTOM, "bottom", 340.0,
                               traces=(2, 22, 62), source_spanning=False)
        candidate, failure = _direct_candidate(
            top, bottom, fixed_height=FiniteInterval.exact(240.0),
            canonical_height_px=240.0, minimum_shared_trace_support=2,
            longitudinal_support_domain_groups_px=groups,
        )
        self.assertIsNone(failure)
        assert candidate is not None
        self.assertEqual(candidate.authority_trace_coordinates_px, (2, 22))
        self.assertEqual(candidate.longitudinal_projection_authority.state,
                         EvidenceState.UNAVAILABLE)

    def test_shared_pair_can_close_different_conditions_in_each_candidate(self) -> None:
        groups = (domains(0, 20, 40, 60), domains(0, 10, 20, 60))
        top = cross_binding(BoundaryRole.TOP, "top", 100.0,
                            traces=(2, 12, 22, 42, 62), source_spanning=False)
        bottom = cross_binding(BoundaryRole.BOTTOM, "bottom", 340.0,
                               traces=(2, 22, 42), source_spanning=False)
        candidate, failure = _direct_candidate(
            top, bottom, fixed_height=FiniteInterval.exact(240.0),
            canonical_height_px=240.0, minimum_shared_trace_support=2,
            longitudinal_support_domain_groups_px=groups,
        )
        self.assertIsNone(failure)
        assert candidate is not None
        self.assertEqual(candidate.authority_trace_coordinates_px, top.trace_coordinates_px)
        self.assertEqual(candidate.longitudinal_projection_authority.basis,
                         Basis.COMPLETE_TEMPLATE_DOMAINS)

    def test_report_requires_all_groups_and_current_fields(self) -> None:
        authority = assess((domains(0, 20, 40), domains(8, 28, 48)),
                           (2, 10, 22, 30, 42, 50))
        record = typed_read_model(authority)
        _validate_cross_longitudinal_projection_authority(record)
        _validate_cross_longitudinal_projection_scope(
            record, "ambiguous", "discrete_phase_ambiguous"
        )
        truncated = deepcopy(record)
        for field in ("candidate_support_domains_px", "supported_domain_ordinals_by_candidate"):
            truncated[field] = truncated[field][:1]
        _validate_cross_longitudinal_projection_authority(truncated)
        with self.assertRaisesRegex(ValueError, "retained phase scope"):
            _validate_cross_longitudinal_projection_scope(
                truncated, "ambiguous", "discrete_phase_ambiguous"
            )
        _validate_cross_longitudinal_projection_scope(truncated, "resolved", None)
        with self.assertRaisesRegex(ValueError, "retained phase scope"):
            _validate_cross_longitudinal_projection_scope(record, "resolved", None)
        for field, value in (
            ("supported_domain_ordinals_by_candidate", [[1, 2, 3], [1, 2]]),
            ("candidate_support_domains_px", record["candidate_support_domains_px"][:1]),
            ("required_independent_domain_count", 6),
        ):
            invalid = deepcopy(record)
            invalid[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                _validate_cross_longitudinal_projection_authority(invalid)
        with self.assertRaises(ValueError):
            replace(authority, supported_domain_ordinals_by_candidate=((1, 2, 3), (1, 2)))
        legacy = deepcopy(record)
        legacy["supported_domain_ordinals"] = [1, 2, 3]
        with self.assertRaises(ValueError):
            _validate_cross_longitudinal_projection_authority(legacy)

    def test_source_spanning_side_cannot_cover_missing_opposite_for_runner(self) -> None:
        groups = (domains(0, 20, 40), domains(8, 28, 48))
        top = cross_binding(
            BoundaryRole.TOP, "spanning-top", 100.0,
            traces=(2, 10, 22, 30, 42, 50), source_spanning=True,
        )
        bottom = cross_binding(
            BoundaryRole.BOTTOM, "local-bottom", 340.0,
            traces=(2, 22, 42), source_spanning=False,
        )
        candidate, failure = _direct_candidate(
            top, bottom, fixed_height=FiniteInterval.exact(240.0),
            canonical_height_px=240.0, minimum_shared_trace_support=2,
            longitudinal_support_domain_groups_px=groups,
        )
        self.assertIsNone(failure)
        assert candidate is not None
        authority = candidate.longitudinal_projection_authority
        self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)
        self.assertNotEqual(authority.basis, Basis.SOURCE_SPANNING_CONTINUOUS)
        self.assertEqual(authority.supported_domain_ordinals_by_candidate,
                         ((1, 2, 3), ()))

    def test_two_two_frame_candidates_do_not_make_three_independent_regions(self) -> None:
        groups = (domains(0, 20), domains(8, 28))
        top = cross_binding(
            BoundaryRole.TOP, "two-region-top", 100.0,
            traces=(2, 10, 22, 30), source_spanning=False, independent_regions=2,
        )
        self.assertTrue(covers_all_template_domains(top.trace_coordinates_px, groups))
        candidate = _single_candidate(
            top, fixed_height=FiniteInterval.exact(240.0),
            canonical_height_px=240.0,
            height_inference_basis=CrossHeightInferenceBasis.CALIBRATED_FORMAT_HEIGHT,
            longitudinal_support_domain_groups_px=groups,
        )
        self.assertIsNone(candidate)

    def test_complementary_pair_requires_complete_union_in_each_candidate(self) -> None:
        groups = (domains(0, 20, 40, 60), domains(8, 28, 48, 68))
        top = cross_binding(
            BoundaryRole.TOP, "complementary-top", 100.0,
            traces=(2, 10, 22, 30), source_spanning=False, independent_regions=2,
        )
        bottom = cross_binding(
            BoundaryRole.BOTTOM, "complementary-bottom", 340.0,
            traces=(42, 50, 62, 70), source_spanning=False, independent_regions=2,
        )
        for traces, accepted in (((42, 50, 62, 70), True), ((42, 50, 62), False)):
            with self.subTest(traces=traces):
                candidate, failure = _direct_candidate(
                    top, replace(bottom, trace_coordinates_px=traces),
                    fixed_height=FiniteInterval.exact(240.0),
                    canonical_height_px=240.0, minimum_shared_trace_support=2,
                    longitudinal_support_domain_groups_px=groups,
                )
                if accepted:
                    self.assertIsNone(failure)
                    assert candidate is not None
                    self.assertEqual(candidate.pair_support_mode,
                                     CrossPairSupportMode.COMPLEMENTARY_DOMAINS)
                    self.assertEqual(candidate.support_trace_coordinates_px, ())
                    self.assertEqual(candidate.longitudinal_projection_authority.basis,
                                     Basis.COMPLETE_TEMPLATE_DOMAINS)
                else:
                    self.assertIsNone(candidate)
                    self.assertEqual(failure, CrossFailureKind.PAIR_SUPPORT_UNAVAILABLE)
