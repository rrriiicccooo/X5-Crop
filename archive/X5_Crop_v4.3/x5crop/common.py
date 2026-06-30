#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X5_Crop.py

Clean single-strip cropper for Hasselblad X5 film-holder TIFF scans.

Design goals:
- Single-strip scans only: horizontal or vertical.
- Automatic high-confidence crop for common 135 and 120 scans.
- half-frame and XPAN remain available, but must be selected manually.
- Difficult scans are marked for review instead of being forced through.
- Debug analysis includes separator evidence and content evidence.
- TIFF pixel data and key TIFF metadata are preserved as much as practical.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import csv
import json
import math
import os
import shutil
import sys
import traceback
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
from PIL import Image, ImageDraw
import tifffile


VERSION = "4.3"
SCRIPT_NAME = "X5_Crop.py"
TIFF_SUFFIXES = {".tif", ".tiff"}
REPORT_RECORD_CACHE: dict[Path, tuple[int, int, list[dict[str, Any]]]] = {}
SEPARATOR_FIRST_OUTER_MODES = {"off", "fallback", "always"}


def configure_text_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except Exception:
            pass


configure_text_output()


@dataclass(frozen=True)
class FilmFormat:
    name: str
    default_count: int
    allowed_counts: tuple[int, ...]
    family: str


FORMATS: dict[str, FilmFormat] = {
    "135": FilmFormat("135", 6, tuple(range(1, 7)), "35mm"),
    "135-dual": FilmFormat("135-dual", 12, (12,), "35mm"),
    "half": FilmFormat("half", 12, tuple(range(1, 13)), "35mm"),
    "xpan": FilmFormat("xpan", 3, (1, 2, 3), "35mm"),
    "120-645": FilmFormat("120-645", 4, (1, 2, 3, 4), "120"),
    "120-66": FilmFormat("120-66", 3, (1, 2, 3), "120"),
    "120-67": FilmFormat("120-67", 3, (1, 2, 3), "120"),
}


FORMAT_CHOICES = tuple(FORMATS.keys())
LAYOUT_CHOICES = ("auto", "horizontal", "vertical")
STRIP_CHOICES = ("full", "partial")
DESKEW_CHOICES = ("off", "auto")
ANALYSIS_CHOICES = ("off", "auto", "always")
COMPRESSION_CHOICES = ("none", "same")
CONTENT_ASPECTS_HORIZONTAL = {
    "135": 3.0 / 2.0,
    "135-dual": 3.0 / 2.0,
    "half": 2.0 / 3.0,
    "xpan": 65.0 / 24.0,
    "120-66": 1.0,
    "120-645": 3.0 / 4.0,
    "120-67": 5.0 / 4.0,
}
PARTIAL_FULL_COMPETE_MIN_CONFIDENCE = 0.78
CONTENT_ONLY_PARTIAL_PASS_MIN_CONFIDENCE = 0.92
HARD_GAP_METHODS = {"detected", "edge-pair", "enhanced-detected", "wide-separator"}
MODEL_GAP_METHODS = {"grid", "equal", "content"}


CONTENT_AMBIGUITY_REASONS = {
    "content_run_count_mismatch",
    "content_grid_fallback",
    "content_runs_incomplete",
    "content_aspect_uncertain",
    "content_coverage_weak",
}

HARD_REVIEW_REASONS = {
    "content_aspect_conflict",
    "content_aspect_uncertain",
    "content_coverage_weak",
    "outer_box_too_large",
    "outer_box_uncertain",
    "unstable_frame_width",
}


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def valid(self) -> bool:
        return self.right > self.left and self.bottom > self.top

    def clamp(self, width: int, height: int) -> "Box":
        return Box(
            max(0, min(width, self.left)),
            max(0, min(height, self.top)),
            max(0, min(width, self.right)),
            max(0, min(height, self.bottom)),
        )

    def expand(self, bleed_x: int, bleed_y: int, width: int, height: int) -> "Box":
        return Box(
            self.left - bleed_x,
            self.top - bleed_y,
            self.right + bleed_x,
            self.bottom + bleed_y,
        ).clamp(width, height)


def clamp_int(value: float, lower: int, upper: int) -> int:
    return int(max(lower, min(upper, int(round(value)))))


def clamp_float(value: float, lower: float, upper: float) -> float:
    return float(max(lower, min(upper, float(value))))


@dataclass
class Gap:
    index: int
    center: float
    score: float
    method: str
    start: Optional[float] = None
    end: Optional[float] = None
    lane_box: Optional[dict[str, int]] = None

    @property
    def width(self) -> float:
        if self.start is None or self.end is None:
            return 0.0
        return max(0.0, float(self.end) - float(self.start))


@dataclass(frozen=True)
class EdgePairParams:
    window_ratio: float
    min_gutter_ratio: float
    max_gutter_ratio: float
    min_strength: float
    min_background: float
    min_quality_for_model_gap: float
    min_quality_for_hard_gap: float
    hard_gap_quality_ratio: float
    max_hard_shift_ratio: float


@dataclass(frozen=True)
class OuterMaskProfile:
    name: str
    low: Optional[int]
    high: Optional[int]
    min_row_fraction: float = 0.012
    min_col_fraction: float = 0.012


