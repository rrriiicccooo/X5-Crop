#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X5_Split_v17.py

安全切分横向 135 胶片 TIFF 长条图。v17 是速度优先的主线整理版：保留 deskew 与检测增强，默认移除 v14-v16 的多阶段慢速补救链。

核心变化：
- --deskew 默认 auto：先检测胶片条是否倾斜；若判断可信，则先小角度旋转校平，再执行外框、分隔线、片距、同画幅尺寸和 bleed 裁切。
- --analysis-enhance 默认 auto：生成检测专用混合增强图；base 检测已稳定时自动跳过增强候选管线以提速。
- 如需完全不旋转、不重采样，可显式使用 --deskew off。
- 检测增强只服务于坐标分析，不写入输出；输出仍尽量保持 dtype、位深、Photometric、ICC、分辨率等关键 TIFF 属性。
- 默认已知横向 count 张，在理论分隔位置附近局部寻找窄分隔带；可疑时回退等分。
- 默认按分隔带中心切线切分，不删除整段黑/白带，避免欠曝区域被误裁。
- 默认每张上下左右各额外保留 10px bleed，降低裁到画面内容的风险。
- 写出后重新打开输出 TIFF 校验 dtype、shape、BitsPerSample、Photometric、ICC、分辨率等关键属性。

macOS 常用命令：
    python3 -m pip install -U numpy tifffile imagecodecs Pillow
    python3 X5_Split_v17.py . --debug --dry-run --report
    python3 X5_Split_v17.py . --debug --overwrite --report

Windows 常用命令：
    py -3 -m pip install -U numpy tifffile imagecodecs Pillow
    py -3 X5_Split_v17.py . --debug --dry-run --report
    py -3 X5_Split_v17.py . --debug --overwrite --report
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
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import numpy as np
import tifffile

VERSION = "17.0-speed-balanced"
SCRIPT_NAME = "X5_Split_v17.py"
TRACEBACK_ENV = "X5_SPLIT_TRACEBACK"
TIFF_SUFFIXES = {".tif", ".tiff"}


