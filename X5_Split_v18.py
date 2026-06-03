#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X5_Split_v18.py

Clean single-strip cropper for Hasselblad X5 film-holder TIFF scans.

Design goals:
- Single-strip scans only: horizontal or vertical.
- Automatic high-confidence crop for common 135 and 120 scans.
- half-frame and XPAN remain available, but must be selected manually.
- Difficult scans are marked for review instead of being forced through.
- TIFF pixel data and key TIFF metadata are preserved as much as practical.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import sys
import traceback
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
from PIL import Image, ImageDraw
import tifffile


VERSION = "18.0-clean-single-strip"
SCRIPT_NAME = "X5_Split_v18.py"
TIFF_SUFFIXES = {".tif", ".tiff"}


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
    manual_only: bool = False


FORMATS: dict[str, FilmFormat] = {
    "135": FilmFormat("135", 6, tuple(range(1, 7)), "35mm"),
    "half": FilmFormat("half", 12, tuple(range(1, 13)), "35mm", manual_only=True),
    "xpan": FilmFormat("xpan", 3, (1, 2, 3), "35mm", manual_only=True),
    "120-645": FilmFormat("120-645", 4, (1, 2, 3, 4), "120"),
    "120-66": FilmFormat("120-66", 3, (1, 2, 3), "120"),
    "120-67": FilmFormat("120-67", 3, (1, 2, 3), "120"),
}


FORMAT_CHOICES = ("auto", *FORMATS.keys())
LAYOUT_CHOICES = ("auto", "horizontal", "vertical")
STRIP_CHOICES = ("auto", "full", "partial")
DESKEW_CHOICES = ("off", "auto")
ANALYSIS_CHOICES = ("off", "auto", "always")
COMPRESSION_CHOICES = ("none", "same")


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
    format_auto: bool
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
            shape=tuple(int(x) for x in arr.shape),
            dtype=str(arr.dtype),
            axes=axes,
            photometric=photometric,
            compression=compression,
            sample_format=(sample_format.value if sample_format else normalize_tag_value(getattr(page, "sampleformat", None))),
            bits_per_sample=(bits_tag.value if bits_tag else None),
            samples_per_pixel=(int(samples_tag.value) if samples_tag else (arr.shape[-1] if axes == "YXS" else arr.shape[0] if axes == "SYX" else 1)),
            planar_config=planar_config_name(getattr(page, "planarconfig", None) or (planar.value if planar else None)),
            resolution=((xres.value if xres else None), (yres.value if yres else None)) if xres or yres else None,
            resolution_unit=(unit.value if unit else None),
            icc_profile=(bytes(icc.value) if icc is not None else None),
        )
        expected_bits = expected_bits_for_dtype(str(arr.dtype), int(profile.samples_per_pixel or 1))
        if profile.bits_per_sample is not None and normalize_tag_value(profile.bits_per_sample) != normalize_tag_value(expected_bits):
            raise ValueError(
                f"Packed or unusual bit depth is not supported safely: "
                f"BitsPerSample={profile.bits_per_sample}, dtype={arr.dtype}. "
                "Refusing to continue to protect output bit depth."
            )
    gray = make_gray_u8(arr, axes, profile.photometric)
    return arr, gray, profile, warnings, page


def holder_ratio(width: int, height: int) -> float:
    return float(max(width, height)) / max(1.0, float(min(width, height)))


def infer_format_from_holder(width: int, height: int) -> str:
    ratio = holder_ratio(width, height)
    if ratio >= 6.0:
        return "135"
    if ratio >= 4.45:
        return "120-645"
    if ratio >= 3.70:
        return "120-67"
    return "120-66"


def infer_layout(width: int, height: int) -> str:
    return "horizontal" if width >= height else "vertical"


def work_gray(gray: np.ndarray, layout: str) -> np.ndarray:
    return gray if layout == "horizontal" else np.ascontiguousarray(gray.T)