@dataclass(frozen=True)
class FormatTuning:
    name: str
    outer_white_x_width_multiplier: float = 1.80
    outer_white_x_extra_ratio: float = 0.060
    outer_candidate_max_area: float = 0.94
    outer_mask_expand_ratio: float = 0.002
    outer_mask_profiles: tuple[OuterMaskProfile, ...] = (
        OuterMaskProfile("mask_not_white_246", None, 246),
        OuterMaskProfile("mask_not_white_225", None, 225),
        OuterMaskProfile("mask_mid_8_246", 8, 246),
    )
    outer_min_width_ratio: float = 0.10
    outer_min_height_ratio: float = 0.10
    outer_min_width_px: int = 20
    outer_min_height_px: int = 20
    outer_bw_not_white_threshold: int = 246
    outer_bw_dark_threshold: int = 210
    outer_bw_min_fraction: float = 0.015
    outer_bw_min_width_ratio: float = 0.10
    outer_bw_min_height_ratio: float = 0.10
    outer_bw_margin_ratio: float = 0.002
    outer_bw_margin_min: int = 2
    outer_white_border_ratio: float = 0.985
    outer_white_run_ratio: float = 0.003
    outer_white_run_min: int = 2
    outer_white_run_max: int = 80
    outer_white_dark_threshold: int = 30
    outer_white_light_threshold: int = 225
    outer_white_min_width_ratio: float = 0.10
    outer_white_min_height_ratio: float = 0.10
    outer_white_margin_ratio: float = 0.002
    outer_white_margin_min: int = 2
    content_profile_smooth_ratio: float = 0.010
    content_profile_min_run_ratio: float = 0.20
    content_profile_threshold_min: float = 0.035
    content_profile_threshold_max: float = 0.40
    content_profile_p35_weight: float = 0.38
    content_profile_p65_multiplier: float = 0.82
    content_mask_p55_weight: float = 0.34
    content_mask_p75_multiplier: float = 0.78
    content_mask_min: float = 0.045
    content_mask_max: float = 0.45
    content_mask_percentiles: tuple[float, float, float] = (55.0, 75.0, 92.0)
    content_bbox_min_fraction: float = 0.008
    content_outer_min_width_ratio: float = 0.08
    content_outer_min_height_ratio: float = 0.08
    content_outer_min_width_px: int = 60
    content_outer_min_height_px: int = 30
    content_expected_width_min_px: float = 8.0
    content_candidate_coverage_weight: float = 0.38
    content_candidate_mean_weight: float = 0.30
    content_candidate_run_weight: float = 0.22
    content_candidate_aspect_weight: float = 0.10
    content_conf_coverage_norm: float = 0.22
    content_conf_mean_norm: float = 0.16
    content_conf_aspect_norm: float = 0.18
    content_weak_coverage: float = 0.14
    content_aspect_uncertain: float = 0.18
    content_evidence_percentile: float = 70.0
    content_evidence_threshold_multiplier: float = 0.70
    content_evidence_threshold_min: float = 0.08
    content_evidence_threshold_max: float = 0.45
    content_evidence_aspect_ok_max: float = 0.22
    content_evidence_present_mean_min: float = 0.075
    content_evidence_present_coverage_min: float = 0.18
    content_grid_fallback_cap: float = 0.82
    content_run_mismatch_cap: float = 0.84
    content_runs_incomplete_cap: float = 0.84
    content_weak_coverage_cap: float = 0.82
    content_aspect_uncertain_cap: float = 0.82
    post_content_aspect_conflict_cap: float = 0.82
    post_content_low_confidence_cap: float = 0.84
    post_outer_mismatch_cap: float = 0.84
    post_lucky_pass_risk_cap: float = 0.84
    gap_radius_ratio: float = 0.16
    gap_radius_min: int = 6
    gap_radius_max: int = 900
    gap_max_width_ratio: float = 0.045
    gap_max_width_min: int = 2
    gap_max_width_max: int = 420
    wide_gap_retry_enabled: bool = True
    wide_gap_retry_max_width_ratio: float = 0.060
    wide_gap_min_mean: float = 0.95
    wide_gap_min_prominence: float = 0.02
    wide_gap_confidence_cap: float = 0.995
    gap_min_width_ratio: float = 0.001
    gap_min_width_min: int = 1
    gap_min_width_max: int = 12
    gap_guard_ratio: float = 0.035
    gap_guard_min: int = 3
    gap_guard_max: int = 220
    gap_min_score: float = 0.22
    gap_peak_multiplier: float = 0.90
    gap_band_multiplier: float = 0.62
    constrain_full_shift_ratio: float = 0.045
    constrain_partial_shift_ratio: float = 0.12
    constrain_shift_min: float = 20.0
    constrain_shift_max: float = 520.0
    nearby_window_ratio: float = 0.040
    nearby_window_min: int = 16
    nearby_window_max: int = 320
    nearby_exclude_ratio: float = 0.012
    nearby_exclude_min: int = 8
    nearby_exclude_max: int = 120
    nearby_max_width_ratio: float = 0.070
    nearby_max_width_min: int = 2
    nearby_max_width_max: int = 520
    nearby_distance_ratio: float = 0.040
    nearby_score_add: float = 0.10
    nearby_score_multiplier: float = 1.22
    nearby_detail_score_add: float = 0.08
    nearby_detail_score_multiplier: float = 1.18
    nearby_local_gain_ratio: float = 0.006
    nearby_local_gain_min: float = 8.0
    nearby_local_gain_max: float = 40.0
    nearby_active_correction: bool = True
    robust_reliable_min_score: float = 0.28
    robust_min_reliable: int = 2
    robust_pitch_min_ratio: float = 0.70
    robust_pitch_max_ratio: float = 1.30
    robust_full_tolerance_ratio: float = 0.040
    robust_partial_tolerance_ratio: float = 0.090
    robust_tolerance_min: float = 4.0
    robust_tolerance_max: float = 520.0
    robust_reject_residual_ratio: float = 0.045
    robust_full_shift_ratio: float = 0.035
    robust_partial_shift_ratio: float = 0.10
    robust_shift_min: float = 20.0
    robust_shift_max: float = 520.0
    robust_hard_keep_ratio: float = 0.025
    robust_hard_keep_min: float = 3.0
    robust_hard_keep_max: float = 180.0
    robust_hard_protect_ratio: float = 0.006
    robust_hard_protect_min: float = 12.0
    robust_hard_protect_max: float = 40.0
    enhanced_max_width_ratio: float = 0.040
    enhanced_max_width_min: float = 3.0
    enhanced_max_width_max: float = 420.0
    enhanced_shift_ratio: float = 0.035
    enhanced_shift_min: float = 4.0
    enhanced_shift_max: float = 420.0
    enhanced_auto_low_score: float = 0.34
    separator_profile_top_ratio: float = 0.10
    separator_profile_bottom_ratio: float = 0.90
    separator_profile_segments: int = 5
    separator_profile_dark_threshold: int = 30
    separator_profile_light_threshold: int = 225
    separator_profile_consistency_percentile: float = 20.0
    separator_profile_average_weight: float = 0.35
    separator_profile_consistency_weight: float = 0.65
    separator_profile_std_norm: float = 70.0
    separator_profile_dark_soft_mean: float = 54.0
    separator_profile_light_soft_mean: float = 225.0
    separator_profile_light_soft_span: float = 30.0
    separator_profile_soft_weight: float = 0.50
    separator_profile_uniform_base: float = 0.90
    separator_profile_uniform_weight: float = 0.10
    separator_profile_gradient_weight: float = 0.25
    separator_profile_smooth_ratio: float = 0.0015
    separator_profile_smooth_min: int = 3
    edge_refine_top_ratio: float = 0.12
    edge_refine_bottom_ratio: float = 0.88
    edge_refine_mean_weight: float = 0.65
    edge_refine_p75_weight: float = 0.35
    edge_refine_smooth_ratio: float = 0.0008
    edge_refine_smooth_min: int = 3
    edge_refine_high_percentile: float = 99.2
    edge_refine_background_dark_threshold: int = 30
    edge_refine_background_light_threshold: int = 225
    edge_refine_y_edge_weight: float = 0.50
    edge_refine_activity_percentile: float = 95.0
    hard_trust_guard_ratio: float = 0.020
    hard_trust_guard_min: int = 4
    hard_trust_guard_max: int = 80
    hard_trust_narrow_ratio: float = 0.020
    hard_trust_narrow_min: float = 3.0
    hard_trust_narrow_max: float = 140.0
    hard_trust_model_delta_ratio: float = 0.040
    hard_trust_geometry_width_ratio: float = 0.018
    hard_trust_strong_min_score: float = 0.90
    hard_trust_strong_width_min: float = 0.018
    hard_trust_strong_width_max: float = 0.065
    hard_trust_narrow_ok_score: float = 0.70
    hard_trust_narrow_ok_width_min: float = 0.006
    hard_trust_narrow_ok_width_max: float = 0.018
    hard_trust_model_conflict_score: float = 1.05
    hard_trust_core_content_threshold: int = 235
    hard_trust_core_dark_threshold: int = 55
    hard_trust_dark_mean_max: float = 45.0
    hard_trust_dark_fraction_min: float = 0.45
    hard_trust_dark_activity_max: float = 0.18
    hard_trust_strong_core_content_max: float = 0.08
    hard_trust_weak_mean_min: float = 70.0
    hard_trust_weak_content_min: float = 0.10
    hard_trust_frame_border_width_ratio: float = 0.010
    hard_trust_continuity_min: float = 0.12
    hard_trust_activity_min: float = 0.030
    diagnostic_overlap_mean_min: float = 55.0
    diagnostic_overlap_weak_continuity: float = 0.16
    diagnostic_overlap_weak_activity: float = 0.04
    diagnostic_overlap_medium_continuity: float = 0.35
    diagnostic_overlap_medium_activity: float = 0.08
    diagnostic_overlap_strong_continuity: float = 0.70
    diagnostic_overlap_strong_activity: float = 0.12
    debug_gap_overlap_tolerance_ratio: float = 0.012
    debug_gap_overlap_tolerance_min: float = 4.0
    debug_gap_overlap_tolerance_max: float = 80.0
    debug_gap_hard_line_width: int = 2
    debug_gap_model_line_width: int = 2
    debug_gap_diagnostic_line_width: int = 3
    outer_align_white_edge_long_ratio: float = 0.0190
    outer_align_white_edge_long_min: int = 90
    outer_align_white_edge_long_max: int = 180
    outer_align_long_gate_ratio: float = 0.0340
    outer_align_long_gate_min: int = 160
    outer_align_long_gate_max: int = 320
    outer_align_short_gate_ratio: float = 0.0060
    outer_align_short_gate_min: int = 28
    outer_align_short_gate_max: int = 80
    outer_align_long_excess_ratio: float = 0.050
    outer_align_long_gate_excess_ratio: float = 0.035
    outer_align_short_excess_ratio: float = 0.035
    outer_align_short_requires_hard_anchors: bool = False
    outer_align_short_content_height_max: float = 1.0
    outer_align_content_width_min: float = 0.985
    outer_align_edge_short_ratio: float = 0.015
    outer_align_edge_dark_max: float = 0.02
    outer_align_border_band_ratio: float = 0.018
    outer_align_margin_x_ratio: float = 0.0030
    outer_align_margin_x_min: int = 15
    outer_align_margin_x_max: int = 30
    outer_align_margin_y_ratio: float = 0.0030
    outer_align_margin_y_min: int = 10
    outer_align_margin_y_max: int = 20
    outer_align_long_margin_ratio: float = 0.012
    outer_align_long_margin_cap_ratio: float = 0.0170
    outer_align_long_margin_cap_min: int = 80
    outer_align_long_margin_cap_max: int = 160
    outer_align_short_margin_ratio: float = 0.010
    outer_align_short_margin_cap_ratio: float = 0.010
    outer_align_short_margin_cap_min: int = 40
    outer_align_short_margin_cap_max: int = 80
    score_width_cv_norm: float = 0.030
    score_gap_weight: float = 0.40
    score_width_weight: float = 0.30
    score_outer_weight: float = 0.20
    score_contrast_weight: float = 0.10
    score_outer_min_area: float = 0.35
    score_outer_max_area: float = 0.995
    score_outer_too_large: float = 0.94
    score_outer_uncertain_confidence: float = 0.45
    score_contrast_min: float = 35.0
    score_contrast_floor: float = 0.35
    score_full_width_cv: float = 0.040
    score_geometry_floor_tight_cv: float = 0.006
    score_geometry_floor_high: float = 0.92
    score_geometry_floor_low: float = 0.88
    score_unstable_width_cv: float = 0.030
    score_full_outer_min_area: float = 0.40
    score_135_min_hard_gaps: int = 2
    score_135_max_equal_min: int = 2
    score_135_low_hard_cap: float = 0.82
    score_135_mostly_equal_cap: float = 0.84
    score_partial_one_cap: float = 0.78
    score_partial_two_35mm_cap: float = 0.82
    score_partial_general_cap: float = 0.84
    score_outer_too_large_cap: float = 0.82
    score_low_confidence_floor: float = 0.85
    score_allow_135_full_detected_geometry: bool = True
    score_allow_half_geometry: bool = True
    calibrate_hard_full_confidence_floor: float = 0.0
    separator_model_grid_credit: float = 0.35
    separator_model_equal_credit: float = 0.12
    separator_gate_mode: str = "135"
    separator_135_needed_hard_max: int = 2
    separator_135_max_equal_min: int = 2
    separator_half_allow_geometry_support: bool = True
    separator_half_wide_geometry_min_hard_ratio: float = 0.60
    separator_half_wide_geometry_min_joint_score: float = 0.78
    separator_half_stable_grid_min_hard_ratio: float = 0.35
    separator_half_stable_grid_min_joint_score: float = 0.65
    separator_120_require_all_hard: bool = True
    separator_120_edge_pair_min_score_without_wide: float = 0.0
    separator_120_edge_pair_min_score_with_wide: float = 0.0
    separator_120_min_wide_gaps_for_auto: int = 0
    leading_grid_failure_enabled: bool = True
    leading_grid_failure_min_count: int = 5
    leading_grid_failure_leading_count: int = 3
    leading_grid_failure_low_score: float = 0.35
    leading_grid_failure_very_low_score: float = 0.12
    leading_grid_failure_very_low_count: int = 2
    leading_grid_failure_max_hard: int = 2
    geometry_width_cv_norm: float = 0.040
    content_support_aspect_norm: float = 0.22
    content_support_coverage_weight: float = 0.42
    content_support_mean_weight: float = 0.40
    content_support_aspect_weight: float = 0.18
    content_support_gate_ok: float = 1.0
    content_support_gate_weak: float = 0.72
    content_support_gate_low_content: float = 0.58
    content_support_gate_aspect_conflict: float = 0.35
    content_support_gate_unknown: float = 0.50
    geometry_support_width_weight: float = 0.34
    geometry_support_outer_weight: float = 0.24
    geometry_support_aspect_weight: float = 0.26
    geometry_support_count_weight: float = 0.16
    geometry_support_outer_uncertain: float = 0.55
    geometry_support_no_aspect_score: float = 0.80
    separator_support_hard_weight: float = 0.78
    separator_support_model_weight: float = 0.22
    calibrate_geometry_weight: float = 0.34
    calibrate_content_weight: float = 0.33
    calibrate_separator_weight: float = 0.33
    calibrate_separator_source_bias: float = 0.03
    calibrate_partial_no_auto_cap: float = 0.82
    calibrate_full_no_auto_cap: float = 0.84
    candidate_competition_top_n: int = 8
    candidate_competition_close_margin: float = 0.04
    candidate_competition_confidence_cap: float = 0.84
    grid_outer_refine_shift_ratio: float = 0.080
    grid_outer_refine_shift_min: int = 8
    grid_outer_refine_shift_max: int = 420
    grid_outer_refine_max_width_change: float = 0.12
    deskew_min_outer_width: int = 100
    deskew_outer_dark_threshold: int = 245
    deskew_outer_min_fraction: float = 0.01
    deskew_sample_width_px: int = 350
    deskew_min_samples: int = 6
    deskew_max_samples: int = 24
    deskew_min_col_content: int = 10
    deskew_min_col_content_ratio: float = 0.05
    deskew_slope_delta_max: float = 0.006
    deskew_residual_min: float = 3.0
    deskew_residual_height_ratio: float = 0.003
    deskew_auto_quality_ok: float = 8.0
    deskew_enhanced_quality_gain: float = 3.0
    deskew_fit_min_points: int = 4
    deskew_fit_tolerance_min: float = 2.0
    deskew_fit_tolerance_multiplier: float = 3.0
    deskew_span_skip_ratio: float = 0.0005
    deskew_span_skip_min: float = 3.0
    deskew_span_skip_max: float = 12.0
    partial_offsets: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
    partial_edge_hint_window_ratio: float = 0.18
    partial_edge_hint_window_min: int = 8
    partial_edge_hint_window_max: int = 900
    partial_content_min_count_35mm: int = 3
    partial_content_min_count_small: int = 2
    content_only_partial_enabled: bool = True
    lucky_pass_risk_enabled: bool = True
    lucky_model_gap_support_min: int = 2
    lucky_model_gap_support_weight: float = 0.24
    lucky_minor_model_gap_support_weight: float = 0.08
    lucky_limited_strong_hard_max: int = 2
    lucky_limited_strong_hard_weight: float = 0.20
    lucky_very_limited_strong_hard_max: int = 1
    lucky_very_limited_strong_hard_weight: float = 0.10
    lucky_suspicious_hard_weight: float = 0.20
    lucky_strong_overlap_weight: float = 0.20
    lucky_combo_weight: float = 0.12
    lucky_unstable_width_cv: float = 0.006
    lucky_unstable_width_weight: float = 0.16
    lucky_mild_width_cv: float = 0.003
    lucky_mild_width_weight: float = 0.08
    lucky_strong_hard_credit_min: int = 3
    lucky_strong_hard_credit: float = -0.15
    lucky_stable_width_cv: float = 0.002
    lucky_stable_model_gap_min: int = 3
    lucky_stable_geometry_credit: float = -0.35
    lucky_risk_threshold: float = 0.80
    approved_polish_long_limit_ratio: float = 0.018
    approved_polish_long_limit_min: int = 20
    approved_polish_long_limit_max: int = 60
    approved_polish_min_ext_ratio: float = 0.0100
    approved_polish_min_ext_min: int = 50
    approved_polish_min_ext_max: int = 120
    outer_retry_enabled: bool = True
    short_axis_aspect_retry_enabled: bool = False
    short_axis_aspect_retry_min_error: float = 0.24
    short_axis_aspect_retry_target_aspect: float = 1.0
    short_axis_aspect_retry_margin_ratio: float = 0.008
    short_axis_aspect_retry_margin_min: int = 12
    short_axis_aspect_retry_margin_max: int = 80
    format_geometry_outer_retry_enabled: bool = True
    format_geometry_outer_retry_ratio_tolerance: float = 0.025
    format_geometry_outer_retry_min_shrink_ratio: float = 0.003
    format_geometry_outer_retry_max_shrink_ratio: float = 0.120
    format_geometry_outer_retry_content_margin_ratio: float = 0.010
    format_geometry_outer_retry_content_margin_min: int = 12
    format_geometry_outer_retry_content_margin_max: int = 80
    floating_full_outer_enabled: bool = False
    floating_full_outer_ratio_extras: tuple[float, ...] = (0.06, 0.10)
    floating_full_outer_content_threshold: int = 225
    floating_full_outer_content_margin_ratio: float = 0.012
    floating_full_outer_content_margin_min: int = 12
    floating_full_outer_content_margin_max: int = 80
    floating_full_outer_min_width_ratio: float = 0.30
    floating_full_outer_max_candidates: int = 12
    long_axis_edge_anchor_outer_enabled: bool = False
    long_axis_edge_anchor_outer_mode: str = "fallback"
    long_axis_edge_anchor_ratio_extras: tuple[float, ...] = (0.06, 0.10)
    long_axis_edge_anchor_content_threshold: int = 225
    long_axis_edge_anchor_content_margin_ratio: float = 0.012
    long_axis_edge_anchor_content_margin_min: int = 12
    long_axis_edge_anchor_content_margin_max: int = 80
    long_axis_edge_anchor_min_width_ratio: float = 0.30
    long_axis_edge_anchor_max_candidates: int = 8
    separator_first_outer_enabled: bool = False
    separator_first_outer_mode: str = "fallback"
    separator_first_outer_min_score: float = 0.58
    separator_first_outer_band_score: float = 0.36
    separator_first_outer_min_width_ratio: float = 0.006
    separator_first_outer_max_width_ratio: float = 0.120
    separator_first_outer_spacing_min_ratio: float = 0.82
    separator_first_outer_spacing_max_ratio: float = 1.24
    separator_first_outer_frame_error_max: float = 0.18
    separator_first_outer_edge_margin_ratio: float = 0.18
    separator_first_outer_gap_max_width_ratio: float = 0.095
    separator_first_outer_source_candidates: int = 2
    separator_first_outer_band_candidates: int = 10
    separator_first_outer_pair_candidates: int = 4
    separator_first_outer_max_candidates: int = 12


