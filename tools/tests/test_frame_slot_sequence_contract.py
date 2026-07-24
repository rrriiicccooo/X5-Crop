from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.support.architecture import PROJECT_ROOT
from tools.tests.support.physical_gates import candidate_fixture
from x5crop.detection.candidate.proposal.sequence import (
    holder_boundaries_without_reliable_content_crossing,
)
from x5crop.detection.physical.model import (
    BoundaryAnchor,
    BoundaryGeometryState,
    BoundaryRoleAuthority,
    FrameBoundarySource,
    ResolvedFrameBoundary,
)
from x5crop.detection.physical.short_axis import (
    SharedShortAxisOutcome,
    SharedShortAxisPlan,
)
from tools.tests.support.photo_edges import (
    photo_edge_pair_fixture,
    shared_short_axis_fixture,
    shared_short_axis_fixture_from_edges,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryPathSample,
    BoundarySide,
    Box,
    ContainmentFallback,
    EvidenceState,
    FrameSequenceSearchScope,
    GrayAppearanceObservation,
    GrayBoundaryPathObservation,
    GrayIntensityTail,
    HolderBoundaryObservation,
    HolderSafetyEnvelope,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhysicalSearchFact,
    PixelInterval,
)
from x5crop.image.content import ContentRegionObservation


def _provenance(name: str) -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
        observation_id=ObservationId(name),
        dependencies=(MeasurementIdentity.GRAY_WORK,),
        description="synthetic measured boundary path",
    )


def _appearance(
    provenance: MeasurementProvenance,
    *,
    active: bool,
) -> GrayAppearanceObservation:
    return GrayAppearanceObservation(
        intensity_median=96.0 if active else 8.0,
        intensity_mad=2.0,
        texture_median=4.0 if active else 0.25,
        gradient_median=8.0 if active else 0.5,
        spatial_continuity=1.0,
        intensity_tail=(
            GrayIntensityTail.MIDRANGE if active else GrayIntensityTail.LOW
        ),
        provenance=provenance,
    )


def _short_path(
    side: BoundarySide,
    position: float,
    name: str,
    *,
    photo_inside: bool,
) -> GrayBoundaryPathObservation:
    provenance = _provenance(name)
    outer = _appearance(provenance, active=False)
    inner = _appearance(provenance, active=photo_inside)
    lower, upper = (outer, inner) if side == BoundarySide.TOP else (inner, outer)
    return GrayBoundaryPathObservation(
        axis=BoundaryAxis.SHORT,
        kind=(
            BoundaryKind.TONAL_TRANSITION
            if photo_inside
            else BoundaryKind.EDGE_ADJACENT_TRANSITION
        ),
        samples=(
            BoundaryPathSample(
                PixelInterval(0.0, 1_000.0),
                PixelInterval.exact(position),
            ),
        ),
        lower_appearance=lower,
        upper_appearance=upper,
        provenance=provenance,
    )


def _long_holder(side: BoundarySide, position: float) -> HolderBoundaryObservation:
    provenance = _provenance(f"holder_{side.value}")
    appearance = _appearance(provenance, active=False)
    path = GrayBoundaryPathObservation(
        axis=BoundaryAxis.LONG,
        kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        samples=(
            BoundaryPathSample(
                PixelInterval(0.0, 200.0),
                PixelInterval.exact(position),
            ),
        ),
        lower_appearance=appearance,
        upper_appearance=appearance,
        provenance=provenance,
    )
    return HolderBoundaryObservation(side, path.position, (path,))


def _search_scope(
    *,
    top: GrayBoundaryPathObservation | None,
    bottom: GrayBoundaryPathObservation | None,
) -> FrameSequenceSearchScope:
    paths = tuple(path for path in (top, bottom) if path is not None)
    return FrameSequenceSearchScope(
        holder_safety=HolderSafetyEnvelope(
            (),
            ContainmentFallback(
                Box(0, 0, 1_000, 200),
                MeasurementProvenance(
                    MeasurementIdentity.CANVAS,
                    ObservationId("canvas_containment"),
                    (),
                    "synthetic canvas containment",
                ),
            ),
        ),
        raw_boundary_paths=paths,
        provenance=_provenance("short_axis_scope"),
    )


