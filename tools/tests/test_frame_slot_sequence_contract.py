from __future__ import annotations

from dataclasses import replace
import unittest

from x5crop.detection.physical.model import (
    BoundaryAnchor,
    BoundaryGeometryState,
    BoundaryRoleAuthority,
    CommonFrameWidthResolution,
    FrameContentOccupancy,
    FrameSlot,
    FrameWidthMeasurementConstraint,
    FrameBoundarySource,
    ResolvedFrameBoundary,
    PhotoHeightEvidence,
    SharedShortAxisBasis,
    SharedShortAxisSafetySpan,
)
from x5crop.detection.physical.sequence_completion import infer_sequence_frame_slot
from x5crop.detection.physical import frame_sequence_common_width as common_width
from x5crop.detection.physical import frame_sequence_solver as solver_module
from x5crop.detection.physical.frame_sequence_solver import (
    solve_frame_sequence,
)
from x5crop.detection.physical.frame_sequence_result import FrameSequenceSolveResult
from x5crop.detection.physical.short_axis import (
    resolve_photo_height_evidence,
    resolve_shared_short_axis,
    shared_short_axis_plan,
)
from tools.tests.frame_slot_solver_support import (
    content as solver_content,
    dimensions as solver_dimensions,
    separator as solver_separator,
    sequence_search_index as solver_search_index,
    scope as solver_scope,
)
from tools.tests.physical_gate_support import candidate_fixture
from x5crop.image.content import ContentRegionObservation
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryPathSample,
    BoundarySide,
    Box,
    ContainmentFallback,
    EvidenceState,
    GrayAppearanceObservation,
    GrayBoundaryPathObservation,
    GrayIntensityTail,
    HolderBoundaryObservation,
    HolderSafetyEnvelope,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    FrameSequenceSearchScope,
    PixelInterval,
)


def _provenance(name: str) -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
        observation_id=ObservationId(name),
        dependencies=(),
        description=name,
    )


def _holder_safety(
    box: Box,
    boundaries: tuple[HolderBoundaryObservation, ...] = (),
) -> HolderSafetyEnvelope:
    return HolderSafetyEnvelope(
        boundaries,
        ContainmentFallback(box, _provenance("holder_safety_fallback")),
    )


def _path(
    axis: BoundaryAxis,
    position: float,
    name: str,
    *,
    kind: BoundaryKind,
) -> GrayBoundaryPathObservation:
    provenance = _provenance(name)
    appearance = GrayAppearanceObservation(
        intensity_median=64.0,
        intensity_mad=1.0,
        texture_median=1.0,
        gradient_median=1.0,
        spatial_continuity=1.0,
        intensity_tail=GrayIntensityTail.MIDRANGE,
        provenance=provenance,
    )
    return GrayBoundaryPathObservation(
        axis=axis,
        kind=kind,
        samples=(
            BoundaryPathSample(
                PixelInterval(0.0, 1000.0),
                PixelInterval.exact(position),
            ),
        ),
        lower_appearance=appearance,
        upper_appearance=appearance,
        provenance=provenance,
    )


def _search_scope(*, holder_bounded: bool) -> FrameSequenceSearchScope:
    kind = (
        BoundaryKind.EDGE_ADJACENT_TRANSITION
        if holder_bounded
        else BoundaryKind.TONAL_TRANSITION
    )
    top = _path(BoundaryAxis.SHORT, 20.0, "top_path", kind=kind)
    bottom = _path(BoundaryAxis.SHORT, 180.0, "bottom_path", kind=kind)
    leading = _path(
        BoundaryAxis.LONG,
        10.0,
        "leading_path",
        kind=BoundaryKind.TONAL_TRANSITION,
    )
    trailing = _path(
        BoundaryAxis.LONG,
        990.0,
        "trailing_path",
        kind=BoundaryKind.TONAL_TRANSITION,
    )
    fallback_provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.CANVAS,
        observation_id=ObservationId("containment"),
        dependencies=(MeasurementIdentity.CANVAS,),
        description="synthetic containment",
    )
    holder_boundaries = (
        (
            HolderBoundaryObservation(BoundarySide.TOP, top.position, (top,)),
            HolderBoundaryObservation(
                BoundarySide.BOTTOM,
                bottom.position,
                (bottom,),
            ),
        )
        if holder_bounded
        else ()
    )
    return FrameSequenceSearchScope(
        holder_safety=HolderSafetyEnvelope(
            holder_boundaries,
            ContainmentFallback(
                Box(0, 0, 1000, 200),
                fallback_provenance,
            ),
        ),
        raw_boundary_paths=(leading, trailing, top, bottom),
        provenance=_provenance("search_scope"),
    )


