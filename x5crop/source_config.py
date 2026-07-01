from __future__ import annotations

from dataclasses import replace

from .config import Config
from .domain import ImageProfile
from .formats import FORMATS
from .geometry.layout import infer_layout
from .utils import spatial_shape_from_shape


def config_for_profile(config: Config, profile: ImageProfile) -> Config:
    h, w = spatial_shape_from_shape(profile.shape)
    fmt = FORMATS[config.film_format]
    count = int(fmt.default_count if config.count_override is None else config.count_override)
    if count not in fmt.allowed_counts:
        allowed = ", ".join(str(x) for x in fmt.allowed_counts)
        raise ValueError(f"--format {fmt.name} allows --count values: {allowed}")
    layout = infer_layout(w, h) if config.layout_auto else config.layout
    return replace(config, layout=layout, count=count)


__all__ = [
    "config_for_profile",
]
