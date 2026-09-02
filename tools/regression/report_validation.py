"""Validate an external current report at its trust boundary."""

from __future__ import annotations

import math
from typing import Any

from x5crop.detection.candidate.assessment.model import CANDIDATE_GATE_CHECK_CODES
from x5crop.detection.decision.vocabulary import FINAL_REVIEW_REASONS
from x5crop.detection.output_deskew import DeskewSkipReason
from x5crop.detection.photo_geometry.output_model import FootprintSaturationKind
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFailureKind,
    PhaseFitStatus,
    PhaseRetainedProposalBasis,
)
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
_FAILURE_FIELDS = {
    "gap",
    "recovery",
    "minimum_missing_fact",
    "recommended_action",
    "detail",
}
_PLACEMENT_PROPOSAL_FIELDS = {
    "lane_id",
    "state",
    "placement_id",
    "output_footprints",
    "failure",
}
_SOURCE_PROPOSAL_FIELDS = {
    "lane_ids",
    "placement_ids",
    "state",
    "failure",
}
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
_PHASE_FAILURE_KINDS = {None, *(item.value for item in PhaseFailureKind)}
_PHASE_STATUSES = {item.value for item in PhaseFitStatus}
_PHASE_RETAINED_PROPOSAL_BASES = {
    item.value for item in PhaseRetainedProposalBasis
}
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
    "adjacency_relations",
    "global_lattice_authority",
    "calibrated_nominal_grid_evidence",
    "adjacency_observation_coverage",
    "adjacency_continuity_observations",
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
_SOURCE_FRAME_WIDTH_AUTHORITY_FIELDS = {
    "authority_id",
    "state",
    "selected_integer_slot_offset",
    "selected_phase_anchor_observation_ids",
    "supporting_role_observation_ids",
    "basis",
    "supporting_frame_ordinals",
    "supporting_constraint_ids",
    "width_px",
    "canonical_width_px",
    "observation_ids",
    "failure_kind",
    "reason",
}
_SOURCE_FRAME_WIDTH_FAILURE_KINDS = {
    "unique_placement_unavailable",
    "direct_role_authority_unavailable",
    "direct_role_authority_contradicted",
    "global_lattice_rank_insufficient",
    "adjacency_coverage_incomplete",
    "source_width_closure_unavailable",
    "physical_width_conflict",
}
_ENCLOSING_SUPPORT_APERTURE_AUTHORITY_FIELDS = {
    "authority_id",
    "state",
    "calibration_id",
    "calibration_cohort_sha256",
    "calibration_observation_set_sha256",
    "eligibility_revision",
    "support_observation_ids",
    "support_span_px",
    "canonical_height_px",
    "calibrated_center_offset_ratio",
    "calibrated_center_offset_px",
    "physical_center_offset_px",
    "effective_center_offset_px",
    "failure_kind",
    "failure_detail",
    "correlated_inference",
    "independent_constraint_rank",
}

_NOMINAL_GRID_EVIDENCE_FIELDS = {
    "evidence_id",
    "state",
    "prior_id",
    "phase_anchor_role_indices",
    "phase_anchor_observation_ids",
    "inferred_adjacency_ordinals",
    "unobserved_frame_ordinals",
    "covering_query_ids",
    "failure_kind",
    "reason",
}
_NOMINAL_GRID_AUTHORITY_FIELDS = {
    "authority_id",
    "state",
    "evidence_id",
    "placement_id",
    "output_geometry_ids",
    "failure_kind",
    "reason",
}
_NOMINAL_GRID_FAILURE_KINDS = {
    "calibrated_nominal_grid_authority_unavailable",
    "nominal_grid_phase_anchor_unavailable",
    "adjacency_observation_coverage_incomplete",
    "nominal_grid_counterevidence",
    "output_footprint_unavailable",
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
                "role_index",
                "value_interval_px",
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
            or (
                constraint["kind"] == "direct_role_coordinate"
                and (
                    not isinstance(constraint["role_index"], int)
                    or constraint["role_index"] < 0
                    or not _valid_interval(constraint["value_interval_px"])
                )
            )
            or (
                constraint["kind"] == "absolute_phase"
                and (
                    constraint["role_index"] is not None
                    or not _valid_interval(constraint["value_interval_px"])
                )
            )
            or (
                constraint["kind"] in {"frame_width", "source_pitch"}
                and (
                    constraint["role_index"] is not None
                    or constraint["value_interval_px"] is not None
                )
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


def _validate_nominal_grid_evidence(value: object) -> None:
    if value is None:
        return
    if (
        not isinstance(value, dict)
        or set(value) != _NOMINAL_GRID_EVIDENCE_FIELDS
        or value["state"] not in {"supported", "unavailable", "contradicted"}
        or not isinstance(value["evidence_id"], str)
        or not value["evidence_id"]
        or not isinstance(value["prior_id"], str)
        or not value["prior_id"]
        or not _valid_ids(value["phase_anchor_observation_ids"], allow_empty=False)
        or not _valid_ids(value["covering_query_ids"])
        or not isinstance(value["phase_anchor_role_indices"], list)
        or not isinstance(value["inferred_adjacency_ordinals"], list)
        or not isinstance(value["unobserved_frame_ordinals"], list)
        or value["phase_anchor_role_indices"]
        != sorted(set(value["phase_anchor_role_indices"]))
        or value["inferred_adjacency_ordinals"]
        != sorted(set(value["inferred_adjacency_ordinals"]))
        or value["unobserved_frame_ordinals"]
        != sorted(set(value["unobserved_frame_ordinals"]))
        or len(value["phase_anchor_role_indices"])
        != len(value["phase_anchor_observation_ids"])
    ):
        raise ValueError("calibrated nominal Grid evidence summary is invalid")
    supported = value["state"] == "supported"
    failed = value["state"] in {"unavailable", "contradicted"}
    if (
        any(
            not isinstance(index, int) or index < 0
            for index in value["phase_anchor_role_indices"]
        )
        or any(
            not isinstance(ordinal, int) or ordinal <= 0
            for ordinal in value["inferred_adjacency_ordinals"]
        )
        or any(
            not isinstance(ordinal, int) or ordinal <= 0
            for ordinal in value["unobserved_frame_ordinals"]
        )
        or supported
        != (value["failure_kind"] is None and value["reason"] is None)
        or failed
        != (
            value["failure_kind"] in _NOMINAL_GRID_FAILURE_KINDS
            and isinstance(value["reason"], str)
            and bool(value["reason"])
        )
    ):
        raise ValueError("calibrated nominal Grid evidence state is invalid")


def _validate_nominal_grid_authority(
    value: object,
    *,
    selected_placement_id: object,
    output_geometry_ids: set[str],
) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != _NOMINAL_GRID_AUTHORITY_FIELDS
        or value["state"]
        not in {"supported", "unavailable", "contradicted", "not_applicable"}
        or not isinstance(value["authority_id"], str)
        or not value["authority_id"]
        or not _valid_ids(value["output_geometry_ids"])
    ):
        raise ValueError("calibrated nominal Grid authority summary is invalid")
    state = value["state"]
    supported = state == "supported"
    not_applicable = state == "not_applicable"
    failed = state in {"unavailable", "contradicted"}
    if (
        supported
        != (
            isinstance(value["evidence_id"], str)
            and bool(value["evidence_id"])
            and value["placement_id"] == selected_placement_id
            and set(value["output_geometry_ids"]) == output_geometry_ids
            and bool(output_geometry_ids)
            and value["failure_kind"] is None
            and value["reason"] is None
        )
        or not_applicable
        != (
            value["evidence_id"] is None
            and value["placement_id"] is None
            and not value["output_geometry_ids"]
            and value["failure_kind"] is None
            and value["reason"] is None
        )
        or failed
        != (
            isinstance(value["evidence_id"], str)
            and bool(value["evidence_id"])
            and (
                value["placement_id"] is None
                or isinstance(value["placement_id"], str)
                and bool(value["placement_id"])
            )
            and value["failure_kind"] in _NOMINAL_GRID_FAILURE_KINDS
            and isinstance(value["reason"], str)
            and bool(value["reason"])
        )
    ):
        raise ValueError("calibrated nominal Grid authority state is invalid")


def _valid_interval(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"minimum", "maximum"}
        and _finite_number(value["minimum"])
        and _finite_number(value["maximum"])
        and float(value["minimum"]) <= float(value["maximum"])
    )