def _boundary(
    name: str,
    position: float,
    side: BoundarySide,
    *,
    source: FrameBoundarySource = FrameBoundarySource.GRAY_PATH_OBSERVATION,
    role_state: EvidenceState = EvidenceState.SUPPORTED,
    geometry_state: BoundaryGeometryState = BoundaryGeometryState.RESOLVED,
) -> ResolvedFrameBoundary:
    provenance = _provenance(name)
    if source == FrameBoundarySource.GRAY_PATH_OBSERVATION:
        observation = _path(
            BoundaryAxis.LONG,
            position,
            name,
            kind=BoundaryKind.TONAL_TRANSITION,
        )
        anchor = BoundaryAnchor(
            observation,
            side,
            role_state,
            (
                BoundaryRoleAuthority.DIRECT_MEASUREMENT
                if role_state == EvidenceState.SUPPORTED
                else BoundaryRoleAuthority.UNAVAILABLE
            ),
            provenance,
        )
        inference_provenance = None
    else:
        if role_state == EvidenceState.SUPPORTED:
            raise ValueError("inferred boundary cannot claim measurement support")
        anchor = None
        inference_provenance = provenance
    return ResolvedFrameBoundary(
        position=PixelInterval.exact(position),
        source=source,
        geometry_state=geometry_state,
        boundary_anchor=anchor,
        inference_provenance=inference_provenance,
    )


def _visible_content() -> ContentRegionObservation:
    return ContentRegionObservation(Box(0, 0, 1000, 200), (), 0)


def _real_slot(index: int, start: float, end: float) -> FrameSlot:
    return FrameSlot(
        index=index,
        visible_long_axis=PixelInterval(start, end),
        leading=_boundary(f"frame_{index}_leading", start, BoundarySide.LEADING),
        trailing=_boundary(f"frame_{index}_trailing", end, BoundarySide.TRAILING),
        content_occupancy=FrameContentOccupancy.CONTENT_OBSERVED,
        edge_occlusion=None,
    )


def _common_width(*slots: FrameSlot) -> CommonFrameWidthResolution:
    return CommonFrameWidthResolution(
        width_px=PixelInterval.exact(100.0),
        constraints=tuple(
            FrameWidthMeasurementConstraint(
                slot.index,
                slot.leading,
                slot.trailing,
            )
            for slot in slots
        ),
        physical_scale_constraint=None,
        state=EvidenceState.SUPPORTED,
        provenance=_provenance("common_width"),
    )


def _long_holder_boundary(
    side: BoundarySide,
    position: float,
) -> HolderBoundaryObservation:
    path = _path(
        BoundaryAxis.LONG,
        position,
        f"holder_{side.value}",
        kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
    )
    return HolderBoundaryObservation(side, path.position, (path,))


