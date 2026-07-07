from __future__ import annotations

from ....constants import REASON_CONTENT_ASPECT_CONFLICT


CANDIDATE_AUTO_GATE_BLOCKING_REASONS = frozenset(
    {
        REASON_CONTENT_ASPECT_CONFLICT,
        "content_aspect_uncertain",
        "content_coverage_weak",
        "outer_box_too_large",
        "outer_box_uncertain",
        "photo_width_unstable",
        "unstable_frame_width",
    }
)


__all__ = [
    "CANDIDATE_AUTO_GATE_BLOCKING_REASONS",
]
