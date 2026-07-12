from __future__ import annotations

from dataclasses import MISSING, fields
from pathlib import Path
import unittest
from unittest.mock import patch

from x5crop.configuration.bundle import DetectionConfigurationBundle
from x5crop.configuration.model import DetectionConfiguration


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DetectionConfigurationBundleTests(unittest.TestCase):
    def test_bundle_resolves_active_and_lane_configurations(self) -> None:
        bundle = DetectionConfigurationBundle.for_format_mode(
            "135-dual",
            "full",
        )

        with patch(
            "x5crop.configuration.bundle.get_detection_configuration",
            side_effect=AssertionError(
                "configuration lookup escaped the runtime boundary"
            ),
        ):
            self.assertIs(
                bundle.configuration_for("135-dual", "full"),
                bundle.initial_configuration,
            )
            self.assertEqual(
                bundle.configuration_for(
                    "135",
                    "full",
                ).physical_spec.format_id,
                "135",
            )
            self.assertEqual(
                bundle.initial_configuration.physical_spec.lane_count,
                2,
            )

    def test_bundle_rejects_unresolved_configuration_requests(self) -> None:
        bundle = DetectionConfigurationBundle.for_format_mode("135", "full")

        with self.assertRaises(KeyError):
            bundle.configuration_for("135", "partial")

    def test_detection_layers_do_not_resolve_configuration_or_format_registries(
        self,
    ) -> None:
        banned = ("get_detection_configuration", "FORMATS[")
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop" / "detection").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(
                        f"{path.relative_to(PROJECT_ROOT)}: {term}"
                    )

        self.assertEqual(offenders, [])

    def test_detection_configuration_requires_all_runtime_surfaces(self) -> None:
        field_names = {
            field.name for field in fields(DetectionConfiguration)
        }
        self.assertIn("physical_spec", field_names)
        self.assertTrue(
            {"format_id", "family", "default_count"}.isdisjoint(field_names)
        )

        runtime_surfaces = {"diagnostics"}
        defaults = {
            field.name: (field.default, field.default_factory)
            for field in fields(DetectionConfiguration)
            if field.name in runtime_surfaces
        }
        self.assertEqual(set(defaults), runtime_surfaces)
        for default, default_factory in defaults.values():
            self.assertIs(default, MISSING)
            self.assertIs(default_factory, MISSING)


if __name__ == "__main__":
    unittest.main()
