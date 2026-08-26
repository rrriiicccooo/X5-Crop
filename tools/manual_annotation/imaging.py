"""Bounded TIFF decoding, previews, native tiles, and review rendering."""

from __future__ import annotations

from contextlib import AbstractContextManager
import hashlib
import io
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import tifffile
from PIL import Image, ImageDraw

from x5crop.io.orientation import OrientationMapping, orientation_mapping

from .model import frame_polygons_display, raw_to_display_point


MAX_ANALYSIS_LONG_SIDE = 3600
MAX_PREVIEW_LONG_SIDE = 2400
MAX_NATIVE_TILE_SIDE = 768


class ImagingError(RuntimeError):
    """Raised when a source is not a supported single-raster TIFF."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_raster(array: np.ndarray, axes: str, path: Path) -> np.ndarray:
    array = np.squeeze(array)
    normalized_axes = axes.replace("Q", "").replace("I", "")
    if array.ndim == 2:
        return array[..., None]
    if array.ndim != 3:
        raise ImagingError(f"unsupported TIFF raster shape for {path}: {array.shape}")
    if normalized_axes in {"SYX", "CYX"} or (
        array.shape[0] in {1, 2, 3, 4}
        and array.shape[-1] not in {1, 2, 3, 4}
    ):
        array = np.moveaxis(array, 0, -1)
    if array.shape[-1] not in {1, 2, 3, 4}:
        raise ImagingError(
            f"unsupported TIFF channel structure for {path}: {array.shape}"
        )
    if array.dtype.kind not in {"u", "i", "f"}:
        raise ImagingError(f"unsupported TIFF dtype for {path}: {array.dtype}")
    return array


def _canonical_view(raw: np.ndarray, orientation: int) -> np.ndarray:
    if orientation == 1:
        return raw
    if orientation == 2:
        return np.flip(raw, axis=1)
    if orientation == 3:
        return np.flip(raw, axis=(0, 1))
    if orientation == 4:
        return np.flip(raw, axis=0)
    if orientation == 5:
        return np.swapaxes(raw, 0, 1)
    if orientation == 6:
        return np.rot90(raw, k=3, axes=(0, 1))
    if orientation == 7:
        return np.flip(np.swapaxes(raw, 0, 1), axis=(0, 1))
    if orientation == 8:
        return np.rot90(raw, k=1, axes=(0, 1))
    raise ImagingError(f"unsupported TIFF Orientation: {orientation}")


def _sample_indices(length: int, target: int) -> np.ndarray:
    if target >= length:
        return np.arange(length, dtype=np.int64)
    return np.rint(np.linspace(0, length - 1, target)).astype(np.int64)


def bounded_sample(view: np.ndarray, maximum_long_side: int) -> np.ndarray:
    height, width = view.shape[:2]
    scale = min(1.0, maximum_long_side / max(height, width))
    out_height = max(2, int(round(height * scale)))
    out_width = max(2, int(round(width * scale)))
    y_indices = _sample_indices(height, out_height)
    x_indices = _sample_indices(width, out_width)
    return np.asarray(view[y_indices][:, x_indices])


def display_levels(sample: np.ndarray) -> list[list[float]]:
    channels = sample.shape[-1]
    levels: list[list[float]] = []
    for channel in range(min(channels, 3)):
        values = sample[..., channel].astype(np.float64, copy=False)
        low, high = np.quantile(values, (0.002, 0.998))
        if not math.isfinite(low) or not math.isfinite(high) or high <= low:
            low = float(np.min(values))
            high = float(np.max(values))
        if high <= low:
            high = low + 1.0
        levels.append([float(low), float(high)])
    if channels == 1:
        levels *= 3
    return levels


def raster_to_rgb8(
    raster: np.ndarray,
    levels: list[list[float]] | None = None,
) -> tuple[np.ndarray, list[list[float]]]:
    if raster.ndim != 3 or raster.shape[-1] not in {1, 2, 3, 4}:
        raise ImagingError("display raster must be YXS")
    colors = raster[..., :3] if raster.shape[-1] >= 3 else raster[..., :1]
    actual_levels = display_levels(colors) if levels is None else levels
    output_channels: list[np.ndarray] = []
    for channel in range(3):
        source_channel = colors[..., min(channel, colors.shape[-1] - 1)].astype(
            np.float32,
            copy=False,
        )
        low, high = actual_levels[channel]
        scaled = (source_channel - low) * (255.0 / max(high - low, 1.0e-12))
        output_channels.append(np.clip(scaled, 0.0, 255.0).astype(np.uint8))
    return np.stack(output_channels, axis=-1), actual_levels


class SourceRaster(AbstractContextManager["SourceRaster"]):
    """One decoded source at a time; compressed rasters spill to a memmap."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        self._temporary_memmap_path: Path | None = None
        with tifffile.TiffFile(self.path) as tif:
            if len(tif.pages) != 1:
                raise ImagingError(f"source must contain exactly one TIFF page: {path}")
            page = tif.pages[0]
            axes = page.axes
            tag = page.tags.get(274)
            self.orientation = 1 if tag is None else int(tag.value)
            raw_shape = tuple(int(value) for value in page.shape)
        try:
            decoded = tifffile.memmap(self.path, mode="r", page=0)
        except (ValueError, OSError):
            with tifffile.TiffFile(self.path) as tif:
                decoded = tif.pages[0].asarray(out="memmap", maxworkers=1)
            filename = getattr(decoded, "filename", None)
            if filename:
                temporary = Path(str(filename)).resolve()
                if temporary != self.path:
                    self._temporary_memmap_path = temporary
        self.raw = _normalize_raster(decoded, axes, self.path)
        if tuple(self.raw.shape[:2]) != tuple(raw_shape[:2]):
            if self.raw.shape[0] <= 0 or self.raw.shape[1] <= 0:
                raise ImagingError(f"invalid TIFF extent for {path}")
        self.mapping = orientation_mapping(
            self.orientation,
            int(self.raw.shape[1]),
            int(self.raw.shape[0]),
        )
        self.canonical = _canonical_view(self.raw, self.orientation)

    def close(self) -> None:
        raw_base = getattr(self.raw, "base", None)
        mmap = getattr(raw_base, "_mmap", None) or getattr(self.raw, "_mmap", None)
        if mmap is not None:
            mmap.close()
        if self._temporary_memmap_path is not None:
            self._temporary_memmap_path.unlink(missing_ok=True)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @property
    def raw_extent(self) -> tuple[int, int]:
        return int(self.raw.shape[1]), int(self.raw.shape[0])

    @property
    def canonical_extent(self) -> tuple[int, int]:
        return int(self.canonical.shape[1]), int(self.canonical.shape[0])

    def analysis_rgb8(self) -> tuple[np.ndarray, list[list[float]]]:
        sample = bounded_sample(self.canonical, MAX_ANALYSIS_LONG_SIDE)
        return raster_to_rgb8(sample)

    def preview_jpeg(
        self,
        *,
        levels: list[list[float]] | None = None,
        maximum_long_side: int = MAX_PREVIEW_LONG_SIDE,
        quality: int = 91,
    ) -> bytes:
        sample = bounded_sample(self.canonical, maximum_long_side)
        rgb, _ = raster_to_rgb8(sample, levels)
        image = Image.fromarray(rgb)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        return output.getvalue()

    def native_tile_png(
        self,
        *,
        center_x: float,
        center_y: float,
        side: int,
        levels: list[list[float]],
    ) -> tuple[bytes, dict[str, int]]:
        if not 64 <= side <= MAX_NATIVE_TILE_SIDE:
            raise ImagingError(f"native tile side must be 64..{MAX_NATIVE_TILE_SIDE}")
        width, height = self.canonical_extent
        half = side // 2
        left = min(max(0, int(round(center_x)) - half), max(0, width - side))
        top = min(max(0, int(round(center_y)) - half), max(0, height - side))
        right = min(width, left + side)
        bottom = min(height, top + side)
        tile = np.asarray(self.canonical[top:bottom, left:right])
        rgb, _ = raster_to_rgb8(tile, levels)
        image = Image.fromarray(rgb)
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue(), {
            "left": left,
            "top": top,
            "width": right - left,
            "height": bottom - top,
        }


