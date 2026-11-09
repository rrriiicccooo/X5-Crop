"""Low-level registered-gray transition measurement on one trace."""

from __future__ import annotations

from dataclasses import dataclass, fields
from hashlib import sha256
import math

import numpy as np

from ...domain import FiniteInterval
from ...domain import WorkspaceExtent
from ..robust_statistics import (
    REGISTERED_UINT8_QUANTIZATION_STEP,
    positive_mad_z,
    positive_mad_z_rows,
)
from .model import PhotoBoundaryMeasurementSpec
from .model import BoundaryAxis
from .transition_peak_source import (
    TransitionPeakGroupSource, TransitionPeakReference, TransitionPeakTraceSource,
)
from .transition_peak_capture import TransitionPeakCapture
from .trace_support import PIXEL_CENTER_HALF_EXTENT_PX


# Half-prominence is the geometric localization interval around one measured
# peak.  It is an algorithm definition, not a film tolerance or approval
# threshold.
PEAK_LOCALIZATION_PROMINENCE_FRACTION = 0.5


def transition_peak_scratch_bytes(coordinate_count: int) -> int:
    """Original 64Q masks/indices plus <=80Q shared ranks and construction.

    At most two localization types retain sorted values and inverse ranks
    (32Q). Stable ordering, its construction arrays, and current-group rank
    deletion are covered separately, including the other retained type.
    All arrays are local to one peak extraction call.
    """
    return 144 * coordinate_count


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
    peak_source: TransitionPeakTraceSource | None = None


@dataclass(frozen=True)
class TraceRowsMeasurement:
    """Local transition measurements for a batch of registered traces."""

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

    def __post_init__(self) -> None:
        arrays = (
            self.gradient_z,
            self.tone_z,
            self.texture_z,
            self.signed_gradient,
            self.left_tone,
            self.right_tone,
            self.left_texture,
            self.right_texture,
        )
        if (
            self.coordinates.ndim != 1
            or self.coordinates.dtype != np.int32
            or any(item.ndim != 2 for item in arrays)
            or any(item.dtype != np.float64 for item in arrays)
            or len({item.shape for item in arrays}) != 1
            or any(item.shape[1] != self.coordinates.size for item in arrays)
            or self.temporary_bytes < 0
        ):
            raise ValueError("trace rows measurement is invalid")


def trace_storage_bytes(measured: TraceMeasurement) -> int:
    """Count retained NumPy storage once; slices and broad aliases are views."""

    buffers: dict[int, int] = {}
    for record in (measured, measured.broad_material):
        if record is None:
            continue
        for field in fields(record):
            value = getattr(record, field.name)
            for array in (value if isinstance(value, tuple) else (value,)):
                if not isinstance(array, np.ndarray):
                    continue
                root = array
                while isinstance(root.base, np.ndarray):
                    root = root.base
                buffers[id(root)] = root.nbytes
    return sum(buffers.values()) + (0 if measured.peak_source is None else measured.peak_source.retained_bytes)


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
class TracePeakSignals:
    """Exact selection inputs, without unrelated side-statistic columns."""

    coordinates: np.ndarray
    gradient_z: np.ndarray
    tone_z: np.ndarray
    texture_z: np.ndarray
    signed_gradient: np.ndarray

    def __post_init__(self):
        if (self.coordinates.ndim != 1 or self.coordinates.dtype != np.int32
                or any(a.ndim != 1 or a.dtype != np.float64 or a.shape != self.coordinates.shape
                       for a in (self.gradient_z,self.tone_z,self.texture_z,self.signed_gradient))):
            raise ValueError('peak signals must retain their exact coordinate-aligned response rows')


@dataclass(frozen=True)
class TransitionPeakSelection:
    localization_interval: FiniteInterval
    physical_position_interval: FiniteInterval
    canonical_coordinate: float
    gradient_z: float
    tone_z: float
    texture_z: float
    peak_width_px: float
    prominence: float
    local_noise: float
    polarity: int
    coordinate_index: int
    source_group: TransitionPeakGroupSource | None = None
    source_reference: TransitionPeakReference | None = None


