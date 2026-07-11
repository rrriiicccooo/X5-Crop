from __future__ import annotations

from typing import Any

from ...domain import DetectionCandidate
from ..evidence.separator_summary import separator_support_detail_summary


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def evidence_summary_for(
    detection: DetectionCandidate,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
) -> dict[str, Any]:
    assessment = _dict(detection.detail.get("candidate_assessment"))
    separator_detail = _dict(assessment.get("separator_support"))
    separator = separator_support_detail_summary(separator_detail)
    photo = _dict(detection.detail.get("photo_width_stability"))
    topology = _dict(detection.detail.get("frame_topology_evidence"))
    partial = _dict(assessment.get("partial_edge_safety"))
    complete_underfilled_strip = bool(
        partial.get("complete_underfilled_strip", False)
    )
    return {
        "frame_topology": {
            "state": "supported" if topology.get("ok", False) else "contradicted",
            "detail": topology,
        },
        "separator_sequence": {
            "state": "supported" if separator_detail.get("ok", False) else "unavailable",
            "expected_gaps": int(separator.expected_gaps),
            "hard_gaps": int(separator.hard_separator_gaps),
            "grid_gaps": int(separator.grid_model_gaps),
            "equal_gaps": int(separator.equal_model_gaps),
            "content_gaps": int(separator.content_model_gaps),
            "detail": separator_detail,
        },
        "photo_geometry": {
            "state": (
                "unavailable"
                if not photo.get("used", False)
                else "contradicted"
                if photo.get("unstable", False)
                else "supported"
            ),
            "detail": photo,
        },
        "content": {
            "state": (
                "contradicted"
                if (
                    content_detail.get("content_boundary_contact", False)
                    and outer_alignment.get("used", False)
                    and not outer_alignment.get("ok", True)
                    and not complete_underfilled_strip
                )
                else "supported"
                if content_detail.get("frame_content_support_available", False)
                else "unavailable"
            ),
            "detail": dict(content_detail),
        },
        "outer_alignment": {
            "state": (
                "not_applicable"
                if not outer_alignment.get("used", False)
                else "contradicted"
                if (
                    outer_alignment.get("confirmed_undercrop", False)
                    and not complete_underfilled_strip
                )
                else "supported"
                if outer_alignment.get("ok", False)
                else "unavailable"
            ),
            "detail": dict(outer_alignment),
        },
        "partial_occupancy": {
            "state": str(partial.get("state", "not_applicable")),
            "detail": partial,
        },
    }
