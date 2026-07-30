from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
import tifffile

from tools.regression.performance import (
    MEASURED_RUN_COUNT,
    PERFORMANCE_RESULT_SCHEMA,
    LocalSampleIdentity,
    PerformanceCohortEntry,
    PerformanceRunGroup,
    PerformanceTiming,
    ProductionPerformanceResult,
    build_group_command,
    resolve_performance_sources,
)


def _timing(
    label: str,
    seconds_per_input: float,
    outputs: int,
) -> PerformanceTiming:
    return PerformanceTiming(
        label=label,
        wall_seconds=seconds_per_input * 24,
        input_count=24,
        completed_inputs=24,
        approved_inputs_with_outputs=24 if outputs else 0,
        frame_output_count=outputs,
    )


class PerformanceCertificationContractTest(unittest.TestCase):
    def _result(
        self,
        seconds_per_input: float,
        outputs: int,
    ) -> ProductionPerformanceResult:
        root = Path(tempfile.gettempdir()) / "x5crop-contract-performance"
        return ProductionPerformanceResult(
            cold=_timing("cold", seconds_per_input, outputs),
            measured=tuple(
                _timing(
                    f"measured-{index}",
                    seconds_per_input,
                    outputs,
                )
                for index in range(1, MEASURED_RUN_COUNT + 1)
            ),
            output_root=root,
            groups=(
                PerformanceRunGroup("135", "full", "horizontal"),
                PerformanceRunGroup("120-66", "partial", "vertical"),
            ),
        )

    def test_v3_requires_real_outputs_and_allows_exact_limit(self) -> None:
        no_outputs = self._result(4.0, 0)
        self.assertFalse(no_outputs.passed)
        self.assertEqual(no_outputs.certification_status, "failed")
        exact = self._result(5.0, 24)
        self.assertTrue(exact.passed)
        self.assertEqual(exact.certification_status, "certified")
        record = exact.as_record()
        self.assertEqual(record["schema"], PERFORMANCE_RESULT_SCHEMA)
        self.assertEqual(
            record["run_topology"],
            ["cold", "measured-1", "measured-2", "measured-3"],
        )
        self.assertEqual(
            record["count_modes"],
            {"full": "fixed_full", "partial": "auto"},
        )
        self.assertEqual(
            {group["count_mode"] for group in record["groups"]},
            {"fixed_full", "auto"},
        )

    def test_group_command_uses_one_boundary_count_mapping(self) -> None:
        input_path = Path("/private/tmp/input")
        output_path = Path("/private/tmp/output")
        full = build_group_command(
            PerformanceRunGroup("135", "full", "horizontal"),
            input_path,
            output_path,
        )
        partial = build_group_command(
            PerformanceRunGroup("120-66", "partial", "vertical"),
            input_path,
            output_path,
        )
        self.assertNotIn("--auto-count", full)
        self.assertNotIn("--auto-count", partial)
        self.assertNotIn("--count", full)
        self.assertNotIn("--count", partial)
        self.assertIn("--jobs", full)
        self.assertEqual(full[full.index("--jobs") + 1], "2")

    def test_wrong_input_count_cannot_be_certified(self) -> None:
        with self.assertRaises(ValueError):
            ProductionPerformanceResult(
                cold=PerformanceTiming("cold", 1.0, 1, 1, 1, 1),
                measured=tuple(
                    PerformanceTiming(
                        f"measured-{index}",
                        1.0,
                        1,
                        1,
                        1,
                        1,
                    )
                    for index in range(1, 4)
                ),
                output_root=Path("/private/tmp/x"),
                groups=(
                    PerformanceRunGroup("135", "full", "horizontal"),
                ),
            )

    def test_source_resolution_uses_canonical_catalog_path_not_sha_scan(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_root = Path(directory) / "Test"
            source = source_root / "135" / "full" / "source.tif"
            source.parent.mkdir(parents=True)
            tifffile.imwrite(
                source,
                np.zeros((8, 16), dtype=np.uint8),
                compression=None,
            )
            duplicate = source_root / "confirmed-baseline.tif"
            duplicate.symlink_to(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            cohort = (
                PerformanceCohortEntry(
                    "S001",
                    digest,
                    "135",
                    "full",
                    "NONE",
                ),
            )
            catalog = {
                "S001": LocalSampleIdentity(
                    "S001",
                    digest,
                    "135",
                    "full",
                    "Test/135/full/source.tif",
                )
            }
            resolved = resolve_performance_sources(
                cohort,
                catalog,
                source_root,
            )
            self.assertEqual(resolved[0].path, source.resolve())


if __name__ == "__main__":
    unittest.main()
