from __future__ import annotations

from pathlib import Path
from typing import Any

from ..runtime.config import RuntimeConfig
from ..detection.detail import final_review_reasons_from_detail
from ..domain import Detection, ImageProfile
from .crops import write_crops
from .review import copy_for_review, review_directory_for


def copy_for_review_if_needed(
    input_file: Path,
    output_dir: Path,
    config: RuntimeConfig,
    detection: Detection,
    status: str,
    warnings: list[str],
) -> str | None:
    if status != "needs_review":
        return None
    reasons = final_review_reasons_from_detail(detection)
    warnings.append(
        f"review required: confidence={detection.confidence:.3f}; "
        f"threshold={config.confidence_threshold:.3f}; "
        f"reasons={','.join(reasons) or 'none'}"
    )
    if not config.copy_review_files:
        return None
    review_copy = str(copy_for_review(input_file, review_directory_for(output_dir, config)))
    warnings.append(f"review copy: {review_copy}")
    return review_copy


def write_crops_if_allowed(
    input_file: Path,
    arr: Any,
    source_arr: Any,
    profile: ImageProfile,
    detection: Detection,
    config: RuntimeConfig,
    deskew_applied: bool,
    output_dir: Path,
    status: str,
) -> list[str]:
    should_export = (status == "approved_auto" or config.export_review) and not config.dry_run
    if not should_export:
        return []
    return write_crops(
        input_file,
        arr,
        source_arr,
        profile,
        detection,
        config,
        deskew_applied,
        output_dir,
    )


__all__ = [
    "copy_for_review_if_needed",
    "write_crops_if_allowed",
]
