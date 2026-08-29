"""Review-only machine salience facts for human-visible sequence boundaries.

This module never changes annotation geometry or grants gold authority.  It
uses a human line only as a registered local query centre, then records whether
the production transition measurement can support that neighbourhood and how
little photo-side signal is present there.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from typing import Any, Iterable

import numpy as np

from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryMeasurementQuery,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    QueryPurpose,
)
from x5crop.detection.photo_geometry.registered_measurement import (
    make_photo_boundary_measurement_field,
    measure_registered_queries,
)
from x5crop.detection.photo_geometry.template_measurement_plan import (
    _lattice_positions,
)
from x5crop.detection.photo_geometry.transition_tracking import (
    track_side_transition_regions,
)
from x5crop.domain import FiniteInterval, PositiveInterval
from x5crop.formats import format_spec

from .model import (
    canonical_record_sha256,
    geometry_snapshot,
    referenced_boundary_ids,
    utc_now,
)
from .refinement import _active_interval, _logical_line


MACHINE_SALIENCE_SCHEMA = "x5crop_machine_salience_review_v1"
MACHINE_SALIENCE_ANALYSIS_REVISION = "registered_human_line_salience_v1"
MACHINE_SALIENCE_REVIEW_STATUSES = {
    "unreviewed",
    "confirmed_low",
    "confirmed_not_low",
}
LOW_REFERENCE_QUANTILE = 0.20
MINIMUM_FORMAT_REFERENCE_LINES = 8
LOCAL_CORRIDOR_HALF_WIDTH_MM = 0.55


def _stable_sha(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _line_uses(record: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for task in record["tasks"]:
        for slot in task["slots"]:
            reference = slot["reference_geometry"]
            if reference.get("kind") != "boundary_pair":
                continue
            for role, key in (
                ("start", "start_boundary_id"),
                ("end", "end_boundary_id"),
            ):
                result.setdefault(str(reference[key]), []).append(
                    {
                        "task_id": str(task["task_id"]),
                        "sample_id": str(task["sample_id"]),
                        "ordinal": int(slot["ordinal"]),
                        "role": role,
                    }
                )
    return result


def _eligibility(
    line: dict[str, Any],
    uses: list[dict[str, Any]],
) -> tuple[bool, str | None, str | None]:
    roles = {str(item["role"]) for item in uses}
    if not uses:
        return False, "not_referenced_by_frame", None
    if roles == {"start", "end"}:
        return False, "shared_start_end_contact_boundary", None
    if roles not in ({"start"}, {"end"}):
        return False, "ambiguous_physical_role", None
    if line.get("review_basis") != "directly_visible":
        return False, "not_directly_visible", roles.pop()
    return True, None, roles.pop()


def _percentile(values: list[float], quantile: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=np.float64), quantile))


def _summary(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "median": _percentile(values, 0.50),
        "q75": _percentile(values, 0.75),
        "q90": _percentile(values, 0.90),
    }


def _side_metrics(
    gray: np.ndarray,
    *,
    record: dict[str, Any],
    logical: Any,
    role: str,
    traces: tuple[int, ...],
    scale_px_per_mm: float,
) -> dict[str, Any]:
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    window = spec.local_window_px(scale_px_per_mm)
    gap = spec.transition_gap_px(scale_px_per_mm)
    tone_difference: list[float] = []
    texture_difference: list[float] = []
    inside_texture: list[float] = []
    outside_texture: list[float] = []
    inside_tone: list[float] = []
    outside_tone: list[float] = []
    center_gradient: list[float] = []
    horizontal = record["strip_axis_display"] == "horizontal"
    for trace in traces:
        coordinate = int(round(float(logical.value(float(trace)))))
        values = gray[trace, :] if horizontal else gray[:, trace]
        differences = np.abs(np.diff(values.astype(np.float64, copy=False)))
        left_start = coordinate - gap - window
        left_stop = coordinate - gap
        right_start = coordinate + gap
        right_stop = coordinate + gap + window
        if left_start < 0 or right_stop > values.size:
            continue
        left_tone = float(np.mean(values[left_start:left_stop], dtype=np.float64))
        right_tone = float(np.mean(values[right_start:right_stop], dtype=np.float64))
        texture_coordinate = int(
            np.clip(
                coordinate,
                window + gap,
                differences.size - window - gap,
            )
        )
        texture_left_start = texture_coordinate - gap - window
        texture_left_stop = texture_coordinate - gap
        texture_right_start = texture_coordinate + gap
        texture_right_stop = texture_coordinate + gap + window
        left_texture = float(
            np.mean(
                differences[texture_left_start:texture_left_stop],
                dtype=np.float64,
            )
        )
        right_texture = float(
            np.mean(
                differences[texture_right_start:texture_right_stop],
                dtype=np.float64,
            )
        )
        tone_difference.append(abs(right_tone - left_tone))
        texture_difference.append(abs(right_texture - left_texture))
        if role == "start":
            inside_tone.append(right_tone)
            outside_tone.append(left_tone)
            inside_texture.append(right_texture)
            outside_texture.append(left_texture)
        else:
            inside_tone.append(left_tone)
            outside_tone.append(right_tone)
            inside_texture.append(left_texture)
            outside_texture.append(right_texture)
        center_gradient.append(
            abs(float(values[coordinate + gap - 1]) - float(values[coordinate - gap]))
        )
    return {
        "sample_count": len(tone_difference),
        "query_trace_count": len(traces),
        "window_px": window,
        "gap_px": gap,
        "tone_difference_codes": _summary(tone_difference),
        "texture_difference_codes": _summary(texture_difference),
        "inside_texture_codes": _summary(inside_texture),
        "outside_texture_codes": _summary(outside_texture),
        "inside_tone_codes": _summary(inside_tone),
        "outside_tone_codes": _summary(outside_tone),
        "center_gradient_codes": _summary(center_gradient),
    }


def analyze_source_lines(
    record: dict[str, Any],
    gray: np.ndarray,
) -> dict[str, Any]:
    """Measure every active long-axis boundary in one prepared source."""

    if gray.dtype != np.uint8 or gray.ndim != 2:
        raise ValueError("machine salience analysis requires registered uint8 gray")
    expected_shape = (
        int(record["source"]["canonical_extent"]["height"]),
        int(record["source"]["canonical_extent"]["width"]),
    )
    if gray.shape != expected_shape:
        raise ValueError("machine salience raster and annotation extent disagree")
    uses_by_id = _line_uses(record)
    referenced = referenced_boundary_ids(record)
    physical = format_spec(str(record["format_id"])).frame
    layout = str(record["strip_axis_display"])
    boundary_axis = BoundaryAxis.X if layout == "horizontal" else BoundaryAxis.Y
    field = make_photo_boundary_measurement_field(gray, layout)
    result: dict[str, Any] = {}
    for line in record["boundary_pool"]:
        line_id = str(line["line_id"])
        if line_id not in referenced:
            continue
        uses = deepcopy(uses_by_id.get(line_id, []))
        eligible, reason, role = _eligibility(line, uses)
        line_geometry_sha256 = _stable_sha(
            {
                "line_id": line_id,
                "points_raw": line["points_raw"],
                "review_basis": line["review_basis"],
                "uses": uses,
            }
        )
        fact: dict[str, Any] = {
            "line_id": line_id,
            "line_geometry_sha256": line_geometry_sha256,
            "review_basis": str(line["review_basis"]),
            "uses": uses,
            "physical_role": role,
            "eligible": eligible,
            "not_applicable_reason": reason,
            "machine_classification": "not_applicable",
            "recall_candidate": False,
            "high_confidence_proposal": False,
            "proposal_reasons": [],
            "review_status": "unreviewed",
            "reviewed_at_utc": None,
        }
        if not eligible:
            result[line_id] = fact
            continue
        logical = _logical_line(record, line, "boundary")
        low, high = _active_interval(record, logical, "boundary")
        scale = (high - low) / physical.frame_height_mm
        spacing = scale * PHOTO_BOUNDARY_MEASUREMENT_SPEC.lattice_spacing_mm(
            physical.frame_height_mm
        )
        traces = _lattice_positions(
            int(math.ceil(low)),
            int(math.floor(high)) + 1,
            spacing,
        )
        radius = float(math.ceil(LOCAL_CORRIDOR_HALF_WIDTH_MM * scale))
        search_intervals: list[FiniteInterval] = []
        for trace in traces:
            center = float(logical.value(float(trace)))
            search_intervals.append(
                FiniteInterval(
                    max(0.0, center - radius),
                    min(float(logical.dependent_extent - 1), center + radius),
                )
            )
        scale_interval = PositiveInterval.exact(scale)
        query = PhotoBoundaryMeasurementQuery(
            query_id=f"manual-salience:{record['source']['sha256']}:{line_id}",
            registration_index=0,
            lane_id="manual-source-reference",
            purpose=QueryPurpose.COARSE_STRIP_LONG,
            boundary_axis=boundary_axis,
            trace_positions_px=traces,
            search_intervals_px=tuple(search_intervals),
            transition_ownership_intervals_px=tuple(search_intervals),
            expected_support_px=high - low,
            boundary_axis_scale_px_per_mm=scale_interval,
            trace_axis_scale_px_per_mm=scale_interval,
            measurement_halo_px=(
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.measurement_halo_px(scale)
            ),
            registration_provenance_ids=(
                MACHINE_SALIENCE_ANALYSIS_REVISION,
                line_geometry_sha256,
            ),
        )
        measurement = measure_registered_queries(field, (query,))[0]
        regions = track_side_transition_regions(
            (measurement,),
            reference_trace_px=0.5 * (low + high),
            boundary_axis_scale_px_per_mm=scale_interval,
            support_interval_px=FiniteInterval(low, high),
        )
        transition_by_id = {
            str(item.transition_id): item for item in measurement.transitions
        }
        tolerance = PHOTO_BOUNDARY_MEASUREMENT_SPEC.line_connection_allowance_px(
            scale
        )
        region_evidence: list[dict[str, Any]] = []
        for region in regions:
            transitions = [
                transition_by_id[str(identity)]
                for identity in region.transition_ids
            ]
            residuals = [
                abs(
                    float(item.coordinate_px)
                    - float(logical.value(float(item.trace_coordinate_px)))
                )
                for item in transitions
            ]
            median_residual = _percentile(residuals, 0.50)
            q80_residual = _percentile(residuals, 0.80)
            region_evidence.append(
                {
                    "region_id": str(region.region_id),
                    "trace_support_count": int(region.trace_support_count),
                    "independent_support_region_count": int(
                        region.independent_support_region_count
                    ),
                    "continuous_support_fraction": float(
                        region.continuous_support_fraction
                    ),
                    "mean_gradient_z": float(region.mean_gradient_z),
                    "mean_tone_or_texture_z": float(
                        region.mean_tone_or_texture_z
                    ),
                    "median_line_residual_px": median_residual,
                    "q80_line_residual_px": q80_residual,
                    "matches_human_line": (
                        median_residual <= tolerance
                        and q80_residual <= 2.0 * tolerance
                    ),
                }
            )
        matched = [item for item in region_evidence if item["matches_human_line"]]
        best = min(
            matched or region_evidence,
            key=lambda item: (
                item["median_line_residual_px"],
                item["q80_line_residual_px"],
                item["region_id"],
            ),
            default=None,
        )
        side_metrics = _side_metrics(
            gray,
            record=record,
            logical=logical,
            role=str(role),
            traces=traces,
            scale_px_per_mm=scale,
        )
        measurable = side_metrics["sample_count"] > 0
        recall_candidate = len(matched) == 0
        fact.update(
            {
                "machine_classification": (
                    "production_edge_matched"
                    if matched
                    else "no_matched_production_edge"
                ),
                "recall_candidate": recall_candidate,
                "measurement": {
                    "scale_px_per_mm": scale,
                    "query_trace_count": len(traces),
                    "transition_count": len(measurement.transitions),
                    "qualified_region_count": len(regions),
                    "matched_region_count": len(matched),
                    "line_match_tolerance_px": tolerance,
                    "best_region": best,
                    "side_metrics": side_metrics,
                    "bilateral_side_metrics_measurable": measurable,
                },
            }
        )
        if not measurable:
            fact["machine_classification"] = "not_measurable_at_source_boundary"
            fact["recall_candidate"] = False
        result[line_id] = fact
    return {
        "source_sha256": str(record["source"]["sha256"]),
        "canonical_sample_id": str(record["source"]["canonical_sample_id"]),
        "format_id": str(record["format_id"]),
        "source_geometry_sha256": canonical_record_sha256(
            geometry_snapshot(record)
        ),
        "lines": result,
    }


def _nearest_empirical_quantile(values: Iterable[float], quantile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("salience reference population is empty")
    return ordered[round((len(ordered) - 1) * quantile)]


def _reference_thresholds(
    source_facts: Iterable[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    metrics = (
        "tone_difference_codes",
        "texture_difference_codes",
        "inside_texture_codes",
    )
    recognized: list[tuple[str, dict[str, Any]]] = []
    for source in source_facts:
        for line in source["lines"].values():
            measurement = line.get("measurement")
            if (
                not line["eligible"]
                or not isinstance(measurement, dict)
                or measurement["matched_region_count"] <= 0
                or not measurement["bilateral_side_metrics_measurable"]
            ):
                continue
            recognized.append((str(source["format_id"]), line))

    def thresholds(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "reference_line_count": len(rows),
            "q20": {
                metric: _nearest_empirical_quantile(
                    (
                        row["measurement"]["side_metrics"][metric]["q75"]
                        for row in rows
                    ),
                    LOW_REFERENCE_QUANTILE,
                )
                for metric in metrics
            },
        }

    global_rows = [line for _format, line in recognized]
    if not global_rows:
        raise ValueError("no production-recognized directly visible reference lines")
    global_threshold = thresholds(global_rows)
    formats = sorted({format_id for format_id, _line in recognized})
    by_format: dict[str, dict[str, Any]] = {}
    for format_id in formats:
        rows = [line for current, line in recognized if current == format_id]
        if len(rows) >= MINIMUM_FORMAT_REFERENCE_LINES:
            item = thresholds(rows)
            item["reference_scope"] = "same_format"
        else:
            item = deepcopy(global_threshold)
            item["reference_scope"] = "global_fallback"
            item["same_format_reference_line_count"] = len(rows)
        by_format[format_id] = item
    global_threshold["reference_scope"] = "all_formats"
    return by_format, global_threshold


def _recompute_summary(review: dict[str, Any]) -> dict[str, int]:
    sources = review["sources"].values()
    lines = [line for source in sources for line in source["lines"].values()]
    proposed_sources = {
        source["source_sha256"]
        for source in review["sources"].values()
        if any(line["high_confidence_proposal"] for line in source["lines"].values())
    }
    pending_proposal_sources = {
        source["source_sha256"]
        for source in review["sources"].values()
        if any(
            line["high_confidence_proposal"]
            and line["review_status"] == "unreviewed"
            for line in source["lines"].values()
        )
    }
    return {
        "source_count": len(review["sources"]),
        "boundary_line_count": len(lines),
        "eligible_line_count": sum(bool(line["eligible"]) for line in lines),
        "not_applicable_line_count": sum(not line["eligible"] for line in lines),
        "recall_candidate_line_count": sum(
            bool(line["recall_candidate"]) for line in lines
        ),
        "high_confidence_proposal_line_count": sum(
            bool(line["high_confidence_proposal"]) for line in lines
        ),
        "high_confidence_proposal_source_count": len(proposed_sources),
        "pending_proposal_line_count": sum(
            line["high_confidence_proposal"]
            and line["review_status"] == "unreviewed"
            for line in lines
        ),
        "pending_proposal_source_count": len(pending_proposal_sources),
        "confirmed_low_line_count": sum(
            line["review_status"] == "confirmed_low" for line in lines
        ),
        "confirmed_not_low_line_count": sum(
            line["review_status"] == "confirmed_not_low" for line in lines
        ),
        "not_measurable_line_count": sum(
            line["machine_classification"]
            == "not_measurable_at_source_boundary"
            for line in lines
        ),
    }


def build_machine_salience_review(
    source_facts: Iterable[dict[str, Any]],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calibrate proposals and preserve only still-current human verdicts."""

    sources = [deepcopy(source) for source in source_facts]
    thresholds_by_format, global_thresholds = _reference_thresholds(sources)
    existing_sources = (
        existing.get("sources", {})
        if isinstance(existing, dict)
        and existing.get("schema") == MACHINE_SALIENCE_SCHEMA
        else {}
    )
    for source in sources:
        threshold = thresholds_by_format.get(
            str(source["format_id"]), global_thresholds
        )["q20"]
        old_source = existing_sources.get(source["source_sha256"], {})
        source_unchanged = (
            old_source.get("source_geometry_sha256")
            == source["source_geometry_sha256"]
        )
        for line_id, line in source["lines"].items():
            metrics = line.get("measurement", {}).get("side_metrics", {})
            low_tail = bool(
                line["eligible"]
                and line["recall_candidate"]
                and line.get("measurement", {}).get("qualified_region_count") == 0
                and line.get("measurement", {}).get(
                    "bilateral_side_metrics_measurable"
                )
                and all(
                    metrics[name]["q75"] <= threshold[name]
                    for name in (
                        "tone_difference_codes",
                        "texture_difference_codes",
                        "inside_texture_codes",
                    )
                )
            )
            line["high_confidence_proposal"] = low_tail
            line["proposal_reasons"] = (
                [
                    "no_matched_production_edge",
                    "no_competing_qualified_local_edge",
                    "same_format_low_tail_tone_texture_and_inside_texture",
                ]
                if low_tail
                else []
            )
            old_line = old_source.get("lines", {}).get(line_id, {})
            if (
                source_unchanged
                and old_line.get("line_geometry_sha256")
                == line["line_geometry_sha256"]
                and old_line.get("review_status")
                in MACHINE_SALIENCE_REVIEW_STATUSES
            ):
                line["review_status"] = old_line["review_status"]
                line["reviewed_at_utc"] = old_line.get("reviewed_at_utc")
    review = {
        "schema": MACHINE_SALIENCE_SCHEMA,
        "analysis_revision": MACHINE_SALIENCE_ANALYSIS_REVISION,
        "generated_at_utc": utc_now(),
        "review_revision": (
            int(existing.get("review_revision", 0)) + 1
            if isinstance(existing, dict)
            else 1
        ),
        "authority": "machine_proposal_for_human_audit_only",
        "policy": {
            "query_corridor_half_width_mm": LOCAL_CORRIDOR_HALF_WIDTH_MM,
            "low_reference_quantile": LOW_REFERENCE_QUANTILE,
            "minimum_same_format_reference_lines": MINIMUM_FORMAT_REFERENCE_LINES,
            "eligible_review_basis": "directly_visible",
            "shared_start_end_contact_boundary": "not_applicable",
            "accuracy_or_runtime_authority": False,
        },
        "thresholds_by_format": thresholds_by_format,
        "global_thresholds": global_thresholds,
        "sources": {
            str(source["source_sha256"]): source
            for source in sources
        },
    }
    review["summary"] = _recompute_summary(review)
    validate_machine_salience_review(review)
    return review


