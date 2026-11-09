"""Bounded gray-pixel bridge measurements; no identity or role authority.

Every corridor keeps the registered normalization domain.  Dense rows are
measured once per identical axis/domain/scale, then sliced with the existing
owner before peak extraction.  These records are signal facts, not a claim
that two peaks belong to one physical edge.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from hashlib import sha256
import math
import struct

import numpy as np

from ...domain import FiniteInterval, WorkspaceExtent
from .measurement_model import PhotoBoundaryMeasurementField
from .model import BoundaryAxis, PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from .registered_measurement import _slice_trace_measurement
from .registered_transition_measurement import (
    TraceMeasurement, TraceRowsMeasurement, measure_trace_rows, measured_transition_peaks, transition_peak_support,
)
from .transition_peak_source import TransitionPeakTraceSource


_PEAK_RECORD = struct.Struct("<q6db7x")
_PEAK_HEX_SIZE = 2 * _PEAK_RECORD.size
_LOCALIZATION_WIDTH = struct.Struct('<d')


def _integer(value, name, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _finite(value, name, *, minimum=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")


def _merge_intervals(intervals):
    merged = []
    for start, stop in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(stop, merged[-1][1]))
        else:
            merged.append((start, stop))
    return tuple(merged)


@dataclass(frozen=True, slots=True)
class NativeTraceBridgePlan:
    source_id: str
    source_extent: WorkspaceExtent
    boundary_axis: BoundaryAxis
    original_query_id: str
    baseline_query_id: str
    normalization_interval_px: FiniteInterval
    coordinate_interval_px: FiniteInterval
    trace_intervals_px: tuple[tuple[int, int], ...]
    coordinate_scale_px_per_mm: float
    original_trace_coordinates_px: tuple[int, ...]
    split_gradient_reversals: bool = True
    record_peaks: bool = True
    retain_responses: bool = False

    def __post_init__(self):
        for name in ("source_id", "original_query_id", "baseline_query_id"):
            if type(getattr(self, name)) is not str or not getattr(self, name):
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.source_extent, WorkspaceExtent) or any(
            type(value) is not int for value in (self.source_extent.width, self.source_extent.height)
        ):
            raise ValueError("bridge source extent must have integer dimensions")
        if not isinstance(self.boundary_axis, BoundaryAxis):
            raise ValueError("bridge boundary axis must be typed")
        if type(self.split_gradient_reversals) is not bool:
            raise ValueError("bridge peak selector must retain its original split rule")
        if type(self.record_peaks) is not bool:
            raise ValueError("bridge measurement must declare its complete peak stage")
        if type(self.retain_responses) is not bool or self.retain_responses and self.record_peaks:
            raise ValueError('response retention belongs only to the complete signal stage')
        _finite(self.coordinate_scale_px_per_mm, "coordinate scale", minimum=0.0)
        if self.coordinate_scale_px_per_mm <= 0:
            raise ValueError("coordinate scale must be positive")
        object.__setattr__(self, "coordinate_scale_px_per_mm", float(self.coordinate_scale_px_per_mm))
        length, trace_length = _axis_lengths(self.source_extent, self.boundary_axis)
        for interval in (self.normalization_interval_px, self.coordinate_interval_px):
            if not isinstance(interval, FiniteInterval):
                raise ValueError("bridge coordinate domains must be FiniteInterval")
            for value in (interval.minimum, interval.maximum):
                _finite(value, "coordinate endpoint")
            if interval.minimum < 0 or interval.maximum > length - 1:
                raise ValueError("bridge coordinate domain leaves the source")
        start, stop = _normalization_domain(self)
        low, high = _corridor_domain(self)
        if stop <= start or low < start or high > stop or high <= low:
            raise ValueError("bridge corridor must be completely kernel-observable in its baseline")
        if type(self.trace_intervals_px) is not tuple or not self.trace_intervals_px:
            raise ValueError("bridge requires frozen non-empty trace intervals")
        previous = -1
        for interval in self.trace_intervals_px:
            if type(interval) is not tuple or len(interval) != 2:
                raise ValueError("trace interval must be a frozen half-open pair")
            first, last = interval
            _integer(first, "trace start")
            _integer(last, "trace stop")
            if first < previous or last <= first or last > trace_length:
                raise ValueError("trace intervals must be ordered, disjoint and source-contained")
            previous = last
        traces = self.original_trace_coordinates_px
        if type(traces) is not tuple:
            raise ValueError("original trace coordinates must be frozen")
        previous = -1
        for trace in traces:
            _integer(trace, "original trace")
            if trace <= previous or trace >= trace_length:
                raise ValueError("original trace coordinates must be ordered, unique and source-contained")
            previous = trace


def _axis_lengths(extent, axis):
    return ((extent.width, extent.height) if axis == BoundaryAxis.X
            else (extent.height, extent.width))


def _normalization_domain(plan):
    return native_trace_bridge_normalization_domain(plan.source_extent, plan.boundary_axis,
        plan.normalization_interval_px, plan.coordinate_scale_px_per_mm)


def native_trace_bridge_normalization_domain(extent, axis, interval, scale):
    """The original scalar owner's kernel-observable half-open baseline."""
    length, _ = _axis_lengths(extent, axis)
    halo = SPEC.measurement_halo_px(scale)
    return max(halo, math.ceil(interval.minimum)), min(length-halo, math.floor(interval.maximum)+1)


def _corridor_domain(plan):
    return math.ceil(plan.coordinate_interval_px.minimum), math.floor(plan.coordinate_interval_px.maximum) + 1


def _included_original_traces(plan):
    """Intersect the two ordered domains with one monotone scan."""
    intervals = iter(plan.trace_intervals_px)
    start, stop = next(intervals)
    for trace in plan.original_trace_coordinates_px:
        while trace >= stop:
            interval = next(intervals, None)
            if interval is None:
                return
            start, stop = interval
        if trace >= start:
            yield trace