@dataclass(frozen=True, kw_only=True)
class MeasuredTransitionPeak(TransitionPeakSelection):
    left_tone: float
    right_tone: float
    left_texture: float
    right_texture: float


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


def _window_prefix(values: np.ndarray) -> np.ndarray:
    if values.ndim == 1:
        prefix = np.empty(values.size + 1, dtype=np.float64)
        prefix[0] = 0.0
        np.cumsum(values, dtype=np.float64, out=prefix[1:])
    elif values.ndim == 2:
        prefix = np.empty((values.shape[0], values.shape[1] + 1), dtype=np.float64)
        prefix[:, 0] = 0.0
        np.cumsum(values, axis=1, dtype=np.float64, out=prefix[:, 1:])
    else:
        raise ValueError("window means require a one- or two-dimensional array")
    return prefix


class _WindowPrefix:
    """Lazy preparation owned by one call and the exact unchanged input array."""

    __slots__ = ("values", "prefix")

    def __init__(self, values: np.ndarray):
        self.values = values
        self.prefix = None

    def for_values(self, values: np.ndarray) -> np.ndarray:
        if values is not self.values:
            raise ValueError("window prefix belongs to another numeric input")
        if self.prefix is None:
            self.prefix = _window_prefix(values)
        return self.prefix

    @property
    def temporary_bytes(self) -> int:
        return 0 if self.prefix is None else self.prefix.nbytes


def window_prefix_cache_bytes(source_length: int) -> int:
    """Two float64 prefixes: L+1 values and L differences-prefix entries."""
    if type(source_length) is not int or source_length < 0:
        raise ValueError("prefix source length must be a non-negative integer")
    return 0 if source_length == 0 else 8 * ((source_length + 1) + source_length)


def _prefix_cache_allowed(source_length, capacity):
    if capacity is not None and (type(capacity) is not int or capacity < 0):
        raise ValueError("prefix cache capacity must be a non-negative integer or None")
    return capacity is None or capacity > 0 and capacity >= window_prefix_cache_bytes(source_length)


def _trace_rows_buffer_reservation(rows, source_length, coordinate_count):
    """The existing row owner's array composition, evaluated from shapes only."""
    if coordinate_count == 0:
        return 0
    values = 8 * rows * source_length
    coordinates = 4 * coordinate_count
    differences = 8 * rows * max(0, source_length - 1)
    responses = 11 * 8 * rows * coordinate_count
    prefixes = 8 * rows * ((source_length + 1) + source_length)
    # diff + two tone/texture/signed-gradient temporaries + four median/MAD
    # response workspaces; eight scalar float64 reductions per row.
    arithmetic = differences + 10 * 8 * rows * coordinate_count + 8 * rows * 8
    return values + coordinates + differences + responses + prefixes + arithmetic


def scalar_trace_buffer_reservation(source_length: int, coordinate_count: int, *,
                                    include_broad_material: bool = True,
                                    prefix_cache_capacity_bytes: int | None = None) -> int:
    """Reserve returned storage PLUS construction scratch before a scalar call.

    One copy of the existing row-construction bound covers the sharp kernel.
    Broad adds two such bounds for its two scales, plus 32 float64 slots per
    coordinate for material reductions and median/MAD scratch: scale arrays
    are already covered; fewer than 16 material float outputs/temporaries,
    eight statistical work arrays and eight slots for masks/indices fit here.
    The existing source receipt contributes 1024 retained + 2048 work bytes.
    Cached prefixes are additional to these original-kernel bounds. The bound
    also covers standalone broad results; caller-owned native luma/scratch,
    input numeric/differences and earlier traces must be added by that caller.
    This function inspects no pixels and allocates no arrays.
    A sharp row's construction bound is at least 212Q bytes. Its retained 68Q
    plus the extraction scratch 144Q fit within that same phase maximum;
    broad construction has a larger bound. No extra resource pool is added.
    """
    if (type(source_length) is not int or source_length < 0 or type(coordinate_count) is not int
            or not 0 <= coordinate_count <= source_length or type(include_broad_material) is not bool):
        raise ValueError("scalar buffer reservation requires valid source/coordinate counts and a broad flag")
    cache_allowed = _prefix_cache_allowed(source_length, prefix_cache_capacity_bytes)
    if coordinate_count == 0:
        return 0
    row = _trace_rows_buffer_reservation(1, source_length, coordinate_count)
    original_kernel = row * (3 if include_broad_material else 1)
    if include_broad_material:
        original_kernel += 32 * 8 * coordinate_count
    cache = window_prefix_cache_bytes(source_length) if include_broad_material and cache_allowed else 0
    return original_kernel + 1024 + 2048 + cache


