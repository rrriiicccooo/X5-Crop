from __future__ import annotations

from dataclasses import replace
import unittest

from x5crop.configuration.photo_edges import PhotoEdgeDetectionParameters
from x5crop.configuration.transform import TransformDetectionParameters
from x5crop.detection.evidence.photo_edges import (
    PhotoEdgeFact,
    PhotoEdgePairEvidence,
    map_photo_edge_pair_evidence,
)
from x5crop.detection.evidence.transform_geometry import (
    TransformGeometryEvidence,
    TransformOutcome,
)
from x5crop.detection.physical.short_axis import (
    SharedShortAxisOutcome,
    shared_short_axis_from_photo_edge_pair,
)
from x5crop.detection.workspace import _transform_geometry
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryPathSample,
    BoundarySide,
    EvidenceState,
    GrayAppearanceObservation,
    GrayBoundaryPathObservation,
    GrayIntensityTail,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from x5crop.geometry.affine import AffineCoordinateTransform
from tools.tests.photo_edge_support import (
    PARAMETERS,
    photo_edge_pair_fixture,
    unavailable_photo_edge_pair_fixture,
)


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
    sample_count: int = 8,
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
    lower, upper = (
        (outer, inner)
        if side == BoundarySide.TOP
        else (inner, outer)
    )
    return GrayBoundaryPathObservation(
        axis=BoundaryAxis.SHORT,
        kind=BoundaryKind.TONAL_TRANSITION,
        samples=tuple(samples),
        lower_appearance=lower,
        upper_appearance=upper,
        provenance=provenance,
    )


def _pair(
    *,
    top_slope: float = 0.0,
    bottom_slope: float | None = None,
    support_start: float = 0.0,
    support_end: float = 1_000.0,
    sample_count: int = 8,
    top_residual: float = 0.0,
) -> PhotoEdgePairEvidence:
    bottom_slope = top_slope if bottom_slope is None else bottom_slope
    return photo_edge_pair_fixture(
        _path(
            "top_photo_edge",
            20.0,
            top_slope,
            BoundarySide.TOP,
            support_start=support_start,
            support_end=support_end,
            sample_count=sample_count,
            residual_offset=top_residual,
        ),
        _path(
            "bottom_photo_edge",
            180.0,
            bottom_slope,
            BoundarySide.BOTTOM,
            support_start=support_start,
            support_end=support_end,
            sample_count=sample_count,
        ),
    )


def _outcome(
    pairs: tuple[PhotoEdgePairEvidence, ...],
    parameters: TransformDetectionParameters | None = None,
    *,
    layout: str = "horizontal",
) -> TransformGeometryEvidence:
    source_width, source_height = (
        (1_000, 200) if layout == "horizontal" else (200, 1_000)
    )
    return _transform_geometry(
        pairs,
        1_000,
        source_width,
        source_height,
        layout,
        parameters or TransformDetectionParameters(),
    )


