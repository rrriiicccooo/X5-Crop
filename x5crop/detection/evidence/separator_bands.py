from __future__ import annotations

import numpy as np

from ...geometry.detection_parameters import GapSearchParameters
from ...policies.runtime_outer import SeparatorGeometryProposalPolicy, SeparatorOuterBandPolicy
from ...utils import clamp_float, clamp_int, runs_from_mask


def separator_outer_band_sequences(
    bands: list[dict[str, float]],
    expected_gaps: int,
    frame_long: float,
    band_policy: SeparatorOuterBandPolicy,
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
                    spacing_ratio < band_policy.spacing_min_ratio
                    or spacing_ratio > band_policy.spacing_max_ratio
                ):
                    continue
                score = 0.5 * (float(left["score"]) + float(right["score"]))
                geometry_error = abs(spacing_ratio - 1.0)
                pairs.append((geometry_error - 0.02 * score, (left, right)))
        return [
            pair
            for _rank, pair in sorted(pairs, key=lambda item: item[0])[
                : max(expected_gaps, int(band_policy.pair_candidate_count) * 3)
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
                    spacing_ratio < band_policy.spacing_min_ratio
                    or spacing_ratio > band_policy.spacing_max_ratio
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
    band_policy: SeparatorOuterBandPolicy,
    gap_search_config: GapSearchParameters,
    separator_policy: SeparatorGeometryProposalPolicy,
) -> tuple[list[dict[str, float]], float]:
    peak_threshold = float(band_policy.min_score)
    band_threshold = max(band_policy.band_score, peak_threshold * 0.58)
    min_width = clamp_int(
        short_axis * band_policy.min_width_ratio,
        gap_search_config.min_width_min,
        gap_search_config.max_width_max,
    )
    max_width = clamp_int(
        short_axis * band_policy.max_width_ratio,
        max(min_width + 1, gap_search_config.max_width_min),
        gap_search_config.max_width_max,
    )
    guard = clamp_int(
        short_axis * gap_search_config.guard_ratio,
        gap_search_config.guard_min,
        gap_search_config.guard_max,
    )
    edge_margin = clamp_float(
        short_axis * band_policy.edge_margin_ratio,
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
        oversized_band = (
            separator_policy.separator_outer_allow_oversized_band
            and width > max_width
            and width <= short_axis * separator_policy.separator_outer_oversized_band_max_ratio
        )
        if width < min_width or (width > max_width and not oversized_band):
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
        if mean_score < gap_search_config.min_score or (prominence < 0.02 and mean_score < 0.88):
            continue
        bands.append(
            {
                "start": float(band_start),
                "end": float(band_end),
                "center": float(center),
                "width": float(width),
                "score": float(
                    mean_score
                    + 0.8 * prominence
                    - (separator_policy.separator_outer_oversized_band_score_penalty if oversized_band else 0.0)
                ),
                "oversized": float(1.0 if oversized_band else 0.0),
            }
        )
    return bands, edge_margin
