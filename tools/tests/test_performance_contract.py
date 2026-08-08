from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

from tools.regression.performance import (
    PERFORMANCE_RECEIPT_SCHEMA,
    SECONDS_PER_INPUT_LIMIT,
    frozen_dependency_versions,
    performance_environment_is_frozen,
    validate_receipt,
)
from tools.regression.performance_identity import (
    FIXED_SOURCE_COUNT,
    cohort_sha256,
    load_performance_sources,
)
from tools.regression.diagnostic_cohort import (
    MAXIMUM_PEAK_TEMPORARY_BYTES_PER_SOURCE_PIXEL,
    MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES,
    WORK_FIELDS,
    _bounded_work,
    _peak_temporary_limit_bytes,
)
from x5crop.runtime.threading import (
    THREAD_ENVIRONMENT_KEYS,
    configure_numeric_threads,
)


class V5PerformanceContractTest(unittest.TestCase):
    @staticmethod
    def _environment() -> dict[str, object]:
        return {
            "python_version": "3.14.6",
            "python_implementation": "CPython",
            "platform": "test",
            "dependencies": frozen_dependency_versions(),
            "threads": {
                "x5crop_source_workers": "--jobs",
                "opencv_threads": 1,
                "environment": {
                    "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1",
                    "VECLIB_MAXIMUM_THREADS": "1",
                    "NUMEXPR_NUM_THREADS": "1",
                },
            },
        }

    def test_source_identity_is_exact_and_status_free(self) -> None:
        sources = load_performance_sources(verify_source_files=False)
        self.assertEqual(len(sources), FIXED_SOURCE_COUNT)
        self.assertEqual(len({item.sample_id for item in sources}), 24)
        self.assertTrue(all(len(item.source_sha256) == 64 for item in sources))

    def test_receipt_binds_commit_cohort_and_user_timing_boundary(self) -> None:
        sources = load_performance_sources(verify_source_files=False)
        commit = "1" * 40
        receipt = {
            "receipt_schema": PERFORMANCE_RECEIPT_SCHEMA,
            "git_commit": commit,
            "cohort_sha256": cohort_sha256(),
            "source_count": 24,
            "source_sha256s": [item.source_sha256 for item in sources],
            "timing_boundary": (
                "production_cli_startup_decode_detection_decision_sampling_"
                "compression_write_readback_publish"
            ),
            "sha_validation_in_timing": False,
            "debug_analysis_in_timing": False,
            "environment": self._environment(),
            "summary": {
                "mean_seconds_per_input": 4.9,
                "p50_seconds": 4.8,
                "p95_seconds": 5.2,
                "slowest_seconds": 5.4,
                "seconds_per_input_limit": SECONDS_PER_INPUT_LIMIT,
                "passed": True,
            },
            "sources": [
                {
                    "sample_id": item.sample_id,
                    "wall_seconds": 4.9,
                    "status": "needs_review",
                    "output_tiff_count": 0,
                    "output_bytes": 0,
                }
                for item in sources
            ],
        }
        validate_receipt(receipt, expected_commit=commit)
        receipt["sha_validation_in_timing"] = True
        with self.assertRaises(ValueError):
            validate_receipt(receipt, expected_commit=commit)

    def test_performance_environment_rejects_dependency_or_thread_drift(
        self,
    ) -> None:
        environment = self._environment()
        self.assertTrue(performance_environment_is_frozen(environment))
        environment["dependencies"]["Pillow"] = "12.2.0"
        self.assertFalse(performance_environment_is_frozen(environment))
        environment = self._environment()
        environment["threads"]["opencv_threads"] = 2
        self.assertFalse(performance_environment_is_frozen(environment))

    def test_opencv_thread_configuration_disables_unsupported_backend(self) -> None:
        cv2 = mock.Mock()
        cv2.getNumThreads.return_value = 12
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.dict(sys.modules, {"cv2": cv2}),
        ):
            configure_numeric_threads()
            self.assertTrue(
                all(os.environ[key] == "1" for key in THREAD_ENVIRONMENT_KEYS)
            )
        self.assertEqual(
            cv2.setNumThreads.call_args_list,
            [mock.call(1), mock.call(0)],
        )

    def test_diagnostic_memory_bound_is_ten_pixels_plus_guard(self) -> None:
        source_pixels = 115_000_000
        self.assertEqual(
            _peak_temporary_limit_bytes(source_pixels),
            source_pixels * 10 + 32 * 1024 * 1024,
        )
        self.assertEqual(MAXIMUM_PEAK_TEMPORARY_BYTES_PER_SOURCE_PIXEL, 10)
        self.assertEqual(
            MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES,
            32 * 1024 * 1024,
        )

    def test_diagnostic_enhanced_work_is_bounded_by_groups_times_roles(
        self,
    ) -> None:
        work = {field: 0 for field in WORK_FIELDS}
        work.update(
            phase_vote_count=5,
            template_group_count=4,
            enhanced_query_count=29,
            domain_pixels=100,
        )
        report = {
            "photo_geometry": {
                "resolved_output_slots": {
                    "lane_output_slot_counts": [3],
                },
                "lanes": [{"work": work}],
            }
        }

        self.assertTrue(_bounded_work(report, source_pixels=100))
        work["enhanced_query_count"] = 30
        self.assertFalse(_bounded_work(report, source_pixels=100))


if __name__ == "__main__":
    unittest.main()
