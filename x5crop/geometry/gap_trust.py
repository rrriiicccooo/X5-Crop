from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..domain import Box, SeparatorBandObservation
from ..gap_methods import is_hard_gap_method
from ..utils import clamp_float, clamp_int
from .detection_parameters import HardGapTrustParameters


@dataclass(frozen=True)
class HardGapPixelSignals:
    core_mean: float
    core_content: float
    core_dark: float
    core_activity: float
    cross_axis_coverage_ratio: float
    cross_axis_continuity_ratio: float
    cross_axis_break_count: int
    separator_band_straightness: float
    left_content: float
    right_content: float
    start: int
    end: int
    guard: int

    @property
    def side_content(self) -> float:
        return min(self.left_content, self.right_content)

    @property
    def side_balance(self) -> float:
        return abs(self.left_content - self.right_content)

    @property
    def continuity(self) -> float:
        return min(self.core_content, self.side_content)


@dataclass(frozen=True)
class HardGapTrustAssessment:
    trust: str
    reason: str
    width_ratio: float
    model_delta_ratio: float | None
    nearby_separator_conflict: bool
    signal_flags: dict[str, bool]

    def detail(self) -> dict[str, Any]:
        return {
            "trust": self.trust,
            "reason": self.reason,
            "width_ratio": float(self.width_ratio),
            "model_delta_ratio": (
                None
                if self.model_delta_ratio is None
                else float(self.model_delta_ratio)
            ),
            "nearby_separator_conflict": bool(self.nearby_separator_conflict),
            "signal_flags": dict(self.signal_flags),
        }


@dataclass(frozen=True)
class HardGapTrustContext:
    width_ratio: float
    model_delta_ratio: float | None
    nearby_separator_conflict: bool
    signal_flags: dict[str, bool]


def hard_gap_width_ratio(gap: SeparatorBandObservation, pitch: float) -> float:
    return float(gap.width) / max(1.0, float(pitch))


def hard_gap_is_narrow(gap: SeparatorBandObservation, pitch: float, config: HardGapTrustParameters) -> bool:
    return 0.0 < gap.width <= clamp_float(
        pitch * config.narrow_ratio,
        config.narrow_min,
        config.narrow_max,
    )


def hard_gap_pixel_signals(
    gray_work: np.ndarray,
    outer: Box,
    gap: SeparatorBandObservation,
    pitch: float,
    config: HardGapTrustParameters,
) -> HardGapPixelSignals | None:
    if gap.start is None or gap.end is None:
        return None
    start = int(round(outer.left + min(gap.start, gap.end)))
    end = int(round(outer.left + max(gap.start, gap.end)))
    start = max(outer.left, min(outer.right, start))
    end = max(start + 1, min(outer.right, end))
    guard = clamp_int(
        max(float(end - start), pitch * config.guard_ratio),
        config.guard_min,
        config.guard_max,
    )
    left_start = max(outer.left, start - guard)
    right_end = min(outer.right, end + guard)
    core = gray_work[outer.top:outer.bottom, start:end]
    if not core.size:
        return None
    left = gray_work[outer.top:outer.bottom, left_start:start]
    right = gray_work[outer.top:outer.bottom, end:right_end]
    cross_axis = hard_gap_cross_axis_continuity(core, config)
    return HardGapPixelSignals(
        core_mean=float(core.mean()),
        core_content=float((core < config.core_content_threshold).mean()),
        core_dark=float((core < config.core_dark_threshold).mean()),
        core_activity=float(core.std() / 255.0),
        cross_axis_coverage_ratio=float(cross_axis["coverage_ratio"]),
        cross_axis_continuity_ratio=float(cross_axis["continuity_ratio"]),
        cross_axis_break_count=int(cross_axis["break_count"]),
        separator_band_straightness=float(cross_axis["straightness"]),
        left_content=float((left < config.core_content_threshold).mean()) if left.size else 0.0,
        right_content=float((right < config.core_content_threshold).mean()) if right.size else 0.0,
        start=int(start),
        end=int(end),
        guard=int(guard),
    )


def _longest_true_run(mask: np.ndarray) -> int:
    longest = 0
    current = 0
    for flag in mask.astype(bool):
        if bool(flag):
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def _transition_count(mask: np.ndarray) -> int:
    if mask.size <= 1:
        return 0
    return int(np.count_nonzero(np.diff(mask.astype(np.int8))))


def hard_gap_cross_axis_continuity(
    core: np.ndarray,
    config: HardGapTrustParameters,
) -> dict[str, float | int | bool]:
    if core.size == 0:
        return {
            "coverage_ratio": 0.0,
            "continuity_ratio": 0.0,
            "break_count": 0,
            "straightness": 0.0,
            "weak": True,
        }
    rows = core.astype(np.float32, copy=False)
    row_activity = rows.std(axis=1) / 255.0
    row_dark = (rows < config.core_dark_threshold).mean(axis=1)
    row_light = (rows >= config.core_content_threshold).mean(axis=1)
    row_nonwhite = (rows < config.core_content_threshold).mean(axis=1)
    low_activity = row_activity <= config.dark_activity_max
    dark_like = row_dark >= config.dark_fraction_min
    light_like = row_light >= 1.0 - config.weak_content_min
    neutral_low_texture = (
        low_activity
        & (row_nonwhite >= config.weak_content_min)
        & (row_nonwhite <= 1.0 - config.weak_content_min)
    )
    separator_like = low_activity & (dark_like | light_like | neutral_low_texture)
    coverage = float(separator_like.mean()) if separator_like.size else 0.0
    longest = _longest_true_run(separator_like)
    continuity = float(longest) / max(1.0, float(separator_like.size))
    transitions = _transition_count(separator_like)
    straightness = max(0.0, 1.0 - transitions / max(1.0, float(separator_like.size - 1)))
    weak = (
        coverage < config.cross_axis_coverage_min
        or continuity < config.cross_axis_continuity_min
    )
    return {
        "coverage_ratio": coverage,
        "continuity_ratio": continuity,
        "break_count": transitions,
        "straightness": straightness,
        "weak": bool(weak),
    }


