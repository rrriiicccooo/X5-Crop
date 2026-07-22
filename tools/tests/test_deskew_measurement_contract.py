from __future__ import annotations

from dataclasses import replace
import unittest

from x5crop.configuration.transform import DeskewDetectionParameters
from x5crop.detection.evidence.transform_geometry import (
    TransformGeometryEvidence,
    TransformOutcome,
)
from x5crop.detection.physical.short_axis import (
    SharedShortAxisPlan,
    photo_edge_is_independent,
    shared_short_axis_from_photo_edges,
)
from x5crop.detection.workspace import (
    _deskew_geometry,
    _mapped_plan,
    _transform_qualified_short_axes,
)
from tools.tests.physical_gate_support import detection_workspace_fixture
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryPathSample,
    BoundarySide,
    EvidenceState,
    GrayAppearanceObservation,
    GrayBoundaryPathObservation,
    GrayIntensityTail,
    HolderBoundaryObservation,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from x5crop.geometry.affine import AffineCoordinateTransform


def _appearance(
    provenance: MeasurementProvenance,
) -> GrayAppearanceObservation:
    return GrayAppearanceObservation(
        intensity_median=64.0,
        intensity_mad=2.0,
        texture_median=2.0,
        gradient_median=4.0,
        spatial_continuity=1.0,
        intensity_tail=GrayIntensityTail.MIDRANGE,
        provenance=provenance,
    )


def _path(
    name: str,
    intercept: float,
    slope: float,
    side: BoundarySide,
    *,
    support_start: float = 0.0,
    support_end: float = 1_000.0,
    sample_count: int = 5,
    residual_offset: float = 0.0,
) -> GrayBoundaryPathObservation:
    provenance = MeasurementProvenance(
        MeasurementIdentity.BOUNDARY_PATHS,
        ObservationId(name),
        (MeasurementIdentity.GRAY_WORK,),
        "synthetic source-coordinate photo edge",
    )
    step = (support_end - support_start) / float(sample_count)
    samples = []
    for index in range(sample_count):
        start = support_start + index * step
        end = start + step
        center = (start + end) / 2.0
        position = intercept + slope * center
        if index == sample_count // 2:
            position += residual_offset
        samples.append(
            BoundaryPathSample(
                PixelInterval(start, end),
                PixelInterval.exact(position),
            )
        )
    inner = _appearance(provenance)
    outer = replace(
        inner,
        intensity_median=8.0,
        texture_median=0.25,
        gradient_median=0.5,
        intensity_tail=GrayIntensityTail.LOW,
    )
    lower, upper = (outer, inner) if side == BoundarySide.TOP else (inner, outer)
    return GrayBoundaryPathObservation(
        axis=BoundaryAxis.SHORT,
        kind=BoundaryKind.TONAL_TRANSITION,
        samples=tuple(samples),
        lower_appearance=lower,
        upper_appearance=upper,
        provenance=provenance,
    )


def _plan(
    *,
    top_slope: float = 0.0,
    bottom_slope: float | None = None,
    top_support: tuple[float, float] = (0.0, 1_000.0),
    bottom_support: tuple[float, float] = (0.0, 1_000.0),
    sample_count: int = 5,
    top_residual: float = 0.0,
) -> SharedShortAxisPlan:
    bottom_slope = top_slope if bottom_slope is None else bottom_slope
    top = _path(
        "top_photo_edge",
        20.0,
        top_slope,
        BoundarySide.TOP,
        support_start=top_support[0],
        support_end=top_support[1],
        sample_count=sample_count,
        residual_offset=top_residual,
    )
    bottom = _path(
        "bottom_photo_edge",
        180.0,
        bottom_slope,
        BoundarySide.BOTTOM,
        support_start=bottom_support[0],
        support_end=bottom_support[1],
        sample_count=sample_count,
    )
    return shared_short_axis_from_photo_edges(
        top,
        bottom,
    )


def _outcome(
    plans: tuple[SharedShortAxisPlan, ...],
    parameters: DeskewDetectionParameters | None = None,
    *,
    layout: str = "horizontal",
) -> TransformGeometryEvidence:
    source_width, source_height = (
        (1_000, 200) if layout == "horizontal" else (200, 1_000)
    )
    evidence = _deskew_geometry(
        plans,
        1_000,
        200,
        source_width,
        source_height,
        layout,
        parameters or DeskewDetectionParameters(),
    )
    return evidence


