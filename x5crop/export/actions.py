from __future__ import annotations

from pathlib import Path
from typing import Any

from ..run_config import RunConfig
from ..detection.decision.model import FinalDetection
from ..domain import ImageProfile
from ..output.surface import OutputSurface
from .crops import write_crops
from .review import copy_for_review, review_directory_for


def copy_for_review_if_needed(
    input_file: Path,
    output_dir: Path,
    config: RunConfig,
    detection: FinalDetection,
    warnings: list[str],
) -> str | None:
    if detection.status != "needs_review":
        return None
    reasons = detection.final_review_reasons
    warnings.append(
        f"review required: reasons={','.join(reasons) or 'none'}"
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
    detection: FinalDetection,
    config: RunConfig,
    deskew_applied: bool,
    output_surface: OutputSurface,
) -> list[str]:
    should_export = (detection.status == "approved_auto" or config.export_review) and not config.dry_run
    if not should_export:
        return []
    output_dir = output_surface.ensure_root()
    return write_crops(
        input_file,
        arr,
        source_arr,
        profile,
        detection.output_geometry.frames,
        config,
        deskew_applied,
        output_dir,
    )
