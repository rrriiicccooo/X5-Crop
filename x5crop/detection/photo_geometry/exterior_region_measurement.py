"""Candidate-independent exterior prefixes and dense weak-signal protection.

These are registered grayscale facts, not a holder-material certificate or a
photo boundary. In particular, AVAILABLE only means that both source-side
seeds have observable departures in every longitudinal third. No constructor
in this module grants output, aperture, phase, or direction authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math

import numpy as np

from ...domain import Box
from ..robust_statistics import NORMAL_MAD_SCALE, REGISTERED_UINT8_QUANTIZATION_STEP
from .measurement_model import PhotoBoundaryMeasurementField
from .model import PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC


EXTERIOR_REGION_REVISION = "exterior-region-gray-prefix-v1"
KERNEL_RADIUS_PX = 2
KERNEL_AREA = (2*KERNEL_RADIUS_PX+1)**2
# Frozen observational hypotheses, not calibrated holder/approval thresholds.
PREFIX_ALLOWANCE_GRAY = 8.0
SEED_MAD_MULTIPLIER = 6.0
EXTERIOR_BAND_RATIO = 0.2


class ExteriorRegionAvailability(str, Enum):
    AVAILABLE = "available"
    SEED_DEPARTURE_UNOBSERVABLE = "seed_departure_unobservable"
    QUERY_UNOBSERVABLE = "query_unobservable"


@dataclass(frozen=True)
class ExteriorRegionQuery:
    lane_id: str
    layout: str
    work_box: Box
    scale_px_per_mm: float
    registration_provenance_id: str
    revision: str = EXTERIOR_REGION_REVISION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.lane_id, str) or not self.lane_id
            or not isinstance(self.registration_provenance_id, str) or not self.registration_provenance_id
            or self.revision != EXTERIOR_REGION_REVISION
            or self.layout not in {"horizontal", "vertical"}
            or not isinstance(self.work_box, Box) or not self.work_box.valid()
            or any(type(value) is not int for value in vars(self.work_box).values())
            or min(self.work_box.left, self.work_box.top) < 0
            or not math.isfinite(self.scale_px_per_mm) or self.scale_px_per_mm <= 0.
        ):
            raise ValueError("exterior region query requires registered lane geometry")

    @property
    def query_id(self) -> str:
        payload = repr((
            EXTERIOR_REGION_REVISION, self.lane_id, self.layout,
            repr(self.work_box), f"{self.scale_px_per_mm:.17g}",
            self.registration_provenance_id,
        )).encode("utf-8")
        return f"{EXTERIOR_REGION_REVISION}:{hashlib.sha256(payload).hexdigest()}"

    @property
    def depth(self) -> int:
        return int(math.ceil(EXTERIOR_BAND_RATIO * self.work_box.height))

    @property
    def window(self) -> int:
        return SPEC.local_window_px(self.scale_px_per_mm)

    @property
    def gap(self) -> int:
        return SPEC.transition_gap_px(self.scale_px_per_mm)

    @property
    def read_depth(self) -> int:
        return self.depth + self.window + self.gap

    @property
    def seed_count(self) -> int:
        return max(3, int(math.ceil(min(32., .01*self.work_box.height))) - KERNEL_RADIUS_PX)

    @property
    def persistence(self) -> int:
        return 3 * max(1, int(math.ceil(self.work_box.height / 2048)))

    @property
    def trace_count(self) -> int:
        return max(0, self.work_box.width - 2*KERNEL_RADIUS_PX)

    @property
    def coordinate_count(self) -> int:
        return max(0, self.depth - 2*KERNEL_RADIUS_PX)

    @property
    def weak_coordinate_count(self) -> int:
        return max(0, self.coordinate_count - self.window - self.gap)

    @property
    def observable(self) -> bool:
        return (
            self.trace_count >= 3
            and self.coordinate_count >= self.seed_count + self.persistence
            and self.weak_coordinate_count > 0
            and self.read_depth <= self.work_box.height
        )

    @property
    def expected_pixel_work(self) -> int:
        if not self.observable:
            return 0
        # Logical sample accesses: source read, 25-tap region averages,
        # prefix comparisons, seed statistics and the existing sharp window
        # cost. Prefix sums accelerate these accesses without erasing cost.
        averages = (self.read_depth - 4) * self.trace_count
        return 2 * (
            self.read_depth * self.work_box.width + KERNEL_AREA*averages
            + (3+2*self.persistence)*self.coordinate_count*self.trace_count
            + 2*self.seed_count*self.trace_count
            + self.weak_coordinate_count*self.trace_count*(2*self.window+2)
        )

    @property
    def temporary_buffer_bound(self) -> int:
        """Dimension-derived upper bound for live numeric buffers, replayable without pixels.

        Source-gray storage and retained scalar observations are not temporary
        measurement arrays. Each stage includes full-lane arrays still alive
        while a streaming block is processed. Exact 25-pixel sums and their
        differences fit int16; cumulative windows use int64, normalized
        values float64, coordinates int32 and masks bool.
        """
        if not self.observable:
            return 0
        rows, columns = self.read_depth-4, self.trace_count
        sums = 2*rows*columns
        # Box sum, seed statistics, colour/persistence and global departure.
        stages = [
            2*(self.read_depth+rows)*columns,
            sums+4*self.seed_count*columns+24*columns,
        ]
        width = min(columns, max(1, SPEC.maximum_streaming_block_pixels//rows))
        field = 8*self.weak_coordinate_count*width
        mask = self.weak_coordinate_count*width
        # Full sums and per-column seed/result vectors stay alive while one
        # block runs. Persistent argmax may copy another boolean field.
        retained = sums+64*columns
        stages.append(retained+11*self.coordinate_count*width+32*width)
        base = retained+4*self.weak_coordinate_count+8*width+mask
        differences = 2*(rows-1)*width
        stages.extend((
            base+3*field,
            base+2*field+mask+32*width,
            base+8*(rows+1)*width+4*field,
            base+2*differences,
            base+differences+8*rows*width+4*field,
            base+differences+2*field+mask+32*width,
            base+mask+24*width,
        ))
        return max(stages)


@dataclass(frozen=True)
class ExteriorSidePrefixes:
    maximum_side: bool
    color_prefix_px: tuple[float | None, ...]
    weak_prefix_px: tuple[float | None, ...]
    seed_minimum_gray: float
    seed_maximum_gray: float
    seed_departure_count_by_third: tuple[int, int, int]


@dataclass(frozen=True)
class ExteriorRegionWork:
    query_id: str
    registered_trace_count: int
    completed_trace_count: int
    coordinate_sample_count: int
    weak_coordinate_sample_count: int
    source_read_pixel_count: int
    pixel_query_count: int
    streaming_block_count: int
    peak_temporary_bytes: int


@dataclass(frozen=True)
class ExteriorRegionMeasurement:
    query: ExteriorRegionQuery
    availability: ExteriorRegionAvailability
    sides: tuple[ExteriorSidePrefixes, ...]
    work: ExteriorRegionWork

    def __post_init__(self) -> None:
        query, work = self.query, self.work
        if (not isinstance(query, ExteriorRegionQuery) or not isinstance(work, ExteriorRegionWork)
                or not isinstance(self.availability, ExteriorRegionAvailability)):
            raise TypeError("exterior measurement requires typed query and work")
        if (
            work.query_id != query.query_id
            or any(type(v) is not int or v < 0 for k, v in vars(work).items() if k != "query_id")
            or work.registered_trace_count != (query.trace_count if query.observable else 0)
            or work.completed_trace_count != work.registered_trace_count
            or work.coordinate_sample_count != 2*query.coordinate_count*work.registered_trace_count
            or work.weak_coordinate_sample_count != 2*query.weak_coordinate_count*work.registered_trace_count
            or work.source_read_pixel_count != (2*query.read_depth*query.work_box.width if query.observable else 0)
            or work.pixel_query_count != query.expected_pixel_work
        ):
            raise ValueError("exterior measurement lost registered coverage or work")
        if not query.observable:
            if (self.sides or self.availability != ExteriorRegionAvailability.QUERY_UNOBSERVABLE
                    or work.streaming_block_count or work.peak_temporary_bytes):
                raise ValueError("unobservable query cannot supply exterior prefixes")
            return
        if (len(self.sides) != 2 or not all(isinstance(s, ExteriorSidePrefixes) for s in self.sides)
                or tuple(s.maximum_side for s in self.sides) != (False, True)):
            raise ValueError("exterior measurement must preserve both source sides")
        block_width = max(1, SPEC.maximum_streaming_block_pixels // (query.read_depth-4))
        if (
            work.streaming_block_count != 2*math.ceil(query.trace_count/block_width)
            or work.peak_temporary_bytes != query.temporary_buffer_bound
        ):
            raise ValueError("exterior work lost its full streaming and buffer coverage")
        for side in self.sides:
            if (
                type(side.maximum_side) is not bool
                or not isinstance(side.color_prefix_px, tuple)
                or not isinstance(side.weak_prefix_px, tuple)
                or len(side.color_prefix_px) != query.trace_count
                or len(side.weak_prefix_px) != query.trace_count
                or not 0 <= side.seed_minimum_gray <= side.seed_maximum_gray <= 255
                or len(side.seed_departure_count_by_third) != 3
                or any(type(n) is not int or n < 0 for n in side.seed_departure_count_by_third)
                or sum(side.seed_departure_count_by_third) > query.trace_count
                or any(n > query.trace_count//3 + (i < query.trace_count%3)
                       for i, n in enumerate(side.seed_departure_count_by_third))
            ):
                raise ValueError("exterior prefixes lost their measured column domain")
            for values, weak in ((side.color_prefix_px, False), (side.weak_prefix_px, True)):
                minimum = KERNEL_RADIUS_PX + (query.window+query.gap-.5 if weak else query.seed_count)
                maximum = query.depth-KERNEL_RADIUS_PX-(1.5 if weak else query.persistence)
                for value in values:
                    if value is None:
                        continue
                    offset = query.work_box.bottom-1-value if side.maximum_side else value-query.work_box.top
                    if (not math.isfinite(value) or not minimum <= offset <= maximum
                            or offset % 1 != (.5 if weak else 0.)):
                        raise ValueError("exterior prefix leaves its measured native domain")
        expected = (ExteriorRegionAvailability.AVAILABLE
            if all(all(s.seed_departure_count_by_third) for s in self.sides)
            else ExteriorRegionAvailability.SEED_DEPARTURE_UNOBSERVABLE)
        if self.availability != expected:
            raise ValueError("exterior availability disagrees with observed seed departures")


def _box_sums(values: np.ndarray) -> tuple[np.ndarray, int]:
    """Exact 25-pixel integer sums avoid orientation-dependent filter roundoff."""
    height, width = values.shape
    # Registered gray is uint8: a horizontal sum is at most 1275, a full
    # kernel 6375, and either signed difference remains inside int16.
    horizontal = np.add(values[:, :width-4], values[:, 1:width-3], dtype=np.int16)
    for shift in range(2, 5):
        horizontal += values[:, shift:width-4+shift]
    sums = horizontal[:height-4].copy()
    for shift in range(1, 5):
        sums += horizontal[shift:height-4+shift]
    return sums, horizontal.nbytes + sums.nbytes


def _first_persistent(mask: np.ndarray, seed_count: int, persistence: int) -> tuple[np.ndarray, np.ndarray]:
    count = mask.shape[0]-persistence+1
    persistent = mask[:count].copy()
    for shift in range(1, persistence):
        persistent &= mask[shift:shift+count]
    persistent[:seed_count] = False
    indices = persistent.argmax(axis=0)
    # Argmax is zero both for an empty column and a first-row hit. Its
    # selected first-row value distinguishes those without a second scan.
    return indices, (indices != 0) | persistent[0]


def _mad_floor_is_proven(deviations: np.ndarray, center: np.ndarray, minimum_scale: float) -> bool:
    """Certify the original per-trace MAD floor without choosing a new scale."""
    bound = math.nextafter(minimum_scale/NORMAL_MAD_SCALE, -math.inf)
    return bool(np.all(np.isfinite(center)) and np.all(
        2*np.count_nonzero(deviations > bound, axis=1) < deviations.shape[1]))


def _weak_prefixes(sums: np.ndarray, query: ExteriorRegionQuery) -> tuple[np.ndarray, int, int]:
    window, gap = query.window, query.gap
    coordinates = np.arange(window+gap, query.coordinate_count, dtype=np.int32)
    block_width = max(1, SPEC.maximum_streaming_block_pixels // len(sums))
    result = np.full(sums.shape[1], np.nan)
    peak, blocks = 0, 0
    for begin in range(0, sums.shape[1], block_width):
        end = min(sums.shape[1], begin+block_width)
        values = sums[:,begin:end]
        # Keep exact integer sums in all cumulative windows. Every contrast
        # uses sum units, including the 25-code minimum noise scale, so the
        # registered dimensionless z predicate remains unchanged.
        base = sums.nbytes + coordinates.nbytes + result.nbytes
        def credible(field, threshold, *, certify_floor=False):
            nonlocal peak
            # Partition one trace's complete coordinate domain contiguously.
            # Only scratch storage changes; each original column keeps its
            # own median/MAD and the returned mask keeps source coordinates.
            scratch = field.T.copy()
            center = np.median(scratch, axis=1, overwrite_input=True)
            np.subtract(field.T, center[:, None], out=scratch)
            np.abs(scratch, out=scratch)
            minimum_scale = KERNEL_AREA*REGISTERED_UINT8_QUANTIZATION_STEP
            # A strict majority below this outward-safe bound proves that
            # the original MAD scale is clamped to its existing floor.
            # Gradient's comparison and reduction use two weak-domain scans.
            # The removed weak-mask and two persistent availability scans
            # cover those within the original coordinate/trace work budget.
            if certify_floor and _mad_floor_is_proven(scratch, center, minimum_scale):
                scale = np.full_like(center, minimum_scale)
            else:
                mad = np.median(scratch, axis=1, overwrite_input=True)
                scale = np.maximum(minimum_scale, NORMAL_MAD_SCALE*mad)
            np.subtract(field.T, center[:, None], out=scratch)
            scratch /= scale[:, None]
            mask = (scratch >= threshold).T
            peak = max(peak, base + field.nbytes + scratch.nbytes + mask.nbytes
                       + 4*center.nbytes)
            return mask
        def contrast(data):
            nonlocal peak
            prefix = np.empty((len(data)+1, data.shape[1]), dtype=np.int64)
            prefix[0] = 0
            np.cumsum(data, axis=0, out=prefix[1:])
            left = prefix[coordinates-gap]-prefix[coordinates-gap-window]
            right = prefix[coordinates+gap+window]-prefix[coordinates+gap]
            peak = max(peak, base + prefix.nbytes + left.nbytes + right.nbytes
                       + 2*left.nbytes)
            left -= right
            result = left.astype(np.float64, order="F")
            result /= window
            np.abs(result, out=result)
            return result
        gradient = np.abs(values[coordinates+gap-1]-values[coordinates-gap]).astype(np.float64, order="F")
        peak = max(peak, base + 3*gradient.nbytes)
        mask = credible(gradient, SPEC.gradient_z_minimum, certify_floor=True)
        del gradient
        base += mask.nbytes
        mask |= credible(contrast(values), SPEC.tone_or_texture_z_minimum)
        differences = np.abs(np.diff(values, axis=0))
        peak = max(peak, base + 2*differences.nbytes)
        # Difference storage remains live during its contrast and MAD work.
        previous_peak = peak
        peak = 0
        mask |= credible(contrast(differences), SPEC.tone_or_texture_z_minimum)
        peak = max(previous_peak, peak + differences.nbytes)
        del differences
        indices = mask.argmax(axis=0)
        available = (indices != 0) | mask[0]
        stopped = coordinates[indices].astype(float)
        stopped += KERNEL_RADIUS_PX
        stopped -= .5
        peak = max(peak, base + indices.nbytes + 2*available.nbytes + stopped.nbytes + 4*(end-begin))
        stopped[~available] = np.nan
        result[begin:end] = stopped
        blocks += 1
        del mask, available, stopped, indices
    return result, peak, blocks


def _side_prefixes(
    sums: np.ndarray,
    query: ExteriorRegionQuery,
) -> tuple[np.ndarray, np.ndarray, float, float, tuple[int, ...], int, int]:
    """Use the complete seed domain, then consume each column block once."""
    seed_values = sums[:query.seed_count]
    seed = np.median(seed_values, axis=0)
    noise = NORMAL_MAD_SCALE*np.median(np.abs(seed_values-seed), axis=0)
    peak = sums.nbytes + 2*seed_values.nbytes + 3*seed.nbytes
    minimum, maximum = float(seed_values.min()), float(seed_values.max())
    threshold = np.maximum(KERNEL_AREA*PREFIX_ALLOWANCE_GRAY, SEED_MAD_MULTIPLIER*noise)
    allowance = np.maximum(KERNEL_AREA*REGISTERED_UINT8_QUANTIZATION_STEP, SEED_MAD_MULTIPLIER*noise)
    color = np.empty(sums.shape[1], dtype=np.float64)
    weak = np.empty_like(color)
    departures = np.empty(sums.shape[1], dtype=bool)
    retained = sum(array.nbytes for array in (sums, seed, noise, threshold, allowance, color, weak, departures))
    block_width = max(1, SPEC.maximum_streaming_block_pixels // len(sums))
    blocks = 0
    for begin in range(0, sums.shape[1], block_width):
        end = min(sums.shape[1], begin+block_width)
        values = sums[:, begin:end]
        band = values[:query.coordinate_count]
        differences = band-seed[begin:end]
        np.abs(differences, out=differences)
        mask = differences > threshold[begin:end]
        indices, available = _first_persistent(mask, query.seed_count, query.persistence)
        peak = max(peak, retained + differences.nbytes + 3*mask.nbytes + 32*(end-begin))
        color[begin:end] = np.where(available, indices + KERNEL_RADIUS_PX, np.nan)
        del differences, mask, indices, available
        global_mask = ((band < minimum-allowance[begin:end]) |
                       (band > maximum+allowance[begin:end]))
        global_indices, global_available = _first_persistent(global_mask, query.seed_count, query.persistence)
        departures[begin:end] = global_available
        peak = max(peak, retained + 4*global_mask.nbytes + 32*(end-begin))
        del global_mask, global_indices, global_available
        weak_values, weak_peak, weak_blocks = _weak_prefixes(values, query)
        weak[begin:end] = weak_values
        peak = max(peak, weak_peak + retained-values.nbytes)
        blocks += weak_blocks
        del weak_values
    counts = tuple(int(np.count_nonzero(part)) for part in np.array_split(departures, 3))
    return color, weak, minimum, maximum, counts, peak, blocks


def measure_exterior_region(field: PhotoBoundaryMeasurementField, query: ExteriorRegionQuery) -> ExteriorRegionMeasurement:
    if field.layout != query.layout:
        raise ValueError("exterior region query layout differs from its field")
    gray = field.source_gray if field.layout == "horizontal" else field.source_gray.T
    box = query.work_box
    if box.bottom > gray.shape[0] or box.right > gray.shape[1]:
        raise ValueError("exterior region query leaves the registered source")
    if not query.observable:
        return ExteriorRegionMeasurement(query, ExteriorRegionAvailability.QUERY_UNOBSERVABLE, (),
            ExteriorRegionWork(query.query_id,0,0,0,0,0,0,0,0))
    lane = gray[box.top:box.bottom, box.left:box.right]
    sides, peak, blocks = [], 0, 0
    for maximum_side in (False, True):
        source = lane[::-1] if maximum_side else lane
        sums, mean_peak = _box_sums(source[:query.read_depth])
        peak = max(peak, mean_peak)
        color, weak, minimum, maximum, counts, side_peak, side_blocks = _side_prefixes(sums, query)
        peak = max(peak, side_peak)
        blocks += side_blocks
        del sums
        if maximum_side:
            color = box.bottom-1-color
            weak = box.bottom-1-weak
        else:
            color += box.top
            weak += box.top
        as_tuple = lambda values: tuple(None if np.isnan(v) else float(v) for v in values)
        sides.append(ExteriorSidePrefixes(maximum_side, as_tuple(color), as_tuple(weak),
                                         minimum/KERNEL_AREA, maximum/KERNEL_AREA, counts))
        del color, weak
    availability = (ExteriorRegionAvailability.AVAILABLE
        if all(all(s.seed_departure_count_by_third) for s in sides)
        else ExteriorRegionAvailability.SEED_DEPARTURE_UNOBSERVABLE)
    count = query.trace_count
    if peak > query.temporary_buffer_bound:
        raise ValueError("exterior numeric buffers exceeded the registered dimension bound")
    return ExteriorRegionMeasurement(query, availability, tuple(sides), ExteriorRegionWork(
        query.query_id, count, count, 2*query.coordinate_count*count,
        2*query.weak_coordinate_count*count, 2*query.read_depth*box.width,
        query.expected_pixel_work, blocks, query.temporary_buffer_bound,
    ))