def hard_gap_tonal_separator_like(signals: HardGapPixelSignals, config: HardGapTrustParameters) -> bool:
    return (
        signals.core_mean <= config.dark_mean_max
        and signals.core_dark >= config.dark_fraction_min
        and signals.core_activity <= config.dark_activity_max
    )


def hard_gap_low_contrast_tonal_gap(signals: HardGapPixelSignals, config: HardGapTrustParameters) -> bool:
    return signals.core_mean >= config.weak_mean_min and signals.core_content >= config.weak_content_min


def hard_gap_content_continuous(signals: HardGapPixelSignals, config: HardGapTrustParameters) -> bool:
    return signals.continuity >= config.continuity_min and signals.core_activity >= config.activity_min


def hard_gap_geometry_conflict(
    width_ratio: float,
    score: float,
    model_delta_ratio: float,
    config: HardGapTrustParameters,
) -> bool:
    return model_delta_ratio >= config.model_delta_ratio and (
        width_ratio < config.geometry_width_ratio or score < config.model_conflict_score
    )


def hard_gap_signal_flags(
    signals: HardGapPixelSignals | None,
    config: HardGapTrustParameters,
) -> dict[str, bool]:
    if signals is None:
        return {}
    return {
        "tonal_separator_like": hard_gap_tonal_separator_like(signals, config),
        "low_contrast_tonal_gap": hard_gap_low_contrast_tonal_gap(signals, config),
        "content_continuous": hard_gap_content_continuous(signals, config),
        "cross_axis_continuity_weak": (
            signals.cross_axis_coverage_ratio < config.cross_axis_coverage_min
            or signals.cross_axis_continuity_ratio < config.cross_axis_continuity_min
        ),
    }


def hard_gap_trust_context(
    config: HardGapTrustParameters,
    *,
    width_ratio: float,
    model_delta_ratio: float | None = None,
    nearby_separator_conflict: bool = False,
    signals: HardGapPixelSignals | None = None,
) -> HardGapTrustContext:
    return HardGapTrustContext(
        width_ratio=float(width_ratio),
        model_delta_ratio=model_delta_ratio,
        nearby_separator_conflict=bool(nearby_separator_conflict),
        signal_flags=hard_gap_signal_flags(signals, config),
    )


def hard_gap_trust_assessment_result(
    context: HardGapTrustContext,
    trust: str,
    reason: str,
) -> HardGapTrustAssessment:
    return HardGapTrustAssessment(
        trust=trust,
        reason=reason,
        width_ratio=context.width_ratio,
        model_delta_ratio=context.model_delta_ratio,
        nearby_separator_conflict=context.nearby_separator_conflict,
        signal_flags=context.signal_flags,
    )




def diagnostic_hard_gap_trust_assessment(
    gap: SeparatorBandObservation,
    pitch: float,
    config: HardGapTrustParameters,
    *,
    width_ratio: float,
    model_delta_ratio: float,
    nearby_separator_conflict: bool,
    signals: HardGapPixelSignals,
) -> HardGapTrustAssessment:
    context = hard_gap_trust_context(
        config,
        width_ratio=width_ratio,
        model_delta_ratio=model_delta_ratio,
        nearby_separator_conflict=nearby_separator_conflict,
        signals=signals,
    )

    def assessment(trust: str, reason: str) -> HardGapTrustAssessment:
        return hard_gap_trust_assessment_result(context, trust, reason)

    if not is_hard_gap_method(gap.method):
        return assessment("not_hard_gap", "not_hard_gap")
    flags = context.signal_flags
    tonal_separator_like = bool(flags.get("tonal_separator_like", False))
    if nearby_separator_conflict:
        return assessment("nearby_separator_conflict", "nearby_separator_candidate_stronger")
    if hard_gap_geometry_conflict(width_ratio, gap.score, model_delta_ratio, config):
        return assessment("geometry_conflict", "model_delta_or_score_conflict")
    if width_ratio < config.frame_border_width_ratio and tonal_separator_like:
        return assessment("suspect_frame_border", "too_narrow_separator_band")
    if hard_gap_is_narrow(gap, pitch, config) and (
        bool(flags.get("content_continuous", False))
        or bool(flags.get("low_contrast_tonal_gap", False))
    ):
        return assessment("suspect_internal_edge", "narrow_content_continuity_or_low_contrast_tonal")
    if bool(flags.get("cross_axis_continuity_weak", False)):
        return assessment("weak_or_ambiguous_separator", "cross_axis_continuity_weak")
    if hard_gap_is_narrow(gap, pitch, config):
        return assessment("narrow_but_ok", "narrow_without_content_continuity")
    if tonal_separator_like or signals.core_content <= config.strong_core_content_max or gap.score >= config.strong_min_score:
        return assessment("strong_separator", "tonal_or_low_content_or_high_score")
    return assessment("weak_or_ambiguous_separator", "no_strong_diagnostic_trust_rule")
