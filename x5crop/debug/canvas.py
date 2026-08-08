from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps


FRAME_FILL_COLORS = (
    (30, 144, 255),
    (255, 120, 40),
    (80, 200, 120),
    (210, 90, 255),
    (255, 210, 40),
    (40, 210, 220),
    (255, 90, 120),
    (150, 170, 255),
    (180, 120, 60),
    (120, 220, 60),
    (255, 160, 190),
    (70, 110, 210),
)


@dataclass
class DebugRenderCache:
    source_images: dict[str, Image.Image] = field(default_factory=dict)


def cached_source_image(
    cache: DebugRenderCache,
    gray: np.ndarray,
    *,
    rotate_clockwise: bool,
) -> Image.Image:
    key = "source_clockwise" if rotate_clockwise else "source"
    cached = cache.source_images.get(key)
    if cached is None:
        image = Image.fromarray(gray, mode="L")
        image = ImageOps.autocontrast(image, cutoff=0.5)
        image = ImageEnhance.Contrast(image).enhance(0.94)
        image = ImageEnhance.Brightness(image).enhance(0.82)
        if rotate_clockwise:
            image = image.transpose(Image.Transpose.ROTATE_270)
        cached = image.convert("RGB")
        cache.source_images[key] = cached
    return cached


def write_rgb_jpeg(
    rgb: np.ndarray,
    output_path: Path,
    *,
    quality: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(np.ascontiguousarray(rgb), mode="RGB")
    image.save(
        output_path,
        format="JPEG",
        quality=quality,
        optimize=True,
        subsampling=0,
    )