def _original_in_strip(plan, start, stop):
    traces = plan.original_trace_coordinates_px
    return traces[bisect_left(traces, start):bisect_left(traces, stop)]


@dataclass(frozen=True, slots=True)
class NativeTraceBridgePeak:
    source_coordinate_px: int
    canonical_coordinate_px: float
    physical_position_interval_px: FiniteInterval
    polarity: int
    gradient_z: float
    tone_z: float
    texture_z: float
    localization_width_px: float | None = None

    def __post_init__(self):
        _integer(self.source_coordinate_px, "source peak coordinate")
        _finite(self.canonical_coordinate_px, "canonical peak coordinate")
        if (not isinstance(self.physical_position_interval_px, FiniteInterval)
                or not self.physical_position_interval_px.contains(self.canonical_coordinate_px)
                or type(self.polarity) is not int or self.polarity not in (-1, 0, 1)):
            raise ValueError("bridge peak lost its original physical interval or polarity")
        for name in ("gradient_z", "tone_z", "texture_z"):
            _finite(getattr(self, name), name, minimum=0.0)
        if self.localization_width_px is not None:
            _finite(self.localization_width_px,'localization width',minimum=0.)
            half = self.localization_width_px/2
            if (self.canonical_coordinate_px-half < self.physical_position_interval_px.minimum
                    or self.canonical_coordinate_px+half > self.physical_position_interval_px.maximum):
                raise ValueError('bridge localization left its complete physical group')


def _validate_mask_hex(encoded, site_count):
    byte_count = (site_count + 7) // 8
    if (type(encoded) is not str or len(encoded) != 2 * byte_count
            or encoded.strip("0123456789abcdef")):
        raise ValueError("bridge mask must have the exact lowercase hexadecimal length")
    if site_count % 8 and int(encoded[-2:], 16) >> (site_count % 8):
        raise ValueError("bridge mask has nonzero little-endian padding bits")


@dataclass(frozen=True, slots=True)
class NativeTraceBridgeStrip:
    plan_index: int
    trace_start_px: int
    trace_stop_px: int
    coordinate_start_px: int
    coordinate_stop_px: int
    positive_mask_hex: str
    negative_mask_hex: str
    credible_mask_hex: str
    peak_records_hex: str
    peak_row_offsets: tuple[int, ...]
    original_trace_sources: tuple[TransitionPeakTraceSource, ...]
    localization_widths_hex: str = ''

    def __post_init__(self):
        for name in ("plan_index", "trace_start_px", "trace_stop_px", "coordinate_start_px", "coordinate_stop_px"):
            _integer(getattr(self, name), name)
        rows = self.trace_stop_px - self.trace_start_px
        columns = self.coordinate_stop_px - self.coordinate_start_px
        if rows <= 0 or columns <= 0:
            raise ValueError("bridge strip must have positive shape")
        for encoded in (self.positive_mask_hex, self.negative_mask_hex, self.credible_mask_hex):
            _validate_mask_hex(encoded, rows * columns)
        positive,negative,credible = (np.frombuffer(bytes.fromhex(encoded),dtype=np.uint8) for encoded in
            (self.positive_mask_hex,self.negative_mask_hex,self.credible_mask_hex))
        if np.any(positive & negative):
            raise ValueError("bridge positive and negative masks overlap")
        if np.any((positive | negative) & ~credible):
            raise ValueError("bridge connected signal leaves its original OR grouping support")
        del positive,negative,credible
        if (type(self.peak_records_hex) is not str
                or self.peak_records_hex.strip("0123456789abcdef")
                or type(self.peak_row_offsets) is not tuple or len(self.peak_row_offsets) != rows + 1
                or any(type(i) is not int or i < 0 for i in self.peak_row_offsets)
                or self.peak_row_offsets[0] != 0
                or any(a > b for a, b in zip(self.peak_row_offsets, self.peak_row_offsets[1:]))
                or len(self.peak_records_hex) != _PEAK_HEX_SIZE * self.peak_row_offsets[-1]):
            raise ValueError("bridge strip must retain the complete packed peak table and every row offset")
        if (type(self.localization_widths_hex) is not str
                or self.localization_widths_hex.strip('0123456789abcdef')
                or self.localization_widths_hex and len(self.localization_widths_hex) != 16*self.peak_row_offsets[-1]):
            raise ValueError('bridge localization widths changed their complete peak table')
        for first, last in zip(self.peak_row_offsets, self.peak_row_offsets[1:]):
            if last - first > columns:
                raise ValueError("bridge row has more candidates than source coordinates")
            previous = self.coordinate_start_px - 1
            for ordinal in range(first, last):
                peak = _unpack_peak(self.peak_records_hex, ordinal,self.localization_widths_hex)
                if not previous < peak.source_coordinate_px < self.coordinate_stop_px:
                    raise ValueError("bridge peak rows changed their source order or corridor")
                previous = peak.source_coordinate_px
        if type(self.original_trace_sources) is not tuple:
            raise ValueError("bridge trace sources must be frozen")
        previous = self.trace_start_px - 1
        for source in self.original_trace_sources:
            if (not isinstance(source, TransitionPeakTraceSource)
                    or not previous < source.trace_coordinate_px < self.trace_stop_px):
                raise ValueError("bridge sources changed their original trace order")
            previous = source.trace_coordinate_px


def _unpack_peak(encoded, ordinal, localization_widths_hex=''):
    start = ordinal * _PEAK_HEX_SIZE
    record = encoded[start:start + _PEAK_HEX_SIZE]
    if record[114:] != "0" * 14:
        raise ValueError("packed bridge peak has nonzero reserved bytes")
    source, canonical, low, high, gradient, tone, texture, polarity = _PEAK_RECORD.unpack(bytes.fromhex(record))
    width = (None if not localization_widths_hex else
             _LOCALIZATION_WIDTH.unpack(bytes.fromhex(localization_widths_hex[16*ordinal:16*(ordinal+1)]))[0])
    return NativeTraceBridgePeak(source, canonical, FiniteInterval(low, high), polarity, gradient, tone, texture,width)


