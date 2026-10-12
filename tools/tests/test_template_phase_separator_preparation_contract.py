from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import unittest
from unittest.mock import patch

from tools.tests.template_test_support import (
    phase_edge,
    phase_separator,
    phase_template,
)
from x5crop.detection.photo_geometry import template_phase_observations as observations
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.domain import FiniteInterval


def separator_fixture():
    edges = tuple(
        replace(phase_edge(str(index), coordinate), qualified_anchor_roles=(role,))
        for index, (coordinate, role) in enumerate(
            (
                (10.0, BoundaryRole.START),
                (110.0, BoundaryRole.END),
                (130.0, BoundaryRole.START),
                (230.0, BoundaryRole.END),
            )
        )
    )
    bands = (
        phase_separator("material", edges[1], edges[2], FiniteInterval.exact(20.0)),
    )
    return edges, bands


class PhaseSeparatorPreparationContractTest(unittest.TestCase):
    def test_prepared_role_ledger_is_immutable_and_reuses_one_component_resolution(self):
        edges, bands = separator_fixture()
        expected = observations._with_separator_role_authority(
            edges, bands, maximum_material_gap_px=20.0
        )
        with patch.object(
            observations,
            "resolve_separator_support",
            wraps=observations.resolve_separator_support,
        ) as resolve:
            prepared = observations.prepare_phase_separator_support(
                edges, bands, maximum_material_gap_px=20.0
            )
        resolve.assert_called_once_with(edges, bands)
        self.assertEqual(prepared.observations, expected)
        self.assertEqual(prepared.bands, bands)
        self.assertEqual(
            prepared.resolution,
            observations.resolve_separator_support(edges, bands),
        )
        with self.assertRaises(FrozenInstanceError):
            prepared.bands = ()

    def test_competition_resolves_components_once_and_preserves_the_complete_result(self):
        edges, bands = separator_fixture()
        template = phase_template(2)
        expected = fit_template_phase(edges, template, separator_bands=bands)
        with patch.object(
            observations,
            "resolve_separator_support",
            wraps=observations.resolve_separator_support,
        ) as resolve:
            actual = fit_template_phase(edges, template, separator_bands=bands)
        resolve.assert_called_once()
        self.assertEqual(actual, expected)

    def test_local_refinement_resolves_components_once(self):
        edges, bands = separator_fixture()
        fit = fit_template_phase(edges, phase_template(2), separator_bands=bands).best
        self.assertIsNotNone(fit)
        expected = observations._refine_local_role_bindings(fit, edges, bands)
        with patch.object(
            observations,
            "resolve_separator_support",
            wraps=observations.resolve_separator_support,
        ) as resolve:
            actual = observations._refine_local_role_bindings(fit, edges, bands)
        resolve.assert_called_once()
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