def base_120_tuning(format_name: str, **overrides: Any) -> FormatTuning:
    params: dict[str, Any] = {
        "score_full_width_cv": 0.012,
        "content_profile_min_run_ratio": 0.18,
        "separator_model_grid_credit": 0.18,
        "separator_model_equal_credit": 0.04,
        "separator_gate_mode": "hard_required",
        "nearby_score_multiplier": 1.28,
        "calibrate_separator_weight": 0.36,
        "calibrate_geometry_weight": 0.32,
        "calibrate_content_weight": 0.32,
        "wide_gap_retry_enabled": False,
        "nearby_active_correction": False,
        "lucky_pass_risk_enabled": False,
        "leading_grid_failure_enabled": False,
    }
    params.update(overrides)
    return FormatTuning(format_name, **params)


def format_tuning(format_name: str) -> FormatTuning:
    if format_name == "half":
        return FormatTuning(
            "half",
            score_full_width_cv=0.008,
            content_profile_min_run_ratio=0.16,
            separator_model_grid_credit=0.25,
            separator_model_equal_credit=0.08,
            separator_gate_mode="half",
            wide_gap_retry_enabled=True,
            wide_gap_retry_max_width_ratio=0.100,
            nearby_active_correction=False,
            lucky_pass_risk_enabled=False,
            leading_grid_failure_enabled=False,
            separator_first_outer_enabled=True,
            separator_first_outer_min_score=0.68,
            separator_first_outer_band_score=0.48,
            separator_first_outer_spacing_min_ratio=0.90,
            separator_first_outer_spacing_max_ratio=1.12,
            separator_first_outer_frame_error_max=0.08,
            separator_first_outer_max_width_ratio=0.055,
            separator_first_outer_gap_max_width_ratio=0.055,
            separator_first_outer_source_candidates=1,
            separator_first_outer_band_candidates=14,
            separator_first_outer_pair_candidates=2,
            separator_first_outer_max_candidates=4,
            long_axis_edge_anchor_outer_enabled=False,
            long_axis_edge_anchor_outer_mode="fallback",
            long_axis_edge_anchor_ratio_extras=(0.04, 0.06),
            long_axis_edge_anchor_max_candidates=4,
        )
    if format_name == "xpan":
        return FormatTuning(
            "xpan",
            outer_align_long_margin_ratio=0.008,
            outer_align_long_margin_cap_ratio=0.012,
            content_profile_min_run_ratio=0.24,
            separator_model_grid_credit=0.20,
            separator_model_equal_credit=0.06,
            separator_gate_mode="hard_required",
            wide_gap_retry_enabled=False,
            nearby_active_correction=False,
            lucky_pass_risk_enabled=False,
            leading_grid_failure_enabled=False,
            separator_first_outer_enabled=True,
            separator_first_outer_min_score=0.66,
            separator_first_outer_band_score=0.44,
            separator_first_outer_spacing_min_ratio=0.86,
            separator_first_outer_spacing_max_ratio=1.16,
            separator_first_outer_frame_error_max=0.10,
            separator_first_outer_max_width_ratio=0.045,
            separator_first_outer_gap_max_width_ratio=0.060,
            separator_first_outer_source_candidates=1,
            separator_first_outer_band_candidates=8,
            separator_first_outer_pair_candidates=3,
            separator_first_outer_max_candidates=4,
            long_axis_edge_anchor_outer_enabled=True,
            long_axis_edge_anchor_outer_mode="fallback",
            long_axis_edge_anchor_ratio_extras=(0.03, 0.06),
            long_axis_edge_anchor_max_candidates=4,
        )
    if format_name == "120-66":
        return base_120_tuning(
            format_name,
            score_outer_max_area=1.0,
            score_outer_too_large=1.0,
            score_outer_too_large_cap=0.86,
            calibrate_hard_full_confidence_floor=0.86,
            gap_max_width_max=720,
            wide_gap_retry_enabled=True,
            wide_gap_retry_max_width_ratio=0.140,
            wide_gap_min_mean=0.90,
            wide_gap_min_prominence=0.015,
            separator_120_edge_pair_min_score_without_wide=1.0,
            separator_120_edge_pair_min_score_with_wide=0.0,
            separator_120_min_wide_gaps_for_auto=0,
            short_axis_aspect_retry_enabled=True,
            short_axis_aspect_retry_min_error=0.24,
            short_axis_aspect_retry_target_aspect=1.0,
            floating_full_outer_enabled=True,
            long_axis_edge_anchor_outer_enabled=True,
            long_axis_edge_anchor_outer_mode="always",
            long_axis_edge_anchor_ratio_extras=(0.06, 0.10),
            long_axis_edge_anchor_max_candidates=6,
            separator_first_outer_enabled=True,
            separator_first_outer_mode="always",
        )
    if format_name == "120-67":
        return base_120_tuning(
            format_name,
            score_outer_too_large=0.995,
            score_outer_too_large_cap=0.86,
            calibrate_hard_full_confidence_floor=0.86,
            wide_gap_retry_enabled=True,
            wide_gap_retry_max_width_ratio=0.090,
            outer_align_short_excess_ratio=0.024,
            outer_align_short_requires_hard_anchors=True,
            outer_align_short_content_height_max=0.970,
            separator_first_outer_enabled=True,
            separator_first_outer_min_score=0.58,
            separator_first_outer_band_score=0.36,
            separator_first_outer_spacing_min_ratio=0.82,
            separator_first_outer_spacing_max_ratio=1.24,
            separator_first_outer_frame_error_max=0.18,
            separator_first_outer_max_width_ratio=0.110,
            separator_first_outer_gap_max_width_ratio=0.095,
            long_axis_edge_anchor_outer_enabled=False,
            long_axis_edge_anchor_outer_mode="fallback",
            long_axis_edge_anchor_ratio_extras=(0.04, 0.08),
            long_axis_edge_anchor_max_candidates=4,
        )
    if format_name == "120-645":
        return base_120_tuning(
            format_name,
            separator_first_outer_enabled=True,
            separator_first_outer_min_score=0.60,
            separator_first_outer_band_score=0.38,
            separator_first_outer_spacing_min_ratio=0.84,
            separator_first_outer_spacing_max_ratio=1.20,
            separator_first_outer_frame_error_max=0.14,
            separator_first_outer_max_width_ratio=0.090,
            separator_first_outer_gap_max_width_ratio=0.080,
            separator_first_outer_band_candidates=10,
            separator_first_outer_pair_candidates=3,
            separator_first_outer_max_candidates=8,
            long_axis_edge_anchor_outer_enabled=False,
            long_axis_edge_anchor_outer_mode="fallback",
            long_axis_edge_anchor_ratio_extras=(0.04, 0.08),
            long_axis_edge_anchor_max_candidates=4,
        )
    if format_name == "135-dual":
        return FormatTuning(
            "135-dual",
            separator_gate_mode="hard_required",
            wide_gap_retry_enabled=False,
            nearby_active_correction=False,
            lucky_pass_risk_enabled=False,
            leading_grid_failure_enabled=False,
            outer_retry_enabled=False,
            long_axis_edge_anchor_outer_enabled=False,
        )
    return FormatTuning(
        "135",
        separator_first_outer_enabled=True,
        separator_first_outer_min_score=0.72,
        separator_first_outer_band_score=0.52,
        separator_first_outer_spacing_min_ratio=0.92,
        separator_first_outer_spacing_max_ratio=1.10,
        separator_first_outer_frame_error_max=0.07,
        separator_first_outer_max_width_ratio=0.050,
        separator_first_outer_gap_max_width_ratio=0.060,
        separator_first_outer_source_candidates=1,
        separator_first_outer_band_candidates=12,
        separator_first_outer_pair_candidates=2,
        separator_first_outer_max_candidates=4,
        long_axis_edge_anchor_outer_enabled=False,
        long_axis_edge_anchor_outer_mode="fallback",
        long_axis_edge_anchor_ratio_extras=(0.02, 0.04),
        long_axis_edge_anchor_max_candidates=4,
    )


