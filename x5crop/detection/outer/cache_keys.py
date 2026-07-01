from __future__ import annotations

from typing import Any

from ...domain import OuterCandidate
from ...formats import FormatSpec
from ...geometry.boxes import box_cache_key


def separator_first_cache_key(
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


def separator_geometry_cache_key(
    base_candidates: list[OuterCandidate],
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
) -> tuple[Any, ...]:
    return (
        "separator_geometry",
        str(fmt.name),
        int(count),
        str(strip_mode),
        tuple((candidate.name, box_cache_key(candidate.box)) for candidate in base_candidates),
    )


def long_axis_edge_anchor_cache_key(
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
