"""Independent, bounded pixel proposals for human source annotation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
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
    COORDINATE_SYSTEM,
    MACHINE_ORIGIN,
    display_to_raw_point,
    validate_annotation_record,
)


PROPOSAL_REVISION = "independent_bounded_gradient_template_v1"
RED_DRAFT_ORIGIN = "user_red_markup_partial_draft_import_v1"


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
) -> dict[str, Any]:
    return {
        "line_id": line_id,
        "role": role,
        "points_raw": [display_to_raw_point(record, point) for point in points_display],
        "origin": origin,
    }


def propose_record(
    *,
    raster: SourceRaster,
    source_relative_path: str,
    source_sha256: str,
    canonical_sample_id: str,
    format_id: str,
    tasks: Iterable[dict[str, Any]],
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
                "boundary_ids": task_boundary_ids,
            }
        )
    validate_annotation_record(record)
    return record, analysis_rgb


def _red_delta_mask(source: np.ndarray, marked: np.ndarray) -> np.ndarray:
    if source.shape[:2] != marked.shape[:2] or min(source.shape[-1], marked.shape[-1]) < 3:
        raise ValueError("red markup draft does not preserve source raster geometry")
    height, width = source.shape[:2]
    mask = np.zeros((height, width), dtype=bool)
    for start in range(0, height, 256):
        stop = min(height, start + 256)
        original = source[start:stop, :, :3].astype(np.int32)
        overlay = marked[start:stop, :, :3].astype(np.int32)
        delta = overlay - original
        red = delta[..., 0]
        mask[start:stop] = (
            (red > 2_000)
            & (red - delta[..., 1] > 5_000)
            & (red - delta[..., 2] > 5_000)
        )
    return mask


def import_partial_red_boundary_draft(
    record: dict[str, Any],
    *,
    source_raster: SourceRaster,
    marked_path: Path,
) -> dict[str, Any]:
    with SourceRaster(marked_path) as marked_raster:
        if source_raster.raw_extent != marked_raster.raw_extent:
            raise ValueError("red markup draft was resized")
        mask_raw = _red_delta_mask(source_raster.raw, marked_raster.raw)
    # Preview saved the existing v2 drafts with Orientation=1.  The mask is
    # raw-coordinate evidence and is mapped through the source orientation.
    orientation = source_raster.orientation
    if orientation == 1:
        canonical_mask = mask_raw
    elif orientation == 2:
        canonical_mask = np.flip(mask_raw, axis=1)
    elif orientation == 3:
        canonical_mask = np.flip(mask_raw, axis=(0, 1))
    elif orientation == 4:
        canonical_mask = np.flip(mask_raw, axis=0)
    elif orientation == 5:
        canonical_mask = np.swapaxes(mask_raw, 0, 1)
    elif orientation == 6:
        canonical_mask = np.rot90(mask_raw, k=3)
    elif orientation == 7:
        canonical_mask = np.flip(np.swapaxes(mask_raw, 0, 1), axis=(0, 1))
    else:
        canonical_mask = np.rot90(mask_raw, k=1)
    horizontal = record["strip_axis_display"] == "horizontal"
    logical = canonical_mask if horizontal else canonical_mask.T
    projection = np.sum(logical, axis=0)
    threshold = max(24, int(round(logical.shape[0] * 0.04)))
    indices = np.flatnonzero(projection >= threshold)
    runs: list[tuple[int, int]] = []
    if len(indices):
        start = previous = int(indices[0])
        for raw in indices[1:]:
            value = int(raw)
            if value - previous > 3:
                runs.append((start, previous))
                start = value
            previous = value
        runs.append((start, previous))
    task = record["tasks"][0]
    expected = int(task["count"]) * 2
    if len(runs) != expected:
        raise ValueError(
            f"partial red draft contains {len(runs)} strong boundaries; expected {expected}"
        )
    display_width = int(record["source"]["canonical_extent"]["width"])
    display_height = int(record["source"]["canonical_extent"]["height"])
    logical_height, logical_width = logical.shape
    pool: list[dict[str, Any]] = []
    boundary_ids: list[str] = []
    for index, (start, stop) in enumerate(runs, start=1):
        band = logical[:, max(0, start - 3) : min(logical_width, stop + 4)]
        y, x_local = np.nonzero(band)
        x = x_local + max(0, start - 3)
        unique_y = np.unique(y)
        centers = np.asarray([np.median(x[y == value]) for value in unique_y])
        slope, intercept, _ = _robust_line(unique_y.astype(np.float64), centers)
        points = _line_points_display(
            line=(slope, intercept),
            family="boundary",
            horizontal=horizontal,
            analysis_width=logical_width,
            analysis_height=logical_height,
            display_width=display_width,
            display_height=display_height,
        )
        line_id = f"B{index:03d}"
        pool.append(
            _new_line(
                record,
                line_id=line_id,
                role="long_boundary",
                points_display=points,
                origin=RED_DRAFT_ORIGIN,
            )
        )
        boundary_ids.append(line_id)
    updated = deepcopy(record)
    updated["boundary_pool"] = pool
    updated["tasks"][0]["boundary_ids"] = boundary_ids
    updated["revision"] = int(record["revision"]) + 1
    updated["state"] = "human_adjusted"
    updated["origin"] = RED_DRAFT_ORIGIN
    updated["reviewed_task_ids"] = []
    updated["confirmation"] = None
    updated["diagnostics"] = dict(record["diagnostics"])
    updated["diagnostics"]["partial_red_markup_import"] = {
        "marked_path": str(marked_path),
        "red_pixel_count": int(np.count_nonzero(mask_raw)),
        "imported_boundary_count": len(pool),
        "missing_shared_edges_retained_from_machine_proposal": True,
    }
    validate_annotation_record(updated)
    return updated
