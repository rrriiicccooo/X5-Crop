"""Independent, bounded pixel proposals for human source annotation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
import math
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import least_squares
from scipy.signal import find_peaks

from x5crop.formats import format_spec

from .imaging import SourceRaster, orientation_record
from .model import (
    ANNOTATION_SCHEMA,
    AnnotationError,
    CLIENT_EDITABLE_SLOT_KINDS,
    COORDINATE_SYSTEM,
    LINE_REVIEW_BASES,
    MACHINE_ORIGIN,
    RED_MARKUP_ORIGIN,
    SLOT_KINDS,
    display_to_raw_point,
    frame_polygons_display,
    raw_to_display_point,
    refresh_adjacency_kinds,
    referenced_boundary_ids,
    slot_boundary_ids,
    validate_annotation_record,
)


PROPOSAL_REVISION = "independent_bounded_gradient_template_v1"
SOURCE_REFERENCE_MAPPING_REVISION = "max_count_monotonic_frame_subset_v1"


@dataclass(frozen=True)
class LogicalFit:
    shared: tuple[tuple[float, float], tuple[float, float]]
    boundaries: tuple[tuple[float, float], ...]
    boundary_scores: tuple[float, ...]
    boundary_source_constrained: tuple[bool, ...]
    template_score: float
    expected_width: float


def _robust_line(independent: np.ndarray, dependent: np.ndarray) -> tuple[float, float, float]:
    if len(independent) < 8:
        raise ValueError("line refinement has insufficient support")
    initial = np.polyfit(independent, dependent, 1)

    def residual(parameters: np.ndarray) -> np.ndarray:
        return parameters[0] * independent + parameters[1] - dependent

    result = least_squares(
        residual,
        initial,
        loss="soft_l1",
        f_scale=1.25,
        max_nfev=180,
    )
    slope, intercept = (float(value) for value in result.x)
    raw = dependent - (slope * independent + intercept)
    center = float(np.median(raw))
    mad = float(np.median(np.abs(raw - center)))
    keep = np.abs(raw - center) <= max(2.5, 5.0 * 1.4826 * mad)
    if int(np.count_nonzero(keep)) >= 8 and not np.all(keep):
        return _robust_line(independent[keep], dependent[keep])
    return slope, intercept, mad


def _shift_support(profile: np.ndarray, shift: float) -> float:
    offset = int(round(shift))
    if offset <= 1 or offset >= len(profile) - 1:
        return 0.0
    products = profile[:-offset] * profile[offset:]
    retain = min(len(products), 32)
    if retain <= 0:
        return 0.0
    return float(np.mean(np.partition(products, -retain)[-retain:]))


def _choose_shared_pair(
    gray: np.ndarray,
    *,
    format_id: str,
    count: int,
) -> tuple[int, int, np.ndarray]:
    height, width = gray.shape
    blurred = cv2.GaussianBlur(gray, (0, 0), 1.15)
    gradient = np.abs(cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3))
    margin = max(2, int(round(width * 0.025)))
    score = np.quantile(gradient[:, margin : width - margin], 0.64, axis=1)
    score = gaussian_filter1d(score.astype(np.float64), 1.2)
    minimum_peak_distance = max(2, int(round(height * 0.025)))
    peaks, _ = find_peaks(score, distance=minimum_peak_distance)
    if len(peaks) < 2:
        peaks = np.argsort(score)[-max(8, height // 30) :]
    low_candidates = [int(value) for value in peaks if 0.015 * height <= value <= 0.32 * height]
    high_candidates = [int(value) for value in peaks if 0.68 * height <= value <= 0.985 * height]
    if not low_candidates or not high_candidates:
        return int(round(height * 0.13)), int(round(height * 0.87)), gradient

    median = float(np.median(score))
    scale = max(float(np.quantile(score, 0.95) - median), 1.0e-6)
    low_candidates = sorted(
        set(
            sorted(low_candidates, key=lambda value: float(score[value]), reverse=True)[:8]
            + sorted(low_candidates)[:6]
        )
    )
    high_candidates = sorted(
        set(
            sorted(high_candidates, key=lambda value: float(score[value]), reverse=True)[:8]
            + sorted(high_candidates, reverse=True)[:6]
        )
    )
    longitudinal_gradient = np.abs(
        cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    )
    broad_low = max(0, int(round(height * 0.10)))
    broad_high = min(height, int(round(height * 0.90)))
    long_profile = _normalized_profile(
        np.quantile(longitudinal_gradient[broad_low:broad_high, :], 0.72, axis=0)
    )
    long_profile = cv2.dilate(
        long_profile.astype(np.float32)[None, :],
        np.ones((1, 5), dtype=np.uint8),
    )[0].astype(np.float64)
    physical = format_spec(format_id).frame
    ratio = physical.frame_width_mm / physical.frame_height_mm
    gap_ratio = (
        physical.format_gap_prior_mm / physical.frame_height_mm
        if physical.format_gap_prior_mm is not None
        else 0.04 * ratio
    )
    best: tuple[float, int, int] | None = None
    for low in low_candidates:
        for high in high_candidates:
            separation = (high - low) / height
            if not 0.48 <= separation <= 0.98:
                continue
            midpoint = (high + low) / (2.0 * height)
            evidence = (score[low] + score[high] - 2.0 * median) / scale
            cross_span = high - low
            expected_width = cross_span * ratio
            width_support = _shift_support(long_profile, expected_width)
            pitch_support = (
                _shift_support(long_profile, expected_width + cross_span * gap_ratio)
                if count > 1
                else width_support
            )
            objective = (
                0.42 * evidence
                + 1.35 * width_support
                + 0.55 * pitch_support
                - 0.65 * abs(separation - 0.78)
                - 0.55 * abs(midpoint - 0.5)
            )
            candidate = (float(objective), low, high)
            if best is None or candidate > best:
                best = candidate
    if best is None:
        return int(round(height * 0.13)), int(round(height * 0.87)), gradient
    return best[1], best[2], gradient


def _refine_shared_line(
    gradient: np.ndarray,
    seed: int,
    *,
    inward_direction: int,
    independent_range: tuple[float, float] | None = None,
) -> tuple[float, float, float]:
    height, width = gradient.shape
    radius = max(4, int(round(height * 0.035)))
    range_start, range_stop = independent_range or (0.0, float(width - 1))
    range_start = max(0.0, min(float(width - 1), range_start))
    range_stop = max(range_start + 1.0, min(float(width - 1), range_stop))
    x_values = np.linspace(
        range_start,
        range_stop,
        min(240, max(16, int(round(range_stop - range_start)) + 1)),
        dtype=np.int64,
    )
    y_values: list[float] = []
    strengths: list[float] = []
    for x in x_values:
        start = max(0, seed - radius)
        stop = min(height, seed + radius + 1)
        signed = gradient[start:stop, x] * float(inward_direction)
        response = np.maximum(signed, 0.0)
        absolute = np.abs(gradient[start:stop, x])
        if float(np.max(response)) < 0.12 * max(float(np.max(absolute)), 1.0):
            response = absolute
        offset = int(np.argmax(response))
        y_values.append(float(start + offset))
        strengths.append(float(response[offset]))
    strength_array = np.asarray(strengths)
    retain = strength_array >= np.quantile(strength_array, 0.35)
    return _robust_line(
        x_values[retain].astype(np.float64),
        np.asarray(y_values)[retain],
    )


def _normalized_profile(values: np.ndarray) -> np.ndarray:
    low, high = np.quantile(values, (0.30, 0.995))
    if high <= low:
        return np.zeros_like(values, dtype=np.float64)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def _template_positions(
    start_profile: np.ndarray,
    end_profile: np.ndarray,
    *,
    count: int,
    expected_width: float,
    expected_gap: float,
) -> tuple[np.ndarray, float]:
    if len(start_profile) != len(end_profile):
        raise ValueError("directional boundary profiles disagree")
    length = len(start_profile)
    radius = max(2, int(round(expected_width * 0.014)))
    kernel = np.ones((1, 2 * radius + 1), dtype=np.uint8)
    local_start = cv2.dilate(
        start_profile.astype(np.float32)[None, :], kernel
    )[0].astype(np.float64)
    local_end = cv2.dilate(
        end_profile.astype(np.float32)[None, :], kernel
    )[0].astype(np.float64)
    if count == 1:
        best: tuple[float, float, float] | None = None
        widths = np.linspace(expected_width * 0.94, expected_width * 1.06, 31)
        for width in widths:
            maximum_start = int(math.floor(length - 1 - width))
            if maximum_start < 0:
                continue
            starts = np.arange(maximum_start + 1, dtype=np.float64)
            stops = starts + width
            scores = np.interp(starts, np.arange(length), local_start) + np.interp(
                stops,
                np.arange(length),
                local_end,
            )
            index = int(np.argmax(scores))
            candidate = (float(scores[index]), float(starts[index]), float(width))
            if best is None or candidate > best:
                best = candidate
        if best is None:
            raise ValueError("one-frame template cannot fit the source")
        return np.asarray([best[1], best[1] + best[2]]), best[0] / 2.0

    nominal_pitch = expected_width + expected_gap
    pitches = np.linspace(nominal_pitch * 0.955, nominal_pitch * 1.045, 61)
    axis = np.arange(length, dtype=np.float64)
    best_result: tuple[float, float, float] | None = None
    for pitch in pitches:
        span = (count - 1) * pitch + expected_width
        maximum_start = int(math.floor(length - 1 - span))
        if maximum_start < 0:
            continue
        starts = np.arange(maximum_start + 1, dtype=np.float64)
        offsets = np.asarray(
            [
                value
                for index in range(count)
                for value in (index * pitch, index * pitch + expected_width)
            ],
        )
        sampled = np.stack(
            [
                np.interp(
                    starts + offset,
                    axis,
                    local_start if role_index % 2 == 0 else local_end,
                )
                for role_index, offset in enumerate(offsets)
            ],
            axis=0,
        )
        # Weak or blank slots remain possible, but a proposal should prefer a
        # placement supported by more than one exceptionally strong edge.
        scores = np.mean(sampled, axis=0) + 0.18 * np.quantile(sampled, 0.25, axis=0)
        index = int(np.argmax(scores))
        candidate = (float(scores[index]), float(starts[index]), float(pitch))
        if best_result is None or candidate > best_result:
            best_result = candidate
    if best_result is None:
        raise ValueError("explicit-count template cannot fit the source")
    score, start, pitch = best_result
    positions = np.asarray(
        [
            value
            for index in range(count)
            for value in (start + index * pitch, start + index * pitch + expected_width)
        ],
        dtype=np.float64,
    )
    return positions, score


def _refine_boundary_line(
    gradient: np.ndarray,
    position: float,
    low_line: tuple[float, float],
    high_line: tuple[float, float],
    expected_width: float,
    inward_direction: int,
) -> tuple[float, float, float, float]:
    height, width = gradient.shape
    midpoint_x = 0.5 * (width - 1)
    low_y = low_line[0] * midpoint_x + low_line[1]
    high_y = high_line[0] * midpoint_x + high_line[1]
    start_y = max(0, int(math.floor(low_y + 0.04 * (high_y - low_y))))
    stop_y = min(height - 1, int(math.ceil(high_y - 0.04 * (high_y - low_y))))
    if stop_y - start_y < 8:
        start_y, stop_y = 0, height - 1
    y_values = np.linspace(start_y, stop_y, min(180, stop_y - start_y + 1), dtype=np.int64)
    mean_shared_slope = 0.5 * (low_line[0] + high_line[0])
    seed_slope = -mean_shared_slope
    center_y = 0.5 * (start_y + stop_y)
    radius = max(4, int(round(expected_width * 0.05)))
    x_values: list[float] = []
    strengths: list[float] = []
    for y in y_values:
        seed = position + seed_slope * (float(y) - center_y)
        start_x = max(0, int(round(seed)) - radius)
        stop_x = min(width, int(round(seed)) + radius + 1)
        signed = gradient[y, start_x:stop_x] * float(inward_direction)
        response = np.maximum(signed, 0.0)
        absolute = np.abs(gradient[y, start_x:stop_x])
        if float(np.max(response)) < 0.12 * max(float(np.max(absolute)), 1.0):
            response = absolute
        offsets = np.arange(start_x, stop_x, dtype=np.float64) - seed
        normalized = response / max(float(np.max(response)), 1.0)
        objective = normalized - 0.45 * np.square(offsets / max(radius, 1))
        offset = int(np.argmax(objective))
        x_values.append(float(start_x + offset))
        strengths.append(float(response[offset]))
    strength_array = np.asarray(strengths)
    retain = strength_array >= np.quantile(strength_array, 0.42)
    try:
        slope, intercept, mad = _robust_line(
            y_values[retain].astype(np.float64),
            np.asarray(x_values)[retain],
        )
    except ValueError:
        slope = seed_slope
        intercept = float(position - seed_slope * center_y)
        mad = math.inf
    return slope, intercept, mad, float(np.median(strength_array))


def _constrain_boundary_line_to_source(
    line: tuple[float, float],
    shared: tuple[tuple[float, float], tuple[float, float]],
    maximum_long_coordinate: float,
    fallback_position: float,
) -> tuple[tuple[float, float], bool]:
    """Translate a proposal line so both shared-edge intersections stay in source."""

    slope, intercept = line
    lower_delta = -math.inf
    upper_delta = math.inf
    for shared_slope, shared_intercept in shared:
        denominator = 1.0 - slope * shared_slope
        if abs(denominator) < 1.0e-9:
            return (0.0, float(np.clip(fallback_position, 0.0, maximum_long_coordinate))), True
        base = (slope * shared_intercept + intercept) / denominator
        coefficient = 1.0 / denominator
        first = (0.0 - base) / coefficient
        second = (maximum_long_coordinate - base) / coefficient
        lower_delta = max(lower_delta, min(first, second))
        upper_delta = min(upper_delta, max(first, second))
    if lower_delta > upper_delta:
        return (0.0, float(np.clip(fallback_position, 0.0, maximum_long_coordinate))), True
    delta = min(max(0.0, lower_delta), upper_delta)
    return (slope, intercept + delta), abs(delta) > 1.0e-9


def _fit_task(
    gray: np.ndarray,
    *,
    format_id: str,
    count: int,
    shared: tuple[tuple[float, float], tuple[float, float]],
) -> LogicalFit:
    low_line, high_line = shared
    height, width = gray.shape
    center_x = 0.5 * (width - 1)
    cross_span = (
        high_line[0] * center_x + high_line[1]
        - low_line[0] * center_x
        - low_line[1]
    )
    physical = format_spec(format_id).frame
    expected_width = cross_span * physical.frame_width_mm / physical.frame_height_mm
    gap_mm = physical.format_gap_prior_mm
    expected_gap = (
        cross_span * gap_mm / physical.frame_height_mm
        if gap_mm is not None
        else expected_width * 0.04
    )
    blurred = cv2.GaussianBlur(gray, (0, 0), 1.05)
    signed_gradient = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gradient = np.abs(signed_gradient)
    low_values = low_line[0] * np.arange(width) + low_line[1]
    high_values = high_line[0] * np.arange(width) + high_line[1]
    low = max(0, int(math.ceil(np.quantile(low_values, 0.90) + 0.04 * cross_span)))
    high = min(
        height,
        int(math.floor(np.quantile(high_values, 0.10) - 0.04 * cross_span)),
    )
    if high - low < 4:
        low, high = 0, height
    start_values = np.quantile(
        np.maximum(signed_gradient[low:high, :], 0.0),
        0.72,
        axis=0,
    )
    end_values = np.quantile(
        np.maximum(-signed_gradient[low:high, :], 0.0),
        0.72,
        axis=0,
    )
    start_profile = gaussian_filter1d(_normalized_profile(start_values), 1.1)
    end_profile = gaussian_filter1d(_normalized_profile(end_values), 1.1)
    positions, template_score = _template_positions(
        start_profile,
        end_profile,
        count=count,
        expected_width=expected_width,
        expected_gap=expected_gap,
    )
    lines: list[tuple[float, float]] = []
    scores: list[float] = []
    constrained: list[bool] = []
    strength_scale = max(float(np.quantile(gradient, 0.95)), 1.0e-6)
    for boundary_index, position in enumerate(positions):
        slope, intercept, mad, strength = _refine_boundary_line(
            signed_gradient,
            float(position),
            low_line,
            high_line,
            expected_width,
            inward_direction=1 if boundary_index % 2 == 0 else -1,
        )
        bounded_line, was_constrained = _constrain_boundary_line_to_source(
            (slope, intercept),
            shared,
            float(width - 1),
            float(position),
        )
        lines.append(bounded_line)
        scores.append(float(strength / strength_scale))
        constrained.append(was_constrained)
    return LogicalFit(
        shared=shared,
        boundaries=tuple(lines),
        boundary_scores=tuple(scores),
        boundary_source_constrained=tuple(constrained),
        template_score=float(template_score),
        expected_width=float(expected_width),
    )


def _line_points_display(
    *,
    line: tuple[float, float],
    family: str,
    horizontal: bool,
    analysis_width: int,
    analysis_height: int,
    display_width: int,
    display_height: int,
) -> list[list[float]]:
    slope, intercept = line
    long_scale = (max(display_width, display_height) - 1) / max(analysis_width - 1, 1)
    cross_scale = (min(display_width, display_height) - 1) / max(analysis_height - 1, 1)
    if family == "shared":
        first_cross = intercept * cross_scale
        second_cross = (slope * (analysis_width - 1) + intercept) * cross_scale
        if horizontal:
            return [[0.0, first_cross], [float(display_width - 1), second_cross]]
        return [[first_cross, 0.0], [second_cross, float(display_height - 1)]]
    first_long = intercept * long_scale
    second_long = (slope * (analysis_height - 1) + intercept) * long_scale
    if horizontal:
        return [[first_long, 0.0], [second_long, float(display_height - 1)]]
    return [[0.0, first_long], [float(display_width - 1), second_long]]


def _new_line(
    record: dict[str, Any],
    *,
    line_id: str,
    role: str,
    points_display: list[list[float]],
    origin: str,
    review_basis: str = "unclassified",
) -> dict[str, Any]:
    return {
        "line_id": line_id,
        "role": role,
        "points_raw": [display_to_raw_point(record, point) for point in points_display],
        "origin": origin,
        "review_basis": review_basis,
    }


def propose_record(
    *,
    raster: SourceRaster,
    source_relative_path: str,
    source_sha256: str,
    canonical_sample_id: str,
    format_id: str,
    tasks: Iterable[dict[str, Any]],
    review_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], np.ndarray]:
    task_rows = sorted(tasks, key=lambda item: (int(item["count"]), item["sample_id"]))
    analysis_rgb, levels = raster.analysis_rgb8()
    analysis_gray = cv2.cvtColor(analysis_rgb, cv2.COLOR_RGB2GRAY)
    horizontal = analysis_gray.shape[1] >= analysis_gray.shape[0]
    logical_gray = analysis_gray if horizontal else analysis_gray.T
    low_seed, high_seed, _ = _choose_shared_pair(
        logical_gray,
        format_id=format_id,
        count=max(int(row["count"]) for row in task_rows),
    )
    signed_cross_gradient = cv2.Sobel(
        cv2.GaussianBlur(logical_gray, (0, 0), 1.15),
        cv2.CV_32F,
        0,
        1,
        ksize=3,
    )
    low_line = _refine_shared_line(
        signed_cross_gradient,
        low_seed,
        inward_direction=1,
    )
    high_line = _refine_shared_line(
        signed_cross_gradient,
        high_seed,
        inward_direction=-1,
    )
    shared = ((low_line[0], low_line[1]), (high_line[0], high_line[1]))
    fits = {
        row["sample_id"]: _fit_task(
            logical_gray,
            format_id=format_id,
            count=int(row["count"]),
            shared=shared,
        )
        for row in task_rows
    }
    references = [
        line[0] * (logical_gray.shape[0] - 1) / 2.0 + line[1]
        for fit in fits.values()
        for line in fit.boundaries
    ]
    reference_width = max(fit.expected_width for fit in fits.values())
    support_range = (
        min(references) - 0.04 * reference_width,
        max(references) + 0.04 * reference_width,
    )
    low_line = _refine_shared_line(
        signed_cross_gradient,
        low_seed,
        inward_direction=1,
        independent_range=support_range,
    )
    high_line = _refine_shared_line(
        signed_cross_gradient,
        high_seed,
        inward_direction=-1,
        independent_range=support_range,
    )
    shared = ((low_line[0], low_line[1]), (high_line[0], high_line[1]))
    fits = {
        row["sample_id"]: _fit_task(
            logical_gray,
            format_id=format_id,
            count=int(row["count"]),
            shared=shared,
        )
        for row in task_rows
    }
    unresolved: list[dict[str, Any]] = []
    if max(float(low_line[2]), float(high_line[2])) > 3.0:
        unresolved.append(
            {
                "kind": "shared_edge_fit_high_residual",
                "action": "inspect_both_shared_edges_at_native_pixels",
            }
        )
    for task_identity, fit in fits.items():
        source_constrained = [
            index + 1
            for index, constrained in enumerate(fit.boundary_source_constrained)
            if constrained
        ]
        if source_constrained:
            unresolved.append(
                {
                    "kind": "proposal_boundary_constrained_to_source",
                    "task_id": task_identity,
                    "boundary_role_indices": source_constrained,
                    "action": "inspect_source_outer_boundary_at_native_pixels",
                }
            )
        if fit.template_score < 0.58:
            unresolved.append(
                {
                    "kind": "weak_directional_template_alignment",
                    "task_id": task_identity,
                    "action": "inspect_every_boundary_pair",
                }
            )
        weak = [
            index + 1
            for index, strength in enumerate(fit.boundary_scores)
            if strength < 0.30
        ]
        if weak:
            unresolved.append(
                {
                    "kind": "weak_local_boundary_evidence",
                    "task_id": task_identity,
                    "boundary_role_indices": weak,
                    "action": "use_native_pixel_tile_and_adjust",
                }
            )
    raw_width, raw_height = raster.raw_extent
    display_width, display_height = raster.canonical_extent
    mapping = orientation_record(raster.mapping)
    record: dict[str, Any] = {
        "annotation_schema": ANNOTATION_SCHEMA,
        "revision": 1,
        "state": "machine_proposal",
        "source": {
            "canonical_sample_id": canonical_sample_id,
            "relative_path": source_relative_path,
            "sha256": source_sha256,
            "raw_extent": {"width": raw_width, "height": raw_height},
            "canonical_extent": {"width": display_width, "height": display_height},
            "orientation_mapping": mapping,
        },
        "format_id": format_id,
        "strip_axis_display": "horizontal" if horizontal else "vertical",
        "coordinate_system": COORDINATE_SYSTEM,
        "origin": MACHINE_ORIGIN,
        "shared_edges": [],
        "boundary_pool": [],
        "tasks": [],
        "diagnostics": {
            "proposal_revision": PROPOSAL_REVISION,
            "analysis_extent": {
                "width": int(analysis_rgb.shape[1]),
                "height": int(analysis_rgb.shape[0]),
            },
            "render_levels": levels,
            "shared_fit_mad_analysis_px": [float(low_line[2]), float(high_line[2])],
            "task_fits": {
                identity: {
                    "template_score": fit.template_score,
                    "expected_frame_width_analysis_px": fit.expected_width,
                    "boundary_strengths": list(fit.boundary_scores),
                    "boundary_source_constrained": list(
                        fit.boundary_source_constrained
                    ),
                }
                for identity, fit in fits.items()
            },
            "unresolved": unresolved,
            "authority": "proposal_only_requires_native_pixel_human_review",
            "review_context": deepcopy(review_context) if review_context else {},
        },
        "reviewed_task_ids": [],
        "confirmation": None,
    }
    analysis_height, analysis_width = logical_gray.shape
    for index, line in enumerate(shared):
        points = _line_points_display(
            line=line,
            family="shared",
            horizontal=horizontal,
            analysis_width=analysis_width,
            analysis_height=analysis_height,
            display_width=display_width,
            display_height=display_height,
        )
        record["shared_edges"].append(
            _new_line(
                record,
                line_id=f"E{index + 1}",
                role="short_low" if index == 0 else "short_high",
                points_display=points,
                origin=MACHINE_ORIGIN,
            )
        )

    pool_positions: list[float] = []
    pool_ids: list[str] = []
    for row in task_rows:
        fit = fits[row["sample_id"]]
        task_boundary_ids: list[str] = []
        for line in fit.boundaries:
            reference = line[0] * (analysis_height - 1) / 2.0 + line[1]
            tolerance = max(1.5, fit.expected_width * 0.006)
            match = next(
                (
                    index
                    for index, value in enumerate(pool_positions)
                    if (
                        abs(reference - value) <= tolerance
                        and pool_ids[index] not in task_boundary_ids
                    )
                ),
                None,
            )
            if match is None:
                line_id = f"B{len(pool_ids) + 1:03d}"
                points = _line_points_display(
                    line=line,
                    family="boundary",
                    horizontal=horizontal,
                    analysis_width=analysis_width,
                    analysis_height=analysis_height,
                    display_width=display_width,
                    display_height=display_height,
                )
                record["boundary_pool"].append(
                    _new_line(
                        record,
                        line_id=line_id,
                        role="long_boundary",
                        points_display=points,
                        origin=MACHINE_ORIGIN,
                    )
                )
                pool_positions.append(reference)
                pool_ids.append(line_id)
            else:
                line_id = pool_ids[match]
            task_boundary_ids.append(line_id)
        record["tasks"].append(
            {
                "task_id": row["sample_id"],
                "sample_id": row["sample_id"],
                "source_relative_path": row["source_relative_path"],
                "count": int(row["count"]),
                "slots": [
                    {
                        "ordinal": index + 1,
                        "slot_kind": "image",
                        "reference_geometry": {
                            "kind": "boundary_pair",
                            "start_boundary_id": task_boundary_ids[index * 2],
                            "end_boundary_id": task_boundary_ids[index * 2 + 1],
                        },
                    }
                    for index in range(int(row["count"]))
                ],
                "adjacencies": [
                    {
                        "left_ordinal": index,
                        "right_ordinal": index + 1,
                        "kind": "separator",
                    }
                    for index in range(1, int(row["count"]))
                ],
            }
        )
    refresh_adjacency_kinds(record)
    record = canonicalize_source_reference_mappings(record)
    validate_annotation_record(record)
    return record, analysis_rgb


def _red_delta_mask(source: np.ndarray, marked: np.ndarray) -> np.ndarray:
    if source.shape[:2] != marked.shape[:2] or min(source.shape[-1], marked.shape[-1]) < 3:
        raise ValueError("red markup draft does not preserve source raster geometry")

    def channel_scale(array: np.ndarray) -> float:
        if np.issubdtype(array.dtype, np.integer):
            return float(np.iinfo(array.dtype).max)
        maximum = float(np.nanmax(array))
        return max(1.0, maximum)

    height, width = source.shape[:2]
    mask = np.zeros((height, width), dtype=bool)
    source_scale = channel_scale(source)
    marked_scale = channel_scale(marked)
    for start in range(0, height, 256):
        stop = min(height, start + 256)
        original = source[start:stop, :, :3].astype(np.float32) / source_scale
        overlay = marked[start:stop, :, :3].astype(np.float32) / marked_scale
        change = np.max(np.abs(overlay - original), axis=-1)
        red_dominance = overlay[..., 0] - np.maximum(
            overlay[..., 1], overlay[..., 2]
        )
        mask[start:stop] = (
            (overlay[..., 0] >= 0.35)
            & (red_dominance >= 0.12)
            & (change >= 0.02)
        )
    return mask


def _runs(indices: np.ndarray, *, allowed_gap: int = 2) -> list[tuple[int, int]]:
    if not len(indices):
        return []
    result: list[tuple[int, int]] = []
    start = previous = int(indices[0])
    for raw in indices[1:]:
        value = int(raw)
        if value - previous > allowed_gap + 1:
            result.append((start, previous))
            start = value
        previous = value
    result.append((start, previous))
    return result


def _fit_red_band(
    logical: np.ndarray,
    *,
    slope: float,
    intercept: float,
    family: str,
    search_distance: float,
) -> tuple[float, float, float, int]:
    y, x = np.nonzero(logical)
    if family == "boundary":
        distance = np.abs(x - (slope * y + intercept))
        selected = distance <= search_distance
        independent = y[selected].astype(np.float64)
        dependent = x[selected].astype(np.float64)
    else:
        distance = np.abs(y - (slope * x + intercept))
        selected = distance <= search_distance
        independent = x[selected].astype(np.float64)
        dependent = y[selected].astype(np.float64)
    if len(independent) < 16:
        raise ValueError("red line seed has insufficient pixel support")
    unique = np.unique(independent)
    centers = np.asarray(
        [np.median(dependent[independent == value]) for value in unique],
        dtype=np.float64,
    )
    fitted_slope, fitted_intercept, mad = _robust_line(unique, centers)
    return fitted_slope, fitted_intercept, mad, int(len(unique))


def _cluster_hough_seeds(
    candidates: list[tuple[float, float, float, float]],
    *,
    cluster_gap: float,
) -> list[tuple[float, float, float, float]]:
    clusters: list[list[tuple[float, float, float, float]]] = []
    for candidate in sorted(candidates, key=lambda item: item[0]):
        if (
            not clusters
            or candidate[0]
            - float(np.median([item[0] for item in clusters[-1]]))
            > cluster_gap
        ):
            clusters.append([candidate])
        else:
            clusters[-1].append(candidate)
    result: list[tuple[float, float, float, float]] = []
    for cluster in clusters:
        weights = np.asarray([item[3] for item in cluster], dtype=np.float64)
        result.append(
            (
                float(np.average([item[0] for item in cluster], weights=weights)),
                float(np.average([item[1] for item in cluster], weights=weights)),
                float(np.average([item[2] for item in cluster], weights=weights)),
                float(np.sum(weights)),
            )
        )
    return result


def _hough_red_lines(
    logical: np.ndarray,
    *,
    family: str,
) -> list[dict[str, float]]:
    cross_length, axis_length = logical.shape
    if family == "boundary":
        minimum_length = max(32, int(round(cross_length * 0.32)))
        threshold = max(28, int(round(cross_length * 0.10)))
        maximum_gap = max(10, int(round(cross_length * 0.07)))
    else:
        minimum_length = max(48, int(round(axis_length * 0.12)))
        threshold = max(36, int(round(axis_length * 0.025)))
        maximum_gap = max(16, int(round(axis_length * 0.045)))
    hough = cv2.HoughLinesP(
        logical.astype(np.uint8) * 255,
        1.0,
        np.pi / 1800.0,
        threshold=threshold,
        minLineLength=minimum_length,
        maxLineGap=maximum_gap,
    )
    if hough is None:
        return []
    candidates: list[tuple[float, float, float, float]] = []
    maximum_slope = math.tan(math.radians(6.0))
    if family == "boundary":
        reference = 0.5 * (cross_length - 1)
        for raw in np.asarray(hough).reshape(-1, 4):
            x1, y1, x2, y2 = (float(value) for value in raw)
            independent_delta = y2 - y1
            if abs(independent_delta) < minimum_length:
                continue
            slope = (x2 - x1) / independent_delta
            if abs(slope) > maximum_slope:
                continue
            intercept = x1 - slope * y1
            candidates.append(
                (slope * reference + intercept, slope, intercept, abs(independent_delta))
            )
        cluster_gap = max(4.0, min(8.0, cross_length * 0.003))
        search_distance = max(5.0, min(9.0, cross_length * 0.004))
    else:
        reference = 0.5 * (axis_length - 1)
        for raw in np.asarray(hough).reshape(-1, 4):
            x1, y1, x2, y2 = (float(value) for value in raw)
            independent_delta = x2 - x1
            if abs(independent_delta) < minimum_length:
                continue
            slope = (y2 - y1) / independent_delta
            if abs(slope) > maximum_slope:
                continue
            intercept = y1 - slope * x1
            candidates.append(
                (slope * reference + intercept, slope, intercept, abs(independent_delta))
            )
        cluster_gap = max(4.0, min(9.0, cross_length * 0.004))
        search_distance = max(5.0, min(10.0, cross_length * 0.005))
    lines: list[dict[str, float]] = []
    for position, slope, intercept, coverage in _cluster_hough_seeds(
        candidates,
        cluster_gap=cluster_gap,
    ):
        try:
            fitted_slope, fitted_intercept, mad, support = _fit_red_band(
                logical,
                slope=slope,
                intercept=intercept,
                family=family,
                search_distance=search_distance,
            )
        except ValueError:
            continue
        fitted_position = (
            fitted_slope * (0.5 * (cross_length - 1)) + fitted_intercept
            if family == "boundary"
            else fitted_slope * (0.5 * (axis_length - 1)) + fitted_intercept
        )
        lines.append(
            {
                "position": float(fitted_position),
                "slope": float(fitted_slope),
                "intercept": float(fitted_intercept),
                "mad_px": float(mad),
                "support": float(max(support, coverage)),
            }
        )
    return sorted(lines, key=lambda item: item["position"])


def _projection_red_boundaries(logical: np.ndarray) -> list[dict[str, float]]:
    cross_length, axis_length = logical.shape
    projection = np.sum(logical, axis=0)
    threshold = max(24, int(round(cross_length * 0.04)))
    runs = _runs(np.flatnonzero(projection >= threshold), allowed_gap=2)
    maximum_band = max(24, int(round(axis_length * 0.01)))
    lines: list[dict[str, float]] = []
    for start, stop in runs:
        if stop - start + 1 > maximum_band:
            continue
        band_start = max(0, start - 3)
        band_stop = min(axis_length, stop + 4)
        band = logical[:, band_start:band_stop]
        y, local_x = np.nonzero(band)
        if len(y) < 16:
            continue
        x = local_x + band_start
        unique = np.unique(y)
        centers = np.asarray([np.median(x[y == value]) for value in unique])
        slope, intercept, mad = _robust_line(unique.astype(np.float64), centers)
        lines.append(
            {
                "position": float(slope * (0.5 * (cross_length - 1)) + intercept),
                "slope": float(slope),
                "intercept": float(intercept),
                "mad_px": float(mad),
                "support": float(len(unique)),
            }
        )
    return sorted(lines, key=lambda item: item["position"])


def _select_red_boundaries(
    logical: np.ndarray,
    *,
    maximum_roles: int,
    force_hough: bool,
) -> tuple[list[dict[str, float]], dict[str, int | str]]:
    projected = _projection_red_boundaries(logical)
    hough = (
        _hough_red_lines(logical, family="boundary")
        if force_hough or len(projected) != maximum_roles
        else []
    )
    if force_hough and hough:
        selected = hough
        method = "hough_for_typed_overlap"
    elif len(projected) > maximum_roles + 2 and hough:
        selected = hough
        method = "hough_rejected_projection_noise"
    elif len(projected) > maximum_roles and 0 < len(hough) <= maximum_roles:
        selected = hough
        method = "hough_resolved_extra_projection_strokes"
    elif len(hough) > len(projected) and len(hough) <= maximum_roles + 2:
        selected = hough
        method = "hough_recovered_close_strokes"
    else:
        selected = projected
        method = "axis_projection"
    return selected, {
        "method": method,
        "projection_count": len(projected),
        "hough_count": len(hough),
    }


def _red_shared_edges(logical: np.ndarray) -> list[dict[str, float]]:
    candidates = _hough_red_lines(logical, family="shared")
    if len(candidates) < 2:
        return []
    cross_length = logical.shape[0]
    eligible: list[tuple[float, int, int]] = []
    for low_index, low in enumerate(candidates):
        for high_index in range(low_index + 1, len(candidates)):
            high = candidates[high_index]
            separation = high["position"] - low["position"]
            if separation < cross_length * 0.35:
                continue
            score = low["support"] + high["support"]
            eligible.append((score, low_index, high_index))
    if not eligible:
        return []
    _score, low_index, high_index = max(eligible)
    return [candidates[low_index], candidates[high_index]]


def _machine_boundary_position(
    record: dict[str, Any],
    line: dict[str, Any],
) -> float:
    first, second = [
        raw_to_display_point(record, point) for point in line["points_raw"]
    ]
    if record["strip_axis_display"] == "horizontal":
        reference = 0.5 * (record["source"]["canonical_extent"]["height"] - 1)
        denominator = second[1] - first[1]
        return first[0] + (second[0] - first[0]) * (reference - first[1]) / denominator
    reference = 0.5 * (record["source"]["canonical_extent"]["width"] - 1)
    denominator = second[0] - first[0]
    return first[1] + (second[1] - first[1]) * (reference - first[0]) / denominator


def _task_role_ids(task: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for slot in task["slots"]:
        pair = slot_boundary_ids(slot)
        if pair is None:
            raise ValueError("red import requires the original machine boundary pair")
        result.extend(pair)
    return result


def _role_groups(
    count: int,
    *,
    contact_after: set[int],
    overlap_after: set[int],
    missing_slots: set[int],
) -> list[tuple[int, ...]]:
    if contact_after & overlap_after:
        raise ValueError("one adjacency cannot be both contact and overlap")
    missing_roles = {
        role
        for ordinal in missing_slots
        for role in (2 * (ordinal - 1), 2 * (ordinal - 1) + 1)
    }
    groups: list[tuple[int, ...]] = []
    role = 0
    while role < count * 2:
        if role in missing_roles:
            role += 1
            continue
        separator_ordinal = (role + 1) // 2 if role % 2 else None
        if role % 2 == 1 and separator_ordinal in contact_after:
            if role + 1 in missing_roles:
                raise ValueError("contact cannot cross a missing slot")
            groups.append((role, role + 1))
            role += 2
            continue
        if role % 2 == 1 and separator_ordinal in overlap_after:
            if role + 1 in missing_roles:
                raise ValueError("overlap cannot cross a missing slot")
            groups.extend(((role + 1,), (role,)))
            role += 2
            continue
        groups.append((role,))
        role += 1
    return groups


def _align_red_roles(
    role_positions: list[float],
    groups: list[tuple[int, ...]],
    observed: list[dict[str, float]],
) -> tuple[dict[int, int], list[int], list[int], float]:
    widths = [
        role_positions[index + 1] - role_positions[index]
        for index in range(0, len(role_positions), 2)
        if role_positions[index + 1] > role_positions[index]
    ]
    scale = max(float(np.median(widths)) if widths else 1.0, 1.0)
    group_count = len(groups)
    observed_count = len(observed)
    if group_count == observed_count:
        mapping = {
            role: observed_index
            for observed_index, group in enumerate(groups)
            for role in group
        }
        cost = sum(
            (
                (
                    observed[index]["position"]
                    - float(np.mean([role_positions[role] for role in group]))
                )
                / scale
            )
            ** 2
            for index, group in enumerate(groups)
        )
        return mapping, [], [], float(cost)
    costs = np.full((group_count + 1, observed_count + 1), np.inf)
    previous: dict[tuple[int, int], tuple[int, int, str]] = {}
    costs[0, 0] = 0.0
    for group_index in range(group_count + 1):
        for observed_index in range(observed_count + 1):
            current = float(costs[group_index, observed_index])
            if not math.isfinite(current):
                continue
            if group_index < group_count:
                skipped = current + 1.6 * len(groups[group_index])
                if skipped < costs[group_index + 1, observed_index]:
                    costs[group_index + 1, observed_index] = skipped
                    previous[(group_index + 1, observed_index)] = (
                        group_index,
                        observed_index,
                        "skip_group",
                    )
            if observed_index < observed_count:
                skipped = current + 1.8
                if skipped < costs[group_index, observed_index + 1]:
                    costs[group_index, observed_index + 1] = skipped
                    previous[(group_index, observed_index + 1)] = (
                        group_index,
                        observed_index,
                        "skip_observed",
                    )
            if group_index < group_count and observed_index < observed_count:
                expected = float(
                    np.mean([role_positions[index] for index in groups[group_index]])
                )
                normalized = (observed[observed_index]["position"] - expected) / scale
                matched = current + normalized * normalized
                if matched < costs[group_index + 1, observed_index + 1]:
                    costs[group_index + 1, observed_index + 1] = matched
                    previous[(group_index + 1, observed_index + 1)] = (
                        group_index,
                        observed_index,
                        "match",
                    )
    role_to_observed: dict[int, int] = {}
    skipped_groups: list[int] = []
    skipped_observed: list[int] = []
    cursor = (group_count, observed_count)
    while cursor != (0, 0):
        before_group, before_observed, operation = previous[cursor]
        group_index, observed_index = cursor
        if operation == "match":
            for role in groups[group_index - 1]:
                role_to_observed[role] = observed_index - 1
        elif operation == "skip_group":
            skipped_groups.extend(groups[group_index - 1])
        else:
            skipped_observed.append(observed_index - 1)
        cursor = (before_group, before_observed)
    return (
        role_to_observed,
        sorted(skipped_groups),
        sorted(skipped_observed),
        float(costs[group_count, observed_count]),
    )


def _task_markup_context(record: dict[str, Any], task_id: str) -> dict[str, Any]:
    review_context = record["diagnostics"].get("review_context", {})
    tasks = review_context.get("tasks", {}) if isinstance(review_context, dict) else {}
    value = tasks.get(task_id, {}) if isinstance(tasks, dict) else {}
    return value if isinstance(value, dict) else {}


def canonicalize_source_reference_mappings(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Map every count task onto one bounded source-level Frame set."""
    updated = deepcopy(record)

    def finalize() -> dict[str, Any]:
        refresh_adjacency_kinds(updated)
        return updated

    if len(updated["tasks"]) < 2:
        return finalize()
    canonical = min(
        updated["tasks"],
        key=lambda task: (
            -int(task["count"]),
            -sum(slot_boundary_ids(slot) is not None for slot in task["slots"]),
            str(task["task_id"]),
        ),
    )
    pool = {line["line_id"]: line for line in updated["boundary_pool"]}

    def frame_rows(task: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for slot in task["slots"]:
            pair = slot_boundary_ids(slot)
            if pair is None:
                continue
            start = _machine_boundary_position(updated, pool[pair[0]])
            end = _machine_boundary_position(updated, pool[pair[1]])
            rows.append(
                {
                    "slot": slot,
                    "pair": pair,
                    "position": 0.5 * (start + end),
                }
            )
        return rows

    canonical_rows = frame_rows(canonical)
    for task in updated["tasks"]:
        if task["task_id"] == canonical["task_id"]:
            continue
        task_rows = frame_rows(task)
        if len(task_rows) > len(canonical_rows):
            raise ValueError(
                f"{task['task_id']}: count task has more visible Frames than the source reference"
            )
        choices = combinations(range(len(canonical_rows)), len(task_rows))
        selected = min(
            choices,
            key=lambda indices: sum(
                (
                    task_rows[offset]["position"]
                    - canonical_rows[index]["position"]
                )
                ** 2
                for offset, index in enumerate(indices)
            ),
            default=(),
        )
        for task_row, canonical_index in zip(task_rows, selected, strict=True):
            canonical_row = canonical_rows[canonical_index]
            task_row["slot"]["reference_geometry"] = deepcopy(
                canonical_row["slot"]["reference_geometry"]
            )

    updated["diagnostics"]["source_reference_mapping"] = {
        "revision": SOURCE_REFERENCE_MAPPING_REVISION,
        "canonical_task_id": canonical["task_id"],
        "canonical_count": canonical["count"],
        "task_ids": [task["task_id"] for task in updated["tasks"]],
    }
    used_ids = referenced_boundary_ids(updated)
    updated["boundary_pool"] = [
        line
        for line in updated["boundary_pool"]
        if line["line_id"] in used_ids
        or line.get("review_basis") == "unresolved_red_stroke"
    ]
    return finalize()


def apply_review_context_line_bases(record: dict[str, Any]) -> dict[str, Any]:
    """Apply explicit user evidence-basis declarations to active annotation lines."""
    updated = deepcopy(record)
    review_context = updated["diagnostics"].get("review_context", {})
    if not isinstance(review_context, dict):
        raise ValueError("review context must be an object")
    shared_basis = review_context.get("shared_edge_review_basis", "unclassified")
    if shared_basis not in {"unclassified", "directly_visible"}:
        raise ValueError("shared-edge review basis is invalid")
    if shared_basis == "directly_visible":
        for line in updated["shared_edges"]:
            line["review_basis"] = shared_basis
    lines = {
        line["line_id"]: line
        for line in [*updated["shared_edges"], *updated["boundary_pool"]]
    }
    requested_by_line: dict[str, str] = {}
    for task in updated["tasks"]:
        context = _task_markup_context(updated, task["task_id"])
        hints = context.get("markup_import", {}) if isinstance(context, dict) else {}
        if not isinstance(hints, dict):
            raise ValueError(f"{task['task_id']}: markup_import must be an object")
        role_bases = hints.get("role_review_basis", {})
        if not isinstance(role_bases, dict):
            raise ValueError(f"{task['task_id']}: line review basis hints must be an object")
        valid_role_keys = {
            f"{ordinal}.{role}"
            for ordinal in range(1, int(task["count"]) + 1)
            for role in ("start", "end")
        }
        if not set(role_bases).issubset(valid_role_keys) or any(
            not isinstance(value, str) or value not in LINE_REVIEW_BASES
            for value in role_bases.values()
        ):
            raise ValueError(f"{task['task_id']}: line review basis hint is invalid")
        slots = {int(slot["ordinal"]): slot for slot in task["slots"]}
        for role_key, basis in role_bases.items():
            ordinal_text, role = str(role_key).split(".", 1)
            pair = slot_boundary_ids(slots[int(ordinal_text)])
            if pair is None:
                raise ValueError(
                    f"{task['task_id']}: line review basis cannot target a blank slot"
                )
            line_id = pair[0] if role == "start" else pair[1]
            previous = requested_by_line.get(line_id)
            if previous is not None and previous != basis:
                raise ValueError("one physical boundary has conflicting review bases")
            requested_by_line[line_id] = str(basis)
    for line_id, basis in requested_by_line.items():
        if line_id not in lines:
            raise ValueError("line review basis references an unknown boundary")
        lines[line_id]["review_basis"] = basis
    return updated


def apply_review_context_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Apply nonstructural user-declared slot and line evidence metadata."""
    updated = deepcopy(record)
    for task in updated["tasks"]:
        context = _task_markup_context(updated, task["task_id"])
        hints = context.get("markup_import", {}) if isinstance(context, dict) else {}
        if not isinstance(hints, dict):
            raise ValueError(f"{task['task_id']}: markup_import must be an object")
        raw_slot_kinds = hints.get("slot_kinds", {})
        if not isinstance(raw_slot_kinds, dict):
            raise ValueError(f"{task['task_id']}: slot kind hints must be an object")
        slot_kinds = {int(key): str(value) for key, value in raw_slot_kinds.items()}
        if not set(slot_kinds).issubset(range(1, int(task["count"]) + 1)) or any(
            value not in SLOT_KINDS for value in slot_kinds.values()
        ):
            raise ValueError(f"{task['task_id']}: slot kind hint is invalid")
        for slot in task["slots"]:
            requested = slot_kinds.get(int(slot["ordinal"]), slot["slot_kind"])
            if requested == slot["slot_kind"]:
                continue
            if (
                requested not in CLIENT_EDITABLE_SLOT_KINDS
                or slot["slot_kind"] not in CLIENT_EDITABLE_SLOT_KINDS
                or slot_boundary_ids(slot) is None
            ):
                raise ValueError(
                    f"{task['task_id']}: structural blank-slot changes require proposal preparation"
                )
            slot["slot_kind"] = requested
    updated = apply_review_context_line_bases(updated)
    validate_annotation_record(updated)
    return updated


def apply_review_context_slot_semantics(record: dict[str, Any]) -> dict[str, Any]:
    """Apply typed slot facts without promoting machine geometry to authority."""
    updated = deepcopy(record)
    blank_by_task: dict[str, set[int]] = {}
    for task in updated["tasks"]:
        context = _task_markup_context(updated, task["task_id"])
        hints = context.get("markup_import", {}) if isinstance(context, dict) else {}
        if not isinstance(hints, dict):
            raise ValueError(f"{task['task_id']}: markup_import must be an object")
        slot_kinds = {
            int(key): str(value) for key, value in hints.get("slot_kinds", {}).items()
        }
        if not set(slot_kinds).issubset(range(1, int(task["count"]) + 1)) or any(
            value not in SLOT_KINDS for value in slot_kinds.values()
        ):
            raise ValueError(f"{task['task_id']}: slot kind hint is invalid")
        blank_ordinals: set[int] = set()
        for slot in task["slots"]:
            kind = slot_kinds.get(int(slot["ordinal"]), str(slot["slot_kind"]))
            slot["slot_kind"] = kind
            if kind == "blank_exposure":
                slot["reference_geometry"] = {"kind": "not_applicable"}
                blank_ordinals.add(int(slot["ordinal"]))
        blank_by_task[task["task_id"]] = blank_ordinals
    updated = canonicalize_source_reference_mappings(updated)
    updated = apply_review_context_line_bases(updated)

    used_ids = referenced_boundary_ids(updated)
    updated["boundary_pool"] = [
        line
        for line in updated["boundary_pool"]
        if line["line_id"] in used_ids
        or line.get("review_basis") == "unresolved_red_stroke"
    ]
    unresolved: list[dict[str, Any]] = []
    for item in updated["diagnostics"].get("unresolved", []):
        if not isinstance(item, dict):
            unresolved.append(item)
            continue
        task_id = item.get("task_id")
        blank_ordinals = blank_by_task.get(str(task_id), set())
        if item.get("kind") in {
            "weak_local_boundary_evidence",
            "red_markup_missing_boundary_roles",
        }:
            blank_roles = {
                role
                for ordinal in blank_ordinals
                for role in (2 * ordinal - 1, 2 * ordinal)
            }
            retained = [
                role
                for role in item.get("boundary_role_indices", [])
                if role not in blank_roles
            ]
            if not retained:
                continue
            item = {**item, "boundary_role_indices": retained}
        unresolved.append(item)
    updated["diagnostics"]["unresolved"] = unresolved
    red_import = updated["diagnostics"].get("red_markup_import")
    if isinstance(red_import, dict):
        assignments = red_import.get("task_assignments")
        if isinstance(assignments, dict):
            for task_id, diagnostic in assignments.items():
                if not isinstance(diagnostic, dict):
                    continue
                blank_ordinals = blank_by_task.get(str(task_id), set())
                blank_roles = {
                    role
                    for ordinal in blank_ordinals
                    for role in (2 * ordinal - 1, 2 * ordinal)
                }
                diagnostic["machine_retained_role_indices"] = [
                    role
                    for role in diagnostic.get("machine_retained_role_indices", [])
                    if role not in blank_roles
                ]
                diagnostic["reference_geometry_not_applicable_ordinals"] = sorted(
                    blank_ordinals
                )
    validate_annotation_record(updated)
    return updated


def _frames_are_source_bounded(record: dict[str, Any]) -> bool:
    width = float(record["source"]["canonical_extent"]["width"])
    height = float(record["source"]["canonical_extent"]["height"])
    try:
        polygons = [
            polygon
            for task in record["tasks"]
            for polygon in frame_polygons_display(record, task)
        ]
    except (AnnotationError, ValueError, ZeroDivisionError):
        return False
    return all(
        -0.5 <= x <= width - 0.5 and -0.5 <= y <= height - 0.5
        for polygon in polygons
        for x, y in polygon
    )


def import_red_markup_draft(
    record: dict[str, Any],
    *,
    source_raster: SourceRaster,
    marked_path: Path,
    marked_relative_path: str,
) -> dict[str, Any]:
    with SourceRaster(marked_path) as marked_raster:
        if source_raster.canonical_extent != marked_raster.canonical_extent:
            raise ValueError("red markup draft was resized")
        canonical_mask = _red_delta_mask(
            source_raster.canonical,
            marked_raster.canonical,
        )
    horizontal = record["strip_axis_display"] == "horizontal"
    logical = canonical_mask if horizontal else canonical_mask.T
    if int(np.count_nonzero(logical)) < 500:
        raise ValueError("red markup draft contains no supported red line evidence")
    maximum_roles = max(int(task["count"]) * 2 for task in record["tasks"])
    force_hough = any(
        bool(
            _task_markup_context(record, task["task_id"])
            .get("markup_import", {})
            .get("overlap_after")
        )
        for task in record["tasks"]
    )
    observed, extraction = _select_red_boundaries(
        logical,
        maximum_roles=maximum_roles,
        force_hough=force_hough,
    )
    if not observed:
        raise ValueError("red markup draft contains no fitted long-axis boundary")
    shared = _red_shared_edges(logical)
    display_width = int(record["source"]["canonical_extent"]["width"])
    display_height = int(record["source"]["canonical_extent"]["height"])
    logical_height, logical_width = logical.shape
    updated = deepcopy(record)
    machine_shared_edges = deepcopy(record["shared_edges"])
    if len(shared) == 2:
        updated["shared_edges"] = []
        for index, line in enumerate(shared, start=1):
            points = _line_points_display(
                line=(line["slope"], line["intercept"]),
                family="shared",
                horizontal=horizontal,
                analysis_width=logical_width,
                analysis_height=logical_height,
                display_width=display_width,
                display_height=display_height,
            )
            updated["shared_edges"].append(
                _new_line(
                    updated,
                    line_id=f"E{index}",
                    role="short_low" if index == 1 else "short_high",
                    points_display=points,
                    origin=RED_MARKUP_ORIGIN,
                    review_basis="directly_visible",
                )
            )
    observed_lines: list[dict[str, Any]] = []
    for index, line in enumerate(observed, start=1):
        points = _line_points_display(
            line=(line["slope"], line["intercept"]),
            family="boundary",
            horizontal=horizontal,
            analysis_width=logical_width,
            analysis_height=logical_height,
            display_width=display_width,
            display_height=display_height,
        )
        observed_lines.append(
            _new_line(
                updated,
                line_id=f"R{index:03d}",
                role="long_boundary",
                points_display=points,
                origin=RED_MARKUP_ORIGIN,
                review_basis="directly_visible",
            )
        )
    original_pool = {line["line_id"]: line for line in record["boundary_pool"]}
    used_machine_ids: set[str] = set()
    used_observed_ids: set[str] = set()
    task_diagnostics: dict[str, Any] = {}
    for task in updated["tasks"]:
        context = _task_markup_context(updated, task["task_id"])
        hints = context.get("markup_import", {}) if isinstance(context, dict) else {}
        if not isinstance(hints, dict):
            raise ValueError(f"{task['task_id']}: markup_import must be an object")
        count = int(task["count"])
        contact_after = {int(value) for value in hints.get("contact_after", [])}
        overlap_after = {int(value) for value in hints.get("overlap_after", [])}
        missing_slots = {int(value) for value in hints.get("missing_slots", [])}
        slot_kinds = {
            int(key): str(value) for key, value in hints.get("slot_kinds", {}).items()
        }
        if not contact_after.issubset(range(1, count)):
            raise ValueError(f"{task['task_id']}: contact adjacency is out of range")
        if not overlap_after.issubset(range(1, count)):
            raise ValueError(f"{task['task_id']}: overlap adjacency is out of range")
        if not missing_slots.issubset(range(1, count + 1)):
            raise ValueError(f"{task['task_id']}: missing slot is out of range")
        if not set(slot_kinds).issubset(range(1, count + 1)) or any(
            value not in SLOT_KINDS for value in slot_kinds.values()
        ):
            raise ValueError(f"{task['task_id']}: slot kind hint is invalid")
        blank_ordinals = {
            ordinal
            for ordinal, kind in slot_kinds.items()
            if kind == "blank_exposure"
        }
        if not blank_ordinals.issubset(missing_slots):
            raise ValueError(
                f"{task['task_id']}: blank exposure must omit red boundary roles"
            )
        role_ids = _task_role_ids(task)
        role_positions = [
            _machine_boundary_position(updated, original_pool[line_id])
            for line_id in role_ids
        ]
        groups = _role_groups(
            count,
            contact_after=contact_after,
            overlap_after=overlap_after,
            missing_slots=missing_slots,
        )
        role_to_observed, skipped_roles, skipped_observed, cost = _align_red_roles(
            role_positions,
            groups,
            observed,
        )
        skipped_roles = sorted(
            set(skipped_roles)
            | {
                role
                for ordinal in missing_slots
                for role in (2 * (ordinal - 1), 2 * (ordinal - 1) + 1)
            }
        )
        mapped_role_ids: list[str] = []
        for role_index, machine_id in enumerate(role_ids):
            observed_index = role_to_observed.get(role_index)
            if observed_index is None:
                mapped_role_ids.append(machine_id)
                if role_index // 2 + 1 not in blank_ordinals:
                    used_machine_ids.add(machine_id)
                continue
            red_id = observed_lines[observed_index]["line_id"]
            mapped_role_ids.append(red_id)
            used_observed_ids.add(red_id)
        task["slots"] = [
            {
                "ordinal": index + 1,
                "slot_kind": slot_kinds.get(index + 1, "image"),
                "reference_geometry": (
                    {"kind": "not_applicable"}
                    if slot_kinds.get(index + 1) == "blank_exposure"
                    else {
                        "kind": "boundary_pair",
                        "start_boundary_id": mapped_role_ids[index * 2],
                        "end_boundary_id": mapped_role_ids[index * 2 + 1],
                    }
                ),
            }
            for index in range(count)
        ]
        task["adjacencies"] = [
            {
                "left_ordinal": index,
                "right_ordinal": index + 1,
                "kind": "not_applicable"
                if index in blank_ordinals or index + 1 in blank_ordinals
                else "separator",
            }
            for index in range(1, count)
        ]
        task_diagnostics[task["task_id"]] = {
            "matched_red_role_indices": sorted(index + 1 for index in role_to_observed),
            "machine_retained_role_indices": sorted(
                index + 1
                for index in skipped_roles
                if index // 2 + 1 not in blank_ordinals
            ),
            "reference_geometry_not_applicable_ordinals": sorted(blank_ordinals),
            "unmatched_red_stroke_indices": sorted(index + 1 for index in skipped_observed),
            "alignment_cost": cost,
        }
    for line in observed_lines:
        if line["line_id"] not in used_observed_ids:
            line["review_basis"] = "unresolved_red_stroke"
    updated["boundary_pool"] = [
        *observed_lines,
        *(deepcopy(original_pool[line_id]) for line_id in sorted(used_machine_ids)),
    ]
    applied_shared_edge_count = 0
    rejected_shared_edge_indices: list[int] = []
    if len(shared) == 2:
        fitted_shared_edges = deepcopy(updated["shared_edges"])
        updated["shared_edges"] = machine_shared_edges
        for index, fitted in enumerate(fitted_shared_edges):
            original = updated["shared_edges"][index]
            updated["shared_edges"][index] = fitted
            if _frames_are_source_bounded(updated):
                applied_shared_edge_count += 1
            else:
                updated["shared_edges"][index] = original
                rejected_shared_edge_indices.append(index + 1)
    updated["revision"] = int(record["revision"]) + 1
    updated["state"] = "human_adjusted"
    updated["origin"] = RED_MARKUP_ORIGIN
    updated["reviewed_task_ids"] = []
    updated["confirmation"] = None
    updated["diagnostics"] = dict(record["diagnostics"])
    unresolved = list(updated["diagnostics"].get("unresolved", []))
    if len(shared) != 2:
        unresolved.append(
            {
                "kind": "red_markup_shared_edges_not_recovered",
                "action": "review_both_machine_shared_edges_at_native_pixels",
            }
        )
    if rejected_shared_edge_indices:
        unresolved.append(
            {
                "kind": "red_markup_shared_edge_incompatible_with_source_raster",
                "shared_edge_indices": rejected_shared_edge_indices,
                "action": "review_machine_retained_shared_edges_at_native_pixels",
            }
        )
    for task_id, diagnostic in task_diagnostics.items():
        if diagnostic["machine_retained_role_indices"]:
            unresolved.append(
                {
                    "kind": "red_markup_missing_boundary_roles",
                    "task_id": task_id,
                    "boundary_role_indices": diagnostic["machine_retained_role_indices"],
                    "action": "review_machine_retained_roles_at_native_pixels",
                }
            )
    globally_unmatched_strokes = [
        index + 1
        for index, line in enumerate(observed_lines)
        if line["line_id"] not in used_observed_ids
    ]
    if globally_unmatched_strokes:
        unresolved.append(
            {
                "kind": "red_markup_unmatched_strokes",
                "red_stroke_indices": globally_unmatched_strokes,
                "action": "inspect_inactive_red_lines_and_task_mapping",
            }
        )
    updated["diagnostics"]["unresolved"] = unresolved
    updated["diagnostics"]["red_markup_import"] = {
        "marked_relative_path": marked_relative_path,
        "red_pixel_count": int(np.count_nonzero(canonical_mask)),
        "detected_boundary_count": len(observed_lines),
        "detected_shared_edge_count": len(shared),
        "applied_shared_edge_count": applied_shared_edge_count,
        "machine_retained_shared_edge_indices": rejected_shared_edge_indices,
        "boundary_extraction": extraction,
        "task_assignments": task_diagnostics,
        "authority": "user_red_strokes_fitted_pending_native_pixel_confirmation",
    }
    updated = apply_review_context_slot_semantics(updated)
    return updated
