"""Recorded raw equality cannot substitute for retained interpretations."""

from copy import deepcopy
from contextlib import redirect_stderr
import hashlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.regression import cross_retention as owner
from tools.regression.cross_retention import _compare_binding, _point_key


def _measurement():
    group = {"source": {"source_id": "source:1", "signal_sha256": "a" * 64,
                         "normalization_domain_px": [10, 990], "window_px": 5, "gap_px": 1},
             "measurement_domain_px": [20, 80], "credible_group_domain_px": [40, 60],
             "candidate_peak_coordinates_px": [50]}
    point = {"transition_id": "raw:1", "query_id": "query:1", "trace_ordinal": 2,
             "trace_coordinate_px": 100, "canonical_coordinate_px": 49.5,
             "physical_position_interval_px": {"minimum": 45.5, "maximum": 55.5},
             "localization_interval_px": {"minimum": 49.5, "maximum": 50.5},
             "polarity": 1, "gradient_z": 12., "texture_sample_coordinate_px": 50,
             "native_background_texture": {"query": {"query_id": "query:1", "boundary_axis": "y",
                 "trace_coordinate_px": 100, "boundary_coordinate_px": 50}, "right_texture_mean": 200.},
             "peak_source": {"group_id": "group:1", "candidate_ordinal": 0,
                             "source_coordinate_px": 50, "polarity": 1}}
    return point, {"group:1": group}


def _comparison(ledger=()):
    point, _ = _measurement()
    before = {"raw_by_observation": {"old": frozenset(("old:1", "old:2"))},
              "points": {f"old:{index}": (f"key:{index}", {**point, "trace_coordinate_px": index * 100}, "bottom")
                         for index in (1, 2)}}
    after = {"indexes": {"key:1": ["new:1"], "key:2": ["new:2"]},
             "traces": {"bottom": {100, 200}}, "ledger": ledger}
    binding = {"observation_id": "old", "role": "bottom", "role_authorized": True}
    return binding, before, after