def configure_text_output() -> None:
    """Avoid UnicodeEncodeError on ASCII or legacy-codepage terminals."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


configure_text_output()

# Tags that are either invalid after cropping or are written by tifffile parameters.
# They are intentionally not blindly copied through extra_tags.
HANDLED_OR_STRUCTURAL_TAGS = {
    254, 255,       # SubfileType
    256, 257,       # ImageWidth, ImageLength
    258,            # BitsPerSample
    259,            # Compression
    262,            # PhotometricInterpretation
    263, 264, 265, 266,
    269,            # DocumentName
    270,            # ImageDescription
    273,            # StripOffsets
    274,            # Orientation; handled explicitly
    277,            # SamplesPerPixel
    278, 279,       # RowsPerStrip, StripByteCounts
    280, 281, 282, 283, 284, 285, 286, 287, 288, 289,
    290, 291, 292, 293, 296, 297,
    305, 306,       # Software, DateTime
    317,            # Predictor
    318, 319, 320, 321,
    322, 323, 324, 325,  # Tile metadata
    330,            # SubIFDs
    338,            # ExtraSamples
    339,            # SampleFormat
    340, 341, 342, 343, 344, 345,
    34675,          # ICC profile
    347,            # JPEGTables
    512, 513, 514, 515, 517, 518, 519, 520, 521,
    529, 530, 531, 532,
    700,            # XMP often contains original dimensions; not safe to copy by default
    34665, 34853, 40965, 42112, 42113,
}

LOSSLESS_COMPRESSION_NAMES = {
    "NONE",
    "CCITTRLE",
    "CCITT_T4",
    "CCITT_T6",
    "LZW",
    "PACKBITS",
    "DEFLATE",
    "ADOBE_DEFLATE",
    "LZMA",
    "ZSTD",
}

LOSSY_OR_UNCERTAIN_COMPRESSION_NAMES = {
    "OJPEG",
    "JPEG",
    "JPEG_2000",
    "JPEG2000",
    "JPEGXR",
    "JPEGXL",
    "WEBP",
    "LERC",
}


# -----------------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Box:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def clamp(self, width: int, height: int) -> "Box":
        return Box(
            left=max(0, min(int(self.left), int(width))),
            top=max(0, min(int(self.top), int(height))),
            right=max(0, min(int(self.right), int(width))),
            bottom=max(0, min(int(self.bottom), int(height))),
        )

    def valid(self) -> bool:
        return self.right > self.left and self.bottom > self.top


@dataclass(frozen=True)
class Gap:
    """Internal separator position relative to the outer-cropped image."""

    start: int          # inclusive
    end: int            # exclusive
    center: float
    score: float
    method: str

    @property
    def width(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class GridModel:
    """Global frame-spacing model: boundary k is start + k * pitch."""

    start: float
    pitch: float
    inlier_indices: tuple[int, ...]
    median_residual: float
    max_residual: float


@dataclass(frozen=True)
class OuterRefineModel:
    """Horizontal outer-box correction inferred from reliable internal boundaries."""

    original_left: int
    original_right: int
    refined_left: int
    refined_right: int
    start: float
    pitch: float
    inlier_indices: tuple[int, ...]
    left_shift: float
    right_shift: float
    mode: str
    iteration: int


@dataclass(frozen=True)
class DeskewModel:
    """Optional pre-detection deskew model.

    In auto/strict mode, the source pixels may be rotated first, and the stable
    detection pipeline then runs on the rotated/horizontal raster. The operation
    is geometric only; it does not intentionally alter tone, contrast, color
    space, bit depth, ICC, or other post-production/color-management metadata.
    """

    mode: str
    angle_degrees: float
    slope: float
    top_slope: float
    bottom_slope: float
    top_span: float
    bottom_span: float
    top_inliers: int
    bottom_inliers: int
    top_median_residual: float
    bottom_median_residual: float
    input_width: int
    input_height: int
    output_width: int
    output_height: int
    interpolation: str


@dataclass
class TiffProfile:
    path: str
    is_bigtiff: bool
    byteorder: str
    shape: tuple[int, ...]
    dtype: str
    axes: str
    width: int
    height: int
    samples_per_pixel: int
    bits_per_sample: Any
    sample_format: Any
    photometric: int
    photometric_name: str
    planarconfig: int
    planarconfig_name: str
    extrasamples: tuple[int, ...]
    compression: int
    compression_name: str
    predictor: int
    rowsperstrip: Optional[int]
    is_tiled: bool
    tile: Optional[tuple[int, int]]
    resolution: Optional[tuple[Any, Any]]
    resolution_unit: Any
    orientation: Any
    icc_len: int
    colormap_shape: Optional[tuple[int, ...]]
    description_copied: bool


@dataclass(frozen=True)
class FrameSizeModel:
    """Same-frame-size correction model for 135 strips."""

    target_width: float
    sample_indices: tuple[int, ...]
    sample_widths: tuple[float, ...]
    adjusted_indices: tuple[int, ...]
    mode: str


@dataclass(frozen=True)
class FilmFormatProfile:
    name: str
    frame_aspect: float
    default_count: int
    allowed_counts: tuple[int, ...]
    family: str


FILM_FORMATS: dict[str, FilmFormatProfile] = {
    "135": FilmFormatProfile("135", 3.0 / 2.0, 6, tuple(range(1, 7)), "35mm"),
    "half": FilmFormatProfile("half", 3.0 / 4.0, 12, tuple(range(1, 13)), "35mm"),
    "xpan": FilmFormatProfile("xpan", 65.0 / 24.0, 3, (1, 2, 3), "35mm"),
    "120-645": FilmFormatProfile("120-645", 4.0 / 3.0, 4, (1, 2, 3, 4), "120"),
    "120-66": FilmFormatProfile("120-66", 1.0, 3, (1, 2, 3), "120"),
    "120-67": FilmFormatProfile("120-67", 4.0 / 5.0, 3, (1, 2, 3), "120"),
}

FORMAT_CHOICES = ("auto", *FILM_FORMATS.keys())
LAYOUT_CHOICES = ("auto", "single-horizontal", "single-vertical")


@dataclass
class ProcessResult:
    source: str
    film_format: str
    layout: str
    strip_completeness: str
    lane_count: int
    frames_per_lane: int
    status: str
    confidence: float
    review_reasons: list[str]
    review_copy: Optional[str]
    output_files: list[str]
    outer_box: dict[str, int]
    frame_boxes: list[dict[str, int]]
    gaps: list[dict[str, Any]]
    outer_refine_model: Optional[dict[str, Any]]
    deskew_model: Optional[dict[str, Any]]
    frame_size_model: Optional[dict[str, Any]]
    analysis_candidate: Optional[dict[str, Any]]
    detection_detail: dict[str, Any]
    profile: dict[str, Any]
    warnings: list[str]


@dataclass
class DetectionRun:
    """One complete detection pass based on a specific analysis gray map."""

    label: str
    outer: Box
    gaps: list[Gap]
    boxes: list[Box]
    outer_refine_model: Optional[OuterRefineModel]
    frame_size_model: Optional[FrameSizeModel]
    warnings: list[str]
    score: float
    score_detail: dict[str, Any]


@dataclass(frozen=True)
class SplitConfig:
    input_path: Path
    output: Optional[Path]
    film_format: str
    format_auto: bool
    layout: str
    strip_completeness: str
    count: int
    page: int

    deskew: str
    deskew_interpolation: str
    deskew_min_angle_deg: float
    deskew_max_angle_deg: float
    deskew_min_span_px: int
    deskew_samples: int
    deskew_search_margin_ratio: float
    deskew_sample_window_ratio: float
    deskew_edge_min_strength: float
    deskew_line_tolerance_px: float
    deskew_max_slope_delta: float
    deskew_chunk_rows: int

    analysis_enhance: str
    analysis_percentile_low: float
    analysis_percentile_high: float
    analysis_shadow_gamma: float
    analysis_edge_weight: float
    analysis_texture_weight: float
    analysis_candidate_gain_ratio: float
    analysis_preserve_gutter: bool
    analysis_gutter_extreme_ratio: float
    analysis_gutter_max_activity: float
    analysis_gutter_max_width_ratio: float
    analysis_geometry_select: bool
    analysis_geometry_min_base_cv: float
    analysis_fast_skip: bool
    analysis_edge_candidate: str
    debug_analysis: bool

    black_thresh: int
    white_thresh: int
    border_ratio: float
    border_min_run_frac: float
    outer_keep_margin: int
    no_outer_crop: bool
    outer_x_detect: str
    outer_x_auto_min_gain_ratio: float
    outer_x_auto_max_expand_ratio: float

    outer_refine: str
    outer_refine_min_inliers: int
    outer_refine_tolerance_ratio: float
    outer_refine_pitch_tolerance_ratio: float
    outer_refine_max_shift_ratio: float
    outer_refine_max_width_change_ratio: float
    outer_refine_min_shift_px: int
    outer_refine_iterations: int

    equal_split: bool
    search_ratio: float
    min_gap_score: float
    min_gap_prominence: float
    max_gap_ratio: float
    min_gap_ratio: float
    side_guard_ratio: float
    vertical_slices: int
    center_y0: float
    center_y1: float
    allow_peak_fallback: bool

    edge_refine: bool
    edge_refine_single: str
    edge_search_ratio: float
    edge_min_strength: float
    edge_min_bg_ratio: float
    edge_max_gutter_ratio: float
    edge_min_gutter_px: int

    grid_fit: str
    grid_min_inliers: int
    grid_tolerance_ratio: float
    grid_pitch_tolerance_ratio: float
    grid_min_replace_px: int

    frame_size_fit: str
    frame_size_min_samples: int
    frame_size_tolerance_ratio: float
    frame_size_min_ratio: float
    frame_size_max_ratio: float
    frame_size_base_weight: float

    bleed_x: int
    bleed_y: int
    gap_crop_mode: str
    gap_trim_px: int

    compression: str
    allow_lossy_compression: bool
    allow_packed_bit_depth: bool
    extra_tags: str
    copy_description: str
    preserve_tiling: bool

    confidence_threshold: float
    review_dir: Optional[Path]
    copy_review_files: bool
    export_low_confidence: bool

    debug: bool
    dry_run: bool
    overwrite: bool
    report: bool


@dataclass
class LayoutDetection:
    film_format: str
    layout: str
    lane_count: int
    frames_per_lane: int
    outer: Box
    boxes: list[Box]
    gaps: list[Gap]
    outer_refine_model: Optional[OuterRefineModel]
    frame_size_model: Optional[FrameSizeModel]
    analysis_candidate: dict[str, Any]
    warnings: list[str]
    confidence: float
    review_reasons: list[str]
    detection_detail: dict[str, Any]


# -----------------------------------------------------------------------------
# Generic helpers
# -----------------------------------------------------------------------------

def enum_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        try:
            return int(value.value)
        except Exception:
            return default


def enum_name(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return getattr(value, "name", str(value))


def tag_value(page: tifffile.TiffPage, code: int, default: Any = None) -> Any:
    tag = page.tags.get(code)
    return default if tag is None else tag.value


def normalize_value(value: Any) -> Any:
    """Normalize tag values for comparison and JSON reporting."""
    if isinstance(value, np.ndarray):
        return normalize_value(value.tolist())
    if isinstance(value, (list, tuple)):
        return tuple(normalize_value(v) for v in value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    try:
        if hasattr(value, "value") and hasattr(value, "name"):
            return int(value)
    except Exception:
        pass
    return value


def json_safe(value: Any) -> Any:
    value = normalize_value(value)
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    return value


@lru_cache(maxsize=1)
def has_imagecodecs() -> bool:
    try:
        import imagecodecs  # noqa: F401
        return True
    except Exception:
        return False


def text_tag_value(page: tifffile.TiffPage, code: int) -> Optional[str]:
    """Return a TIFF ASCII text tag as str, or None if it is empty/unsafe to pass through."""
    value = tag_value(page, code)
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    elif isinstance(value, bytearray):
        value = bytes(value).decode("utf-8", "ignore")
    else:
        value = str(value)
    value = value.rstrip("\x00")
    return value if value else None


def temp_tiff_path(out_path: Path) -> Path:
    """Return a temporary TIFF-looking path so tifffile never has to infer from .tmp."""
    return out_path.with_name(out_path.stem + ".tmp" + out_path.suffix)


# -----------------------------------------------------------------------------
# Axis, grayscale, and crop helpers
# -----------------------------------------------------------------------------

def infer_axes(page: tifffile.TiffPage, arr: np.ndarray) -> str:
    axes = getattr(page, "axes", None)
    if axes and len(axes) == arr.ndim and "Y" in axes and "X" in axes:
        return str(axes)

    samples = int(getattr(page, "samplesperpixel", 1) or 1)
    if arr.ndim == 2:
        return "YX"
    if arr.ndim == 3:
        if arr.shape[-1] == samples:
            return "YXS"
        if arr.shape[0] == samples:
            return "SYX"

    raise RuntimeError(
        f"无法判断 TIFF 图像轴顺序：shape={arr.shape}, "
        f"samplesperpixel={samples}, page.axes={axes!r}。"
    )


def spatial_size(arr: np.ndarray, axes: str) -> tuple[int, int]:
    return int(arr.shape[axes.index("Y")]), int(arr.shape[axes.index("X")])


def crop_yx(arr: np.ndarray, axes: str, box: Box) -> np.ndarray:
    slices: list[slice] = [slice(None)] * arr.ndim
    slices[axes.index("Y")] = slice(box.top, box.bottom)
    slices[axes.index("X")] = slice(box.left, box.right)
    return arr[tuple(slices)]


def as_yxs_or_yx(arr: np.ndarray, axes: str) -> np.ndarray:
    """Return a view whose first two dimensions are Y, X and optional third is samples."""
    if axes == "YX":
        return arr
    if "S" in axes:
        return np.moveaxis(arr, [axes.index("Y"), axes.index("X"), axes.index("S")], [0, 1, 2])
    return np.moveaxis(arr, [axes.index("Y"), axes.index("X")], [0, 1])


def dtype_fullscale(dtype: np.dtype, bits_per_sample: Any) -> float:
    dtype = np.dtype(dtype)
    bits = bits_per_sample[0] if isinstance(bits_per_sample, (tuple, list)) and bits_per_sample else bits_per_sample
    try:
        bit_count = int(bits)
    except Exception:
        bit_count = dtype.itemsize * 8

    if np.issubdtype(dtype, np.integer):
        return float((1 << max(1, bit_count)) - 1)
    if np.issubdtype(dtype, np.floating):
        return 1.0
    return 255.0


def channel_to_u8(channel: np.ndarray, fullscale: float) -> np.ndarray:
    """Scale a single channel to uint8 for detection/debug only."""
    if np.issubdtype(channel.dtype, np.floating):
        finite = channel[np.isfinite(channel)]
        if finite.size == 0:
            return np.zeros(channel.shape, dtype=np.uint8)
        lo, hi = np.percentile(finite, [0.1, 99.9])
        if hi <= lo:
            hi = lo + 1.0
        scaled = (np.clip(channel, lo, hi) - lo) / (hi - lo) * 255.0
        return scaled.astype(np.uint8)

    if fullscale <= 0:
        fullscale = float(np.iinfo(channel.dtype).max) if np.issubdtype(channel.dtype, np.integer) else 255.0
    scaled = np.clip(channel.astype(np.float32) / fullscale * 255.0, 0, 255)
    return scaled.astype(np.uint8)


def make_gray_u8(arr: np.ndarray, axes: str, bits_per_sample: Any, photometric: int) -> np.ndarray:
    """
    Convert TIFF array to 8-bit grayscale for boundary detection only.
    This function never feeds output pixels, so it cannot change saved bit depth or color.
    """
    fullscale = dtype_fullscale(arr.dtype, bits_per_sample)
    view = as_yxs_or_yx(arr, axes)

    if view.ndim == 2:
        gray = channel_to_u8(view, fullscale)
    elif view.ndim == 3:
        sample_count = view.shape[-1]
        if sample_count >= 3:
            c0 = channel_to_u8(view[..., 0], fullscale).astype(np.float32)
            c1 = channel_to_u8(view[..., 1], fullscale).astype(np.float32)
            c2 = channel_to_u8(view[..., 2], fullscale).astype(np.float32)
            gray = np.clip(0.299 * c0 + 0.587 * c1 + 0.114 * c2, 0, 255).astype(np.uint8)
        else:
            gray = channel_to_u8(view[..., 0], fullscale)
    else:
        raise RuntimeError(f"不支持的检测数组维度：view.shape={view.shape}, axes={axes!r}")

    # MINISWHITE: 0 means white. Invert only for more intuitive debug/threshold behavior.
    if int(photometric) == 0:
        gray = 255 - gray
    return gray



def sampled_values_for_percentile(gray: np.ndarray, max_samples: int = 1_000_000) -> np.ndarray:
    """Return a deterministic sample for robust percentiles without copying giant arrays."""
    flat = gray.ravel()
    if flat.size <= max_samples:
        return flat
    step = max(1, flat.size // max_samples)
    return flat[::step]


def percentile_stretch_u8(gray: np.ndarray, low: float, high: float, gamma: float) -> np.ndarray:
    """Detection-only percentile stretch with optional shadow-lift gamma."""
    if gray.size == 0:
        return gray.copy()
    sample = sampled_values_for_percentile(gray)
    lo, hi = np.percentile(sample.astype(np.float32, copy=False), [float(low), float(high)])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo + 1e-6:
        return gray.copy()
    norm = (gray.astype(np.float32, copy=False) - float(lo)) / float(hi - lo)
    np.clip(norm, 0.0, 1.0, out=norm)
    g = max(0.05, float(gamma))
    if abs(g - 1.0) > 1e-6:
        norm = np.power(norm, g, dtype=np.float32)
    return np.clip(norm * 255.0, 0, 255).astype(np.uint8)


def edge_magnitude_u8(gray: np.ndarray) -> np.ndarray:
    """Cheap full-frame edge map for detection scoring/debug only."""
    if gray.size == 0:
        return gray.copy()
    g16 = gray.astype(np.int16, copy=False)
    edge = np.zeros(gray.shape, dtype=np.uint8)
    if gray.shape[1] > 1:
        gx = np.abs(np.diff(g16, axis=1))
        gx = np.clip(gx, 0, 255).astype(np.uint8)
        edge[:, 1:] = np.maximum(edge[:, 1:], gx)
        edge[:, :-1] = np.maximum(edge[:, :-1], gx)
    if gray.shape[0] > 1:
        gy = np.abs(np.diff(g16, axis=0))
        gy = np.clip(gy, 0, 255).astype(np.uint8)
        edge[1:, :] = np.maximum(edge[1:, :], gy)
        edge[:-1, :] = np.maximum(edge[:-1, :], gy)
    # Edge magnitude has a very skewed distribution; stretch high percentiles.
    return percentile_stretch_u8(edge, 70.0, 99.7, 0.70)


def dilate_bool_1d(mask: np.ndarray, radius: int) -> np.ndarray:
    """Small 1D dilation helper used by the detection-only analysis layer."""
    if mask.size == 0:
        return mask.astype(bool, copy=False)
    radius = max(0, int(radius))
    if radius <= 0:
        return mask.astype(bool, copy=False)
    kernel = np.ones(radius * 2 + 1, dtype=np.int16)
    return np.convolve(mask.astype(np.int16, copy=False), kernel, mode="same") > 0


def keep_only_short_true_runs(mask: np.ndarray, max_width: int) -> np.ndarray:
    """Keep only short True runs; long runs are likely blank/underexposed frames, not gutters."""
    if mask.size == 0:
        return mask.astype(bool, copy=False)
    max_width = max(1, int(max_width))
    out = np.zeros(mask.shape, dtype=bool)
    for start, end in runs_from_mask(mask.astype(bool, copy=False)):
        if 0 < (end - start) <= max_width:
            out[start:end] = True
    return out


def make_analysis_gray(gray: np.ndarray, config: SplitConfig) -> np.ndarray:
    """
    Build a detection-only enhanced grayscale map for underexposed strips.

    v17 uses a hybrid strategy:
    - photographed content is lifted with percentile/gamma enhancement;
    - short, low-activity black/white gutters are preserved from the base map.

    This avoids the v17 failure mode where enhancement made true separators less
    extreme, while dark photographed areas were still ambiguous. Output TIFF pixels
    are always cropped from the original or deskewed source array, never from this map.
    """
    mode = str(config.analysis_enhance)
    if mode == "off" or gray.size == 0:
        return gray

    gamma = float(config.analysis_shadow_gamma)
    if mode == "strict":
        gamma = max(0.20, gamma * 0.82)
    low = float(config.analysis_percentile_low)
    high = float(config.analysis_percentile_high)
    shadow = percentile_stretch_u8(gray, low, high, gamma)

    edge_weight = max(0.0, min(0.80, float(config.analysis_edge_weight)))
    texture_weight = max(0.0, min(0.80, float(config.analysis_texture_weight)))
    if edge_weight <= 0.0 and texture_weight <= 0.0:
        enhanced = shadow
        edge = np.zeros_like(shadow, dtype=np.uint8)
    else:
        edge = edge_magnitude_u8(shadow)
        # Keep the result intensity-like; do not replace it with a pure edge map.
        # This preserves the existing threshold logic while making dark-content boundaries visible.
        mix_weight = min(0.70, edge_weight + texture_weight * 0.65)
        enhanced_f = shadow.astype(np.float32) * (1.0 - mix_weight)
        enhanced_f += np.maximum(shadow, edge).astype(np.float32) * mix_weight
        enhanced = np.clip(enhanced_f, 0, 255).astype(np.uint8)

    if not bool(config.analysis_preserve_gutter) or gray.ndim != 2 or gray.shape[1] <= 1:
        return enhanced

    height, width = gray.shape
    y0 = max(0, min(height - 1, int(round(height * float(config.center_y0)))))
    y1 = max(y0 + 1, min(height, int(round(height * float(config.center_y1)))))
    base_mid = gray[y0:y1, :]
    shadow_mid = shadow[y0:y1, :]
    edge_mid = edge[y0:y1, :] if edge.shape == gray.shape else edge_magnitude_u8(shadow)[y0:y1, :]

    if base_mid.size == 0:
        return enhanced

    dark_ratio = (base_mid <= int(config.black_thresh)).mean(axis=0).astype(np.float32)
    white_ratio = (base_mid >= int(config.white_thresh)).mean(axis=0).astype(np.float32)
    extreme_ratio = np.maximum(dark_ratio, white_ratio)

    # Activity is intentionally computed from the lifted map. Underexposed photo
    # content often becomes textured after shadow lifting, while a true film gutter
    # remains low-activity and vertically uniform.
    shadow_float = shadow_mid.astype(np.float32, copy=False)
    col_std = shadow_float.std(axis=0)
    edge_mean = edge_mid.astype(np.float32, copy=False).mean(axis=0)
    activity = normalize_profile(col_std + 0.60 * edge_mean, 95.0)

    extreme_threshold = max(0.50, min(0.995, float(config.analysis_gutter_extreme_ratio)))
    activity_threshold = max(0.0, min(1.0, float(config.analysis_gutter_max_activity)))
    raw_gutter_cols = (extreme_ratio >= extreme_threshold) & (activity <= activity_threshold)

    # Do not preserve an entire dark blank frame as a gutter. Only short vertical
    # runs are protected as separators. This is the key difference from a simple
    # "keep all black pixels" blend.
    nominal_frame_w = float(width) / max(1.0, float(config.count))
    max_run = max(3, int(round(nominal_frame_w * float(config.analysis_gutter_max_width_ratio))))
    gutter_cols = keep_only_short_true_runs(raw_gutter_cols, max_run)
    gutter_cols = dilate_bool_1d(gutter_cols, max(1, int(round(width * 0.00018))))

    if not gutter_cols.any():
        return enhanced

    hybrid = enhanced.copy()
    hybrid[:, gutter_cols] = gray[:, gutter_cols]
    return hybrid

def deskew_model_quality(model: Optional[DeskewModel]) -> float:
    if model is None:
        return -1e9
    inliers = float(model.top_inliers + model.bottom_inliers)
    residual = float(model.top_median_residual + model.bottom_median_residual)
    span_bonus = min(10.0, (abs(float(model.top_span)) + abs(float(model.bottom_span))) / 10.0)
    return inliers * 3.0 + span_bonus - residual * 1.5


def choose_deskew_model_from_analysis(
    base_gray: np.ndarray,
    analysis_gray: np.ndarray,
    config: SplitConfig,
) -> tuple[Optional[DeskewModel], list[str], str]:
    """Estimate deskew from base and optional enhanced analysis maps, then choose one."""
    if config.deskew == "off":
        return None, [], "off"

    base_outer = rough_outer_for_deskew(base_gray, config)
    base_model, base_warnings = estimate_deskew_model(base_gray, base_outer, config)
    if config.analysis_enhance == "off" or analysis_gray is base_gray or np.shares_memory(analysis_gray, base_gray):
        return base_model, base_warnings, "base"

    analysis_outer = rough_outer_for_deskew(analysis_gray, config)
    analysis_model, analysis_warnings = estimate_deskew_model(analysis_gray, analysis_outer, config)

    base_q = deskew_model_quality(base_model)
    analysis_q = deskew_model_quality(analysis_model)
    warnings: list[str] = []

    if analysis_model is not None and (base_model is None or analysis_q > base_q + (1.0 if config.analysis_enhance == "auto" else -0.25)):
        warnings.append(
            f"analysis-enhance 用于 deskew：选择增强分析图角度 {analysis_model.angle_degrees:.4f}° "
            f"而非 base 候选 {('none' if base_model is None else f'{base_model.angle_degrees:.4f}°')}。"
        )
        # If strict produced warnings for the chosen candidate, surface them.
        warnings.extend(analysis_warnings)
        return analysis_model, warnings, "analysis"

    warnings.extend(base_warnings)
    if analysis_model is not None and base_model is not None:
        warnings.append(
            f"analysis-enhance deskew 候选未采用：base={base_model.angle_degrees:.4f}°，"
            f"analysis={analysis_model.angle_degrees:.4f}°。"
        )
    return base_model, warnings, "base"


def vertical_deskew_model_from_transposed(model: Optional[DeskewModel], original_width: int, original_height: int) -> Optional[DeskewModel]:
    if model is None:
        return None
    angle_degrees = -float(model.angle_degrees)
    out_w, out_h, *_ = rotated_output_geometry(original_width, original_height, angle_degrees)
    return replace(
        model,
        mode=f"{model.mode}-vertical",
        angle_degrees=float(angle_degrees),
        slope=-float(model.slope),
        top_slope=-float(model.top_slope),
        bottom_slope=-float(model.bottom_slope),
        input_width=int(original_width),
        input_height=int(original_height),
        output_width=int(out_w),
        output_height=int(out_h),
    )


def choose_deskew_model_for_layout(
    base_gray: np.ndarray,
    analysis_gray: np.ndarray,
    config: SplitConfig,
) -> tuple[Optional[DeskewModel], list[str], str, str]:
    """Choose a deskew model whose target orientation matches the strip layout."""
    if config.layout == "single-vertical":
        work_config = config_for_split_axis(config, "y")
        work_base = np.ascontiguousarray(base_gray.T)
        work_analysis = np.ascontiguousarray(analysis_gray.T)
        model, warnings, source = choose_deskew_model_from_analysis(work_base, work_analysis, work_config)
        vertical_model = vertical_deskew_model_from_transposed(model, base_gray.shape[1], base_gray.shape[0])
        if vertical_model is not None:
            warnings.append(
                "deskew 竖向布局：在转置检测图上估计倾斜，并将反向角度应用到原图，使胶片条对齐垂直方向。"
            )
        return vertical_model, warnings, f"{source}-vertical", "垂直"

    model, warnings, source = choose_deskew_model_from_analysis(base_gray, analysis_gray, config)
    return model, warnings, source, "水平"


def moving_average(x: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window))
    if window <= 1:
        return x.astype(np.float32)
    if window % 2 == 0:
        window += 1
    pad = window // 2
    padded = np.pad(x.astype(np.float32), (pad, pad), mode="edge")
    kernel = np.ones(window, dtype=np.float32) / float(window)
    return np.convolve(padded, kernel, mode="valid")


def runs_from_mask(mask: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: Optional[int] = None
    for i, value in enumerate(mask):
        if bool(value) and start is None:
            start = i
        elif not bool(value) and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


# -----------------------------------------------------------------------------
# Detection: outer crop, separator detection, and frame boxes
# -----------------------------------------------------------------------------

def first_content_index(border_mask: np.ndarray, min_run: int) -> int:
    min_run = max(1, min(int(min_run), len(border_mask)))
    content = ~border_mask
    for i in range(0, len(border_mask) - min_run + 1):
        if content[i:i + min_run].mean() >= 0.8:
            return i
    candidates = np.flatnonzero(content)
    return int(candidates[0]) if candidates.size else 0


def detect_outer_box(
    gray: np.ndarray,
    black_thresh: int,
    white_thresh: int,
    border_ratio: float,
    min_run_frac: float,
    keep_margin: int,
) -> Box:
    """Detect content area by black/white background-pixel ratio, not row/column mean."""
    height, width = gray.shape
    background = (gray <= black_thresh) | (gray >= white_thresh)
    row_is_border = background.mean(axis=1) >= border_ratio
    col_is_border = background.mean(axis=0) >= border_ratio

    min_run_y = max(2, min(80, int(round(height * min_run_frac))))
    min_run_x = max(2, min(80, int(round(width * min_run_frac))))

    top = first_content_index(row_is_border, min_run_y)
    bottom = height - first_content_index(row_is_border[::-1], min_run_y)
    left = first_content_index(col_is_border, min_run_x)
    right = width - first_content_index(col_is_border[::-1], min_run_x)

    box = Box(left - keep_margin, top - keep_margin, right + keep_margin, bottom + keep_margin).clamp(width, height)
    return box if box.valid() else Box(0, 0, width, height)



def detect_outer_box_white_x(
    gray: np.ndarray,
    black_thresh: int,
    white_thresh: int,
    border_ratio: float,
    min_run_frac: float,
    keep_margin: int,
) -> Box:
    """Detect outer box while treating horizontal black columns as possible image content.

    Top/bottom still use black-or-white border detection. Left/right only treat
    near-white columns as background. This protects extremely underexposed first
    or last frames from being mistaken for a black outer border.
    """
    height, width = gray.shape
    y_background = (gray <= black_thresh) | (gray >= white_thresh)
    x_background = gray >= white_thresh

    row_is_border = y_background.mean(axis=1) >= border_ratio
    col_is_border = x_background.mean(axis=0) >= border_ratio

    min_run_y = max(2, min(80, int(round(height * min_run_frac))))
    min_run_x = max(2, min(80, int(round(width * min_run_frac))))

    top = first_content_index(row_is_border, min_run_y)
    bottom = height - first_content_index(row_is_border[::-1], min_run_y)
    left = first_content_index(col_is_border, min_run_x)
    right = width - first_content_index(col_is_border[::-1], min_run_x)

    box = Box(left - keep_margin, top - keep_margin, right + keep_margin, bottom + keep_margin).clamp(width, height)
    return box if box.valid() else Box(0, 0, width, height)


# -----------------------------------------------------------------------------
# Optional pre-detection deskew
# -----------------------------------------------------------------------------

def rough_outer_for_deskew(gray: np.ndarray, config: SplitConfig) -> Box:
    """A lightweight outer estimate used only for measuring strip skew.

    It intentionally does not run the full v8 gap pipeline. The final detection
    still happens after optional deskew, using the normal outer/gap logic.
    """
    height, width = gray.shape
    if config.no_outer_crop:
        return Box(0, 0, width, height)

    bw = detect_outer_box(
        gray=gray,
        black_thresh=config.black_thresh,
        white_thresh=config.white_thresh,
        border_ratio=config.border_ratio,
        min_run_frac=config.border_min_run_frac,
        keep_margin=config.outer_keep_margin,
    )
    white = detect_outer_box_white_x(
        gray=gray,
        black_thresh=config.black_thresh,
        white_thresh=config.white_thresh,
        border_ratio=config.border_ratio,
        min_run_frac=config.border_min_run_frac,
        keep_margin=config.outer_keep_margin,
    )

    if config.outer_x_detect == "bw":
        return bw
    if config.outer_x_detect == "white":
        return white

    # For measuring skew, a wider horizontal span is usually better. Avoid absurd
    # expansion caused by a white-only candidate that covers the whole scanner bed.
    if bw.valid() and white.valid():
        max_reasonable = max(float(bw.width) * float(config.outer_x_auto_max_expand_ratio), float(bw.width) + width * 0.06)
        if white.width >= bw.width and white.width <= max_reasonable:
            return white
    return bw if bw.valid() else Box(0, 0, width, height)


def horizontal_edge_strength(block: np.ndarray) -> np.ndarray:
    """Return row-to-row transition strength for an x-window block."""
    if block.shape[0] < 2 or block.shape[1] < 1:
        return np.zeros(0, dtype=np.float32)
    block_f = block.astype(np.float32, copy=False)
    mean_diff = np.abs(np.diff(block_f.mean(axis=1))).astype(np.float32)
    diff = np.abs(np.diff(block.astype(np.int16, copy=False), axis=0)).astype(np.float32)
    if diff.size:
        p75 = np.percentile(diff, 75, axis=1).astype(np.float32)
    else:
        p75 = np.zeros_like(mean_diff, dtype=np.float32)
    return 0.55 * mean_diff + 0.45 * p75


def find_horizontal_edge_y(
    gray: np.ndarray,
    x_center: float,
    x_half_width: int,
    y0: int,
    y1: int,
    min_strength: float,
) -> Optional[tuple[float, float]]:
    """Find the strongest horizontal edge near x_center inside y0:y1."""
    height, width = gray.shape
    xl = max(0, int(round(x_center)) - int(x_half_width))
    xr = min(width, int(round(x_center)) + int(x_half_width) + 1)
    y0 = max(0, min(int(y0), height))
    y1 = max(y0, min(int(y1), height))
    if xr - xl < 2 or y1 - y0 < 3:
        return None
    block = gray[y0:y1, xl:xr]
    strength = horizontal_edge_strength(block)
    if strength.size == 0:
        return None
    peak_index = int(np.argmax(strength))
    peak_strength = float(strength[peak_index])
    if peak_strength < float(min_strength):
        return None
    return float(y0 + peak_index + 1), peak_strength


def weighted_xy_line_fit(points: list[tuple[float, float, float]]) -> Optional[tuple[float, float]]:
    """Fit y = slope * x + intercept with weights."""
    if len(points) < 2:
        return None
    x = np.array([p[0] for p in points], dtype=np.float64)
    y = np.array([p[1] for p in points], dtype=np.float64)
    w = np.array([max(1e-3, p[2]) for p in points], dtype=np.float64)
    sw = np.sqrt(w)
    design = np.stack([x, np.ones_like(x)], axis=1) * sw[:, None]
    target = y * sw
    try:
        slope, intercept = np.linalg.lstsq(design, target, rcond=None)[0]
    except Exception:
        return None
    if not np.isfinite(slope) or not np.isfinite(intercept):
        return None
    return float(slope), float(intercept)


def robust_horizontal_line_fit(
    points: list[tuple[float, float, float]],
    tolerance_px: float,
    min_inliers: int,
) -> Optional[tuple[float, float, int, float]]:
    """Robustly fit a film-edge line y = slope*x + intercept."""
    if len(points) < max(2, int(min_inliers)):
        return None
    fit = weighted_xy_line_fit(points)
    if fit is None:
        return None
    slope, intercept = fit
    residuals = np.array([abs(y - (slope * x + intercept)) for x, y, _ in points], dtype=np.float64)
    median = float(np.median(residuals)) if residuals.size else 0.0
    mad = float(np.median(np.abs(residuals - median))) if residuals.size else 0.0
    threshold = max(float(tolerance_px), median + 3.0 * 1.4826 * mad)
    threshold = min(max(threshold, float(tolerance_px)), max(float(tolerance_px) * 3.0, 18.0))
    inliers = [p for p, r in zip(points, residuals) if float(r) <= threshold]
    if len(inliers) < max(2, int(min_inliers)):
        return None
    refined = weighted_xy_line_fit(inliers)
    if refined is None:
        return None
    slope, intercept = refined
    refined_residuals = np.array([abs(y - (slope * x + intercept)) for x, y, _ in inliers], dtype=np.float64)
    median_residual = float(np.median(refined_residuals)) if refined_residuals.size else 0.0
    return float(slope), float(intercept), len(inliers), median_residual


def rotated_output_geometry(width: int, height: int, angle_degrees: float) -> tuple[int, int, float, float, float, float, float, float]:
    """Return output size and rotation geometry for an expanded canvas.

    The forward transform is:
        x' = cos*a*x - sin*a*y
        y' = sin*a*x + cos*a*y
    using image coordinates (x right, y down), around the input center.
    """
    theta = math.radians(float(angle_degrees))
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    cx = (float(width) - 1.0) / 2.0
    cy = (float(height) - 1.0) / 2.0
    corners = np.array(
        [
            [0.0 - cx, 0.0 - cy],
            [float(width - 1) - cx, 0.0 - cy],
            [0.0 - cx, float(height - 1) - cy],
            [float(width - 1) - cx, float(height - 1) - cy],
        ],
        dtype=np.float64,
    )
    x_rot = cos_t * corners[:, 0] - sin_t * corners[:, 1]
    y_rot = sin_t * corners[:, 0] + cos_t * corners[:, 1]
    min_x = float(np.floor(x_rot.min()))
    max_x = float(np.ceil(x_rot.max()))
    min_y = float(np.floor(y_rot.min()))
    max_y = float(np.ceil(y_rot.max()))
    out_w = int(max(1, round(max_x - min_x + 1)))
    out_h = int(max(1, round(max_y - min_y + 1)))
    return out_w, out_h, min_x, min_y, cx, cy, cos_t, sin_t


def line_y(slope: float, intercept: float, x: float) -> float:
    return float(slope) * float(x) + float(intercept)


def estimate_deskew_model(gray: np.ndarray, outer: Box, config: SplitConfig) -> tuple[Optional[DeskewModel], list[str]]:
    """Estimate a pre-rotation deskew angle from the top/bottom film edges."""
    warnings: list[str] = []
    if config.deskew == "off" or outer.width <= 1 or outer.height <= 1:
        return None, warnings

    height, width = gray.shape
    sample_count = max(6, int(config.deskew_samples))
    sample_count = min(sample_count, max(6, outer.width // 20)) if outer.width >= 120 else sample_count
    xs = np.linspace(outer.left + outer.width * 0.04, outer.right - outer.width * 0.04, sample_count)
    x_half = max(4, int(round(outer.width * float(config.deskew_sample_window_ratio))))

    vertical_margin = max(8, int(round(outer.height * float(config.deskew_search_margin_ratio))))
    inner_search = max(vertical_margin, int(round(outer.height * 0.20)))
    top_y0 = max(0, outer.top - vertical_margin)
    top_y1 = min(height, outer.top + inner_search)
    bottom_y0 = max(0, outer.bottom - inner_search)
    bottom_y1 = min(height, outer.bottom + vertical_margin)

    top_points: list[tuple[float, float, float]] = []
    bottom_points: list[tuple[float, float, float]] = []
    for x in xs:
        top = find_horizontal_edge_y(gray, float(x), x_half, top_y0, top_y1, config.deskew_edge_min_strength)
        if top is not None:
            y, strength = top
            top_points.append((float(x), float(y), max(0.25, float(strength))))
        bottom = find_horizontal_edge_y(gray, float(x), x_half, bottom_y0, bottom_y1, config.deskew_edge_min_strength)
        if bottom is not None:
            y, strength = bottom
            bottom_points.append((float(x), float(y), max(0.25, float(strength))))

    min_inliers = max(4, int(round(sample_count * (0.48 if config.deskew == "auto" else 0.35))))
    top_fit = robust_horizontal_line_fit(top_points, config.deskew_line_tolerance_px, min_inliers)
    bottom_fit = robust_horizontal_line_fit(bottom_points, config.deskew_line_tolerance_px, min_inliers)
    if top_fit is None or bottom_fit is None:
        if config.deskew == "strict":
            warnings.append(
                f"deskew 跳过：无法可靠拟合上下胶片边缘；top_points={len(top_points)}, bottom_points={len(bottom_points)}, min_inliers={min_inliers}。"
            )
        return None, warnings

    top_slope, top_intercept, top_inliers, top_median_residual = top_fit
    bottom_slope, bottom_intercept, bottom_inliers, bottom_median_residual = bottom_fit
    x0 = float(outer.left)
    x1 = float(outer.right)
    top_span = abs(line_y(top_slope, top_intercept, x1) - line_y(top_slope, top_intercept, x0))
    bottom_span = abs(line_y(bottom_slope, bottom_intercept, x1) - line_y(bottom_slope, bottom_intercept, x0))
    max_span = max(float(top_span), float(bottom_span))
    if max_span < float(config.deskew_min_span_px):
        if config.deskew == "strict":
            warnings.append(f"deskew 跳过：检测到的最大倾斜跨度 {max_span:.1f}px 小于阈值 {config.deskew_min_span_px}px。")
        return None, warnings

    slope_delta = abs(float(top_slope) - float(bottom_slope))
    max_delta = float(config.deskew_max_slope_delta) * (2.0 if config.deskew == "strict" else 1.0)
    if slope_delta > max_delta:
        warnings.append(
            f"deskew 跳过：上下边缘斜率差异过大 top={top_slope:.6f}, bottom={bottom_slope:.6f}, delta={slope_delta:.6f}。"
        )
        return None, warnings

    # If the two edge slopes point in opposite directions, this is more likely a
    # perspective/border detection issue than a simple rotation. Strict mode allows
    # it only when both slopes are tiny.
    if top_slope * bottom_slope < 0 and max(abs(top_slope), abs(bottom_slope)) > (0.0015 if config.deskew == "strict" else 0.0008):
        warnings.append(f"deskew 跳过：上下边缘斜率方向不一致 top={top_slope:.6f}, bottom={bottom_slope:.6f}。")
        return None, warnings

    top_weight = max(1.0, float(top_inliers)) / (1.0 + float(top_median_residual))
    bottom_weight = max(1.0, float(bottom_inliers)) / (1.0 + float(bottom_median_residual))
    slope = (float(top_slope) * top_weight + float(bottom_slope) * bottom_weight) / (top_weight + bottom_weight)

    # Forward rotation by +angle in our image-coordinate convention adds roughly
    # +tan(angle) to a horizontal line slope. Therefore deskew uses -atan(slope).
    angle_degrees = -math.degrees(math.atan(float(slope)))
    abs_angle = abs(float(angle_degrees))
    if abs_angle < float(config.deskew_min_angle_deg):
        if config.deskew == "strict":
            warnings.append(f"deskew 跳过：角度 {angle_degrees:.4f}° 小于阈值 {config.deskew_min_angle_deg}°。")
        return None, warnings
    if abs_angle > float(config.deskew_max_angle_deg):
        warnings.append(f"deskew 跳过：角度 {angle_degrees:.4f}° 超过安全上限 {config.deskew_max_angle_deg}°。")
        return None, warnings

    out_w, out_h, *_ = rotated_output_geometry(width, height, angle_degrees)
    model = DeskewModel(
        mode=str(config.deskew),
        angle_degrees=float(angle_degrees),
        slope=float(slope),
        top_slope=float(top_slope),
        bottom_slope=float(bottom_slope),
        top_span=float(top_span),
        bottom_span=float(bottom_span),
        top_inliers=int(top_inliers),
        bottom_inliers=int(bottom_inliers),
        top_median_residual=float(top_median_residual),
        bottom_median_residual=float(bottom_median_residual),
        input_width=int(width),
        input_height=int(height),
        output_width=int(out_w),
        output_height=int(out_h),
        interpolation=str(config.deskew_interpolation),
    )
    return model, warnings


def estimate_fill_values_yxs(view: np.ndarray, patch: int = 96) -> np.ndarray | float:
    """Estimate background fill values from image corners for rotation canvas."""
    height, width = view.shape[:2]
    patch_h = max(1, min(int(patch), height))
    patch_w = max(1, min(int(patch), width))
    corners = [
        view[0:patch_h, 0:patch_w],
        view[0:patch_h, width - patch_w:width],
        view[height - patch_h:height, 0:patch_w],
        view[height - patch_h:height, width - patch_w:width],
    ]
    if view.ndim == 2:
        values = np.concatenate([c.reshape(-1) for c in corners], axis=0)
        return float(np.median(values.astype(np.float64))) if values.size else 0.0
    sample_count = view.shape[2]
    values = np.concatenate([c.reshape(-1, sample_count) for c in corners], axis=0)
    if values.size == 0:
        return np.zeros((sample_count,), dtype=np.float64)
    return np.median(values.astype(np.float64), axis=0)


def cast_interpolated_values(values: np.ndarray, dtype: np.dtype) -> np.ndarray:
    dtype = np.dtype(dtype)
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        return np.clip(np.rint(values), info.min, info.max).astype(dtype)
    if np.issubdtype(dtype, np.floating):
        return values.astype(dtype)
    return values.astype(dtype)


def filled_chunk(shape: tuple[int, ...], dtype: np.dtype, fill_values: np.ndarray | float) -> np.ndarray:
    out = np.empty(shape, dtype=dtype)
    if len(shape) == 2:
        out[...] = np.array(fill_values, dtype=dtype).item()
    else:
        fill = np.asarray(fill_values, dtype=dtype)
        if fill.ndim == 0:
            out[...] = fill.item()
        else:
            out[...] = fill.reshape((1, 1, -1))
    return out


def rotate_yxs_or_yx_expand(
    view: np.ndarray,
    angle_degrees: float,
    interpolation: str,
    fill_values: np.ndarray | float,
    chunk_rows: int,
) -> np.ndarray:
    """Rotate a YX or YXS view onto an expanded canvas while preserving dtype."""
    if view.ndim not in (2, 3):
        raise RuntimeError(f"deskew 只支持 YX 或 YXS 检测视图，收到 shape={view.shape}")
    height, width = view.shape[:2]
    out_w, out_h, min_x, min_y, cx, cy, cos_t, sin_t = rotated_output_geometry(width, height, angle_degrees)
    dtype = np.dtype(view.dtype)
    interpolation = str(interpolation)
    if interpolation not in {"nearest", "bilinear"}:
        raise ValueError(f"未知 deskew interpolation：{interpolation}")

    out_shape = (out_h, out_w) if view.ndim == 2 else (out_h, out_w, view.shape[2])
    out = filled_chunk(out_shape, dtype, fill_values)
    x_grid = np.arange(out_w, dtype=np.float64)[None, :]
    rows_per_chunk = max(8, int(chunk_rows))

    for row0 in range(0, out_h, rows_per_chunk):
        row1 = min(out_h, row0 + rows_per_chunk)
        y_grid = np.arange(row0, row1, dtype=np.float64)[:, None]
        xf = x_grid + min_x
        yf = y_grid + min_y
        xin = cos_t * xf + sin_t * yf + cx
        yin = -sin_t * xf + cos_t * yf + cy

        if interpolation == "nearest":
            xi = np.rint(xin).astype(np.int64)
            yi = np.rint(yin).astype(np.int64)
            valid = (xi >= 0) & (xi < width) & (yi >= 0) & (yi < height)
            if not valid.any():
                continue
            if view.ndim == 2:
                chunk = out[row0:row1, :]
                chunk[valid] = view[yi[valid], xi[valid]]
            else:
                chunk = out[row0:row1, :, :]
                chunk[valid, :] = view[yi[valid], xi[valid], :]
            continue

        valid = (xin >= 0.0) & (xin <= float(width - 1)) & (yin >= 0.0) & (yin <= float(height - 1))
        if not valid.any():
            continue
        x0 = np.floor(np.clip(xin, 0, width - 1)).astype(np.int64)
        y0 = np.floor(np.clip(yin, 0, height - 1)).astype(np.int64)
        x1 = np.minimum(x0 + 1, width - 1)
        y1 = np.minimum(y0 + 1, height - 1)
        dx = (xin - x0).astype(np.float64)
        dy = (yin - y0).astype(np.float64)
        w00 = (1.0 - dx) * (1.0 - dy)
        w10 = dx * (1.0 - dy)
        w01 = (1.0 - dx) * dy
        w11 = dx * dy

        if view.ndim == 2:
            values = (
                view[y0, x0].astype(np.float64) * w00
                + view[y0, x1].astype(np.float64) * w10
                + view[y1, x0].astype(np.float64) * w01
                + view[y1, x1].astype(np.float64) * w11
            )
            chunk = out[row0:row1, :]
            chunk[valid] = cast_interpolated_values(values[valid], dtype)
        else:
            chunk = out[row0:row1, :, :]
            for sample in range(view.shape[2]):
                values = (
                    view[y0, x0, sample].astype(np.float64) * w00
                    + view[y0, x1, sample].astype(np.float64) * w10
                    + view[y1, x0, sample].astype(np.float64) * w01
                    + view[y1, x1, sample].astype(np.float64) * w11
                )
                chunk[..., sample][valid] = cast_interpolated_values(values[valid], dtype)
    return out


def yxs_or_yx_to_axes(rotated_view: np.ndarray, axes: str) -> np.ndarray:
    """Move a rotated YX/YXS view back to the source TIFF axes order."""
    if axes == "YX":
        return rotated_view
    if "S" in axes:
        return np.moveaxis(rotated_view, [0, 1, 2], [axes.index("Y"), axes.index("X"), axes.index("S")])
    return np.moveaxis(rotated_view, [0, 1], [axes.index("Y"), axes.index("X")])


def rotate_array_yx_same_axes(
    arr: np.ndarray,
    axes: str,
    angle_degrees: float,
    interpolation: str,
    chunk_rows: int,
) -> np.ndarray:
    """Rotate the source array and return an array in the original axes order."""
    view = np.ascontiguousarray(as_yxs_or_yx(arr, axes))
    fill_values = estimate_fill_values_yxs(view)
    rotated_view = rotate_yxs_or_yx_expand(
        view=view,
        angle_degrees=angle_degrees,
        interpolation=interpolation,
        fill_values=fill_values,
        chunk_rows=chunk_rows,
    )
    rotated = yxs_or_yx_to_axes(rotated_view, axes)
    return np.ascontiguousarray(rotated)


def make_equal_gaps(width: int, count: int, method: str) -> list[Gap]:
    frame_w = width / float(count)
    gaps: list[Gap] = []
    for k in range(1, count):
        cut = int(round(k * frame_w))
        gaps.append(Gap(cut, cut, float(cut), 0.0, method))
    return gaps


def build_separator_score(
    gray_outer: np.ndarray,
    black_thresh: int,
    white_thresh: int,
    center_y0_ratio: float,
    center_y1_ratio: float,
    vertical_slices: int,
) -> np.ndarray:
    """
    Score each x column as separator-like.
    A good separator is black/white, narrow, and vertically consistent.
    """
    height, width = gray_outer.shape
    y0 = max(0, min(height - 1, int(round(height * center_y0_ratio))))
    y1 = max(y0 + 1, min(height, int(round(height * center_y1_ratio))))
    middle = gray_outer[y0:y1, :]
    middle_float = middle.astype(np.float32)

    slices = max(1, int(vertical_slices))
    profiles: list[np.ndarray] = []
    for index in range(slices):
        sy0 = int(round(index * middle.shape[0] / slices))
        sy1 = int(round((index + 1) * middle.shape[0] / slices))
        if sy1 <= sy0:
            continue
        part = middle[sy0:sy1, :]
        black_ratio = (part <= black_thresh).mean(axis=0).astype(np.float32)
        white_ratio = (part >= white_thresh).mean(axis=0).astype(np.float32)
        profiles.append(np.maximum(black_ratio, white_ratio))

    if not profiles:
        profiles.append(((middle <= black_thresh) | (middle >= white_thresh)).mean(axis=0).astype(np.float32))

    stack = np.stack(profiles, axis=0)
    average_extreme = stack.mean(axis=0).astype(np.float32)
    vertical_consistency = np.percentile(stack, 20, axis=0).astype(np.float32)
    extreme_score = 0.35 * average_extreme + 0.65 * vertical_consistency

    # Uniformity is auxiliary only. It must not let a dark wall/night scene win by itself.
    col_std = middle_float.std(axis=0)
    uniform_score = 1.0 - np.clip(col_std / 70.0, 0.0, 1.0)
    col_mean = middle_float.mean(axis=0)
    dark_soft = np.clip((black_thresh * 1.8 - col_mean) / max(1.0, black_thresh * 1.8), 0.0, 1.0)
    light_soft = np.clip((col_mean - white_thresh) / max(1.0, 255.0 - white_thresh), 0.0, 1.0)
    soft_score = np.maximum(dark_soft, light_soft) * uniform_score * 0.50

    score = np.maximum(extreme_score * (0.90 + 0.10 * uniform_score), soft_score)
    return moving_average(score, max(3, int(round(width * 0.0015))))


def detect_gaps_near_expected_positions(
    gray_outer: np.ndarray,
    count: int,
    black_thresh: int,
    white_thresh: int,
    search_ratio: float,
    min_score: float,
    max_gap_ratio: float,
    min_gap_ratio: float,
    side_guard_ratio: float,
    center_y0_ratio: float,
    center_y1_ratio: float,
    min_prominence: float,
    vertical_slices: int,
    allow_peak_fallback: bool,
) -> list[Gap]:
    """
    Find one separator per theoretical boundary. If a local peak looks like a broad
    underexposed region, fall back to the theoretical equal-split position.
    """
    height, width = gray_outer.shape
    if count <= 1:
        return []

    score = build_separator_score(
        gray_outer=gray_outer,
        black_thresh=black_thresh,
        white_thresh=white_thresh,
        center_y0_ratio=center_y0_ratio,
        center_y1_ratio=center_y1_ratio,
        vertical_slices=vertical_slices,
    )

    frame_w = width / float(count)
    max_gap_w = max(2, int(round(frame_w * max_gap_ratio)))
    min_gap_w = max(1, int(round(frame_w * min_gap_ratio)))
    guard_w = max(3, int(round(frame_w * side_guard_ratio)))

    gaps: list[Gap] = []
    for k in range(1, count):
        expected = k * frame_w
        expected_cut = int(round(expected))
        lo = max(1, int(round(expected - frame_w * search_ratio)))
        hi = min(width - 1, int(round(expected + frame_w * search_ratio)))
        if hi <= lo:
            gaps.append(Gap(expected_cut, expected_cut, float(expected_cut), 0.0, "equal-empty-window"))
            continue

        local = score[lo:hi]
        local_max = float(local.max()) if local.size else 0.0
        if local.size == 0 or local_max < min_score:
            gaps.append(Gap(expected_cut, expected_cut, float(expected_cut), local_max, "equal-low-score"))
            continue

        peak_threshold = max(float(min_score), local_max * 0.90)
        broad_region_threshold = max(float(min_score) * 0.72, local_max * 0.48)
        band_expand_threshold = max(float(min_score) * 0.86, local_max * 0.62)

        candidates: list[tuple[float, float, float, int, int, float]] = []
        rejected_broad_or_weak = False

        for run_start, run_end in runs_from_mask(local >= peak_threshold):
            # Expand to a lower threshold to judge whether this is actually a broad dark/bright region.
            region_start, region_end = run_start, run_end
            while region_start > 0 and local[region_start - 1] >= broad_region_threshold:
                region_start -= 1
            while region_end < len(local) and local[region_end] >= broad_region_threshold:
                region_end += 1

            region_width = region_end - region_start
            touches_window_edge = region_start == 0 or region_end == len(local)
            if region_width > max_gap_w * 1.5:
                rejected_broad_or_weak = True
                continue
            if touches_window_edge and region_width > max_gap_w * 0.9:
                rejected_broad_or_weak = True
                continue

            # Estimate a tighter separator band. Default crop mode only uses center,
            # but width still matters for rejecting dark scene content.
            band_start, band_end = run_start, run_end
            while band_start > 0 and local[band_start - 1] >= band_expand_threshold and (band_end - (band_start - 1)) <= max_gap_w:
                band_start -= 1
            while band_end < len(local) and local[band_end] >= band_expand_threshold and ((band_end + 1) - band_start) <= max_gap_w:
                band_end += 1

            band_width = band_end - band_start
            if band_width < min_gap_w or band_width > max_gap_w:
                rejected_broad_or_weak = True
                continue

            left_guard = local[max(0, band_start - guard_w):band_start]
            right_guard = local[band_end:min(len(local), band_end + guard_w)]
            if left_guard.size == 0 or right_guard.size == 0:
                rejected_broad_or_weak = True
                continue

            mean_score = float(local[band_start:band_end].mean())
            side_score = max(float(left_guard.mean()), float(right_guard.mean()))
            prominence = mean_score - side_score
            if prominence < min_prominence and mean_score < 0.95:
                rejected_broad_or_weak = True
                continue

            center = lo + (band_start + band_end - 1) / 2.0
            distance = abs(center - expected) / max(1.0, frame_w)
            quality = mean_score + 0.8 * prominence
            candidates.append((distance, -quality, -mean_score, lo + band_start, lo + band_end, center))

        if candidates:
            distance, neg_quality, neg_mean_score, start, end, center = sorted(candidates)[0]
            gaps.append(Gap(int(start), int(end), float(center), float(-neg_mean_score), "detected"))
        elif allow_peak_fallback:
            cut = lo + int(local.argmax())
            gaps.append(Gap(cut, cut, float(cut), local_max, "peak-fallback"))
        else:
            method = "equal-suspect-broad-region" if rejected_broad_or_weak else "equal-no-candidate"
            gaps.append(Gap(expected_cut, expected_cut, float(expected_cut), local_max, method))

    return gaps



def sample_middle_rows(gray_outer: np.ndarray, center_y0_ratio: float, center_y1_ratio: float, max_rows: int = 1200) -> np.ndarray:
    """Return central rows for detection; downsample vertically to control memory use."""
    height, _ = gray_outer.shape
    y0 = max(0, min(height - 1, int(round(height * center_y0_ratio))))
    y1 = max(y0 + 1, min(height, int(round(height * center_y1_ratio))))
    middle = gray_outer[y0:y1, :]
    if middle.shape[0] > max_rows:
        step = int(math.ceil(middle.shape[0] / max_rows))
        middle = middle[::step, :]
    return middle


def normalize_profile(profile: np.ndarray, high_percentile: float = 99.0) -> np.ndarray:
    profile = profile.astype(np.float32, copy=False)
    if profile.size == 0:
        return profile
    hi = float(np.percentile(profile, high_percentile))
    if hi <= 1e-6:
        return np.zeros_like(profile, dtype=np.float32)
    return np.clip(profile / hi, 0.0, 1.0).astype(np.float32)


def build_edge_refine_profiles(
    gray_outer: np.ndarray,
    black_thresh: int,
    white_thresh: int,
    center_y0_ratio: float,
    center_y1_ratio: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Build profiles used only by optional edge refinement:
    - edge: vertical transition strength, normalized to 0..1
    - background: ratio of black/white extreme pixels per column
    - activity: texture/variation score per column, normalized to 0..1
    """
    height, width = gray_outer.shape
    middle = sample_middle_rows(gray_outer, center_y0_ratio, center_y1_ratio)
    if middle.size == 0 or width <= 1:
        zeros = np.zeros(width, dtype=np.float32)
        return zeros, zeros, zeros

    middle_i16 = middle.astype(np.int16, copy=False)

    # Transition between x-1 and x. Use both mean and high percentile so that
    # an edge that spans most of the frame height is preferred, but partial edges
    # can still contribute.
    diff_x = np.abs(np.diff(middle_i16, axis=1)).astype(np.float32)
    if diff_x.shape[1] == 0:
        edge = np.zeros(width, dtype=np.float32)
    else:
        edge_raw = 0.65 * diff_x.mean(axis=0) + 0.35 * np.percentile(diff_x, 75, axis=0)
        edge = np.zeros(width, dtype=np.float32)
        edge[1:] = edge_raw
        smooth_window = max(3, int(round(width * 0.0008)))
        edge = normalize_profile(moving_average(edge, smooth_window), 99.2)

    background = ((middle <= black_thresh) | (middle >= white_thresh)).mean(axis=0).astype(np.float32)

    col_std = middle.astype(np.float32, copy=False).std(axis=0)
    if middle.shape[0] > 1:
        diff_y = np.abs(np.diff(middle_i16, axis=0)).astype(np.float32)
        y_edge = diff_y.mean(axis=0)
    else:
        y_edge = np.zeros(width, dtype=np.float32)
    activity = normalize_profile(col_std + 0.5 * y_edge, 95.0)
    return edge, background, activity


