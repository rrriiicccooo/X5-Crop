"""Validate an external current report at its trust boundary."""

from __future__ import annotations

import math
from typing import Any

from x5crop.detection.candidate.assessment.model import CANDIDATE_GATE_CHECK_CODES
from x5crop.detection.decision.vocabulary import FINAL_REVIEW_REASONS
from x5crop.detection.output_deskew import DeskewSkipReason
from x5crop.detection.photo_geometry.output_model import FootprintSaturationKind
from x5crop.domain import Box
from x5crop.formats import OUTPUT_PROTECTION_SPEC
from x5crop.geometry.convex import clip_convex_polygon_to_box
from x5crop.report.identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION


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
    "maximum_same_state_cross_alignment_padding_mm",
    "maximum_same_state_cross_alignment_padding_within_limit",
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
_TEMPLATE_ALIGNMENT_FIELDS = {
    "path",
    "pattern",
    "absolute_phase_px",
    "canonical_pitch_px",
    "pitch_delta_from_compiled_center_px",
    "maximum_absolute_role_residual_px",
    "local_advance_relations",
    "global_lattice_authority",
    "adjacency_observation_coverage",
    "direct_role_binding_authority",
    "outer_frame_observation_authority",
    "frame_width_inference",
    "unbound_direct_observation_count",
    "unresolved_reason",
}
_APERTURE_ASPECT_RATIO_FIELDS = {
    "authority_id",
    "state",
    "calibration_id",
    "axis_guard_calibration_id",
    "raw_width_over_height",
    "guarded_width_over_height",
    "width_guard_mm",
    "height_guard_mm",
    "width_guard_ratio",
    "height_guard_ratio",
    "scale_height_over_width",
    "source_width_px",
    "inferred_height_px",
    "effective_height_px",
    "canonical_height_px",
    "width_observation_ids",
    "minimum_output_expansion_mm",
    "output_expansion_limit_mm",
    "failure_kind",
    "failure_detail",
    "consumed_for_cross_inference",
    "blocks_cross_resolution",
    "direct_height_px",
    "correlated_inference",
    "independent_constraint_rank",
}


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _valid_ids(value: object, *, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and item for item in value)
        and len(set(value)) == len(value)
    )


def _constraint_rank(rows: list[list[float]]) -> int:
    matrix = [list(map(float, row)) for row in rows]
    rank = 0
    for column in range(3):
        pivot = next(
            (
                index
                for index in range(rank, len(matrix))
                if abs(matrix[index][column]) > 1.0e-12
            ),
            None,
        )
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        divisor = matrix[rank][column]
        matrix[rank] = [value / divisor for value in matrix[rank]]
        for index, row in enumerate(matrix):
            if index == rank or abs(row[column]) <= 1.0e-12:
                continue
            factor = row[column]
            matrix[index] = [
                value - factor * pivot_value
                for value, pivot_value in zip(
                    row,
                    matrix[rank],
                    strict=True,
                )
            ]
        rank += 1
        if rank == 3:
            break
    return rank


