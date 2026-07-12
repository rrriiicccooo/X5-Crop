from __future__ import annotations

import unittest

from tools.tests.architecture_contracts import (
    RUNTIME_ROOTS,
    SOURCE_LAYER_PREFIXES,
    STANDALONE_ROOTS,
    STANDALONE_TOOL_ROOTS,
    forbidden_import_edges,
    functions_with_unused_local_assignments,
    functions_with_unused_parameters,
    functions_with_untyped_parameters,
    invalid_dataclass_default_factories,
    modules_with_export_lists,
    pass_through_classes,
    reachable_source_modules,
    source_import_graph,
    source_layer_memberships,
    source_modules,
    standalone_tool_modules,
    unreferenced_dataclass_fields,
    unreferenced_methods,
    unreferenced_public_assignments,
    unreferenced_public_symbols,
    unreferenced_top_level_symbols,
    unused_imports,
)


def _cycles(graph: dict[str, frozenset[str]]) -> list[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()

    def visit(node: str, path: tuple[str, ...]) -> None:
        if node in path:
            cycle = path[path.index(node) :] + (node,)
            rotations = tuple(
                cycle[index:-1] + cycle[:index] + (cycle[index],)
                for index in range(len(cycle) - 1)
            )
            found.add(min(rotations))
            return
        for target in graph.get(node, ()):  # stdlib and tools are absent
            visit(target, path + (node,))

    for module in graph:
        visit(module, ())
    return sorted(found)


class LayerBoundariesContractTest(unittest.TestCase):
    def test_active_source_import_graph_is_acyclic(self) -> None:
        self.assertEqual(_cycles(source_import_graph()), [])

    def test_every_active_module_has_one_layer_and_is_reachable(self) -> None:
        modules = set(source_modules())
        self.assertEqual(
            {
                module: source_layer_memberships(module)
                for module in modules
                if len(source_layer_memberships(module)) != 1
            },
            {},
        )
        reached = set(reachable_source_modules(RUNTIME_ROOTS | STANDALONE_ROOTS))
        self.assertEqual(sorted(modules - reached), [])
        self.assertEqual(standalone_tool_modules(), STANDALONE_TOOL_ROOTS)

    def test_foundation_layers_do_not_import_application_layers(self) -> None:
        self.assertEqual(
            forbidden_import_edges(
                (
                    "x5crop.geometry",
                    "x5crop.image",
                    "x5crop.io",
                ),
                (
                    "x5crop.runtime",
                    "x5crop.configuration",
                    "x5crop.detection",
                    "x5crop.report",
                    "x5crop.debug",
                    "x5crop.export",
                ),
            ),
            [],
        )

    def test_detection_stages_follow_one_way_ownership(self) -> None:
        contracts = (
            (
                ("x5crop.detection.physical",),
                (
                    "x5crop.detection.guidance",
                    "x5crop.detection.candidate",
                    "x5crop.detection.decision",
                    "x5crop.detection.final",
                ),
            ),
            (
                ("x5crop.detection.guidance",),
                (
                    "x5crop.detection.candidate",
                    "x5crop.detection.decision",
                    "x5crop.detection.final",
                ),
            ),
            (
                ("x5crop.detection.evidence",),
                (
                    "x5crop.detection.candidate",
                    "x5crop.detection.decision",
                    "x5crop.detection.final",
                ),
            ),
            (
                ("x5crop.detection.candidate.plan",),
                (
                    "x5crop.detection.candidate.build",
                    "x5crop.detection.candidate.assessment",
                    "x5crop.detection.candidate.selection",
                    "x5crop.detection.decision",
                ),
            ),
            (
                ("x5crop.detection.candidate.build",),
                (
                    "x5crop.detection.candidate.assessment",
                    "x5crop.detection.candidate.selection",
                    "x5crop.detection.decision",
                ),
            ),
            (
                ("x5crop.detection.candidate.assessment",),
                (
                    "x5crop.detection.candidate.selection",
                    "x5crop.detection.decision",
                    "x5crop.detection.final",
                ),
            ),
        )
        offenders = [
            edge
            for sources, targets in contracts
            for edge in forbidden_import_edges(sources, targets)
        ]
        self.assertEqual(offenders, [])

    def test_output_and_runtime_do_not_reverse_dependency_direction(self) -> None:
        self.assertEqual(
            forbidden_import_edges(("x5crop.output",), ("x5crop.detection", "x5crop.runtime")),
            [],
        )
        self.assertEqual(
            forbidden_import_edges(("x5crop.runtime",), ("x5crop.entry",)),
            [],
        )

    def test_active_source_has_no_orphans_or_unused_interfaces(self) -> None:
        self.assertEqual(unreferenced_public_assignments(), [])
        self.assertEqual(unreferenced_public_symbols(), [])
        self.assertEqual(unreferenced_top_level_symbols(), [])
        self.assertEqual(unreferenced_methods(), [])
        self.assertEqual(unreferenced_dataclass_fields(), [])
        self.assertEqual(functions_with_unused_parameters(), [])
        self.assertEqual(functions_with_unused_local_assignments(), [])
        self.assertEqual(unused_imports(), [])
        self.assertEqual(modules_with_export_lists(), [])
        self.assertEqual(pass_through_classes(), [])

    def test_active_interfaces_are_typed_and_configuration_defaults_are_explicit(self) -> None:
        self.assertEqual(functions_with_untyped_parameters(), [])
        self.assertEqual(
            invalid_dataclass_default_factories("x5crop.configuration"),
            [],
        )

    def test_source_layer_registry_contains_only_current_layers(self) -> None:
        self.assertEqual(
            tuple(SOURCE_LAYER_PREFIXES),
            (
                "core",
                "entry",
                "runtime",
                "formats",
                "configuration",
                "cache",
                "geometry",
                "image",
                "io",
                "detection",
                "output",
                "export",
                "report",
                "debug",
            ),
        )


if __name__ == "__main__":
    unittest.main()
