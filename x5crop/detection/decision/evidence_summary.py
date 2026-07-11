from __future__ import annotations

from typing import Any

from ...domain import DetectionCandidate
from ..evidence.frame_coverage import FrameCoverageEvidence
from ..evidence.separator_summary import separator_support_detail_summary


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def evidence_summary_for(
    detection: DetectionCandidate,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    frame_coverage: FrameCoverageEvidence,
) -> dict[str, Any]:
    assessment = _dict(detection.detail.get("candidate_assessment"))
    separator_detail = _dict(assessment.get("separator_support"))
    separator = separator_support_detail_summary(separator_detail)
    photo = _dict(detection.detail.get("photo_width_stability"))
    topology = _dict(detection.detail.get("frame_topology_evidence"))
    partial = _dict(assessment.get("partial_edge_safety"))
    return {
        "frame_topology": {
            "state": "supported" if topology.get("ok", False) else "contradicted",
            "detail": topology,
        },
        "separator_sequence": {
            "state": "supported" if separator_detail.get("ok", False) else "unavailable",
            "expected_gaps": int(separator.expected_gaps),
            "hard_gaps": int(separator.hard_separator_gaps),
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
                    frame_coverage.state.value == "contradicted"
                    or (
                    content_detail.get("content_boundary_contact", False)
                    and outer_alignment.get("used", False)
                    and not outer_alignment.get("ok", True)
                    )
                )
                else "supported"
                if content_detail.get("frame_content_support_available", False)
                else "unavailable"
            ),
            "detail": dict(content_detail),
        },
        "frame_coverage": {
            "state": frame_coverage.state.value,
            "reason": frame_coverage.reason,
            "holder_interval": list(frame_coverage.holder_interval),
            "film_interval": (
                None
                if frame_coverage.film_interval is None
                else list(frame_coverage.film_interval)
            ),
            "content_runs": list(frame_coverage.content_runs),
            "frame_intervals": list(frame_coverage.frame_intervals),
            "uncovered_content": list(frame_coverage.uncovered_content),
        },
        "outer_alignment": {
            "state": (
                "not_applicable"
                if not outer_alignment.get("used", False)
                else "contradicted"
                if outer_alignment.get("confirmed_undercrop", False)
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
