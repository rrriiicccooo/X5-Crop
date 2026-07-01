from __future__ import annotations

from importlib import import_module
from functools import lru_cache

from ..common import FORMATS, FORMAT_CHOICES, STRIP_CHOICES, format_tuning
from ..geometry import frame_fit_policy
from .base import (
    FULL,
    PARTIAL,
    ContentPolicy,
    CountPolicy,
    DetectionPolicy,
    GatePolicy,
    OuterPolicy,
    PostprocessPolicy,
    ScoringPolicy,
    SelectionPolicy,
    SeparatorPolicy,
)

FORMAT_POLICY_MODULES = {
    "135": "format_135",
    "135-dual": "format_135_dual",
    "half": "format_half",
    "xpan": "format_xpan",
    "120-645": "format_120_645",
    "120-66": "format_120_66",
    "120-67": "format_120_67",
}


def _format_policy_meta(format_id: str, strip_mode: str) -> tuple[str, tuple[str, ...]]:
    module_name = FORMAT_POLICY_MODULES.get(format_id)
    if module_name is None:
        return "format_mode_policy", ()
    module = import_module(f"{__package__}.{module_name}")
    roles = getattr(module, "POLICY_ROLES", {})
    notes = getattr(module, "POLICY_NOTES", {})
    return (
        str(roles.get(strip_mode, "format_mode_policy")),
        tuple(notes.get(strip_mode, ())),
    )


def _count_policy(format_id: str, strip_mode: str, *, include_default_partial: bool) -> CountPolicy:
    fmt = FORMATS[format_id]
    tuning = format_tuning(format_id)
    if strip_mode == FULL:
        return CountPolicy(fixed_count=None, auto_counts=(fmt.default_count,))
    return CountPolicy(
        fixed_count=None,
        auto_counts=tuple(reversed(fmt.allowed_counts)),
        partial_offsets=tuning.partial_offsets,
        include_default_in_partial_auto=include_default_partial,
    )


def _separator_policy(format_id: str, strip_mode: str) -> SeparatorPolicy:
    tuning = format_tuning(format_id)
    return SeparatorPolicy(
        gate_mode=tuning.separator_gate_mode,
        hard_required_all_gaps=bool(tuning.separator_hard_required_all_gaps),
        wide_retry=bool(
            (strip_mode == FULL and tuning.wide_gap_retry_enabled)
            or (strip_mode == PARTIAL and tuning.wide_gap_retry_partial_enabled)
        ),
        wide_retry_max_width_ratio=float(tuning.wide_gap_retry_max_width_ratio),
    )


def _outer_policy(format_id: str, strip_mode: str, *, dark_band: str = "off") -> OuterPolicy:
    tuning = format_tuning(format_id)
    is_full = strip_mode == FULL
    return OuterPolicy(
        content_floating=bool(tuning.floating_outer_full_enabled if is_full else tuning.floating_outer_partial_enabled),
        edge_anchor=(
            tuning.long_axis_edge_anchor_outer_mode
            if is_full and tuning.long_axis_edge_anchor_outer_enabled
            else tuning.long_axis_edge_anchor_partial_mode
            if (not is_full and tuning.long_axis_edge_anchor_partial_enabled)
            else "off"
        ),
        separator_first=(
            tuning.separator_first_outer_mode
            if is_full and tuning.separator_first_outer_enabled
            else tuning.separator_first_partial_mode
            if (not is_full and tuning.separator_first_partial_enabled)
            else "off"
        ),
        separator_geometry=(
            tuning.separator_geometry_outer_full_mode
            if is_full
            else tuning.separator_geometry_outer_partial_mode
        ),
        dark_band=dark_band,
        retries=tuple(
            name
            for name, enabled in (
                ("content_aligned_retry", tuning.outer_retry_enabled),
                ("format_geometry_retry", tuning.format_geometry_outer_retry_enabled),
                ("short_axis_retry", tuning.short_axis_aspect_retry_enabled),
            )
            if enabled
        ),
    )


def _gate_policy(format_id: str, strip_mode: str) -> GatePolicy:
    tuning = format_tuning(format_id)
    partial_safe = strip_mode == PARTIAL and bool(tuning.partial_safe_extra_frames_enabled)
    return GatePolicy(
        ordered_gates=(
            "confidence_floor_gate",
            "separator_gate",
            "content_gate",
            "geometry_gate",
            "mode_specific_gate",
            "hard_review_reason_gate",
            "auto_pass_gate",
            "postprocess_gate",
        ),
        partial_safe_extra_frames=partial_safe,
        partial_requires_wide_like_gaps=(
            int(tuning.partial_safe_extra_frames_min_wide_like_gaps) if partial_safe else 0
        ),
        partial_checks_leading_content=bool(
            partial_safe and tuning.partial_safe_extra_frames_leading_content_check
        ),
        partial_checks_frame_content=bool(
            partial_safe and tuning.partial_safe_extra_frames_frame_content_check
        ),
    )


def _scoring_policy(format_id: str) -> ScoringPolicy:
    tuning = format_tuning(format_id)
    return ScoringPolicy(
        no_auto_cap_full=float(tuning.calibrate_full_no_auto_cap),
        no_auto_cap_partial=float(tuning.calibrate_partial_no_auto_cap),
        competition_top_n=int(tuning.candidate_competition_top_n),
        competition_close_margin=float(tuning.candidate_competition_close_margin),
    )


def _selection_policy(format_id: str) -> SelectionPolicy:
    tuning = format_tuning(format_id)
    return SelectionPolicy(
        top_n=int(tuning.candidate_competition_top_n),
        close_margin=float(tuning.candidate_competition_close_margin),
        confidence_cap=float(tuning.candidate_competition_confidence_cap),
        half_content_mismatch_review=(format_id == "half"),
    )


def _postprocess_policy(format_id: str) -> PostprocessPolicy:
    tuning = format_tuning(format_id)
    return PostprocessPolicy(
        align_outer_to_content=True,
        retry_uncertain_outer=bool(tuning.outer_retry_enabled),
        apply_output_bleed=True,
        apply_approved_geometry_adjustment=True,
    )


def build_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    if format_id not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format policy: {format_id}")
    if strip_mode not in STRIP_CHOICES:
        raise ValueError(f"Unsupported strip policy: {strip_mode}")
    fmt = FORMATS[format_id]
    tuning = format_tuning(format_id)
    include_default = bool(tuning.partial_auto_include_default_count)
    dark_band = "conditional" if format_id == "120-66" else "off"
    role, notes = _format_policy_meta(format_id, strip_mode)
    return DetectionPolicy(
        policy_id=f"{format_id.replace('-', '_')}_{strip_mode}",
        format_id=format_id,
        strip_mode=strip_mode,
        family=fmt.family,
        role=role,
        tuning=tuning,
        counts=_count_policy(format_id, strip_mode, include_default_partial=include_default),
        outer=_outer_policy(format_id, strip_mode, dark_band=dark_band),
        separator=_separator_policy(format_id, strip_mode),
        content=ContentPolicy(can_auto_pass_alone=False),
        frame_fit=frame_fit_policy(fmt, strip_mode),
        gates=_gate_policy(format_id, strip_mode),
        scoring=_scoring_policy(format_id),
        candidate_selection=_selection_policy(format_id),
        postprocess=_postprocess_policy(format_id),
        notes=notes,
    )


@lru_cache(maxsize=None)
def get_detection_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    return build_policy(format_id, strip_mode)


def policy_report_detail(format_id: str, strip_mode: str) -> dict:
    return get_detection_policy(format_id, strip_mode).report_detail()
