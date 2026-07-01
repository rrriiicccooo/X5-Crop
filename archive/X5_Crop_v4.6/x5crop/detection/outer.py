from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ..common import *
from ..geometry import *
from ..geometry import (
    long_axis_edge_anchor_outer_mode_for_strip,
    separator_first_outer_mode_for_strip,
    separator_geometry_outer_mode_for_strip,
)
from ..policies import DetectionPolicy, get_detection_policy


@dataclass(frozen=True)
class OuterProposalStrategy:
    name: str
    report_strategy: str
    mode: str
    fallback_only: bool
    risk_level: str

    @property
    def enabled(self) -> bool:
        return self.mode != "off"


def separator_first_cache_key(
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
) -> tuple[Any, ...]:
    return (
        str(fmt.name),
        int(count),
        str(strip_mode),
        tuple((candidate.name, box_cache_key(candidate.box)) for candidate in base_candidates),
    )


def separator_geometry_cache_key(
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
) -> tuple[Any, ...]:
    return (
        "separator_geometry",
        str(fmt.name),
        int(count),
        str(strip_mode),
        tuple((candidate.name, box_cache_key(candidate.box)) for candidate in base_candidates),
    )


def long_axis_edge_anchor_cache_key(
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
) -> tuple[Any, ...]:
    return (
        str(fmt.name),
        int(count),
        str(strip_mode),
        tuple((candidate.name, box_cache_key(candidate.box)) for candidate in base_candidates),
    )

def outer_proposal_strategy_plan(
    tuning: FormatTuning,
    strip_mode: str,
    include_separator_first_mode: str = "off",
    include_long_axis_edge_anchor_mode: str = "off",
    include_separator_geometry_mode: str = "off",
    fallback_only: bool = False,
) -> list[OuterProposalStrategy]:
    base = [
        OuterProposalStrategy("base", "base_outer", "always", False, "low"),
        OuterProposalStrategy("content_floating", "content_outer", "always", False, "medium"),
    ]
    active = [
        OuterProposalStrategy(
            "long_axis_edge_anchor",
            "edge_anchor_outer",
            long_axis_edge_anchor_outer_mode_for_strip(tuning, strip_mode),
            True,
            "medium",
        ),
        OuterProposalStrategy(
            "separator_first",
            "separator_outer",
            separator_first_outer_mode_for_strip(tuning, strip_mode),
            True,
            "medium",
        ),
        OuterProposalStrategy(
            "separator_geometry",
            "separator_geometry_outer",
            separator_geometry_outer_mode_for_strip(tuning, strip_mode),
            True,
            "medium",
        ),
    ]
    if fallback_only:
        return [
            strategy
            for strategy in active
            if (
                (strategy.name == "long_axis_edge_anchor" and strategy.mode == include_long_axis_edge_anchor_mode)
                or (strategy.name == "separator_first" and strategy.mode == include_separator_first_mode)
                or (strategy.name == "separator_geometry" and strategy.mode == include_separator_geometry_mode)
            )
        ]
    return [
        *base,
        *[
            strategy
            for strategy in active
            if (
                (strategy.name == "long_axis_edge_anchor" and strategy.mode == include_long_axis_edge_anchor_mode)
                or (strategy.name == "separator_first" and strategy.mode == include_separator_first_mode)
                or (strategy.name == "separator_geometry" and strategy.mode == include_separator_geometry_mode)
            )
        ],
    ]


def outer_proposal_strategy_plan_for_policy(
    policy: DetectionPolicy,
    fallback_only: bool = False,
) -> list[OuterProposalStrategy]:
    base = [
        OuterProposalStrategy("base", "base_outer", "always", False, "low"),
        OuterProposalStrategy("content_floating", "content_outer", "always", False, "medium"),
    ]
    active = [
        OuterProposalStrategy(
            "long_axis_edge_anchor",
            "edge_anchor_outer",
            policy.outer.edge_anchor,
            True,
            "medium",
        ),
        OuterProposalStrategy(
            "separator_first",
            "separator_outer",
            policy.outer.separator_first,
            True,
            "medium",
        ),
        OuterProposalStrategy(
            "separator_geometry",
            "separator_geometry_outer",
            policy.outer.separator_geometry,
            True,
            "medium",
        ),
    ]
    if fallback_only:
        return [strategy for strategy in active if strategy.mode == "fallback"]
    return [*base, *[strategy for strategy in active if strategy.mode == "always"]]


