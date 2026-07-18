from __future__ import annotations

import ast
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
    def test_measurement_and_common_width_authority_have_one_owner(self) -> None:
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
                    "frame_sequence_solver",
                }
            )
        )
        self.assertIn(
            "frame_sequence_measurements",
            _relative_import_modules(common_width),
        )
        self.assertNotIn(
            "frame_sequence_solver",
            _relative_import_modules(common_width),
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