def peaks_at_row(strip: NativeTraceBridgeStrip, row: int) -> tuple[NativeTraceBridgePeak, ...]:
    """Decode one relative row only; the caller owns its <=768B/peak DTOs."""
    if not isinstance(strip, NativeTraceBridgeStrip) or type(row) is not int or not 0 <= row < strip.trace_stop_px-strip.trace_start_px:
        raise ValueError("peak decoding requires a typed strip and a valid relative row")
    return tuple(_unpack_peak(strip.peak_records_hex, i,strip.localization_widths_hex)
                 for i in range(strip.peak_row_offsets[row], strip.peak_row_offsets[row + 1]))


def decode_mask(strip: NativeTraceBridgeStrip, polarity: int, *, trace_interval_px=None) -> np.ndarray:
    """Decode one checked row-major mask (one byte/site plus packed input).

    This helper allocates the returned uint8 array; its caller owns that
    replay allocation. It does not read source pixels or change the strip.
    """
    if not isinstance(strip, NativeTraceBridgeStrip) or type(polarity) is not int or polarity not in (-1, 1):
        raise ValueError("mask decoding requires a typed strip and polarity +/-1")
    encoded = strip.positive_mask_hex if polarity > 0 else strip.negative_mask_hex
    return _decode_checked_mask(strip, encoded, trace_interval_px)


def decode_credible_mask(strip: NativeTraceBridgeStrip, *, trace_interval_px=None) -> np.ndarray:
    """Decode original OR support; an AND component cannot substitute for it."""
    if not isinstance(strip, NativeTraceBridgeStrip):
        raise ValueError("group support decoding requires a typed strip")
    return _decode_checked_mask(strip, strip.credible_mask_hex, trace_interval_px)


def _decode_checked_mask(strip, encoded, trace_interval_px=None):
    rows = strip.trace_stop_px - strip.trace_start_px
    columns = strip.coordinate_stop_px - strip.coordinate_start_px
    _validate_mask_hex(encoded, rows * columns)
    low,high = ((strip.trace_start_px,strip.trace_stop_px) if trace_interval_px is None else trace_interval_px)
    if (type(low) is not int or type(high) is not int
            or not strip.trace_start_px <= low < high <= strip.trace_stop_px):
        raise ValueError('mask decoding requires a source-contained nonempty row range')
    start = (low-strip.trace_start_px)*columns
    count = (high-low)*columns
    first,last = start//8,(start+count+7)//8
    packed = np.frombuffer(bytes.fromhex(encoded[2*first:2*last]),dtype=np.uint8)
    return np.unpackbits(packed,bitorder='little',count=start%8+count)[start%8:].reshape(high-low,columns)


@dataclass(frozen=True, slots=True)
class NativeTraceBridgeBatch:
    plans: tuple[NativeTraceBridgePlan, ...]
    strips: tuple[NativeTraceBridgeStrip, ...]
    pixel_query_count: int
    value_visit_bound: int
    mask_site_work_bound: int
    retained_bytes: int
    peak_temporary_bytes: int
    bound_exceeded: bool
    required_pixel_query_count: int = 0
    required_value_visit_bound: int = 0
    required_peak_temporary_bytes: int = 0
    preflight_value_visit_bound: int = 0
    response_cache_bytes: int = 0
    response_source_plans: tuple[NativeTraceBridgePlan,...] | None = None

    def __post_init__(self):
        if type(self.plans) is not tuple or any(not isinstance(p, NativeTraceBridgePlan) for p in self.plans):
            raise ValueError("bridge batch plans must be frozen")
        if type(self.strips) is not tuple or any(not isinstance(s, NativeTraceBridgeStrip) for s in self.strips):
            raise ValueError("bridge batch strips must be frozen")
        for name in ("pixel_query_count", "value_visit_bound", "mask_site_work_bound", "retained_bytes",
                     "peak_temporary_bytes", "required_pixel_query_count", "required_value_visit_bound",
                     "required_peak_temporary_bytes", "preflight_value_visit_bound", "response_cache_bytes"):
            _integer(getattr(self, name), name)
        if type(self.bound_exceeded) is not bool:
            raise ValueError("bridge completion state must be a boolean")
        if self.bound_exceeded:
            if self.strips or any((self.pixel_query_count, self.value_visit_bound, self.mask_site_work_bound,
                                   self.retained_bytes, self.peak_temporary_bytes,self.response_cache_bytes)):
                raise ValueError("failed bridge batch cannot expose a measured prefix")
            return
        expected_cache = native_trace_response_cache_byte_bound(self.plans) if any(p.retain_responses for p in self.plans) else 0
        if self.response_cache_bytes != expected_cache:
            raise ValueError('bridge response cache changed its complete reservation')
        if self.response_source_plans is not None:
            _reuse_plan_indices(self.plans,self.response_source_plans)
        if (self.pixel_query_count != self.required_pixel_query_count
                or self.value_visit_bound != self.required_value_visit_bound
                or self.peak_temporary_bytes != self.required_peak_temporary_bytes
                or self.mask_site_work_bound > self.value_visit_bound
                or self.retained_bytes > self.peak_temporary_bytes):
            raise ValueError("bridge batch work does not match its complete reservation")
        coverage = [[] for _ in self.plans]
        for strip in self.strips:
            if strip.plan_index >= len(self.plans):
                raise ValueError("bridge strip references an unknown plan")
            plan = self.plans[strip.plan_index]
            if not plan.record_peaks and (strip.peak_records_hex or strip.localization_widths_hex
                                         or any(strip.peak_row_offsets)):
                raise ValueError('signal-only bridge cannot claim measured peak records')
            if len(strip.localization_widths_hex) != (0 if plan.split_gradient_reversals or not plan.record_peaks
                                                     else 16*strip.peak_row_offsets[-1]):
                raise ValueError('bridge peak selector lost its registered localization-width payload')
            if (strip.coordinate_start_px, strip.coordinate_stop_px) != _corridor_domain(plan):
                raise ValueError("bridge strip changed its original query corridor")
            coverage[strip.plan_index].append((strip.trace_start_px, strip.trace_stop_px))
            expected = _original_in_strip(plan, strip.trace_start_px, strip.trace_stop_px)
            if tuple(s.trace_coordinate_px for s in strip.original_trace_sources) != expected:
                raise ValueError("bridge strip omitted an original sampled trace source")
            low, high = _normalization_domain(plan)
            for source in strip.original_trace_sources:
                if (source.source_id != plan.source_id or source.source_extent != plan.source_extent
                        or source.boundary_axis != plan.boundary_axis
                        or source.normalization_domain_px != (low, high - 1)
                        or source.window_px != SPEC.local_window_px(plan.coordinate_scale_px_per_mm)
                        or source.gap_px != SPEC.transition_gap_px(plan.coordinate_scale_px_per_mm)
                        or source.gradient_z_minimum != SPEC.gradient_z_minimum
                        or source.tone_or_texture_z_minimum != SPEC.tone_or_texture_z_minimum):
                    raise ValueError("bridge source changed its registered normalization context")
        for plan, intervals in zip(self.plans, coverage, strict=True):
            if (sum(b-a for a, b in intervals) != sum(b-a for a, b in plan.trace_intervals_px)
                    or _merge_intervals(intervals) != _merge_intervals(plan.trace_intervals_px)):
                raise ValueError("bridge batch omitted or duplicated a dense trace interval")