def map_work_box(box: Box, layout: str, width: int, height: int) -> Box:
    if layout == "horizontal":
        return box.clamp(width, height)
    return Box(box.top, box.left, box.bottom, box.right).clamp(width, height)


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
    rejected_broad = False

    for run_start, run_end in runs_from_mask(local >= peak_threshold):
        region_start, region_end = run_start, run_end
        while region_start > 0 and local[region_start - 1] >= broad_threshold:
            region_start -= 1
        while region_end < len(local) and local[region_end] >= broad_threshold:
            region_end += 1
        region_width = region_end - region_start
        touches_edge = region_start == 0 or region_end == len(local)
        if region_width > max_gap_w * 1.5 or (touches_edge and region_width > max_gap_w * 0.9):
            rejected_broad = True
            continue

        band_start, band_end = run_start, run_end
        while band_start > 0 and local[band_start - 1] >= band_threshold and (band_end - (band_start - 1)) <= max_gap_w:
            band_start -= 1
        while band_end < len(local) and local[band_end] >= band_threshold and ((band_end + 1) - band_start) <= max_gap_w:
            band_end += 1
        band_width = band_end - band_start
        if band_width < min_gap_w or band_width > max_gap_w:
            rejected_broad = True
            continue

        left_guard = local[max(0, band_start - guard_w):band_start]
        right_guard = local[band_end:min(len(local), band_end + guard_w)]
        if left_guard.size == 0 or right_guard.size == 0:
            rejected_broad = True
            continue
        mean_score = float(local[band_start:band_end].mean())
        side_score = max(float(left_guard.mean()), float(right_guard.mean()))
        prominence = mean_score - side_score
        if prominence < 0.08 and mean_score < 0.95:
            rejected_broad = True
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

    method = "equal-broad-region" if rejected_broad else "equal"
    return Gap(index, float(expected), local_max, method)


def constrain_gap_to_geometry(gap: Gap, expected: float, pitch: float, strip_mode: str) -> Gap:
    if gap.method != "detected":
        return Gap(gap.index, float(expected), gap.score, "equal")
    max_shift = pitch * (0.045 if strip_mode == "full" else 0.12)
    shift = max(-max_shift, min(max_shift, gap.center - expected))
    method = "detected" if abs(shift) >= 1.0 else "grid"
    if gap.start is not None and gap.end is not None:
        start = float(gap.start + shift)
        end = float(gap.end + shift)
    else:
        start = None
        end = None
    return Gap(gap.index, float(expected + shift), gap.score, method, start, end)


def apply_robust_grid(gaps: list[Gap], origin: float, pitch: float, strip_mode: str) -> tuple[list[Gap], dict[str, Any]]:
    if not gaps:
        return gaps, {"grid_used": False}
    constrained = [constrain_gap_to_geometry(gap, origin + pitch * gap.index, pitch, strip_mode) for gap in gaps]
    reliable = [gap for gap in constrained if gap.method == "detected" and gap.score >= 0.28]
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
    for gap in constrained:
        predicted = float(fit_origin + fit_pitch * gap.index)
        theoretical = float(origin + pitch * gap.index)
        predicted = max(theoretical - max_shift, min(theoretical + max_shift, predicted))
        if gap.method == "detected" and abs(gap.center - predicted) <= max(3.0, pitch * 0.025):
            adjusted.append(gap)
        else:
            adjusted.append(Gap(gap.index, predicted, gap.score, "grid"))
    return adjusted, {
        "grid_used": True,
        "reliable_gaps": len(reliable),
        "grid_inliers": int(inlier_count),
        "grid_pitch": float(fit_pitch),
        "grid_origin": float(fit_origin),
        "grid_residual": median_residual,
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
) -> list[Box]:
    if pitch is None:
        cuts = [float(outer.left)] + [gap.center + outer.left for gap in gaps] + [float(outer.right)]
    else:
        cuts = [outer.left + origin] + [outer.left + gap.center for gap in gaps] + [outer.left + origin + pitch * count]
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


