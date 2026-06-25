from __future__ import annotations

from .common import *
from .evidence import *
from .io import *
from .geometry import *
from .detection.pipeline import *
from .deskew import *
from .debug.render import *
from .reports import *

def process_one_worker(input_file: Path, config: Config) -> ProcessResult:
    return process_one(input_file, replace(config, report=False))


def process_one(input_file: Path, config: Config) -> ProcessResult:
    output_dir = output_directory_for(input_file, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile, warnings = read_tiff_profile(input_file, config.page)
    config = config_for_profile(config, profile)
    fmt = FORMATS[config.film_format]

    if config.reuse_analysis and not config.dry_run and not config.debug_analysis:
        cached_record = find_reusable_analysis(input_file, output_dir, profile, config)
        if cached_record is not None:
            status = str(cached_record["status"])
            warnings.append("reused analysis report: split_report.jsonl")
            if status == "needs_review":
                warnings.append("cached status is needs_review; skipped export")
                result = ProcessResult(
                    source=str(input_file),
                    status=status,
                    confidence=float(cached_record["confidence"]),
                    film_format=str(cached_record["film_format"]),
                    layout=str(cached_record["layout"]),
                    strip_mode=str(cached_record["strip_mode"]),
                    count=int(cached_record["count"]),
                    review_reasons=list(cached_record.get("review_reasons", [])),
                    output_files=[],
                    review_copy=cached_record.get("review_copy"),
                    outer_box=dict(cached_record.get("outer_box", {})),
                    frame_boxes=list(cached_record.get("frame_boxes", [])),
                    gaps=list(cached_record.get("gaps", [])),
                    detail={**dict(cached_record.get("detail", {})), "reused_analysis": True},
                    profile=json_safe(asdict(profile)),
                    warnings=warnings,
                )
                if config.report:
                    write_jsonl(output_dir / "split_report.jsonl", result)
                    write_summary(output_dir / "split_summary.csv", result)
                return result

            arr, gray, profile, page_warnings, page = read_tiff(input_file, config.page)
            warnings.extend(w for w in page_warnings if w not in warnings)
            source_arr = arr
            detection = detection_from_record(cached_record)
            arr, gray, deskew_applied = apply_cached_deskew(
                arr,
                gray,
                profile.axes,
                profile.photometric,
                detection.detail,
                warnings,
            )
            reapply_cached_output_bleed(detection, config, gray.shape[1], gray.shape[0])
            output_config = output_bleed_config_for_detection(config, detection)
            reapply_cached_output_bleed(detection, output_config, gray.shape[1], gray.shape[0])
            output_files = write_crops(
                input_file,
                arr,
                source_arr,
                profile,
                page,
                detection,
                config,
                deskew_applied,
                output_dir,
            )
            detail = dict(detection.detail)
            detail["reused_analysis"] = True
            result = ProcessResult(
                source=str(input_file),
                status=status,
                confidence=float(detection.confidence),
                film_format=detection.film_format,
                layout=detection.layout,
                strip_mode=detection.strip_mode,
                count=int(detection.count),
                review_reasons=list(detection.review_reasons),
                output_files=output_files,
                review_copy=cached_record.get("review_copy"),
                outer_box=asdict(detection.outer),
                frame_boxes=[asdict(box) for box in detection.frames],
                gaps=[asdict(gap) for gap in detection.gaps],
                detail=json_safe(detail),
                profile=json_safe(asdict(profile)),
                warnings=warnings,
            )
            if config.report:
                write_jsonl(output_dir / "split_report.jsonl", result)
                write_summary(output_dir / "split_summary.csv", result)
            return result

    arr, gray, profile, page_warnings, page = read_tiff(input_file, config.page)
    warnings.extend(w for w in page_warnings if w not in warnings)
    source_arr = arr
    config = config_for_profile(config, profile)
    fmt = FORMATS[config.film_format]
    tuning = format_tuning(fmt.name)

    deskew_detail: dict[str, Any] = {"applied": False}
    if config.deskew != "off":
        angle, angle_detail = choose_deskew_angle(gray, config.layout, config.analysis, fmt.name)
        deskew_detail.update(angle_detail)
        deskew_detail["angle"] = angle
        deskew_work_width = float(work_gray(gray, config.layout).shape[1])
        deskew_span = abs(math.tan(math.radians(angle)) * deskew_work_width)
        deskew_span_threshold = clamp_float(
            deskew_work_width * tuning.deskew_span_skip_ratio,
            tuning.deskew_span_skip_min,
            tuning.deskew_span_skip_max,
        )
        deskew_detail["span_px"] = deskew_span
        deskew_detail["span_threshold_px"] = deskew_span_threshold
        if deskew_span < deskew_span_threshold:
            deskew_detail["skipped"] = "span_below_threshold"
        elif config.deskew_min_angle <= abs(angle) <= config.deskew_max_angle:
            arr = rotate_array_expand(arr, -angle, profile.axes)
            gray = make_gray_u8(arr, profile.axes, profile.photometric)
            h, w = spatial_shape(arr)
            deskew_detail["applied"] = True
            warnings.append(f"deskew applied: {-angle:.4f} degrees")
        else:
            deskew_detail["skipped"] = "angle_out_of_range"

    analysis_cache = make_analysis_cache(gray, config.layout)
    detection_config = detection_geometry_config(config)
    detection = choose_detection_v2(gray, detection_config, fmt, analysis_cache)
    content_detail = content_evidence_detail(gray, detection, analysis_cache)
    detection.detail["content_evidence"] = content_detail
    outer_alignment = outer_content_alignment_detail(gray, detection, analysis_cache)
    detection.detail["outer_content_alignment"] = outer_alignment
    unsupported_mode = detection.detail.get("analysis_source") == "unsupported_mode"

    allow_outer_retry = detection.detail.get("analysis_source") != "hard_fallback" and tuning.outer_retry_enabled
    if allow_outer_retry and not unsupported_mode:
        retried_detection = retry_with_short_axis_aspect_outer(gray, detection_config, fmt, detection, content_detail, analysis_cache)
        if retried_detection is not None:
            detection = retried_detection
            content_detail = dict(detection.detail.get("content_evidence", {}))
            outer_alignment = dict(detection.detail.get("outer_content_alignment", {}))
    prior_outer_correction = detection.detail.get("outer_correction", {})
    skip_content_aligned_retry = (
        isinstance(prior_outer_correction, dict)
        and str(prior_outer_correction.get("source_reason", "")) == "short_axis_aspect_conflict"
    )
    if allow_outer_retry and not skip_content_aligned_retry and bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        retried_detection = retry_with_content_aligned_outer(gray, detection_config, fmt, detection, outer_alignment, analysis_cache)
        if retried_detection is not None:
            detection = retried_detection
            content_detail = dict(detection.detail.get("content_evidence", {}))
            outer_alignment = dict(detection.detail.get("outer_content_alignment", {}))
        else:
            detection.detail["outer_correction"] = {
                "used": False,
                "reason": "no_valid_content_aligned_outer_retry",
            }

    if not unsupported_mode and bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            detection.confidence = min(detection.confidence, tuning.post_content_aspect_conflict_cap)
            detection.review_reasons.append("content_aspect_conflict")
        elif support == "low_content" and detection.confidence >= config.confidence_threshold:
            detection.confidence = min(detection.confidence, tuning.post_content_low_confidence_cap)
            detection.review_reasons.append("content_evidence_weak")
    if not unsupported_mode and not skip_content_aligned_retry and bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        detection.confidence = min(detection.confidence, tuning.post_outer_mismatch_cap)
        detection.review_reasons.append("outer_content_bbox_mismatch")
    lucky_pass_risk = lucky_pass_risk_score_detail(gray, detection, config.confidence_threshold, analysis_cache)
    detection.detail["lucky_pass_risk_score"] = lucky_pass_risk
    if bool(lucky_pass_risk.get("risk", False)):
        detection.confidence = min(detection.confidence, tuning.post_lucky_pass_risk_cap)
        detection.review_reasons.append("lucky_pass_risk")

    if detection.confidence < config.confidence_threshold:
        if detection.detail.get("partial_best"):
            detection.review_reasons.append("likely_partial_strip")
        if float(detection.detail.get("outer_area_spread_ratio", 0.0)) >= 0.20:
            detection.review_reasons.append("outer_candidate_disagreement")
        if deskew_detail.get("skipped") == "angle_out_of_range" or deskew_detail.get("reason"):
            detection.review_reasons.append("deskew_uncertain")
        detection.review_reasons = sorted(set(detection.review_reasons))
    status = "approved_auto" if detection.confidence >= config.confidence_threshold else "needs_review"
    output_files: list[str] = []
    review_copy: Optional[str] = None
    apply_approved_geometry_polish(detection, gray, config, status)
    output_config = output_bleed_config_for_detection(config, detection)
    apply_output_bleed(detection, detection_config, output_config, gray.shape[1], gray.shape[0])
    apply_edge_bleed_protection(detection, output_config, gray.shape[1], gray.shape[0])
    if config.diagnostics:
        attach_read_only_diagnostics(gray, detection, analysis_cache)

    if status == "needs_review":
        warnings.append(
            f"low confidence: {detection.confidence:.3f} < {config.confidence_threshold:.3f}; "
            f"reasons={','.join(detection.review_reasons)}"
        )
        if config.copy_review_files:
            review_copy = str(copy_for_review(input_file, review_directory_for(output_dir, config)))
            warnings.append(f"review copy: {review_copy}")

    should_export = status == "approved_auto" or config.export_review
    if config.dry_run:
        should_export = False

    if should_export:
        output_files = write_crops(
            input_file,
            arr,
            source_arr,
            profile,
            page,
            detection,
            config,
            bool(deskew_detail["applied"]),
            output_dir,
        )

    if config.debug and not config.debug_analysis:
        debug_path = output_dir / "_debug" / f"{input_file.stem}_debug.jpg"
        write_debug_preview(gray, detection, debug_path, config.confidence_threshold)
        warnings.append(f"debug preview: {display_generated_path(debug_path, config)}")
    if config.debug_analysis:
        for analysis_path in write_debug_analysis(gray, detection, output_dir, input_file.stem, config.confidence_threshold, analysis_cache):
            warnings.append(f"debug analysis: {display_generated_path(analysis_path, config)}")

    detail = dict(detection.detail)
    detail["deskew"] = deskew_detail
    detail["analysis_cache"] = make_analysis_cache_metadata(input_file, profile, config)
    result = ProcessResult(
        source=str(input_file),
        status=status,
        confidence=float(detection.confidence),
        film_format=detection.film_format,
        layout=detection.layout,
        strip_mode=detection.strip_mode,
        count=int(detection.count),
        review_reasons=list(detection.review_reasons),
        output_files=output_files,
        review_copy=review_copy,
        outer_box=asdict(detection.outer),
        frame_boxes=[asdict(box) for box in detection.frames],
        gaps=[asdict(gap) for gap in detection.gaps],
        detail=json_safe(detail),
        profile=json_safe(asdict(profile)),
        warnings=warnings,
    )
    if config.report:
        write_jsonl(output_dir / "split_report.jsonl", result)
        write_summary(output_dir / "split_summary.csv", result)
    return result


def iter_input_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() not in TIFF_SUFFIXES:
            raise ValueError(f"Input is not a TIFF: {path}")
        return [path]
    if path.is_dir():
        return [p for p in sorted(path.iterdir()) if p.is_file() and p.suffix.lower() in TIFF_SUFFIXES]
    raise ValueError(f"Path does not exist: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"X5 Crop V{VERSION} single-strip TIFF film cropper.")
    parser.add_argument("input", nargs="?", default=".", help="TIFF file or directory; default current directory.")
    parser.add_argument("-o", "--output", default=None, help="Output directory; default input/split_output.")
    parser.add_argument("--format", choices=FORMAT_CHOICES, required=True, help="Film format; launchers pass this explicitly.")
    parser.add_argument("--layout", choices=LAYOUT_CHOICES, default="auto", help="auto/horizontal/vertical single-strip layout.")
    parser.add_argument("--strip", choices=STRIP_CHOICES, default="full", help="full strip or partial/head mode.")
    parser.add_argument("-n", "--count", type=int, default=None, help="Override frame count.")
    parser.add_argument("--page", type=int, default=0, help="TIFF page index; default 0.")
    parser.add_argument("--bleed", type=int, default=None, help="Bleed in pixels on all sides; overrides layout-aware defaults.")
    parser.add_argument("--bleed-x", type=int, default=None, help="Long-axis bleed override; default 20, or 50 when overlap/continuous-content risk is detected. Horizontal scans: left/right. Vertical scans: top/bottom.")
    parser.add_argument("--bleed-y", type=int, default=None, help="Short-axis bleed override; default 10. Horizontal scans: top/bottom. Vertical scans: left/right.")
    parser.add_argument("--deskew", choices=DESKEW_CHOICES, default="auto", help="Deskew strip before detection/export.")
    parser.add_argument("--analysis", choices=ANALYSIS_CHOICES, default="auto", help="Enhanced analysis for separator assist and deskew angle selection. auto runs enhanced separator only on weak separator evidence and enhanced deskew only when base deskew quality is weak; always enables enhanced passes; off disables enhanced analysis.")
    parser.add_argument("--compression", choices=COMPRESSION_CHOICES, default="same", help="TIFF output compression: same for known lossless source compression, or none.")
    parser.add_argument("--deskew-min-angle", type=float, default=0.03, help="Minimum absolute deskew angle in degrees.")
    parser.add_argument("--deskew-max-angle", type=float, default=2.0, help="Maximum absolute deskew angle in degrees.")
    parser.add_argument("--confidence-threshold", type=float, default=0.85, help="Minimum confidence for automatic export.")
    parser.add_argument("--copy-review-files", dest="copy_review_files", action="store_true", default=True, help="Copy low-confidence source TIFFs to review folder; default on.")
    parser.add_argument("--no-copy-review-files", dest="copy_review_files", action="store_false", help="Do not copy low-confidence source TIFFs to review folder.")
    parser.add_argument("--review-dir", default=None, help="Review folder; default output/needs_review.")
    parser.add_argument("--export-review", action="store_true", help="Export crops even when confidence is below threshold.")
    parser.add_argument("--dry-run", action="store_true", help="Detect only; do not write cropped TIFFs.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs.")
    parser.add_argument("--report", action="store_true", help="Write split_report.jsonl and split_summary.csv.")
    parser.add_argument("--debug", action="store_true", help="Write lightweight JPG previews with detected outer/frame boxes.")
    parser.add_argument("--debug-analysis", action="store_true", help="Write one combined JPG with debug boxes, original gray, separator evidence, and content evidence.")
    parser.add_argument("--diagnostics", action="store_true", help="Write read-only diagnostics and diagnostic Debug Analysis overlays. Does not change crop output.")
    parser.add_argument("--no-reuse-analysis", dest="reuse_analysis", action="store_false", default=True, help="Do not reuse matching Debug Analysis report data for non-dry-run export.")
    parser.add_argument("--jobs", type=int, default=2, help="Parallel TIFF workers. Default 2. Normal runs cap at 2; diagnostics runs cap at 4.")
    parser.add_argument("--debug-errors", action="store_true", help="Print tracebacks on errors.")
    parser.add_argument("--version", action="version", version=f"{SCRIPT_NAME} {VERSION}")
    return parser


def config_from_args(args: argparse.Namespace) -> Config:
    input_path = Path(args.input).expanduser().resolve()
    files_for_probe = [input_path] if input_path.is_file() else iter_input_files(input_path)
    first_file = next(iter(files_for_probe), None)
    if first_file is None:
        raise ValueError(f"No TIFF files found: {input_path}")
    with tifffile.TiffFile(first_file) as tif:
        shape = tuple(int(x) for x in tif.pages[int(args.page)].shape)
    height, width = spatial_shape_from_shape(shape)

    film_format = str(args.format)
    fmt = FORMATS[film_format]
    count = int(fmt.default_count if args.count is None else args.count)
    if count not in fmt.allowed_counts:
        allowed = ", ".join(str(x) for x in fmt.allowed_counts)
        raise ValueError(f"--format {fmt.name} allows --count values: {allowed}")
    layout_auto = str(args.layout) == "auto"
    layout = infer_layout(width, height) if layout_auto else str(args.layout)
    bleed_x_default = 20 if args.bleed is None else int(args.bleed)
    bleed_y_default = 10 if args.bleed is None else int(args.bleed)
    bleed_x = int(bleed_x_default if args.bleed_x is None else args.bleed_x)
    bleed_y = int(bleed_y_default if args.bleed_y is None else args.bleed_y)
    if bleed_x < 0 or bleed_y < 0:
        raise ValueError("Bleed cannot be negative")
    if not (0.0 <= float(args.confidence_threshold) <= 1.0):
        raise ValueError("--confidence-threshold must be between 0 and 1")
    if float(args.deskew_min_angle) < 0 or float(args.deskew_max_angle) <= 0:
        raise ValueError("Deskew angle limits are invalid")
    jobs_cap = 4 if bool(args.diagnostics) else 2
    jobs = max(1, min(jobs_cap, int(args.jobs)))
    return Config(
        input_path=input_path,
        output_dir=Path(args.output).expanduser().resolve() if args.output else None,
        film_format=film_format,
        layout_auto=layout_auto,
        layout=layout,
        strip_mode=str(args.strip),
        count=count,
        count_override=(None if args.count is None else int(args.count)),
        page=int(args.page),
        bleed_x=bleed_x,
        bleed_y=bleed_y,
        deskew=str(args.deskew),
        analysis=str(args.analysis),
        deskew_min_angle=float(args.deskew_min_angle),
        deskew_max_angle=float(args.deskew_max_angle),
        confidence_threshold=float(args.confidence_threshold),
        review_dir=Path(args.review_dir).expanduser().resolve() if args.review_dir else None,
        copy_review_files=bool(args.copy_review_files),
        export_review=bool(args.export_review),
        compression=str(args.compression),
        debug=bool(args.debug),
        debug_analysis=bool(args.debug_analysis),
        dry_run=bool(args.dry_run),
        diagnostics=bool(args.diagnostics),
        overwrite=bool(args.overwrite),
        report=bool(args.report),
        debug_errors=bool(args.debug_errors),
        reuse_analysis=bool(args.reuse_analysis),
        jobs=jobs,
    )


def print_process_result(result: ProcessResult, config: Config) -> None:
    print(f"  status={result.status} confidence={result.confidence:.3f}")
    for warning in result.warnings:
        print(f"  info: {warning}")
    if result.output_files:
        print(f"  wrote: {len(result.output_files)} TIFF files")
        if config.output_dir is not None:
            for out in result.output_files:
                print(f"    {Path(out).name}")


def process_parallel_files(
    files: list[Path],
    config: Config,
    worker_config: Config,
) -> tuple[int, int, int, int]:
    ok = 0
    failed = 0
    approved = 0
    review = 0
    total = len(files)
    try:
        executor_context = concurrent.futures.ProcessPoolExecutor(max_workers=config.jobs)
    except (OSError, PermissionError) as exc:
        print(f"info: process workers unavailable ({exc}); using thread workers")
        executor_context = concurrent.futures.ThreadPoolExecutor(max_workers=config.jobs)
    with executor_context as executor:
        future_to_path = {
            executor.submit(process_one_worker, path, worker_config): path
            for path in files
        }
        for index, future in enumerate(concurrent.futures.as_completed(future_to_path), start=1):
            path = future_to_path[future]
            print(f"\n[{index}/{total}] {path.name}")
            try:
                result = future.result()
                ok += 1
                approved += int(result.status == "approved_auto")
                review += int(result.status == "needs_review")
                write_reports_for_result(result, config)
                print_process_result(result, config)
            except Exception as exc:
                failed += 1
                print(f"  error: {exc}", file=sys.stderr)
                if config.debug_errors:
                    traceback.print_exc()
    return ok, failed, approved, review


def main() -> int:
    parser = build_parser()
    try:
        config = config_from_args(parser.parse_args())
        files = iter_input_files(config.input_path)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"{SCRIPT_NAME} {VERSION}")
    print(f"input: {config.input_path}")
    print(f"files: {len(files)}")
    layout_label = f"auto(probe={config.layout})" if config.layout_auto else config.layout
    mode_parts = [f"layout: {layout_label}", f"strip: {config.strip_mode}"]
    if config.strip_mode == "partial" and config.count_override is None:
        mode_parts.append("count: auto")
    if config.debug_analysis:
        mode_parts.append("debug analysis")
    if config.dry_run:
        mode_parts.append("dry run")
    print("; ".join(mode_parts))
    print(f"threshold: {config.confidence_threshold:.2f}; analysis: {config.analysis}")
    if len(files) > 1 and config.jobs > 1:
        print(f"parallel: {config.jobs} workers")
    if config.output_dir is not None:
        print(f"output: {config.output_dir}")

    ok = 0
    failed = 0
    approved = 0
    review = 0
    total = len(files)
    worker_config = replace(config, report=False)
    if total > 1 and config.jobs > 1:
        ok, failed, approved, review = process_parallel_files(files, config, worker_config)
    else:
        for index, path in enumerate(files, start=1):
            print(f"\n[{index}/{total}] {path.name}")
            try:
                result = process_one_worker(path, worker_config)
                ok += 1
                approved += int(result.status == "approved_auto")
                review += int(result.status == "needs_review")
                write_reports_for_result(result, config)
                print_process_result(result, config)
            except Exception as exc:
                failed += 1
                print(f"  error: {exc}", file=sys.stderr)
                if config.debug_errors:
                    traceback.print_exc()

    print(f"\ndone: ok={ok} failed={failed} approved={approved} review={review}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
