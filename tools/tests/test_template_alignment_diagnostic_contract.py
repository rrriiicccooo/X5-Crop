from __future__ import annotations

from dataclasses import replace
import unittest

from x5crop.domain import FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.template_alignment_diagnostic import (
    template_alignment_diagnostic,
)
from x5crop.detection.photo_geometry.template_model import (
    LocalAdvanceKind,
    LocalAdvanceRelation,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFailureKind,
    PhaseFitStatus,
)
from x5crop.detection.photo_geometry.template_residual import ResidualPattern
from tools.tests.template_test_support import (
    phase_edge as edge,
    phase_separator as separator,
    phase_template as template,
)


class TemplateAlignmentDiagnosticContractTest(unittest.TestCase):
    @staticmethod
    def _shift_observation(observation, delta: float):
        interval = FiniteInterval(
            observation.canonical_position_px + delta - 0.5,
            observation.canonical_position_px + delta + 0.5,
        )
        return replace(
            observation,
            discovery_interval_px=interval,
            canonical_position_px=observation.canonical_position_px + delta,
            fit_position_interval_px=interval,
            full_position_interval_px=interval,
        )

    def test_normal_fit_reports_direct_role_residuals_and_unbound_noise(self) -> None:
        observations = tuple(
            edge(name, coordinate)
            for name, coordinate in (
                ("start:1", 40.0),
                ("end:1", 140.0),
                ("start:2", 160.0),
                ("end:2", 260.0),
                ("unbound", 700.0),
            )
        )
        phase = fit_template_phase(observations, template(2))
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)
        diagnostic = template_alignment_diagnostic(phase, observations)
        self.assertEqual(diagnostic.pattern, ResidualPattern.NORMAL)
        self.assertEqual(len(diagnostic.role_residuals), 4)
        self.assertEqual(
            diagnostic.unbound_direct_observation_ids,
            (ObservationId("unbound"),),
        )
        self.assertLessEqual(
            diagnostic.maximum_absolute_role_residual_px or 0.0,
            1.0e-7,
        )

    def test_one_direct_suffix_shift_is_named_without_new_search(self) -> None:
        observations = tuple(
            edge(name, coordinate)
            for name, coordinate in (
                ("start:1", 40.0),
                ("end:1", 140.0),
                ("start:2", 160.0),
                ("end:2", 260.0),
            )
        )
        phase = fit_template_phase(observations, template(2))
        assert phase.best is not None
        relation = LocalAdvanceRelation(
            relation_ordinal=1,
            kind=LocalAdvanceKind.WIDE,
            delta_interval_px=FiniteInterval.exact(10.0),
            canonical_delta_px=10.0,
            observation_ids=(ObservationId("start:2"), ObservationId("end:1")),
        )
        phase = replace(
            phase,
            best=replace(phase.best, local_advance_relations=(relation,)),
        )
        diagnostic = template_alignment_diagnostic(phase, observations)
        self.assertEqual(diagnostic.pattern, ResidualPattern.LOCAL_STEP)
        self.assertEqual(diagnostic.local_advance_relations, (relation,))

    def test_unresolved_fit_preserves_the_minimum_reason(self) -> None:
        observations = (edge("only", 40.0),)
        phase = fit_template_phase(observations, template(2))
        phase = replace(
            phase,
            best=None,
            runner_up=None,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason="one direct phase anchor is still missing",
            failure_kind=PhaseFailureKind.DIRECT_PHASE_ANCHOR_UNAVAILABLE,
            winner_basis=None,
        )
        diagnostic = template_alignment_diagnostic(phase, observations)
        self.assertEqual(diagnostic.pattern, ResidualPattern.UNRESOLVED)
        self.assertEqual(
            diagnostic.unresolved_reason,
            "one direct phase anchor is still missing",
        )
        self.assertIsNone(diagnostic.absolute_phase_px)

    def test_repeated_separator_shape_conflicts_remain_diagnostic_only(self) -> None:
        observations = tuple(
            edge(name, coordinate)
            for name, coordinate in (
                ("start:1", 40.0),
                ("end:1", 140.0),
                ("start:2", 160.0),
                ("end:2", 260.0),
                ("start:3", 280.0),
                ("end:3", 380.0),
            )
        )
        phase = fit_template_phase(observations, template(3))
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)
        shifted = (
            observations[0],
            self._shift_observation(observations[1], 10.0),
            self._shift_observation(observations[2], -10.0),
            self._shift_observation(observations[3], 10.0),
            self._shift_observation(observations[4], -10.0),
            observations[5],
        )
        bands = (
            separator(
                "separator:shape:1",
                shifted[1],
                shifted[2],
                FiniteInterval.exact(0.0),
            ),
            separator(
                "separator:shape:2",
                shifted[3],
                shifted[4],
                FiniteInterval.exact(0.0),
            ),
        )
        diagnostic = template_alignment_diagnostic(
            phase,
            shifted,
            bands,
        )
        self.assertEqual(
            diagnostic.pattern,
            ResidualPattern.UNRESOLVED,
        )
        self.assertEqual(len(diagnostic.incompatible_separator_support_ids), 2)
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)
        self.assertIsNotNone(phase.best)

    def test_one_separator_width_departure_does_not_invent_a_local_step(self) -> None:
        observations = tuple(
            edge(name, coordinate)
            for name, coordinate in (
                ("start:1", 40.0),
                ("end:1", 140.0),
                ("start:2", 160.0),
                ("end:2", 260.0),
            )
        )
        phase = fit_template_phase(observations, template(2))
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)
        shifted = (
            observations[0],
            self._shift_observation(observations[1], 10.0),
            self._shift_observation(observations[2], -10.0),
            observations[3],
        )
        band = separator(
            "separator:one-width-departure",
            shifted[1],
            shifted[2],
            FiniteInterval.exact(0.0),
        )
        diagnostic = template_alignment_diagnostic(
            phase,
            shifted,
            (band,),
        )
        self.assertEqual(diagnostic.pattern, ResidualPattern.NORMAL)
        self.assertEqual(
            diagnostic.incompatible_separator_support_ids,
            (band.observation_id,),
        )
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)


if __name__ == "__main__":
    unittest.main()