def score_detection(gray_work: np.ndarray, outer: Box, gaps: list[Gap], boxes: list[Box], count: int, fmt: FilmFormat, strip_mode: str) -> tuple[float, list[str], dict[str, Any]]:
    expected_gaps = max(0, count - 1)
    actual_detected = sum(1 for gap in gaps if gap.method == "detected")
    grid_gaps = sum(1 for gap in gaps if gap.method == "grid")
    detected = actual_detected + grid_gaps
    equal = sum(1 for gap in gaps if gap.method == "equal")
    reliable = sum(1 for gap in gaps if gap.method in {"detected", "grid"} and gap.score >= 0.28)
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
    if width_cv > 0.030:
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
        if actual_detected < 2:
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
) -> Detection:
    h, w = gray.shape
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0 or outer.width <= 0:
        outer = Box(0, 0, ww, wh)
        crop = gray_work
    profile = separator_profile(crop)
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
    gaps, grid_detail = apply_robust_grid(gaps, origin, pitch, strip_mode)
    if strip_mode == "full" and bool(grid_detail.get("grid_used", False)):
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
            profile = separator_profile(crop)
            pitch = outer.width / float(max(1, count))
            origin = 0.0
            gaps = [find_gap(profile, pitch * i, pitch, i) for i in range(1, count)]
            gaps, grid_detail = apply_robust_grid(gaps, origin, pitch, strip_mode)
            grid_detail["outer_refined"] = True
    boxes_work = frame_boxes_from_gaps(outer, gaps, count, ww, wh, config.bleed_x, config.bleed_y, origin=origin, pitch=pitch)
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
            "partial_edge_hint": partial_edge_hint(profile, origin, pitch, count) if strip_mode == "partial" else {},
            "gap_centers": [gap.center for gap in gaps],
            "gap_scores": [gap.score for gap in gaps],
            "gap_methods": [gap.method for gap in gaps],
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
) -> Detection:
    gray_work = work_gray(gray, config.layout)
    outer_candidates = detect_outer_candidates(gray_work)
    candidates = [
        build_detection_for_outer(gray, config, fmt, count, strip_mode, candidate.box, offset_fraction, candidate.name)
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


def choose_detection(gray: np.ndarray, config: Config, fmt: FilmFormat) -> Detection:
    if config.strip_mode == "full":
        return detect_for_count(gray, config, fmt, config.count, "full")
    if config.strip_mode == "partial":
        detections = [
            detect_for_count(gray, config, fmt, c, "partial", offset)
            for c in partial_candidates(fmt, None)
            for offset in partial_offsets(fmt, c)
        ]
        return max(detections, key=lambda d: detection_rank(d, config.confidence_threshold))

    full = detect_for_count(gray, config, fmt, config.count, "full")
    if full.confidence >= config.confidence_threshold:
        return full
    partials = [
        detect_for_count(gray, config, fmt, c, "partial", offset)
        for c in partial_candidates(fmt, full)
        for offset in partial_offsets(fmt, c)
    ]
    best_partial = max(partials, key=lambda d: detection_rank(d, config.confidence_threshold))
    if best_partial.confidence >= config.confidence_threshold:
        best_partial.detail["auto_full_confidence"] = full.confidence
        return best_partial
    full.detail["partial_best"] = {
        "count": best_partial.count,
        "confidence": best_partial.confidence,
        "reasons": best_partial.review_reasons,
    }
    return full


def enhanced_detection_is_better(base: Detection, enhanced: Detection, config: Config) -> bool:
    if enhanced.count != base.count and enhanced.confidence < config.confidence_threshold:
        return False
    base_width = float(base.detail.get("width_cv", 1.0))
    enhanced_width = float(enhanced.detail.get("width_cv", 1.0))
    base_area = float(base.detail.get("outer_area_ratio", 0.0))
    enhanced_area = float(enhanced.detail.get("outer_area_ratio", 0.0))
    geometry_not_worse = enhanced_width <= max(0.040, base_width * 1.25) and enhanced_area >= base_area - 0.04
    if not geometry_not_worse:
        return False
    if enhanced.confidence >= config.confidence_threshold and base.confidence < config.confidence_threshold:
        return True
    return enhanced.confidence >= base.confidence + 0.10


def choose_detection_with_analysis(gray: np.ndarray, config: Config, fmt: FilmFormat) -> Detection:
    base = choose_detection(gray, config, fmt)
    base.detail["analysis_source"] = "base"
    if config.analysis == "off":
        return base
    if config.analysis == "auto" and base.confidence >= config.confidence_threshold:
        base.detail["analysis_skipped"] = "base_confident"
        return base

    enhanced_gray = make_analysis_gray(gray)
    enhanced = choose_detection(enhanced_gray, config, fmt)
    enhanced.detail["analysis_source"] = "enhanced"
    enhanced.detail["base_confidence"] = base.confidence
    enhanced.detail["base_reasons"] = list(base.review_reasons)

    if config.analysis == "always" and enhanced_detection_is_better(base, enhanced, config):
        return enhanced
    if config.analysis == "auto" and enhanced_detection_is_better(base, enhanced, config):
        return enhanced

    base.detail["analysis_candidate"] = {
        "confidence": enhanced.confidence,
        "count": enhanced.count,
        "reasons": enhanced.review_reasons,
        "selected": False,
    }
    return base


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
    work_outer_raw = detection.detail.get("work_outer")
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
    if gap.method == "detected" and gap.start is not None and gap.end is not None:
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
    work_outer_raw = detection.detail.get("work_outer")
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


def debug_status_label(detection: Detection, threshold: float) -> tuple[str, tuple[int, int, int]]:
    passed = detection.confidence >= threshold
    status = "PASS" if passed else "REVIEW"
    op = ">=" if passed else "<"
    label = f"{status} confidence {detection.confidence:.3f} {op} threshold {threshold:.3f}"
    if detection.review_reasons:
        label += " | " + ",".join(detection.review_reasons[:3])
    color = (40, 180, 90) if passed else (230, 80, 70)
    return label, color


def add_status_bar(rgb: np.ndarray, detection: Detection, threshold: float) -> np.ndarray:
    label, color = debug_status_label(detection, threshold)
    bar_h = 40
    h, w = rgb.shape[:2]
    panel = np.full((h + bar_h, w, 3), 18, dtype=np.uint8)
    panel[bar_h:, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, w - 1, bar_h - 1), outline=color, width=2)
    draw.text((12, 12), label, fill=(245, 245, 245))
    return np.asarray(image)