def local_peaks(profile: np.ndarray, lo: int, hi: int, min_strength: float) -> list[int]:
    """Find peak columns in profile[lo:hi], merging adjacent above-threshold columns."""
    width = len(profile)
    lo = max(0, min(int(lo), width))
    hi = max(lo, min(int(hi), width))
    if hi <= lo:
        return []
    local = profile[lo:hi]
    if local.size == 0:
        return []
    # Combine an absolute normalized threshold with local percentile. This keeps
    # the refinement conservative on noisy scenes.
    threshold = max(float(min_strength), float(np.percentile(local, 82)))
    runs = runs_from_mask(local >= threshold)
    peaks: list[int] = []
    for start, end in runs:
        if end <= start:
            continue
        peak_local = start + int(np.argmax(local[start:end]))
        peak = lo + peak_local
        if profile[peak] >= min_strength:
            peaks.append(int(peak))
    # De-duplicate near-equal peaks created by anti-aliasing / smoothing.
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


def content_signal(bg_mean: float, activity_mean: float) -> float:
    """Higher means more likely to be a photographed frame rather than blank film/leader."""
    return float((1.0 - bg_mean) * 0.65 + activity_mean * 0.35)


def classify_single_edge_direction(
    edge_x: int,
    background: np.ndarray,
    activity: np.ndarray,
    half_gutter: float,
    min_bg_ratio: float,
) -> Optional[str]:
    """
    Decide whether a single edge is photo->blank or blank->photo.
    Returns 'right' if cut should move to edge + half_gutter,
    'left' if cut should move to edge - half_gutter, else None.
    """
    span = max(4, int(round(half_gutter * 2.0)))
    left_bg = interval_mean(background, edge_x - span, edge_x)
    right_bg = interval_mean(background, edge_x + 1, edge_x + 1 + span)
    left_act = interval_mean(activity, edge_x - span, edge_x)
    right_act = interval_mean(activity, edge_x + 1, edge_x + 1 + span)

    left_content = content_signal(left_bg, left_act)
    right_content = content_signal(right_bg, right_act)

    left_blank = left_bg >= min_bg_ratio and left_act < 0.45
    right_blank = right_bg >= min_bg_ratio and right_act < 0.45

    # Skip black leader -> white leader edges: both sides are blank/background.
    if left_blank and right_blank:
        return None

    # Photo on left, blank on right: separator center should be to the right.
    if right_blank and left_content > right_content + 0.16:
        return "right"
    # Blank on left, photo on right: separator center should be to the left.
    if left_blank and right_content > left_content + 0.16:
        return "left"
    return None


def refine_gaps_by_vertical_edges(
    gray_outer: np.ndarray,
    gaps: list[Gap],
    count: int,
    black_thresh: int,
    white_thresh: int,
    center_y0_ratio: float,
    center_y1_ratio: float,
    edge_search_ratio: float,
    edge_min_strength: float,
    edge_min_bg_ratio: float,
    edge_max_gutter_ratio: float,
    edge_min_gutter_px: int,
    single_mode: str,
) -> list[Gap]:
    """
    Optional conservative post-processing for rare strips with blank frames/leader.

    The conservative separator logic is kept as the base. This function only moves a cut when
    there is strong evidence of a real photographed-frame edge pair enclosing a
    black/white gutter. If evidence is weak, the original gap is returned.
    """
    height, width = gray_outer.shape
    if count <= 1 or width <= 1 or not gaps:
        return gaps

    edge, background, activity = build_edge_refine_profiles(
        gray_outer=gray_outer,
        black_thresh=black_thresh,
        white_thresh=white_thresh,
        center_y0_ratio=center_y0_ratio,
        center_y1_ratio=center_y1_ratio,
    )

    frame_w = width / float(count)
    window = max(8, int(round(frame_w * edge_search_ratio)))
    max_gutter = max(int(edge_min_gutter_px) + 1, int(round(frame_w * edge_max_gutter_ratio)))
    min_gutter = max(2, int(edge_min_gutter_px))

    refined: list[Gap] = []
    learned_gutters: list[int] = []

    for gap in gaps:
        x0 = int(round(gap.center))
        lo = max(1, x0 - window)
        hi = min(width - 1, x0 + window)
        peaks = local_peaks(edge, lo, hi, edge_min_strength)

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
                if bg_between < edge_min_bg_ratio:
                    continue
                strength = (float(edge[a]) + float(edge[b])) / 2.0
                # Prefer a pair near the existing cut, with a background-like interval.
                distance = abs(center - x0) / max(1.0, frame_w)
                quality = strength + 0.6 * bg_between
                candidates.append((distance, -quality, -bg_between, int(a), int(b)))

        if candidates:
            _, neg_quality, neg_bg, a, b = sorted(candidates)[0]
            center = (a + b) / 2.0
            refined.append(Gap(a, b + 1, center, float(-neg_quality), "edge-pair"))
            learned_gutters.append(b - a)
        else:
            refined.append(gap)

    if single_mode == "learned" and learned_gutters:
        median_gutter = float(np.median(learned_gutters))
        half_gutter = median_gutter / 2.0
        second_pass: list[Gap] = []
        for original, current in zip(gaps, refined):
            if current.method == "edge-pair":
                second_pass.append(current)
                continue

            x0 = int(round(original.center))
            lo = max(1, x0 - window)
            hi = min(width - 1, x0 + window)
            peaks = local_peaks(edge, lo, hi, edge_min_strength)
            if not peaks:
                second_pass.append(current)
                continue

            best: Optional[tuple[float, int, str]] = None
            for peak in peaks:
                direction = classify_single_edge_direction(
                    edge_x=peak,
                    background=background,
                    activity=activity,
                    half_gutter=half_gutter,
                    min_bg_ratio=edge_min_bg_ratio,
                )
                if direction is None:
                    continue
                cut = float(peak + half_gutter if direction == "right" else peak - half_gutter)
                if cut < 1 or cut > width - 1:
                    continue
                if abs(cut - x0) > window:
                    continue
                # Do not let a single edge outrank the existing reliable separator detection.
                if original.method == "detected" and abs(cut - original.center) > max(4.0, half_gutter):
                    continue
                score = float(edge[peak]) - abs(cut - x0) / max(1.0, frame_w)
                candidate = (score, int(round(cut)), direction)
                if best is None or candidate > best:
                    best = candidate

            if best is None:
                second_pass.append(current)
            else:
                _, cut, _ = best
                second_pass.append(Gap(cut, cut, float(cut), float(edge[min(max(cut, 0), width - 1)]), "edge-single-learned"))
        refined = second_pass

    return refined


# -----------------------------------------------------------------------------
# Robust global grid fitting
# -----------------------------------------------------------------------------

def gap_is_reliable_for_grid(gap: Gap, min_score: float) -> bool:
    """
    Return True if a gap can be used as evidence for the global frame pitch.

    Equal-split fallbacks are not evidence. They may later be replaced by a
    grid inferred from stronger neighboring separators.
    """
    if gap.method in {"detected", "edge-pair"}:
        return gap.score >= min_score * 0.70
    if gap.method == "edge-single-learned":
        return gap.score >= 0.30
    return False


def weighted_line_fit(points: list[tuple[int, float, float]]) -> Optional[tuple[float, float]]:
    """Fit x = start + k * pitch using weighted least squares."""
    if len(points) < 2:
        return None
    k = np.array([p[0] for p in points], dtype=np.float64)
    x = np.array([p[1] for p in points], dtype=np.float64)
    w = np.array([max(1e-3, p[2]) for p in points], dtype=np.float64)
    sw = np.sqrt(w)
    design = np.stack([np.ones_like(k), k], axis=1) * sw[:, None]
    target = x * sw
    try:
        start, pitch = np.linalg.lstsq(design, target, rcond=None)[0]
    except Exception:
        return None
    if not np.isfinite(start) or not np.isfinite(pitch) or pitch <= 0:
        return None
    return float(start), float(pitch)


def evaluate_grid_model(
    start: float,
    pitch: float,
    points: list[tuple[int, float, float]],
    nominal_pitch: float,
    tolerance_ratio: float,
) -> tuple[tuple[int, ...], float, float, float]:
    """Return inlier k indices, inlier weight, median residual, max residual."""
    tolerance = max(4.0, float(pitch) * float(tolerance_ratio))
    residuals: list[float] = []
    inliers: list[int] = []
    weight = 0.0
    for k, center, point_weight in points:
        residual = abs(float(center) - (float(start) + int(k) * float(pitch)))
        if residual <= tolerance:
            inliers.append(int(k))
            residuals.append(float(residual))
            weight += float(point_weight)
    if residuals:
        median_residual = float(np.median(np.array(residuals, dtype=np.float64)))
        max_residual = float(np.max(np.array(residuals, dtype=np.float64)))
    else:
        median_residual = float("inf")
        max_residual = float("inf")
    return tuple(inliers), weight, median_residual, max_residual


def fit_robust_grid_model(
    gaps: list[Gap],
    count: int,
    width: int,
    min_score: float,
    min_inliers: int,
    tolerance_ratio: float,
    pitch_tolerance_ratio: float,
) -> Optional[GridModel]:
    """
    Fit a global 135-frame spacing model from reliable separators.

    This intentionally does NOT restore the old global black-band scan. It only
    uses the separators already accepted by the safer local detector / optional
    edge-refine detector, then rejects separators that are inconsistent with the
    learned film pitch.
    """
    if count <= 1 or width <= 1:
        return None

    nominal_pitch = width / float(count)
    points: list[tuple[int, float, float]] = []
    for k, gap in enumerate(gaps, 1):
        if not gap_is_reliable_for_grid(gap, min_score):
            continue
        # Scores from edge-pair can be >1. Clamp the influence so one very high
        # score cannot dominate the global fit.
        weight = min(2.0, max(0.25, float(gap.score)))
        points.append((k, float(gap.center), weight))

    if len(points) < max(2, int(min_inliers)):
        return None

    min_pitch = nominal_pitch * max(0.20, 1.0 - float(pitch_tolerance_ratio))
    max_pitch = nominal_pitch * (1.0 + float(pitch_tolerance_ratio))
    max_start_abs = nominal_pitch * 0.45

    candidates: list[tuple[int, float, float, float, float, float, tuple[int, ...]]] = []

    # RANSAC-like pair models. One wrong local separator should not pull the grid.
    for i, (ki, xi, _) in enumerate(points):
        for kj, xj, _ in points[i + 1:]:
            dk = int(kj) - int(ki)
            if dk == 0:
                continue
            pitch = (float(xj) - float(xi)) / float(dk)
            if pitch < min_pitch or pitch > max_pitch:
                continue
            start = float(xi) - int(ki) * pitch
            if abs(start) > max_start_abs:
                continue
            inliers, inlier_weight, median_residual, max_residual = evaluate_grid_model(
                start, pitch, points, nominal_pitch, tolerance_ratio
            )
            if len(inliers) < int(min_inliers):
                continue
            # Higher inlier count / weight wins. Then prefer lower residual and
            # a start closer to the outer box left edge.
            candidates.append((
                len(inliers),
                inlier_weight,
                -median_residual,
                -max_residual,
                -abs(start) / max(1.0, nominal_pitch),
                pitch,
                inliers,
            ))

    # Also test a weighted fit over all reliable points; useful when no single
    # point is a large outlier.
    fit = weighted_line_fit(points)
    if fit is not None:
        start, pitch = fit
        if min_pitch <= pitch <= max_pitch and abs(start) <= max_start_abs:
            inliers, inlier_weight, median_residual, max_residual = evaluate_grid_model(
                start, pitch, points, nominal_pitch, tolerance_ratio
            )
            if len(inliers) >= int(min_inliers):
                candidates.append((
                    len(inliers),
                    inlier_weight,
                    -median_residual,
                    -max_residual,
                    -abs(start) / max(1.0, nominal_pitch),
                    pitch,
                    inliers,
                ))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    _, _, _, _, _, _, best_inliers = candidates[0]
    inlier_points = [p for p in points if p[0] in set(best_inliers)]
    refined_fit = weighted_line_fit(inlier_points)
    if refined_fit is None:
        return None
    start, pitch = refined_fit
    if pitch < min_pitch or pitch > max_pitch or abs(start) > max_start_abs:
        return None

    inliers, _, median_residual, max_residual = evaluate_grid_model(
        start, pitch, points, nominal_pitch, tolerance_ratio
    )
    if len(inliers) < int(min_inliers):
        return None

    # Ensure predicted internal boundaries stay inside the outer-cropped strip.
    for k in range(1, count):
        predicted = start + k * pitch
        if predicted <= 1 or predicted >= width - 1:
            return None

    return GridModel(
        start=float(start),
        pitch=float(pitch),
        inlier_indices=tuple(int(k) for k in inliers),
        median_residual=float(median_residual),
        max_residual=float(max_residual),
    )


