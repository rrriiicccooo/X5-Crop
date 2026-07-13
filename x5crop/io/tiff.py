from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import tifffile

from .model import ImageProfile, TiffExtraTag, TiffMetadata
from ..utils import (
    enum_name,
    infer_axes,
    infer_axes_from_shape,
    planar_config_name,
    spatial_shape_from_shape,
)


LOSSLESS_COMPRESSIONS = {"NONE", "LZW", "ADOBE_DEFLATE", "DEFLATE", "ZSTD"}
TIFF_ICC_PROFILE_TAG = 34675
BITS_PER_BYTE = 8
TIFF_RESOLUTION_ABSOLUTE_TOLERANCE = 1e-6
TIFF_IMAGE_DESCRIPTION_TAG = 270
TIFF_SOFTWARE_TAG = 305
TIFF_DATETIME_TAG = 306
TRANSFERABLE_EXTRA_TAG_TYPES = {
    269: "s",  # DocumentName
    271: "s",  # Make
    272: "s",  # Model
    285: "s",  # PageName
    315: "s",  # Artist
    316: "s",  # HostComputer
    700: "B",  # XMP
    33723: "B",  # IPTC/NAA
    34377: "B",  # Photoshop image resources
    33432: "s",  # Copyright
}


def _text_tag_value(page: Any, code: int) -> str | None:
    tag = page.tags.get(code)
    if tag is None:
        return None
    value = normalize_tag_value(tag.value)
    if isinstance(value, bytes):
        return value.rstrip(b"\0").decode("utf-8", errors="replace")
    return str(value)


def _extra_tag_value(
    value: Any,
    dtype: str,
) -> str | bytes | tuple[int, ...] | tuple[float, ...]:
    normalized = normalize_tag_value(value)
    if dtype == "s":
        if isinstance(normalized, bytes):
            return normalized.rstrip(b"\0").decode("utf-8", errors="replace")
        return str(normalized)
    if isinstance(normalized, bytes):
        return normalized
    if isinstance(normalized, tuple):
        if all(isinstance(item, int) for item in normalized):
            return tuple(int(item) for item in normalized)
        if all(isinstance(item, (int, float)) for item in normalized):
            return tuple(float(item) for item in normalized)
    raise ValueError("transferable TIFF byte metadata has an unsupported value")


def tiff_metadata_from_page(page: Any) -> TiffMetadata:
    extra_tags = tuple(
        TiffExtraTag(
            code=code,
            dtype=dtype,
            count=(
                0
                if dtype == "s"
                else len(value)
                if isinstance(value, (bytes, tuple))
                else int(page.tags[code].count)
            ),
            value=value,
        )
        for code, dtype in TRANSFERABLE_EXTRA_TAG_TYPES.items()
        if code in page.tags
        for value in (_extra_tag_value(page.tags[code].value, dtype),)
    )
    return TiffMetadata(
        description=_text_tag_value(page, TIFF_IMAGE_DESCRIPTION_TAG),
        datetime=_text_tag_value(page, TIFF_DATETIME_TAG),
        software=_text_tag_value(page, TIFF_SOFTWARE_TAG),
        extra_tags=extra_tags,
    )


