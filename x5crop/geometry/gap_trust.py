from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ..domain import Box, Gap
from ..gap_methods import is_hard_gap_method
from ..utils import clamp_float, clamp_int
from .nearby_separator import nearby_separator_replacement_assessment
from .detection_parameters import HardGapTrustParameters, NearbySeparatorCorrectionParameters


@dataclass(frozen=True)
class HardGapPixelSignals:
    core_mean: float
    core_content: float
    core_dark: float
    core_activity: float
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


def hard_gap_width_ratio(gap: Gap, pitch: float) -> float:
    return float(gap.width) / max(1.0, float(pitch))


def hard_gap_is_narrow(gap: Gap, pitch: float, config: HardGapTrustParameters) -> bool:
    return 0.0 < gap.width <= clamp_float(
        pitch * config.narrow_ratio,
        config.narrow_min,
        config.narrow_max,
    )


def hard_gap_pixel_signals(
    gray_work: np.ndarray,
    outer: Box,
    gap: Gap,
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
    return HardGapPixelSignals(
        core_mean=float(core.mean()),
        core_content=float((core < config.core_content_threshold).mean()),
        core_dark=float((core < config.core_dark_threshold).mean()),
        core_activity=float(core.std() / 255.0),
        left_content=float((left < config.core_content_threshold).mean()) if left.size else 0.0,
        right_content=float((right < config.core_content_threshold).mean()) if right.size else 0.0,
        start=int(start),
        end=int(end),
        guard=int(guard),
    )


def hard_gap_dark_separator_like(signals: HardGapPixelSignals, config: HardGapTrustParameters) -> bool:
    return (
        signals.core_mean <= config.dark_mean_max
        and signals.core_dark >= config.dark_fraction_min
        and signals.core_activity <= config.dark_activity_max
    )


def hard_gap_weak_dark_gap(signals: HardGapPixelSignals, config: HardGapTrustParameters) -> bool:
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
        "dark_separator_like": hard_gap_dark_separator_like(signals, config),
        "weak_dark_gap": hard_gap_weak_dark_gap(signals, config),
        "content_continuous": hard_gap_content_continuous(signals, config),
    }


def runtime_hard_gap_trust_assessment(
    gap: Gap,
    pitch: float,
    config: HardGapTrustParameters,
    *,
    width_ratio: float,
    model_delta_ratio: float | None = None,
    nearby_separator_conflict: bool = False,
    signals: HardGapPixelSignals | None = None,
) -> HardGapTrustAssessment:
    flags = hard_gap_signal_flags(signals, config)

    def assessment(trust: str, reason: str) -> HardGapTrustAssessment:
        return HardGapTrustAssessment(
            trust=trust,
            reason=reason,
            width_ratio=width_ratio,
            model_delta_ratio=model_delta_ratio,
            nearby_separator_conflict=nearby_separator_conflict,
            signal_flags=flags,
        )

    if not is_hard_gap_method(gap.method) or pitch <= 0:
        return assessment("not_hard_gap", "not_hard_gap_or_invalid_pitch")
    if nearby_separator_conflict:
        return assessment("nearby_separator_conflict", "nearby_separator_candidate_stronger")
    if model_delta_ratio is not None and hard_gap_geometry_conflict(width_ratio, gap.score, model_delta_ratio, config):
        return assessment("geometry_conflict", "model_delta_or_score_conflict")
    if signals is not None:
        dark_separator_like = bool(flags.get("dark_separator_like", False))
        if width_ratio < config.frame_border_width_ratio and dark_separator_like:
            return assessment("suspect_frame_border", "too_narrow_separator_band")
        if hard_gap_is_narrow(gap, pitch, config) and (
            bool(flags.get("content_continuous", False))
            or bool(flags.get("weak_dark_gap", False))
        ):
            return assessment("suspect_internal_edge", "narrow_content_continuity_or_weak_dark")
    if gap.score >= config.strong_min_score and config.strong_width_min <= width_ratio <= config.strong_width_max:
        return assessment("strong_separator", "score_and_width_in_strong_range")
    if gap.score >= config.narrow_ok_score and config.narrow_ok_width_min <= width_ratio < config.narrow_ok_width_max:
        return assessment("narrow_but_ok", "narrow_score_and_width_ok")
    return assessment("weak_or_ambiguous_separator", "no_strong_runtime_trust_rule")


def classify_runtime_hard_gap_trust(
    gap: Gap,
    pitch: float,
    config: HardGapTrustParameters,
    *,
    width_ratio: float,
    model_delta_ratio: float | None = None,
    nearby_separator_conflict: bool = False,
    signals: HardGapPixelSignals | None = None,
) -> str:
    return runtime_hard_gap_trust_assessment(
        gap,
        pitch,
        config,
        width_ratio=width_ratio,
        model_delta_ratio=model_delta_ratio,
        nearby_separator_conflict=nearby_separator_conflict,
        signals=signals,
    ).trust