def _validate_global_lattice_authority(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "state",
        "direct_role_constraint_rank",
        "joint_constraint_rank",
        "constraints",
        "role_observation_ids",
        "registered_evidence",
        "basis",
        "reason",
    }:
        raise ValueError("global lattice authority summary is invalid")
    constraints = value["constraints"]
    evidence = value["registered_evidence"]
    if (
        not isinstance(constraints, list)
        or not isinstance(evidence, dict)
        or set(evidence)
        != {
            "phase_observation_ids",
            "frame_width_observation_ids",
            "pitch_observation_ids",
        }
        or any(not _valid_ids(evidence[key]) for key in evidence)
        or not _valid_ids(value["role_observation_ids"])
    ):
        raise ValueError("global lattice provenance summary is invalid")
    allowed_kinds = {
        "direct_role_coordinate",
        "absolute_phase",
        "frame_width",
        "source_pitch",
    }
    rows: list[list[float]] = []
    direct_rows: list[list[float]] = []
    direct_ids: list[str] = []
    constraint_ids: list[str] = []
    for constraint in constraints:
        if (
            not isinstance(constraint, dict)
            or set(constraint)
            != {
                "constraint_id",
                "kind",
                "coefficients",
                "observation_ids",
            }
            or not isinstance(constraint["constraint_id"], str)
            or not constraint["constraint_id"]
            or constraint["kind"] not in allowed_kinds
            or not isinstance(constraint["coefficients"], list)
            or len(constraint["coefficients"]) != 3
            or any(
                not _finite_number(item)
                for item in constraint["coefficients"]
            )
            or not any(
                abs(float(item)) > 1.0e-12
                for item in constraint["coefficients"]
            )
            or not _valid_ids(
                constraint["observation_ids"],
                allow_empty=False,
            )
        ):
            raise ValueError("global lattice constraint summary is invalid")
        constraint_ids.append(constraint["constraint_id"])
        rows.append(constraint["coefficients"])
        if constraint["kind"] == "direct_role_coordinate":
            direct_rows.append(constraint["coefficients"])
            direct_ids.extend(constraint["observation_ids"])
    direct_rank = value["direct_role_constraint_rank"]
    joint_rank = value["joint_constraint_rank"]
    supported = value["state"] == "supported"
    if (
        len(set(constraint_ids)) != len(constraint_ids)
        or direct_ids != value["role_observation_ids"]
        or not isinstance(direct_rank, int)
        or not isinstance(joint_rank, int)
        or direct_rank != _constraint_rank(direct_rows)
        or joint_rank != _constraint_rank(rows)
        or not 0 <= direct_rank <= joint_rank <= 3
        or value["state"] not in {"supported", "unavailable"}
        or supported != (joint_rank == 3)
        or supported
        != (
            value["basis"]
            in {
                "direct_role_system",
                "complementary_direct_evidence",
            }
        )
        or supported != (value["reason"] is None)
    ):
        raise ValueError("global lattice closure summary is invalid")


def _valid_interval(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"minimum", "maximum"}
        and _finite_number(value["minimum"])
        and _finite_number(value["maximum"])
        and float(value["minimum"]) <= float(value["maximum"])
    )


