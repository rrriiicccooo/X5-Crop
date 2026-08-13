from __future__ import annotations

import cv2
import numpy as np
from scipy import ndimage

from ...domain import (
    Box,
    ObservationId,
)
from ..robust_statistics import REGISTERED_UINT8_QUANTIZATION_STEP
from ...run_local_identity import run_local_id
from .content_occupancy_model import (
    CONTENT_OCCUPANCY_MEASUREMENT_SPEC,
    ContentOccupancyMeasurementSpec,
    ContentOccupancyObservation,
    ContentOccupancyObservationSet,
)


# OpenCV's 3x3 Scharr derivative has a positive-side coefficient sum of 16;
# 1/32 gives the centred derivative in registered-gray code units.  This is a
# kernel normalization, not a content-confidence threshold.
SCHARR_DERIVATIVE_NORMALIZATION = 1.0 / 32.0


def _stable_id(
    lane_id: str,
    source_box: Box,
    source_cells: tuple[Box, ...],
    reliability: float,
) -> ObservationId:
    return ObservationId(
        run_local_id(
            "content",
            lane_id,
            source_box,
            source_cells,
            reliability.hex(),
        )
    )


def _source_box_from_work_box(box: Box, layout: str) -> Box:
    if layout == "horizontal":
        return box
    if layout == "vertical":
        return Box(box.top, box.left, box.bottom, box.right)
    raise ValueError(f"unsupported content-observation layout: {layout}")


def _sample_indices(
    extent: int,
    step_px: int,
    *,
    minimum_cell_extent_px: int,
) -> np.ndarray:
    if extent <= 0 or step_px <= 0:
        raise ValueError("content sampling extent and step must be positive")
    values = np.arange(0, extent, step_px, dtype=np.int64)
    if (
        values.size > 1
        and extent - int(values[-1]) < minimum_cell_extent_px
    ):
        values = values[:-1]
    if values[-1] != extent:
        values = np.append(values, extent)
    return values


def _subcell_indices(
    cell_indices: np.ndarray,
    *,
    subcells_per_axis: int,
) -> np.ndarray:
    """Subdivide every physical cell without crossing its boundary."""

    values: list[int] = []
    for start, stop in zip(cell_indices, cell_indices[1:]):
        width = int(stop - start)
        if width < subcells_per_axis:
            raise ValueError("content cell is too small for internal gradients")
        values.extend(
            int(start) + width * index // subcells_per_axis
            for index in range(subcells_per_axis)
        )
    values.append(int(cell_indices[-1]))
    result = np.asarray(values, dtype=np.int64)
    if np.any(np.diff(result) <= 0):
        raise ValueError("content subcell lattice must be strictly increasing")
    return result


def _segment_means(
    values: np.ndarray,
    starts: np.ndarray,
    stops: np.ndarray,
) -> np.ndarray:
    prefix = np.empty(values.size + 1, dtype=np.float64)
    prefix[0] = 0.0
    np.cumsum(values, dtype=np.float64, out=prefix[1:])
    lengths = stops - starts
    if np.any(lengths <= 0):
        raise ValueError("content lattice segment is empty")
    return (prefix[stops] - prefix[starts]) / lengths


def _cell_means(
    lane: np.ndarray,
    long_indices: np.ndarray,
    cross_indices: np.ndarray,
) -> np.ndarray:
    means = np.empty(
        (len(cross_indices) - 1, len(long_indices) - 1),
        dtype=np.float32,
    )
    for row, (cross_start, cross_stop) in enumerate(
        zip(cross_indices, cross_indices[1:])
    ):
        strip_mean = np.mean(
            lane[int(cross_start):int(cross_stop), :],
            axis=0,
            dtype=np.float64,
        )
        means[row] = _segment_means(
            strip_mean,
            long_indices[:-1],
            long_indices[1:],
        )
    return means


