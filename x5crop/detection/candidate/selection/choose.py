from __future__ import annotations

from x5crop.domain import EvidenceState
from ..model import AssessedCandidate
from .model import GeometryCluster, GeometryResolution, SelectionResult


def candidate_rank(
    candidate: AssessedCandidate,
) -> tuple[int, int, int, int, int, int, float, float, float]:
    quality = candidate.assessment.quality
    residuals = quality.physical_residuals
    partial_auto_count = (
        candidate.geometry.count
        if candidate.geometry.strip_mode == "partial"
        and candidate.count_hypothesis is not None
        and candidate.count_hypothesis.source == "automatic_count"
        else 0
    )
    dimension_residual = (
        residuals.dimension
        if residuals is not None and residuals.dimension is not None
        else float("inf")
    )
    conservation_residual = (
        residuals.conservation
        if residuals is not None and residuals.conservation is not None
        else float("inf")
    )
    boundary_residual = (
        residuals.boundary_uncertainty
        if residuals is not None
        else float("inf")
    )
    return (
        int(quality.covered_content_px),
        -int(quality.uncovered_content_px),
        -len(quality.contradicted),
        len(quality.supported_proof_paths),
        1 if candidate.geometry.automatic_processing_supported else 0,
        int(partial_auto_count),
        -float(dimension_residual),
        -float(conservation_residual),
        -float(boundary_residual),
    )


def candidate_dominates(
    left: AssessedCandidate,
    right: AssessedCandidate,
) -> bool:
    left_rank = candidate_rank(left)
    right_rank = candidate_rank(right)
    return bool(
        all(
            left_value >= right_value
            for left_value, right_value in zip(left_rank, right_rank)
        )
        and any(
            left_value > right_value
            for left_value, right_value in zip(left_rank, right_rank)
        )
    )


def geometry_equivalent(
    left: AssessedCandidate,
    right: AssessedCandidate,
) -> bool:
    left_geometry = left.geometry
    right_geometry = right.geometry
    if (
        left_geometry.count != right_geometry.count
        or left_geometry.strip_mode != right_geometry.strip_mode
        or len(left_geometry.frames) != len(right_geometry.frames)
    ):
        return False
    if left_geometry.photo_intervals and right_geometry.photo_intervals:
        return all(
            left_photo.start.intersects(right_photo.start)
            and left_photo.end.intersects(right_photo.end)
            for left_photo, right_photo in zip(
                left_geometry.photo_intervals,
                right_geometry.photo_intervals,
            )
        )
    return left_geometry.frames == right_geometry.frames


def geometry_clusters(
    candidates: tuple[AssessedCandidate, ...],
) -> tuple[GeometryCluster, ...]:
    groups: list[list[AssessedCandidate]] = []
    for candidate in candidates:
        for group in groups:
            if all(
                geometry_equivalent(candidate, existing)
                for existing in group
            ):
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
    fixed_count = bool(
        hypothesis is not None
        and hypothesis.source in {"format_default", "requested_count"}
    )
    count_topology_supported = bool(
        hypothesis is not None
        and hypothesis.allowed_by_physical_spec
        and evidence.frame_topology.state == EvidenceState.SUPPORTED
        and evidence.frame_topology.count_matches
    )
    conservation_not_contradicted = (
        evidence.frame_sequence.conservation.state != EvidenceState.CONTRADICTED
    )
    assignment_geometry_resolved = (
        selected.geometry.assignment_consensus.state == EvidenceState.SUPPORTED
    )
    automatic_count_supported = bool(
        count_topology_supported
        and evidence.frame_coverage.state == EvidenceState.SUPPORTED
        and evidence.frame_dimensions.state == EvidenceState.SUPPORTED
        and conservation_not_contradicted
        and evidence.content_preservation.state == EvidenceState.SUPPORTED
        and boundary_supported
        and assignment_geometry_resolved
        and not selected.geometry.search_budget_exhausted
    )
    count_resolved = bool(
        count_topology_supported
        and (fixed_count or automatic_count_supported)
    )
    placement_resolved = bool(
        count_resolved
        and selected.geometry.visible_sequence_span.box.valid()
        and len(selected.geometry.frames) == selected.geometry.count
        and boundary_supported
        and conservation_not_contradicted
        and assignment_geometry_resolved
        and not selected.geometry.search_budget_exhausted
    )
    boundaries_resolved = bool(boundary_supported)
    content_preservation_compatible = bool(
        evidence.frame_coverage.state != EvidenceState.CONTRADICTED
        and evidence.content_preservation.state != EvidenceState.CONTRADICTED
    )
    alternative_geometries_resolved = consensus != "disagreed"
    reasons: list[str] = []
    if not count_resolved:
        reasons.append("count_unresolved")
    if not placement_resolved:
        reasons.append("placement_unresolved")
    if not boundaries_resolved:
        reasons.append("boundaries_unresolved")
    if not content_preservation_compatible:
        reasons.append("content_preservation_contradicted")
    if not larger_counts_evaluated:
        reasons.append("larger_counts_not_evaluated")
    if not alternative_geometries_resolved:
        reasons.append("geometry_clusters_disagree")
    if not assignment_geometry_resolved:
        reasons.append("separator_assignment_geometry_unresolved")
    if selected.geometry.search_budget_exhausted:
        reasons.append("search_budget_exhausted")
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
        content_preservation_compatible=content_preservation_compatible,
        larger_counts_evaluated=larger_counts_evaluated,
        alternative_geometries_resolved=alternative_geometries_resolved,
        reasons=tuple(reasons),
    )


def select_candidates(
    candidates: tuple[AssessedCandidate, ...],
    *,
    larger_counts_evaluated: bool,
) -> SelectionResult:
    if not candidates:
        raise ValueError("candidate selection requires at least one candidate")
    ranked = tuple(sorted(candidates, key=candidate_rank, reverse=True))
    clusters = geometry_clusters(ranked)
    selected = ranked[0]
    selected_cluster = next(
        cluster for cluster in clusters if selected in cluster.candidates
    )
    competing = tuple(
        cluster for cluster in clusters if cluster is not selected_cluster
    )
    unresolved_competitors = tuple(
        cluster
        for cluster in competing
        if not candidate_dominates(selected, cluster.representative)
    )
    disagreement = bool(unresolved_competitors)
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
