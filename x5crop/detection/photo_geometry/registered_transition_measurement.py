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
    broad_material: "BroadMaterialTraceMeasurement | None" = None


@dataclass(frozen=True)
class BroadMaterialTraceMeasurement:
    """Two-scale material state on one already registered trace."""

    window_scales_mm: tuple[float, ...]
    signed_tone_by_scale: tuple[np.ndarray, ...]
    left_tone_by_scale: tuple[np.ndarray, ...]
    right_tone_by_scale: tuple[np.ndarray, ...]
    left_texture_by_scale: tuple[np.ndarray, ...]
    right_texture_by_scale: tuple[np.ndarray, ...]
    observable: np.ndarray
    supported: np.ndarray
    polarity: np.ndarray
    background_side: np.ndarray
    contrast_lower_bound: np.ndarray
    contrast_z: np.ndarray
    background_uniformity_upper_bound: np.ndarray
    left_tone: np.ndarray
    right_tone: np.ndarray
    left_texture: np.ndarray
    right_texture: np.ndarray
    temporary_bytes: int

    def __post_init__(self) -> None:
        arrays = (
            *self.signed_tone_by_scale,
            *self.left_tone_by_scale,
            *self.right_tone_by_scale,
            *self.left_texture_by_scale,
            *self.right_texture_by_scale,
            self.observable,
            self.supported,
            self.polarity,
            self.background_side,
            self.contrast_lower_bound,
            self.contrast_z,
            self.background_uniformity_upper_bound,
            self.left_tone,
            self.right_tone,
            self.left_texture,
            self.right_texture,
        )
        if (
            len(self.window_scales_mm) < 2
            or tuple(sorted(set(self.window_scales_mm)))
            != self.window_scales_mm
            or any(
                not math.isfinite(value) or value <= 0.0
                for value in self.window_scales_mm
            )
            or any(
                len(values) != len(self.window_scales_mm)
                for values in (
                    self.signed_tone_by_scale,
                    self.left_tone_by_scale,
                    self.right_tone_by_scale,
                    self.left_texture_by_scale,
                    self.right_texture_by_scale,
                )
            )
            or not arrays
            or len({item.shape for item in arrays}) != 1
            or any(item.ndim != 1 for item in arrays)
            or self.observable.dtype != np.bool_
            or self.supported.dtype != np.bool_
            or self.polarity.dtype != np.int8
            or self.background_side.dtype != np.int8
            or np.any(~np.isin(self.polarity, (-1, 0, 1)))
            or np.any(~np.isin(self.background_side, (-1, 0, 1)))
            or np.any(self.contrast_lower_bound < 0.0)
            or np.any(self.contrast_z < 0.0)
            or np.any(self.background_uniformity_upper_bound < 0.0)
            or self.temporary_bytes < 0
        ):
            raise ValueError("broad material trace measurement is invalid")


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


@dataclass(frozen=True)
class MeasuredBroadMaterialPeak:
    localization_interval: FiniteInterval
    physical_position_interval: FiniteInterval
    canonical_coordinate: float
    window_scales_mm: tuple[float, ...]
    scale_tone_contrasts: tuple[float, ...]
    material_contrast_z: float
    material_contrast_lower_bound: float
    background_uniformity_upper_bound: float
    left_tone: float
    right_tone: float
    left_texture: float
    right_texture: float
    polarity: int
    background_side: int
    peak_width_px: float
    prominence: float
    local_noise: float
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