def profile_from_page(page: Any, shape: tuple[int, ...], dtype: np.dtype, axes: str) -> ImageProfile:
    photometric = enum_name(getattr(page, "photometric", None), "UNKNOWN")
    compression = enum_name(getattr(page, "compression", None), "NONE")
    sample_format = page.tags.get("SampleFormat")
    bits_tag = page.tags.get("BitsPerSample")
    samples_tag = page.tags.get("SamplesPerPixel")
    planar = page.tags.get("PlanarConfiguration")
    xres = page.tags.get("XResolution")
    yres = page.tags.get("YResolution")
    unit = page.tags.get("ResolutionUnit")
    icc = page.tags.get(TIFF_ICC_PROFILE_TAG)
    x_resolution = rational_to_float(xres.value) if xres else None
    y_resolution = rational_to_float(yres.value) if yres else None
    profile = ImageProfile(
        shape=tuple(int(x) for x in shape),
        dtype=str(np.dtype(dtype)),
        axes=axes,
        photometric=photometric,
        compression=compression,
        sample_format=normalize_tag_value(
            sample_format.value
            if sample_format
            else getattr(page, "sampleformat", None)
        ),
        bits_per_sample=normalize_tag_value(bits_tag.value) if bits_tag else None,
        samples_per_pixel=(int(samples_tag.value) if samples_tag else (shape[-1] if axes == "YXS" else shape[0] if axes == "SYX" else 1)),
        planar_config=planar_config_name(getattr(page, "planarconfig", None) or (planar.value if planar else None)),
        resolution=(
            (x_resolution, y_resolution)
            if x_resolution is not None and y_resolution is not None
            else None
        ),
        resolution_unit=(
            normalize_tag_value(unit.value) if unit else None
        ),
        icc_profile=(bytes(icc.value) if icc is not None else None),
        metadata=tiff_metadata_from_page(page),
    )
    expected_bits = expected_bits_for_dtype(profile.dtype, int(profile.samples_per_pixel or 1))
    if profile.bits_per_sample is not None and normalize_tag_value(profile.bits_per_sample) != normalize_tag_value(expected_bits):
        raise ValueError(
            f"Packed or unusual bit depth is not supported safely: "
            f"BitsPerSample={profile.bits_per_sample}, dtype={profile.dtype}. "
            "Refusing to continue to protect output bit depth."
        )
    return profile


def read_tiff_profile(path: Path, page_index: int) -> tuple[ImageProfile, list[str]]:
    warnings: list[str] = []
    with tifffile.TiffFile(path) as tif:
        if not tif.pages:
            raise ValueError("TIFF has no pages")
        if page_index < 0 or page_index >= len(tif.pages):
            raise ValueError(f"--page {page_index} is out of range; TIFF has {len(tif.pages)} pages")
        if len(tif.pages) > 1 and page_index == 0:
            warnings.append(f"TIFF has {len(tif.pages)} pages; processing page 0")
        page = tif.pages[page_index]
        shape = tuple(int(x) for x in page.shape)
        axes = str(getattr(page, "axes", "") or "")
        if axes not in {"YX", "YXS", "SYX"}:
            axes = infer_axes_from_shape(shape)
        profile = profile_from_page(page, shape, np.dtype(page.dtype), axes)
    return profile, warnings


def read_tiff_page_shape(path: Path, page_index: int) -> tuple[int, int]:
    if page_index < 0:
        raise ValueError("--page must be 0 or greater")
    with tifffile.TiffFile(path) as tif:
        if not tif.pages:
            raise ValueError(f"TIFF has no pages: {path}")
        if page_index >= len(tif.pages):
            raise ValueError(
                f"--page {page_index} is out of range; "
                f"TIFF has {len(tif.pages)} pages"
            )
        shape = tuple(int(value) for value in tif.pages[page_index].shape)
    return spatial_shape_from_shape(shape)


def read_tiff(path: Path, page_index: int) -> tuple[np.ndarray, ImageProfile, list[str]]:
    warnings: list[str] = []
    with tifffile.TiffFile(path) as tif:
        if not tif.pages:
            raise ValueError("TIFF has no pages")
        if page_index < 0 or page_index >= len(tif.pages):
            raise ValueError(f"--page {page_index} is out of range; TIFF has {len(tif.pages)} pages")
        if len(tif.pages) > 1 and page_index == 0:
            warnings.append(f"TIFF has {len(tif.pages)} pages; processing page 0")
        page = tif.pages[page_index]
        arr = page.asarray()
        axes = infer_axes(arr)
        profile = profile_from_page(page, tuple(int(x) for x in arr.shape), arr.dtype, axes)
    return arr, profile, warnings


