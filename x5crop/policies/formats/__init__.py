"""Explicit format policy and parameter registry."""

from __future__ import annotations

from collections.abc import Callable

from ..parameters.aggregate import FormatParameters
from ..runtime.policy import DetectionPolicy
from . import (
    format_120_645,
    format_120_66,
    format_120_67,
    format_135,
    format_135_dual,
    format_half,
    format_xpan,
)

PARAMETER_FACTORIES: dict[str, Callable[[], FormatParameters]] = {
    format_135.FORMAT_ID: format_135.parameters,
    format_135_dual.FORMAT_ID: format_135_dual.parameters,
    format_half.FORMAT_ID: format_half.parameters,
    format_xpan.FORMAT_ID: format_xpan.parameters,
    format_120_645.FORMAT_ID: format_120_645.parameters,
    format_120_66.FORMAT_ID: format_120_66.parameters,
    format_120_67.FORMAT_ID: format_120_67.parameters,
}

POLICY_BUILDERS: dict[str, Callable[[str], DetectionPolicy]] = {
    format_135.FORMAT_ID: format_135.build_policy,
    format_135_dual.FORMAT_ID: format_135_dual.build_policy,
    format_half.FORMAT_ID: format_half.build_policy,
    format_xpan.FORMAT_ID: format_xpan.build_policy,
    format_120_645.FORMAT_ID: format_120_645.build_policy,
    format_120_66.FORMAT_ID: format_120_66.build_policy,
    format_120_67.FORMAT_ID: format_120_67.build_policy,
}

__all__ = [
    "PARAMETER_FACTORIES",
    "POLICY_BUILDERS",
]