def _material_scale_measurement(
    values: np.ndarray,
    differences: np.ndarray,
    coordinates: np.ndarray,
    *,
    window: int,
    gap: int,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    observable = (
        (coordinates - gap - window >= 0)
        & (coordinates + gap + window <= values.size)
    )
    signed_tone = np.zeros(coordinates.size, dtype=np.float64)
    left_tone = np.zeros_like(signed_tone)
    right_tone = np.zeros_like(signed_tone)
    left_texture = np.zeros_like(signed_tone)
    right_texture = np.zeros_like(signed_tone)
    if not np.any(observable):
        return (
            signed_tone,
            left_tone,
            right_tone,
            left_texture,
            right_texture,
            observable,
        )
    retained = coordinates[observable]
    measured_left, measured_right = _window_means(
        values,
        retained,
        window,
        gap,
    )
    texture_coordinates = np.clip(
        retained,
        window + gap,
        differences.size - window - gap,
    )
    measured_left_texture, measured_right_texture = _window_means(
        differences,
        texture_coordinates,
        window,
        gap,
    )
    left_tone[observable] = measured_left
    right_tone[observable] = measured_right
    signed_tone[observable] = measured_right - measured_left
    left_texture[observable] = measured_left_texture
    right_texture[observable] = measured_right_texture
    return (
        signed_tone,
        left_tone,
        right_tone,
        left_texture,
        right_texture,
        observable,
    )


def broad_material_from_scale_measurements(
    window_scales_mm: tuple[float, ...],
    signed_tone_by_scale: tuple[np.ndarray, ...],
    left_tone_by_scale: tuple[np.ndarray, ...],
    right_tone_by_scale: tuple[np.ndarray, ...],
    left_texture_by_scale: tuple[np.ndarray, ...],
    right_texture_by_scale: tuple[np.ndarray, ...],
    observable_by_scale: tuple[np.ndarray, ...],
) -> BroadMaterialTraceMeasurement:
    if (
        len(window_scales_mm) < 2
        or any(
            len(values) != len(window_scales_mm)
            for values in (
                signed_tone_by_scale,
                left_tone_by_scale,
                right_tone_by_scale,
                left_texture_by_scale,
                right_texture_by_scale,
                observable_by_scale,
            )
        )
    ):
        raise ValueError("broad material scales are incomplete")
    observable = np.logical_and.reduce(observable_by_scale)
    positive = np.logical_and.reduce(
        tuple(
            item > REGISTERED_UINT8_QUANTIZATION_STEP
            for item in signed_tone_by_scale
        )
    )
    negative = np.logical_and.reduce(
        tuple(
            item < -REGISTERED_UINT8_QUANTIZATION_STEP
            for item in signed_tone_by_scale
        )
    )
    polarity = np.zeros_like(signed_tone_by_scale[0], dtype=np.int8)
    polarity[positive] = 1
    polarity[negative] = -1
    left_background = np.logical_and.reduce(
        tuple(
            left + REGISTERED_UINT8_QUANTIZATION_STEP < right
            for left, right in zip(
                left_texture_by_scale,
                right_texture_by_scale,
                strict=True,
            )
        )
    )
    right_background = np.logical_and.reduce(
        tuple(
            right + REGISTERED_UINT8_QUANTIZATION_STEP < left
            for left, right in zip(
                left_texture_by_scale,
                right_texture_by_scale,
                strict=True,
            )
        )
    )
    background_side = np.zeros_like(signed_tone_by_scale[0], dtype=np.int8)
    background_side[left_background] = -1
    background_side[right_background] = 1
    contrast_lower_bound = np.minimum.reduce(
        tuple(np.abs(item) for item in signed_tone_by_scale)
    )
    left_uniformity = np.maximum.reduce(left_texture_by_scale)
    right_uniformity = np.maximum.reduce(right_texture_by_scale)
    background_uniformity = np.where(
        background_side < 0,
        left_uniformity,
        np.where(background_side > 0, right_uniformity, 0.0),
    )
    supported = (
        observable
        & (polarity != 0)
        & (background_side != 0)
        & (
            contrast_lower_bound
            > background_uniformity + REGISTERED_UINT8_QUANTIZATION_STEP
        )
    )
    contrast_z = positive_mad_z(
        np.where(supported, contrast_lower_bound, 0.0),
        minimum_scale=REGISTERED_UINT8_QUANTIZATION_STEP,
    )
    broad_index = len(window_scales_mm) - 1
    arrays = (
        *signed_tone_by_scale,
        *left_tone_by_scale,
        *right_tone_by_scale,
        *left_texture_by_scale,
        *right_texture_by_scale,
        observable,
        supported,
        polarity,
        background_side,
        contrast_lower_bound,
        contrast_z,
        background_uniformity,
    )
    return BroadMaterialTraceMeasurement(
        window_scales_mm=window_scales_mm,
        signed_tone_by_scale=signed_tone_by_scale,
        left_tone_by_scale=left_tone_by_scale,
        right_tone_by_scale=right_tone_by_scale,
        left_texture_by_scale=left_texture_by_scale,
        right_texture_by_scale=right_texture_by_scale,
        observable=observable,
        supported=supported,
        polarity=polarity,
        background_side=background_side,
        contrast_lower_bound=contrast_lower_bound,
        contrast_z=contrast_z,
        background_uniformity_upper_bound=background_uniformity,
        left_tone=left_tone_by_scale[broad_index],
        right_tone=right_tone_by_scale[broad_index],
        left_texture=left_texture_by_scale[broad_index],
        right_texture=right_texture_by_scale[broad_index],
        temporary_bytes=sum(item.nbytes for item in arrays),
    )


def broad_material_trace_measurement(
    values: np.ndarray,
    differences: np.ndarray,
    coordinates: np.ndarray,
    scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
) -> BroadMaterialTraceMeasurement:
    scales = (spec.local_window_mm, spec.broad_material_window_mm)
    measured = tuple(
        _material_scale_measurement(
            values,
            differences,
            coordinates,
            window=max(1, int(math.ceil(window_mm * scale_px_per_mm))),
            gap=spec.transition_gap_px(scale_px_per_mm),
        )
        for window_mm in scales
    )
    return broad_material_from_scale_measurements(
        scales,
        tuple(item[0] for item in measured),
        tuple(item[1] for item in measured),
        tuple(item[2] for item in measured),
        tuple(item[3] for item in measured),
        tuple(item[4] for item in measured),
        tuple(item[5] for item in measured),
    )


def measure_trace(
    values_u8: np.ndarray,
    interval: FiniteInterval,
    scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
    *,
    include_broad_material: bool = False,
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
    broad_material = (
        broad_material_trace_measurement(
            values,
            differences,
            coordinates,
            scale_px_per_mm,
            spec,
        )
        if include_broad_material
        else None
    )
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
            + (0 if broad_material is None else broad_material.temporary_bytes)
        ),
        broad_material=broad_material,
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


def measured_broad_material_peaks(
    measurement: TraceMeasurement,
    spec: PhotoBoundaryMeasurementSpec,
) -> tuple[MeasuredBroadMaterialPeak, ...]:
    """Localize broad material changes without pretending they are gradients."""

    material = measurement.broad_material
    if material is None or measurement.coordinates.size == 0:
        return ()
    credible = material.supported & (
        material.contrast_z >= spec.tone_or_texture_z_minimum
    )
    indices = np.flatnonzero(credible)
    if indices.size == 0:
        return ()
    split_at = np.flatnonzero(
        (np.diff(indices) > 1)
        | (
            material.polarity[indices[1:]]
            != material.polarity[indices[:-1]]
        )
        | (
            material.background_side[indices[1:]]
            != material.background_side[indices[:-1]]
        )
    ) + 1
    groups = np.split(indices, split_at)
    records: list[MeasuredBroadMaterialPeak] = []
    for group in groups:
        if group.size == 0:
            continue
        peak_index = int(
            group[int(np.argmax(material.contrast_z[group]))]
        )
        outside = np.ones(material.contrast_z.size, dtype=bool)
        outside[group] = False
        local_noise = float(
            np.median(material.contrast_z[outside])
            if np.any(outside)
            else np.min(material.contrast_z[group])
        )
        prominence = max(
            0.0,
            float(material.contrast_z[peak_index]) - local_noise,
        )
        half_height = (
            local_noise
            + PEAK_LOCALIZATION_PROMINENCE_FRACTION * prominence
        )
        peak_position = int(np.flatnonzero(group == peak_index)[0])
        left_position = peak_position
        right_position = peak_position
        peak_polarity = int(material.polarity[peak_index])
        peak_background = int(material.background_side[peak_index])

        def same_peak(candidate: int) -> bool:
            return (
                material.contrast_z[candidate] >= half_height
                and int(material.polarity[candidate]) == peak_polarity
                and int(material.background_side[candidate])
                == peak_background
            )

        while left_position > 0 and same_peak(
            int(group[left_position - 1])
        ):
            left_position -= 1
        while right_position + 1 < group.size and same_peak(
            int(group[right_position + 1])
        ):
            right_position += 1
        peak_members = group[left_position : right_position + 1]
        peak_minimum = (
            float(measurement.coordinates[int(peak_members[0])])
            - PIXEL_CENTER_HALF_EXTENT_PX
        )
        peak_maximum = (
            float(measurement.coordinates[int(peak_members[-1])])
            + PIXEL_CENTER_HALF_EXTENT_PX
        )
        physical_minimum = (
            float(measurement.coordinates[int(group[0])])
            - PIXEL_CENTER_HALF_EXTENT_PX
        )
        physical_maximum = (
            float(measurement.coordinates[int(group[-1])])
            + PIXEL_CENTER_HALF_EXTENT_PX
        )
        records.append(
            MeasuredBroadMaterialPeak(
                localization_interval=FiniteInterval(
                    peak_minimum,
                    peak_maximum,
                ),
                physical_position_interval=FiniteInterval(
                    physical_minimum,
                    physical_maximum,
                ),
                canonical_coordinate=(peak_minimum + peak_maximum) / 2.0,
                window_scales_mm=material.window_scales_mm,
                scale_tone_contrasts=tuple(
                    abs(float(values[peak_index]))
                    for values in material.signed_tone_by_scale
                ),
                material_contrast_z=float(
                    material.contrast_z[peak_index]
                ),
                material_contrast_lower_bound=float(
                    material.contrast_lower_bound[peak_index]
                ),
                background_uniformity_upper_bound=float(
                    material.background_uniformity_upper_bound[peak_index]
                ),
                left_tone=float(material.left_tone[peak_index]),
                right_tone=float(material.right_tone[peak_index]),
                left_texture=float(material.left_texture[peak_index]),
                right_texture=float(material.right_texture[peak_index]),
                polarity=peak_polarity,
                background_side=peak_background,
                peak_width_px=peak_maximum - peak_minimum,
                prominence=prominence,
                local_noise=local_noise,
                coordinate_index=peak_index,
            )
        )
    return tuple(records)