def _window_means(
    values: np.ndarray,
    coordinates: np.ndarray,
    window: int,
    gap: int,
    *,
    preparation: _WindowPrefix | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    left_stop = coordinates - gap
    left_start = left_stop - window
    right_start = coordinates + gap
    right_stop = right_start + window
    prefix = _window_prefix(values) if preparation is None else preparation.for_values(values)
    if values.ndim == 1:
        left = (prefix[left_stop] - prefix[left_start]) / float(window)
        right = (prefix[right_stop] - prefix[right_start]) / float(window)
    else:
        left = (prefix[:, left_stop] - prefix[:, left_start]) / float(window)
        right = (prefix[:, right_stop] - prefix[:, right_start]) / float(window)
    return left, right


def _material_scale_measurement(
    values: np.ndarray,
    differences: np.ndarray,
    coordinates: np.ndarray,
    *,
    window: int,
    gap: int,
    prefixes: tuple[_WindowPrefix, _WindowPrefix] | None = None,
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
        preparation=None if prefixes is None else prefixes[0],
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
        preparation=None if prefixes is None else prefixes[1],
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
    *,
    intensity_quantum: float = REGISTERED_UINT8_QUANTIZATION_STEP,
    _temporary_prefix_bytes: int = 0,
) -> BroadMaterialTraceMeasurement:
    if not math.isfinite(intensity_quantum) or intensity_quantum <= 0.0:
        raise ValueError("broad material intensity quantum must be positive")
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
            item > intensity_quantum
            for item in signed_tone_by_scale
        )
    )
    negative = np.logical_and.reduce(
        tuple(
            item < -intensity_quantum
            for item in signed_tone_by_scale
        )
    )
    polarity = np.zeros_like(signed_tone_by_scale[0], dtype=np.int8)
    polarity[positive] = 1
    polarity[negative] = -1
    left_background = np.logical_and.reduce(
        tuple(
            left + intensity_quantum < right
            for left, right in zip(
                left_texture_by_scale,
                right_texture_by_scale,
                strict=True,
            )
        )
    )
    right_background = np.logical_and.reduce(
        tuple(
            right + intensity_quantum < left
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
            > background_uniformity + intensity_quantum
        )
    )
    contrast_z = positive_mad_z(
        np.where(supported, contrast_lower_bound, 0.0),
        minimum_scale=intensity_quantum,
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
        temporary_bytes=sum(item.nbytes for item in arrays) + _temporary_prefix_bytes,
    )


def broad_material_trace_measurement(
    values: np.ndarray,
    differences: np.ndarray,
    coordinates: np.ndarray,
    scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
    *,
    intensity_quantum: float = REGISTERED_UINT8_QUANTIZATION_STEP,
    prefix_cache_capacity_bytes: int | None = None,
    _prefixes: tuple[_WindowPrefix, _WindowPrefix] | None = None,
) -> BroadMaterialTraceMeasurement:
    scales = (spec.local_window_mm, spec.broad_material_window_mm)
    cache_allowed = _prefix_cache_allowed(values.size, prefix_cache_capacity_bytes)
    if _prefixes is not None and not cache_allowed:
        raise ValueError("provided window prefixes exceed the call-local cache capacity")
    prefixes = (_prefixes if _prefixes is not None else
                (_WindowPrefix(values), _WindowPrefix(differences)) if cache_allowed else None)
    measured = tuple(
        _material_scale_measurement(
            values,
            differences,
            coordinates,
            window=max(1, int(math.ceil(window_mm * scale_px_per_mm))),
            gap=spec.transition_gap_px(scale_px_per_mm),
            prefixes=prefixes,
        )
        for window_mm in scales
    )
    # Both prefixes stay live across the two physical window scales. They are
    # call-local scratch, never retained in the returned trace or a cache.
    return broad_material_from_scale_measurements(
        scales,
        tuple(item[0] for item in measured),
        tuple(item[1] for item in measured),
        tuple(item[2] for item in measured),
        tuple(item[3] for item in measured),
        tuple(item[4] for item in measured),
        tuple(item[5] for item in measured),
        intensity_quantum=intensity_quantum,
        _temporary_prefix_bytes=0 if prefixes is None else sum(p.temporary_bytes for p in prefixes),
    )