def apply_robust_grid(
    gaps: list[Gap],
    count: int,
    width: int,
    min_score: float,
    mode: str,
    min_inliers: int,
    tolerance_ratio: float,
    pitch_tolerance_ratio: float,
    min_replace_px: int,
) -> tuple[list[Gap], list[str]]:
    """
    Replace only suspicious separators with a globally consistent frame grid.

    mode:
        off    -> do nothing
        auto   -> replace equal fallbacks and clear outliers
        strict -> also replace weak single-edge refinements when they drift
    """
    warnings: list[str] = []
    if mode == "off" or count <= 1 or len(gaps) != count - 1:
        return gaps, warnings

    model = fit_robust_grid_model(
        gaps=gaps,
        count=count,
        width=width,
        min_score=min_score,
        min_inliers=min_inliers,
        tolerance_ratio=tolerance_ratio,
        pitch_tolerance_ratio=pitch_tolerance_ratio,
    )
    if model is None:
        return gaps, warnings

    replace_threshold = max(float(min_replace_px), float(model.pitch) * float(tolerance_ratio) * 1.15)
    new_gaps: list[Gap] = []
    replaced: list[int] = []
    for k, gap in enumerate(gaps, 1):
        predicted = float(model.start) + int(k) * float(model.pitch)
        residual = abs(float(gap.center) - predicted)
        replace = False

        if gap.method.startswith("equal-"):
            # Equal fallback is not evidence; once a robust grid exists, use it.
            replace = True
        elif gap.method == "peak-fallback":
            replace = True
        elif residual > replace_threshold:
            replace = True
        elif mode == "strict" and gap.method == "edge-single-learned" and residual > replace_threshold * 0.55:
            replace = True

        if replace and 0 < predicted < width:
            cut = int(round(predicted))
            new_gaps.append(Gap(cut, cut, float(predicted), float(gap.score), f"grid-fit-{gap.method}"))
            replaced.append(k)
        else:
            new_gaps.append(gap)

    if replaced:
        warnings.append(
            "全局片距校正已替换第 "
            + ", ".join(str(i) for i in replaced)
            + " 条内部分隔线；这些线与其他可靠分隔线的等距关系不一致，常见原因是画面内强竖边、暗部或模糊高光被误认为分隔线。"
        )
        warnings.append(
            f"全局片距模型：start={model.start:.1f}, pitch={model.pitch:.1f}, "
            f"inliers={list(model.inlier_indices)}, median_residual={model.median_residual:.1f}px。"
        )
    return new_gaps, warnings



# -----------------------------------------------------------------------------
# Outer-box refinement from internal frame grid
# -----------------------------------------------------------------------------

def detect_local_gaps(gray_outer: np.ndarray, config: SplitConfig) -> list[Gap]:
    """Run local separator detection before global grid fitting."""
    if config.equal_split:
        return make_equal_gaps(gray_outer.shape[1], config.count, "equal-forced")

    gaps = detect_gaps_near_expected_positions(
        gray_outer=gray_outer,
        count=config.count,
        black_thresh=config.black_thresh,
        white_thresh=config.white_thresh,
        search_ratio=config.search_ratio,
        min_score=config.min_gap_score,
        max_gap_ratio=config.max_gap_ratio,
        min_gap_ratio=config.min_gap_ratio,
        side_guard_ratio=config.side_guard_ratio,
        center_y0_ratio=config.center_y0,
        center_y1_ratio=config.center_y1,
        min_prominence=config.min_gap_prominence,
        vertical_slices=config.vertical_slices,
        allow_peak_fallback=config.allow_peak_fallback,
    )

    if config.edge_refine:
        gaps = refine_gaps_by_vertical_edges(
            gray_outer=gray_outer,
            gaps=gaps,
            count=config.count,
            black_thresh=config.black_thresh,
            white_thresh=config.white_thresh,
            center_y0_ratio=config.center_y0,
            center_y1_ratio=config.center_y1,
            edge_search_ratio=config.edge_search_ratio,
            edge_min_strength=config.edge_min_strength,
            edge_min_bg_ratio=config.edge_min_bg_ratio,
            edge_max_gutter_ratio=config.edge_max_gutter_ratio,
            edge_min_gutter_px=config.edge_min_gutter_px,
            single_mode=config.edge_refine_single,
        )
    return gaps



def score_outer_candidate(gray: np.ndarray, outer: Box, config: SplitConfig) -> tuple[float, list[Gap], Optional[GridModel]]:
    """Score an outer box candidate using already established separator/grid logic."""
    if not outer.valid() or outer.width <= 1 or outer.height <= 1:
        return -1e9, [], None
    gray_outer = gray[outer.top:outer.bottom, outer.left:outer.right]
    gaps = detect_local_gaps(gray_outer, config)
    reliable = sum(1 for gap in gaps if gap_is_reliable_for_grid(gap, config.min_gap_score))
    detected = sum(1 for gap in gaps if gap.method in {"detected", "edge-pair", "edge-single-learned"})
    equal = sum(1 for gap in gaps if gap.method.startswith("equal-"))
    model = fit_robust_grid_model(
        gaps=gaps,
        count=config.count,
        width=outer.width,
        min_score=config.min_gap_score,
        min_inliers=max(2, min(config.grid_min_inliers, config.count - 1)),
        tolerance_ratio=config.grid_tolerance_ratio,
        pitch_tolerance_ratio=max(config.grid_pitch_tolerance_ratio, config.outer_refine_pitch_tolerance_ratio),
    )
    model_inliers = len(model.inlier_indices) if model is not None else 0
    residual_bonus = 0.0 if model is None else max(0.0, 1.0 - model.median_residual / max(1.0, outer.width / max(1, config.count)))
    score = 5.0 * model_inliers + 2.0 * reliable + 1.0 * detected + residual_bonus - 0.35 * equal
    return float(score), gaps, model


def choose_initial_outer_box(gray: np.ndarray, config: SplitConfig, warnings: list[str]) -> tuple[Box, list[Gap]]:
    """Choose the initial outer crop candidate before final refinements.

    The previous direct black/white outer detector remains available. also tests a white-only-X
    candidate that preserves black underexposed edge frames. The candidates are
    judged with the same separator/grid logic used later in the script.
    """
    height, width = gray.shape
    bw = detect_outer_box(
        gray=gray,
        black_thresh=config.black_thresh,
        white_thresh=config.white_thresh,
        border_ratio=config.border_ratio,
        min_run_frac=config.border_min_run_frac,
        keep_margin=config.outer_keep_margin,
    )
    if config.outer_x_detect == "bw" or config.equal_split:
        score, gaps, _ = score_outer_candidate(gray, bw, config)
        if config.equal_split and config.outer_x_detect == "auto":
            warnings.append("已启用 --equal-split；初始外框左右策略保持 bw，避免在无分隔线证据时扩大到黑色扫描边。")
        return bw, gaps

    white_x = detect_outer_box_white_x(
        gray=gray,
        black_thresh=config.black_thresh,
        white_thresh=config.white_thresh,
        border_ratio=config.border_ratio,
        min_run_frac=config.border_min_run_frac,
        keep_margin=config.outer_keep_margin,
    )
    if config.outer_x_detect == "white":
        score, gaps, _ = score_outer_candidate(gray, white_x, config)
        return white_x, gaps

    bw_score, bw_gaps, _ = score_outer_candidate(gray, bw, config)
    white_score, white_gaps, _ = score_outer_candidate(gray, white_x, config)

    # The white-X candidate is allowed to be wider, but not absurdly wider. This
    # prevents a large black scanner surround from becoming the crop when the
    # normal black/white detector already works.
    max_expand = max(1.0, float(config.outer_x_auto_max_expand_ratio))
    min_gain = float(config.outer_x_auto_min_gain_ratio)
    wider = white_x.width > bw.width * (1.0 + min_gain)
    not_too_wide = white_x.width <= max(1, bw.width) * max_expand
    substantially_better = white_score >= bw_score + 1.5
    tie_but_safer = wider and white_score >= bw_score - 0.25

    if not_too_wide and (substantially_better or tie_but_safer):
        warnings.append(
            f"外框初选已使用 white-x 候选以保护欠曝边缘：bw_width={bw.width}, white_x_width={white_x.width}, "
            f"score={bw_score:.1f}->{white_score:.1f}。"
        )
        return white_x, white_gaps

    return bw, bw_gaps

def propose_outer_x_from_grid(
    outer: Box,
    gaps: list[Gap],
    image_width: int,
    image_height: int,
    config: SplitConfig,
    iteration: int,
) -> tuple[Box, Optional[OuterRefineModel], list[str]]:
    """Infer a better horizontal outer box from reliable internal boundaries."""
    warnings: list[str] = []
    if config.outer_refine == "off" or config.equal_split or config.no_outer_crop:
        return outer, None, warnings
    if config.count <= 1 or outer.width <= 1 or len(gaps) != config.count - 1:
        return outer, None, warnings

    model = fit_robust_grid_model(
        gaps=gaps,
        count=config.count,
        width=outer.width,
        min_score=config.min_gap_score,
        min_inliers=max(2, int(config.outer_refine_min_inliers)),
        tolerance_ratio=config.outer_refine_tolerance_ratio,
        pitch_tolerance_ratio=config.outer_refine_pitch_tolerance_ratio,
    )
    if model is None:
        return outer, None, warnings

    left_float = float(outer.left) + float(model.start)
    right_float = float(outer.left) + float(model.start) + float(config.count) * float(model.pitch)
    proposed_width = right_float - left_float
    if proposed_width <= 1:
        return outer, None, warnings

    width_change_ratio = abs(proposed_width - float(outer.width)) / max(1.0, float(outer.width))
    max_width_change = float(config.outer_refine_max_width_change_ratio)
    if width_change_ratio > max_width_change:
        if config.outer_refine == "strict":
            warnings.append(
                f"outer-refine 跳过：拟合外框宽度变化 {width_change_ratio:.1%} 超过上限 {max_width_change:.1%}。"
            )
        return outer, None, warnings

    max_shift = max(float(config.outer_refine_min_shift_px), float(model.pitch) * float(config.outer_refine_max_shift_ratio))
    left_shift = left_float - float(outer.left)
    right_shift = right_float - float(outer.right)
    if abs(left_shift) > max_shift or abs(right_shift) > max_shift:
        if config.outer_refine == "strict":
            warnings.append(
                f"outer-refine 跳过：左右外框修正量过大 left={left_shift:.1f}px, right={right_shift:.1f}px, 上限={max_shift:.1f}px。"
            )
        return outer, None, warnings

    out_of_bounds = max(0.0, -left_float) + max(0.0, right_float - float(image_width))
    if out_of_bounds > max(2.0, float(config.outer_refine_min_shift_px) * 2.0):
        if config.outer_refine == "strict":
            warnings.append(f"outer-refine 跳过：拟合外框超出源图范围 {out_of_bounds:.1f}px。")
        return outer, None, warnings

    refined = Box(
        left=int(round(left_float)),
        top=outer.top,
        right=int(round(right_float)),
        bottom=outer.bottom,
    ).clamp(image_width, image_height)

    if not refined.valid():
        return outer, None, warnings

    actual_left_shift = float(refined.left - outer.left)
    actual_right_shift = float(refined.right - outer.right)
    if max(abs(actual_left_shift), abs(actual_right_shift)) < float(config.outer_refine_min_shift_px):
        return outer, None, warnings

    if refined.width < outer.width * 0.70 or refined.width > outer.width * 1.30:
        if config.outer_refine == "strict":
            warnings.append(f"outer-refine 跳过：修正后宽度 {refined.width}px 与原外框 {outer.width}px 差异过大。")
        return outer, None, warnings

    refine_model = OuterRefineModel(
        original_left=int(outer.left),
        original_right=int(outer.right),
        refined_left=int(refined.left),
        refined_right=int(refined.right),
        start=float(model.start),
        pitch=float(model.pitch),
        inlier_indices=tuple(int(k) for k in model.inlier_indices),
        left_shift=actual_left_shift,
        right_shift=actual_right_shift,
        mode=str(config.outer_refine),
        iteration=int(iteration),
    )
    warnings.append(
        f"outer-refine 已根据可靠内部分隔线修正横向外框："
        f"left {outer.left}->{refined.left}, right {outer.right}->{refined.right}, "
        f"pitch={model.pitch:.1f}px, inliers={list(model.inlier_indices)}。"
    )
    return refined, refine_model, warnings


def refine_outer_and_redetect_gaps(
    gray: np.ndarray,
    outer: Box,
    gaps: list[Gap],
    image_width: int,
    image_height: int,
    config: SplitConfig,
) -> tuple[Box, list[Gap], Optional[OuterRefineModel], list[str]]:
    """Optionally refine horizontal outer box and re-run local gap detection."""
    warnings: list[str] = []
    last_model: Optional[OuterRefineModel] = None
    iterations = max(0, int(config.outer_refine_iterations))
    if iterations <= 0 or config.outer_refine == "off":
        return outer, gaps, None, warnings

    current_outer = outer
    current_gaps = gaps
    for iteration in range(1, iterations + 1):
        refined, model, step_warnings = propose_outer_x_from_grid(
            outer=current_outer,
            gaps=current_gaps,
            image_width=image_width,
            image_height=image_height,
            config=config,
            iteration=iteration,
        )
        warnings.extend(step_warnings)
        if model is None or refined == current_outer:
            break

        current_outer = refined
        last_model = model
        gray_outer = gray[current_outer.top:current_outer.bottom, current_outer.left:current_outer.right]
        current_gaps = detect_local_gaps(gray_outer, config)

    return current_outer, current_gaps, last_model, warnings


# -----------------------------------------------------------------------------
# Same-frame-size correction
# -----------------------------------------------------------------------------

def relative_content_ranges_from_gaps(
    gaps: list[Gap],
    count: int,
    outer_width: int,
    gap_crop_mode: str,
    gap_trim_px: int,
) -> list[tuple[float, float]]:
    """Return content ranges relative to the outer-cropped strip, before bleed."""
    if len(gaps) != max(0, count - 1):
        raise RuntimeError(f"内部分隔线数量异常：expected={count - 1}, got={len(gaps)}")

    trim = max(0, int(gap_trim_px))
    ranges: list[tuple[float, float]] = []
    for index in range(count):
        if index == 0:
            rel_left = 0.0
        else:
            left_gap = gaps[index - 1]
            if gap_crop_mode == "detected" and left_gap.width > 0:
                rel_left = float(left_gap.end)
            else:
                rel_left = float(left_gap.center) + (trim if gap_crop_mode == "fixed" else 0)

        if index == count - 1:
            rel_right = float(outer_width)
        else:
            right_gap = gaps[index]
            if gap_crop_mode == "detected" and right_gap.width > 0:
                rel_right = float(right_gap.start)
            else:
                rel_right = float(right_gap.center) - (trim if gap_crop_mode == "fixed" else 0)

        if rel_right <= rel_left:
            # Safety fallback for too-large fixed trim or inconsistent gaps.
            rel_left = 0.0 if index == 0 else float(gaps[index - 1].center)
            rel_right = float(outer_width) if index == count - 1 else float(gaps[index].center)
        ranges.append((rel_left, rel_right))
    return ranges


def gap_edge_weight(gap: Gap, min_score: float) -> float:
    """
    Weight of a separator band as evidence for true frame edges.

    Only actual bands/edge-pairs expose two useful edges. Center-only cuts are
    useful for splitting, but not for learning the true photographed-frame width.
    """
    if gap.width <= 0:
        return 0.0
    method = str(gap.method)
    if method == "edge-pair":
        base = 1.25
    elif method == "detected":
        base = 1.0
    else:
        return 0.0

    if method == "detected" and gap.score < float(min_score) * 0.55:
        return 0.0
    score_factor = min(1.50, max(0.25, float(gap.score)))
    return float(base * (0.60 + 0.40 * score_factor))


def trusted_frame_edges_from_gaps(
    gaps: list[Gap],
    count: int,
    min_score: float,
) -> tuple[list[Optional[tuple[float, float]]], list[Optional[tuple[float, float]]]]:
    """
    For each frame, return optional left/right photographed-frame edges.

    If gap i has a trusted band from x=start..end, then:
    - frame i right edge is start
    - frame i+1 left edge is end
    Coordinates are relative to the outer-cropped strip.
    """
    left_edges: list[Optional[tuple[float, float]]] = [None] * count
    right_edges: list[Optional[tuple[float, float]]] = [None] * count
    for index, gap in enumerate(gaps):
        weight = gap_edge_weight(gap, min_score)
        if weight <= 0.0:
            continue
        right_edges[index] = (float(gap.start), weight)
        left_edges[index + 1] = (float(gap.end), weight)
    return left_edges, right_edges


def robust_frame_width_from_edge_samples(
    left_edges: list[Optional[tuple[float, float]]],
    right_edges: list[Optional[tuple[float, float]]],
    nominal_width: float,
    min_samples: int,
    tolerance_ratio: float,
    min_ratio: float,
    max_ratio: float,
    mode: str,
) -> Optional[tuple[float, tuple[int, ...], tuple[float, ...]]]:
    """Estimate the common photographed-frame width from frames with both edges visible."""
    samples: list[tuple[int, float]] = []
    lo = float(nominal_width) * float(min_ratio)
    hi = float(nominal_width) * float(max_ratio)
    for index, (left, right) in enumerate(zip(left_edges, right_edges), 1):
        if left is None or right is None:
            continue
        width = float(right[0]) - float(left[0])
        if lo <= width <= hi:
            samples.append((index, width))

    needed = int(min_samples)
    if mode == "strict":
        needed = max(1, needed)
    if len(samples) < needed:
        return None

    widths = np.array([width for _, width in samples], dtype=np.float64)
    median = float(np.median(widths))
    if median <= 0:
        return None

    abs_tol = max(3.0, median * float(tolerance_ratio))
    mad = float(np.median(np.abs(widths - median))) if widths.size else 0.0
    robust_tol = max(abs_tol, mad * 3.0 * 1.4826)
    inliers = [(idx, width) for idx, width in samples if abs(width - median) <= robust_tol]
    if len(inliers) < needed:
        # If there are very few samples, do not over-filter them away.
        inliers = samples

    target = float(np.median(np.array([width for _, width in inliers], dtype=np.float64)))
    if not (lo <= target <= hi):
        return None
    return target, tuple(idx for idx, _ in inliers), tuple(float(width) for _, width in inliers)



def target_frame_width_from_pitch_and_gutters(
    gaps: list[Gap],
    count: int,
    nominal_width: float,
    min_gap_score: float,
    min_ratio: float,
    max_ratio: float,
    mode: str,
) -> Optional[tuple[float, tuple[int, ...], tuple[float, ...]]]:
    """
    Fallback estimator for cases where only a few adjacent frame-edge pairs are visible.

    It uses trusted separator centers to estimate the frame pitch, then subtracts the
    median trusted gutter width. This still relies only on locally accepted separators;
    it does not revive the old global black-band scan.
    """
    trusted: list[tuple[int, Gap, float]] = []
    for k, gap in enumerate(gaps, 1):
        weight = gap_edge_weight(gap, min_gap_score)
        if weight > 0.0 and gap.width > 0:
            trusted.append((k, gap, weight))

    if len(trusted) < (2 if mode == "strict" else 3):
        return None

    min_pitch = float(nominal_width) * 0.78
    max_pitch = float(nominal_width) * 1.22
    pitch_samples: list[float] = []
    for i, (ki, gi, _) in enumerate(trusted):
        for kj, gj, _ in trusted[i + 1:]:
            dk = int(kj) - int(ki)
            if dk <= 0:
                continue
            pitch = (float(gj.center) - float(gi.center)) / float(dk)
            if min_pitch <= pitch <= max_pitch:
                pitch_samples.append(float(pitch))

    if not pitch_samples:
        return None
    if mode == "auto" and len(pitch_samples) < 2:
        return None

    pitch = float(np.median(np.array(pitch_samples, dtype=np.float64)))
    gutter = float(np.median(np.array([gap.width for _, gap, _ in trusted], dtype=np.float64)))
    target = pitch - gutter
    lo = float(nominal_width) * float(min_ratio)
    hi = float(nominal_width) * float(max_ratio)
    if not (lo <= target <= hi):
        return None
    return float(target), tuple(k for k, _, _ in trusted), (float(target),)

def weighted_median(candidates: list[tuple[float, float]]) -> float:
    """Robust one-dimensional weighted median."""
    if not candidates:
        return 0.0
    ordered = sorted((float(v), max(0.0, float(w))) for v, w in candidates)
    total = sum(w for _, w in ordered)
    if total <= 0:
        return float(np.median(np.array([v for v, _ in ordered], dtype=np.float64)))
    acc = 0.0
    half = total / 2.0
    for value, weight in ordered:
        acc += weight
        if acc >= half:
            return value
    return ordered[-1][0]


def frame_has_weak_boundary(gaps: list[Gap], frame_index: int, count: int) -> bool:
    """Whether a frame is adjacent to a boundary that is not direct band/edge evidence."""
    adjacent: list[Gap] = []
    if frame_index > 0:
        adjacent.append(gaps[frame_index - 1])
    if frame_index < count - 1:
        adjacent.append(gaps[frame_index])
    for gap in adjacent:
        method = str(gap.method)
        if method.startswith("equal-") or method.startswith("grid-fit-") or method in {"peak-fallback", "edge-single-learned"}:
            return True
    return False


def boxes_from_relative_ranges(
    outer: Box,
    ranges: list[tuple[float, float]],
    image_width: int,
    image_height: int,
    bleed_x: int,
    bleed_y: int,
) -> list[Box]:
    boxes: list[Box] = []
    for left, right in ranges:
        box = Box(
            left=outer.left + int(round(left)) - bleed_x,
            top=outer.top - bleed_y,
            right=outer.left + int(round(right)) + bleed_x,
            bottom=outer.bottom + bleed_y,
        ).clamp(image_width, image_height)
        boxes.append(box)
    return boxes


def frame_boxes_with_same_size_fit(
    outer: Box,
    gaps: list[Gap],
    count: int,
    image_width: int,
    image_height: int,
    bleed_x: int,
    bleed_y: int,
    gap_crop_mode: str,
    gap_trim_px: int,
    fit_mode: str,
    min_samples: int,
    tolerance_ratio: float,
    min_ratio: float,
    max_ratio: float,
    base_weight: float,
    min_gap_score: float,
) -> tuple[list[Box], Optional[FrameSizeModel], list[str]]:
    """
    Build output boxes. Optional same-frame-size correction uses the 135-film prior that all
    photographed frames on one strip should have the same physical width.

    The correction is a post-processing step. It never searches the whole image
    for black bands, and it is skipped when there is not enough edge evidence.
    """
    base_ranges = relative_content_ranges_from_gaps(
        gaps=gaps,
        count=count,
        outer_width=outer.width,
        gap_crop_mode=gap_crop_mode,
        gap_trim_px=gap_trim_px,
    )
    warnings: list[str] = []

    if fit_mode == "off" or count <= 1 or outer.width <= 1:
        return boxes_from_relative_ranges(outer, base_ranges, image_width, image_height, bleed_x, bleed_y), None, warnings

    left_edges, right_edges = trusted_frame_edges_from_gaps(gaps, count, min_gap_score)
    nominal_width = float(outer.width) / float(count)
    model_data = robust_frame_width_from_edge_samples(
        left_edges=left_edges,
        right_edges=right_edges,
        nominal_width=nominal_width,
        min_samples=min_samples,
        tolerance_ratio=tolerance_ratio,
        min_ratio=min_ratio,
        max_ratio=max_ratio,
        mode=fit_mode,
    )
    if model_data is None:
        model_data = target_frame_width_from_pitch_and_gutters(
            gaps=gaps,
            count=count,
            nominal_width=nominal_width,
            min_gap_score=min_gap_score,
            min_ratio=min_ratio,
            max_ratio=max_ratio,
            mode=fit_mode,
        )
    if model_data is None:
        return boxes_from_relative_ranges(outer, base_ranges, image_width, image_height, bleed_x, bleed_y), None, warnings

    target_width, sample_indices, sample_widths = model_data
    if target_width <= 1 or target_width >= outer.width:
        return boxes_from_relative_ranges(outer, base_ranges, image_width, image_height, bleed_x, bleed_y), None, warnings

    max_left = max(0.0, float(outer.width) - target_width)
    new_ranges: list[tuple[float, float]] = []
    adjusted: list[int] = []
    tolerance_px = max(3.0, float(target_width) * float(tolerance_ratio))
    base_weight = max(0.0, float(base_weight))

    for index, (base_left, base_right) in enumerate(base_ranges):
        base_width = float(base_right) - float(base_left)
        weak = frame_has_weak_boundary(gaps, index, count)
        has_edge_anchor = left_edges[index] is not None or right_edges[index] is not None
        needs_adjust = (
            fit_mode == "strict"
            or weak
            or has_edge_anchor
            or abs(base_width - target_width) > tolerance_px
        )

        # In auto mode, avoid moving a completely unanchored frame that already
        # has a plausible width. This keeps normal strips close to the conservative base behavior.
        if fit_mode == "auto" and not needs_adjust:
            new_ranges.append((base_left, base_right))
            continue

        candidates: list[tuple[float, float]] = []
        if left_edges[index] is not None:
            candidates.append((float(left_edges[index][0]), float(left_edges[index][1])))
        if right_edges[index] is not None:
            candidates.append((float(right_edges[index][0]) - target_width, float(right_edges[index][1])))

        # Base center is a gentle fallback, not the main evidence.
        base_center_left = (float(base_left) + float(base_right) - target_width) / 2.0
        if base_weight > 0.0 or not candidates:
            fallback_weight = base_weight if candidates else 1.0
            candidates.append((base_center_left, fallback_weight))

        new_left = weighted_median(candidates)
        new_left = min(max(0.0, new_left), max_left)
        new_right = new_left + target_width

        if abs(new_left - float(base_left)) > 1.0 or abs(new_right - float(base_right)) > 1.0:
            adjusted.append(index + 1)
        new_ranges.append((new_left, new_right))

    model = FrameSizeModel(
        target_width=float(target_width),
        sample_indices=tuple(int(i) for i in sample_indices),
        sample_widths=tuple(float(w) for w in sample_widths),
        adjusted_indices=tuple(int(i) for i in adjusted),
        mode=str(fit_mode),
    )

    if adjusted:
        warnings.append(
            "同画幅尺寸校正已调整第 "
            + ", ".join(str(i) for i in adjusted)
            + f" 张；目标画幅宽度={target_width:.1f}px，样本帧={list(sample_indices)}。"
        )
    elif sample_indices:
        warnings.append(f"同画幅尺寸校正已学习目标画幅宽度={target_width:.1f}px，但无需移动输出框。")

    return boxes_from_relative_ranges(outer, new_ranges, image_width, image_height, bleed_x, bleed_y), model, warnings


