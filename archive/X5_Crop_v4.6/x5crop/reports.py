from __future__ import annotations

from .common import *
from .io import *
from .geometry import *
from .deskew import *

def output_directory_for(input_file: Path, config: Config) -> Path:
    if config.output_dir is not None:
        return config.output_dir
    return input_file.parent / "x5_crop_output"


def review_directory_for(output_dir: Path, config: Config) -> Path:
    return config.review_dir if config.review_dir is not None else output_dir / "needs_review"


def display_generated_path(path: Path | str, config: Config) -> str:
    path = Path(path)
    if config.output_dir is None:
        return path.name
    return str(path)


def copy_for_review(input_file: Path, review_dir: Path) -> Path:
    review_dir.mkdir(parents=True, exist_ok=True)
    target = review_dir / input_file.name
    if target.exists():
        return target
    shutil.copy2(input_file, target)
    return target


def source_cache_signature(input_file: Path, profile: ImageProfile, page_index: int) -> dict[str, Any]:
    stat = input_file.stat()
    return {
        "name": input_file.name,
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "page": int(page_index),
        "shape": list(profile.shape),
        "dtype": profile.dtype,
        "axes": profile.axes,
        "photometric": profile.photometric,
    }


def config_cache_signature(config: Config) -> dict[str, Any]:
    return {
        "film_format": config.film_format,
        "layout": config.layout,
        "strip_mode": config.strip_mode,
        "count": int(config.count),
        "page": int(config.page),
        "deskew": config.deskew,
        "analysis": config.analysis,
        "deskew_min_angle": float(config.deskew_min_angle),
        "deskew_max_angle": float(config.deskew_max_angle),
        "confidence_threshold": float(config.confidence_threshold),
    }


def make_analysis_cache_metadata(input_file: Path, profile: ImageProfile, config: Config) -> dict[str, Any]:
    return {
        "script": SCRIPT_NAME,
        "version": VERSION,
        "source": source_cache_signature(input_file, profile, config.page),
        "config": config_cache_signature(config),
    }


def box_from_dict(value: dict[str, Any]) -> Box:
    return Box(int(value["left"]), int(value["top"]), int(value["right"]), int(value["bottom"]))


def gap_from_dict(value: dict[str, Any]) -> Gap:
    return Gap(
        index=int(value.get("index", 0)),
        center=float(value.get("center", 0.0)),
        score=float(value.get("score", 0.0)),
        method=str(value.get("method", "cached")),
        start=(None if value.get("start") is None else float(value.get("start"))),
        end=(None if value.get("end") is None else float(value.get("end"))),
        lane_box=(dict(value["lane_box"]) if isinstance(value.get("lane_box"), dict) else None),
    )


def cached_record_matches(record: dict[str, Any], input_file: Path, profile: ImageProfile, config: Config) -> bool:
    detail = record.get("detail")
    if not isinstance(detail, dict):
        return False
    cache = detail.get("analysis_cache")
    if not isinstance(cache, dict):
        return False
    if cache.get("script") != SCRIPT_NAME or cache.get("version") != VERSION:
        return False
    expected_source = source_cache_signature(input_file, profile, config.page)
    expected_config = config_cache_signature(config)
    if cache.get("source") != expected_source:
        return False
    cached_config = cache.get("config")
    if not isinstance(cached_config, dict):
        return False
    comparable_cached_config = dict(cached_config)
    comparable_cached_config.pop("bleed_x", None)
    comparable_cached_config.pop("bleed_y", None)
    if comparable_cached_config != expected_config:
        return False
    return str(record.get("status", "")) in {"approved_auto", "needs_review"}


def load_report_records(report_path: Path) -> list[dict[str, Any]]:
    try:
        stat = report_path.stat()
    except FileNotFoundError:
        return []
    cached = REPORT_RECORD_CACHE.get(report_path)
    signature = (int(stat.st_size), int(stat.st_mtime_ns))
    if cached is not None and cached[0] == signature[0] and cached[1] == signature[1]:
        return cached[2]
    try:
        lines = report_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []
    records: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    REPORT_RECORD_CACHE[report_path] = (signature[0], signature[1], records)
    return records


