from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....domain import DetectionCandidate
from ...evidence.separator_summary import separator_support_detail_summary
from ..plan.count_hypotheses import CountHypothesis


@dataclass(frozen=True)
class PhysicalCountResolution:
    count_resolved: bool
    placement_resolved: bool
    evidence: dict[str, Any]

    def report_detail(self) -> dict[str, Any]:
        return {
            "count_resolved": bool(self.count_resolved),
            "placement_resolved": bool(self.placement_resolved),
            "evidence": dict(self.evidence),
        }


def physical_count_resolution(
    candidate: DetectionCandidate,
    hypothesis: CountHypothesis,
) -> PhysicalCountResolution:
    assessment = candidate.detail.get("candidate_assessment", {})
    assessment = dict(assessment) if isinstance(assessment, dict) else {}
    separator = assessment.get("separator_support", {})
    separator = dict(separator) if isinstance(separator, dict) else {}
    separator_summary = separator_support_detail_summary(separator)
    topology = candidate.detail.get("frame_topology_evidence", {})
    topology = dict(topology) if isinstance(topology, dict) else {}
    photo_size = candidate.detail.get("photo_width_stability", {})
    photo_size = dict(photo_size) if isinstance(photo_size, dict) else {}
    coverage = candidate.detail.get("frame_coverage_evidence", {})
    coverage = dict(coverage) if isinstance(coverage, dict) else {}

    expected_gaps = max(0, int(hypothesis.count) - 1)
    hard_separator_complete = bool(
        expected_gaps > 0
        and separator_summary.hard_separator_gaps >= expected_gaps
    )
    topology_valid = all(
        bool(topology.get(key, False))
        for key in (
            "frame_extent_valid",
            "frame_order_valid",
            "frame_overlap_absent",
        )
    )
    photo_size_consistent = bool(
        photo_size.get("used", False) and not photo_size.get("unstable", True)
    )
    frame_coverage_complete = coverage.get("state") == "supported"
    count_resolved = all(
        (
            hypothesis.physically_supported,
            int(candidate.count) == int(hypothesis.count),
            hard_separator_complete,
            topology_valid,
            photo_size_consistent,
            frame_coverage_complete,
        )
    )
    return PhysicalCountResolution(
        count_resolved=bool(count_resolved),
        placement_resolved=bool(count_resolved),
        evidence={
            "hypothesis_physically_supported": bool(hypothesis.physically_supported),
            "expected_gap_count": int(expected_gaps),
            "hard_separator_gap_count": int(separator_summary.hard_separator_gaps),
            "hard_separator_complete": bool(hard_separator_complete),
            "photo_size_consistent": bool(photo_size_consistent),
            "frame_topology_valid": bool(topology_valid),
            "frame_coverage_complete": bool(frame_coverage_complete),
        },
    )


@dataclass(frozen=True)
class CountHypothesisEvaluation:
    hypothesis: CountHypothesis
    candidates: tuple[DetectionCandidate, ...]
    count_resolved: bool
    placement_resolved: bool
    resolved_offsets: tuple[float, ...]
    resolution_checks: tuple[dict[str, Any], ...]

    def report_detail(self) -> dict[str, Any]:
        confidences = [float(candidate.confidence) for candidate in self.candidates]
        return {
            **self.hypothesis.report_detail(),
            "candidate_count": len(self.candidates),
            "max_confidence": max(confidences) if confidences else None,
            "count_resolved": bool(self.count_resolved),
            "placement_resolved": bool(self.placement_resolved),
            "resolved_offsets": [float(offset) for offset in self.resolved_offsets],
            "resolution_checks": [dict(check) for check in self.resolution_checks],
        }
