from __future__ import annotations

import shutil
from pathlib import Path

from ..output.naming import portable_component


def review_directory_for(output_dir: Path) -> Path:
    return output_dir / "needs_review"


def copy_for_review(
    input_file: Path,
    review_dir: Path,
    *,
    portable_stem: str,
    input_ordinal: int,
) -> Path:
    review_dir.mkdir(parents=True, exist_ok=True)
    target = review_dir / portable_component(
        portable_stem,
        input_ordinal=input_ordinal,
        suffix=input_file.suffix.lower(),
    ).value
    if target.exists():
        raise FileExistsError(f"review target was not fresh: {target}")
    shutil.copy2(input_file, target)
    return target
