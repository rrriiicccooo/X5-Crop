from __future__ import annotations

from typing import Optional

import numpy as np

from ...domain import Box, OuterCandidate
from ...formats import CONTENT_ASPECTS_HORIZONTAL, FormatSpec
from ...geometry.separator_cache import cached_separator_profile
from ...policies.registry import get_detection_policy
from ...policies.runtime_policy import DetectionPolicy
from ...runtime import AnalysisCache
from .bands import collect_separator_outer_bands, separator_outer_band_sequences
from .base import unique_outer_candidates
from .outer_cache_keys import separator_first_cache_key


def separator_first_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
) -> list[OuterCandidate]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    if policy.outer.separator_first == "off":
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
    band_policy = policy.outer.separator_outer_band
    expected_gaps = count - 1
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[: max(1, int(band_policy.source_candidate_count))]
    candidates: list[OuterCandidate] = []

    for source in source_candidates:
        outer = source.box.clamp(w, h)
        if not outer.valid() or outer.height <= 0 or outer.width <= 0:
            continue
        short_axis = float(outer.height)
        frame_long = short_axis * float(aspect)
        if frame_long <= 1.0:
            continue
        profile = cached_separator_profile(cache, gray_work, outer, fmt.name, policy.separator.profile)
        if profile.size <= 0:
            continue

        bands, edge_margin = collect_separator_outer_bands(
            profile,
            short_axis,
            float(outer.width),
            band_policy,
            policy.separator.gap_search,
            policy.outer,
        )

        if len(bands) < expected_gaps:
            continue
        bands = sorted(
            bands,
            key=lambda band: (-float(band["score"]), float(band["center"])),
        )[: max(expected_gaps, int(band_policy.band_candidate_count))]
        sequences: list[tuple[float, tuple[dict[str, float], ...], float]] = []
        for sequence in separator_outer_band_sequences(bands, expected_gaps, frame_long, band_policy):
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
            if max_frame_error > band_policy.frame_error_max:
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
            sorted(sequences, key=lambda item: item[0])[: max(1, int(band_policy.pair_candidate_count))],
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
                    "separator_outer",
                )
            )

    result = unique_outer_candidates(candidates)[: int(band_policy.max_candidates)]
    if cache is not None:
        cache.separator_first_outer_candidates[candidate_key] = list(result)
    return result
