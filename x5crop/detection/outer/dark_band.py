from __future__ import annotations

from typing import Optional

import numpy as np

from ...domain import Box, OuterCandidate
from ...formats import CONTENT_ASPECTS_HORIZONTAL, FormatSpec
from ...policies.registry import get_detection_policy
from ...policies.runtime_policy import DetectionPolicy
from ...utils import clamp_float, clamp_int, runs_from_mask, sampled_percentile, smooth_1d
from .base import unique_outer_candidates


def separator_dark_band_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    policy: Optional[DetectionPolicy] = None,
) -> list[OuterCandidate]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    dark_band = policy.outer.dark_band_outer
    if dark_band.mode == "off" or strip_mode not in {"full", "partial"} or count != dark_band.required_count:
        return []
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return []
    h, w = gray_work.shape
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[: dark_band.source_candidate_count]
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
        dark_threshold = float(p01) + span * dark_band.threshold_span_ratio
        dark_profile = (crop <= dark_threshold).mean(axis=0).astype(np.float32)
        dark_profile = smooth_1d(
            dark_profile,
            max(
                dark_band.profile_smooth_min,
                int(round(full_long_outer.height * dark_band.profile_smooth_short_axis_ratio)),
            ),
        )
        short_axis = float(full_long_outer.height)
        frame_long = short_axis * float(aspect)
        edge_margin = clamp_float(
            short_axis * dark_band.edge_margin_ratio,
            dark_band.edge_margin_min,
            max(dark_band.edge_margin_min, short_axis * dark_band.edge_margin_cap_ratio),
        )
        min_width = clamp_int(
            short_axis * dark_band.min_width_ratio,
            dark_band.min_width_min,
            dark_band.min_width_max,
        )
        max_width = clamp_int(
            short_axis * dark_band.max_width_ratio,
            min_width + 1,
            max(dark_band.max_width_floor, int(short_axis * dark_band.max_width_cap_ratio)),
        )
        bands: list[dict[str, float]] = []
        for run_start, run_end in runs_from_mask(dark_profile >= dark_band.threshold_ratio):
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
        bands = sorted(bands, key=lambda band: (-float(band["score"]), float(band["center"])))[: dark_band.band_candidate_count]
        sequences: list[tuple[float, tuple[dict[str, float], dict[str, float]]]] = []
        for index, first in enumerate(bands):
            for second in bands[index + 1:]:
                spacing = float(second["center"]) - float(first["center"])
                spacing_ratio = spacing / max(1.0, frame_long)
                if spacing_ratio < dark_band.spacing_min_ratio or spacing_ratio > dark_band.spacing_max_ratio:
                    continue
                inner_width = float(second["start"]) - float(first["end"])
                if inner_width <= 0:
                    continue
                frame_error = abs(inner_width - frame_long) / max(1.0, frame_long)
                sequence_score = (float(first["score"]) + float(second["score"])) * 0.5
                rank = frame_error - dark_band.sequence_score_weight * sequence_score
                sequences.append((rank, (first, second)))
        for rank, (_score, sequence) in enumerate(sorted(sequences, key=lambda item: item[0])[: dark_band.sequence_candidate_count], start=1):
            first, second = sequence
            proposed_left = int(round(float(first["start"]) - frame_long))
            proposed_right = int(round(float(second["end"]) + frame_long))
            proposed = Box(proposed_left, full_long_outer.top, proposed_right, full_long_outer.bottom).clamp(w, h)
            if not proposed.valid():
                continue
            candidates.append(OuterCandidate(f"separator_dark_band_{source.name}_{rank}", proposed, "dark_band_outer"))
    return unique_outer_candidates(candidates)[: dark_band.max_candidates]
