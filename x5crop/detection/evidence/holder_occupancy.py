from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ...domain import Box, DetectionCandidate
from ...formats import FormatPhysicalSpec
from ...units import ScanCalibration
from ...utils import box_from_dict


def _work_outer(detection: DetectionCandidate) -> Box:
    value = detection.detail.get("work_outer")
    if isinstance(value, dict):
        try:
            box = box_from_dict(value)
            if box.valid():
                return box
        except (KeyError, TypeError, ValueError):
            pass
    return detection.outer


def _work_frames(detection: DetectionCandidate) -> list[Box]:
    value = detection.detail.get("work_frame_boxes")
    boxes: list[Box] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            try:
                box = box_from_dict(item)
            except (KeyError, TypeError, ValueError):
                continue
            if box.valid():
                boxes.append(box)
    return boxes or [box for box in detection.frames if box.valid()]


def _holder_reference_outer(detection: DetectionCandidate) -> Box:
    holder_reference = detection.detail.get("holder_reference_outer_box")
    if isinstance(holder_reference, dict):
        try:
            box = box_from_dict(holder_reference)
            if box.valid():
                return box
        except (KeyError, TypeError, ValueError):
            pass
    return _work_outer(detection)


def strip_completeness_evidence(detection: DetectionCandidate, fmt: FormatPhysicalSpec) -> dict[str, Any]:
    frames = _work_frames(detection)
    valid_frame_count = len(frames)
    expected_gap_count = max(0, int(detection.count) - 1)
    return {
        "strip_frame_count_complete": int(detection.count) == int(fmt.default_count),
        "frame_sequence_complete": (
            int(detection.count) == int(fmt.default_count)
            and valid_frame_count == int(detection.count)
        ),
        "count": int(detection.count),
        "default_count": int(fmt.default_count),
        "valid_frame_count": int(valid_frame_count),
        "expected_gap_count": int(expected_gap_count),
        "observed_gap_count": int(len(detection.gaps)),
        "role": "film_sequence_completeness_evidence",
    }


def _film_span_px(frames: list[Box]) -> tuple[float | None, float | None, float | None]:
    if not frames:
        return None, None, None
    left = min(float(frame.left) for frame in frames)
    right = max(float(frame.right) for frame in frames)
    return left, right, max(0.0, right - left)


def _photo_width_stable(detection: DetectionCandidate) -> bool:
    detail = detection.detail.get("photo_width_stability")
    if isinstance(detail, dict) and bool(detail.get("used", False)):
        return not bool(detail.get("unstable", False))
    width_source = str(detection.detail.get("width_cv_source") or "")
    return width_source != "photo_edges"


def holder_occupancy_evidence(
    detection: DetectionCandidate,
    fmt: FormatPhysicalSpec,
    content_containment: dict[str, Any],
    *,
    calibration: ScanCalibration | None = None,
) -> dict[str, Any]:
    holder_outer = _holder_reference_outer(detection)
    frames = _work_frames(detection)
    strip_completeness = strip_completeness_evidence(detection, fmt)
    film_left, film_right, observed_film_span_px = _film_span_px(frames)
    leading_slack_px = None
    trailing_slack_px = None
    holder_fill_ratio = None
    if film_left is not None and film_right is not None and holder_outer.width > 0:
        leading_slack_px = max(0.0, float(film_left) - float(holder_outer.left))
        trailing_slack_px = max(0.0, float(holder_outer.right) - float(film_right))
        holder_fill_ratio = float(observed_film_span_px or 0.0) / float(max(1, holder_outer.width))

    px_per_mm = calibration.px_per_mm("x") if calibration is not None and calibration.trusted else None
    leading_slack_mm = (
        None if px_per_mm is None or leading_slack_px is None else float(leading_slack_px) / float(px_per_mm)
    )
    trailing_slack_mm = (
        None if px_per_mm is None or trailing_slack_px is None else float(trailing_slack_px) / float(px_per_mm)
    )
    expected_film_span_mm = (
        float(detection.count) * float(fmt.nominal_frame_size_mm.width_mm)
        if int(detection.count) > 0
        else None
    )
    content_contained = bool(content_containment.get("content_containment_ok", False)) and not bool(
        content_containment.get("content_integrity_failed", True)
    )
    photo_width_stable = _photo_width_stable(detection)
    complete_underfilled = bool(
        fmt.complete_strip_can_be_underfilled
        and detection.strip_mode == "partial"
        and strip_completeness["frame_sequence_complete"]
        and content_contained
        and photo_width_stable
    )
    if detection.strip_mode == "full":
        occupancy_status = "filled"
    elif complete_underfilled:
        occupancy_status = "underfilled"
    else:
        occupancy_status = "unknown"

    return {
        "strip_completeness": strip_completeness,
        "strip_frame_count_complete": strip_completeness["strip_frame_count_complete"],
        "frame_sequence_complete": strip_completeness["frame_sequence_complete"],
        "complete_strip_can_be_underfilled": bool(fmt.complete_strip_can_be_underfilled),
        "expected_film_span_mm": expected_film_span_mm,
        "expected_film_span_mm_source": "nominal_frame_size_mm_without_separator_gap",
        "observed_film_span_px": observed_film_span_px,
        "leading_holder_slack_px": leading_slack_px,
        "trailing_holder_slack_px": trailing_slack_px,
        "leading_holder_slack_mm": leading_slack_mm,
        "trailing_holder_slack_mm": trailing_slack_mm,
        "holder_fill_ratio": holder_fill_ratio,
        "occupancy_status": occupancy_status,
        "complete_underfilled_strip": complete_underfilled,
        "content_contained": content_contained,
        "photo_width_stable": photo_width_stable,
        "holder_reference_outer_box": asdict(holder_outer),
        "film_span": (
            None
            if film_left is None or film_right is None
            else {"left": film_left, "right": film_right}
        ),
        "scan_calibration_used": bool(calibration is not None and calibration.trusted),
    }


def enrich_holder_occupancy_with_calibration(
    detail: dict[str, Any],
    calibration: ScanCalibration,
) -> dict[str, Any]:
    enriched = dict(detail)
    if not calibration.trusted:
        enriched["scan_calibration_used"] = False
        return enriched
    px_per_mm = calibration.px_per_mm("x")
    if px_per_mm is None or px_per_mm <= 0.0:
        enriched["scan_calibration_used"] = False
        return enriched
    for px_key, mm_key in (
        ("leading_holder_slack_px", "leading_holder_slack_mm"),
        ("trailing_holder_slack_px", "trailing_holder_slack_mm"),
    ):
        value = enriched.get(px_key)
        try:
            enriched[mm_key] = None if value is None else float(value) / float(px_per_mm)
        except (TypeError, ValueError):
            enriched[mm_key] = None
    enriched["scan_calibration_used"] = True
    return enriched
