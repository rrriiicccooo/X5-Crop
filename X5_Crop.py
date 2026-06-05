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


VERSION = "3.4.1"
SCRIPT_NAME = "X5_Crop.py"
TIFF_SUFFIXES = {".tif", ".tiff"}
REPORT_RECORD_CACHE: dict[Path, tuple[int, int, list[dict[str, Any]]]] = {}


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
    "120-67": 4.0 / 5.0,
}
PARTIAL_FULL_COMPETE_MIN_CONFIDENCE = 0.78
CONTENT_ONLY_PARTIAL_PASS_MIN_CONFIDENCE = 0.92


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


@dataclass
class Gap:
    index: int
    center: float
    score: float
    method: str
    start: Optional[float] = None
    end: Optional[float] = None
    lane_box: Optional[dict[str, int]] = None
    overlap_like: bool = False

    @property
    def width(self) -> float:
        if self.start is None or self.end is None:
            return 0.0
        return max(0.0, float(self.end) - float(self.start))


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
    separator_profiles: dict[tuple[int, int, int, int], np.ndarray] = field(default_factory=dict)
    separator_evidence_crops: dict[tuple[int, int, int, int], np.ndarray] = field(default_factory=dict)
    edge_refine_profiles: dict[tuple[int, int, int, int], tuple[np.ndarray, np.ndarray, np.ndarray]] = field(default_factory=dict)


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


