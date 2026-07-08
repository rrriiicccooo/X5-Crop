from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..parameters.registry import base_format_parameters

FORMAT_ID = "135-dual"


def parameters() -> FormatParameters:
    return base_format_parameters(FORMAT_ID)
