from __future__ import annotations

from pathlib import Path

from .review import copy_for_review, review_directory_for


def prepare_review_artifact(
    input_file: Path,
    portable_stem: str,
    input_ordinal: int,
    output_dir: Path,
    final_review_reasons: tuple[str, ...],
    warnings: list[str],
) -> str | None:
    warnings.append(
        "review required: reasons="
        + (",".join(final_review_reasons) or "none")
    )
    review_copy = str(
        copy_for_review(
            input_file,
            review_directory_for(output_dir),
            portable_stem=portable_stem,
            input_ordinal=input_ordinal,
        )
    )
    warnings.append(
        "review copy: "
        + Path(review_copy).relative_to(output_dir).as_posix()
    )
    return review_copy
