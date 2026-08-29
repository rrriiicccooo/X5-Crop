from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image
import tifffile

from tools.manual_annotation.imaging import SourceRaster, orientation_record, sha256_file
from tools.manual_annotation.model import (
    ANNOTATION_SCHEMA,
    BASELINE_SCHEMA,
    COORDINATE_SYSTEM,
    EVALUATION_ROLE_CONTRACT,
    AnnotationError,
    apply_client_geometry,
    confirmed_baseline_rows,
    display_to_raw_point,
    evaluation_role_summary,
    frame_state_summary,
    frame_polygons_display,
    frame_polygons_raw,
    line_basis_summary,
    raw_to_display_point,
    record_for_client,
    refresh_adjacency_kinds,
    slot_boundary_ids,
    validate_annotation_record,
)
from tools.manual_annotation.proposal import (
    _align_red_roles,
    _constrain_boundary_line_to_source,
    canonicalize_source_reference_mappings,
)
from tools.manual_annotation.refinement import (
    REFINEMENT_REVISION,
    WIDTH_REFINEMENT_ORIGIN,
    refine_record,
)
from tools.manual_annotation.server import create_server
from tools.manual_annotation.workspace import ReviewWorkspace, WorkspaceError
from tools.release.manifest import RELEASE_FILES
from x5crop.debug.canvas import FRAME_FILL_COLORS
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
                        "slot_kind": "image",
                        "reference_geometry": {
                            "kind": "boundary_pair",
                            "start_boundary_id": "B001",
                            "end_boundary_id": "B002",
                        },
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
                        "slot_kind": "image",
                        "reference_geometry": {
                            "kind": "boundary_pair",
                            "start_boundary_id": "B001",
                            "end_boundary_id": "B002",
                        },
                    },
                    {
                        "ordinal": 2,
                        "slot_kind": "image",
                        "reference_geometry": {
                            "kind": "boundary_pair",
                            "start_boundary_id": "B003",
                            "end_boundary_id": "B004",
                        },
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
            "review_basis": "unclassified",
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


def _client_edit_payload(
    client_record: dict[str, object],
    *,
    expected_revision: int = 1,
) -> dict[str, object]:
    return {
        "expected_revision": expected_revision,
        "shared_edges": [
            {
                "line_id": line["line_id"],
                "points_display": line["points_display"],
                "review_basis": line["review_basis"],
            }
            for line in client_record["shared_edges"]
        ],
        "boundary_pool": [
            {
                "line_id": line["line_id"],
                "points_display": line["points_display"],
                "review_basis": line["review_basis"],
            }
            for line in client_record["boundary_pool"]
        ],
        "slot_kinds": [
            {
                "task_id": task["task_id"],
                "ordinal": slot["ordinal"],
                "slot_kind": slot["slot_kind"],
            }
            for task in client_record["tasks"]
            for slot in task["slots"]
        ],
    }


def _classify_all_lines_directly_visible(record: dict[str, object]) -> None:
    for line in [*record["shared_edges"], *record["boundary_pool"]]:
        line["review_basis"] = "directly_visible"


def _extend_second_task_to_four_frames(
    record: dict[str, object],
) -> None:
    task = record["tasks"][1]
    task["count"] = 4
    for ordinal in (3, 4):
        start_id = f"B{ordinal * 2 - 1:03d}"
        end_id = f"B{ordinal * 2:03d}"
        task["slots"].append(
            {
                "ordinal": ordinal,
                "slot_kind": "image",
                "reference_geometry": {
                    "kind": "boundary_pair",
                    "start_boundary_id": start_id,
                    "end_boundary_id": end_id,
                },
            }
        )
        for line_id in (start_id, end_id):
            line = deepcopy(record["boundary_pool"][0])
            line["line_id"] = line_id
            record["boundary_pool"].append(line)


class ManualAnnotationModelContractTest(unittest.TestCase):
    def test_two_sided_floating_partial_sequence_needs_two_direct_outers(
        self,
    ) -> None:
        record = _annotation_record()
        record["tasks"] = [record["tasks"][0]]
        _classify_all_lines_directly_visible(record)
        for line_id, x in (("B001", 150.0), ("B002", 340.0)):
            line = next(
                item
                for item in record["boundary_pool"]
                if item["line_id"] == line_id
            )
            line["points_raw"] = [
                display_to_raw_point(record, [x, 0.0]),
                display_to_raw_point(record, [x + 1.0, 99.0]),
            ]

        direct_summary = evaluation_role_summary(record)["tasks"][0]
        self.assertEqual(direct_summary["cohort_role"], "nominal")
        self.assertEqual(direct_summary["reasons"], [])

        next(
            line
            for line in record["boundary_pool"]
            if line["line_id"] == "B002"
        )["review_basis"] = "visible_content_limit"
        floating_summary = evaluation_role_summary(record)["tasks"][0]

        self.assertEqual(floating_summary["cohort_role"], "challenge")
        self.assertEqual(
            floating_summary["reasons"],
            ["two_sided_floating_partial_sequence"],
        )

    def test_evaluation_roles_are_task_level_and_structural(self) -> None:
        record = _annotation_record()
        _classify_all_lines_directly_visible(record)

        summary = evaluation_role_summary(record)
        self.assertEqual(summary["source_role"], "nominal")
        self.assertEqual(summary["nominal_task_count"], 2)
        self.assertEqual(summary["challenge_task_count"], 0)

        record["boundary_pool"][0]["review_basis"] = "human_width_estimate"
        for task in record["tasks"]:
            task["slots"][0]["slot_kind"] = "partial_exposure"
        summary = evaluation_role_summary(record)
        self.assertEqual(summary["source_role"], "nominal")
        self.assertTrue(all(not task["reasons"] for task in summary["tasks"]))

        record["tasks"][1]["adjacencies"][0]["kind"] = "contact"
        summary = evaluation_role_summary(record)
        self.assertEqual(summary["source_role"], "challenge")
        self.assertEqual(summary["nominal_task_count"], 1)
        self.assertEqual(summary["challenge_task_count"], 1)
        self.assertEqual(summary["tasks"][0]["cohort_role"], "nominal")
        self.assertEqual(summary["tasks"][1]["cohort_role"], "challenge")
        self.assertEqual(summary["tasks"][1]["reasons"], ["contact_adjacency"])

    def test_evaluation_role_requires_direct_anchors_and_known_frames(self) -> None:
        record = _annotation_record()
        _classify_all_lines_directly_visible(record)
        for line in record["boundary_pool"]:
            line["review_basis"] = "human_width_estimate"
        record["tasks"][0]["slots"][0]["slot_kind"] = "unknown"

        summary = evaluation_role_summary(record)

        self.assertEqual(summary["source_role"], "challenge")
        self.assertEqual(
            summary["tasks"][0]["reasons"],
            [
                "no_direct_sequence_anchor",
                "non_direct_boundary_count_threshold",
                "unknown_required_frame",
            ],
        )
        self.assertEqual(
            summary["tasks"][1]["reasons"],
            [
                "no_direct_sequence_anchor",
                "clustered_non_direct_boundaries",
                "non_direct_boundary_count_threshold",
            ],
        )

    def test_short_task_becomes_challenge_at_two_non_direct_boundaries(
        self,
    ) -> None:
        record = _annotation_record()
        _classify_all_lines_directly_visible(record)
        record["boundary_pool"][0]["review_basis"] = "human_width_estimate"
        record["boundary_pool"][2]["review_basis"] = "visible_content_limit"

        summary = evaluation_role_summary(record)
        first, second = summary["tasks"]

        self.assertEqual(first["cohort_role"], "nominal")
        self.assertEqual(first["non_direct_boundary_count"], 1)
        self.assertEqual(second["cohort_role"], "challenge")
        self.assertEqual(
            second["reasons"],
            ["non_direct_boundary_count_threshold"],
        )
        self.assertEqual(second["non_direct_boundary_count"], 2)
        self.assertEqual(second["non_direct_boundary_challenge_threshold"], 2)
        self.assertEqual(
            second["non_direct_boundary_ids"],
            ["B001", "B003"],
        )
        self.assertEqual(second["two_sided_non_direct_frame_ordinals"], [])

    def test_long_task_challenges_clustered_non_direct_boundaries(self) -> None:
        record = _annotation_record()
        _classify_all_lines_directly_visible(record)
        _extend_second_task_to_four_frames(record)
        for line_id in ("B001", "B002", "B003"):
            next(
                line
                for line in record["boundary_pool"]
                if line["line_id"] == line_id
            )["review_basis"] = "human_width_estimate"

        task_summary = evaluation_role_summary(record)["tasks"][1]

        self.assertEqual(task_summary["cohort_role"], "challenge")
        self.assertEqual(
            task_summary["reasons"],
            ["clustered_non_direct_boundaries"],
        )
        self.assertEqual(task_summary["non_direct_boundary_count"], 3)
        self.assertEqual(
            task_summary["non_direct_boundary_challenge_threshold"],
            4,
        )
        self.assertEqual(
            task_summary["two_sided_non_direct_frame_ordinals"],
            [1],
        )

    def test_long_task_becomes_challenge_at_four_distinct_non_direct_boundaries(
        self,
    ) -> None:
        record = _annotation_record()
        _classify_all_lines_directly_visible(record)
        _extend_second_task_to_four_frames(record)
        for line_id in ("B001", "B003", "B005", "B007"):
            next(
                line
                for line in record["boundary_pool"]
                if line["line_id"] == line_id
            )["review_basis"] = "human_width_estimate"

        task_summary = evaluation_role_summary(record)["tasks"][1]

        self.assertEqual(task_summary["cohort_role"], "challenge")
        self.assertEqual(
            task_summary["reasons"],
            ["non_direct_boundary_count_threshold"],
        )
        self.assertEqual(task_summary["non_direct_boundary_count"], 4)
        self.assertEqual(
            task_summary["two_sided_non_direct_frame_ordinals"],
            [],
        )

    def test_contact_boundary_identity_is_not_counted_twice(self) -> None:
        record = _annotation_record()
        _classify_all_lines_directly_visible(record)
        _extend_second_task_to_four_frames(record)
        task = record["tasks"][1]
        task["slots"][1]["reference_geometry"]["start_boundary_id"] = "B002"
        task["adjacencies"][0]["kind"] = "contact"
        for line_id in ("B001", "B002"):
            next(
                line
                for line in record["boundary_pool"]
                if line["line_id"] == line_id
            )["review_basis"] = "human_width_estimate"

        task_summary = evaluation_role_summary(record)["tasks"][1]

        self.assertEqual(task_summary["non_direct_boundary_count"], 2)
        self.assertEqual(
            task_summary["two_sided_non_direct_frame_ordinals"],
            [1],
        )
        self.assertEqual(
            task_summary["clustered_non_direct_frame_ordinals"],
            [],
        )
        self.assertEqual(task_summary["reasons"], ["contact_adjacency"])

    def test_frame_state_summary_separates_normal_and_non_normal_slots(self) -> None:
        record = _annotation_record()

        summary = frame_state_summary(record)

        self.assertEqual(summary["status"], "all_frames_normal")
        self.assertTrue(summary["all_frames_normal"])
        self.assertEqual(summary["non_normal_slots"], [])

        for task in record["tasks"]:
            task["slots"][0]["slot_kind"] = "partial_exposure"
        summary = frame_state_summary(record)

        self.assertEqual(summary["status"], "has_non_normal_frames")
        self.assertFalse(summary["all_frames_normal"])
        self.assertEqual(summary["non_normal_slot_count"], 2)
        self.assertEqual(
            {
                (item["task_id"], item["ordinal"], item["slot_kind"])
                for item in summary["non_normal_slots"]
            },
            {
                ("S001", 1, "partial_exposure"),
                ("S002", 1, "partial_exposure"),
            },
        )

    def test_line_basis_summary_separates_unclassified_indirect_and_direct_sources(
        self,
    ) -> None:
        record = _annotation_record()

        summary = line_basis_summary(record)
        self.assertEqual(summary["status"], "needs_classification")
        self.assertEqual(summary["unclassified_line_count"], 6)
        self.assertEqual(
            {line["line_id"] for line in summary["attention_lines"]},
            {"E1", "E2", "B001", "B002", "B003", "B004"},
        )

        for line in [*record["shared_edges"], *record["boundary_pool"]]:
            line["review_basis"] = "directly_visible"
        summary = line_basis_summary(record)
        self.assertEqual(summary["status"], "all_directly_visible")
        self.assertTrue(summary["classification_complete"])
        self.assertEqual(summary["attention_lines"], [])

        record["boundary_pool"][0]["review_basis"] = "human_width_estimate"
        summary = line_basis_summary(record)
        self.assertEqual(summary["status"], "has_non_direct_basis")
        self.assertEqual(summary["non_direct_line_count"], 1)
        self.assertEqual(summary["attention_lines"][0]["line_id"], "B001")

        for task in record["tasks"]:
            task["slots"][0]["slot_kind"] = "source_truncated"
        summary = line_basis_summary(record)
        self.assertEqual(summary["status"], "has_non_direct_basis")
        self.assertEqual(
            {(item["task_id"], item["ordinal"]) for item in summary["source_conditions"]},
            {("S001", 1), ("S002", 1)},
        )

    def test_shared_edges_are_editable_and_coordinate_changes_do_not_invent_basis(
        self,
    ) -> None:
        record = _annotation_record()
        client = record_for_client(record)
        self.assertEqual(
            client["line_basis_summary"]["status"],
            "needs_classification",
        )
        client["shared_edges"][0]["review_basis"] = "visible_content_limit"
        client["boundary_pool"][0]["points_display"][0][0] += 1.0

        updated = apply_client_geometry(record, _client_edit_payload(client))

        self.assertEqual(
            updated["shared_edges"][0]["review_basis"],
            "visible_content_limit",
        )
        self.assertEqual(
            updated["boundary_pool"][0]["review_basis"],
            "unclassified",
        )
        self.assertEqual(updated["boundary_pool"][0]["origin"], "human_adjustment")

    def test_multiple_line_bases_change_without_geometry_or_provenance_changes(
        self,
    ) -> None:
        record = _annotation_record()
        before_points = {
            line["line_id"]: deepcopy(line["points_raw"])
            for line in [*record["shared_edges"], *record["boundary_pool"]]
        }
        before_origins = {
            line["line_id"]: line["origin"]
            for line in [*record["shared_edges"], *record["boundary_pool"]]
        }
        before_tasks = deepcopy(record["tasks"])
        client = record_for_client(record)
        client["shared_edges"][0]["review_basis"] = "directly_visible"
        client["boundary_pool"][0]["review_basis"] = "visible_content_limit"
        client["boundary_pool"][1]["review_basis"] = "human_width_estimate"

        updated = apply_client_geometry(record, _client_edit_payload(client))

        self.assertEqual(updated["shared_edges"][0]["review_basis"], "directly_visible")
        self.assertEqual(
            updated["boundary_pool"][0]["review_basis"],
            "visible_content_limit",
        )
        self.assertEqual(
            updated["boundary_pool"][1]["review_basis"],
            "human_width_estimate",
        )
        for line in [*updated["shared_edges"], *updated["boundary_pool"]]:
            self.assertEqual(line["points_raw"], before_points[line["line_id"]])
            self.assertEqual(line["origin"], before_origins[line["line_id"]])
        self.assertEqual(updated["tasks"], before_tasks)
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["state"], "human_adjusted")

    def test_semantic_edit_supersedes_refinement_line_evidence(self) -> None:
        record = _annotation_record()
        record["diagnostics"]["refinement"] = {
            "lines": {
                "B001": {"human_review_status": "pending"},
                "B002": {"human_review_status": "pending"},
            },
            "human_review_state": "pending",
        }
        client = record_for_client(record)
        client["boundary_pool"][0]["review_basis"] = "directly_visible"
        for task in client["tasks"]:
            task["slots"][0]["slot_kind"] = "partial_exposure"

        updated = apply_client_geometry(record, _client_edit_payload(client))

        evidence = updated["diagnostics"]["refinement"]["lines"]
        self.assertEqual(
            evidence["B001"]["human_review_status"],
            "adjusted_after_refinement",
        )
        self.assertEqual(
            evidence["B002"]["human_review_status"],
            "adjusted_after_refinement",
        )

    def test_geometry_edit_automatically_records_overlap_adjacency(self) -> None:
        record = _annotation_record()
        before_slots = deepcopy(record["tasks"][1]["slots"])
        client = record_for_client(record)
        boundary = next(
            line for line in client["boundary_pool"] if line["line_id"] == "B002"
        )
        for point in boundary["points_display"]:
            point[0] += 110.0

        updated = apply_client_geometry(record, _client_edit_payload(client))

        self.assertEqual(updated["tasks"][1]["adjacencies"][0]["kind"], "overlap")
        self.assertEqual(updated["tasks"][1]["slots"], before_slots)
        self.assertEqual(
            next(
                line for line in updated["boundary_pool"] if line["line_id"] == "B002"
            )["origin"],
            "human_adjustment",
        )

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
            slot_boundary_ids(record["tasks"][0]["slots"][0])[0],
            slot_boundary_ids(record["tasks"][1]["slots"][0])[0],
        )

    def test_source_review_cannot_be_partial_across_count_aliases(self) -> None:
        record = _annotation_record()
        record["reviewed_task_ids"] = ["S001"]
        with self.assertRaisesRegex(
            AnnotationError,
            "source reference review state is invalid",
        ):
            validate_annotation_record(record)

    def test_lower_count_maps_to_canonical_source_frame_subset(self) -> None:
        record = _annotation_record()
        record["tasks"][0]["slots"][0]["reference_geometry"] = {
            "kind": "boundary_pair",
            "start_boundary_id": "B001",
            "end_boundary_id": "B004",
        }
        with self.assertRaisesRegex(
            AnnotationError,
            "not a subset of the source reference",
        ):
            validate_annotation_record(record)
        normalized = canonicalize_source_reference_mappings(record)
        canonical_pairs = {
            slot_boundary_ids(slot)
            for slot in normalized["tasks"][1]["slots"]
            if slot_boundary_ids(slot) is not None
        }
        lower_pairs = {
            slot_boundary_ids(slot)
            for slot in normalized["tasks"][0]["slots"]
            if slot_boundary_ids(slot) is not None
        }
        self.assertTrue(lower_pairs.issubset(canonical_pairs))
        self.assertEqual(
            normalized["diagnostics"]["source_reference_mapping"]["canonical_task_id"],
            "S002",
        )
        validate_annotation_record(normalized)

    def test_contact_reuses_one_physical_boundary(self) -> None:
        record = _annotation_record()
        task = record["tasks"][1]
        task["slots"][1]["reference_geometry"]["start_boundary_id"] = "B002"
        task["adjacencies"][0]["kind"] = "contact"
        record["boundary_pool"] = [
            line for line in record["boundary_pool"] if line["line_id"] != "B003"
        ]
        validate_annotation_record(record)
        self.assertEqual(
            slot_boundary_ids(task["slots"][0])[1],
            slot_boundary_ids(task["slots"][1])[0],
        )

    def test_overlap_keeps_crossed_physical_boundaries(self) -> None:
        record = _annotation_record()
        task = record["tasks"][1]
        task["slots"][0]["reference_geometry"]["end_boundary_id"] = "B003"
        task["slots"][1]["reference_geometry"]["start_boundary_id"] = "B002"
        task["adjacencies"][0]["kind"] = "overlap"
        record = canonicalize_source_reference_mappings(record)
        validate_annotation_record(record)
        self.assertEqual(len(frame_polygons_display(record, task)), 2)

    def test_adjacency_kind_must_match_derived_geometry(self) -> None:
        record = _annotation_record()
        task = record["tasks"][1]
        task["slots"][0]["reference_geometry"]["end_boundary_id"] = "B003"
        task["slots"][1]["reference_geometry"]["start_boundary_id"] = "B002"
        task["adjacencies"][0]["kind"] = "unresolved"

        with self.assertRaisesRegex(AnnotationError, "adjacency semantics are invalid"):
            validate_annotation_record(record)

        refresh_adjacency_kinds(record)
        record = canonicalize_source_reference_mappings(record)
        task = record["tasks"][1]
        self.assertEqual(task["adjacencies"][0]["kind"], "overlap")
        validate_annotation_record(record)

    def test_blank_exposure_has_no_reference_polygon_or_accuracy_frame(self) -> None:
        record = _annotation_record()
        task = record["tasks"][1]
        task["slots"][1]["slot_kind"] = "blank_exposure"
        task["slots"][1]["reference_geometry"] = {"kind": "not_applicable"}
        task["adjacencies"][0]["kind"] = "not_applicable"
        record["boundary_pool"] = record["boundary_pool"][:2]
        validate_annotation_record(record)
        self.assertEqual(len(frame_polygons_display(record, task)), 1)
        self.assertIsNone(slot_boundary_ids(task["slots"][1]))

        _classify_all_lines_directly_visible(record)
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
        row = confirmed_baseline_rows(record)[1]
        self.assertEqual(row["baseline_schema"], BASELINE_SCHEMA)
        self.assertEqual([frame["frame_index"] for frame in row["frames"]], [1])
        self.assertEqual(row["evaluation_role"]["cohort_role"], "nominal")
        self.assertEqual(
            row["slots"][1]["reference_geometry"],
            {"kind": "not_applicable"},
        )

    def test_source_truncated_frame_clips_physical_geometry_to_tiff_raster(self) -> None:
        record = _annotation_record()
        client = record_for_client(record)
        client["shared_edges"][0]["points_display"] = [
            [0.0, -4.0],
            [599.0, 8.0],
        ]

        with self.assertRaisesRegex(
            AnnotationError,
            "leaves the source raster",
        ):
            apply_client_geometry(record, _client_edit_payload(client))

        for task in client["tasks"]:
            task["slots"][0]["slot_kind"] = "source_truncated"
        updated = apply_client_geometry(record, _client_edit_payload(client))
        polygon = frame_polygons_display(updated, updated["tasks"][0])[0]

        self.assertEqual(updated["revision"], 2)
        self.assertEqual(len(polygon), 5)
        self.assertTrue(
            all(
                -0.5 <= x <= 599.5 and -0.5 <= y <= 99.5
                for x, y in polygon
            )
        )
        self.assertTrue(any(abs(y + 0.5) < 1.0e-9 for _x, y in polygon))
        self.assertLess(client["shared_edges"][0]["points_display"][0][1], -0.5)

        _classify_all_lines_directly_visible(updated)
        updated["state"] = "user_confirmed"
        updated["reviewed_task_ids"] = ["S001", "S002"]
        updated["confirmation"] = {
            "confirmed_at_utc": "2026-08-28T00:00:00Z",
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
        baseline = confirmed_baseline_rows(updated)[0]
        self.assertEqual(
            baseline["frames"][0]["polygon_source_pixel_center_coordinates"],
            polygon,
        )

    def test_source_truncated_clipping_preserves_orientation_eight_raw_bounds(self) -> None:
        record = _annotation_record(orientation=8)
        client = record_for_client(record)
        client["shared_edges"][0]["points_display"] = [
            [0.0, -4.0],
            [599.0, 8.0],
        ]
        for task in client["tasks"]:
            task["slots"][0]["slot_kind"] = "source_truncated"

        updated = apply_client_geometry(record, _client_edit_payload(client))
        polygon = frame_polygons_raw(updated, updated["tasks"][0])[0]

        self.assertEqual(len(polygon), 5)
        self.assertTrue(
            all(
                -0.5 <= x <= 99.5 and -0.5 <= y <= 599.5
                for x, y in polygon
            )
        )

    def test_source_truncated_clipping_is_generic_across_all_tiff_edges(self) -> None:
        cases = (
            ("top", "E1", [[0.0, -4.0], [599.0, 8.0]], 1, -0.5),
            ("bottom", "E2", [[0.0, 96.0], [599.0, 108.0]], 1, 99.5),
            ("left", "B001", [[-4.0, 0.0], [8.0, 99.0]], 0, -0.5),
            ("right", "B002", [[592.0, 0.0], [604.0, 99.0]], 0, 599.5),
        )

        for edge, line_id, points, axis, boundary in cases:
            with self.subTest(edge=edge):
                record = _annotation_record()
                record["tasks"] = [record["tasks"][0]]
                record["boundary_pool"] = record["boundary_pool"][:2]
                client = record_for_client(record)
                client["tasks"][0]["slots"][0]["slot_kind"] = "source_truncated"
                lines = [*client["shared_edges"], *client["boundary_pool"]]
                next(line for line in lines if line["line_id"] == line_id)[
                    "points_display"
                ] = points

                updated = apply_client_geometry(record, _client_edit_payload(client))
                polygon = frame_polygons_display(updated, updated["tasks"][0])[0]

                self.assertTrue(
                    all(
                        -0.5 <= x <= 599.5 and -0.5 <= y <= 99.5
                        for x, y in polygon
                    )
                )
                self.assertEqual(
                    sum(abs(point[axis] - boundary) < 1.0e-9 for point in polygon),
                    2,
                )

    def test_source_truncated_may_be_preclassified_but_must_leave_raster_to_confirm(self) -> None:
        record = _annotation_record()
        for task in record["tasks"]:
            task["slots"][0]["slot_kind"] = "source_truncated"

        validate_annotation_record(record)
        summary = frame_state_summary(record)
        self.assertEqual(
            summary["pending_source_truncated_geometry"],
            [
                {"task_id": "S001", "ordinal": 1},
                {"task_id": "S002", "ordinal": 1},
            ],
        )

        _classify_all_lines_directly_visible(record)
        record["state"] = "user_confirmed"
        record["reviewed_task_ids"] = ["S001", "S002"]
        record["confirmation"] = {
            "confirmed_at_utc": "2026-08-29T00:00:00Z",
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
        with self.assertRaisesRegex(
            AnnotationError,
            "source_truncated frames must physically leave the source raster.*S001#1.*S002#1",
        ):
            validate_annotation_record(record)

    def test_nonblank_slot_cannot_omit_reference_geometry(self) -> None:
        record = _annotation_record()
        record["tasks"][0]["slots"][0]["reference_geometry"] = {
            "kind": "not_applicable"
        }
        with self.assertRaisesRegex(
            AnnotationError,
            "only blank exposure may omit reference geometry",
        ):
            validate_annotation_record(record)

    def test_unused_machine_line_cannot_pose_as_reference_geometry(self) -> None:
        record = _annotation_record()
        orphan = deepcopy(record["boundary_pool"][-1])
        orphan["line_id"] = "B005"
        record["boundary_pool"].append(orphan)
        with self.assertRaisesRegex(
            AnnotationError,
            "unused machine boundary is not reference geometry",
        ):
            validate_annotation_record(record)

    def test_orientation_eight_client_round_trip_preserves_raw_authority(self) -> None:
        record = _annotation_record(orientation=8)
        validate_annotation_record(record)
        client = record_for_client(record)
        original = deepcopy(record)
        payload = _client_edit_payload(client)
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
        record["boundary_pool"][1]["review_basis"] = "human_width_estimate"
        client = record_for_client(record)
        client["boundary_pool"][1]["points_display"][0][0] += 1.0
        updated = apply_client_geometry(record, _client_edit_payload(client))
        self.assertEqual(updated["boundary_pool"][1]["origin"], "human_adjustment")
        self.assertEqual(
            updated["boundary_pool"][1]["review_basis"],
            "human_width_estimate",
        )
        self.assertEqual(
            updated["boundary_pool"][0]["origin"],
            "test_machine_proposal",
        )

    def test_visible_content_limit_survives_native_pixel_adjustment(self) -> None:
        record = _annotation_record()
        record["boundary_pool"][0]["review_basis"] = "visible_content_limit"
        client = record_for_client(record)
        client["boundary_pool"][0]["points_display"][0][0] += 1.0

        updated = apply_client_geometry(record, _client_edit_payload(client))

        self.assertEqual(updated["boundary_pool"][0]["origin"], "human_adjustment")
        self.assertEqual(
            updated["boundary_pool"][0]["review_basis"],
            "visible_content_limit",
        )

    def test_client_can_classify_boundary_evidence(self) -> None:
        for review_basis in (
            "directly_visible",
            "visible_content_limit",
            "human_width_estimate",
        ):
            with self.subTest(review_basis=review_basis):
                record = _annotation_record()
                client = record_for_client(record)
                client["boundary_pool"][0]["review_basis"] = review_basis

                updated = apply_client_geometry(
                    record,
                    _client_edit_payload(client),
                )

                self.assertEqual(
                    updated["boundary_pool"][0]["review_basis"],
                    review_basis,
                )
                self.assertEqual(
                    updated["boundary_pool"][0]["origin"],
                    "test_machine_proposal",
                )

    def test_client_updates_one_physical_frame_kind_across_count_tasks(self) -> None:
        for slot_kind in ("partial_exposure", "source_truncated", "unknown"):
            with self.subTest(slot_kind=slot_kind):
                record = _annotation_record()
                client = record_for_client(record)
                for task in client["tasks"]:
                    task["slots"][0]["slot_kind"] = slot_kind

                updated = apply_client_geometry(
                    record,
                    _client_edit_payload(client),
                )

                self.assertTrue(
                    all(
                        task["slots"][0]["slot_kind"] == slot_kind
                        for task in updated["tasks"]
                    )
                )

    def test_client_cannot_convert_structural_blank_slot(self) -> None:
        record = _annotation_record()
        record["tasks"][0]["slots"][0] = {
            "ordinal": 1,
            "slot_kind": "blank_exposure",
            "reference_geometry": {"kind": "not_applicable"},
        }
        validate_annotation_record(record)
        client = record_for_client(record)

        unchanged = apply_client_geometry(record, _client_edit_payload(client))
        self.assertEqual(
            unchanged["tasks"][0]["slots"][0]["slot_kind"],
            "blank_exposure",
        )

        client["tasks"][0]["slots"][0]["slot_kind"] = "partial_exposure"
        with self.assertRaisesRegex(
            AnnotationError,
            "slot kind change is not editable",
        ):
            apply_client_geometry(
                record,
                _client_edit_payload(client),
            )

    def test_client_rejects_conflicting_kinds_for_one_physical_frame(self) -> None:
        record = _annotation_record()
        client = record_for_client(record)
        client["tasks"][0]["slots"][0]["slot_kind"] = "partial_exposure"

        with self.assertRaisesRegex(
            AnnotationError,
            "one physical frame cannot have conflicting slot kinds",
        ):
            apply_client_geometry(record, _client_edit_payload(client))

    def test_confirmation_is_immutable_and_exports_accuracy_key(self) -> None:
        record = _annotation_record()
        _classify_all_lines_directly_visible(record)
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
        self.assertTrue(
            all(
                row["evaluation_role"]
                == {
                    "contract": EVALUATION_ROLE_CONTRACT,
                    "cohort_role": "nominal",
                    "reasons": [],
                }
                for row in rows
            )
        )
        self.assertTrue(
            all(
                row["coordinate_system"]["canonical_extent"]
                == record["source"]["canonical_extent"]
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
                    "slot_kinds": [],
                },
            )


class SyntheticReviewRepository:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source_relative = "Test/135/S001_count-1.tif"
        self.copy_relative = (
            "Test/manual_review/gold_calibration/135/S001_count-1.tif"
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
        tifffile.imwrite(
            source,
            raster,
            photometric="rgb",
            compression=None,
            byteorder=">",
        )
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
            "manifest_schema": "x5crop_manual_review_manifest_v5",
            **cohort,
            "sort_index": 1,
            "calibration_canonical_sample_id": "S001",
            "calibration_copy_relative_path": self.copy_relative,
            "source_alias_sample_ids": ["S001"],
        }
        cohort_path = (
            self.root
            / "tools/regression/cohorts/development_diagnostic.jsonl"
        )
        cohort_path.parent.mkdir(parents=True)
        cohort_path.write_text(json.dumps(cohort) + "\n", encoding="utf-8")
        manifest_path = self.root / "Test/manual_review/manifest.jsonl"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        self.source_sha = source_sha
        self.source_path = source

    def add_two_count_alias(self) -> None:
        cohort_path = (
            self.root
            / "tools/regression/cohorts/development_diagnostic.jsonl"
        )
        first_cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
        first_cohort["format_id"] = "half"
        second_cohort = {
            **first_cohort,
            "sample_id": "S002",
            "count": 2,
        }
        cohort_path.write_text(
            "\n".join(json.dumps(row) for row in (first_cohort, second_cohort))
            + "\n",
            encoding="utf-8",
        )

        manifest_path = self.root / "Test/manual_review/manifest.jsonl"
        first_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        first_manifest.update(
            {
                "format_id": "half",
                "source_alias_sample_ids": ["S001", "S002"],
            }
        )
        second_manifest = {
            **first_manifest,
            "sample_id": "S002",
            "sort_index": 2,
            "count": 2,
        }
        manifest_path.write_text(
            "\n".join(json.dumps(row) for row in (first_manifest, second_manifest))
            + "\n",
            encoding="utf-8",
        )

    def write_review_context(
        self,
        *,
        unmarked: bool = False,
        blank: bool = False,
        width_estimate: bool = False,
        partial: bool = False,
        shared_basis: str = "unclassified",
    ) -> None:
        context = {
            "review_context_schema": "x5crop_manual_review_context_v2",
            "default_pending_markup_state": "user_declared_marked",
            "default_film_polarity": "negative",
            "shared_edge_review_basis": shared_basis,
            "positive_sample_ids": [],
            "unmarked_sample_ids": ["S001"] if unmarked else [],
            "samples": (
                {
                    "S001": {
                        "markup_import": {
                            "missing_slots": [1],
                            "slot_kinds": {"1": "blank_exposure"},
                        }
                    }
                }
                if blank
                else {
                    "S001": {
                        "case_tags": ["human_width_estimate"],
                        "markup_import": {
                            "role_review_basis": {
                                "1.start": "human_width_estimate"
                            }
                        },
                    }
                }
                if width_estimate
                else {
                    sample_id: {
                        "case_tags": ["partial_exposure"],
                        "markup_import": {
                            "slot_kinds": {"1": "partial_exposure"}
                        },
                    }
                    for sample_id in ("S001", "S002")
                }
                if partial
                else {}
            ),
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

    def draw_four_red_boundaries(self) -> None:
        raster = tifffile.imread(self.source_path)
        red = np.asarray([65535, 0, 0], dtype=np.uint16)
        raster[51:57, 80:560] = red
        raster[263:269, 80:560] = red
        for coordinate in (110, 270, 330, 500):
            raster[45:275, coordinate : coordinate + 6] = red
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
        reviewed = workspace.set_source_reviewed(
            "S001",
            expected_revision=record["revision"],
            reviewed=True,
        )
        with self.assertRaisesRegex(
            WorkspaceError,
            "unclassified.*E1.*E2",
        ):
            workspace.confirm(
                "S001",
                expected_revision=reviewed["revision"],
            )
        client = workspace.load_record("S001", client=True)
        for line in [*client["shared_edges"], *client["boundary_pool"]]:
            line["review_basis"] = "directly_visible"
        record = workspace.update_geometry(
            "S001",
            _client_edit_payload(
                client,
                expected_revision=reviewed["revision"],
            ),
        )
        reviewed = workspace.set_source_reviewed(
            "S001",
            expected_revision=record["revision"],
            reviewed=True,
        )
        confirmed = workspace.confirm(
            "S001",
            expected_revision=reviewed["revision"],
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
            workspace.set_source_reviewed(
                "S001",
                expected_revision=confirmed["revision"],
                reviewed=False,
            )

    def test_refinement_is_reviewable_idempotent_and_source_read_only(self) -> None:
        workspace = ReviewWorkspace(self.fixture.root)
        workspace.prepare()
        client = workspace.load_record("S001", client=True)
        for line in [*client["shared_edges"], *client["boundary_pool"]]:
            line["review_basis"] = "directly_visible"
        first_boundary = client["boundary_pool"][0]
        for point in first_boundary["points_display"]:
            point[0] += 5.0
        adjusted = workspace.update_geometry(
            "S001",
            _client_edit_payload(client),
        )
        source_before = sha256_file(self.fixture.source_path)

        counts = workspace.refine(identities=["S001"])

        self.assertEqual(counts["refined_sources"], 1)
        self.assertGreater(counts["moved_lines"], 0)
        refined = workspace.load_record("S001", client=True)
        self.assertEqual(refined["revision"], adjusted["revision"] + 1)
        self.assertEqual(refined["state"], "human_adjusted")
        self.assertEqual(refined["reviewed_task_ids"], [])
        self.assertIsNone(refined["confirmation"])
        self.assertEqual(sha256_file(self.fixture.source_path), source_before)
        evidence = refined["diagnostics"]["refinement"]
        self.assertEqual(evidence["refinement_revision"], REFINEMENT_REVISION)
        self.assertEqual(
            evidence["authority"],
            "proposal_only_requires_native_pixel_human_review",
        )
        self.assertEqual(
            evidence["line_count"],
            evidence["moved_line_count"] + evidence["retained_line_count"],
        )
        self.assertEqual(
            evidence["lines"][first_boundary["line_id"]]["decision"],
            "moved_to_unique_local_edge",
        )
        self.assertEqual(
            evidence["lines"][first_boundary["line_id"]]["human_review_status"],
            "pending",
        )
        self.assertNotEqual(
            evidence["lines"][first_boundary["line_id"]]["input_points_raw"],
            evidence["lines"][first_boundary["line_id"]]["output_points_raw"],
        )
        revision = refined["revision"]

        repeated = workspace.refine(identities=["S001"])

        self.assertEqual(repeated["unchanged_existing"], 1)
        self.assertEqual(workspace.load_record("S001")["revision"], revision)

        client = workspace.load_record("S001", client=True)
        changed_line = next(
            line
            for line in client["boundary_pool"]
            if line["line_id"] == first_boundary["line_id"]
        )
        for point in changed_line["points_display"]:
            point[0] += 1.0
        manually_adjusted = workspace.update_geometry(
            "S001",
            _client_edit_payload(client, expected_revision=revision),
        )
        self.assertEqual(
            manually_adjusted["diagnostics"]["refinement"]["lines"][
                first_boundary["line_id"]
            ]["human_review_status"],
            "adjusted_after_refinement",
        )
        points_before_repeat = deepcopy(changed_line["points_display"])

        protected = workspace.refine(identities=["S001"])

        self.assertEqual(protected["skipped_modified_after_refinement"], 1)
        after_protected = workspace.load_record("S001", client=True)
        actual = next(
            line
            for line in after_protected["boundary_pool"]
            if line["line_id"] == first_boundary["line_id"]
        )
        self.assertEqual(actual["points_display"], points_before_repeat)

    def test_refinement_dry_run_does_not_write_record(self) -> None:
        workspace = ReviewWorkspace(self.fixture.root)
        workspace.prepare()
        client = workspace.load_record("S001", client=True)
        _classify_all_lines_directly_visible(client)
        workspace.update_geometry("S001", _client_edit_payload(client))
        before = workspace.load_record("S001")

        counts = workspace.refine(identities=["S001"], dry_run=True)

        self.assertEqual(counts["refined_sources"], 1)
        self.assertEqual(workspace.load_record("S001"), before)

    def test_refinement_requires_complete_line_classification(self) -> None:
        workspace = ReviewWorkspace(self.fixture.root)
        workspace.prepare()

        with self.assertRaisesRegex(
            WorkspaceError,
            "all active line bases must be classified",
        ):
            workspace.refine(identities=["S001"])

    def test_width_estimate_uses_consistent_direct_frames_and_stays_nonblocking(
        self,
    ) -> None:
        record = _annotation_record()
        record["state"] = "human_adjusted"
        record["diagnostics"] = {
            "render_levels": [[0.0, 65535.0]] * 3,
        }
        record["tasks"] = [
            {
                "task_id": "S001",
                "sample_id": "S001",
                "source_relative_path": "Test/135/S001_count-3.tif",
                "count": 3,
                "slots": [
                    {
                        "ordinal": index + 1,
                        "slot_kind": "image",
                        "reference_geometry": {
                            "kind": "boundary_pair",
                            "start_boundary_id": f"B{index * 2 + 1:03d}",
                            "end_boundary_id": f"B{index * 2 + 2:03d}",
                        },
                    }
                    for index in range(3)
                ],
                "adjacencies": [
                    {"left_ordinal": 1, "right_ordinal": 2, "kind": "separator"},
                    {"left_ordinal": 2, "right_ordinal": 3, "kind": "separator"},
                ],
            }
        ]
        record["source"]["relative_path"] = "Test/135/S001_count-3.tif"

        def boundary(identity: str, coordinate: float) -> dict[str, object]:
            return {
                "line_id": identity,
                "role": "long_boundary",
                "points_raw": [
                    display_to_raw_point(record, [coordinate, 0.0]),
                    display_to_raw_point(record, [coordinate, 99.0]),
                ],
                "origin": "human_adjustment",
                "review_basis": "directly_visible",
            }

        record["boundary_pool"] = [
            boundary("B001", 20.0),
            boundary("B002", 120.0),
            boundary("B003", 200.0),
            boundary("B004", 300.0),
            boundary("B005", 365.0),
            boundary("B006", 480.0),
        ]
        record["boundary_pool"][4]["review_basis"] = "human_width_estimate"
        _classify_all_lines_directly_visible(record)
        record["boundary_pool"][4]["review_basis"] = "human_width_estimate"
        refresh_adjacency_kinds(record)
        validate_annotation_record(record)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "constant.tif"
            tifffile.imwrite(
                path,
                np.full((100, 600, 3), 32000, dtype=np.uint16),
                photometric="rgb",
                compression=None,
            )
            with SourceRaster(path) as raster:
                refined, evidence = refine_record(record, raster)

        estimate = next(
            line
            for line in refined["boundary_pool"]
            if line["line_id"] == "B005"
        )
        estimate_points = [
            raw_to_display_point(refined, point)
            for point in estimate["points_raw"]
        ]
        self.assertAlmostEqual(estimate_points[0][0], 380.0, places=5)
        self.assertAlmostEqual(estimate_points[1][0], 380.0, places=5)
        self.assertEqual(estimate["review_basis"], "human_width_estimate")
        self.assertEqual(estimate["origin"], WIDTH_REFINEMENT_ORIGIN)
        self.assertEqual(
            evidence["lines"]["B005"]["decision"],
            "moved_to_same_source_width",
        )
        self.assertEqual(evidence["width_consensus"]["status"], "accepted")

    def test_one_source_review_covers_every_count_alias(self) -> None:
        self.fixture.add_two_count_alias()
        workspace = ReviewWorkspace(self.fixture.root)
        workspace.prepare()
        record = workspace.load_record("S001")
        reviewed = workspace.set_source_reviewed(
            "S001",
            expected_revision=record["revision"],
            reviewed=True,
        )
        self.assertEqual(
            reviewed["reviewed_task_ids"],
            ["S001", "S002"],
        )
        unreviewed = workspace.set_source_reviewed(
            "S001",
            expected_revision=reviewed["revision"],
            reviewed=False,
        )
        self.assertEqual(unreviewed["reviewed_task_ids"], [])

    def test_review_context_cannot_rewrite_frozen_geometry_metadata(self) -> None:
        workspace = ReviewWorkspace(self.fixture.root)
        workspace.prepare()
        client = workspace.load_record("S001", client=True)
        _classify_all_lines_directly_visible(client)
        record = workspace.update_geometry(
            "S001",
            _client_edit_payload(client),
        )
        reviewed = workspace.set_source_reviewed(
            "S001",
            expected_revision=record["revision"],
            reviewed=True,
        )
        workspace.confirm(
            "S001",
            expected_revision=reviewed["revision"],
        )
        self.fixture.write_review_context(width_estimate=True)
        workspace = ReviewWorkspace(self.fixture.root)

        before = workspace.load_record("S001")
        with self.assertRaisesRegex(WorkspaceError, "immutable"):
            workspace.reconcile_review_context(identities=["S001"])
        self.assertEqual(workspace.load_record("S001"), before)
        current_view = workspace.load_record("S001", client=True)
        self.assertEqual(
            current_view["diagnostics"]["review_context"]["tasks"]["S001"][
                "case_tags"
            ],
            ["human_width_estimate"],
        )
        self.assertTrue(
            all(
                line["review_basis"] == "directly_visible"
                for line in [
                    *current_view["shared_edges"],
                    *current_view["boundary_pool"],
                ]
            )
        )

    def test_explicit_context_reconciles_shared_partial_frame_without_geometry_change(
        self,
    ) -> None:
        self.fixture.add_two_count_alias()
        workspace = ReviewWorkspace(self.fixture.root)
        workspace.prepare()
        before = workspace.load_record("S001")
        points_before = [
            deepcopy(line["points_raw"])
            for line in [*before["shared_edges"], *before["boundary_pool"]]
        ]
        self.fixture.write_review_context(partial=True)
        workspace = ReviewWorkspace(self.fixture.root)

        counts = workspace.reconcile_review_context(identities=["S001"])

        self.assertEqual(
            counts,
            {"changed_sources": 1, "changed_lines": 0, "changed_slots": 2},
        )
        corrected = workspace.load_record("S001")
        self.assertTrue(
            all(
                task["slots"][0]["slot_kind"] == "partial_exposure"
                for task in corrected["tasks"]
            )
        )
        self.assertEqual(
            points_before,
            [
                line["points_raw"]
                for line in [
                    *corrected["shared_edges"],
                    *corrected["boundary_pool"],
                ]
            ],
        )

    def test_explicit_context_reconciles_all_shared_edges_without_geometry_change(
        self,
    ) -> None:
        workspace = ReviewWorkspace(self.fixture.root)
        workspace.prepare()
        before = workspace.load_record("S001")
        points_before = {
            line["line_id"]: deepcopy(line["points_raw"])
            for line in [*before["shared_edges"], *before["boundary_pool"]]
        }
        origins_before = {
            line["line_id"]: line["origin"]
            for line in [*before["shared_edges"], *before["boundary_pool"]]
        }
        tasks_before = deepcopy(before["tasks"])
        self.fixture.write_review_context(shared_basis="directly_visible")
        workspace = ReviewWorkspace(self.fixture.root)

        counts = workspace.reconcile_review_context(identities=["S001"])

        self.assertEqual(
            counts,
            {"changed_sources": 1, "changed_lines": 2, "changed_slots": 0},
        )
        corrected = workspace.load_record("S001")
        self.assertTrue(
            all(
                line["review_basis"] == "directly_visible"
                for line in corrected["shared_edges"]
            )
        )
        self.assertTrue(
            all(
                line["review_basis"] == "unclassified"
                for line in corrected["boundary_pool"]
            )
        )
        for line in [*corrected["shared_edges"], *corrected["boundary_pool"]]:
            self.assertEqual(line["points_raw"], points_before[line["line_id"]])
            self.assertEqual(line["origin"], origins_before[line["line_id"]])
        self.assertEqual(corrected["tasks"], tasks_before)

    def test_prepare_rejects_invalid_existing_count_mapping(self) -> None:
        self.fixture.add_two_count_alias()
        workspace = ReviewWorkspace(self.fixture.root)
        workspace.prepare()
        record_path = workspace.record_path(self.fixture.source_sha)
        record = json.loads(record_path.read_text(encoding="utf-8"))
        canonical = max(record["tasks"], key=lambda task: int(task["count"]))
        canonical_pairs = [
            slot_boundary_ids(slot)
            for slot in canonical["slots"]
            if slot_boundary_ids(slot) is not None
        ]
        record["tasks"][0]["slots"][0]["reference_geometry"] = {
            "kind": "boundary_pair",
            "start_boundary_id": canonical_pairs[0][0],
            "end_boundary_id": canonical_pairs[-1][1],
        }
        canonical["adjacencies"][0]["kind"] = "unresolved"
        record_path.write_text(json.dumps(record), encoding="utf-8")

        with self.assertRaisesRegex(WorkspaceError, "annotation record is invalid"):
            workspace.prepare()

    def test_user_red_markup_is_fitted_as_reviewable_geometry(self) -> None:
        self.fixture.write_review_context()
        self.fixture.draw_red_markup()
        workspace = ReviewWorkspace(self.fixture.root)
        counts = workspace.prepare()
        record = workspace.load_record("S001")
        self.assertEqual(counts["red_drafts"], 1)
        self.assertEqual(record["state"], "human_adjusted")
        self.assertEqual(record["origin"], "user_red_markup_import")
        self.assertEqual(
            record["diagnostics"]["red_markup_import"]["detected_shared_edge_count"],
            2,
        )
        self.assertEqual(
            record["diagnostics"]["red_markup_import"]["detected_boundary_count"],
            2,
        )
        self.assertEqual(
            record["diagnostics"]["red_markup_import"]["marked_relative_path"],
            self.fixture.copy_relative,
        )
        self.assertNotIn("marked_path", record["diagnostics"]["red_markup_import"])

    def test_multi_count_alias_does_not_report_red_lines_used_by_other_task(self) -> None:
        self.fixture.add_two_count_alias()
        self.fixture.write_review_context()
        self.fixture.draw_four_red_boundaries()
        workspace = ReviewWorkspace(self.fixture.root)
        workspace.prepare()
        record = workspace.load_record("S001")
        assignments = record["diagnostics"]["red_markup_import"][
            "task_assignments"
        ]
        self.assertTrue(assignments["S001"]["unmatched_red_stroke_indices"])
        self.assertEqual(assignments["S002"]["unmatched_red_stroke_indices"], [])
        self.assertFalse(
            any(
                item["kind"] == "red_markup_unmatched_strokes"
                for item in record["diagnostics"]["unresolved"]
            )
        )

    def test_explicitly_unmarked_copy_does_not_become_human_geometry(self) -> None:
        self.fixture.write_review_context(unmarked=True)
        self.fixture.draw_red_markup()
        workspace = ReviewWorkspace(self.fixture.root)
        counts = workspace.prepare()
        record = workspace.load_record("S001")
        self.assertEqual(counts["red_drafts"], 0)
        self.assertEqual(record["state"], "machine_proposal")

    def test_unmarked_blank_slot_has_no_machine_reference_geometry(self) -> None:
        self.fixture.write_review_context(unmarked=True, blank=True)
        workspace = ReviewWorkspace(self.fixture.root)
        workspace.prepare()
        record = workspace.load_record("S001")
        slot = record["tasks"][0]["slots"][0]
        self.assertEqual(slot["slot_kind"], "blank_exposure")
        self.assertEqual(slot["reference_geometry"], {"kind": "not_applicable"})
        self.assertEqual(record["boundary_pool"], [])
        self.assertEqual(frame_polygons_display(record, record["tasks"][0]), ())

    def test_red_markup_import_applies_blank_slot_after_role_alignment(self) -> None:
        self.fixture.write_review_context(blank=True)
        self.fixture.draw_red_markup()
        workspace = ReviewWorkspace(self.fixture.root)
        counts = workspace.prepare()
        record = workspace.load_record("S001")
        self.assertEqual(counts["red_drafts"], 1)
        self.assertEqual(
            record["tasks"][0]["slots"][0]["reference_geometry"],
            {"kind": "not_applicable"},
        )
        self.assertEqual(frame_polygons_display(record, record["tasks"][0]), ())

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
        index = json.loads(body)
        self.assertEqual(index["index_schema"], "x5crop_source_annotation_index_v6")
        self.assertEqual(index["tile_max_render_dimension"], 3072)
        self.assertEqual(index["tile_max_source_dimension"], 16384)
        self.assertEqual(index["tile_max_source_pixels"], 32_000_000)
        self.assertEqual(index["total_unique_sources"], 1)
        self.assertEqual(index["basis_states"], {"needs_classification": 1})
        self.assertEqual(index["frame_states"], {"all_frames_normal": 1})
        self.assertEqual(index["evaluation_roles"], {"challenge": 1})
        self.assertEqual(
            index["items"][0]["evaluation_role_summary"]["source_role"],
            "challenge",
        )
        self.assertEqual(
            index["items"][0]["frame_state_summary"]["status"],
            "all_frames_normal",
        )
        self.assertEqual(
            index["items"][0]["line_basis_summary"]["status"],
            "needs_classification",
        )
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

    def test_review_tile_is_bounded_scaled_and_source_bound(self) -> None:
        status, payload = self._status(
            Request(
                f"{self.base}/api/tile/S001?x=320&y=160&source_width=640"
                "&source_height=320&render_width=320&render_height=160",
                headers={"X-X5-Token": "fixed-test-token"},
            )
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.startswith(b"\x89PNG"))
        with Image.open(BytesIO(payload)) as image:
            self.assertEqual(image.size, (320, 160))
            pixels = np.asarray(image)
        self.assertGreater(float(pixels[5, 5].mean()), 240.0)
        self.assertLess(float(pixels[80, 75].mean()), 30.0)

    def test_confirmation_is_one_source_level_decision(self) -> None:
        headers = {
            "X-X5-Token": "fixed-test-token",
            "X-X5-Write": "1",
            "Content-Type": "application/json",
        }
        record = self.workspace.load_record("S001", client=True)
        for line in [*record["shared_edges"], *record["boundary_pool"]]:
            line["review_basis"] = "directly_visible"
        status, body = self._status(
            Request(
                f"{self.base}/api/geometry/S001",
                data=json.dumps(_client_edit_payload(record)).encode(),
                method="PATCH",
                headers=headers,
            )
        )
        self.assertEqual(status, 200, body)
        record = json.loads(body)
        status, body = self._status(
            Request(
                f"{self.base}/api/review/S001",
                data=json.dumps(
                    {"expected_revision": record["revision"], "reviewed": True}
                ).encode(),
                method="POST",
                headers=headers,
            )
        )
        self.assertEqual(status, 200, body)
        reviewed = json.loads(body)
        status, body = self._status(
            Request(
                f"{self.base}/api/confirm/S001",
                data=json.dumps({"expected_revision": reviewed["revision"]}).encode(),
                method="POST",
                headers=headers,
            )
        )
        self.assertEqual(status, 200, body)
        record = json.loads(body)
        self.assertEqual(record["state"], "user_confirmed")
        self.assertTrue(all(record["confirmation"]["checklist"].values()))


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
        self.assertIn('id="annotationsvg"', joined)
        self.assertIn('id="loupesvg"', joined)
        self.assertIn('id="rolefilter"', joined)
        palette_matches = re.findall(
            r"\.frame-color-(\d+)\s*\{\s*fill:\s*rgb\((\d+),\s*(\d+),\s*(\d+)\);",
            assets["styles.css"],
        )
        self.assertEqual(
            tuple(
                tuple(int(value) for value in match[1:])
                for match in sorted(palette_matches, key=lambda match: int(match[0]))
            ),
            FRAME_FILL_COLORS,
        )
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