def frame_box_warnings(boxes: list[Box], count: int) -> list[str]:
    warnings: list[str] = []
    widths = np.array([box.width for box in boxes], dtype=np.float64)
    if len(widths) != count or np.any(widths <= 0):
        return ["存在无效输出框。"]
    median_width = float(np.median(widths))
    if median_width <= 0:
        return ["输出宽度中位数无效。"]
    for i, width in enumerate(widths, 1):
        if width < median_width * 0.65 or width > median_width * 1.35:
            warnings.append(f"第 {i} 张宽度 {int(width)} 与中位宽度 {int(median_width)} 差异较大，请查看 debug 预览。")
    return warnings


# -----------------------------------------------------------------------------
# TIFF profile, writing, and validation
# -----------------------------------------------------------------------------

def description_is_safe(description: Any) -> bool:
    if not description:
        return False
    if isinstance(description, (bytes, bytearray)):
        text = bytes(description[:4096]).decode("utf-8", "ignore")
    else:
        text = str(description)[:4096]
    lowered = text.lower()
    risky_tokens = ("<ome", "imagej=", "images=", "channels=", "slices=", "frames=", "hyperstack=")
    return not any(token in lowered for token in risky_tokens)


def should_copy_description(page: tifffile.TiffPage, mode: str) -> bool:
    description = tag_value(page, 270)
    if mode == "yes":
        return bool(description)
    if mode == "no":
        return False
    return description_is_safe(description)


def extract_profile(path: Path, tif: tifffile.TiffFile, page: tifffile.TiffPage, arr: np.ndarray, axes: str, copy_description: str) -> TiffProfile:
    height, width = spatial_size(arr, axes)
    xres = tag_value(page, 282)
    yres = tag_value(page, 283)
    resolution = (xres, yres) if xres is not None and yres is not None else None

    icc = tag_value(page, 34675)
    colormap = getattr(page, "colormap", None)

    tile: Optional[tuple[int, int]] = None
    if bool(getattr(page, "is_tiled", False)):
        tile_length = int(getattr(page, "tilelength", 0) or 0)
        tile_width = int(getattr(page, "tilewidth", 0) or 0)
        if tile_length > 0 and tile_width > 0:
            tile = (tile_length, tile_width)

    return TiffProfile(
        path=str(path),
        is_bigtiff=bool(getattr(tif, "is_bigtiff", False)),
        byteorder=str(getattr(tif, "byteorder", "=")),
        shape=tuple(int(x) for x in arr.shape),
        dtype=str(arr.dtype),
        axes=axes,
        width=width,
        height=height,
        samples_per_pixel=int(getattr(page, "samplesperpixel", 1) or 1),
        bits_per_sample=normalize_value(tag_value(page, 258, getattr(page, "bitspersample", None))),
        sample_format=normalize_value(tag_value(page, 339, getattr(page, "sampleformat", None))),
        photometric=enum_int(getattr(page, "photometric", None), 1),
        photometric_name=enum_name(getattr(page, "photometric", None), ""),
        planarconfig=enum_int(getattr(page, "planarconfig", None), 1),
        planarconfig_name=enum_name(getattr(page, "planarconfig", None), ""),
        extrasamples=tuple(enum_int(x) for x in (getattr(page, "extrasamples", ()) or ())),
        compression=enum_int(getattr(page, "compression", None), 1),
        compression_name=enum_name(getattr(page, "compression", None), "NONE"),
        predictor=enum_int(getattr(page, "predictor", None), 1),
        rowsperstrip=int(getattr(page, "rowsperstrip", 0) or 0) or None,
        is_tiled=bool(getattr(page, "is_tiled", False)),
        tile=tile,
        resolution=resolution,
        resolution_unit=normalize_value(tag_value(page, 296)),
        orientation=normalize_value(tag_value(page, 274)),
        icc_len=len(icc) if isinstance(icc, (bytes, bytearray)) else 0,
        colormap_shape=tuple(int(x) for x in colormap.shape) if isinstance(colormap, np.ndarray) else None,
        description_copied=should_copy_description(page, copy_description),
    )


def bits_tuple(bits_per_sample: Any) -> tuple[Any, ...]:
    if isinstance(bits_per_sample, list):
        return tuple(bits_per_sample)
    if isinstance(bits_per_sample, tuple):
        return bits_per_sample
    return (bits_per_sample,)


def ensure_safe_bit_depth(profile: TiffProfile, arr: np.ndarray, allow_packed: bool) -> None:
    dtype_bits = np.dtype(arr.dtype).itemsize * 8
    mismatched: list[int] = []
    for bit_value in bits_tuple(profile.bits_per_sample):
        try:
            bit_int = int(bit_value)
        except Exception:
            continue
        if bit_int != dtype_bits:
            mismatched.append(bit_int)

    if mismatched and not allow_packed:
        raise RuntimeError(
            f"源文件 BitsPerSample={profile.bits_per_sample!r}，但 numpy dtype={arr.dtype} 通常会按 {dtype_bits}-bit 写出。\n"
            "这可能是 packed/非整字节位深 TIFF。为避免悄悄改变位深，脚本已停止。\n"
            "确认 tifffile 能正确写出这种位深后，才使用 --allow-packed-bit-depth。"
        )


def choose_compression(profile: TiffProfile, mode: str, allow_lossy: bool) -> Optional[int | str]:
    name = profile.compression_name.upper()
    compression_code = int(profile.compression)

    if mode == "same":
        if name in LOSSY_OR_UNCERTAIN_COMPRESSION_NAMES and not allow_lossy:
            raise RuntimeError(
                f"源 TIFF 压缩为 {profile.compression_name}，这类压缩可能是有损或不确定有损。\n"
                "为了确保输出只做裁切，脚本默认拒绝重新用同类压缩写出。\n"
                "可改用 --compression none，或确认后加 --allow-lossy-compression。"
            )
        if name not in LOSSLESS_COMPRESSION_NAMES and not allow_lossy:
            raise RuntimeError(
                f"源 TIFF 压缩为 {profile.compression_name}，脚本无法确认它一定无损。\n"
                "可改用 --compression none，或确认后加 --allow-lossy-compression。"
            )
        return None if compression_code == 1 else compression_code

    explicit = {
        "none": None,
        "lzw": "lzw",
        "deflate": "deflate",
        "zstd": "zstd",
    }
    if mode not in explicit:
        raise ValueError(f"未知压缩模式：{mode}")
    return explicit[mode]


def build_safe_extratags(page: tifffile.TiffPage, policy: str, max_bytes: int = 1_000_000) -> list[tuple[int, Any, int, Any, bool]]:
    if policy == "none":
        return []

    extratags: list[tuple[int, Any, int, Any, bool]] = []
    for tag in page.tags.values():
        code = int(tag.code)
        if code in HANDLED_OR_STRUCTURAL_TAGS:
            continue

        name = str(getattr(tag, "name", "")).lower()
        if any(token in name for token in ("offset", "bytecount", "strip", "tile", "subifd")):
            continue

        value = tag.value
        if value is None:
            continue

        if policy == "safe":
            if isinstance(value, (bytes, bytearray)) and len(value) > max_bytes:
                continue
            if isinstance(value, np.ndarray) and value.nbytes > max_bytes:
                continue
            if isinstance(value, str) and len(value.encode("utf-8", "ignore")) > max_bytes:
                continue

        if isinstance(value, np.ndarray):
            value = value.tolist()

        try:
            extratags.append((code, tag.dtype, int(tag.count), value, False))
        except Exception:
            continue

    return extratags


def add_managed_extratags(extratags: list[tuple[int, Any, int, Any, bool]], profile: TiffProfile) -> list[tuple[int, Any, int, Any, bool]]:
    # Orientation is not size-dependent and should remain identical after a crop.
    # tifffile.imwrite has no dedicated orientation parameter, so preserve it explicitly.
    if profile.orientation is not None:
        try:
            extratags.append((274, "H", 1, int(profile.orientation), False))
        except Exception:
            pass
    return extratags


def selected_description(page: tifffile.TiffPage, mode: str) -> Optional[str]:
    description = tag_value(page, 270)
    if mode == "no":
        return None
    if mode == "auto" and not description_is_safe(description):
        return None
    return text_tag_value(page, 270)


def packed_bits_value(profile: TiffProfile, arr: np.ndarray, allow_packed: bool) -> Optional[int]:
    if not allow_packed:
        return None
    values = bits_tuple(profile.bits_per_sample)
    if not values:
        return None
    try:
        unique_values = {int(v) for v in values if v is not None}
    except Exception:
        return None
    if len(unique_values) == 1:
        bit_count = unique_values.pop()
        if bit_count != np.dtype(arr.dtype).itemsize * 8:
            return bit_count
    return None


def write_kwargs(
    profile: TiffProfile,
    page: tifffile.TiffPage,
    cropped: np.ndarray,
    config: SplitConfig,
) -> dict[str, Any]:
    compression = choose_compression(profile, config.compression, config.allow_lossy_compression)

    kwargs: dict[str, Any] = {
        "bigtiff": bool(profile.is_bigtiff or cropped.nbytes > 3_800_000_000),
        "byteorder": profile.byteorder if profile.byteorder in ("<", ">") else None,
        "photometric": int(profile.photometric),  # 0 / MINISWHITE is valid and must be preserved.
        "metadata": None,
        "compression": compression,
        "software": text_tag_value(page, 305) if text_tag_value(page, 305) is not None else False,
        "description": selected_description(page, config.copy_description),
        "datetime": text_tag_value(page, 306),
    }

    if profile.samples_per_pixel > 1:
        kwargs["planarconfig"] = int(profile.planarconfig)
    if profile.extrasamples:
        kwargs["extrasamples"] = tuple(int(x) for x in profile.extrasamples)

    # Predictor is meaningful only with compression. Passing it with uncompressed output can create invalid tags.
    if compression is not None and profile.predictor and int(profile.predictor) != 1:
        kwargs["predictor"] = int(profile.predictor)

    packed_bits = packed_bits_value(profile, cropped, config.allow_packed_bit_depth)
    if packed_bits is not None:
        kwargs["bitspersample"] = int(packed_bits)

    if profile.resolution is not None:
        kwargs["resolution"] = profile.resolution
    if profile.resolution_unit is not None:
        kwargs["resolutionunit"] = int(profile.resolution_unit)

    icc = tag_value(page, 34675)
    if isinstance(icc, (bytes, bytearray)) and len(icc) > 0:
        kwargs["iccprofile"] = bytes(icc)

    colormap = getattr(page, "colormap", None)
    if isinstance(colormap, np.ndarray):
        kwargs["colormap"] = colormap

    if config.preserve_tiling and profile.is_tiled and profile.tile is not None:
        kwargs["tile"] = profile.tile
    elif profile.rowsperstrip:
        out_height = int(cropped.shape[profile.axes.index("Y")])
        kwargs["rowsperstrip"] = max(1, min(int(profile.rowsperstrip), out_height))

    extratags = build_safe_extratags(page, config.extra_tags)
    extratags = add_managed_extratags(extratags, profile)
    if extratags:
        kwargs["extratags"] = extratags

    return {key: value for key, value in kwargs.items() if value is not None}


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------

def values_equal(src: Any, out: Any) -> bool:
    return normalize_value(src) == normalize_value(out)


def append_mismatch(label: str, src: Any, out: Any, problems: list[str]) -> None:
    if not values_equal(src, out):
        problems.append(f"{label}: source={normalize_value(src)!r}, output={normalize_value(out)!r}")


def is_rational_pair(value: Any) -> bool:
    value = normalize_value(value)
    if not isinstance(value, tuple) or len(value) != 2:
        return False
    try:
        denominator = int(value[1])
        int(value[0])
    except Exception:
        return False
    return denominator != 0


def rational_value(value: Any) -> tuple[int, int]:
    value = normalize_value(value)
    return int(value[0]), int(value[1])


def resolution_equal(src: Any, out: Any) -> bool:
    src_norm = normalize_value(src)
    out_norm = normalize_value(out)
    if src_norm == out_norm:
        return True
    if is_rational_pair(src_norm) and is_rational_pair(out_norm):
        a, b = rational_value(src_norm)
        c, d = rational_value(out_norm)
        return a * d == c * b
    try:
        src_float = float(src_norm[0]) / float(src_norm[1]) if is_rational_pair(src_norm) else float(src_norm)
        out_float = float(out_norm[0]) / float(out_norm[1]) if is_rational_pair(out_norm) else float(out_norm)
        return math.isclose(src_float, out_float, rel_tol=1e-12, abs_tol=1e-12)
    except Exception:
        return False


def append_resolution_mismatch(label: str, src: Any, out: Any, problems: list[str]) -> None:
    if not resolution_equal(src, out):
        problems.append(f"{label}: source={normalize_value(src)!r}, output={normalize_value(out)!r}")


def validate_output(
    out_path: Path,
    profile: TiffProfile,
    source_page: tifffile.TiffPage,
    expected_shape: tuple[int, ...],
    expected_dtype: np.dtype,
    require_same_compression: bool,
) -> None:
    problems: list[str] = []
    with tifffile.TiffFile(out_path) as tif:
        if len(tif.pages) != 1:
            problems.append(f"pages: expected=1, output={len(tif.pages)}")
        page = tif.pages[0]

        try:
            out_arr = page.asarray()
            if tuple(int(x) for x in out_arr.shape) != tuple(int(x) for x in expected_shape):
                problems.append(f"array shape: expected={expected_shape}, output={out_arr.shape}")
            if str(out_arr.dtype) != str(expected_dtype):
                problems.append(f"dtype: expected={expected_dtype}, output={out_arr.dtype}")
        except Exception as exc:
            problems.append(f"readback: output cannot be read back ({exc})")

        append_mismatch("BitsPerSample", profile.bits_per_sample, tag_value(page, 258, getattr(page, "bitspersample", None)), problems)
        append_mismatch("SamplesPerPixel", profile.samples_per_pixel, int(getattr(page, "samplesperpixel", 1) or 1), problems)
        append_mismatch("PhotometricInterpretation", profile.photometric, enum_int(getattr(page, "photometric", None), 1), problems)
        append_mismatch("SampleFormat", profile.sample_format, tag_value(page, 339, getattr(page, "sampleformat", None)), problems)
        append_mismatch("ExtraSamples", profile.extrasamples, tuple(enum_int(x) for x in (getattr(page, "extrasamples", ()) or ())), problems)

        if profile.samples_per_pixel > 1:
            append_mismatch("PlanarConfiguration", profile.planarconfig, enum_int(getattr(page, "planarconfig", None), 1), problems)

        if profile.orientation is not None:
            append_mismatch("Orientation", profile.orientation, tag_value(page, 274), problems)

        src_icc = tag_value(source_page, 34675)
        out_icc = tag_value(page, 34675)
        if isinstance(src_icc, (bytes, bytearray)) and len(src_icc) > 0:
            if bytes(src_icc) != bytes(out_icc or b""):
                problems.append(f"ICCProfile: source={len(src_icc)} bytes, output={len(out_icc or b'')} bytes")

        if profile.resolution is not None:
            append_resolution_mismatch("XResolution", profile.resolution[0], tag_value(page, 282), problems)
            append_resolution_mismatch("YResolution", profile.resolution[1], tag_value(page, 283), problems)
        if profile.resolution_unit is not None:
            append_mismatch("ResolutionUnit", profile.resolution_unit, tag_value(page, 296), problems)

        if require_same_compression:
            append_mismatch("Compression", profile.compression, enum_int(getattr(page, "compression", None), 1), problems)
            if profile.predictor and int(profile.predictor) != 1:
                append_mismatch("Predictor", profile.predictor, enum_int(getattr(page, "predictor", None), 1), problems)

    if problems:
        raise RuntimeError("输出 TIFF 校验失败：\n  - " + "\n  - ".join(problems))


# -----------------------------------------------------------------------------
# Debug/report and processing
# -----------------------------------------------------------------------------

def save_debug_preview(gray: np.ndarray, outer: Box, boxes: list[Box], gaps: list[Gap], out_path: Path) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise RuntimeError("--debug 需要安装 Pillow：macOS 用 python3 -m pip install Pillow；Windows 用 py -3 -m pip install Pillow") from exc

    image = Image.fromarray(gray).convert("RGB")
    max_width = 2400
    scale = min(1.0, max_width / max(1, image.width))
    if scale < 1.0:
        new_size = (max(1, int(round(image.width * scale))), max(1, int(round(image.height * scale))))
        try:
            resample = Image.Resampling.BOX
        except AttributeError:
            resample = Image.BOX
        image = image.resize(new_size, resample=resample)

    def sx(x: int | float) -> int:
        return int(round(float(x) * scale))

    def sy(y: int | float) -> int:
        return int(round(float(y) * scale))

    draw = ImageDraw.Draw(image)
    draw.rectangle([sx(outer.left), sy(outer.top), sx(outer.right), sy(outer.bottom)], outline=(0, 255, 0), width=3)
    for box in boxes:
        draw.rectangle([sx(box.left), sy(box.top), sx(box.right), sy(box.bottom)], outline=(0, 128, 255), width=2)
    for gap in gaps:
        x0 = outer.left + gap.start
        x1 = outer.left + gap.end
        if gap.width > 0:
            draw.rectangle([sx(x0), sy(outer.top), sx(x1), sy(outer.bottom)], outline=(255, 0, 0), width=3)
        else:
            x = sx(outer.left + gap.center)
            draw.line([(x, sy(outer.top)), (x, sy(outer.bottom))], fill=(255, 0, 0), width=3)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, quality=92)



