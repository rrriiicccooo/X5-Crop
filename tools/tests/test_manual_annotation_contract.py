from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import tifffile

from tools.manual_annotation.imaging import orientation_record, sha256_file
from tools.manual_annotation.model import (
    ANNOTATION_SCHEMA,
    COORDINATE_SYSTEM,
    AnnotationError,
    apply_client_geometry,
    confirmed_baseline_rows,
    display_to_raw_point,
    frame_polygons_display,
    record_for_client,
    validate_annotation_record,
)
from tools.manual_annotation.proposal import (
    _align_red_roles,
    _constrain_boundary_line_to_source,
)
from tools.manual_annotation.server import create_server
from tools.manual_annotation.workspace import ReviewWorkspace, WorkspaceError
from tools.release.manifest import RELEASE_FILES
from x5crop.io.orientation import orientation_mapping


def _annotation_record(*, orientation: int = 1) -> dict[str, object]:
    raw_width, raw_height = (600, 100) if orientation == 1 else (100, 600)
    mapping = orientation_mapping(orientation, raw_width, raw_height)
    record: dict[str, object] = {
        "annotation_schema": ANNOTATION_SCHEMA,
        "revision": 1,
        "state": "machine_proposal",
        "source": {
            "canonical_sample_id": "S001",
            "relative_path": "Test/135/S001_count-1.tif",
            "sha256": "a" * 64,
            "raw_extent": {"width": raw_width, "height": raw_height},
            "canonical_extent": {
                "width": mapping.canonical_width,
                "height": mapping.canonical_height,
            },
            "orientation_mapping": orientation_record(mapping),
        },
        "format_id": "135",
        "strip_axis_display": "horizontal",
        "coordinate_system": COORDINATE_SYSTEM,
        "origin": "test_machine_proposal",
        "shared_edges": [],
        "boundary_pool": [],
        "tasks": [
            {
                "task_id": "S001",
                "sample_id": "S001",
                "source_relative_path": "Test/135/S001_count-1.tif",
                "count": 1,
                "slots": [
                    {
                        "ordinal": 1,
                        "start_boundary_id": "B001",
                        "end_boundary_id": "B002",
                        "slot_kind": "image",
                    }
                ],
                "adjacencies": [],
            },
            {
                "task_id": "S002",
                "sample_id": "S002",
                "source_relative_path": "Test/135/S002_count-2.tif",
                "count": 2,
                "slots": [
                    {
                        "ordinal": 1,
                        "start_boundary_id": "B001",
                        "end_boundary_id": "B002",
                        "slot_kind": "image",
                    },
                    {
                        "ordinal": 2,
                        "start_boundary_id": "B003",
                        "end_boundary_id": "B004",
                        "slot_kind": "image",
                    },
                ],
                "adjacencies": [
                    {"left_ordinal": 1, "right_ordinal": 2, "kind": "separator"}
                ],
            },
        ],
        "diagnostics": {},
        "reviewed_task_ids": [],
        "confirmation": None,
    }

    def line(
        identity: str,
        role: str,
        points: list[list[float]],
    ) -> dict[str, object]:
        return {
            "line_id": identity,
            "role": role,
            "points_raw": [display_to_raw_point(record, point) for point in points],
            "origin": "test_machine_proposal",
            "review_basis": "machine_proposal_pending_review",
        }

    record["shared_edges"] = [
        line("E1", "short_low", [[0.0, 10.0], [599.0, 12.0]]),
        line("E2", "short_high", [[0.0, 88.0], [599.0, 90.0]]),
    ]
    record["boundary_pool"] = [
        line("B001", "long_boundary", [[20.0, 0.0], [21.0, 99.0]]),
        line("B002", "long_boundary", [[210.0, 0.0], [211.0, 99.0]]),
        line("B003", "long_boundary", [[300.0, 0.0], [301.0, 99.0]]),
        line("B004", "long_boundary", [[490.0, 0.0], [491.0, 99.0]]),
    ]
    return record