def outer_candidate_strategy(candidate_name: str) -> str:
    if candidate_name.startswith("separator_dark_band_"):
        return "dark_band_outer"
    if candidate_name.startswith("separator_geometry_"):
        return "separator_geometry_outer"
    if candidate_name.startswith("separator_first_"):
        return "separator_outer"
    if candidate_name.startswith("long_axis_edge_anchor_"):
        return "edge_anchor_outer"
    if candidate_name.startswith("floating_"):
        return "content_outer"
    if candidate_name.startswith("content_aligned_"):
        return "content_aligned_retry"
    if candidate_name.startswith("format_geometry_"):
        return "format_geometry_retry"
    if candidate_name.startswith("short_axis_aspect_"):
        return "short_axis_retry"
    if candidate_name in {"bw", "white_x"} or candidate_name.startswith("mask_"):
        return "base_outer"
    return "unknown_outer"


def outer_proposal_candidates(
    gray_work: np.ndarray,
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
    include_separator_first_mode: str = "off",
    include_long_axis_edge_anchor_mode: str = "off",
    include_separator_geometry_mode: str = "off",
    fallback_only: bool = False,
    policy: Optional[DetectionPolicy] = None,
) -> list[OuterCandidate]:
    tuning = format_tuning(fmt.name)
    if policy is not None:
        strategy_plan = outer_proposal_strategy_plan_for_policy(policy, fallback_only=fallback_only)
    else:
        strategy_plan = outer_proposal_strategy_plan(
            tuning,
            strip_mode,
            include_separator_first_mode=include_separator_first_mode,
            include_long_axis_edge_anchor_mode=include_long_axis_edge_anchor_mode,
            include_separator_geometry_mode=include_separator_geometry_mode,
            fallback_only=fallback_only,
        )
    enabled_strategy_names = {strategy.name for strategy in strategy_plan if strategy.enabled}
    base_candidates = detect_outer_candidates(gray_work, fmt.name)
    floating_candidates = floating_outer_candidates(gray_work, base_candidates, fmt, count, strip_mode)
    pre_separator_candidates = unique_outer_candidates([*base_candidates, *floating_candidates])
    long_axis_candidates: list[OuterCandidate] = []
    if "long_axis_edge_anchor" in enabled_strategy_names:
        long_axis_candidates = long_axis_edge_anchor_outer_candidates(
            gray_work,
            pre_separator_candidates,
            fmt,
            count,
            strip_mode,
            cache,
        )
        pre_separator_candidates = unique_outer_candidates([*pre_separator_candidates, *long_axis_candidates])
    separator_first_candidates: list[OuterCandidate] = []
    if "separator_first" in enabled_strategy_names:
        separator_first_candidates = separator_first_outer_candidates(
            gray_work,
            pre_separator_candidates,
            fmt,
            count,
            strip_mode,
            cache,
        )
    separator_geometry_candidates: list[OuterCandidate] = []
    if "separator_geometry" in enabled_strategy_names:
        separator_geometry_candidates = separator_geometry_outer_candidates(
            gray_work,
            pre_separator_candidates,
            fmt,
            count,
            strip_mode,
            cache,
        )
    if fallback_only:
        return unique_outer_candidates([*long_axis_candidates, *separator_first_candidates, *separator_geometry_candidates])
    return unique_outer_candidates([*base_candidates, *floating_candidates, *long_axis_candidates, *separator_first_candidates, *separator_geometry_candidates])


