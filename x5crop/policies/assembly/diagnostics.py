from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.diagnostics import RuntimeDiagnosticsPolicy


def diagnostics_policy(params: FormatParameters) -> RuntimeDiagnosticsPolicy:
    return RuntimeDiagnosticsPolicy(
        debug_gap_overlay=params.diagnostics.debug_gap_overlay,
        nearby_separator=params.diagnostics.nearby_separator_diagnostics,
    )