class ManualAnnotationModelContractTest(unittest.TestCase):
    def test_complete_red_line_set_maps_in_order_even_when_machine_phase_is_wrong(self) -> None:
        mapping, skipped_roles, skipped_observed, _cost = _align_red_roles(
            [0.0, 10.0],
            [(0,), (1,)],
            [
                {"position": 100.0},
                {"position": 110.0},
            ],
        )
        self.assertEqual(mapping, {0: 0, 1: 1})
        self.assertEqual(skipped_roles, [])
        self.assertEqual(skipped_observed, [])

    def test_machine_boundary_is_translated_inside_source_intersections(self) -> None:
        shared = ((0.004, 302.0), (0.004, 2100.0))
        bounded, constrained = _constrain_boundary_line_to_source(
            (-0.0022, 0.25),
            shared,
            17262.0,
            0.0,
        )
        self.assertTrue(constrained)
        for shared_slope, shared_intercept in shared:
            coordinate = (
                bounded[0] * shared_intercept + bounded[1]
            ) / (1.0 - bounded[0] * shared_slope)
            self.assertGreaterEqual(coordinate, 0.0)
            self.assertLessEqual(coordinate, 17262.0)

    def test_source_pool_supports_distinct_multi_count_task_mappings(self) -> None:
        record = _annotation_record()
        validate_annotation_record(record)
        self.assertEqual(len(frame_polygons_display(record, record["tasks"][0])), 1)
        self.assertEqual(len(frame_polygons_display(record, record["tasks"][1])), 2)
        self.assertEqual(
            record["tasks"][0]["slots"][0]["start_boundary_id"],
            record["tasks"][1]["slots"][0]["start_boundary_id"],
        )

    def test_contact_reuses_one_physical_boundary(self) -> None:
        record = _annotation_record()
        task = record["tasks"][1]
        task["slots"][1]["start_boundary_id"] = "B002"
        task["adjacencies"][0]["kind"] = "contact"
        validate_annotation_record(record)
        self.assertEqual(
            task["slots"][0]["end_boundary_id"],
            task["slots"][1]["start_boundary_id"],
        )

    def test_overlap_keeps_crossed_physical_boundaries(self) -> None:
        record = _annotation_record()
        task = record["tasks"][1]
        task["slots"][0]["end_boundary_id"] = "B003"
        task["slots"][1]["start_boundary_id"] = "B002"
        task["adjacencies"][0]["kind"] = "overlap"
        validate_annotation_record(record)
        self.assertEqual(len(frame_polygons_display(record, task)), 2)

    def test_unresolved_machine_adjacency_may_keep_crossed_proposals(self) -> None:
        record = _annotation_record()
        task = record["tasks"][1]
        task["slots"][0]["end_boundary_id"] = "B003"
        task["slots"][1]["start_boundary_id"] = "B002"
        task["adjacencies"][0]["kind"] = "unresolved"
        validate_annotation_record(record)

    def test_orientation_eight_client_round_trip_preserves_raw_authority(self) -> None:
        record = _annotation_record(orientation=8)
        validate_annotation_record(record)
        client = record_for_client(record)
        original = deepcopy(record)
        payload = {
            "expected_revision": 1,
            "shared_edges": [
                {
                    "line_id": line["line_id"],
                    "points_display": line["points_display"],
                }
                for line in client["shared_edges"]
            ],
            "boundary_pool": [
                {
                    "line_id": line["line_id"],
                    "points_display": line["points_display"],
                }
                for line in client["boundary_pool"]
            ],
        }
        updated = apply_client_geometry(record, payload)
        self.assertEqual(updated["revision"], 2)
        for before, after in zip(
            original["boundary_pool"],
            updated["boundary_pool"],
            strict=True,
        ):
            for first, second in zip(
                before["points_raw"],
                after["points_raw"],
                strict=True,
            ):
                self.assertAlmostEqual(first[0], second[0])
                self.assertAlmostEqual(first[1], second[1])
        self.assertTrue(
            all(
                line["origin"] == "test_machine_proposal"
                for line in updated["shared_edges"] + updated["boundary_pool"]
            )
        )

    def test_geometry_update_marks_only_the_changed_line_as_human(self) -> None:
        record = _annotation_record()
        client = record_for_client(record)
        client["boundary_pool"][1]["points_display"][0][0] += 1.0
        updated = apply_client_geometry(
            record,
            {
                "expected_revision": 1,
                "shared_edges": [
                    {
                        "line_id": line["line_id"],
                        "points_display": line["points_display"],
                    }
                    for line in client["shared_edges"]
                ],
                "boundary_pool": [
                    {
                        "line_id": line["line_id"],
                        "points_display": line["points_display"],
                    }
                    for line in client["boundary_pool"]
                ],
            },
        )
        self.assertEqual(updated["boundary_pool"][1]["origin"], "human_adjustment")
        self.assertEqual(
            updated["boundary_pool"][0]["origin"],
            "test_machine_proposal",
        )

    def test_confirmation_is_immutable_and_exports_accuracy_key(self) -> None:
        record = _annotation_record()
        record["state"] = "user_confirmed"
        record["reviewed_task_ids"] = ["S001", "S002"]
        record["confirmation"] = {
            "confirmed_at_utc": "2026-08-24T00:00:00Z",
            "proposal_snapshot_sha256": "b" * 64,
            "review_artifact_relative_path": "Test/manual_review/review.jpg",
            "review_artifact_sha256": "c" * 64,
            "checklist": {
                "shared_edges": True,
                "task_boundaries": True,
                "native_pixel_checks": True,
                "safe_without_bleed": True,
            },
        }
        validate_annotation_record(record)
        rows = confirmed_baseline_rows(record)
        self.assertEqual([row["count"] for row in rows], [1, 2])
        self.assertTrue(all(row["strip_orientation"] == "horizontal" for row in rows))
        self.assertTrue(
            all(
                "minimum_acceptable_no_bleed_crop_baseline"
                in row["confirmation_scope"]
                for row in rows
            )
        )
        with self.assertRaisesRegex(AnnotationError, "immutable"):
            apply_client_geometry(
                record,
                {
                    "expected_revision": 1,
                    "shared_edges": [],
                    "boundary_pool": [],
                },
            )