def floating_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
) -> list[OuterCandidate]:
    tuning = format_tuning(fmt.name)
    enabled = tuning.floating_outer_full_enabled if strip_mode == "full" else tuning.floating_outer_partial_enabled
    if not enabled:
        return []
    if strip_mode == "full" and count != fmt.default_count:
        return []
    if strip_mode not in {"full", "partial"} or count <= 0:
        return []
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return []
    if not base_candidates:
        return []

    h, w = gray_work.shape
    content = bbox_from_mask(
        gray_work < int(tuning.floating_outer_content_threshold),
        min_row_fraction=0.010,
        min_col_fraction=0.010,
    )
    candidates: list[OuterCandidate] = []
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[:1]

    for source in source_candidates:
        outer = source.box.clamp(w, h)
        if not outer.valid() or outer.height <= 0:
            continue
        margin = clamp_int(
            float(outer.height) * tuning.floating_outer_content_margin_ratio,
            tuning.floating_outer_content_margin_min,
            tuning.floating_outer_content_margin_max,
        )
        y_top = outer.top
        y_bottom = outer.bottom
        if content is not None and content.valid():
            y_top = max(outer.top, content.top - margin)
            y_bottom = min(outer.bottom, content.bottom + margin)
            if y_bottom - y_top < max(40, int(round(outer.height * 0.65))):
                y_top = outer.top
                y_bottom = outer.bottom
        height = max(1, y_bottom - y_top)
        min_width = max(80, int(round(float(outer.width) * tuning.floating_outer_min_width_ratio)))

        starts_from_content: list[int] = []
        if content is not None and content.valid():
            starts_from_content.extend(
                [
                    int(round(float(content.left - margin))),
                    int(round(float(content.right + margin))),
                    int(round(float((content.left + content.right) * 0.5))),
                ]
            )

        for extra in tuning.floating_outer_ratio_extras:
            target_ratio = float(count) * float(aspect) + float(extra)
            target_width = int(round(float(height) * target_ratio))
            if target_width < min_width or target_width >= outer.width:
                continue
            starts: list[int] = []
            available = max(0, outer.width - target_width)
            starts.extend(
                [
                    outer.left,
                    outer.left + int(round(available * 0.50)),
                    outer.left + available,
                ]
            )
            for anchor in starts_from_content:
                starts.append(anchor)
                starts.append(anchor - target_width)
                starts.append(anchor - int(round(target_width * 0.5)))
            for start in starts:
                left = max(outer.left, min(start, outer.right - target_width))
                right = left + target_width
                box = Box(left, y_top, right, y_bottom).clamp(w, h)
                if not box.valid() or box.width < min_width:
                    continue
                candidates.append(
                    OuterCandidate(
                        f"floating_{strip_mode}_{source.name}_r{target_ratio:.3f}",
                        box,
                    )
                )

    return unique_outer_candidates(candidates)[: int(tuning.floating_outer_max_candidates)]


