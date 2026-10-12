from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tools.tests.template_test_support import placement_direction
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_cross import (
    calibrate_source_frame_height,
    fit_template_cross,
)
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossEvidence,
    CrossFailureKind,
    CrossFitStatus,
    CrossHeightInferenceBasis,
    CrossHeightProjectionBasis,
    CrossLineProjectionBasis,
    CrossLongitudinalProjectionBasis,
    CrossLongitudinalProjectionFailureKind,
    CrossPairSupportMode,
    CrossRetainedProposalBasis,
    CrossWinnerBasis,
    CrossRoleBinding,
    TemplateCrossInput as _TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_aspect_ratio_model import (
    ApertureAspectRatioAuthority,
    ApertureAspectRatioFailureKind,
)
from x5crop.detection.photo_geometry.output_model import OutputBoundaryUse
from x5crop.detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC
from x5crop.detection.photo_geometry.trace_support import (
    source_spanning_continuous_trace_support,
)
from x5crop.formats import FramePhysicalSpec


from tools.tests.cross_fixture_support import (
    _supported_aspect_ratio,
    aspect_input,
    binding,
    template,
)

class TemplateCrossMembershipContractTest(unittest.TestCase):
    def test_shared_anchor_does_not_merge_distinct_opposite_boundaries(self) -> None:
            # Both alternatives independently meet the ordinary two-region
            # boundary minimum; a local one-region line is not a legal global
            # alternative merely because the selected template has one domain.
            result = fit_template_cross(
                aspect_input(
                    template=template(),
                    fixed_height_px=FiniteInterval(238.0, 242.0),
                    registered_trace_coordinates_px=(0, 20, 40, 60, 80, 100),
                    longitudinal_support_domain_groups_px=((FiniteInterval(0.0, 100.0),),),
                    top_bindings=(
                        binding(
                            BoundaryRole.TOP,
                            "shared-top",
                            100.0,
                            traces=(0, 20, 40, 60, 100),
                            independent_regions=3,
                            source_spanning=False,
                        ),
                    ),
                    bottom_bindings=(
                        binding(
                            BoundaryRole.BOTTOM,
                            "front-bottom",
                            340.0,
                            traces=(0, 40),
                            independent_regions=2,
                            source_spanning=False,
                        ),
                        binding(
                            BoundaryRole.BOTTOM,
                            "back-bottom",
                            340.0,
                            traces=(60, 100),
                            independent_regions=2,
                            source_spanning=False,
                        ),
                    ),
                )
            )
            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            assert result.best is not None
            self.assertIsNotNone(result.runner_up)
            self.assertTrue(result.best.direct_pair)
            self.assertIn("non-equivalent", result.reason or "")

    def test_selection_does_not_own_exact_subset_family_identity(self) -> None:
            registered = tuple(range(0, 101, 10))
            result = fit_template_cross(
                aspect_input(
                    template=template(count=3),
                    fixed_height_px=FiniteInterval(236.0, 240.0),
                    registered_trace_coordinates_px=registered,
                    longitudinal_support_domain_groups_px=((
                        FiniteInterval(-1.0, 21.0),
                        FiniteInterval(39.0, 61.0),
                        FiniteInterval(79.0, 101.0),
                    ),),
                    top_bindings=(
                        binding(
                            BoundaryRole.TOP,
                            "exact-broader-top",
                            100.0,
                            traces=(0, 20, 40, 60, 80, 100),
                            independent_regions=2,
                            source_spanning=False,
                            angle=-0.2,
                            angle_interval=FiniteInterval(-0.3, -0.1),
                        ),
                        binding(
                            BoundaryRole.TOP,
                            "exact-local-top",
                            104.0,
                            traces=(40, 60, 80),
                            independent_regions=2,
                            source_spanning=False,
                            angle=0.2,
                            angle_interval=FiniteInterval(0.1, 0.3),
                        ),
                    ),
                    bottom_bindings=(
                        binding(
                            BoundaryRole.BOTTOM,
                            "exact-shared-bottom",
                            340.0,
                            traces=registered,
                            independent_regions=3,
                            source_spanning=False,
                            angle=0.0,
                            angle_interval=FiniteInterval(-0.4, 0.4),
                        ),
                    ),
                )
            )

            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertIsNotNone(result.best)
            self.assertIsNotNone(result.runner_up)

    def test_selection_does_not_own_staggered_family_identity(self) -> None:
            domains = (
                FiniteInterval(-1.0, 21.0),
                FiniteInterval(39.0, 61.0),
                FiniteInterval(79.0, 101.0),
            )
            registered = tuple(range(0, 101, 10))
            result = fit_template_cross(
                aspect_input(
                    template=template(count=3),
                    fixed_height_px=FiniteInterval(236.0, 240.0),
                    registered_trace_coordinates_px=registered,
                    longitudinal_support_domain_groups_px=(domains,),
                    top_bindings=(
                        binding(
                            BoundaryRole.TOP,
                            "broader-top",
                            100.0,
                            traces=(0, 20, 40, 60, 80, 100),
                            independent_regions=3,
                            source_spanning=False,
                        ),
                        binding(
                            BoundaryRole.TOP,
                            "staggered-local-top",
                            104.0,
                            traces=(50, 70, 90),
                            independent_regions=2,
                            source_spanning=False,
                        ),
                    ),
                    bottom_bindings=(
                        binding(
                            BoundaryRole.BOTTOM,
                            "shared-bottom",
                            340.0,
                            traces=registered,
                            independent_regions=3,
                            source_spanning=False,
                        ),
                    ),
                )
            )

            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertIsNotNone(result.best)
            self.assertIsNotNone(result.runner_up)
            self.assertEqual(result.receipt.compatible_pair_count, 2)
            # Every attempted support proof, including rejected pairs, is charged.
            self.assertEqual(result.receipt.evaluated_fit_count, 3)

    def test_equal_domain_side_tracks_remain_discrete(self) -> None:
            registered = tuple(range(0, 101, 10))
            result = fit_template_cross(
                aspect_input(
                    template=template(count=3),
                    fixed_height_px=FiniteInterval(236.0, 240.0),
                    registered_trace_coordinates_px=registered,
                    longitudinal_support_domain_groups_px=((
                        FiniteInterval(-1.0, 21.0),
                        FiniteInterval(39.0, 61.0),
                        FiniteInterval(79.0, 101.0),
                    ),),
                    top_bindings=(
                        binding(
                            BoundaryRole.TOP,
                            "equal-domain-broader-top",
                            100.0,
                            traces=(0, 20, 40, 60, 80, 100),
                            independent_regions=3,
                            source_spanning=False,
                        ),
                        binding(
                            BoundaryRole.TOP,
                            "equal-domain-local-top",
                            104.0,
                            traces=(10, 30, 50, 70, 90),
                            independent_regions=3,
                            source_spanning=False,
                        ),
                    ),
                    bottom_bindings=(
                        binding(
                            BoundaryRole.BOTTOM,
                            "equal-domain-shared-bottom",
                            340.0,
                            traces=registered,
                            independent_regions=3,
                            source_spanning=False,
                        ),
                    ),
                )
            )

            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertIsNotNone(result.best)
            self.assertIsNotNone(result.runner_up)

    def test_disjoint_side_track_extents_remain_discrete(self) -> None:
            registered = tuple(range(0, 111, 10))
            result = fit_template_cross(
                aspect_input(
                    template=template(count=4),
                    fixed_height_px=FiniteInterval(236.0, 240.0),
                    registered_trace_coordinates_px=registered,
                    longitudinal_support_domain_groups_px=((
                        FiniteInterval(-1.0, 21.0),
                        FiniteInterval(29.0, 51.0),
                        FiniteInterval(59.0, 81.0),
                        FiniteInterval(89.0, 111.0),
                    ),),
                    top_bindings=(
                        binding(
                            BoundaryRole.TOP,
                            "disjoint-broader-top",
                            100.0,
                            traces=(0, 20, 40, 60, 70),
                            independent_regions=3,
                            source_spanning=False,
                        ),
                        binding(
                            BoundaryRole.TOP,
                            "disjoint-local-top",
                            104.0,
                            traces=(80, 90, 100, 110),
                            independent_regions=2,
                            source_spanning=False,
                        ),
                    ),
                    bottom_bindings=(
                        binding(
                            BoundaryRole.BOTTOM,
                            "disjoint-shared-bottom",
                            340.0,
                            traces=registered,
                            independent_regions=3,
                            source_spanning=False,
                        ),
                    ),
                )
            )

            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertIsNotNone(result.best)
            self.assertIsNotNone(result.runner_up)

    def test_disconnected_broader_side_track_cannot_dominate(self) -> None:
            registered = tuple(range(0, 101, 10))
            result = fit_template_cross(
                aspect_input(
                    template=template(count=3),
                    fixed_height_px=FiniteInterval(236.0, 240.0),
                    registered_trace_coordinates_px=registered,
                    longitudinal_support_domain_groups_px=((
                        FiniteInterval(-1.0, 21.0),
                        FiniteInterval(39.0, 61.0),
                        FiniteInterval(79.0, 101.0),
                    ),),
                    top_bindings=(
                        binding(
                            BoundaryRole.TOP,
                            "disconnected-broader-top",
                            100.0,
                            traces=(0, 50, 100),
                            independent_regions=3,
                            source_spanning=False,
                        ),
                        binding(
                            BoundaryRole.TOP,
                            "inside-connected-local-top",
                            104.0,
                            traces=(30, 50, 70, 90),
                            independent_regions=2,
                            source_spanning=False,
                        ),
                    ),
                    bottom_bindings=(
                        binding(
                            BoundaryRole.BOTTOM,
                            "disconnected-broader-shared-bottom",
                            340.0,
                            traces=registered,
                            independent_regions=3,
                            source_spanning=False,
                        ),
                    ),
                )
            )

            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertIsNotNone(result.runner_up)

    def test_disconnected_local_side_track_cannot_be_discarded(self) -> None:
            registered = tuple(range(0, 101, 10))
            result = fit_template_cross(
                aspect_input(
                    template=template(count=3),
                    fixed_height_px=FiniteInterval(236.0, 240.0),
                    registered_trace_coordinates_px=registered,
                    longitudinal_support_domain_groups_px=((
                        FiniteInterval(-1.0, 21.0),
                        FiniteInterval(39.0, 61.0),
                        FiniteInterval(79.0, 101.0),
                    ),),
                    top_bindings=(
                        binding(
                            BoundaryRole.TOP,
                            "connected-broader-top",
                            100.0,
                            traces=(0, 20, 40, 60, 80, 100),
                            independent_regions=3,
                            source_spanning=False,
                        ),
                        binding(
                            BoundaryRole.TOP,
                            "disconnected-inside-local-top",
                            104.0,
                            traces=(10, 90),
                            independent_regions=2,
                            source_spanning=False,
                        ),
                    ),
                    bottom_bindings=(
                        binding(
                            BoundaryRole.BOTTOM,
                            "disconnected-local-shared-bottom",
                            340.0,
                            traces=registered,
                            independent_regions=3,
                            source_spanning=False,
                        ),
                    ),
                )
            )

            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertIsNotNone(result.runner_up)

    def test_different_opposite_bindings_remain_discrete(self) -> None:
            registered = tuple(range(0, 101, 10))
            result = fit_template_cross(
                aspect_input(
                    template=template(count=3),
                    fixed_height_px=240.0,
                    registered_trace_coordinates_px=registered,
                    longitudinal_support_domain_groups_px=((
                        FiniteInterval(-1.0, 21.0),
                        FiniteInterval(39.0, 61.0),
                        FiniteInterval(79.0, 101.0),
                    ),),
                    top_bindings=(
                        binding(
                            BoundaryRole.TOP,
                            "different-opposite-broader-top",
                            100.0,
                            traces=(0, 20, 40, 60, 80, 100),
                            independent_regions=3,
                            source_spanning=False,
                        ),
                        binding(
                            BoundaryRole.TOP,
                            "different-opposite-local-top",
                            104.0,
                            traces=(50, 70, 90),
                            independent_regions=2,
                            source_spanning=False,
                        ),
                    ),
                    bottom_bindings=(
                        binding(
                            BoundaryRole.BOTTOM,
                            "different-opposite-broad-bottom",
                            340.0,
                            traces=registered,
                            independent_regions=3,
                            source_spanning=False,
                        ),
                        binding(
                            BoundaryRole.BOTTOM,
                            "different-opposite-local-bottom",
                            344.0,
                            traces=registered,
                            independent_regions=3,
                            source_spanning=False,
                        ),
                    ),
                )
            )

            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertIsNotNone(result.best)
            self.assertIsNotNone(result.runner_up)

    def test_direction_disjoint_side_tracks_remain_discrete(self) -> None:
            registered = tuple(range(0, 101, 10))
            result = fit_template_cross(
                aspect_input(
                    template=template(count=3),
                    fixed_height_px=FiniteInterval(236.0, 240.0),
                    registered_trace_coordinates_px=registered,
                    longitudinal_support_domain_groups_px=((
                        FiniteInterval(-1.0, 21.0),
                        FiniteInterval(39.0, 61.0),
                        FiniteInterval(79.0, 101.0),
                    ),),
                    top_bindings=(
                        binding(
                            BoundaryRole.TOP,
                            "direction-broader-top",
                            100.0,
                            traces=(0, 20, 40, 60, 80, 100),
                            independent_regions=3,
                            source_spanning=False,
                            angle=-0.2,
                            angle_interval=FiniteInterval(-0.3, -0.1),
                        ),
                        binding(
                            BoundaryRole.TOP,
                            "direction-local-top",
                            104.0,
                            traces=(50, 70, 90),
                            independent_regions=2,
                            source_spanning=False,
                            angle=0.2,
                            angle_interval=FiniteInterval(0.1, 0.3),
                        ),
                    ),
                    bottom_bindings=(
                        binding(
                            BoundaryRole.BOTTOM,
                            "direction-shared-bottom",
                            340.0,
                            traces=registered,
                            independent_regions=3,
                            source_spanning=False,
                            angle=0.0,
                            angle_interval=FiniteInterval(-0.4, 0.4),
                        ),
                    ),
                )
            )

            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertIsNotNone(result.runner_up)

    def test_two_domain_side_cannot_gain_global_dominance(self) -> None:
            registered = tuple(range(0, 101, 10))
            result = fit_template_cross(
                aspect_input(
                    template=template(count=3),
                    fixed_height_px=FiniteInterval(236.0, 240.0),
                    registered_trace_coordinates_px=registered,
                    longitudinal_support_domain_groups_px=((
                        FiniteInterval(-1.0, 21.0),
                        FiniteInterval(39.0, 61.0),
                        FiniteInterval(79.0, 101.0),
                    ),),
                    top_bindings=(
                        binding(
                            BoundaryRole.TOP,
                            "two-domain-broader-top",
                            100.0,
                            traces=(0, 20, 40, 60),
                            independent_regions=2,
                            source_spanning=False,
                        ),
                        binding(
                            BoundaryRole.TOP,
                            "one-domain-local-top",
                            104.0,
                            traces=(30, 50),
                            independent_regions=1,
                            source_spanning=False,
                        ),
                    ),
                    bottom_bindings=(
                        binding(
                            BoundaryRole.BOTTOM,
                            "two-domain-shared-bottom",
                            340.0,
                            traces=(0, 20, 30, 50),
                            independent_regions=2,
                            source_spanning=False,
                        ),
                    ),
                )
            )

            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertIsNotNone(result.best)
            self.assertIsNotNone(result.runner_up)

    def test_under_supported_local_side_cannot_be_discarded(self) -> None:
            registered = tuple(range(0, 101, 10))
            domains = (
                FiniteInterval(-1.0, 21.0),
                FiniteInterval(39.0, 61.0),
                FiniteInterval(79.0, 101.0),
                FiniteInterval(109.0, 131.0),
            )
            local_cases = (
                ("one-region-ledger", (50, 70, 90), 1, (0, 20, 50, 70)),
            )
            for name, local_traces, local_regions, bottom_traces in local_cases:
                with self.subTest(name=name):
                    result = fit_template_cross(
                        aspect_input(
                            template=template(count=4),
                            fixed_height_px=FiniteInterval(236.0, 240.0),
                            registered_trace_coordinates_px=registered,
                            longitudinal_support_domain_groups_px=(domains,),
                            top_bindings=(
                                binding(
                                    BoundaryRole.TOP,
                                    f"{name}-broader-top",
                                    100.0,
                                    traces=(0, 20, 40, 60, 80, 100),
                                    independent_regions=3,
                                    source_spanning=False,
                                ),
                                binding(
                                    BoundaryRole.TOP,
                                    f"{name}-local-top",
                                    104.0,
                                    traces=local_traces,
                                    independent_regions=local_regions,
                                    source_spanning=False,
                                ),
                            ),
                            bottom_bindings=(
                                binding(
                                    BoundaryRole.BOTTOM,
                                    f"{name}-shared-bottom",
                                    340.0,
                                    traces=bottom_traces,
                                    independent_regions=2,
                                    source_spanning=False,
                                ),
                            ),
                        )
                    )

                    self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
                    self.assertIsNotNone(result.best)
                    self.assertIsNotNone(result.runner_up)

    def test_selection_does_not_own_one_domain_family_identity(self) -> None:
            result = fit_template_cross(
                aspect_input(
                    template=template(count=4),
                    fixed_height_px=FiniteInterval(236.0, 240.0),
                    registered_trace_coordinates_px=tuple(range(0, 101, 10)),
                    longitudinal_support_domain_groups_px=((
                        FiniteInterval(-1.0, 21.0),
                        FiniteInterval(39.0, 61.0),
                        FiniteInterval(79.0, 101.0),
                        FiniteInterval(109.0, 131.0),
                    ),),
                    top_bindings=(
                        binding(
                            BoundaryRole.TOP,
                            "one-domain-broader-top",
                            100.0,
                            traces=(0, 20, 40, 60, 80, 100),
                            independent_regions=3,
                            source_spanning=False,
                        ),
                        binding(
                            BoundaryRole.TOP,
                            "one-domain-local-top",
                            104.0,
                            traces=(30, 50),
                            independent_regions=2,
                            source_spanning=False,
                        ),
                    ),
                    bottom_bindings=(
                        binding(
                            BoundaryRole.BOTTOM,
                            "one-domain-shared-bottom",
                            340.0,
                            traces=(0, 20, 30, 50),
                            independent_regions=2,
                            source_spanning=False,
                        ),
                    ),
                )
            )

            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertIsNotNone(result.best)
            self.assertIsNotNone(result.runner_up)

    def test_missing_or_unregistered_lattice_cannot_authorize_dominance(self) -> None:
            domains = (
                FiniteInterval(-1.0, 21.0),
                FiniteInterval(39.0, 61.0),
                FiniteInterval(79.0, 101.0),
            )
            for name, registered in (
                ("missing", ()),
                ("local-off-lattice", (0, 20, 40, 60, 80, 100)),
            ):
                with self.subTest(name=name):
                    result = fit_template_cross(
                        aspect_input(
                            template=template(count=3),
                            fixed_height_px=FiniteInterval(236.0, 240.0),
                            registered_trace_coordinates_px=registered,
                            longitudinal_support_domain_groups_px=(domains,),
                            top_bindings=(
                                binding(
                                    BoundaryRole.TOP,
                                    f"{name}-broader-top",
                                    100.0,
                                    traces=(0, 20, 40, 60, 80, 100),
                                    independent_regions=3,
                                    source_spanning=False,
                                ),
                                binding(
                                    BoundaryRole.TOP,
                                    f"{name}-local-top",
                                    104.0,
                                    traces=(50, 70, 90),
                                    independent_regions=2,
                                    source_spanning=False,
                                ),
                            ),
                            bottom_bindings=(
                                binding(
                                    BoundaryRole.BOTTOM,
                                    f"{name}-shared-bottom",
                                    340.0,
                                    traces=tuple(range(0, 101, 10)),
                                    independent_regions=3,
                                    source_spanning=False,
                                ),
                            ),
                        )
                    )

                    self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
                    self.assertIsNotNone(result.best)
                    self.assertIsNotNone(result.runner_up)

    def test_disconnected_local_pairs_remain_discrete_answers(self) -> None:
            result = fit_template_cross(
                aspect_input(
                    template=template(),
                    fixed_height_px=FiniteInterval(238.0, 242.0),
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
                aspect_input(
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

    def test_spanning_side_infers_when_local_closures_are_ambiguous(self) -> None:
            result = fit_template_cross(
                aspect_input(
                    template=template(),
                    fixed_height_px=FiniteInterval(238.0, 242.0),
                    top_bindings=(
                        binding(BoundaryRole.TOP, "spanning-top", 100.0),
                    ),
                    bottom_bindings=(
                        binding(
                            BoundaryRole.BOTTOM,
                            "local-bottom-a",
                            339.0,
                            source_spanning=False,
                        ),
                        binding(
                            BoundaryRole.BOTTOM,
                            "local-bottom-b",
                            341.0,
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
                (ObservationId("observation:spanning-top"),),
            )
            self.assertAlmostEqual(result.best.top_canonical_px, 100.0)
            self.assertAlmostEqual(result.best.bottom_canonical_px, 340.0)

    def test_spanning_side_does_not_export_local_role_closure(self) -> None:
            result = fit_template_cross(
                aspect_input(
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
            self.assertFalse(result.best.direct_pair)
            self.assertEqual(
                result.best.direct_provenance_ids,
                (ObservationId("observation:spanning-top"),),
            )

    def test_template_wide_side_infers_opposite_without_local_fragment_authority(self) -> None:
            domains = (
                FiniteInterval(0.0, 20.0),
                FiniteInterval(40.0, 60.0),
                FiniteInterval(80.0, 100.0),
            )
            result = fit_template_cross(
                aspect_input(
                    template=template(count=3),
                    fixed_height_px=240.0,
                    longitudinal_support_domain_groups_px=(domains,),
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

    def test_three_selected_domains_cannot_authorize_a_one_region_anchor(self) -> None:
            result = fit_template_cross(
                aspect_input(
                    template=template(count=3),
                    fixed_height_px=240.0,
                    registered_trace_coordinates_px=tuple(range(0, 120, 10)),
                    longitudinal_support_domain_groups_px=(tuple(
                        FiniteInterval(float(start), float(start + 5))
                        for start in (0, 10, 20)
                    ),),
                    top_bindings=(binding(
                        BoundaryRole.TOP, "one-region-complete-domains", 100.0,
                        traces=(0, 10, 20), independent_regions=1,
                        source_spanning=False,
                    ),),
                )
            )
            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertEqual(result.failure_kind, CrossFailureKind.INDEPENDENT_SUPPORT_UNAVAILABLE)

    def test_three_selected_domains_cannot_authorize_a_one_region_pair_side(self) -> None:
            queried_traces = tuple(range(0, 120, 10))
            domains = tuple(
                FiniteInterval(float(start), float(start + 5)) for start in (0, 10, 20)
            )
            for top_regions, bottom_regions in ((1, 1), (1, 3), (3, 1)):
                with self.subTest(top_regions=top_regions, bottom_regions=bottom_regions):
                    def side(role, coordinate, regions):
                        return binding(
                            role, f"{role.value}-{regions}-regions", coordinate,
                            traces=(0, 10, 20) if regions == 1 else queried_traces,
                            independent_regions=regions,
                            source_spanning=regions == 3,
                        )
                    result = fit_template_cross(aspect_input(
                        template=template(count=3), fixed_height_px=240.0,
                        registered_trace_coordinates_px=queried_traces,
                        longitudinal_support_domain_groups_px=(domains,),
                        top_bindings=(side(BoundaryRole.TOP, 100.0, top_regions),),
                        bottom_bindings=(side(BoundaryRole.BOTTOM, 340.0, bottom_regions),),
                    ))
                    if top_regions == bottom_regions == 1:
                        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
                        self.assertIsNotNone(result.best)
                    else:
                        # A genuine source-wide side may still infer fixed H,
                        # but the one-region opposite cannot own native height.
                        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
                        self.assertFalse(result.best.direct_pair)
                        self.assertEqual(len(result.best.direct_bindings), 1)
                        self.assertEqual(result.best.direct_bindings[0].independent_support_region_count, 3)

    def test_independently_authorized_local_outward_line_remains_counterevidence(self) -> None:
            queried = tuple(range(0, 120, 10))
            result = fit_template_cross(aspect_input(
                template=template(count=3), fixed_height_px=FiniteInterval(230.0, 250.0),
                registered_trace_coordinates_px=queried,
                longitudinal_support_domain_groups_px=(tuple(
                    FiniteInterval(float(start), float(start + 5)) for start in (0, 10, 20)
                ),),
                top_bindings=(
                    binding(BoundaryRole.TOP, "complete-top", 100.0,
                            traces=queried, independent_regions=3, source_spanning=False),
                    binding(BoundaryRole.TOP, "local-outward-top", 95.0,
                            traces=(0, 40), independent_regions=2, source_spanning=False),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "complete-bottom", 340.0,
                            traces=queried, independent_regions=3, source_spanning=False),
                ),
            ))
            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertEqual(result.failure_kind, CrossFailureKind.OUTWARD_ROLE_COUNTEREVIDENCE)