class SyntheticReviewRepository:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source_relative = "Test/135/S001_count-1.tif"
        self.copy_relative = (
            "Test/manual_review/gold_calibration_v2/135/S001_count-1.tif"
        )
        source = self.root / self.source_relative
        source.parent.mkdir(parents=True)
        raster = np.full((320, 640, 3), 65535, dtype=np.uint16)
        raster[54:266, 144:496] = 1200
        y, x = np.indices((190, 300))
        texture = ((x * 97 + y * 173) % 42000 + 8000).astype(np.uint16)
        raster[65:255, 170:470, 0] = texture
        raster[65:255, 170:470, 1] = np.flip(texture, axis=1)
        raster[65:255, 170:470, 2] = np.flip(texture, axis=0)
        tifffile.imwrite(source, raster, photometric="rgb", compression=None)
        copy = self.root / self.copy_relative
        copy.parent.mkdir(parents=True)
        shutil.copyfile(source, copy)
        source_sha = sha256_file(source)
        cohort = {
            "sample_id": "S001",
            "format_id": "135",
            "count": 1,
            "source_relative_path": self.source_relative,
            "source_sha256": source_sha,
        }
        manifest = {
            "manifest_schema": "x5crop_manual_review_manifest_v3",
            **cohort,
            "sort_index": 1,
            "calibration_state": "pending_user_markup",
            "calibration_canonical_sample_id": "S001",
            "calibration_copy_relative_path": self.copy_relative,
            "source_alias_sample_ids": ["S001"],
        }
        cohort_path = (
            self.root
            / "tools/regression/cohorts/diagnostic_unreviewed.jsonl"
        )
        cohort_path.parent.mkdir(parents=True)
        cohort_path.write_text(json.dumps(cohort) + "\n", encoding="utf-8")
        manifest_path = self.root / "Test/manual_review/manifest.jsonl"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        baseline_path = (
            self.root / "Test/manual_review/user_confirmed_golden_baseline.jsonl"
        )
        baseline_path.write_text("", encoding="utf-8")
        self.source_sha = source_sha
        self.source_path = source

    def write_review_context(self, *, unmarked: bool = False) -> None:
        context = {
            "review_context_schema": "x5crop_manual_review_context_v1",
            "default_pending_markup_state": "user_declared_marked",
            "default_film_polarity": "negative",
            "positive_sample_ids": [],
            "unmarked_sample_ids": ["S001"] if unmarked else [],
            "samples": {},
        }
        path = self.root / "Test/manual_review/review_context.json"
        path.write_text(json.dumps(context), encoding="utf-8")

    def draw_red_markup(self) -> None:
        raster = tifffile.imread(self.source_path)
        red = np.asarray([65535, 0, 0], dtype=np.uint16)
        raster[51:57, 110:530] = red
        raster[263:269, 110:530] = red
        raster[45:275, 141:147] = red
        raster[45:275, 493:499] = red
        tifffile.imwrite(
            self.root / self.copy_relative,
            raster,
            photometric="rgb",
            compression=None,
        )

    def close(self) -> None:
        self.temporary.cleanup()


class ManualAnnotationWorkspaceContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = SyntheticReviewRepository()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_prepare_review_confirm_and_source_immutability(self) -> None:
        workspace = ReviewWorkspace(self.fixture.root)
        source_before = sha256_file(self.fixture.source_path)
        counts = workspace.prepare()
        self.assertEqual(counts["prepared"], 1)
        record = workspace.load_record("S001")
        self.assertEqual(record["state"], "machine_proposal")
        self.assertEqual(record["tasks"][0]["count"], 1)
        self.assertEqual(sha256_file(self.fixture.source_path), source_before)
        preview = workspace.preview_path(self.fixture.source_sha)
        self.assertEqual(
            sha256_file(preview),
            record["diagnostics"]["preview_jpeg_sha256"],
        )
        reviewed = workspace.set_task_reviewed(
            "S001",
            expected_revision=record["revision"],
            task_id="S001",
            reviewed=True,
        )
        confirmed = workspace.confirm(
            "S001",
            expected_revision=reviewed["revision"],
            checklist={
                "shared_edges": True,
                "task_boundaries": True,
                "native_pixel_checks": True,
                "safe_without_bleed": True,
            },
        )
        self.assertEqual(confirmed["state"], "user_confirmed")
        artifact = (
            self.fixture.root
            / confirmed["confirmation"]["review_artifact_relative_path"]
        )
        self.assertEqual(
            sha256_file(artifact),
            confirmed["confirmation"]["review_artifact_sha256"],
        )
        with self.assertRaisesRegex(WorkspaceError, "immutable"):
            workspace.set_task_reviewed(
                "S001",
                expected_revision=confirmed["revision"],
                task_id="S001",
                reviewed=False,
            )

    def test_user_red_markup_is_fitted_as_reviewable_geometry(self) -> None:
        self.fixture.write_review_context()
        self.fixture.draw_red_markup()
        workspace = ReviewWorkspace(self.fixture.root)
        counts = workspace.prepare()
        record = workspace.load_record("S001")
        self.assertEqual(counts["red_drafts"], 1)
        self.assertEqual(record["state"], "human_adjusted")
        self.assertEqual(record["origin"], "user_red_markup_hybrid_draft_import_v2")
        self.assertEqual(
            record["diagnostics"]["red_markup_import"]["detected_shared_edge_count"],
            2,
        )
        self.assertEqual(
            record["diagnostics"]["red_markup_import"]["detected_boundary_count"],
            2,
        )

    def test_explicitly_unmarked_copy_does_not_become_human_geometry(self) -> None:
        self.fixture.write_review_context(unmarked=True)
        self.fixture.draw_red_markup()
        workspace = ReviewWorkspace(self.fixture.root)
        counts = workspace.prepare()
        record = workspace.load_record("S001")
        self.assertEqual(counts["red_drafts"], 0)
        self.assertEqual(record["state"], "machine_proposal")

    def test_manifest_must_match_tracked_count(self) -> None:
        manifest = self.fixture.root / "Test/manual_review/manifest.jsonl"
        row = json.loads(manifest.read_text(encoding="utf-8"))
        row["count"] = 2
        manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceError, "tracked authority"):
            ReviewWorkspace(self.fixture.root)

    def test_repository_path_rejects_parent_and_symlink_escape(self) -> None:
        workspace = ReviewWorkspace(self.fixture.root)
        with self.assertRaisesRegex(WorkspaceError, "safe relative"):
            workspace.resolve_repository_path("../outside.tif")
        outside = Path(self.fixture.temporary.name).parent / "outside-x5.tif"
        outside.write_bytes(b"outside")
        link = self.fixture.root / "Test/escape.tif"
        link.symlink_to(outside)
        try:
            with self.assertRaisesRegex(WorkspaceError, "symlink"):
                workspace.resolve_repository_path("Test/escape.tif")
        finally:
            link.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)


class ManualAnnotationServerContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = SyntheticReviewRepository()
        self.workspace = ReviewWorkspace(self.fixture.root)
        self.workspace.prepare()
        self.server = create_server(self.workspace, token="fixed-test-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.fixture.close()

    def _status(self, request: Request) -> tuple[int, bytes]:
        try:
            with urlopen(request, timeout=8) as response:
                return response.status, response.read()
        except HTTPError as error:
            try:
                return error.code, error.read()
            finally:
                error.close()

    def test_token_static_allowlist_and_write_origin_protection(self) -> None:
        status, body = self._status(Request(f"{self.base}/"))
        self.assertEqual(status, 200)
        self.assertIn(b"X5 Crop", body)
        status, _ = self._status(Request(f"{self.base}/api/index"))
        self.assertEqual(status, 401)
        status, body = self._status(
            Request(
                f"{self.base}/api/index",
                headers={"X-X5-Token": "fixed-test-token"},
            )
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["total_unique_sources"], 1)
        status, _ = self._status(
            Request(
                f"{self.base}/api/record/%2e%2e%2fREADME.md",
                headers={"X-X5-Token": "fixed-test-token"},
            )
        )
        self.assertIn(status, {400, 404})
        status, _ = self._status(
            Request(
                f"{self.base}/api/review/S001",
                data=json.dumps(
                    {
                        "expected_revision": 1,
                        "task_id": "S001",
                        "reviewed": True,
                    }
                ).encode(),
                method="POST",
                headers={
                    "X-X5-Token": "fixed-test-token",
                    "X-X5-Write": "1",
                    "Content-Type": "application/json",
                    "Origin": "http://malicious.invalid",
                },
            )
        )
        self.assertEqual(status, 403)

    def test_native_tile_is_bounded_and_source_bound(self) -> None:
        status, payload = self._status(
            Request(
                f"{self.base}/api/tile/S001?x=320&y=160&side=128",
                headers={"X-X5-Token": "fixed-test-token"},
            )
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.startswith(b"\x89PNG"))


class ManualAnnotationPackagingContractTest(unittest.TestCase):
    def test_web_assets_are_local_and_tool_is_not_released(self) -> None:
        web_root = Path(__file__).resolve().parents[1] / "manual_annotation/web"
        assets = {path.name: path.read_text(encoding="utf-8") for path in web_root.iterdir()}
        self.assertEqual(set(assets), {"index.html", "app.js", "styles.css"})
        joined = "\n".join(assets.values()).lower()
        self.assertNotIn("https://", joined)
        self.assertNotIn('src="http', joined)
        self.assertNotIn('href="http', joined)
        self.assertNotIn("cdn", joined)
        self.assertIn('id="loupelinelayer"', joined)
        self.assertNotIn('id="loupeline"', joined)
        self.assertIn("renderloupelines", joined)
        self.assertIn("annotation-selection-halo", joined)
        self.assertIn("loupe-selection-halo", joined)
        self.assertNotIn(".annotation-line.selected { stroke: #fff", joined)
        self.assertNotIn(".loupe-annotation-line.selected { stroke: #fff", joined)
        self.assertIn("min(564px, 46vw)", joined)
        self.assertIn("最内侧可接受", joined)
        self.assertIn("不得向其内侧越界", joined)
        self.assertIn("bracketleft", joined)
        self.assertIn('data-rotate="-1"', joined)
        self.assertFalse(
            any(
                source and source.startswith("tools/manual_annotation/")
                for _archive, source in RELEASE_FILES
            )
        )

    def test_cli_help_has_no_startup_side_effect(self) -> None:
        completed = subprocess.run(
            (sys.executable, "-m", "tools.manual_annotation", "--help"),
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn("Machine proposals never become gold", completed.stdout)


if __name__ == "__main__":
    unittest.main()
