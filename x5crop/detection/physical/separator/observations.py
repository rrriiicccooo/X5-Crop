from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

import numpy as np

from ....domain import MeasurementProvenance
from ....configuration.separator import SeparatorObservationParameters
from ....utils import runs_from_mask
from x5crop.domain import PixelInterval, SeparatorBandObservation


@dataclass(frozen=True)
class SeparatorObservationSet:
    observations: tuple[SeparatorBandObservation, ...]
    budget_exhausted: bool


def _activation_threshold(
    profile: np.ndarray,
    parameters: SeparatorObservationParameters,
) -> tuple[float, float] | None:
    if not profile.size:
        return None
    minimum = float(profile.min())
    maximum = float(profile.max())
    spread = maximum - minimum
    if spread <= float(parameters.minimum_profile_range):
        return None
    threshold = float(
        np.percentile(profile, parameters.activation_percentile)
    )
    return threshold, spread


def measure_focused_separator_band(
    profile: np.ndarray,
    allowed_interval: PixelInterval,
    *,
    corridor_start: float,
    parameters: SeparatorObservationParameters,
) -> SeparatorBandObservation | None:
    if profile.ndim != 1:
        raise ValueError("separator profile must be one-dimensional")
    local_start = max(
        0,
        int(floor(float(allowed_interval.minimum) - float(corridor_start))),
    )
    local_end = min(
        int(profile.size),
        int(ceil(float(allowed_interval.maximum) - float(corridor_start))),
    )
    if local_end <= local_start:
        return None
    minimum_width = int(parameters.minimum_run_px)
    measured: list[SeparatorBandObservation] = []
    focused = profile[local_start:local_end]
    activation = _activation_threshold(profile, parameters)
    if activation is None:
        return None
    threshold, spread = activation
    for start, end in runs_from_mask(
        focused >= threshold
    ):
        if end - start < minimum_width:
            continue
        absolute_start = float(corridor_start + local_start + start)
        absolute_end = float(corridor_start + local_start + end)
        measured.append(
            SeparatorBandObservation(
                start=absolute_start,
                end=absolute_end,
                center=0.5 * (absolute_start + absolute_end),
                tonal_evidence=float(
                    max(0.0, focused[start:end].mean() - threshold) / spread
                ),
                provenance=MeasurementProvenance(
                    root_measurement="separator_profile",
                    source="focused_dimension_window",
                    dependencies=(
                        "gray_work",
                        "frame_dimensions",
                        "sequence_boundaries",
                    ),
                ),
            )
        )
    return max(
        measured,
        key=lambda item: (item.tonal_evidence, item.width),
        default=None,
    )


def measure_separator_bands(
    profile: np.ndarray,
    *,
    corridor_start: float,
    parameters: SeparatorObservationParameters,
) -> SeparatorObservationSet:
    if profile.ndim != 1:
        raise ValueError("separator profile must be one-dimensional")
    activation = _activation_threshold(profile, parameters)
    if activation is None:
        return SeparatorObservationSet((), False)
    threshold, spread = activation
    minimum_width = int(parameters.minimum_run_px)
    measured: list[SeparatorBandObservation] = []
    for local_start, local_end in runs_from_mask(
        profile >= threshold
    ):
        if int(local_end) - int(local_start) < minimum_width:
            continue
        start = float(corridor_start) + float(local_start)
        end = float(corridor_start) + float(local_end)
        center = 0.5 * (start + end)
        measured.append(
            SeparatorBandObservation(
                start=start,
                end=end,
                center=center,
                tonal_evidence=float(
                    max(0.0, profile[local_start:local_end].mean() - threshold)
                    / spread
                ),
                provenance=MeasurementProvenance(
                    root_measurement="separator_profile",
                    source="observed_separator_band",
                    dependencies=("gray_work", "boundary_corridor"),
                ),
            )
        )
    budget = int(parameters.maximum_observations)
    strongest = sorted(
        measured,
        key=lambda observation: (
            observation.tonal_evidence,
            observation.width,
        ),
        reverse=True,
    )[:budget]
    return SeparatorObservationSet(
        observations=tuple(
            sorted(strongest, key=lambda observation: observation.center)
        ),
        budget_exhausted=len(measured) > budget,
    )