def separator_first_outer_mode(tuning: FormatTuning) -> str:
    mode = str(tuning.separator_first_outer_mode).strip().lower()
    if mode not in SEPARATOR_FIRST_OUTER_MODES:
        raise ValueError(f"invalid separator_first_outer_mode: {tuning.separator_first_outer_mode!r}")
    if not tuning.separator_first_outer_enabled:
        return "off"
    return mode


def long_axis_edge_anchor_outer_mode(tuning: FormatTuning) -> str:
    mode = str(tuning.long_axis_edge_anchor_outer_mode).strip().lower()
    if mode not in SEPARATOR_FIRST_OUTER_MODES:
        raise ValueError(f"invalid long_axis_edge_anchor_outer_mode: {tuning.long_axis_edge_anchor_outer_mode!r}")
    if not tuning.long_axis_edge_anchor_outer_enabled:
        return "off"
    return mode


@dataclass(frozen=True)
class OuterCandidate:
    name: str
    box: Box


@dataclass
class Detection:
    film_format: str
    layout: str
    strip_mode: str
    count: int
    outer: Box
    frames: list[Box]
    gaps: list[Gap]
    confidence: float
    review_reasons: list[str]
    detail: dict[str, Any]


@dataclass
class ImageProfile:
    shape: tuple[int, ...]
    dtype: str
    axes: str
    photometric: str
    compression: str
    sample_format: Optional[Any]
    bits_per_sample: Optional[Any]
    samples_per_pixel: Optional[int]
    planar_config: Optional[str]
    resolution: Optional[tuple[Any, Any]]
    resolution_unit: Optional[Any]
    icc_profile: Optional[bytes]


