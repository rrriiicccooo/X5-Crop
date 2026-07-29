from __future__ import annotations

from pathlib import Path

from ..run_config import RunConfig
from ..detection.final.model import FinalDetection
from ..output.surface import OutputSurface
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
    detection: FinalDetection,
    config: RunConfig,
    output_surface: OutputSurface,
) -> list[str]:
    del input_file, config, output_surface
    if detection.frame_export_eligible:
        raise RuntimeError(
            "current source-core baseline cannot expose frame export"
        )
    return []
