from __future__ import annotations

from typing import Any

import numpy as np

from ...domain import Box, Gap
from ...gap_methods import is_hard_gap_method
from ...geometry.detection_parameters import HardGapTrustParameters
from ...geometry.gap_trust import hard_gap_pixel_signals, hard_gap_signal_flags


def separator_cross_axis_continuity_evidence(
    gray_work: np.ndarray,
    outer: Box,
    gaps: list[Gap],
    pitch: float,
    parameters: HardGapTrustParameters,
) -> dict[str, Any]:
    if pitch <= 0.0:
        return {
            "used": False,
            "reason": "invalid_pitch",
        }
    records: list[dict[str, Any]] = []
    weak_indexes: list[int] = []
    for gap in gaps:
        if not is_hard_gap_method(gap.method):
            continue
        signals = hard_gap_pixel_signals(gray_work, outer, gap, pitch, parameters)
        if signals is None:
            records.append(
                {
                    "index": int(gap.index),
                    "method": gap.method,
                    "measured": False,
                    "reason": "missing_gap_edges",
                }
            )
            weak_indexes.append(int(gap.index))
            continue
        flags = hard_gap_signal_flags(signals, parameters)
        weak = bool(flags.get("cross_axis_continuity_weak", False))
        if weak:
            weak_indexes.append(int(gap.index))
        records.append(
            {
                "index": int(gap.index),
                "method": gap.method,
                "measured": True,
                "cross_axis_coverage_ratio": float(signals.cross_axis_coverage_ratio),
                "cross_axis_continuity_ratio": float(signals.cross_axis_continuity_ratio),
                "cross_axis_break_count": int(signals.cross_axis_break_count),
                "separator_band_straightness": float(signals.separator_band_straightness),
                "weak": weak,
            }
        )
    ok = not weak_indexes
    return {
        "used": bool(records),
        "evidence_role": "hard_separator_cross_axis_continuity",
        "physical_rule": "separator_crosses_short_axis_as_a_continuous_band",
        "ok": bool(ok),
        "reason": "ok" if ok else "separator_cross_axis_continuity_weak",
        "hard_gap_count": int(len(records)),
        "weak_gap_indexes": weak_indexes,
        "records": records,
        "minimums": {
            "cross_axis_coverage_ratio": float(parameters.cross_axis_coverage_min),
            "cross_axis_continuity_ratio": float(parameters.cross_axis_continuity_min),
        },
    }