def _validate_aperture_aspect_ratio_authority(value: object) -> None:
    if not isinstance(value, dict) or set(value) != _APERTURE_ASPECT_RATIO_FIELDS:
        raise ValueError("aperture aspect-ratio authority is incomplete")
    state = value["state"]
    supported = state == "supported"
    failed = state in {"unavailable", "contradicted"}
    if (
        not (supported or failed)
        or not isinstance(value["authority_id"], str)
        or not value["authority_id"]
        or value["correlated_inference"] is not True
        or value["independent_constraint_rank"] != 0
        or not isinstance(value["consumed_for_cross_inference"], bool)
        or not isinstance(value["blocks_cross_resolution"], bool)
        or (
            value["consumed_for_cross_inference"]
            and value["blocks_cross_resolution"]
        )
        or not _valid_ids(value["width_observation_ids"])
    ):
        raise ValueError("aperture aspect-ratio authority state is invalid")
    interval_fields = (
        "raw_width_over_height",
        "guarded_width_over_height",
        "scale_height_over_width",
        "source_width_px",
        "inferred_height_px",
        "effective_height_px",
    )
    for key in interval_fields:
        if value[key] is not None and not _valid_interval(value[key]):
            raise ValueError("aperture aspect-ratio interval is invalid")
    for key in (
        "width_guard_mm",
        "height_guard_mm",
        "width_guard_ratio",
        "height_guard_ratio",
        "minimum_output_expansion_mm",
        "output_expansion_limit_mm",
    ):
        if value[key] is not None and (
            not _finite_number(value[key]) or float(value[key]) < 0.0
        ):
            raise ValueError("aperture aspect-ratio scalar is invalid")
    for key in ("width_guard_ratio", "height_guard_ratio"):
        if value[key] is not None and not 0.0 < float(value[key]) < 1.0:
            raise ValueError("aperture aspect-ratio guard is invalid")
    if supported:
        if (
            not isinstance(value["calibration_id"], str)
            or not value["calibration_id"]
            or not isinstance(value["axis_guard_calibration_id"], str)
            or not value["axis_guard_calibration_id"]
            or any(value[key] is None for key in interval_fields)
            or any(
                value[key] is None
                for key in (
                    "width_guard_mm",
                    "height_guard_mm",
                    "width_guard_ratio",
                    "height_guard_ratio",
                )
            )
            or not _finite_number(value["canonical_height_px"])
            or not _finite_number(value["minimum_output_expansion_mm"])
            or not _finite_number(value["output_expansion_limit_mm"])
            or value["failure_kind"] is not None
            or value["failure_detail"] is not None
            or len(value["width_observation_ids"]) < 4
        ):
            raise ValueError("supported aspect-ratio authority is invalid")
    elif (
        value["failure_kind"]
        not in {
            "aperture_aspect_ratio_authority_unavailable",
            "aperture_aspect_ratio_physical_prior_conflict",
            "aperture_aspect_ratio_direct_conflict",
            "aperture_aspect_ratio_budget_exhausted",
        }
        or not isinstance(value["failure_detail"], str)
        or not value["failure_detail"]
    ):
        raise ValueError("failed aspect-ratio authority is invalid")
    if value["calibration_id"] is not None and (
        not isinstance(value["calibration_id"], str)
        or not value["calibration_id"]
        or not isinstance(value["axis_guard_calibration_id"], str)
        or not value["axis_guard_calibration_id"]
        or any(
            value[key] is None
            for key in (
                "raw_width_over_height",
                "guarded_width_over_height",
                "scale_height_over_width",
                "source_width_px",
                "inferred_height_px",
                "width_guard_mm",
                "height_guard_mm",
                "width_guard_ratio",
                "height_guard_ratio",
                "output_expansion_limit_mm",
            )
        )
    ):
        raise ValueError("calibrated aspect-ratio failure lost provenance")
    if value["calibration_id"] is None and any(
        value[key] is not None
        for key in (
            "axis_guard_calibration_id",
            "raw_width_over_height",
            "guarded_width_over_height",
            "scale_height_over_width",
            "source_width_px",
            "inferred_height_px",
            "effective_height_px",
            "canonical_height_px",
            "width_guard_mm",
            "height_guard_mm",
            "width_guard_ratio",
            "height_guard_ratio",
            "minimum_output_expansion_mm",
            "output_expansion_limit_mm",
        )
    ):
        raise ValueError("uncalibrated aspect-ratio failure has derived state")
    if value["direct_height_px"] is not None and not _valid_interval(
        value["direct_height_px"]
    ):
        raise ValueError("direct aspect-ratio comparison is invalid")


