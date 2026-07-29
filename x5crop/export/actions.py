from __future__ import annotations

from pathlib import Path

from ..detection.final.model import FinalDetection
from ..run_config import RunConfig
from .review import copy_for_review, review_directory_for


def prepare_review_artifact(
    input_file: Path,
    output_dir: Path,
    config: RunConfig,
    detection: FinalDetection,
    warnings: list[str],
) -> str | None:
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