def _validate_enclosing_support_aperture_authority(
    value: object,
) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != _ENCLOSING_SUPPORT_APERTURE_AUTHORITY_FIELDS
        or not isinstance(value["authority_id"], str)
        or not value["authority_id"]
        or value["state"]
        not in {"supported", "not_applicable", "unavailable", "contradicted"}
        or not isinstance(value["support_observation_ids"], list)
        or len(set(value["support_observation_ids"]))
        != len(value["support_observation_ids"])
        or value["correlated_inference"] is not True
        or value["independent_constraint_rank"] != 0
    ):
        raise ValueError("enclosing-support aperture authority is invalid")
    optional = (
        "calibration_id",
        "calibration_cohort_sha256",
        "calibration_observation_set_sha256",
        "eligibility_revision",
        "support_span_px",
        "canonical_height_px",
        "calibrated_center_offset_ratio",
        "calibrated_center_offset_px",
        "physical_center_offset_px",
        "effective_center_offset_px",
    )
    if value["state"] == "not_applicable":
        if (
            any(value[key] is not None for key in optional)
            or value["support_observation_ids"]
            or value["failure_kind"] is not None
            or value["failure_detail"] is not None
        ):
            raise ValueError(
                "non-enclosing output carries aperture authority"
            )
        return
    support_span = value["support_span_px"]
    height = value["canonical_height_px"]
    if (
        len(value["support_observation_ids"]) < 2
        or not _valid_interval(support_span)
        or not _finite_number(height)
        or float(height) <= 0.0
        or float(support_span["minimum"]) <= float(height)
        or not _valid_interval(value["physical_center_offset_px"])
    ):
        raise ValueError("enclosing-support physical authority is invalid")
    if value["state"] == "unavailable":
        if (
            any(
                value[key] is not None
                for key in (
                    "calibration_id",
                    "calibration_cohort_sha256",
                    "calibration_observation_set_sha256",
                    "eligibility_revision",
                    "calibrated_center_offset_ratio",
                    "calibrated_center_offset_px",
                    "effective_center_offset_px",
                )
            )
            or value["failure_kind"]
            != "enclosing_support_aperture_calibration_unavailable"
            or not isinstance(value["failure_detail"], str)
            or not value["failure_detail"]
        ):
            raise ValueError(
                "unavailable enclosing-support calibration is invalid"
            )
        return
    if (
        not isinstance(value["calibration_id"], str)
        or not value["calibration_id"]
        or not isinstance(value["calibration_cohort_sha256"], str)
        or len(value["calibration_cohort_sha256"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in value["calibration_cohort_sha256"]
        )
        or not isinstance(
            value["calibration_observation_set_sha256"], str
        )
        or len(value["calibration_observation_set_sha256"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in value["calibration_observation_set_sha256"]
        )
        or not isinstance(value["eligibility_revision"], str)
        or not value["eligibility_revision"]
        or not _valid_interval(value["calibrated_center_offset_ratio"])
        or not _valid_interval(value["calibrated_center_offset_px"])
    ):
        raise ValueError(
            "enclosing-support aperture calibration provenance is invalid"
        )
    if value["state"] == "supported":
        if (
            not _valid_interval(value["effective_center_offset_px"])
            or value["failure_kind"] is not None
            or value["failure_detail"] is not None
        ):
            raise ValueError(
                "supported enclosing-support aperture authority is invalid"
            )
    elif (
        value["effective_center_offset_px"] is not None
        or value["failure_kind"]
        != "enclosing_support_aperture_center_conflict"
        or not isinstance(value["failure_detail"], str)
        or not value["failure_detail"]
    ):
        raise ValueError(
            "contradicted enclosing-support aperture authority is invalid"
        )


def _interval_contains(
    interval: object,
    value: object,
    *,
    epsilon: float = 1.0e-9,
) -> bool:
    return (
        _valid_interval(interval)
        and _finite_number(value)
        and float(interval["minimum"]) - epsilon
        <= float(value)
        <= float(interval["maximum"]) + epsilon
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
            or len(value["width_observation_ids"]) < 3
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


def _validate_adjacency_continuity(value: object) -> None:
    if not isinstance(value, list):
        raise ValueError("adjacency continuity summary is invalid")
    ordinals: list[int] = []
    for observation in value:
        if not isinstance(observation, dict) or set(observation) != {
            "observation_id",
            "relation_ordinal",
            "state",
            "kind",
            "basis",
            "required_interval_px",
            "covering_query_ids",
            "end_observation_id",
            "next_start_observation_id",
            "separator_band_observation_ids",
            "contact_observation_id",
            "overlap_observation_id",
            "signed_gap_interval_px",
            "failure_kind",
            "reason",
        }:
            raise ValueError("adjacency continuity item is invalid")
        ordinal = observation["relation_ordinal"]
        state = observation["state"]
        kind = observation["kind"]
        basis = observation["basis"]
        end_id = observation["end_observation_id"]
        start_id = observation["next_start_observation_id"]
        separator_band_ids = observation["separator_band_observation_ids"]
        contact_id = observation["contact_observation_id"]
        overlap_id = observation["overlap_observation_id"]
        signed_gap = observation["signed_gap_interval_px"]
        failure_kind = observation["failure_kind"]
        reason = observation["reason"]
        if (
            not isinstance(observation["observation_id"], str)
            or not observation["observation_id"]
            or not isinstance(ordinal, int)
            or ordinal <= 0
            or state not in {"supported", "contradicted", "unavailable"}
            or kind
            not in {
                "separator_material",
                "contact",
                "overlap",
                "no_counterevidence_observed",
                "separator_material_unresolved",
                "unresolved",
                "coverage_incomplete",
            }
            or basis
            not in {
                None,
                "positive_separator_band",
                "shared_physical_edge",
                "independent_reversed_edges",
                "complete_registered_corridor",
            }
            or not _valid_interval(observation["required_interval_px"])
            or not _valid_ids(observation["covering_query_ids"])
            or observation["covering_query_ids"]
            != sorted(observation["covering_query_ids"])
            or any(
                item is not None
                and (not isinstance(item, str) or not item)
                for item in (end_id, start_id)
            )
            or not _valid_ids(separator_band_ids)
            or separator_band_ids != sorted(separator_band_ids)
            or contact_id is not None
            and (not isinstance(contact_id, str) or not contact_id)
            or overlap_id is not None
            and (not isinstance(overlap_id, str) or not overlap_id)
            or signed_gap is not None
            and not _valid_interval(signed_gap)
            or failure_kind
            not in {
                None,
                "multiple_separator_bands",
                "separator_material_unresolved",
                "separator_role_conflict",
                "signed_gap_crosses_zero",
                "overlap_observation_unavailable",
                "registered_coverage_incomplete",
            }
            or reason is not None
            and (not isinstance(reason, str) or not reason)
        ):
            raise ValueError("adjacency continuity item is invalid")
        ordinals.append(ordinal)
        failed = kind in {
            "separator_material_unresolved",
            "unresolved",
            "coverage_incomplete",
        }
        if (
            (
                kind
                in {
                    "separator_material",
                    "contact",
                    "overlap",
                    "no_counterevidence_observed",
                }
            )
            != (state == "supported")
            or state == "contradicted"
            or failed != (state == "unavailable")
            or failed != (failure_kind is not None and reason is not None)
            or (not failed) != (failure_kind is None and reason is None)
        ):
            raise ValueError("adjacency continuity state is inconsistent")
        allowed_failures = {
            "separator_material_unresolved": {
                "separator_material_unresolved",
            },
            "unresolved": {
                "multiple_separator_bands",
                "separator_role_conflict",
                "signed_gap_crosses_zero",
                "overlap_observation_unavailable",
            },
            "coverage_incomplete": {
                "registered_coverage_incomplete",
            },
        }
        if failed and failure_kind not in allowed_failures[kind]:
            raise ValueError("adjacency continuity failure kind is invalid")
        direct_pair = end_id is not None and start_id is not None
        if kind == "separator_material":
            if (
                basis != "positive_separator_band"
                or not direct_pair
                or len(separator_band_ids) != 1
                or signed_gap is None
                or float(signed_gap["minimum"]) <= 1.0e-7
            ):
                raise ValueError("separator continuity fact is incomplete")
        elif kind == "contact":
            if (
                basis != "shared_physical_edge"
                or not direct_pair
                or end_id != start_id
                or separator_band_ids
                or signed_gap != {"minimum": 0.0, "maximum": 0.0}
                or contact_id is None
            ):
                raise ValueError("contact continuity fact is incomplete")
        elif kind == "overlap":
            if (
                basis != "independent_reversed_edges"
                or not direct_pair
                or end_id == start_id
                or separator_band_ids
                or signed_gap is None
                or float(signed_gap["maximum"]) >= -1.0e-7
                or overlap_id is None
            ):
                raise ValueError("overlap continuity fact is incomplete")
        elif kind == "no_counterevidence_observed":
            if (
                basis != "complete_registered_corridor"
                or separator_band_ids
            ):
                raise ValueError("neutral continuity fact is invalid")
        elif basis is not None:
            raise ValueError("unresolved continuity cannot claim a basis")
        if kind != "contact" and contact_id is not None:
            raise ValueError("non-contact continuity retained contact evidence")
        if kind != "overlap" and overlap_id is not None:
            raise ValueError("non-overlap continuity retained overlap evidence")
        if kind == "separator_material_unresolved" and (
            not direct_pair
            or not separator_band_ids
            or signed_gap is None
        ):
            raise ValueError("unresolved material provenance is invalid")
        if failure_kind == "multiple_separator_bands" and (
            not direct_pair or len(separator_band_ids) < 2
        ):
            raise ValueError("multiple separator provenance is invalid")
        if failure_kind == "separator_role_conflict" and (
            not direct_pair
            or len(separator_band_ids) != 1
            or signed_gap is None
        ):
            raise ValueError("separator role-conflict provenance is invalid")
        if failure_kind == "signed_gap_crosses_zero" and (
            not direct_pair
            or separator_band_ids
            or signed_gap is None
            or float(signed_gap["minimum"]) > 1.0e-7
            or float(signed_gap["maximum"]) <= 1.0e-7
        ):
            raise ValueError("cross-zero gap provenance is invalid")
        if failure_kind == "overlap_observation_unavailable" and (
            not direct_pair
            or separator_band_ids
            or signed_gap is None
            or float(signed_gap["maximum"]) >= -1.0e-7
        ):
            raise ValueError("unregistered overlap provenance is invalid")
        if (
            failure_kind == "registered_coverage_incomplete"
            and separator_band_ids
        ):
            raise ValueError("incomplete coverage retained a material band")
    if ordinals != list(range(1, len(ordinals) + 1)):
        raise ValueError("adjacency continuity ordinals are invalid")


def _validate_adjacency_relations(
    value: object,
) -> dict[str, tuple[str, int]]:
    """Validate the serialized adjacency sum type and return topologies."""

    if not isinstance(value, list):
        raise ValueError("adjacency relation summary is invalid")
    ordinals: list[int] = []
    topologies: dict[str, tuple[str, int]] = {}
    separator_fields = {
        "relation_ordinal",
        "kind",
        "delta_interval_px",
        "canonical_delta_px",
        "separator_band_observation_id",
        "end_edge_observation_id",
        "next_start_edge_observation_id",
        "signed_gap_interval_px",
        "canonical_signed_gap_px",
    }
    contact_fields = {
        "relation_ordinal",
        "contact_observation_id",
        "physical_edge_id",
        "shared_edge_observation_id",
        "delta_interval_px",
        "canonical_delta_px",
        "supporting_observation_ids",
        "kind",
    }
    overlap_fields = {
        "relation_ordinal",
        "overlap_observation_id",
        "end_edge_observation_id",
        "next_start_edge_observation_id",
        "signed_gap_interval_px",
        "canonical_signed_gap_px",
        "delta_interval_px",
        "canonical_delta_px",
        "supporting_observation_ids",
        "kind",
    }
    for relation in value:
        if not isinstance(relation, dict):
            raise ValueError("adjacency relation is invalid")
        fields = set(relation)
        ordinal = relation.get("relation_ordinal")
        interval = relation.get("delta_interval_px")
        canonical = relation.get("canonical_delta_px")
        if (
            not isinstance(ordinal, int)
            or ordinal <= 0
            or not _valid_interval(interval)
            or not _interval_contains(interval, canonical)
        ):
            raise ValueError("adjacency relation geometry is invalid")
        ordinals.append(ordinal)
        if fields == separator_fields:
            kind = relation["kind"]
            direct_ids = (
                relation["separator_band_observation_id"],
                relation["end_edge_observation_id"],
                relation["next_start_edge_observation_id"],
            )
            signed_gap = relation["signed_gap_interval_px"]
            canonical_signed_gap = relation["canonical_signed_gap_px"]
            if (
                kind not in {"nominal", "normal", "wide", "narrow"}
                or (kind == "nominal")
                != (
                    interval == {"minimum": 0.0, "maximum": 0.0}
                    and float(canonical) == 0.0
                    and all(identity is None for identity in direct_ids)
                    and signed_gap is None
                    and canonical_signed_gap is None
                )
                or (
                    kind != "nominal"
                    and (
                        any(
                            not isinstance(identity, str) or not identity
                            for identity in direct_ids
                        )
                        or len(set(direct_ids)) != len(direct_ids)
                        or not _valid_interval(signed_gap)
                        or float(signed_gap["minimum"]) <= 0.0
                        or not _interval_contains(
                            signed_gap,
                            canonical_signed_gap,
                        )
                        or (
                            kind == "normal"
                            and abs(float(canonical)) > 1.0e-9
                        )
                        or (kind == "wide" and float(canonical) <= 0.0)
                        or (kind == "narrow" and float(canonical) >= 0.0)
                    )
                )
            ):
                raise ValueError("separator relation is invalid")
            continue
        if fields == contact_fields and relation["kind"] == "contact":
            contact_id = relation["contact_observation_id"]
            physical_id = relation["physical_edge_id"]
            shared_id = relation["shared_edge_observation_id"]
            supporting_ids = relation["supporting_observation_ids"]
            if (
                any(
                    not isinstance(identity, str) or not identity
                    for identity in (contact_id, physical_id, shared_id)
                )
                or physical_id != shared_id
                or not _valid_ids(supporting_ids, allow_empty=False)
                or supporting_ids != list(dict.fromkeys(supporting_ids))
                or physical_id not in supporting_ids
                or contact_id in topologies
            ):
                raise ValueError("contact relation is invalid")
            topologies[contact_id] = ("contact", ordinal)
            continue
        if fields != overlap_fields or relation["kind"] != "overlap":
            raise ValueError("adjacency relation sum type is invalid")
        overlap_id = relation["overlap_observation_id"]
        end_id = relation["end_edge_observation_id"]
        start_id = relation["next_start_edge_observation_id"]
        signed_gap = relation["signed_gap_interval_px"]
        canonical_signed_gap = relation["canonical_signed_gap_px"]
        supporting_ids = relation["supporting_observation_ids"]
        if (
            any(
                not isinstance(identity, str) or not identity
                for identity in (overlap_id, end_id, start_id)
            )
            or end_id == start_id
            or overlap_id in topologies
            or not _valid_interval(signed_gap)
            or float(signed_gap["maximum"]) >= 0.0
            or not _interval_contains(signed_gap, canonical_signed_gap)
            or supporting_ids != [end_id, start_id]
        ):
            raise ValueError("overlap relation is invalid")
        topologies[overlap_id] = ("overlap", ordinal)
    if ordinals != list(range(1, len(ordinals) + 1)):
        raise ValueError("adjacency relation ordinals are invalid")
    return topologies


def _validate_contact_edge_observations(value: object) -> dict[str, str]:
    """Validate role-free contact proposals without granting placement."""

    if not isinstance(value, list):
        raise ValueError("contact-edge observation summary is invalid")
    observations: dict[str, str] = {}
    fields = {
        "observation_id",
        "physical_edge_id",
        "shared_edge_observation_id",
        "authority_bases",
        "qualified_anchor_roles",
    }
    for observation in value:
        if not isinstance(observation, dict) or set(observation) != fields:
            raise ValueError("contact-edge observation is invalid")
        identity = observation["observation_id"]
        physical_id = observation["physical_edge_id"]
        shared_id = observation["shared_edge_observation_id"]
        bases = observation["authority_bases"]
        roles = observation["qualified_anchor_roles"]
        if (
            any(
                not isinstance(item, str) or not item
                for item in (identity, physical_id, shared_id)
            )
            or physical_id != shared_id
            or identity in observations
            or not isinstance(bases, list)
            or not bases
            or bases != list(dict.fromkeys(bases))
            or any(
                item not in {"source_wide_edge", "aggregate_union"}
                for item in bases
            )
            or not isinstance(roles, list)
            or not roles
            or roles != list(dict.fromkeys(roles))
            or any(item not in {"start", "end"} for item in roles)
        ):
            raise ValueError("contact-edge observation is invalid")
        observations[identity] = shared_id
    return observations


def _validate_overlap_edge_pair_observations(
    value: object,
) -> dict[str, tuple[str, str]]:
    """Validate ordinal-free overlap proposals without granting placement."""

    if not isinstance(value, list):
        raise ValueError("overlap edge-pair observation summary is invalid")
    observations: dict[str, tuple[str, str]] = {}
    fields = {
        "observation_id",
        "end_edge_observation_id",
        "next_start_edge_observation_id",
        "signed_gap_interval_px",
        "canonical_signed_gap_px",
        "end_authority_bases",
        "next_start_authority_bases",
    }
    for observation in value:
        if not isinstance(observation, dict) or set(observation) != fields:
            raise ValueError("overlap edge-pair observation is invalid")
        identity = observation["observation_id"]
        end_id = observation["end_edge_observation_id"]
        start_id = observation["next_start_edge_observation_id"]
        signed_gap = observation["signed_gap_interval_px"]
        canonical = observation["canonical_signed_gap_px"]
        bases = (
            observation["end_authority_bases"],
            observation["next_start_authority_bases"],
        )
        if (
            any(
                not isinstance(item, str) or not item
                for item in (identity, end_id, start_id)
            )
            or identity in observations
            or end_id == start_id
            or not _valid_interval(signed_gap)
            or float(signed_gap["maximum"]) >= -1.0e-7
            or not _finite_number(canonical)
            or not float(signed_gap["minimum"])
            <= float(canonical)
            <= float(signed_gap["maximum"])
            or any(
                not isinstance(items, list)
                or not items
                or items != list(dict.fromkeys(items))
                or any(
                    item not in {"source_wide_edge", "aggregate_union"}
                    for item in items
                )
                for items in bases
            )
        ):
            raise ValueError("overlap edge-pair observation is invalid")
        observations[identity] = (end_id, start_id)
    return observations


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
        "authority_id",
        "authority_basis",
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
    authority_basis = value["authority_basis"]
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
            not isinstance(value["authority_id"], str)
            or not value["authority_id"]
            or authority_basis
            not in {
                "independent_complete_frames",
                "direct_lattice_closure",
                "reconciled_direct_constraints",
            }
            or (
                authority_basis == "independent_complete_frames"
                and (len(supporting) < 2 or len(observation_ids) < 4)
            )
            or (
                authority_basis == "reconciled_direct_constraints"
                and (len(supporting) < 2 or len(observation_ids) < 4)
            )
            or (
                authority_basis == "direct_lattice_closure"
                and len(observation_ids) < 3
            )
            or not _valid_interval(width)
            or not _finite_number(canonical)
            or float(canonical) < float(width["minimum"]) - 1.0e-9
            or float(canonical) > float(width["maximum"]) + 1.0e-9
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
        or value["authority_id"] is not None
        or authority_basis is not None
        or value["failure_kind"]
        not in {
            "complete_frame_unobserved",
            "common_width_authority_unavailable",
            "direct_lattice_counterevidence",
        }
    ):
        raise ValueError("unavailable Frame width inference is invalid")


def _validate_source_frame_width_authority(value: object) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != _SOURCE_FRAME_WIDTH_AUTHORITY_FIELDS
        or not isinstance(value["authority_id"], str)
        or not value["authority_id"]
    ):
        raise ValueError("source Frame-width authority summary is invalid")
    state = value["state"]
    phase_anchor_ids = value["selected_phase_anchor_observation_ids"]
    supporting_role_ids = value["supporting_role_observation_ids"]
    basis = value["basis"]
    supporting = value["supporting_frame_ordinals"]
    constraint_ids = value["supporting_constraint_ids"]
    observation_ids = value["observation_ids"]
    if (
        state not in {"supported", "unavailable", "contradicted"}
        or not isinstance(phase_anchor_ids, list)
        or not isinstance(supporting_role_ids, list)
        or len(supporting_role_ids) != len(phase_anchor_ids)
        or any(
            identity is not None
            and (not isinstance(identity, str) or not identity)
            for identity in (*phase_anchor_ids, *supporting_role_ids)
        )
        or not isinstance(supporting, list)
        or supporting != sorted(set(supporting))
        or any(
            not isinstance(ordinal, int) or ordinal <= 0
            for ordinal in supporting
        )
        or not isinstance(constraint_ids, list)
        or constraint_ids != sorted(set(constraint_ids))
        or any(
            not isinstance(identity, str) or not identity
            for identity in constraint_ids
        )
        or not _valid_ids(observation_ids)
        or observation_ids != sorted(observation_ids)
    ):
        raise ValueError("source Frame-width authority ledger is invalid")
    supported = state == "supported"
    width = value["width_px"]
    canonical = value["canonical_width_px"]
    if supported:
        if (
            not isinstance(value["selected_integer_slot_offset"], int)
            or not phase_anchor_ids
            or not any(phase_anchor_ids)
            or not any(supporting_role_ids)
            or {
                identity
                for identity in supporting_role_ids
                if identity is not None
            }
            != set(observation_ids)
            or basis
            not in {
                "independent_complete_frames",
                "direct_lattice_closure",
                "reconciled_direct_constraints",
            }
            or (
                basis == "independent_complete_frames"
                and (
                    len(supporting) < 2
                    or constraint_ids
                    or len(observation_ids) < 4
                )
            )
            or (
                basis == "reconciled_direct_constraints"
                and (
                    len(supporting) < 2
                    or len(constraint_ids) < 3
                    or len(observation_ids) < 4
                )
            )
            or (
                basis == "direct_lattice_closure"
                and (
                    supporting
                    or len(constraint_ids) < 3
                    or len(observation_ids) < 3
                )
            )
            or not _valid_interval(width)
            or float(width["minimum"]) <= 0.0
            or not _finite_number(canonical)
            or float(canonical) < float(width["minimum"]) - 1.0e-9
            or float(canonical) > float(width["maximum"]) + 1.0e-9
            or value["failure_kind"] is not None
            or value["reason"] is not None
        ):
            raise ValueError("supported source Frame-width authority is invalid")
        return
    if (
        value["selected_integer_slot_offset"] is not None
        or phase_anchor_ids
        or supporting_role_ids
        or basis is not None
        or supporting
        or constraint_ids
        or width is not None
        or canonical is not None
        or observation_ids
        or value["failure_kind"] not in _SOURCE_FRAME_WIDTH_FAILURE_KINDS
        or not isinstance(value["reason"], str)
        or not value["reason"]
    ):
        raise ValueError("failed source Frame-width authority is invalid")


def _validate_source_frame_width_topology_assessment(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "source_frame_width_authority_id",
        "state",
        "facts",
        "failure_kind",
        "reason",
    }:
        raise ValueError("source-W topology assessment schema is invalid")
    authority_id = value["source_frame_width_authority_id"]
    facts = value["facts"]
    if (
        not isinstance(authority_id, str)
        or not authority_id
        or not isinstance(facts, list)
    ):
        raise ValueError("source-W topology assessment ledger is invalid")
    states: list[str] = []
    ordinals: list[int] = []
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != {
            "relation_ordinal",
            "inferred_role_indices",
            "signed_gap_interval_px",
            "canonical_signed_gap_px",
            "state",
        }:
            raise ValueError("source-W topology fact schema is invalid")
        ordinal = fact["relation_ordinal"]
        inferred = fact["inferred_role_indices"]
        interval = fact["signed_gap_interval_px"]
        canonical = fact["canonical_signed_gap_px"]
        if (
            not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or ordinal <= 0
            or not isinstance(inferred, list)
            or not inferred
            or inferred != sorted(set(inferred))
            or any(
                not isinstance(index, int)
                or isinstance(index, bool)
                or index not in {2 * ordinal - 1, 2 * ordinal}
                for index in inferred
            )
            or not _valid_interval(interval)
            or not _finite_number(canonical)
            or float(canonical) < float(interval["minimum"]) - 1.0e-9
            or float(canonical) > float(interval["maximum"]) + 1.0e-9
        ):
            raise ValueError("source-W topology fact geometry is invalid")
        expected_state = (
            "supported"
            if float(interval["minimum"]) >= -1.0e-9
            else "contradicted"
            if float(interval["maximum"]) < -1.0e-9
            else "unavailable"
        )
        if fact["state"] != expected_state:
            raise ValueError("source-W topology fact state is invalid")
        ordinals.append(ordinal)
        states.append(expected_state)
    if ordinals != sorted(set(ordinals)):
        raise ValueError("source-W topology facts are not canonical")
    expected_state = (
        "contradicted"
        if "contradicted" in states
        else "unavailable"
        if "unavailable" in states
        else "supported"
    )
    expected_failure = (
        "normal_adjacency_contradicted"
        if expected_state == "contradicted"
        else "normal_adjacency_unresolved"
        if expected_state == "unavailable"
        else None
    )
    if (
        value["state"] != expected_state
        or value["failure_kind"] != expected_failure
        or (expected_state == "supported") != (value["reason"] is None)
        or value["reason"] is not None
        and (
            not isinstance(value["reason"], str)
            or not value["reason"]
        )
    ):
        raise ValueError("source-W topology assessment state is invalid")


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
        "aggregate_union",
        "separator_pair",
        "partial_height_separator_pair",
    }
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != {
            "role_index",
            "lane_ordinal",
            "role",
            "observation_id",
            "evidence_group_id",
            "independent_support_region_count",
            "bases",
            "blocking_material_conflict_ids",
            "state",
            "trace_coordinates_px",
        }:
            raise ValueError("direct-role authority fact is invalid")
        index = fact["role_index"]
        bases = fact["bases"]
        conflicts = fact["blocking_material_conflict_ids"]
        traces = fact["trace_coordinates_px"]
        supported = fact["state"] == "supported"
        conflict = fact["state"] == "contradicted"
        if (
            not isinstance(index, int)
            or index < 0
            or fact["lane_ordinal"] != index // 2 + 1
            or fact["role"] != ("start" if index % 2 == 0 else "end")
            or not isinstance(fact["observation_id"], str)
            or not fact["observation_id"]
            or not isinstance(fact["evidence_group_id"], str)
            or not fact["evidence_group_id"]
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
            or not isinstance(traces, list)
            or traces != sorted(set(traces))
            or any(not isinstance(item, int) for item in traces)
            or (
                "partial_height_separator_pair" in bases
                and not traces
            )
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


def _validate_direct_role_aperture_domain_authority(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "state",
        "facts",
        "unsupported_role_indices",
        "reason",
    }:
        raise ValueError("direct-role aperture-domain authority is invalid")
    facts = value["facts"]
    unsupported = value["unsupported_role_indices"]
    if not isinstance(facts, list) or not facts or not isinstance(unsupported, list):
        raise ValueError("direct-role aperture-domain ledger is invalid")
    indices: list[int] = []
    blocked: list[int] = []
    contradicted = False
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != {
            "role_index",
            "observation_id",
            "role_position_interval_px",
            "support_trace_interval_px",
            "guaranteed_aperture_interval_px",
            "basis",
            "cross_observation_ids",
            "state",
            "failure_kind",
        }:
            raise ValueError("direct-role aperture-domain fact is invalid")
        index = fact["role_index"]
        state = fact["state"]
        basis = fact["basis"]
        failure = fact["failure_kind"]
        domain = fact["guaranteed_aperture_interval_px"]
        trace = fact["support_trace_interval_px"]
        cross_ids = fact["cross_observation_ids"]
        contained = (
            _valid_interval(domain)
            and _valid_interval(trace)
            and float(domain["minimum"]) <= float(trace["minimum"])
            and float(trace["maximum"]) <= float(domain["maximum"])
        )
        has_cross_domain = basis is not None and _valid_ids(
            cross_ids,
            allow_empty=False,
        )
        collapsed = failure == "aperture_domain_collapsed"
        outside = failure == "support_outside_aperture_domain"
        if (
            not isinstance(index, int)
            or index < 0
            or not isinstance(fact["observation_id"], str)
            or not fact["observation_id"]
            or not _valid_interval(fact["role_position_interval_px"])
            or not _valid_interval(trace)
            or domain is not None and not _valid_interval(domain)
            or basis not in {
                None,
                "direct_aperture_pair",
                "enclosing_support_aperture",
            }
            or not _valid_ids(cross_ids)
            or state not in {"supported", "contradicted", "unavailable"}
            or failure
            not in {
                None,
                "two_sided_cross_domain_unavailable",
                "aperture_domain_collapsed",
                "support_outside_aperture_domain",
            }
            or (state == "supported")
            != (
                has_cross_domain
                and failure is None
                and contained
            )
            or (state == "contradicted")
            != (
                has_cross_domain
                and (
                    (collapsed and domain is None)
                    or (
                        outside
                        and domain is not None
                        and not contained
                    )
                )
            )
            or (state == "unavailable")
            != (
                basis is None
                and domain is None
                and failure == "two_sided_cross_domain_unavailable"
            )
        ):
            raise ValueError("direct-role aperture-domain fact is invalid")
        indices.append(index)
        if state != "supported":
            blocked.append(index)
        contradicted = contradicted or state == "contradicted"
    expected = (
        "contradicted" if contradicted else "unavailable" if blocked else "supported"
    )
    if (
        indices != sorted(set(indices))
        or unsupported != blocked
        or value["state"] != expected
        or (expected == "supported") != (value["reason"] is None)
        or value["reason"] is not None
        and (not isinstance(value["reason"], str) or not value["reason"])
    ):
        raise ValueError("direct-role aperture-domain authority is invalid")


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
    aperture_risk = output.get("enclosing_support_aperture_risk")
    protections = output.get("boundary_protections")
    protection_fields = {
        "role",
        "measurement_expansion_px",
        "base_bleed_px",
        "topology_protection_px",
        "topology_relation_id",
        "local_boundary_residual_px",
        "joint_expansion_px",
    }
    if not isinstance(protections, list) or any(
        not isinstance(item, dict) for item in protections
    ):
        raise ValueError("boundary protection facts are invalid")
    support_output = boundary_use == "enclosing_support_pair"
    risk_fields = {
        "aperture_authority_id",
        "aperture_authority_state",
        "canonical_height_px",
        "center_offset_interval_px",
        "maximum_center_shift_px",
        "top_expansion_px",
        "bottom_expansion_px",
        "feasible_state_count",
    }
    if support_output:
        if (
            not isinstance(aperture_risk, dict)
            or set(aperture_risk) != risk_fields
            or any(
                not _finite_number(aperture_risk[key])
                or float(aperture_risk[key]) < 0.0
                for key in (
                    "maximum_center_shift_px",
                    "top_expansion_px",
                    "bottom_expansion_px",
                )
            )
            or not _finite_number(aperture_risk["canonical_height_px"])
            or float(aperture_risk["canonical_height_px"]) <= 0.0
            or not isinstance(aperture_risk["aperture_authority_id"], str)
            or not aperture_risk["aperture_authority_id"]
            or aperture_risk["aperture_authority_state"]
            not in {"supported", "unavailable", "contradicted"}
            or not _valid_interval(
                aperture_risk["center_offset_interval_px"]
            )
            or not isinstance(aperture_risk["feasible_state_count"], int)
            or aperture_risk["feasible_state_count"] <= 0
        ):
            raise ValueError("enclosing-support aperture risk is invalid")
        center_interval = aperture_risk["center_offset_interval_px"]
        expected_shift = max(
            abs(float(center_interval["minimum"])),
            abs(float(center_interval["maximum"])),
        )
        if (
            abs(
                float(aperture_risk["maximum_center_shift_px"])
                - expected_shift
            )
            > 1.0e-8
        ):
            raise ValueError(
                "enclosing-support aperture center risk is inconsistent"
            )
    elif aperture_risk is not None:
        raise ValueError("aperture output carries enclosing-support risk")
    if (
        tuple(item.get("role") for item in protections)
        != ("start", "end", "top", "bottom")
        or any(
            set(item) != protection_fields
            or any(
                not _finite_number(item[key]) or float(item[key]) < 0.0
                for key in (
                    "measurement_expansion_px",
                    "base_bleed_px",
                    "topology_protection_px",
                    "local_boundary_residual_px",
                    "joint_expansion_px",
                )
            )
            or (float(item["topology_protection_px"]) > 0.0)
            != (
                isinstance(item["topology_relation_id"], str)
                and bool(item["topology_relation_id"])
            )
            or item["topology_relation_id"] is not None
            and item["role"] not in {"start", "end"}
            or item["topology_relation_id"] is not None
            and abs(
                float(item["topology_protection_px"])
                - float(item["base_bleed_px"])
            )
            > 1.0e-8
            for item in protections
        )
    ):
        raise ValueError("boundary protection facts are invalid")
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


def _valid_failure(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == _FAILURE_FIELDS
        and all(isinstance(value.get(key), str) and value.get(key) for key in value)
    )


def _validate_placement_proposal(
    value: object,
    *,
    lane_id: str,
) -> list[dict[str, Any]]:
    if (
        not isinstance(value, dict)
        or set(value) != _PLACEMENT_PROPOSAL_FIELDS
        or value["lane_id"] != lane_id
        or value["state"] not in {"generated", "unavailable"}
        or not isinstance(value["output_footprints"], list)
        or value["placement_id"] is not None
        and (
            not isinstance(value["placement_id"], str)
            or not value["placement_id"]
        )
    ):
        raise ValueError("placement proposal summary is invalid")
    outputs = value["output_footprints"]
    generated = value["state"] == "generated"
    if generated != bool(value["placement_id"] and outputs) or (
        generated and value["failure"] is not None
    ) or (not generated and (outputs or not _valid_failure(value["failure"]))):
        raise ValueError("placement proposal state is inconsistent")
    for output in outputs:
        validate_output_footprint_authority(output)
        envelope = output.get("envelope", {})
        if (
            envelope.get("lane_id") != lane_id
            or envelope.get("placement_id") != value["placement_id"]
        ):
            raise ValueError("proposal output identity is inconsistent")
    if generated and tuple(
        output["envelope"]["lane_ordinal"] for output in outputs
    ) != tuple(range(1, len(outputs) + 1)):
        raise ValueError("proposal outputs do not cover contiguous lane slots")
    return outputs


def _validate_source_proposal(value: object) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value) != _SOURCE_PROPOSAL_FIELDS
        or value["state"] not in {"generated", "unavailable"}
        or not isinstance(value["lane_ids"], list)
        or len(set(value["lane_ids"])) != len(value["lane_ids"])
        or any(not isinstance(item, str) or not item for item in value["lane_ids"])
        or not isinstance(value["placement_ids"], list)
        or len(value["placement_ids"]) != len(value["lane_ids"])
        or any(
            item is not None and (not isinstance(item, str) or not item)
            for item in value["placement_ids"]
        )
    ):
        raise ValueError("source proposal summary is invalid")
    generated = value["state"] == "generated"
    if (
        generated
        and (
            not value["lane_ids"]
            or not all(value["placement_ids"])
            or value["failure"] is not None
        )
    ) or (
        not generated and not _valid_failure(value["failure"])
    ):
        raise ValueError("source proposal state is inconsistent")
    return value


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
    source_proposal = _validate_source_proposal(
        geometry.get("source_placement_proposal")
    )
    source_selection = geometry.get("source_placement_selection")
    if (
        not isinstance(source_selection, dict)
        or set(source_selection)
        != {
            "state",
            "failure",
            "selected_placement_ids",
            "runner_up_placement_ids",
        }
        or source_selection["state"] not in {"supported", "unavailable"}
        or not isinstance(source_selection["selected_placement_ids"], list)
        or not isinstance(source_selection["runner_up_placement_ids"], list)
        or len(source_selection["selected_placement_ids"])
        != len(source_selection["runner_up_placement_ids"])
    ):
        raise ValueError("source placement selection is invalid")
    source_selected = source_selection["state"] == "supported"
    if (
        source_selected
        and (
            not source_selection["selected_placement_ids"]
            or not all(source_selection["selected_placement_ids"])
            or source_selection["failure"] is not None
        )
    ) or (
        not source_selected
        and (
            any(source_selection["selected_placement_ids"])
            or not _valid_failure(source_selection["failure"])
        )
    ):
        raise ValueError("source placement selection state is inconsistent")
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
    lane_ids: list[str] = []
    lane_proposal_ids: list[str | None] = []
    lane_selected_ids: list[str | None] = []
    for lane in geometry["lanes"]:
        lane_id = lane.get("lane_id")
        if not isinstance(lane_id, str) or not lane_id:
            raise ValueError("source lane identity is invalid")
        proposal_outputs = _validate_placement_proposal(
            lane.get("placement_proposal"),
            lane_id=lane_id,
        )
        proposal = lane["placement_proposal"]
        lane_ids.append(lane_id)
        lane_proposal_ids.append(
            proposal["placement_id"]
            if proposal["state"] == "generated"
            else None
        )
        outputs = lane["output_footprints"]
        budgets = lane["direct_use_budget_assessments"]
        outputs_by_id = {item["geometry_id"]: item for item in outputs}
        alignment = lane.get("template_alignment")
        contact_edge_observations = _validate_contact_edge_observations(
            lane.get("contact_edge_observations")
        )
        overlap_edge_pair_observations = (
            _validate_overlap_edge_pair_observations(
                lane.get("overlap_edge_pair_observations")
            )
        )
        coarse = lane.get("coarse_strip_support")
        aspect_ratio = lane.get("aperture_aspect_ratio_authority")
        _validate_aperture_aspect_ratio_authority(aspect_ratio)
        enclosing_aperture = lane.get(
            "enclosing_support_aperture_authority"
        )
        _validate_enclosing_support_aperture_authority(enclosing_aperture)
        source_width = lane.get("source_frame_width_authority")
        _validate_source_frame_width_authority(source_width)
        source_width_topology = lane.get(
            "source_frame_width_topology_assessment"
        )
        _validate_source_frame_width_topology_assessment(
            source_width_topology
        )
        if (
            (source_width["state"] == "supported")
            != isinstance(source_width_topology, dict)
            or isinstance(source_width_topology, dict)
            and source_width_topology["source_frame_width_authority_id"]
            != source_width["authority_id"]
        ):
            raise ValueError(
                "source W and its topology assessment disagree"
            )
        if (
            aspect_ratio["calibration_id"] is not None
            and aspect_ratio["width_observation_ids"]
            != source_width["observation_ids"]
        ):
            raise ValueError(
                "aspect ratio and canonical source W authority disagree"
            )
        support_output = (
            lane.get("selected_cross_boundary_use")
            == "enclosing_support_pair"
        )
        if support_output == (
            enclosing_aperture["state"] == "not_applicable"
        ):
            raise ValueError(
                "selected cross and enclosing aperture authority disagree"
            )
        for output in outputs:
            aperture_risk = output.get(
                "enclosing_support_aperture_risk"
            )
            if aperture_risk is not None and (
                aperture_risk["aperture_authority_id"]
                != enclosing_aperture["authority_id"]
                or aperture_risk["aperture_authority_state"]
                != enclosing_aperture["state"]
            ):
                raise ValueError(
                    "output changed enclosing-support aperture authority"
                )
        _validate_direct_role_aperture_domain_authority(
            lane.get("direct_role_aperture_domain_authority")
        )
        source_geometry = lane.get("source_scan_geometry")
        width_state = (
            None
            if not isinstance(source_geometry, dict)
            else source_geometry.get("width_state")
        )
        width_ids = (
            None
            if not isinstance(width_state, dict)
            else width_state.get("observation_ids")
        )
        phase_status = lane.get("phase_status")
        phase_failure_kind = lane.get("phase_failure_kind")
        phase_failure_reason = lane.get("phase_failure_reason")
        phase_retained_proposal_basis = lane.get(
            "phase_retained_proposal_basis"
        )
        if (
            phase_status not in _PHASE_STATUSES
            or phase_failure_kind not in _PHASE_FAILURE_KINDS
            or (phase_status == PhaseFitStatus.RESOLVED.value)
            != (
                phase_failure_kind is None
                and phase_failure_reason is None
            )
            or phase_failure_reason is not None
            and (
                not isinstance(phase_failure_reason, str)
                or not phase_failure_reason
            )
            or phase_retained_proposal_basis is not None
            and (
                # A complete long-axis proposal may remain visible while an
                # independent cross-axis gap keeps the source proposal absent.
                phase_retained_proposal_basis
                not in _PHASE_RETAINED_PROPOSAL_BASES
                or phase_status == PhaseFitStatus.RESOLVED.value
            )
        ):
            raise ValueError("phase status is invalid")
        if (
            not isinstance(width_ids, list)
            or (source_width["state"] == "supported") != bool(width_ids)
            or source_width["state"] == "supported"
            and source_width["observation_ids"] != width_ids
        ):
            raise ValueError("source geometry and source W authority disagree")
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
            not in {"normal", "measured_relations", "unresolved"}
            or alignment["path"]
            != (
                "retained_pre_local_phase_proposal"
                if phase_retained_proposal_basis is not None
                else {
                    "normal": "normal",
                    "measured_relations": "adjacency_relations",
                    "unresolved": None,
                }[alignment["pattern"]]
            )
            or phase_retained_proposal_basis is not None
            and alignment["pattern"] != "unresolved"
            or (alignment["pattern"] == "unresolved")
            != (alignment["unresolved_reason"] is not None)
            or "direct_role_aperture_domain_authority" not in lane
            or lane.get("selected_cross_boundary_use")
            not in {None, "aperture_pair", "enclosing_support_pair"}
        ):
            raise ValueError("template alignment summary is invalid")
        _validate_global_lattice_authority(
            alignment["global_lattice_authority"]
        )
        _validate_nominal_grid_evidence(
            alignment["calibrated_nominal_grid_evidence"]
        )
        _validate_adjacency_coverage(
            alignment["adjacency_observation_coverage"]
        )
        _validate_adjacency_continuity(
            alignment["adjacency_continuity_observations"]
        )
        topology_relations = _validate_adjacency_relations(
            alignment["adjacency_relations"]
        )
        contact_relations = {
            identity: ordinal
            for identity, (kind, ordinal) in topology_relations.items()
            if kind == "contact"
        }
        overlap_relations = {
            identity: ordinal
            for identity, (kind, ordinal) in topology_relations.items()
            if kind == "overlap"
        }
        if not set(contact_relations).issubset(contact_edge_observations):
            raise ValueError(
                "contact relation leaves the registered contact observations"
            )
        for relation in alignment["adjacency_relations"]:
            if relation["kind"] != "contact":
                continue
            if contact_edge_observations[
                relation["contact_observation_id"]
            ] != relation["shared_edge_observation_id"]:
                raise ValueError(
                    "contact relation changed its registered physical edge"
                )
        if not set(overlap_relations).issubset(
            overlap_edge_pair_observations
        ):
            raise ValueError(
                "overlap relation leaves the registered overlap observations"
            )
        for relation in alignment["adjacency_relations"]:
            if relation["kind"] != "overlap":
                continue
            if overlap_edge_pair_observations[
                relation["overlap_observation_id"]
            ] != (
                relation["end_edge_observation_id"],
                relation["next_start_edge_observation_id"],
            ):
                raise ValueError(
                    "overlap relation changed its registered reversed edges"
                )
        if [
            item["relation_ordinal"]
            for item in alignment["adjacency_observation_coverage"]
        ] != [
            item["relation_ordinal"]
            for item in alignment["adjacency_continuity_observations"]
        ]:
            raise ValueError("adjacency coverage and continuity disagree")
        continuity_contacts = {
            item["contact_observation_id"]: (
                "contact",
                item["relation_ordinal"],
            )
            for item in alignment["adjacency_continuity_observations"]
            if item["kind"] == "contact"
        }
        continuity_overlaps = {
            item["overlap_observation_id"]: (
                "overlap",
                item["relation_ordinal"],
            )
            for item in alignment["adjacency_continuity_observations"]
            if item["kind"] == "overlap"
        }
        if any(
            topology_relations.get(identity) != topology
            for identity, topology in {
                **continuity_contacts,
                **continuity_overlaps,
            }.items()
        ):
            raise ValueError(
                "topology continuity leaves the selected adjacency relation"
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
        _validate_nominal_grid_authority(
            lane.get("calibrated_nominal_grid_authority"),
            selected_placement_id=lane.get("selected_placement_id"),
            output_geometry_ids=set(outputs_by_id),
        )
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
                aperture_risk = output.get(
                    "enclosing_support_aperture_risk"
                )
                edge_by_role = {edge["role"]: edge for edge in edges}
                if (
                    not isinstance(aperture_risk, dict)
                    or abs(
                        float(edge_by_role["top"]["expansion_px"])
                        - float(aperture_risk["top_expansion_px"])
                    )
                    > 1.0e-8
                    or abs(
                        float(edge_by_role["bottom"]["expansion_px"])
                        - float(aperture_risk["bottom_expansion_px"])
                    )
                    > 1.0e-8
                ):
                    raise ValueError(
                        "enclosing-support aperture risk budget is invalid"
                    )
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
        protected_contact_sides = {
            (
                protection["topology_relation_id"],
                output["envelope"]["lane_ordinal"],
                protection["role"],
            )
            for output in outputs
            for protection in output["boundary_protections"]
            if protection["topology_relation_id"] is not None
        }
        expected_contact_sides = {
            (identity, ordinal, "end")
            for identity, ordinal in contact_relations.items()
        }.union(
            {
                (identity, ordinal + 1, "start")
                for identity, ordinal in contact_relations.items()
            }
        )
        if outputs and protected_contact_sides != expected_contact_sides:
            raise ValueError(
                "output topology protection disagrees with contact relations"
            )
        selected = lane["selected_placement_id"]
        if (selected is None) != (not outputs):
            raise ValueError("selected template output is incomplete")
        if selected is not None and (
            proposal["state"] != "generated"
            or proposal["placement_id"] != selected
            or proposal_outputs != outputs
        ):
            raise ValueError("selected output does not reuse the proposal")
        lane_selected_ids.append(selected)
        if not isinstance(lane.get("peak_temporary_bytes"), int) or lane[
            "peak_temporary_bytes"
        ] < 0:
            raise ValueError("template peak-memory fact is invalid")
    if (
        source_proposal["lane_ids"] != lane_ids
        or source_proposal["placement_ids"] != lane_proposal_ids
        or source_selection["selected_placement_ids"] != lane_selected_ids
        or len(source_selection["runner_up_placement_ids"]) != len(lane_ids)
        or source_selected
        and (
            source_proposal["state"] != "generated"
            or source_proposal["placement_ids"]
            != source_selection["selected_placement_ids"]
        )
    ):
        raise ValueError("proposal, eligibility, and source selection disagree")


def _validate_phase_candidate_projection(
    value: object,
    fit: object,
) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "input_direct_role_authority",
        "outcome",
        "basis",
        "projected_out_bindings",
        "retained_direct_constraint_rank",
        "reason",
    }:
        raise ValueError("phase-candidate projection schema is invalid")
    authority = value["input_direct_role_authority"]
    _validate_direct_role_binding_authority(authority)
    assert isinstance(authority, dict)
    facts = authority["facts"]
    projected = value["projected_out_bindings"]
    if not isinstance(projected, list):
        raise ValueError("phase-candidate authority facts are invalid")
    assert isinstance(facts, list)
    projected_fields = {"role_index", "observation_id"}
    if any(
        not isinstance(item, dict) or set(item) != projected_fields
        for item in projected
    ):
        raise ValueError("phase-candidate projected binding schema is invalid")
    projected_pairs = tuple(
        (item["role_index"], item["observation_id"])
        for item in projected
    )
    if projected_pairs != tuple(sorted(set(projected_pairs))):
        raise ValueError("phase-candidate projected bindings are not canonical")
    unavailable_pairs = tuple(
        (item["role_index"], item["observation_id"])
        for item in facts
        if item["state"] == "unavailable"
    )
    outcome = value["outcome"]
    rank = value["retained_direct_constraint_rank"]
    reason = value["reason"]
    outcomes = {
        "unchanged",
        "direct_separator_refit",
        "projected",
        "calibrated_nominal_grid",
        "direct_role_contradiction",
        "topology_binding_unavailable",
        "calibrated_nominal_grid_unavailable",
        "calibrated_nominal_grid_conflict",
        "nominal_grid_phase_anchor_unavailable",
        "refit_unavailable",
        "discrete_identity_changed",
    }
    basis = value["basis"]
    expected_basis = {
        "unchanged": "direct_bindings",
        "direct_separator_refit": "direct_separator_gap",
        "projected": "direct_rank_three",
        "calibrated_nominal_grid": "calibrated_nominal_grid",
    }.get(outcome)
    state = authority["state"]
    state_matches_outcome = {
        "supported": outcome
        in {
            "unchanged",
            "direct_separator_refit",
            "calibrated_nominal_grid",
            "calibrated_nominal_grid_unavailable",
            "calibrated_nominal_grid_conflict",
            "nominal_grid_phase_anchor_unavailable",
            "topology_binding_unavailable",
            "refit_unavailable",
            "discrete_identity_changed",
        },
        "contradicted": outcome == "direct_role_contradiction",
        "unavailable": outcome
        not in {"unchanged", "direct_role_contradiction"},
    }[state]
    if (
        outcome not in outcomes
        or basis != expected_basis
        or not isinstance(rank, int)
        or isinstance(rank, bool)
        or not 0 <= rank <= 3
        or (
            outcome
            in {
                "unchanged",
                "direct_separator_refit",
                "projected",
                "calibrated_nominal_grid",
            }
        )
        != (reason is None)
        or reason is not None
        and (not isinstance(reason, str) or not reason)
        or not state_matches_outcome
        or (outcome == "projected" and rank != 3)
        or (
            authority["state"] == "unavailable"
            and projected_pairs != unavailable_pairs
        )
        or (authority["state"] != "unavailable" and projected_pairs)
    ):
        raise ValueError("phase-candidate projection contract is invalid")
    if fit is None or not isinstance(fit, dict):
        if outcome == "direct_role_contradiction":
            return
        raise ValueError("phase-candidate projection has no candidate")
    bindings = fit.get("role_bindings")
    if not isinstance(bindings, list):
        raise ValueError("phase-candidate binding ledger is invalid")
    if outcome in {
        "direct_separator_refit",
        "projected",
        "calibrated_nominal_grid",
    }:
        for role_index, observation_id in projected_pairs:
            if (
                not isinstance(role_index, int)
                or not 0 <= role_index < len(bindings)
                or bindings[role_index] is not None
                and bindings[role_index].get("use") == "phase_anchor"
            ):
                raise ValueError("projected binding still owns phase geometry")
        for fact in facts:
            if fact["state"] != "supported":
                continue
            role_index = fact["role_index"]
            if (
                not isinstance(role_index, int)
                or not 0 <= role_index < len(bindings)
                or not isinstance(bindings[role_index], dict)
                or bindings[role_index].get("use")
                not in {"phase_anchor", "local_refinement"}
                or bindings[role_index].get("observation_id")
                != fact["observation_id"]
            ):
                raise ValueError("retained direct role lost its native binding")


