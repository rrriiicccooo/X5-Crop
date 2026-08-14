from __future__ import annotations

import unittest

from x5crop.domain import FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.observation_types import BoundaryEdgeObservation
from x5crop.detection.photo_geometry.output_model import SharedStripDirection
from x5crop.detection.photo_geometry.template_cross import (
    CrossRoleBinding,
    TemplateCrossInput,
    fit_template_cross,
)
from x5crop.detection.photo_geometry.template_direction import (
    lane_template_direction,
    shared_template_direction,
)
from x5crop.detection.photo_geometry.template_model import (
    PhaseAuthority,
    PhaseLatticeAuthority,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase


def _direction(name: str, minimum: float, maximum: float, value: float):
    return SharedStripDirection(
        direction_id=f"direction:{name}",
        selected_observation_ids=(ObservationId(f"observation:{name}"),),
        full_angle_interval_degrees=FiniteInterval(minimum, maximum),
        canonical_angle_degrees=value,
    )


def _template() -> TemplateSpec:
    return TemplateSpec(
        template_id="direction-template",
        frame_width_px=100.0,
        pitch_px=120.0,
        frame_height_px=240.0,
        count=3,
        phase_authority=PhaseAuthority.PARTIAL_FREE,
        phase_lattice_authority=PhaseLatticeAuthority(
            period_px=120.0,
            cycle_origin_px=0.0,
            minimum_slot_offset=-1,
            maximum_slot_offset=4,
            phase_authority=PhaseAuthority.PARTIAL_FREE,
        ),
        nominal_gap_px=20.0,
    )


def _edge(
    name: str,
    coordinate: float,
    angle: float,
    angle_interval: FiniteInterval,
) -> BoundaryEdgeObservation:
    identity = ObservationId(f"sequence:{name}")
    return BoundaryEdgeObservation(
        observation_id=identity,
        run_id=f"run:{name}",
        coordinate_interval_px=FiniteInterval(
            coordinate - 0.1,
            coordinate + 0.1,
        ),
        transition_ids=(ObservationId(f"transition:{name}"),),
        trace_coordinates_px=(0, 50, 100),
        polarity=1,
        support_fraction=1.0,
        continuous_support_fraction=1.0,
        fit_residual_px=0.0,
        canonical_direction_degrees=angle,
        fit_direction_interval_degrees=angle_interval,
        full_direction_interval_degrees=FiniteInterval(-0.5, 0.5),
        qualified_anchor_roles=(BoundaryRole.START, BoundaryRole.END),
    )


def _cross_binding(
    role: BoundaryRole,
    name: str,
    coordinate: float,
    *,
    angle: float = 0.0,
    fit_interval: FiniteInterval = FiniteInterval(-0.05, 0.05),
    full_interval: FiniteInterval = FiniteInterval(-0.1, 0.1),
    source_spanning: bool = False,
):
    exact = FiniteInterval.exact(coordinate)
    return CrossRoleBinding(
        role=role,
        run_id=f"cross-run:{name}",
        observation_id=ObservationId(f"cross:{name}"),
        coordinate_interval_px=exact,
        trace_coordinates_px=(0, 50, 100),
        support_fraction=1.0,
        continuous_support_fraction=1.0,
        fit_residual_px=0.0,
        fit_interval_px=exact,
        full_interval_px=exact,
        canonical_direction_degrees=angle,
        fit_direction_interval_degrees=fit_interval,
        full_direction_interval_degrees=full_interval,
        source_spanning_continuous=source_spanning,
    )


def _sequence_observations() -> tuple[BoundaryEdgeObservation, ...]:
    return (
        _edge("outer-start", 40.0, 0.00, FiniteInterval(-0.02, 0.02)),
        _edge("gap-1-end", 140.0, 0.18, FiniteInterval(0.16, 0.20)),
        _edge("gap-1-start", 160.0, 0.22, FiniteInterval(0.20, 0.24)),
        _edge("gap-2-end", 260.0, 0.20, FiniteInterval(0.18, 0.22)),
        _edge("gap-2-start", 280.0, 0.24, FiniteInterval(0.22, 0.26)),
        _edge("outer-end", 380.0, 0.22, FiniteInterval(0.20, 0.24)),
    )


class TemplateDirectionContractTest(unittest.TestCase):
    def test_independent_sequence_positions_close_one_lane_direction(self) -> None:
        template = _template()
        observations = _sequence_observations()
        phase = fit_template_phase(observations, template)
        self.assertIsNotNone(phase.best)
        cross = fit_template_cross(
            TemplateCrossInput(
                template=template,
                fixed_height_px=240.0,
                top_bindings=(
                    _cross_binding(
                        BoundaryRole.TOP,
                        "top",
                        100.0,
                        angle=0.12,
                        fit_interval=FiniteInterval(0.10, 0.14),
                        full_interval=FiniteInterval(-0.1, 0.3),
                    ),
                ),
                bottom_bindings=(
                    _cross_binding(
                        BoundaryRole.BOTTOM,
                        "bottom",
                        340.0,
                        angle=0.04,
                        fit_interval=FiniteInterval(0.02, 0.06),
                        full_interval=FiniteInterval(-0.1, 0.3),
                    ),
                ),
                parallel_direction_tolerance_degrees=0.8,
            )
        )
        self.assertIsNotNone(cross.best)
        result = lane_template_direction(
            phase.best,
            observations,
            cross.best,
        )
        self.assertAlmostEqual(
            result.full_angle_interval_degrees.minimum,
            0.17,
        )
        self.assertAlmostEqual(
            result.full_angle_interval_degrees.maximum,
            0.24,
        )
        self.assertAlmostEqual(result.canonical_angle_degrees, 0.21)
        self.assertEqual(
            len(result.selected_observation_ids),
            8,
        )

    def test_source_spanning_cross_owns_canonical_lane_direction(self) -> None:
        template = _template()
        observations = _sequence_observations()
        phase = fit_template_phase(observations, template)
        self.assertIsNotNone(phase.best)
        cross = fit_template_cross(
            TemplateCrossInput(
                template=template,
                fixed_height_px=240.0,
                top_bindings=(
                    _cross_binding(
                        BoundaryRole.TOP,
                        "spanning-top",
                        100.0,
                        angle=0.19,
                        fit_interval=FiniteInterval(0.17, 0.21),
                        full_interval=FiniteInterval(0.15, 0.25),
                        source_spanning=True,
                    ),
                ),
                bottom_bindings=(
                    _cross_binding(
                        BoundaryRole.BOTTOM,
                        "local-bottom",
                        340.0,
                        angle=0.21,
                        fit_interval=FiniteInterval(0.19, 0.23),
                        full_interval=FiniteInterval(0.15, 0.27),
                    ),
                ),
            )
        )
        self.assertIsNotNone(cross.best)
        assert cross.best is not None and cross.best.selected_direction is not None
        result = lane_template_direction(phase.best, observations, cross.best)
        self.assertEqual(
            result.full_angle_interval_degrees,
            cross.best.selected_direction.full_angle_interval_degrees,
        )
        self.assertEqual(
            result.canonical_angle_degrees,
            cross.best.selected_direction.canonical_angle_degrees,
        )

    def test_sequence_closure_limits_local_pair_to_direct_fit_hull(self) -> None:
        template = _template()
        observations = _sequence_observations()
        phase = fit_template_phase(observations, template)
        assert phase.best is not None
        cross = fit_template_cross(
            TemplateCrossInput(
                template=template,
                fixed_height_px=240.0,
                top_bindings=(
                    _cross_binding(
                        BoundaryRole.TOP,
                        "local-top",
                        100.0,
                        angle=0.19,
                        fit_interval=FiniteInterval(0.15, 0.25),
                        full_interval=FiniteInterval(-0.2, 0.4),
                    ),
                ),
                bottom_bindings=(
                    _cross_binding(
                        BoundaryRole.BOTTOM,
                        "local-bottom",
                        340.0,
                        angle=0.18,
                        fit_interval=FiniteInterval(0.16, 0.22),
                        full_interval=FiniteInterval(-0.3, 0.5),
                    ),
                ),
            )
        )
        assert cross.best is not None
        result = lane_template_direction(phase.best, observations, cross.best)
        self.assertEqual(
            result.full_angle_interval_degrees,
            FiniteInterval(0.16, 0.22),
        )
        self.assertAlmostEqual(result.canonical_angle_degrees, 0.185)

    def test_lane_directions_resolve_to_intersection_once(self) -> None:
        result = shared_template_direction(
            (
                _direction("left", -0.2, 0.2, 0.05),
                _direction("right", -0.1, 0.3, 0.1),
            )
        )
        self.assertEqual(result.full_angle_interval_degrees, FiniteInterval(-0.1, 0.2))
        self.assertEqual(
            set(result.selected_observation_ids),
            {ObservationId("observation:left"), ObservationId("observation:right")},
        )

    def test_disjoint_lane_directions_remain_unresolved(self) -> None:
        with self.assertRaises(ValueError):
            shared_template_direction(
                (
                    _direction("left", -0.2, -0.1, -0.15),
                    _direction("right", 0.1, 0.2, 0.15),
                )
            )


if __name__ == "__main__":
    unittest.main()
