from __future__ import annotations

from copy import deepcopy
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
from tools.regression.performance_compare import (
    BASELINE_PAIRED_RELATIVE_PATH,
    BASELINE_PAIRED_SHA256,
    BASELINE_S062_RELATIVE_PATH,
    BASELINE_S062_SHA256,
    CANDIDATE_PAIRED_RELATIVE_PATH,
    CANDIDATE_S062_RELATIVE_PATH,
    OLD_V49_COMMIT,
    PerformanceReceipt,
    performance_compare,
)
from tools.regression.profile_fixed_sample import PROFILE_RECEIPT_SCHEMA


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


def _s062_receipts(
    candidate_commit: str,
) -> tuple[PerformanceReceipt, PerformanceReceipt]:
    identity = {
        "sample_id": "S062",
        "source_sha256": "e" * 64,
        "format_id": "120-66",
        "strip_mode": "partial",
        "count_mode": "auto",
        "selected_scan_canvas_profile_id": "120_wide_224_5",
        "lane_output_slot_counts": [3],
        "output_slot_count": 3,
        "slot_identities": [
            {
                "global_output_ordinal": index,
                "lane_id": "lane:0",
                "lane_ordinal": index,
            }
            for index in range(1, 4)
        ],
        "selected_aperture_labels": ["56x56mm"],
    }
    baseline_metrics = {
        "measurement_query_count": 39,
        "pixel_query_count": 8_906_190,
        "physical_geometry_count": 3,
        "dp_states": 3,
        "dp_transitions": 2,
        "shared_measurement_reuse_count": 39,
        "domain_pixels": 27_687_503,
        "peak_temporary_bytes": 254_840_313,
    }
    candidate_metrics = {
        "measurement_query_count": 39,
        "pixel_query_count": 8_906_190,
        "basic_profile_coordinate_count": 1_000,
        "basic_profile_run_count": 20,
        "phase_vote_count": 60,
        "template_group_count": 3,
        "template_role_lookup_count": 18,
        "template_role_match_count": 20,
        "local_relation_evaluation_count": 6,
        "enhanced_query_count": 0,
        "materialized_frame_geometry_count": 3,
        "shared_measurement_reuse_count": 39,
        "domain_pixels": 27_687_503,
        "peak_temporary_bytes": 254_840_313,
    }
    baseline = {
        "schema": "x5crop_fixed_sample_profile_v3",
        **identity,
        "runtime_metrics": baseline_metrics,
        "decision_status": "approved_auto",
        "geometry_unresolved_codes": [],
    }
    candidate = {
        **{
            key: value
            for key, value in baseline.items()
            if key != "geometry_unresolved_codes"
        },
        "schema": PROFILE_RECEIPT_SCHEMA,
        "v49_commit": candidate_commit,
        "runtime_metrics": candidate_metrics,
        "structural_limits": {
            "template_role_lookup_count": 18,
            "template_role_match_count": 60,
            "local_relation_evaluation_count": 6,
            "enhanced_query_count": 60,
        },
    }
    return (
        PerformanceReceipt(baseline, BASELINE_S062_SHA256),
        PerformanceReceipt(candidate, "6" * 64),
    )


def _comparison_inputs(candidate_commit: str):
    baseline_record = _result(
        (144.0, 144.0, 144.0),
        (120.0, 120.0, 120.0),
    ).as_record()
    baseline_record["v49_commit"] = OLD_V49_COMMIT
    candidate_record = deepcopy(baseline_record)
    candidate_record["v49_commit"] = candidate_commit
    baseline_s062, candidate_s062 = _s062_receipts(candidate_commit)
    return (
        PerformanceReceipt(baseline_record, BASELINE_PAIRED_SHA256),
        PerformanceReceipt(candidate_record, "7" * 64),
        baseline_s062,
        candidate_s062,
        candidate_commit,
    )


