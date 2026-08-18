from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from tools.regression import performance
from tools.regression.performance import (
    PERFORMANCE_RECEIPT_SCHEMA,
    PRODUCTION_TIMING_BOUNDARY,
    SECONDS_PER_INPUT_LIMIT,
    frozen_dependency_identity,
    performance_environment_is_frozen,
    validate_receipt,
)
from tools.regression.performance_profile import (
    STAGE_NAMES,
    _run_profiled,
    _runtime_peak_temporary,
)
from tools.regression.performance_hardware import build_hardware_identity
from tools.regression.performance_identity import (
    FIXED_SOURCE_COUNT,
    cohort_sha256,
    load_performance_sources,
)
from tools.regression.diagnostic_contract import (
    MAXIMUM_PEAK_TEMPORARY_BYTES_PER_SOURCE_PIXEL,
    MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES,
    WORK_FIELDS,
    bounded_work,
    peak_temporary_limit_bytes,
)
from x5crop.runtime.threading import (
    THREAD_ENVIRONMENT_KEYS,
    configure_numeric_threads,
)
from tools.regression.environment_identity import verification_environment_identity


class V5PerformanceContractTest(unittest.TestCase):
    def test_failed_gate_preserves_the_measured_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "performance_receipt.json"
            measured = {"git_commit": "current-but-failed"}
            with mock.patch.object(
                performance,
                "build_receipt",
                return_value=measured,
            ):
                with self.assertRaisesRegex(ValueError, "Gate is invalid"):
                    performance.main(("--output", str(output)))
            self.assertEqual(json.loads(output.read_text()), measured)

    def test_receipt_revision_is_current_only(self) -> None:
        self.assertEqual(
            PERFORMANCE_RECEIPT_SCHEMA,
            "x5crop_performance_receipt_v5_3",
        )
        self.assertEqual(
            STAGE_NAMES,
            (
                "startup_import_unattributed",
                "decode",
                "workspace_gray",
                "coarse_support",
                "registered_measurement",
                "template_alignment_decision",
                "sampling",
                "encode_write",
                "readback",
                "publish",
            ),
        )

    @staticmethod
    def _environment() -> dict[str, object]:
        dependencies = {
            name: {
                **required,
                "module_origin": f"/provider/{name}/__init__.py",
                "provider": "external",
                "package": name,
                "package_version": required["module_version"],
            }
            for name, required in frozen_dependency_identity().items()
        }
        return {
            "python_version": "3.14.6",
            "python_implementation": "CPython",
            "platform": "test",
            "platform_system": "Darwin",
            "dependencies": dependencies,
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
            "environment": self._environment(),
            "hardware": {
                "machine_name": "named-machine",
                "cpu_model": "test-cpu",
                "physical_core_count": 4,
                "logical_core_count": 8,
                "total_memory_bytes": 16 * 1024**3,
                "input_volume": {"filesystem": {"filesystem_kind": "apfs"}},
                "output_volume": {"filesystem": {"filesystem_kind": "apfs"}},
                "power": {"source": "AC"},
                "windows_defender": {"applicable": False},
            },
            "production_gate": {
                "timing_boundary": PRODUCTION_TIMING_BOUNDARY,
                "sha_validation_in_timing": False,
                "debug_analysis_in_timing": False,
                "summary": {
                    "mean_seconds_per_input": 4.9,
                    "p50_seconds": 4.8,
                    "p95_seconds": 5.2,
                    "slowest_source": sources[-1].sample_id,
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
            },
            "profiling": {
                "method": "external_cprofile_subprocess_and_rss_polling",
                "participates_in_speed_gate": False,
                "stage_names": list(STAGE_NAMES),
                "summary": {
                    "wall_p50_seconds": 5.0,
                    "wall_p95_seconds": 5.5,
                    "slowest_source": sources[-1].sample_id,
                    "slowest_seconds": 5.5,
                    "process_peak_rss_bytes": {},
                    "runtime_peak_temporary_bytes": {},
                    "stages": {
                        name: {} for name in (*STAGE_NAMES, "io_total")
                    },
                },
                "sources": [
                    {
                        "sample_id": item.sample_id,
                        "wall_seconds": 5.0,
                        "stages": {name: 0.1 for name in STAGE_NAMES},
                        "io_total_seconds": 0.4,
                        "process_peak_rss_bytes": 1024,
                        "runtime_peak_temporary_bytes": 512,
                    }
                    for item in sources
                ],
            },
        }
        validate_receipt(receipt, expected_commit=commit)
        receipt["production_gate"]["sha_validation_in_timing"] = True
        with self.assertRaises(ValueError):
            validate_receipt(receipt, expected_commit=commit)

    def test_profiling_is_external_and_cannot_participate_in_speed_gate(self) -> None:
        runtime_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (Path(__file__).resolve().parents[2] / "x5crop").rglob("*.py")
        )
        self.assertNotIn("cProfile", runtime_source)
        self.assertNotIn("tracemalloc", runtime_source)

    def test_hardware_identity_is_named_without_sensitive_device_identifiers(self) -> None:
        identity = build_hardware_identity(Path(__file__).resolve().parents[2])
        self.assertTrue(identity["cpu_model"])
        self.assertGreater(identity["logical_core_count"], 0)
        self.assertGreater(identity["total_memory_bytes"], 0)
        serialized = str(identity).casefold()
        self.assertNotIn("serial number", serialized)
        self.assertNotIn("hardware uuid", serialized)
        self.assertNotIn("provisioning udid", serialized)

    def test_performance_environment_rejects_dependency_or_thread_drift(
        self,
    ) -> None:
        environment = self._environment()
        self.assertTrue(performance_environment_is_frozen(environment))
        environment["dependencies"]["pillow"]["module_version"] = "12.2.0"
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

    def test_dependency_provider_identity_is_verification_only(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertFalse((root / "x5crop/runtime/dependency_identity.py").exists())
        identity = verification_environment_identity()
        self.assertEqual(
            set(identity["dependencies"]),
            {"numpy", "scipy", "opencv", "tifffile", "imagecodecs", "pillow"},
        )

    def test_diagnostic_memory_bound_is_ten_pixels_plus_guard(self) -> None:
        source_pixels = 115_000_000
        self.assertEqual(
            peak_temporary_limit_bytes(source_pixels),
            source_pixels * 10 + 32 * 1024 * 1024,
        )
        self.assertEqual(MAXIMUM_PEAK_TEMPORARY_BYTES_PER_SOURCE_PIXEL, 10)
        self.assertEqual(
            MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES,
            32 * 1024 * 1024,
        )

    def test_profiler_reads_lightweight_production_peak_temporary(self) -> None:
        report = {
            "photo_geometry": {
                "lanes": [
                    {"peak_temporary_bytes": 120},
                    {"peak_temporary_bytes": 90},
                ]
            }
        }
        self.assertEqual(_runtime_peak_temporary(report), 120)

    def test_profiler_observes_child_peak_rss_without_report_instrumentation(
        self,
    ) -> None:
        _wall, peak, output, returncode = _run_profiled(
            [sys.executable, "-c", "print('profile-child')"]
        )
        self.assertEqual(returncode, 0)
        self.assertEqual(output.strip(), "profile-child")
        self.assertGreater(peak, 0)

    def test_diagnostic_local_relations_are_bounded_by_template_adjacencies(
        self,
    ) -> None:
        work = {field: 0 for field in WORK_FIELDS}
        work.update(
            phase_hypothesis_count=4,
            phase_fit_pass_count=2,
            phase_role_lookup_count=4,
            phase_role_binding_count=24,
            local_relation_evaluation_count=4,
            domain_pixels=100,
        )
        report = {
            "photo_geometry": {
                "resolved_output_slots": {
                    "lane_output_slot_counts": [3],
                },
                "lanes": [{}],
            }
            ,"development": {"lanes": [{"work": work}]}
        }

        self.assertTrue(bounded_work(report, source_pixels=100))
        work["local_relation_evaluation_count"] = 5
        self.assertFalse(bounded_work(report, source_pixels=100))


if __name__ == "__main__":
    unittest.main()
