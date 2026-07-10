from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.diagnostics import (
    DebugGapOverlayPolicy,
    NearbySeparatorDiagnosticsPolicy,
    RuntimeDiagnosticsPolicy,
)


def diagnostics_policy(params: FormatParameters) -> RuntimeDiagnosticsPolicy:
    debug_gap = params.diagnostics.debug_gap_overlay
    nearby = params.diagnostics.nearby_separator_diagnostics
    return RuntimeDiagnosticsPolicy(
        debug_gap_overlay=DebugGapOverlayPolicy(
            overlap_tolerance_ratio=float(debug_gap.overlap_tolerance_ratio),
            overlap_tolerance_min=float(debug_gap.overlap_tolerance_min),
            overlap_tolerance_max=float(debug_gap.overlap_tolerance_max),
            tick_length_ratio=float(debug_gap.tick_length_ratio),
            tick_length_min=int(debug_gap.tick_length_min),
            hard_line_width=int(debug_gap.hard_line_width),
            model_line_width=int(debug_gap.model_line_width),
            diagnostic_line_width=int(debug_gap.diagnostic_line_width),
        ),
        nearby_separator=NearbySeparatorDiagnosticsPolicy(
            window_ratio=float(nearby.window_ratio),
            window_min=int(nearby.window_min),
            window_max=int(nearby.window_max),
            exclude_ratio=float(nearby.exclude_ratio),
            exclude_min=int(nearby.exclude_min),
            exclude_max=int(nearby.exclude_max),
            max_width_ratio=float(nearby.max_width_ratio),
            max_width_min=int(nearby.max_width_min),
            max_width_max=int(nearby.max_width_max),
            detail_score_add=float(nearby.detail_score_add),
            detail_score_multiplier=float(nearby.detail_score_multiplier),
        ),
    )
