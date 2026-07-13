from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...geometry_resolution import GeometryResolution
from ..model import AssessedCandidate


@dataclass(frozen=True)
class GeometryCluster:
    candidates: tuple[AssessedCandidate, ...]
    representative: AssessedCandidate

    def __post_init__(self) -> None:
        if not self.candidates:
            raise ValueError("geometry cluster requires candidates")
        if len({id(candidate) for candidate in self.candidates}) != len(
            self.candidates
        ):
            raise ValueError("geometry cluster candidates must be unique")
        if not any(
            candidate is self.representative for candidate in self.candidates
        ):
            raise ValueError("geometry cluster representative must belong to the cluster")


class CountResolutionOutcome(str, Enum):
    REQUESTED_COUNT = "requested_count"
    FORMAT_DEFAULT_COUNT = "format_default_count"
    LARGEST_PHYSICALLY_RESOLVED_COUNT = "largest_physically_resolved_count"
    BEST_COVERAGE_WITHOUT_PHYSICAL_RESOLUTION = (
        "best_coverage_without_physical_resolution"
    )


class SelectionConsensus(str, Enum):
    AGREED = "agreed"
    UNCONTESTED = "uncontested"
    DISAGREED = "disagreed"


@dataclass(frozen=True)
class CountResolution:
    selected_count: int
    search_order: tuple[int, ...]
    evaluated_counts: tuple[int, ...]
    stopped_after_count: int | None
    outcome: CountResolutionOutcome

    def __post_init__(self) -> None:
        if self.selected_count <= 0:
            raise ValueError("selected count must be positive")
        if not isinstance(self.outcome, CountResolutionOutcome):
            raise TypeError("count resolution requires a typed outcome")
        if (
            not self.search_order
            or not self.evaluated_counts
            or any(count <= 0 for count in (*self.search_order, *self.evaluated_counts))
        ):
            raise ValueError("count resolution requires positive search and evaluation counts")
        if len(set(self.search_order)) != len(self.search_order) or len(
            set(self.evaluated_counts)
        ) != len(self.evaluated_counts):
            raise ValueError("count resolution counts must be unique")
        if self.evaluated_counts != self.search_order[: len(self.evaluated_counts)]:
            raise ValueError("evaluated counts must be a prefix of search order")
        if self.selected_count not in self.evaluated_counts:
            raise ValueError("selected count must have been evaluated")
        if self.stopped_after_count is not None and (
            self.stopped_after_count != self.evaluated_counts[-1]
            or self.stopped_after_count != self.selected_count
        ):
            raise ValueError("count early-stop must identify the selected evaluation")
        if (
            self.outcome
            == CountResolutionOutcome.LARGEST_PHYSICALLY_RESOLVED_COUNT
        ) != (self.stopped_after_count is not None):
            raise ValueError("count resolution outcome must match early-stop facts")


@dataclass(frozen=True)
class SelectionResult:
    selected: AssessedCandidate
    ranked_candidates: tuple[AssessedCandidate, ...]
    clusters: tuple[GeometryCluster, ...]
    consensus: SelectionConsensus
    geometry_resolution: GeometryResolution
    count_resolution: CountResolution | None = None

    def __post_init__(self) -> None:
        if not self.ranked_candidates or self.selected is not self.ranked_candidates[0]:
            raise ValueError("selection must choose the first ranked candidate")
        ranked_ids = tuple(id(candidate) for candidate in self.ranked_candidates)
        if len(set(ranked_ids)) != len(ranked_ids):
            raise ValueError("ranked candidates must be unique")
        if not self.clusters:
            raise ValueError("selection requires geometry clusters")
        clustered = tuple(
            candidate
            for cluster in self.clusters
            for candidate in cluster.candidates
        )
        if len(clustered) != len(self.ranked_candidates) or {
            id(candidate) for candidate in clustered
        } != set(ranked_ids):
            raise ValueError("geometry clusters must partition ranked candidates")
        selected_cluster = next(
            (
                cluster
                for cluster in self.clusters
                if any(candidate is self.selected for candidate in cluster.candidates)
            ),
            None,
        )
        if selected_cluster is None:
            raise ValueError("selected candidate must belong to one cluster")
        if not isinstance(self.consensus, SelectionConsensus):
            raise TypeError("selection requires a typed consensus")
        alternatives_resolved = (
            self.geometry_resolution.alternative_geometries_resolved
        )
        if self.consensus == SelectionConsensus.DISAGREED and alternatives_resolved:
            raise ValueError("disagreed selection requires unresolved alternatives")
        if self.consensus != SelectionConsensus.DISAGREED and not alternatives_resolved:
            raise ValueError("selection consensus must match geometry alternatives")
        if self.consensus == SelectionConsensus.AGREED and len(selected_cluster.candidates) <= 1:
            raise ValueError("agreed selection requires equivalent candidates")
        if (
            self.consensus == SelectionConsensus.UNCONTESTED
            and len(selected_cluster.candidates) != 1
        ):
            raise ValueError("uncontested selection requires one selected-cluster candidate")
        if (
            self.count_resolution is not None
            and self.count_resolution.selected_count != self.selected.geometry.count
        ):
            raise ValueError("count resolution must match selected candidate")
