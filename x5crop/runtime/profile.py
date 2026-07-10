from __future__ import annotations

from dataclasses import replace

from ..domain import ImageProfile
from ..geometry.layout import infer_layout
from ..utils import spatial_shape_from_shape
from .config import RuntimeConfig


def runtime_for_profile(config: RuntimeConfig, profile: ImageProfile) -> RuntimeConfig:
    h, w = spatial_shape_from_shape(profile.shape)
    layout = infer_layout(w, h) if config.layout_auto else config.layout
    return replace(config, layout=layout)


__all__ = [
    "runtime_for_profile",
]
