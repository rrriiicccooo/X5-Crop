from __future__ import annotations

import ast

from tools.tests.current_only_support import *


class RepositoryContractTest(unittest.TestCase):
    def test_runtime_dependency_surface_is_pinned_and_shared(self) -> None:
        contract_path = ROOT / "tools/install/dependencies.toml"
        self.assertTrue(contract_path.is_file())
        self.assertFalse((ROOT / "tools/install/requirements.txt").exists())
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("tools/install/dependency_manager.py", workflow)
        self.assertIn("tools/install/dependencies.toml", workflow)
        for relative in (
            "tools/install/X5_Crop_Mac_install.command",
            "tools/install/X5_Crop_win_install.bat",
        ):
            with self.subTest(installer=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("dependency_manager.py", text)
                self.assertIn(" check", text)
                self.assertNotIn("pip install --user -U", text)
                self.assertNotIn("ensurepip --upgrade", text)
        for relative in ("X5_Crop_Mac.command", "X5_Crop_win.bat"):
            launcher = (ROOT / relative).read_text()
            self.assertIn("dependency_manager.py", launcher)
            self.assertIn("dependencies.toml", launcher)
            self.assertIn(" check", launcher)
            self.assertNotIn("REQUIRED_IMPORTS", launcher)

    def test_repository_layout_and_release_manifest_are_current(self) -> None:
        for relative in (
            "ARCHITECTURE.md",
            "CHANGELOG.md",
            "PROJECT_MEMORY.md",
            "install",
            "X5_Crop_Mac_diagnostics.command",
            "tools/regression/golden_baseline.py",
            "tools/regression/safe_crop_acceptance.py",
            "tools/regression/gold_comparator.py",
            "tools/regression/gold_accuracy.py",
            "tools/regression/non_detection_freeze.py",
            "tools/regression/contracts/non_detection_freeze_v1.json",
            "tools/regression/contracts/non_detection_protected_paths_v1.txt",
            "tools/regression/compare.py",
            "tools/regression/template_measurement_replay.py",
            "tools/tests/test_bounded_grid_contract.py",
            "tools/tests/test_affine_tiff_foundation_contract.py",
            "tools/tests/test_chain_selection_contract.py",
            "tools/tests/test_current_only_contract.py",
            "tools/tests/test_non_detection_freeze_contract.py",
            "tools/tests/test_photo_geometry_contract.py",
            "tools/tests/test_template_measurement_replay_contract.py",
            "tools/tests/test_physical_chain_architecture_contract.py",
            "tools/tests/transaction_crash_worker.py",
        ):
            with self.subTest(absent=relative):
                self.assertFalse((ROOT / relative).exists())
        for relative in (
            "LICENSE",
            "docs/ARCHITECTURE.md",
            "docs/CHANGELOG.md",
            "docs/PROJECT_MEMORY.md",
            "tools/install/X5_Crop_Mac_install.command",
            "tools/install/X5_Crop_win_install.bat",
            "tools/install/X5_Crop_Mac_uninstall.command",
            "tools/install/X5_Crop_win_uninstall.bat",
            "tools/install/dependency_manager.py",
            "tools/install/dependencies.toml",
            "tools/tests/test_boundary_measurement_contract.py",
            "tools/tests/test_registered_measurement_contract.py",
            "tools/tests/test_fixed_format_runtime_contract.py",
            "tools/tests/test_content_veto_contract.py",
            "tools/tests/test_template_measurement_plan_contract.py",
            "tools/tests/test_template_phase_contract.py",
            "tools/tests/test_template_cross_contract.py",
            "tools/tests/test_template_placement_contract.py",
            "tools/tests/test_template_runtime_model_contract.py",
            "tools/regression/gold_geometry.py",
            "tools/regression/diagnostic_contract.py",
            "tools/regression/file_identity.py",
        ):
            with self.subTest(present=relative):
                self.assertTrue((ROOT / relative).is_file())

        release_sources = dict(RELEASE_FILES)
        self.assertIn("LICENSE", RELEASE_PATHS)
        self.assertEqual(
            release_sources["install/X5_Crop_Mac_install.command"],
            "tools/install/X5_Crop_Mac_install.command",
        )
        self.assertEqual(
            release_sources["install/X5_Crop_win_install.bat"],
            "tools/install/X5_Crop_win_install.bat",
        )
        self.assertEqual(
            release_sources["install/X5_Crop_Mac_uninstall.command"],
            "tools/install/X5_Crop_Mac_uninstall.command",
        )
        self.assertEqual(
            release_sources["install/X5_Crop_win_uninstall.bat"],
            "tools/install/X5_Crop_win_uninstall.bat",
        )
        self.assertEqual(
            release_sources["install/dependency_manager.py"],
            "tools/install/dependency_manager.py",
        )
        self.assertEqual(
            release_sources["install/dependencies.toml"],
            "tools/install/dependencies.toml",
        )

        project_memory = (ROOT / "docs/PROJECT_MEMORY.md").read_text(
            encoding="utf-8"
        )
        for obsolete in (
            "source_core_grid_authority",
            "frame_grid_authority_unavailable",
            "NO_INDEPENDENT_PHASE_AUTHORITY",
        ):
            with self.subTest(obsolete_memory=obsolete):
                self.assertNotIn(obsolete, project_memory)

    def test_public_docs_expose_user_behavior_not_internal_architecture(
        self,
    ) -> None:
        public_docs = (
            ROOT / "README.md",
            ROOT / "docs/quick-start.zh-CN.md",
            ROOT / "docs/quick-start.en.md",
            ROOT / "docs/user-guide.zh-CN.md",
            ROOT / "docs/user-guide.en.md",
        )
        forbidden = (
            "CandidateGate",
            "DecisionGate",
            "schema_revision",
            "SourceScanGeometry",
            "NominalPitch",
            "sequence_group_count",
            "gold_accuracy",
            "S062",
            "0fdb90dc",
            "dirty tree",
            "dirty 开发树",
        )
        for path in public_docs:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(path=path.name, token=token):
                    self.assertNotIn(token, text)

        architecture = (ROOT / "docs/ARCHITECTURE.md").read_text(
            encoding="utf-8"
        )
        for retired in (
            "FrameGeometryState",
            "GridInferredBlankOutputGeometry",
            "lane-local ordered DP",
            "source_coordinate_photo_geometry",
            "non-detection",
        ):
            with self.subTest(retired_architecture=retired):
                self.assertNotIn(retired, architecture)

    def test_documents_keep_their_single_current_responsibility(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        changelog = (ROOT / "docs/CHANGELOG.md").read_text(encoding="utf-8")
        memory = (ROOT / "docs/PROJECT_MEMORY.md").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("当前源码检查点是 `X5_Crop.py` V4.9", agents)
        self.assertIn("仓库只有一条 V5 current-only production path", agents)
        for task_state in (
            "当前完成边界",
            "S051/explicit",
            "S062/explicit",
            "S109/explicit",
            "精确下一步",
        ):
            with self.subTest(changelog_task_state=task_state):
                self.assertNotIn(task_state, changelog)
        for stale_memory in (
            "当前源码和 [ARCHITECTURE.md](ARCHITECTURE.md) 仍是 V4.9",
            "V5 runtime、唯一 schema",
            "第一条端到端 slice",
        ):
            with self.subTest(stale_memory=stale_memory):
                self.assertNotIn(stale_memory, memory)

    def test_completed_phase_freeze_is_not_a_verifier_owner(self) -> None:
        verifier = (ROOT / "tools/verify").read_text(encoding="utf-8")
        platform_receipt = (
            ROOT / "tools/regression/platform_receipt.py"
        ).read_text(encoding="utf-8")
        for retired in (
            "non-detection)",
            "audit)",
            "tools.regression.non_detection_freeze",
        ):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, verifier)
        self.assertNotIn("non_detection_audit", platform_receipt)
        self.assertIn(
            'PLATFORM_RECEIPT_SCHEMA = "x5crop_platform_receipt_v3"',
            platform_receipt,
        )

    def test_launcher_is_thin_and_standalone_embeds_current_modules(self) -> None:
        launcher = (ROOT / "X5_Crop.py").read_text(encoding="utf-8")
        self.assertEqual(len(launcher.splitlines()), 13)
        self.assertIn("from x5crop.entry.cli import main", launcher)
        sources = read_sources()
        for module in (
            "x5crop.detection.photo_geometry.detector",
            "x5crop.detection.photo_geometry.registered_measurement",
            "x5crop.detection.photo_geometry.measurement_model",
            "x5crop.detection.photo_geometry.search_model",
            "x5crop.detection.photo_geometry.line_observations",
            "x5crop.detection.photo_geometry.transition_tracking",
            "x5crop.detection.photo_geometry.boundary_fitting",
            "x5crop.detection.photo_geometry.source_geometry",
            "x5crop.detection.photo_geometry.content_veto",
            "x5crop.detection.photo_geometry.observations",
            "x5crop.detection.photo_geometry.separator_observations",
            "x5crop.detection.photo_geometry.profile_adapters",
            "x5crop.detection.photo_geometry.observation_types",
            "x5crop.detection.photo_geometry.template_measurement_plan",
            "x5crop.detection.photo_geometry.template_measurement_plan_model",
            "x5crop.detection.photo_geometry.template_registration",
            "x5crop.detection.photo_geometry.template_phase",
            "x5crop.detection.photo_geometry.template_phase_candidates",
            "x5crop.detection.photo_geometry.template_phase_model",
            "x5crop.detection.photo_geometry.template_residual",
            "x5crop.detection.photo_geometry.template_cross",
            "x5crop.detection.photo_geometry.template_cross_candidates",
            "x5crop.detection.photo_geometry.template_cross_model",
            "x5crop.detection.photo_geometry.template_direction",
            "x5crop.detection.photo_geometry.template_placement",
            "x5crop.detection.photo_geometry.template_selection",
            "x5crop.detection.photo_geometry.template_output",
            "x5crop.detection.photo_geometry.template_precision",
            "x5crop.detection.photo_geometry.template_gate",
            "x5crop.detection.photo_geometry.template_runtime_model",
        ):
            with self.subTest(embedded=module):
                self.assertIn(module, sources)
        for module in (
            "x5crop.detection.photo_geometry.geometry_build",
            "x5crop.detection.photo_geometry.sequence",
            "x5crop.detection.photo_geometry.solver",
            "x5crop.detection.photo_geometry.selection",
            "x5crop.detection.photo_geometry.measurement",
            "x5crop.detection.photo_geometry.chains",
            "x5crop.detection.photo_geometry.chain_materialization",
            "x5crop.detection.photo_geometry.source_chain_materialization",
            "x5crop.detection.photo_geometry.sequence_models",
            "x5crop.detection.photo_geometry.cross_proposals",
            "x5crop.detection.photo_geometry.placement_clusters",
            "x5crop.detection.photo_geometry.source_selection",
            "x5crop.detection.photo_geometry.selection_identity",
        ):
            with self.subTest(retired=module):
                self.assertNotIn(module, sources)

    def test_template_modules_have_one_owner_and_bounded_file_scope(self) -> None:
        directory = ROOT / "x5crop/detection/photo_geometry"
        modules = tuple(directory.glob("template_*.py"))
        oversized = {
            path.name: len(path.read_text(encoding="utf-8").splitlines())
            for path in modules
            if len(path.read_text(encoding="utf-8").splitlines()) > 1_000
        }
        self.assertEqual(oversized, {})

        retired_reexports = {
            "template_measurement_plan": {
                "TemplateMeasurementPlan",
                "TemplateQueryIntent",
            },
            "template_phase": {
                "PhaseFailureKind",
                "PhaseFitResult",
                "PhaseFitStatus",
                "PhaseWinnerBasis",
            },
            "template_cross": {
                "CrossFit",
                "CrossFitCompetition",
                "CrossFitStatus",
                "CrossRoleBinding",
                "TemplateCrossInput",
            },
        }
        for module, forbidden in retired_reexports.items():
            source = (directory / f"{module}.py").read_text(encoding="utf-8")
            tree = ast.parse(source)
            exported = next(
                (
                    {
                        item.value
                        for item in node.value.elts
                        if isinstance(item, ast.Constant)
                        and isinstance(item.value, str)
                    }
                    for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(
                        isinstance(target, ast.Name) and target.id == "__all__"
                        for target in node.targets
                    )
                    and isinstance(node.value, (ast.List, ast.Tuple))
                ),
                set(),
            )
            self.assertFalse(exported & forbidden)


if __name__ == "__main__":
    unittest.main()