def diagnostic_hard_gap_trust_assessment(
    gap: Gap,
    pitch: float,
    config: HardGapTrustParameters,
    *,
    width_ratio: float,
    model_delta_ratio: float,
    nearby_separator_conflict: bool,
    signals: HardGapPixelSignals,
) -> HardGapTrustAssessment:
    flags = hard_gap_signal_flags(signals, config)

    def assessment(trust: str, reason: str) -> HardGapTrustAssessment:
        return HardGapTrustAssessment(
            trust=trust,
            reason=reason,
            width_ratio=width_ratio,
            model_delta_ratio=model_delta_ratio,
            nearby_separator_conflict=nearby_separator_conflict,
            signal_flags=flags,
        )

    if not is_hard_gap_method(gap.method):
        return assessment("not_hard_gap", "not_hard_gap")
    dark_separator_like = bool(flags.get("dark_separator_like", False))
    if nearby_separator_conflict:
        return assessment("nearby_separator_conflict", "nearby_separator_candidate_stronger")
    if hard_gap_geometry_conflict(width_ratio, gap.score, model_delta_ratio, config):
        return assessment("geometry_conflict", "model_delta_or_score_conflict")
    if width_ratio < config.frame_border_width_ratio and dark_separator_like:
        return assessment("suspect_frame_border", "too_narrow_separator_band")
    if hard_gap_is_narrow(gap, pitch, config) and (
        bool(flags.get("content_continuous", False))
        or bool(flags.get("weak_dark_gap", False))
    ):
        return assessment("suspect_internal_edge", "narrow_content_continuity_or_weak_dark")
    if hard_gap_is_narrow(gap, pitch, config):
        return assessment("narrow_but_ok", "narrow_without_content_continuity")
    if dark_separator_like or signals.core_content <= config.strong_core_content_max or gap.score >= config.strong_min_score:
        return assessment("strong_separator", "dark_or_low_content_or_high_score")
    return assessment("weak_or_ambiguous_separator", "no_strong_diagnostic_trust_rule")


def classify_diagnostic_hard_gap_trust(
    gap: Gap,
    pitch: float,
    config: HardGapTrustParameters,
    *,
    width_ratio: float,
    model_delta_ratio: float,
    nearby_separator_conflict: bool,
    signals: HardGapPixelSignals,
) -> str:
    return diagnostic_hard_gap_trust_assessment(
        gap,
        pitch,
        config,
        width_ratio=width_ratio,
        model_delta_ratio=model_delta_ratio,
        nearby_separator_conflict=nearby_separator_conflict,
        signals=signals,
    ).trust


def runtime_signal_detail(signals: HardGapPixelSignals) -> dict[str, Any]:
    return {
        "core_mean": signals.core_mean,
        "core_content": signals.core_content,
        "core_dark": signals.core_dark,
        "core_activity": signals.core_activity,
        "left_content": signals.left_content,
        "right_content": signals.right_content,
        "side_content": signals.side_content,
        "side_balance": signals.side_balance,
        "continuity": signals.continuity,
        "window": {
            "start": int(signals.start),
            "end": int(signals.end),
            "guard": int(signals.guard),
        },
    }


def light_hard_gap_trust(
    gap: Gap,
    pitch: float,
    *,
    predicted: Optional[float] = None,
    profile: Optional[np.ndarray] = None,
    gray_work: Optional[np.ndarray] = None,
    outer: Optional[Box] = None,
    hard_gap_trust: HardGapTrustParameters | None = None,
    nearby_correction: NearbySeparatorCorrectionParameters | None = None,
) -> tuple[str, dict[str, Any]]:
    trust_config = hard_gap_trust or HardGapTrustParameters()
    if not is_hard_gap_method(gap.method) or pitch <= 0:
        assessment = runtime_hard_gap_trust_assessment(
            gap,
            pitch,
            trust_config,
            width_ratio=0.0,
        )
        return "not_hard_gap", {
            "reason": "not_hard_gap",
            "classification": assessment.detail(),
        }
    width_ratio = hard_gap_width_ratio(gap, pitch)
    detail: dict[str, Any] = {
        "width_ratio": float(width_ratio),
        "score": float(gap.score),
    }
    nearby_conflict = False
    if profile is not None:
        nearby_assessment = nearby_separator_replacement_assessment(profile, gap, pitch, nearby_correction)
        detail["nearby_separator_assessment"] = nearby_assessment.detail(gap)
        if nearby_assessment.replacement is not None:
            detail["nearby_separator_candidate"] = nearby_assessment.replacement
            nearby_conflict = True
    if nearby_conflict:
        assessment = runtime_hard_gap_trust_assessment(
            gap,
            pitch,
            trust_config,
            width_ratio=width_ratio,
            nearby_separator_conflict=True,
        )
        detail["classification"] = assessment.detail()
        return assessment.trust, detail
    model_delta_ratio = None
    if predicted is not None:
        model_delta_ratio = abs(float(gap.center) - float(predicted)) / max(1.0, float(pitch))
        detail["model_delta_ratio"] = float(model_delta_ratio)
        if hard_gap_geometry_conflict(width_ratio, gap.score, model_delta_ratio, trust_config):
            assessment = runtime_hard_gap_trust_assessment(
                gap,
                pitch,
                trust_config,
                width_ratio=width_ratio,
                model_delta_ratio=model_delta_ratio,
            )
            detail["classification"] = assessment.detail()
            return assessment.trust, detail
    signals = None
    if gray_work is not None and outer is not None and gap.start is not None and gap.end is not None:
        signals = hard_gap_pixel_signals(gray_work, outer, gap, pitch, trust_config)
        if signals is not None:
            detail["signals"] = runtime_signal_detail(signals)
    assessment = runtime_hard_gap_trust_assessment(
        gap,
        pitch,
        trust_config,
        width_ratio=width_ratio,
        model_delta_ratio=model_delta_ratio,
        nearby_separator_conflict=nearby_conflict,
        signals=signals,
    )
    detail["classification"] = assessment.detail()
    return assessment.trust, detail