def native_trace_bridge_preflight_value_visit_bound(plans, response_source_plans=None) -> int:
    """Structural work, included once in the batch's combined allowance."""
    if type(plans) is not tuple or any(not isinstance(plan, NativeTraceBridgePlan) for plan in plans):
        raise ValueError("bridge plans must be a frozen tuple of typed plans")
    return (512 + 128 * len(plans) + 128 * sum(len(p.trace_intervals_px) for p in plans)
            + 64 * sum(len(p.original_trace_coordinates_px) for p in plans)
            +(0 if response_source_plans is None else native_trace_response_consumption_work(response_source_plans)))


def native_trace_response_consumption_work(plans):
    return (4096+512*sum(b-a for p in plans for a,b in p.trace_intervals_px)+128*len(plans)) if plans else 0


def native_trace_response_cache_byte_bound(plans):
    if not plans:
        return 0
    return 8192+4096*len(plans)+sum(1024*(b-a)+64*(b-a)*(_corridor_domain(p)[1]-_corridor_domain(p)[0])
        for p in plans for a,b in p.trace_intervals_px)+4*sum(_corridor_domain(p)[1]-_corridor_domain(p)[0] for p in plans)


def _reuse_plan_indices(plans,sources):
    if type(sources) is not tuple or any(not isinstance(p,NativeTraceBridgePlan) or p.record_peaks
                                       or not p.retain_responses for p in sources):
        raise ValueError('response reuse requires complete retained signal plans')
    indices = []
    for p in plans:
        matches = [i for i,s in enumerate(sources) if replace(p,record_peaks=False,retain_responses=True,
                    trace_intervals_px=s.trace_intervals_px) == s]
        if (not p.record_peaks or p.retain_responses or len(matches)!=1
                or any(not any(a<=low and high<=b for a,b in sources[matches[0]].trace_intervals_px)
                       for low,high in p.trace_intervals_px)):
            raise ValueError('refinement changed its original retained response context or coverage')
        indices.append(matches[0])
    if len(set(indices)) != len(indices):
        raise ValueError('refinement duplicated a retained query context')
    return tuple(indices)


_RESPONSE_FIELDS = ('gradient_z','tone_z','texture_z','signed_gradient','left_tone','right_tone','left_texture','right_texture')


class NativeTraceResponseCache:
    """Call-local compact float64 rows; never serialized or shared across sources."""
    def __init__(self,plans):
        self.plans,self.rows,self.coordinates,self.signal_batch = plans,{}, {},None
        self.closed = False

    def capture(self,index,trace,view,source):
        key = (index,trace)
        if self.closed or self.signal_batch is not None or key in self.rows:
            raise ValueError('response cache is sealed or has duplicate traces')
        coordinates = self.coordinates.get(index)
        if coordinates is None:
            coordinates = view.coordinates.copy()
            coordinates.flags.writeable = False
            self.coordinates[index] = coordinates
        elif not np.array_equal(coordinates,view.coordinates):
            raise ValueError('response cache changed its complete query corridor')
        # Copy only the corridor, never a view retaining a full baseline block.
        matrix = np.stack(tuple(getattr(view,name) for name in _RESPONSE_FIELDS))
        matrix.flags.writeable = False
        self.rows[key] = (matrix,source)

    def seal(self,batch):
        expected = {(i,t) for i,p in enumerate(self.plans) for a,b in p.trace_intervals_px for t in range(a,b)}
        if self.closed or batch.bound_exceeded or batch.plans != self.plans or set(self.rows)!=expected:
            raise ValueError('response cache omitted its complete measured inventory')
        self.signal_batch = batch

    def release(self):
        self.rows.clear()
        self.coordinates.clear()
        self.closed = True


@dataclass(frozen=True, slots=True)
class _Group:
    plan_indices: tuple[int, ...]
    trace_intervals: tuple[tuple[int, int], ...]
    source_length: int
    normalization_start: int
    normalization_stop: int
    maximum_corridor_width: int
    batch_rows: int = 1


