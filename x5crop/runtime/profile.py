from __future__ import annotations

from dataclasses import replace

from ..domain import ImageProfile
from ..formats import FORMATS
from ..geometry.layout import infer_layout
from ..utils import spatial_shape_from_shape
from .config import RuntimeConfig


def runtime_for_profile(config: RuntimeConfig, profile: ImageProfile) -> RuntimeConfig:
    h, w = spatial_shape_from_shape(profile.shape)
    fmt = FORMATS[config.film_format]
    count = int(fmt.default_count if config.count_override is None else config.count_override)
    if count not in fmt.allowed_counts:
        allowed = ", ".join(str(x) for x in fmt.allowed_counts)
        raise ValueError(f"--format {fmt.name} allows --count values: {allowed}")
    layout = infer_layout(w, h) if config.layout_auto else config.layout
    return replace(config, layout=layout, count=count)


__all__ = [
    "runtime_for_profile",
]
