from __future__ import annotations

from pathlib import Path
import unittest

from tools.release.manifest import RELEASE_FILES


ROOT = Path(__file__).resolve().parents[2]


class RepositoryContractTest(unittest.TestCase):
    def test_runtime_dependencies_have_one_contract_and_thin_launchers(self) -> None:
        contract = ROOT / "tools/install/dependencies.toml"
        self.assertTrue(contract.is_file())
        self.assertFalse((ROOT / "tools/install/requirements.txt").exists())
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("tools/install/dependency_manager.py", workflow)
        self.assertIn("tools/install/dependencies.toml", workflow)
        self.assertNotIn("paths-ignore", workflow)

        for relative in (
            "tools/install/X5_Crop_Mac_install.command",
            "tools/install/X5_Crop_win_install.bat",
            "X5_Crop_Mac.command",
            "X5_Crop_win.bat",
        ):
            with self.subTest(path=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("dependency_manager.py", source)
                self.assertIn("dependencies.toml", source)
                self.assertIn(" check", source)

    def test_installation_docs_match_checkout_and_release_layouts(self) -> None:
        documents = (
            ROOT / "docs/quick-start.zh-CN.md",
            ROOT / "docs/quick-start.en.md",
            ROOT / "docs/user-guide.zh-CN.md",
            ROOT / "docs/user-guide.en.md",
        )
        repository_installers = (
            "tools/install/X5_Crop_Mac_install.command",
            "tools/install/X5_Crop_win_install.bat",
        )
        for path in documents:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                for installer in repository_installers:
                    self.assertIn(installer, source)
                self.assertIn("`install/`", source)

        release_sources = dict(RELEASE_FILES)
        for installer in repository_installers:
            release_path = installer.removeprefix("tools/")
            self.assertEqual(release_sources[release_path], installer)

    def test_public_launcher_is_only_the_current_entrypoint(self) -> None:
        launcher = (ROOT / "X5_Crop.py").read_text(encoding="utf-8")
        self.assertEqual(len(launcher.splitlines()), 13)
        self.assertIn("from x5crop.entry.cli import main", launcher)


if __name__ == "__main__":
    unittest.main()
