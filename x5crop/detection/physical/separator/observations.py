from __future__ import annotations

from math import ceil, floor

import numpy as np

from ....domain import MeasurementProvenance
from ....policies.parameters.separator import SeparatorObservationParameters
from ....utils import runs_from_mask
from x5crop.domain import PixelInterval, SeparatorBandObservation


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
    minimum_width = max(1, int(parameters.minimum_run_px))
    measured: list[SeparatorBandObservation] = []
    focused = profile[local_start:local_end]
    for start, end in runs_from_mask(
        focused >= float(parameters.profile_threshold)
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
                score=float(focused[start:end].mean()),
                provenance=MeasurementProvenance(
                    root_measurement="separator_profile",
                    source="focused_dimension_window",
                    dependencies=(
                        "gray_work",
                        "frame_dimensions",
                        "sequence_boundaries",
                    ),
                ),
                tonal_evidence=float(focused[start:end].mean()),
            )
        )
    return max(measured, key=lambda item: (item.score, item.width), default=None)


def measure_separator_bands(
    profile: np.ndarray,
    *,
    corridor_start: float,
    parameters: SeparatorObservationParameters,
) -> tuple[SeparatorBandObservation, ...]:
    if profile.ndim != 1:
        raise ValueError("separator profile must be one-dimensional")
    minimum_width = max(1, int(parameters.minimum_run_px))
    measured: list[SeparatorBandObservation] = []
    for local_start, local_end in runs_from_mask(
        profile >= float(parameters.profile_threshold)
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
                score=float(profile[local_start:local_end].mean()),
                provenance=MeasurementProvenance(
                    root_measurement="separator_profile",
                    source="observed_separator_band",
                    dependencies=("gray_work", "boundary_corridor"),
                ),
                tonal_evidence=float(profile[local_start:local_end].mean()),
            )
        )
    budget = max(0, int(parameters.maximum_observations))
    if budget == 0:
        return ()
    strongest = sorted(
        measured,
        key=lambda observation: (observation.score, observation.width),
        reverse=True,
    )[:budget]
    return tuple(sorted(strongest, key=lambda observation: observation.center))
