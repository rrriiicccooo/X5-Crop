from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.install.dependency_manager import (
    RECEIPT_SCHEMA,
    DependencyState,
    pip_package_for_record,
    build_uninstall_plan,
    check_dependencies,
    fresh_installed_versions,
    install_dependencies,
    load_dependency_contract,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "tools/install/dependencies.toml"


class DependencyInstallerContractTest(unittest.TestCase):
    def test_installer_receipt_revision_is_current_only(self) -> None:
        self.assertEqual(RECEIPT_SCHEMA, "x5crop_user_dependencies_v3")

    @staticmethod
    def _states(
        *,
        opencv_version: str | None = "5.0.0",
        opencv_provider: str = "homebrew",
    ) -> tuple[DependencyState, ...]:
        contract = load_dependency_contract(CONTRACT_PATH)
        states: list[DependencyState] = []
        for pin in contract.dependencies:
            version = (
                opencv_version if pin.name == "opencv" else pin.module_version
            )
            states.append(
                DependencyState(
                    name=pin.name,
                    module=pin.module,
                    available=version is not None,
                    module_version=version,
                    module_origin=(
                        None
                        if version is None
                        else f"/provider/{pin.name}/__init__.py"
                    ),
                    provider=(
                        "missing" if version is None else (
                            opencv_provider if pin.name == "opencv" else "external"
                        )
                    ),
                    package=(
                        None
                        if version is None
                        else (
                            "opencv"
                            if pin.name == "opencv" and opencv_provider == "homebrew"
                            else pin.pip_distribution
                        )
                    ),
                    package_version=version,
                )
            )
        return tuple(states)

    def test_dependency_contract_is_capability_based_not_platform_bound(self) -> None:
        contract = load_dependency_contract(CONTRACT_PATH)
        self.assertEqual(
            tuple(
                (
                    pin.name,
                    pin.module,
                    pin.module_version,
                    pin.pip_distribution,
                    pin.pip_version,
                    pin.homebrew_formula,
                )
                for pin in contract.dependencies
            ),
            (
                ("numpy", "numpy", "2.5.1", "numpy", "2.5.1", "numpy"),
                ("scipy", "scipy", "1.18.0", "scipy", "1.18.0", "scipy"),
                (
                    "opencv",
                    "cv2",
                    "5.0.0",
                    "opencv-python-headless",
                    "5.0.0.93",
                    "opencv",
                ),
                (
                    "tifffile",
                    "tifffile",
                    "2026.7.31",
                    "tifffile",
                    "2026.7.31",
                    None,
                ),
                (
                    "imagecodecs",
                    "imagecodecs",
                    "2026.6.26",
                    "imagecodecs",
                    "2026.6.26",
                    None,
                ),
                ("pillow", "PIL", "12.3.0", "Pillow", "12.3.0", "pillow"),
            ),
        )
        text = CONTRACT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("Darwin", text)
        self.assertNotIn("Windows", text)
        self.assertNotIn("Linux", text)

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
        self.assertIn('"--user"', source)

    def test_exact_usable_dependencies_are_reused_without_any_install(self) -> None:
        states = self._states()
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "receipt.json"
            with (
                mock.patch(
                    "tools.install.dependency_manager.inspect_dependency_states",
                    return_value=states,
                ),
                mock.patch(
                    "tools.install.dependency_manager._install_with_pip"
                ) as pip_install,
                mock.patch(
                    "tools.install.dependency_manager._update_homebrew_formula"
                ) as brew_update,
            ):
                result = install_dependencies(
                    CONTRACT_PATH,
                    receipt,
                    break_system_packages=False,
                )
                receipt_text = receipt.read_text()
        self.assertEqual(result, 0)
        pip_install.assert_not_called()
        brew_update.assert_not_called()
        self.assertIn('"action": "reused"', receipt_text)

    def test_read_only_check_distinguishes_ready_from_needs_action(self) -> None:
        with mock.patch(
            "tools.install.dependency_manager.inspect_dependency_states",
            side_effect=(
                self._states(),
                self._states(opencv_version=None),
            ),
        ):
            self.assertEqual(check_dependencies(CONTRACT_PATH, quiet=True), 0)
            self.assertEqual(check_dependencies(CONTRACT_PATH, quiet=True), 1)

    def test_missing_dependency_uses_minimal_user_pip_install(self) -> None:
        before = self._states(opencv_version=None)
        after = self._states(opencv_provider="pip")
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "receipt.json"
            with (
                mock.patch(
                    "tools.install.dependency_manager.inspect_dependency_states",
                    side_effect=(before, after),
                ),
                mock.patch(
                    "tools.install.dependency_manager.installed_versions",
                    return_value={},
                ),
                mock.patch(
                    "tools.install.dependency_manager.fresh_installed_versions",
                    return_value={"opencv-python-headless": "5.0.0.93"},
                ),
                mock.patch(
                    "tools.install.dependency_manager._ensure_pip_available",
                    return_value=0,
                ),
                mock.patch(
                    "tools.install.dependency_manager._preflight_pip",
                    return_value=0,
                ),
                mock.patch(
                    "tools.install.dependency_manager._install_with_pip",
                    return_value=0,
                ) as pip_install,
                mock.patch(
                    "tools.install.dependency_manager._update_homebrew_formula"
                ) as brew_update,
            ):
                result = install_dependencies(
                    CONTRACT_PATH,
                    receipt,
                    break_system_packages=False,
                )
        self.assertEqual(result, 0)
        self.assertEqual(
            tuple(pin.name for pin in pip_install.call_args.args[0]),
            ("opencv",),
        )
        brew_update.assert_not_called()

    def test_wrong_homebrew_dependency_updates_with_homebrew_not_pip(self) -> None:
        before = self._states(opencv_version="4.12.0")
        after = self._states()
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "receipt.json"
            with (
                mock.patch(
                    "tools.install.dependency_manager.inspect_dependency_states",
                    side_effect=(before, after),
                ),
                mock.patch(
                    "tools.install.dependency_manager._homebrew_can_supply",
                    return_value=True,
                ),
                mock.patch(
                    "tools.install.dependency_manager._update_homebrew_formula"
                ) as brew_update,
                mock.patch(
                    "tools.install.dependency_manager._install_with_pip"
                ) as pip_install,
            ):
                result = install_dependencies(
                    CONTRACT_PATH,
                    receipt,
                    break_system_packages=False,
                )
        self.assertEqual(result, 0)
        brew_update.assert_called_once_with("opencv")
        pip_install.assert_not_called()

    def test_wrong_unknown_provider_stops_instead_of_layering_duplicate(self) -> None:
        states = self._states(
            opencv_version="4.12.0",
            opencv_provider="external",
        )
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "receipt.json"
            with (
                mock.patch(
                    "tools.install.dependency_manager.inspect_dependency_states",
                    return_value=states,
                ),
                mock.patch(
                    "tools.install.dependency_manager._install_with_pip"
                ) as pip_install,
                mock.patch(
                    "tools.install.dependency_manager._update_homebrew_formula"
                ) as brew_update,
                self.assertRaisesRegex(RuntimeError, "unknown provider"),
            ):
                install_dependencies(
                    CONTRACT_PATH,
                    receipt,
                    break_system_packages=False,
                )
        pip_install.assert_not_called()
        brew_update.assert_not_called()
        self.assertFalse(receipt.exists())

    def test_ambiguous_pip_namespace_stops_before_install(self) -> None:
        contract = load_dependency_contract(CONTRACT_PATH)
        records = {
            pin.name: {
                "available": True,
                "module_version": pin.module_version,
                "module_origin": f"/user/site/{pin.module}/__init__.py",
                "import_error": None,
                "distributions": (
                    {
                        "opencv-python": {
                            "version": "5.0.0.93",
                            "root": "/user/site",
                        },
                        "opencv-python-headless": {
                            "version": "5.0.0.93",
                            "root": "/user/site",
                        },
                    }
                    if pin.name == "opencv"
                    else {}
                ),
            }
            for pin in contract.dependencies
        }
        with (
            mock.patch(
                "tools.install.dependency_manager._fresh_module_records",
                return_value=records,
            ),
            mock.patch(
                "tools.install.dependency_manager._homebrew_package_for_origin",
                return_value=None,
            ),
            self.assertRaisesRegex(RuntimeError, "ambiguous pip ownership"),
        ):
            from tools.install.dependency_manager import inspect_dependency_states

            inspect_dependency_states(contract)

    def test_equivalent_distribution_spellings_are_one_pip_owner(self) -> None:
        pillow = load_dependency_contract(CONTRACT_PATH).by_name()["pillow"]
        record = {
            "module_origin": "/user/site/PIL/__init__.py",
            "distributions": {
                "pillow": {
                    "version": "12.3.0",
                    "root": "/user/site",
                },
                "Pillow": {
                    "version": "12.3.0",
                    "root": "/user/site",
                },
            },
        }

        self.assertEqual(
            pip_package_for_record(pillow, record),
            ("Pillow", "12.3.0"),
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
                ("scipy", "scipy", "1.18.0"),
                ("imagecodecs", "imagecodecs", "2026.6.26"),
            )
        )
        plan = build_uninstall_plan(
            receipt,
            {
                "numpy": "2.5.1",
                "scipy": "1.18.0",
                "imagecodecs": "2026.6.26",
            },
            {
                "scipy": {"another-photo-app"},
                "numpy": {"scipy", "imagecodecs"},
            },
        )
        self.assertEqual(plan.removable, ("imagecodecs",))
        self.assertIn("scipy", plan.preserved)
        self.assertIn("numpy", plan.preserved)


if __name__ == "__main__":
    unittest.main()
