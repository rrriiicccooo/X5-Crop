from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.diagnostics import RuntimeDiagnosticsPolicy


def diagnostics_policy(params: FormatParameters) -> RuntimeDiagnosticsPolicy:
    return RuntimeDiagnosticsPolicy(
        debug_gap_overlay=params.diagnostics.debug_gap_overlay,
        nearby_separator_search=params.separator.nearby_separator_refinement,
        nearby_separator_comparison=params.diagnostics.nearby_separator_diagnostics,
    )
