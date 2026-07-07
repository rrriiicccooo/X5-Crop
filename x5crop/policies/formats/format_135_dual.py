from __future__ import annotations

from ..assembly.format_presets import build_policy_from_format
from ..parameters.aggregate import FormatParameters
from ..parameters.registry import base_format_parameters

FORMAT_ID = "135-dual"


def parameters() -> FormatParameters:
    return base_format_parameters(FORMAT_ID)


def build_policy(strip_mode: str):
    return build_policy_from_format(FORMAT_ID, parameters, strip_mode)