def measure_trace(
    values_u8: np.ndarray,
    interval: FiniteInterval,
    scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
    *,
    include_broad_material: bool = False,
    peak_source_context: tuple[str, WorkspaceExtent, BoundaryAxis, int] | None = None,
    prefix_cache_capacity_bytes: int | None = None,
) -> TraceMeasurement:
    cache_allowed = _prefix_cache_allowed(values_u8.size, prefix_cache_capacity_bytes)
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
    value_prefix = _WindowPrefix(values) if include_broad_material and cache_allowed else None
    left_tone, right_tone = _window_means(values, coordinates, window, gap, preparation=value_prefix)
    tone = np.abs(right_tone - left_tone)
    differences = np.abs(np.diff(values))
    difference_prefix = _WindowPrefix(differences) if include_broad_material and cache_allowed else None
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
        preparation=difference_prefix,
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
            prefix_cache_capacity_bytes=prefix_cache_capacity_bytes,
            _prefixes=None if value_prefix is None else (value_prefix, difference_prefix),
        )
        if include_broad_material
        else None
    )
    del value_prefix, difference_prefix
    gradient_z = positive_mad_z(gradient, minimum_scale=REGISTERED_UINT8_QUANTIZATION_STEP)
    tone_z = positive_mad_z(tone, minimum_scale=REGISTERED_UINT8_QUANTIZATION_STEP)
    texture_z = positive_mad_z(texture, minimum_scale=REGISTERED_UINT8_QUANTIZATION_STEP)
    source = None
    if peak_source_context is not None:
        if values_u8.dtype != np.uint8:
            raise ValueError("original peak source requires canonical uint8 gray")
        digest = sha256()
        for array in (coordinates, gradient_z, tone_z, texture_z, signed_gradient):
            digest.update(memoryview(array).cast("B"))
        source_id, source_extent, boundary_axis, trace_coordinate = peak_source_context
        source = TransitionPeakTraceSource(source_id, source_extent, boundary_axis,
            trace_coordinate, (int(coordinates[0]), int(coordinates[-1])), window, gap,
            float(spec.gradient_z_minimum), float(spec.tone_or_texture_z_minimum), digest.hexdigest())
    return TraceMeasurement(
        coordinates=coordinates,
        gradient_z=gradient_z,
        tone_z=tone_z,
        texture_z=texture_z,
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
            + (2048 if source is not None else 0)
        ),
        broad_material=broad_material,
        peak_source=source,
    )


def _trace_rows_temporary_bytes(
    values: np.ndarray,
    coordinates: np.ndarray,
    differences: np.ndarray,
    left_tone: np.ndarray,
    right_tone: np.ndarray,
    tone: np.ndarray,
    left_texture: np.ndarray,
    right_texture: np.ndarray,
    texture: np.ndarray,
    signed_gradient: np.ndarray,
    gradient: np.ndarray,
    gradient_z: np.ndarray,
    tone_z: np.ndarray,
    texture_z: np.ndarray,
) -> int:
    """Conservatively bound all numeric buffers live during row measurement."""

    rows, trace_length = values.shape
    return _trace_rows_buffer_reservation(rows, trace_length, coordinates.size)


