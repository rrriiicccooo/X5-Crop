from __future__ import annotations

from .common import *
from .evidence import *

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
    icc = page.tags.get(34675)
    profile = ImageProfile(
        shape=tuple(int(x) for x in shape),
        dtype=str(np.dtype(dtype)),
        axes=axes,
        photometric=photometric,
        compression=compression,
        sample_format=(sample_format.value if sample_format else normalize_tag_value(getattr(page, "sampleformat", None))),
        bits_per_sample=(bits_tag.value if bits_tag else None),
        samples_per_pixel=(int(samples_tag.value) if samples_tag else (shape[-1] if axes == "YXS" else shape[0] if axes == "SYX" else 1)),
        planar_config=planar_config_name(getattr(page, "planarconfig", None) or (planar.value if planar else None)),
        resolution=((xres.value if xres else None), (yres.value if yres else None)) if xres or yres else None,
        resolution_unit=(unit.value if unit else None),
        icc_profile=(bytes(icc.value) if icc is not None else None),
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


def read_tiff(path: Path, page_index: int) -> tuple[np.ndarray, np.ndarray, ImageProfile, list[str], Any]:
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
    gray = make_gray_u8(arr, axes, profile.photometric)
    return arr, gray, profile, warnings, page


def compression_for_write(profile: ImageProfile, mode: str) -> Optional[str]:
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


def tiff_write_kwargs(profile: ImageProfile, page: Any, config: Config) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    photometric = profile.photometric.lower()
    if photometric in {"rgb", "minisblack", "miniswhite"}:
        kwargs["photometric"] = photometric
    if profile.planar_config and profile.photometric.upper() == "RGB":
        planar = profile.planar_config.lower()
        if planar in {"contig", "separate"}:
            kwargs["planarconfig"] = planar
    compression = compression_for_write(profile, config.compression)
    if compression is not None:
        kwargs["compression"] = compression
    if profile.resolution and profile.resolution[0] and profile.resolution[1]:
        kwargs["resolution"] = profile.resolution
    if profile.resolution_unit:
        kwargs["resolutionunit"] = profile.resolution_unit
    if profile.icc_profile:
        kwargs["iccprofile"] = profile.icc_profile
    return kwargs


def normalize_tag_value(value: Any) -> Any:
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
    bits = int(dtype.itemsize * 8)
    if samples <= 1:
        return bits
    return tuple(bits for _ in range(samples))


def rational_to_float(value: Any) -> Optional[float]:
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


def resolutions_equivalent(a: Any, b: Any, tolerance: float = 1e-6) -> bool:
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


def validate_written_tiff(out_path: Path, expected_array: np.ndarray, source_profile: ImageProfile, config: Config) -> None:
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
        icc = page.tags.get(34675)

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
        if config.compression == "same" and compression.upper() != source_profile.compression.upper():
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
            if not resolutions_equivalent(actual_resolution, source_profile.resolution):
                problems.append(f"Resolution changed: {source_profile.resolution} -> {actual_resolution}")
        if source_profile.resolution_unit is not None:
            actual_unit = unit.value if unit else None
            if normalize_tag_value(actual_unit) != normalize_tag_value(source_profile.resolution_unit):
                problems.append(f"ResolutionUnit changed: {source_profile.resolution_unit} -> {actual_unit}")
        if source_profile.icc_profile is not None:
            actual_icc = bytes(icc.value) if icc is not None else None
            if actual_icc != source_profile.icc_profile:
                problems.append("ICC profile changed or was dropped")

    if problems:
        raise RuntimeError("Output TIFF validation failed for " + str(out_path) + ":\n  - " + "\n  - ".join(problems))
