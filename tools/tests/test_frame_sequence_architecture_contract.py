from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT


_PHYSICAL_ROOT = PROJECT_ROOT / "x5crop/detection/physical"

_CANONICAL_OWNERS = {
    "frame_sequence_measurements.py": {
        "EdgeConstraint",
        "MeasuredFrameConstraint",
        "interval_envelope",
        "measurement_intervals_are_compatible",
        "largest_measurement_compatible_interval_indexes",
    },
    "frame_sequence_common_width.py": {
        "CommonWidthHypothesis",
        "RecurringBoundaryWidthHypothesis",
        "DimensionPlacementHypothesis",
        "measured_constraint_common_width",
        "resolve_common_frame_width",
    },
    "frame_sequence_search.py": {
        "SequenceGraphContext",
        "SequenceGraphEvaluations",
        "SequenceGraphFeasibility",
        "MeasuredFrameSequenceSearchResult",
        "measured_frame_option_rank",
        "measured_frame_sequences",
    },
    "frame_sequence_candidates.py": {
        "SequenceBuildObjectives",
        "SeparatorBandBinding",
        "SequenceBuild",
        "conflicting_internal_frame_indexes",
        "external_endpoint_alternatives",
        "physically_preferred_builds",
        "representative_build",
        "build_preserves_visible_content",
        "frame_slots_are_strictly_monotonic",
        "resolve_edge_constraint",
        "spacing_from_frame_edges",
        "uncorroborated_overlap_extent",
        "unexplained_spacing_extent",
        "uncorroborated_contact_count",
        "inferred_boundary_count",
        "long_axis_assignments_for_slots",
        "bindings_for_resolved_slots",
        "rebuild_sequence_build",
    },
    "frame_sequence_consensus.py": {
        "sequence_assignment_consensus",
        "internal_geometry_uncertainty_boundary",
        "apply_internal_geometry_uncertainty",
        "external_safety_boundary",
        "apply_external_safety_envelope",
    },
    "frame_sequence_separator_assignment.py": {
        "separator_band_edge_constraint",
        "observed_band_edges",
        "candidate_specific_separator_edge_roles",
        "candidate_specific_holder_band_roles",
        "spacing_for_band",
        "separator_observation_assignment",
        "assign_unique_separator_observations",
        "separator_assignments_from_bindings",
    },
    "frame_sequence_boundary_roles.py": {
        "corroborate_build_roles_from_repeated_frame_width",
        "corroborate_build_roles_from_physical_scale",
        "corroborate_adjacent_boundary_pair",
        "corroborate_build_adjacent_boundary_roles",
        "corroborate_build_boundary_roles",
    },
    "frame_sequence_candidate_resolution.py": {
        "holder_boundaries",
        "resolve_dimension_boundaries_from_common_width",
        "resolve_build_dimension_boundaries",
        "resolve_build_physical_boundaries",
    },
}


def _definitions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _relative_import_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level <= 0:
            continue
        if node.module:
            modules.add(node.module)
        else:
            modules.update(alias.name for alias in node.names)
    return modules


