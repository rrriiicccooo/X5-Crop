from __future__ import annotations

from typing import Any

import numpy as np

from ....policies.runtime.candidate import PartialEdgeHintPolicy
from ....utils import clamp_int


def partial_edge_hint(
    profile: np.ndarray,
    origin: float,
    pitch: float,
    count: int,
    policy: PartialEdgeHintPolicy,
) -> dict[str, Any]:
    if profile.size == 0 or count <= 0:
        return {}
    span_start = int(max(0, min(len(profile) - 1, round(origin))))
    span_end = int(max(0, min(len(profile), round(origin + pitch * count))))
    edge_window = clamp_int(pitch * policy.window_ratio, policy.window_min, policy.window_max)
    left_window = profile[span_start:min(len(profile), span_start + edge_window)]
    right_window = profile[max(0, span_end - edge_window):span_end]
    return {
        "left_edge_score": float(left_window.max()) if left_window.size else 0.0,
        "right_edge_score": float(right_window.max()) if right_window.size else 0.0,
        "span_start": span_start,
        "span_end": span_end,
    }
