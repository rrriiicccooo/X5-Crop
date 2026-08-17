from __future__ import annotations

import unittest

from x5crop.detection.photo_geometry.observation_types import BoundaryEdgeObservation
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_model import (
    PhaseLatticeAuthority,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_pitch import (
    calibrate_template_source_pitch,
)
from x5crop.domain import FiniteInterval, ObservationId


def edge(name: str, coordinate: float) -> BoundaryEdgeObservation:
    return BoundaryEdgeObservation(
        observation_id=ObservationId(name),
        run_id=f"run:{name}",
        coordinate_interval_px=FiniteInterval(coordinate - 1.0, coordinate + 1.0),
        transition_ids=(ObservationId(f"transition:{name}"),),
        trace_coordinates_px=(0, 10, 20),
        polarity=1,
        support_fraction=1.0,
        continuous_support_fraction=1.0,
        fit_residual_px=0.0,
        canonical_direction_degrees=None,
        fit_direction_interval_degrees=None,
        full_direction_interval_degrees=None,
        qualified_anchor_roles=(BoundaryRole.START,),
    )


def template() -> TemplateSpec:
    return TemplateSpec(
        template_id="pitch-template",
        frame_width_px=FiniteInterval(98.0, 102.0),
        pitch_px=FiniteInterval(118.0, 126.0),
        nominal_gap_px=FiniteInterval(18.0, 24.0),
        count=3,
        phase_lattice_authority=PhaseLatticeAuthority(
            period_px=FiniteInterval(118.0, 126.0),
            cycle_origin_px=0.0,
            minimum_slot_offset=-1,
            maximum_slot_offset=20,
        ),
    )


class TemplatePitchContractTest(unittest.TestCase):
    def test_two_adjacent_same_role_advances_authorize_source_pitch(self) -> None:
        observations = (edge("start:1", 40.0), edge("start:2", 160.0), edge("start:3", 280.0))
        phase = fit_template_phase(observations, template())
        calibrated = calibrate_template_source_pitch(
            template(),
            phase,
            observations,
        )
        self.assertEqual(calibrated.pitch_px.minimum, 118.0)
        self.assertEqual(calibrated.pitch_px.maximum, 122.0)
        self.assertEqual(calibrated.phase_lattice_authority.period_px, calibrated.pitch_px)
        self.assertEqual(calibrated.gap_prior_px, FiniteInterval(16.0, 24.0))

    def test_one_advance_or_discrete_advances_do_not_rewrite_prior(self) -> None:
        compiled = template()
        two = (edge("two:1", 40.0), edge("two:2", 160.0))
        phase = fit_template_phase(two, compiled)
        self.assertIs(
            calibrate_template_source_pitch(compiled, phase, two),
            compiled,
        )


if __name__ == "__main__":
    unittest.main()
