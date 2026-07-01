from __future__ import annotations

import math
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Optional

from .app_info import VERSION
from .config import Config
from .detection.pipeline import choose_detection
from .detection.postprocess import finalize_detection_decision
from .detection.schema import report_schema_for_detection
from .debug.render import write_debug_analysis, write_debug_preview
from .domain import ProcessResult
from .format_specs import FORMATS
from .geometry import (
    detection_geometry_config,
    make_analysis_cache,
    output_bleed_config_for_detection,
    reapply_cached_output_bleed,
    work_gray,
)
from .image.deskew import choose_deskew_angle, rotate_array_expand
from .image.evidence import make_gray_u8
from .io import read_tiff, read_tiff_profile
from .policies.parameters import format_parameters
from .policies.registry import get_detection_policy
from .reports import (
    apply_cached_deskew,
    config_for_profile,
    copy_for_review,
    detection_from_record,
    display_generated_path,
    find_reusable_analysis,
    make_analysis_cache_metadata,
    output_directory_for,
    review_directory_for,
    write_crops,
    write_jsonl,
    write_summary,
)
from .utils import clamp_float, json_safe


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
                    version=VERSION,
                    policy_id=str(cached_record.get("policy_id", "")),
                )
                result.report_schema = dict(cached_record.get("report_schema", {}))
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
            policy = get_detection_policy(detection.film_format, detection.strip_mode)
            output_config = output_bleed_config_for_detection(config, detection, policy.output)
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
                version=VERSION,
                policy_id=str(
                    detection.detail.get("policy_id")
                    or detection.detail.get("policy", {}).get("policy_id", "")
                ),
            )
            result.report_schema = report_schema_for_detection(detection, result)
            if config.report:
                write_jsonl(output_dir / "split_report.jsonl", result)
                write_summary(output_dir / "split_summary.csv", result)
            return result

    arr, gray, profile, page_warnings, page = read_tiff(input_file, config.page)
    warnings.extend(w for w in page_warnings if w not in warnings)
    source_arr = arr
    config = config_for_profile(config, profile)
    fmt = FORMATS[config.film_format]
    tuning = format_parameters(fmt.name)

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
            deskew_detail["applied"] = True
            warnings.append(f"deskew applied: {-angle:.4f} degrees")
        else:
            deskew_detail["skipped"] = "angle_out_of_range"

    analysis_cache = make_analysis_cache(gray, config.layout)
    policy = get_detection_policy(fmt.name, config.strip_mode)
    detection_config = detection_geometry_config(config, policy.output)
    detection = choose_detection(gray, detection_config, fmt, analysis_cache)
    postprocess = finalize_detection_decision(
        gray,
        detection,
        config,
        fmt,
        analysis_cache,
        deskew_detail,
    )
    detection = postprocess.detection
    status = postprocess.status
    output_files: list[str] = []
    review_copy: Optional[str] = None

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
        write_debug_preview(gray, detection, debug_path, config.confidence_threshold, analysis_cache)
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
        version=VERSION,
        policy_id=str(
            detection.detail.get("policy_id")
            or detection.detail.get("policy", {}).get("policy_id", "")
        ),
    )
    result.report_schema = report_schema_for_detection(detection, result)
    if config.report:
        write_jsonl(output_dir / "split_report.jsonl", result)
        write_summary(output_dir / "split_summary.csv", result)
    return result


__all__ = [
    "process_one",
    "process_one_worker",
]
