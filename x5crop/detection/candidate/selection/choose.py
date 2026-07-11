from __future__ import annotations

from ....domain import Box
from ....policies.parameters.scoring import SelectionConsensusParameters
from ...evidence.state import EvidenceState
from ..model import AssessedCandidate
from .model import GeometryCluster, GeometryResolution, SelectionResult


def candidate_rank(
    candidate: AssessedCandidate,
) -> tuple[int, int, int, int, int, float, float]:
    evidence = candidate.assessment.evidence
    contradictions = sum(
        state == EvidenceState.CONTRADICTED
        for state in (
            evidence.frame_topology.state,
            evidence.frame_coverage.state,
            evidence.frame_dimensions.state,
            evidence.content_preservation.state,
            evidence.independence.state,
        )
    )
    proof_supported = any(
        path.state == EvidenceState.SUPPORTED
        for path in candidate.assessment.gate.proof_paths
    )
    return (
        1 if proof_supported else 0,
        1 if candidate.geometry.automatic_processing_supported else 0,
        1 if candidate.assessment.gate.passed else 0,
        1 if evidence.frame_coverage.state == EvidenceState.SUPPORTED else 0,
        -int(contradictions),
        float(candidate.geometry.count),
        float(candidate.assessment.scores.confidence),
    )


def _box_edge_distance(left: Box, right: Box, scale: float) -> float:
    return max(
        abs(left.left - right.left),
        abs(left.top - right.top),
        abs(left.right - right.right),
        abs(left.bottom - right.bottom),
    ) / max(1.0, scale)


def geometry_distance(
    left: AssessedCandidate,
    right: AssessedCandidate,
) -> float | None:
    left_geometry = left.geometry
    right_geometry = right.geometry
    if (
        left_geometry.count != right_geometry.count
        or left_geometry.strip_mode != right_geometry.strip_mode
        or len(left_geometry.work_frames) != len(right_geometry.work_frames)
    ):
        return None
    scale = max(
        1.0,
        float(left_geometry.pitch),
        float(right_geometry.pitch),
    )
    distances = [
        _box_edge_distance(
            left_geometry.film_span.box,
            right_geometry.film_span.box,
            scale,
        )
    ]
    distances.extend(
        _box_edge_distance(left_box, right_box, scale)
        for left_box, right_box in zip(
            left_geometry.work_frames,
            right_geometry.work_frames,
        )
    )
    return max(distances, default=0.0)


def geometry_clusters(
    candidates: tuple[AssessedCandidate, ...],
    tolerance: float,
) -> tuple[GeometryCluster, ...]:
    groups: list[list[AssessedCandidate]] = []
    for candidate in candidates:
        for group in groups:
            distance = geometry_distance(candidate, group[0])
            if distance is not None and distance <= tolerance:
                group.append(candidate)
                break
        else:
            groups.append([candidate])
    return tuple(
        GeometryCluster(
            candidates=tuple(group),
            representative=max(group, key=candidate_rank),
        )
        for group in groups
    )


def geometry_resolution_for_selection(
    selected: AssessedCandidate,
    *,
    consensus: str,
    larger_counts_evaluated: bool,
) -> GeometryResolution:
    evidence = selected.assessment.evidence
    hypothesis = selected.count_hypothesis
    boundary_supported = any(
        path.state == EvidenceState.SUPPORTED
        for path in selected.assessment.gate.proof_paths
    )
    count_resolved = bool(
        hypothesis is not None
        and hypothesis.allowed_by_physical_spec
        and evidence.frame_topology.state == EvidenceState.SUPPORTED
        and evidence.frame_coverage.state == EvidenceState.SUPPORTED
        and evidence.frame_dimensions.state == EvidenceState.SUPPORTED
        and boundary_supported
    )
    placement_resolved = bool(
        count_resolved
        and selected.geometry.film_span.box.valid()
        and len(selected.geometry.work_frames) == selected.geometry.count
    )
    boundaries_resolved = bool(boundary_supported)
    coverage_resolved = (
        evidence.frame_coverage.state == EvidenceState.SUPPORTED
    )
    alternative_geometries_resolved = consensus != "disagreed"
    reasons: list[str] = []
    if not count_resolved:
        reasons.append("count_unresolved")
    if not placement_resolved:
        reasons.append("placement_unresolved")
    if not boundaries_resolved:
        reasons.append("boundaries_unresolved")
    if not coverage_resolved:
        reasons.append("coverage_unresolved")
    if not larger_counts_evaluated:
        reasons.append("larger_counts_not_evaluated")
    if not alternative_geometries_resolved:
        reasons.append("geometry_clusters_disagree")
    supported = not reasons
    return GeometryResolution(
        state=(
            EvidenceState.SUPPORTED
            if supported
            else EvidenceState.UNAVAILABLE
        ),
        count_resolved=count_resolved,
        placement_resolved=placement_resolved,
        boundaries_resolved=boundaries_resolved,
        coverage_resolved=coverage_resolved,
        larger_counts_evaluated=larger_counts_evaluated,
        alternative_geometries_resolved=alternative_geometries_resolved,
        reasons=tuple(reasons),
    )


def select_candidates(
    candidates: tuple[AssessedCandidate, ...],
    parameters: SelectionConsensusParameters,
    *,
    larger_counts_evaluated: bool,
) -> SelectionResult:
    if not candidates:
        raise ValueError("candidate selection requires at least one candidate")
    ranked = tuple(sorted(candidates, key=candidate_rank, reverse=True))
    clusters = geometry_clusters(ranked, parameters.geometry_tolerance_ratio)
    selected = ranked[0]
    selected_cluster = next(
        cluster for cluster in clusters if selected in cluster.candidates
    )
    competing = tuple(
        cluster for cluster in clusters if cluster is not selected_cluster
    )
    nearest_competitor = (
        max(competing, key=lambda cluster: candidate_rank(cluster.representative))
        if competing
        else None
    )
    disagreement = bool(
        nearest_competitor is not None
        and candidate_rank(nearest_competitor.representative)[:5]
        == candidate_rank(selected)[:5]
        and abs(
            selected.assessment.scores.confidence
            - nearest_competitor.representative.assessment.scores.confidence
        )
        < parameters.confidence_tie_margin
    )
    if disagreement:
        consensus = "disagreed"
    elif len(selected_cluster.candidates) > 1:
        consensus = "agreed"
    else:
        consensus = "uncontested"
    resolution = geometry_resolution_for_selection(
        selected,
        consensus=consensus,
        larger_counts_evaluated=larger_counts_evaluated,
    )
    return SelectionResult(
        selected=selected,
        ranked_candidates=ranked,
        clusters=clusters,
        consensus=consensus,
        geometry_resolution=resolution,
    )
