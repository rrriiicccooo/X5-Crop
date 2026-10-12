from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import unittest
from unittest.mock import patch

from tools.tests.template_test_support import phase_edge, phase_template
from x5crop.detection.photo_geometry import template_phase_fitting as fitting
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_phase_candidate_model import _PhaseSeed
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_observations import _facts
from x5crop.domain import FiniteInterval, ObservationId


def matching_fixture(direction=1):
    compiled = phase_template(2)
    template = replace(
        compiled,
        direction=direction,
        phase_lattice_authority=replace(
            compiled.phase_lattice_authority, minimum_slot_offset=-20
        ),
    )
    observations = tuple(
        replace(
            phase_edge(str(index), 500.0 + direction * coordinate),
            qualified_anchor_roles=(role,),
        )
        for index, (coordinate, role) in enumerate(
            (
                (0.0, BoundaryRole.START),
                (100.0, BoundaryRole.END),
                (120.0, BoundaryRole.START),
                (220.0, BoundaryRole.END),
            )
        )
    )
    return template, observations, _facts(observations)


class PhaseMatchingIndexContractTest(unittest.TestCase):
    def test_indices_are_readonly_and_bound_to_the_exact_fact_and_pair_input(self):
        template, _observations, direct = matching_fixture()
        pairs = ((direct[1], direct[2]),)
        index = fitting._PhaseMatchingIndex(direct, template.roles, pairs)
        self.assertEqual(index.centers, tuple(item.coordinate_px for item in direct))
        self.assertEqual(index.optional_separator_pairs, pairs)
        self.assertEqual(index.separator_ids, frozenset((ObservationId("1"), ObservationId("2"))))
        with self.assertRaises(FrozenInstanceError):
            index.centers = ()
        with self.assertRaises(TypeError):
            index.direct_by_id[ObservationId("0")] = direct[1]
        with self.assertRaises(TypeError):
            index.role_by_index[0] = template.roles[1]
        index.validate_input(direct, template.roles, pairs)
        with self.assertRaisesRegex(ValueError, "different input"):
            index.validate_input(tuple(list(direct)), template.roles, pairs)
        with self.assertRaisesRegex(ValueError, "different input"):
            index.validate_input(direct, template.roles, tuple(list(pairs)))
        with self.assertRaisesRegex(ValueError, "different input"):
            index.validate_input(direct, template.roles[:2], pairs)

    def test_competition_shares_one_index_across_all_existing_seeds(self):
        template, observations, _direct = matching_fixture()
        with patch.object(fitting, "_PhaseMatchingIndex", wraps=fitting._PhaseMatchingIndex) as build, patch.object(
            fitting, "_fit_seed", wraps=fitting._fit_seed
        ) as fit:
            result = fit_template_phase(observations, template)
        self.assertIsNotNone(result.best)
        build.assert_called_once()
        self.assertEqual(fit.call_count, result.receipt.phase_hypothesis_count)
        indices = {id(call.kwargs["matching_index"]) for call in fit.call_args_list}
        self.assertEqual(len(indices), 1)
        result.receipt.validate_bounds()

    def test_one_subset_index_serves_every_iteration_in_both_directions(self):
        for direction in (1, -1):
            with self.subTest(direction=direction):
                template, _observations, direct = matching_fixture(direction)
                seed = _PhaseSeed(500.0, 120.0, ((0, ObservationId("0")), (3, ObservationId("3"))))
                with patch.object(fitting, "_PhaseMatchingIndex", wraps=fitting._PhaseMatchingIndex) as build, patch.object(
                    fitting, "_match_roles", wraps=fitting._match_roles
                ) as match:
                    result = fitting._fit_seed(
                        seed,
                        direct,
                        (),
                        template.roles,
                        template,
                        (),
                        FiniteInterval.exact(120.0),
                        None,
                        2.0,
                    )
                self.assertIsNotNone(result)
                build.assert_called_once()
                self.assertGreater(match.call_count, 1)
                self.assertEqual(len({id(call.kwargs["matching_index"]) for call in match.call_args_list}), 1)
                self.assertAlmostEqual(result.fit.phase_lattice_fit.canonical_absolute_phase_px, 500.0)
                self.assertEqual(result.fit.binding_observation_ids, tuple(ObservationId(str(index)) for index in range(4)))


if __name__ == "__main__":
    unittest.main()
