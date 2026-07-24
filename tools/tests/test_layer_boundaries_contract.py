from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.tests.architecture_contracts import (
    PROJECT_ROOT,
    RUNTIME_ROOTS,
    SOURCE_LAYER_PREFIXES,
    SourceModule,
    STANDALONE_ROOTS,
    STANDALONE_TOOL_ROOTS,
    forbidden_import_edges,
    functions_with_unused_local_assignments,
    functions_with_unused_parameters,
    functions_with_untyped_parameters,
    invalid_dataclass_default_factories,
    modules_importing_external,
    modules_with_export_lists,
    pass_through_classes,
    pass_through_source_functions,
    pass_through_tool_functions,
    reachable_source_modules,
    source_import_graph,
    source_layer_import_graph,
    source_layer_memberships,
    source_modules,
    standalone_tool_modules,
    unreferenced_dataclass_fields,
    unreferenced_methods,
    unreferenced_public_assignments,
    unreferenced_public_symbols,
    unreferenced_top_level_symbols,
    unused_imports,
    unused_tool_imports,
    unreferenced_enum_members,
    unreferenced_tool_helpers,
    unreferenced_tool_assignments,
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
    def test_deskew_is_detection_owned_with_no_legacy_runtime_path(self) -> None:
        for relative_path in (
            "x5crop/image/deskew.py",
            "x5crop/image/deskew_parameters.py",
            "x5crop/runtime/deskew.py",
            "x5crop/runtime/prepared_workspace.py",
        ):
            self.assertFalse((PROJECT_ROOT / relative_path).exists(), relative_path)
        workspace_source = (
            PROJECT_ROOT / "x5crop/detection/workspace.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class DetectionWorkspace", workspace_source)
        self.assertIn("def prepare_detection_workspace", workspace_source)
        self.assertNotIn("shared_short_axis_fixture(", (
            PROJECT_ROOT / "x5crop/detection/pipeline.py"
        ).read_text(encoding="utf-8"))
        self.assertNotIn(
            'PREPROCESS = "preprocess"',
            (PROJECT_ROOT / "x5crop/runtime/outcome.py").read_text(
                encoding="utf-8"
            ),
        )

    def test_scan_canvas_photo_edge_model_has_no_superseded_inputs(self) -> None:
        active_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT_ROOT / "x5crop").rglob("*.py")
        )
        for forbidden in (
            "minimum_observed_leverage",
            "observed_leverage",
            "photo_height_multiple",
            "ResolutionMetadataObservation",
            "FrameScaleObservation",
            "resolution_metadata",
            "source_shared_short_axes",
        ):
            self.assertNotIn(forbidden, active_source)

        photo_edge_source = (
            PROJECT_ROOT / "x5crop/detection/evidence/photo_edges.py"
        ).read_text(encoding="utf-8")
        photo_edge_configuration = (
            PROJECT_ROOT / "x5crop/configuration/photo_edges.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("minimum_path_support_ratio", photo_edge_source)
        self.assertNotIn(
            "minimum_path_support_ratio",
            photo_edge_configuration,
        )

        workspace_source = (
            PROJECT_ROOT / "x5crop/detection/workspace.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("boundary_paths_in_domain", workspace_source)
        self.assertNotIn("short_axis_boundary_path_pairs(", workspace_source)
        self.assertNotIn("short_axis_boundary_paths(", workspace_source)
        self.assertEqual(
            workspace_source.count("observe_fixed_canvas_photo_edges("),
            1,
        )
        self.assertEqual(
            workspace_source.count("observe_image_only_lane_photo_edges("),
            1,
        )
        self.assertNotIn("boundary_measurements", workspace_source)
        self.assertNotIn("if scan_canvas is None:", workspace_source)

    def test_scan_canvas_dimensions_have_one_catalog_owner(self) -> None:
        physical_tokens = ("32.22", "63.44", "224.5", "188.5")
        owners = {
            token: tuple(
                path.relative_to(PROJECT_ROOT).as_posix()
                for path in (PROJECT_ROOT / "x5crop").rglob("*.py")
                if token in path.read_text(encoding="utf-8")
            )
            for token in physical_tokens
        }
        self.assertEqual(
            owners,
            {
                token: ("x5crop/formats/scan_canvas.py",)
                for token in physical_tokens
            },
        )

    def test_active_source_import_graph_is_acyclic(self) -> None:
        self.assertEqual(_cycles(source_import_graph()), [])

    def test_source_layer_import_graph_is_acyclic(self) -> None:
        self.assertEqual(_cycles(source_layer_import_graph()), [])

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
                    "x5crop.cache",
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
        self.assertEqual(
            forbidden_import_edges(("x5crop.io",), ("x5crop.run_config",)),
            [],
        )

    def test_tiff_library_and_metadata_semantics_have_one_io_owner(self) -> None:
        self.assertEqual(modules_importing_external("tifffile"), ["x5crop.io.tiff"])

        io_source = (PROJECT_ROOT / "x5crop/io/tiff.py").read_text(encoding="utf-8")
        bootstrap_source = (PROJECT_ROOT / "x5crop/runtime/bootstrap.py").read_text(
            encoding="utf-8"
        )
        export_source = (PROJECT_ROOT / "x5crop/export/crops.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def read_tiff_page_shape", io_source)
        self.assertIn("def write_validated_tiff", io_source)
        self.assertIn("read_tiff_page_shape", bootstrap_source)
        self.assertIn("write_validated_tiff", export_source)
        self.assertNotIn("run_config", io_source)

    def test_detection_stages_follow_one_way_ownership(self) -> None:
        contracts = (
            (
                ("x5crop.detection.physical",),
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

    def test_count_independent_observations_precede_candidate_execution(self) -> None:
        self.assertEqual(
            forbidden_import_edges(
                ("x5crop.detection.candidate.execution",),
                ("x5crop.detection.evidence",),
            ),
            [],
        )
        self.assertFalse(
            (
                PROJECT_ROOT
                / "x5crop/detection/candidate/execution/source_candidates.py"
            ).exists()
        )

    def test_report_depends_on_models_not_computation_stages(self) -> None:
        self.assertEqual(
            forbidden_import_edges(
                ("x5crop.report",),
                (
                    "x5crop.detection.candidate.assessment.candidate_gate",
                    "x5crop.detection.candidate.plan.counts",
                    "x5crop.detection.final.finalize",
                ),
            ),
            [],
        )

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
        self.assertEqual(pass_through_source_functions(), [])
        self.assertEqual(
            unreferenced_enum_members("x5crop.domain", "MeasurementIdentity"),
            [],
        )

    def test_tools_and_tests_have_no_orphan_or_pass_through_helpers(self) -> None:
        self.assertEqual(unreferenced_tool_helpers(), [])
        self.assertEqual(unreferenced_tool_assignments(), [])
        self.assertEqual(pass_through_tool_functions(), [])
        self.assertEqual(unused_tool_imports(), [])

    def test_pass_through_detection_follows_parameter_attribute_chains(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "fixture.py"
            path.write_text(
                "def forwarded(candidate):\n"
                "    return typed_read_model(candidate.assessment.evidence)\n",
                encoding="utf-8",
            )
            module = SourceModule("x5crop.fixture", path)
            with patch(
                "tools.tests.architecture_contracts.source_modules",
                return_value={module.name: module},
            ):
                self.assertEqual(
                    pass_through_source_functions(),
                    ["x5crop.fixture:1:forwarded"],
                )

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