class CrossRetentionContractTest(unittest.TestCase):
    def test_local_names_and_trace_ordinal_do_not_change_recorded_measurements(self):
        point, groups = _measurement()
        renamed = deepcopy(point)
        renamed.update(transition_id="raw:999", query_id="query:999", trace_ordinal=99)
        renamed["native_background_texture"]["query"]["query_id"] = "query:999"
        renamed["peak_source"]["group_id"] = "group:999"
        new_groups = {"group:999": deepcopy(groups["group:1"])}
        new_groups["group:999"]["source"]["source_id"] = "source:999"
        self.assertEqual(_point_key(point, groups, purpose="bottom_corridor", source_sha256="b" * 64),
                         _point_key(renamed, new_groups, purpose="bottom_corridor", source_sha256="b" * 64))

    def test_source_intervals_signal_and_texture_are_not_ignored(self):
        point, groups = _measurement()
        original = _point_key(point, groups, purpose="bottom_corridor", source_sha256="b" * 64)
        for field in ("physical_position_interval_px", "localization_interval_px"):
            changed = deepcopy(point)
            changed[field]["maximum"] += 0.01
            self.assertNotEqual(original, _point_key(changed, groups, purpose="bottom_corridor", source_sha256="b" * 64))
        changed = deepcopy(groups)
        changed["group:1"]["source"]["signal_sha256"] = "c" * 64
        self.assertNotEqual(original, _point_key(point, changed, purpose="bottom_corridor", source_sha256="b" * 64))
        changed = deepcopy(point)
        changed["native_background_texture"]["right_texture_mean"] += 0.01
        self.assertNotEqual(original, _point_key(changed, groups, purpose="bottom_corridor", source_sha256="b" * 64))
        self.assertNotEqual(original, _point_key(point, groups, purpose="top_corridor", source_sha256="b" * 64))
        self.assertNotEqual(original, _point_key(point, groups, purpose="bottom_corridor", source_sha256="d" * 64))

    def test_missing_peak_proof_is_preserved_and_reported_without_inventing_one(self):
        point, groups = _measurement()
        unavailable = {**point, "peak_source": None}
        self.assertNotEqual(_point_key(point, groups, purpose="bottom_corridor", source_sha256="b" * 64),
                            _point_key(unavailable, groups, purpose="bottom_corridor", source_sha256="b" * 64))
        binding, before, after = _comparison()
        before["points"]["old:1"] = ("key:1", unavailable, "bottom")
        self.assertEqual(_compare_binding(binding, before, after)["before_peak_provenance_unavailable_count"], 1)

    def test_scattered_raw_points_do_not_retain_their_original_interpretation(self):
        binding, before, after = _comparison((
            ("fitted", "bottom", frozenset(("new:1",))),
            ("fitted", "bottom", frozenset(("new:2",))),
        ))
        result = _compare_binding(binding, before, after)
        self.assertEqual(result["measurement_gaps"], [])
        self.assertEqual(result["state"], "unrepresented_registered_interpretation")

    def test_solver_superset_does_not_prove_the_old_complete_state_family(self):
        binding, before, after = _comparison((
            ("base_solver", "bottom", frozenset(("new:1", "new:2", "extra"))),
        ))
        result = _compare_binding(binding, before, after)
        self.assertEqual(result["state"], "extended_solver_raw_requires_association_proof")
        self.assertEqual(result["exact_raw_representations"], {})
        self.assertEqual(result["containing_raw_representations"], {"base_solver": 1})

    def test_family_and_membership_accounting_do_not_grant_solver_qualification(self):
        binding, before, after = _comparison(tuple(
            (kind, "bottom", frozenset(("new:1", "new:2")))
            for kind in ("tracking", "family_atom", "family_union", "membership_union")))
        result = _compare_binding(binding, before, after)
        self.assertEqual(result["state"], "ledger_only_requires_qualification_proof")
        self.assertNotIn("base_solver", result["exact_raw_representations"])

    def test_exact_raw_retention_has_a_separate_narrow_state(self):
        binding, before, after = _comparison((
            ("base_solver", "bottom", frozenset(("new:1", "new:2"))),
        ))
        self.assertEqual(_compare_binding(binding, before, after)["state"], "exact_solver_raw_retained")

    def test_duplicate_recorded_identity_is_not_resolved_by_list_order(self):
        binding, before, after = _comparison()
        after["indexes"]["key:1"].append("other:1")
        result = _compare_binding(binding, before, after)
        self.assertEqual(result["state"], "measurement_not_comparable")
        self.assertEqual(result["measurement_gaps"][0]["reason"], "non_unique_raw_identity")

    def test_missing_trace_and_changed_measurement_remain_distinct(self):
        binding, before, after = _comparison()
        after["indexes"] = {}
        after["traces"]["bottom"].remove(100)
        result = _compare_binding(binding, before, after)
        self.assertEqual([gap["reason"] for gap in result["measurement_gaps"]],
                         ["trace_not_registered", "measurement_changed_or_unavailable"])

    def test_concurrent_artifact_creation_cannot_overwrite_the_other_result(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, cohort = root / "source.tif", root / "cohort.jsonl"
            before, after, output = (root / name for name in ("before.jsonl", "after.jsonl", "audit.json"))
            source.write_bytes(b"source bytes")
            cohort.write_text(json.dumps({"sample_id": "test", "source_relative_path": source.name,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}) + "\n", encoding="utf-8")
            for report in (before, after):
                report.write_text("{}\n", encoding="utf-8")

            def concurrent_creation(*_args, **_kwargs):
                output.write_text("other completed audit\n", encoding="utf-8")
                return {}

            with patch.object(owner, "PROJECT_ROOT", root), \
                    patch.object(owner, "DEVELOPMENT_GOLD_COHORT_PATH", cohort), \
                    patch.object(owner, "_read_bound_report", return_value={}), \
                    patch.object(owner, "compare_reports", side_effect=concurrent_creation), \
                    redirect_stderr(StringIO()):
                status = owner.main(["--sample-id", "test", "--before-report", str(before),
                                     "--after-report", str(after), "--output", str(output)])
            self.assertEqual(status, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "other completed audit\n")


if __name__ == "__main__":
    unittest.main()
