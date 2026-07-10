from __future__ import annotations

from dataclasses import MISSING, fields
from pathlib import Path
import unittest
from unittest.mock import patch

from x5crop.policies.runtime.bundle import DetectionPolicyBundle
from x5crop.policies.runtime.policy import DetectionPolicy


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DetectionPolicyBundleTests(unittest.TestCase):
    def test_bundle_resolves_active_and_lane_policies_at_construction(self) -> None:
        bundle = DetectionPolicyBundle.for_format_mode("135-dual", "full")

        with patch(
            "x5crop.policies.runtime.bundle.get_detection_policy",
            side_effect=AssertionError("policy lookup escaped the runtime boundary"),
        ):
            self.assertIs(bundle.policy_for("135-dual", "full"), bundle.initial_policy)
            self.assertEqual(
                bundle.policy_for("135", "full").physical_spec.format_id.value,
                "135",
            )
            self.assertEqual(bundle.initial_policy.physical_spec.lane_count, 2)

    def test_bundle_rejects_unresolved_policy_requests(self) -> None:
        bundle = DetectionPolicyBundle.for_format_mode("135", "full")

        with self.assertRaises(KeyError):
            bundle.policy_for("135", "partial")

    def test_detection_layers_do_not_resolve_policy_or_format_registries(self) -> None:
        banned = ("get_detection_policy", "FORMATS[")
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop" / "detection").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_detection_policy_requires_all_runtime_surfaces(self) -> None:
        field_names = {field.name for field in fields(DetectionPolicy)}
        self.assertIn("physical_spec", field_names)
        self.assertTrue({"format_id", "family", "default_count"}.isdisjoint(field_names))

        runtime_surfaces = {"output", "diagnostics", "report"}
        defaults = {
            field.name: (field.default, field.default_factory)
            for field in fields(DetectionPolicy)
            if field.name in runtime_surfaces
        }
        self.assertEqual(set(defaults), runtime_surfaces)
        for default, default_factory in defaults.values():
            self.assertIs(default, MISSING)
            self.assertIs(default_factory, MISSING)


if __name__ == "__main__":
    unittest.main()