def compression_for_write(
    profile: ImageProfile,
    mode: str,
) -> str | None:
    if mode not in {"none", "same"}:
        raise ValueError(f"Unsupported TIFF compression mode: {mode}")
    if mode == "none":
        return None
    name = profile.compression.upper()
    if name == "NONE":
        return None
    if name not in LOSSLESS_COMPRESSIONS:
        raise ValueError(f"Refusing to preserve non-lossless or unknown compression: {profile.compression}")
    mapping = {
        "LZW": "lzw",
        "ADOBE_DEFLATE": "deflate",
        "DEFLATE": "deflate",
        "ZSTD": "zstd",
    }
    return mapping.get(name)


def tiff_write_kwargs(
    profile: ImageProfile,
    compression_mode: str,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"metadata": None}
    photometric = profile.photometric.lower()
    if photometric in {"rgb", "minisblack", "miniswhite"}:
        kwargs["photometric"] = photometric
    if profile.planar_config and profile.photometric.upper() == "RGB":
        planar = profile.planar_config.lower()
        if planar in {"contig", "separate"}:
            kwargs["planarconfig"] = planar
    compression = compression_for_write(profile, compression_mode)
    if compression is not None:
        kwargs["compression"] = compression
    if profile.resolution and profile.resolution[0] and profile.resolution[1]:
        kwargs["resolution"] = profile.resolution
    if profile.resolution_unit:
        kwargs["resolutionunit"] = profile.resolution_unit
    if profile.icc_profile:
        kwargs["iccprofile"] = profile.icc_profile
    metadata = profile.metadata
    if metadata.description is not None:
        kwargs["description"] = metadata.description
    if metadata.datetime is not None:
        kwargs["datetime"] = metadata.datetime
    kwargs["software"] = (
        metadata.software if metadata.software is not None else False
    )
    if metadata.extra_tags:
        kwargs["extratags"] = tuple(
            (tag.code, tag.dtype, tag.count, tag.value, False)
            for tag in metadata.extra_tags
        )
    return kwargs


def normalize_tag_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return normalize_tag_value(value.value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, tuple):
        return tuple(normalize_tag_value(v) for v in value)
    if isinstance(value, list):
        return tuple(normalize_tag_value(v) for v in value)
    return value


def expected_bits_for_dtype(dtype_name: str, samples: int) -> int | tuple[int, ...] | None:
    dtype = np.dtype(dtype_name)
    if not np.issubdtype(dtype, np.integer) and not np.issubdtype(dtype, np.floating):
        return None
    bits = int(dtype.itemsize * BITS_PER_BYTE)
    if samples <= 1:
        return bits
    return tuple(bits for _ in range(samples))


def rational_to_float(value: Any) -> float | None:
    value = normalize_tag_value(value)
    if isinstance(value, tuple) and len(value) == 2:
        denominator = float(value[1])
        if denominator == 0:
            return None
        return float(value[0]) / denominator
    try:
        return float(value)
    except Exception:
        return None


def resolutions_equivalent(a: Any, b: Any, tolerance: float) -> bool:
    if a is None or b is None:
        return a is b
    if len(a) != 2 or len(b) != 2:
        return False
    for left, right in zip(a, b):
        lf = rational_to_float(left)
        rf = rational_to_float(right)
        if lf is None or rf is None:
            return normalize_tag_value(left) == normalize_tag_value(right)
        if abs(lf - rf) > tolerance:
            return False
    return True


