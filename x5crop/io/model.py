from __future__ import annotations

from dataclasses import dataclass


TiffTagScalar = int | float | str
TiffTagValue = TiffTagScalar | tuple[TiffTagScalar, ...]


@dataclass(frozen=True)
class ImageProfile:
    shape: tuple[int, ...]
    dtype: str
    axes: str
    photometric: str
    compression: str
    sample_format: TiffTagValue | None
    bits_per_sample: int | tuple[int, ...] | None
    samples_per_pixel: int | None
    planar_config: str | None
    resolution: tuple[float, float] | None
    resolution_unit: int | str | None
    icc_profile: bytes | None