def long_axis_edge_anchor_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
) -> list[OuterCandidate]:
    tuning = format_tuning(fmt.name)
    enabled = tuning.long_axis_edge_anchor_outer_enabled if strip_mode == "full" else tuning.long_axis_edge_anchor_partial_enabled
    if not enabled:
        return []
    if strip_mode == "full" and count != fmt.default_count:
        return []
    if strip_mode not in {"full", "partial"} or count <= 0:
        return []
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return []
    if not base_candidates:
        return []
    if cache is not None:
        candidate_key = long_axis_edge_anchor_cache_key(base_candidates, fmt, count, strip_mode)
        cached_candidates = cache.long_axis_edge_anchor_outer_candidates.get(candidate_key)
        if cached_candidates is not None:
            return list(cached_candidates)

    h, w = gray_work.shape
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[:1]
    candidates: list[OuterCandidate] = []

    for source in source_candidates:
        outer = source.box.clamp(w, h)
        if not outer.valid() or outer.height <= 0 or outer.width <= 0:
            continue
        outer_crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
        local_content = bbox_from_mask(
            outer_crop < int(tuning.long_axis_edge_anchor_content_threshold),
            min_row_fraction=0.010,
            min_col_fraction=0.010,
        )
        content = None
        if local_content is not None and local_content.valid():
            content = Box(
                outer.left + local_content.left,
                outer.top + local_content.top,
                outer.left + local_content.right,
                outer.top + local_content.bottom,
            ).clamp(w, h)
        if strip_mode == "partial":
            if content is None or not content.valid():
                continue
            content_center = ((float(content.left + content.right) * 0.5) - float(outer.left)) / max(1.0, float(outer.width))
            edge_limit = float(tuning.long_axis_edge_anchor_partial_center_ratio)
            if edge_limit <= content_center <= (1.0 - edge_limit):
                continue
        margin = clamp_int(
            float(outer.height) * tuning.long_axis_edge_anchor_content_margin_ratio,
            tuning.long_axis_edge_anchor_content_margin_min,
            tuning.long_axis_edge_anchor_content_margin_max,
        )
        y_top = outer.top
        y_bottom = outer.bottom
        if content is not None and content.valid():
            y_top = max(outer.top, content.top - margin)
            y_bottom = min(outer.bottom, content.bottom + margin)
            if y_bottom - y_top < max(40, int(round(float(outer.height) * 0.65))):
                y_top = outer.top
                y_bottom = outer.bottom
        short_axis = max(1, y_bottom - y_top)
        min_width = max(80, int(round(float(outer.width) * tuning.long_axis_edge_anchor_min_width_ratio)))

        for extra in tuning.long_axis_edge_anchor_ratio_extras:
            target_ratio = float(count) * float(aspect) + float(extra)
            target_width = int(round(float(short_axis) * target_ratio))
            if target_width < min_width or target_width >= outer.width:
                continue
            anchors = (
                ("start", outer.left, outer.left + target_width),
                ("end", outer.right - target_width, outer.right),
            )
            for anchor_name, left, right in anchors:
                box = Box(int(left), y_top, int(right), y_bottom).clamp(w, h)
                if not box.valid() or box.width < min_width:
                    continue
                candidates.append(
                    OuterCandidate(
                        f"long_axis_edge_anchor_{strip_mode}_{anchor_name}_{source.name}_r{target_ratio:.3f}",
                        box,
                    )
                )

    result = unique_outer_candidates(candidates)[: int(tuning.long_axis_edge_anchor_max_candidates)]
    if cache is not None:
        cache.long_axis_edge_anchor_outer_candidates[candidate_key] = list(result)
    return result


def separator_outer_band_sequences(
    bands: list[dict[str, float]],
    expected_gaps: int,
    frame_long: float,
    tuning: FormatTuning,
) -> list[tuple[dict[str, float], ...]]:
    ordered = sorted(bands, key=lambda band: float(band["center"]))
    if expected_gaps <= 0 or len(ordered) < expected_gaps:
        return []
    if expected_gaps == 1:
        return [(band,) for band in ordered]
    if expected_gaps == 2:
        pairs: list[tuple[float, tuple[dict[str, float], dict[str, float]]]] = []
        for left_index, left in enumerate(ordered[:-1]):
            for right in ordered[left_index + 1:]:
                inner_width = float(right["start"]) - float(left["end"])
                if inner_width <= 0:
                    continue
                spacing = float(right["center"]) - float(left["center"])
                spacing_ratio = spacing / max(1.0, frame_long)
                if (
                    spacing_ratio < tuning.separator_first_outer_spacing_min_ratio
                    or spacing_ratio > tuning.separator_first_outer_spacing_max_ratio
                ):
                    continue
                score = 0.5 * (float(left["score"]) + float(right["score"]))
                geometry_error = abs(spacing_ratio - 1.0)
                pairs.append((geometry_error - 0.02 * score, (left, right)))
        return [
            pair
            for _rank, pair in sorted(pairs, key=lambda item: item[0])[
                : max(expected_gaps, int(tuning.separator_first_outer_pair_candidates) * 3)
            ]
        ]
    sequences: list[tuple[dict[str, float], ...]] = []

    def extend(start_index: int, selected: list[dict[str, float]]) -> None:
        remaining = expected_gaps - len(selected)
        if remaining <= 0:
            sequences.append(tuple(selected))
            return
        last = selected[-1] if selected else None
        max_start = len(ordered) - remaining
        for index in range(start_index, max_start + 1):
            band = ordered[index]
            if last is not None:
                inner_width = float(band["start"]) - float(last["end"])
                if inner_width <= 0:
                    continue
                spacing = float(band["center"]) - float(last["center"])
                spacing_ratio = spacing / max(1.0, frame_long)
                if (
                    spacing_ratio < tuning.separator_first_outer_spacing_min_ratio
                    or spacing_ratio > tuning.separator_first_outer_spacing_max_ratio
                ):
                    continue
            selected.append(band)
            extend(index + 1, selected)
            selected.pop()

    extend(0, [])
    return sequences