def make_gray_u8(arr: np.ndarray, axes: str, photometric: str) -> np.ndarray:
    if axes == "YX":
        gray = arr
    elif axes == "YXS":
        rgb = arr[..., :3].astype(np.float32)
        gray = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    elif axes == "SYX":
        rgb = arr[:3, ...].astype(np.float32)
        gray = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    else:
        raise ValueError(f"Unsupported axes: {axes}")

    gray = gray.astype(np.float32, copy=False)
    finite = np.isfinite(gray)
    if not finite.any():
        return np.zeros(gray.shape, dtype=np.uint8)
    finite_values = sampled_values_for_percentile(gray[finite])
    lo, hi = np.percentile(finite_values, [0.2, 99.8])
    if hi <= lo:
        hi = float(finite_values.max())
        lo = float(finite_values.min())
    if hi <= lo:
        out = np.zeros(gray.shape, dtype=np.uint8)
    else:
        out = np.clip((gray - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
    if photometric.upper() == "MINISWHITE":
        out = 255 - out
    return out


def make_analysis_gray(gray: np.ndarray) -> np.ndarray:
    data = gray.astype(np.float32)
    lo, hi = sampled_percentile(data, [0.5, 99.5])
    if hi <= lo:
        return gray.copy()
    stretched = np.clip((data - lo) / (hi - lo), 0.0, 1.0)
    shadow_lift = np.power(stretched, 0.72)
    gx = np.abs(np.diff(shadow_lift, axis=1, prepend=shadow_lift[:, :1]))
    gy = np.abs(np.diff(shadow_lift, axis=0, prepend=shadow_lift[:1, :]))
    edge = np.clip((gx + gy) * 2.0, 0.0, 1.0)
    enhanced = np.clip(shadow_lift * 0.82 + edge * 0.18, 0.0, 1.0)
    extreme = ((gray < 35) | (gray > 235)).mean(axis=0)
    activity = (gx + gy).mean(axis=0)
    gutter_cols = (extreme >= 0.82) & (activity <= 0.10)
    for start, end in runs_from_mask(gutter_cols):
        if end - start <= max(3, gray.shape[1] // 14):
            enhanced[:, start:end] = stretched[:, start:end]
    return (enhanced * 255.0 + 0.5).astype(np.uint8)


def make_separator_evidence_gray(gray: np.ndarray) -> np.ndarray:
    data = gray.astype(np.float32, copy=False)
    lo, hi = sampled_percentile(data, [2.0, 98.0])
    if hi <= lo:
        return gray.copy()
    local = np.clip((data - lo) / (hi - lo), 0.0, 1.0)
    gx = np.abs(np.diff(local, axis=1, prepend=local[:, :1]))
    vertical_edge = smooth_1d(gx.mean(axis=0).astype(np.float32), max(3, int(round(gray.shape[1] * 0.0015))))
    column_mean = local.mean(axis=0)
    dark_band = np.clip((0.28 - column_mean) / 0.28, 0.0, 1.0)
    light_band = np.clip((column_mean - 0.78) / 0.22, 0.0, 1.0)
    band = np.maximum(dark_band, light_band)
    evidence = np.maximum(local * 0.72, vertical_edge[None, :] * 0.28)
    evidence = np.maximum(evidence, band[None, :] * 0.55)
    return (np.clip(evidence, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def normalize_score_image(score: np.ndarray, percentile: float = 99.4) -> np.ndarray:
    data = score.astype(np.float32, copy=False)
    hi = float(sampled_percentile(data, [percentile])[0])
    if hi <= 1e-6:
        return np.zeros(data.shape, dtype=np.float32)
    return np.clip(data / hi, 0.0, 1.0)


def make_content_evidence_gray(gray: np.ndarray) -> np.ndarray:
    data = gray.astype(np.float32, copy=False) / 255.0
    if data.size == 0:
        return gray.copy()

    gx = np.abs(np.diff(data, axis=1, prepend=data[:, :1]))
    gy = np.abs(np.diff(data, axis=0, prepend=data[:1, :]))
    gradient = normalize_score_image(gx + gy, 99.2)

    north = np.empty_like(data)
    south = np.empty_like(data)
    west = np.empty_like(data)
    east = np.empty_like(data)
    north[0, :] = data[0, :]
    north[1:, :] = data[:-1, :]
    south[-1, :] = data[-1, :]
    south[:-1, :] = data[1:, :]
    west[:, 0] = data[:, 0]
    west[:, 1:] = data[:, :-1]
    east[:, -1] = data[:, -1]
    east[:, :-1] = data[:, 1:]
    neighbor_texture = (np.abs(data - north) + np.abs(data - south) + np.abs(data - west) + np.abs(data - east)) * 0.25
    texture = normalize_score_image(neighbor_texture, 99.2)

    local_mean = (data + north + south + west + east) * 0.2
    local_contrast = normalize_score_image(np.abs(data - local_mean), 99.0)

    tonal_presence = normalize_score_image(np.abs(data - float(np.median(sampled_values_for_percentile(data)))) * 0.35, 99.0)
    evidence = 0.42 * gradient + 0.34 * texture + 0.18 * local_contrast + 0.06 * tonal_presence
    evidence = np.clip(evidence, 0.0, 1.0)
    return (evidence * 255.0 + 0.5).astype(np.uint8)


def expected_content_aspect(format_name: str, layout: str) -> Optional[float]:
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(format_name)
    if aspect is None:
        return None
    if layout == "vertical":
        return 1.0 / aspect
    return aspect


def content_evidence_detail(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> dict[str, Any]:
    if cache is not None and cache.layout == detection.layout:
        return content_evidence_detail_from_cache(gray, detection, cache)

    outer = detection.outer.clamp(gray.shape[1], gray.shape[0])
    if not outer.valid():
        return {"used": False, "reason": "invalid_outer"}

    source_crop = gray[outer.top:outer.bottom, outer.left:outer.right]
    if source_crop.size == 0:
        return {"used": False, "reason": "empty_outer"}

    evidence = make_content_evidence_gray(source_crop).astype(np.float32) / 255.0
    outer_p70 = float(sampled_percentile(evidence, [70.0])[0])
    threshold = max(0.08, min(0.45, outer_p70 * 0.70))
    frame_scores: list[dict[str, Any]] = []
    means: list[float] = []
    coverages: list[float] = []
    aspect_errors: list[float] = []
    expected_aspect = expected_content_aspect(detection.film_format, detection.layout)

    for index, frame in enumerate(detection.frames, start=1):
        absolute_box = frame.clamp(gray.shape[1], gray.shape[0])
        box = Box(
            max(0, absolute_box.left - outer.left),
            max(0, absolute_box.top - outer.top),
            min(outer.width, absolute_box.right - outer.left),
            min(outer.height, absolute_box.bottom - outer.top),
        )
        if not box.valid():
            continue
        crop = evidence[box.top:box.bottom, box.left:box.right]
        if crop.size == 0:
            continue
        mean = float(crop.mean())
        coverage = float((crop >= threshold).mean())
        means.append(mean)
        coverages.append(coverage)
        actual_aspect = float(absolute_box.width) / max(1.0, float(absolute_box.height))
        aspect_error: Optional[float] = None
        if expected_aspect is not None and expected_aspect > 0:
            aspect_error = abs(actual_aspect - expected_aspect) / expected_aspect
            aspect_errors.append(float(aspect_error))
        frame_scores.append(
            {
                "index": index,
                "mean": mean,
                "coverage": coverage,
                "actual_aspect": actual_aspect,
                "expected_aspect": expected_aspect,
                "aspect_error": aspect_error,
            }
        )

    if not frame_scores:
        return {"used": False, "reason": "no_valid_frames"}

    median_mean = float(np.median(np.array(means, dtype=np.float32))) if means else 0.0
    min_mean = float(min(means)) if means else 0.0
    median_coverage = float(np.median(np.array(coverages, dtype=np.float32))) if coverages else 0.0
    max_aspect_error = float(max(aspect_errors)) if aspect_errors else None
    aspect_ok = max_aspect_error is None or max_aspect_error <= 0.22
    content_present = median_mean >= 0.075 or median_coverage >= 0.18
    support = "ok" if content_present and aspect_ok else "weak"
    if not aspect_ok:
        support = "aspect_conflict"
    elif not content_present:
        support = "low_content"

    return {
        "used": True,
        "support": support,
        "composite": "gradient+neighbor_texture+local_contrast+tonal_presence",
        "threshold": threshold,
        "median_mean": median_mean,
        "min_mean": min_mean,
        "median_coverage": median_coverage,
        "expected_aspect": expected_aspect,
        "max_aspect_error": max_aspect_error,
        "frame_scores": frame_scores,
    }


def content_evidence_detail_from_cache(gray: np.ndarray, detection: Detection, cache: AnalysisCache) -> dict[str, Any]:
    source_h, source_w = gray.shape
    work_h, work_w = cache.gray_work.shape
    outer = original_box_to_work(detection.outer, detection.layout, source_w, source_h).clamp(work_w, work_h)
    if not outer.valid():
        return {"used": False, "reason": "invalid_outer"}

    evidence = cache.content_evidence_float_work[outer.top:outer.bottom, outer.left:outer.right]
    if evidence.size == 0:
        return {"used": False, "reason": "empty_outer"}

    outer_p70 = float(sampled_percentile(evidence, [70.0])[0])
    threshold = max(0.08, min(0.45, outer_p70 * 0.70))
    frame_scores: list[dict[str, Any]] = []
    means: list[float] = []
    coverages: list[float] = []
    aspect_errors: list[float] = []
    expected_aspect = CONTENT_ASPECTS_HORIZONTAL.get(detection.film_format)

    for index, frame in enumerate(detection.frames, start=1):
        absolute_box = original_box_to_work(frame, detection.layout, source_w, source_h).clamp(work_w, work_h)
        box = Box(
            max(0, absolute_box.left - outer.left),
            max(0, absolute_box.top - outer.top),
            min(outer.width, absolute_box.right - outer.left),
            min(outer.height, absolute_box.bottom - outer.top),
        )
        if not box.valid():
            continue
        crop = evidence[box.top:box.bottom, box.left:box.right]
        if crop.size == 0:
            continue
        mean = float(crop.mean())
        coverage = float((crop >= threshold).mean())
        means.append(mean)
        coverages.append(coverage)
        actual_aspect = float(absolute_box.width) / max(1.0, float(absolute_box.height))
        aspect_error: Optional[float] = None
        if expected_aspect is not None and expected_aspect > 0:
            aspect_error = abs(actual_aspect - expected_aspect) / expected_aspect
            aspect_errors.append(float(aspect_error))
        frame_scores.append(
            {
                "index": index,
                "mean": mean,
                "coverage": coverage,
                "actual_aspect": actual_aspect,
                "expected_aspect": expected_aspect,
                "aspect_error": aspect_error,
            }
        )

    if not frame_scores:
        return {"used": False, "reason": "no_valid_frames"}

    median_mean = float(np.median(np.array(means, dtype=np.float32))) if means else 0.0
    min_mean = float(min(means)) if means else 0.0
    median_coverage = float(np.median(np.array(coverages, dtype=np.float32))) if coverages else 0.0
    max_aspect_error = float(max(aspect_errors)) if aspect_errors else None
    aspect_ok = max_aspect_error is None or max_aspect_error <= 0.22
    content_present = median_mean >= 0.075 or median_coverage >= 0.18
    support = "ok" if content_present and aspect_ok else "weak"
    if not aspect_ok:
        support = "aspect_conflict"
    elif not content_present:
        support = "low_content"

    return {
        "used": True,
        "support": support,
        "composite": "cached_gradient+neighbor_texture+local_contrast+tonal_presence",
        "threshold": threshold,
        "median_mean": median_mean,
        "min_mean": min_mean,
        "median_coverage": median_coverage,
        "expected_aspect": expected_aspect,
        "max_aspect_error": max_aspect_error,
        "frame_scores": frame_scores,
    }


def outer_content_alignment_detail(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> dict[str, Any]:
    gray_work = cache.gray_work if cache is not None and cache.layout == detection.layout else work_gray(gray, detection.layout)
    work_h, work_w = gray_work.shape
    source_h, source_w = gray.shape
    outer = original_box_to_work(detection.outer, detection.layout, source_w, source_h).clamp(work_w, work_h)
    if not outer.valid():
        return {"used": False, "reason": "invalid_outer"}

    candidates: list[tuple[str, Box]] = []
    for threshold in (225, 210, 190):
        box = bbox_from_mask(gray_work < threshold, min_row_fraction=0.015, min_col_fraction=0.015)
        if box is not None and box.valid():
            candidates.append((f"gray_lt_{threshold}", box))
    if not candidates:
        return {"used": False, "reason": "no_content_bbox"}

    source, content_box = candidates[0]
    pitch = float(outer.width) / float(max(1, detection.count))
    long_slack_left = max(0, content_box.left - outer.left)
    long_slack_right = max(0, outer.right - content_box.right)
    short_slack_top = max(0, content_box.top - outer.top)
    short_slack_bottom = max(0, outer.bottom - content_box.bottom)
    max_long_slack = max(long_slack_left, long_slack_right)
    max_short_slack = max(short_slack_top, short_slack_bottom)
    long_slack_ratio = float(max_long_slack) / max(1.0, pitch)
    short_slack_ratio = float(max_short_slack) / max(1.0, float(outer.height))
    content_width_ratio = float(content_box.width) / max(1.0, float(outer.width))
    content_height_ratio = float(content_box.height) / max(1.0, float(outer.height))

    edge_band = max(4, min(80, int(round(min(outer.width, outer.height) * 0.018))))
    outer_crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if outer_crop.size:
        left_band = outer_crop[:, :min(edge_band, outer_crop.shape[1])]
        right_band = outer_crop[:, max(0, outer_crop.shape[1] - edge_band):]
        top_band = outer_crop[:min(edge_band, outer_crop.shape[0]), :]
        bottom_band = outer_crop[max(0, outer_crop.shape[0] - edge_band):, :]
        border_dark_fraction = {
            "left": float((left_band < 245).mean()) if left_band.size else 0.0,
            "right": float((right_band < 245).mean()) if right_band.size else 0.0,
            "top": float((top_band < 245).mean()) if top_band.size else 0.0,
            "bottom": float((bottom_band < 245).mean()) if bottom_band.size else 0.0,
        }
    else:
        border_dark_fraction = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}

    excess_long = long_slack_ratio > 0.050 or (max_long_slack >= 160 and long_slack_ratio > 0.035)
    excess_short = short_slack_ratio > 0.035 and max_short_slack >= 28
    ok = not (excess_long or excess_short)
    reason = "ok"
    if excess_long:
        reason = "outer_long_axis_excess"
    elif excess_short:
        reason = "outer_short_axis_excess"

    return {
        "used": True,
        "ok": ok,
        "reason": reason,
        "content_bbox_source": source,
        "outer_work_box": asdict(outer),
        "content_work_box": asdict(content_box),
        "long_slack_left": int(long_slack_left),
        "long_slack_right": int(long_slack_right),
        "short_slack_top": int(short_slack_top),
        "short_slack_bottom": int(short_slack_bottom),
        "max_long_slack": int(max_long_slack),
        "max_short_slack": int(max_short_slack),
        "long_slack_ratio": long_slack_ratio,
        "short_slack_ratio": short_slack_ratio,
        "content_width_ratio": content_width_ratio,
        "content_height_ratio": content_height_ratio,
        "border_dark_fraction": border_dark_fraction,
    }


def corrected_outer_from_alignment(alignment: dict[str, Any], config: Config, count: int) -> Optional[Box]:
    if not bool(alignment.get("used", False)) or bool(alignment.get("ok", True)):
        return None
    try:
        outer = box_from_dict(alignment["outer_work_box"])
        content = box_from_dict(alignment["content_work_box"])
    except Exception:
        return None
    if not outer.valid() or not content.valid():
        return None

    pitch = float(outer.width) / float(max(1, count))
    alignment_bleed_x = min(int(config.bleed_x), 15)
    alignment_bleed_y = min(int(config.bleed_y), 10)
    long_margin = max(alignment_bleed_x, min(80, int(round(pitch * 0.012))))
    short_margin = max(alignment_bleed_y, min(40, int(round(float(outer.height) * 0.010))))
    left, top, right, bottom = outer.left, outer.top, outer.right, outer.bottom

    if int(alignment.get("long_slack_left", 0)) > 0:
        left = max(outer.left, content.left - long_margin)
    if int(alignment.get("long_slack_right", 0)) > 0:
        right = min(outer.right, content.right + long_margin)
    if int(alignment.get("short_slack_top", 0)) > 0 and str(alignment.get("reason", "")) == "outer_short_axis_excess":
        top = max(outer.top, content.top - short_margin)
    if int(alignment.get("short_slack_bottom", 0)) > 0 and str(alignment.get("reason", "")) == "outer_short_axis_excess":
        bottom = min(outer.bottom, content.bottom + short_margin)

    corrected = Box(left, top, right, bottom)
    if not corrected.valid():
        return None
    if corrected.width < max(80, int(round(outer.width * 0.80))) or corrected.height < max(40, int(round(outer.height * 0.80))):
        return None
    if corrected == outer:
        return None
    return corrected


def retry_with_content_aligned_outer(
    gray: np.ndarray,
    config: Config,
    fmt: FilmFormat,
    detection: Detection,
    alignment: dict[str, Any],
    cache: AnalysisCache,
) -> Optional[Detection]:
    if detection.strip_mode != "full":
        return None
    corrected_outer = corrected_outer_from_alignment(alignment, config, detection.count)
    if corrected_outer is None:
        return None

    retried = build_detection_for_outer(
        gray,
        config,
        fmt,
        detection.count,
        detection.strip_mode,
        corrected_outer,
        float(detection.detail.get("offset_fraction", 0.0)),
        "content_aligned_outer",
        cache=cache,
        allow_outer_refine=False,
    )
    retried = calibrate_v2_candidate(gray, retried, config, fmt, "separator", cache)
    retry_alignment = outer_content_alignment_detail(gray, retried, cache)
    retry_content = content_evidence_detail(gray, retried, cache)
    retried.detail["outer_content_alignment"] = retry_alignment
    retried.detail["content_evidence"] = retry_content
    retried.detail["outer_correction"] = {
        "used": True,
        "source_reason": alignment.get("reason"),
        "original_outer_work_box": alignment.get("outer_work_box"),
        "content_work_box": alignment.get("content_work_box"),
        "corrected_outer_work_box": asdict(corrected_outer),
        "retry_alignment": retry_alignment,
        "retry_content_support": retry_content.get("support"),
    }
    return retried


def content_profile_runs(evidence: np.ndarray, outer: Box, count: int) -> tuple[list[tuple[int, int]], dict[str, Any]]:
    crop = evidence[outer.top:outer.bottom, outer.left:outer.right].astype(np.float32) / 255.0
    if crop.size == 0:
        return [], {"reason": "empty_content_outer"}
    profile = crop.mean(axis=0)
    smooth_window = max(5, int(round(max(1, outer.width) * 0.010)))
    smoothed = smooth_1d(profile.astype(np.float32), smooth_window)
    p35, p65, p90 = sampled_percentile(smoothed, [35, 65, 90])
    threshold = max(0.035, min(0.40, float(p35 + (p90 - p35) * 0.38), float(p65) * 0.82))
    runs = runs_from_mask(smoothed >= threshold)
    min_width = max(6, int(round(outer.width / max(1, count) * 0.20)))
    filtered: list[tuple[int, int]] = []
    for start, end in runs:
        if end - start >= min_width:
            filtered.append((outer.left + start, outer.left + end))
    return filtered, {
        "profile_threshold": threshold,
        "profile_smooth_window": smooth_window,
        "profile_percentiles": {"p35": float(p35), "p65": float(p65), "p90": float(p90)},
        "raw_run_count": len(runs),
        "usable_run_count": len(filtered),
        "min_run_width": min_width,
    }


def select_content_runs(runs: list[tuple[int, int]], count: int) -> list[tuple[int, int]]:
    if len(runs) <= count:
        return runs
    ordered = sorted(runs, key=lambda run: run[1] - run[0], reverse=True)[:count]
    return sorted(ordered)


def content_detection_for_count(
    gray: np.ndarray,
    config: Config,
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
) -> Optional[Detection]:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    if cache is not None and cache.layout == config.layout:
        evidence = cache.content_evidence_work
        evidence_float = cache.content_evidence_float_work
    else:
        evidence = make_content_evidence_gray(gray_work)
        evidence_float = evidence.astype(np.float32) / 255.0
    p55, p75, p92 = sampled_percentile(evidence_float, [55, 75, 92])
    mask_threshold = max(0.045, min(0.45, float(p55 + (p92 - p55) * 0.34), float(p75) * 0.78))
    mask = evidence_float >= mask_threshold
    outer = bbox_from_mask(mask, min_row_fraction=0.008, min_col_fraction=0.008)
    if outer is None or outer.width < max(60, int(ww * 0.08)) or outer.height < max(30, int(wh * 0.08)):
        return None
    outer = outer.expand(max(2, int(round(ww * 0.002))), max(2, int(round(wh * 0.002))), ww, wh)

    expected_aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if expected_aspect is None or expected_aspect <= 0:
        return None
    runs, run_detail = content_profile_runs(evidence, outer, count)
    selected_runs = select_content_runs(runs, count)

    frame_h = max(1.0, float(outer.height))
    expected_w = max(8.0, frame_h * expected_aspect)
    raw_boxes: list[Box] = []
    placement = "content_runs" if len(selected_runs) >= count else "content_grid_fallback"
    if placement == "content_runs":
        for start, end in selected_runs[:count]:
            center = (float(start) + float(end)) * 0.5
            left = int(round(center - expected_w * 0.5))
            right = int(round(center + expected_w * 0.5))
            raw_boxes.append(Box(left, outer.top, right, outer.bottom).clamp(ww, wh))
    else:
        if strip_mode == "partial" and count < fmt.default_count:
            pitch = max(expected_w, outer.width / float(max(1, fmt.default_count)))
            total_width = pitch * count
            origin = max(0.0, min(float(outer.width) - total_width, (float(outer.width) - total_width) * offset_fraction))
            start_x = outer.left + origin
        else:
            pitch = max(expected_w, outer.width / float(max(1, count)))
            total_width = pitch * count
            start_x = outer.left + max(0.0, (outer.width - total_width) * 0.5)
        for i in range(count):
            center = start_x + pitch * (i + 0.5)
            raw_boxes.append(Box(int(round(center - expected_w * 0.5)), outer.top, int(round(center + expected_w * 0.5)), outer.bottom).clamp(ww, wh))

    raw_boxes = [box for box in raw_boxes if box.valid()]
    if len(raw_boxes) != count:
        return None

    boxes_work = [box.expand(config.bleed_x, config.bleed_y, ww, wh) for box in raw_boxes]
    boxes = [map_work_box(box, config.layout, gray.shape[1], gray.shape[0]) for box in boxes_work]
    outer_original = map_work_box(outer, config.layout, gray.shape[1], gray.shape[0])
    gaps: list[Gap] = []
    for index in range(1, count):
        left_box = raw_boxes[index - 1]
        right_box = raw_boxes[index]
        center = (float(left_box.right) + float(right_box.left)) * 0.5 - float(outer.left)
        gaps.append(Gap(index, center, 0.0, "content", float(left_box.right - outer.left), float(right_box.left - outer.left)))

    means: list[float] = []
    coverages: list[float] = []
    for box in raw_boxes:
        crop = evidence_float[box.top:box.bottom, box.left:box.right]
        if crop.size:
            means.append(float(crop.mean()))
            coverages.append(float((crop >= mask_threshold).mean()))
    median_mean = float(np.median(np.array(means, dtype=np.float32))) if means else 0.0
    median_coverage = float(np.median(np.array(coverages, dtype=np.float32))) if coverages else 0.0
    run_conf = min(1.0, len(selected_runs) / float(max(1, count)))
    coverage_conf = min(1.0, median_coverage / 0.22)
    mean_conf = min(1.0, median_mean / 0.16)
    aspect_errors = [abs((box.width / max(1.0, float(box.height))) - expected_aspect) / expected_aspect for box in raw_boxes]
    max_aspect_error = float(max(aspect_errors)) if aspect_errors else 1.0
    aspect_conf = max(0.0, min(1.0, 1.0 - max_aspect_error / 0.18))
    confidence = 0.38 * coverage_conf + 0.30 * mean_conf + 0.22 * run_conf + 0.10 * aspect_conf
    reasons: list[str] = []
    if placement != "content_runs":
        confidence = min(confidence, 0.82)
        reasons.append("content_grid_fallback")
    if len(runs) != count:
        confidence = min(confidence, 0.84)
        reasons.append("content_run_count_mismatch")
    if run_conf < 1.0:
        confidence = min(confidence, 0.84)
        reasons.append("content_runs_incomplete")
    if median_coverage < 0.14:
        confidence = min(confidence, 0.82)
        reasons.append("content_coverage_weak")
    if max_aspect_error > 0.18:
        confidence = min(confidence, 0.82)
        reasons.append("content_aspect_uncertain")
    if strip_mode == "partial":
        reasons.append("partial_strip_count_candidate")
    if confidence < config.confidence_threshold and not reasons:
        reasons.append("content_confidence_low")

    detail = {
        "analysis_source": "content_primary",
        "candidate_count": count,
        "offset_fraction": float(offset_fraction),
        "layout": config.layout,
        "outer_candidate": "content_evidence",
        "work_outer": asdict(outer),
        "content_primary": {
            "used": True,
            "placement": placement,
            "mask_threshold": mask_threshold,
            "expected_frame_aspect": expected_aspect,
            "expected_frame_width": expected_w,
            "median_mean": median_mean,
            "median_coverage": median_coverage,
            "run_conf": run_conf,
            "coverage_conf": coverage_conf,
            "mean_conf": mean_conf,
            "max_aspect_error": max_aspect_error,
            "raw_boxes": [asdict(box) for box in raw_boxes],
            **run_detail,
        },
        "gap_centers": [gap.center for gap in gaps],
        "gap_scores": [gap.score for gap in gaps],
        "gap_methods": [gap.method for gap in gaps],
    }
    return Detection(fmt.name, config.layout, strip_mode, count, outer_original, boxes, gaps, float(max(0.0, min(1.0, confidence))), sorted(set(reasons)), detail)


def profile_from_page(page: Any, shape: tuple[int, ...], dtype: np.dtype, axes: str) -> ImageProfile:
    photometric = enum_name(getattr(page, "photometric", None), "UNKNOWN")
    compression = enum_name(getattr(page, "compression", None), "NONE")
    sample_format = page.tags.get("SampleFormat")
    bits_tag = page.tags.get("BitsPerSample")
    samples_tag = page.tags.get("SamplesPerPixel")
    planar = page.tags.get("PlanarConfiguration")
    xres = page.tags.get("XResolution")
    yres = page.tags.get("YResolution")
    unit = page.tags.get("ResolutionUnit")
    icc = page.tags.get(34675)
    profile = ImageProfile(
        shape=tuple(int(x) for x in shape),
        dtype=str(np.dtype(dtype)),
        axes=axes,
        photometric=photometric,
        compression=compression,
        sample_format=(sample_format.value if sample_format else normalize_tag_value(getattr(page, "sampleformat", None))),
        bits_per_sample=(bits_tag.value if bits_tag else None),
        samples_per_pixel=(int(samples_tag.value) if samples_tag else (shape[-1] if axes == "YXS" else shape[0] if axes == "SYX" else 1)),
        planar_config=planar_config_name(getattr(page, "planarconfig", None) or (planar.value if planar else None)),
        resolution=((xres.value if xres else None), (yres.value if yres else None)) if xres or yres else None,
        resolution_unit=(unit.value if unit else None),
        icc_profile=(bytes(icc.value) if icc is not None else None),
    )
    expected_bits = expected_bits_for_dtype(profile.dtype, int(profile.samples_per_pixel or 1))
    if profile.bits_per_sample is not None and normalize_tag_value(profile.bits_per_sample) != normalize_tag_value(expected_bits):
        raise ValueError(
            f"Packed or unusual bit depth is not supported safely: "
            f"BitsPerSample={profile.bits_per_sample}, dtype={profile.dtype}. "
            "Refusing to continue to protect output bit depth."
        )
    return profile


def read_tiff_profile(path: Path, page_index: int) -> tuple[ImageProfile, list[str]]:
    warnings: list[str] = []
    with tifffile.TiffFile(path) as tif:
        if not tif.pages:
            raise ValueError("TIFF has no pages")
        if page_index < 0 or page_index >= len(tif.pages):
            raise ValueError(f"--page {page_index} is out of range; TIFF has {len(tif.pages)} pages")
        if len(tif.pages) > 1 and page_index == 0:
            warnings.append(f"TIFF has {len(tif.pages)} pages; processing page 0")
        page = tif.pages[page_index]
        shape = tuple(int(x) for x in page.shape)
        axes = str(getattr(page, "axes", "") or "")
        if axes not in {"YX", "YXS", "SYX"}:
            axes = infer_axes_from_shape(shape)
        profile = profile_from_page(page, shape, np.dtype(page.dtype), axes)
    return profile, warnings


def read_tiff(path: Path, page_index: int) -> tuple[np.ndarray, np.ndarray, ImageProfile, list[str], Any]:
    warnings: list[str] = []
    with tifffile.TiffFile(path) as tif:
        if not tif.pages:
            raise ValueError("TIFF has no pages")
        if page_index < 0 or page_index >= len(tif.pages):
            raise ValueError(f"--page {page_index} is out of range; TIFF has {len(tif.pages)} pages")
        if len(tif.pages) > 1 and page_index == 0:
            warnings.append(f"TIFF has {len(tif.pages)} pages; processing page 0")
        page = tif.pages[page_index]
        arr = page.asarray()
        axes = infer_axes(arr)
        profile = profile_from_page(page, tuple(int(x) for x in arr.shape), arr.dtype, axes)
    gray = make_gray_u8(arr, axes, profile.photometric)
    return arr, gray, profile, warnings, page


def infer_layout(width: int, height: int) -> str:
    return "horizontal" if width >= height else "vertical"


def work_gray(gray: np.ndarray, layout: str) -> np.ndarray:
    return gray if layout == "horizontal" else np.ascontiguousarray(gray.T)


def make_analysis_cache(gray: np.ndarray, layout: str) -> AnalysisCache:
    gray_work = work_gray(gray, layout)
    content_evidence = make_content_evidence_gray(gray_work)
    return AnalysisCache(
        layout=layout,
        gray_work=gray_work,
        content_evidence_work=content_evidence,
        content_evidence_float_work=content_evidence.astype(np.float32) / 255.0,
    )


def box_cache_key(box: Box) -> tuple[int, int, int, int]:
    return (int(box.left), int(box.top), int(box.right), int(box.bottom))


def crop_work_outer(gray_work: np.ndarray, outer: Box) -> np.ndarray:
    if not outer.valid():
        return gray_work
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    return crop if crop.size else gray_work


def cached_separator_profile(cache: Optional[AnalysisCache], gray_work: np.ndarray, outer: Box) -> np.ndarray:
    if cache is None:
        return separator_profile(crop_work_outer(gray_work, outer))
    key = box_cache_key(outer)
    profile = cache.separator_profiles.get(key)
    if profile is None:
        profile = separator_profile(crop_work_outer(cache.gray_work, outer))
        cache.separator_profiles[key] = profile
    return profile


def cached_separator_evidence_crop(cache: Optional[AnalysisCache], gray_work: np.ndarray, outer: Box) -> np.ndarray:
    if cache is None:
        return make_separator_evidence_gray(crop_work_outer(gray_work, outer))
    key = box_cache_key(outer)
    evidence = cache.separator_evidence_crops.get(key)
    if evidence is None:
        evidence = make_separator_evidence_gray(crop_work_outer(cache.gray_work, outer))
        cache.separator_evidence_crops[key] = evidence
    return evidence


def cached_edge_refine_profiles(
    cache: Optional[AnalysisCache],
    crop: np.ndarray,
    outer: Box,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if cache is None:
        return edge_refine_profiles(crop)
    key = box_cache_key(outer)
    profiles = cache.edge_refine_profiles.get(key)
    if profiles is None:
        profiles = edge_refine_profiles(crop_work_outer(cache.gray_work, outer))
        cache.edge_refine_profiles[key] = profiles
    return profiles


def map_work_box(box: Box, layout: str, width: int, height: int) -> Box:
    if layout == "horizontal":
        return box.clamp(width, height)
    return Box(box.top, box.left, box.bottom, box.right).clamp(width, height)


def original_box_to_work(box: Box, layout: str, width: int, height: int) -> Box:
    if layout == "horizontal":
        return box.clamp(width, height)
    return Box(box.top, box.left, box.bottom, box.right).clamp(height, width)


def apply_edge_bleed_protection(detection: Detection, config: Config, image_w: int, image_h: int) -> None:
    if detection.strip_mode != "full" or detection.count <= 1 or len(detection.frames) != detection.count:
        return
    outer_work = original_box_to_work(detection.outer, detection.layout, image_w, image_h)
    frames_work = [original_box_to_work(frame, detection.layout, image_w, image_h) for frame in detection.frames]
    if not outer_work.valid() or any(not frame.valid() for frame in frames_work):
        return

    work_w = image_w if detection.layout == "horizontal" else image_h
    nominal = float(outer_work.width) / float(max(1, detection.count))
    edge_guard = max(float(config.bleed_x * 2), min(90.0, nominal * 0.018))
    changed: list[str] = []

    first_target = max(0, outer_work.left - int(config.bleed_x))
    if frames_work[0].left > first_target + edge_guard:
        frames_work[0] = Box(first_target, frames_work[0].top, frames_work[0].right, frames_work[0].bottom)
        changed.append("first")

    last_target = min(work_w, outer_work.right + int(config.bleed_x))
    if frames_work[-1].right < last_target - edge_guard:
        frames_work[-1] = Box(frames_work[-1].left, frames_work[-1].top, last_target, frames_work[-1].bottom)
        changed.append("last")

    if not changed or any(not frame.valid() for frame in frames_work):
        return

    detection.frames = [map_work_box(frame, detection.layout, image_w, image_h) for frame in frames_work]
    detection.detail["edge_bleed_protection"] = {
        "used": True,
        "pinned": changed,
        "edge_guard": edge_guard,
        "long_axis_bleed": int(config.bleed_x),
    }


def detection_geometry_config(config: Config) -> Config:
    return replace(
        config,
        bleed_x=0,
        bleed_y=0,
    )


def apply_output_bleed(detection: Detection, detection_config: Config, output_config: Config, image_w: int, image_h: int) -> None:
    if int(detection_config.bleed_x) == int(output_config.bleed_x) and int(detection_config.bleed_y) == int(output_config.bleed_y):
        return
    frames_work = [original_box_to_work(frame, detection.layout, image_w, image_h) for frame in detection.frames]
    work_w = image_w if detection.layout == "horizontal" else image_h
    work_h = image_h if detection.layout == "horizontal" else image_w
    adjusted_work: list[Box] = []
    for frame in frames_work:
        raw = Box(
            frame.left + int(detection_config.bleed_x),
            frame.top + int(detection_config.bleed_y),
            frame.right - int(detection_config.bleed_x),
            frame.bottom - int(detection_config.bleed_y),
        )
        if not raw.valid():
            return
        adjusted_work.append(raw.expand(int(output_config.bleed_x), int(output_config.bleed_y), work_w, work_h))
    detection.frames = [map_work_box(frame, detection.layout, image_w, image_h) for frame in adjusted_work]
    detection.detail["output_bleed"] = {
        "used": True,
        "detection_long_axis_bleed": int(detection_config.bleed_x),
        "detection_short_axis_bleed": int(detection_config.bleed_y),
        "output_long_axis_bleed": int(output_config.bleed_x),
        "output_short_axis_bleed": int(output_config.bleed_y),
    }


def apply_approved_geometry_polish(detection: Detection, gray: np.ndarray, config: Config, status: str) -> None:
    if status != "approved_auto" or detection.strip_mode != "full" or len(detection.frames) != detection.count:
        return
    if detection.review_reasons:
        return
    gray_work = work_gray(gray, detection.layout)
    h, w = gray_work.shape
    outer = original_box_to_work(detection.outer, detection.layout, gray.shape[1], gray.shape[0])
    frames = [original_box_to_work(frame, detection.layout, gray.shape[1], gray.shape[0]) for frame in detection.frames]
    if not outer.valid() or any(not frame.valid() for frame in frames):
        return

    original_outer = outer
    changes: dict[str, Any] = {}

    long_limit = max(20, min(60, int(round((outer.width / float(max(1, detection.count))) * 0.018))))
    band_top = outer.top + int(round(outer.height * 0.12))
    band_bottom = outer.bottom - int(round(outer.height * 0.12))
    if band_bottom <= band_top:
        band_top, band_bottom = outer.top, outer.bottom

    def side_extension(side: str) -> int:
        if side == "left":
            lo, hi = max(0, outer.left - long_limit), outer.left
        else:
            lo, hi = outer.right, min(w, outer.right + long_limit)
        if hi <= lo:
            return 0
        strip = gray_work[band_top:band_bottom, lo:hi]
        if strip.size == 0:
            return 0
        col_content = (strip < 242).mean(axis=0)
        if side == "left":
            active = np.where(col_content > 0.018)[0]
            return int(hi - (lo + int(active[0]))) if active.size else 0
        active = np.where(col_content > 0.018)[0]
        return int(int(active[-1]) + 1) if active.size else 0

    min_long_ext = 50
    left_ext = side_extension("left")
    right_ext = side_extension("right")
    left_ext = left_ext if left_ext >= min_long_ext else 0
    right_ext = right_ext if right_ext >= min_long_ext else 0
    if 0 < left_ext <= long_limit:
        outer = Box(max(0, outer.left - left_ext), outer.top, outer.right, outer.bottom)
        frames[0] = Box(outer.left, frames[0].top, frames[0].right, frames[0].bottom)
    if 0 < right_ext <= long_limit:
        outer = Box(outer.left, outer.top, min(w, outer.right + right_ext), outer.bottom)
        frames[-1] = Box(frames[-1].left, frames[-1].top, outer.right, frames[-1].bottom)
    if left_ext or right_ext:
        changes["long_axis_expand"] = {
            "left": int(left_ext),
            "right": int(right_ext),
            "limit": int(long_limit),
            "minimum": int(min_long_ext),
        }

    if not changes or not outer.valid() or any(not frame.valid() for frame in frames):
        return
    detection.detail["geometry_polish"] = {
        "used": True,
        "original_outer": asdict(original_outer),
        "polished_outer": asdict(outer),
        **changes,
    }
    detection.outer = map_work_box(outer, detection.layout, gray.shape[1], gray.shape[0])
    detection.frames = [map_work_box(frame, detection.layout, gray.shape[1], gray.shape[0]) for frame in frames]


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


def first_content_index(border_mask: np.ndarray, min_run: int) -> int:
    if border_mask.size == 0:
        return 0
    content = ~border_mask.astype(bool)
    runs = runs_from_mask(content)
    for start, end in runs:
        if end - start >= min_run:
            return int(start)
    candidates = np.flatnonzero(content)
    return int(candidates[0]) if candidates.size else 0


def detect_outer(gray: np.ndarray) -> Box:
    h, w = gray.shape
    not_white = gray < 246
    dark = gray < 210
    mask = not_white | dark
    box = bbox_from_mask(mask, min_row_fraction=0.015, min_col_fraction=0.015)
    if box is None or box.width < max(20, w * 0.10) or box.height < max(20, h * 0.10):
        return Box(0, 0, w, h)

    margin_x = max(2, int(round(w * 0.002)))
    margin_y = max(2, int(round(h * 0.002)))
    return box.expand(margin_x, margin_y, w, h)


def detect_outer_white_x(gray: np.ndarray) -> Box:
    h, w = gray.shape
    border_ratio = 0.985
    min_run_y = max(2, min(80, int(round(h * 0.003))))
    min_run_x = max(2, min(80, int(round(w * 0.003))))
    y_background = (gray <= 30) | (gray >= 225)
    x_background = gray >= 225
    row_border = y_background.mean(axis=1) >= border_ratio
    col_border = x_background.mean(axis=0) >= border_ratio
    top = first_content_index(row_border, min_run_y)
    bottom = h - first_content_index(row_border[::-1], min_run_y)
    left = first_content_index(col_border, min_run_x)
    right = w - first_content_index(col_border[::-1], min_run_x)
    margin_x = max(2, int(round(w * 0.002)))
    margin_y = max(2, int(round(h * 0.002)))
    box = Box(left, top, right, bottom).expand(margin_x, margin_y, w, h)
    if not box.valid() or box.width < max(20, w * 0.10) or box.height < max(20, h * 0.10):
        return Box(0, 0, w, h)
    return box


def unique_outer_candidates(candidates: Iterable[OuterCandidate]) -> list[OuterCandidate]:
    seen: set[tuple[int, int, int, int]] = set()
    out: list[OuterCandidate] = []
    for candidate in candidates:
        box = candidate.box
        key = (box.left, box.top, box.right, box.bottom)
        if key in seen or not box.valid():
            continue
        seen.add(key)
        out.append(candidate)
    return out


def detect_outer_candidates(gray: np.ndarray) -> list[OuterCandidate]:
    h, w = gray.shape
    bw = detect_outer(gray)
    white_x = detect_outer_white_x(gray)
    candidates = [OuterCandidate("bw", bw)]
    if white_x.valid():
        max_reasonable = max(float(bw.width) * 1.80, float(bw.width) + w * 0.06)
        if white_x.width >= bw.width and white_x.width <= max_reasonable:
            candidates.append(OuterCandidate("white_x", white_x))
    masks = [
        ("mask_not_white_246", gray < 246),
        ("mask_not_white_225", gray < 225),
        ("mask_mid_8_246", (gray > 8) & (gray < 246)),
    ]
    for name, mask in masks:
        box = bbox_from_mask(mask, min_row_fraction=0.012, min_col_fraction=0.012)
        if box is None:
            continue
        if box.width < max(20, w * 0.10) or box.height < max(20, h * 0.10):
            continue
        candidates.append(OuterCandidate(name, box.expand(max(2, int(w * 0.002)), max(2, int(h * 0.002)), w, h)))
    unique = unique_outer_candidates(candidates)
    canvas_area = float(w * h)
    non_full = [
        candidate for candidate in unique
        if (candidate.box.width * candidate.box.height) / max(1.0, canvas_area) <= 0.94
    ]
    if non_full:
        return non_full
    return unique or [OuterCandidate("full_canvas", Box(0, 0, w, h))]


def separator_profile(crop: np.ndarray) -> np.ndarray:
    h, w = crop.shape
    if h <= 0 or w <= 0:
        return np.zeros(0, dtype=np.float32)
    y0 = max(0, min(h - 1, int(round(h * 0.10))))
    y1 = max(y0 + 1, min(h, int(round(h * 0.90))))
    middle = crop[y0:y1, :]
    middle_f = middle.astype(np.float32, copy=False)

    profiles: list[np.ndarray] = []
    for i in range(5):
        sy0 = int(round(i * middle.shape[0] / 5))
        sy1 = int(round((i + 1) * middle.shape[0] / 5))
        if sy1 <= sy0:
            continue
        part = middle[sy0:sy1, :]
        black = (part <= 30).mean(axis=0).astype(np.float32)
        white = (part >= 225).mean(axis=0).astype(np.float32)
        profiles.append(np.maximum(black, white))
    if not profiles:
        profiles.append(((middle <= 30) | (middle >= 225)).mean(axis=0).astype(np.float32))

    stack = np.stack(profiles, axis=0)
    average_extreme = stack.mean(axis=0).astype(np.float32)
    vertical_consistency = np.percentile(stack, 20, axis=0).astype(np.float32)
    extreme_score = 0.35 * average_extreme + 0.65 * vertical_consistency

    col_std = middle_f.std(axis=0)
    uniform_score = 1.0 - np.clip(col_std / 70.0, 0.0, 1.0)
    col_mean = middle_f.mean(axis=0)
    dark_soft = np.clip((54.0 - col_mean) / 54.0, 0.0, 1.0)
    light_soft = np.clip((col_mean - 225.0) / 30.0, 0.0, 1.0)
    soft_score = np.maximum(dark_soft, light_soft) * uniform_score * 0.50

    gradient = np.abs(np.diff(middle_f, axis=1, prepend=middle_f[:, :1])).mean(axis=0) / 255.0
    score = np.maximum(extreme_score * (0.90 + 0.10 * uniform_score), soft_score)
    score = np.maximum(score, np.clip(gradient, 0.0, 1.0) * 0.25)
    return smooth_1d(score.astype(np.float32), max(3, int(round(w * 0.0015))))


def normalize_profile(profile: np.ndarray, high_percentile: float = 99.0) -> np.ndarray:
    profile = profile.astype(np.float32, copy=False)
    if profile.size == 0:
        return profile
    hi = float(np.percentile(profile, high_percentile))
    if hi <= 1e-6:
        return np.zeros_like(profile, dtype=np.float32)
    return np.clip(profile / hi, 0.0, 1.0).astype(np.float32)


def edge_refine_profiles(crop: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h, w = crop.shape
    if h <= 0 or w <= 1:
        zeros = np.zeros(w, dtype=np.float32)
        return zeros, zeros, zeros
    y0 = max(0, min(h - 1, int(round(h * 0.12))))
    y1 = max(y0 + 1, min(h, int(round(h * 0.88))))
    middle = crop[y0:y1, :]
    if middle.size == 0:
        zeros = np.zeros(w, dtype=np.float32)
        return zeros, zeros, zeros
    middle_i16 = middle.astype(np.int16, copy=False)
    diff_x = np.abs(np.diff(middle_i16, axis=1)).astype(np.float32)
    edge = np.zeros(w, dtype=np.float32)
    if diff_x.shape[1] > 0:
        raw = 0.65 * diff_x.mean(axis=0) + 0.35 * np.percentile(diff_x, 75, axis=0)
        edge[1:] = raw
        edge = normalize_profile(smooth_1d(edge, max(3, int(round(w * 0.0008)))), 99.2)
    background = ((middle <= 30) | (middle >= 225)).mean(axis=0).astype(np.float32)
    col_std = middle.astype(np.float32, copy=False).std(axis=0)
    if middle.shape[0] > 1:
        diff_y = np.abs(np.diff(middle_i16, axis=0)).astype(np.float32)
        y_edge = diff_y.mean(axis=0)
    else:
        y_edge = np.zeros(w, dtype=np.float32)
    activity = normalize_profile(col_std + 0.5 * y_edge, 95.0)
    return edge, background, activity


def local_edge_peaks(profile: np.ndarray, lo: int, hi: int, min_strength: float) -> list[int]:
    width = len(profile)
    lo = max(0, min(int(lo), width))
    hi = max(lo, min(int(hi), width))
    if hi <= lo:
        return []
    local = profile[lo:hi]
    if local.size == 0:
        return []
    threshold = max(float(min_strength), float(np.percentile(local, 84)))
    peaks: list[int] = []
    for start, end in runs_from_mask(local >= threshold):
        if end <= start:
            continue
        peak = lo + start + int(np.argmax(local[start:end]))
        if float(profile[peak]) >= min_strength:
            peaks.append(int(peak))
    deduped: list[int] = []
    for peak in sorted(peaks):
        if not deduped or peak - deduped[-1] > 2:
            deduped.append(peak)
        elif profile[peak] > profile[deduped[-1]]:
            deduped[-1] = peak
    return deduped


def interval_mean(profile: np.ndarray, start: int, end: int) -> float:
    start = max(0, min(int(start), len(profile)))
    end = max(start, min(int(end), len(profile)))
    if end <= start:
        return 0.0
    return float(profile[start:end].mean())


def refine_gaps_by_edge_pairs(
    crop: np.ndarray,
    gaps: list[Gap],
    count: int,
    cache: Optional[AnalysisCache] = None,
    outer: Optional[Box] = None,
) -> tuple[list[Gap], dict[str, Any]]:
    h, w = crop.shape
    if count <= 1 or w <= 1 or not gaps:
        return gaps, {"used": False, "reason": "empty"}
    edge, background, _activity = cached_edge_refine_profiles(cache, crop, outer) if outer is not None else edge_refine_profiles(crop)
    pitch = w / float(max(1, count))
    window = max(8, int(round(pitch * 0.08)))
    min_gutter = max(2, int(round(pitch * 0.004)))
    max_gutter = max(min_gutter + 1, int(round(pitch * 0.050)))
    min_strength = 0.42
    min_bg = 0.62
    refined: list[Gap] = []
    accepted: list[dict[str, Any]] = []
    rejected = 0
    for gap in gaps:
        x0 = int(round(gap.center))
        lo = max(1, x0 - window)
        hi = min(w - 1, x0 + window)
        peaks = local_edge_peaks(edge, lo, hi, min_strength)
        candidates: list[tuple[float, float, float, int, int]] = []
        for i, a in enumerate(peaks):
            for b in peaks[i + 1:]:
                gutter_w = b - a
                if gutter_w < min_gutter or gutter_w > max_gutter:
                    continue
                center = (a + b) / 2.0
                if abs(center - x0) > window:
                    continue
                bg_between = interval_mean(background, a, b + 1)
                if bg_between < min_bg:
                    continue
                strength = (float(edge[a]) + float(edge[b])) / 2.0
                quality = strength + 0.6 * bg_between
                distance = abs(center - x0) / max(1.0, pitch)
                candidates.append((distance, -quality, -bg_between, int(a), int(b)))
        if not candidates:
            refined.append(gap)
            rejected += 1
            continue
        _distance, neg_quality, _neg_bg, a, b = sorted(candidates)[0]
        center = (a + b) / 2.0
        edge_gap = Gap(gap.index, float(center), float(-neg_quality), "edge-pair", float(a), float(b + 1))
        if gap.method == "detected" and abs(edge_gap.center - gap.center) > max(4.0, edge_gap.width):
            refined.append(gap)
            rejected += 1
            continue
        refined.append(edge_gap)
        accepted.append(
            {
                "index": int(gap.index),
                "center": float(edge_gap.center),
                "width": float(edge_gap.width),
                "score": float(edge_gap.score),
                "replaced_method": gap.method,
            }
        )
    return refined, {"used": True, "accepted": accepted, "accepted_count": len(accepted), "rejected_count": rejected}


def find_gap(profile: np.ndarray, expected: float, pitch: float, index: int) -> Gap:
    radius = max(6, int(round(pitch * 0.16)))
    lo = max(1, int(round(expected)) - radius)
    hi = min(len(profile) - 1, int(round(expected)) + radius + 1)
    if hi <= lo:
        return Gap(index, float(expected), 0.0, "equal")
    local = profile[lo:hi]
    local_max = float(local.max()) if local.size else 0.0
    min_score = 0.22
    if local.size == 0 or local_max < min_score:
        return Gap(index, float(expected), local_max, "equal")

    max_gap_w = max(2, int(round(pitch * 0.045)))
    min_gap_w = max(1, int(round(pitch * 0.001)))
    guard_w = max(3, int(round(pitch * 0.035)))
    peak_threshold = max(min_score, local_max * 0.90)
    broad_threshold = max(min_score * 0.72, local_max * 0.48)
    band_threshold = max(min_score * 0.86, local_max * 0.62)
    candidates: list[tuple[float, float, float, float]] = []
    for run_start, run_end in runs_from_mask(local >= peak_threshold):
        region_start, region_end = run_start, run_end
        while region_start > 0 and local[region_start - 1] >= broad_threshold:
            region_start -= 1
        while region_end < len(local) and local[region_end] >= broad_threshold:
            region_end += 1
        band_start, band_end = run_start, run_end
        while band_start > 0 and local[band_start - 1] >= band_threshold and (band_end - (band_start - 1)) <= max_gap_w:
            band_start -= 1
        while band_end < len(local) and local[band_end] >= band_threshold and ((band_end + 1) - band_start) <= max_gap_w:
            band_end += 1
        band_width = band_end - band_start
        if band_width < min_gap_w or band_width > max_gap_w:
            continue

        left_guard = local[max(0, band_start - guard_w):band_start]
        right_guard = local[band_end:min(len(local), band_end + guard_w)]
        if left_guard.size == 0 or right_guard.size == 0:
            continue
        mean_score = float(local[band_start:band_end].mean())
        side_score = max(float(left_guard.mean()), float(right_guard.mean()))
        prominence = mean_score - side_score
        if prominence < 0.08 and mean_score < 0.95:
            continue

        center = float(lo + (band_start + band_end - 1) / 2.0)
        start = float(lo + band_start)
        end = float(lo + band_end)
        distance = abs(center - expected) / max(1.0, pitch)
        quality = mean_score + 0.8 * prominence
        candidates.append((distance, -quality, -mean_score, center, start, end))

    if candidates:
        _, neg_quality, _, center, start, end = sorted(candidates)[0]
        return Gap(index, center, float(-neg_quality), "detected", start, end)

    return Gap(index, float(expected), local_max, "equal")


def constrain_gap_to_geometry(gap: Gap, expected: float, pitch: float, strip_mode: str) -> Gap:
    if gap.method not in {"detected", "edge-pair"}:
        return Gap(gap.index, float(expected), gap.score, "equal")
    max_shift = pitch * (0.045 if strip_mode == "full" else 0.12)
    shift = max(-max_shift, min(max_shift, gap.center - expected))
    center = float(expected + shift)
    method = gap.method
    if gap.start is not None and gap.end is not None:
        delta = center - float(gap.center)
        start = float(gap.start + delta)
        end = float(gap.end + delta)
    else:
        start = None
        end = None
    return Gap(gap.index, center, gap.score, method, start, end)


def apply_robust_grid(gaps: list[Gap], origin: float, pitch: float, strip_mode: str) -> tuple[list[Gap], dict[str, Any]]:
    if not gaps:
        return gaps, {"grid_used": False}
    constrained = [constrain_gap_to_geometry(gap, origin + pitch * gap.index, pitch, strip_mode) for gap in gaps]
    reliable = [gap for gap in constrained if gap.method in {"detected", "edge-pair"} and gap.score >= 0.28]
    if len(reliable) < 2:
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable)}
    best: Optional[tuple[int, float, float, float]] = None
    for a_i, a in enumerate(reliable):
        for b in reliable[a_i + 1:]:
            dk = b.index - a.index
            if dk == 0:
                continue
            cand_pitch = (b.center - a.center) / float(dk)
            if cand_pitch <= pitch * 0.70 or cand_pitch >= pitch * 1.30:
                continue
            cand_origin = a.center - cand_pitch * a.index
            residuals = [abs(g.center - (cand_origin + cand_pitch * g.index)) for g in reliable]
            tolerance = max(4.0, pitch * (0.040 if strip_mode == "full" else 0.090))
            inliers = sum(1 for value in residuals if value <= tolerance)
            median_residual = float(np.median(np.array(residuals, dtype=np.float64))) if residuals else 0.0
            rank = (inliers, -median_residual, -abs(cand_pitch - pitch), cand_pitch)
            if best is None or rank > (best[0], -best[3], -abs(best[1] - pitch), best[1]):
                best = (inliers, float(cand_pitch), float(cand_origin), median_residual)
    if best is None:
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable), "grid_rejected": "no_pair_model"}
    inlier_count, fit_pitch, fit_origin, median_residual = best
    if inlier_count < 2:
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable), "grid_rejected": "too_few_inliers"}
    if median_residual > max(4.0, pitch * 0.045):
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable), "grid_rejected": "high_residual", "grid_residual": median_residual}
    max_shift = pitch * (0.035 if strip_mode == "full" else 0.10)
    adjusted: list[Gap] = []
    hard_preserved = 0
    hard_conflicts: list[dict[str, Any]] = []
    for gap in constrained:
        predicted = float(fit_origin + fit_pitch * gap.index)
        theoretical = float(origin + pitch * gap.index)
        predicted = max(theoretical - max_shift, min(theoretical + max_shift, predicted))
        residual = abs(gap.center - predicted)
        tight_tolerance = max(3.0, pitch * 0.025)
        if gap.method in {"detected", "edge-pair"}:
            strong_score = 0.75 if gap.method == "edge-pair" else 0.55
            plausible_width = gap.width <= max(2.0, pitch * 0.060) or gap.width <= 0.0
            if residual <= tight_tolerance or (gap.score >= strong_score and plausible_width):
                hard_preserved += 1
                if residual > tight_tolerance:
                    if len(hard_conflicts) < 4:
                        hard_conflicts.append({
                            "index": gap.index,
                            "method": gap.method,
                            "center": float(gap.center),
                            "grid_center": float(predicted),
                            "residual": float(residual),
                            "score": float(gap.score),
                        })
                adjusted.append(gap)
                continue
        adjusted.append(Gap(gap.index, predicted, gap.score, "grid"))
    return adjusted, {
        "grid_used": True,
        "reliable_gaps": len(reliable),
        "grid_inliers": int(inlier_count),
        "grid_pitch": float(fit_pitch),
        "grid_origin": float(fit_origin),
        "grid_residual": median_residual,
        "hard_preserved_count": int(hard_preserved),
        "hard_conflicts": hard_conflicts,
    }