def _storage_reservation(plans):
    rows = sum(b-a for p in plans for a,b in p.trace_intervals_px)
    sites = sum(sum(b-a for a,b in p.trace_intervals_px)*(_corridor_domain(p)[1]-_corridor_domain(p)[0])
                for p in plans if p.record_peaks)
    localization_sites = sum(sum(b-a for a,b in p.trace_intervals_px)*(_corridor_domain(p)[1]-_corridor_domain(p)[0])
                             for p in plans if p.record_peaks and not p.split_gradient_reversals)
    original_count = sum(sum(1 for _ in _included_original_traces(p)) for p in plans)
    metadata = (8192 + 4096*len(plans)+256*sum(len(p.trace_intervals_px) for p in plans)
                +128*sum(len(p.original_trace_coordinates_px) for p in plans)
                +4*sum(len(p.source_id)+len(p.original_query_id)+len(p.baseline_query_id) for p in plans))
    mask_hex = 6*sum(sum(b-a for a,b in p.trace_intervals_px)
                    *((_corridor_domain(p)[1]-_corridor_domain(p)[0]+7)//8) for p in plans)
    return metadata,metadata+1120*rows+128*sites+16*localization_sites+mask_hex+1024*original_count


def native_trace_bridge_retained_byte_bound(plans):
    return 0 if not plans else _storage_reservation(plans)[1]


def _value_reservation(plans,hash_work=0,*,reuse_masks=False):
    rows = sum(b-a for p in plans for a,b in p.trace_intervals_px)
    sites = lambda predicate: sum(sum(b-a for a,b in p.trace_intervals_px)
        *(_corridor_domain(p)[1]-_corridor_domain(p)[0]) for p in plans if predicate(p))
    # Reuse copies the three original packed rows, including unaligned bit
    # boundaries, then validates the same payload. It does not rebuild support
    # from responses. 16 visits/site covers unpack/repack and packed validation;
    # the original response comparisons and mask construction require 32.
    mask_work = (16 if reuse_masks else 32)*sites(lambda p:True)+96*rows
    visits = (hash_work+704*sites(lambda p:p.record_peaks)
        +64*sites(lambda p:p.record_peaks and not p.split_gradient_reversals)+160*rows+mask_work
        +128*(len(plans)+sum(len(p.trace_intervals_px) for p in plans)
              +sum(len(p.original_trace_coordinates_px) for p in plans))
        # Eight float64 fields are read and copied (16 visits/site), and the
        # shared coordinates are compared (2). The 24-site bound includes
        # stacking/ownership overhead; row metadata is charged separately.
        +24*sites(lambda p:p.retain_responses)
        +512*sum(b-a for p in plans if p.retain_responses for a,b in p.trace_intervals_px))
    return visits,mask_work


def _prepare_refinement(plans,sources,maximum_temporary_bytes):
    _reuse_plan_indices(plans,sources)
    metadata,retained = _storage_reservation(plans)
    context_bytes = 4096+4096*len(sources)+128*sum(len(p.original_trace_coordinates_px) for p in sources)
    metadata += context_bytes
    # Unrequested rows are discarded before encoding. Each requested row is
    # popped before its encoded replacement is appended; one-row overlap is
    # covered by the same fixed peak-selection scratch owner.
    mixed = metadata+8192+4096*len(plans)
    groups = []
    for i,p in enumerate(plans):
        width = _corridor_domain(p)[1]-_corridor_domain(p)[0]
        rows = sum(b-a for a,b in p.trace_intervals_px)
        # The requested-only dictionary's capacity survives pop(), so its row
        # metadata stays live beside every encoded replacement.
        mixed += 1024*rows
        cached = 64*width
        encoded = 1120+128*width+(0 if p.split_gradient_reversals else 16*width)+6*((width+7)//8)+1024
        mixed += rows*max(cached,encoded)+4*width
        low,high = _normalization_domain(p)
        groups.append(_Group((i,),p.trace_intervals_px,_axis_lengths(p.source_extent,p.boundary_axis)[0],
                             low,high,width,1))
    peak = max(native_trace_response_cache_byte_bound(sources),
        mixed+4096+2048*max((_corridor_domain(p)[1]-_corridor_domain(p)[0] for p in plans),default=0))
    visits,mask_work = _value_reservation(plans,reuse_masks=True)
    return tuple(groups),0,visits,mask_work,peak,metadata,peak<=maximum_temporary_bytes


def _prepare(plans, maximum_temporary_bytes, response_source_plans=None):
    if response_source_plans is not None:
        return _prepare_refinement(plans,response_source_plans,maximum_temporary_bytes)
    indices = {}
    for index, plan in enumerate(plans):
        key = (plan.boundary_axis, plan.normalization_interval_px, plan.coordinate_scale_px_per_mm)
        indices.setdefault(key, []).append(index)
    groups = []
    pixel_work = hash_work = 0
    for members in indices.values():
        plan = plans[members[0]]
        intervals = _merge_intervals(i for index in members for i in plans[index].trace_intervals_px)
        start, stop = _normalization_domain(plan)
        rows = sum(b-a for a, b in intervals)
        radius = SPEC.local_measurement_work_radius_px(plan.coordinate_scale_px_per_mm)
        length, _ = _axis_lengths(plan.source_extent, plan.boundary_axis)
        # The row owner casts/differences the full source row and builds its
        # prefix arrays even when the registered normalization domain is tiny.
        # Charge that source read in addition to the original kernel work.
        pixel_work += rows * (length + (stop-start) * (2 * radius + 2))
        original = set(t for index in members for t in _included_original_traces(plans[index]))
        # A vectorized response row need not be C-contiguous. Copying its
        # logical bytes before hashing adds at most another five value visits.
        hash_work += len(original) * (10 * (stop-start) + 32 + 256)
        groups.append(_Group(tuple(members), intervals, length,
                             start, stop, max(_corridor_domain(plans[i])[1] - _corridor_domain(plans[i])[0]
                                              for i in members)))
    # One strip per row is a conservative reservation for every possible block
    # partition. Each view coordinate can create at most one retained peak.
    metadata,retained_bound = _storage_reservation(plans)
    # Keep the existing 256Q+32 peak scan reservation, and separately cover
    # fixed-record packing, hexadecimal validation and one-record decoding.
    # The extra group-support mask, its subset checks and row metadata are
    # included before pixel access; the proof's flank scan is charged later.
    value_work,mask_work = _value_reservation(plans,hash_work)
    cache_bound = native_trace_response_cache_byte_bound(plans) if any(p.retain_responses for p in plans) else 0
    required_peak = retained_bound+cache_bound
    sized = []
    fits = True
    for group in groups:
        length, width = group.source_length, group.maximum_corridor_width
        fixed = 4096 + 8 * length + 2048 * width
        # The third OR mask and its encoding/validation buffers stay live
        # beside both AND masks and packed peak construction.
        per_row = 256 * (length + 1) + 112 * width
        if any(plans[i].record_peaks and not plans[i].split_gradient_reversals for i in group.plan_indices):
            per_row += 32*width
        streaming_rows = SPEC.maximum_streaming_block_pixels // length
        available_rows = (maximum_temporary_bytes - retained_bound-cache_bound - fixed) // per_row
        if streaming_rows < 1 or available_rows < 1:
            fits = False
        batch_rows = max(1, min(streaming_rows, available_rows,
                                max(b-a for a, b in group.trace_intervals)))
        required_peak = max(required_peak,retained_bound+cache_bound+fixed+per_row*batch_rows)
        sized.append(replace(group, batch_rows=batch_rows))
    return tuple(sized), pixel_work, value_work, mask_work, required_peak, metadata, fits


def _row(measured, index):
    return TraceMeasurement(measured.coordinates, *(getattr(measured, name)[index] for name in (
        "gradient_z", "tone_z", "texture_z", "signed_gradient", "left_tone", "right_tone",
        "left_texture", "right_texture")), temporary_bytes=measured.temporary_bytes)


def _source(row, plan, trace):
    digest = sha256()
    for array in (row.coordinates, row.gradient_z, row.tone_z, row.texture_z, row.signed_gradient):
        digest.update(array.tobytes(order="C"))
    return TransitionPeakTraceSource(plan.source_id, plan.source_extent, plan.boundary_axis, trace,
        (int(row.coordinates[0]), int(row.coordinates[-1])), SPEC.local_window_px(plan.coordinate_scale_px_per_mm),
        SPEC.transition_gap_px(plan.coordinate_scale_px_per_mm), float(SPEC.gradient_z_minimum),
        float(SPEC.tone_or_texture_z_minimum), digest.hexdigest())


def _strip(measured, block_start, start, stop, index, plan, sources, response_cache=None, row_masks=None):
    left, right = _corridor_domain(plan)
    if row_masks is not None and (stop != start+1 or response_cache is not None):
        raise ValueError('retained masks require one complete refinement row')
    if row_masks is None:
        positive = np.empty((stop-start, right-left), dtype=np.uint8)
        negative = np.empty_like(positive)
        credible = np.empty_like(positive)
    peak_records = bytearray()
    localization_widths = bytearray()
    row_offsets = [0]
    for trace in range(start, stop):
        view = _slice_trace_measurement(_row(measured, trace-block_start), plan.coordinate_interval_px)
        if response_cache is not None:
            response_cache.capture(index,trace,view,sources.get(trace))
        if row_masks is None:
            gradient, secondary, group_support = transition_peak_support(view, SPEC)
            connected = gradient & (secondary >= SPEC.tone_or_texture_z_minimum)
            positive[trace-start] = connected & (view.signed_gradient > 0.0)
            negative[trace-start] = connected & (view.signed_gradient < 0.0)
            credible[trace-start] = group_support
        peaks = (measured_transition_peaks(view,SPEC,split_gradient_reversals=plan.split_gradient_reversals)
                 if plan.record_peaks else ())
        for peak in peaks:
            peak_records.extend(_PEAK_RECORD.pack(int(view.coordinates[peak.coordinate_index]), peak.canonical_coordinate,
                peak.physical_position_interval.minimum, peak.physical_position_interval.maximum,
                peak.gradient_z, peak.tone_z, peak.texture_z, peak.polarity))
            if not plan.split_gradient_reversals:
                localization_widths.extend(_LOCALIZATION_WIDTH.pack(peak.localization_interval.width))
        row_offsets.append(len(peak_records) // _PEAK_RECORD.size)
    masks = (tuple(np.packbits(mask,bitorder='little').tobytes().hex() for mask in (positive,negative,credible))
             if row_masks is None else row_masks)
    return NativeTraceBridgeStrip(index, start, stop, left, right,
        *masks, peak_records.hex(), tuple(row_offsets),
        tuple(sources[t] for t in _original_in_strip(plan, start, stop)),localization_widths.hex())


def _mask_row_hex(strip,encoded,trace):
    """Copy exactly one original row, including non-byte-aligned starts."""
    width = strip.coordinate_stop_px-strip.coordinate_start_px
    start = (trace-strip.trace_start_px)*width
    first,last = start//8,(start+width+7)//8
    packed = np.frombuffer(bytes.fromhex(encoded[2*first:2*last]),dtype=np.uint8)
    bits = np.unpackbits(packed,bitorder='little',count=start%8+width)[start%8:]
    return np.packbits(bits,bitorder='little').tobytes().hex()


def _retained_strip_bytes(metadata, strips):
    return metadata + sum(1024 + 48 * len(strip.peak_row_offsets) + len(strip.peak_records_hex)
        + len(strip.localization_widths_hex)
        + len(strip.positive_mask_hex) + len(strip.negative_mask_hex) + len(strip.credible_mask_hex)
        + 1024 * len(strip.original_trace_sources) for strip in strips)


def validate_native_trace_bridge_batch(batch: NativeTraceBridgeBatch) -> None:
    """Validate complete work/storage metadata without pixels or array replay.

    Successful reservations are reconstructed with the same preparation
    owner, using the reported peak as its budget. Failed required memory is
    diagnostic only: no caller memory allowance is retained in those records.
    This validates resource accounting, not the truth of pixel measurements.
    """
    if not isinstance(batch, NativeTraceBridgeBatch):
        raise ValueError("bridge work validation requires a typed batch")
    batch.__post_init__()
    preflight = native_trace_bridge_preflight_value_visit_bound(batch.plans,batch.response_source_plans)
    if batch.preflight_value_visit_bound != preflight:
        raise ValueError("bridge structural preflight work changed")
    if not batch.plans:
        if any((batch.required_pixel_query_count, batch.required_value_visit_bound)) or (
            not batch.bound_exceeded and any((batch.pixel_query_count, batch.value_visit_bound,
                batch.mask_site_work_bound, batch.retained_bytes, batch.peak_temporary_bytes,
                batch.required_peak_temporary_bytes))
        ):
            raise ValueError("empty bridge batch claimed measured work or storage")
        return
    groups, pixels, visits, mask_work, peak, metadata, fits = _prepare(
        batch.plans,batch.peak_temporary_bytes,batch.response_source_plans)
    if (batch.required_pixel_query_count != pixels or batch.required_value_visit_bound != visits):
        raise ValueError("bridge required work changed its complete plans")
    if batch.bound_exceeded:
        return
    if (not fits or batch.pixel_query_count != pixels or batch.value_visit_bound != visits
            or batch.mask_site_work_bound != mask_work or batch.peak_temporary_bytes != peak
            or batch.required_peak_temporary_bytes != peak
            or batch.retained_bytes != _retained_strip_bytes(metadata, batch.strips)):
        raise ValueError("bridge measured work or storage differs from its complete reservation")
    row_limits = {index: group.batch_rows for group in groups for index in group.plan_indices}
    if any(strip.trace_stop_px - strip.trace_start_px > row_limits[strip.plan_index] for strip in batch.strips):
        raise ValueError("bridge strip exceeds its reserved streaming row block")


def measure_native_trace_bridges(field: PhotoBoundaryMeasurementField, plans: tuple[NativeTraceBridgePlan, ...], *,
                                 maximum_pixel_queries: int, maximum_temporary_bytes: int) -> NativeTraceBridgeBatch:
    """Measure the whole frozen batch or return no measured strips.

    ``maximum_pixel_queries`` is the caller's remaining combined pixel/value
    allowance, including ``preflight_value_visit_bound``. The required value
    bound excludes that separately named preflight. ``mask_site_work_bound``
    is a subset of ``value_visit_bound``.
    Peak memory reserves all possible fixed-size peak records before reading any pixel;
    it is deliberately conservative even when the eventual image is flat.
    """
    if any(p.retain_responses for p in plans):
        raise ValueError('retained signals require their call-local response owner')
    return _measure_native_trace_bridges(field,plans,maximum_pixel_queries=maximum_pixel_queries,
                                        maximum_temporary_bytes=maximum_temporary_bytes)[0]


def measure_native_trace_signals(field,plans,*,maximum_pixel_queries,maximum_temporary_bytes):
    if any(p.record_peaks or not p.retain_responses for p in plans):
        raise ValueError('retained signal measurement requires signal-only plans')
    return _measure_native_trace_bridges(field,plans,maximum_pixel_queries=maximum_pixel_queries,
        maximum_temporary_bytes=maximum_temporary_bytes,capture_responses=True)


def _measure_native_trace_bridges(field,plans,*,maximum_pixel_queries,maximum_temporary_bytes,capture_responses=False):
    preflight = native_trace_bridge_preflight_value_visit_bound(plans)
    _integer(maximum_pixel_queries, "maximum pixel queries")
    _integer(maximum_temporary_bytes, "maximum temporary bytes")
    if not isinstance(field, PhotoBoundaryMeasurementField):
        raise ValueError("bridge measurement requires a typed immutable field")
    if any(plan.source_id != field.source_id or plan.source_extent != field.source_extent for plan in plans):
        raise ValueError("bridge plans belong to another original source field")
    if not plans:
        batch = NativeTraceBridgeBatch((), (), 0, 0, 0, 0, 0, preflight > maximum_pixel_queries,
                                      preflight_value_visit_bound=preflight)
        cache = NativeTraceResponseCache(plans) if capture_responses and not batch.bound_exceeded else None
        if cache is not None:cache.seal(batch)
        return batch,cache
    groups, pixels, visits, mask_work, peak, metadata, fits = _prepare(plans, maximum_temporary_bytes)
    if not fits or peak > maximum_temporary_bytes or pixels + visits + preflight > maximum_pixel_queries:
        return NativeTraceBridgeBatch(plans, (), 0, 0, 0, 0, 0, True,pixels,visits,peak,preflight),None
    cache = NativeTraceResponseCache(plans) if capture_responses else None
    strips = []
    for group in groups:
        first = plans[group.plan_indices[0]]
        original = set(t for i in group.plan_indices for t in _included_original_traces(plans[i]))
        segments = sorted((low, high, index) for index in group.plan_indices
                          for low, high in plans[index].trace_intervals_px)
        segment_index = 0
        active = []
        for begin, end in group.trace_intervals:
            for block_start in range(begin, end, group.batch_rows):
                block_stop = min(end, block_start + group.batch_rows)
                values = (field.source_gray[block_start:block_stop, :] if first.boundary_axis == BoundaryAxis.X
                          else field.source_gray[:, block_start:block_stop].T)
                measured = measure_trace_rows(values, first.normalization_interval_px,
                                              first.coordinate_scale_px_per_mm, SPEC)
                sources = {trace: _source(_row(measured, trace-block_start), first, trace)
                           for trace in range(block_start, block_stop) if trace in original}
                # Visit only intervals intersecting this block, rather than
                # scanning every plan/interval for every dense row block.
                while segment_index < len(segments) and segments[segment_index][0] < block_stop:
                    active.append(segments[segment_index])
                    segment_index += 1
                active = [segment for segment in active if segment[1] > block_start]
                for low, high, index in active:
                    start, stop = max(block_start, low), min(block_stop, high)
                    strips.append(_strip(measured,block_start,start,stop,index,plans[index],sources,cache))
                del measured, values, sources
    frozen = tuple(strips)
    retained = _retained_strip_bytes(metadata, frozen)
    if retained > peak:
        raise RuntimeError("bridge measurement exceeded its pre-reserved retained storage")
    batch = NativeTraceBridgeBatch(plans,frozen,pixels,visits,mask_work,retained,peak,False,
        pixels,visits,peak,preflight,response_cache_bytes=(0 if cache is None else native_trace_response_cache_byte_bound(plans)))
    if cache is not None:cache.seal(batch)
    return batch,cache


def refine_native_trace_responses(signal,cache,plans,*,maximum_pixel_queries,maximum_temporary_bytes):
    """Consume the exact retained response rows without another source read."""
    if (not isinstance(cache,NativeTraceResponseCache) or cache.closed or cache.signal_batch is not signal
            or signal.bound_exceeded or cache.plans != signal.plans):
        raise ValueError('refinement lost its same-call complete response owner')
    indices = _reuse_plan_indices(plans,signal.plans)
    preflight = native_trace_bridge_preflight_value_visit_bound(plans,signal.plans)
    _integer(maximum_pixel_queries,'maximum pixel queries')
    _integer(maximum_temporary_bytes,'maximum temporary bytes')
    _,pixels,visits,mask_work,peak,metadata,fits = _prepare(plans,maximum_temporary_bytes,signal.plans)
    if not fits or peak>maximum_temporary_bytes or visits+preflight>maximum_pixel_queries:
        return NativeTraceBridgeBatch(plans,(),0,0,0,0,0,True,pixels,visits,peak,preflight,
                                      response_source_plans=signal.plans)
    expected = {(i,t) for i,p in enumerate(signal.plans) for a,b in p.trace_intervals_px for t in range(a,b)}
    if set(cache.rows)!=expected:
        raise ValueError('response cache lost or duplicated a measured trace')
    requested = {(source,t) for source,p in zip(indices,plans,strict=True)
                 for a,b in p.trace_intervals_px for t in range(a,b)}
    # Rebuild the maps: deleting entries alone retains full signal hash-table
    # capacity alongside the growing encoded refinement. The initial cache
    # header allowance includes these short-lived metadata copies.
    cache.rows = {key:value for key,value in cache.rows.items() if key in requested}
    cache.coordinates = {source:cache.coordinates[source] for source in indices}
    del expected,requested
    strips = []
    for index,(source,plan) in enumerate(zip(indices,plans,strict=True)):
        coordinates = cache.coordinates[source]
        originals = sorted((s for s in signal.strips if s.plan_index==source),key=lambda s:s.trace_start_px)
        starts = tuple(s.trace_start_px for s in originals)
        for a,b in plan.trace_intervals_px:
            for trace in range(a,b):
                matrix,origin = cache.rows.pop((source,trace))
                if (matrix.dtype != np.float64 or matrix.shape != (8,coordinates.size) or matrix.flags.writeable
                        or coordinates.flags.writeable):
                    raise ValueError('response cache changed its exact immutable numeric payload')
                measured = TraceRowsMeasurement(coordinates,*(matrix[i:i+1] for i in range(8)),temporary_bytes=matrix.nbytes)
                sources = {} if origin is None else {trace:origin}
                original = originals[bisect_right(starts,trace)-1]
                masks = tuple(_mask_row_hex(original,getattr(original,name),trace)
                    for name in ('positive_mask_hex','negative_mask_hex','credible_mask_hex'))
                strips.append(_strip(measured,trace,trace,trace+1,index,plan,sources,row_masks=masks))
                del matrix,measured,sources,origin
    cache.release()
    frozen = tuple(strips)
    retained = _retained_strip_bytes(metadata,frozen)
    if retained>peak:
        raise RuntimeError('refinement exceeded its reserved retained storage')
    return NativeTraceBridgeBatch(plans,frozen,0,visits,mask_work,retained,peak,False,
                                  0,visits,peak,preflight,response_source_plans=signal.plans)


def validate_native_trace_response_reuse(batch,signal):
    """Bind a reused batch to every original signal row, without source pixels."""
    if signal.bound_exceeded or batch.response_source_plans != signal.plans:
        raise ValueError('refinement changed its complete measured signal source')
    indices = _reuse_plan_indices(batch.plans,signal.plans)
    for target,source in enumerate(indices):
        rows = {s.trace_start_px:s for s in batch.strips if s.plan_index==target}
        for original in signal.strips:
            if original.plan_index!=source:continue
            fields = ('positive_mask_hex','negative_mask_hex','credible_mask_hex')
            decoded = tuple(_decode_checked_mask(original,getattr(original,f)) for f in fields)
            origins = {s.trace_coordinate_px:s for s in original.original_trace_sources}
            for trace in range(original.trace_start_px,original.trace_stop_px):
                strip = rows.get(trace)
                if strip is None:continue
                if strip.trace_stop_px!=trace+1 or strip.original_trace_sources != (() if trace not in origins else (origins[trace],)):
                    raise ValueError('refinement lost its exact original trace source')
                for field,values in zip(fields,decoded,strict=True):
                    if not np.array_equal(_decode_checked_mask(strip,getattr(strip,field))[0],values[trace-original.trace_start_px]):
                        raise ValueError('refinement changed its original complete signal masks')


__all__ = ["NativeTraceBridgePlan", "NativeTraceBridgePeak", "NativeTraceBridgeStrip", "NativeTraceBridgeBatch",
           "native_trace_bridge_preflight_value_visit_bound", "measure_native_trace_bridges", "decode_mask", "decode_credible_mask", "peaks_at_row",
           "validate_native_trace_bridge_batch", "native_trace_bridge_normalization_domain",
           "native_trace_bridge_retained_byte_bound", "native_trace_response_cache_byte_bound",
           "measure_native_trace_signals", "refine_native_trace_responses"]