def collect_separator_outer_bands(
    profile: np.ndarray,
    short_axis: float,
    coordinate_limit: float,
    tuning: FormatTuning,
) -> tuple[list[dict[str, float]], float]:
    peak_threshold = float(tuning.separator_first_outer_min_score)
    band_threshold = max(tuning.separator_first_outer_band_score, peak_threshold * 0.58)
    min_width = clamp_int(
        short_axis * tuning.separator_first_outer_min_width_ratio,
        tuning.gap_min_width_min,
        tuning.gap_max_width_max,
    )
    max_width = clamp_int(
        short_axis * tuning.separator_first_outer_max_width_ratio,
        max(min_width + 1, tuning.gap_max_width_min),
        tuning.gap_max_width_max,
    )
    guard = clamp_int(short_axis * tuning.gap_guard_ratio, tuning.gap_guard_min, tuning.gap_guard_max)
    edge_margin = clamp_float(
        short_axis * tuning.separator_first_outer_edge_margin_ratio,
        60.0,
        max(60.0, short_axis * 0.80),
    )

    bands: list[dict[str, float]] = []
    for run_start, run_end in runs_from_mask(profile >= peak_threshold):
        band_start, band_end = int(run_start), int(run_end)
        while band_start > 0 and profile[band_start - 1] >= band_threshold and (band_end - (band_start - 1)) <= max_width:
            band_start -= 1
        while band_end < len(profile) and profile[band_end] >= band_threshold and ((band_end + 1) - band_start) <= max_width:
            band_end += 1
        width = band_end - band_start
        oversized_66_band = (
            tuning.name == "120-66"
            and width > max_width
            and width <= short_axis * 0.45
        )
        if width < min_width or (width > max_width and not oversized_66_band):
            continue
        center = (band_start + band_end - 1) / 2.0
        if center < edge_margin or center > float(coordinate_limit) - edge_margin:
            continue
        left_guard = profile[max(0, band_start - guard):band_start]
        right_guard = profile[band_end:min(len(profile), band_end + guard)]
        if left_guard.size == 0 or right_guard.size == 0:
            continue
        mean_score = float(profile[band_start:band_end].mean())
        side_score = max(float(left_guard.mean()), float(right_guard.mean()))
        prominence = mean_score - side_score
        if mean_score < tuning.gap_min_score or (prominence < 0.02 and mean_score < 0.88):
            continue
        bands.append(
            {
                "start": float(band_start),
                "end": float(band_end),
                "center": float(center),
                "width": float(width),
                "score": float(mean_score + 0.8 * prominence - (0.08 if oversized_66_band else 0.0)),
                "oversized": float(1.0 if oversized_66_band else 0.0),
            }
        )
    return bands, edge_margin