def mark_overlap_like_gaps(
    gray_work: np.ndarray,
    outer: Box,
    gaps: list[Gap],
    pitch: float,
    fmt: FilmFormat,
    strip_mode: str,
    count: int,
    cache: Optional[AnalysisCache] = None,
) -> tuple[list[Gap], dict[str, Any]]:
    if fmt.name != "135" or strip_mode != "full" or count != fmt.default_count or not gaps:
        return gaps, {"used": False, "reason": "not_applicable"}
    if outer.width <= 1 or outer.height <= 1:
        return gaps, {"used": False, "reason": "invalid_outer"}

    if cache is not None:
        content = cache.content_evidence_float_work[outer.top:outer.bottom, outer.left:outer.right]
    else:
        crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
        content = make_content_evidence_gray(crop).astype(np.float32) / 255.0 if crop.size else np.zeros((0, 0), dtype=np.float32)
    if content.size == 0:
        return gaps, {"used": False, "reason": "empty_outer"}

    separator = cached_separator_profile(cache, gray_work, outer)
    if separator.size == 0:
        return gaps, {"used": False, "reason": "empty_separator_profile"}

    marked: list[Gap] = []
    records: list[dict[str, Any]] = []
    gap_half = max(3, int(round(pitch * 0.012)))
    side_half = max(gap_half + 2, int(round(pitch * 0.050)))
    search_half = max(gap_half + 2, int(round(pitch * 0.030)))
    content_profile = content.mean(axis=0).astype(np.float32)
    if content_profile.size != outer.width:
        return gaps, {"used": False, "reason": "content_profile_shape_mismatch"}

    for gap in gaps:
        x = int(round(gap.center))
        gap_lo = max(0, x - gap_half)
        gap_hi = min(outer.width, x + gap_half + 1)
        left_lo = max(0, x - side_half)
        left_hi = max(left_lo, x - gap_half)
        right_lo = min(outer.width, x + gap_half + 1)
        right_hi = min(outer.width, x + side_half + 1)
        sep_lo = max(0, x - search_half)
        sep_hi = min(len(separator), x + search_half + 1)

        if gap_hi <= gap_lo or left_hi <= left_lo or right_hi <= right_lo or sep_hi <= sep_lo:
            marked.append(gap)
            continue

        gap_content = float(np.median(content_profile[gap_lo:gap_hi]))
        left_content = float(np.median(content_profile[left_lo:left_hi]))
        right_content = float(np.median(content_profile[right_lo:right_hi]))
        side_content = min(left_content, right_content)
        continuity = gap_content / max(0.001, side_content)
        separator_peak = float(np.max(separator[sep_lo:sep_hi]))
        weak_hard = gap.method in {"detected", "edge-pair"} and (
            gap.score < 0.50 or gap.width <= max(2.0, pitch * 0.006)
        )
        model_only = gap.method in {"grid", "equal"}
        overlap_like = (
            side_content >= 0.080
            and gap_content >= 0.070
            and continuity >= 0.72
            and separator_peak < 0.46
            and (model_only or weak_hard)
        )

        if overlap_like:
            marked.append(replace(gap, overlap_like=True))
            records.append(
                {
                    "index": int(gap.index),
                    "method": gap.method,
                    "center": float(gap.center),
                    "score": float(gap.score),
                    "gap_content": gap_content,
                    "left_content": left_content,
                    "right_content": right_content,
                    "continuity": continuity,
                    "separator_peak": separator_peak,
                }
            )
        else:
            marked.append(gap)

    return marked, {
        "used": True,
        "marked_count": len(records),
        "marked": records,
        "gap_half_window_px": int(gap_half),
        "side_window_px": int(side_half),
        "separator_window_px": int(search_half),
    }


