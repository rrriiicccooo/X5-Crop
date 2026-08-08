from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from tools.regression.non_detection_freeze import (
    BASELINE_PATH,
    PIXEL_TOLERANCE,
    assert_semantically_equal,
    load_protected_paths,
    validate_baseline,
)


class NonDetectionFreezeContractTests(unittest.TestCase):
    def test_tracked_baseline_and_exact_manifest_are_strict(self) -> None:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        validate_baseline(baseline)
        rows = load_protected_paths()
        self.assertIn(
            ("historical", "tools/regression/accuracy.py"),
            rows,
        )
        self.assertIn(
            ("anchor", "tools/regression/non_detection_freeze.py"),
            rows,
        )

    def test_normalized_schema_rejects_missing_or_extra_fields(self) -> None:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        missing = copy.deepcopy(baseline)
        missing["tasks"][0].pop("canonical")
        with self.assertRaisesRegex(ValueError, "missing, extra, or reordered"):
            validate_baseline(missing)
        extra = copy.deepcopy(baseline)
        extra["tasks"][0]["unexpected"] = None
        with self.assertRaisesRegex(ValueError, "missing, extra, or reordered"):
            validate_baseline(extra)

    def test_semantic_comparison_uses_frozen_numeric_tolerances(self) -> None:
        assert_semantically_equal(
            {"coordinate_px": 10.0},
            {"coordinate_px": 10.0 + PIXEL_TOLERANCE / 2.0},
        )
        with self.assertRaisesRegex(ValueError, "numeric semantic drift"):
            assert_semantically_equal(
                {"coordinate_px": 10.0},
                {"coordinate_px": 10.0 + PIXEL_TOLERANCE * 2.0},
            )

    def test_accuracy_owner_remains_byte_frozen(self) -> None:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        expected = baseline["comparator_dependencies"][
            "tools/regression/accuracy.py"
        ]
        import hashlib

        actual = hashlib.sha256(
            Path("tools/regression/accuracy.py").read_bytes()
        ).hexdigest()
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