def write_debug_preview(gray: np.ndarray, detection: Detection, output_path: Path, threshold: float) -> None:
    rgb = add_status_bar(make_debug_preview_rgb(gray, detection), detection, threshold)
    write_rgb_jpeg(rgb, output_path)


def make_debug_preview_rgb(gray: np.ndarray, detection: Detection) -> np.ndarray:
    rgb, scale = preview_gray(gray)
    draw_preview_rect(rgb, detection.outer, scale, (0, 255, 0), 3)
    for box in detection.frames:
        draw_preview_rect(rgb, box, scale, (0, 128, 255), 2)
    gap_colors = {
        "detected": (255, 0, 0),
        "grid": (255, 220, 30),
        "equal": (190, 80, 255),
        "equal-broad-region": (190, 80, 255),
    }
    pitch = float(detection.detail.get("pitch", 0.0) or 0.0)
    detected_centers = [gap.center for gap in detection.gaps if gap.method == "detected"]
    overlap_tolerance = max(4.0, pitch * 0.012)
    for gap in detection.gaps:
        if gap.method != "detected":
            continue
        mark = gap_mark_box(detection, gap)
        if mark is not None:
            draw_preview_mark(rgb, mark, scale, gap_colors.get(gap.method, (255, 255, 255)), 2)
    for gap in detection.gaps:
        if gap.method == "detected":
            continue
        if any(abs(gap.center - center) <= overlap_tolerance for center in detected_centers):
            continue
        color = gap_colors.get(gap.method, (255, 255, 255))
        for tick in gap_tick_boxes(detection, gap):
            if detection.layout == "horizontal":
                draw_preview_line(rgb, tick, scale, color, 2)
            else:
                draw_preview_hline(rgb, tick, scale, color, 2)
    return rgb