@dataclass
class ProcessResult:
    source: str
    status: str
    confidence: float
    film_format: str
    layout: str
    strip_mode: str
    count: int
    review_reasons: list[str]
    output_files: list[str]
    review_copy: Optional[str]
    outer_box: dict[str, int]
    frame_boxes: list[dict[str, int]]
    gaps: list[dict[str, Any]]
    detail: dict[str, Any]
    profile: dict[str, Any]
    warnings: list[str]


@dataclass
class Config:
    input_path: Path
    output_dir: Optional[Path]
    film_format: str
    layout_auto: bool
    layout: str
    strip_mode: str
    count: int
    count_override: Optional[int]
    page: int
    bleed_x: int
    bleed_y: int
    deskew: str
    analysis: str
    deskew_min_angle: float
    deskew_max_angle: float
    confidence_threshold: float
    review_dir: Optional[Path]
    copy_review_files: bool
    export_review: bool
    compression: str
    debug: bool
    debug_analysis: bool
    dry_run: bool
    diagnostics: bool
    overwrite: bool
    report: bool
    debug_errors: bool
    reuse_analysis: bool
    jobs: int


@dataclass
class AnalysisCache:
    layout: str
    gray_work: np.ndarray
    content_evidence_work: np.ndarray
    content_evidence_float_work: np.ndarray
    separator_evidence_work_full: Optional[np.ndarray] = None
    separator_profiles: dict[tuple[str, int, int, int, int], np.ndarray] = field(default_factory=dict)
    separator_profiles_full: dict[str, np.ndarray] = field(default_factory=dict)
    enhanced_separator_profiles: dict[tuple[str, int, int, int, int], np.ndarray] = field(default_factory=dict)
    enhanced_separator_profiles_full: dict[str, np.ndarray] = field(default_factory=dict)
    separator_evidence_crops: dict[tuple[int, int, int, int], np.ndarray] = field(default_factory=dict)
    edge_refine_profiles: dict[tuple[str, int, int, int, int], tuple[np.ndarray, np.ndarray, np.ndarray]] = field(default_factory=dict)
    preview_rgb_cache: dict[tuple[str, int], tuple[np.ndarray, float]] = field(default_factory=dict)
    content_profile_runs: dict[tuple[str, int, int, int, int, int], tuple[list[tuple[int, int]], dict[str, Any]]] = field(default_factory=dict)
    content_evidence_details: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    outer_alignment_details: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    separator_first_outer_candidates: dict[tuple[Any, ...], list[OuterCandidate]] = field(default_factory=dict)
    long_axis_edge_anchor_outer_candidates: dict[tuple[Any, ...], list[OuterCandidate]] = field(default_factory=dict)