class DeskewMeasurementContractTest(unittest.TestCase):
    def test_weak_intensity_change_is_not_a_photo_edge(self) -> None:
        path = _path(
            "weak_top_photo_edge",
            20.0,
            0.0,
            BoundarySide.TOP,
        )
        path = replace(
            path,
            lower_appearance=replace(
                path.lower_appearance,
                intensity_median=60.0,
                intensity_tail=GrayIntensityTail.HIGH,
            ),
        )

        self.assertFalse(
            photo_edge_is_independent(
                path,
                BoundarySide.TOP,
                None,
                minimum_intensity_contrast=10.0,
                minimum_holder_gap=2.0,
            )
        )

    def test_photo_edge_must_be_independent_of_holder_measurement_window(self) -> None:
        path = _path(
            "top_photo_edge_near_holder",
            20.0,
            0.0,
            BoundarySide.TOP,
        )
        holder_path = replace(
            _path(
                "top_holder_edge",
                10.0,
                0.0,
                BoundarySide.TOP,
            ),
            kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        )
        holder = HolderBoundaryObservation(
            BoundarySide.TOP,
            holder_path.position,
            (holder_path,),
        )

        self.assertFalse(
            photo_edge_is_independent(
                path,
                BoundarySide.TOP,
                holder,
                minimum_intensity_contrast=10.0,
                minimum_holder_gap=15.0,
            )
        )
        self.assertTrue(
            photo_edge_is_independent(
                path,
                BoundarySide.TOP,
                holder,
                minimum_intensity_contrast=10.0,
                minimum_holder_gap=5.0,
            )
        )

    def test_detection_workspace_rejects_mixed_short_axis_identity(self) -> None:
        workspace = detection_workspace_fixture(width=1_000, height=200)

        with self.assertRaises(ValueError):
            replace(
                workspace,
                shared_short_axes=(_plan(top_slope=0.001),),
            )

    def test_transform_outcomes_are_current_and_exhaustive(self) -> None:
        self.assertEqual(
            {outcome.value for outcome in TransformOutcome},
            {
                "photo_edges_unavailable",
                "insufficient_common_support",
                "edge_slopes_disagree",
                "edge_fit_high_residual",
                "identity_within_tolerance",
                "deskew_applied",
                "angle_out_of_range",
            },
        )

    def test_only_identity_and_applied_transform_are_supported(self) -> None:
        states = {
            outcome: TransformGeometryEvidence(
                outcome=outcome,
                estimated_angle_degrees=(
                    0.0
                    if outcome == TransformOutcome.IDENTITY_WITHIN_TOLERANCE
                    else None
                ),
                projected_edge_drift_px=(
                    0.0
                    if outcome == TransformOutcome.IDENTITY_WITHIN_TOLERANCE
                    else None
                ),
                identity_drift_threshold_px=(
                    3.0
                    if outcome == TransformOutcome.IDENTITY_WITHIN_TOLERANCE
                    else None
                ),
                position_uncertainty_px=0.0,
                coordinate_transform=AffineCoordinateTransform.identity(100, 20),
            ).state
            for outcome in TransformOutcome
            if outcome != TransformOutcome.DESKEW_APPLIED
        }
        self.assertEqual(
            states[TransformOutcome.IDENTITY_WITHIN_TOLERANCE],
            EvidenceState.SUPPORTED,
        )
        self.assertEqual(
            states[TransformOutcome.PHOTO_EDGES_UNAVAILABLE],
            EvidenceState.UNAVAILABLE,
        )
        self.assertEqual(
            states[TransformOutcome.EDGE_SLOPES_DISAGREE],
            EvidenceState.CONTRADICTED,
        )

    def test_failed_transform_has_no_fake_zero_angle(self) -> None:
        with self.assertRaises(ValueError):
            TransformGeometryEvidence(
                outcome=TransformOutcome.PHOTO_EDGES_UNAVAILABLE,
                estimated_angle_degrees=0.0,
                projected_edge_drift_px=None,
                identity_drift_threshold_px=None,
                position_uncertainty_px=0.0,
                coordinate_transform=AffineCoordinateTransform.identity(100, 20),
            )

    def test_dual_photo_edges_drive_every_transform_outcome(self) -> None:
        cases = (
            ((), TransformOutcome.PHOTO_EDGES_UNAVAILABLE),
            (
                (_plan(sample_count=3),),
                TransformOutcome.INSUFFICIENT_COMMON_SUPPORT,
            ),
            (
                (
                    _plan(
                        top_support=(0.0, 400.0),
                        bottom_support=(600.0, 1_000.0),
                    ),
                ),
                TransformOutcome.INSUFFICIENT_COMMON_SUPPORT,
            ),
            (
                (
                    _plan(
                        top_support=(0.0, 800.0),
                        bottom_support=(0.0, 800.0),
                    ),
                ),
                TransformOutcome.INSUFFICIENT_COMMON_SUPPORT,
            ),
            (
                (_plan(top_slope=0.001, bottom_slope=0.02),),
                TransformOutcome.EDGE_SLOPES_DISAGREE,
            ),
            (
                (_plan(top_slope=0.001, top_residual=20.0),),
                TransformOutcome.EDGE_FIT_HIGH_RESIDUAL,
            ),
            ((_plan(top_slope=0.001),), TransformOutcome.IDENTITY_WITHIN_TOLERANCE),
            ((_plan(top_slope=0.01),), TransformOutcome.DESKEW_APPLIED),
            ((_plan(top_slope=0.05),), TransformOutcome.ANGLE_OUT_OF_RANGE),
        )
        for plans, expected in cases:
            with self.subTest(expected=expected):
                evidence = _outcome(plans)
                self.assertEqual(evidence.outcome, expected)
                if evidence.state != EvidenceState.SUPPORTED:
                    self.assertIsNone(evidence.estimated_angle_degrees)
                    self.assertIsNone(evidence.applied_angle_degrees)

    def test_dual_lane_requires_angle_consistency(self) -> None:
        consistent = _outcome((_plan(top_slope=0.01), _plan(top_slope=0.011)))
        conflict = _outcome((_plan(top_slope=0.01), _plan(top_slope=-0.01)))

        self.assertEqual(consistent.outcome, TransformOutcome.DESKEW_APPLIED)
        self.assertEqual(conflict.outcome, TransformOutcome.EDGE_SLOPES_DISAGREE)

    def test_layout_and_slope_sign_determine_the_one_correction(self) -> None:
        horizontal_positive = _outcome((_plan(top_slope=0.01),))
        horizontal_negative = _outcome((_plan(top_slope=-0.01),))
        vertical_positive = _outcome(
            (_plan(top_slope=0.01),),
            layout="vertical",
        )

        self.assertGreater(horizontal_positive.estimated_angle_degrees, 0.0)
        self.assertLess(horizontal_positive.applied_angle_degrees, 0.0)
        self.assertLess(horizontal_negative.estimated_angle_degrees, 0.0)
        self.assertGreater(horizontal_negative.applied_angle_degrees, 0.0)
        self.assertLess(vertical_positive.estimated_angle_degrees, 0.0)
        self.assertGreater(vertical_positive.applied_angle_degrees, 0.0)
        self.assertEqual(
            vertical_positive.coordinate_transform.source_extent.width,
            200,
        )
        self.assertEqual(
            vertical_positive.coordinate_transform.source_extent.height,
            1_000,
        )

    def test_mapped_plan_uses_the_same_observations_without_pixel_search(self) -> None:
        source = _plan(top_slope=0.01)
        evidence = _outcome((source,))

        mapped = _mapped_plan(source, evidence, "horizontal")

        self.assertIsNot(mapped, source)
        self.assertTrue(mapped.supports_safe_crop)
        assert source.top_photo_edge is not None
        assert source.bottom_photo_edge is not None
        assert mapped.top_photo_edge is not None
        assert mapped.bottom_photo_edge is not None
        self.assertEqual(
            mapped.top_photo_edge.provenance.boundary_anchors,
            (source.top_photo_edge.provenance.observation_id,),
        )
        self.assertEqual(
            mapped.bottom_photo_edge.provenance.boundary_anchors,
            (source.bottom_photo_edge.provenance.observation_id,),
        )
        self.assertNotEqual(
            mapped.provenance.observation_id,
            source.provenance.observation_id,
        )

    def test_unqualified_edges_cannot_supply_a_shared_short_axis_span(self) -> None:
        plan = _plan(top_slope=0.001, top_residual=20.0)
        evidence = _outcome((plan,))

        qualified = _transform_qualified_short_axes((plan,), evidence)[0]

        self.assertIsNone(qualified.span)
        self.assertEqual(qualified.state, EvidenceState.CONTRADICTED)
        self.assertIsNotNone(qualified.top_photo_edge)
        self.assertIsNotNone(qualified.bottom_photo_edge)

    def test_maximum_angle_is_detection_configuration(self) -> None:
        parameters = replace(
            DeskewDetectionParameters(),
            maximum_angle_degrees=0.25,
        )
        self.assertEqual(
            _outcome((_plan(top_slope=0.01),), parameters).outcome,
            TransformOutcome.ANGLE_OUT_OF_RANGE,
        )


if __name__ == "__main__":
    unittest.main()
