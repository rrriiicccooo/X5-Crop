from __future__ import annotations

import unittest

from x5crop.domain import FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_cross import (
    CrossEvidence,
    CrossFitStatus,
    CrossRoleBinding,
    TemplateCrossInput,
    fit_template_cross,
)
from x5crop.detection.photo_geometry.template_model import PhaseAuthority, TemplateSpec


def template() -> TemplateSpec:
    return TemplateSpec(
        template_id="cross-test",
        frame_width_px=100.0,
        pitch_px=120.0,
        frame_height_px=240.0,
        count=1,
        phase_authority=PhaseAuthority.FULL_CENTERED,
    )


def binding(
    role: BoundaryRole,
    name: str,
    coordinate: float,
    *,
    traces: tuple[int, ...] = (0, 50, 100),
    residual: float = 0.0,
    support: float = 1.0,
    continuous: float = 1.0,
    angle: float = 0.0,
    angle_interval: FiniteInterval = FiniteInterval(-0.2, 0.2),
) -> CrossRoleBinding:
    coordinate_interval = FiniteInterval.exact(coordinate)
    return CrossRoleBinding(
        role=role,
        run_id=f"run:{name}",
        observation_id=ObservationId(f"observation:{name}"),
        coordinate_interval_px=coordinate_interval,
        trace_coordinates_px=traces,
        support_fraction=support,
        continuous_support_fraction=continuous,
        fit_residual_px=residual,
        fit_interval_px=coordinate_interval,
        full_interval_px=coordinate_interval,
        canonical_direction_degrees=angle,
        full_direction_interval_degrees=angle_interval,
    )


class TemplateCrossContractTest(unittest.TestCase):
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
        self.assertEqual(result.best.direct_observation_ids, (
            ObservationId("observation:top"),
            ObservationId("observation:bottom"),
        ))
        self.assertEqual(result.receipt.compatible_pair_count, 1)

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
        self.assertEqual(result.receipt.single_side_inference_count, 1)

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

    def test_center_compatible_fit_beats_off_center_clutter(self) -> None:
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
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(result.best.direct_observation_ids[0], ObservationId("observation:normal-top"))
        self.assertTrue(result.best.center_compatible)

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
        self.assertEqual(direction.full_angle_interval_degrees, FiniteInterval(-0.1, 0.2))


if __name__ == "__main__":
    unittest.main()
