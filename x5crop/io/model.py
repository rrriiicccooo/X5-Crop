from __future__ import annotations

from dataclasses import dataclass


TiffTagScalar = int | float | str
TiffTagValue = TiffTagScalar | tuple[TiffTagScalar, ...]
TiffExtraTagValue = str | bytes | tuple[int, ...] | tuple[float, ...]


@dataclass(frozen=True)
class TiffExtraTag:
    code: int
    dtype: str
    count: int
    value: TiffExtraTagValue

    def __post_init__(self) -> None:
        if self.code <= 0 or not self.dtype or self.count < 0:
            raise ValueError("TIFF extra tag requires a valid code, type, and count")


@dataclass(frozen=True)
class TiffMetadata:
    description: str | None
    datetime: str | None
    software: str | None
    extra_tags: tuple[TiffExtraTag, ...]

    def __post_init__(self) -> None:
        codes = tuple(tag.code for tag in self.extra_tags)
        if len(codes) != len(set(codes)):
            raise ValueError("TIFF metadata extra tags must be unique")


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
    metadata: TiffMetadata
