"""Human-guided, bounded native-pixel refinement for pending gold geometry."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Any, Iterable

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import least_squares

from .imaging import SourceRaster
from .model import (
    AnnotationError,
    canonical_record_sha256,
    display_to_raw_point,
    geometry_snapshot,
    line_basis_summary,
    raw_to_display_point,
    referenced_boundary_ids,
    refresh_adjacency_kinds,
    slot_boundary_ids,
    utc_now,
    validate_annotation_record,
)


REFINEMENT_REVISION = "human_guided_bounded_native_edge_v1"
PIXEL_REFINEMENT_ORIGIN = "bounded_native_pixel_refinement_v1"
WIDTH_REFINEMENT_ORIGIN = "same_source_visible_width_refinement_v1"


@dataclass(frozen=True)
class LogicalLine:
    """A line as dependent = slope * independent + intercept."""

    slope: float
    intercept: float
    independent_extent: int
    dependent_extent: int

    def value(self, independent: np.ndarray | float) -> np.ndarray | float:
        return self.slope * independent + self.intercept


@dataclass(frozen=True)
class PixelFit:
    decision: str
    reason: str
    slope: float
    intercept: float
    center_delta_px: float
    endpoint_delta_px: tuple[float, float]
    sample_count: int
    support_count: int
    support_fraction: float
    score: float
    runner_score: float
    uniqueness_margin: float
    gain_over_input: float
    search_radius_px: int

    @property
    def accepted(self) -> bool:
        return self.decision == "moved_to_unique_local_edge"


def _line_family(record: dict[str, Any], line_id: str) -> str:
    return "shared" if any(
        line["line_id"] == line_id for line in record["shared_edges"]
    ) else "boundary"


def _display_points(
    record: dict[str, Any],
    line: dict[str, Any],
) -> tuple[tuple[float, float], tuple[float, float]]:
    points = tuple(
        tuple(float(value) for value in raw_to_display_point(record, point))
        for point in line["points_raw"]
    )
    if len(points) != 2:
        raise AnnotationError("refinement line requires two points")
    return points  # type: ignore[return-value]


def _logical_line(
    record: dict[str, Any],
    line: dict[str, Any],
    family: str,
) -> LogicalLine:
    first, second = _display_points(record, line)
    horizontal = record["strip_axis_display"] == "horizontal"
    width = int(record["source"]["canonical_extent"]["width"])
    height = int(record["source"]["canonical_extent"]["height"])
    long_extent = width if horizontal else height
    cross_extent = height if horizontal else width
    if family == "shared":
        independent = (first[0], second[0]) if horizontal else (first[1], second[1])
        dependent = (first[1], second[1]) if horizontal else (first[0], second[0])
        independent_extent, dependent_extent = long_extent, cross_extent
    else:
        independent = (first[1], second[1]) if horizontal else (first[0], second[0])
        dependent = (first[0], second[0]) if horizontal else (first[1], second[1])
        independent_extent, dependent_extent = cross_extent, long_extent
    denominator = independent[1] - independent[0]
    if abs(denominator) <= 1.0e-9:
        raise AnnotationError("refinement line has no independent span")
    slope = (dependent[1] - dependent[0]) / denominator
    intercept = dependent[0] - slope * independent[0]
    return LogicalLine(
        slope=float(slope),
        intercept=float(intercept),
        independent_extent=independent_extent,
        dependent_extent=dependent_extent,
    )


def _display_points_from_logical(
    record: dict[str, Any],
    line: LogicalLine,
    family: str,
) -> list[list[float]]:
    final = float(line.independent_extent - 1)
    first_dependent = float(line.intercept)
    final_dependent = float(line.value(final))
    horizontal = record["strip_axis_display"] == "horizontal"
    if (family == "shared" and horizontal) or (
        family == "boundary" and not horizontal
    ):
        return [[0.0, first_dependent], [final, final_dependent]]
    return [[first_dependent, 0.0], [final_dependent, final]]


def _intersection_independent(
    primary: LogicalLine,
    secondary: LogicalLine,
) -> float:
    """Return primary independent coordinate at two orthogonal logical lines."""

    denominator = 1.0 - secondary.slope * primary.slope
    if abs(denominator) <= 1.0e-9:
        raise AnnotationError("refinement lines are numerically parallel")
    return float(
        (secondary.slope * primary.intercept + secondary.intercept) / denominator
    )


def _active_interval(
    record: dict[str, Any],
    line: LogicalLine,
    family: str,
) -> tuple[float, float]:
    if family == "shared":
        referenced = referenced_boundary_ids(record)
        intersections = [
            _intersection_independent(
                line,
                _logical_line(record, boundary, "boundary"),
            )
            for boundary in record["boundary_pool"]
            if boundary["line_id"] in referenced
        ]
        if len(intersections) >= 2:
            low, high = min(intersections), max(intersections)
            padding = 0.015 * max(high - low, 1.0)
            low -= padding
            high += padding
        else:
            low, high = 0.0, float(line.independent_extent - 1)
    else:
        intersections = [
            _intersection_independent(
                line,
                _logical_line(record, shared, "shared"),
            )
            for shared in record["shared_edges"]
        ]
        low, high = min(intersections), max(intersections)
        inset = min(12.0, 0.006 * max(high - low, 1.0))
        low += inset
        high -= inset
    low = max(0.0, min(float(line.independent_extent - 1), low))
    high = max(0.0, min(float(line.independent_extent - 1), high))
    if high - low < 24.0:
        return 0.0, float(line.independent_extent - 1)
    return low, high


def _frame_width_hint(record: dict[str, Any]) -> float:
    pool = {line["line_id"]: line for line in record["boundary_pool"]}
    widths: list[float] = []
    for task in record["tasks"]:
        for slot in task["slots"]:
            pair = slot_boundary_ids(slot)
            if pair is None:
                continue
            start = _logical_line(record, pool[pair[0]], "boundary")
            end = _logical_line(record, pool[pair[1]], "boundary")
            reference = 0.5 * (start.independent_extent - 1)
            width = float(end.value(reference) - start.value(reference))
            if width > 4.0:
                widths.append(width)
    if widths:
        return float(np.median(widths))
    long_extent = (
        int(record["source"]["canonical_extent"]["width"])
        if record["strip_axis_display"] == "horizontal"
        else int(record["source"]["canonical_extent"]["height"])
    )
    count = max(int(task["count"]) for task in record["tasks"])
    return float(long_extent / max(count, 1))


def _search_radius(
    record: dict[str, Any],
    family: str,
) -> int:
    if family == "shared":
        cross_extent = (
            int(record["source"]["canonical_extent"]["height"])
            if record["strip_axis_display"] == "horizontal"
            else int(record["source"]["canonical_extent"]["width"])
        )
        return int(np.clip(round(cross_extent * 0.008), 10, 24))
    return int(np.clip(round(_frame_width_hint(record) * 0.006), 8, 28))


def _sample_gradient_band(
    record: dict[str, Any],
    raster: SourceRaster,
    line: LogicalLine,
    family: str,
    *,
    radius: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    low, high = _active_interval(record, line, family)
    target_count = 1024 if family == "shared" else 512
    sample_count = min(target_count, max(2, int(round(high - low)) + 1))
    independent = np.unique(
        np.rint(np.linspace(low, high, sample_count)).astype(np.int64)
    ).astype(np.float64)
    halo = 3
    offsets = np.arange(-radius - halo, radius + halo + 1, dtype=np.int64)
    dependent = np.asarray(line.value(independent), dtype=np.float64)
    valid = (
        dependent + float(offsets[0]) >= 0.0
    ) & (
        dependent + float(offsets[-1]) <= float(line.dependent_extent - 1)
    )
    independent = independent[valid]
    dependent = dependent[valid]
    if len(independent) < (96 if family == "shared" else 48):
        return independent, np.empty((0, 0), dtype=np.float32), np.empty(0)

    independent_index = np.rint(independent).astype(np.int64)[:, None]
    dependent_index = np.rint(
        dependent[:, None] + offsets[None, :]
    ).astype(np.int64)
    if family == "shared":
        long_index, cross_index = independent_index, dependent_index
    else:
        long_index, cross_index = dependent_index, independent_index
    if record["strip_axis_display"] == "horizontal":
        y_index, x_index = cross_index, long_index
    else:
        y_index, x_index = long_index, cross_index
    samples = np.asarray(raster.canonical[y_index, x_index]).astype(
        np.float32,
        copy=False,
    )
    if samples.ndim == 2:
        samples = samples[..., None]
    channels = min(3, samples.shape[-1])
    levels = record["diagnostics"].get("render_levels")
    normalized: list[np.ndarray] = []
    for channel in range(channels):
        values = samples[..., channel]
        if (
            isinstance(levels, list)
            and channel < len(levels)
            and isinstance(levels[channel], list)
            and len(levels[channel]) == 2
        ):
            low_level, high_level = (float(value) for value in levels[channel])
        else:
            low_level, high_level = (
                float(value) for value in np.quantile(values, (0.002, 0.998))
            )
        span = max(high_level - low_level, 1.0e-12)
        normalized.append(np.clip((values - low_level) / span, 0.0, 1.0))
    colors = np.stack(normalized, axis=-1)
    colors = gaussian_filter1d(colors, 0.9, axis=1, mode="nearest")
    gradient = np.sqrt(
        np.sum(np.gradient(colors, axis=1) ** 2, axis=-1)
    ).astype(np.float32)
    gradient = gradient[:, halo : halo + 2 * radius + 1]
    search_offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    return independent, gradient, search_offsets


def _candidate_score(values: np.ndarray) -> float:
    if not len(values):
        return 0.0
    retain = max(12, int(math.ceil(0.12 * len(values))))
    retain = min(retain, len(values))
    top = np.partition(values, len(values) - retain)[-retain:]
    return float(np.mean(top) + 0.15 * np.mean(values))


def _sample_candidate(
    evidence: np.ndarray,
    offsets: np.ndarray,
    requested: np.ndarray,
) -> np.ndarray:
    lower = np.floor(requested).astype(np.int64)
    upper = np.ceil(requested).astype(np.int64)
    lower = np.clip(lower, int(offsets[0]), int(offsets[-1]))
    upper = np.clip(upper, int(offsets[0]), int(offsets[-1]))
    rows = np.arange(len(requested), dtype=np.int64)
    lower_values = evidence[rows, lower - int(offsets[0])]
    upper_values = evidence[rows, upper - int(offsets[0])]
    fraction = requested - lower
    return lower_values * (1.0 - fraction) + upper_values * fraction


def _fit_pixel_line(
    record: dict[str, Any],
    raster: SourceRaster,
    line: dict[str, Any],
    family: str,
) -> PixelFit:
    logical = _logical_line(record, line, family)
    radius = _search_radius(record, family)
    independent, gradient, offsets = _sample_gradient_band(
        record,
        raster,
        logical,
        family,
        radius=radius,
    )
    minimum_samples = 96 if family == "shared" else 48
    if gradient.size == 0 or len(independent) < minimum_samples:
        return PixelFit(
            decision="retained",
            reason="insufficient_in_source_pixel_band",
            slope=logical.slope,
            intercept=logical.intercept,
            center_delta_px=0.0,
            endpoint_delta_px=(0.0, 0.0),
            sample_count=int(len(independent)),
            support_count=0,
            support_fraction=0.0,
            score=0.0,
            runner_score=0.0,
            uniqueness_margin=0.0,
            gain_over_input=0.0,
            search_radius_px=radius,
        )

    row_noise = np.median(gradient, axis=1, keepdims=True)
    excess = np.maximum(gradient - row_noise, 0.0)
    scale = max(float(np.quantile(excess, 0.95)), 1.0e-6)
    evidence = np.clip(excess / scale, 0.0, 4.0)
    midpoint = 0.5 * (float(independent[0]) + float(independent[-1]))
    half_span = max(0.5 * (float(independent[-1]) - float(independent[0])), 1.0)
    normalized_independent = (independent - midpoint) / half_span
    tilt_limit = max(2, min(10, radius // 2))
    candidates: list[tuple[float, float, float, np.ndarray]] = []
    tilt_values = sorted(set(range(-tilt_limit, tilt_limit + 1, 2)) | {0})
    for center in range(-radius, radius + 1):
        for tilt in tilt_values:
            requested = center + tilt * normalized_independent
            if (
                float(np.min(requested)) < -radius
                or float(np.max(requested)) > radius
            ):
                continue
            values = _sample_candidate(evidence, offsets, requested)
            candidates.append(
                (_candidate_score(values), float(center), float(tilt), values)
            )
    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, center, tilt, best_values = candidates[0]
    best_offsets = center + tilt * normalized_independent
    baseline_values = _sample_candidate(
        evidence,
        offsets,
        np.zeros_like(independent),
    )
    baseline_score = _candidate_score(baseline_values)
    runner_score = 0.0
    for score, runner_center, runner_tilt, _values in candidates[1:]:
        runner_offsets = runner_center + runner_tilt * normalized_independent
        if float(np.sqrt(np.mean((runner_offsets - best_offsets) ** 2))) >= 2.0:
            runner_score = score
            break
    uniqueness = (best_score - runner_score) / max(best_score, 1.0e-9)
    gain = (best_score - baseline_score) / max(best_score, 1.0e-9)
    support_mask = best_values >= 0.55
    support_count = int(np.count_nonzero(support_mask))
    support_fraction = support_count / len(best_values)
    endpoint_delta = (float(center - tilt), float(center + tilt))
    rms_delta = float(np.sqrt(np.mean(best_offsets**2)))
    at_limit = max(abs(endpoint_delta[0]), abs(endpoint_delta[1])) >= radius - 0.5

    reason = "unique_local_edge"
    accepted = True
    if rms_delta <= 0.75:
        accepted = False
        reason = "already_aligned_with_local_edge"
    elif at_limit:
        accepted = False
        reason = "best_edge_reaches_search_limit"
    elif support_count < max(12, int(math.ceil(0.04 * len(best_values)))):
        accepted = False
        reason = "insufficient_coherent_edge_support"
    elif uniqueness < 0.055:
        accepted = False
        reason = "competing_local_edges"
    elif gain < 0.06:
        accepted = False
        reason = "input_line_already_within_ambiguous_edge_band"

    slope_delta = tilt / half_span
    intercept_delta = center - slope_delta * midpoint
    if accepted and support_count >= 12:
        local_offsets = np.clip(np.rint(best_offsets).astype(np.int64), -radius, radius)
        rows = np.arange(len(best_offsets), dtype=np.int64)
        refined_offsets = local_offsets.astype(np.float64)
        refined_strength = np.zeros(len(best_offsets), dtype=np.float64)
        for delta in (-2, -1, 0, 1, 2):
            candidate_offsets = np.clip(local_offsets + delta, -radius, radius)
            values = evidence[rows, candidate_offsets + radius]
            replace = values > refined_strength
            refined_offsets[replace] = candidate_offsets[replace]
            refined_strength[replace] = values[replace]
        retain_threshold = max(0.55, float(np.quantile(refined_strength, 0.70)))
        retain = refined_strength >= retain_threshold
        if int(np.count_nonzero(retain)) >= 12:
            retained_independent = independent[retain]
            retained_offsets = refined_offsets[retain]
            coverage = (
                float(np.max(retained_independent) - np.min(retained_independent))
                / max(float(independent[-1] - independent[0]), 1.0)
            )
            initial = np.asarray([slope_delta, intercept_delta], dtype=np.float64)

            def residual(parameters: np.ndarray) -> np.ndarray:
                return (
                    parameters[0] * retained_independent
                    + parameters[1]
                    - retained_offsets
                )

            fitted = least_squares(
                residual,
                initial,
                loss="soft_l1",
                f_scale=0.8,
                max_nfev=120,
            ).x
            fitted_start = float(fitted[1] + fitted[0] * independent[0])
            fitted_end = float(fitted[1] + fitted[0] * independent[-1])
            if coverage < 0.30:
                fitted_start = fitted_end = float(np.median(retained_offsets))
            if (
                max(abs(fitted_start), abs(fitted_end)) <= radius
                and abs(fitted_start - endpoint_delta[0]) <= 3.0
                and abs(fitted_end - endpoint_delta[1]) <= 3.0
            ):
                slope_delta = (fitted_end - fitted_start) / max(
                    float(independent[-1] - independent[0]),
                    1.0,
                )
                intercept_delta = fitted_start - slope_delta * float(independent[0])
                endpoint_delta = (fitted_start, fitted_end)
                center = float(slope_delta * midpoint + intercept_delta)

    return PixelFit(
        decision=("moved_to_unique_local_edge" if accepted else "retained"),
        reason=reason,
        slope=float(logical.slope + slope_delta) if accepted else logical.slope,
        intercept=(
            float(logical.intercept + intercept_delta)
            if accepted
            else logical.intercept
        ),
        center_delta_px=float(center) if accepted else 0.0,
        endpoint_delta_px=(
            (float(endpoint_delta[0]), float(endpoint_delta[1]))
            if accepted
            else (0.0, 0.0)
        ),
        sample_count=int(len(independent)),
        support_count=support_count,
        support_fraction=float(support_fraction),
        score=float(best_score),
        runner_score=float(runner_score),
        uniqueness_margin=float(uniqueness),
        gain_over_input=float(gain),
        search_radius_px=radius,
    )


def _adjacency_signature(record: dict[str, Any]) -> tuple[tuple[str, int, int, str], ...]:
    return tuple(
        (
            str(task["task_id"]),
            int(adjacency["left_ordinal"]),
            int(adjacency["right_ordinal"]),
            str(adjacency["kind"]),
        )
        for task in record["tasks"]
        for adjacency in task["adjacencies"]
    )


def _replace_logical_line(
    record: dict[str, Any],
    line_id: str,
    logical: LogicalLine,
    family: str,
    origin: str,
) -> None:
    lines: Iterable[dict[str, Any]] = (
        record["shared_edges"] if family == "shared" else record["boundary_pool"]
    )
    line = next(item for item in lines if item["line_id"] == line_id)
    line["points_raw"] = [
        display_to_raw_point(record, point)
        for point in _display_points_from_logical(record, logical, family)
    ]
    line["origin"] = origin


def _try_geometry_change(
    current: dict[str, Any],
    changes: Iterable[tuple[str, LogicalLine, str, str]],
    *,
    adjacency_before: tuple[tuple[str, int, int, str], ...],
) -> tuple[dict[str, Any] | None, str | None]:
    candidate = deepcopy(current)
    for line_id, logical, family, origin in changes:
        _replace_logical_line(candidate, line_id, logical, family, origin)
    refresh_adjacency_kinds(candidate)
    if _adjacency_signature(candidate) != adjacency_before:
        return None, "would_change_human_adjacency_fact"
    try:
        validate_annotation_record(candidate)
    except AnnotationError as error:
        return None, f"geometry_contract_rejected:{error}"
    return candidate, None


def _direct_width_consensus(
    record: dict[str, Any],
) -> tuple[tuple[float, float] | None, dict[str, Any]]:
    pool = {line["line_id"]: line for line in record["boundary_pool"]}
    canonical = min(
        record["tasks"],
        key=lambda task: (
            -int(task["count"]),
            -sum(slot_boundary_ids(slot) is not None for slot in task["slots"]),
            str(task["task_id"]),
        ),
    )
    cross_extent = (
        int(record["source"]["canonical_extent"]["height"])
        if record["strip_axis_display"] == "horizontal"
        else int(record["source"]["canonical_extent"]["width"])
    )
    anchors = (0.25 * (cross_extent - 1), 0.75 * (cross_extent - 1))
    observations: list[tuple[str, float, float]] = []
    for slot in canonical["slots"]:
        pair = slot_boundary_ids(slot)
        if pair is None:
            continue
        start, end = pool[pair[0]], pool[pair[1]]
        if (
            start["review_basis"] != "directly_visible"
            or end["review_basis"] != "directly_visible"
        ):
            continue
        start_line = _logical_line(record, start, "boundary")
        end_line = _logical_line(record, end, "boundary")
        widths = tuple(
            float(end_line.value(anchor) - start_line.value(anchor))
            for anchor in anchors
        )
        if min(widths) <= 4.0:
            continue
        observations.append(
            (f"{canonical['task_id']}#{slot['ordinal']}", widths[0], widths[1])
        )
    diagnostics: dict[str, Any] = {
        "source_frame_ids": [item[0] for item in observations],
        "observation_count": len(observations),
        "accepted_observation_count": 0,
        "status": "insufficient_direct_frame_widths",
    }
    if len(observations) < 2:
        return None, diagnostics
    matrix = np.asarray([[item[1], item[2]] for item in observations], dtype=np.float64)
    center_widths = np.mean(matrix, axis=1)
    median_width = float(np.median(center_widths))
    mad = float(np.median(np.abs(center_widths - median_width)))
    tolerance = max(3.0 * 1.4826 * mad, 0.012 * median_width, 2.0)
    retain = np.abs(center_widths - median_width) <= tolerance
    retained = matrix[retain]
    diagnostics.update(
        {
            "median_width_px": median_width,
            "mad_width_px": mad,
            "inlier_tolerance_px": float(tolerance),
            "accepted_observation_count": int(len(retained)),
            "rejected_source_frame_ids": [
                observations[index][0]
                for index, accepted in enumerate(retain)
                if not accepted
            ],
        }
    )
    if len(retained) < 2:
        diagnostics["status"] = "insufficient_consistent_direct_frame_widths"
        return None, diagnostics
    consensus = np.median(retained, axis=0)
    spread = float(
        np.max(np.abs(np.mean(retained, axis=1) - np.mean(consensus)))
        / max(float(np.mean(consensus)), 1.0)
    )
    diagnostics["maximum_relative_inlier_spread"] = spread
    if spread > 0.035:
        diagnostics["status"] = "direct_frame_widths_not_consistent"
        return None, diagnostics
    slope = float((consensus[1] - consensus[0]) / (anchors[1] - anchors[0]))
    intercept = float(consensus[0] - slope * anchors[0])
    diagnostics.update(
        {
            "status": "accepted",
            "consensus_width_at_anchors_px": [
                float(consensus[0]),
                float(consensus[1]),
            ],
        }
    )
    return (slope, intercept), diagnostics


def _width_estimate_changes(
    record: dict[str, Any],
    width: tuple[float, float],
) -> tuple[list[tuple[str, LogicalLine, str, str]], dict[str, dict[str, Any]]]:
    pool = {line["line_id"]: line for line in record["boundary_pool"]}
    suggestions: dict[str, list[LogicalLine]] = {}
    uses: dict[str, list[str]] = {}
    seen_pairs: set[tuple[str, str]] = set()
    width_slope, width_intercept = width
    for task in record["tasks"]:
        for slot in task["slots"]:
            pair = slot_boundary_ids(slot)
            if pair is None or pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            start, end = pool[pair[0]], pool[pair[1]]
            start_estimated = start["review_basis"] == "human_width_estimate"
            end_estimated = end["review_basis"] == "human_width_estimate"
            if not start_estimated and not end_estimated:
                continue
            start_line = _logical_line(record, start, "boundary")
            end_line = _logical_line(record, end, "boundary")
            if start_estimated and end_estimated:
                center_slope = 0.5 * (start_line.slope + end_line.slope)
                center_intercept = 0.5 * (
                    start_line.intercept + end_line.intercept
                )
                proposed_start = LogicalLine(
                    center_slope - 0.5 * width_slope,
                    center_intercept - 0.5 * width_intercept,
                    start_line.independent_extent,
                    start_line.dependent_extent,
                )
                proposed_end = LogicalLine(
                    center_slope + 0.5 * width_slope,
                    center_intercept + 0.5 * width_intercept,
                    end_line.independent_extent,
                    end_line.dependent_extent,
                )
                suggestions.setdefault(pair[0], []).append(proposed_start)
                suggestions.setdefault(pair[1], []).append(proposed_end)
            elif start_estimated:
                suggestions.setdefault(pair[0], []).append(
                    LogicalLine(
                        end_line.slope - width_slope,
                        end_line.intercept - width_intercept,
                        start_line.independent_extent,
                        start_line.dependent_extent,
                    )
                )
            else:
                suggestions.setdefault(pair[1], []).append(
                    LogicalLine(
                        start_line.slope + width_slope,
                        start_line.intercept + width_intercept,
                        end_line.independent_extent,
                        end_line.dependent_extent,
                    )
                )
            uses.setdefault(pair[0], []).append(
                f"{task['task_id']}#{slot['ordinal']}.start"
            )
            uses.setdefault(pair[1], []).append(
                f"{task['task_id']}#{slot['ordinal']}.end"
            )

    changes: list[tuple[str, LogicalLine, str, str]] = []
    outcomes: dict[str, dict[str, Any]] = {}
    for line_id, candidates in suggestions.items():
        original = _logical_line(record, pool[line_id], "boundary")
        endpoint_rows = np.asarray(
            [
                [
                    candidate.intercept,
                    float(candidate.value(candidate.independent_extent - 1)),
                ]
                for candidate in candidates
            ],
            dtype=np.float64,
        )
        disagreement = float(
            np.max(np.ptp(endpoint_rows, axis=0)) if len(endpoint_rows) > 1 else 0.0
        )
        if disagreement > 2.0:
            outcomes[line_id] = {
                "decision": "retained",
                "reason": "conflicting_same_source_width_constraints",
                "uses": sorted(set(uses.get(line_id, []))),
                "constraint_disagreement_px": disagreement,
                "human_review_status": "pending",
            }
            continue
        endpoints = np.median(endpoint_rows, axis=0)
        slope = float(
            (endpoints[1] - endpoints[0]) / max(original.independent_extent - 1, 1)
        )
        proposed = LogicalLine(
            slope,
            float(endpoints[0]),
            original.independent_extent,
            original.dependent_extent,
        )
        before = np.asarray(
            [original.intercept, original.value(original.independent_extent - 1)],
            dtype=np.float64,
        )
        delta = endpoints - before
        if float(np.max(np.abs(delta))) <= 0.25:
            outcomes[line_id] = {
                "decision": "retained",
                "reason": "already_matches_same_source_width",
                "uses": sorted(set(uses.get(line_id, []))),
                "endpoint_delta_px": [float(delta[0]), float(delta[1])],
                "human_review_status": "pending",
            }
            continue
        changes.append(
            (line_id, proposed, "boundary", WIDTH_REFINEMENT_ORIGIN)
        )
        outcomes[line_id] = {
            "decision": "moved_to_same_source_width",
            "reason": "robust_direct_frame_width_consensus",
            "uses": sorted(set(uses.get(line_id, []))),
            "endpoint_delta_px": [float(delta[0]), float(delta[1])],
            "human_review_status": "pending",
        }
    return changes, outcomes


def refine_record(
    record: dict[str, Any],
    raster: SourceRaster,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Refine one pending human draft without granting confirmation authority."""

    validate_annotation_record(record)
    if record["state"] == "user_confirmed":
        raise AnnotationError("confirmed annotation is immutable")
    if not line_basis_summary(record)["classification_complete"]:
        raise AnnotationError(
            "all active line bases must be classified before refinement"
        )
    if tuple(raster.canonical_extent) != (
        int(record["source"]["canonical_extent"]["width"]),
        int(record["source"]["canonical_extent"]["height"]),
    ):
        raise AnnotationError("refinement raster extent disagrees with annotation")
    updated = deepcopy(record)
    input_geometry_sha = canonical_record_sha256(geometry_snapshot(record))
    adjacency_before = _adjacency_signature(record)
    referenced = referenced_boundary_ids(record)
    active_lines = [
        *record["shared_edges"],
        *(
            line
            for line in record["boundary_pool"]
            if line["line_id"] in referenced
        ),
    ]
    outcomes: dict[str, dict[str, Any]] = {}
    for original_line in active_lines:
        line_id = str(original_line["line_id"])
        family = _line_family(record, line_id)
        basis = str(original_line["review_basis"])
        if basis == "human_width_estimate":
            continue
        current_line = next(
            line
            for line in [*updated["shared_edges"], *updated["boundary_pool"]]
            if line["line_id"] == line_id
        )
        fit = _fit_pixel_line(updated, raster, current_line, family)
        outcome = {
            "review_basis": basis,
            "method": "bounded_native_pixel_band",
            "decision": fit.decision,
            "reason": fit.reason,
            "center_delta_px": fit.center_delta_px,
            "endpoint_delta_px": list(fit.endpoint_delta_px),
            "sample_count": fit.sample_count,
            "support_count": fit.support_count,
            "support_fraction": fit.support_fraction,
            "score": fit.score,
            "runner_score": fit.runner_score,
            "uniqueness_margin": fit.uniqueness_margin,
            "gain_over_input": fit.gain_over_input,
            "search_radius_px": fit.search_radius_px,
            "human_review_status": "pending",
        }
        if fit.accepted:
            logical = _logical_line(updated, current_line, family)
            proposed = LogicalLine(
                fit.slope,
                fit.intercept,
                logical.independent_extent,
                logical.dependent_extent,
            )
            candidate, rejection = _try_geometry_change(
                updated,
                [(line_id, proposed, family, PIXEL_REFINEMENT_ORIGIN)],
                adjacency_before=adjacency_before,
            )
            if candidate is None:
                outcome.update(
                    {
                        "decision": "retained",
                        "reason": rejection,
                        "center_delta_px": 0.0,
                        "endpoint_delta_px": [0.0, 0.0],
                    }
                )
            else:
                updated = candidate
        outcomes[line_id] = outcome

    consensus, consensus_diagnostics = _direct_width_consensus(updated)
    estimated_ids = sorted(
        line["line_id"]
        for line in updated["boundary_pool"]
        if line["line_id"] in referenced
        and line["review_basis"] == "human_width_estimate"
    )
    if consensus is None:
        for line_id in estimated_ids:
            outcomes[line_id] = {
                "review_basis": "human_width_estimate",
                "method": "same_source_direct_frame_width",
                "decision": "retained",
                "reason": consensus_diagnostics["status"],
                "human_review_status": "pending",
            }
    else:
        changes, width_outcomes = _width_estimate_changes(updated, consensus)
        for line_id in estimated_ids:
            outcome = width_outcomes.get(
                line_id,
                {
                    "decision": "retained",
                    "reason": "estimated_line_has_no_active_frame_use",
                    "human_review_status": "pending",
                },
            )
            outcome.update(
                {
                    "review_basis": "human_width_estimate",
                    "method": "same_source_direct_frame_width",
                }
            )
            outcomes[line_id] = outcome
        if changes:
            candidate, rejection = _try_geometry_change(
                updated,
                changes,
                adjacency_before=adjacency_before,
            )
            if candidate is None:
                changed_ids = {item[0] for item in changes}
                for line_id in changed_ids:
                    outcomes[line_id].update(
                        {
                            "decision": "retained",
                            "reason": rejection,
                            "endpoint_delta_px": [0.0, 0.0],
                        }
                    )
            else:
                updated = candidate

    output_geometry_sha = canonical_record_sha256(geometry_snapshot(updated))
    input_lines = {
        line["line_id"]: line
        for line in [*record["shared_edges"], *record["boundary_pool"]]
    }
    output_lines = {
        line["line_id"]: line
        for line in [*updated["shared_edges"], *updated["boundary_pool"]]
    }
    for line_id, outcome in outcomes.items():
        outcome["input_points_raw"] = deepcopy(input_lines[line_id]["points_raw"])
        outcome["output_points_raw"] = deepcopy(output_lines[line_id]["points_raw"])
    moved = sorted(
        line_id
        for line_id, outcome in outcomes.items()
        if str(outcome["decision"]).startswith("moved_to_")
    )
    retained = sorted(set(outcomes) - set(moved))
    refinement = {
        "refinement_revision": REFINEMENT_REVISION,
        "generated_at_utc": utc_now(),
        "authority": "proposal_only_requires_native_pixel_human_review",
        "human_review_state": "pending",
        "input_geometry_sha256": input_geometry_sha,
        "output_geometry_sha256": output_geometry_sha,
        "current_geometry_sha256": output_geometry_sha,
        "line_count": len(outcomes),
        "moved_line_count": len(moved),
        "retained_line_count": len(retained),
        "moved_line_ids": moved,
        "retained_line_ids": retained,
        "width_consensus": consensus_diagnostics,
        "lines": dict(sorted(outcomes.items())),
    }
    updated["diagnostics"]["refinement"] = refinement
    updated["revision"] = int(record["revision"]) + 1
    updated["state"] = "human_adjusted"
    updated["reviewed_task_ids"] = []
    updated["confirmation"] = None
    validate_annotation_record(updated)
    return updated, refinement