def _validate_adjacency_coverage(value: object) -> None:
    if not isinstance(value, list):
        raise ValueError("adjacency coverage summary is invalid")
    ordinals: list[int] = []
    for coverage in value:
        if not isinstance(coverage, dict) or set(coverage) != {
            "relation_ordinal",
            "required_interval_px",
            "covering_query_ids",
            "trace_coverage",
            "required_trace_count",
            "covered_trace_count",
            "required_coordinate_count",
            "covered_coordinate_count",
            "normal_inference_required",
            "state",
        }:
            raise ValueError("adjacency coverage item is invalid")
        ordinal = coverage["relation_ordinal"]
        required = coverage["required_interval_px"]
        traces = coverage["trace_coverage"]
        if (
            not isinstance(ordinal, int)
            or ordinal <= 0
            or not _valid_interval(required)
            or not _valid_ids(coverage["covering_query_ids"])
            or coverage["covering_query_ids"]
            != sorted(coverage["covering_query_ids"])
            or not isinstance(traces, list)
            or not isinstance(coverage["normal_inference_required"], bool)
            or coverage["state"] not in {"complete", "incomplete"}
        ):
            raise ValueError("adjacency coverage item is invalid")
        ordinals.append(ordinal)
        trace_positions: list[int] = []
        trace_query_ids: set[str] = set()
        required_coordinates = 0
        covered_coordinates = 0
        complete_traces = 0
        for trace in traces:
            if (
                not isinstance(trace, dict)
                or set(trace)
                != {
                    "trace_position_px",
                    "covering_query_ids",
                    "covered_intervals_px",
                    "required_coordinate_count",
                    "covered_coordinate_count",
                    "complete",
                }
                or not isinstance(trace["trace_position_px"], int)
                or not _valid_ids(trace["covering_query_ids"])
                or trace["covering_query_ids"]
                != sorted(trace["covering_query_ids"])
                or not isinstance(trace["covered_intervals_px"], list)
                or any(
                    not _valid_interval(interval)
                    or float(interval["minimum"])
                    < float(required["minimum"])
                    or float(interval["maximum"])
                    > float(required["maximum"])
                    for interval in trace["covered_intervals_px"]
                )
                or not isinstance(trace["required_coordinate_count"], int)
                or not isinstance(trace["covered_coordinate_count"], int)
                or not 0
                <= trace["covered_coordinate_count"]
                <= trace["required_coordinate_count"]
                or not isinstance(trace["complete"], bool)
                or trace["complete"]
                and trace["covered_coordinate_count"]
                != trace["required_coordinate_count"]
            ):
                raise ValueError("adjacency trace coverage is invalid")
            trace_positions.append(trace["trace_position_px"])
            trace_query_ids.update(trace["covering_query_ids"])
            required_coordinates += trace["required_coordinate_count"]
            covered_coordinates += trace["covered_coordinate_count"]
            complete_traces += int(trace["complete"])
        complete = (
            bool(traces)
            and complete_traces == len(traces)
            and covered_coordinates == required_coordinates
        )
        if (
            trace_positions != sorted(set(trace_positions))
            or sorted(trace_query_ids) != coverage["covering_query_ids"]
            or coverage["required_trace_count"] != len(traces)
            or coverage["covered_trace_count"] != complete_traces
            or coverage["required_coordinate_count"] != required_coordinates
            or coverage["covered_coordinate_count"] != covered_coordinates
            or complete != (coverage["state"] == "complete")
        ):
            raise ValueError("adjacency aggregate coverage is invalid")
    if ordinals != list(range(1, len(ordinals) + 1)):
        raise ValueError("adjacency coverage ordinals are invalid")


def _validate_outer_frame_observation_authority(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "state",
        "first_frame_ordinal",
        "last_frame_ordinal",
        "first_frame_observation_ids",
        "last_frame_observation_ids",
        "reason",
    }:
        raise ValueError("outer-frame observation authority summary is invalid")
    first = value["first_frame_observation_ids"]
    last = value["last_frame_observation_ids"]
    supported = value["state"] == "supported"
    if (
        value["state"] not in {"supported", "unavailable"}
        or value["first_frame_ordinal"] != 1
        or not isinstance(value["last_frame_ordinal"], int)
        or value["last_frame_ordinal"] < 1
        or not _valid_ids(first)
        or not _valid_ids(last)
        or supported != bool(first and last)
        or supported != (value["reason"] is None)
        or value["reason"] is not None
        and (not isinstance(value["reason"], str) or not value["reason"])
    ):
        raise ValueError("outer-frame observation authority summary is invalid")


