from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..frame_coverage import FrameCoverageEvidence
from ..state import EvidenceState


@dataclass(frozen=True)
class ContentPreservationEvidence:
    state: EvidenceState
    reason: str
    detail: dict[str, Any]

    def report_detail(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "reason": self.reason,
            "detail": dict(self.detail),
        }


def content_preservation_evidence(
    content: dict[str, Any],
    outer_alignment: dict[str, Any],
    partial_edge: dict[str, Any],
    frame_coverage: FrameCoverageEvidence,
) -> ContentPreservationEvidence:
    partial_failures = set(partial_edge.get("preservation_failures", []))
    complete_underfilled_strip = bool(partial_edge.get("complete_underfilled_strip", False))
    direct_undercrop = bool(
        "partial_edge_content_present" in partial_failures
        or outer_alignment.get("confirmed_undercrop", False)
    )
    corroborated_undercrop = bool(
        content.get("content_boundary_contact", False)
        and outer_alignment.get("used", False)
        and not outer_alignment.get("ok", True)
    )
    if frame_coverage.state == EvidenceState.CONTRADICTED:
        return ContentPreservationEvidence(
            EvidenceState.CONTRADICTED,
            "content_outside_frame_union",
            {
                "uncovered_content": list(frame_coverage.uncovered_content),
                "frame_intervals": list(frame_coverage.frame_intervals),
                "content_runs": list(frame_coverage.content_runs),
            },
        )
    if direct_undercrop or corroborated_undercrop:
        return ContentPreservationEvidence(
            EvidenceState.CONTRADICTED,
            "content_undercrop_confirmed",
            {
                "outer_alignment": dict(outer_alignment),
                "partial_preservation_failures": sorted(partial_failures),
                "frame_boundary_contact": bool(
                    content.get("content_boundary_contact", False)
                ),
                "complete_underfilled_strip": complete_underfilled_strip,
            },
        )
    if not bool(outer_alignment.get("used", False)):
        return ContentPreservationEvidence(
            EvidenceState.UNAVAILABLE,
            "outer_alignment_unavailable",
            {"outer_alignment": dict(outer_alignment)},
        )
    if bool(outer_alignment.get("ok", True)):
        return ContentPreservationEvidence(
            EvidenceState.SUPPORTED,
            "content_inside_outer",
            {"outer_alignment": dict(outer_alignment)},
        )
    return ContentPreservationEvidence(
        EvidenceState.UNAVAILABLE,
        "global_bbox_conflicts_with_frame_evidence",
        {
            "outer_alignment": dict(outer_alignment),
            "frame_content_support_available": bool(
                content.get("frame_content_support_available", False)
            ),
            "complete_underfilled_strip": complete_underfilled_strip,
        },
    )
