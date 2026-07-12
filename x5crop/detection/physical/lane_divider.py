from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np

from ...configuration.candidate import DualLaneDividerParameters
from ...domain import Box, EvidenceState, MeasurementProvenance
from ...utils import clamp_int


DUAL_LANE_COUNT = 2


@dataclass(frozen=True)
class LaneDividerEvidence:
    center: int
    gutter: Box
    normalized_gutter_residual: float
    normalized_lane_residuals: tuple[float, float]
    provenance: MeasurementProvenance
    state: EvidenceState = field(init=False)

    def __post_init__(self) -> None:
        residuals = (
            self.normalized_gutter_residual,
            *self.normalized_lane_residuals,
        )
        if (
            not self.gutter.valid()
            or not self.gutter.top <= self.center < self.gutter.bottom
        ):
            raise ValueError("lane divider gutter must contain its center")
        if any(not math.isfinite(value) or value < 0.0 for value in residuals):
            raise ValueError("lane divider residuals must be finite and non-negative")
        upper_residual, lower_residual = self.normalized_lane_residuals
        if self.normalized_gutter_residual < min(upper_residual, lower_residual):
            state = EvidenceState.SUPPORTED
        elif self.normalized_gutter_residual > max(upper_residual, lower_residual):
            state = EvidenceState.CONTRADICTED
        else:
            state = EvidenceState.UNAVAILABLE
        object.__setattr__(self, "state", state)

    def lane_boxes(self, canvas_width: int, canvas_height: int) -> tuple[Box, Box]:
        if not 0 < self.center < canvas_height or canvas_width <= 0:
            raise ValueError("lane divider must split a positive canvas")
        return (
            Box(0, 0, canvas_width, self.center),
            Box(0, self.center, canvas_width, canvas_height),
        )


@dataclass(frozen=True)
class LaneDividerEvidenceSet:
    candidates: tuple[LaneDividerEvidence, ...]
    budget_exhausted: bool


def _divider_evidence(
    residual: np.ndarray,
    center: int,
    band_width: int,
    canvas_width: int,
    *,
    source: str,
) -> LaneDividerEvidence | None:
    height = int(residual.shape[0])
    half = max(1, band_width // DUAL_LANE_COUNT)
    gutter = Box(
        0,
        max(1, center - half),
        canvas_width,
        min(height - 1, center + half),
    )
    reference_width = gutter.height
    upper = residual[max(0, gutter.top - reference_width) : gutter.top]
    gutter_sample = residual[gutter.top : gutter.bottom]
    lower = residual[gutter.bottom : min(height, gutter.bottom + reference_width)]
    if not upper.size or not gutter_sample.size or not lower.size:
        return None
    return LaneDividerEvidence(
        center=center,
        gutter=gutter,
        normalized_gutter_residual=float(np.mean(gutter_sample, dtype=np.float64)),
        normalized_lane_residuals=(
            float(np.mean(upper, dtype=np.float64)),
            float(np.mean(lower, dtype=np.float64)),
        ),
        provenance=MeasurementProvenance(
            root_measurement="lane_divider_profile",
            source=source,
            dependencies=("content_evidence_image",),
        ),
    )


def measure_lane_dividers(
    content_evidence: np.ndarray,
    parameters: DualLaneDividerParameters,
) -> LaneDividerEvidenceSet:
    if content_evidence.ndim != 2:
        raise ValueError("dual-lane divider requires two-dimensional evidence")
    height, width = content_evidence.shape
    if height < DUAL_LANE_COUNT or width < 1:
        return LaneDividerEvidenceSet((), False)
    start = max(1, int(round(height * parameters.search_min_ratio)))
    end = min(height - 1, int(round(height * parameters.search_max_ratio)))
    if end <= start:
        return LaneDividerEvidenceSet((), False)
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
    residual = np.maximum(
        row_content / content_scale,
        row_texture / texture_scale,
    )
    band_width = clamp_int(
        height * parameters.band_width_ratio,
        parameters.band_width_min_px,
        parameters.band_width_max_px,
    )
    kernel = np.ones(band_width, dtype=np.float64) / float(band_width)
    smoothed = np.convolve(residual, kernel, mode="same")
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

    candidates = tuple(
        evidence
        for row in selected
        if (
            evidence := _divider_evidence(
                residual,
                row,
                band_width,
                width,
                source="adaptive_lane_divider",
            )
        )
        is not None
    )
    center = height // DUAL_LANE_COUNT
    if all(
        abs(center - evidence.center) >= max(1, band_width // 2)
        for evidence in candidates
    ):
        center_evidence = _divider_evidence(
            residual,
            center,
            band_width,
            width,
            source="center_lane_divider_measurement",
        )
        if center_evidence is not None:
            candidates = (*candidates, center_evidence)
    return LaneDividerEvidenceSet(candidates, budget_exhausted)