def save_analysis_debug(base_gray: np.ndarray, analysis_gray: np.ndarray, out_path: Path) -> None:
    """Save a compact before/after analysis map preview for tuning underexposed strips."""
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise RuntimeError("--debug-analysis 需要安装 Pillow：macOS 用 python3 -m pip install Pillow；Windows 用 py -3 -m pip install Pillow") from exc

    base = Image.fromarray(base_gray).convert("RGB")
    analysis = Image.fromarray(analysis_gray).convert("RGB")
    max_width = 2400
    scale = min(1.0, max_width / max(1, base.width))
    if scale < 1.0:
        new_size = (max(1, int(round(base.width * scale))), max(1, int(round(base.height * scale))))
        try:
            resample = Image.Resampling.BOX
        except AttributeError:
            resample = Image.BOX
        base = base.resize(new_size, resample=resample)
        analysis = analysis.resize(new_size, resample=resample)
    pad = 28
    sheet = Image.new("RGB", (base.width, base.height * 2 + pad * 2), (245, 245, 245))
    sheet.paste(base, (0, pad))
    sheet.paste(analysis, (0, base.height + pad * 2))
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 6), "base detection gray", fill=(0, 0, 0))
    draw.text((8, base.height + pad + 6), "hybrid enhanced analysis gray", fill=(0, 0, 0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=92)


def detection_score_detail(run_label: str, gray: np.ndarray, outer: Box, gaps: list[Gap], boxes: list[Box], frame_size_model: Optional[FrameSizeModel], config: SplitConfig) -> dict[str, Any]:
    reliable = sum(1 for gap in gaps if gap_is_reliable_for_grid(gap, config.min_gap_score))
    detected = sum(1 for gap in gaps if gap.method in {"detected", "edge-pair", "edge-single-learned"})
    equal = sum(1 for gap in gaps if gap.method.startswith("equal-"))
    peak = sum(1 for gap in gaps if gap.method == "peak-fallback")
    model = fit_robust_grid_model(
        gaps=gaps,
        count=config.count,
        width=outer.width,
        min_score=config.min_gap_score,
        min_inliers=max(2, min(config.grid_min_inliers, max(2, config.count - 2))),
        tolerance_ratio=max(config.grid_tolerance_ratio, config.outer_refine_tolerance_ratio),
        pitch_tolerance_ratio=max(config.grid_pitch_tolerance_ratio, config.outer_refine_pitch_tolerance_ratio),
    )
    nominal_width = float(outer.width) / max(1, int(config.count))
    if boxes:
        widths = np.array([max(1, box.width - 2 * int(config.bleed_x)) for box in boxes], dtype=np.float64)
        median_width = float(np.median(widths)) if widths.size else 0.0
        width_cv = float(np.std(widths) / max(1.0, median_width)) if widths.size else 1.0
        frame_widths = [float(x) for x in widths.tolist()]
    else:
        median_width = 0.0
        width_cv = 1.0
        frame_widths = []

    outer_area_ratio = float(outer.width * outer.height) / max(1.0, float(gray.shape[0] * gray.shape[1]))
    grid_residual = None if model is None else float(model.median_residual)
    grid_score = 0.0 if model is None else max(0.0, 1.0 - float(model.median_residual) / max(1.0, nominal_width * 0.10))
    width_score = max(0.0, 1.0 - width_cv * 8.0)
    score = 0.0
    score += reliable * 2.75
    score += detected * 0.90
    score -= equal * 0.60
    score -= peak * 1.25
    score += grid_score * 4.0
    score += width_score * 2.5
    if frame_size_model is not None:
        score += 0.80
        if frame_size_model.adjusted_indices:
            score += 0.25
    if not outer.valid() or len(boxes) != int(config.count):
        score -= 100.0
    if outer_area_ratio < 0.40:
        score -= (0.40 - outer_area_ratio) * 10.0
    if outer_area_ratio > 0.995:
        # The whole scanner bed is sometimes correct with --no-outer-crop, so keep this gentle.
        score -= 0.3

    return {
        "label": run_label,
        "score": float(score),
        "reliable_gaps": int(reliable),
        "detected_gaps": int(detected),
        "equal_gaps": int(equal),
        "peak_fallback_gaps": int(peak),
        "grid_residual": grid_residual,
        "width_cv": float(width_cv),
        "median_frame_width_without_bleed": float(median_width),
        "outer_area_ratio": float(outer_area_ratio),
        "outer_box": asdict(outer),
        "gap_methods": [str(gap.method) for gap in gaps],
        "gap_centers": [float(gap.center) for gap in gaps],
        "gap_scores": [float(gap.score) for gap in gaps],
        "frame_widths_without_bleed": frame_widths,
    }


def run_detection_pipeline(gray_for_detection: np.ndarray, image_width: int, image_height: int, config: SplitConfig, label: str) -> DetectionRun:
    """Run the established outer/gap/grid/frame-size pipeline on one detection gray map."""
    run_warnings: list[str] = []
    if config.no_outer_crop:
        outer = Box(0, 0, image_width, image_height)
        gray_outer = gray_for_detection[outer.top:outer.bottom, outer.left:outer.right]
        gaps = detect_local_gaps(gray_outer, config)
    else:
        outer, gaps = choose_initial_outer_box(gray_for_detection, config, run_warnings)

    outer, gaps, outer_refine_model, outer_refine_warnings = refine_outer_and_redetect_gaps(
        gray=gray_for_detection,
        outer=outer,
        gaps=gaps,
        image_width=image_width,
        image_height=image_height,
        config=config,
    )
    run_warnings.extend(outer_refine_warnings)

    gaps, grid_warnings = apply_robust_grid(
        gaps=gaps,
        count=config.count,
        width=outer.width,
        min_score=config.min_gap_score,
        mode=config.grid_fit,
        min_inliers=config.grid_min_inliers,
        tolerance_ratio=config.grid_tolerance_ratio,
        pitch_tolerance_ratio=config.grid_pitch_tolerance_ratio,
        min_replace_px=config.grid_min_replace_px,
    )
    run_warnings.extend(grid_warnings)
    run_warnings.extend(warning_for_gap_methods(gaps))

    boxes, frame_size_model, frame_size_warnings = frame_boxes_with_same_size_fit(
        outer=outer,
        gaps=gaps,
        count=config.count,
        image_width=image_width,
        image_height=image_height,
        bleed_x=config.bleed_x,
        bleed_y=config.bleed_y,
        gap_crop_mode=config.gap_crop_mode,
        gap_trim_px=config.gap_trim_px,
        fit_mode=config.frame_size_fit,
        min_samples=config.frame_size_min_samples,
        tolerance_ratio=config.frame_size_tolerance_ratio,
        min_ratio=config.frame_size_min_ratio,
        max_ratio=config.frame_size_max_ratio,
        base_weight=config.frame_size_base_weight,
        min_gap_score=config.min_gap_score,
    )
    run_warnings.extend(frame_size_warnings)
    run_warnings.extend(frame_box_warnings(boxes, config.count))

    detail = detection_score_detail(label, gray_for_detection, outer, gaps, boxes, frame_size_model, config)
    return DetectionRun(
        label=label,
        outer=outer,
        gaps=gaps,
        boxes=boxes,
        outer_refine_model=outer_refine_model,
        frame_size_model=frame_size_model,
        warnings=run_warnings,
        score=float(detail["score"]),
        score_detail=detail,
    )



def detection_run_is_confident_for_fast_skip(run: DetectionRun, config: SplitConfig) -> bool:
    """Return True when the base candidate is stable enough to skip extra auto candidates.

    This is intentionally conservative: it only skips enhanced candidate pipelines
    for normal/easy strips where the established base pipeline already has enough
    reliable separators or very stable geometry. Underexposed/ambiguous strips still
    get the enhanced analysis pass.
    """
    if config.analysis_enhance != "auto" or not bool(config.analysis_fast_skip):
        return False

    detail = run.score_detail
    reliable = int(detail.get("reliable_gaps", 0))
    detected = int(detail.get("detected_gaps", 0))
    equal = int(detail.get("equal_gaps", 0))
    peak = int(detail.get("peak_fallback_gaps", 0))
    width_cv = float(detail.get("width_cv", 1.0))
    outer_area = float(detail.get("outer_area_ratio", 0.0))
    residual = detail.get("grid_residual", None)
    median_w = float(detail.get("median_frame_width_without_bleed", 0.0))

    if peak > 0 or not (0.42 <= outer_area <= 0.995):
        return False

    if residual is None:
        residual_ok = equal >= max(3, int(config.count) - 2) and width_cv <= 0.0035
    else:
        residual_ok = float(residual) <= max(2.0, median_w * 0.022)

    # Normal case: enough actual separators and stable geometry.
    if reliable >= max(3, int(config.count) - 3) and detected >= 2 and equal <= 2 and width_cv <= 0.010 and residual_ok:
        return True

    # Safe geometric case: no suspicious peaks, all/everything mostly falls back
    # to the theoretical grid, and frame widths are extremely consistent. This is
    # often preferable for very dark frames where chasing weak local evidence hurts.
    if equal >= max(4, int(config.count) - 2) and width_cv <= 0.0025 and outer_area >= 0.50:
        return True

    return False


def should_run_analysis_edge_candidate(base_run: DetectionRun, analysis_run: Optional[DetectionRun], config: SplitConfig) -> bool:
    """Decide whether the expensive enhanced-edge candidate is worth running."""
    policy = str(config.analysis_edge_candidate)
    if policy == "off" or analysis_run is None:
        return False
    if policy == "always" or config.analysis_enhance == "strict":
        return True

    base = base_run.score_detail
    cand = analysis_run.score_detail
    base_rel = int(base.get("reliable_gaps", 0))
    cand_rel = int(cand.get("reliable_gaps", 0))
    base_equal = int(base.get("equal_gaps", 0))
    cand_equal = int(cand.get("equal_gaps", 0))
    base_width_cv = float(base.get("width_cv", 1.0))
    cand_width_cv = float(cand.get("width_cv", 1.0))

    weak_base = base_rel <= 1 or base_equal >= 2 or base_width_cv >= max(0.006, float(config.analysis_geometry_min_base_cv))
    weak_analysis = cand_rel <= 1 or cand_equal >= 2 or cand_width_cv >= max(0.006, float(config.analysis_geometry_min_base_cv))
    analysis_improves = cand_rel > base_rel or cand_equal < base_equal or cand_width_cv < base_width_cv * 0.75

    return weak_base and (weak_analysis or analysis_improves)

def selection_reason_against_base(base_run: DetectionRun, candidate: DetectionRun, config: SplitConfig) -> Optional[str]:
    """Return a reason when an enhanced/edge candidate is allowed to replace base."""
    base = base_run.score_detail
    cand = candidate.score_detail
    base_score = float(base.get("score", base_run.score))
    cand_score = float(cand.get("score", candidate.score))
    base_rel = int(base.get("reliable_gaps", 0))
    cand_rel = int(cand.get("reliable_gaps", 0))
    base_equal = int(base.get("equal_gaps", 0))
    cand_equal = int(cand.get("equal_gaps", 0))
    base_width_cv = float(base.get("width_cv", 1.0))
    cand_width_cv = float(cand.get("width_cv", 1.0))
    base_outer_area = float(base.get("outer_area_ratio", 0.0))
    cand_outer_area = float(cand.get("outer_area_ratio", 0.0))
    base_med = float(base.get("median_frame_width_without_bleed", 0.0))
    cand_med = float(cand.get("median_frame_width_without_bleed", 0.0))

    if config.analysis_enhance == "strict":
        if cand_score >= base_score - 0.25 or cand_rel > base_rel or cand_equal < base_equal:
            return "strict-analysis"

    gain = max(0.35, abs(base_score) * float(config.analysis_candidate_gain_ratio))
    if cand_score >= base_score + gain:
        return f"analysis-score-gain>={gain:.2f}"
    if cand_rel >= base_rel + 1 and cand_equal <= base_equal:
        return "analysis-more-reliable-gaps"
    if base_equal >= 2 and cand_equal < base_equal and cand_score >= base_score - 0.20:
        return "analysis-reduces-equal-fallbacks"

    # New in v17: for very low-evidence strips, a candidate that falls back to a
    # clean geometric split can be more useful than one or two unstable detected
    # separators. This targets underexposed test cases where the picture content
    # is visible in the analysis map but true gutters are too broad/weak for a
    # normal narrow-band detector.
    if bool(config.analysis_geometry_select) and base_rel <= 1 and cand_rel <= 1 and base_equal >= max(3, config.count - 3) and base_width_cv >= float(config.analysis_geometry_min_base_cv):
        median_close = True
        if base_med > 0 and cand_med > 0:
            median_close = abs(cand_med - base_med) / max(base_med, cand_med, 1.0) <= 0.08
        area_safe = cand_outer_area >= base_outer_area - 0.025
        width_much_better = cand_width_cv <= max(0.0015, base_width_cv * 0.35)
        score_not_absurd = cand_score >= base_score - 5.0
        if median_close and area_safe and width_much_better and score_not_absurd:
            return "low-evidence-geometry-fallback"

    # Another safe case: candidate uses edge refinement to turn broad dark bands
    # into consistent frame geometry. Let it replace base when geometry is much
    # more stable and it does not shrink the usable strip materially.
    if candidate.label.endswith("edge") and cand_rel >= base_rel and base_equal >= 2:
        if cand_width_cv <= max(0.002, base_width_cv * 0.55) and cand_outer_area >= base_outer_area - 0.02:
            return "analysis-edge-geometry"

    return None


def choose_detection_run(
    base_run: DetectionRun,
    analysis_run: Optional[DetectionRun],
    config: SplitConfig,
    extra_runs: Optional[list[DetectionRun]] = None,
) -> tuple[DetectionRun, dict[str, Any], list[str]]:
    """Select base or one of the detection-only enhanced candidates."""
    runs: list[DetectionRun] = []
    if analysis_run is not None:
        runs.append(analysis_run)
    if extra_runs:
        runs.extend(extra_runs)

    if not runs or config.analysis_enhance == "off":
        return base_run, {"selected": "base", "reason": "base-only", "base": base_run.score_detail, "analysis": None, "candidates": []}, []

    eligible: list[tuple[DetectionRun, str]] = []
    for run in runs:
        reason = selection_reason_against_base(base_run, run, config)
        if reason is not None:
            eligible.append((run, reason))

    if eligible:
        def rank(item: tuple[DetectionRun, str]) -> tuple[float, int, int, float, float]:
            run, reason = item
            detail = run.score_detail
            # Score first; geometry fallback can have low score, so include
            # reliable/equal and width stability as secondary criteria.
            return (
                float(run.score),
                int(detail.get("reliable_gaps", 0)),
                -int(detail.get("equal_gaps", 0)),
                -float(detail.get("width_cv", 1.0)),
                float(detail.get("outer_area_ratio", 0.0)),
            )
        selected, reason = max(eligible, key=rank)
    else:
        selected, reason = base_run, "base-kept"

    warnings: list[str] = []
    if selected is base_run:
        score_parts = ", ".join(f"{run.label}={run.score:.2f}" for run in runs)
        warnings.append(f"analysis-enhance 未替换 base 候选：base_score={base_run.score:.2f}, {score_parts}。")
    else:
        warnings.append(
            f"analysis-enhance 已采用 {selected.label} 候选：base_score={base_run.score:.2f}, "
            f"selected_score={selected.score:.2f}, reason={reason}。"
        )

    return selected, {
        "selected": selected.label,
        "reason": reason,
        "base": base_run.score_detail,
        "analysis": analysis_run.score_detail if analysis_run is not None else None,
        "candidates": [run.score_detail for run in runs],
    }, warnings

def write_report(report_path: Path, result: ProcessResult) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(json_safe(asdict(result)), ensure_ascii=False) + "\n")


def write_summary_report(summary_path: Path, result: ProcessResult) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source",
        "status",
        "confidence",
        "film_format",
        "layout",
        "strip_completeness",
        "lane_count",
        "frames_per_lane",
        "review_reasons",
        "output_count",
    ]
    exists = summary_path.exists()
    with summary_path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "source": result.source,
                "status": result.status,
                "confidence": f"{result.confidence:.3f}",
                "film_format": result.film_format,
                "layout": result.layout,
                "strip_completeness": result.strip_completeness,
                "lane_count": int(result.lane_count),
                "frames_per_lane": int(result.frames_per_lane),
                "review_reasons": ";".join(result.review_reasons),
                "output_count": len(result.output_files),
            }
        )


def warning_for_gap_methods(gaps: list[Gap]) -> list[str]:
    warnings: list[str] = []
    for index, gap in enumerate(gaps, 1):
        if gap.method.startswith("equal-") and gap.method != "equal-forced":
            warnings.append(
                f"第 {index} 条内部分隔线使用理论等分位置而不是暗/亮峰值；"
                "这通常是为了避免欠曝暗区被当作分隔条。"
            )
        if gap.method == "peak-fallback":
            warnings.append(f"第 {index} 条内部分隔线使用了 --allow-peak-fallback，欠曝图存在误切风险。")
    return warnings


def output_directory_for(input_file: Path, config: SplitConfig) -> Path:
    return config.output.resolve() if config.output else input_file.parent / "split_output"


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def image_quality_detail(gray: np.ndarray) -> dict[str, float]:
    sample = gray
    if sample.size > 1_500_000:
        step = max(1, int(math.sqrt(sample.size / 1_500_000)))
        sample = sample[::step, ::step]
    p01, p05, p50, p95, p99 = np.percentile(sample, [1, 5, 50, 95, 99])
    return {
        "p01": float(p01),
        "p05": float(p05),
        "p50": float(p50),
        "p95": float(p95),
        "p99": float(p99),
        "range_1_99": float(p99 - p01),
    }


def assess_auto_confidence(run: DetectionRun, gray: np.ndarray, config: SplitConfig) -> tuple[float, list[str], dict[str, Any]]:
    detail = dict(run.score_detail)
    expected_gaps = max(0, int(config.count) - 1)
    reliable = int(detail.get("reliable_gaps", 0))
    detected = int(detail.get("detected_gaps", 0))
    equal = int(detail.get("equal_gaps", 0))
    peak = int(detail.get("peak_fallback_gaps", 0))
    width_cv = float(detail.get("width_cv", 1.0))
    outer_area = float(detail.get("outer_area_ratio", 0.0))
    median_width = float(detail.get("median_frame_width_without_bleed", 0.0))
    residual = detail.get("grid_residual", None)

    if expected_gaps <= 0:
        gap_conf = 1.0
        reliable_ratio = 1.0
        equal_ratio = 0.0
    else:
        reliable_ratio = clamp01(reliable / float(expected_gaps))
        equal_ratio = clamp01(equal / float(expected_gaps))
        detected_ratio = clamp01(detected / float(expected_gaps))
        gap_conf = clamp01(0.70 * reliable_ratio + 0.20 * detected_ratio + 0.10 * (1.0 - equal_ratio))

    if residual is None:
        grid_conf = 0.78 if width_cv <= 0.004 and equal >= max(1, expected_gaps - 1) else 0.35
    else:
        grid_conf = clamp01(1.0 - float(residual) / max(2.0, median_width * 0.035))

    width_conf = clamp01(1.0 - width_cv / 0.025)
    if 0.45 <= outer_area <= 0.995:
        outer_conf = 1.0
    elif 0.35 <= outer_area < 0.45:
        outer_conf = clamp01((outer_area - 0.35) / 0.10)
    elif 0.995 < outer_area <= 1.0:
        outer_conf = 0.85
    else:
        outer_conf = 0.30

    quality = image_quality_detail(gray)
    quality_conf = 1.0
    if quality["range_1_99"] < 24:
        quality_conf = 0.55
    elif quality["range_1_99"] < 40:
        quality_conf = 0.78
    if quality["p95"] < 36 or quality["p05"] > 220:
        quality_conf = min(quality_conf, 0.70)

    confidence = (
        0.42 * gap_conf
        + 0.24 * grid_conf
        + 0.18 * width_conf
        + 0.10 * outer_conf
        + 0.06 * quality_conf
    )
    if peak > 0:
        confidence -= 0.22
    if len(run.boxes) != int(config.count):
        confidence -= 0.35
    confidence = clamp01(confidence)

    reasons: list[str] = []
    if expected_gaps > 0 and reliable < max(2, expected_gaps - 1):
        reasons.append("weak_separators")
    if expected_gaps > 0 and equal >= max(2, expected_gaps - 2):
        reasons.append("equal_split_fallback")
    if peak > 0:
        reasons.append("peak_fallback_used")
    if residual is None:
        reasons.append("grid_model_missing")
    elif median_width > 0 and float(residual) > max(2.0, median_width * 0.035):
        reasons.append("unstable_spacing")
    if width_cv > 0.025:
        reasons.append("unstable_frame_width")
    if not (0.40 <= outer_area <= 0.995):
        reasons.append("outer_box_uncertain")
    if quality["range_1_99"] < 40:
        reasons.append("low_contrast")
    if quality["p95"] < 36:
        reasons.append("low_exposure")
    if quality["p05"] > 220:
        reasons.append("mostly_bright_scan")
    if len(run.boxes) != int(config.count):
        reasons.append("frame_count_mismatch")

    profile = FILM_FORMATS.get(config.film_format)
    full_geometry_width_limit = {
        "135": 0.008,
        "half": 0.006,
        "xpan": 0.010,
        "120-645": 0.010,
        "120-66": 0.010,
        "120-67": 0.010,
    }.get(config.film_format, 0.008)
    full_geometry_separator_ok = (
        config.film_format in {"135", "half"}
        or expected_gaps <= 0
        or reliable >= max(1, expected_gaps // 2)
    )
    full_strip_geometry = (
        profile is not None
        and config.strip_completeness == "full"
        and int(config.count) == int(profile.default_count)
        and len(run.boxes) == int(config.count)
        and width_cv <= full_geometry_width_limit
        and 0.45 <= outer_area <= 0.995
        and full_geometry_separator_ok
    )
    if full_strip_geometry:
        confidence = max(confidence, 0.88)
        reasons = [
            reason for reason in reasons
            if reason not in {"weak_separators", "equal_split_fallback", "grid_model_missing", "low_confidence"}
        ]
        detail["full_strip_geometry_confident"] = True

    if profile is not None and config.strip_completeness == "partial" and int(config.count) < int(profile.default_count):
        if int(config.count) <= 1:
            confidence = min(confidence, 0.78)
            if "partial_too_ambiguous" not in reasons:
                reasons.append("partial_too_ambiguous")
        elif int(config.count) <= 2 and int(profile.default_count) >= 6:
            confidence = min(confidence, 0.82)
            if "partial_too_ambiguous" not in reasons:
                reasons.append("partial_too_ambiguous")
        else:
            confidence = min(confidence, 0.84)
        if "partial_strip_count_candidate" not in reasons:
            reasons.append("partial_strip_count_candidate")

    if confidence < float(config.confidence_threshold) and not reasons:
        reasons.append("low_confidence")

    review_detail = {
        **detail,
        "confidence": float(confidence),
        "confidence_threshold": float(config.confidence_threshold),
        "confidence_parts": {
            "gap": float(gap_conf),
            "grid": float(grid_conf),
            "width": float(width_conf),
            "outer": float(outer_conf),
            "quality": float(quality_conf),
        },
        "image_quality": quality,
    }
    return confidence, reasons, review_detail


def review_directory_for(output_dir: Path, config: SplitConfig) -> Path:
    return config.review_dir.resolve() if config.review_dir else output_dir / "needs_review"


def unique_review_copy_path(input_file: Path, review_dir: Path) -> Path:
    candidate = review_dir / input_file.name
    if not candidate.exists():
        return candidate
    for index in range(2, 10_000):
        candidate = review_dir / f"{input_file.stem}_{index:02d}{input_file.suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法为 review 文件生成不冲突的文件名：{input_file.name}")


def copy_file_for_review(input_file: Path, review_dir: Path) -> Path:
    review_dir.mkdir(parents=True, exist_ok=True)
    destination = unique_review_copy_path(input_file, review_dir)
    shutil.copy2(input_file, destination)
    return destination


def shift_box(box: Box, dx: int, dy: int) -> Box:
    return Box(box.left + dx, box.top + dy, box.right + dx, box.bottom + dy)


def union_box(boxes: list[Box], image_width: int, image_height: int) -> Box:
    valid = [box for box in boxes if box.valid()]
    if not valid:
        return Box(0, 0, image_width, image_height)
    return Box(
        min(box.left for box in valid),
        min(box.top for box in valid),
        max(box.right for box in valid),
        max(box.bottom for box in valid),
    ).clamp(image_width, image_height)


def box_from_work_axis(box: Box, split_axis: str, dx: int = 0, dy: int = 0) -> Box:
    if split_axis == "x":
        return shift_box(box, dx, dy)
    return Box(
        left=box.top + dx,
        top=box.left + dy,
        right=box.bottom + dx,
        bottom=box.right + dy,
    )


def config_for_split_axis(config: SplitConfig, split_axis: str) -> SplitConfig:
    if split_axis == "x":
        return config
    return replace(config, bleed_x=config.bleed_y, bleed_y=config.bleed_x)


def work_gray_for_axis(gray: np.ndarray, split_axis: str) -> np.ndarray:
    return gray if split_axis == "x" else np.ascontiguousarray(gray.T)


def detect_single_strip_layout(
    gray: np.ndarray,
    analysis_gray: np.ndarray,
    image_width: int,
    image_height: int,
    config: SplitConfig,
    split_axis: str,
    label_prefix: str,
    offset_x: int = 0,
    offset_y: int = 0,
) -> LayoutDetection:
    work_config = config_for_split_axis(config, split_axis)
    work_gray = work_gray_for_axis(gray, split_axis)
    work_analysis_gray = work_gray_for_axis(analysis_gray, split_axis)
    work_height, work_width = work_gray.shape

    warnings: list[str] = []
    base_run = run_detection_pipeline(work_gray, work_width, work_height, work_config, f"{label_prefix}-base")
    analysis_run: Optional[DetectionRun] = None
    extra_runs: list[DetectionRun] = []
    if work_config.analysis_enhance != "off":
        if work_analysis_gray is work_gray or np.shares_memory(work_analysis_gray, work_gray):
            warnings.append("analysis-enhance 已开启，但增强分析图与 base 灰度图一致，跳过增强候选。")
        elif detection_run_is_confident_for_fast_skip(base_run, work_config):
            warnings.append(
                "analysis-enhance auto：base 候选已经足够稳定，跳过增强候选检测管线以提速；"
                "如需强制评估增强候选，使用 --analysis-no-fast-skip 或 --analysis-enhance strict。"
            )
        else:
            analysis_run = run_detection_pipeline(work_analysis_gray, work_width, work_height, work_config, f"{label_prefix}-analysis-enhanced")
            if not work_config.edge_refine and should_run_analysis_edge_candidate(base_run, analysis_run, work_config):
                edge_config = replace(work_config, edge_refine=True, edge_refine_single="learned")
                extra_runs.append(run_detection_pipeline(work_analysis_gray, work_width, work_height, edge_config, f"{label_prefix}-analysis-enhanced-edge"))

    selected_run, analysis_candidate, selection_warnings = choose_detection_run(base_run, analysis_run, work_config, extra_runs)
    warnings.extend(selection_warnings)
    warnings.extend(selected_run.warnings)

    confidence, review_reasons, detection_detail = assess_auto_confidence(selected_run, work_gray, work_config)
    boxes = [box_from_work_axis(box, split_axis, offset_x, offset_y).clamp(image_width, image_height) for box in selected_run.boxes]
    outer = box_from_work_axis(selected_run.outer, split_axis, offset_x, offset_y).clamp(image_width, image_height)
    gaps = selected_run.gaps if split_axis == "x" and offset_x == 0 and offset_y == 0 else []
    detection_detail["split_axis"] = split_axis
    detection_detail["offset"] = {"x": int(offset_x), "y": int(offset_y)}

    return LayoutDetection(
        film_format=config.film_format,
        layout=("single-horizontal" if split_axis == "x" else "single-vertical"),
        lane_count=1,
        frames_per_lane=int(config.count),
        outer=outer,
        boxes=boxes,
        gaps=gaps,
        outer_refine_model=selected_run.outer_refine_model,
        frame_size_model=selected_run.frame_size_model,
        analysis_candidate=json_safe(analysis_candidate),
        warnings=warnings,
        confidence=float(confidence),
        review_reasons=review_reasons,
        detection_detail=json_safe(detection_detail),
    )


def detect_layout(
    gray: np.ndarray,
    analysis_gray: np.ndarray,
    image_width: int,
    image_height: int,
    config: SplitConfig,
) -> LayoutDetection:
    layout = str(config.layout)
    if layout == "single-horizontal":
        return detect_single_strip_layout(gray, analysis_gray, image_width, image_height, config, "x", "single-horizontal")
    if layout == "single-vertical":
        return detect_single_strip_layout(gray, analysis_gray, image_width, image_height, config, "y", "single-vertical")

    raise RuntimeError(f"内部错误：未知 layout={layout}")


def rank_layout_detection(detection: LayoutDetection, config: SplitConfig) -> tuple[int, float, int]:
    approved = 1 if detection.confidence >= float(config.confidence_threshold) else 0
    return approved, float(detection.confidence), int(detection.frames_per_lane)