def measure_trace_rows(
    values_u8: np.ndarray,
    interval: FiniteInterval,
    scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
    *,
    intensity_quantum: float | None = None,
) -> TraceRowsMeasurement:
    """Measure local transitions for all rows in one frozen trace domain.

    This is the row-vectorized counterpart of :func:`measure_trace`.  It only
    computes the local transition arrays and does not perform broad-material,
    peak, identity, or role selection. The default units are uint8 codes;
    unclipped native intensities require an explicit positive quantum.
    """

    if intensity_quantum is None and values_u8.dtype != np.uint8:
        raise ValueError("trace rows require a two-dimensional uint8 array")
    quantum = REGISTERED_UINT8_QUANTIZATION_STEP if intensity_quantum is None else intensity_quantum
    if (values_u8.ndim != 2 or values_u8.dtype.kind not in "uif"
            or not np.all(np.isfinite(values_u8))
            or isinstance(quantum, bool) or not math.isfinite(quantum) or quantum <= 0.0):
        raise ValueError("registered trace rows require finite intensities and an explicit positive quantum")
    window = spec.local_window_px(scale_px_per_mm)
    gap = spec.transition_gap_px(scale_px_per_mm)
    trace_length = values_u8.shape[1]
    lower = max(window + gap, int(math.ceil(interval.minimum)))
    upper = min(
        trace_length - window - gap,
        int(math.floor(interval.maximum)) + 1,
    )
    if upper <= lower:
        coordinates = np.empty(0, dtype=np.int32)
        empty = np.empty((values_u8.shape[0], 0), dtype=np.float64)
        return TraceRowsMeasurement(
            coordinates,
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
    differences = np.abs(np.diff(values, axis=1))
    texture_coordinates = np.clip(
        coordinates,
        window + gap,
        differences.shape[1] - window - gap,
    )
    left_texture, right_texture = _window_means(
        differences,
        texture_coordinates,
        window,
        gap,
    )
    texture = np.abs(right_texture - left_texture)
    signed_gradient = (
        values[:, np.minimum(values.shape[1] - 1, coordinates + gap - 1)]
        - values[:, coordinates - gap]
    )
    gradient = np.abs(signed_gradient)
    gradient_z = positive_mad_z_rows(
        gradient,
        minimum_scale=quantum,
    )
    tone_z = positive_mad_z_rows(
        tone,
        minimum_scale=quantum,
    )
    texture_z = positive_mad_z_rows(
        texture,
        minimum_scale=quantum,
    )
    temporary_bytes = _trace_rows_temporary_bytes(
        values,
        coordinates,
        differences,
        left_tone,
        right_tone,
        tone,
        left_texture,
        right_texture,
        texture,
        signed_gradient,
        gradient,
        gradient_z,
        tone_z,
        texture_z,
    )
    return TraceRowsMeasurement(
        coordinates=coordinates,
        gradient_z=gradient_z,
        tone_z=tone_z,
        texture_z=texture_z,
        signed_gradient=signed_gradient,
        left_tone=left_tone,
        right_tone=right_tone,
        left_texture=left_texture,
        right_texture=right_texture,
        temporary_bytes=temporary_bytes,
    )


@dataclass
class _GroupNoiseStatistics:
    finite: bool
    zero_count: int
    sorted_values: np.ndarray | None = None
    ranks: np.ndarray | None = None


def _zero_median_statistics(values: np.ndarray) -> _GroupNoiseStatistics:
    return _GroupNoiseStatistics(bool(np.all(np.isfinite(values))),
                                 values.size - int(np.count_nonzero(values)))


def _group_local_noise(values: np.ndarray, group: np.ndarray, statistics: _GroupNoiseStatistics) -> float:
    """Exactly reproduce the outside-group median; groups contain unique indices."""
    outside_count = values.size - group.size
    if outside_count:
        outside_zeros = statistics.zero_count - (group.size - int(np.count_nonzero(values[group])))
        # A strict majority pins both middle order statistics to zero. Equality
        # is insufficient for an even-sized sample; nonfinite values fall back.
        if statistics.finite and outside_zeros > outside_count // 2:
            return 0.0
        if statistics.finite:
            if statistics.ranks is None:
                order = np.argsort(values, kind="stable")
                ranks = np.empty(values.size, dtype=np.intp)
                ranks[order] = np.arange(values.size, dtype=np.intp)
                statistics.sorted_values = values[order]
                statistics.ranks = ranks
            removed = np.sort(statistics.ranks[group])
            removed -= np.arange(group.size, dtype=np.intp)
            middle = (np.asarray((outside_count//2,), dtype=np.intp) if outside_count % 2
                      else np.asarray((outside_count//2-1, outside_count//2), dtype=np.intp))
            # Removing sorted ranks d_j shifts every remaining kth rank by
            # exactly count(d_j-j <= k). Both original median order statistics
            # survive, including ties and even/odd cardinality.
            middle += np.searchsorted(removed, middle, side="right")
            return float(np.mean(statistics.sorted_values[middle]))
        # Preserve the original NaN/Inf behavior; these are not independent
        # finite order statistics and must not take the indexed shortcut.
        outside = np.ones(values.size, dtype=bool)
        outside[group] = False
        return float(np.median(values[outside]))
    return float(np.min(values[group]))


def transition_peak_support(measurement: TraceMeasurement | TracePeakSignals, spec: PhotoBoundaryMeasurementSpec):
    """The original OR grouping support, separate from a connected step mask."""
    gradient_supported = measurement.gradient_z >= spec.gradient_z_minimum
    secondary = np.maximum(measurement.tone_z, measurement.texture_z)
    credible = gradient_supported | (secondary >= spec.tone_or_texture_z_minimum)
    return gradient_supported, secondary, credible


def measured_transition_peaks(
    measurement: TraceMeasurement,
    spec: PhotoBoundaryMeasurementSpec,
    *,
    split_gradient_reversals: bool,
    peak_source_capture: TransitionPeakCapture | None = None,
) -> tuple[MeasuredTransitionPeak, ...]:
    return _select_transition_peaks(measurement,spec,split_gradient_reversals=split_gradient_reversals,
                                   peak_source_capture=peak_source_capture,side_statistics=True)


def measured_transition_peak_geometry(measurement: TraceMeasurement | TracePeakSignals,
        spec: PhotoBoundaryMeasurementSpec, *, split_gradient_reversals: bool) -> tuple[TransitionPeakSelection,...]:
    """Use the same selector; materialize only fields consumed by a bridge."""
    return _select_transition_peaks(measurement,spec,split_gradient_reversals=split_gradient_reversals,
                                   peak_source_capture=None,side_statistics=False)


def _select_transition_peaks(measurement,spec,*,split_gradient_reversals,peak_source_capture,side_statistics):
    coordinates = measurement.coordinates
    gradient_supported, secondary, credible = transition_peak_support(measurement, spec)
    indices = np.flatnonzero(credible)
    del credible
    if indices.size == 0:
        return ()
    split_at = np.flatnonzero(np.diff(indices) > 1) + 1
    groups = np.split(indices, split_at)
    gradient_supported &= measurement.signed_gradient != 0.0
    noise_statistics = {}
    record_type = MeasuredTransitionPeak if side_statistics else TransitionPeakSelection
    records = []
    for group in groups:
        if group.size == 0:
            continue
        reliable_gradient = group[gradient_supported[group]]
        polarity_runs = ()
        if reliable_gradient.size:
            polarity_runs = (
                np.split(
                    reliable_gradient,
                    np.flatnonzero(
                        np.diff(measurement.signed_gradient[reliable_gradient] > 0.0)
                    ) + 1,
                )
                if split_gradient_reversals
                else (reliable_gradient,)
            )
        peak_candidates = (
            tuple(
                int(run[np.argmax(measurement.gradient_z[run])])
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
        key = bool(polarity_runs)
        statistics = noise_statistics.get(key)
        if statistics is None:
            statistics = _zero_median_statistics(localization)
            noise_statistics[key] = statistics
        local_noise = _group_local_noise(localization, group, statistics)
        source_group = None
        if peak_source_capture is not None and measurement.peak_source is not None and peak_source_capture.complete:
            if peak_source_capture.reserve_group(int(group.size), int(reliable_gradient.size), len(peak_candidates)):
                natural_runs = (polarity_runs if split_gradient_reversals else tuple(np.split(reliable_gradient, np.flatnonzero(
                    np.diff(measurement.signed_gradient[reliable_gradient] > 0.0)) + 1))
                    if reliable_gradient.size else ())
                source_group = TransitionPeakGroupSource(
                    source=measurement.peak_source,
                    measurement_domain_px=(int(coordinates[0]), int(coordinates[-1])),
                    credible_group_domain_px=(int(coordinates[group[0]]), int(coordinates[group[-1]])),
                    reliable_gradient_partitions=tuple((
                        1 if measurement.signed_gradient[run[0]] > 0 else -1,
                        tuple(map(int, coordinates[run]))) for run in natural_runs),
                    candidate_peak_coordinates_px=tuple(int(coordinates[index]) for index in peak_candidates),
                    selection_basis="gradient" if polarity_runs else "secondary",
                    split_gradient_reversals=split_gradient_reversals,
                )
                peak_source_capture.retain(source_group)
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
            assigned = group if len(peak_candidates) == 1 else group[
                (coordinates[group] >= physical_minimum)
                & (coordinates[group] <= physical_maximum)
            ]
            peak_position = int(np.searchsorted(assigned, peak_index))
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
            observed_left = int(peak_members[0])
            observed_right = int(peak_members[-1])
            while observed_left > 0 and same_peak(observed_left - 1):
                observed_left -= 1
            while observed_right + 1 < coordinates.size and same_peak(observed_right + 1):
                observed_right += 1
            if observed_left == 0 or observed_right == coordinates.size - 1:
                # A half-height lobe cut by the measured domain has no
                # observed midpoint.  Its visible tail must not become a
                # precise boundary position. Probe past credible-group ends
                # without changing their localization or merging identities:
                # a below-threshold but observed tail is not missing data.
                continue
            peak_minimum = (
                float(coordinates[int(peak_members[0])])
                - PIXEL_CENTER_HALF_EXTENT_PX
            )
            peak_maximum = (
                float(coordinates[int(peak_members[-1])])
                + PIXEL_CENTER_HALF_EXTENT_PX
            )
            side_fields = (dict(left_tone=float(measurement.left_tone[peak_index]),
                               right_tone=float(measurement.right_tone[peak_index]),
                               left_texture=float(measurement.left_texture[peak_index]),
                               right_texture=float(measurement.right_texture[peak_index])) if side_statistics else {})
            records.append(
                record_type(
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
                    peak_width_px=peak_maximum - peak_minimum,
                    prominence=prominence,
                    local_noise=local_noise,
                    polarity=peak_polarity,
                    coordinate_index=peak_index,
                    source_group=source_group,
                    source_reference=(None if source_group is None or not polarity_runs else
                        TransitionPeakReference(source_group.primitive_id, ordinal,
                            int(coordinates[peak_index]), peak_polarity)),
                    **side_fields,
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
    noise_statistics = _zero_median_statistics(material.contrast_z)
    records: list[MeasuredBroadMaterialPeak] = []
    for group in groups:
        if group.size == 0:
            continue
        peak_index = int(
            group[int(np.argmax(material.contrast_z[group]))]
        )
        local_noise = _group_local_noise(material.contrast_z, group, noise_statistics)
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
        observed_left = int(peak_members[0])
        observed_right = int(peak_members[-1])
        while (
            observed_left > 0
            and material.observable[observed_left - 1]
            and same_peak(observed_left - 1)
        ):
            observed_left -= 1
        while (
            observed_right + 1 < measurement.coordinates.size
            and material.observable[observed_right + 1]
            and same_peak(observed_right + 1)
        ):
            observed_right += 1
        if (
            observed_left == 0
            or observed_right == measurement.coordinates.size - 1
            or not material.observable[observed_left - 1]
            or not material.observable[observed_right + 1]
        ):
            # Broad windows have a smaller observable domain than the sharp
            # trace. Masked zeroes beyond it are not observed peak flanks.
            continue
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
