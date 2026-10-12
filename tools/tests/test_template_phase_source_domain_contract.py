from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from x5crop.detection.photo_geometry import template_phase_competition as phase_competition
from tools.tests.template_test_support import (
    phase_edge as edge,
    placement_sequence,
    phase_sequence_measurement,
    phase_template as template,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.model import BoundaryAxis
from x5crop.detection.photo_geometry.template_model import (
    SeparatorRelationKind,
    SeparatorRelation,
)
from x5crop.detection.photo_geometry.template_phase_competition import (
    _candidate_respects_holder_or_terminal_source,
    fit_template_phase,
)
from x5crop.detection.photo_geometry.template_phase_state import (
    _merge_continuous_placement,
    _same_continuous_placement,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase_candidate_with_adjacency_relations
from x5crop.detection.photo_geometry.template_source_domain import (
    PhaseSourceDomain,
    source_clipped_terminal_roles,
)
from x5crop.detection.photo_geometry.axis_layout import axis_interval
from x5crop.detection.photo_geometry.template_phase_candidate_model import _BoundFit
from x5crop.detection.photo_geometry.template_phase_model import TemplatePhaseInput
from x5crop.domain import (
    Box,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
    WorkspaceExtent,
)


class TemplatePhaseSourceDomainContractTest(unittest.TestCase):
    def test_source_classification_distinguishes_invalid_unclipped_and_clipped(self) -> None:
        domain = PhaseSourceDomain("lane:test", Box(0, 0, 1000, 1000), WorkspaceExtent(1000, 1000), BoundaryAxis.X)
        def classify(positions, direction=1):
            return source_clipped_terminal_roles(SimpleNamespace(
                model_role_positions_px=positions,
                template=SimpleNamespace(direction=direction),
            ), domain)
        self.assertEqual(classify((50, 300, 400, 700)), ())
        self.assertEqual(classify((-100, 300, 400, 700)), (0,))
        self.assertEqual(classify((50, 300, 400, 1100)), (3,))
        self.assertEqual(classify((-100, 300, 400, 1100)), (0, 3))
        self.assertEqual(classify((1100, 700, 400, -100), -1), (0, 3))
        self.assertIsNone(classify((-100, -0.5, 400, 700)))

    def test_twenty_terminal_geometry_cases_preserve_the_legacy_first_check(self) -> None:
        full = PhaseSourceDomain("lane:test", Box(0, 0, 1000, 1000), WorkspaceExtent(1000, 1000), BoundaryAxis.X)
        internal = replace(full, sampling_authority_box=Box(100, 0, 900, 1000))
        half = replace(full, sampling_authority_box=Box(0, 0, 500, 1000))
        dual = replace(full, sampling_authority_box=Box(0, 0, 1000, 500))
        vertical = replace(full, source_extent=WorkspaceExtent(80, 100), sampling_authority_box=Box(0, 0, 80, 100), width_axis=BoundaryAxis.Y)
        vertical_internal = replace(vertical, sampling_authority_box=Box(0, 10, 80, 90))
        cases = (
            ("first START", (-100, 200, 300, 600, 700, 950), 1, full, True),
            ("last END", (50, 300, 400, 700, 800, 1100), 1, full, True),
            ("both terminals", (-100, 200, 300, 600, 700, 1100), 1, full, True),
            ("internal low", (80, 280, 400, 600, 750, 950), 1, internal, False),
            ("internal high", (50, 150, 200, 300, 400, 600), 1, half, False),
            ("whole first frame outside", (-250, -50, 100, 300, 500, 700), 1, full, False),
            ("zero visible first frame", (-100, -0.5, 100, 300, 500, 700), 1, full, False),
            ("interior role outside", (-100, 100, -20, 200, 400, 1200), 1, full, False),
            ("reverse both terminals", (1100, 800, 700, 400, 300, -100), -1, full, True),
            ("reverse wrong source side", (-100, 200, 300, 600, 700, 1100), -1, full, False),
            ("dual lane long side", (50, 300, 400, 700, 800, 1100), 1, dual, True),
            ("no source proof", (50, 300, 400, 700, 800, 1100), 1, None, False),
            ("old holder slack", (-5, 200, 300, 600, 700, 1005), 1, full, True),
            ("canonical vertical", (-20, 10, 20, 40, 60, 120), 1, vertical, True),
            ("internal vertical", (-20, 20, 30, 50, 60, 120), 1, vertical_internal, False),
            ("nonpositive interior frame", (-100, 200, 600, 300, 700, 1100), 1, full, False),
            ("whole last frame outside", (50, 300, 400, 700, 1100, 1300), 1, full, False),
            ("zero visible last frame", (50, 300, 400, 700, 999.5, 1100), 1, full, False),
            ("positive visible sliver", (-100, -0.499, 100, 300, 500, 700), 1, full, True),
            ("legacy path without proof", (-5, 200, 300, 600, 700, 1005), 1, None, True),
        )
        self.assertEqual(len(cases), 20)
        for name, positions, direction, domain, expected in cases:
            with self.subTest(name=name):
                holder = axis_interval((domain or full).sampling_authority_box, (domain or full).width_axis)
                fit = SimpleNamespace(model_role_positions_px=positions, template=SimpleNamespace(direction=direction))
                self.assertEqual(_candidate_respects_holder_or_terminal_source(
                    fit, holder_span_px=holder, holder_slack_px=8.0, source_domain=domain,
                ), expected)

    def test_source_domain_registration_is_typed_and_bound_to_holder_and_queries(self) -> None:
        domain = PhaseSourceDomain("lane:test", Box(0, 0, 1000, 1000), WorkspaceExtent(1000, 1000), BoundaryAxis.X)
        holder = axis_interval(domain.sampling_authority_box, domain.width_axis)
        measurement = phase_sequence_measurement("source-domain", holder)
        compiled = template(2)
        kwargs = dict(observations=(), separator_bands=(), template=compiled, scale_px_per_mm=None,
            holder_span_px=holder, phase_authority_px=None,
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(compiled),
            sequence_measurement_sets=(measurement,), source_domain=domain)
        self.assertIs(TemplatePhaseInput(**kwargs).source_domain, domain)
        for changes in (
            {"holder_span_px": FiniteInterval(1.0, 999.0)},
            {"sequence_measurement_sets": (replace(measurement, query=replace(measurement.query, lane_id="lane:other")),)},
            {"sequence_measurement_sets": (replace(measurement, query=replace(measurement.query, boundary_axis=BoundaryAxis.Y)),)},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                TemplatePhaseInput(**(kwargs | changes))
        with self.assertRaises(TypeError):
            TemplatePhaseInput(**(kwargs | {"source_domain": True}))
        with self.assertRaises(TypeError):
            fit_template_phase((), compiled, holder_span_px=holder, source_domain=True)
        with self.assertRaises(ValueError):
            fit_template_phase((), compiled, holder_span_px=FiniteInterval(1.0, 999.0), source_domain=domain)
        with self.assertRaises(ValueError):
            replace(domain, source_extent=WorkspaceExtent(1000.0, 1000))
        with self.assertRaises(ValueError):
            replace(domain, sampling_authority_box=Box(0, 0, 1001, 1000))

    def test_exact_continuous_merge_is_idempotent_but_nonidentical_hull_still_rejects(self) -> None:
        fit = placement_sequence(template(2))
        authority = replace(fit.template.phase_lattice_authority, period_px=PositiveInterval(120.0, 125.0))
        fit = replace(fit, template=replace(fit.template, phase_lattice_authority=authority),
            phase_lattice_fit=replace(fit.phase_lattice_fit, authority=authority,
                cycle_phase_interval_px=FiniteInterval(99.0, 121.0)))
        for left_compatible in (False, True):
            for right_compatible in (False, True):
                merged = _merge_continuous_placement(_BoundFit(fit, left_compatible), _BoundFit(fit, right_compatible))
                self.assertIs(merged.fit, fit)
                self.assertEqual(merged.residual_compatible, left_compatible and right_compatible)
        intervals = list(fit.model_full_role_intervals_px)
        intervals[0] = FiniteInterval(intervals[0].minimum - 1.0, intervals[0].maximum + 1.0)
        other = replace(fit, model_full_role_intervals_px=tuple(intervals))
        self.assertTrue(_same_continuous_placement(fit, other))
        with self.assertRaisesRegex(ValueError, "hull crosses a lattice period"):
            _merge_continuous_placement(_BoundFit(fit, True), _BoundFit(other, True))

    def test_normal_and_adjacency_refit_share_the_registered_source_proof(self) -> None:
        compiled = template(2)
        observations = tuple(edge(f"proof:{index}", value) for index, value in enumerate((10.0, 110.0, 130.0, 230.0)))
        domain = PhaseSourceDomain("lane:test", Box(0, 0, 600, 100), WorkspaceExtent(600, 100), BoundaryAxis.X)
        holder = axis_interval(domain.sampling_authority_box, domain.width_axis)
        phase_input = TemplatePhaseInput(observations=observations, separator_bands=(), template=compiled,
            scale_px_per_mm=None, holder_span_px=holder, phase_authority_px=None,
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(compiled),
            sequence_measurement_sets=(phase_sequence_measurement("source-refit", holder),), source_domain=domain)
        relation = SeparatorRelation(relation_ordinal=1, kind=SeparatorRelationKind.NORMAL,
            delta_interval_px=FiniteInterval.exact(0.0), canonical_delta_px=0.0,
            separator_band_observation_id=ObservationId("proof:band"),
            end_edge_observation_id=observations[1].observation_id,
            next_start_edge_observation_id=observations[2].observation_id,
            signed_gap_interval_px=FiniteInterval.exact(20.0), canonical_signed_gap_px=20.0)
        analysis = SimpleNamespace(unresolved_reason=None, adjacency_facts=(), relations=(relation,), evaluated_adjacency_count=1)
        with (
            patch.object(phase_competition, "fit_template_phase", wraps=fit_template_phase) as fits,
            patch("x5crop.detection.photo_geometry.template_residual.derive_adjacency_relations", return_value=analysis),
        ):
            fit_template_phase_candidate_with_adjacency_relations(phase_input)
        self.assertEqual(fits.call_count, 2)
        self.assertTrue(all(call.kwargs["source_domain"] is domain for call in fits.call_args_list))


if __name__ == "__main__":
    unittest.main()
