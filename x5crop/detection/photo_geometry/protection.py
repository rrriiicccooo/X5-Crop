from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputProtectionSpec:
    format_id: str
    long_axis_mm_per_side: float
    short_axis_mm_per_side: float

    def __post_init__(self) -> None:
        if (
            not self.format_id
            or self.long_axis_mm_per_side <= 0.0
            or self.short_axis_mm_per_side <= 0.0
        ):
            raise ValueError("output protection requires positive millimetres")


_OUTPUT_PROTECTION_BY_FORMAT = {
    "half": OutputProtectionSpec("half", 0.15, 0.25),
    "135": OutputProtectionSpec("135", 0.25, 0.25),
    "135-dual": OutputProtectionSpec("135-dual", 0.25, 0.25),
    "120-645": OutputProtectionSpec("120-645", 0.30, 0.25),
    "120-66": OutputProtectionSpec("120-66", 0.40, 0.25),
    "xpan": OutputProtectionSpec("xpan", 0.45, 0.25),
    "120-67": OutputProtectionSpec("120-67", 0.50, 0.25),
}


def output_protection_spec(format_id: str) -> OutputProtectionSpec:
    return _OUTPUT_PROTECTION_BY_FORMAT[format_id]
