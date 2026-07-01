from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..common import FilmFormat, FormatTuning
from ..geometry import FrameFitPolicy


FULL = "full"
PARTIAL = "partial"


@dataclass(frozen=True)
class CountPolicy:
    """Frame-count and partial-offset policy for one format/mode pair."""

    fixed_count: int | None
    auto_counts: tuple[int, ...]
    partial_offsets: tuple[float, ...] = (0.0,)
    include_default_in_partial_auto: bool = False

    def count_specs(
        self,
        fmt: FilmFormat,
        strip_mode: str,
        requested_count: int,
        count_override: int | None,
    ) -> list[tuple[int, str, tuple[float, ...]]]:
        if strip_mode == FULL:
            count = requested_count if self.fixed_count is None else self.fixed_count
            return [(count, FULL, (0.0,))]
        if strip_mode != PARTIAL:
            raise ValueError(f"Unsupported strip mode: {strip_mode}")
        if count_override is not None:
            return [(requested_count, PARTIAL, self.partial_offsets)]
        counts = [
            count
            for count in self.auto_counts
            if count < fmt.default_count or self.include_default_in_partial_auto
        ]
        return [(count, PARTIAL, self.partial_offsets) for count in counts] or [
            (1, PARTIAL, self.partial_offsets)
        ]


@dataclass(frozen=True)
class OuterPolicy:
    base_outer: bool = True
    content_floating: bool = False
    edge_anchor: str = "off"
    separator_first: str = "off"
    separator_geometry: str = "off"
    dark_band: str = "off"
    retries: tuple[str, ...] = ()


@dataclass(frozen=True)
class SeparatorPolicy:
    gate_mode: str
    hard_required_all_gaps: bool
    wide_retry: bool
    wide_retry_max_width_ratio: float
    hard_methods: tuple[str, ...] = ("detected", "edge_pair", "enhanced_detected", "wide_separator")
    model_methods: tuple[str, ...] = ("grid", "equal", "content")


@dataclass(frozen=True)
class ContentPolicy:
    can_auto_pass_alone: bool
    required_support_for_auto: str = "ok"
    validates_candidates: bool = True


@dataclass(frozen=True)
class GatePolicy:
    ordered_gates: tuple[str, ...]
    hard_review_reasons_block_auto: bool = True
    partial_safe_extra_frames: bool = False
    partial_requires_wide_like_gaps: int = 0
    partial_checks_leading_content: bool = False
    partial_checks_frame_content: bool = False


@dataclass(frozen=True)
class ScoringPolicy:
    confidence_threshold_default: float = 0.85
    no_auto_cap_full: float = 0.84
    no_auto_cap_partial: float = 0.82
    competition_top_n: int = 8
    competition_close_margin: float = 0.04


@dataclass(frozen=True)
class SelectionPolicy:
    top_n: int = 8
    close_margin: float = 0.04
    confidence_cap: float = 0.84
    half_content_mismatch_review: bool = False


@dataclass(frozen=True)
class PostprocessPolicy:
    align_outer_to_content: bool = True
    retry_uncertain_outer: bool = True
    apply_output_bleed: bool = True
    apply_approved_geometry_adjustment: bool = True


@dataclass(frozen=True)
class OutputPolicy:
    detection_long_axis_bleed: int = 0
    detection_short_axis_bleed: int = 0
    output_long_axis_bleed_default: int = 20
    output_short_axis_bleed_default: int = 10
    overlap_risk_long_axis_bleed: int = 50


@dataclass(frozen=True)
class DiagnosticsPolicy:
    attach_read_only_only_when_requested: bool = True
    debug_panels: tuple[str, ...] = (
        "original_gray",
        "debug_boxes",
        "separator_evidence",
    )


@dataclass(frozen=True)
class DetectionPolicy:
    policy_id: str
    format_id: str
    strip_mode: str
    family: str
    role: str
    tuning: FormatTuning
    counts: CountPolicy
    outer: OuterPolicy
    separator: SeparatorPolicy
    content: ContentPolicy
    frame_fit: FrameFitPolicy
    gates: GatePolicy
    scoring: ScoringPolicy
    candidate_selection: SelectionPolicy
    postprocess: PostprocessPolicy
    output: OutputPolicy = field(default_factory=OutputPolicy)
    diagnostics: DiagnosticsPolicy = field(default_factory=DiagnosticsPolicy)
    notes: tuple[str, ...] = ()

    def report_detail(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "format": self.format_id,
            "strip_mode": self.strip_mode,
            "family": self.family,
            "role": self.role,
            "outer": {
                "content_floating": self.outer.content_floating,
                "edge_anchor": self.outer.edge_anchor,
                "separator_first": self.outer.separator_first,
                "separator_geometry": self.outer.separator_geometry,
                "dark_band": self.outer.dark_band,
                "retries": list(self.outer.retries),
            },
            "separator": {
                "gate_mode": self.separator.gate_mode,
                "hard_required_all_gaps": self.separator.hard_required_all_gaps,
                "wide_retry": self.separator.wide_retry,
                "wide_retry_max_width_ratio": self.separator.wide_retry_max_width_ratio,
            },
            "content": {
                "can_auto_pass_alone": self.content.can_auto_pass_alone,
                "required_support_for_auto": self.content.required_support_for_auto,
            },
            "gates": list(self.gates.ordered_gates),
            "selection": {
                "top_n": self.candidate_selection.top_n,
                "close_margin": self.candidate_selection.close_margin,
                "confidence_cap": self.candidate_selection.confidence_cap,
                "half_content_mismatch_review": self.candidate_selection.half_content_mismatch_review,
            },
            "postprocess": {
                "align_outer_to_content": self.postprocess.align_outer_to_content,
                "retry_uncertain_outer": self.postprocess.retry_uncertain_outer,
                "apply_output_bleed": self.postprocess.apply_output_bleed,
                "apply_approved_geometry_adjustment": self.postprocess.apply_approved_geometry_adjustment,
            },
            "notes": list(self.notes),
        }
