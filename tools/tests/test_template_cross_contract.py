from __future__ import annotations

from dataclasses import replace
import unittest
from types import SimpleNamespace

from tools.tests.template_test_support import (
    cross_binding as binding,
    cross_template as template,
)
from x5crop.domain import FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossEvidence,
    CrossFitStatus,
    CrossRoleBinding,
    TemplateCrossInput,
)
from x5crop.detection.photo_geometry.output_model import OutputBoundaryUse
from x5crop.detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC
from x5crop.detection.photo_geometry.trace_support import (
    source_spanning_continuous_trace_support,
)
class TemplateCrossContractTest(unittest.TestCase):
    def test_source_spanning_reaches_both_registered_domain_ends(self) -> None:
        queried = tuple(range(0, 101, 10))
        self.assertTrue(
            source_spanning_continuous_trace_support(
                queried,
                tuple(range(10, 91, 10)),
                spec=PHOTO_BOUNDARY_MEASUREMENT_SPEC,
            )
        )
        self.assertFalse(
            source_spanning_continuous_trace_support(
                queried,
                tuple(range(30, 71, 10)),
                spec=PHOTO_BOUNDARY_MEASUREMENT_SPEC,
            )
        )

    def test_measurement_registration_transfers_support_provenance(self) -> None:
        run = SimpleNamespace(
            role_hint=BoundaryRole.TOP,
            run_id="run:registered",
            trace_coordinates_px=(0, 50, 100),
            support_fraction=0.9,
            continuous_support_fraction=0.8,
        )
        observation = SimpleNamespace(
            role=BoundaryRole.TOP,
            observation_id=ObservationId("observation:registered"),
            coordinate_interval_px=FiniteInterval(99.0, 101.0),
            fit_residual_px=0.4,
            canonical_direction_degrees=0.1,
            fit_angle_interval_degrees=FiniteInterval(-0.1, 0.2),
            full_direction_interval_degrees=FiniteInterval(-0.2, 0.3),
            independent_support_region_count=2,
            source_spanning_continuous=True,
        )
        registered = CrossRoleBinding.from_measurement(
            run,
            observation,
            lane_reference_trace_px=0.0,
        )
        self.assertEqual(registered.independent_support_region_count, 2)
        self.assertTrue(registered.source_spanning_continuous)

    def test_unique_direct_pair_wins(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                top_bindings=(binding(BoundaryRole.TOP, "top", 100.0),),
                bottom_bindings=(binding(BoundaryRole.BOTTOM, "bottom", 340.0),),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNotNone(result.best)
        assert result.best is not None
        self.assertTrue(result.best.direct_pair)
        self.assertEqual(result.best.boundary_use, OutputBoundaryUse.APERTURE_PAIR)
        self.assertEqual(result.best.direct_observation_ids, (
            ObservationId("observation:top"),
            ObservationId("observation:bottom"),
        ))
        self.assertEqual(result.receipt.compatible_pair_count, 1)

    def test_physical_direction_intervals_close_disjoint_local_fits(self) -> None:
        top = binding(
            BoundaryRole.TOP,
            "budget-top",
            100.0,
            angle=-0.15,
            angle_interval=FiniteInterval(-0.18, -0.12),
            full_angle_interval=FiniteInterval(-0.3, 0.1),
        )
        bottom = binding(
            BoundaryRole.BOTTOM,
            "budget-bottom",
            340.0,
            angle=0.05,
            angle_interval=FiniteInterval(0.02, 0.08),
            full_angle_interval=FiniteInterval(-0.2, 0.2),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(top,),
                bottom_bindings=(bottom,),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        assert result.best.selected_direction is not None
        self.assertEqual(
            result.best.selected_direction.full_angle_interval_degrees,
            FiniteInterval(-0.3, 0.2),
        )

    def test_spanning_direction_safety_contains_canonical_angle(self) -> None:
        top = binding(
            BoundaryRole.TOP,
            "spanning-direction-top",
            100.0,
            angle=0.05,
            angle_interval=FiniteInterval(-0.05, 0.05),
            full_angle_interval=FiniteInterval(-0.05, 0.05),
        )
        bottom = binding(
            BoundaryRole.BOTTOM,
            "local-direction-bottom",
            340.0,
            angle=0.16,
            angle_interval=FiniteInterval(-0.05, 0.2),
            full_angle_interval=FiniteInterval(-0.2, 0.2),
            source_spanning=False,
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(top,),
                bottom_bindings=(bottom,),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        assert result.best.selected_direction is not None
        self.assertEqual(
            result.best.selected_direction.full_angle_interval_degrees,
            FiniteInterval(-0.05, 0.05),
        )
        self.assertEqual(
            result.best.selected_direction.canonical_angle_degrees,
            0.05,
        )

    def test_two_region_pair_requires_both_outside_role_authorities(self) -> None:
        top = binding(
            BoundaryRole.TOP,
            "role-top",
            100.0,
            traces=(0, 50),
            independent_regions=2,
            source_spanning=False,
        )
        wrong_bottom = binding(
            BoundaryRole.BOTTOM,
            "wrong-role-bottom",
            340.0,
            traces=(0, 50),
            independent_regions=2,
            source_spanning=False,
            role_authorized=False,
        )
        rejected = fit_template_cross(
            TemplateCrossInput(
                template=template(count=2),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                registered_trace_coordinates_px=(0, 50, 100),
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 10.0),
                    FiniteInterval(40.0, 60.0),
                ),
                top_bindings=(top,),
                bottom_bindings=(wrong_bottom,),
            )
        )
        self.assertEqual(rejected.status, CrossFitStatus.UNRESOLVED)

        supported = fit_template_cross(
            TemplateCrossInput(
                template=template(count=2),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                registered_trace_coordinates_px=(0, 50, 100),
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 10.0),
                    FiniteInterval(40.0, 60.0),
                ),
                top_bindings=(top,),
                bottom_bindings=(replace(wrong_bottom, role_authorized=True),),
            )
        )
        self.assertEqual(supported.status, CrossFitStatus.RESOLVED)
        assert supported.best is not None
        self.assertEqual(supported.best.independent_support_region_count, 2)
        self.assertEqual(supported.best.longitudinal_support_domain_count, 2)
        self.assertEqual(
            supported.best.role_authorized_pair_support_domain_count,
            2,
        )

    def test_local_and_spanning_pairs_keep_canonical_fixed_height(self) -> None:
        fixed_template = replace(
            template(count=2),
            frame_height_px=FiniteInterval(230.0, 250.0),
        )
        domains = (FiniteInterval(0.0, 60.0), FiniteInterval(100.0, 160.0))
        local_top = binding(
            BoundaryRole.TOP,
            "local-height-top",
            100.0,
            traces=(10, 130),
            independent_regions=2,
            source_spanning=False,
        )
        local_bottom = binding(
            BoundaryRole.BOTTOM,
            "local-height-bottom",
            338.0,
            traces=(10, 130),
            independent_regions=2,
            source_spanning=False,
        )
        local = fit_template_cross(
            TemplateCrossInput(
                template=fixed_template,
                fixed_height_px=FiniteInterval(230.0, 250.0),
                canonical_fixed_height_px=245.0,
                top_bindings=(local_top,),
                bottom_bindings=(local_bottom,),
                longitudinal_support_domains_px=domains,
                registered_trace_coordinates_px=(10, 130),
            )
        )
        self.assertEqual(local.status, CrossFitStatus.RESOLVED)
        assert local.best is not None
        self.assertAlmostEqual(
            local.best.bottom_canonical_px - local.best.top_canonical_px,
            245.0,
        )
        spanning = fit_template_cross(
            TemplateCrossInput(
                template=fixed_template,
                fixed_height_px=FiniteInterval(230.0, 250.0),
                canonical_fixed_height_px=245.0,
                top_bindings=(
                    replace(local_top, source_spanning_continuous=True),
                ),
                bottom_bindings=(local_bottom,),
                longitudinal_support_domains_px=domains,
                registered_trace_coordinates_px=(10, 130),
            )
        )
        self.assertEqual(spanning.status, CrossFitStatus.RESOLVED)
        assert spanning.best is not None
        self.assertAlmostEqual(
            spanning.best.bottom_canonical_px - spanning.best.top_canonical_px,
            245.0,
        )

    def test_single_side_infers_opposite_fixed_height(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                top_bindings=(binding(BoundaryRole.TOP, "top", 100.0),),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertAlmostEqual(result.best.top_canonical_px, 100.0)
        self.assertAlmostEqual(result.best.bottom_canonical_px, 340.0)
        self.assertEqual(result.best.inferred_bindings[0].evidence, CrossEvidence.FIXED_HEIGHT_INFERRED)
        self.assertEqual(
            result.best.inferred_bindings[0].source_observation_ids,
            (ObservationId("observation:top"),),
        )
        self.assertEqual(
            result.best.inferred_bindings[0].independent_support_region_count,
            3,
        )
        self.assertEqual(
            result.best.selected_direction.selected_observation_ids,
            (ObservationId("observation:top"),),
        )
        self.assertEqual(result.receipt.single_side_inference_count, 1)

    def test_single_side_does_not_recalibrate_fixed_height_or_center(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                holder_short_axis_center_px=FiniteInterval(215.0, 225.0),
                top_bindings=(binding(BoundaryRole.TOP, "top-offset", 105.0),),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertAlmostEqual(result.best.top_canonical_px, 105.0)
        self.assertAlmostEqual(result.best.bottom_canonical_px, 345.0)
        self.assertEqual(
            result.best.height_compatibility_px,
            FiniteInterval(238.0, 242.0),
        )
        self.assertEqual(
            result.best.center_interval_px,
            FiniteInterval(215.0, 225.0),
        )
        self.assertEqual(
            result.best.top_full_interval_px,
            FiniteInterval.exact(105.0),
        )
        self.assertEqual(
            result.best.bottom_full_interval_px,
            FiniteInterval.exact(345.0),
        )

    def test_two_region_fragment_cannot_supply_single_side_direction(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                holder_short_axis_center_px=FiniteInterval(215.0, 225.0),
                registered_trace_coordinates_px=(0, 20, 40, 60, 80, 100),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "two-region-fragment",
                        100.0,
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)

    def test_center_owned_discrete_single_sides_remain_unresolved(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                holder_short_axis_center_px=FiniteInterval(215.0, 225.0),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "top-a",
                        96.0,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "top-b",
                        104.0,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.runner_up)
        assert result.best is not None
        # Holder centre compatibility is not output uncertainty; the local
        # direct measurements remain discrete placement interpretations.
        self.assertAlmostEqual(result.best.top_canonical_px, 96.0)
        self.assertAlmostEqual(result.runner_up.top_canonical_px, 104.0)
        self.assertAlmostEqual(
            result.best.bottom_canonical_px - result.best.top_canonical_px,
            240.0,
        )

    def test_three_region_direct_pair_narrows_center_owned_height(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                holder_short_axis_center_px=FiniteInterval(215.0, 225.0),
                longitudinal_support_domains_px=(FiniteInterval(0.0, 100.0),),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "fragmented-top",
                        100.0,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "fragmented-bottom",
                        340.0,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertTrue(result.best.direct_pair)
        self.assertEqual(
            result.best.height_compatibility_px,
            FiniteInterval.exact(240.0),
        )

    def test_connected_local_pairs_can_form_one_source_wide_network(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                holder_short_axis_center_px=FiniteInterval(215.0, 225.0),
                registered_trace_coordinates_px=(0, 20, 40, 60, 80, 100),
                longitudinal_support_domains_px=(FiniteInterval(0.0, 100.0),),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "shared-top",
                        100.0,
                        traces=(0, 20, 50, 100),
                        independent_regions=3,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "front-bottom",
                        340.0,
                        traces=(0, 20),
                        independent_regions=1,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "back-bottom",
                        340.0,
                        traces=(50, 100),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertIsNone(result.runner_up)
        self.assertTrue(result.best.direct_pair)
        self.assertEqual(result.best.independent_support_region_count, 3)
        self.assertEqual(len(result.best.direct_provenance_ids), 3)

    def test_disconnected_local_pairs_remain_discrete_answers(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                holder_short_axis_center_px=FiniteInterval(215.0, 225.0),
                registered_trace_coordinates_px=(0, 20, 40, 60, 80, 100),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "front-top",
                        100.0,
                        traces=(0, 20),
                        independent_regions=1,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "back-top",
                        100.0,
                        traces=(80, 100),
                        independent_regions=1,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "front-bottom",
                        340.0,
                        traces=(0, 20),
                        independent_regions=1,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "back-bottom",
                        340.0,
                        traces=(80, 100),
                        independent_regions=1,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)
        assert result.best is not None
        assert result.runner_up is not None
        self.assertTrue(
            set(result.best.direct_provenance_ids).isdisjoint(
                result.runner_up.direct_provenance_ids
            )
        )

    def test_spanning_side_infers_opposite_without_fragment_authority(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(BoundaryRole.TOP, "spanning-top", 100.0),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "fragment-a",
                        500.0,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "fragment-b",
                        700.0,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            set(result.best.direct_provenance_ids),
            {
                ObservationId("observation:spanning-top"),
            },
        )

    def test_spanning_side_rejects_wrong_role_local_closure(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(BoundaryRole.TOP, "spanning-top", 100.0),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "wrong-role-bottom",
                        339.0,
                        source_spanning=False,
                        role_authorized=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "authorized-bottom",
                        340.0,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        self.assertEqual(
            result.best.direct_provenance_ids,
            (
                ObservationId("observation:spanning-top"),
                ObservationId("observation:authorized-bottom"),
            ),
        )

    def test_template_wide_side_infers_opposite_without_local_fragment_authority(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=3),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "template-wide-top",
                        100.0,
                        traces=(10, 50, 90),
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "wrong-role-bottom-a",
                        340.0,
                        traces=(10,),
                        source_spanning=False,
                        role_authorized=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "wrong-role-bottom-b",
                        341.0,
                        traces=(90,),
                        source_spanning=False,
                        role_authorized=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            result.best.direct_provenance_ids,
            (ObservationId("observation:template-wide-top"),),
        )

    def test_domain_complete_role_anchor_resolves_with_two_regions(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=3),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                registered_trace_coordinates_px=(10, 50, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-complete-two-region-top",
                        100.0,
                        traces=(10, 50, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            result.best.direct_provenance_ids,
            (ObservationId("observation:domain-complete-two-region-top"),),
        )
        self.assertAlmostEqual(result.best.top_canonical_px, 100.0)
        self.assertAlmostEqual(result.best.bottom_canonical_px, 340.0)

    def test_domain_complete_role_anchor_does_not_require_holder_center(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(10, 50, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-complete-no-center-top",
                        100.0,
                        traces=(10, 50, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertAlmostEqual(result.best.top_canonical_px, 100.0)
        self.assertAlmostEqual(result.best.bottom_canonical_px, 340.0)

    def test_domain_complete_anchor_requires_at_least_three_domains(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=2),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                registered_trace_coordinates_px=(10, 50),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-complete-two-domain-top",
                        100.0,
                        traces=(10, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(result.best)

    def test_domain_complete_anchor_requires_every_frame_domain(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=3),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                registered_trace_coordinates_px=(10, 50, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-incomplete-top",
                        100.0,
                        traces=(10, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(result.best)

    def test_domain_complete_anchor_requires_complete_direction(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=3),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                registered_trace_coordinates_px=(10, 50, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-no-direction-top",
                        100.0,
                        traces=(10, 50, 90),
                        independent_regions=2,
                        source_spanning=False,
                        angle=None,
                        angle_interval=None,
                        full_angle_interval=None,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(result.best)

    def test_domain_complete_anchor_requires_role_authority(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=3),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                registered_trace_coordinates_px=(10, 50, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-unauthorized-top",
                        100.0,
                        traces=(10, 50, 90),
                        independent_regions=2,
                        source_spanning=False,
                        role_authorized=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(result.best)

    def test_disconnected_fragments_cannot_combine_domain_coverage(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=3),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                registered_trace_coordinates_px=(10, 50, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-fragment-front",
                        100.0,
                        traces=(10, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "domain-fragment-back",
                        100.0,
                        traces=(50, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(result.best)

    def test_template_wide_anchor_refines_the_nearest_opposite_line(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=3),
                fixed_height_px=FiniteInterval(230.0, 250.0),
                canonical_fixed_height_px=240.0,
                holder_short_axis_center_px=FiniteInterval(215.0, 225.0),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "template-refine-top",
                        100.0,
                        traces=(10, 50, 90),
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "near-bottom",
                        342.0,
                        traces=(10, 50),
                        source_spanning=False,
                        role_authorized=False,
                        independent_regions=2,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "far-bottom",
                        347.0,
                        traces=(10, 50),
                        source_spanning=False,
                        role_authorized=False,
                        independent_regions=2,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertTrue(result.best.direct_pair)
        self.assertAlmostEqual(result.best.top_canonical_px, 100.0)
        self.assertAlmostEqual(result.best.bottom_canonical_px, 342.0)
        self.assertEqual(
            result.best.direct_bindings[1].evidence,
            CrossEvidence.TEMPLATE_LOCAL_REFINEMENT,
        )

    def test_equal_nearest_local_outer_lines_remain_unresolved(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=3),
                fixed_height_px=FiniteInterval(230.0, 250.0),
                canonical_fixed_height_px=240.0,
                holder_short_axis_center_px=FiniteInterval(215.0, 225.0),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "ambiguous-refine-top",
                        100.0,
                        traces=(10, 50, 90),
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "lower-near",
                        338.0,
                        traces=(10, 50),
                        source_spanning=False,
                        role_authorized=False,
                        independent_regions=2,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "upper-near",
                        342.0,
                        traces=(10, 50),
                        source_spanning=False,
                        role_authorized=False,
                        independent_regions=2,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)

    def test_role_authorized_direct_pair_precedes_single_side_inference(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=3),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "template-wide-paired-top",
                        100.0,
                        traces=(10, 50, 90),
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "two-domain-bottom",
                        340.0,
                        traces=(10, 50),
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertTrue(result.best.direct_pair)
        self.assertEqual(len(result.best.direct_bindings), 2)

    def test_fragment_only_group_cannot_compete_with_spanning_closure(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(BoundaryRole.TOP, "spanning-top", 100.0),
                    binding(
                        BoundaryRole.TOP,
                        "fragment-top",
                        500.0,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "spanning-bottom-fragment",
                        340.0,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "fragment-bottom",
                        740.0,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        self.assertIn(
            ObservationId("observation:spanning-top"),
            result.best.direct_provenance_ids,
        )

    def test_equally_strong_non_equivalent_fits_keep_runner_up_unresolved(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "top-a", 100.0),
                    binding(BoundaryRole.TOP, "top-b", 500.0),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "bottom-a", 340.0),
                    binding(BoundaryRole.BOTTOM, "bottom-b", 740.0),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)
        self.assertEqual(result.receipt.evaluated_fit_count, 2)

    def test_nearby_exact_pairs_remain_discrete_without_shared_identity(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "top-a", 100.0, role_authorized=False),
                    binding(BoundaryRole.TOP, "top-b", 104.0, role_authorized=False),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "bottom-a", 340.0, role_authorized=False),
                    binding(BoundaryRole.BOTTOM, "bottom-b", 344.0, role_authorized=False),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertTrue(
            result.best is None
            or result.best.boundary_use != OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
        )

    def test_role_authorized_line_can_join_one_uniform_enclosing_pair(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                canonical_fixed_height_px=240.0,
                holder_short_axis_center_px=FiniteInterval(224.0, 226.0),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "aperture-or-support-top",
                        100.0,
                        enclosing_pair_id="support:one",
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom",
                        350.0,
                        enclosing_pair_id="support:one",
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.boundary_use,
            OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR,
        )
        self.assertIsNotNone(result.best.enclosing_support_pair)
        self.assertFalse(result.best.single_side_inferred)

    def test_enclosing_support_evaluations_share_the_cross_fit_bound(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                maximum_evaluated_fits=1,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "support-top-a",
                        100.0,
                        role_authorized=False,
                        enclosing_pair_id="support:a",
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "support-top-b",
                        101.0,
                        role_authorized=False,
                        enclosing_pair_id="support:b",
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom-a",
                        345.0,
                        role_authorized=False,
                        enclosing_pair_id="support:a",
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom-b",
                        346.0,
                        role_authorized=False,
                        enclosing_pair_id="support:b",
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertEqual(result.receipt.evaluated_fit_count, 2)
        self.assertEqual(result.receipt.evaluated_fit_bound, 1)

    def test_preclosed_enclosing_pair_cannot_detach_and_recombine(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                canonical_fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "support-top-a",
                        100.0,
                        role_authorized=False,
                        enclosing_pair_id="support:a",
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom-a",
                        350.0,
                        role_authorized=False,
                        enclosing_pair_id="support:a",
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom-b",
                        349.0,
                        role_authorized=False,
                        enclosing_pair_id="support:b",
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.direct_provenance_ids,
            (
                ObservationId("observation:support-top-a"),
                ObservationId("observation:support-bottom-a"),
            ),
        )
        self.assertEqual(result.receipt.evaluated_fit_count, 1)

    def test_enclosing_support_records_straight_model_residual(self) -> None:
        top = replace(
            binding(
                BoundaryRole.TOP,
                "bent-support-top",
                100.0,
                role_authorized=False,
                enclosing_pair_id="support:bent",
            ),
            trace_position_intervals_px=(
                FiniteInterval.exact(100.0),
                FiniteInterval.exact(104.0),
                FiniteInterval.exact(100.0),
            ),
        )
        bottom = replace(
            binding(
                BoundaryRole.BOTTOM,
                "bent-support-bottom",
                350.0,
                role_authorized=False,
                enclosing_pair_id="support:bent",
            ),
            trace_position_intervals_px=(
                FiniteInterval.exact(350.0),
                FiniteInterval.exact(346.0),
                FiniteInterval.exact(350.0),
            ),
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                canonical_fixed_height_px=240.0,
                top_bindings=(top,),
                bottom_bindings=(bottom,),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        assert result.best.enclosing_support_pair is not None
        self.assertEqual(
            result.best.enclosing_support_pair.top_straight_model_residual_px,
            4.0,
        )
        self.assertEqual(
            result.best.enclosing_support_pair.bottom_straight_model_residual_px,
            4.0,
        )

    def test_local_role_line_cannot_compete_with_source_wide_support(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=3),
                fixed_height_px=FiniteInterval(235.0, 245.0),
                canonical_fixed_height_px=240.0,
                holder_short_axis_center_px=FiniteInterval(200.0, 210.0),
                registered_trace_coordinates_px=(0, 50, 100),
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 1.0),
                    FiniteInterval(49.0, 51.0),
                    FiniteInterval(99.0, 101.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "local-role-top",
                        75.0,
                        traces=(0, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "whole-support-top",
                        80.0,
                        source_spanning=False,
                        role_authorized=False,
                        enclosing_pair_id="support:whole",
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "whole-support-bottom",
                        330.0,
                        source_spanning=False,
                        role_authorized=False,
                        enclosing_pair_id="support:whole",
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.boundary_use,
            OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR,
        )
        assert result.best.enclosing_support_pair is not None
        self.assertEqual(
            result.best.enclosing_support_pair.top_provenance_ids,
            (ObservationId("observation:whole-support-top"),),
        )

    def test_distinct_exact_bindings_are_not_hulled_into_uncertainty(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                holder_short_axis_center_px=FiniteInterval(219.0, 221.0),
                top_bindings=(
                    binding(BoundaryRole.TOP, "top-a", 100.0, traces=(0, 50)),
                    binding(BoundaryRole.TOP, "top-b", 100.25, traces=(50, 100)),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "bottom-a", 340.0, traces=(0, 50)),
                    binding(BoundaryRole.BOTTOM, "bottom-b", 340.5, traces=(50, 100)),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.runner_up)
        assert result.best is not None
        self.assertEqual(result.best.top_full_interval_px.width, 0.0)
        self.assertEqual(result.best.bottom_full_interval_px.width, 0.0)

    def test_two_sided_spanning_closure_excludes_local_false_pair(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(BoundaryRole.TOP, "true-top", 100.0),
                    binding(
                        BoundaryRole.TOP,
                        "local-top",
                        70.0,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "true-bottom", 340.0),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.direct_provenance_ids,
            (
                ObservationId("observation:true-top"),
                ObservationId("observation:true-bottom"),
            ),
        )
        self.assertAlmostEqual(result.best.top_canonical_px, 100.0)

    def test_far_groups_are_not_hulled_and_keep_runner_up(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "near-top", 100.0),
                    binding(BoundaryRole.TOP, "far-top", 500.0),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "near-bottom", 340.0),
                    binding(BoundaryRole.BOTTOM, "far-bottom", 740.0),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)
        assert result.best is not None
        assert result.runner_up is not None
        self.assertEqual(
            result.best.top_full_interval_px,
            FiniteInterval.exact(100.0),
        )
        self.assertEqual(
            result.runner_up.top_full_interval_px,
            FiniteInterval.exact(500.0),
        )

    def test_holder_center_cannot_select_between_direct_aperture_pairs(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "normal-top", 100.0),
                    binding(BoundaryRole.TOP, "clutter-top", 300.0),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "normal-bottom", 340.0),
                    binding(BoundaryRole.BOTTOM, "clutter-bottom", 540.0),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        assert result.best is not None
        assert result.runner_up is not None
        self.assertEqual(result.best.direct_observation_ids[0], ObservationId("observation:normal-top"))
        self.assertTrue(result.best.center_compatible)
        self.assertEqual(
            result.runner_up.direct_observation_ids[0],
            ObservationId("observation:clutter-top"),
        )
        self.assertFalse(result.runner_up.center_compatible)

    def test_unique_direct_aperture_pair_owns_offset_outside_holder_center(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                holder_short_axis_center_px=220.0,
                top_bindings=(binding(BoundaryRole.TOP, "top", 300.0),),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "bottom", 540.0),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        self.assertFalse(result.best.center_compatible)

    def test_direct_height_contradiction_does_not_recalibrate_or_resolve(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval.exact(240.0),
                top_bindings=(binding(BoundaryRole.TOP, "top", 100.0),),
                bottom_bindings=(binding(BoundaryRole.BOTTOM, "bottom", 500.0),),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(result.best)
        self.assertEqual(result.receipt.compatible_pair_count, 0)

    def test_receipt_bound_overflow_is_explicit(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(binding(BoundaryRole.TOP, "top", 100.0),),
                bottom_bindings=(binding(BoundaryRole.BOTTOM, "bottom", 340.0),),
                maximum_fitted_observations=1,
            )
        )
        self.assertEqual(result.status, CrossFitStatus.BOUND_EXCEEDED)
        with self.assertRaises(ValueError):
            result.receipt.__class__(
                **{
                    **result.receipt.__dict__,
                    "evaluated_fit_count": result.receipt.evaluated_fit_bound + 1,
                }
            ).validate_bounds()

    def test_direction_provenance_retains_selected_observations_and_interval(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "top",
                        100.0,
                        angle=0.05,
                        angle_interval=FiniteInterval(-0.2, 0.2),
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "bottom",
                        340.0,
                        angle=0.1,
                        angle_interval=FiniteInterval(-0.1, 0.3),
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        assert result.best.selected_direction is not None
        direction = result.best.selected_direction
        self.assertEqual(
            set(direction.selected_observation_ids),
            {
                ObservationId("observation:top"),
                ObservationId("observation:bottom"),
            },
        )
        self.assertEqual(direction.full_angle_interval_degrees, FiniteInterval(-0.2, 0.3))
        self.assertEqual(
            result.best.direction_provenance_ids,
            (
                ObservationId("observation:top"),
                ObservationId("observation:bottom"),
            ),
        )

    def test_local_opposite_edge_does_not_expand_source_direction(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "spanning-top",
                        100.0,
                        angle=-0.15,
                        angle_interval=FiniteInterval(-0.2, -0.1),
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "local-bottom",
                        340.0,
                        angle=-0.1,
                        angle_interval=FiniteInterval(-1.0, 0.2),
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        assert result.best.selected_direction is not None
        self.assertTrue(result.best.direct_pair)
        self.assertEqual(
            result.best.selected_direction.full_angle_interval_degrees,
            FiniteInterval(-0.2, -0.1),
        )

    def test_missing_direction_cannot_resolve(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "top-no-direction",
                        100.0,
                        angle=None,
                        angle_interval=None,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "bottom-no-direction",
                        340.0,
                        angle=None,
                        angle_interval=None,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(result.reason, "cross direction unavailable")

    def test_single_side_requires_spanning_independent_regions(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "isolated-top",
                        100.0,
                        independent_regions=1,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(result.best)

    def test_support_and_residual_do_not_choose_discrete_groups(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "high-support-top",
                        100.0,
                        support=1.0,
                        residual=0.0,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "low-support-top",
                        500.0,
                        support=0.2,
                        residual=10.0,
                    ),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "high-support-bottom", 340.0),
                    binding(
                        BoundaryRole.BOTTOM,
                        "low-support-bottom",
                        740.0,
                        support=0.2,
                        residual=10.0,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.runner_up)

    def test_support_across_three_template_frames_rejects_local_runner(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(count=4),
                fixed_height_px=240.0,
                holder_short_axis_center_px=FiniteInterval(219.0, 225.0),
                registered_trace_coordinates_px=(0, 20, 40, 60, 80, 100),
                longitudinal_support_domains_px=(
                    FiniteInterval(5.0, 20.0),
                    FiniteInterval(25.0, 40.0),
                    FiniteInterval(45.0, 60.0),
                    FiniteInterval(65.0, 80.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "whole-top",
                        100.0,
                        traces=(10, 35, 55, 75),
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "local-top",
                        104.0,
                        traces=(35, 55),
                        source_spanning=False,
                        role_authorized=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "whole-bottom",
                        340.0,
                        traces=(10, 35, 55, 75),
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "local-bottom",
                        344.0,
                        traces=(35, 55),
                        source_spanning=False,
                        role_authorized=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        self.assertEqual(result.best.independent_support_region_count, 3)
        self.assertEqual(
            set(result.best.direct_observation_ids),
            {
                ObservationId("observation:whole-top"),
                ObservationId("observation:whole-bottom"),
            },
        )

    def test_all_h_compatible_pairs_are_retained_until_bound(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(240.0, 242.0),
                maximum_compatible_pairs=2,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "wide-top",
                        100.0,
                        angle_interval=FiniteInterval(-1.0, 1.0),
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "wide-bottom-a",
                        340.0,
                        angle_interval=FiniteInterval(-1.0, 1.0),
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "wide-bottom-b",
                        341.0,
                        angle_interval=FiniteInterval(-1.0, 1.0),
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "wide-bottom-c",
                        342.0,
                        angle_interval=FiniteInterval(-1.0, 1.0),
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertEqual(result.receipt.compatible_pair_count, 3)

    def test_staggered_trace_lattices_can_share_independent_regions(self) -> None:
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "top", 100.0, traces=(0, 50, 100)),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "bottom", 340.0, traces=(1, 51, 101)),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertGreaterEqual(result.best.shared_trace_support_count, 2)


if __name__ == "__main__":
    unittest.main()
