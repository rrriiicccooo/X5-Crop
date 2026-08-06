from __future__ import annotations

from pathlib import Path
import unittest

from tools.install.dependency_manager import (
    CONFLICTING_OPENCV_DISTRIBUTIONS,
    build_uninstall_plan,
    fresh_installed_versions,
    load_pins,
)


ROOT = Path(__file__).resolve().parents[2]


class DependencyInstallerContractTest(unittest.TestCase):
    def test_known_cv2_namespace_conflicts_are_explicit(self) -> None:
        self.assertEqual(
            CONFLICTING_OPENCV_DISTRIBUTIONS,
            (
                "opencv-contrib-python",
                "opencv-contrib-python-headless",
                "opencv-python",
                "opencv-python-rolling",
            ),
        )

    def test_fresh_version_lookup_uses_a_new_interpreter(self) -> None:
        versions = fresh_installed_versions({"pip": "pip"})
        self.assertIn("pip", versions)

    def test_installer_avoids_source_builds_and_persistent_wheel_cache(self) -> None:
        source = (ROOT / "tools/install/dependency_manager.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"--only-binary=:all:"', source)
        self.assertIn('"--no-cache-dir"', source)
        self.assertIn('"--no-deps"', source)

    def test_requirements_are_the_complete_exact_v5_set(self) -> None:
        pins = load_pins(ROOT / "tools/install/requirements.txt")
        self.assertEqual(
            tuple((pin.canonical_name, pin.version) for pin in pins),
            (
                ("numpy", "2.5.1"),
                ("scipy", "1.18.0"),
                ("opencv-python-headless", "5.0.0.93"),
                ("tifffile", "2026.7.31"),
                ("imagecodecs", "2026.6.26"),
                ("pillow", "12.3.0"),
            ),
        )

    def test_uninstaller_never_removes_preexisting_or_changed_packages(self) -> None:
        receipt = (
            {
                "distribution": "numpy",
                "canonical_name": "numpy",
                "preexisting_version": "2.4.0",
                "installed_version": "2.5.1",
            },
            {
                "distribution": "imagecodecs",
                "canonical_name": "imagecodecs",
                "preexisting_version": None,
                "installed_version": "2026.6.26",
            },
            {
                "distribution": "Pillow",
                "canonical_name": "pillow",
                "preexisting_version": None,
                "installed_version": "12.3.0",
            },
        )
        plan = build_uninstall_plan(
            receipt,
            {
                "numpy": "2.5.1",
                "imagecodecs": "2027.1.1",
                "pillow": "12.3.0",
            },
            {},
        )
        self.assertEqual(plan.removable, ("Pillow",))
        self.assertIn("numpy", {name.lower() for name in plan.preserved})
        self.assertIn("imagecodecs", plan.preserved)

    def test_external_dependency_preservation_propagates_to_its_dependencies(
        self,
    ) -> None:
        receipt = tuple(
            {
                "distribution": distribution,
                "canonical_name": canonical,
                "preexisting_version": None,
                "installed_version": version,
            }
            for distribution, canonical, version in (
                ("numpy", "numpy", "2.5.1"),
                ("SciPy", "scipy", "1.18.0"),
                ("opencv-python-headless", "opencv-python-headless", "5.0.0.93"),
            )
        )
        plan = build_uninstall_plan(
            receipt,
            {
                "numpy": "2.5.1",
                "scipy": "1.18.0",
                "opencv-python-headless": "5.0.0.93",
            },
            {
                "scipy": {"another-photo-app"},
                "numpy": {"scipy", "opencv-python-headless"},
            },
        )
        self.assertEqual(plan.removable, ("opencv-python-headless",))
        self.assertIn("SciPy", plan.preserved)
        self.assertIn("numpy", plan.preserved)


if __name__ == "__main__":
    unittest.main()