class PhotoEdgeTransformContractTest(unittest.TestCase):
    def test_configuration_separates_photo_edges_and_transform(self) -> None:
        self.assertEqual(
            PhotoEdgeDetectionParameters().minimum_candidate_sections,
            3,
        )
        self.assertEqual(
            TransformDetectionParameters().maximum_angle_degrees,
            2.0,
        )

    def test_transform_outcomes_are_current_and_exhaustive(self) -> None:
        self.assertEqual(
            {outcome.value for outcome in TransformOutcome},
            {
                "photo_edge_pair_unavailable",
                "angle_estimation_unavailable",
                "edge_slopes_disagree",
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
            states[TransformOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE],
            EvidenceState.UNAVAILABLE,
        )
        self.assertEqual(
            states[TransformOutcome.EDGE_SLOPES_DISAGREE],
            EvidenceState.CONTRADICTED,
        )

    def test_failed_transform_has_no_fake_zero_angle(self) -> None:
        with self.assertRaises(ValueError):
            TransformGeometryEvidence(
                outcome=TransformOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE,
                estimated_angle_degrees=0.0,
                projected_edge_drift_px=None,
                identity_drift_threshold_px=None,
                position_uncertainty_px=0.0,
                coordinate_transform=AffineCoordinateTransform.identity(100, 20),
            )

    def test_supported_pair_drives_identity_rotation_and_angle_range(self) -> None:
        self.assertEqual(
            _outcome((_pair(top_slope=0.001),)).outcome,
            TransformOutcome.IDENTITY_WITHIN_TOLERANCE,
        )
        self.assertEqual(
            _outcome((_pair(top_slope=0.01),)).outcome,
            TransformOutcome.DESKEW_APPLIED,
        )
        self.assertEqual(
            _outcome((_pair(top_slope=0.05),)).outcome,
            TransformOutcome.ANGLE_OUT_OF_RANGE,
        )
        unavailable = unavailable_photo_edge_pair_fixture()
        self.assertEqual(
            _outcome((unavailable,)).outcome,
            TransformOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE,
        )

    def test_dual_lane_requires_angle_consistency(self) -> None:
        consistent = _outcome(
            (_pair(top_slope=0.01), _pair(top_slope=0.011))
        )
        conflict = _outcome(
            (_pair(top_slope=0.01), _pair(top_slope=-0.01))
        )
        self.assertEqual(consistent.outcome, TransformOutcome.DESKEW_APPLIED)
        self.assertEqual(conflict.outcome, TransformOutcome.EDGE_SLOPES_DISAGREE)

    def test_layout_and_slope_sign_determine_one_correction(self) -> None:
        horizontal = _outcome((_pair(top_slope=0.01),))
        vertical = _outcome((_pair(top_slope=0.01),), layout="vertical")
        assert horizontal.estimated_angle_degrees is not None
        assert horizontal.applied_angle_degrees is not None
        assert vertical.estimated_angle_degrees is not None
        assert vertical.applied_angle_degrees is not None
        self.assertGreater(horizontal.estimated_angle_degrees, 0.0)
        self.assertLess(horizontal.applied_angle_degrees, 0.0)
        self.assertLess(vertical.estimated_angle_degrees, 0.0)
        self.assertGreater(vertical.applied_angle_degrees, 0.0)

    def test_mapping_preserves_pair_and_candidate_identity(self) -> None:
        source = _pair(top_slope=0.01)
        transform = _outcome((source,))
        mapped = map_photo_edge_pair_evidence(
            source,
            transform.coordinate_transform,
            "horizontal",
            transform.position_uncertainty_px,
        )
        self.assertIsNot(mapped, source)
        self.assertEqual(
            mapped.observation_id,
            ObservationId(f"workspace:{source.observation_id}"),
        )
        self.assertEqual(len(mapped.candidates), len(source.candidates))
        for source_candidate, mapped_candidate in zip(
            source.candidates,
            mapped.candidates,
            strict=True,
        ):
            self.assertEqual(
                mapped_candidate.path.provenance.boundary_anchors,
                (source_candidate.path.provenance.observation_id,),
            )

    def test_robust_fit_ignores_one_large_residual(self) -> None:
        pair = _pair(
            top_slope=0.001,
            sample_count=10,
            top_residual=20.0,
        )
        self.assertEqual(pair.state, EvidenceState.SUPPORTED)
        top, _ = pair.selected_candidates or (None, None)
        assert top is not None
        self.assertGreaterEqual(top.fit.inlier_ratio, 0.8)
        self.assertLess(len(top.fit.inlier_indices), len(top.path.samples))

    def test_overlapping_inner_windows_cannot_self_prove_a_photo_band(
        self,
    ) -> None:
        pair = photo_edge_pair_fixture(
            _path(
                "nearby_top_transition",
                20.0,
                0.0,
                BoundarySide.TOP,
            ),
            _path(
                "nearby_bottom_transition",
                40.0,
                0.0,
                BoundarySide.BOTTOM,
            ),
            photo_band_support_depth_px=12.0,
        )

        self.assertEqual(pair.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(pair.selected_pair_id)
        self.assertEqual(
            pair.hypotheses[0].facts,
            (PhotoEdgeFact.PHOTO_BAND_EVIDENCE_UNAVAILABLE,),
        )

    def test_shared_axis_has_independent_extrapolation_gate(self) -> None:
        pair = _pair(
            support_start=450.0,
            support_end=1_450.0,
        )
        transform = _outcome((pair,))
        self.assertEqual(transform.state, EvidenceState.SUPPORTED)
        plan = shared_short_axis_from_photo_edge_pair(
            pair,
            20_000,
            PARAMETERS,
        )
        self.assertEqual(
            plan.outcome,
            SharedShortAxisOutcome.EXTRAPOLATION_UNCERTAINTY_TOO_LARGE,
        )
        self.assertIsNone(plan.span)

    def test_retained_border_candidate_is_valid_when_its_samples_are_in_bounds(
        self,
    ) -> None:
        from tools.tests.physical_gate_support import (
            detection_workspace_fixture,
        )

        workspace = detection_workspace_fixture(width=1_000, height=200)
        border_pair = photo_edge_pair_fixture(
            _path(
                "border_photo_edge",
                1.0,
                0.0,
                BoundarySide.TOP,
                residual_offset=4.0,
            ),
            _path(
                "bottom_photo_edge",
                180.0,
                0.0,
                BoundarySide.BOTTOM,
            ),
        )
        border_candidate = border_pair.candidates[0]
        self.assertLess(border_candidate.path.position.minimum, 0.0)
        evidence = replace(
            border_pair,
            candidates=(border_candidate,),
            hypotheses=(),
            selected_pair_id=None,
            state=EvidenceState.UNAVAILABLE,
            facts=(PhotoEdgeFact.PHOTO_BAND_EVIDENCE_UNAVAILABLE,),
        )
        mapped = map_photo_edge_pair_evidence(
            evidence,
            workspace.transform_geometry.coordinate_transform,
            workspace.measurement_cache.layout,
            workspace.transform_geometry.position_uncertainty_px,
        )
        plan = shared_short_axis_from_photo_edge_pair(
            mapped,
            workspace.measurement_cache.gray_work.shape[1],
            PARAMETERS,
        )

        replaced = replace(
            workspace,
            source_photo_edge_pairs=(evidence,),
            mapped_photo_edge_pairs=(mapped,),
            shared_short_axes=(plan,),
        )

        self.assertIs(replaced.source_photo_edge_pairs[0], evidence)

    def test_unavailable_pair_keeps_typed_reason(self) -> None:
        evidence = unavailable_photo_edge_pair_fixture()
        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(evidence.facts, (PhotoEdgeFact.PATHS_UNAVAILABLE,))


if __name__ == "__main__":
    unittest.main()