def partial_count_candidates(config: SplitConfig, seed_detection: Optional[LayoutDetection] = None) -> tuple[int, ...]:
    profile = FILM_FORMATS[config.film_format]
    allowed = tuple(int(x) for x in profile.allowed_counts if int(x) <= int(profile.default_count))
    default = int(profile.default_count)
    candidates: set[int] = {default}

    # Try counts close to a normal full strip first; leader/tail cases often miss
    # only one or two frames.
    for count in (default - 1, default - 2):
        if count >= 1:
            candidates.add(count)

    # Use the already-computed full pass as a cheap hint. If it saw roughly N
    # separators, N+1 frames is worth checking before running every allowed count.
    if seed_detection is not None:
        detail = seed_detection.detection_detail
        for key in ("reliable_gaps", "detected_gaps"):
            seen = int(detail.get(key, 0))
            for count in (seen + 1, seen, seen + 2):
                if count >= 1:
                    candidates.add(count)

    # Keep a few low-count tail/leader candidates, but do not let them explode
    # into a full sweep for half-frame strips.
    candidates.add(1)
    if default >= 3:
        candidates.add(2)
    if default >= 6:
        candidates.add(max(1, default // 2))

    filtered = [count for count in candidates if count in allowed]
    return tuple(sorted(set(filtered), reverse=True))


def detect_partial_layout(
    gray: np.ndarray,
    analysis_gray: np.ndarray,
    image_width: int,
    image_height: int,
    config: SplitConfig,
    seed_detection: Optional[LayoutDetection] = None,
) -> LayoutDetection:
    candidates: list[LayoutDetection] = []
    for count in partial_count_candidates(config, seed_detection):
        if seed_detection is not None and int(count) == int(seed_detection.frames_per_lane):
            detection = replace(
                seed_detection,
                detection_detail=dict(seed_detection.detection_detail),
                review_reasons=list(seed_detection.review_reasons),
                warnings=list(seed_detection.warnings),
            )
        else:
            candidate_config = replace(config, count=int(count), strip_completeness="partial")
            try:
                detection = detect_layout(gray, analysis_gray, image_width, image_height, candidate_config)
            except Exception as exc:
                continue
        detection.detection_detail["strip_completeness"] = "partial"
        detection.detection_detail["count_candidate"] = int(count)
        candidates.append(detection)

    if not candidates:
        raise RuntimeError("partial-strip 未找到可用候选。")

    best = max(candidates, key=lambda item: rank_layout_detection(item, config))
    best.analysis_candidate = {
        "selected": best.analysis_candidate,
        "strip_completeness": "partial",
        "count_candidates": [
            {
                "count": int(item.frames_per_lane),
                "confidence": float(item.confidence),
                "reasons": list(item.review_reasons),
            }
            for item in candidates
        ],
    }
    if "partial_strip_candidate" not in best.review_reasons and best.confidence < float(config.confidence_threshold):
        best.review_reasons.append("partial_strip_candidate")
    return best


def detect_layout_with_completeness(
    gray: np.ndarray,
    analysis_gray: np.ndarray,
    image_width: int,
    image_height: int,
    config: SplitConfig,
) -> LayoutDetection:
    if config.strip_completeness == "full":
        detection = detect_layout(gray, analysis_gray, image_width, image_height, replace(config, strip_completeness="full"))
        detection.detection_detail["strip_completeness"] = "full"
        return detection

    if config.strip_completeness == "partial":
        return detect_partial_layout(gray, analysis_gray, image_width, image_height, config)

    full_config = replace(config, strip_completeness="full")
    full_detection = detect_layout(gray, analysis_gray, image_width, image_height, full_config)
    full_detection.detection_detail["strip_completeness"] = "full"
    if full_detection.confidence >= float(config.confidence_threshold):
        return full_detection

    try:
        partial_detection = detect_partial_layout(gray, analysis_gray, image_width, image_height, config, full_detection)
    except Exception as exc:
        full_detection.warnings.append(f"strip-completeness auto：full 未达阈值，partial 候选失败：{exc}")
        return full_detection

    if rank_layout_detection(partial_detection, config) > rank_layout_detection(full_detection, config):
        partial_detection.warnings.append(
            f"strip-completeness auto：full confidence={full_detection.confidence:.3f} 未达阈值，"
            f"采用 partial count={partial_detection.frames_per_lane} 候选。"
        )
        return partial_detection

    full_detection.analysis_candidate = {
        "selected": full_detection.analysis_candidate,
        "strip_completeness": "auto-full-kept",
        "partial_candidate": {
            "count": int(partial_detection.frames_per_lane),
            "confidence": float(partial_detection.confidence),
            "reasons": list(partial_detection.review_reasons),
        },
    }
    full_detection.warnings.append(
        f"strip-completeness auto：full confidence={full_detection.confidence:.3f} 未达阈值；"
        f"partial 最佳候选 count={partial_detection.frames_per_lane}, confidence={partial_detection.confidence:.3f}，未替换 full。"
    )
    return full_detection


def format_competition_candidates(config: SplitConfig) -> tuple[str, ...]:
    current = FILM_FORMATS[config.film_format]
    if current.family == "35mm":
        return ("135",)
    return ("120-645", "120-66", "120-67")


def format_switch_has_separator_evidence(format_name: str, detection: LayoutDetection) -> bool:
    profile = FILM_FORMATS[format_name]
    expected_gaps = max(0, int(profile.default_count) - 1)
    if expected_gaps <= 0:
        return True
    detail = detection.detection_detail
    reliable = int(detail.get("reliable_gaps", 0))
    equal = int(detail.get("equal_gaps", 0))
    required = max(1, min(expected_gaps, int(math.ceil(expected_gaps * 0.45))))
    return reliable >= required and equal <= max(1, expected_gaps - required)


def choose_auto_format_config(
    gray: np.ndarray,
    image_width: int,
    image_height: int,
    input_file: Path,
    config: SplitConfig,
) -> tuple[SplitConfig, list[str]]:
    if not bool(config.format_auto):
        return config, []
    if FILM_FORMATS[config.film_format].family == "35mm":
        return config, []

    candidates: list[tuple[str, str, float, LayoutDetection]] = []
    for format_name in format_competition_candidates(config):
        profile = FILM_FORMATS[format_name]
        try:
            layout = auto_layout_for_format(profile, input_file)
            candidate_config = replace(
                config,
                film_format=format_name,
                layout=layout,
                count=int(profile.default_count),
                strip_completeness="full",
                analysis_enhance="off",
                debug_analysis=False,
            )
            detection = detect_layout(gray, gray, image_width, image_height, candidate_config)
        except Exception:
            continue
        candidates.append((format_name, layout, float(detection.confidence), detection))

    if not candidates:
        return config, []

    current_item = next((item for item in candidates if item[0] == config.film_format), None)
    best = max(candidates, key=lambda item: (item[2], item[3].frames_per_lane))
    if current_item is None:
        current_confidence = 0.0
    else:
        current_confidence = float(current_item[2])

    best_name, best_layout, best_confidence, _best_detection = best
    if best_name == config.film_format:
        return config, []
    if not format_switch_has_separator_evidence(best_name, _best_detection):
        return config, []

    confidence_gain = best_confidence - current_confidence
    strong_best = best_confidence >= float(config.confidence_threshold)
    current_weak = current_confidence < float(config.confidence_threshold)
    if not (confidence_gain >= 0.12 and (strong_best or current_weak)):
        return config, []

    profile = FILM_FORMATS[best_name]
    new_config = replace(
        config,
        film_format=best_name,
        layout=best_layout,
        count=int(profile.default_count),
    )
    summary = ", ".join(f"{name}/{layout}={confidence:.3f}" for name, layout, confidence, _ in candidates)
    return new_config, [f"format auto：根据同家族 full 几何竞争，从 {config.film_format} 切换为 {best_name}；候选置信度：{summary}。"]


def process_one(input_file: Path, config: SplitConfig) -> ProcessResult:
    warnings: list[str] = []
    output_dir = output_directory_for(input_file, config)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tifffile.TiffFile(input_file) as tif:
        if len(tif.pages) == 0:
            raise RuntimeError("TIFF 中没有页面。")
        if len(tif.pages) > 1 and config.page == 0:
            warnings.append(f"源 TIFF 有 {len(tif.pages)} 页；默认只处理第 1 页。若需指定页，使用 --page。")
        if config.page < 0 or config.page >= len(tif.pages):
            raise RuntimeError(f"--page {config.page} 超出范围；源 TIFF 共 {len(tif.pages)} 页。")

        page = tif.pages[config.page]
        compression_code = enum_int(getattr(page, "compression", None), 1)
        compression_name = enum_name(getattr(page, "compression", None), "NONE")
        if compression_code != 1 and not has_imagecodecs():
            warnings.append(f"源文件使用 {compression_name} 压缩。若读取/写入失败，请安装 imagecodecs。")

        arr = page.asarray()
        axes = infer_axes(page, arr)
        profile = extract_profile(input_file, tif, page, arr, axes, config.copy_description)
        ensure_safe_bit_depth(profile, arr, config.allow_packed_bit_depth)

        height, width = spatial_size(arr, axes)
        gray = make_gray_u8(arr, axes, profile.bits_per_sample, profile.photometric)
        if gray.shape != (height, width):
            raise RuntimeError(f"检测灰度图尺寸 {gray.shape} 与 TIFF 空间尺寸 {(height, width)} 不一致。")

        analysis_gray = make_analysis_gray(gray, config)
        config, format_warnings = choose_auto_format_config(gray, width, height, input_file, config)
        warnings.extend(format_warnings)

        deskew_model: Optional[DeskewModel] = None
        if config.deskew != "off":
            estimated_model, deskew_warnings, deskew_source, deskew_target = choose_deskew_model_for_layout(gray, analysis_gray, config)
            warnings.extend(deskew_warnings)
            if estimated_model is not None:
                warnings.append(
                    f"deskew 已启用：使用 {deskew_source} 检测图，将源图旋转 {estimated_model.angle_degrees:.4f}° 至{deskew_target}，"
                    "再执行外框、分隔线、片距和同画幅尺寸检测。"
                )
                arr = rotate_array_yx_same_axes(
                    arr=arr,
                    axes=axes,
                    angle_degrees=estimated_model.angle_degrees,
                    interpolation=config.deskew_interpolation,
                    chunk_rows=config.deskew_chunk_rows,
                )
                height, width = spatial_size(arr, axes)
                gray = make_gray_u8(arr, axes, profile.bits_per_sample, profile.photometric)
                if gray.shape != (height, width):
                    raise RuntimeError(f"deskew 后检测灰度图尺寸 {gray.shape} 与 TIFF 空间尺寸 {(height, width)} 不一致。")
                analysis_gray = make_analysis_gray(gray, config)
                deskew_model = replace(estimated_model, output_width=int(width), output_height=int(height))
            elif config.deskew == "strict":
                warnings.append("deskew strict 未找到可信倾斜模型，本文件按不旋转流程处理。")

        layout_detection = detect_layout_with_completeness(gray, analysis_gray, width, height, config)
        warnings.extend(layout_detection.warnings)

        outer = layout_detection.outer
        gaps = layout_detection.gaps
        boxes = layout_detection.boxes
        outer_refine_model = layout_detection.outer_refine_model
        frame_size_model = layout_detection.frame_size_model
        analysis_candidate = layout_detection.analysis_candidate

        confidence = float(layout_detection.confidence)
        review_reasons = list(layout_detection.review_reasons)
        detection_detail = layout_detection.detection_detail
        status = "approved_auto" if confidence >= float(config.confidence_threshold) else "needs_review"
        review_copy: Optional[str] = None
        if status == "needs_review":
            warnings.append(
                f"低置信度：confidence={confidence:.3f} < threshold={config.confidence_threshold:.3f}；"
                f"reasons={','.join(review_reasons)}。"
            )
            if config.copy_review_files:
                copied = copy_file_for_review(input_file, review_directory_for(output_dir, config))
                review_copy = str(copied)
                warnings.append(f"已复制原文件到 review 文件夹：{copied}")

        if config.debug:
            debug_path = output_dir / "_debug" / f"{input_file.stem}_debug.jpg"
            save_debug_preview(gray, outer, boxes, gaps, debug_path)
            print(f"  debug: {debug_path}")
        if config.debug_analysis and config.analysis_enhance != "off":
            analysis_debug_path = output_dir / "_debug" / f"{input_file.stem}_analysis.jpg"
            save_analysis_debug(gray, analysis_gray, analysis_debug_path)
            print(f"  analysis-debug: {analysis_debug_path}")

        output_files: list[str] = []
        if config.dry_run:
            print("  dry-run: 不写出裁切 TIFF。")
        elif status == "needs_review" and not config.export_low_confidence:
            print(
                f"  needs-review: confidence={confidence:.3f} < {config.confidence_threshold:.3f}；"
                "跳过自动裁切。"
            )
        else:
            if status == "needs_review":
                print("  export-low-confidence: 已按用户要求输出低置信裁切结果。")
            for index, box in enumerate(boxes, 1):
                if not box.valid():
                    raise RuntimeError(f"第 {index} 张裁切框无效：{box}")

                cropped = np.ascontiguousarray(crop_yx(arr, axes, box))
                out_path = output_dir / f"{input_file.stem}_{index:02d}.tif"
                if out_path.exists() and not config.overwrite:
                    raise RuntimeError(f"输出文件已存在：{out_path}；如需覆盖，使用 --overwrite。")

                tmp_path = temp_tiff_path(out_path)
                if tmp_path.exists():
                    tmp_path.unlink()

                try:
                    tifffile.imwrite(tmp_path, cropped, **write_kwargs(profile, page, cropped, config))
                    validate_output(
                        out_path=tmp_path,
                        profile=profile,
                        source_page=page,
                        expected_shape=tuple(int(x) for x in cropped.shape),
                        expected_dtype=cropped.dtype,
                        require_same_compression=(config.compression == "same"),
                    )
                    os.replace(tmp_path, out_path)
                except Exception:
                    if tmp_path.exists():
                        tmp_path.unlink()
                    raise

                output_files.append(str(out_path))
                print(f"  → {out_path.name}  box=({box.left},{box.top},{box.right},{box.bottom})  shape={cropped.shape} dtype={cropped.dtype}")

    result = ProcessResult(
        source=str(input_file),
        film_format=str(config.film_format),
        layout=str(config.layout),
        strip_completeness=str(layout_detection.detection_detail.get("strip_completeness", config.strip_completeness)),
        lane_count=int(layout_detection.lane_count),
        frames_per_lane=int(layout_detection.frames_per_lane),
        status=status,
        confidence=float(confidence),
        review_reasons=review_reasons,
        review_copy=review_copy,
        output_files=output_files,
        outer_box=asdict(outer),
        frame_boxes=[asdict(box) for box in boxes],
        gaps=[asdict(gap) for gap in gaps],
        outer_refine_model=(json_safe(asdict(outer_refine_model)) if outer_refine_model is not None else None),
        deskew_model=(json_safe(asdict(deskew_model)) if deskew_model is not None else None),
        frame_size_model=(json_safe(asdict(frame_size_model)) if frame_size_model is not None else None),
        analysis_candidate=json_safe(analysis_candidate) if analysis_candidate is not None else None,
        detection_detail=json_safe(detection_detail),
        profile=json_safe(asdict(profile)),
        warnings=warnings,
    )

    if config.report:
        write_report(output_dir / "split_report.jsonl", result)
        write_summary_report(output_dir / "split_summary.csv", result)
    return result


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def iter_input_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() not in TIFF_SUFFIXES:
            raise RuntimeError(f"输入文件不是 TIFF：{path}")
        return [path]
    if path.is_dir():
        return [p for p in sorted(path.iterdir()) if p.is_file() and p.suffix.lower() in TIFF_SUFFIXES]
    raise RuntimeError(f"路径不存在：{path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "安全切分 X5 胶片长条 TIFF。默认 deskew=auto：高置信检测到倾斜时先几何校平，"
            "再执行稳定裁切；默认保位深/关键 TIFF 标签，不做色彩、反差、锐化等后期处理，"
            "并给每张四周保留 10px bleed。"
        )
    )
    parser.add_argument("input", nargs="?", default=".", help="输入 TIFF 文件或目录；默认当前目录。")
    parser.add_argument("-o", "--output", default=None, help="输出目录；默认 input 所在目录/split_output。")
    parser.add_argument("--format", choices=FORMAT_CHOICES, default="auto", help="胶片格式：135 / half / xpan / 120-645 / 120-66 / 120-67。默认 auto 只自动区分普通 135 和 120 家族；half/xpan 需手动指定。")
    parser.add_argument("--layout", choices=LAYOUT_CHOICES, default="auto", help="扫描布局：single-horizontal / single-vertical。默认 auto。")
    parser.add_argument("--strip-completeness", choices=("auto", "full", "partial"), default="auto", help="条带完整性：full=完整条按默认张数优先等距；partial=片头片尾/不满片夹，尝试允许张数候选；auto=先 full，高置信失败再 partial。默认 auto。")
    parser.add_argument("-n", "--count", type=int, default=None, help="每条胶片中的张数；默认按 --format 推导，例如 135=6、half=12、xpan=3、66=3、67=3、645=4。")
    parser.add_argument("--page", type=int, default=0, help="多页 TIFF 时处理第几页，从 0 开始；默认 0。")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    parser.add_argument("--deskew", choices=("off", "auto", "strict"), default="auto", help="先检测胶片条是否倾斜，若可信则先旋转校平再运行稳定检测裁切流程。off=关闭旋正；auto=高置信才启用；strict=更积极。默认 auto。")
    parser.add_argument("--deskew-interpolation", choices=("nearest", "bilinear"), default="bilinear", help="deskew 旋转插值。bilinear 更平滑；nearest 不插值但锯齿更明显。默认 bilinear。")
    parser.add_argument("--deskew-min-angle-deg", type=float, default=0.08, help="deskew 触发的最小角度，默认 0.08°。")
    parser.add_argument("--deskew-max-angle-deg", type=float, default=3.0, help="deskew 允许的最大角度，超过则跳过，默认 3.0°。")
    parser.add_argument("--deskew-min-span-px", type=int, default=5, help="整条胶片上下边缘倾斜跨度小于该像素数时认为近似水平，默认 5px。")
    parser.add_argument("--deskew-samples", type=int, default=32, help="deskew 横向采样点数量，默认 32。")
    parser.add_argument("--deskew-search-margin-ratio", type=float, default=0.14, help="deskew 在粗外框上下附近搜索胶片边缘的范围，以外框高度为单位，默认 0.14。")
    parser.add_argument("--deskew-sample-window-ratio", type=float, default=0.010, help="deskew 每个采样点的横向窗口宽度，以外框宽度为单位，默认 0.010。")
    parser.add_argument("--deskew-edge-min-strength", type=float, default=5.0, help="deskew 上下边缘最低强度，检测灰度单位，默认 5.0。")
    parser.add_argument("--deskew-line-tolerance-px", type=float, default=5.0, help="deskew 拟合上下边缘线的基础容差，默认 5px。")
    parser.add_argument("--deskew-max-slope-delta", type=float, default=0.006, help="deskew 上下边缘斜率最大允许差，默认 0.006。")
    parser.add_argument("--deskew-chunk-rows", type=int, default=64, help="deskew 旋转输出时每块处理多少行；内存紧张可降到 32，默认 64。")

    parser.add_argument("--analysis-enhance", choices=("off", "auto", "strict"), default="auto", help="检测专用增强分析层：off=关闭；auto=生成增强候选但只有评分更好才采用；strict=更积极用于极度欠曝片。默认 auto。")
    parser.add_argument("--analysis-percentile-low", type=float, default=0.4, help="检测增强 percentile 拉伸低位，默认 0.4。")
    parser.add_argument("--analysis-percentile-high", type=float, default=99.7, help="检测增强 percentile 拉伸高位，默认 99.7。")
    parser.add_argument("--analysis-shadow-gamma", type=float, default=0.45, help="检测增强暗部提升 gamma，小于 1 会提亮暗部，默认 0.45。")
    parser.add_argument("--analysis-edge-weight", type=float, default=0.20, help="检测增强边缘混合权重，默认 0.20。")
    parser.add_argument("--analysis-texture-weight", type=float, default=0.22, help="检测增强暗部纹理混合权重，默认 0.22。")
    parser.add_argument("--analysis-candidate-gain-ratio", type=float, default=0.08, help="auto 模式中增强候选相对 base 的最低评分增益比例，默认 0.08。")
    parser.add_argument("--analysis-no-preserve-gutter", action="store_true", help="关闭 v17 的检测增强混合保护：默认会保留短而低纹理的黑/白片间分隔条。")
    parser.add_argument("--analysis-gutter-extreme-ratio", type=float, default=0.82, help="检测增强混合中，判定一列接近黑/白分隔条的最低极端像素比例，默认 0.82。")
    parser.add_argument("--analysis-gutter-max-activity", type=float, default=0.44, help="检测增强混合中，保留为分隔条的最高活动/纹理分数，默认 0.44。")
    parser.add_argument("--analysis-gutter-max-width-ratio", type=float, default=0.075, help="检测增强混合中，允许保留为片间分隔条的最大连续宽度，以单帧宽度为单位，默认 0.075。")
    parser.add_argument("--analysis-no-geometry-select", action="store_true", help="关闭 v17 的几何稳定选择：默认在 base 分隔线很弱且画幅宽度不稳定时，可采用更规则的增强候选。")
    parser.add_argument("--analysis-geometry-min-base-cv", type=float, default=0.004, help="几何稳定选择触发所需的 base 画幅宽度变异系数，默认 0.004。")
    parser.add_argument("--analysis-no-fast-skip", dest="analysis_fast_skip", action="store_false", help="关闭 v17 的提速策略：即使 base 检测已经稳定，也继续运行增强候选检测管线。")
    parser.set_defaults(analysis_fast_skip=True)
    parser.add_argument("--analysis-edge-candidate", choices=("off", "auto", "always"), default="auto", help="增强边缘候选的运行策略：auto=只在 base/analysis 证据弱时运行；always=始终运行；off=关闭。默认 auto。")

    parser.add_argument("--black-thresh", type=int, default=30, help="检测用黑色阈值，0-255，默认 30。")
    parser.add_argument("--white-thresh", type=int, default=225, help="检测用白色阈值，0-255，默认 225。")
    parser.add_argument("--border-ratio", type=float, default=0.985, help="行/列黑或白背景像素比例达到多少才视为外边框，默认 0.985。")
    parser.add_argument("--border-min-run-frac", type=float, default=0.003, help="外框检测要求连续内容的最小比例，默认 0.003。")
    parser.add_argument("--outer-keep-margin", type=int, default=0, help="裁外框时额外保留像素，默认 0。")
    parser.add_argument("--no-outer-crop", action="store_true", help="关闭外框裁切；第一/最后一张欠曝边缘被误裁时可先测试。")
    parser.add_argument("--outer-x-detect", choices=("auto", "bw", "white"), default="auto", help="初始外框左右检测策略：bw=黑/白都当边框；white=左右只去白边保护黑色欠曝帧；auto=两者评分选择。默认 auto。")
    parser.add_argument("--outer-x-auto-min-gain-ratio", type=float, default=0.06, help="auto 选择 white-x 候选时，候选宽度至少比 bw 候选大多少才视为有保护价值，默认 0.06。")
    parser.add_argument("--outer-x-auto-max-expand-ratio", type=float, default=1.80, help="auto 中 white-x 候选相对 bw 候选的最大允许宽度，默认 1.80。")
    parser.add_argument("--outer-refine", choices=("off", "auto", "strict"), default="auto", help="横向外框校正：用可靠内部分隔线反推 boundary 0 和 boundary N。auto=保守启用；strict=更积极；off=关闭。默认 auto。")
    parser.add_argument("--outer-refine-min-inliers", type=int, default=2, help="outer-refine 至少需要多少条可靠内部分隔线，默认 2。")
    parser.add_argument("--outer-refine-tolerance-ratio", type=float, default=0.070, help="outer-refine 拟合容差，以单帧宽度为单位，默认 0.070。")
    parser.add_argument("--outer-refine-pitch-tolerance-ratio", type=float, default=0.30, help="outer-refine 片距相对当前等分宽度允许偏离比例，默认 0.30。")
    parser.add_argument("--outer-refine-max-shift-ratio", type=float, default=0.35, help="outer-refine 单侧最大修正量，以拟合片距为单位，默认 0.35。")
    parser.add_argument("--outer-refine-max-width-change-ratio", type=float, default=0.22, help="outer-refine 外框宽度最大变化比例，默认 0.22。")
    parser.add_argument("--outer-refine-min-shift-px", type=int, default=3, help="outer-refine 小于多少像素的修正忽略，默认 3。")
    parser.add_argument("--outer-refine-iterations", type=int, default=1, help="outer-refine 迭代次数；每次修正外框后会重新检测内部分隔线，默认 1。")

    # Backward-compatible aliases from earlier X5_Split versions. They are hidden from --help
    # but keep older command lines such as --outer-fit strict working.
    parser.add_argument("--outer-fit", choices=("off", "auto", "strict"), default=None, help=argparse.SUPPRESS)
    parser.add_argument("--no-outer-fit-second-pass", action="store_true", help=argparse.SUPPRESS)

    parser.add_argument("--equal-split", action="store_true", help="强制在裁掉外框后按 count 等分，不检测内部分隔带。")
    parser.add_argument("--search-ratio", type=float, default=0.16, help="在理论分隔位置左右搜索范围，以单帧宽度为单位，默认 0.16。")
    parser.add_argument("--min-gap-score", type=float, default=0.70, help="内部分隔带最低可信分数，默认 0.70。欠曝误判时可升到 0.78~0.85。")
    parser.add_argument("--min-gap-prominence", type=float, default=0.12, help="候选分隔带相对两侧邻域最低突出度，默认 0.12。")
    parser.add_argument("--max-gap-ratio", type=float, default=0.045, help="候选分隔带最大宽度，以单帧宽度为单位，默认 0.045。")
    parser.add_argument("--min-gap-ratio", type=float, default=0.001, help="候选分隔带最小宽度，以单帧宽度为单位，默认 0.001。")
    parser.add_argument("--side-guard-ratio", type=float, default=0.035, help="候选分隔带两侧护栏宽度，以单帧宽度为单位，默认 0.035。")
    parser.add_argument("--vertical-slices", type=int, default=5, help="纵向切成多少段检查分隔带贯穿性，默认 5。")
    parser.add_argument("--center-y0", type=float, default=0.10, help="分隔带检测只看中部区域的起始高度比例，默认 0.10。")
    parser.add_argument("--center-y1", type=float, default=0.90, help="分隔带检测只看中部区域的结束高度比例，默认 0.90。")
    parser.add_argument("--allow-peak-fallback", action="store_true", help="危险选项：可疑时允许追随局部黑/白峰值。默认关闭。")

    parser.add_argument("--edge-refine", action="store_true", help="可选：用真实画幅竖向边缘微调切线。默认关闭，以避免影响常规片。")
    parser.add_argument("--edge-refine-single", choices=("none", "learned"), default="none", help="edge-refine 后是否用已学到的片间距修正单边可见的画幅边缘；默认 none。")
    parser.add_argument("--leader-mode", action="store_true", help="兼容旧参数：等同于 --strip-completeness partial，并启用 --edge-refine --edge-refine-single learned。")
    # Compatibility no-op switches from X5_Split_v14-v16. They are accepted so old
    # command lines do not fail, but v17 intentionally removes these slow multi-pass
    # refiners from the default code path.
    parser.add_argument("--side-refine", choices=("off", "auto", "strict"), default=None, help=argparse.SUPPRESS)
    parser.add_argument("--side-refine-single", choices=("none", "learned"), default=None, help=argparse.SUPPRESS)
    parser.add_argument("--partial-edge-refine", choices=("off", "auto", "strict"), default=None, help=argparse.SUPPRESS)
    parser.add_argument("--partial-edge-single", choices=("none", "learned"), default=None, help=argparse.SUPPRESS)
    parser.add_argument("--partial-side-complete", choices=("off", "auto", "strict"), default=None, help=argparse.SUPPRESS)
    parser.add_argument("--partial-outer-refine", choices=("off", "auto", "strict"), default=None, help=argparse.SUPPRESS)
    parser.add_argument("--edge-search-ratio", type=float, default=0.14, help="edge-refine 搜索窗口，以单帧宽度为单位，默认 0.14。")
    parser.add_argument("--edge-min-strength", type=float, default=0.30, help="edge-refine 竖向边缘最低强度，0~1，默认 0.30。")
    parser.add_argument("--edge-min-bg-ratio", type=float, default=0.58, help="edge-refine 判断片间黑/白背景区域的最低比例，默认 0.58。")
    parser.add_argument("--edge-max-gutter-ratio", type=float, default=0.18, help="edge-refine 两个画幅边缘之间最大间隔，以单帧宽度为单位，默认 0.18。")
    parser.add_argument("--edge-min-gutter-px", type=int, default=4, help="edge-refine 两个画幅边缘之间最小间隔，默认 4px。")

    parser.add_argument("--grid-fit", choices=("off", "auto", "strict"), default="auto", help="全局片距校正：auto=只替换等分回退和明显离群切线；strict=更积极校正单边边缘；off=关闭。默认 auto。")
    parser.add_argument("--grid-min-inliers", type=int, default=3, help="拟合全局片距至少需要多少条可靠分隔线，默认 3。特殊样本可降到 2。")
    parser.add_argument("--grid-tolerance-ratio", type=float, default=0.075, help="全局片距拟合/替换容差，以单帧宽度为单位，默认 0.075。")
    parser.add_argument("--grid-pitch-tolerance-ratio", type=float, default=0.22, help="全局片距相对等分宽度允许偏离比例，默认 0.22。")
    parser.add_argument("--grid-min-replace-px", type=int, default=10, help="全局片距校正最小替换偏差像素，默认 10。")

    parser.add_argument("--frame-size-fit", choices=("off", "auto", "strict"), default="auto", help="同画幅尺寸校正：利用 135 单张画幅尺寸一致的先验修正细微错位。auto=保守启用；strict=更强约束；off=关闭。默认 auto。")
    parser.add_argument("--frame-size-min-samples", type=int, default=2, help="学习共同画幅宽度至少需要多少个清晰样本帧，默认 2；极端样本可用 1。")
    parser.add_argument("--frame-size-tolerance-ratio", type=float, default=0.035, help="同画幅尺寸校正容差，以画幅宽度为单位，默认 0.035。想更积极可降到 0.02。")
    parser.add_argument("--frame-size-min-ratio", type=float, default=0.72, help="共同画幅宽度相对等分宽度的最小合理比例，默认 0.72。")
    parser.add_argument("--frame-size-max-ratio", type=float, default=1.10, help="共同画幅宽度相对等分宽度的最大合理比例，默认 1.10。")
    parser.add_argument("--frame-size-base-weight", type=float, default=0.18, help="同画幅尺寸校正中基础框位置的保守权重，默认 0.18。越小越相信真实边缘。")

    parser.add_argument("--bleed", type=int, default=10, help="每张输出图上下左右额外保留像素；默认 10。")
    parser.add_argument("--bleed-x", type=int, default=None, help="单独设置左右额外保留像素；默认跟随 --bleed。")
    parser.add_argument("--bleed-y", type=int, default=None, help="单独设置上下额外保留像素；默认跟随 --bleed。")
    parser.add_argument(
        "--gap-crop-mode",
        choices=("center", "fixed", "detected"),
        default="center",
        help="内部分隔条处理方式：center=只按中心切线，最安全；fixed=中心左右固定去边；detected=删除检测整条分隔带，风险较高。默认 center。",
    )
    parser.add_argument("--gap-trim-px", type=int, default=0, help="--gap-crop-mode fixed 时，中心左右各去掉多少像素，默认 0。")

    parser.add_argument("--compression", choices=("same", "none", "lzw", "deflate", "zstd"), default="same", help="输出压缩方式。same=沿用源文件无损压缩；none=未压缩。默认 same。")
    parser.add_argument("--allow-lossy-compression", action="store_true", help="允许重新写出 JPEG/WebP/JPEG2000/LERC 等有损或疑似有损压缩。默认拒绝。")
    parser.add_argument("--allow-packed-bit-depth", action="store_true", help="允许处理 BitsPerSample 与 numpy dtype 位数不一致的 packed TIFF。默认拒绝。")
    parser.add_argument("--extra-tags", choices=("none", "safe", "all"), default="safe", help="复制非结构性附加 TIFF 标签。safe=保守复制；none=不复制；all=尽量复制。默认 safe。")
    parser.add_argument("--copy-description", choices=("auto", "yes", "no"), default="auto", help="是否复制 ImageDescription。auto 会跳过 OME/ImageJ 等含尺寸信息的描述。默认 auto。")
    parser.add_argument("--preserve-tiling", action="store_true", help="源 TIFF 为 tiled 时尝试保留 tile 尺寸。默认改用 strip 写出，更兼容。")

    parser.add_argument("--confidence-threshold", type=float, default=0.85, help="自动裁切最低置信度阈值，低于该值默认只标记为 needs_review，不写裁切 TIFF。默认 0.85。")
    parser.add_argument("--review-dir", default=None, help="低置信原文件复制目录；默认输出目录/needs_review。仅配合 --copy-review-files 使用。")
    parser.add_argument("--copy-review-files", action="store_true", help="低置信文件复制到 review 目录，方便后续人工或专用脚本处理。默认不复制，避免批量复制大 TIFF。")
    parser.add_argument("--export-low-confidence", action="store_true", help="即使检测低于置信度阈值也继续导出裁切 TIFF。默认低置信只写 debug/report。")

    parser.add_argument("--debug", action="store_true", help="输出绿色外框、蓝色输出框、红色分隔线 debug JPG 到 split_output/_debug。")
    parser.add_argument("--debug-analysis", action="store_true", help="额外输出 base / enhanced 检测分析图，便于检查欠曝图增强效果。")
    parser.add_argument("--dry-run", action="store_true", help="只检测并生成 debug/report，不写裁切 TIFF。")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已存在的输出文件。")
    parser.add_argument("--report", action="store_true", help="写 split_report.jsonl，记录裁切框和源 TIFF 关键属性。")
    return parser


def tiff_spatial_size_for_path(input_path: Path) -> tuple[int, int]:
    try:
        with tifffile.TiffFile(input_path) as tif:
            page = tif.pages[0]
            shape = tuple(page.shape)
            if len(shape) < 2:
                return 1, 1
            height, width = int(shape[0]), int(shape[1])
    except Exception:
        return 1, 1
    return width, height


def holder_long_short_ratio(width: int, height: int) -> float:
    return float(max(width, height)) / max(1.0, float(min(width, height)))


def infer_format_from_holder(width: int, height: int) -> FilmFormatProfile:
    ratio = holder_long_short_ratio(width, height)

    # X5 holder geometry is the most stable signal here. 35mm holders are much
    # narrower/longer than 120 holders; DPI changes scale both axes together.
    if ratio >= 6.0:
        return FILM_FORMATS["135"]

    # 120 holders are wider/shorter. These thresholds are intentionally broad
    # because holder margins and partial strips shift the ideal frame math.
    if ratio >= 4.45:
        return FILM_FORMATS["120-645"]
    if ratio >= 3.70:
        return FILM_FORMATS["120-67"]
    return FILM_FORMATS["120-66"]


def resolve_film_format(format_name: str, input_path: Path) -> FilmFormatProfile:
    if format_name == "auto":
        width, height = tiff_spatial_size_for_path(input_path)
        return infer_format_from_holder(width, height)
    return FILM_FORMATS[str(format_name)]


def auto_layout_for_format(profile: FilmFormatProfile, input_path: Path) -> str:
    width, height = tiff_spatial_size_for_path(input_path)
    aspect = float(width) / max(1.0, float(height))
    return "single-horizontal" if aspect >= 1.0 else "single-vertical"


def resolve_layout(layout: str, profile: FilmFormatProfile, input_path: Path) -> str:
    return auto_layout_for_format(profile, input_path) if layout == "auto" else str(layout)


def resolve_strip_completeness(strip_completeness: str, profile: FilmFormatProfile, leader_mode: bool) -> str:
    if leader_mode:
        return "partial"
    return str(strip_completeness)


def config_from_args(args: argparse.Namespace) -> SplitConfig:
    input_path = Path(args.input).expanduser().resolve()
    profile = resolve_film_format(str(args.format), input_path)
    strip_completeness = resolve_strip_completeness(str(args.strip_completeness), profile, bool(args.leader_mode))
    count = int(profile.default_count if args.count is None else args.count)
    if count < 1:
        raise ValueError("--count 必须大于等于 1。")
    if count not in profile.allowed_counts:
        allowed = ", ".join(str(x) for x in profile.allowed_counts)
        raise ValueError(f"--format {profile.name} 允许的 --count 为：{allowed}。")
    layout = resolve_layout(str(args.layout), profile, input_path)

    bleed_x = int(args.bleed if args.bleed_x is None else args.bleed_x)
    bleed_y = int(args.bleed if args.bleed_y is None else args.bleed_y)
    if bleed_x < 0 or bleed_y < 0:
        raise ValueError("--bleed / --bleed-x / --bleed-y 不能为负数。")
    if int(args.page) < 0:
        raise ValueError("--page 不能为负数。")
    if float(args.deskew_min_angle_deg) < 0 or float(args.deskew_max_angle_deg) <= 0:
        raise ValueError("--deskew-min-angle-deg 不能为负，--deskew-max-angle-deg 必须大于 0。")
    if float(args.deskew_min_angle_deg) > float(args.deskew_max_angle_deg):
        raise ValueError("--deskew-min-angle-deg 不能大于 --deskew-max-angle-deg。")
    if int(args.deskew_min_span_px) < 0:
        raise ValueError("--deskew-min-span-px 不能为负数。")
    if int(args.deskew_samples) < 6:
        raise ValueError("--deskew-samples 必须大于等于 6。")
    if float(args.deskew_search_margin_ratio) <= 0 or float(args.deskew_sample_window_ratio) <= 0:
        raise ValueError("--deskew-search-margin-ratio 和 --deskew-sample-window-ratio 必须大于 0。")
    if float(args.deskew_edge_min_strength) < 0 or float(args.deskew_line_tolerance_px) <= 0:
        raise ValueError("--deskew-edge-min-strength 不能为负，--deskew-line-tolerance-px 必须大于 0。")
    if float(args.deskew_max_slope_delta) <= 0:
        raise ValueError("--deskew-max-slope-delta 必须大于 0。")
    if int(args.deskew_chunk_rows) < 8:
        raise ValueError("--deskew-chunk-rows 必须大于等于 8。")
    if not (0.0 <= float(args.analysis_percentile_low) < float(args.analysis_percentile_high) <= 100.0):
        raise ValueError("必须满足 0 <= --analysis-percentile-low < --analysis-percentile-high <= 100。")
    if float(args.analysis_shadow_gamma) <= 0:
        raise ValueError("--analysis-shadow-gamma 必须大于 0。")
    if not (0.0 <= float(args.analysis_edge_weight) <= 1.0):
        raise ValueError("--analysis-edge-weight 必须在 0~1 之间。")
    if not (0.0 <= float(args.analysis_texture_weight) <= 1.0):
        raise ValueError("--analysis-texture-weight 必须在 0~1 之间。")
    if float(args.analysis_candidate_gain_ratio) < 0:
        raise ValueError("--analysis-candidate-gain-ratio 不能为负数。")
    if not (0.0 <= float(args.analysis_gutter_extreme_ratio) <= 1.0):
        raise ValueError("--analysis-gutter-extreme-ratio 必须在 0~1 之间。")
    if not (0.0 <= float(args.analysis_gutter_max_activity) <= 1.0):
        raise ValueError("--analysis-gutter-max-activity 必须在 0~1 之间。")
    if float(args.analysis_gutter_max_width_ratio) <= 0:
        raise ValueError("--analysis-gutter-max-width-ratio 必须大于 0。")
    if float(args.analysis_geometry_min_base_cv) < 0:
        raise ValueError("--analysis-geometry-min-base-cv 不能为负数。")
    if str(args.analysis_edge_candidate) not in {"off", "auto", "always"}:
        raise ValueError("--analysis-edge-candidate 必须是 off / auto / always。")
    if int(args.outer_keep_margin) < 0:
        raise ValueError("--outer-keep-margin 不能为负数。")
    if int(args.gap_trim_px) < 0:
        raise ValueError("--gap-trim-px 不能为负数。")

    if not (0 <= args.black_thresh <= 255 and 0 <= args.white_thresh <= 255):
        raise ValueError("--black-thresh 和 --white-thresh 必须在 0~255 之间。")
    if args.black_thresh >= args.white_thresh:
        raise ValueError("--black-thresh 必须小于 --white-thresh。")
    if not (0.0 < float(args.border_ratio) <= 1.0):
        raise ValueError("--border-ratio 必须在 (0, 1] 之间。")
    if float(args.border_min_run_frac) <= 0:
        raise ValueError("--border-min-run-frac 必须大于 0。")
    if float(args.search_ratio) <= 0:
        raise ValueError("--search-ratio 必须大于 0。")
    if not (0.0 <= float(args.min_gap_score) <= 1.5):
        raise ValueError("--min-gap-score 建议在 0~1.5 之间。")
    if float(args.min_gap_prominence) < 0:
        raise ValueError("--min-gap-prominence 不能为负数。")
    if float(args.min_gap_ratio) < 0 or float(args.max_gap_ratio) <= 0 or float(args.min_gap_ratio) > float(args.max_gap_ratio):
        raise ValueError("必须满足 0 <= --min-gap-ratio <= --max-gap-ratio，且 --max-gap-ratio > 0。")
    if float(args.side_guard_ratio) <= 0:
        raise ValueError("--side-guard-ratio 必须大于 0。")
    if int(args.vertical_slices) < 1:
        raise ValueError("--vertical-slices 必须大于等于 1。")
    if args.outer_x_auto_min_gain_ratio < 0:
        raise ValueError("--outer-x-auto-min-gain-ratio 不能为负数。")
    if args.outer_x_auto_max_expand_ratio <= 1.0:
        raise ValueError("--outer-x-auto-max-expand-ratio 必须大于 1。")
    if args.outer_refine_min_inliers < 2:
        raise ValueError("--outer-refine-min-inliers 必须大于等于 2。")
    if args.outer_refine_tolerance_ratio <= 0 or args.outer_refine_pitch_tolerance_ratio <= 0:
        raise ValueError("--outer-refine-tolerance-ratio 和 --outer-refine-pitch-tolerance-ratio 必须大于 0。")
    if args.outer_refine_max_shift_ratio <= 0 or args.outer_refine_max_width_change_ratio <= 0:
        raise ValueError("--outer-refine-max-shift-ratio 和 --outer-refine-max-width-change-ratio 必须大于 0。")
    if args.outer_refine_min_shift_px < 0 or args.outer_refine_iterations < 0:
        raise ValueError("--outer-refine-min-shift-px 和 --outer-refine-iterations 不能为负数。")
    if not (0.0 <= args.center_y0 < args.center_y1 <= 1.0):
        raise ValueError("必须满足 0 <= --center-y0 < --center-y1 <= 1。")
    if args.edge_search_ratio <= 0 or args.edge_max_gutter_ratio <= 0:
        raise ValueError("--edge-search-ratio 和 --edge-max-gutter-ratio 必须大于 0。")
    if args.edge_min_gutter_px < 1:
        raise ValueError("--edge-min-gutter-px 必须大于等于 1。")
    if not (0.0 <= float(args.edge_min_strength) <= 1.5):
        raise ValueError("--edge-min-strength 建议在 0~1.5 之间。")
    if not (0.0 <= float(args.edge_min_bg_ratio) <= 1.0):
        raise ValueError("--edge-min-bg-ratio 必须在 0~1 之间。")
    if args.grid_min_inliers < 2:
        raise ValueError("--grid-min-inliers 必须大于等于 2。")
    if args.grid_tolerance_ratio <= 0 or args.grid_pitch_tolerance_ratio <= 0:
        raise ValueError("--grid-tolerance-ratio 和 --grid-pitch-tolerance-ratio 必须大于 0。")
    if args.grid_min_replace_px < 0:
        raise ValueError("--grid-min-replace-px 不能为负数。")
    if args.frame_size_min_samples < 1:
        raise ValueError("--frame-size-min-samples 必须大于等于 1。")
    if args.frame_size_tolerance_ratio <= 0:
        raise ValueError("--frame-size-tolerance-ratio 必须大于 0。")
    if not (0 < args.frame_size_min_ratio < args.frame_size_max_ratio):
        raise ValueError("必须满足 0 < --frame-size-min-ratio < --frame-size-max-ratio。")
    if args.frame_size_base_weight < 0:
        raise ValueError("--frame-size-base-weight 不能为负数。")
    if not (0.0 <= float(args.confidence_threshold) <= 1.0):
        raise ValueError("--confidence-threshold 必须在 0~1 之间。")

    return SplitConfig(
        input_path=input_path,
        output=Path(args.output).expanduser().resolve() if args.output else None,
        film_format=str(profile.name),
        format_auto=(str(args.format) == "auto"),
        layout=layout,
        strip_completeness=strip_completeness,
        count=count,
        page=int(args.page),
        deskew=str(args.deskew),
        deskew_interpolation=str(args.deskew_interpolation),
        deskew_min_angle_deg=float(args.deskew_min_angle_deg),
        deskew_max_angle_deg=float(args.deskew_max_angle_deg),
        deskew_min_span_px=int(args.deskew_min_span_px),
        deskew_samples=int(args.deskew_samples),
        deskew_search_margin_ratio=float(args.deskew_search_margin_ratio),
        deskew_sample_window_ratio=float(args.deskew_sample_window_ratio),
        deskew_edge_min_strength=float(args.deskew_edge_min_strength),
        deskew_line_tolerance_px=float(args.deskew_line_tolerance_px),
        deskew_max_slope_delta=float(args.deskew_max_slope_delta),
        deskew_chunk_rows=int(args.deskew_chunk_rows),
        analysis_enhance=str(args.analysis_enhance),
        analysis_percentile_low=float(args.analysis_percentile_low),
        analysis_percentile_high=float(args.analysis_percentile_high),
        analysis_shadow_gamma=float(args.analysis_shadow_gamma),
        analysis_edge_weight=float(args.analysis_edge_weight),
        analysis_texture_weight=float(args.analysis_texture_weight),
        analysis_candidate_gain_ratio=float(args.analysis_candidate_gain_ratio),
        analysis_preserve_gutter=not bool(args.analysis_no_preserve_gutter),
        analysis_gutter_extreme_ratio=float(args.analysis_gutter_extreme_ratio),
        analysis_gutter_max_activity=float(args.analysis_gutter_max_activity),
        analysis_gutter_max_width_ratio=float(args.analysis_gutter_max_width_ratio),
        analysis_geometry_select=not bool(args.analysis_no_geometry_select),
        analysis_geometry_min_base_cv=float(args.analysis_geometry_min_base_cv),
        analysis_fast_skip=bool(args.analysis_fast_skip),
        analysis_edge_candidate=str(args.analysis_edge_candidate),
        debug_analysis=bool(args.debug_analysis),
        black_thresh=int(args.black_thresh),
        white_thresh=int(args.white_thresh),
        border_ratio=float(args.border_ratio),
        border_min_run_frac=float(args.border_min_run_frac),
        outer_keep_margin=int(args.outer_keep_margin),
        no_outer_crop=bool(args.no_outer_crop),
        outer_x_detect=str(args.outer_x_detect),
        outer_x_auto_min_gain_ratio=float(args.outer_x_auto_min_gain_ratio),
        outer_x_auto_max_expand_ratio=float(args.outer_x_auto_max_expand_ratio),
        outer_refine=str(args.outer_fit if args.outer_fit is not None else args.outer_refine),
        outer_refine_min_inliers=int(args.outer_refine_min_inliers),
        outer_refine_tolerance_ratio=float(args.outer_refine_tolerance_ratio),
        outer_refine_pitch_tolerance_ratio=float(args.outer_refine_pitch_tolerance_ratio),
        outer_refine_max_shift_ratio=float(args.outer_refine_max_shift_ratio),
        outer_refine_max_width_change_ratio=float(args.outer_refine_max_width_change_ratio),
        outer_refine_min_shift_px=int(args.outer_refine_min_shift_px),
        outer_refine_iterations=(1 if bool(args.no_outer_fit_second_pass) else int(args.outer_refine_iterations)),
        equal_split=bool(args.equal_split),
        search_ratio=float(args.search_ratio),
        min_gap_score=float(args.min_gap_score),
        min_gap_prominence=float(args.min_gap_prominence),
        max_gap_ratio=float(args.max_gap_ratio),
        min_gap_ratio=float(args.min_gap_ratio),
        side_guard_ratio=float(args.side_guard_ratio),
        vertical_slices=int(args.vertical_slices),
        center_y0=float(args.center_y0),
        center_y1=float(args.center_y1),
        allow_peak_fallback=bool(args.allow_peak_fallback),
        edge_refine=bool(args.edge_refine or args.leader_mode),
        edge_refine_single=("learned" if args.leader_mode and args.edge_refine_single == "none" else str(args.edge_refine_single)),
        edge_search_ratio=float(args.edge_search_ratio),
        edge_min_strength=float(args.edge_min_strength),
        edge_min_bg_ratio=float(args.edge_min_bg_ratio),
        edge_max_gutter_ratio=float(args.edge_max_gutter_ratio),
        edge_min_gutter_px=int(args.edge_min_gutter_px),
        grid_fit=str(args.grid_fit),
        grid_min_inliers=int(args.grid_min_inliers),
        grid_tolerance_ratio=float(args.grid_tolerance_ratio),
        grid_pitch_tolerance_ratio=float(args.grid_pitch_tolerance_ratio),
        grid_min_replace_px=int(args.grid_min_replace_px),
        frame_size_fit=str(args.frame_size_fit),
        frame_size_min_samples=int(args.frame_size_min_samples),
        frame_size_tolerance_ratio=float(args.frame_size_tolerance_ratio),
        frame_size_min_ratio=float(args.frame_size_min_ratio),
        frame_size_max_ratio=float(args.frame_size_max_ratio),
        frame_size_base_weight=float(args.frame_size_base_weight),
        bleed_x=bleed_x,
        bleed_y=bleed_y,
        gap_crop_mode=str(args.gap_crop_mode),
        gap_trim_px=int(args.gap_trim_px),
        compression=str(args.compression),
        allow_lossy_compression=bool(args.allow_lossy_compression),
        allow_packed_bit_depth=bool(args.allow_packed_bit_depth),
        extra_tags=str(args.extra_tags),
        copy_description=str(args.copy_description),
        preserve_tiling=bool(args.preserve_tiling),
        confidence_threshold=float(args.confidence_threshold),
        review_dir=Path(args.review_dir).expanduser().resolve() if args.review_dir else None,
        copy_review_files=bool(args.copy_review_files),
        export_low_confidence=bool(args.export_low_confidence),
        debug=bool(args.debug),
        dry_run=bool(args.dry_run),
        overwrite=bool(args.overwrite),
        report=bool(args.report),
    )


def main() -> int:
    parser = build_parser()
    try:
        config = config_from_args(parser.parse_args())
        files = iter_input_files(config.input_path)
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    if not files:
        print(f"未找到 TIFF 文件：{config.input_path}", file=sys.stderr)
        return 2

    default_output = config.output if config.output else (config.input_path if config.input_path.is_dir() else config.input_path.parent) / "split_output"
    print(f"{SCRIPT_NAME} 版本：{VERSION}")
    print(f"输入：{config.input_path}")
    print(f"文件数：{len(files)}")
    print(f"输出：{default_output}")
    print(f"依赖：tifffile={getattr(tifffile, '__version__', 'unknown')}  imagecodecs={'yes' if has_imagecodecs() else 'no'}")
    print(f"格式：{config.film_format}；布局：{config.layout}；完整性：{config.strip_completeness}；每条张数：{config.count}")
    print(f"安全 bleed：左右 {config.bleed_x}px，上下 {config.bleed_y}px")
    print(f"deskew：{config.deskew}；默认 auto，高置信倾斜时会先几何校平；可用 --deskew off 关闭")
    print(f"检测增强 analysis-enhance：{config.analysis_enhance}；hybrid_gutter={config.analysis_preserve_gutter}；geometry_select={config.analysis_geometry_select}")
    print(f"初始外框左右策略：{config.outer_x_detect}")
    print(f"横向外框校正：{config.outer_refine}；min_inliers={config.outer_refine_min_inliers}；iterations={config.outer_refine_iterations}")
    print(f"全局片距校正：{config.grid_fit}；min_inliers={config.grid_min_inliers}；tolerance={config.grid_tolerance_ratio}")
    print(f"同画幅尺寸校正：{config.frame_size_fit}；min_samples={config.frame_size_min_samples}；tolerance={config.frame_size_tolerance_ratio}")
    print(f"自动裁切置信度阈值：{config.confidence_threshold:.2f}；低置信默认标记 needs_review 并跳过导出")
    if config.edge_refine:
        print(f"edge-refine：开启；single={config.edge_refine_single}；适合片头/片尾/空白帧特殊场景")

    ok = 0
    fail = 0
    approved = 0
    review = 0
    for file in files:
        print(f"\n[{file.name}]")
        try:
            result = process_one(file, config)
            print(f"  status: {result.status}  confidence={result.confidence:.3f}")
            for warning in result.warnings:
                print(f"  警告：{warning}")
            if result.status == "approved_auto":
                approved += 1
            elif result.status == "needs_review":
                review += 1
            ok += 1
        except Exception as exc:
            fail += 1
            print(f"  ✗ 失败：{exc}", file=sys.stderr)
            if os.environ.get(TRACEBACK_ENV) == "1" or os.environ.get("SPLIT_TIFF_TRACEBACK") == "1":
                traceback.print_exc()

    print(f"\n完成：成功 {ok}，失败 {fail}")
    print(f"自动通过：{approved}，待复核：{review}")
    print(f"输出目录：{default_output}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
