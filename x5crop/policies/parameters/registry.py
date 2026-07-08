from __future__ import annotations

from typing import Any

from ...formats import FORMAT_CHOICES
from .aggregate import FormatParameters
from .ownership import split_format_parameter_overrides


def base_format_parameters(format_name: str, **overrides: Any) -> FormatParameters:
    layers = split_format_parameter_overrides(overrides)
    return FormatParameters(format_name, **layers.as_dict())


def base_medium_format_parameters(format_name: str, **overrides: Any) -> FormatParameters:
    params: dict[str, Any] = {
        "content_profile_min_run_ratio": 0.18,
    }
    params.update(overrides)
    return base_format_parameters(format_name, **params)


def format_parameters(format_name: str) -> FormatParameters:
    if format_name not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format parameters: {format_name}")
    from ..formats import PARAMETER_FACTORIES

    try:
        parameters = PARAMETER_FACTORIES[format_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported format parameters: {format_name}") from exc
    return parameters()

__all__ = [
    "base_format_parameters",
    "base_medium_format_parameters",
    "format_parameters",
]
