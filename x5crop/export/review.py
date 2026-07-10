from __future__ import annotations

import shutil
from pathlib import Path

from ..run_config import RunConfig


def review_directory_for(output_dir: Path, config: RunConfig) -> Path:
    return config.review_dir if config.review_dir is not None else output_dir / "needs_review"


def copy_for_review(input_file: Path, review_dir: Path) -> Path:
    review_dir.mkdir(parents=True, exist_ok=True)
    target = review_dir / input_file.name
    if target.exists():
        return target
    shutil.copy2(input_file, target)
    return target
