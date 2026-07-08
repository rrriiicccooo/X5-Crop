from __future__ import annotations

import numpy as np

from ....domain import Box, OuterCandidate
from ....geometry.detection_parameters import OuterBoxDetectionParameters
from ....geometry.outer_boxes import detect_mask_profile_outer, detect_outer, detect_outer_white_x
from .common import unique_outer_candidates
from .side_boundary import side_boundary_outer


def base_outer_candidates(
    gray: np.ndarray,
    config: OuterBoxDetectionParameters,
) -> list[OuterCandidate]:
    h, w = gray.shape
    bw = detect_outer(gray, config)
    white_x = detect_outer_white_x(gray, config)
    side_boundary = side_boundary_outer(gray, config)
    candidates = [
        OuterCandidate(
            "bw",
            bw,
            "base_outer",
            {"family": "base_outer", "method": "bw"},
        )
    ]
    if white_x.valid():
        max_reasonable = max(
            float(bw.width) * config.white_x_width_multiplier,
            float(bw.width) + w * config.white_x_extra_ratio,
        )
        if white_x.width >= bw.width and white_x.width <= max_reasonable:
            candidates.append(
                OuterCandidate(
                    "white_x",
                    white_x,
                    "base_outer",
                    {"family": "base_outer", "method": "white_x"},
                )
            )
    if side_boundary.box is not None:
        candidates.append(
            OuterCandidate(
                "mixed_boundary",
                side_boundary.box,
                "base_outer",
                side_boundary.detail(),
            )
        )
    for profile in config.mask_profiles:
        box = detect_mask_profile_outer(gray, profile, config)
        if box is not None:
            candidates.append(
                OuterCandidate(
                    profile.name,
                    box,
                    "base_outer",
                    {"family": "base_outer", "method": "mask_profile", "profile": profile.name},
                )
            )

    unique = unique_outer_candidates(candidates)
    canvas_area = float(w * h)
    non_full = [
        candidate for candidate in unique
        if (candidate.box.width * candidate.box.height) / max(1.0, canvas_area) <= config.candidate_max_area
    ]
    if non_full:
        return non_full
    return unique or [
        OuterCandidate(
            "full_canvas",
            Box(0, 0, w, h),
            "base_outer",
            {"family": "base_outer", "method": "full_canvas"},
        )
    ]