def validate_machine_salience_review(review: dict[str, Any]) -> None:
    if (
        review.get("schema") != MACHINE_SALIENCE_SCHEMA
        or review.get("analysis_revision")
        != MACHINE_SALIENCE_ANALYSIS_REVISION
        or review.get("authority") != "machine_proposal_for_human_audit_only"
        or not isinstance(review.get("review_revision"), int)
        or isinstance(review.get("review_revision"), bool)
        or int(review["review_revision"]) <= 0
        or not isinstance(review.get("sources"), dict)
        or not isinstance(review.get("summary"), dict)
    ):
        raise ValueError("machine salience review schema is not current")
    for sha, source in review["sources"].items():
        if (
            not isinstance(sha, str)
            or len(sha) != 64
            or source.get("source_sha256") != sha
            or not isinstance(source.get("source_geometry_sha256"), str)
            or not isinstance(source.get("lines"), dict)
        ):
            raise ValueError("machine salience source record is invalid")
        for line_id, line in source["lines"].items():
            if (
                line.get("line_id") != line_id
                or line.get("review_status")
                not in MACHINE_SALIENCE_REVIEW_STATUSES
                or not isinstance(line.get("eligible"), bool)
                or not isinstance(line.get("recall_candidate"), bool)
                or not isinstance(line.get("high_confidence_proposal"), bool)
                or not isinstance(line.get("line_geometry_sha256"), str)
            ):
                raise ValueError("machine salience line record is invalid")
            if line["review_status"] == "unreviewed":
                if line.get("reviewed_at_utc") is not None:
                    raise ValueError("unreviewed salience line has a review timestamp")
            elif not isinstance(line.get("reviewed_at_utc"), str):
                raise ValueError("reviewed salience line lacks a review timestamp")
    if review["summary"] != _recompute_summary(review):
        raise ValueError("machine salience summary is stale")


