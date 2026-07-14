from __future__ import annotations

from pathlib import Path

import numpy as np

from ..run_config import RunConfig
from ..detection.final.model import FinalDetection
from ..io.model import ImageProfile
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
    if detection.decision.status != "needs_review":
        return None
    reasons = detection.decision.final_review_reasons
    warnings.append(
        f"review required: reasons={','.join(reasons) or 'none'}"
    )
    if not config.copy_review_files:
        return None
    review_copy = str(
        copy_for_review(
            input_file,
            review_directory_for(output_dir, config),
            overwrite=config.overwrite,
        )
    )
    warnings.append(f"review copy: {review_copy}")
    return review_copy


def write_crops_if_allowed(
    input_file: Path,
    arr: np.ndarray,
    source_arr: np.ndarray,
    profile: ImageProfile,
    detection: FinalDetection,
    config: RunConfig,
    deskew_applied: bool,
    output_surface: OutputSurface,
) -> list[str]:
    should_export = (
        detection.decision.status == "approved_auto" or config.export_review
    ) and not config.dry_run
    if not should_export:
        return []
    output_geometry = detection.output_geometry
    if output_geometry is None:
        return []
    output_dir = output_surface.root
    output_dir.mkdir(parents=True, exist_ok=True)
    return write_crops(
        input_file,
        arr,
        source_arr,
        profile,
        output_geometry.final_boxes,
        config,
        deskew_applied,
        output_dir,
    )
