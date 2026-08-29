from __future__ import annotations

from dataclasses import replace
import unittest

from x5crop.domain import FiniteInterval
from x5crop.detection.photo_geometry.template_feasible_geometry import (
    project_selected_placement,
)
from x5crop.detection.photo_geometry.template_model import (
    PhaseLatticeFit,
    PitchFit,
)
from tools.tests.template_test_support import (
    placement_compose as _compose,
    placement_cross as _cross,
    placement_direction as _direction,
    placement_sequence as _sequence,
    placement_template as _template,
)


class TemplateFeasibleGeometryContractTest(unittest.TestCase):
    @staticmethod
    def _sequence_interval(projection, frame_index: int, edge: int) -> FiniteInterval:
        values = tuple(
            (
                state.sequence_start_px
                if edge == 0
                else state.sequence_end_px
            )
            for state in projection.frame_states[frame_index]
        )
        return FiniteInterval(min(values), max(values))

    @staticmethod
    def _cross_interval(projection, edge: int) -> FiniteInterval:
        values = tuple(
            (
                state.top_at_lane_reference_px
                if edge == 0
                else state.bottom_at_lane_reference_px
            )
            for state in projection.frame_states[0]
        )
        return FiniteInterval(min(values), max(values))

    def test_phase_and_pitch_extremes_remain_correlated(self) -> None:
        template = _template(2)
        sequence = _sequence(template)
        sequence = replace(
            sequence,
            phase_lattice_fit=PhaseLatticeFit(
                authority=template.phase_lattice_authority,
                cycle_phase_interval_px=FiniteInterval(95.0, 105.0),
                canonical_cycle_phase_px=100.0,
                integer_slot_offset=0,
                canonical_period_px=120.0,
                absolute_phase_interval_px=FiniteInterval(95.0, 105.0),
                canonical_absolute_phase_px=100.0,
                direction=1,
            ),
            pitch_fit=PitchFit(
                frame_width_px=FiniteInterval.exact(100.0),
                gap_interval_px=FiniteInterval(15.0, 25.0),
                pitch_interval_px=FiniteInterval(115.0, 125.0),
                canonical_frame_width_px=100.0,
                canonical_pitch_px=120.0,
                observation_ids=sequence.pitch_fit.observation_ids,
            ),
            model_role_intervals_px=(
                FiniteInterval(95.0, 105.0),
                FiniteInterval(195.0, 205.0),
                FiniteInterval.exact(220.0),
                FiniteInterval.exact(320.0),
            ),
            model_full_role_intervals_px=(
                FiniteInterval(95.0, 105.0),
                FiniteInterval(195.0, 205.0),
                FiniteInterval.exact(220.0),
                FiniteInterval.exact(320.0),
            ),
        )
        placement = _compose(
            template,
            sequence,
            _cross(template, direction=_direction()),
        )
        projection = project_selected_placement(placement)
        self.assertEqual(
            self._sequence_interval(projection, 1, 0),
            FiniteInterval.exact(220.0),
        )
        self.assertEqual(
            self._sequence_interval(projection, 1, 1),
            FiniteInterval.exact(320.0),
        )
        self.assertLessEqual(projection.extreme_evaluation_count, 64 * 3)
        self.assertNotIn(
            (215.0, 315.0),
            {
                (state.sequence_start_px, state.sequence_end_px)
                for state in projection.frame_states[1]
            },
        )

    def test_fixed_height_keeps_top_and_bottom_correlated(self) -> None:
        template = _template(1)
        cross = replace(
            _cross(template, direction=_direction()),
            top_canonical_px=7.5,
            bottom_canonical_px=247.5,
            top_fit_interval_px=FiniteInterval.exact(7.5),
            bottom_fit_interval_px=FiniteInterval.exact(247.5),
            top_full_interval_px=FiniteInterval(0.0, 20.0),
            bottom_full_interval_px=FiniteInterval(245.0, 250.0),
        )
        placement = _compose(template, _sequence(template), cross)
        projection = project_selected_placement(placement)
        self.assertEqual(
            self._cross_interval(projection, 0),
            FiniteInterval(5.0, 10.0),
        )
        self.assertEqual(
            self._cross_interval(projection, 1),
            FiniteInterval(245.0, 250.0),
        )
        self.assertTrue(
            all(
                state.bottom_at_lane_reference_px
                - state.top_at_lane_reference_px
                == 240.0
                for state in projection.frame_states[0]
            )
        )

    def test_narrower_joint_constraints_never_widen_projection(self) -> None:
        template = _template(1)
        broad = _compose(
            template,
            _sequence(template),
            replace(
                _cross(template, direction=_direction()),
                top_full_interval_px=FiniteInterval(5.0, 15.0),
                bottom_full_interval_px=FiniteInterval(245.0, 255.0),
            ),
        )
        narrow = replace(
            broad,
            cross_fit=replace(
                broad.cross_fit,
                top_full_interval_px=FiniteInterval(8.0, 12.0),
                bottom_full_interval_px=FiniteInterval(248.0, 252.0),
            ),
        )
        broad_projection = project_selected_placement(broad)
        narrow_projection = project_selected_placement(narrow)
        self.assertGreaterEqual(
            self._cross_interval(narrow_projection, 0).minimum,
            self._cross_interval(broad_projection, 0).minimum,
        )
        self.assertLessEqual(
            self._cross_interval(narrow_projection, 0).maximum,
            self._cross_interval(broad_projection, 0).maximum,
        )
        self.assertGreaterEqual(
            self._cross_interval(narrow_projection, 1).minimum,
            self._cross_interval(broad_projection, 1).minimum,
        )
        self.assertLessEqual(
            self._cross_interval(narrow_projection, 1).maximum,
            self._cross_interval(broad_projection, 1).maximum,
        )


if __name__ == "__main__":
    unittest.main()
