from __future__ import annotations

import numpy as np

from ....domain import Box, OuterCandidate
from ....geometry.detection_parameters import OuterBoxDetectionParameters
from ....geometry.outer_boxes import detect_mask_profile_outer, detect_outer, detect_outer_white_x
from .common import unique_outer_candidates
from .side_boundary import side_boundary_outer


def base_outer_candidates(
    gray: np.ndarray,
    config: OuterBoxDetectionParameters | None = None,
) -> list[OuterCandidate]:
    outer_config = config or OuterBoxDetectionParameters()
    h, w = gray.shape
    bw = detect_outer(gray, outer_config)
    white_x = detect_outer_white_x(gray, outer_config)
    side_boundary = side_boundary_outer(gray, outer_config)
    candidates = [OuterCandidate("bw", bw, "base_outer")]
    if white_x.valid():
        max_reasonable = max(
            float(bw.width) * outer_config.white_x_width_multiplier,
            float(bw.width) + w * outer_config.white_x_extra_ratio,
        )
        if white_x.width >= bw.width and white_x.width <= max_reasonable:
            candidates.append(OuterCandidate("white_x", white_x, "base_outer"))
    if side_boundary.box is not None:
        candidates.append(OuterCandidate("side_boundary", side_boundary.box, "base_outer"))
    for profile in outer_config.mask_profiles:
        box = detect_mask_profile_outer(gray, profile, outer_config)
        if box is not None:
            candidates.append(OuterCandidate(profile.name, box, "base_outer"))

    unique = unique_outer_candidates(candidates)
    canvas_area = float(w * h)
    non_full = [
        candidate for candidate in unique
        if (candidate.box.width * candidate.box.height) / max(1.0, canvas_area) <= outer_config.candidate_max_area
    ]
    if non_full:
        return non_full
    return unique or [OuterCandidate("full_canvas", Box(0, 0, w, h), "base_outer")]