class FrameSlotSequenceContractTest(unittest.TestCase):
    def test_canvas_fallback_is_not_resolved_holder_geometry(self) -> None:
        provenance = _provenance("holder_canvas_fallback")
        envelope = HolderSafetyEnvelope(
            boundaries=(),
            containment_fallback=ContainmentFallback(
                Box(0, 0, 1000, 200),
                provenance,
            ),
        )

        self.assertEqual(envelope.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(envelope.box, Box(0, 0, 1000, 200))

    def test_boundary_identity_is_assigned_after_raw_path_measurement(self) -> None:
        path = _path(
            BoundaryAxis.LONG,
            100.0,
            "candidate_specific_edge",
            kind=BoundaryKind.TONAL_TRANSITION,
        )
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
        self.assertEqual(boundary.role_state, EvidenceState.SUPPORTED)
        self.assertIs(boundary.boundary_anchor.observation, path)

    def test_short_axis_is_resolved_once_from_holder_inner_edges(self) -> None:
        search_scope = _search_scope(holder_bounded=True)

        resolved = resolve_shared_short_axis(search_scope)

        self.assertEqual(
            resolved.basis,
            SharedShortAxisBasis.HOLDER_EDGE_BOUNDED,
        )
        self.assertEqual(resolved.top, PixelInterval.exact(20.0))
        self.assertEqual(resolved.bottom, PixelInterval.exact(180.0))
        self.assertTrue(resolved.supports_safe_crop)

    def test_one_holder_edge_and_opposite_canvas_form_safe_short_axis(self) -> None:
        search_scope = _search_scope(holder_bounded=True)
        bottom = search_scope.holder_safety.boundary(BoundarySide.BOTTOM)
        assert bottom is not None
        search_scope = replace(
            search_scope,
            holder_safety=HolderSafetyEnvelope(
                (bottom,),
                search_scope.holder_safety.containment_fallback,
            ),
        )

        resolved = resolve_shared_short_axis(search_scope)

        self.assertEqual(resolved.basis, SharedShortAxisBasis.HOLDER_EDGE_BOUNDED)
        self.assertEqual(resolved.top, PixelInterval.exact(0.0))
        self.assertEqual(resolved.bottom, PixelInterval.exact(180.0))
        self.assertTrue(resolved.supports_safe_crop)

    def test_crossed_holder_interpretations_choose_larger_safe_span(self) -> None:
        top_path = _path(
            BoundaryAxis.SHORT,
            195.0,
            "crossed_top_holder",
            kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        )
        bottom_path = _path(
            BoundaryAxis.SHORT,
            193.0,
            "crossed_bottom_holder",
            kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        )
        search_scope = _search_scope(holder_bounded=False)
        search_scope = replace(
            search_scope,
            holder_safety=HolderSafetyEnvelope(
                (
                    HolderBoundaryObservation(
                        BoundarySide.TOP,
                        top_path.position,
                        (top_path,),
                    ),
                    HolderBoundaryObservation(
                        BoundarySide.BOTTOM,
                        bottom_path.position,
                        (bottom_path,),
                    ),
                ),
                search_scope.holder_safety.containment_fallback,
            ),
            raw_boundary_paths=(
                *search_scope.raw_boundary_paths,
                top_path,
                bottom_path,
            ),
        )

        resolved = resolve_shared_short_axis(search_scope)

        self.assertEqual(
            search_scope.holder_safety.box,
            Box(0, 0, 1000, 193),
        )
        self.assertEqual(resolved.top, PixelInterval.exact(0.0))
        self.assertEqual(resolved.bottom, PixelInterval.exact(193.0))
        self.assertTrue(resolved.supports_safe_crop)

    def test_safe_short_axis_is_clamped_to_canvas_not_holder_interpretation(
        self,
    ) -> None:
        geometry = candidate_fixture().geometry
        top_path = _path(
            BoundaryAxis.SHORT,
            93.0,
            "broad_top_holder_interpretation",
            kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        )
        top_path = replace(
            top_path,
            samples=(
                BoundaryPathSample(
                    top_path.orthogonal_extent,
                    PixelInterval(90.0, 96.0),
                ),
            ),
        )
        bottom_path = _path(
            BoundaryAxis.SHORT,
            96.0,
            "broad_bottom_holder_interpretation",
            kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        )
        bottom_path = replace(
            bottom_path,
            samples=(
                BoundaryPathSample(
                    bottom_path.orthogonal_extent,
                    PixelInterval(93.0, 99.0),
                ),
            ),
        )
        long_boundaries = tuple(
            boundary
            for boundary in geometry.holder_safety.boundaries
            if boundary.side in {BoundarySide.LEADING, BoundarySide.TRAILING}
        )
        holder_safety = HolderSafetyEnvelope(
            (
                *long_boundaries,
                HolderBoundaryObservation(
                    BoundarySide.TOP,
                    top_path.position,
                    (top_path,),
                ),
                HolderBoundaryObservation(
                    BoundarySide.BOTTOM,
                    bottom_path.position,
                    (bottom_path,),
                ),
            ),
            geometry.holder_safety.containment_fallback,
        )
        safe_short_axis = SharedShortAxisSafetySpan(
            top=PixelInterval.exact(0.0),
            bottom=bottom_path.position,
            basis=SharedShortAxisBasis.HOLDER_EDGE_BOUNDED,
            state=EvidenceState.SUPPORTED,
            provenance=bottom_path.provenance,
        )

        updated = replace(
            geometry,
            holder_safety=holder_safety,
            shared_short_axis=safe_short_axis,
            raw_boundary_paths=(
                *geometry.raw_boundary_paths,
                top_path,
                bottom_path,
            ),
        )

        self.assertEqual(updated.shared_short_axis, safe_short_axis)

    def test_generic_paths_do_not_become_photo_height_evidence(self) -> None:
        search_scope = _search_scope(holder_bounded=False)

        safety = resolve_shared_short_axis(search_scope)
        photo_height = resolve_photo_height_evidence(search_scope)

        self.assertEqual(
            safety.basis,
            SharedShortAxisBasis.CONTAINMENT_FALLBACK,
        )
        self.assertFalse(safety.supports_safe_crop)
        self.assertIsInstance(photo_height, PhotoHeightEvidence)
        self.assertEqual(photo_height.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(photo_height.height_px)

    def test_strip_wide_inner_paths_do_not_claim_photo_edge_identity(self) -> None:
        search_scope = _search_scope(holder_bounded=True)
        top_photo = _path(
            BoundaryAxis.SHORT,
            30.0,
            "top_photo_edge",
            kind=BoundaryKind.TONAL_TRANSITION,
        )
        bottom_photo = _path(
            BoundaryAxis.SHORT,
            170.0,
            "bottom_photo_edge",
            kind=BoundaryKind.TONAL_TRANSITION,
        )
        search_scope = replace(
            search_scope,
            raw_boundary_paths=(
                *search_scope.raw_boundary_paths,
                top_photo,
                bottom_photo,
            ),
        )

        safety = resolve_shared_short_axis(search_scope)
        photo_height = resolve_photo_height_evidence(search_scope)

        self.assertEqual(safety.basis, SharedShortAxisBasis.HOLDER_EDGE_BOUNDED)
        self.assertEqual(safety.top, PixelInterval.exact(20.0))
        self.assertEqual(safety.bottom, PixelInterval.exact(180.0))
        self.assertEqual(photo_height.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(photo_height.height_px)

    def test_two_holder_to_active_image_contacts_support_photo_height(self) -> None:
        search_scope = _search_scope(holder_bounded=True)
        by_side = {
            boundary.side: boundary
            for boundary in search_scope.holder_safety.boundaries
        }

        def appearance(
            path: GrayBoundaryPathObservation,
            *,
            intensity: float,
            texture: float,
            gradient: float,
            tail: GrayIntensityTail,
        ) -> GrayAppearanceObservation:
            return GrayAppearanceObservation(
                intensity_median=intensity,
                intensity_mad=0.0,
                texture_median=texture,
                gradient_median=gradient,
                spatial_continuity=1.0,
                intensity_tail=tail,
                provenance=path.provenance,
            )

        top_path = by_side[BoundarySide.TOP].supporting_paths[0]
        bottom_path = by_side[BoundarySide.BOTTOM].supporting_paths[0]
        top_path = replace(
            top_path,
            lower_appearance=appearance(
                top_path,
                intensity=255.0,
                texture=0.0,
                gradient=0.0,
                tail=GrayIntensityTail.HIGH,
            ),
            upper_appearance=appearance(
                top_path,
                intensity=96.0,
                texture=12.0,
                gradient=2.0,
                tail=GrayIntensityTail.MIDRANGE,
            ),
        )
        bottom_path = replace(
            bottom_path,
            lower_appearance=appearance(
                bottom_path,
                intensity=96.0,
                texture=12.0,
                gradient=2.0,
                tail=GrayIntensityTail.MIDRANGE,
            ),
            upper_appearance=appearance(
                bottom_path,
                intensity=255.0,
                texture=0.0,
                gradient=0.0,
                tail=GrayIntensityTail.HIGH,
            ),
        )
        holder_safety = HolderSafetyEnvelope(
            (
                HolderBoundaryObservation(
                    BoundarySide.TOP,
                    top_path.position,
                    (top_path,),
                ),
                HolderBoundaryObservation(
                    BoundarySide.BOTTOM,
                    bottom_path.position,
                    (bottom_path,),
                ),
            ),
            search_scope.holder_safety.containment_fallback,
        )
        search_scope = replace(
            search_scope,
            holder_safety=holder_safety,
            raw_boundary_paths=(
                *tuple(
                    path
                    for path in search_scope.raw_boundary_paths
                    if path.axis != BoundaryAxis.SHORT
                ),
                top_path,
                bottom_path,
            ),
        )

        plan = shared_short_axis_plan(search_scope)

        self.assertEqual(plan.span.basis, SharedShortAxisBasis.PHOTO_EDGE_BOUNDED)
        self.assertEqual(plan.photo_height_evidence.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            plan.photo_height_evidence.height_px,
            PixelInterval.exact(160.0),
        )

    def test_repeated_inner_gray_paths_do_not_prove_photo_height(self) -> None:
        search_scope = _search_scope(holder_bounded=True)

        def active_contact_path(
            position: PixelInterval,
            name: str,
            *,
            top: bool,
            active_gradient: float = 2.0,
        ) -> GrayBoundaryPathObservation:
            path = _path(
                BoundaryAxis.SHORT,
                position.midpoint,
                name,
                kind=BoundaryKind.TONAL_TRANSITION,
            )
            path = replace(
                path,
                samples=(
                    BoundaryPathSample(
                        path.orthogonal_extent,
                        position,
                    ),
                ),
            )
            quiet = GrayAppearanceObservation(
                intensity_median=20.0,
                intensity_mad=1.0,
                texture_median=2.0,
                gradient_median=0.5,
                spatial_continuity=1.0,
                intensity_tail=GrayIntensityTail.LOW,
                provenance=path.provenance,
            )
            active = GrayAppearanceObservation(
                intensity_median=96.0,
                intensity_mad=4.0,
                texture_median=12.0,
                gradient_median=active_gradient,
                spatial_continuity=1.0,
                intensity_tail=GrayIntensityTail.MIDRANGE,
                provenance=path.provenance,
            )
            return replace(
                path,
                lower_appearance=quiet if top else active,
                upper_appearance=active if top else quiet,
            )

        paths = (
            active_contact_path(PixelInterval(30.0, 32.0), "top_photo_a", top=True),
            active_contact_path(
                PixelInterval(31.0, 33.0),
                "top_photo_b",
                top=True,
                active_gradient=0.25,
            ),
            active_contact_path(
                PixelInterval(167.0, 170.0),
                "bottom_photo_a",
                top=False,
            ),
            active_contact_path(
                PixelInterval(168.0, 171.0),
                "bottom_photo_b",
                top=False,
            ),
        )
        search_scope = replace(
            search_scope,
            raw_boundary_paths=(*search_scope.raw_boundary_paths, *paths),
        )

        plan = shared_short_axis_plan(search_scope)

        self.assertEqual(plan.span.basis, SharedShortAxisBasis.HOLDER_EDGE_BOUNDED)
        self.assertEqual(plan.span.top, PixelInterval.exact(20.0))
        self.assertEqual(plan.span.bottom, PixelInterval.exact(180.0))
        self.assertEqual(plan.photo_height_evidence.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(plan.photo_height_evidence.height_px)

    def test_every_frame_slot_reuses_one_shared_short_axis_span(self) -> None:
        short_axis = SharedShortAxisSafetySpan(
            top=PixelInterval.exact(10.0),
            bottom=PixelInterval.exact(90.0),
            basis=SharedShortAxisBasis.HOLDER_EDGE_BOUNDED,
            state=EvidenceState.SUPPORTED,
            provenance=_provenance("short_axis"),
        )
        first = FrameSlot(
            index=1,
            visible_long_axis=PixelInterval(0.0, 100.0),
            leading=_boundary("first_leading", 0.0, BoundarySide.LEADING),
            trailing=_boundary("first_trailing", 100.0, BoundarySide.TRAILING),
            content_occupancy=FrameContentOccupancy.CONTENT_OBSERVED,
            edge_occlusion=None,
        )
        second = FrameSlot(
            index=2,
            visible_long_axis=PixelInterval(110.0, 210.0),
            leading=_boundary("second_leading", 110.0, BoundarySide.LEADING),
            trailing=_boundary("second_trailing", 210.0, BoundarySide.TRAILING),
            content_occupancy=FrameContentOccupancy.UNAVAILABLE,
            edge_occlusion=None,
        )

        first_envelope = first.crop_envelope(short_axis)
        second_envelope = second.crop_envelope(short_axis)
        self.assertTrue(first_envelope.box.valid())
        self.assertEqual(first_envelope.box.top, 10)
        self.assertEqual(second_envelope.box.bottom, 90)

    def test_holder_bounded_span_is_safe_but_not_photo_height_evidence(self) -> None:
        span = SharedShortAxisSafetySpan(
            top=PixelInterval.exact(5.0),
            bottom=PixelInterval.exact(95.0),
            basis=SharedShortAxisBasis.HOLDER_EDGE_BOUNDED,
            state=EvidenceState.SUPPORTED,
            provenance=_provenance("holder_short_axis"),
        )
        photo_height = PhotoHeightEvidence(
            height_px=None,
            state=EvidenceState.UNAVAILABLE,
            provenance=span.provenance,
        )

        self.assertTrue(span.supports_safe_crop)
        self.assertEqual(photo_height.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(span.basis, SharedShortAxisBasis.HOLDER_EDGE_BOUNDED)

    def test_dimension_boundary_can_resolve_geometry_without_becoming_measurement(self) -> None:
        boundary = _boundary(
            "dimension_boundary",
            100.0,
            BoundarySide.LEADING,
            source=FrameBoundarySource.DIMENSION_CONSTRAINED,
            role_state=EvidenceState.UNAVAILABLE,
        )

        self.assertTrue(boundary.geometry_resolved)
        self.assertFalse(boundary.independently_observed)

    def test_dimension_boundary_cannot_claim_independent_measurement(self) -> None:
        with self.assertRaises(ValueError):
            _boundary(
                "invalid_dimension_boundary",
                100.0,
                BoundarySide.LEADING,
                source=FrameBoundarySource.DIMENSION_CONSTRAINED,
                role_state=EvidenceState.SUPPORTED,
            )

    def test_one_measured_internal_slot_requires_independent_scale(
        self,
    ) -> None:
        search_scope = solver_scope(
            width=320,
            height=120,
            leading=0.0,
            trailing=320.0,
            top=10.0,
            bottom=110.0,
            holder_sides=(
                BoundarySide.LEADING,
                BoundarySide.TRAILING,
                BoundarySide.TOP,
                BoundarySide.BOTTOM,
            ),
            holder_positions={
                BoundarySide.LEADING: 0.0,
                BoundarySide.TRAILING: 320.0,
                BoundarySide.TOP: 10.0,
                BoundarySide.BOTTOM: 110.0,
            },
        )
        plan = shared_short_axis_plan(search_scope)
        plan = replace(
            plan,
            photo_height_evidence=PhotoHeightEvidence(
                height_px=PixelInterval(99.0, 101.0),
                state=EvidenceState.SUPPORTED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.PHOTO_EDGES,
                    ObservationId("independent_photo_height"),
                    (MeasurementIdentity.BOUNDARY_PATHS,),
                    "independently measured photo height",
                ),
            ),
        )
        supports = (
            solver_separator(100.0, 110.0, plan, supported=True),
            solver_separator(210.0, 220.0, plan, supported=True),
        )

        solved = solve_frame_sequence(
            solver_search_index(search_scope, supports),
            search_scope,
            plan,
            3,
            solver_dimensions(1.0, 1.0),
            solver_content(
                width=320,
                height=120,
                runs=((0, 100), (110, 210), (220, 320)),
            ),
            100_000,
            strip_mode="full",
            nominal_count=3,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(
            tuple(
                constraint.frame_index
                for constraint in solved.common_frame_width.constraints
            ),
            (2,),
        )
        self.assertIsNotNone(
            solved.common_frame_width.physical_scale_constraint,
        )
        self.assertEqual(
            solved.common_frame_width.state,
            EvidenceState.SUPPORTED,
        )

    def test_independent_scale_and_separator_anchor_corroborate_photo_edge(
        self,
    ) -> None:
        search_scope = solver_scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
            holder_sides=(BoundarySide.TOP, BoundarySide.BOTTOM),
        )
        plan = shared_short_axis_plan(search_scope)
        plan = replace(
            plan,
            photo_height_evidence=PhotoHeightEvidence(
                height_px=PixelInterval(99.0, 101.0),
                state=EvidenceState.SUPPORTED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.PHOTO_EDGES,
                    ObservationId("independent_photo_height_with_anchor"),
                    (MeasurementIdentity.BOUNDARY_PATHS,),
                    "independently measured photo height",
                ),
            ),
        )
        support = solver_separator(100.0, 110.0, plan, supported=True)

        solved = solve_frame_sequence(
            solver_search_index(search_scope, (support,)),
            search_scope,
            plan,
            2,
            solver_dimensions(1.0, 1.0),
            solver_content(
                width=210,
                height=120,
                runs=((0, 100), (110, 210)),
            ),
            100_000,
            strip_mode="full",
            nominal_count=2,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.SUPPORTED)
        self.assertTrue(
            solved.frame_slots[0].leading.position_independently_observed
        )
        self.assertFalse(solved.frame_slots[0].leading.independently_observed)
        self.assertTrue(solved.frame_slots[0].trailing.independently_observed)
        self.assertEqual(len(solved.separator_assignments), 1)

    def test_independent_scale_without_slot_constraint_stays_unavailable(
        self,
    ) -> None:
        search_scope = solver_scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
            holder_sides=(BoundarySide.TOP, BoundarySide.BOTTOM),
        )
        plan = shared_short_axis_plan(search_scope)
        plan = replace(
            plan,
            photo_height_evidence=PhotoHeightEvidence(
                height_px=PixelInterval(99.0, 101.0),
                state=EvidenceState.SUPPORTED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.PHOTO_EDGES,
                    ObservationId("independent_photo_height_without_anchor"),
                    (MeasurementIdentity.BOUNDARY_PATHS,),
                    "independently measured photo height",
                ),
            ),
        )

        solved = solve_frame_sequence(
            solver_search_index(search_scope),
            search_scope,
            plan,
            2,
            solver_dimensions(1.0, 1.0),
            solver_content(width=210, height=120),
            100_000,
            strip_mode="full",
            nominal_count=2,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.UNAVAILABLE)

    def test_independent_physical_scale_prunes_infeasible_width_search(self) -> None:
        search_scope = solver_scope(
            width=650,
            height=120,
            leading=0.0,
            trailing=650.0,
            top=10.0,
            bottom=110.0,
            internal_paths=tuple(float(position) for position in range(20, 640, 20)),
            holder_sides=(BoundarySide.TOP, BoundarySide.BOTTOM),
        )
        plan = shared_short_axis_plan(search_scope)
        plan = replace(
            plan,
            photo_height_evidence=PhotoHeightEvidence(
                height_px=PixelInterval(99.0, 101.0),
                state=EvidenceState.SUPPORTED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.PHOTO_EDGES,
                    ObservationId("physical_scale_search_height"),
                    (MeasurementIdentity.BOUNDARY_PATHS,),
                    "independently measured photo height",
                ),
            ),
        )
        support = solver_separator(100.0, 110.0, plan, supported=True)
        search_index = solver_search_index(search_scope, (support,))
        scale_constraint = common_width.frame_width_physical_scale_constraint(
            plan.photo_height_evidence,
            solver_dimensions(1.0, 1.0),
        )
        self.assertIsNotNone(scale_constraint)
        assert scale_constraint is not None

        search_space = solver_module._measured_frame_search_space(
            search_index,
            (scale_constraint.width_px,),
            scale_constraint.width_px,
            scale_constraint,
        )
        self.assertLess(
            len(search_space.observed_constraints),
            len(search_index.observed_constraints),
        )
        self.assertTrue(
            all(
                constraint.leading_holder_clip_supported
                or constraint.trailing_holder_clip_supported
                or constraint.width_px.intersects(scale_constraint.width_px)
                for constraint in search_space.observed_constraints
            )
        )

    def test_internal_slot_is_inferred_without_separator_measurements(self) -> None:
        real_slots = (
            _real_slot(1, 0.0, 100.0),
            _real_slot(2, 210.0, 310.0),
            _real_slot(3, 320.0, 420.0),
        )
        neighboring_boundaries = (
            real_slots[0].trailing,
            real_slots[1].leading,
        )

        inferred_slot = infer_sequence_frame_slot(
            real_slots,
            insertion_index=2,
            common_width=_common_width(*real_slots),
            holder_safety=_holder_safety(Box(0, 0, 500, 100)),
        )

        self.assertIsNotNone(inferred_slot)
        assert (
            inferred_slot is not None
            and inferred_slot.sequence_inference is not None
        )
        self.assertEqual(
            inferred_slot.sequence_inference.position.value,
            "interior",
        )
        self.assertEqual(
            neighboring_boundaries,
            (real_slots[0].trailing, real_slots[1].leading),
        )
        self.assertFalse(inferred_slot.leading.independently_observed)
        self.assertFalse(inferred_slot.trailing.independently_observed)
        self.assertEqual(
            inferred_slot.sequence_inference.safe_output_interval,
            PixelInterval(100.0, 210.0),
        )
        self.assertEqual(real_slots[0].trailing.position, PixelInterval.exact(100.0))
        self.assertEqual(real_slots[1].leading.position, PixelInterval.exact(210.0))

    def test_leading_and_trailing_inference_require_holder_safe_boundary(self) -> None:
        leading_real_slots = (
            _real_slot(1, 110.0, 210.0),
            _real_slot(2, 220.0, 320.0),
            _real_slot(3, 330.0, 430.0),
        )
        holder = _holder_safety(Box(0, 0, 550, 100))

        self.assertIsNone(
            infer_sequence_frame_slot(
                leading_real_slots,
                insertion_index=1,
                common_width=_common_width(*leading_real_slots),
                holder_safety=holder,
            )
        )
        leading = infer_sequence_frame_slot(
            leading_real_slots,
            insertion_index=1,
            common_width=_common_width(*leading_real_slots),
            holder_safety=_holder_safety(
                Box(0, 0, 550, 100),
                (_long_holder_boundary(BoundarySide.LEADING, 0.0),),
            ),
        )
        trailing_real_slots = (
            _real_slot(1, 0.0, 100.0),
            _real_slot(2, 110.0, 210.0),
            _real_slot(3, 220.0, 320.0),
        )
        trailing = infer_sequence_frame_slot(
            trailing_real_slots,
            insertion_index=4,
            common_width=_common_width(*trailing_real_slots),
            holder_safety=_holder_safety(
                Box(0, 0, 550, 100),
                (_long_holder_boundary(BoundarySide.TRAILING, 550.0),),
            ),
        )

        self.assertIsNotNone(leading)
        self.assertIsNotNone(trailing)
        assert leading is not None and leading.sequence_inference is not None
        assert trailing is not None and trailing.sequence_inference is not None
        self.assertEqual(leading.sequence_inference.position.value, "leading")
        self.assertEqual(trailing.sequence_inference.position.value, "trailing")

    def test_sequence_inference_does_not_assign_content_identity(self) -> None:
        real_slots = (
            _real_slot(1, 0.0, 100.0),
            _real_slot(2, 210.0, 310.0),
            _real_slot(3, 320.0, 420.0),
        )

        inferred_slot = infer_sequence_frame_slot(
            real_slots,
            insertion_index=2,
            common_width=_common_width(*real_slots),
            holder_safety=_holder_safety(Box(0, 0, 500, 100)),
        )

        self.assertIsNotNone(inferred_slot)
        assert inferred_slot is not None
        observed = replace(
            inferred_slot,
            content_occupancy=FrameContentOccupancy.CONTENT_OBSERVED,
        )
        self.assertTrue(observed.sequence_inferred)
        self.assertEqual(
            observed.content_occupancy,
            FrameContentOccupancy.CONTENT_OBSERVED,
        )

    def test_full_solver_can_resolve_one_internal_blank_from_the_global_sequence(
        self,
    ) -> None:
        search_scope = solver_scope(
            width=660,
            height=120,
            leading=0.0,
            trailing=650.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(
                100.0,
                110.0,
                210.0,
                330.0,
                430.0,
                440.0,
                540.0,
                550.0,
            ),
            holder_sides=(
                BoundarySide.LEADING,
                BoundarySide.TRAILING,
                BoundarySide.TOP,
                BoundarySide.BOTTOM,
            ),
            holder_positions={
                BoundarySide.LEADING: 0.0,
                BoundarySide.TRAILING: 660.0,
                BoundarySide.TOP: 0.0,
                BoundarySide.BOTTOM: 120.0,
            },
        )
        visible_content = solver_content(
            width=660,
            height=120,
            runs=(
                (0, 100),
                (110, 210),
                (330, 430),
                (440, 540),
                (550, 650),
            ),
        )
        plan = shared_short_axis_plan(search_scope)
        plan = replace(
            plan,
            photo_height_evidence=PhotoHeightEvidence(
                height_px=PixelInterval(99.0, 101.0),
                state=EvidenceState.SUPPORTED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.PHOTO_EDGES,
                    ObservationId("blank_sequence_photo_height"),
                    (MeasurementIdentity.BOUNDARY_PATHS,),
                    "independently measured photo height",
                ),
            ),
        )
        supports = tuple(
            solver_separator(start, end, plan, supported=True)
            for start, end in ((100, 110), (430, 440), (540, 550))
        )

        solved = solve_frame_sequence(
            solver_search_index(search_scope, supports),
            search_scope,
            plan,
            6,
            solver_dimensions(1.0, 1.0),
            visible_content,
            100_000,
            strip_mode="full",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.frame_slots[2].sequence_inference.position.value, "interior")
        self.assertEqual(len(solved.separator_assignments), 3)
        self.assertEqual(solved.assignment_consensus.state, EvidenceState.SUPPORTED)

    def test_full_solver_can_resolve_one_leading_or_trailing_blank(self) -> None:
        cases = (
            (
                "leading",
                120.0,
                660.0,
                (220.0, 230.0, 330.0, 340.0, 440.0, 450.0, 550.0, 560.0),
                ((120, 220), (230, 330), (340, 440), (450, 550), (560, 660)),
                ((220, 230), (330, 340), (440, 450), (550, 560)),
                1,
            ),
            (
                "trailing",
                0.0,
                540.0,
                (100.0, 110.0, 210.0, 220.0, 320.0, 330.0, 430.0, 440.0),
                ((0, 100), (110, 210), (220, 320), (330, 430), (440, 540)),
                ((100, 110), (210, 220), (320, 330), (430, 440)),
                6,
            ),
        )
        for (
            position,
            leading,
            trailing,
            internal_paths,
            runs,
            separator_spans,
            blank_index,
        ) in cases:
            with self.subTest(position=position):
                search_scope = solver_scope(
                    width=660,
                    height=120,
                    leading=leading,
                    trailing=trailing,
                    top=10.0,
                    bottom=110.0,
                    internal_paths=internal_paths,
                    holder_sides=(
                        BoundarySide.LEADING,
                        BoundarySide.TRAILING,
                        BoundarySide.TOP,
                        BoundarySide.BOTTOM,
                    ),
                    holder_positions={
                        BoundarySide.LEADING: 0.0,
                        BoundarySide.TRAILING: 660.0,
                        BoundarySide.TOP: 0.0,
                        BoundarySide.BOTTOM: 120.0,
                    },
                )
                visible_content = solver_content(
                    width=660,
                    height=120,
                    runs=runs,
                )
                plan = shared_short_axis_plan(search_scope)
                supports = tuple(
                    solver_separator(start, end, plan, supported=True)
                    for start, end in separator_spans
                )

                solved = solve_frame_sequence(
                    solver_search_index(search_scope, supports),
                    search_scope,
                    plan,
                    6,
                    solver_dimensions(1.0, 1.0),
                    visible_content,
                    100_000,
                    strip_mode="full",
                    nominal_count=6,
                )

                self.assertIsInstance(solved, FrameSequenceSolveResult)
                assert isinstance(solved, FrameSequenceSolveResult)
                blank = solved.frame_slots[blank_index - 1]
                self.assertTrue(blank.sequence_inferred)
                assert blank.sequence_inference is not None
                self.assertEqual(blank.sequence_inference.position.value, position)
                self.assertEqual(
                    blank.sequence_inference.measurement_state,
                    EvidenceState.UNAVAILABLE,
                )

    def test_ambiguous_leading_and_trailing_blank_placements_are_unresolved(
        self,
    ) -> None:
        search_scope = solver_scope(
            width=780,
            height=120,
            leading=120.0,
            trailing=660.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(220.0, 230.0, 330.0, 340.0, 440.0, 450.0, 550.0, 560.0),
            holder_sides=(
                BoundarySide.LEADING,
                BoundarySide.TRAILING,
                BoundarySide.TOP,
                BoundarySide.BOTTOM,
            ),
            holder_positions={
                BoundarySide.LEADING: 0.0,
                BoundarySide.TRAILING: 780.0,
                BoundarySide.TOP: 0.0,
                BoundarySide.BOTTOM: 120.0,
            },
        )
        visible_content = solver_content(
            width=780,
            height=120,
            runs=((120, 220), (230, 330), (340, 440), (450, 550), (560, 660)),
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            solver_separator(start, end, plan, supported=True)
            for start, end in ((220, 230), (330, 340), (440, 450), (550, 560))
        )

        solved = solve_frame_sequence(
            solver_search_index(search_scope, supports),
            search_scope,
            plan,
            6,
            solver_dimensions(1.0, 1.0),
            visible_content,
            100_000,
            strip_mode="full",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.assignment_consensus.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            solved.assignment_consensus.reason,
            "alternative_frame_slot_assignments_disagree",
        )
        self.assertFalse(solved.search_outcome.budget_exhausted)

if __name__ == "__main__":
    unittest.main()