def json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def enum_name(value: Any, default: str = "") -> str:
    return str(getattr(value, "name", value) or default)


def planar_config_name(value: Any) -> Optional[str]:
    if value is None:
        return None
    name = enum_name(value, "")
    upper = name.upper()
    if upper in {"1", "CONTIG", "CONTIGUOUS"}:
        return "CONTIG"
    if upper in {"2", "SEPARATE"}:
        return "SEPARATE"
    return upper or None


def spatial_shape(arr: np.ndarray) -> tuple[int, int]:
    if arr.ndim < 2:
        raise ValueError(f"Unsupported image shape: {arr.shape}")
    if arr.ndim == 3 and arr.shape[0] in (3, 4) and arr.shape[-1] not in (3, 4):
        return int(arr.shape[1]), int(arr.shape[2])
    return int(arr.shape[0]), int(arr.shape[1])


def infer_axes(arr: np.ndarray) -> str:
    if arr.ndim == 2:
        return "YX"
    if arr.ndim == 3 and arr.shape[-1] in (3, 4):
        return "YXS"
    if arr.ndim == 3 and arr.shape[0] in (3, 4):
        return "SYX"
    raise ValueError(f"Unsupported TIFF array shape: {arr.shape}")


def infer_axes_from_shape(shape: tuple[int, ...]) -> str:
    if len(shape) == 2:
        return "YX"
    if len(shape) == 3 and shape[-1] in (3, 4):
        return "YXS"
    if len(shape) == 3 and shape[0] in (3, 4):
        return "SYX"
    raise ValueError(f"Unsupported TIFF array shape: {shape}")