def separator_geometry_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
) -> list[OuterCandidate]:
    tuning = format_tuning(fmt.name)
    if separator_geometry_outer_mode_for_strip(tuning, strip_mode) == "off":
        return []
    if strip_mode not in {"full", "partial"} or count <= 1:
        return []
    expected_count = int(tuning.separator_geometry_outer_count)
    if expected_count > 0 and count != expected_count:
        return []
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return []
    if not base_candidates:
        return []
    if cache is not None:
        candidate_key = separator_geometry_cache_key(base_candidates, fmt, count, strip_mode)
        cached_candidates = cache.separator_geometry_outer_candidates.get(candidate_key)
        if cached_candidates is not None:
            return list(cached_candidates)

    h, w = gray_work.shape
    expected_gaps = count - 1
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[: max(1, int(tuning.separator_geometry_outer_source_candidates))]
    candidates: list[OuterCandidate] = []

    for source in source_candidates:
        source_box = source.box.clamp(w, h)
        if not source_box.valid() or source_box.height <= 0:
            continue
        full_long_outer = Box(0, source_box.top, w, source_box.bottom)
        short_axis = float(full_long_outer.height)
        frame_long = short_axis * float(aspect)
        if frame_long <= 1.0:
            continue
        profile = cached_separator_profile(cache, gray_work, full_long_outer, fmt.name)
        if profile.size <= 0:
            continue

        bands, edge_margin = collect_separator_outer_bands(profile, short_axis, float(w), tuning)

        if len(bands) < expected_gaps:
            continue
        bands = sorted(
            bands,
            key=lambda band: (-float(band["score"]), float(band["center"])),
        )[: max(expected_gaps, int(tuning.separator_first_outer_band_candidates))]
        sequences: list[tuple[float, tuple[dict[str, float], ...], float]] = []
        for sequence in separator_outer_band_sequences(bands, expected_gaps, frame_long, tuning):
            frame_widths: list[float] = []
            previous: Optional[dict[str, float]] = None
            valid = True
            for band in sequence:
                if previous is not None:
                    inner_width = float(band["start"]) - float(previous["end"])
                    if inner_width <= 0:
                        valid = False
                        break
                    frame_widths.append(inner_width)
                previous = band
            if not valid:
                continue
            if frame_widths:
                frame_errors = [abs(width - frame_long) / max(1.0, frame_long) for width in frame_widths]
                max_frame_error = max(frame_errors)
                mean_frame_error = float(sum(frame_errors) / len(frame_errors))
            else:
                max_frame_error = 0.0
                mean_frame_error = 0.0
            if max_frame_error > tuning.separator_first_outer_frame_error_max:
                continue

            separator_total = sum(float(band["width"]) for band in sequence)
            expected_ratio_base = float(count) * float(aspect) + separator_total / max(1.0, short_axis)
            sequence_score = sum(float(band["score"]) for band in sequence) / max(1, len(sequence))
            for margin_ratio in tuning.separator_geometry_outer_margin_ratios:
                margin = float(margin_ratio) * short_axis
                first_band = sequence[0]
                last_band = sequence[-1]
                proposed_left = int(round(float(first_band["start"]) - frame_long - margin))
                proposed_right = int(round(float(last_band["end"]) + frame_long + margin))
                if proposed_right <= proposed_left:
                    continue
                proposed = Box(proposed_left, full_long_outer.top, proposed_right, full_long_outer.bottom).clamp(w, h)
                if not proposed.valid():
                    continue
                left_loss = max(0, -proposed_left)
                right_loss = max(0, proposed_right - w)
                if left_loss > edge_margin or right_loss > edge_margin:
                    continue
                actual_ratio = proposed.width / max(1.0, float(proposed.height))
                expected_ratio = expected_ratio_base + 2.0 * float(margin_ratio)
                ratio_error = abs(actual_ratio - expected_ratio)
                sequence_rank = ratio_error + mean_frame_error - 0.02 * sequence_score
                sequences.append((sequence_rank, sequence, expected_ratio))

        for rank, (_sequence_rank, sequence, expected_ratio) in enumerate(
            sorted(sequences, key=lambda item: item[0])[: max(1, int(tuning.separator_geometry_outer_max_candidates))],
            start=1,
        ):
            first_band = sequence[0]
            last_band = sequence[-1]
            separator_total = sum(float(band["width"]) for band in sequence)
            margin = max(0.0, (expected_ratio - (float(count) * float(aspect) + separator_total / max(1.0, short_axis))) * short_axis * 0.5)
            proposed = Box(
                int(round(float(first_band["start"]) - frame_long - margin)),
                full_long_outer.top,
                int(round(float(last_band["end"]) + frame_long + margin)),
                full_long_outer.bottom,
            ).clamp(w, h)
            if not proposed.valid():
                continue
            candidates.append(
                OuterCandidate(
                    f"separator_geometry_{source.name}_{rank}_r{expected_ratio:.3f}",
                    proposed,
                )
            )

    result = unique_outer_candidates(candidates)[: int(tuning.separator_geometry_outer_max_candidates)]
    if cache is not None:
        cache.separator_geometry_outer_candidates[candidate_key] = list(result)
    return result