def write_rgb_jpeg(rgb: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(np.ascontiguousarray(rgb), mode="RGB")
    image.save(output_path, format="JPEG", quality=92, optimize=True)


def write_gray_preview_jpeg(gray: np.ndarray, output_path: Path) -> None:
    rgb, _ = preview_gray(gray)
    write_rgb_jpeg(rgb, output_path)


def add_panel_label(rgb: np.ndarray, label: str) -> np.ndarray:
    label_h = 34
    h, w = rgb.shape[:2]
    panel = np.full((h + label_h, w, 3), 18, dtype=np.uint8)
    panel[label_h:, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.text((12, 9), label, fill=(245, 245, 245))
    return np.asarray(image)


def make_debug_analysis_panel(gray: np.ndarray, detection: Detection, threshold: float) -> np.ndarray:
    status, _ = debug_status_label(detection, threshold)
    debug_rgb = add_panel_label(make_debug_preview_rgb(gray, detection), f"Debug boxes | {status.split()[0]}")
    base_rgb, _ = preview_gray(gray)
    base_rgb = add_panel_label(base_rgb, "Original gray")
    enhanced_rgb, _ = preview_gray(make_analysis_gray(gray))
    enhanced_rgb = add_panel_label(enhanced_rgb, "Enhanced gray")
    panels = [debug_rgb, base_rgb, enhanced_rgb]
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


def write_debug_analysis(gray: np.ndarray, detection: Detection, output_dir: Path, stem: str, threshold: float) -> list[str]:
    analysis_dir = output_dir / "_debug_analysis"
    panel_path = analysis_dir / f"{stem}_debug_analysis.jpg"
    write_rgb_jpeg(make_debug_analysis_panel(gray, detection, threshold), panel_path)
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


def copy_for_review(input_file: Path, review_dir: Path) -> Path:
    review_dir.mkdir(parents=True, exist_ok=True)
    target = review_dir / input_file.name
    if target.exists():
        return target
    shutil.copy2(input_file, target)
    return target


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


def process_one(input_file: Path, config: Config) -> ProcessResult:
    output_dir = output_directory_for(input_file, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    arr, gray, profile, warnings, page = read_tiff(input_file, config.page)
    source_arr = arr
    h, w = spatial_shape(arr)
    film_format = infer_format_from_holder(w, h) if config.format_auto else config.film_format
    fmt = FORMATS[film_format]
    count = int(fmt.default_count if config.count_override is None else config.count_override)
    if count not in fmt.allowed_counts:
        allowed = ", ".join(str(x) for x in fmt.allowed_counts)
        raise ValueError(f"--format {fmt.name} allows --count values: {allowed}")
    layout = infer_layout(w, h) if config.layout_auto else config.layout
    config = replace(config, film_format=film_format, layout=layout, count=count)

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

    detection = choose_detection_with_analysis(gray, config, fmt)
    if detection.confidence < config.confidence_threshold:
        if config.format_auto:
            detection.review_reasons.append("format_auto_low_confidence")
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
        for i, box in enumerate(detection.frames, 1):
            if not box.valid():
                raise RuntimeError(f"Invalid crop box for frame {i}: {box}")
            out_path = output_dir / f"{input_file.stem}_{i:02d}.tif"
            if out_path.exists() and not config.overwrite:
                raise RuntimeError(f"Output exists: {out_path}; use --overwrite")
            cropped = np.ascontiguousarray(crop_array(arr, profile.axes, box))
            if not deskew_detail["applied"]:
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

    if config.debug and not config.debug_analysis:
        debug_path = output_dir / "_debug" / f"{input_file.stem}_debug.jpg"
        write_debug_preview(gray, detection, debug_path, config.confidence_threshold)
        warnings.append(f"debug preview: {debug_path}")
    if config.debug_analysis:
        for analysis_path in write_debug_analysis(gray, detection, output_dir, input_file.stem, config.confidence_threshold):
            warnings.append(f"debug analysis: {analysis_path}")

    detail = dict(detection.detail)
    detail["deskew"] = deskew_detail
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
    parser = argparse.ArgumentParser(description="Clean X5 single-strip TIFF film cropper.")
    parser.add_argument("input", nargs="?", default=".", help="TIFF file or directory; default current directory.")
    parser.add_argument("-o", "--output", default=None, help="Output directory; default input/split_output.")
    parser.add_argument("--format", choices=FORMAT_CHOICES, default="auto", help="auto detects 135 vs 120 family. half/xpan require explicit selection.")
    parser.add_argument("--layout", choices=LAYOUT_CHOICES, default="auto", help="auto/horizontal/vertical single-strip layout.")
    parser.add_argument("--strip", choices=STRIP_CHOICES, default="auto", help="full, partial, or auto full-then-partial.")
    parser.add_argument("-n", "--count", type=int, default=None, help="Override frame count.")
    parser.add_argument("--page", type=int, default=0, help="TIFF page index; default 0.")
    parser.add_argument("--bleed", type=int, default=10, help="Bleed in pixels on all sides; default 10.")
    parser.add_argument("--bleed-x", type=int, default=None, help="Horizontal bleed override.")
    parser.add_argument("--bleed-y", type=int, default=None, help="Vertical bleed override.")
    parser.add_argument("--deskew", choices=DESKEW_CHOICES, default="auto", help="Deskew strip before detection/export.")
    parser.add_argument("--analysis", choices=ANALYSIS_CHOICES, default="auto", help="Detection-only enhanced gray candidate: off, auto, or always.")
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
    parser.add_argument("--debug-analysis", action="store_true", help="Write one combined JPG with debug boxes, original gray, and enhanced gray.")
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
        shape = tif.pages[int(args.page)].shape
    height, width = int(shape[0]), int(shape[1])

    format_auto = str(args.format) == "auto"
    film_format = infer_format_from_holder(width, height) if format_auto else str(args.format)
    fmt = FORMATS[film_format]
    count = int(fmt.default_count if args.count is None else args.count)
    if not format_auto and count not in fmt.allowed_counts:
        allowed = ", ".join(str(x) for x in fmt.allowed_counts)
        raise ValueError(f"--format {fmt.name} allows --count values: {allowed}")
    layout_auto = str(args.layout) == "auto"
    layout = infer_layout(width, height) if layout_auto else str(args.layout)
    bleed_x = int(args.bleed if args.bleed_x is None else args.bleed_x)
    bleed_y = int(args.bleed if args.bleed_y is None else args.bleed_y)
    if bleed_x < 0 or bleed_y < 0:
        raise ValueError("Bleed cannot be negative")
    if not (0.0 <= float(args.confidence_threshold) <= 1.0):
        raise ValueError("--confidence-threshold must be between 0 and 1")
    if float(args.deskew_min_angle) < 0 or float(args.deskew_max_angle) <= 0:
        raise ValueError("Deskew angle limits are invalid")
    return Config(
        input_path=input_path,
        output_dir=Path(args.output).expanduser().resolve() if args.output else None,
        film_format=film_format,
        format_auto=format_auto,
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
    )


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
    format_label = f"auto(probe={config.film_format})" if config.format_auto else config.film_format
    layout_label = f"auto(probe={config.layout})" if config.layout_auto else config.layout
    count_label = "auto" if config.count_override is None else str(config.count_override)
    print(f"format: {format_label}; layout: {layout_label}; strip: {config.strip_mode}; count: {count_label}")
    print(f"threshold: {config.confidence_threshold:.2f}; analysis={config.analysis}; dry_run={config.dry_run}")

    ok = 0
    failed = 0
    approved = 0
    review = 0
    for path in files:
        print(f"\n[{path.name}]")
        try:
            result = process_one(path, config)
            ok += 1
            approved += int(result.status == "approved_auto")
            review += int(result.status == "needs_review")
            print(f"  status={result.status} confidence={result.confidence:.3f} format={result.film_format} count={result.count}")
            for warning in result.warnings:
                print(f"  warning: {warning}")
            for out in result.output_files:
                print(f"  wrote: {Path(out).name}")
        except Exception as exc:
            failed += 1
            print(f"  error: {exc}", file=sys.stderr)
            if config.debug_errors:
                traceback.print_exc()

    print(f"\ndone: ok={ok} failed={failed} approved={approved} review={review}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
