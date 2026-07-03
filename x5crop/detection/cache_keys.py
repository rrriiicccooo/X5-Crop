from __future__ import annotations

from typing import Any

from ..domain import OuterCandidate
from ..formats import FormatSpec
from ..geometry.boxes import box_cache_key


def separator_outer_cache_key(
    variant: str,
    base_candidates: list[OuterCandidate],
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
) -> tuple[Any, ...]:
    return (
        "separator_outer",
        str(variant),
        str(fmt.name),
        int(count),
        str(strip_mode),
        tuple((candidate.name, box_cache_key(candidate.box)) for candidate in base_candidates),
    )


def edge_anchored_outer_cache_key(
    base_candidates: list[OuterCandidate],
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
) -> tuple[Any, ...]:
    return (
        str(fmt.name),
        int(count),
        str(strip_mode),
        tuple((candidate.name, box_cache_key(candidate.box)) for candidate in base_candidates),
    )
