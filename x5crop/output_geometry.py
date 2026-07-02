from __future__ import annotations

from dataclasses import replace

from .config import RuntimeConfig
from .domain import Box, Detection
from .geometry.boxes import map_work_box, original_box_to_work
from .policies.runtime_policy import OutputPolicy


def detection_geometry_config(config: RuntimeConfig, output_policy: OutputPolicy) -> RuntimeConfig:
    return replace(
        config,
        bleed_x=int(output_policy.detection_long_axis_bleed),
        bleed_y=int(output_policy.detection_short_axis_bleed),
    )


def detection_has_overlap_bleed_risk(detection: Detection) -> bool:
    overlap_bleed = detection.detail.get("overlap_bleed_risk")
    if isinstance(overlap_bleed, dict) and bool(overlap_bleed.get("risk", False)):
        return True

    lucky = detection.detail.get("lucky_pass_risk_score")
    if isinstance(lucky, dict):
        if bool(lucky.get("risk", False)):
            return True
        counts = lucky.get("overlap_risk_counts")
        if isinstance(counts, dict):
            if int(counts.get("strong", 0) or 0) > 0 or int(counts.get("medium", 0) or 0) > 0:
                return True

    diagnostics = detection.detail.get("diagnostics")
    if isinstance(diagnostics, dict):
        summary = diagnostics.get("summary")
        if isinstance(summary, dict):
            if int(summary.get("overlap_like_model_gaps", 0) or 0) > 0:
                return True
            counts = summary.get("overlap_risk_counts")
            if isinstance(counts, dict):
                if int(counts.get("strong", 0) or 0) > 0 or int(counts.get("medium", 0) or 0) > 0:
                    return True
    return False


def output_bleed_config_for_detection(
    config: RuntimeConfig,
    detection: Detection,
    output_policy: OutputPolicy,
) -> RuntimeConfig:
    if not detection_has_overlap_bleed_risk(detection):
        return config
    target_bleed_x = max(int(config.bleed_x), int(output_policy.overlap_risk_long_axis_bleed))
    if target_bleed_x == int(config.bleed_x):
        return config
    return replace(config, bleed_x=target_bleed_x)


def apply_output_bleed(
    detection: Detection,
    detection_config: RuntimeConfig,
    output_config: RuntimeConfig,
    image_w: int,
    image_h: int,
) -> None:
    if (
        int(detection_config.bleed_x) == int(output_config.bleed_x)
        and int(detection_config.bleed_y) == int(output_config.bleed_y)
    ):
        return
    frames_work = [original_box_to_work(frame, detection.layout, image_w, image_h) for frame in detection.frames]
    work_w = image_w if detection.layout == "horizontal" else image_h
    work_h = image_h if detection.layout == "horizontal" else image_w
    adjusted_work: list[Box] = []
    for frame in frames_work:
        raw = Box(
            frame.left + int(detection_config.bleed_x),
            frame.top + int(detection_config.bleed_y),
            frame.right - int(detection_config.bleed_x),
            frame.bottom - int(detection_config.bleed_y),
        )
        if not raw.valid():
            return
        adjusted_work.append(raw.expand(int(output_config.bleed_x), int(output_config.bleed_y), work_w, work_h))
    detection.frames = [map_work_box(frame, detection.layout, image_w, image_h) for frame in adjusted_work]
    detection.detail["output_bleed"] = {
        "used": True,
        "detection_long_axis_bleed": int(detection_config.bleed_x),
        "detection_short_axis_bleed": int(detection_config.bleed_y),
        "output_long_axis_bleed": int(output_config.bleed_x),
        "output_short_axis_bleed": int(output_config.bleed_y),
        "overlap_risk_long_axis_bleed": bool(detection_has_overlap_bleed_risk(detection)),
    }


def reapply_cached_output_bleed(detection: Detection, config: RuntimeConfig, image_w: int, image_h: int) -> None:
    output_bleed = detection.detail.get("output_bleed")
    if not isinstance(output_bleed, dict):
        return
    try:
        cached_x = int(output_bleed.get("output_long_axis_bleed", config.bleed_x))
        cached_y = int(output_bleed.get("output_short_axis_bleed", config.bleed_y))
    except (TypeError, ValueError):
        return
    if cached_x == int(config.bleed_x) and cached_y == int(config.bleed_y):
        return
    cached_config = replace(config, bleed_x=cached_x, bleed_y=cached_y)
    apply_output_bleed(detection, cached_config, config, image_w, image_h)
    detection.detail["reused_output_bleed_adjustment"] = {
        "from_long_axis_bleed": int(cached_x),
        "from_short_axis_bleed": int(cached_y),
        "to_long_axis_bleed": int(config.bleed_x),
        "to_short_axis_bleed": int(config.bleed_y),
    }


__all__ = [
    "apply_output_bleed",
    "detection_geometry_config",
    "detection_has_overlap_bleed_risk",
    "output_bleed_config_for_detection",
    "reapply_cached_output_bleed",
]