def set_line_review_status(
    review: dict[str, Any],
    *,
    source_sha256: str,
    source_geometry_sha256: str,
    line_id: str,
    review_status: str,
    expected_review_revision: int,
) -> dict[str, Any]:
    validate_machine_salience_review(review)
    if (
        not isinstance(expected_review_revision, int)
        or isinstance(expected_review_revision, bool)
        or expected_review_revision != review["review_revision"]
    ):
        raise ValueError("machine salience review revision conflict")
    if review_status not in MACHINE_SALIENCE_REVIEW_STATUSES:
        raise ValueError("machine salience review status is invalid")
    source = review["sources"].get(source_sha256)
    if not isinstance(source, dict):
        raise ValueError("machine salience source is not analyzed")
    if source.get("source_geometry_sha256") != source_geometry_sha256:
        raise ValueError("machine salience source geometry is stale")
    line = source["lines"].get(line_id)
    if not isinstance(line, dict) or not line.get("eligible"):
        raise ValueError("line is not eligible for machine salience review")
    updated = deepcopy(review)
    target = updated["sources"][source_sha256]["lines"][line_id]
    target["review_status"] = review_status
    target["reviewed_at_utc"] = (
        None if review_status == "unreviewed" else utc_now()
    )
    updated["review_revision"] = int(review["review_revision"]) + 1
    updated["summary"] = _recompute_summary(updated)
    validate_machine_salience_review(updated)
    return updated