def frame_boxes_from_gaps(
    outer: Box,
    gaps: list[Gap],
    count: int,
    image_w: int,
    image_h: int,
    bleed_x: int,
    bleed_y: int,
    origin: float = 0.0,
    pitch: Optional[float] = None,
    apply_size_fit: bool = True,
) -> list[Box]:
    if pitch is None:
        cuts = [float(outer.left)] + [gap.center + outer.left for gap in gaps] + [float(outer.right)]
    else:
        cuts = [outer.left + origin] + [outer.left + gap.center for gap in gaps] + [outer.left + origin + pitch * count]
    if apply_size_fit:
        cuts = apply_frame_size_fit(cuts, outer, count, pitch)
    boxes: list[Box] = []
    for left, right in zip(cuts[:-1], cuts[1:]):
        box = Box(int(round(left)), outer.top, int(round(right)), outer.bottom)
        boxes.append(box.expand(bleed_x, bleed_y, image_w, image_h))
    return boxes[:count]


def apply_frame_size_fit(cuts: list[float], outer: Box, count: int, pitch: Optional[float]) -> list[float]:
    if len(cuts) != count + 1 or count <= 1:
        return cuts
    widths = np.diff(np.array(cuts, dtype=np.float64))
    if widths.size != count or np.any(widths <= 1):
        return cuts
    width_cv = float(widths.std() / max(1.0, widths.mean()))
    target = float(np.median(widths))
    if pitch is not None and 0.85 <= target / max(1.0, float(pitch)) <= 1.15:
        target = float(pitch)
    if width_cv <= 0.006:
        return cuts

    centers = (np.array(cuts[:-1], dtype=np.float64) + np.array(cuts[1:], dtype=np.float64)) / 2.0
    starts = centers - (np.arange(count, dtype=np.float64) + 0.5) * target
    start = float(np.median(starts))
    start = max(float(outer.left), min(float(outer.right) - target * count, start))
    fitted = [start + target * i for i in range(count + 1)]
    if fitted[0] < outer.left - 1 or fitted[-1] > outer.right + 1:
        return cuts
    if len(fitted) != len(cuts) or any(b <= a for a, b in zip(fitted[:-1], fitted[1:])):
        return cuts
    return fitted


def frame_edge_weight(gap: Gap) -> float:
    if gap.overlap_like:
        return 0.0
    if gap.width <= 0:
        return 0.0
    if gap.method == "edge-pair":
        return max(0.0, min(1.8, gap.score)) * 1.20
    if gap.method == "detected":
        return max(0.0, min(1.5, gap.score))
    return 0.0


def relative_ranges_from_gaps(outer: Box, gaps: list[Gap], count: int) -> list[tuple[float, float]]:
    cuts = [0.0] + [float(gap.center) for gap in gaps] + [float(outer.width)]
    return [(left, right) for left, right in zip(cuts[:-1], cuts[1:])]


def box_list_from_relative_ranges(
    outer: Box,
    ranges: list[tuple[float, float]],
    image_w: int,
    image_h: int,
    bleed_x: int,
    bleed_y: int,
) -> list[Box]:
    out: list[Box] = []
    for left, right in ranges:
        box = Box(outer.left + int(round(left)), outer.top, outer.left + int(round(right)), outer.bottom)
        out.append(box.expand(bleed_x, bleed_y, image_w, image_h))
    return out


def same_frame_size_fit_boxes(
    outer: Box,
    gaps: list[Gap],
    count: int,
    image_w: int,
    image_h: int,
    bleed_x: int,
    bleed_y: int,
) -> tuple[Optional[list[Box]], dict[str, Any]]:
    if count <= 1 or len(gaps) != count - 1 or outer.width <= 1:
        return None, {"used": False, "reason": "not_applicable"}
    left_edges: list[Optional[tuple[float, float]]] = [None] * count
    right_edges: list[Optional[tuple[float, float]]] = [None] * count
    for i, gap in enumerate(gaps):
        weight = frame_edge_weight(gap)
        if weight <= 0 or gap.start is None or gap.end is None:
            continue
        right_edges[i] = (float(gap.start), weight)
        left_edges[i + 1] = (float(gap.end), weight)

    nominal = outer.width / float(count)
    samples: list[tuple[int, float]] = []
    for i, (left, right) in enumerate(zip(left_edges, right_edges), 1):
        if left is None or right is None:
            continue
        width = float(right[0]) - float(left[0])
        if nominal * 0.72 <= width <= nominal * 1.10:
            samples.append((i, width))
    if len(samples) < 2:
        return None, {"used": False, "reason": "too_few_edge_samples", "sample_count": len(samples)}

    widths = np.array([width for _, width in samples], dtype=np.float64)
    target = float(np.median(widths))
    tol = max(3.0, target * 0.035)
    inliers = [(i, width) for i, width in samples if abs(width - target) <= tol]
    if len(inliers) < 2:
        return None, {"used": False, "reason": "edge_samples_disagree", "sample_count": len(samples)}
    sample_indices = [i for i, _ in inliers]
    leading_model_gaps = 0
    for gap in gaps:
        if gap.method in {"grid", "equal"}:
            leading_model_gaps += 1
            continue
        break
    if (
        count == 6
        and len(sample_indices) == 2
        and sample_indices[1] - sample_indices[0] <= 1
        and min(sample_indices) >= 4
        and leading_model_gaps >= 2
    ):
        return None, {
            "used": False,
            "reason": "clustered_late_edge_samples_with_leading_model_gaps",
            "sample_indices": sample_indices,
            "leading_model_gaps": leading_model_gaps,
        }
    target = float(np.median(np.array([width for _, width in inliers], dtype=np.float64)))
    if not (nominal * 0.72 <= target <= nominal * 1.10):
        return None, {"used": False, "reason": "target_width_out_of_range", "target_width": target}

    base_ranges = relative_ranges_from_gaps(outer, gaps, count)
    max_left = max(0.0, float(outer.width) - target)
    fitted: list[tuple[float, float]] = []
    adjusted: list[int] = []
    for i, (base_left, base_right) in enumerate(base_ranges):
        candidates: list[tuple[float, float]] = []
        if left_edges[i] is not None:
            candidates.append((float(left_edges[i][0]), float(left_edges[i][1])))
        if right_edges[i] is not None:
            candidates.append((float(right_edges[i][0]) - target, float(right_edges[i][1])))
        weak_boundary = any(
            0 <= gi < len(gaps) and (gaps[gi].method in {"equal", "grid"} or gaps[gi].overlap_like)
            for gi in (i - 1, i)
        )
        overlap_boundary = any(0 <= gi < len(gaps) and gaps[gi].overlap_like for gi in (i - 1, i))
        base_width = float(base_right) - float(base_left)
        if not candidates and not weak_boundary and abs(base_width - target) <= tol:
            fitted.append((base_left, base_right))
            continue
        if not candidates and overlap_boundary:
            fitted.append((base_left, base_right))
            continue
        base_left_from_center = (float(base_left) + float(base_right) - target) / 2.0
        candidates.append((base_left_from_center, 0.10 if candidates and overlap_boundary else 0.18 if candidates else 1.0))
        if candidates and overlap_boundary:
            candidates.append((base_left, 0.45))
        new_left = weighted_median(candidates)
        new_left = min(max(0.0, new_left), max_left)
        new_right = new_left + target
        if abs(new_left - base_left) > 1.0 or abs(new_right - base_right) > 1.0:
            adjusted.append(i + 1)
        fitted.append((new_left, new_right))
    if not adjusted:
        return None, {
            "used": False,
            "reason": "no_adjustment_needed",
            "target_width": target,
            "sample_indices": [i for i, _ in inliers],
        }
    return box_list_from_relative_ranges(outer, fitted, image_w, image_h, bleed_x, bleed_y), {
        "used": True,
        "target_width": target,
        "sample_indices": [i for i, _ in inliers],
        "sample_widths": [float(width) for _, width in inliers],
        "adjusted_indices": adjusted,
    }


def weighted_median(candidates: list[tuple[float, float]]) -> float:
    ordered = sorted((float(value), max(0.0, float(weight))) for value, weight in candidates)
    if not ordered:
        return 0.0
    total = sum(weight for _, weight in ordered)
    if total <= 0:
        return float(np.median(np.array([value for value, _ in ordered], dtype=np.float64)))
    acc = 0.0
    for value, weight in ordered:
        acc += weight
        if acc >= total / 2.0:
            return value
    return ordered[-1][0]