class PairedPerformanceContractTest(unittest.TestCase):
    def test_fixed_performance_comparator_closes_timing_and_s062(self) -> None:
        inputs = list(_comparison_inputs("9" * 40))
        candidate = deepcopy(inputs[3].record)
        candidate["selected_aperture_labels"] = ["54x54mm"]
        inputs[3] = PerformanceReceipt(candidate, "8" * 64)
        comparison = performance_compare(*inputs)
        self.assertTrue(comparison["passed"])
        self.assertEqual(comparison["regression"], 0.0)
        self.assertEqual(comparison["allowed_regression"], 0.01)

    def test_new_noise_cannot_expand_allowed_regression(self) -> None:
        inputs = list(_comparison_inputs("9" * 40))
        candidate = deepcopy(inputs[1].record)
        for group, wall in zip(
            candidate["paired_groups"],
            (90.0, 120.0, 150.0),
            strict=True,
        ):
            group["v49"]["wall_seconds"] = wall
        inputs[1] = PerformanceReceipt(candidate, "8" * 64)
        comparison = performance_compare(*inputs)
        self.assertFalse(comparison["checks"]["new_noise_floor_valid"])
        self.assertEqual(comparison["allowed_regression"], 0.01)

    def test_s062_comparable_work_growth_or_reuse_loss_blocks(self) -> None:
        inputs = list(_comparison_inputs("9" * 40))
        candidate = deepcopy(inputs[3].record)
        candidate["runtime_metrics"]["measurement_query_count"] += 1
        candidate["runtime_metrics"]["shared_measurement_reuse_count"] -= 1
        inputs[3] = PerformanceReceipt(candidate, "8" * 64)
        comparison = performance_compare(*inputs)
        self.assertFalse(comparison["passed"])
        self.assertFalse(
            comparison["checks"][
                "s062_measurement_query_count_not_increased"
            ]
        )
        self.assertFalse(
            comparison["checks"]["s062_measurement_reuse_not_reduced"]
        )

    def test_s062_template_work_uses_current_structural_units(self) -> None:
        inputs = list(_comparison_inputs("9" * 40))
        candidate = deepcopy(inputs[3].record)
        candidate["runtime_metrics"]["template_role_match_count"] = 61
        inputs[3] = PerformanceReceipt(candidate, "8" * 64)
        comparison = performance_compare(*inputs)
        self.assertFalse(comparison["passed"])
        self.assertFalse(
            comparison["checks"][
                "s062_template_work_structurally_bounded"
            ]
        )
        self.assertNotIn(
            "s062_dp_states_not_increased",
            comparison["checks"],
        )

    def test_s062_enhanced_work_cannot_exceed_preregistered_votes(self) -> None:
        inputs = list(_comparison_inputs("9" * 40))
        candidate = deepcopy(inputs[3].record)
        candidate["runtime_metrics"]["enhanced_query_count"] = 61
        inputs[3] = PerformanceReceipt(candidate, "8" * 64)
        comparison = performance_compare(*inputs)
        self.assertFalse(comparison["passed"])
        self.assertFalse(
            comparison["checks"][
                "s062_template_work_structurally_bounded"
            ]
        )

    def test_performance_paths_are_explicit_and_unique(self) -> None:
        self.assertEqual(
            tuple(
                map(
                    str,
                    (
                        BASELINE_PAIRED_RELATIVE_PATH,
                        BASELINE_S062_RELATIVE_PATH,
                        CANDIDATE_PAIRED_RELATIVE_PATH,
                        CANDIDATE_S062_RELATIVE_PATH,
                    ),
                )
            ),
            (
                "build/v49-orthogonal-budget/baseline/paired/paired_performance_result.json",
                "build/v49-orthogonal-budget/baseline/s062/fixed_sample_profile.json",
                "build/v49-orthogonal-budget/current/paired/paired_performance_result.json",
                "build/v49-orthogonal-budget/current/s062/fixed_sample_profile.json",
            ),
        )

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
