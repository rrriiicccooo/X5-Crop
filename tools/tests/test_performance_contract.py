from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from tools.regression.benchmark_adapter import (
    ADAPTER_RESULT_SCHEMA,
    _sample_task,
    _write_and_readback,
)
from tools.regression.benchmark_workload import (
    FIXED_SOURCE_COUNT,
    FIXED_WORKLOAD_COUNT,
    load_performance_sources,
    load_workload_records,
)
from tools.regression.diagnostic_cohort import (
    MAXIMUM_PEAK_TEMPORARY_BYTES_PER_SOURCE_PIXEL,
    MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES,
    _peak_temporary_limit_bytes,
)
from tools.regression.performance import (
    BASELINE_COMMIT,
    PAIRED_ORDERS,
    PERFORMANCE_RESULT_SCHEMA,
    PairedPerformanceResult,
    PairedRunGroup,
    VersionRunTiming,
    build_parser,
)


def _adapter_result(version_kind: str) -> dict:
    tasks_per_source = FIXED_WORKLOAD_COUNT // FIXED_SOURCE_COUNT
    remainder = FIXED_WORKLOAD_COUNT % FIXED_SOURCE_COUNT
    sources = [
        {
            "sample_id": f"S{index:03d}",
            "source_sha256": f"{index:064x}",
            "decision_status": (
                "needs_review" if index % 2 else "approved_auto"
            ),
            "detection_decision_seconds": 1.0,
            "benchmark_io_seconds": 0.5,
            "total_seconds": 1.5,
            "workload_task_count": (
                tasks_per_source + (index <= remainder)
            ),
            "sampled_output_pixels": 100,
            "benchmark_output_bytes": 200,
            "source_decode_count": 1,
            "official_product_tiff_count": 0,
        }
        for index in range(1, FIXED_SOURCE_COUNT + 1)
    ]
    return {
        "adapter_result_schema": ADAPTER_RESULT_SCHEMA,
        "version_kind": version_kind,
        "jobs": 2,
        "source_count": FIXED_SOURCE_COUNT,
        "workload_task_count": FIXED_WORKLOAD_COUNT,
        "source_decode_count": FIXED_SOURCE_COUNT,
        "official_product_tiff_count": 0,
        "adapter_wall_seconds": 10.0,
        "sources": sources,
        "completed": True,
    }


def _timing(label: str, kind: str, wall: float) -> VersionRunTiming:
    return VersionRunTiming(
        label,
        kind,
        wall,
        _adapter_result(kind),
    )


def _result(
    v428_times: tuple[float, float, float],
    v49_times: tuple[float, float, float],
) -> PairedPerformanceResult:
    groups = tuple(
        PairedRunGroup(
            group_ordinal=index,
            order=order,
            v428=_timing(f"group-{index}-v428", "v428", old),
            v49=_timing(f"group-{index}-v49", "v49", new),
        )
        for index, (order, old, new) in enumerate(
            zip(PAIRED_ORDERS, v428_times, v49_times, strict=True),
            1,
        )
    )
    return PairedPerformanceResult(
        output_root=Path("/benchmark"),
        baseline_commit=BASELINE_COMMIT,
        v49_commit="1" * 40,
        workload_sha256="2" * 64,
        controller_sha256="3" * 64,
        adapter_sha256="4" * 64,
        source_manifest_sha256="5" * 64,
        source_sha256s=tuple(
            f"{index:064x}" for index in range(FIXED_SOURCE_COUNT)
        ),
        warmups=(
            _timing("warmup-v428", "v428", 130.0),
            _timing("warmup-v49", "v49", 110.0),
        ),
        groups=groups,
        environment={"python_version": "test"},
    )


class PairedPerformanceContractTest(unittest.TestCase):
    def test_diagnostic_memory_bound_scales_with_source_extent(self) -> None:
        source_pixels = 115_000_000
        self.assertEqual(
            _peak_temporary_limit_bytes(source_pixels),
            (
                source_pixels
                * MAXIMUM_PEAK_TEMPORARY_BYTES_PER_SOURCE_PIXEL
                + MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES
            ),
        )
        self.assertEqual(
            MAXIMUM_PEAK_TEMPORARY_BYTES_PER_SOURCE_PIXEL,
            10,
        )
        self.assertEqual(
            MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES,
            32 * 1024 * 1024,
        )

    def test_absolute_and_relative_gates_use_all_fixed_inputs(self) -> None:
        result = _result(
            (144.0, 144.0, 144.0),
            (120.0, 120.0, 120.0),
        )
        self.assertEqual(result.median_v49_seconds_per_input, 5.0)
        self.assertEqual(result.noise_floor, 0.01)
        self.assertTrue(result.absolute_passed)
        self.assertTrue(result.relative_passed)
        self.assertTrue(result.passed)
        record = result.as_record()
        self.assertEqual(
            record["performance_schema"],
            PERFORMANCE_RESULT_SCHEMA,
        )
        self.assertFalse(record["status_filtering"])
        self.assertEqual(record["source_count"], 24)
        self.assertEqual(record["workload_task_count"], 168)
        self.assertEqual(
            [group["order"] for group in record["paired_groups"]],
            [list(order) for order in PAIRED_ORDERS],
        )

    def test_five_percent_is_not_hardcoded_and_noise_must_be_beaten(
        self,
    ) -> None:
        noisy = _result(
            (100.0, 120.0, 140.0),
            (95.0, 114.0, 133.0),
        )
        self.assertGreater(noisy.noise_floor, 0.01)
        self.assertFalse(noisy.relative_passed)
        slow = _result(
            (130.0, 130.0, 130.0),
            (121.0, 121.0, 121.0),
        )
        self.assertFalse(slow.absolute_passed)
        self.assertTrue(slow.relative_passed)
        self.assertFalse(slow.passed)

    def test_workload_and_source_identity_are_tracked_and_status_free(
        self,
    ) -> None:
        sources = load_performance_sources(
            verify_source_files=False,
        )
        workload = load_workload_records()
        self.assertEqual(len(sources), 24)
        self.assertEqual(len(workload), 168)
        self.assertEqual(
            {task["source_sha256"] for task in workload},
            {source.source_sha256 for source in sources},
        )
        forbidden = {"status", "candidate_id", "selected_geometry"}
        self.assertTrue(
            all(forbidden.isdisjoint(task) for task in workload)
        )

    def test_adapter_affine_sampling_and_readback_are_identity_exact(
        self,
    ) -> None:
        source = np.arange(8 * 10, dtype=np.uint16).reshape(8, 10)
        task = {
            "source_to_output_affine": [
                [1.0, 0.0, -2.0],
                [0.0, 1.0, -1.0],
                [0.0, 0.0, 1.0],
            ],
            "output_extent": {"width": 5, "height": 4},
            "compression": "NONE",
            "metadata_profile": {
                "profile": "benchmark_minimal_source_photometric",
                "photometric": "MINISBLACK",
            },
        }
        sampled = _sample_task(source, task)
        np.testing.assert_array_equal(sampled, source[1:5, 2:7])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "benchmark-only" / "sample.tif"
            size = _write_and_readback(sampled, task, path)
            self.assertGreater(size, 0)
            self.assertTrue(path.is_file())

    def test_cli_has_one_fixed_owner_and_no_legacy_catalog_inputs(self) -> None:
        parser = build_parser()
        options = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertEqual(
            options.intersection(
                {
                    "--source-root",
                    "--catalog",
                    "--cohort",
                    "--export-review",
                }
            ),
            set(),
        )
        self.assertIn("--output-root", options)


if __name__ == "__main__":
    unittest.main()