def _validate_frame_width_inference(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "state",
        "inferred_role_indices",
        "supporting_frame_ordinals",
        "width_px",
        "canonical_width_px",
        "observation_ids",
        "failure_kind",
        "validation_only_role_indices",
        "validation_observation_ids",
    }:
        raise ValueError("Frame width inference summary is invalid")
    inferred = value["inferred_role_indices"]
    supporting = value["supporting_frame_ordinals"]
    observation_ids = value["observation_ids"]
    validation_only = value["validation_only_role_indices"]
    validation_ids = value["validation_observation_ids"]
    supported = value["state"] == "supported"
    if (
        value["state"] not in {"supported", "unavailable"}
        or not isinstance(inferred, list)
        or inferred != sorted(set(inferred))
        or not inferred
        or any(not isinstance(index, int) or index < 0 for index in inferred)
        or not isinstance(supporting, list)
        or supporting != sorted(set(supporting))
        or any(
            not isinstance(ordinal, int) or ordinal <= 0
            for ordinal in supporting
        )
        or not _valid_ids(observation_ids)
        or not isinstance(validation_only, list)
        or validation_only != sorted(set(validation_only))
        or any(
            not isinstance(index, int) or index < 0
            for index in validation_only
        )
        or any(index not in inferred for index in validation_only)
        or not _valid_ids(validation_ids)
        or len(validation_only) != len(validation_ids)
        or not set(validation_ids).isdisjoint(observation_ids)
    ):
        raise ValueError("Frame width inference ledger is invalid")
    if supported:
        width = value["width_px"]
        canonical = value["canonical_width_px"]
        if (
            len(supporting) < 2
            or len(observation_ids) < 4
            or not _valid_interval(width)
            or not _finite_number(canonical)
            or not float(width["minimum"])
            <= float(canonical)
            <= float(width["maximum"])
            or value["failure_kind"] is not None
        ):
            raise ValueError("supported Frame width inference is invalid")
    elif (
        supporting
        or observation_ids
        or validation_only
        or validation_ids
        or value["width_px"] is not None
        or value["canonical_width_px"] is not None
        or value["failure_kind"]
        not in {
            "complete_frame_unobserved",
            "common_width_authority_unavailable",
        }
    ):
        raise ValueError("unavailable Frame width inference is invalid")


def _validate_direct_role_binding_authority(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "state",
        "facts",
        "unsupported_role_indices",
        "reason",
    }:
        raise ValueError("direct-role binding authority summary is invalid")
    facts = value["facts"]
    unsupported = value["unsupported_role_indices"]
    if not isinstance(facts, list) or not isinstance(unsupported, list):
        raise ValueError("direct-role binding authority ledger is invalid")
    indices: list[int] = []
    blocked: list[int] = []
    contradicted = False
    allowed_bases = {
        "source_wide_edge",
        "cross_height_union",
        "separator_pair",
        "partial_height_separator_pair",
    }
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != {
            "role_index",
            "lane_ordinal",
            "role",
            "observation_id",
            "independent_support_region_count",
            "bases",
            "blocking_material_conflict_ids",
            "state",
        }:
            raise ValueError("direct-role authority fact is invalid")
        index = fact["role_index"]
        bases = fact["bases"]
        conflicts = fact["blocking_material_conflict_ids"]
        supported = fact["state"] == "supported"
        conflict = fact["state"] == "contradicted"
        if (
            not isinstance(index, int)
            or index < 0
            or fact["lane_ordinal"] != index // 2 + 1
            or fact["role"] != ("start" if index % 2 == 0 else "end")
            or not isinstance(fact["observation_id"], str)
            or not fact["observation_id"]
            or fact["independent_support_region_count"] not in {1, 2, 3}
            or not isinstance(bases, list)
            or bases != list(dict.fromkeys(bases))
            or any(item not in allowed_bases for item in bases)
            or (
                "partial_height_separator_pair" in bases
                and (
                    bases != ["partial_height_separator_pair"]
                    or fact["independent_support_region_count"] != 2
                )
            )
            or not isinstance(conflicts, list)
            or conflicts != sorted(set(conflicts))
            or any(not isinstance(item, str) or not item for item in conflicts)
            or fact["state"]
            not in {"supported", "contradicted", "unavailable"}
            or conflict != bool(conflicts)
            or supported != (bool(bases) and not conflicts)
            or (fact["state"] == "unavailable")
            != (not bases and not conflicts)
        ):
            raise ValueError("direct-role authority fact is invalid")
        indices.append(index)
        if not supported:
            blocked.append(index)
        contradicted = contradicted or conflict
    expected_state = (
        "contradicted" if contradicted else "unavailable" if blocked else "supported"
    )
    if (
        indices != sorted(set(indices))
        or unsupported != blocked
        or value["state"] != expected_state
        or (expected_state == "supported") != (value["reason"] is None)
        or value["reason"] is not None
        and (not isinstance(value["reason"], str) or not value["reason"])
    ):
        raise ValueError("direct-role binding authority summary is invalid")


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