def spatial_shape_from_shape(shape: tuple[int, ...]) -> tuple[int, int]:
    axes = infer_axes_from_shape(shape)
    if axes == "SYX":
        return int(shape[1]), int(shape[2])
    return int(shape[0]), int(shape[1])


def sampled_values_for_percentile(values: np.ndarray, max_samples: int = 1_000_000) -> np.ndarray:
    flat = values.reshape(-1)
    if flat.size <= max_samples:
        return flat
    step = max(1, int(math.ceil(flat.size / float(max_samples))))
    return flat[::step]


def sampled_percentile(values: np.ndarray, percentiles: Iterable[float], max_samples: int = 1_000_000) -> np.ndarray:
    sample = sampled_values_for_percentile(values, max_samples=max_samples)
    if sample.size == 0:
        return np.array([0.0 for _ in percentiles], dtype=np.float64)
    return np.percentile(sample, list(percentiles))





def smooth_1d(values: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window))
    if window <= 1:
        return values.astype(np.float32, copy=False)
    kernel = np.ones(window, dtype=np.float32) / float(window)
    return np.convolve(values.astype(np.float32), kernel, mode="same")


def runs_from_mask(mask: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: Optional[int] = None
    for i, flag in enumerate(mask.astype(bool)):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def bbox_from_mask(mask: np.ndarray, min_row_fraction: float = 0.01, min_col_fraction: float = 0.01) -> Optional[Box]:
    if mask.size == 0:
        return None
    row_has = mask.mean(axis=1) >= min_row_fraction
    col_has = mask.mean(axis=0) >= min_col_fraction
    rows = np.flatnonzero(row_has)
    cols = np.flatnonzero(col_has)
    if rows.size == 0 or cols.size == 0:
        return None
    return Box(int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)


def box_from_dict(value: dict[str, Any]) -> Box:
    return Box(int(value["left"]), int(value["top"]), int(value["right"]), int(value["bottom"]))


def gap_from_dict(value: dict[str, Any]) -> Gap:
    return Gap(
        index=int(value["index"]),
        center=float(value["center"]),
        score=float(value.get("score", 0.0)),
        method=str(value.get("method", "unknown")),
        start=(None if value.get("start") is None else float(value.get("start"))),
        end=(None if value.get("end") is None else float(value.get("end"))),
        lane_box=value.get("lane_box"),
    )