def orientation_record(mapping: OrientationMapping) -> dict[str, Any]:
    return {
        "original_tag": mapping.original_tag,
        "raw_to_canonical": [list(row) for row in mapping.raw_to_canonical],
        "canonical_to_raw": [list(row) for row in mapping.canonical_to_raw],
    }


def render_review_artifact(
    preview_jpeg: bytes,
    record: dict[str, Any],
    *,
    maximum_long_side: int = MAX_PREVIEW_LONG_SIDE,
) -> bytes:
    image = Image.open(io.BytesIO(preview_jpeg)).convert("RGB")
    draw = ImageDraw.Draw(image, mode="RGBA")
    display_width = float(record["source"]["canonical_extent"]["width"])
    display_height = float(record["source"]["canonical_extent"]["height"])
    scale_x = image.width / display_width
    scale_y = image.height / display_height

    def scaled(point: list[float]) -> tuple[float, float]:
        return point[0] * scale_x, point[1] * scale_y

    task_colors = (
        (64, 236, 160, 110),
        (104, 177, 255, 105),
        (255, 205, 92, 105),
    )
    for task_index, task in enumerate(record["tasks"]):
        color = task_colors[task_index % len(task_colors)]
        for polygon in frame_polygons_display(record, task):
            draw.polygon([scaled(point) for point in polygon], fill=color)

    line_width = max(2, int(round(maximum_long_side / 900)))
    for line in record["shared_edges"]:
        points = [scaled(raw_to_display_point(record, point)) for point in line["points_raw"]]
        draw.line(points, fill=(0, 235, 255, 255), width=line_width)
    used_ids = {
        line_id
        for task in record["tasks"]
        for slot in task["slots"]
        for line_id in (slot["start_boundary_id"], slot["end_boundary_id"])
    }
    for line in record["boundary_pool"]:
        points = [scaled(raw_to_display_point(record, point)) for point in line["points_raw"]]
        color = (255, 95, 105, 255) if line["line_id"] in used_ids else (170, 170, 180, 180)
        draw.line(points, fill=color, width=line_width)

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=94, optimize=True)
    return output.getvalue()