def score_detection(gray_work: np.ndarray, outer: Box, gaps: list[Gap], boxes: list[Box], count: int, fmt: FilmFormat, strip_mode: str) -> tuple[float, list[str], dict[str, Any]]:
    expected_gaps = max(0, count - 1)
    actual_detected = sum(1 for gap in gaps if gap.method in {"detected", "edge-pair"})
    grid_gaps = sum(1 for gap in gaps if gap.method == "grid")
    detected = actual_detected + grid_gaps
    equal = sum(1 for gap in gaps if gap.method == "equal")
    reliable = sum(1 for gap in gaps if gap.method in {"detected", "edge-pair", "grid"} and gap.score >= 0.28)
    widths = np.array([box.width for box in boxes if box.valid()], dtype=np.float64)
    width_cv = float(widths.std() / max(1.0, widths.mean())) if widths.size else 1.0
    outer_area = float(outer.width * outer.height) / max(1.0, float(gray_work.shape[0] * gray_work.shape[1]))
    p01, p50, p99 = sampled_percentile(gray_work, [1, 50, 99])
    contrast = float(p99 - p01)

    gap_conf = 1.0 if expected_gaps == 0 else detected / float(expected_gaps)
    width_conf = max(0.0, min(1.0, 1.0 - width_cv / 0.030))
    outer_conf = 1.0 if 0.35 <= outer_area <= 0.995 else 0.45
    contrast_conf = 1.0 if contrast >= 35 else max(0.35, contrast / 35.0)
    enough_135_separator_evidence = (
        fmt.name != "135"
        or expected_gaps <= 1
        or (actual_detected >= 2 and equal <= max(2, expected_gaps // 2))
    )

    confidence = 0.40 * gap_conf + 0.30 * width_conf + 0.20 * outer_conf + 0.10 * contrast_conf

    full_geometry_ok = (
        strip_mode == "full"
        and count == fmt.default_count
        and len(boxes) == count
        and (
            width_cv <= (0.040 if fmt.name == "135" else 0.008 if fmt.name == "half" else 0.012)
            or (fmt.name == "135" and detected == expected_gaps)
        )
        and 0.40 <= outer_area <= 0.995
        and outer_area <= 0.94
        and enough_135_separator_evidence
        and (fmt.name in {"135", "half"} or (reliable >= expected_gaps and equal == 0))
    )
    if full_geometry_ok:
        geometry_floor = 0.92 if fmt.name in {"135", "half"} and width_cv <= 0.006 else 0.88
        confidence = max(confidence, geometry_floor)

    reasons: list[str] = []
    if expected_gaps and detected < max(1, expected_gaps // 2) and not full_geometry_ok:
        reasons.append("weak_separators")
    if equal >= max(2, expected_gaps // 2 + 1) and not full_geometry_ok:
        reasons.append("mostly_equal_split")
    if fmt.name == "135" and expected_gaps >= 3 and actual_detected < 2:
        reasons.append("too_few_detected_separators")
    if width_cv > 0.030 and not full_geometry_ok:
        reasons.append("unstable_frame_width")
    if not (0.35 <= outer_area <= 0.995):
        reasons.append("outer_box_uncertain")
    if outer_area > 0.94:
        reasons.append("outer_box_too_large")
    if fmt.family == "120" and detected < expected_gaps:
        reasons.append("120_separator_uncertain")
    if contrast < 35:
        reasons.append("low_contrast")
    if len(boxes) != count:
        reasons.append("frame_count_mismatch")
    if confidence < 0.85 and not reasons:
        reasons.append("low_confidence")

    if strip_mode == "partial" and count < fmt.default_count:
        if count <= 1:
            confidence = min(confidence, 0.78)
            reasons.append("partial_too_ambiguous")
        elif count <= 2 and fmt.default_count >= 6:
            confidence = min(confidence, 0.82)
            reasons.append("partial_too_ambiguous")
        else:
            confidence = min(confidence, 0.84)
        reasons.append("partial_strip_count_candidate")

    if fmt.name == "135" and expected_gaps >= 3:
        if actual_detected < 1:
            confidence = min(confidence, 0.82)
        elif actual_detected < 2:
            confidence = min(confidence, 0.82)
        elif equal >= max(2, expected_gaps // 2 + 1):
            confidence = min(confidence, 0.84)
    if outer_area > 0.94:
        confidence = min(confidence, 0.82)

    detail = {
        "detected_gaps": detected,
        "actual_detected_gaps": actual_detected,
        "grid_gaps": grid_gaps,
        "reliable_gaps": reliable,
        "equal_gaps": equal,
        "width_cv": width_cv,
        "outer_area_ratio": outer_area,
        "image_quality": {
            "p01": float(p01),
            "p50": float(p50),
            "p99": float(p99),
            "range_1_99": contrast,
        },
        "contrast_1_99": contrast,
        "full_geometry_ok": full_geometry_ok,
    }
    return float(max(0.0, min(1.0, confidence))), sorted(set(reasons)), detail


def build_detection_for_outer(
    gray: np.ndarray,
    config: Config,
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    outer: Box,
    offset_fraction: float = 0.0,
    outer_candidate_name: str = "unknown",
    cache: Optional[AnalysisCache] = None,
    allow_outer_refine: bool = True,
) -> Detection:
    h, w = gray.shape
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0 or outer.width <= 0:
        outer = Box(0, 0, ww, wh)
        crop = gray_work
    profile = cached_separator_profile(cache, gray_work, outer)
    if strip_mode == "partial" and count < fmt.default_count:
        pitch = outer.width / float(max(1, fmt.default_count))
        total_width = pitch * count
        origin = max(0.0, min(float(outer.width) - total_width, (float(outer.width) - total_width) * offset_fraction))
    else:
        pitch = outer.width / float(max(1, count))
        origin = 0.0
    gaps = [find_gap(profile, origin + pitch * i, pitch, i) for i in range(1, count)]
    if strip_mode == "full" and fmt.name == "half" and count == fmt.default_count:
        gaps = [
            Gap(i, origin + pitch * i, float(profile[min(len(profile) - 1, max(0, int(round(origin + pitch * i))))]), "equal")
            for i in range(1, count)
        ]
    edge_refine_detail: dict[str, Any] = {"used": False, "reason": "disabled"}
    if strip_mode == "full" and fmt.name == "135" and count > 1:
        gaps, edge_refine_detail = refine_gaps_by_edge_pairs(crop, gaps, count, cache, outer)
    gaps, grid_detail = apply_robust_grid(gaps, origin, pitch, strip_mode)
    if allow_outer_refine and strip_mode == "full" and bool(grid_detail.get("grid_used", False)):
        model_origin = float(grid_detail.get("grid_origin", 0.0))
        model_pitch = float(grid_detail.get("grid_pitch", pitch))
        proposed_left = int(round(outer.left + model_origin))
        proposed_right = int(round(outer.left + model_origin + model_pitch * count))
        max_shift = max(8, int(round(pitch * 0.08)))
        width_change = abs((proposed_right - proposed_left) - outer.width) / max(1.0, float(outer.width))
        if (
            proposed_right > proposed_left
            and abs(proposed_left - outer.left) <= max_shift
            and abs(proposed_right - outer.right) <= max_shift
            and width_change <= 0.12
            and 0 <= proposed_left < proposed_right <= ww
        ):
            outer = Box(proposed_left, outer.top, proposed_right, outer.bottom)
            crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
            profile = cached_separator_profile(cache, gray_work, outer)
            pitch = outer.width / float(max(1, count))
            origin = 0.0
            gaps = [find_gap(profile, pitch * i, pitch, i) for i in range(1, count)]
            if strip_mode == "full" and fmt.name == "135" and count > 1:
                gaps, edge_refine_detail = refine_gaps_by_edge_pairs(crop, gaps, count, cache, outer)
            gaps, grid_detail = apply_robust_grid(gaps, origin, pitch, strip_mode)
            grid_detail["outer_refined"] = True
    overlap_detail: dict[str, Any] = {"used": False, "reason": "disabled"}
    if strip_mode == "full" and fmt.name == "135":
        gaps, overlap_detail = mark_overlap_like_gaps(gray_work, outer, gaps, pitch, fmt, strip_mode, count, cache)
    use_simple_size_fit = not (strip_mode == "full" and fmt.name == "135")
    boxes_work_for_score = frame_boxes_from_gaps(
        outer,
        gaps,
        count,
        ww,
        wh,
        config.bleed_x,
        config.bleed_y,
        origin=origin,
        pitch=pitch,
        apply_size_fit=use_simple_size_fit,
    )
    frame_size_detail: dict[str, Any] = {"used": False, "reason": "disabled"}
    fitted_boxes_work: Optional[list[Box]] = None
    if strip_mode == "full" and fmt.name == "135":
        fitted_boxes_work, frame_size_detail = same_frame_size_fit_boxes(outer, gaps, count, ww, wh, config.bleed_x, config.bleed_y)
    boxes_work = fitted_boxes_work if fitted_boxes_work is not None else boxes_work_for_score
    boxes = [map_work_box(box, config.layout, w, h) for box in boxes_work]
    outer_original = map_work_box(outer, config.layout, w, h)
    confidence, reasons, detail = score_detection(gray_work, outer, gaps, boxes_work, count, fmt, strip_mode)
    detail.update(
        {
            "candidate_count": count,
            "offset_fraction": float(offset_fraction),
            "origin": float(origin),
            "pitch": float(pitch),
            "layout": config.layout,
            "outer_candidate": outer_candidate_name,
            "work_outer": asdict(outer),
            "grid": grid_detail,
            "grid_residual": grid_detail.get("grid_residual"),
            "grid_used": bool(grid_detail.get("grid_used", False)),
            "edge_refine": edge_refine_detail,
            "frame_size_fit": frame_size_detail,
            "overlap_like_gaps": overlap_detail,
            "partial_edge_hint": partial_edge_hint(profile, origin, pitch, count) if strip_mode == "partial" else {},
            "gap_centers": [gap.center for gap in gaps],
            "gap_scores": [gap.score for gap in gaps],
            "gap_methods": [gap.method for gap in gaps],
            "gap_overlap_like": [bool(gap.overlap_like) for gap in gaps],
        }
    )
    return Detection(fmt.name, config.layout, strip_mode, count, outer_original, boxes, gaps, confidence, reasons, detail)


def detection_rank(detection: Detection, threshold: float) -> tuple[int, float, int, float]:
    return (
        1 if detection.confidence >= threshold else 0,
        float(detection.confidence),
        int(detection.count),
        -float(detection.detail.get("width_cv", 1.0)),
    )


def detect_for_count(
    gray: np.ndarray,
    config: Config,
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
) -> Detection:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    outer_candidates = detect_outer_candidates(gray_work)
    candidates = [
        build_detection_for_outer(gray, config, fmt, count, strip_mode, candidate.box, offset_fraction, candidate.name, cache=cache)
        for candidate in outer_candidates
    ]
    best = max(candidates, key=lambda d: detection_rank(d, config.confidence_threshold))
    areas = [candidate.box.width * candidate.box.height for candidate in outer_candidates if candidate.box.valid()]
    if areas:
        best.detail["outer_candidate_count"] = len(outer_candidates)
        best.detail["outer_area_spread_ratio"] = (max(areas) - min(areas)) / max(1.0, float(max(areas)))
        best.detail["outer_candidates"] = [
            {"name": candidate.name, "box": asdict(candidate.box)}
            for candidate in outer_candidates
        ]
    return best


def translate_box(box: Box, dx: int, dy: int) -> Box:
    return Box(box.left + dx, box.top + dy, box.right + dx, box.bottom + dy)


def split_dual_135_lanes(gray_work: np.ndarray) -> list[Box]:
    h, w = gray_work.shape
    content = bbox_from_mask(gray_work < 246, min_row_fraction=0.010, min_col_fraction=0.010)
    if content is None or not content.valid():
        content = Box(0, 0, w, h)
    split_y = int(round((content.top + content.bottom) / 2.0))
    guard = max(2, min(80, int(round(content.height * 0.006))))
    lanes = [
        Box(content.left, content.top, content.right, max(content.top + 1, split_y - guard)).clamp(w, h),
        Box(content.left, min(content.bottom - 1, split_y + guard), content.right, content.bottom).clamp(w, h),
    ]
    if any(not lane.valid() or lane.height < max(20, h * 0.10) for lane in lanes):
        split_y = h // 2
        lanes = [Box(0, 0, w, split_y), Box(0, split_y, w, h)]
    return lanes


def detect_dual_135_lane(
    gray: np.ndarray,
    config: Config,
    lane: Box,
    lane_index: int,
    cache: AnalysisCache,
) -> Optional[Detection]:
    lane_crop = cache.gray_work[lane.top:lane.bottom, lane.left:lane.right]
    if lane_crop.size == 0:
        return None
    fmt_135 = FORMATS["135"]
    lane_config = replace(config, film_format="135", count=fmt_135.default_count, count_override=fmt_135.default_count)
    candidates: list[Detection] = []
    for outer_candidate in detect_outer_candidates(lane_crop):
        lane_outer = translate_box(outer_candidate.box, lane.left, lane.top)
        raw = build_detection_for_outer(
            gray,
            lane_config,
            fmt_135,
            fmt_135.default_count,
            "full",
            lane_outer,
            0.0,
            f"135_dual_lane_{lane_index}_{outer_candidate.name}",
            cache=cache,
        )
        calibrated = calibrate_v2_candidate(gray, raw, lane_config, fmt_135, "separator", cache)
        calibrated.detail["dual_lane_index"] = lane_index
        calibrated.detail["dual_lane_work_box"] = asdict(lane)
        candidates.append(calibrated)
    if not candidates:
        return None
    best = max(candidates, key=lambda d: v2_candidate_rank(d, config.confidence_threshold))
    content_detail = content_evidence_detail(gray, best, cache)
    outer_alignment = outer_content_alignment_detail(gray, best, cache)
    best.detail["content_evidence"] = content_detail
    best.detail["outer_content_alignment"] = outer_alignment
    if bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            best.confidence = min(best.confidence, 0.82)
            best.review_reasons.append("content_aspect_conflict")
        elif support in {"low_content", "weak"} and best.confidence >= config.confidence_threshold:
            best.confidence = min(best.confidence, 0.84)
            best.review_reasons.append("content_evidence_weak")
    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        best.confidence = min(best.confidence, 0.84)
        best.review_reasons.append("outer_content_bbox_mismatch")
    best.review_reasons = sorted(set(best.review_reasons))
    return best


def unsupported_dual_135_partial_detection(gray: np.ndarray, config: Config) -> Detection:
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    outer = Box(0, 0, ww, wh)
    source_h, source_w = gray.shape
    return Detection(
        "135-dual",
        config.layout,
        config.strip_mode,
        12,
        map_work_box(outer, config.layout, source_w, source_h),
        [],
        [],
        0.0,
        ["135_dual_partial_not_supported", "needs_manual_review"],
        {
            "analysis_source": "unsupported_mode",
            "candidate_count": 0,
            "layout": config.layout,
            "work_outer": asdict(outer),
            "v2_competition": {
                "candidate_count": 0,
                "formats": ["135-dual"],
                "selected_candidate": {
                    "format": "135-dual",
                    "count": 12,
                    "strip_mode": config.strip_mode,
                    "confidence": 0.0,
                    "review_reasons": ["135_dual_partial_not_supported", "needs_manual_review"],
                },
                "selection_override": "unsupported_135_dual_partial",
                "top_candidates": [],
            },
        },
    )


def choose_detection_135_dual(gray: np.ndarray, config: Config, cache: AnalysisCache) -> Detection:
    if config.strip_mode != "full":
        return unsupported_dual_135_partial_detection(gray, config)

    gray_work = cache.gray_work
    source_h, source_w = gray.shape
    lanes = split_dual_135_lanes(gray_work)
    lane_detections = [
        detect_dual_135_lane(gray, config, lane, index, cache)
        for index, lane in enumerate(lanes, start=1)
    ]
    if any(detection is None for detection in lane_detections):
        detection = hard_fallback_detection(gray, config, FORMATS["135-dual"])
        detection.review_reasons.append("135_dual_lane_detection_failed")
        detection.review_reasons = sorted(set(detection.review_reasons))
        return detection

    confirmed_lanes = [detection for detection in lane_detections if detection is not None]
    lane_work_outers = [
        box_from_dict(detection.detail["work_outer"])
        for detection in confirmed_lanes
        if isinstance(detection.detail.get("work_outer"), dict)
    ]
    if len(lane_work_outers) != 2:
        detection = hard_fallback_detection(gray, config, FORMATS["135-dual"])
        detection.review_reasons.append("135_dual_outer_detection_failed")
        detection.review_reasons = sorted(set(detection.review_reasons))
        return detection

    combined_work_outer = Box(
        min(box.left for box in lane_work_outers),
        min(box.top for box in lane_work_outers),
        max(box.right for box in lane_work_outers),
        max(box.bottom for box in lane_work_outers),
    )
    frames = [box for detection in confirmed_lanes for box in detection.frames]
    gaps: list[Gap] = []
    for lane_number, detection in enumerate(confirmed_lanes, start=1):
        lane_work_outer = box_from_dict(detection.detail["work_outer"])
        for gap in detection.gaps:
            gaps.append(
                Gap(
                    index=(lane_number - 1) * 6 + int(gap.index),
                    center=float(gap.center),
                    score=float(gap.score),
                    method=gap.method,
                    start=gap.start,
                    end=gap.end,
                    lane_box=asdict(lane_work_outer),
                    overlap_like=bool(gap.overlap_like),
                )
            )

    lane_confidences = [float(detection.confidence) for detection in confirmed_lanes]
    confidence = min(lane_confidences)
    review_reasons = sorted(set(reason for detection in confirmed_lanes for reason in detection.review_reasons))
    if any(conf < config.confidence_threshold for conf in lane_confidences):
        confidence = min(confidence, 0.84)
        review_reasons.append("135_dual_lane_below_threshold")
    if len(frames) != 12:
        confidence = min(confidence, 0.82)
        review_reasons.append("frame_count_mismatch")

    lane_summaries = [
        {
            "lane": index,
            "lane_format": "135",
            "lane_count": 6,
            "total_format": "135-dual",
            "total_count": 12,
            "confidence": float(detection.confidence),
            "review_reasons": list(detection.review_reasons),
            "work_outer": detection.detail.get("work_outer"),
            "content_evidence": detection.detail.get("content_evidence", {}),
            "outer_content_alignment": detection.detail.get("outer_content_alignment", {}),
            "v2_candidate": detection.detail.get("v2_candidate", {}),
        }
        for index, detection in enumerate(confirmed_lanes, start=1)
    ]
    detail = {
        "analysis_source": "135_dual_parallel_lanes",
        "layout": config.layout,
        "candidate_count": 12,
        "work_outer": asdict(combined_work_outer),
        "dual_lane_work_boxes": [asdict(lane) for lane in lanes],
        "dual_lane_detections": lane_summaries,
        "gap_centers": [gap.center for gap in gaps],
        "gap_scores": [gap.score for gap in gaps],
        "gap_methods": [gap.method for gap in gaps],
        "v2_competition": {
            "candidate_count": 2,
            "formats": ["135-dual"],
            "selected_candidate": {
                "format": "135-dual",
                "count": 12,
                "strip_mode": "full",
                "confidence": float(confidence),
                "review_reasons": sorted(set(review_reasons)),
            },
            "selection_override": None,
            "top_candidates": lane_summaries,
        },
    }
    outer_original = map_work_box(combined_work_outer, config.layout, source_w, source_h)
    return Detection(
        "135-dual",
        config.layout,
        "full",
        12,
        outer_original,
        frames,
        gaps,
        float(max(0.0, min(1.0, confidence))),
        sorted(set(review_reasons)),
        detail,
    )


def partial_candidates(fmt: FilmFormat, seed: Optional[Detection]) -> tuple[int, ...]:
    default = fmt.default_count
    candidates: set[int] = {default, max(1, default - 1), max(1, default - 2), 1}
    if default >= 3:
        candidates.add(2)
    if default >= 6:
        candidates.add(max(1, default // 2))
    if seed is not None:
        detected = int(seed.detail.get("detected_gaps", 0))
        for count in (detected, detected + 1, detected + 2):
            if count >= 1:
                candidates.add(count)
    return tuple(sorted((c for c in candidates if c in fmt.allowed_counts), reverse=True))


def partial_offsets(fmt: FilmFormat, count: int) -> tuple[float, ...]:
    if count >= fmt.default_count:
        return (0.0,)
    return (0.0, 0.25, 0.5, 0.75, 1.0)


def partial_edge_hint(profile: np.ndarray, origin: float, pitch: float, count: int) -> dict[str, Any]:
    if profile.size == 0 or count <= 0:
        return {}
    span_start = int(max(0, min(len(profile) - 1, round(origin))))
    span_end = int(max(0, min(len(profile), round(origin + pitch * count))))
    left_window = profile[span_start:min(len(profile), span_start + max(8, int(pitch * 0.18)))]
    right_window = profile[max(0, span_end - max(8, int(pitch * 0.18))):span_end]
    return {
        "left_edge_score": float(left_window.max()) if left_window.size else 0.0,
        "right_edge_score": float(right_window.max()) if right_window.size else 0.0,
        "span_start": span_start,
        "span_end": span_end,
    }


def content_is_ambiguous(detection: Detection) -> bool:
    return bool(CONTENT_AMBIGUITY_REASONS.intersection(detection.review_reasons))


def separator_hard_evidence_ok(detection: Detection, threshold: float) -> tuple[bool, dict[str, Any]]:
    expected = max(0, int(detection.count) - 1)
    actual = int(detection.detail.get("actual_detected_gaps", 0))
    grid = int(detection.detail.get("grid_gaps", 0))
    equal = int(detection.detail.get("equal_gaps", 0))
    hard = actual
    hard_indexes = [
        int(gap.index)
        for gap in detection.gaps
        if gap.method in {"detected", "edge-pair"}
    ]
    leading_grid_scores: list[float] = []
    for gap in detection.gaps:
        if gap.method != "grid":
            break
        leading_grid_scores.append(float(gap.score))
    hard_adjacent_late = False
    if hard_indexes:
        expected_sequence = list(
            range(max(hard_indexes) - len(hard_indexes) + 1, max(hard_indexes) + 1)
        )
        hard_adjacent_late = hard_indexes == expected_sequence and min(hard_indexes) >= 4
    leading_grid_failure = (
        detection.film_format == "135"
        and detection.strip_mode == "full"
        and expected >= 5
        and len(leading_grid_scores) >= 3
        and all(score < 0.35 for score in leading_grid_scores[:3])
        and sum(1 for score in leading_grid_scores[:3] if score < 0.12) >= 2
        and len(hard_indexes) <= 2
        and hard_adjacent_late
    )

    if expected == 0:
        ok = detection.confidence >= threshold
        reason = "single_frame_no_separator_needed" if ok else "single_frame_low_confidence"
    elif detection.confidence < threshold:
        ok = False
        reason = "separator_below_threshold"
    elif leading_grid_failure:
        ok = False
        reason = "135_leading_grid_separator_failure"
    elif detection.film_format == "135":
        needed = min(expected, 2)
        ok = hard >= needed and equal <= max(2, expected // 2)
        reason = "135_hard_separator_support" if ok else "135_separator_support_weak"
    elif detection.film_format == "half":
        ok = detection.confidence >= threshold and equal <= expected
        reason = "half_geometry_support" if ok else "half_separator_support_weak"
    else:
        needed = max(1, expected)
        ok = hard >= needed
        reason = "120_hard_separator_support" if ok else "120_separator_support_weak"

    return ok, {
        "ok": ok,
        "reason": reason,
        "expected_gaps": expected,
        "hard_gaps": hard,
        "actual_detected_gaps": actual,
        "grid_gaps": grid,
        "equal_gaps": equal,
        "hard_gap_indexes": hard_indexes,
        "leading_grid_scores": leading_grid_scores,
        "leading_grid_separator_failure": bool(leading_grid_failure),
        "separator_confidence": float(detection.confidence),
    }


def content_only_partial_can_pass(detection: Detection, threshold: float, fmt: FilmFormat) -> bool:
    min_partial_count = 3 if fmt.default_count >= 6 else 2
    return (
        detection.strip_mode == "partial"
        and detection.count < fmt.default_count
        and detection.count >= min_partial_count
        and detection.confidence >= max(threshold, CONTENT_ONLY_PARTIAL_PASS_MIN_CONFIDENCE)
        and not content_is_ambiguous(detection)
    )


def content_support_score(detail: dict[str, Any]) -> float:
    if not bool(detail.get("used", False)):
        return 0.0
    mean_score = min(1.0, float(detail.get("median_mean", 0.0)) / 0.16)
    coverage_score = min(1.0, float(detail.get("median_coverage", 0.0)) / 0.22)
    aspect_error = detail.get("max_aspect_error")
    aspect_score = 0.75 if aspect_error is None else max(0.0, min(1.0, 1.0 - float(aspect_error) / 0.22))
    support = str(detail.get("support", ""))
    support_gate = {"ok": 1.0, "weak": 0.72, "low_content": 0.58, "aspect_conflict": 0.35}.get(support, 0.50)
    return max(0.0, min(1.0, (0.42 * coverage_score + 0.40 * mean_score + 0.18 * aspect_score) * support_gate))


def geometry_support_score(detection: Detection, content_detail: dict[str, Any]) -> float:
    width_cv = float(detection.detail.get("width_cv", 0.0))
    if width_cv <= 0.0:
        widths = np.array([box.width for box in detection.frames if box.valid()], dtype=np.float64)
        width_cv = float(widths.std() / max(1.0, widths.mean())) if widths.size else 1.0
    width_score = max(0.0, min(1.0, 1.0 - width_cv / 0.040))
    outer_area = float(detection.detail.get("outer_area_ratio", 0.70))
    outer_score = 1.0 if 0.35 <= outer_area <= 0.94 else 0.55
    aspect_error = content_detail.get("max_aspect_error")
    aspect_score = 0.80 if aspect_error is None else max(0.0, min(1.0, 1.0 - float(aspect_error) / 0.22))
    count_score = 1.0 if len(detection.frames) == detection.count else 0.0
    return max(0.0, min(1.0, 0.34 * width_score + 0.24 * outer_score + 0.26 * aspect_score + 0.16 * count_score))


def separator_support_score(detection: Detection, hard_detail: dict[str, Any]) -> float:
    expected = max(0, int(hard_detail.get("expected_gaps", 0)))
    if expected == 0:
        return 1.0 if detection.confidence >= 0.85 else min(0.75, detection.confidence)
    hard = int(hard_detail.get("hard_gaps", 0))
    grid = int(hard_detail.get("grid_gaps", 0))
    equal = int(hard_detail.get("equal_gaps", 0))
    hard_ratio = min(1.0, hard / float(max(1, expected)))
    model_ratio = min(1.0, (hard + 0.35 * grid + 0.12 * equal) / float(max(1, expected)))
    return max(0.0, min(1.0, 0.78 * hard_ratio + 0.22 * model_ratio))


def candidate_counts_for_format(config: Config, fmt: FilmFormat) -> list[tuple[int, str, tuple[float, ...]]]:
    def v2_offsets(count: int) -> tuple[float, ...]:
        return partial_offsets(fmt, count)

    if config.strip_mode == "full":
        return [(config.count, "full", (0.0,))]
    if config.strip_mode == "partial":
        if config.count_override is not None:
            return [(config.count, "partial", v2_offsets(config.count))]
        return [
            (count, "partial", v2_offsets(count))
            for count in partial_candidates(fmt, None)
            if count < fmt.default_count
        ] or [(1, "partial", partial_offsets(fmt, 1))]
    raise ValueError(f"Unsupported strip mode: {config.strip_mode}")


def calibrate_v2_candidate(
    gray: np.ndarray,
    detection: Detection,
    config: Config,
    fmt: FilmFormat,
    source: str,
    cache: Optional[AnalysisCache] = None,
) -> Detection:
    candidate = replace(
        detection,
        review_reasons=list(detection.review_reasons),
        detail=dict(detection.detail),
    )
    content_detail = content_evidence_detail(gray, candidate, cache)
    hard_ok, hard_detail = separator_hard_evidence_ok(candidate, config.confidence_threshold)
    content_score = content_support_score(content_detail)
    geometry_score = geometry_support_score(candidate, content_detail)
    separator_score = separator_support_score(candidate, hard_detail) if source == "separator" else 0.0
    source_bias = 0.03 if source == "separator" else 0.0
    joint_score = 0.34 * geometry_score + 0.33 * content_score + 0.33 * separator_score + source_bias
    joint_score = max(0.0, min(1.0, joint_score))
    support = str(content_detail.get("support", ""))
    reasons = list(candidate.review_reasons)

    if source == "separator" and not hard_ok:
        reasons.append("separator_hard_evidence_weak")
    if support == "aspect_conflict":
        reasons.append("content_aspect_conflict")
    elif support == "low_content":
        reasons.append("content_evidence_weak")
    elif support == "weak":
        reasons.append("content_evidence_weak")
    if source == "content" and not content_only_partial_can_pass(candidate, config.confidence_threshold, fmt):
        reasons.append("content_only_not_enough_for_auto")

    confidence = max(float(candidate.confidence), joint_score)
    hard_reasons = HARD_REVIEW_REASONS.intersection(reasons)
    auto_gate = False
    if source == "separator":
        auto_gate = hard_ok and support == "ok" and not hard_reasons
    elif source == "content":
        auto_gate = content_only_partial_can_pass(candidate, config.confidence_threshold, fmt)

    if not auto_gate:
        cap = 0.82 if candidate.strip_mode == "partial" else 0.84
        confidence = min(confidence, cap)
        reasons.append("v2_auto_gate_not_satisfied")
    else:
        confidence = max(confidence, config.confidence_threshold + min(0.10, joint_score * 0.08))

    candidate.confidence = float(max(0.0, min(1.0, confidence)))
    candidate.review_reasons = sorted(set(reasons))
    candidate.detail["analysis_source"] = f"v2_{source}_candidate"
    candidate.detail["content_evidence"] = content_detail
    candidate.detail["v2_candidate"] = {
        "source": source,
        "joint_score": float(joint_score),
        "auto_gate": bool(auto_gate),
        "geometry_score": float(geometry_score),
        "separator_score": float(separator_score),
        "content_score": float(content_score),
        "content_support": support,
        "separator_hard_evidence": hard_detail,
    }
    return candidate


def v2_candidate_rank(detection: Detection, threshold: float) -> tuple[int, float, int, float]:
    candidate = detection.detail.get("v2_candidate", {})
    joint = float(candidate.get("joint_score", 0.0)) if isinstance(candidate, dict) else 0.0
    return (
        1 if detection.confidence >= threshold else 0,
        float(detection.confidence),
        int(detection.count),
        joint,
    )


def hard_fallback_detection(gray: np.ndarray, config: Config, fmt: FilmFormat) -> Detection:
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    count = max(1, int(config.count))
    outer = Box(0, 0, ww, wh)
    if count > 1:
        pitch = ww / float(count)
        gaps = [Gap(i, pitch * i, 0.0, "equal") for i in range(1, count)]
    else:
        pitch = float(ww)
        gaps = []
    boxes_work = frame_boxes_from_gaps(outer, gaps, count, ww, wh, config.bleed_x, config.bleed_y, origin=0.0, pitch=pitch)
    source_h, source_w = gray.shape
    boxes = [map_work_box(box, config.layout, source_w, source_h) for box in boxes_work]
    outer_original = map_work_box(outer, config.layout, source_w, source_h)
    return Detection(
        fmt.name,
        config.layout,
        config.strip_mode,
        count,
        outer_original,
        boxes,
        gaps,
        0.0,
        ["hard_fallback_no_v2_candidates", "needs_manual_review"],
        {
            "analysis_source": "hard_fallback",
            "candidate_count": count,
            "layout": config.layout,
            "work_outer": asdict(outer),
            "pitch": float(pitch),
            "gap_centers": [gap.center for gap in gaps],
            "gap_scores": [gap.score for gap in gaps],
            "gap_methods": [gap.method for gap in gaps],
            "v2_competition": {
                "candidate_count": 0,
                "formats": [fmt.name],
                "selected_candidate": {
                    "format": fmt.name,
                    "count": count,
                    "strip_mode": config.strip_mode,
                    "confidence": 0.0,
                    "review_reasons": ["hard_fallback_no_v2_candidates", "needs_manual_review"],
                },
                "selection_override": "hard_fallback_no_v2_candidates",
                "top_candidates": [],
            },
        },
    )


def choose_detection_v2(gray: np.ndarray, config: Config, fmt: FilmFormat, cache: Optional[AnalysisCache] = None) -> Detection:
    candidates: list[Detection] = []
    cache = cache if cache is not None and cache.layout == config.layout else make_analysis_cache(gray, config.layout)
    if fmt.name == "135-dual":
        return choose_detection_135_dual(gray, config, cache)
    format_candidates = [fmt]
    for fmt in format_candidates:
        count_specs = candidate_counts_for_format(config, fmt)
        for count, strip_mode, offsets in count_specs:
            if count not in fmt.allowed_counts:
                continue
            for offset in offsets:
                separator = detect_for_count(gray, config, fmt, count, strip_mode, offset, cache)
                separator_candidate = calibrate_v2_candidate(gray, separator, config, fmt, "separator", cache)
                candidates.append(separator_candidate)
                separator_auto_gate = bool(
                    separator_candidate.detail.get("v2_candidate", {}).get("auto_gate", False)
                )
                if strip_mode == "full" and separator_auto_gate and separator_candidate.confidence >= config.confidence_threshold:
                    separator_candidate.detail["content_candidate_skipped"] = "separator_auto_gate_passed"
                    continue
                if strip_mode == "full":
                    separator_candidate.detail["content_candidate_skipped"] = "full_strip_uses_content_validation_only"
                    continue
                content = content_detection_for_count(gray, config, fmt, count, strip_mode, offset, cache)
                if content is not None:
                    candidates.append(calibrate_v2_candidate(gray, content, config, fmt, "content", cache))

    if not candidates:
        return hard_fallback_detection(gray, config, fmt)

    candidates = sorted(candidates, key=lambda d: v2_candidate_rank(d, config.confidence_threshold), reverse=True)
    best = candidates[0]
    selected_by_full_guard = False
    if best.strip_mode == "partial":
        best_full = next(
            (
                candidate
                for candidate in candidates
                if candidate.film_format == best.film_format
                and candidate.strip_mode == "full"
                and candidate.count == FORMATS[candidate.film_format].default_count
                and candidate.confidence >= PARTIAL_FULL_COMPETE_MIN_CONFIDENCE
            ),
            None,
        )
        if best_full is not None:
            best_full.review_reasons.append("partial_competes_with_plausible_full_strip")
            best_full.review_reasons = sorted(set(best_full.review_reasons))
            best_full.detail["partial_best"] = {
                "count": int(best.count),
                "confidence": float(best.confidence),
                "review_reasons": list(best.review_reasons),
                "v2_candidate": best.detail.get("v2_candidate", {}),
            }
            best = best_full
            selected_by_full_guard = True
    second = next((candidate for candidate in candidates if candidate is not best), None)
    competition = [
        {
            "rank": index,
            "selected": candidate is best,
            "format": candidate.film_format,
            "count": int(candidate.count),
            "strip_mode": candidate.strip_mode,
            "confidence": float(candidate.confidence),
            "review_reasons": list(candidate.review_reasons),
            "v2_candidate": candidate.detail.get("v2_candidate", {}),
        }
        for index, candidate in enumerate(candidates[:8], start=1)
    ]
    best.detail["v2_competition"] = {
        "candidate_count": len(candidates),
        "formats": [fmt.name for fmt in format_candidates],
        "selected_candidate": {
            "format": best.film_format,
            "count": int(best.count),
            "strip_mode": best.strip_mode,
            "confidence": float(best.confidence),
            "review_reasons": list(best.review_reasons),
            "v2_candidate": best.detail.get("v2_candidate", {}),
        },
        "selection_override": "partial_competes_with_plausible_full_strip" if selected_by_full_guard else None,
        "top_candidates": competition,
    }
    if second is not None:
        margin = float(best.confidence) - float(second.confidence)
        best.detail["v2_competition"]["margin_to_second"] = margin
        second_close = margin < 0.04
        partial_full_conflict = (
            best.strip_mode != second.strip_mode
            and min(best.confidence, second.confidence) >= config.confidence_threshold
        )
        if (
            best.confidence >= config.confidence_threshold
            and not selected_by_full_guard
            and (second_close or partial_full_conflict)
        ):
            best.confidence = min(best.confidence, 0.84)
            best.review_reasons.append("v2_candidate_competition_uncertain")
            best.review_reasons = sorted(set(best.review_reasons))
    return best


def fit_line(points: list[tuple[float, float]]) -> Optional[dict[str, Any]]:
    if len(points) < 4:
        return None
    x = np.array([p[0] for p in points], dtype=np.float64)
    y = np.array([p[1] for p in points], dtype=np.float64)
    slope, intercept = np.polyfit(x, y, 1)
    residuals = np.abs(y - (slope * x + intercept))
    median_residual = float(np.median(residuals)) if residuals.size else 0.0
    tolerance = max(2.0, median_residual * 3.0)
    inliers = residuals <= tolerance
    if int(inliers.sum()) >= 4 and int(inliers.sum()) < len(points):
        slope, intercept = np.polyfit(x[inliers], y[inliers], 1)
        residuals = np.abs(y[inliers] - (slope * x[inliers] + intercept))
        median_residual = float(np.median(residuals)) if residuals.size else 0.0
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "inliers": int(inliers.sum()),
        "samples": len(points),
        "median_residual": median_residual,
    }


def fit_edge_angle(gray: np.ndarray, layout: str) -> tuple[float, dict[str, Any]]:
    work = work_gray(gray, layout)
    h, w = work.shape
    mask = work < 245
    outer = bbox_from_mask(mask, 0.01, 0.01)
    if outer is None or outer.width < 100:
        return 0.0, {"reason": "no_outer"}

    xs = np.linspace(outer.left, outer.right - 1, num=min(24, max(6, outer.width // 350))).astype(int)
    top_points: list[tuple[float, float]] = []
    bottom_points: list[tuple[float, float]] = []
    for x in xs:
        col = mask[:, x]
        ys = np.flatnonzero(col)
        if ys.size < max(10, h * 0.05):
            continue
        top_points.append((float(x), float(ys[0])))
        bottom_points.append((float(x), float(ys[-1])))

    top_fit = fit_line(top_points)
    bottom_fit = fit_line(bottom_points)
    fits = [fit for fit in (top_fit, bottom_fit) if fit is not None]
    if not fits:
        return 0.0, {"reason": "not_enough_points", "top_samples": len(top_points), "bottom_samples": len(bottom_points)}

    slopes = [float(fit["slope"]) for fit in fits]
    if len(slopes) == 2 and abs(slopes[0] - slopes[1]) > 0.006:
        return 0.0, {
            "reason": "top_bottom_disagree",
            "top": top_fit,
            "bottom": bottom_fit,
            "slope_delta": abs(slopes[0] - slopes[1]),
        }
    if any(float(fit["median_residual"]) > max(3.0, h * 0.003) for fit in fits):
        return 0.0, {"reason": "high_residual", "top": top_fit, "bottom": bottom_fit}

    slope = float(np.median(slopes))
    angle = math.degrees(math.atan(slope))
    if layout == "vertical":
        angle = -angle
    return angle, {
        "slope": slope,
        "top": top_fit,
        "bottom": bottom_fit,
        "samples": len(top_points) + len(bottom_points),
    }


def deskew_quality(detail: dict[str, Any]) -> float:
    if detail.get("reason"):
        return -1.0
    fits = [detail.get("top"), detail.get("bottom")]
    score = 0.0
    for fit in fits:
        if isinstance(fit, dict):
            score += float(fit.get("inliers", 0)) * 2.0
            score -= float(fit.get("median_residual", 10.0))
    return score


def choose_deskew_angle(gray: np.ndarray, layout: str, analysis: str) -> tuple[float, dict[str, Any]]:
    base_angle, base_detail = fit_edge_angle(gray, layout)
    base_detail["source"] = "base"
    if analysis == "off":
        return base_angle, base_detail
    if analysis == "auto" and deskew_quality(base_detail) >= 8.0:
        base_detail["enhanced_candidate"] = {"skipped": "auto_base_quality_ok"}
        return base_angle, base_detail
    enhanced_gray = make_analysis_gray(gray)
    enhanced_angle, enhanced_detail = fit_edge_angle(enhanced_gray, layout)
    enhanced_detail["source"] = "enhanced"
    if deskew_quality(enhanced_detail) > deskew_quality(base_detail) + 3.0:
        enhanced_detail["base_candidate"] = base_detail
        return enhanced_angle, enhanced_detail
    base_detail["enhanced_candidate"] = enhanced_detail
    return base_angle, base_detail


def dtype_white(dtype: np.dtype) -> int | float:
    if np.issubdtype(dtype, np.integer):
        return int(np.iinfo(dtype).max)
    return 1.0


def rotate_array_expand(arr: np.ndarray, angle_degrees: float, axes: str) -> np.ndarray:
    if abs(angle_degrees) < 1e-9:
        return arr
    if axes == "SYX":
        rotated = rotate_array_expand(np.moveaxis(arr, 0, -1), angle_degrees, "YXS")
        return np.moveaxis(rotated, -1, 0)
    angle = math.radians(angle_degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    h, w = spatial_shape(arr)
    corners = np.array(
        [[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]],
        dtype=np.float64,
    )
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0
    centered = corners - np.array([cx, cy])
    rot = np.column_stack(
        [
            centered[:, 0] * cos_a - centered[:, 1] * sin_a,
            centered[:, 0] * sin_a + centered[:, 1] * cos_a,
        ]
    )
    min_xy = rot.min(axis=0)
    max_xy = rot.max(axis=0)
    out_w = int(math.ceil(max_xy[0] - min_xy[0] + 1))
    out_h = int(math.ceil(max_xy[1] - min_xy[1] + 1))
    out_shape = (out_h, out_w) + tuple(arr.shape[2:])
    out = np.full(out_shape, dtype_white(arr.dtype), dtype=arr.dtype)

    out_cx = (out_w - 1) / 2.0
    out_cy = (out_h - 1) / 2.0
    chunk = 256
    for y0 in range(0, out_h, chunk):
        y1 = min(out_h, y0 + chunk)
        yy, xx = np.mgrid[y0:y1, 0:out_w].astype(np.float64)
        x_rel = xx - out_cx
        y_rel = yy - out_cy
        src_x = x_rel * cos_a + y_rel * sin_a + cx
        src_y = -x_rel * sin_a + y_rel * cos_a + cy
        valid = (src_x >= 0) & (src_x <= w - 1) & (src_y >= 0) & (src_y <= h - 1)
        if not valid.any():
            continue
        x0f = np.floor(src_x).astype(np.int64)
        y0f = np.floor(src_y).astype(np.int64)
        x1f = np.clip(x0f + 1, 0, w - 1)
        y1f = np.clip(y0f + 1, 0, h - 1)
        x0f = np.clip(x0f, 0, w - 1)
        y0f = np.clip(y0f, 0, h - 1)
        wx = src_x - x0f
        wy = src_y - y0f
        if arr.ndim == 2:
            value = (
                arr[y0f, x0f] * (1 - wx) * (1 - wy)
                + arr[y0f, x1f] * wx * (1 - wy)
                + arr[y1f, x0f] * (1 - wx) * wy
                + arr[y1f, x1f] * wx * wy
            )
            out[y0:y1, :][valid] = np.clip(value[valid], 0, dtype_white(arr.dtype)).astype(arr.dtype)
        elif axes == "YXS":
            value = (
                arr[y0f, x0f].astype(np.float64) * ((1 - wx) * (1 - wy))[..., None]
                + arr[y0f, x1f].astype(np.float64) * (wx * (1 - wy))[..., None]
                + arr[y1f, x0f].astype(np.float64) * ((1 - wx) * wy)[..., None]
                + arr[y1f, x1f].astype(np.float64) * (wx * wy)[..., None]
            )
            out_chunk = out[y0:y1, :]
            out_chunk[valid] = np.clip(value[valid], 0, dtype_white(arr.dtype)).astype(arr.dtype)
        else:
            raise ValueError(f"Unsupported axes for deskew rotation: {axes}")
    return out


def crop_array(arr: np.ndarray, axes: str, box: Box) -> np.ndarray:
    if axes == "YX":
        return arr[box.top:box.bottom, box.left:box.right]
    if axes == "YXS":
        return arr[box.top:box.bottom, box.left:box.right, :]
    if axes == "SYX":
        return arr[:, box.top:box.bottom, box.left:box.right]
    raise ValueError(f"Unsupported axes: {axes}")


def validate_source_crop_pixels(source_arr: np.ndarray, axes: str, box: Box, cropped: np.ndarray) -> None:
    expected = np.ascontiguousarray(crop_array(source_arr, axes, box))
    if expected.dtype != cropped.dtype or tuple(expected.shape) != tuple(cropped.shape):
        raise RuntimeError(
            f"Source crop validation failed: expected {expected.shape}/{expected.dtype}, "
            f"got {cropped.shape}/{cropped.dtype}"
        )
    if not np.array_equal(expected, cropped):
        raise RuntimeError("Source crop validation failed: cropped pixels differ from source")


def preview_gray(gray: np.ndarray, max_side: int = 1800) -> tuple[np.ndarray, float]:
    h, w = gray.shape
    scale = min(1.0, float(max_side) / float(max(h, w)))
    if scale < 1.0:
        step = max(1, int(math.ceil(1.0 / scale)))
        small = gray[::step, ::step]
        actual_scale = float(small.shape[1]) / float(w)
    else:
        small = gray
        actual_scale = 1.0
    rgb = np.repeat(small[..., None], 3, axis=2).astype(np.uint8, copy=False)
    return rgb, actual_scale


def draw_preview_rect(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], thickness: int = 2) -> None:
    h, w = rgb.shape[:2]
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    if right <= left or bottom <= top:
        return
    t = max(1, int(thickness))
    rgb[top:min(bottom, top + t), left:right] = color
    rgb[max(top, bottom - t):bottom, left:right] = color
    rgb[top:bottom, left:min(right, left + t)] = color
    rgb[top:bottom, max(left, right - t):right] = color


FRAME_FILL_COLORS = (
    (30, 144, 255),
    (255, 120, 40),
    (80, 200, 120),
    (210, 90, 255),
    (255, 210, 40),
    (40, 210, 220),
    (255, 90, 120),
    (150, 170, 255),
)


def fill_preview_rect(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], alpha: float = 0.24) -> None:
    h, w = rgb.shape[:2]
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    if right <= left or bottom <= top:
        return
    overlay = np.array(color, dtype=np.float32)
    region = rgb[top:bottom, left:right].astype(np.float32, copy=False)
    rgb[top:bottom, left:right] = np.clip(region * (1.0 - alpha) + overlay * alpha, 0, 255).astype(np.uint8)


def draw_preview_line(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], thickness: int = 2) -> None:
    h, w = rgb.shape[:2]
    x = max(0, min(w - 1, int(round(box.left * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    if bottom <= top:
        return
    t = max(1, int(thickness))
    rgb[top:bottom, max(0, x - t // 2):min(w, x + (t + 1) // 2)] = color


def draw_preview_hline(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], thickness: int = 2) -> None:
    h, w = rgb.shape[:2]
    y = max(0, min(h - 1, int(round(box.top * scale))))
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    if right <= left:
        return
    t = max(1, int(thickness))
    rgb[max(0, y - t // 2):min(h, y + (t + 1) // 2), left:right] = color


def draw_preview_mark(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], thickness: int = 2) -> None:
    if box.width > 1 or box.height > 1:
        draw_preview_rect(rgb, box, scale, color, thickness)
    else:
        draw_preview_line(rgb, box, scale, color, thickness)


def gap_mark_box(detection: Detection, gap: Gap) -> Optional[Box]:
    work_outer_raw = gap.lane_box if isinstance(gap.lane_box, dict) else detection.detail.get("work_outer")
    if not isinstance(work_outer_raw, dict):
        return None
    try:
        work_outer = Box(
            int(work_outer_raw["left"]),
            int(work_outer_raw["top"]),
            int(work_outer_raw["right"]),
            int(work_outer_raw["bottom"]),
        )
    except Exception:
        return None
    if gap.method in {"detected", "edge-pair"} and gap.start is not None and gap.end is not None:
        start = int(round(work_outer.left + min(gap.start, gap.end)))
        end = int(round(work_outer.left + max(gap.start, gap.end)))
        if end <= start:
            end = start + 1
        if detection.layout == "horizontal":
            return Box(start, work_outer.top, end, work_outer.bottom)
        return Box(work_outer.top, start, work_outer.bottom, end)

    x = int(round(work_outer.left + gap.center))
    if detection.layout == "horizontal":
        return Box(x, work_outer.top, x + 1, work_outer.bottom)
    return Box(work_outer.top, x, work_outer.bottom, x + 1)


def gap_tick_boxes(detection: Detection, gap: Gap) -> list[Box]:
    work_outer_raw = gap.lane_box if isinstance(gap.lane_box, dict) else detection.detail.get("work_outer")
    if not isinstance(work_outer_raw, dict):
        return []
    try:
        work_outer = Box(
            int(work_outer_raw["left"]),
            int(work_outer_raw["top"]),
            int(work_outer_raw["right"]),
            int(work_outer_raw["bottom"]),
        )
    except Exception:
        return []
    tick = max(20, int(round((work_outer.height if detection.layout == "horizontal" else work_outer.width) * 0.12)))
    if detection.layout == "horizontal":
        x = int(round(work_outer.left + gap.center))
        return [
            Box(x, work_outer.top, x + 1, min(work_outer.bottom, work_outer.top + tick)),
            Box(x, max(work_outer.top, work_outer.bottom - tick), x + 1, work_outer.bottom),
        ]
    y = int(round(work_outer.left + gap.center))
    return [
        Box(work_outer.top, y, min(work_outer.bottom, work_outer.top + tick), y + 1),
        Box(max(work_outer.top, work_outer.bottom - tick), y, work_outer.bottom, y + 1),
    ]


def debug_status_parts(detection: Detection, threshold: float) -> tuple[str, str, tuple[int, int, int]]:
    passed = detection.confidence >= threshold
    status = "PASS" if passed else "REVIEW"
    op = ">=" if passed else "<"
    detail = f"confidence {detection.confidence:.3f} {op} threshold {threshold:.3f}"
    if detection.review_reasons:
        detail += " | " + ",".join(detection.review_reasons[:3])
    color = (40, 180, 90) if passed else (230, 80, 70)
    return status, detail, color


def draw_large_status(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, color: tuple[int, int, int]) -> tuple[int, int]:
    x, y = xy
    offsets = ((0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2))
    for dx, dy in offsets:
        draw.text((x + dx, y + dy), text, fill=color)
    try:
        bbox = draw.textbbox((x, y), text)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
    except Exception:
        width = len(text) * 8
        height = 12
    return width + 3, height + 3


def add_status_bar(rgb: np.ndarray, detection: Detection, threshold: float) -> np.ndarray:
    status, detail, color = debug_status_parts(detection, threshold)
    bar_h = 48
    h, w = rgb.shape[:2]
    panel = np.full((h + bar_h, w, 3), 18, dtype=np.uint8)
    panel[bar_h:, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, w - 1, bar_h - 1), outline=color, width=2)
    status_w, _ = draw_large_status(draw, (12, 10), status, color)
    draw.text((12 + status_w + 14, 17), detail, fill=(245, 245, 245))
    return np.asarray(image)


def write_debug_preview(gray: np.ndarray, detection: Detection, output_path: Path, threshold: float) -> None:
    rgb = add_status_bar(make_debug_preview_rgb(gray, detection), detection, threshold)
    write_rgb_jpeg(rgb, output_path)


def make_debug_preview_rgb(gray: np.ndarray, detection: Detection) -> np.ndarray:
    rgb, scale = preview_gray(gray)
    for index, box in enumerate(detection.frames):
        color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
        fill_preview_rect(rgb, box, scale, color, 0.26)
        draw_preview_rect(rgb, box, scale, color, 1)
    draw_preview_rect(rgb, detection.outer, scale, (0, 255, 0), 3)
    return rgb


def draw_gap_overlay(rgb: np.ndarray, detection: Detection, scale: float) -> None:
    gap_colors = {
        "detected": (255, 0, 0),
        "edge-pair": (255, 0, 0),
        "grid": (255, 220, 30),
        "equal": (190, 80, 255),
    }
    pitch = float(detection.detail.get("pitch", 0.0) or 0.0)
    detected_centers = [gap.center for gap in detection.gaps if gap.method in {"detected", "edge-pair"}]
    overlap_tolerance = max(4.0, pitch * 0.012)
    for gap in detection.gaps:
        if not gap.overlap_like:
            continue
        mark = gap_mark_box(detection, gap)
        if mark is not None:
            fill_preview_rect(rgb, mark, scale, (180, 180, 180), 0.22)
    for gap in detection.gaps:
        if gap.method not in {"detected", "edge-pair"}:
            continue
        mark = gap_mark_box(detection, gap)
        if mark is not None:
            draw_preview_mark(rgb, mark, scale, gap_colors.get(gap.method, (255, 255, 255)), 2)
    for gap in detection.gaps:
        if gap.method in {"detected", "edge-pair"}:
            continue
        if any(abs(gap.center - center) <= overlap_tolerance for center in detected_centers):
            continue
        color = gap_colors.get(gap.method, (255, 255, 255))
        for tick in gap_tick_boxes(detection, gap):
            if detection.layout == "horizontal":
                draw_preview_line(rgb, tick, scale, color, 2)
            else:
                draw_preview_hline(rgb, tick, scale, color, 2)


def make_separator_evidence_debug_gray(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    out = np.full(gray.shape, 235, dtype=np.uint8)
    box = detection.outer.clamp(gray.shape[1], gray.shape[0])
    if not box.valid():
        return make_separator_evidence_gray(gray)
    if cache is not None and cache.layout == detection.layout:
        work_box = original_box_to_work(box, detection.layout, gray.shape[1], gray.shape[0]).clamp(
            cache.gray_work.shape[1],
            cache.gray_work.shape[0],
        )
        evidence_crop = cached_separator_evidence_crop(cache, cache.gray_work, work_box)
        if evidence_crop.size:
            patch = evidence_crop if detection.layout == "horizontal" else evidence_crop.T
            ph = min(box.height, patch.shape[0])
            pw = min(box.width, patch.shape[1])
            out[box.top:box.top + ph, box.left:box.left + pw] = patch[:ph, :pw]
            return out
    crop = gray[box.top:box.bottom, box.left:box.right]
    if crop.size == 0:
        return out
    out[box.top:box.bottom, box.left:box.right] = make_separator_evidence_gray(crop)
    return out


def make_separator_evidence_debug_rgb(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    rgb, scale = preview_gray(make_separator_evidence_debug_gray(gray, detection, cache))
    draw_gap_overlay(rgb, detection, scale)
    return rgb


def make_content_evidence_debug_gray(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    out = np.full(gray.shape, 235, dtype=np.uint8)
    box = detection.outer.clamp(gray.shape[1], gray.shape[0])
    if not box.valid():
        return make_content_evidence_gray(gray)
    if cache is not None and cache.layout == detection.layout:
        work_box = original_box_to_work(box, detection.layout, gray.shape[1], gray.shape[0]).clamp(
            cache.content_evidence_work.shape[1],
            cache.content_evidence_work.shape[0],
        )
        evidence_crop = cache.content_evidence_work[work_box.top:work_box.bottom, work_box.left:work_box.right]
        if evidence_crop.size:
            patch = evidence_crop if detection.layout == "horizontal" else evidence_crop.T
            ph = min(box.height, patch.shape[0])
            pw = min(box.width, patch.shape[1])
            out[box.top:box.top + ph, box.left:box.left + pw] = patch[:ph, :pw]
            return out
    crop = gray[box.top:box.bottom, box.left:box.right]
    if crop.size == 0:
        return out
    out[box.top:box.bottom, box.left:box.right] = make_content_evidence_gray(crop)
    return out


def write_rgb_jpeg(rgb: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(np.ascontiguousarray(rgb), mode="RGB")
    image.save(output_path, format="JPEG", quality=92, optimize=True)


def add_panel_label(rgb: np.ndarray, label: str) -> np.ndarray:
    label_h = 34
    h, w = rgb.shape[:2]
    panel = np.full((h + label_h, w, 3), 18, dtype=np.uint8)
    panel[label_h:, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.text((12, 9), label, fill=(245, 245, 245))
    return np.asarray(image)


def make_debug_analysis_panel(gray: np.ndarray, detection: Detection, threshold: float, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    base_rgb, _ = preview_gray(gray)
    base_rgb = add_panel_label(base_rgb, "Original gray")
    debug_rgb = add_panel_label(make_debug_preview_rgb(gray, detection), "Debug boxes")
    evidence_rgb = make_separator_evidence_debug_rgb(gray, detection, cache)
    evidence_rgb = add_panel_label(evidence_rgb, "Separator evidence")
    content_rgb, _ = preview_gray(make_content_evidence_debug_gray(gray, detection, cache))
    content_rgb = add_panel_label(content_rgb, "Content evidence")
    panels = [base_rgb, debug_rgb, evidence_rgb, content_rgb]
    gap = 12
    if gray.shape[1] >= gray.shape[0]:
        max_w = max(panel.shape[1] for panel in panels)
        total_h = sum(panel.shape[0] for panel in panels) + gap * (len(panels) - 1)
        canvas = np.full((total_h, max_w, 3), 32, dtype=np.uint8)
        y = 0
        for panel in panels:
            h, w = panel.shape[:2]
            canvas[y:y + h, :w] = panel
            y += h + gap
    else:
        max_h = max(panel.shape[0] for panel in panels)
        total_w = sum(panel.shape[1] for panel in panels) + gap * (len(panels) - 1)
        canvas = np.full((max_h, total_w, 3), 32, dtype=np.uint8)
        x = 0
        for panel in panels:
            h, w = panel.shape[:2]
            canvas[:h, x:x + w] = panel
            x += w + gap
    return add_status_bar(canvas, detection, threshold)


def write_debug_analysis(
    gray: np.ndarray,
    detection: Detection,
    output_dir: Path,
    stem: str,
    threshold: float,
    cache: Optional[AnalysisCache] = None,
) -> list[str]:
    analysis_dir = output_dir / "_debug_analysis"
    panel_path = analysis_dir / f"{stem}_debug_analysis.jpg"
    write_rgb_jpeg(make_debug_analysis_panel(gray, detection, threshold, cache), panel_path)
    return [str(panel_path)]


LOSSLESS_COMPRESSIONS = {"NONE", "LZW", "ADOBE_DEFLATE", "DEFLATE", "ZSTD"}


def compression_for_write(profile: ImageProfile, mode: str) -> Optional[str]:
    if mode == "none":
        return None
    name = profile.compression.upper()
    if name == "NONE":
        return None
    if name not in LOSSLESS_COMPRESSIONS:
        raise ValueError(f"Refusing to preserve non-lossless or unknown compression: {profile.compression}")
    mapping = {
        "LZW": "lzw",
        "ADOBE_DEFLATE": "deflate",
        "DEFLATE": "deflate",
        "ZSTD": "zstd",
    }
    return mapping.get(name)


def tiff_write_kwargs(profile: ImageProfile, page: Any, config: Config) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    photometric = profile.photometric.lower()
    if photometric in {"rgb", "minisblack", "miniswhite"}:
        kwargs["photometric"] = photometric
    if profile.planar_config and profile.photometric.upper() == "RGB":
        planar = profile.planar_config.lower()
        if planar in {"contig", "separate"}:
            kwargs["planarconfig"] = planar
    compression = compression_for_write(profile, config.compression)
    if compression is not None:
        kwargs["compression"] = compression
    if profile.resolution and profile.resolution[0] and profile.resolution[1]:
        kwargs["resolution"] = profile.resolution
    if profile.resolution_unit:
        kwargs["resolutionunit"] = profile.resolution_unit
    if profile.icc_profile:
        kwargs["iccprofile"] = profile.icc_profile
    return kwargs


def normalize_tag_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, tuple):
        return tuple(normalize_tag_value(v) for v in value)
    if isinstance(value, list):
        return tuple(normalize_tag_value(v) for v in value)
    return value


def expected_bits_for_dtype(dtype_name: str, samples: int) -> int | tuple[int, ...] | None:
    dtype = np.dtype(dtype_name)
    if not np.issubdtype(dtype, np.integer) and not np.issubdtype(dtype, np.floating):
        return None
    bits = int(dtype.itemsize * 8)
    if samples <= 1:
        return bits
    return tuple(bits for _ in range(samples))


def rational_to_float(value: Any) -> Optional[float]:
    value = normalize_tag_value(value)
    if isinstance(value, tuple) and len(value) == 2:
        denominator = float(value[1])
        if denominator == 0:
            return None
        return float(value[0]) / denominator
    try:
        return float(value)
    except Exception:
        return None


def resolutions_equivalent(a: Any, b: Any, tolerance: float = 1e-6) -> bool:
    if a is None or b is None:
        return a is b
    if len(a) != 2 or len(b) != 2:
        return False
    for left, right in zip(a, b):
        lf = rational_to_float(left)
        rf = rational_to_float(right)
        if lf is None or rf is None:
            return normalize_tag_value(left) == normalize_tag_value(right)
        if abs(lf - rf) > tolerance:
            return False
    return True


def validate_written_tiff(out_path: Path, expected_array: np.ndarray, source_profile: ImageProfile, config: Config) -> None:
    problems: list[str] = []
    with tifffile.TiffFile(out_path) as tif:
        if not tif.pages:
            raise RuntimeError(f"Output TIFF has no pages: {out_path}")
        page = tif.pages[0]
        arr = page.asarray()
        axes = infer_axes(arr)
        photometric = enum_name(getattr(page, "photometric", None), "UNKNOWN")
        compression = enum_name(getattr(page, "compression", None), "NONE")
        xres = page.tags.get("XResolution")
        yres = page.tags.get("YResolution")
        unit = page.tags.get("ResolutionUnit")
        sample_format = page.tags.get("SampleFormat")
        bits = page.tags.get("BitsPerSample")
        samples = page.tags.get("SamplesPerPixel")
        planar = page.tags.get("PlanarConfiguration")
        icc = page.tags.get(34675)

        if arr.dtype != expected_array.dtype:
            problems.append(f"dtype changed: {expected_array.dtype} -> {arr.dtype}")
        if tuple(arr.shape) != tuple(expected_array.shape):
            problems.append(f"shape changed after write/read: expected {expected_array.shape}, got {arr.shape}")
        elif not np.array_equal(arr, expected_array):
            problems.append("pixel data changed after write/read")
        if axes != source_profile.axes:
            problems.append(f"axes changed: {source_profile.axes} -> {axes}")
        if photometric.upper() != source_profile.photometric.upper():
            problems.append(f"Photometric changed: {source_profile.photometric} -> {photometric}")
        if config.compression == "same" and compression.upper() != source_profile.compression.upper():
            problems.append(f"Compression changed: {source_profile.compression} -> {compression}")
        if source_profile.sample_format is not None:
            actual_sample_format = normalize_tag_value(sample_format.value if sample_format else getattr(page, "sampleformat", None))
            if normalize_tag_value(actual_sample_format) != normalize_tag_value(source_profile.sample_format):
                problems.append(f"SampleFormat changed: {source_profile.sample_format} -> {actual_sample_format}")

        expected_samples = int(source_profile.samples_per_pixel or 1)
        actual_samples = int(samples.value) if samples else (arr.shape[-1] if axes == "YXS" else arr.shape[0] if axes == "SYX" else 1)
        if actual_samples != expected_samples:
            problems.append(f"SamplesPerPixel changed: {expected_samples} -> {actual_samples}")
        if source_profile.planar_config is not None:
            actual_planar = planar_config_name(getattr(page, "planarconfig", None) or (planar.value if planar else None))
            if actual_planar != source_profile.planar_config:
                problems.append(f"PlanarConfiguration changed: {source_profile.planar_config} -> {actual_planar}")

        actual_bits = normalize_tag_value(bits.value) if bits else expected_bits_for_dtype(str(arr.dtype), actual_samples)
        expected_bits = normalize_tag_value(source_profile.bits_per_sample)
        if expected_bits is None:
            expected_bits = expected_bits_for_dtype(source_profile.dtype, expected_samples)
        if normalize_tag_value(actual_bits) != normalize_tag_value(expected_bits):
            problems.append(f"BitsPerSample changed: {expected_bits} -> {actual_bits}")

        if source_profile.resolution is not None:
            actual_resolution = ((xres.value if xres else None), (yres.value if yres else None))
            if not resolutions_equivalent(actual_resolution, source_profile.resolution):
                problems.append(f"Resolution changed: {source_profile.resolution} -> {actual_resolution}")
        if source_profile.resolution_unit is not None:
            actual_unit = unit.value if unit else None
            if normalize_tag_value(actual_unit) != normalize_tag_value(source_profile.resolution_unit):
                problems.append(f"ResolutionUnit changed: {source_profile.resolution_unit} -> {actual_unit}")
        if source_profile.icc_profile is not None:
            actual_icc = bytes(icc.value) if icc is not None else None
            if actual_icc != source_profile.icc_profile:
                problems.append("ICC profile changed or was dropped")

    if problems:
        raise RuntimeError("Output TIFF validation failed for " + str(out_path) + ":\n  - " + "\n  - ".join(problems))


def output_directory_for(input_file: Path, config: Config) -> Path:
    if config.output_dir is not None:
        return config.output_dir
    return input_file.parent / "split_output"


def review_directory_for(output_dir: Path, config: Config) -> Path:
    return config.review_dir if config.review_dir is not None else output_dir / "needs_review"


def display_generated_path(path: Path | str, config: Config) -> str:
    path = Path(path)
    if config.output_dir is None:
        return path.name
    return str(path)


def copy_for_review(input_file: Path, review_dir: Path) -> Path:
    review_dir.mkdir(parents=True, exist_ok=True)
    target = review_dir / input_file.name
    if target.exists():
        return target
    shutil.copy2(input_file, target)
    return target


def source_cache_signature(input_file: Path, profile: ImageProfile, page_index: int) -> dict[str, Any]:
    stat = input_file.stat()
    return {
        "name": input_file.name,
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "page": int(page_index),
        "shape": list(profile.shape),
        "dtype": profile.dtype,
        "axes": profile.axes,
        "photometric": profile.photometric,
    }


def config_cache_signature(config: Config) -> dict[str, Any]:
    return {
        "film_format": config.film_format,
        "layout": config.layout,
        "strip_mode": config.strip_mode,
        "count": int(config.count),
        "page": int(config.page),
        "bleed_x": int(config.bleed_x),
        "bleed_y": int(config.bleed_y),
        "deskew": config.deskew,
        "analysis": config.analysis,
        "deskew_min_angle": float(config.deskew_min_angle),
        "deskew_max_angle": float(config.deskew_max_angle),
        "confidence_threshold": float(config.confidence_threshold),
    }


def make_analysis_cache_metadata(input_file: Path, profile: ImageProfile, config: Config) -> dict[str, Any]:
    return {
        "script": SCRIPT_NAME,
        "version": VERSION,
        "source": source_cache_signature(input_file, profile, config.page),
        "config": config_cache_signature(config),
    }


def box_from_dict(value: dict[str, Any]) -> Box:
    return Box(int(value["left"]), int(value["top"]), int(value["right"]), int(value["bottom"]))


def gap_from_dict(value: dict[str, Any]) -> Gap:
    return Gap(
        index=int(value.get("index", 0)),
        center=float(value.get("center", 0.0)),
        score=float(value.get("score", 0.0)),
        method=str(value.get("method", "cached")),
        start=(None if value.get("start") is None else float(value.get("start"))),
        end=(None if value.get("end") is None else float(value.get("end"))),
        lane_box=(dict(value["lane_box"]) if isinstance(value.get("lane_box"), dict) else None),
        overlap_like=bool(value.get("overlap_like", False)),
    )


def cached_record_matches(record: dict[str, Any], input_file: Path, profile: ImageProfile, config: Config) -> bool:
    detail = record.get("detail")
    if not isinstance(detail, dict):
        return False
    cache = detail.get("analysis_cache")
    if not isinstance(cache, dict):
        return False
    if cache.get("script") != SCRIPT_NAME or cache.get("version") != VERSION:
        return False
    expected_source = source_cache_signature(input_file, profile, config.page)
    expected_config = config_cache_signature(config)
    if cache.get("source") != expected_source:
        return False
    if cache.get("config") != expected_config:
        return False
    return str(record.get("status", "")) in {"approved_auto", "needs_review"}


def load_report_records(report_path: Path) -> list[dict[str, Any]]:
    try:
        stat = report_path.stat()
    except FileNotFoundError:
        return []
    cached = REPORT_RECORD_CACHE.get(report_path)
    signature = (int(stat.st_size), int(stat.st_mtime_ns))
    if cached is not None and cached[0] == signature[0] and cached[1] == signature[1]:
        return cached[2]
    try:
        lines = report_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []
    records: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    REPORT_RECORD_CACHE[report_path] = (signature[0], signature[1], records)
    return records


def find_reusable_analysis(input_file: Path, output_dir: Path, profile: ImageProfile, config: Config) -> Optional[dict[str, Any]]:
    report_path = output_dir / "split_report.jsonl"
    for record in load_report_records(report_path):
        if Path(str(record.get("source", ""))).name != input_file.name:
            continue
        if cached_record_matches(record, input_file, profile, config):
            return record
    return None


def config_for_profile(config: Config, profile: ImageProfile) -> Config:
    h, w = spatial_shape_from_shape(profile.shape)
    fmt = FORMATS[config.film_format]
    count = int(fmt.default_count if config.count_override is None else config.count_override)
    if count not in fmt.allowed_counts:
        allowed = ", ".join(str(x) for x in fmt.allowed_counts)
        raise ValueError(f"--format {fmt.name} allows --count values: {allowed}")
    layout = infer_layout(w, h) if config.layout_auto else config.layout
    return replace(config, layout=layout, count=count)


def detection_from_record(record: dict[str, Any]) -> Detection:
    return Detection(
        film_format=str(record["film_format"]),
        layout=str(record["layout"]),
        strip_mode=str(record["strip_mode"]),
        count=int(record["count"]),
        outer=box_from_dict(record["outer_box"]),
        frames=[box_from_dict(box) for box in record.get("frame_boxes", [])],
        gaps=[gap_from_dict(gap) for gap in record.get("gaps", [])],
        confidence=float(record["confidence"]),
        review_reasons=list(record.get("review_reasons", [])),
        detail=dict(record.get("detail", {})),
    )


def apply_cached_deskew(
    arr: np.ndarray,
    gray: np.ndarray,
    axes: str,
    photometric: str,
    detail: dict[str, Any],
    warnings: list[str],
) -> tuple[np.ndarray, np.ndarray, bool]:
    deskew_detail = detail.get("deskew")
    if not isinstance(deskew_detail, dict) or not bool(deskew_detail.get("applied", False)):
        return arr, gray, False
    angle = float(deskew_detail.get("angle", 0.0))
    arr = rotate_array_expand(arr, -angle, axes)
    gray = make_gray_u8(arr, axes, photometric)
    warnings.append(f"reused deskew: {-angle:.4f} degrees")
    return arr, gray, True


def write_crops(
    input_file: Path,
    arr: np.ndarray,
    source_arr: np.ndarray,
    profile: ImageProfile,
    page: Any,
    detection: Detection,
    config: Config,
    deskew_applied: bool,
    output_dir: Path,
) -> list[str]:
    output_files: list[str] = []
    for i, box in enumerate(detection.frames, 1):
        if not box.valid():
            raise RuntimeError(f"Invalid crop box for frame {i}: {box}")
        out_path = output_dir / f"{input_file.stem}_{i:02d}.tif"
        if out_path.exists() and not config.overwrite:
            raise RuntimeError(f"Output exists: {out_path}; use --overwrite")
        cropped = np.ascontiguousarray(crop_array(arr, profile.axes, box))
        if not deskew_applied:
            validate_source_crop_pixels(source_arr, profile.axes, box, cropped)
        tmp = out_path.with_name(f".{out_path.stem}.tmp{out_path.suffix}")
        if tmp.exists():
            tmp.unlink()
        try:
            tifffile.imwrite(tmp, cropped, **tiff_write_kwargs(profile, page, config))
            validate_written_tiff(tmp, cropped, profile, config)
            os.replace(tmp, out_path)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
        output_files.append(str(out_path))
    return output_files


def write_jsonl(path: Path, result: ProcessResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(json_safe(asdict(result)), ensure_ascii=False) + "\n")


def write_summary(path: Path, result: ProcessResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source",
        "status",
        "confidence",
        "film_format",
        "layout",
        "strip_mode",
        "count",
        "review_reasons",
        "output_count",
    ]
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "source": result.source,
                "status": result.status,
                "confidence": f"{result.confidence:.3f}",
                "film_format": result.film_format,
                "layout": result.layout,
                "strip_mode": result.strip_mode,
                "count": result.count,
                "review_reasons": ";".join(result.review_reasons),
                "output_count": len(result.output_files),
            }
        )


def write_reports_for_result(result: ProcessResult, config: Config) -> None:
    if not config.report:
        return
    output_dir = output_directory_for(Path(result.source), config)
    write_jsonl(output_dir / "split_report.jsonl", result)
    write_summary(output_dir / "split_summary.csv", result)


def process_one_worker(input_file: Path, config: Config) -> ProcessResult:
    return process_one(input_file, replace(config, report=False))


def process_one(input_file: Path, config: Config) -> ProcessResult:
    output_dir = output_directory_for(input_file, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile, warnings = read_tiff_profile(input_file, config.page)
    config = config_for_profile(config, profile)
    fmt = FORMATS[config.film_format]

    if config.reuse_analysis and not config.dry_run and not config.debug_analysis:
        cached_record = find_reusable_analysis(input_file, output_dir, profile, config)
        if cached_record is not None:
            status = str(cached_record["status"])
            warnings.append("reused analysis report: split_report.jsonl")
            if status == "needs_review":
                warnings.append("cached status is needs_review; skipped export")
                result = ProcessResult(
                    source=str(input_file),
                    status=status,
                    confidence=float(cached_record["confidence"]),
                    film_format=str(cached_record["film_format"]),
                    layout=str(cached_record["layout"]),
                    strip_mode=str(cached_record["strip_mode"]),
                    count=int(cached_record["count"]),
                    review_reasons=list(cached_record.get("review_reasons", [])),
                    output_files=[],
                    review_copy=cached_record.get("review_copy"),
                    outer_box=dict(cached_record.get("outer_box", {})),
                    frame_boxes=list(cached_record.get("frame_boxes", [])),
                    gaps=list(cached_record.get("gaps", [])),
                    detail={**dict(cached_record.get("detail", {})), "reused_analysis": True},
                    profile=json_safe(asdict(profile)),
                    warnings=warnings,
                )
                if config.report:
                    write_jsonl(output_dir / "split_report.jsonl", result)
                    write_summary(output_dir / "split_summary.csv", result)
                return result

            arr, gray, profile, page_warnings, page = read_tiff(input_file, config.page)
            warnings.extend(w for w in page_warnings if w not in warnings)
            source_arr = arr
            detection = detection_from_record(cached_record)
            arr, gray, deskew_applied = apply_cached_deskew(
                arr,
                gray,
                profile.axes,
                profile.photometric,
                detection.detail,
                warnings,
            )
            output_files = write_crops(
                input_file,
                arr,
                source_arr,
                profile,
                page,
                detection,
                config,
                deskew_applied,
                output_dir,
            )
            detail = dict(detection.detail)
            detail["reused_analysis"] = True
            result = ProcessResult(
                source=str(input_file),
                status=status,
                confidence=float(detection.confidence),
                film_format=detection.film_format,
                layout=detection.layout,
                strip_mode=detection.strip_mode,
                count=int(detection.count),
                review_reasons=list(detection.review_reasons),
                output_files=output_files,
                review_copy=cached_record.get("review_copy"),
                outer_box=asdict(detection.outer),
                frame_boxes=[asdict(box) for box in detection.frames],
                gaps=[asdict(gap) for gap in detection.gaps],
                detail=json_safe(detail),
                profile=json_safe(asdict(profile)),
                warnings=warnings,
            )
            if config.report:
                write_jsonl(output_dir / "split_report.jsonl", result)
                write_summary(output_dir / "split_summary.csv", result)
            return result

    arr, gray, profile, page_warnings, page = read_tiff(input_file, config.page)
    warnings.extend(w for w in page_warnings if w not in warnings)
    source_arr = arr
    config = config_for_profile(config, profile)
    fmt = FORMATS[config.film_format]

    deskew_detail: dict[str, Any] = {"applied": False}
    if config.deskew != "off":
        angle, angle_detail = choose_deskew_angle(gray, config.layout, config.analysis)
        deskew_detail.update(angle_detail)
        deskew_detail["angle"] = angle
        deskew_span = abs(math.tan(math.radians(angle)) * float(work_gray(gray, config.layout).shape[1]))
        deskew_detail["span_px"] = deskew_span
        if deskew_span < 5.0:
            deskew_detail["skipped"] = "span_below_threshold"
        elif config.deskew_min_angle <= abs(angle) <= config.deskew_max_angle:
            arr = rotate_array_expand(arr, -angle, profile.axes)
            gray = make_gray_u8(arr, profile.axes, profile.photometric)
            h, w = spatial_shape(arr)
            deskew_detail["applied"] = True
            warnings.append(f"deskew applied: {-angle:.4f} degrees")
        else:
            deskew_detail["skipped"] = "angle_out_of_range"

    analysis_cache = make_analysis_cache(gray, config.layout)
    detection_config = detection_geometry_config(config)
    detection = choose_detection_v2(gray, detection_config, fmt, analysis_cache)
    content_detail = content_evidence_detail(gray, detection, analysis_cache)
    detection.detail["content_evidence"] = content_detail
    outer_alignment = outer_content_alignment_detail(gray, detection, analysis_cache)
    detection.detail["outer_content_alignment"] = outer_alignment
    unsupported_mode = detection.detail.get("analysis_source") == "unsupported_mode"

    allow_outer_retry = detection.detail.get("analysis_source") != "hard_fallback" and detection.film_format != "135-dual"
    if allow_outer_retry and bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        retried_detection = retry_with_content_aligned_outer(gray, detection_config, fmt, detection, outer_alignment, analysis_cache)
        if retried_detection is not None:
            detection = retried_detection
            content_detail = dict(detection.detail.get("content_evidence", {}))
            outer_alignment = dict(detection.detail.get("outer_content_alignment", {}))
        else:
            detection.detail["outer_correction"] = {
                "used": False,
                "reason": "no_valid_content_aligned_outer_retry",
            }

    if not unsupported_mode and bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            detection.confidence = min(detection.confidence, 0.82)
            detection.review_reasons.append("content_aspect_conflict")
        elif support == "low_content" and detection.confidence >= config.confidence_threshold:
            detection.confidence = min(detection.confidence, 0.84)
            detection.review_reasons.append("content_evidence_weak")
    if not unsupported_mode and bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        detection.confidence = min(detection.confidence, 0.84)
        detection.review_reasons.append("outer_content_bbox_mismatch")

    if detection.confidence < config.confidence_threshold:
        if detection.detail.get("partial_best"):
            detection.review_reasons.append("likely_partial_strip")
        if float(detection.detail.get("outer_area_spread_ratio", 0.0)) >= 0.20:
            detection.review_reasons.append("outer_candidate_disagreement")
        if deskew_detail.get("skipped") == "angle_out_of_range" or deskew_detail.get("reason"):
            detection.review_reasons.append("deskew_uncertain")
        detection.review_reasons = sorted(set(detection.review_reasons))
    status = "approved_auto" if detection.confidence >= config.confidence_threshold else "needs_review"
    output_files: list[str] = []
    review_copy: Optional[str] = None
    apply_approved_geometry_polish(detection, gray, config, status)
    apply_output_bleed(detection, detection_config, config, gray.shape[1], gray.shape[0])
    apply_edge_bleed_protection(detection, config, gray.shape[1], gray.shape[0])

    if status == "needs_review":
        warnings.append(
            f"low confidence: {detection.confidence:.3f} < {config.confidence_threshold:.3f}; "
            f"reasons={','.join(detection.review_reasons)}"
        )
        if config.copy_review_files:
            review_copy = str(copy_for_review(input_file, review_directory_for(output_dir, config)))
            warnings.append(f"review copy: {review_copy}")

    should_export = status == "approved_auto" or config.export_review
    if config.dry_run:
        should_export = False

    if should_export:
        output_files = write_crops(
            input_file,
            arr,
            source_arr,
            profile,
            page,
            detection,
            config,
            bool(deskew_detail["applied"]),
            output_dir,
        )

    if config.debug and not config.debug_analysis:
        debug_path = output_dir / "_debug" / f"{input_file.stem}_debug.jpg"
        write_debug_preview(gray, detection, debug_path, config.confidence_threshold)
        warnings.append(f"debug preview: {display_generated_path(debug_path, config)}")
    if config.debug_analysis:
        for analysis_path in write_debug_analysis(gray, detection, output_dir, input_file.stem, config.confidence_threshold, analysis_cache):
            warnings.append(f"debug analysis: {display_generated_path(analysis_path, config)}")

    detail = dict(detection.detail)
    detail["deskew"] = deskew_detail
    detail["analysis_cache"] = make_analysis_cache_metadata(input_file, profile, config)
    result = ProcessResult(
        source=str(input_file),
        status=status,
        confidence=float(detection.confidence),
        film_format=detection.film_format,
        layout=detection.layout,
        strip_mode=detection.strip_mode,
        count=int(detection.count),
        review_reasons=list(detection.review_reasons),
        output_files=output_files,
        review_copy=review_copy,
        outer_box=asdict(detection.outer),
        frame_boxes=[asdict(box) for box in detection.frames],
        gaps=[asdict(gap) for gap in detection.gaps],
        detail=json_safe(detail),
        profile=json_safe(asdict(profile)),
        warnings=warnings,
    )
    if config.report:
        write_jsonl(output_dir / "split_report.jsonl", result)
        write_summary(output_dir / "split_summary.csv", result)
    return result


def iter_input_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() not in TIFF_SUFFIXES:
            raise ValueError(f"Input is not a TIFF: {path}")
        return [path]
    if path.is_dir():
        return [p for p in sorted(path.iterdir()) if p.is_file() and p.suffix.lower() in TIFF_SUFFIXES]
    raise ValueError(f"Path does not exist: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="X5 Crop V3.4.1 candidate-scored single-strip TIFF film cropper.")
    parser.add_argument("input", nargs="?", default=".", help="TIFF file or directory; default current directory.")
    parser.add_argument("-o", "--output", default=None, help="Output directory; default input/split_output.")
    parser.add_argument("--format", choices=FORMAT_CHOICES, required=True, help="Film format; launchers pass this explicitly.")
    parser.add_argument("--layout", choices=LAYOUT_CHOICES, default="auto", help="auto/horizontal/vertical single-strip layout.")
    parser.add_argument("--strip", choices=STRIP_CHOICES, default="full", help="full strip or partial/head mode.")
    parser.add_argument("-n", "--count", type=int, default=None, help="Override frame count.")
    parser.add_argument("--page", type=int, default=0, help="TIFF page index; default 0.")
    parser.add_argument("--bleed", type=int, default=None, help="Bleed in pixels on all sides; overrides layout-aware defaults.")
    parser.add_argument("--bleed-x", type=int, default=None, help="Long-axis bleed override; default 15. Horizontal scans: left/right. Vertical scans: top/bottom.")
    parser.add_argument("--bleed-y", type=int, default=None, help="Short-axis bleed override; default 10. Horizontal scans: top/bottom. Vertical scans: left/right.")
    parser.add_argument("--deskew", choices=DESKEW_CHOICES, default="auto", help="Deskew strip before detection/export.")
    parser.add_argument("--analysis", choices=ANALYSIS_CHOICES, default="auto", help="Deskew analysis assist: auto tries enhanced gray only when base deskew is weak; always tries it every time; off disables it.")
    parser.add_argument("--compression", choices=COMPRESSION_CHOICES, default="same", help="TIFF output compression: same for known lossless source compression, or none.")
    parser.add_argument("--deskew-min-angle", type=float, default=0.03, help="Minimum absolute deskew angle in degrees.")
    parser.add_argument("--deskew-max-angle", type=float, default=2.0, help="Maximum absolute deskew angle in degrees.")
    parser.add_argument("--confidence-threshold", type=float, default=0.85, help="Minimum confidence for automatic export.")
    parser.add_argument("--copy-review-files", dest="copy_review_files", action="store_true", default=True, help="Copy low-confidence source TIFFs to review folder; default on.")
    parser.add_argument("--no-copy-review-files", dest="copy_review_files", action="store_false", help="Do not copy low-confidence source TIFFs to review folder.")
    parser.add_argument("--review-dir", default=None, help="Review folder; default output/needs_review.")
    parser.add_argument("--export-review", action="store_true", help="Export crops even when confidence is below threshold.")
    parser.add_argument("--dry-run", action="store_true", help="Detect only; do not write cropped TIFFs.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs.")
    parser.add_argument("--report", action="store_true", help="Write split_report.jsonl and split_summary.csv.")
    parser.add_argument("--debug", action="store_true", help="Write lightweight JPG previews with detected outer/frame boxes.")
    parser.add_argument("--debug-analysis", action="store_true", help="Write one combined JPG with debug boxes, original gray, separator evidence, and content evidence.")
    parser.add_argument("--no-reuse-analysis", dest="reuse_analysis", action="store_false", default=True, help="Do not reuse matching Debug Analysis report data for non-dry-run export.")
    parser.add_argument("--jobs", type=int, default=2, help="Parallel TIFF workers. Default 2; values above 2 are capped to protect memory.")
    parser.add_argument("--debug-errors", action="store_true", help="Print tracebacks on errors.")
    parser.add_argument("--version", action="version", version=f"{SCRIPT_NAME} {VERSION}")
    return parser


def config_from_args(args: argparse.Namespace) -> Config:
    input_path = Path(args.input).expanduser().resolve()
    files_for_probe = [input_path] if input_path.is_file() else iter_input_files(input_path)
    first_file = next(iter(files_for_probe), None)
    if first_file is None:
        raise ValueError(f"No TIFF files found: {input_path}")
    with tifffile.TiffFile(first_file) as tif:
        shape = tuple(int(x) for x in tif.pages[int(args.page)].shape)
    height, width = spatial_shape_from_shape(shape)

    film_format = str(args.format)
    fmt = FORMATS[film_format]
    count = int(fmt.default_count if args.count is None else args.count)
    if count not in fmt.allowed_counts:
        allowed = ", ".join(str(x) for x in fmt.allowed_counts)
        raise ValueError(f"--format {fmt.name} allows --count values: {allowed}")
    layout_auto = str(args.layout) == "auto"
    layout = infer_layout(width, height) if layout_auto else str(args.layout)
    bleed_x_default = 20 if args.bleed is None else int(args.bleed)
    bleed_y_default = 10 if args.bleed is None else int(args.bleed)
    bleed_x = int(bleed_x_default if args.bleed_x is None else args.bleed_x)
    bleed_y = int(bleed_y_default if args.bleed_y is None else args.bleed_y)
    if bleed_x < 0 or bleed_y < 0:
        raise ValueError("Bleed cannot be negative")
    if not (0.0 <= float(args.confidence_threshold) <= 1.0):
        raise ValueError("--confidence-threshold must be between 0 and 1")
    if float(args.deskew_min_angle) < 0 or float(args.deskew_max_angle) <= 0:
        raise ValueError("Deskew angle limits are invalid")
    jobs = max(1, min(2, int(args.jobs)))
    return Config(
        input_path=input_path,
        output_dir=Path(args.output).expanduser().resolve() if args.output else None,
        film_format=film_format,
        layout_auto=layout_auto,
        layout=layout,
        strip_mode=str(args.strip),
        count=count,
        count_override=(None if args.count is None else int(args.count)),
        page=int(args.page),
        bleed_x=bleed_x,
        bleed_y=bleed_y,
        deskew=str(args.deskew),
        analysis=str(args.analysis),
        deskew_min_angle=float(args.deskew_min_angle),
        deskew_max_angle=float(args.deskew_max_angle),
        confidence_threshold=float(args.confidence_threshold),
        review_dir=Path(args.review_dir).expanduser().resolve() if args.review_dir else None,
        copy_review_files=bool(args.copy_review_files),
        export_review=bool(args.export_review),
        compression=str(args.compression),
        debug=bool(args.debug),
        debug_analysis=bool(args.debug_analysis),
        dry_run=bool(args.dry_run),
        overwrite=bool(args.overwrite),
        report=bool(args.report),
        debug_errors=bool(args.debug_errors),
        reuse_analysis=bool(args.reuse_analysis),
        jobs=jobs,
    )


def print_process_result(result: ProcessResult, config: Config) -> None:
    print(f"  status={result.status} confidence={result.confidence:.3f}")
    for warning in result.warnings:
        print(f"  info: {warning}")
    if result.output_files:
        print(f"  wrote: {len(result.output_files)} TIFF files")
        if config.output_dir is not None:
            for out in result.output_files:
                print(f"    {Path(out).name}")


def process_parallel_files(
    files: list[Path],
    config: Config,
    worker_config: Config,
) -> tuple[int, int, int, int]:
    ok = 0
    failed = 0
    approved = 0
    review = 0
    total = len(files)
    try:
        executor_context = concurrent.futures.ProcessPoolExecutor(max_workers=config.jobs)
    except (OSError, PermissionError) as exc:
        print(f"info: process workers unavailable ({exc}); using thread workers")
        executor_context = concurrent.futures.ThreadPoolExecutor(max_workers=config.jobs)
    with executor_context as executor:
        future_to_path = {
            executor.submit(process_one_worker, path, worker_config): path
            for path in files
        }
        for index, future in enumerate(concurrent.futures.as_completed(future_to_path), start=1):
            path = future_to_path[future]
            print(f"\n[{index}/{total}] {path.name}")
            try:
                result = future.result()
                ok += 1
                approved += int(result.status == "approved_auto")
                review += int(result.status == "needs_review")
                write_reports_for_result(result, config)
                print_process_result(result, config)
            except Exception as exc:
                failed += 1
                print(f"  error: {exc}", file=sys.stderr)
                if config.debug_errors:
                    traceback.print_exc()
    return ok, failed, approved, review


def main() -> int:
    parser = build_parser()
    try:
        config = config_from_args(parser.parse_args())
        files = iter_input_files(config.input_path)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"{SCRIPT_NAME} {VERSION}")
    print(f"input: {config.input_path}")
    print(f"files: {len(files)}")
    layout_label = f"auto(probe={config.layout})" if config.layout_auto else config.layout
    mode_parts = [f"layout: {layout_label}", f"strip: {config.strip_mode}"]
    if config.strip_mode == "partial" and config.count_override is None:
        mode_parts.append("count: auto")
    if config.debug_analysis:
        mode_parts.append("debug analysis")
    if config.dry_run:
        mode_parts.append("dry run")
    print("; ".join(mode_parts))
    print(f"threshold: {config.confidence_threshold:.2f}; analysis: {config.analysis}")
    if len(files) > 1 and config.jobs > 1:
        print(f"parallel: {config.jobs} workers")
    if config.output_dir is not None:
        print(f"output: {config.output_dir}")

    ok = 0
    failed = 0
    approved = 0
    review = 0
    total = len(files)
    worker_config = replace(config, report=False)
    if total > 1 and config.jobs > 1:
        ok, failed, approved, review = process_parallel_files(files, config, worker_config)
    else:
        for index, path in enumerate(files, start=1):
            print(f"\n[{index}/{total}] {path.name}")
            try:
                result = process_one_worker(path, worker_config)
                ok += 1
                approved += int(result.status == "approved_auto")
                review += int(result.status == "needs_review")
                write_reports_for_result(result, config)
                print_process_result(result, config)
            except Exception as exc:
                failed += 1
                print(f"  error: {exc}", file=sys.stderr)
                if config.debug_errors:
                    traceback.print_exc()

    print(f"\ndone: ok={ok} failed={failed} approved={approved} review={review}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