def _validate_phase_competition(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "template",
        "best",
        "runner_up",
        "status",
        "ambiguity_reason",
        "receipt",
        "registered_direct_observation_ids",
        "failure_kind",
        "winner_basis",
        "retained_proposal_basis",
        "best_phase_candidate_authority_projection",
        "runner_phase_candidate_authority_projection",
        "eliminated_candidate_authority_projections",
        "global_lattice_authority",
        "calibrated_nominal_grid_evidence",
        "adjacency_observation_coverage",
        "adjacency_continuity_observations",
        "direct_role_binding_authority",
        "outer_frame_observation_authority",
        "source_frame_width_topology_assessment",
    }:
        raise ValueError("development phase competition schema is invalid")
    best = value["best"]
    runner = value["runner_up"]
    best_projection = value["best_phase_candidate_authority_projection"]
    runner_projection = value["runner_phase_candidate_authority_projection"]
    retained_proposal_basis = value["retained_proposal_basis"]
    if retained_proposal_basis is not None:
        calibrated = (
            isinstance(best, dict)
            and best.get("calibrated_nominal_grid_fit_state") is not None
        )
        if (
            retained_proposal_basis not in _PHASE_RETAINED_PROPOSAL_BASES
            or best is None
            or value["status"] == PhaseFitStatus.RESOLVED.value
            or calibrated
            != (
                retained_proposal_basis
                == PhaseRetainedProposalBasis
                .CALIBRATED_NOMINAL_GRID_BEFORE_LOCAL_COUNTEREVIDENCE.value
            )
        ):
            raise ValueError("development retained phase proposal is invalid")
    if (
        best is None
        and best_projection is not None
        or runner is None
        and runner_projection is not None
    ):
        raise ValueError("phase-candidate projection lost its candidate")
    _validate_phase_candidate_projection(best_projection, best)
    _validate_phase_candidate_projection(runner_projection, runner)
    eliminated = value["eliminated_candidate_authority_projections"]
    if (
        not isinstance(eliminated, list)
        or len(eliminated) > 2
        or any(
            not isinstance(item, dict)
            or item.get("outcome") != "direct_role_contradiction"
            for item in eliminated
        )
    ):
        raise ValueError("eliminated phase-candidate ledger is invalid")
    for projection in eliminated:
        _validate_phase_candidate_projection(projection, None)
    _validate_nominal_grid_evidence(
        value["calibrated_nominal_grid_evidence"]
    )
    _validate_adjacency_coverage(value["adjacency_observation_coverage"])
    _validate_adjacency_continuity(
        value["adjacency_continuity_observations"]
    )
    _validate_source_frame_width_topology_assessment(
        value["source_frame_width_topology_assessment"]
    )
    if [
        item["relation_ordinal"]
        for item in value["adjacency_observation_coverage"]
    ] != [
        item["relation_ordinal"]
        for item in value["adjacency_continuity_observations"]
    ]:
        raise ValueError("adjacency coverage and continuity disagree")
    receipt = value["receipt"]
    receipt_fields = {
        "observation_count",
        "role_count",
        "phase_lookup_count",
        "role_binding_count",
        "adjacency_relation_evaluation_count",
        "local_refinement_lookup_count",
        "local_refinement_binding_count",
        "phase_hypothesis_count",
        "phase_offset_lookup_count",
        "direct_observation_count",
        "inferred_role_count",
        "peak_temporary_bytes",
        "fit_pass_count",
        "separator_lattice_hypothesis_count",
        "candidate_direct_role_authority_evaluation_count",
        "candidate_direct_role_authority_terminal_count",
        "candidate_direct_role_authority_role_check_count",
        "candidate_direct_role_projection_evaluation_count",
        "candidate_direct_role_projection_success_count",
        "candidate_direct_role_projection_binding_count",
        "candidate_nominal_grid_solve_count",
        "candidate_nominal_grid_solve_success_count",
        "selected_direct_role_projection_evaluation_count",
        "selected_direct_role_projection_binding_count",
        "selected_nominal_grid_solve_count",
        "selected_nominal_grid_solve_success_count",
    }
    if not isinstance(receipt, dict) or set(receipt) != receipt_fields:
        raise ValueError("phase-candidate work receipt schema is invalid")
    if any(
        not isinstance(receipt[field], int)
        or isinstance(receipt[field], bool)
        or receipt[field] < 0
        for field in receipt_fields
    ):
        raise ValueError("phase-candidate work receipt value is invalid")
    authority_count = receipt[
        "candidate_direct_role_authority_evaluation_count"
    ]
    projection_count = receipt[
        "candidate_direct_role_projection_evaluation_count"
    ]
    selected_projection_count = receipt[
        "selected_direct_role_projection_evaluation_count"
    ]
    if (
        projection_count != authority_count
        or receipt["candidate_direct_role_authority_terminal_count"]
        + receipt["candidate_direct_role_projection_success_count"]
        > projection_count
        or receipt["candidate_direct_role_projection_binding_count"]
        > receipt["candidate_direct_role_authority_role_check_count"]
        or receipt["candidate_nominal_grid_solve_success_count"]
        > receipt["candidate_nominal_grid_solve_count"]
        or receipt["candidate_nominal_grid_solve_count"] > projection_count
        or selected_projection_count > 2 * receipt["fit_pass_count"]
        or receipt["selected_direct_role_projection_binding_count"]
        > receipt["role_count"] * selected_projection_count
        or receipt["selected_nominal_grid_solve_success_count"]
        > receipt["selected_nominal_grid_solve_count"]
        or receipt["selected_nominal_grid_solve_count"]
        > selected_projection_count
    ):
        raise ValueError("phase-candidate work receipt is inconsistent")
    if value["status"] == "bound_exceeded" and any(
        item is not None for item in (best, runner, best_projection, runner_projection)
    ):
        raise ValueError("bound-exceeded phase carries a candidate")


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
    production_geometry = record["photo_geometry"]
    production_lanes = production_geometry["lanes"]
    if (
        not isinstance(lanes, list)
        or len(lanes) != len(production_lanes)
        or development.get("source_placement_proposal")
        != production_geometry.get("source_placement_proposal")
    ):
        raise ValueError("development lane facts are unavailable")
    for lane, production_lane in zip(lanes, production_lanes, strict=True):
        placement = lane.get("placement_competition")
        work = lane.get("work")
        winner = lane.get("winner_basis")
        if (
            not isinstance(placement, dict)
            or not isinstance(work, dict)
            or work.get("placement_evaluation_count")
            != len(placement.get("placements", ()))
            or not isinstance(lane.get("phase_competition"), dict)
            or not isinstance(lane.get("source_frame_width_authority"), dict)
            or lane.get("source_frame_width_topology_assessment")
            != lane["phase_competition"].get(
                "source_frame_width_topology_assessment"
            )
            or not isinstance(lane.get("cross_competition"), dict)
            or lane.get("aperture_aspect_ratio_authority")
            != lane.get("cross_competition", {}).get(
                "aperture_aspect_ratio_authority"
            )
            or not isinstance(lane.get("template_alignment"), dict)
            or lane.get("placement_proposal")
            != production_lane.get("placement_proposal")
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
        _validate_direct_role_aperture_domain_authority(
            placement.get("direct_role_aperture_domain_authority")
        )
        _validate_phase_competition(lane["phase_competition"])


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