def _two_dimensional_structure(
    lane: np.ndarray,
    long_indices: np.ndarray,
    cross_indices: np.ndarray,
    *,
    spec: ContentOccupancyMeasurementSpec,
) -> tuple[np.ndarray, np.ndarray]:
    """Return second-direction signal and its tensor energy fraction.

    Scharr gradients are evaluated on a four-by-four subcell lattice.  Only
    the central two-by-two samples are retained, so every gradient footprint
    lies wholly inside its owning physical cell.  A strong edge between two
    cells can therefore never manufacture occupied cells on both sides.
    """

    subcells = spec.internal_subcells_per_axis
    fine_long_indices = _subcell_indices(
        long_indices,
        subcells_per_axis=subcells,
    )
    fine_cross_indices = _subcell_indices(
        cross_indices,
        subcells_per_axis=subcells,
    )
    means = _cell_means(lane, fine_long_indices, fine_cross_indices)
    gradient_x = cv2.Scharr(
        means,
        cv2.CV_32F,
        1,
        0,
        scale=SCHARR_DERIVATIVE_NORMALIZATION,
        borderType=cv2.BORDER_REFLECT_101,
    )
    gradient_y = cv2.Scharr(
        means,
        cv2.CV_32F,
        0,
        1,
        scale=SCHARR_DERIVATIVE_NORMALIZATION,
        borderType=cv2.BORDER_REFLECT_101,
    )
    cell_rows = len(cross_indices) - 1
    cell_columns = len(long_indices) - 1
    gradient_x = gradient_x.reshape(
        cell_rows,
        subcells,
        cell_columns,
        subcells,
    )[:, 1:-1, :, 1:-1]
    gradient_y = gradient_y.reshape(
        cell_rows,
        subcells,
        cell_columns,
        subcells,
    )[:, 1:-1, :, 1:-1]
    tensor_xx = np.mean(gradient_x * gradient_x, axis=(1, 3))
    tensor_yy = np.mean(gradient_y * gradient_y, axis=(1, 3))
    tensor_xy = np.mean(gradient_x * gradient_y, axis=(1, 3))
    trace = tensor_xx + tensor_yy
    discriminant = np.sqrt(
        np.maximum(
            0.0,
            (tensor_xx - tensor_yy) ** 2 + 4.0 * tensor_xy * tensor_xy,
        )
    )
    minimum_eigenvalue = np.maximum(0.0, (trace - discriminant) * 0.5)
    maximum_eigenvalue = np.maximum(0.0, (trace + discriminant) * 0.5)
    second_fraction = np.divide(
        minimum_eigenvalue,
        maximum_eigenvalue,
        out=np.zeros_like(minimum_eigenvalue),
        where=maximum_eigenvalue > np.finfo(np.float32).eps,
    )
    # Eigenvalues are squared registered-gray gradients.  Their square root
    # is therefore a gray-code signal amplitude.  Dividing by the canonical
    # uint8 quantization step gives an explicit measurement unit and remains
    # meaningful when real content fills most of the source; a global MAD
    # rank would incorrectly call such content ordinary background.
    second_direction_signal_codes = (
        np.sqrt(minimum_eigenvalue)
        / REGISTERED_UINT8_QUANTIZATION_STEP
    )
    return second_direction_signal_codes, second_fraction