def find_reusable_analysis(input_file: Path, output_dir: Path, profile: ImageProfile, config: Config) -> Optional[dict[str, Any]]:
    report_path = output_dir / "split_report.jsonl"
    for record in load_report_records(report_path):
        if Path(str(record.get("source", ""))).name != input_file.name:
            continue
        if cached_record_matches(record, input_file, profile, config):
            return record
    return None


def config_for_profile(config: Config, profile: ImageProfile) -> Config:
    h, w = spatial_shape_from_shape(profile.shape)
    fmt = FORMATS[config.film_format]
    tuning = format_tuning(fmt.name)
    count = int(fmt.default_count if config.count_override is None else config.count_override)
    if count not in fmt.allowed_counts:
        allowed = ", ".join(str(x) for x in fmt.allowed_counts)
        raise ValueError(f"--format {fmt.name} allows --count values: {allowed}")
    layout = infer_layout(w, h) if config.layout_auto else config.layout
    return replace(config, layout=layout, count=count)


def detection_from_record(record: dict[str, Any]) -> Detection:
    return Detection(
        film_format=str(record["film_format"]),
        layout=str(record["layout"]),
        strip_mode=str(record["strip_mode"]),
        count=int(record["count"]),
        outer=box_from_dict(record["outer_box"]),
        frames=[box_from_dict(box) for box in record.get("frame_boxes", [])],
        gaps=[gap_from_dict(gap) for gap in record.get("gaps", [])],
        confidence=float(record["confidence"]),
        review_reasons=list(record.get("review_reasons", [])),
        detail=dict(record.get("detail", {})),
    )


def apply_cached_deskew(
    arr: np.ndarray,
    gray: np.ndarray,
    axes: str,
    photometric: str,
    detail: dict[str, Any],
    warnings: list[str],
) -> tuple[np.ndarray, np.ndarray, bool]:
    deskew_detail = detail.get("deskew")
    if not isinstance(deskew_detail, dict) or not bool(deskew_detail.get("applied", False)):
        return arr, gray, False
    angle = float(deskew_detail.get("angle", 0.0))
    arr = rotate_array_expand(arr, -angle, axes)
    gray = make_gray_u8(arr, axes, photometric)
    warnings.append(f"reused deskew: {-angle:.4f} degrees")
    return arr, gray, True


def write_crops(
    input_file: Path,
    arr: np.ndarray,
    source_arr: np.ndarray,
    profile: ImageProfile,
    page: Any,
    detection: Detection,
    config: Config,
    deskew_applied: bool,
    output_dir: Path,
) -> list[str]:
    output_files: list[str] = []
    for i, box in enumerate(detection.frames, 1):
        if not box.valid():
            raise RuntimeError(f"Invalid crop box for frame {i}: {box}")
        out_path = output_dir / f"{input_file.stem}_{i:02d}.tif"
        if out_path.exists() and not config.overwrite:
            raise RuntimeError(f"Output exists: {out_path}; use --overwrite")
        cropped = np.ascontiguousarray(crop_array(arr, profile.axes, box))
        if not deskew_applied:
            validate_source_crop_pixels(source_arr, profile.axes, box, cropped)
        tmp = out_path.with_name(f".{out_path.stem}.tmp{out_path.suffix}")
        if tmp.exists():
            tmp.unlink()
        try:
            tifffile.imwrite(tmp, cropped, **tiff_write_kwargs(profile, page, config))
            validate_written_tiff(tmp, cropped, profile, config)
            os.replace(tmp, out_path)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
        output_files.append(str(out_path))
    return output_files


def write_jsonl(path: Path, result: ProcessResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(json_safe(asdict(result)), ensure_ascii=False) + "\n")


def write_summary(path: Path, result: ProcessResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source",
        "status",
        "confidence",
        "film_format",
        "layout",
        "strip_mode",
        "count",
        "review_reasons",
        "output_count",
    ]
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "source": result.source,
                "status": result.status,
                "confidence": f"{result.confidence:.3f}",
                "film_format": result.film_format,
                "layout": result.layout,
                "strip_mode": result.strip_mode,
                "count": result.count,
                "review_reasons": ";".join(result.review_reasons),
                "output_count": len(result.output_files),
            }
        )


def write_reports_for_result(result: ProcessResult, config: Config) -> None:
    if not config.report:
        return
    output_dir = output_directory_for(Path(result.source), config)
    write_jsonl(output_dir / "split_report.jsonl", result)
    write_summary(output_dir / "split_summary.csv", result)
