"""Low-level registered-gray transition measurement on one trace."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ...domain import FiniteInterval
from ..robust_statistics import (
    REGISTERED_UINT8_QUANTIZATION_STEP,
    positive_mad_z,
)
from .model import PhotoBoundaryMeasurementSpec
from .trace_support import PIXEL_CENTER_HALF_EXTENT_PX


# Half-prominence is the geometric localization interval around one measured
# peak.  It is an algorithm definition, not a film tolerance or approval
# threshold.
PEAK_LOCALIZATION_PROMINENCE_FRACTION = 0.5


@dataclass(frozen=True)
class TraceMeasurement:
    coordinates: np.ndarray
    gradient_z: np.ndarray
    tone_z: np.ndarray
    texture_z: np.ndarray
    signed_gradient: np.ndarray
    left_tone: np.ndarray
    right_tone: np.ndarray
    left_texture: np.ndarray
    right_texture: np.ndarray
    temporary_bytes: int


@dataclass(frozen=True)
class MeasuredTransitionPeak:
    localization_interval: FiniteInterval
    physical_position_interval: FiniteInterval
    canonical_coordinate: float
    gradient_z: float
    tone_z: float
    texture_z: float
    left_tone: float
    right_tone: float
    left_texture: float
    right_texture: float
    peak_width_px: float
    prominence: float
    local_noise: float
    polarity: int
    coordinate_index: int


def _window_means(
    values: np.ndarray,
    coordinates: np.ndarray,
    window: int,
    gap: int,
) -> tuple[np.ndarray, np.ndarray]:
    prefix = np.empty(values.size + 1, dtype=np.float64)
    prefix[0] = 0.0
    np.cumsum(values, dtype=np.float64, out=prefix[1:])
    left_stop = coordinates - gap
    left_start = left_stop - window
    right_start = coordinates + gap
    right_stop = right_start + window
    left = (prefix[left_stop] - prefix[left_start]) / float(window)
    right = (prefix[right_stop] - prefix[right_start]) / float(window)
    return left, right


def measure_trace(
    values_u8: np.ndarray,
    interval: FiniteInterval,
    scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
) -> TraceMeasurement:
    window = spec.local_window_px(scale_px_per_mm)
    gap = spec.transition_gap_px(scale_px_per_mm)
    lower = max(window + gap, int(math.ceil(interval.minimum)))
    upper = min(
        values_u8.size - window - gap,
        int(math.floor(interval.maximum)) + 1,
    )
    if upper <= lower:
        empty = np.empty(0, dtype=np.float64)
        return TraceMeasurement(
            np.empty(0, dtype=np.int32),
            empty,
            empty.copy(),
            empty.copy(),
            empty.copy(),
            empty.copy(),
            empty.copy(),
            empty.copy(),
            empty.copy(),
            0,
        )
    coordinates = np.arange(lower, upper, dtype=np.int32)
    values = values_u8.astype(np.float64, copy=False)
    left_tone, right_tone = _window_means(values, coordinates, window, gap)
    tone = np.abs(right_tone - left_tone)
    differences = np.abs(np.diff(values))
    texture_coordinates = np.clip(
        coordinates,
        window + gap,
        differences.size - window - gap,
    )
    left_texture, right_texture = _window_means(
        differences,
        texture_coordinates,
        window,
        gap,
    )
    texture = np.abs(right_texture - left_texture)
    signed_gradient = (
        values[np.minimum(values.size - 1, coordinates + gap - 1)]
        - values[coordinates - gap]
    )
    gradient = np.abs(signed_gradient)
    return TraceMeasurement(
        coordinates=coordinates,
        gradient_z=positive_mad_z(
            gradient,
            minimum_scale=REGISTERED_UINT8_QUANTIZATION_STEP,
        ),
        tone_z=positive_mad_z(
            tone,
            minimum_scale=REGISTERED_UINT8_QUANTIZATION_STEP,
        ),
        texture_z=positive_mad_z(
            texture,
            minimum_scale=REGISTERED_UINT8_QUANTIZATION_STEP,
        ),
        signed_gradient=signed_gradient,
        left_tone=left_tone,
        right_tone=right_tone,
        left_texture=left_texture,
        right_texture=right_texture,
        temporary_bytes=int(
            coordinates.nbytes
            + left_tone.nbytes
            + right_tone.nbytes
            + differences.nbytes
            + left_texture.nbytes
            + right_texture.nbytes
            + gradient.nbytes
        ),
    )


def measured_transition_peaks(
    measurement: TraceMeasurement,
    spec: PhotoBoundaryMeasurementSpec,
    *,
    split_gradient_reversals: bool,
) -> tuple[MeasuredTransitionPeak, ...]:
    coordinates = measurement.coordinates
    credible = (
        (measurement.gradient_z >= spec.gradient_z_minimum)
        | (
            np.maximum(measurement.tone_z, measurement.texture_z)
            >= spec.tone_or_texture_z_minimum
        )
    )
    indices = np.flatnonzero(credible)
    if indices.size == 0:
        return ()
    split_at = np.flatnonzero(np.diff(indices) > 1) + 1
    groups = np.split(indices, split_at)
    secondary = np.maximum(measurement.tone_z, measurement.texture_z)
    records: list[MeasuredTransitionPeak] = []
    for group in groups:
        if group.size == 0:
            continue
        reliable_gradient = tuple(
            int(index)
            for index in group
            if measurement.gradient_z[int(index)] >= spec.gradient_z_minimum
            and measurement.signed_gradient[int(index)] != 0.0
        )
        polarity_runs: list[list[int]] = []
        for index in reliable_gradient:
            polarity = 1 if measurement.signed_gradient[index] > 0.0 else -1
            previous = (
                None
                if not polarity_runs
                else 1
                if measurement.signed_gradient[polarity_runs[-1][-1]] > 0.0
                else -1
            )
            if not split_gradient_reversals:
                if not polarity_runs:
                    polarity_runs.append([])
                polarity_runs[0].append(index)
            elif previous != polarity:
                polarity_runs.append([index])
            else:
                polarity_runs[-1].append(index)
        peak_candidates = (
            tuple(
                max(run, key=lambda index: (measurement.gradient_z[index], -index))
                for run in polarity_runs
            )
            if polarity_runs
            else (int(group[int(np.argmax(secondary[group]))]),)
        )
        partitions = tuple(
            math.floor(
                (
                    float(coordinates[left_peak])
                    + float(coordinates[right_peak])
                )
                / 2.0
            )
            + PIXEL_CENTER_HALF_EXTENT_PX
            for left_peak, right_peak in zip(
                peak_candidates,
                peak_candidates[1:],
            )
        )
        localization = measurement.gradient_z if polarity_runs else secondary
        outside = np.ones(localization.size, dtype=bool)
        outside[group] = False
        local_noise = float(
            np.median(localization[outside])
            if np.any(outside)
            else np.min(localization[group])
        )
        for ordinal, peak_index in enumerate(peak_candidates):
            prominence = max(0.0, float(localization[peak_index]) - local_noise)
            half_height = (
                local_noise
                + PEAK_LOCALIZATION_PROMINENCE_FRACTION * prominence
            )
            physical_minimum = (
                float(coordinates[int(group[0])])
                - PIXEL_CENTER_HALF_EXTENT_PX
                if ordinal == 0
                else partitions[ordinal - 1]
            )
            physical_maximum = (
                float(coordinates[int(group[-1])])
                + PIXEL_CENTER_HALF_EXTENT_PX
                if ordinal == len(peak_candidates) - 1
                else partitions[ordinal]
            )
            assigned = group[
                (coordinates[group] >= physical_minimum)
                & (coordinates[group] <= physical_maximum)
            ]
            peak_position = int(np.flatnonzero(assigned == peak_index)[0])
            left_position = peak_position
            right_position = peak_position
            peak_polarity = (
                1
                if measurement.signed_gradient[peak_index] > 0.0
                else -1
                if measurement.signed_gradient[peak_index] < 0.0
                else 0
            )

            def same_peak(candidate: int) -> bool:
                candidate_polarity = (
                    1
                    if measurement.signed_gradient[candidate] > 0.0
                    else -1
                    if measurement.signed_gradient[candidate] < 0.0
                    else 0
                )
                return localization[candidate] >= half_height and (
                    not polarity_runs or candidate_polarity == peak_polarity
                )

            while left_position > 0 and same_peak(
                int(assigned[left_position - 1])
            ):
                left_position -= 1
            while right_position + 1 < assigned.size and same_peak(
                int(assigned[right_position + 1])
            ):
                right_position += 1
            peak_members = assigned[left_position : right_position + 1]
            peak_minimum = (
                float(coordinates[int(peak_members[0])])
                - PIXEL_CENTER_HALF_EXTENT_PX
            )
            peak_maximum = (
                float(coordinates[int(peak_members[-1])])
                + PIXEL_CENTER_HALF_EXTENT_PX
            )
            records.append(
                MeasuredTransitionPeak(
                    localization_interval=FiniteInterval(
                        peak_minimum,
                        peak_maximum,
                    ),
                    physical_position_interval=FiniteInterval(
                        physical_minimum,
                        physical_maximum,
                    ),
                    canonical_coordinate=(peak_minimum + peak_maximum) / 2.0,
                    gradient_z=float(measurement.gradient_z[peak_index]),
                    tone_z=float(measurement.tone_z[peak_index]),
                    texture_z=float(measurement.texture_z[peak_index]),
                    left_tone=float(measurement.left_tone[peak_index]),
                    right_tone=float(measurement.right_tone[peak_index]),
                    left_texture=float(measurement.left_texture[peak_index]),
                    right_texture=float(measurement.right_texture[peak_index]),
                    peak_width_px=peak_maximum - peak_minimum,
                    prominence=prominence,
                    local_noise=local_noise,
                    polarity=peak_polarity,
                    coordinate_index=peak_index,
                )
            )
    return tuple(records)
