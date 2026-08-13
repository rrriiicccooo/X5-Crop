"""Pixel-identity relations shared by sequence and cross edge families."""

from __future__ import annotations

from ...domain import FiniteInterval


def disjoint_family_pairs(
    supports: tuple[FiniteInterval, ...],
) -> tuple[tuple[int, int], ...]:
    """Return observations measured in non-overlapping spatial regions.

    Distance is deliberately absent.  Two separated regions may still be
    observations of one long physical edge; the caller must prove that their
    complete union supports one common line before merging them.
    """

    pairs = {
        (left_index, right_index)
        for left_index, left in enumerate(supports)
        for right_index, right in enumerate(supports)
        if left_index < right_index
        and (
            left.maximum < right.minimum
            or right.maximum < left.minimum
        )
    }
    return tuple(sorted(pairs))