class FrameSequenceArchitectureContractTest(unittest.TestCase):
    def test_frame_sequence_authorities_have_one_owner(self) -> None:
        all_definitions = {
            path.name: _definitions(path)
            for path in _PHYSICAL_ROOT.glob("*.py")
        }
        for owner, symbols in _CANONICAL_OWNERS.items():
            with self.subTest(owner=owner):
                self.assertTrue((_PHYSICAL_ROOT / owner).is_file())
            for symbol in symbols:
                with self.subTest(symbol=symbol):
                    self.assertEqual(
                        sorted(
                            name
                            for name, definitions in all_definitions.items()
                            if symbol in definitions
                        ),
                        [owner],
                    )

    def test_common_width_depends_on_measurements_in_one_direction(self) -> None:
        measurements = _PHYSICAL_ROOT / "frame_sequence_measurements.py"
        common_width = _PHYSICAL_ROOT / "frame_sequence_common_width.py"

        self.assertTrue(
            _relative_import_modules(measurements).isdisjoint(
                {
                    "frame_sequence_common_width",
                    "frame_sequence_search",
                    "frame_sequence_candidates",
                    "frame_sequence_consensus",
                    "frame_sequence_separator_assignment",
                    "frame_sequence_boundary_roles",
                    "frame_sequence_candidate_resolution",
                    "frame_sequence_solver",
                }
            )
        )
        self.assertIn(
            "frame_sequence_measurements",
            _relative_import_modules(common_width),
        )
        self.assertNotIn(
            "frame_sequence_search",
            _relative_import_modules(common_width),
        )
        self.assertNotIn(
            "frame_sequence_candidates",
            _relative_import_modules(common_width),
        )
        self.assertNotIn(
            "frame_sequence_consensus",
            _relative_import_modules(common_width),
        )
        self.assertNotIn(
            "frame_sequence_separator_assignment",
            _relative_import_modules(common_width),
        )
        self.assertNotIn(
            "frame_sequence_boundary_roles",
            _relative_import_modules(common_width),
        )
        self.assertNotIn(
            "frame_sequence_candidate_resolution",
            _relative_import_modules(common_width),
        )
        self.assertNotIn(
            "frame_sequence_solver",
            _relative_import_modules(common_width),
        )

    def test_search_depends_on_lower_physical_owners_not_solver(self) -> None:
        search = _PHYSICAL_ROOT / "frame_sequence_search.py"
        imports = _relative_import_modules(search)

        self.assertTrue(
            {
                "frame_sequence_measurements",
                "frame_sequence_common_width",
            }.issubset(imports)
        )
        self.assertNotIn("frame_sequence_solver", imports)
        self.assertTrue(
            imports.isdisjoint(
                {
                    "frame_sequence_candidates",
                    "frame_sequence_consensus",
                    "frame_sequence_separator_assignment",
                    "frame_sequence_boundary_roles",
                    "frame_sequence_candidate_resolution",
                }
            )
        )

    def test_candidate_owner_does_not_depend_on_higher_owners(self) -> None:
        candidates = _PHYSICAL_ROOT / "frame_sequence_candidates.py"

        self.assertTrue(
            {
                "frame_sequence_measurements",
            }.issubset(_relative_import_modules(candidates))
        )
        self.assertTrue(
            _relative_import_modules(candidates).isdisjoint(
                {
                    "frame_sequence_search",
                    "frame_sequence_consensus",
                    "frame_sequence_separator_assignment",
                    "frame_sequence_boundary_roles",
                    "frame_sequence_candidate_resolution",
                    "frame_sequence_solver",
                }
            )
        )

    def test_consensus_depends_on_candidate_state_not_solver(self) -> None:
        consensus = _PHYSICAL_ROOT / "frame_sequence_consensus.py"
        imports = _relative_import_modules(consensus)

        self.assertIn("frame_sequence_candidates", imports)
        self.assertNotIn("frame_sequence_solver", imports)
        self.assertNotIn("frame_sequence_separator_assignment", imports)
        self.assertNotIn("frame_sequence_boundary_roles", imports)
        self.assertNotIn("frame_sequence_candidate_resolution", imports)

    def test_separator_assignment_depends_on_lower_facts_not_solver(self) -> None:
        assignment = (
            _PHYSICAL_ROOT / "frame_sequence_separator_assignment.py"
        )
        imports = _relative_import_modules(assignment)

        self.assertTrue(
            {
                "frame_sequence_measurements",
                "frame_sequence_candidates",
            }.issubset(imports)
        )
        self.assertTrue(
            imports.isdisjoint(
                {
                    "frame_sequence_search",
                    "frame_sequence_consensus",
                    "frame_sequence_boundary_roles",
                    "frame_sequence_candidate_resolution",
                    "frame_sequence_solver",
                }
            )
        )

    def test_boundary_roles_depend_on_measurements_and_candidates_not_solver(
        self,
    ) -> None:
        roles = _PHYSICAL_ROOT / "frame_sequence_boundary_roles.py"
        imports = _relative_import_modules(roles)

        self.assertTrue(
            {
                "frame_sequence_measurements",
                "frame_sequence_candidates",
            }.issubset(imports)
        )
        self.assertTrue(
            imports.isdisjoint(
                {
                    "frame_sequence_search",
                    "frame_sequence_consensus",
                    "frame_sequence_separator_assignment",
                    "frame_sequence_candidate_resolution",
                    "frame_sequence_solver",
                }
            )
        )

    def test_candidate_resolution_consumes_lower_owners_not_solver(self) -> None:
        resolution = _PHYSICAL_ROOT / "frame_sequence_candidate_resolution.py"
        imports = _relative_import_modules(resolution)

        self.assertTrue(
            {
                "frame_sequence_measurements",
                "frame_sequence_common_width",
                "frame_sequence_candidates",
                "frame_sequence_boundary_roles",
            }.issubset(imports)
        )
        self.assertTrue(
            imports.isdisjoint(
                {
                    "frame_sequence_search",
                    "frame_sequence_consensus",
                    "frame_sequence_separator_assignment",
                    "frame_sequence_solver",
                }
            )
        )

    def test_search_result_owns_budget_state_not_final_decision(self) -> None:
        from x5crop.detection.physical.frame_sequence_search import (
            MeasuredFrameSequenceSearchResult,
        )

        self.assertEqual(
            tuple(field.name for field in fields(MeasuredFrameSequenceSearchResult)),
            (
                "sequences",
                "assignment_evaluations",
                "budget_exhausted",
            ),
        )

    def test_solver_does_not_compatibility_export_owned_symbols(self) -> None:
        solver = _PHYSICAL_ROOT / "frame_sequence_solver.py"
        tree = ast.parse(solver.read_text(encoding="utf-8"), filename=str(solver))
        owned_symbols = set().union(*_CANONICAL_OWNERS.values())

        imported_names = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module
            in {
                "frame_sequence_measurements",
                "frame_sequence_common_width",
                "frame_sequence_search",
                "frame_sequence_candidates",
                "frame_sequence_consensus",
                "frame_sequence_separator_assignment",
                "frame_sequence_boundary_roles",
                "frame_sequence_candidate_resolution",
            }
            for alias in node.names
        }
        assigned_names = {
            target.id
            for node in tree.body
            for target in (
                node.targets
                if isinstance(node, ast.Assign)
                else (node.target,)
                if isinstance(node, ast.AnnAssign)
                else ()
            )
            if isinstance(target, ast.Name)
        }
        self.assertTrue(imported_names.isdisjoint(owned_symbols))
        self.assertTrue(assigned_names.isdisjoint(owned_symbols))


if __name__ == "__main__":
    unittest.main()