def source_review_summary(source: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {
            "analysis_state": "missing",
            "boundary_line_count": 0,
            "eligible_line_count": 0,
            "not_applicable_line_count": 0,
            "recall_candidate_line_count": 0,
            "high_confidence_proposal_line_count": 0,
            "pending_proposal_line_count": 0,
            "pending_recall_line_count": 0,
            "confirmed_low_line_count": 0,
            "confirmed_not_low_line_count": 0,
            "not_measurable_line_count": 0,
        }
    lines = list(source["lines"].values())
    return {
        "analysis_state": "current",
        "boundary_line_count": len(lines),
        "eligible_line_count": sum(line["eligible"] for line in lines),
        "not_applicable_line_count": sum(not line["eligible"] for line in lines),
        "recall_candidate_line_count": sum(
            line["recall_candidate"] for line in lines
        ),
        "high_confidence_proposal_line_count": sum(
            line["high_confidence_proposal"] for line in lines
        ),
        "pending_proposal_line_count": sum(
            line["high_confidence_proposal"]
            and line["review_status"] == "unreviewed"
            for line in lines
        ),
        "pending_recall_line_count": sum(
            line["recall_candidate"]
            and line["review_status"] == "unreviewed"
            for line in lines
        ),
        "confirmed_low_line_count": sum(
            line["review_status"] == "confirmed_low" for line in lines
        ),
        "confirmed_not_low_line_count": sum(
            line["review_status"] == "confirmed_not_low" for line in lines
        ),
        "not_measurable_line_count": sum(
            line["machine_classification"]
            == "not_measurable_at_source_boundary"
            for line in lines
        ),
    }
