"""Measure both texture directions at already registered Cross transitions."""

import numpy as np

from ...domain import EvidenceState
from ...image.gray import BaseGrayParameters, _luma_u16
from .measurement_model import NativeBackgroundTexture, NativeBackgroundTextureQuery
from .model import BoundaryAxis, QueryPurpose


def native_background_texture_query(source_extent, query, transition, spec):
    if transition.texture_sample_coordinate_px is None:
        raise ValueError("native texture requires the original localized peak coordinate")
    return NativeBackgroundTextureQuery(query.query_id, query.boundary_axis,
        transition.trace_coordinate_px, transition.texture_sample_coordinate_px, source_extent,
        spec.local_window_px(query.boundary_axis_scale_px_per_mm.maximum),
        spec.transition_gap_px(query.boundary_axis_scale_px_per_mm.maximum),
        spec.local_window_px(query.trace_axis_scale_px_per_mm.maximum))


def measure_native_background_texture(field, query):
    if query.source_extent != field.source_extent:
        raise ValueError("native background texture belongs to a different source extent")
    if not query.observable:
        return NativeBackgroundTexture(query, EvidenceState.UNAVAILABLE, None, None)
    box = query.requested_box
    patch = field.source_rgb[box.top:box.bottom, box.left:box.right]
    if query.boundary_axis == BoundaryAxis.X:
        patch = patch.transpose(1, 0, 2)
    luma = np.empty(patch.shape[:2], dtype=np.float32)
    scratch = np.empty_like(luma)
    _luma_u16(patch, luma, scratch, BaseGrayParameters())
    longitudinal = np.abs(np.diff(luma, axis=1)).mean(axis=1, dtype=np.float64)
    cross = np.abs(np.diff(luma, axis=0)).mean(axis=1, dtype=np.float64)
    texture = 0.5 * (longitudinal[:-1] + longitudinal[1:]) + cross
    center = query.window_px + query.gap_px + 1
    return NativeBackgroundTexture(query, EvidenceState.SUPPORTED,
        float(texture[center-query.gap_px-query.window_px:center-query.gap_px].mean()),
        float(texture[center+query.gap_px:center+query.gap_px+query.window_px].mean()))


def validate_native_background_textures(measurement, source_extent, spec):
    coverage = measurement.coverage
    applicable = measurement.query.purpose in (QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR)
    if not applicable:
        if (any(t.native_background_texture is not None for t in measurement.transitions)
                or coverage.native_texture_query_count or coverage.native_texture_completed_count
                or coverage.native_texture_pixel_query_count or coverage.native_texture_bound_exceeded):
            raise ValueError("native background texture belongs only to registered Cross windows")
        return
    if measurement.state != EvidenceState.SUPPORTED:
        if coverage.native_texture_completed_count or coverage.native_texture_pixel_query_count:
            raise ValueError("failed native texture batch exposed a completed prefix")
        return
    work, peak = 0, 0
    for transition in measurement.transitions:
        expected = native_background_texture_query(source_extent, measurement.query, transition, spec)
        evidence = transition.native_background_texture
        if evidence is None or evidence.query != expected:
            raise ValueError("native background texture changed its complete registered pixel domain")
        work += expected.pixel_query_count
        peak = max(peak, expected.peak_temporary_bytes)
    if (coverage.native_texture_query_count != len(measurement.transitions)
            or coverage.native_texture_completed_count != len(measurement.transitions)
            or coverage.native_texture_pixel_query_count != work
            or coverage.peak_temporary_bytes < peak):
        raise ValueError("native background texture work receipt is incomplete")