def _occupied_components(
    occupied: np.ndarray,
    *,
    minimum_interior_radius_cells: int,
) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Return deterministic 2-D components with a real interior."""

    if minimum_interior_radius_cells <= 0:
        raise ValueError("content interior radius must be positive")

    labels, count = ndimage.label(
        occupied,
        structure=np.asarray(
            (
                (0, 1, 0),
                (1, 1, 1),
                (0, 1, 0),
            ),
            dtype=np.uint8,
        ),
    )
    if count == 0:
        return ()

    interior_distance = ndimage.distance_transform_edt(occupied)
    label_ids = np.arange(1, count + 1, dtype=np.int32)
    maximum_interior_distance = np.asarray(
        ndimage.maximum(
            interior_distance,
            labels=labels,
            index=label_ids,
        ),
        dtype=np.float64,
    )
    retained = {
        int(label)
        for label, distance in zip(
            label_ids,
            maximum_interior_distance,
            strict=True,
        )
        if float(distance) >= minimum_interior_radius_cells
    }
    if not retained:
        return ()

    # Visit occupied cells once.  Scanning the whole label raster separately
    # for every component made content measurement quadratic in the number of
    # small components without adding any evidence.
    grouped: dict[int, list[tuple[int, int]]] = {
        label: [] for label in retained
    }
    for row, column in np.argwhere(labels > 0):
        label = int(labels[row, column])
        component = grouped.get(label)
        if component is not None:
            component.append((int(row), int(column)))
    return tuple(tuple(grouped[label]) for label in sorted(grouped))


def observe_content_occupancy(
    gray_work: np.ndarray,
    *,
    lane_id: str,
    lane_work_box: Box,
    layout: str,
    long_step_px: int | None,
    cross_step_px: int | None,
    spec: ContentOccupancyMeasurementSpec = CONTENT_OCCUPANCY_MEASUREMENT_SPEC,
) -> ContentOccupancyObservationSet:
    """Measure candidate-independent local 2-D content occupancy.

    A lattice cell is occupied only when it contains statistically reliable
    change on both source axes.  A single long edge therefore remains neutral.
    Four-connected cells retain the real 2-D component.  Assessments consume
    exact cells rather than the report-only component bounding box.
    """

    if gray_work.ndim != 2 or not lane_work_box.valid():
        raise ValueError("content occupancy requires a valid gray lane")
    lane = gray_work[
        lane_work_box.top : lane_work_box.bottom,
        lane_work_box.left : lane_work_box.right,
    ]
    if long_step_px is None or cross_step_px is None:
        return ContentOccupancyObservationSet(
            lane_id=lane_id,
            observations=(),
            long_step_px=None,
            cross_step_px=None,
            long_sample_count=0,
            cross_sample_count=0,
            occupied_cell_count=0,
            long_support_depth_px=None,
            cross_support_depth_px=None,
        )
    if (
        long_step_px < spec.internal_subcells_per_axis
        or cross_step_px < spec.internal_subcells_per_axis
        or lane.shape[1] < spec.internal_subcells_per_axis
        or lane.shape[0] < spec.internal_subcells_per_axis
    ):
        return ContentOccupancyObservationSet(
            lane_id=lane_id,
            observations=(),
            long_step_px=long_step_px,
            cross_step_px=cross_step_px,
            long_sample_count=0,
            cross_sample_count=0,
            occupied_cell_count=0,
            long_support_depth_px=long_step_px,
            cross_support_depth_px=cross_step_px,
        )
    minimum_cell_extent_px = spec.internal_subcells_per_axis
    long_indices = _sample_indices(
        lane.shape[1],
        long_step_px,
        minimum_cell_extent_px=minimum_cell_extent_px,
    )
    cross_indices = _sample_indices(
        lane.shape[0],
        cross_step_px,
        minimum_cell_extent_px=minimum_cell_extent_px,
    )
    if min(len(cross_indices), len(long_indices)) < 2:
        return ContentOccupancyObservationSet(
            lane_id=lane_id,
            observations=(),
            long_step_px=long_step_px,
            cross_step_px=cross_step_px,
            long_sample_count=len(long_indices),
            cross_sample_count=len(cross_indices),
            occupied_cell_count=0,
            long_support_depth_px=long_step_px,
            cross_support_depth_px=cross_step_px,
        )

    # OpenCV supplies the registered low-frequency structure tensor.  Its
    # minimum eigenvalue is the second independent direction: a single line or
    # boundary has no content authority even when its first eigenvalue is
    # strong.
    second_direction_signal_codes, second_eigenvalue_fraction = (
        _two_dimensional_structure(
        lane,
        long_indices,
        cross_indices,
        spec=spec,
        )
    )
    # Content authority comes from coherent two-axis structure, not absolute
    # brightness.  Dark photographs are still photographs, while a black
    # separator remains neutral because it has no reliable structure on both
    # axes.  A tone split would silently classify all dark image detail as
    # non-content and let an otherwise invalid crop survive the negative veto.
    occupied = (
        (
            second_direction_signal_codes
            >= spec.minimum_internal_gradient_signal_codes
        )
        & (
            second_eigenvalue_fraction
            >= spec.minimum_second_eigenvalue_fraction
        )
    )

    observations: list[ContentOccupancyObservation] = []
    for component in _occupied_components(
        occupied,
        minimum_interior_radius_cells=(
            spec.minimum_component_interior_radius_cells
        ),
    ):
        source_cells = tuple(
            sorted(
                (
                    _source_box_from_work_box(
                        Box(
                            lane_work_box.left + int(long_indices[column]),
                            lane_work_box.top + int(cross_indices[row]),
                            lane_work_box.left + int(long_indices[column + 1]),
                            lane_work_box.top + int(cross_indices[row + 1]),
                        ),
                        layout,
                    )
                    for row, column in component
                ),
                key=lambda cell: (
                    cell.top,
                    cell.left,
                    cell.bottom,
                    cell.right,
                ),
            )
        )
        source_box = Box(
            min(cell.left for cell in source_cells),
            min(cell.top for cell in source_cells),
            max(cell.right for cell in source_cells),
            max(cell.bottom for cell in source_cells),
        )
        reliability = min(
            min(
                float(
                    second_direction_signal_codes[row, column]
                    / spec.minimum_internal_gradient_signal_codes
                ),
                float(
                    second_eigenvalue_fraction[row, column]
                    / spec.minimum_second_eigenvalue_fraction
                ),
            )
            for row, column in component
        )
        identity = _stable_id(
            lane_id,
            source_box,
            source_cells,
            reliability,
        )
        observations.append(
            ContentOccupancyObservation(
                observation_id=identity,
                lane_id=lane_id,
                source_box=source_box,
                source_cells=source_cells,
                reliability=reliability,
            )
        )
    return ContentOccupancyObservationSet(
        lane_id=lane_id,
        observations=tuple(observations),
        long_step_px=long_step_px,
        cross_step_px=cross_step_px,
        long_sample_count=len(long_indices),
        cross_sample_count=len(cross_indices),
        occupied_cell_count=int(np.count_nonzero(occupied)),
        # The tensor has already established true two-axis structure inside
        # each retained cell.  A physical contradiction needs one independent
        # occupied cell on each side of the boundary.  Reapplying the Scharr
        # and tensor filter radii here would count the same footprint twice.
        long_support_depth_px=long_step_px,
        cross_support_depth_px=cross_step_px,
    )