def separator_dark_band_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    policy: Optional[DetectionPolicy] = None,
) -> list[OuterCandidate]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    if policy.outer.dark_band == "off" or strip_mode not in {"full", "partial"} or count != 3:
        return []
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return []
    h, w = gray_work.shape
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[:2]
    candidates: list[OuterCandidate] = []
    for source in source_candidates:
        source_box = source.box.clamp(w, h)
        if not source_box.valid() or source_box.height <= 0:
            continue
        full_long_outer = Box(0, source_box.top, w, source_box.bottom)
        crop = gray_work[full_long_outer.top:full_long_outer.bottom, :]
        if crop.size == 0:
            continue
        sample = crop[:: max(1, crop.shape[0] // 500), :: max(1, crop.shape[1] // 2000)]
        p01, p99 = sampled_percentile(sample, [1, 99])
        span = max(1.0, float(p99 - p01))
        dark_threshold = float(p01) + span * 0.12
        dark_profile = (crop <= dark_threshold).mean(axis=0).astype(np.float32)
        dark_profile = smooth_1d(dark_profile, max(15, int(round(full_long_outer.height * 0.018))))
        short_axis = float(full_long_outer.height)
        frame_long = short_axis * float(aspect)
        edge_margin = clamp_float(short_axis * 0.18, 60.0, max(60.0, short_axis * 0.80))
        min_width = clamp_int(short_axis * 0.030, 80, 520)
        max_width = clamp_int(short_axis * 0.48, min_width + 1, max(600, int(short_axis * 0.55)))
        bands: list[dict[str, float]] = []
        for run_start, run_end in runs_from_mask(dark_profile >= 0.42):
            width = int(run_end - run_start)
            if width < min_width or width > max_width:
                continue
            center = (float(run_start) + float(run_end) - 1.0) * 0.5
            if center < edge_margin or center > float(w) - edge_margin:
                continue
            score = float(dark_profile[run_start:run_end].mean())
            bands.append(
                {
                    "start": float(run_start),
                    "end": float(run_end),
                    "center": center,
                    "width": float(width),
                    "score": score,
                }
            )
        bands = sorted(bands, key=lambda band: (-float(band["score"]), float(band["center"])))[:10]
        sequences: list[tuple[float, tuple[dict[str, float], dict[str, float]]]] = []
        for index, first in enumerate(bands):
            for second in bands[index + 1:]:
                spacing = float(second["center"]) - float(first["center"])
                spacing_ratio = spacing / max(1.0, frame_long)
                if spacing_ratio < 0.82 or spacing_ratio > 1.18:
                    continue
                inner_width = float(second["start"]) - float(first["end"])
                if inner_width <= 0:
                    continue
                frame_error = abs(inner_width - frame_long) / max(1.0, frame_long)
                sequence_score = (float(first["score"]) + float(second["score"])) * 0.5
                rank = frame_error - 0.04 * sequence_score
                sequences.append((rank, (first, second)))
        for rank, (_score, sequence) in enumerate(sorted(sequences, key=lambda item: item[0])[:4], start=1):
            first, second = sequence
            proposed_left = int(round(float(first["start"]) - frame_long))
            proposed_right = int(round(float(second["end"]) + frame_long))
            proposed = Box(proposed_left, full_long_outer.top, proposed_right, full_long_outer.bottom).clamp(w, h)
            if not proposed.valid():
                continue
            candidates.append(OuterCandidate(f"separator_dark_band_{source.name}_{rank}", proposed))
    return unique_outer_candidates(candidates)[:4]


def separator_first_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
) -> list[OuterCandidate]:
    tuning = format_tuning(fmt.name)
    if not tuning.separator_first_outer_enabled:
        return []
    if strip_mode == "full" and count != fmt.default_count:
        return []
    if strip_mode not in {"full", "partial"} or count <= 1:
        return []
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return []
    if not base_candidates:
        return []
    if cache is not None:
        candidate_key = separator_first_cache_key(base_candidates, fmt, count, strip_mode)
        cached_candidates = cache.separator_first_outer_candidates.get(candidate_key)
        if cached_candidates is not None:
            return list(cached_candidates)

    h, w = gray_work.shape
    expected_gaps = count - 1
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[: max(1, int(tuning.separator_first_outer_source_candidates))]
    candidates: list[OuterCandidate] = []

    for source in source_candidates:
        outer = source.box.clamp(w, h)
        if not outer.valid() or outer.height <= 0 or outer.width <= 0:
            continue
        short_axis = float(outer.height)
        frame_long = short_axis * float(aspect)
        if frame_long <= 1.0:
            continue
        profile = cached_separator_profile(cache, gray_work, outer, fmt.name)
        if profile.size <= 0:
            continue

        bands, edge_margin = collect_separator_outer_bands(profile, short_axis, float(outer.width), tuning)

        if len(bands) < expected_gaps:
            continue
        bands = sorted(
            bands,
            key=lambda band: (-float(band["score"]), float(band["center"])),
        )[: max(expected_gaps, int(tuning.separator_first_outer_band_candidates))]
        sequences: list[tuple[float, tuple[dict[str, float], ...], float]] = []
        for sequence in separator_outer_band_sequences(bands, expected_gaps, frame_long, tuning):
            frame_widths: list[float] = []
            previous: Optional[dict[str, float]] = None
            valid = True
            for band in sequence:
                if previous is not None:
                    inner_width = float(band["start"]) - float(previous["end"])
                    if inner_width <= 0:
                        valid = False
                        break
                    frame_widths.append(inner_width)
                previous = band
            if not valid or len(frame_widths) != max(0, expected_gaps - 1):
                continue
            if frame_widths:
                frame_errors = [abs(width - frame_long) / max(1.0, frame_long) for width in frame_widths]
                max_frame_error = max(frame_errors)
                mean_frame_error = float(sum(frame_errors) / len(frame_errors))
            else:
                max_frame_error = 0.0
                mean_frame_error = 0.0
            if max_frame_error > tuning.separator_first_outer_frame_error_max:
                continue

            first_band = sequence[0]
            last_band = sequence[-1]
            proposed_left = int(round(outer.left + float(first_band["start"]) - frame_long))
            proposed_right = int(round(outer.left + float(last_band["end"]) + frame_long))
            if proposed_right <= proposed_left:
                continue
            proposed = Box(proposed_left, outer.top, proposed_right, outer.bottom).clamp(w, h)
            if not proposed.valid():
                continue
            left_loss = max(0, -proposed_left)
            right_loss = max(0, proposed_right - w)
            if left_loss > edge_margin or right_loss > edge_margin:
                continue

            separator_total = sum(float(band["width"]) for band in sequence)
            expected_ratio = float(count) * float(aspect) + separator_total / max(1.0, short_axis)
            actual_ratio = proposed.width / max(1.0, float(proposed.height))
            ratio_error = abs(actual_ratio - expected_ratio)
            sequence_score = sum(float(band["score"]) for band in sequence) / max(1, len(sequence))
            sequence_rank = ratio_error + mean_frame_error - 0.02 * sequence_score
            sequences.append((sequence_rank, sequence, expected_ratio))

        for rank, (_sequence_rank, sequence, expected_ratio) in enumerate(
            sorted(sequences, key=lambda item: item[0])[: max(1, int(tuning.separator_first_outer_pair_candidates))],
            start=1,
        ):
            first_band = sequence[0]
            last_band = sequence[-1]
            proposed = Box(
                int(round(outer.left + float(first_band["start"]) - frame_long)),
                outer.top,
                int(round(outer.left + float(last_band["end"]) + frame_long)),
                outer.bottom,
            ).clamp(w, h)
            if not proposed.valid():
                continue
            candidates.append(
                OuterCandidate(
                    f"separator_first_{source.name}_{rank}_r{expected_ratio:.3f}",
                    proposed,
                )
            )

    result = unique_outer_candidates(candidates)[: int(tuning.separator_first_outer_max_candidates)]
    if cache is not None:
        cache.separator_first_outer_candidates[candidate_key] = list(result)
    return result

__all__ = [
    "OuterProposalStrategy",
    "outer_candidate_strategy",
    "outer_proposal_strategy_plan",
    "outer_proposal_strategy_plan_for_policy",
    "outer_proposal_candidates",
    "floating_outer_candidates",
    "long_axis_edge_anchor_outer_candidates",
    "separator_outer_band_sequences",
    "collect_separator_outer_bands",
    "separator_geometry_outer_candidates",
    "separator_dark_band_outer_candidates",
    "separator_first_outer_candidates",
]