class FrameSlotSequenceContractTest(unittest.TestCase):
    def test_reliable_content_refutes_only_crossed_long_axis_holder_boundary(
        self,
    ) -> None:
        leading = _long_holder(BoundarySide.LEADING, 20.0)
        trailing = _long_holder(BoundarySide.TRAILING, 900.0)
        top_path = _short_path(
            BoundarySide.TOP,
            20.0,
            "top_holder",
            photo_inside=False,
        )
        top = HolderBoundaryObservation(
            BoundarySide.TOP,
            top_path.position,
            (top_path,),
        )
        content = ContentRegionObservation(
            Box(0, 0, 1_000, 200),
            ((850, 980),),
            10,
        )

        retained = holder_boundaries_without_reliable_content_crossing(
            (leading, trailing, top),
            content,
        )

        self.assertEqual(retained, (leading, top))

    def test_canvas_fallback_is_containment_not_resolved_geometry(self) -> None:
        envelope = _search_scope(top=None, bottom=None).holder_safety

        self.assertEqual(envelope.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(envelope.box, Box(0, 0, 1_000, 200))

    def test_boundary_identity_is_assigned_after_raw_path_measurement(self) -> None:
        path = _long_holder(BoundarySide.LEADING, 100.0).supporting_paths[0]
        self.assertFalse(hasattr(path, "physical_role"))
        anchor = BoundaryAnchor(
            observation=path,
            physical_role=BoundarySide.LEADING,
            role_state=EvidenceState.SUPPORTED,
            role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
            role_provenance=path.provenance,
        )
        boundary = ResolvedFrameBoundary(
            position=path.position,
            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            geometry_state=BoundaryGeometryState.RESOLVED,
            boundary_anchor=anchor,
            inference_provenance=None,
        )

        self.assertTrue(boundary.independently_observed)
        self.assertIs(boundary.boundary_anchor.observation, path)

    def test_two_photo_inner_edges_resolve_the_only_shared_short_axis(self) -> None:
        top = _short_path(
            BoundarySide.TOP,
            20.0,
            "top_photo_edge",
            photo_inside=True,
        )
        bottom = _short_path(
            BoundarySide.BOTTOM,
            180.0,
            "bottom_photo_edge",
            photo_inside=True,
        )

        plan = shared_short_axis_fixture(_search_scope(top=top, bottom=bottom))
        evidence = photo_edge_pair_fixture(top, bottom)

        self.assertIsInstance(plan, SharedShortAxisPlan)
        self.assertTrue(plan.supports_safe_crop)
        self.assertEqual(plan.photo_edge_pair_id, evidence.observation_id)
        self.assertEqual(plan.top, PixelInterval.exact(20.0))
        self.assertEqual(plan.bottom, PixelInterval.exact(180.0))

    def test_equivalent_duplicate_paths_do_not_create_false_ambiguity(self) -> None:
        paths = (
            _short_path(BoundarySide.TOP, 20.0, "top_photo_edge_a", photo_inside=True),
            _short_path(BoundarySide.TOP, 20.0, "top_photo_edge_b", photo_inside=True),
            _short_path(BoundarySide.BOTTOM, 180.0, "bottom_photo_edge_a", photo_inside=True),
            _short_path(BoundarySide.BOTTOM, 180.0, "bottom_photo_edge_b", photo_inside=True),
        )
        search_scope = replace(
            _search_scope(top=None, bottom=None),
            raw_boundary_paths=paths,
        )

        plan = shared_short_axis_fixture(search_scope)

        self.assertTrue(plan.supports_safe_crop)

    def test_distinct_photo_edge_pair_hypotheses_remain_unresolved(self) -> None:
        paths = (
            _short_path(BoundarySide.TOP, 20.0, "top_photo_edge_a", photo_inside=True),
            _short_path(BoundarySide.TOP, 40.0, "top_photo_edge_b", photo_inside=True),
            _short_path(BoundarySide.BOTTOM, 160.0, "bottom_photo_edge_a", photo_inside=True),
            _short_path(BoundarySide.BOTTOM, 180.0, "bottom_photo_edge_b", photo_inside=True),
        )
        search_scope = replace(
            _search_scope(top=None, bottom=None),
            raw_boundary_paths=paths,
        )

        plan = shared_short_axis_fixture(search_scope)

        self.assertFalse(plan.supports_safe_crop)
        self.assertEqual(
            plan.outcome,
            SharedShortAxisOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE,
        )

    def test_single_edge_never_manufactures_containment_coordinates(self) -> None:
        top = _short_path(
            BoundarySide.TOP,
            20.0,
            "single_top_photo_edge",
            photo_inside=True,
        )

        plan = shared_short_axis_fixture(_search_scope(top=top, bottom=None))

        self.assertFalse(plan.supports_safe_crop)
        self.assertIsNone(plan.span)
        self.assertIn(
            PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,
            plan.physical_search.facts,
        )

    def test_holder_edges_cannot_resolve_shared_short_axis(self) -> None:
        top = _short_path(
            BoundarySide.TOP,
            20.0,
            "holder_top",
            photo_inside=False,
        )
        bottom = _short_path(
            BoundarySide.BOTTOM,
            180.0,
            "holder_bottom",
            photo_inside=False,
        )

        plan = shared_short_axis_fixture(_search_scope(top=top, bottom=bottom))

        self.assertFalse(plan.supports_safe_crop)
        self.assertEqual(
            plan.outcome,
            SharedShortAxisOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE,
        )

        with self.assertRaises(ValueError):
            shared_short_axis_fixture_from_edges(top, bottom)

    def test_shared_short_axis_references_pair_without_copying_edges(
        self,
    ) -> None:
        top = _short_path(
            BoundarySide.TOP,
            20.0,
            "top_photo_edge_for_reference_contract",
            photo_inside=True,
        )
        bottom = _short_path(
            BoundarySide.BOTTOM,
            180.0,
            "bottom_photo_edge_for_reference_contract",
            photo_inside=True,
        )
        evidence = photo_edge_pair_fixture(top, bottom)
        plan = shared_short_axis_fixture_from_edges(top, bottom)

        self.assertEqual(plan.photo_edge_pair_id, evidence.observation_id)
        self.assertNotIn(
            "top_photo_edge",
            SharedShortAxisPlan.__dataclass_fields__,
        )
        self.assertNotIn(
            "bottom_photo_edge",
            SharedShortAxisPlan.__dataclass_fields__,
        )

    def test_every_frame_crop_reuses_one_shared_short_axis_fixture(self) -> None:
        geometry = candidate_fixture().geometry
        plan = geometry.shared_short_axis

        self.assertTrue(plan.supports_safe_crop)
        self.assertTrue(
            all(
                envelope.box.top == int(plan.top.minimum)
                and envelope.box.bottom == int(plan.bottom.maximum)
                for envelope in geometry.frame_crop_envelopes
            )
        )

    def test_superseded_short_axis_models_and_resolvers_are_absent(self) -> None:
        physical_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT_ROOT / "x5crop/detection/physical").rglob("*.py")
        )
        for removed in (
            "SharedShortAxisSafetySpan",
            "SharedShortAxisBasis",
            "PhotoHeightEvidence",
            "resolve_photo_height_evidence",
            "resolve_shared_short_axis",
            "holder_edge_bounded",
        ):
            with self.subTest(removed=removed):
                self.assertNotIn(removed, physical_source)


if __name__ == "__main__":
    unittest.main()
