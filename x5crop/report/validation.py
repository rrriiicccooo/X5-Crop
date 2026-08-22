"""Validate an external current report at its trust boundary."""

from __future__ import annotations

import math
from typing import Any

from ..detection.candidate.assessment.model import CANDIDATE_GATE_CHECK_CODES
from ..detection.decision.vocabulary import FINAL_REVIEW_REASONS
from ..detection.output_deskew import DeskewSkipReason
from .identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION
from .summary import AUTHORITY_PARTITION


CURRENT_REPORT_SECTIONS = (
    "schema_id",
    "schema_revision",
    "detail_level",
    "script_version",
    "source",
    "input",
    "configuration",
    "measurement",
    "photo_geometry",
    "candidate_gate",
    "decision",
    "output",
    "runtime_identity",
    "development",
)

_AUTHORITY_SIDES = ("left", "top", "right", "bottom")
_DIRECT_USE_BUDGET_FIELDS = {
    "geometry_id",
    "boundary_use",
    "edge_assessments",
    "enclosing_support_height_ratio",
    "enclosing_support_within_limit",
    "state",
}
_DIRECT_USE_EDGE_FIELDS = {
    "role",
    "expansion_px",
    "expansion_mm",
    "limit_mm",
    "limit_applies",
    "within_limit",
}
_DESKEW_SKIP_REASONS = tuple(item.value for item in DeskewSkipReason)
_OBSERVED_DESKEW_SKIP_REASONS = {
    DeskewSkipReason.ROTATION_NOT_NEEDED.value,
    DeskewSkipReason.ROTATION_EXCEEDS_CLEANUP_LIMIT.value,
}


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_polygon(value: object, label: str) -> list[list[float]]:
    if (
        not isinstance(value, list)
        or len(value) < 3
        or any(
            not isinstance(point, list)
            or len(point) != 2
            or any(not _finite_number(coordinate) for coordinate in point)
            for point in value
        )
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _validate_box(value: object, label: str) -> dict[str, float]:
    if (
        not isinstance(value, dict)
        or tuple(value) != _AUTHORITY_SIDES
        or any(not _finite_number(value.get(side)) for side in _AUTHORITY_SIDES)
        or float(value["right"]) <= float(value["left"])
        or float(value["bottom"]) <= float(value["top"])
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _outside_authority_sides(
    footprint: list[list[float]],
    authority: dict[str, float],
) -> tuple[str, ...]:
    result = []
    if min(float(point[0]) for point in footprint) < authority["left"]:
        result.append("left")
    if min(float(point[1]) for point in footprint) < authority["top"]:
        result.append("top")
    if max(float(point[0]) for point in footprint) > authority["right"] - 1:
        result.append("right")
    if max(float(point[1]) for point in footprint) > authority["bottom"] - 1:
        result.append("bottom")
    return tuple(result)


def validate_output_footprint_authority(output: dict[str, Any]) -> None:
    """Validate one serialized output footprint without silent clipping."""

    if not isinstance(output, dict):
        raise ValueError("output footprint is invalid")
    required = _validate_polygon(
        output.get("required_source_footprint"),
        "required source footprint",
    )
    authority = _validate_box(
        output.get("sampling_authority_box"),
        "sampling authority box",
    )
    expected = set(_outside_authority_sides(required, authority))
    facts = output.get("saturation_facts")
    if not isinstance(facts, list):
        raise ValueError("footprint saturation facts are invalid")
    recorded: set[str] = set()
    for fact in facts:
        if (
            not isinstance(fact, dict)
            or set(fact) != {"authority_side"}
        ):
            raise ValueError("footprint saturation fact is invalid")
        side = fact["authority_side"]
        if (
            side not in _AUTHORITY_SIDES
            or side in recorded
        ):
            raise ValueError("footprint authority side is invalid")
        recorded.add(side)
    if recorded != expected:
        raise ValueError("footprint saturation facts disagree with authority")


def _validate_transform(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "matrix",
        "source_extent",
        "output_extent",
    }:
        raise ValueError("deskew transform is invalid")
    matrix = value["matrix"]
    if (
        not isinstance(matrix, list)
        or len(matrix) != 3
        or any(
            not isinstance(row, list)
            or len(row) != 3
            or any(not _finite_number(item) for item in row)
            for row in matrix
        )
        or tuple(float(item) for item in matrix[2]) != (0.0, 0.0, 1.0)
    ):
        raise ValueError("deskew affine matrix is invalid")
    determinant = (
        float(matrix[0][0]) * float(matrix[1][1])
        - float(matrix[0][1]) * float(matrix[1][0])
    )
    if abs(determinant) < 1.0e-12:
        raise ValueError("deskew affine matrix is singular")
    extents = []
    for name in ("source_extent", "output_extent"):
        extent = value[name]
        if (
            not isinstance(extent, dict)
            or set(extent) != {"width", "height"}
            or type(extent["width"]) is not int
            or type(extent["height"]) is not int
            or min(extent["width"], extent["height"]) <= 0
        ):
            raise ValueError(f"deskew {name} is invalid")
        extents.append(extent)
    identity_matrix = matrix == [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    return identity_matrix and extents[0] == extents[1]


def _validate_deskew_assessment(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "deskew_applied",
        "observed_angle_degrees",
        "applied_source_rotation_degrees",
        "skip_reason",
        "transform",
    }:
        raise ValueError("deskew assessment is invalid")
    applied = value["deskew_applied"]
    observed = value["observed_angle_degrees"]
    rotation = value["applied_source_rotation_degrees"]
    reason = value["skip_reason"]
    identity = _validate_transform(value["transform"])
    if type(applied) is not bool:
        raise ValueError("deskew applied fact is invalid")
    if applied:
        if (
            not _finite_number(observed)
            or not _finite_number(rotation)
            or float(rotation) == 0.0
            or reason is not None
            or identity
        ):
            raise ValueError("applied deskew assessment is inconsistent")
    elif observed is None:
        if (
            rotation is not None
            or reason not in _DESKEW_SKIP_REASONS
            or reason in _OBSERVED_DESKEW_SKIP_REASONS
            or not identity
        ):
            raise ValueError("unavailable deskew assessment is inconsistent")
    elif (
        not _finite_number(observed)
        or rotation != 0.0
        or reason not in _OBSERVED_DESKEW_SKIP_REASONS
        or not identity
    ):
        raise ValueError("observed deskew skip is inconsistent")
    return value


def _validate_gate(record: dict[str, Any], stage: str) -> None:
    checks = record.get("checks")
    check_keys = {
        "code",
        "stage",
        "state",
        "gap",
        "failure",
        "final_review_reason",
        "evaluated",
        "blocks",
    }
    if (
        not isinstance(checks, list)
        or tuple(item.get("code") for item in checks)
        != CANDIDATE_GATE_CHECK_CODES
        or any(item.get("stage") != stage for item in checks)
        or any(set(item) != check_keys for item in checks)
    ):
        raise ValueError(f"{stage} Gate is incomplete or out of order")
    for item in checks:
        supported = item.get("state") == "supported"
        evaluated = bool(item.get("evaluated"))
        if not evaluated:
            if (
                item.get("state") != "unavailable"
                or item.get("gap") is not None
                or item.get("failure") is not None
                or item.get("final_review_reason") is not None
                or bool(item.get("blocks"))
            ):
                raise ValueError(f"{stage} Gate unevaluated check is invalid")
            continue
        failure = item.get("failure")
        failure_valid = (
            failure is None
            if supported
            else isinstance(failure, dict)
            and set(failure)
            == {
                "gap",
                "recovery",
                "minimum_missing_fact",
                "recommended_action",
                "detail",
            }
            and failure.get("gap") == item.get("gap")
            and all(
                isinstance(failure.get(key), str) and failure.get(key)
                for key in (
                    "recovery",
                    "minimum_missing_fact",
                    "recommended_action",
                    "detail",
                )
            )
        )
        if (
            supported != (item.get("gap") is None)
            or not failure_valid
            or bool(item.get("blocks")) != (not supported)
            or (stage == "candidate" and item.get("final_review_reason") is not None)
            or (
                stage == "decision"
                and supported != (item.get("final_review_reason") is None)
            )
        ):
            raise ValueError(f"{stage} Gate typed gap is inconsistent")


def _validate_finalization(record: dict[str, Any]) -> None:
    status = record["decision"]["status"]
    finalization = record["output"]["finalization"]
    resolved = finalization["resolved_output_slots"]
    count = finalization["output_slot_count"]
    identities = finalization["slot_identities"]
    footprints = finalization["output_footprints"]
    authorities = finalization["sampling_authority_boxes"]
    boxes = finalization["final_boxes"]
    transforms = finalization["output_transforms"]
    deskew = _validate_deskew_assessment(finalization["deskew_assessment"])
    output_files = record["output"]["output_files"]
    review_copy = record["output"]["review_copy"]
    requested = finalization["frame_export_requested"]
    expected_tiff_validation = "header_validated" if output_files else "not_created"
    if record["output"]["tiff_fidelity"].get("validation") != expected_tiff_validation:
        raise ValueError("TIFF validation fact is inconsistent")
    if resolved is None:
        if count is not None or identities:
            raise ValueError("unresolved slots cannot claim identities")
    elif count != sum(resolved["lane_output_slot_counts"]) or len(identities) != count:
        raise ValueError("resolved output-slot identity is inconsistent")
    if status == "approved_auto":
        if (
            not finalization["frame_export_eligible"]
            or not isinstance(count, int)
            or count <= 0
            or any(len(values) != count for values in (
                footprints,
                authorities,
                boxes,
                transforms,
            ))
            or any(transform != deskew["transform"] for transform in transforms)
        ):
            raise ValueError("approved output lacks complete geometry")
        output_extent = deskew["transform"]["output_extent"]
        for box_value in boxes:
            box = _validate_box(box_value, "final output box")
            if (
                box["left"] < 0
                or box["top"] < 0
                or box["right"] > output_extent["width"]
                or box["bottom"] > output_extent["height"]
            ):
                raise ValueError("final output box exceeds deskew extent")
        if requested and (
            not finalization["frame_export_performed"]
            or finalization["official_tiff_count"] != count
            or len(output_files) != count
            or review_copy is not None
            or record["output"]["tiff_fidelity"]["validation"]
            != "header_validated"
        ):
            raise ValueError("approved output lacks validated TIFFs")
    elif status != "needs_review" or (
        finalization["frame_export_eligible"]
        or deskew["skip_reason"]
        != DeskewSkipReason.OUTPUT_NOT_ELIGIBLE.value
        or footprints
        or authorities
        or boxes
        or transforms
    ):
        raise ValueError("review output exposed official geometry")
    if not requested and (
        finalization["frame_export_performed"]
        or finalization["official_tiff_count"] != 0
        or output_files
        or review_copy is not None
    ):
        raise ValueError("analysis-only output created production artifacts")
    if status == "needs_review" and requested and (
        finalization["frame_export_performed"]
        or finalization["official_tiff_count"] != 0
        or output_files
        or review_copy is None
    ):
        raise ValueError("review output contract is incomplete")


def _validate_geometry(record: dict[str, Any]) -> None:
    geometry = record["photo_geometry"]
    if geometry.get("authority_partition") != AUTHORITY_PARTITION:
        raise ValueError("physical authority partition is invalid")
    resolved = geometry.get("resolved_slot_count")
    holder = geometry.get("matched_holder")
    if resolved is not None and (
        holder is None
        or resolved["matched_holder_profile_id"] != holder["profile"]["profile_id"]
        or resolved["holder_full_count"] != holder["full_count"]
        or resolved["output_count"] != geometry["output_slot_count"]
        or (
            resolved["authority"] == "matched_holder_default_count"
            and resolved["output_count"] != resolved["holder_full_count"]
        )
        or resolved["authority"]
        not in {"matched_holder_default_count", "user_explicit_count"}
    ):
        raise ValueError("matched holder and resolved count disagree")
    for lane in geometry["lanes"]:
        outputs = lane["output_footprints"]
        budgets = lane["direct_use_budget_assessments"]
        alignment = lane.get("template_alignment")
        coarse = lane.get("coarse_strip_support")
        if (
            not isinstance(coarse, dict)
            or set(coarse)
            != {
                "long_authority",
                "short_authority",
                "long_interval_px",
                "short_interval_px",
            }
            or coarse["long_authority"]
            not in {"pixel_observed", "holder_conservative"}
            or coarse["short_authority"]
            not in {"pixel_observed", "holder_conservative"}
            or not isinstance(alignment, dict)
            or set(alignment)
            != {
                "path",
                "pattern",
                "absolute_phase_px",
                "canonical_pitch_px",
                "pitch_delta_from_compiled_center_px",
                "maximum_absolute_role_residual_px",
                "local_advance_relations",
                "unbound_direct_observation_count",
                "unresolved_reason",
            }
            or alignment["pattern"] not in {"normal", "local_step", "unresolved"}
            or alignment["path"]
            != {
                "normal": "normal",
                "local_step": "local_advance",
                "unresolved": None,
            }[alignment["pattern"]]
            or (alignment["pattern"] == "unresolved")
            != (alignment["unresolved_reason"] is not None)
            or lane.get("selected_cross_boundary_use")
            not in {None, "aperture_pair", "enclosing_support_pair"}
        ):
            raise ValueError("template alignment summary is invalid")
        if {item["geometry_id"] for item in outputs} != {
            item["geometry_id"] for item in budgets
        }:
            raise ValueError("budget does not cover selected output")
        for budget in budgets:
            if (
                not isinstance(budget, dict)
                or set(budget) != _DIRECT_USE_BUDGET_FIELDS
            ):
                raise ValueError("direct-use budget summary is invalid")
            edges = budget.get("edge_assessments")
            if (
                budget.get("boundary_use")
                not in {"aperture_pair", "enclosing_support_pair"}
                or budget.get("state") not in {"supported", "contradicted"}
                or not isinstance(edges, list)
                or any(
                    not isinstance(edge, dict)
                    or set(edge) != _DIRECT_USE_EDGE_FIELDS
                    for edge in edges
                )
                or tuple(edge["role"] for edge in edges)
                != ("start", "end", "top", "bottom")
            ):
                raise ValueError("direct-use budget summary is invalid")
        for output in outputs:
            validate_output_footprint_authority(output)
        selected = lane["selected_placement_id"]
        if (selected is None) != (not outputs):
            raise ValueError("selected template output is incomplete")
        if not isinstance(lane.get("peak_temporary_bytes"), int) or lane[
            "peak_temporary_bytes"
        ] < 0:
            raise ValueError("template peak-memory fact is invalid")


def _validate_development(record: dict[str, Any]) -> None:
    detail = record["detail_level"]
    development = record["development"]
    if detail == "production":
        if development is not None:
            raise ValueError("production report contains development facts")
        return
    if detail != "development" or not isinstance(development, dict):
        raise ValueError("development report detail is unavailable")
    lanes = development.get("lanes")
    if not isinstance(lanes, list):
        raise ValueError("development lane facts are unavailable")
    for lane in lanes:
        placement = lane.get("placement_competition")
        work = lane.get("work")
        if (
            not isinstance(placement, dict)
            or not isinstance(work, dict)
            or work.get("placement_evaluation_count")
            != len(placement.get("placements", ()))
            or not isinstance(lane.get("phase_competition"), dict)
            or not isinstance(lane.get("cross_competition"), dict)
            or not isinstance(lane.get("template_alignment"), dict)
            or not isinstance(lane.get("winner_basis"), dict)
        ):
            raise ValueError("development template ledger is invalid")


def validate_current_report_record(record: dict[str, Any]) -> None:
    if tuple(record) != CURRENT_REPORT_SECTIONS:
        raise ValueError("current report sections are incomplete or out of order")
    if (
        record["schema_id"] != REPORT_SCHEMA_ID
        or record["schema_revision"] != REPORT_SCHEMA_REVISION
        or record["configuration"]["execution"]["detector_kind"]
        != "v5_bounded_template_placement"
    ):
        raise ValueError("report does not use the current-only schema")
    _validate_geometry(record)
    _validate_gate(record["candidate_gate"], "candidate")
    _validate_gate(record["decision"]["gate"], "decision")
    status = record["decision"].get("status")
    reasons = tuple(record["decision"].get("final_review_reasons", ()))
    if (
        status not in {"approved_auto", "needs_review"}
        or any(reason not in FINAL_REVIEW_REASONS for reason in reasons)
        or (status == "approved_auto") != (not reasons)
    ):
        raise ValueError("DecisionGate status/reasons are inconsistent")
    _validate_finalization(record)
    runtime = record["runtime_identity"]
    source = runtime.get("source", {})
    if (
        "runtime_environment" in runtime
        or not isinstance(source.get("input_ordinal"), int)
        or source.get("input_ordinal", 0) <= 0
        or not isinstance(source.get("orientation"), dict)
    ):
        raise ValueError("runtime identity is not lightweight")
    output_identity = runtime["output_identity"]
    finalization = record["output"]["finalization"]
    if (
        geometry := record["photo_geometry"]
    ) and (
        geometry["resolved_output_slots"] != finalization["resolved_output_slots"]
        or geometry["output_slot_count"] != finalization["output_slot_count"]
        or geometry["slot_identities"] != finalization["slot_identities"]
        or output_identity["resolved_output_slots"]
        != finalization["resolved_output_slots"]
        or output_identity["output_slot_count"] != finalization["output_slot_count"]
        or output_identity["slot_identities"] != finalization["slot_identities"]
    ):
        raise ValueError("output identities disagree")
    _validate_development(record)
