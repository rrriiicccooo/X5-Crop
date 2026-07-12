from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...domain import Box
from ...configuration.candidate import DualLaneDividerParameters
from ...utils import clamp_int


DUAL_LANE_COUNT = 2


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


@dataclass(frozen=True)
class LaneDividerProposalSet:
    proposals: tuple[LaneDividerProposal, ...]
    budget_exhausted: bool


def lane_divider_proposals(
    content_evidence: np.ndarray,
    parameters: DualLaneDividerParameters,
) -> LaneDividerProposalSet:
    if content_evidence.ndim != 2:
        raise ValueError("dual-lane divider requires two-dimensional evidence")
    height, width = content_evidence.shape
    if height < DUAL_LANE_COUNT or width < 1:
        return LaneDividerProposalSet((), False)
    start = max(1, int(round(height * parameters.search_min_ratio)))
    end = min(height - 1, int(round(height * parameters.search_max_ratio)))
    if end <= start:
        return LaneDividerProposalSet((), False)
    row_content = content_evidence.mean(axis=1, dtype=np.float64)
    row_texture = content_evidence.std(axis=1, dtype=np.float64)
    content_scale = max(
        parameters.numerical_floor,
        float(np.percentile(row_content, parameters.residual_scale_percentile)),
    )
    texture_scale = max(
        parameters.numerical_floor,
        float(np.percentile(row_texture, parameters.residual_scale_percentile)),
    )
    gutter_residual = np.maximum(
        row_content / content_scale,
        row_texture / texture_scale,
    )
    band_width = clamp_int(
        height * parameters.band_width_ratio,
        parameters.band_width_min_px,
        parameters.band_width_max_px,
    )
    kernel_width = band_width
    kernel = np.ones(kernel_width, dtype=np.float64) / float(kernel_width)
    smoothed = np.convolve(gutter_residual, kernel, mode="same")
    minimum_separation = max(
        1,
        int(round(height * parameters.minimum_center_separation_ratio)),
    )
    selected: list[int] = []
    budget_exhausted = False
    for row in sorted(range(start, end), key=lambda index: float(smoothed[index])):
        if all(abs(row - existing) >= minimum_separation for existing in selected):
            if len(selected) >= int(parameters.proposal_count):
                budget_exhausted = True
                break
            selected.append(row)

    half = max(1, band_width // DUAL_LANE_COUNT)
    proposals = [
        LaneDividerProposal(
            center=row,
            gutter=Box(0, max(1, row - half), width, min(height - 1, row + half)),
            source="measured_holder_gutter",
        )
        for row in selected
    ]
    center = height // DUAL_LANE_COUNT
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
    return LaneDividerProposalSet(tuple(proposals), budget_exhausted)