def _authority_overflow_px(
    footprint: list[list[float]],
    authority: dict[str, float],
    side: str,
) -> float:
    if side == "left":
        return max(0.0, authority["left"] - min(point[0] for point in footprint))
    if side == "top":
        return max(0.0, authority["top"] - min(point[1] for point in footprint))
    if side == "right":
        return max(
            0.0,
            max(point[0] for point in footprint) - (authority["right"] - 1),
        )
    return max(
        0.0,
        max(point[1] for point in footprint) - (authority["bottom"] - 1),
    )


def _same_polygon(
    left: list[list[float]],
    right: tuple[tuple[float, float], ...],
) -> bool:
    return len(left) == len(right) and all(
        abs(float(a[0]) - b[0]) <= 1.0e-8
        and abs(float(a[1]) - b[1]) <= 1.0e-8
        for a, b in zip(left, right, strict=True)
    )


def validate_output_footprint_authority(output: dict[str, Any]) -> None:
    """Validate one serialized output footprint and explicit edge saturation."""

    if not isinstance(output, dict):
        raise ValueError("output footprint is invalid")
    mandatory = _validate_polygon(
        output.get("mandatory_source_footprint"),
        "mandatory source footprint",
    )
    requested = _validate_polygon(
        output.get("requested_source_footprint"),
        "requested source footprint",
    )
    required = _validate_polygon(
        output.get("required_source_footprint"),
        "required source footprint",
    )
    authority = _validate_box(
        output.get("sampling_authority_box"),
        "sampling authority box",
    )
    envelope = output.get("envelope")
    boundary_use = (
        envelope.get("boundary_use") if isinstance(envelope, dict) else None
    )
    same_state_cross_padding = output.get(
        "maximum_same_state_cross_alignment_padding_px"
    )
    support_output = boundary_use == "enclosing_support_pair"
    if support_output != _finite_number(same_state_cross_padding) or (
        support_output and float(same_state_cross_padding) < 0.0
    ):
        raise ValueError("same-state cross padding is invalid")
    expected = set(_outside_authority_sides(requested, authority))
    facts = output.get("saturation_facts")
    if not isinstance(facts, list):
        raise ValueError("footprint saturation facts are invalid")
    recorded: set[str] = set()
    for fact in facts:
        if (
            not isinstance(fact, dict)
            or set(fact)
            != {
                "authority_side",
                "kind",
                "requested_overflow_px",
                "mandatory_overflow_px",
            }
        ):
            raise ValueError("footprint saturation fact is invalid")
        side = fact["authority_side"]
        kind = fact["kind"]
        requested_overflow = fact["requested_overflow_px"]
        mandatory_overflow = fact["mandatory_overflow_px"]
        if (
            side not in _AUTHORITY_SIDES
            or side in recorded
            or kind not in {item.value for item in FootprintSaturationKind}
            or not _finite_number(requested_overflow)
            or float(requested_overflow) <= 0.0
            or not _finite_number(mandatory_overflow)
            or float(mandatory_overflow) < 0.0
            or abs(
                float(requested_overflow)
                - _authority_overflow_px(requested, authority, side)
            )
            > 1.0e-8
            or abs(
                float(mandatory_overflow)
                - _authority_overflow_px(mandatory, authority, side)
            )
            > 1.0e-8
            or (
                kind
                in {
                    FootprintSaturationKind.SOURCE_BOUNDARY_JOINT_PROTECTION.value,
                    FootprintSaturationKind.LANE_BOUNDARY_JOINT_PROTECTION.value,
                }
            )
            != (float(mandatory_overflow) > 0.0)
        ):
            raise ValueError("footprint authority side is invalid")
        recorded.add(side)
    if recorded != expected:
        raise ValueError("footprint saturation facts disagree with authority")
    safely_source_bounded = all(
        fact["kind"]
        in {
            FootprintSaturationKind.SOURCE_BOUNDARY_OPTIONAL_BLEED.value,
            FootprintSaturationKind.SOURCE_BOUNDARY_JOINT_PROTECTION.value,
        }
        for fact in facts
    )
    source_box_values = tuple(authority[side] for side in _AUTHORITY_SIDES)
    if any(float(value) != int(value) for value in source_box_values):
        raise ValueError("sampling authority box must use integer pixel bounds")
    expected_required = (
        clip_convex_polygon_to_box(
            tuple((float(point[0]), float(point[1])) for point in requested),
            Box(*(int(value) for value in source_box_values)),
        )
        if facts and safely_source_bounded
        else tuple((float(point[0]), float(point[1])) for point in requested)
    )
    if not _same_polygon(required, expected_required):
        raise ValueError("required source footprint violates saturation contract")


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
    geometry = record["photo_geometry"]
    resolved = geometry["resolved_output_slots"]
    count = geometry["output_slot_count"]
    identities = geometry["slot_identities"]
    footprints = finalization["output_footprints"]
    boxes = finalization["final_boxes"]
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
            or len(footprints) != count
            or len(boxes) != count
        ):
            raise ValueError("approved output lacks complete geometry")
        for footprint in footprints:
            validate_output_footprint_authority(footprint)
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
        or boxes
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
        outputs_by_id = {item["geometry_id"]: item for item in outputs}
        alignment = lane.get("template_alignment")
        coarse = lane.get("coarse_strip_support")
        _validate_aperture_aspect_ratio_authority(
            lane.get("aperture_aspect_ratio_authority")
        )
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
            or set(alignment) != _TEMPLATE_ALIGNMENT_FIELDS
            or alignment["pattern"]
            not in {"normal", "measured_advances", "unresolved"}
            or alignment["path"]
            != {
                "normal": "normal",
                "measured_advances": "local_advance",
                "unresolved": None,
            }[alignment["pattern"]]
            or (alignment["pattern"] == "unresolved")
            != (alignment["unresolved_reason"] is not None)
            or lane.get("selected_cross_boundary_use")
            not in {None, "aperture_pair", "enclosing_support_pair"}
        ):
            raise ValueError("template alignment summary is invalid")
        _validate_global_lattice_authority(
            alignment["global_lattice_authority"]
        )
        _validate_adjacency_coverage(
            alignment["adjacency_observation_coverage"]
        )
        _validate_direct_role_binding_authority(
            alignment["direct_role_binding_authority"]
        )
        _validate_outer_frame_observation_authority(
            alignment["outer_frame_observation_authority"]
        )
        _validate_frame_width_inference(
            alignment["frame_width_inference"]
        )
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
            if any(
                not _finite_number(edge[key]) or float(edge[key]) < 0.0
                for edge in edges
                for key in ("expansion_px", "expansion_mm", "limit_mm")
            ) or any(
                edge["limit_applies"] is not True
                or edge["within_limit"]
                != (float(edge["expansion_mm"]) <= float(edge["limit_mm"]))
                for edge in edges
            ):
                raise ValueError("direct-use edge budget is invalid")
            support = budget["boundary_use"] == "enclosing_support_pair"
            support_fields_present = (
                _finite_number(budget["enclosing_support_height_ratio"])
                and isinstance(
                    budget["enclosing_support_within_limit"], bool
                )
                and _finite_number(
                    budget["maximum_same_state_cross_alignment_padding_mm"]
                )
                and isinstance(
                    budget[
                        "maximum_same_state_cross_alignment_padding_within_limit"
                    ],
                    bool,
                )
            )
            if support != support_fields_present:
                raise ValueError("enclosing-support budget is invalid")
            if not support and any(
                budget[key] is not None
                for key in (
                    "enclosing_support_height_ratio",
                    "enclosing_support_within_limit",
                    "maximum_same_state_cross_alignment_padding_mm",
                    "maximum_same_state_cross_alignment_padding_within_limit",
                )
            ):
                raise ValueError("aperture budget carries support fields")
            if support:
                output = outputs_by_id.get(budget["geometry_id"])
                source_geometry = lane.get("source_scan_geometry")
                height_state = (
                    None
                    if not isinstance(source_geometry, dict)
                    else source_geometry.get("height_state")
                )
                height_vertices = (
                    None
                    if not isinstance(height_state, dict)
                    else height_state.get("vertices")
                )
                if (
                    not isinstance(output, dict)
                    or not isinstance(height_vertices, list)
                    or not height_vertices
                    or any(
                        not isinstance(vertex, list)
                        or len(vertex) != 2
                        or not _finite_number(vertex[0])
                        or float(vertex[0]) <= 0.0
                        for vertex in height_vertices
                    )
                ):
                    raise ValueError("same-state cross padding source is invalid")
                cross_limit = min(
                    float(edge["limit_mm"])
                    for edge in edges
                    if edge["role"] in {"top", "bottom"}
                )
                padding_px = output.get(
                    "maximum_same_state_cross_alignment_padding_px"
                )
                if not _finite_number(padding_px) or float(padding_px) < 0.0:
                    raise ValueError("same-state cross padding is invalid")
                expected_padding_mm = float(padding_px) / min(
                    float(vertex[0]) for vertex in height_vertices
                )
                if (
                    float(budget["enclosing_support_height_ratio"]) <= 1.0
                    or budget["enclosing_support_within_limit"]
                    != (
                        float(budget["enclosing_support_height_ratio"])
                        <= OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
                    )
                    or abs(
                        float(
                            budget[
                                "maximum_same_state_cross_alignment_padding_mm"
                            ]
                        )
                        - expected_padding_mm
                    )
                    > 1.0e-8
                    or float(
                        budget[
                            "maximum_same_state_cross_alignment_padding_mm"
                        ]
                    )
                    < 0.0
                    or budget[
                        "maximum_same_state_cross_alignment_padding_within_limit"
                    ]
                    != (
                        float(
                            budget[
                                "maximum_same_state_cross_alignment_padding_mm"
                            ]
                        )
                        <= cross_limit
                    )
                ):
                    raise ValueError("support cross-alignment budget is invalid")
            supported = all(edge["within_limit"] for edge in edges) and (
                budget["enclosing_support_within_limit"] is not False
            ) and (
                budget[
                    "maximum_same_state_cross_alignment_padding_within_limit"
                ]
                is not False
            )
            if (budget["state"] == "supported") != supported:
                raise ValueError("direct-use budget state is invalid")
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
        winner = lane.get("winner_basis")
        if (
            not isinstance(placement, dict)
            or not isinstance(work, dict)
            or work.get("placement_evaluation_count")
            != len(placement.get("placements", ()))
            or not isinstance(lane.get("phase_competition"), dict)
            or not isinstance(lane.get("cross_competition"), dict)
            or lane.get("aperture_aspect_ratio_authority")
            != lane.get("cross_competition", {}).get(
                "aperture_aspect_ratio_authority"
            )
            or not isinstance(lane.get("template_alignment"), dict)
            or not isinstance(winner, dict)
            or set(winner)
            != {
                "state",
                "phase",
                "cross",
                "failure",
                "selected_placement_id",
                "runner_up_placement_id",
            }
            or winner["phase"]
            != lane["phase_competition"].get("winner_basis")
            or winner["cross"]
            != lane["cross_competition"].get("winner_basis")
            or winner["state"] != placement.get("state")
            or winner["failure"] != placement.get("failure")
            or winner["selected_placement_id"]
            != placement.get("selected_placement_id")
            or winner["runner_up_placement_id"]
            != placement.get("runner_up_placement_id")
        ):
            raise ValueError("development template ledger is invalid")


def validate_current_report_record(record: dict[str, Any]) -> None:
    if tuple(record) != CURRENT_REPORT_SECTIONS:
        raise ValueError("current report sections are incomplete or out of order")
    if (
        record["schema_id"] != REPORT_SCHEMA_ID
        or record["schema_revision"] != REPORT_SCHEMA_REVISION
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
    _validate_development(record)
