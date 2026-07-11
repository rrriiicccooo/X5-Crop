from __future__ import annotations

import numpy as np

from ....domain import Box, MeasurementProvenance
from ....geometry.detection_parameters import OuterBoxDetectionParameters
from ....geometry.outer_boxes import detect_mask_profile_outer, detect_outer, detect_outer_white_x
from .common import unique_outer_proposals
from .side_boundary import side_boundary_outer_proposals
from .types import OuterProposal


def base_outer_candidates(
    gray: np.ndarray,
    config: OuterBoxDetectionParameters,
) -> list[OuterProposal]:
    h, w = gray.shape
    bw = detect_outer(gray, config)
    white_x = detect_outer_white_x(gray, config)
    candidates = [
        OuterProposal(
            "bw",
            bw,
            "base_outer",
            MeasurementProvenance(
                "holder_boundary_profile",
                "bw",
                ("gray_work",),
            ),
        )
    ]
    if white_x.valid():
        max_reasonable = max(
            float(bw.width) * config.white_x_width_multiplier,
            float(bw.width) + w * config.white_x_extra_ratio,
        )
        if white_x.width >= bw.width and white_x.width <= max_reasonable:
            candidates.append(
                OuterProposal(
                    "white_x",
                    white_x,
                    "base_outer",
                    MeasurementProvenance(
                        "holder_boundary_profile",
                        "white_x",
                        ("gray_work",),
                    ),
                )
            )
    for side_boundary in side_boundary_outer_proposals(gray, config):
        if side_boundary.box is None:
            continue
        candidates.append(
            OuterProposal(
                side_boundary.reason,
                side_boundary.box,
                "base_outer",
                MeasurementProvenance(
                    "holder_boundary_profile",
                    side_boundary.reason,
                    tuple(side.boundary_model for side in side_boundary.sides),
                    tuple(side.side for side in side_boundary.sides),
                ),
            )
        )
    for profile in config.mask_profiles:
        box = detect_mask_profile_outer(gray, profile, config)
        if box is not None:
            candidates.append(
                OuterProposal(
                    profile.name,
                    box,
                    "base_outer",
                    MeasurementProvenance(
                        "holder_boundary_profile",
                        profile.name,
                        ("gray_work", "mask_profile"),
                    ),
                )
            )
    candidates.append(
        OuterProposal(
            "full_canvas",
            Box(0, 0, w, h),
            "base_outer",
            MeasurementProvenance(
                "holder_canvas",
                "full_canvas",
                ("canvas",),
            ),
        )
    )
    return unique_outer_proposals(candidates)