def validate_written_tiff(
    out_path: Path,
    expected_array: np.ndarray,
    source_profile: ImageProfile,
    compression_mode: str,
) -> None:
    problems: list[str] = []
    with tifffile.TiffFile(out_path) as tif:
        if not tif.pages:
            raise RuntimeError(f"Output TIFF has no pages: {out_path}")
        page = tif.pages[0]
        arr = page.asarray()
        axes = infer_axes(arr)
        photometric = enum_name(getattr(page, "photometric", None), "UNKNOWN")
        compression = enum_name(getattr(page, "compression", None), "NONE")
        xres = page.tags.get("XResolution")
        yres = page.tags.get("YResolution")
        unit = page.tags.get("ResolutionUnit")
        sample_format = page.tags.get("SampleFormat")
        bits = page.tags.get("BitsPerSample")
        samples = page.tags.get("SamplesPerPixel")
        planar = page.tags.get("PlanarConfiguration")
        icc = page.tags.get(TIFF_ICC_PROFILE_TAG)
        metadata = tiff_metadata_from_page(page)

        if arr.dtype != expected_array.dtype:
            problems.append(f"dtype changed: {expected_array.dtype} -> {arr.dtype}")
        if tuple(arr.shape) != tuple(expected_array.shape):
            problems.append(f"shape changed after write/read: expected {expected_array.shape}, got {arr.shape}")
        elif not np.array_equal(arr, expected_array):
            problems.append("pixel data changed after write/read")
        if axes != source_profile.axes:
            problems.append(f"axes changed: {source_profile.axes} -> {axes}")
        if photometric.upper() != source_profile.photometric.upper():
            problems.append(f"Photometric changed: {source_profile.photometric} -> {photometric}")
        if compression_mode == "same" and compression.upper() != source_profile.compression.upper():
            problems.append(f"Compression changed: {source_profile.compression} -> {compression}")
        if source_profile.sample_format is not None:
            actual_sample_format = normalize_tag_value(sample_format.value if sample_format else getattr(page, "sampleformat", None))
            if normalize_tag_value(actual_sample_format) != normalize_tag_value(source_profile.sample_format):
                problems.append(f"SampleFormat changed: {source_profile.sample_format} -> {actual_sample_format}")

        expected_samples = int(source_profile.samples_per_pixel or 1)
        actual_samples = int(samples.value) if samples else (arr.shape[-1] if axes == "YXS" else arr.shape[0] if axes == "SYX" else 1)
        if actual_samples != expected_samples:
            problems.append(f"SamplesPerPixel changed: {expected_samples} -> {actual_samples}")
        if source_profile.planar_config is not None:
            actual_planar = planar_config_name(getattr(page, "planarconfig", None) or (planar.value if planar else None))
            if actual_planar != source_profile.planar_config:
                problems.append(f"PlanarConfiguration changed: {source_profile.planar_config} -> {actual_planar}")

        actual_bits = normalize_tag_value(bits.value) if bits else expected_bits_for_dtype(str(arr.dtype), actual_samples)
        expected_bits = normalize_tag_value(source_profile.bits_per_sample)
        if expected_bits is None:
            expected_bits = expected_bits_for_dtype(source_profile.dtype, expected_samples)
        if normalize_tag_value(actual_bits) != normalize_tag_value(expected_bits):
            problems.append(f"BitsPerSample changed: {expected_bits} -> {actual_bits}")

        if source_profile.resolution is not None:
            actual_resolution = ((xres.value if xres else None), (yres.value if yres else None))
            if not resolutions_equivalent(
                actual_resolution,
                source_profile.resolution,
                TIFF_RESOLUTION_ABSOLUTE_TOLERANCE,
            ):
                problems.append(f"Resolution changed: {source_profile.resolution} -> {actual_resolution}")
        if source_profile.resolution_unit is not None:
            actual_unit = unit.value if unit else None
            if normalize_tag_value(actual_unit) != normalize_tag_value(source_profile.resolution_unit):
                problems.append(f"ResolutionUnit changed: {source_profile.resolution_unit} -> {actual_unit}")
        if source_profile.icc_profile is not None:
            actual_icc = bytes(icc.value) if icc is not None else None
            if actual_icc != source_profile.icc_profile:
                problems.append("ICC profile changed or was dropped")
        if metadata != source_profile.metadata:
            problems.append(
                f"TIFF metadata changed: {source_profile.metadata} -> {metadata}"
            )

    if problems:
        raise RuntimeError("Output TIFF validation failed for " + str(out_path) + ":\n  - " + "\n  - ".join(problems))


def write_validated_tiff(
    path: Path,
    pixels: np.ndarray,
    source_profile: ImageProfile,
    compression_mode: str,
) -> None:
    tifffile.imwrite(
        path,
        pixels,
        **tiff_write_kwargs(source_profile, compression_mode),
    )
    validate_written_tiff(path, pixels, source_profile, compression_mode)
