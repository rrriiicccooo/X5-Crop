from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...domain import Box
from ...policies.parameters.candidate import DualLaneDividerParameters
from ...utils import clamp_int


@dataclass(frozen=True)
class LaneDividerProposal:
    center: int
    gutter: Box
    source: str

    def lane_boxes(self, canvas_width: int, canvas_height: int) -> tuple[Box, Box]:
        return (
            Box(0, 0, canvas_width, self.gutter.top),
            Box(0, self.gutter.bottom, canvas_width, canvas_height),
        )


def lane_divider_proposals(
    content_evidence: np.ndarray,
    parameters: DualLaneDividerParameters,
) -> tuple[LaneDividerProposal, ...]:
    if content_evidence.ndim != 2:
        raise ValueError("dual-lane divider requires two-dimensional evidence")
    height, width = content_evidence.shape
    if height < 2 or width < 1:
        return ()
    start = max(1, int(round(height * parameters.search_min_ratio)))
    end = min(height - 1, int(round(height * parameters.search_max_ratio)))
    if end <= start:
        return ()
    row_content = content_evidence.mean(axis=1, dtype=np.float64)
    row_texture = content_evidence.std(axis=1, dtype=np.float64)
    content_scale = max(1e-6, float(np.percentile(row_content, 90.0)))
    texture_scale = max(1e-6, float(np.percentile(row_texture, 90.0)))
    gutter_residual = np.maximum(
        row_content / content_scale,
        row_texture / texture_scale,
    )
    band_width = clamp_int(
        height * parameters.band_width_ratio,
        parameters.band_width_min_px,
        parameters.band_width_max_px,
    )
    kernel_width = max(1, band_width)
    kernel = np.ones(kernel_width, dtype=np.float64) / float(kernel_width)
    smoothed = np.convolve(gutter_residual, kernel, mode="same")
    minimum_separation = max(
        1,
        int(round(height * parameters.minimum_center_separation_ratio)),
    )
    selected: list[int] = []
    for row in sorted(range(start, end), key=lambda index: float(smoothed[index])):
        if all(abs(row - existing) >= minimum_separation for existing in selected):
            selected.append(row)
        if len(selected) >= int(parameters.proposal_count):
            break

    half = max(1, band_width // 2)
    proposals = [
        LaneDividerProposal(
            center=row,
            gutter=Box(0, max(1, row - half), width, min(height - 1, row + half)),
            source="measured_holder_gutter",
        )
        for row in selected
    ]
    center = height // 2
    if all(abs(center - proposal.center) >= half for proposal in proposals):
        proposals.append(
            LaneDividerProposal(
                center=center,
                gutter=Box(
                    0,
                    max(1, center - half),
                    width,
                    min(height - 1, center + half),
                ),
                source="center_safety",
            )
        )
    return tuple(proposals)
