from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import math
from typing import Callable

import numpy as np

from ...configuration.photo_edges import (
    PHOTO_EDGE_SUPPORT_BIN_COUNT,
    PhotoEdgeDetectionParameters,
)
from ...formats import FrameSizeMm
from ...domain import (
    BoundaryAxis,
    BoundaryMeasurementSet,
    BoundaryPathSample,
    BoundarySide,
    EvidenceState,
    GrayBoundaryPathObservation,
    HolderBoundaryObservation,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from ...geometry.affine import (
    AFFINE_INVERTIBILITY_FLOOR,
    AffineCoordinateTransform,
)
from ...geometry.layout import is_horizontal_layout
from .scan_canvas import ScanCanvasEvidence, ScanCanvasOutcome


ROBUST_FIT_MINIMUM_POSITION_UNCERTAINTY_PX = 0.5
ROBUST_SLOPE_INTERVAL_PERCENTILES = (2.5, 97.5)
POSITION_INTERVAL_SIDE_COUNT = 2.0


class PhotoEdgeWindowState(str, Enum):
    SUPPORTED = "supported"
    NEUTRAL = "neutral"
    CONTRADICTED = "contradicted"


class PhotoEdgeCandidateDisposition(str, Enum):
    EVIDENCE_UNAVAILABLE = "evidence_unavailable"
    EQUIVALENT_CONFIDENCE_MERGED = "equivalent_confidence_merged"
    PAIR_UNAVAILABLE = "pair_unavailable"


class PhotoEdgeFact(str, Enum):
    PATHS_UNAVAILABLE = "paths_unavailable"
    INSUFFICIENT_DISTRIBUTED_SUPPORT = "insufficient_distributed_support"
    PHOTO_BAND_EVIDENCE_UNAVAILABLE = "photo_band_evidence_unavailable"
    PHOTO_BAND_CONTRADICTED = "photo_band_contradicted"
    PAIR_GEOMETRY_CONTRADICTED = "pair_geometry_contradicted"
    COMPETING_PAIRS_UNRESOLVED = "competing_pairs_unresolved"


@dataclass(frozen=True)
class PhotoEdgeSearchBand:
    band_id: str
    scan_canvas_profile_id: str
    frame_size_mm: FrameSizeMm
    work_long_axis_px: int
    work_short_axis_px: int
    nominal_top_px: float
    nominal_bottom_px: float
    maximum_center_offset_px: float
    maximum_dimension_deviation_px: float
    maximum_angle_degrees: float

    def __post_init__(self) -> None:
        if not self.band_id or not self.scan_canvas_profile_id:
            raise ValueError("photo-edge search band requires identities")
        if min(self.work_long_axis_px, self.work_short_axis_px) <= 0:
            raise ValueError("photo-edge search band requires positive extents")
        values = (
            self.nominal_top_px,
            self.nominal_bottom_px,
            self.maximum_center_offset_px,
            self.maximum_dimension_deviation_px,
            self.maximum_angle_degrees,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("photo-edge search band must be finite")
        if (
            self.nominal_top_px < 0.0
            or self.nominal_bottom_px <= self.nominal_top_px
            or self.nominal_bottom_px > float(self.work_short_axis_px)
        ):
            raise ValueError(
                "photo-edge nominal band must lie inside the scan canvas"
            )
        if (
            self.maximum_center_offset_px <= 0.0
            or self.maximum_dimension_deviation_px <= 0.0
            or self.maximum_angle_degrees <= 0.0
        ):
            raise ValueError("photo-edge search allowances must be positive")

    @property
    def nominal_height_px(self) -> float:
        return self.nominal_bottom_px - self.nominal_top_px

    @property
    def nominal_center_px(self) -> float:
        return (
            self.nominal_top_px + self.nominal_bottom_px
        ) / POSITION_INTERVAL_SIDE_COUNT

    def _angle_allowance_px(self, coordinate: float) -> float:
        center = (
            float(self.work_long_axis_px) / POSITION_INTERVAL_SIDE_COUNT
        )
        return abs(float(coordinate) - center) * math.tan(
            math.radians(self.maximum_angle_degrees)
        )

    def position_intervals_at(
        self,
        coordinate: float,
    ) -> tuple[PixelInterval, PixelInterval]:
        allowance = (
            self.maximum_center_offset_px
            + self.maximum_dimension_deviation_px
            / POSITION_INTERVAL_SIDE_COUNT
            + self._angle_allowance_px(coordinate)
        )
        canvas = PixelInterval(0.0, float(self.work_short_axis_px))
        top = PixelInterval(
            self.nominal_top_px - allowance,
            self.nominal_top_px + allowance,
        ).intersection(canvas)
        bottom = PixelInterval(
            self.nominal_bottom_px - allowance,
            self.nominal_bottom_px + allowance,
        ).intersection(canvas)
        if top is None or bottom is None:
            raise ValueError("photo-edge search interval left the scan canvas")
        return top, bottom

    def allows_pair(
        self,
        coordinate: float,
        top_position: float,
        bottom_position: float,
    ) -> bool:
        if bottom_position <= top_position:
            return False
        top_interval, bottom_interval = self.position_intervals_at(
            coordinate
        )
        height = bottom_position - top_position
        center = (
            top_position + bottom_position
        ) / POSITION_INTERVAL_SIDE_COUNT
        return bool(
            top_interval.minimum
            <= top_position
            <= top_interval.maximum
            and bottom_interval.minimum
            <= bottom_position
            <= bottom_interval.maximum
            and self.height_interval.minimum
            <= height
            <= self.height_interval.maximum
            and self.center_interval_at(coordinate).minimum
            <= center
            <= self.center_interval_at(coordinate).maximum
        )

    @property
    def height_interval(self) -> PixelInterval:
        return PixelInterval(
            self.nominal_height_px - self.maximum_dimension_deviation_px,
            self.nominal_height_px + self.maximum_dimension_deviation_px,
        )

    def center_interval_at(self, coordinate: float) -> PixelInterval:
        allowance = (
            self.maximum_center_offset_px
            + self._angle_allowance_px(coordinate)
        )
        return PixelInterval(
            self.nominal_center_px - allowance,
            self.nominal_center_px + allowance,
        )


@dataclass(frozen=True)
class PhotoEdgePhysicalSelection:
    source_band_id: str
    scan_canvas_profile_id: str
    frame_size_mm: FrameSizeMm

    def __post_init__(self) -> None:
        if not self.source_band_id or not self.scan_canvas_profile_id:
            raise ValueError(
                "photo-edge physical selection requires source identities"
            )


@dataclass(frozen=True)
class PhotoEdgePathPairProposal:
    top_path_id: ObservationId
    bottom_path_id: ObservationId
    physical_band_id: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.top_path_id,
            ObservationId,
        ) or not isinstance(
            self.bottom_path_id,
            ObservationId,
        ):
            raise TypeError(
                "photo-edge path-pair proposal requires typed path identities"
            )
        if self.top_path_id == self.bottom_path_id:
            raise ValueError(
                "photo-edge path-pair proposal requires distinct paths"
            )
        if not self.physical_band_id:
            raise ValueError(
                "photo-edge path-pair proposal requires a physical band"
            )


def photo_edge_search_bands(
    scan_canvas: ScanCanvasEvidence,
    frame_size_options: tuple[FrameSizeMm, ...],
    parameters: PhotoEdgeDetectionParameters,
    maximum_angle_degrees: float,
) -> tuple[PhotoEdgeSearchBand, ...]:
    if scan_canvas.outcome != ScanCanvasOutcome.SUPPORTED:
        return ()
    profile = scan_canvas.selected_profile
    scale = scan_canvas.pixel_scale
    assert profile is not None and scale is not None
    bands: list[PhotoEdgeSearchBand] = []
    for option in frame_size_options:
        photo_height_px = (
            option.height_mm * scale.short_axis_px_per_mm
        )
        margin_px = (
            float(scan_canvas.observed_short_axis_px) - photo_height_px
        ) / POSITION_INTERVAL_SIDE_COUNT
        bands.append(
            PhotoEdgeSearchBand(
                band_id=(
                    f"{profile.profile_id}:"
                    f"{option.width_mm:g}x{option.height_mm:g}"
                ),
                scan_canvas_profile_id=profile.profile_id,
                frame_size_mm=option,
                work_long_axis_px=scan_canvas.observed_long_axis_px,
                work_short_axis_px=scan_canvas.observed_short_axis_px,
                nominal_top_px=margin_px,
                nominal_bottom_px=margin_px + photo_height_px,
                maximum_center_offset_px=(
                    parameters.maximum_center_offset_mm
                    * scale.short_axis_px_per_mm
                ),
                maximum_dimension_deviation_px=(
                    parameters.maximum_photo_dimension_deviation_mm
                    * scale.short_axis_px_per_mm
                ),
                maximum_angle_degrees=maximum_angle_degrees,
            )
        )
    return tuple(bands)


@dataclass(frozen=True)
class SlopeInterval:
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.minimum)
            or not math.isfinite(self.maximum)
            or self.maximum < self.minimum
        ):
            raise ValueError("slope interval must be finite and ordered")

    def intersects(self, other: "SlopeInterval") -> bool:
        return max(self.minimum, other.minimum) <= min(
            self.maximum,
            other.maximum,
        )


@dataclass(frozen=True)
class RobustBoundaryFit:
    slope: float
    intercept: float
    slope_interval: SlopeInterval
    position_uncertainty_px: float
    residual_mad_px: float
    orthogonal_extent: PixelInterval
    inlier_indices: tuple[int, ...]
    sample_count: int

    def __post_init__(self) -> None:
        values = (
            self.slope,
            self.intercept,
            self.position_uncertainty_px,
            self.residual_mad_px,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("robust boundary fit requires finite measurements")
        if self.position_uncertainty_px < 0.0 or self.residual_mad_px < 0.0:
            raise ValueError("robust boundary fit uncertainty cannot be negative")
        if self.sample_count <= 0:
            raise ValueError("robust boundary fit requires samples")
        if (
            not self.inlier_indices
            or tuple(sorted(set(self.inlier_indices))) != self.inlier_indices
            or self.inlier_indices[-1] >= self.sample_count
        ):
            raise ValueError("robust boundary fit inliers must be unique sample indices")

    @property
    def inlier_ratio(self) -> float:
        return len(self.inlier_indices) / float(self.sample_count)

    def position_interval_at(self, coordinate: float) -> PixelInterval:
        predictions = (
            self.intercept + self.slope_interval.minimum * float(coordinate),
            self.intercept + self.slope_interval.maximum * float(coordinate),
        )
        return PixelInterval(
            min(predictions) - self.position_uncertainty_px,
            max(predictions) + self.position_uncertainty_px,
        )


@dataclass(frozen=True)
class PhotoEdgeLocalEvidence:
    sample_index: int
    state: PhotoEdgeWindowState
    intensity_effect: float
    texture_effect: float
    gradient_effect: float

    def __post_init__(self) -> None:
        if self.sample_index < 0:
            raise ValueError("photo-edge local evidence index cannot be negative")
        if not isinstance(self.state, PhotoEdgeWindowState):
            raise TypeError("photo-edge local evidence requires a typed state")
        effects = (
            self.intensity_effect,
            self.texture_effect,
            self.gradient_effect,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in effects):
            raise ValueError("photo-edge local effects must be finite and non-negative")


@dataclass(frozen=True)
class PhotoBandEvidence:
    top_supported_window_count: int
    top_support_distribution_bins: int
    bottom_supported_window_count: int
    bottom_support_distribution_bins: int
    state: EvidenceState

    def __post_init__(self) -> None:
        counts = (
            self.top_supported_window_count,
            self.top_support_distribution_bins,
            self.bottom_supported_window_count,
            self.bottom_support_distribution_bins,
        )
        if any(value < 0 for value in counts):
            raise ValueError(
                "photo-band support counts cannot be negative"
            )
        if self.state not in {
            EvidenceState.SUPPORTED,
            EvidenceState.UNAVAILABLE,
            EvidenceState.CONTRADICTED,
        }:
            raise ValueError(
                "photo-band evidence uses current evidence states only"
            )
        if self.state == EvidenceState.SUPPORTED and any(
            value <= 0 for value in counts
        ):
            raise ValueError(
                "supported photo-band evidence requires both distributed sides"
            )


@dataclass(frozen=True)
class PhotoEdgeCandidateSummary:
    disposition: PhotoEdgeCandidateDisposition
    facts: tuple[PhotoEdgeFact, ...]
    physical_band_ids: tuple[str, ...]
    observed_section_counts: tuple[int, ...]
    candidate_count: int

    def __post_init__(self) -> None:
        if not isinstance(
            self.disposition,
            PhotoEdgeCandidateDisposition,
        ):
            raise TypeError(
                "photo-edge candidate summary requires a typed disposition"
            )
        if any(not isinstance(fact, PhotoEdgeFact) for fact in self.facts):
            raise TypeError(
                "photo-edge candidate summary facts must be typed"
            )
        if tuple(
            fact for fact in PhotoEdgeFact if fact in self.facts
        ) != self.facts:
            raise ValueError(
                "photo-edge candidate summary facts must be ordered and unique"
            )
        if (
            len(set(self.physical_band_ids))
            != len(self.physical_band_ids)
            or any(not item for item in self.physical_band_ids)
        ):
            raise ValueError(
                "photo-edge candidate summary physical bands must be unique"
            )
        if (
            not self.observed_section_counts
            or tuple(
                sorted(set(self.observed_section_counts))
            )
            != self.observed_section_counts
            or any(count <= 0 for count in self.observed_section_counts)
        ):
            raise ValueError(
                "photo-edge candidate summary requires positive section counts"
            )
        if self.candidate_count <= 0:
            raise ValueError(
                "photo-edge candidate summary count must be positive"
            )
        if (
            self.disposition
            == PhotoEdgeCandidateDisposition.EVIDENCE_UNAVAILABLE
        ) != bool(self.facts):
            raise ValueError(
                "only unavailable candidate summaries carry failure facts"
            )


@dataclass(frozen=True)
class PhotoEdgeCandidate:
    path: GrayBoundaryPathObservation
    fit: RobustBoundaryFit
    local_evidence: tuple[PhotoEdgeLocalEvidence, ...]
    physical_band_ids: tuple[str, ...]
    state: EvidenceState
    facts: tuple[PhotoEdgeFact, ...]
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.path.axis != BoundaryAxis.SHORT:
            raise ValueError("photo-edge candidate must use the short axis")
        if self.fit.sample_count != len(self.path.samples):
            raise ValueError("photo-edge fit must cover the candidate path")
        if len(self.local_evidence) != len(self.path.samples):
            raise ValueError("photo-edge local evidence must cover every path sample")
        if tuple(item.sample_index for item in self.local_evidence) != tuple(
            range(len(self.path.samples))
        ):
            raise ValueError("photo-edge local evidence must preserve sample order")
        if (
            len(set(self.physical_band_ids))
            != len(self.physical_band_ids)
            or any(not item for item in self.physical_band_ids)
        ):
            raise ValueError(
                "photo-edge candidate physical bands must be unique identities"
            )
        if self.state == EvidenceState.SUPPORTED:
            if self.facts:
                raise ValueError(
                    "supported photo-edge candidate cannot carry failure facts"
                )
        elif self.state == EvidenceState.UNAVAILABLE:
            if not self.facts:
                raise ValueError(
                    "unavailable photo-edge candidate requires typed facts"
                )
        else:
            raise ValueError(
                "photo-edge candidate is retained or supported, never contradicted"
            )
        if any(not isinstance(fact, PhotoEdgeFact) for fact in self.facts):
            raise TypeError("photo-edge candidate facts must be typed")
        if self.provenance.root_measurement != MeasurementIdentity.PHOTO_EDGES:
            raise ValueError("photo-edge candidate requires photo-edge provenance")
        if (
            self.path.provenance.observation_id
            not in self.provenance.boundary_anchors
        ):
            raise ValueError(
                "photo-edge candidate must anchor its representative path"
            )

    @property
    def observation_id(self) -> ObservationId:
        return self.provenance.observation_id

    @property
    def supported_window_indices(self) -> tuple[int, ...]:
        return tuple(
            item.sample_index
            for item in self.local_evidence
            if item.state == PhotoEdgeWindowState.SUPPORTED
        )


@dataclass(frozen=True)
class PhotoEdgePairHypothesis:
    top_candidate_id: ObservationId
    bottom_candidate_id: ObservationId
    physical_band_id: str | None
    common_support: PixelInterval | None
    photo_height_px: PixelInterval | None
    separation_drift_ratio: float | None
    photo_band_evidence: PhotoBandEvidence
    state: EvidenceState
    facts: tuple[PhotoEdgeFact, ...]
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.top_candidate_id == self.bottom_candidate_id:
            raise ValueError("photo-edge pair requires two distinct candidates")
        if not isinstance(self.photo_band_evidence, PhotoBandEvidence):
            raise TypeError(
                "photo-edge pair requires typed photo-band evidence"
            )
        if self.physical_band_id is not None and not self.physical_band_id:
            raise ValueError("photo-edge physical band identity cannot be empty")
        if self.state == EvidenceState.SUPPORTED:
            if self.facts:
                raise ValueError("supported photo-edge pair cannot carry failure facts")
            if (
                self.common_support is None
                or self.photo_height_px is None
                or self.separation_drift_ratio is None
            ):
                raise ValueError("supported photo-edge pair requires complete geometry")
            if self.photo_band_evidence.state != EvidenceState.SUPPORTED:
                raise ValueError(
                    "supported photo-edge pair requires supported photo-band evidence"
                )
        elif not self.facts:
            raise ValueError("unresolved photo-edge pair requires typed facts")
        if self.state not in {
            EvidenceState.SUPPORTED,
            EvidenceState.UNAVAILABLE,
            EvidenceState.CONTRADICTED,
        }:
            raise ValueError("photo-edge pair uses current evidence states only")
        if any(not isinstance(fact, PhotoEdgeFact) for fact in self.facts):
            raise TypeError("photo-edge pair facts must be typed")
        if len(set(self.facts)) != len(self.facts):
            raise ValueError("photo-edge pair facts must be unique")
        if self.separation_drift_ratio is not None and (
            not math.isfinite(self.separation_drift_ratio)
            or self.separation_drift_ratio < 0.0
        ):
            raise ValueError("photo-edge separation drift must be non-negative")

    @property
    def observation_id(self) -> ObservationId:
        return self.provenance.observation_id


@dataclass(frozen=True)
class PhotoEdgePairEvidence:
    candidates: tuple[PhotoEdgeCandidate, ...]
    candidate_summaries: tuple[PhotoEdgeCandidateSummary, ...]
    search_bands: tuple[PhotoEdgeSearchBand, ...]
    hypotheses: tuple[PhotoEdgePairHypothesis, ...]
    selected_pair_id: ObservationId | None
    physical_selection: PhotoEdgePhysicalSelection | None
    state: EvidenceState
    facts: tuple[PhotoEdgeFact, ...]
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        candidate_ids = tuple(item.observation_id for item in self.candidates)
        band_ids = tuple(item.band_id for item in self.search_bands)
        hypothesis_ids = tuple(item.observation_id for item in self.hypotheses)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("photo-edge candidate identities must be unique")
        summary_keys = tuple(
            (
                item.disposition,
                item.facts,
                item.physical_band_ids,
            )
            for item in self.candidate_summaries
        )
        if len(set(summary_keys)) != len(summary_keys):
            raise ValueError(
                "photo-edge candidate summaries must be canonical"
            )
        if len(set(hypothesis_ids)) != len(hypothesis_ids):
            raise ValueError("photo-edge hypothesis identities must be unique")
        if len(set(band_ids)) != len(band_ids):
            raise ValueError("photo-edge search-band identities must be unique")
        if self.search_bands and any(
            not candidate.physical_band_ids
            or not set(candidate.physical_band_ids).issubset(band_ids)
            for candidate in self.candidates
        ):
            raise ValueError(
                "source photo-edge candidates must trace to physical bands"
            )
        if any(
            item.top_candidate_id not in candidate_ids
            or item.bottom_candidate_id not in candidate_ids
            for item in self.hypotheses
        ):
            raise ValueError("photo-edge hypotheses must reference retained candidates")
        if any(
            item.physical_band_id is not None
            and item.physical_band_id not in band_ids
            for item in self.hypotheses
        ):
            raise ValueError(
                "photo-edge hypotheses must reference retained physical bands"
            )
        candidate_by_id = {
            candidate.observation_id: candidate
            for candidate in self.candidates
        }
        if any(
            item.physical_band_id is not None
            and (
                item.physical_band_id
                not in candidate_by_id[
                    item.top_candidate_id
                ].physical_band_ids
                or item.physical_band_id
                not in candidate_by_id[
                    item.bottom_candidate_id
                ].physical_band_ids
            )
            for item in self.hypotheses
        ):
            raise ValueError(
                "photo-edge hypotheses must preserve candidate physical bands"
            )
        selected = tuple(
            item
            for item in self.hypotheses
            if item.observation_id == self.selected_pair_id
        )
        if self.state == EvidenceState.SUPPORTED:
            if len(selected) != 1 or selected[0].state != EvidenceState.SUPPORTED:
                raise ValueError("supported photo-edge evidence requires one selected pair")
            if self.facts:
                raise ValueError("supported photo-edge evidence cannot carry failure facts")
            selected_band_id = selected[0].physical_band_id
            if self.search_bands:
                if (
                    selected_band_id is None
                    or self.physical_selection is None
                ):
                    raise ValueError(
                        "supported source physical pair requires its selection"
                    )
                if (
                    selected_band_id
                    != self.physical_selection.source_band_id
                ):
                    raise ValueError(
                        "physical selection must identify the selected source band"
                    )
                source_band = next(
                    (
                        band
                        for band in self.search_bands
                        if band.band_id == selected_band_id
                    ),
                    None,
                )
                if source_band is not None and (
                    source_band.scan_canvas_profile_id
                    != self.physical_selection.scan_canvas_profile_id
                    or source_band.frame_size_mm
                    != self.physical_selection.frame_size_mm
                ):
                    raise ValueError(
                        "physical selection must preserve source-band facts"
                    )
            elif selected_band_id is not None:
                raise ValueError(
                    "mapped or image-only pair cannot carry a source band"
                )
        else:
            if selected:
                raise ValueError("unresolved photo-edge evidence cannot select a pair")
            if self.physical_selection is not None:
                raise ValueError(
                    "unresolved photo-edge evidence cannot select physical facts"
                )
            if not self.facts:
                raise ValueError("unresolved photo-edge evidence requires typed facts")
        if self.state not in {
            EvidenceState.SUPPORTED,
            EvidenceState.UNAVAILABLE,
            EvidenceState.CONTRADICTED,
        }:
            raise ValueError("photo-edge evidence uses current evidence states only")
        if any(not isinstance(fact, PhotoEdgeFact) for fact in self.facts):
            raise TypeError("photo-edge evidence facts must be typed")
        if len(set(self.facts)) != len(self.facts):
            raise ValueError("photo-edge evidence facts must be unique")
        if self.provenance.root_measurement != MeasurementIdentity.PHOTO_EDGES:
            raise ValueError("photo-edge pair evidence requires photo-edge provenance")

    @property
    def observation_id(self) -> ObservationId:
        return self.provenance.observation_id

    @property
    def selected_pair(self) -> PhotoEdgePairHypothesis | None:
        if self.selected_pair_id is None:
            return None
        return next(
            item
            for item in self.hypotheses
            if item.observation_id == self.selected_pair_id
        )

    def candidate(self, observation_id: ObservationId) -> PhotoEdgeCandidate:
        return next(
            item for item in self.candidates if item.observation_id == observation_id
        )

    @property
    def selected_candidates(
        self,
    ) -> tuple[PhotoEdgeCandidate, PhotoEdgeCandidate] | None:
        pair = self.selected_pair
        if pair is None:
            return None
        return (
            self.candidate(pair.top_candidate_id),
            self.candidate(pair.bottom_candidate_id),
        )


@dataclass(frozen=True)
class PhotoEdgeInnerLine:
    slope: float
    intercept: float
    slope_interval: SlopeInterval
    position_uncertainty_px: float

    def position_interval_at(self, coordinate: float) -> PixelInterval:
        positions = (
            self.intercept + self.slope_interval.minimum * float(coordinate),
            self.intercept + self.slope_interval.maximum * float(coordinate),
        )
        return PixelInterval(
            min(positions) - self.position_uncertainty_px,
            max(positions) + self.position_uncertainty_px,
        )


def _ordered_facts(facts: set[PhotoEdgeFact]) -> tuple[PhotoEdgeFact, ...]:
    return tuple(fact for fact in PhotoEdgeFact if fact in facts)


def _line_fit(
    coordinates: np.ndarray,
    positions: np.ndarray,
) -> tuple[float, float]:
    if coordinates.size <= 1:
        return 0.0, float(positions[0])
    center = float(np.mean(coordinates))
    denominator = float(np.sum((coordinates - center) ** 2))
    if denominator <= 0.0:
        return 0.0, float(np.median(positions))
    position_center = float(np.mean(positions))
    slope = float(
        np.sum((coordinates - center) * (positions - position_center))
        / denominator
    )
    return slope, position_center - slope * center


def _robust_fit(
    path: GrayBoundaryPathObservation,
    parameters: PhotoEdgeDetectionParameters,
    *,
    fixed_inlier_indices: tuple[int, ...] | None = None,
) -> RobustBoundaryFit:
    coordinates = np.asarray(
        [sample.orthogonal_interval.midpoint for sample in path.samples],
        dtype=np.float64,
    )
    positions = np.asarray(
        [sample.position.midpoint for sample in path.samples],
        dtype=np.float64,
    )
    if fixed_inlier_indices is None:
        pairwise_slopes = [
            float((positions[right] - positions[left]) / (coordinates[right] - coordinates[left]))
            for left in range(len(path.samples))
            for right in range(left + 1, len(path.samples))
            if coordinates[right] != coordinates[left]
        ]
        initial_slope = float(np.median(pairwise_slopes)) if pairwise_slopes else 0.0
        initial_intercept = float(np.median(positions - initial_slope * coordinates))
        residuals = positions - (initial_intercept + initial_slope * coordinates)
        residual_center = float(np.median(residuals))
        residual_mad = float(np.median(np.abs(residuals - residual_center)))
        position_half_width = max(
            0.5 * (sample.position.maximum - sample.position.minimum)
            for sample in path.samples
        )
        tolerance = max(
            position_half_width,
            parameters.robust_mad_multiplier
            * max(
                residual_mad,
                ROBUST_FIT_MINIMUM_POSITION_UNCERTAINTY_PX,
            ),
        )
        inliers = tuple(
            int(index)
            for index, residual in enumerate(residuals)
            if abs(float(residual) - residual_center) <= tolerance
        )
        if len(inliers) < min(2, len(path.samples)):
            ranked = np.argsort(np.abs(residuals - residual_center))
            inliers = tuple(sorted(int(index) for index in ranked[:2]))
    else:
        inliers = fixed_inlier_indices
        if not inliers:
            raise ValueError("mapped robust fit requires retained inliers")

    inlier_coordinates = coordinates[list(inliers)]
    inlier_positions = positions[list(inliers)]
    slope, intercept = _line_fit(inlier_coordinates, inlier_positions)
    fitted_residuals = inlier_positions - (
        intercept + slope * inlier_coordinates
    )
    residual_center = float(np.median(fitted_residuals))
    residual_mad = float(
        np.median(np.abs(fitted_residuals - residual_center))
    )
    position_half_width = float(
        np.median(
            [
                0.5
                * (
                    path.samples[index].position.maximum
                    - path.samples[index].position.minimum
                )
                for index in inliers
            ]
        )
    )
    position_uncertainty = max(
        ROBUST_FIT_MINIMUM_POSITION_UNCERTAINTY_PX,
        position_half_width,
        float(np.median(np.abs(fitted_residuals))),
        parameters.robust_mad_multiplier * residual_mad,
    )
    pairwise_inlier_slopes = np.asarray(
        [
            float(
                (inlier_positions[right] - inlier_positions[left])
                / (inlier_coordinates[right] - inlier_coordinates[left])
            )
            for left in range(len(inliers))
            for right in range(left + 1, len(inliers))
            if inlier_coordinates[right] != inlier_coordinates[left]
        ],
        dtype=np.float64,
    )
    baseline = max(
        1.0,
        float(np.max(inlier_coordinates) - np.min(inlier_coordinates)),
    )
    slope_floor = position_uncertainty / baseline
    if pairwise_inlier_slopes.size:
        lower, upper = np.percentile(
            pairwise_inlier_slopes,
            ROBUST_SLOPE_INTERVAL_PERCENTILES,
        )
        slope_interval = SlopeInterval(
            min(float(lower), slope - slope_floor),
            max(float(upper), slope + slope_floor),
        )
    else:
        slope_interval = SlopeInterval(
            slope - slope_floor,
            slope + slope_floor,
        )
    return RobustBoundaryFit(
        slope=slope,
        intercept=intercept,
        slope_interval=slope_interval,
        position_uncertainty_px=position_uncertainty,
        residual_mad_px=residual_mad,
        orthogonal_extent=PixelInterval(
            min(path.samples[index].orthogonal_interval.minimum for index in inliers),
            max(path.samples[index].orthogonal_interval.maximum for index in inliers),
        ),
        inlier_indices=inliers,
        sample_count=len(path.samples),
    )


def photo_edge_inner_line(
    candidate: PhotoEdgeCandidate,
    side: BoundarySide,
) -> PhotoEdgeInnerLine:
    if side not in {BoundarySide.TOP, BoundarySide.BOTTOM}:
        raise ValueError("photo-edge inner line requires top or bottom")
    coordinates = np.asarray(
        [
            candidate.path.samples[index].orthogonal_interval.midpoint
            for index in candidate.fit.inlier_indices
        ],
        dtype=np.float64,
    )
    positions = np.asarray(
        [
            (
                candidate.path.samples[index].position.maximum
                if side == BoundarySide.TOP
                else candidate.path.samples[index].position.minimum
            )
            for index in candidate.fit.inlier_indices
        ],
        dtype=np.float64,
    )
    slope, intercept = _line_fit(coordinates, positions)
    residuals = positions - (intercept + slope * coordinates)
    return PhotoEdgeInnerLine(
        slope=slope,
        intercept=intercept,
        slope_interval=candidate.fit.slope_interval,
        position_uncertainty_px=max(
            candidate.fit.position_uncertainty_px,
            float(np.median(np.abs(residuals))),
        ),
    )


def _patch_statistics(patch: np.ndarray) -> tuple[float, float, float]:
    if not patch.size:
        return 0.0, 0.0, 0.0
    values = np.asarray(patch, dtype=np.float32)
    center = float(np.median(values))
    mad = float(np.median(np.abs(values - center)))
    horizontal = np.abs(np.diff(values, axis=1)) if values.shape[1] > 1 else np.zeros((1,))
    vertical = np.abs(np.diff(values, axis=0)) if values.shape[0] > 1 else np.zeros((1,))
    texture = float(
        np.median(
            np.concatenate(
                (
                    horizontal.reshape(-1),
                    vertical.reshape(-1),
                )
            )
        )
    )
    return center, mad, texture


def _local_evidence(
    gray_work: np.ndarray,
    path: GrayBoundaryPathObservation,
    parameters: PhotoEdgeDetectionParameters,
) -> tuple[PhotoEdgeLocalEvidence, ...]:
    height, width = gray_work.shape
    window = _local_window_depth(height, parameters)
    evidence: list[PhotoEdgeLocalEvidence] = []
    for index, sample in enumerate(path.samples):
        left = max(0, min(width - 1, int(math.floor(sample.orthogonal_interval.minimum))))
        right = max(left + 1, min(width, int(math.ceil(sample.orthogonal_interval.maximum))))
        position = max(1, min(height - 1, int(round(sample.position.midpoint))))
        lower = gray_work[max(0, position - window) : position, left:right]
        upper = gray_work[position : min(height, position + window), left:right]
        if not lower.size or not upper.size:
            evidence.append(
                PhotoEdgeLocalEvidence(
                    sample_index=index,
                    state=PhotoEdgeWindowState.NEUTRAL,
                    intensity_effect=0.0,
                    texture_effect=0.0,
                    gradient_effect=0.0,
                )
            )
            continue
        lower_center, lower_mad, lower_texture = _patch_statistics(lower)
        upper_center, upper_mad, upper_texture = _patch_statistics(upper)
        noise = max(1.0, lower_mad + upper_mad)
        boundary_gradient = float(
            np.median(
                np.abs(
                    gray_work[position, left:right].astype(np.float32)
                    - gray_work[position - 1, left:right].astype(np.float32)
                )
            )
        )
        intensity_effect = abs(upper_center - lower_center) / noise
        texture_effect = abs(upper_texture - lower_texture) / noise
        gradient_effect = boundary_gradient / noise
        strongest = max(intensity_effect, texture_effect, gradient_effect)
        evidence.append(
            PhotoEdgeLocalEvidence(
                sample_index=index,
                state=(
                    PhotoEdgeWindowState.SUPPORTED
                    if strongest >= parameters.minimum_local_effect
                    else PhotoEdgeWindowState.NEUTRAL
                ),
                intensity_effect=intensity_effect,
                texture_effect=texture_effect,
                gradient_effect=gradient_effect,
            )
        )
    return tuple(evidence)


def _local_window_depth(
    short_axis_length: int,
    parameters: PhotoEdgeDetectionParameters,
) -> int:
    if short_axis_length <= 0:
        raise ValueError("photo-edge short-axis length must be positive")
    return max(
        parameters.local_window_min_px,
        int(round(short_axis_length * parameters.local_window_height_ratio)),
    )


def _candidate(
    gray_work: np.ndarray,
    path: GrayBoundaryPathObservation,
    parameters: PhotoEdgeDetectionParameters,
    physical_band_ids: tuple[str, ...],
) -> PhotoEdgeCandidate:
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(
            f"photo_edge_candidate:{path.provenance.observation_id}"
        ),
        dependencies=tuple(
            dict.fromkeys(
                (
                    path.provenance.root_measurement,
                    *path.provenance.dependencies,
                    MeasurementIdentity.GRAY_WORK,
                )
            )
        ),
        description="source-coordinate photo-edge candidate",
        boundary_anchors=(path.provenance.observation_id,),
    )
    fit = _robust_fit(path, parameters)
    local_evidence = _local_evidence(gray_work, path, parameters)
    facts: set[PhotoEdgeFact] = set()
    if (
        len(fit.inlier_indices) < parameters.minimum_fit_inliers
        or fit.inlier_ratio < parameters.minimum_inlier_ratio
        or _occupied_sample_bins(
            path,
            fit.inlier_indices,
            fit.orthogonal_extent,
        )
        < parameters.minimum_support_distribution_bins
    ):
        facts.add(PhotoEdgeFact.INSUFFICIENT_DISTRIBUTED_SUPPORT)
    supported_windows = tuple(
        item.sample_index
        for item in local_evidence
        if item.state == PhotoEdgeWindowState.SUPPORTED
    )
    if (
        len(supported_windows) < parameters.minimum_supported_windows
        or _occupied_sample_bins(
            path,
            supported_windows,
            fit.orthogonal_extent,
        )
        < parameters.minimum_support_distribution_bins
    ):
        facts.add(PhotoEdgeFact.PHOTO_BAND_EVIDENCE_UNAVAILABLE)
    return PhotoEdgeCandidate(
        path=path,
        fit=fit,
        local_evidence=local_evidence,
        physical_band_ids=physical_band_ids,
        state=(
            EvidenceState.SUPPORTED
            if not facts
            else EvidenceState.UNAVAILABLE
        ),
        facts=_ordered_facts(facts),
        provenance=provenance,
    )


def _candidates_have_equivalent_confidence(
    left: PhotoEdgeCandidate,
    right: PhotoEdgeCandidate,
) -> bool:
    common = left.fit.orthogonal_extent.intersection(
        right.fit.orthogonal_extent
    )
    if (
        common is None
        or common.maximum <= common.minimum
        or not left.fit.slope_interval.intersects(right.fit.slope_interval)
    ):
        return False
    return all(
        left.fit.position_interval_at(coordinate).intersection(
            right.fit.position_interval_at(coordinate)
        )
        is not None
        for coordinate in (
            common.minimum,
            common.midpoint,
            common.maximum,
        )
    )


def _candidate_representative_key(
    candidate: PhotoEdgeCandidate,
) -> tuple[object, ...]:
    return (
        -int(candidate.state == EvidenceState.SUPPORTED),
        -len(candidate.fit.inlier_indices),
        -len(candidate.supported_window_indices),
        -candidate.fit.inlier_ratio,
        candidate.fit.position_uncertainty_px,
        candidate.fit.residual_mad_px,
        str(candidate.observation_id),
    )


def _merge_equivalent_candidates(
    candidates: tuple[PhotoEdgeCandidate, ...],
) -> tuple[PhotoEdgeCandidate, ...]:
    groups: list[list[PhotoEdgeCandidate]] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (
            item.path.position.midpoint,
            str(item.observation_id),
        ),
    ):
        group = next(
            (
                existing
                for existing in groups
                if all(
                    _candidates_have_equivalent_confidence(
                        candidate,
                        member,
                    )
                    for member in existing
                )
            ),
            None,
        )
        if group is None:
            groups.append([candidate])
        else:
            group.append(candidate)

    merged: list[PhotoEdgeCandidate] = []
    for group in groups:
        representative = min(group, key=_candidate_representative_key)
        if len(group) == 1:
            merged.append(representative)
            continue
        provenance = replace(
            representative.provenance,
            dependencies=tuple(
                dict.fromkeys(
                    dependency
                    for candidate in group
                    for dependency in candidate.provenance.dependencies
                )
            ),
            description=(
                "source-coordinate photo-edge candidate from "
                "equivalent confidence tracks"
            ),
            boundary_anchors=tuple(
                sorted(
                    {
                        anchor
                        for candidate in group
                        for anchor in candidate.provenance.boundary_anchors
                    },
                    key=str,
                )
            ),
        )
        merged.append(
            replace(
                representative,
                physical_band_ids=tuple(
                    sorted(
                        {
                            band_id
                            for candidate in group
                            for band_id in candidate.physical_band_ids
                        }
                    )
                ),
                provenance=provenance,
            )
        )
    return tuple(merged)


def _occupied_sample_bins(
    path: GrayBoundaryPathObservation,
    indices: tuple[int, ...],
    common: PixelInterval,
) -> int:
    length = max(1.0, common.maximum - common.minimum)
    return len(
        {
            min(
                PHOTO_EDGE_SUPPORT_BIN_COUNT - 1,
                max(
                    0,
                    int(
                        float(PHOTO_EDGE_SUPPORT_BIN_COUNT)
                        * (
                            path.samples[index].orthogonal_interval.midpoint
                            - common.minimum
                        )
                        / length
                    ),
                ),
            )
            for index in indices
            if common.minimum
            <= path.samples[index].orthogonal_interval.midpoint
            <= common.maximum
        }
    )


def _occupied_bins(
    candidate: PhotoEdgeCandidate,
    indices: tuple[int, ...],
    common: PixelInterval,
) -> int:
    return _occupied_sample_bins(candidate.path, indices, common)


def _photo_side_structure_effect(
    gray_work: np.ndarray,
    sample: BoundaryPathSample,
    side: BoundarySide,
    window_depth: int,
) -> float:
    if side not in {BoundarySide.TOP, BoundarySide.BOTTOM}:
        raise ValueError(
            "photo-side structure requires a top or bottom role"
        )
    if window_depth <= 0:
        raise ValueError(
            "photo-side structure requires a positive window depth"
        )
    height, width = gray_work.shape
    left = max(
        0,
        min(
            width - 1,
            int(math.floor(sample.orthogonal_interval.minimum)),
        ),
    )
    right = max(
        left + 1,
        min(
            width,
            int(math.ceil(sample.orthogonal_interval.maximum)),
        ),
    )
    position = max(
        1,
        min(height - 1, int(round(sample.position.midpoint))),
    )
    above = gray_work[
        max(0, position - window_depth) : position,
        left:right,
    ]
    below = gray_work[
        position : min(height, position + window_depth),
        left:right,
    ]
    photo_patch, exterior_patch = (
        (below, above)
        if side == BoundarySide.TOP
        else (above, below)
    )
    if not photo_patch.size or not exterior_patch.size:
        return 0.0
    _, photo_mad, photo_texture = _patch_statistics(photo_patch)
    _, exterior_mad, exterior_texture = _patch_statistics(
        exterior_patch
    )
    photo_structure = max(photo_mad, photo_texture)
    exterior_structure = max(
        1.0,
        exterior_mad,
        exterior_texture,
    )
    return photo_structure / exterior_structure


def _photo_band_evidence(
    gray_work: np.ndarray,
    top: PhotoEdgeCandidate,
    bottom: PhotoEdgeCandidate,
    common: PixelInterval | None,
    parameters: PhotoEdgeDetectionParameters,
) -> PhotoBandEvidence:
    if common is None:
        return PhotoBandEvidence(
            top_supported_window_count=0,
            top_support_distribution_bins=0,
            bottom_supported_window_count=0,
            bottom_support_distribution_bins=0,
            state=EvidenceState.UNAVAILABLE,
        )
    window_depth = _local_window_depth(
        gray_work.shape[0],
        parameters,
    )
    support: list[tuple[int, int]] = []
    for candidate, side in (
        (top, BoundarySide.TOP),
        (bottom, BoundarySide.BOTTOM),
    ):
        indices = tuple(
            index
            for index in candidate.fit.inlier_indices
            if _photo_side_structure_effect(
                gray_work,
                candidate.path.samples[index],
                side,
                window_depth,
            )
            >= parameters.minimum_local_effect
        )
        support.append(
            (
                len(indices),
                _occupied_bins(candidate, indices, common),
            )
        )
    top_support, bottom_support = support
    supported = all(
        window_count >= parameters.minimum_supported_windows
        and distribution_bins
        >= parameters.minimum_support_distribution_bins
        for window_count, distribution_bins in support
    )
    return PhotoBandEvidence(
        top_supported_window_count=top_support[0],
        top_support_distribution_bins=top_support[1],
        bottom_supported_window_count=bottom_support[0],
        bottom_support_distribution_bins=bottom_support[1],
        state=(
            EvidenceState.SUPPORTED
            if supported
            else EvidenceState.UNAVAILABLE
        ),
    )


def _independent_holder_contradiction(
    candidate: PhotoEdgeCandidate,
    side: BoundarySide,
    holder_boundaries: tuple[HolderBoundaryObservation, ...],
) -> bool:
    boundary = next(
        (item for item in holder_boundaries if item.side == side),
        None,
    )
    if boundary is None:
        return False
    supporting_ids = {
        path.provenance.observation_id for path in boundary.supporting_paths
    }
    if candidate.path.provenance.observation_id in supporting_ids:
        return False
    if side == BoundarySide.TOP:
        return candidate.path.position.maximum < boundary.position.minimum
    return candidate.path.position.minimum > boundary.position.maximum


def _geometry_metrics(
    top: PhotoEdgeCandidate,
    bottom: PhotoEdgeCandidate,
) -> tuple[
    PixelInterval | None,
    PixelInterval | None,
    float | None,
]:
    common = top.fit.orthogonal_extent.intersection(bottom.fit.orthogonal_extent)
    if common is None or common.maximum <= common.minimum:
        return None, None, None
    coordinate = common.midpoint
    top_position = top.fit.position_interval_at(coordinate)
    bottom_position = bottom.fit.position_interval_at(coordinate)
    if bottom_position.minimum <= top_position.maximum:
        return common, None, None
    height = bottom_position.minus(top_position)
    if height.minimum <= 0.0:
        return common, None, None
    separation_drift = (
        abs(bottom.fit.slope - top.fit.slope)
        * (common.maximum - common.minimum)
        / height.midpoint
    )
    return common, height, separation_drift


def _interval_is_contained(
    interval: PixelInterval,
    container: PixelInterval,
) -> bool:
    return bool(
        container.minimum <= interval.minimum
        and interval.maximum <= container.maximum
    )


def _pair_center_interval_at(
    top: PhotoEdgeCandidate,
    bottom: PhotoEdgeCandidate,
    coordinate: float,
) -> PixelInterval:
    top_position = top.fit.position_interval_at(coordinate)
    bottom_position = bottom.fit.position_interval_at(coordinate)
    return PixelInterval(
        (top_position.minimum + bottom_position.minimum)
        / POSITION_INTERVAL_SIDE_COUNT,
        (top_position.maximum + bottom_position.maximum)
        / POSITION_INTERVAL_SIDE_COUNT,
    )


def _physical_band_assessment(
    top: PhotoEdgeCandidate,
    bottom: PhotoEdgeCandidate,
    common: PixelInterval,
    height: PixelInterval,
    band: PhotoEdgeSearchBand,
) -> tuple[EvidenceState, tuple[PhotoEdgeFact, ...]]:
    allowed_height = band.height_interval
    if height.intersection(allowed_height) is None:
        return (
            EvidenceState.CONTRADICTED,
            (PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED,),
        )
    state = EvidenceState.SUPPORTED
    facts: set[PhotoEdgeFact] = set()
    if not _interval_is_contained(height, allowed_height):
        state = EvidenceState.UNAVAILABLE
        facts.add(PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED)
    maximum_slope = math.tan(math.radians(band.maximum_angle_degrees))
    if max(abs(top.fit.slope), abs(bottom.fit.slope)) > maximum_slope:
        return (
            EvidenceState.CONTRADICTED,
            (PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED,),
        )
    for coordinate in (common.minimum, common.maximum):
        observed_center = _pair_center_interval_at(
            top,
            bottom,
            coordinate,
        )
        allowed_center = band.center_interval_at(coordinate)
        if observed_center.intersection(allowed_center) is None:
            return (
                EvidenceState.CONTRADICTED,
                (PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED,),
            )
        if not _interval_is_contained(observed_center, allowed_center):
            state = EvidenceState.UNAVAILABLE
            facts.add(PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED)
    return state, _ordered_facts(facts)


def _hypothesis(
    top: PhotoEdgeCandidate,
    bottom: PhotoEdgeCandidate,
    holder_boundaries: tuple[HolderBoundaryObservation, ...],
    parameters: PhotoEdgeDetectionParameters,
    photo_band_support_depth_px: float,
    photo_band_evidence: PhotoBandEvidence,
    physical_band: PhotoEdgeSearchBand | None = None,
) -> PhotoEdgePairHypothesis:
    if (
        not math.isfinite(photo_band_support_depth_px)
        or photo_band_support_depth_px < 0.0
    ):
        raise ValueError("photo-band support depth must be finite and non-negative")
    if not isinstance(photo_band_evidence, PhotoBandEvidence):
        raise TypeError(
            "photo-edge hypothesis requires typed photo-band evidence"
        )
    common, height, separation_drift = _geometry_metrics(top, bottom)
    facts: set[PhotoEdgeFact] = set()
    state = EvidenceState.UNAVAILABLE
    if common is None or height is None:
        facts.add(PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED)
        state = EvidenceState.CONTRADICTED
    else:
        if (
            height.minimum
            <= POSITION_INTERVAL_SIDE_COUNT * photo_band_support_depth_px
        ):
            facts.add(PhotoEdgeFact.PHOTO_BAND_EVIDENCE_UNAVAILABLE)
        if photo_band_evidence.state == EvidenceState.UNAVAILABLE:
            facts.add(PhotoEdgeFact.PHOTO_BAND_EVIDENCE_UNAVAILABLE)
        elif photo_band_evidence.state == EvidenceState.CONTRADICTED:
            facts.add(PhotoEdgeFact.PHOTO_BAND_CONTRADICTED)
            state = EvidenceState.CONTRADICTED
        for candidate in (top, bottom):
            if (
                len(candidate.fit.inlier_indices) < parameters.minimum_fit_inliers
                or candidate.fit.inlier_ratio < parameters.minimum_inlier_ratio
                or _occupied_bins(
                    candidate,
                    candidate.fit.inlier_indices,
                    common,
                )
                < parameters.minimum_support_distribution_bins
            ):
                facts.add(PhotoEdgeFact.INSUFFICIENT_DISTRIBUTED_SUPPORT)
            supported_indices = candidate.supported_window_indices
            if (
                len(supported_indices) < parameters.minimum_supported_windows
                or _occupied_bins(candidate, supported_indices, common)
                < parameters.minimum_support_distribution_bins
            ):
                facts.add(PhotoEdgeFact.PHOTO_BAND_EVIDENCE_UNAVAILABLE)
        if (
            _independent_holder_contradiction(
                top,
                BoundarySide.TOP,
                holder_boundaries,
            )
            or _independent_holder_contradiction(
                bottom,
                BoundarySide.BOTTOM,
                holder_boundaries,
            )
        ):
            facts.add(PhotoEdgeFact.PHOTO_BAND_CONTRADICTED)
            state = EvidenceState.CONTRADICTED
        slope_compatible = top.fit.slope_interval.intersects(
            bottom.fit.slope_interval
        )
        if (
            not slope_compatible
            or separation_drift is None
            or separation_drift > parameters.maximum_separation_drift_ratio
        ):
            facts.add(PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED)
            state = EvidenceState.CONTRADICTED
        if physical_band is not None:
            physical_state, physical_facts = _physical_band_assessment(
                top,
                bottom,
                common,
                height,
                physical_band,
            )
            facts.update(physical_facts)
            if physical_state == EvidenceState.CONTRADICTED:
                state = EvidenceState.CONTRADICTED
            elif (
                physical_state == EvidenceState.UNAVAILABLE
                and state != EvidenceState.CONTRADICTED
            ):
                state = EvidenceState.UNAVAILABLE
        if not facts:
            state = EvidenceState.SUPPORTED
        elif state != EvidenceState.CONTRADICTED:
            state = EvidenceState.UNAVAILABLE
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(
            "photo_edge_pair:"
            f"{top.observation_id}:{bottom.observation_id}:"
            f"{physical_band.band_id if physical_band is not None else 'image'}"
        ),
        dependencies=tuple(
            dict.fromkeys(
                dependency
                for dependency in (
                    top.provenance.root_measurement,
                    *top.provenance.dependencies,
                    bottom.provenance.root_measurement,
                    *bottom.provenance.dependencies,
                )
                if dependency != MeasurementIdentity.PHOTO_EDGES
            )
        ),
        description="ordered source-coordinate photo-edge pair hypothesis",
        boundary_anchors=(
            top.path.provenance.observation_id,
            bottom.path.provenance.observation_id,
        ),
    )
    return PhotoEdgePairHypothesis(
        top_candidate_id=top.observation_id,
        bottom_candidate_id=bottom.observation_id,
        physical_band_id=(
            None if physical_band is None else physical_band.band_id
        ),
        common_support=common,
        photo_height_px=height,
        separation_drift_ratio=separation_drift,
        photo_band_evidence=photo_band_evidence,
        state=state,
        facts=() if state == EvidenceState.SUPPORTED else _ordered_facts(facts),
        provenance=provenance,
    )


def _hypotheses_have_equivalent_confidence(
    left: PhotoEdgePairHypothesis,
    right: PhotoEdgePairHypothesis,
    candidates: dict[ObservationId, PhotoEdgeCandidate],
) -> bool:
    if left.physical_band_id != right.physical_band_id:
        return False
    if left.common_support is None or right.common_support is None:
        return False
    common = left.common_support.intersection(right.common_support)
    if common is None or common.maximum <= common.minimum:
        return False
    left_top = candidates[left.top_candidate_id]
    left_bottom = candidates[left.bottom_candidate_id]
    right_top = candidates[right.top_candidate_id]
    right_bottom = candidates[right.bottom_candidate_id]
    return all(
        left_candidate.fit.position_interval_at(
            coordinate
        ).intersection(
            right_candidate.fit.position_interval_at(coordinate)
        )
        is not None
        for coordinate in (
            common.minimum,
            common.midpoint,
            common.maximum,
        )
        for left_candidate, right_candidate in (
            (left_top, right_top),
            (left_bottom, right_bottom),
        )
    )


def _hypothesis_representative_key(
    hypothesis: PhotoEdgePairHypothesis,
    candidates: dict[ObservationId, PhotoEdgeCandidate],
) -> tuple[object, ...]:
    state_order = (
        EvidenceState.SUPPORTED,
        EvidenceState.UNAVAILABLE,
        EvidenceState.CONTRADICTED,
    )
    top = candidates[hypothesis.top_candidate_id]
    bottom = candidates[hypothesis.bottom_candidate_id]
    common_length = (
        0.0
        if hypothesis.common_support is None
        else hypothesis.common_support.maximum
        - hypothesis.common_support.minimum
    )
    return (
        state_order.index(hypothesis.state),
        -common_length,
        -len(top.fit.inlier_indices) - len(bottom.fit.inlier_indices),
        -len(top.supported_window_indices)
        - len(bottom.supported_window_indices),
        top.fit.position_uncertainty_px
        + bottom.fit.position_uncertainty_px,
        top.fit.residual_mad_px + bottom.fit.residual_mad_px,
        str(hypothesis.observation_id),
    )


def _merge_equivalent_hypotheses(
    hypotheses: tuple[PhotoEdgePairHypothesis, ...],
    candidates: tuple[PhotoEdgeCandidate, ...],
) -> tuple[PhotoEdgePairHypothesis, ...]:
    candidate_by_id = {
        candidate.observation_id: candidate for candidate in candidates
    }
    groups: list[list[PhotoEdgePairHypothesis]] = []
    for hypothesis in sorted(
        hypotheses,
        key=lambda item: (
            "" if item.physical_band_id is None else item.physical_band_id,
            str(item.observation_id),
        ),
    ):
        group = next(
            (
                existing
                for existing in groups
                if all(
                    _hypotheses_have_equivalent_confidence(
                        hypothesis,
                        member,
                        candidate_by_id,
                    )
                    for member in existing
                )
            ),
            None,
        )
        if group is None:
            groups.append([hypothesis])
        else:
            group.append(hypothesis)

    merged: list[PhotoEdgePairHypothesis] = []
    for group in groups:
        representative = min(
            group,
            key=lambda item: _hypothesis_representative_key(
                item,
                candidate_by_id,
            ),
        )
        if len(group) == 1:
            merged.append(representative)
            continue
        merged.append(
            replace(
                representative,
                provenance=replace(
                    representative.provenance,
                    description=(
                        "ordered photo-edge pair from equivalent "
                        "confidence tracks"
                    ),
                    boundary_anchors=tuple(
                        sorted(
                            {
                                anchor
                                for item in group
                                for anchor in (
                                    item.provenance.boundary_anchors
                                )
                            },
                            key=str,
                        )
                    ),
                ),
            )
        )
    return tuple(merged)


def _candidate_summaries(
    candidates: tuple[PhotoEdgeCandidate, ...],
    retained_candidate_ids: frozenset[ObservationId],
    hypothesized_candidate_ids: frozenset[ObservationId],
) -> tuple[PhotoEdgeCandidateSummary, ...]:
    groups: dict[
        tuple[
            PhotoEdgeCandidateDisposition,
            tuple[PhotoEdgeFact, ...],
            tuple[str, ...],
        ],
        list[PhotoEdgeCandidate],
    ] = {}
    for candidate in candidates:
        if candidate.observation_id in retained_candidate_ids:
            continue
        disposition = (
            PhotoEdgeCandidateDisposition.EVIDENCE_UNAVAILABLE
            if candidate.state == EvidenceState.UNAVAILABLE
            else (
                PhotoEdgeCandidateDisposition.EQUIVALENT_CONFIDENCE_MERGED
                if candidate.observation_id
                in hypothesized_candidate_ids
                else PhotoEdgeCandidateDisposition.PAIR_UNAVAILABLE
            )
        )
        key = (
            disposition,
            candidate.facts,
            candidate.physical_band_ids,
        )
        groups.setdefault(key, []).append(candidate)
    return tuple(
        PhotoEdgeCandidateSummary(
            disposition=disposition,
            facts=facts,
            physical_band_ids=physical_band_ids,
            observed_section_counts=tuple(
                sorted(
                    {
                        len(candidate.path.samples)
                        for candidate in group
                    }
                )
            ),
            candidate_count=len(group),
        )
        for (
            disposition,
            facts,
            physical_band_ids,
        ), group in sorted(
            groups.items(),
            key=lambda item: (
                item[0][0].value,
                tuple(fact.value for fact in item[0][1]),
                item[0][2],
            ),
        )
    )


def observe_photo_edge_pairs(
    gray_work: np.ndarray,
    measurements: BoundaryMeasurementSet,
    parameters: PhotoEdgeDetectionParameters,
    *,
    observation_id: str = "source_photo_edge_pair_evidence",
    search_bands: tuple[PhotoEdgeSearchBand, ...] = (),
    path_pair_proposals: tuple[PhotoEdgePathPairProposal, ...]
    | None = None,
) -> PhotoEdgePairEvidence:
    if search_bands and path_pair_proposals is None:
        raise ValueError(
            "physical photo-edge bands require paired path proposals"
        )
    if path_pair_proposals is not None:
        if not search_bands and path_pair_proposals:
            raise ValueError(
                "photo-edge path-pair proposals require physical bands"
            )
        if len(set(path_pair_proposals)) != len(path_pair_proposals):
            raise ValueError(
                "photo-edge path-pair proposals must be unique"
            )
    paths = tuple(
        path
        for path in measurements.raw_paths
        if path.axis == BoundaryAxis.SHORT
        and len(path.samples) >= parameters.minimum_candidate_sections
    )
    raw_path_ids = {
        path.provenance.observation_id for path in paths
    }
    band_ids = {band.band_id for band in search_bands}
    physical_bands_by_path: dict[
        ObservationId,
        set[str],
    ] = {path_id: set() for path_id in raw_path_ids}
    if path_pair_proposals is not None:
        for proposal in path_pair_proposals:
            if (
                proposal.top_path_id not in raw_path_ids
                or proposal.bottom_path_id not in raw_path_ids
            ):
                raise ValueError(
                    "photo-edge proposal must reference retained raw paths"
                )
            if proposal.physical_band_id not in band_ids:
                raise ValueError(
                    "photo-edge proposal must reference a retained physical band"
                )
            physical_bands_by_path[proposal.top_path_id].add(
                proposal.physical_band_id
            )
            physical_bands_by_path[proposal.bottom_path_id].add(
                proposal.physical_band_id
            )
    raw_candidates = tuple(
        _candidate(
            gray_work,
            path,
            parameters,
            tuple(
                sorted(
                    physical_bands_by_path[
                        path.provenance.observation_id
                    ]
                )
            ),
        )
        for path in paths
    )
    candidates = _merge_equivalent_candidates(raw_candidates)
    ordered_candidates = tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.path.position.midpoint,
                str(item.observation_id),
            ),
        )
    )
    hypothesis_candidates = tuple(
        candidate
        for candidate in ordered_candidates
        if PhotoEdgeFact.INSUFFICIENT_DISTRIBUTED_SUPPORT
        not in candidate.facts
    )
    if path_pair_proposals is None:
        proposed_candidates = tuple(
            (top, bottom, None)
            for index, top in enumerate(hypothesis_candidates)
            for bottom in hypothesis_candidates[index + 1 :]
            if bottom.path.position.midpoint
            > top.path.position.midpoint
        )
    else:
        band_by_id = {
            band.band_id: band for band in search_bands
        }
        candidate_by_anchor: dict[
            ObservationId,
            PhotoEdgeCandidate,
        ] = {}
        for candidate in hypothesis_candidates:
            for anchor in candidate.provenance.boundary_anchors:
                existing = candidate_by_anchor.get(anchor)
                if (
                    existing is not None
                    and existing.observation_id
                    != candidate.observation_id
                ):
                    raise ValueError(
                        "raw photo-edge path maps to multiple candidates"
                    )
                candidate_by_anchor[anchor] = candidate
        canonical_proposals: dict[
            tuple[ObservationId, ObservationId, str],
            tuple[
                PhotoEdgeCandidate,
                PhotoEdgeCandidate,
                PhotoEdgeSearchBand,
            ],
        ] = {}
        for proposal in path_pair_proposals:
            top = candidate_by_anchor.get(proposal.top_path_id)
            bottom = candidate_by_anchor.get(
                proposal.bottom_path_id
            )
            if top is None or bottom is None:
                continue
            if (
                top.observation_id == bottom.observation_id
                or bottom.path.position.midpoint
                <= top.path.position.midpoint
            ):
                continue
            key = (
                top.observation_id,
                bottom.observation_id,
                proposal.physical_band_id,
            )
            canonical_proposals[key] = (
                top,
                bottom,
                band_by_id[proposal.physical_band_id],
            )
        proposed_candidates = tuple(
            canonical_proposals[key]
            for key in sorted(
                canonical_proposals,
                key=lambda item: (
                    str(item[0]),
                    str(item[1]),
                    item[2],
                ),
            )
        )
    raw_hypotheses = tuple(
        _hypothesis(
            top,
            bottom,
            measurements.holder_boundaries,
            parameters,
            float(
                _local_window_depth(
                    gray_work.shape[0],
                    parameters,
                )
            ),
            _photo_band_evidence(
                gray_work,
                top,
                bottom,
                top.fit.orthogonal_extent.intersection(
                    bottom.fit.orthogonal_extent
                ),
                parameters,
            ),
            physical_band,
        )
        for top, bottom, physical_band in proposed_candidates
    )
    hypotheses = _merge_equivalent_hypotheses(
        raw_hypotheses,
        ordered_candidates,
    )
    retained_candidate_ids = frozenset(
        candidate_id
        for hypothesis in hypotheses
        for candidate_id in (
            hypothesis.top_candidate_id,
            hypothesis.bottom_candidate_id,
        )
    )
    candidate_summaries = _candidate_summaries(
        ordered_candidates,
        retained_candidate_ids,
        frozenset(
            candidate_id
            for hypothesis in raw_hypotheses
            for candidate_id in (
                hypothesis.top_candidate_id,
                hypothesis.bottom_candidate_id,
            )
        ),
    )
    retained_candidates = tuple(
        candidate
        for candidate in ordered_candidates
        if candidate.observation_id in retained_candidate_ids
    )
    supported = tuple(
        item for item in hypotheses if item.state == EvidenceState.SUPPORTED
    )
    if len(supported) == 1:
        state = EvidenceState.SUPPORTED
        facts: tuple[PhotoEdgeFact, ...] = ()
        selected_pair_id = supported[0].observation_id
        selected_band = (
            None
            if supported[0].physical_band_id is None
            else next(
                band
                for band in search_bands
                if band.band_id == supported[0].physical_band_id
            )
        )
        physical_selection = (
            None
            if selected_band is None
            else PhotoEdgePhysicalSelection(
                source_band_id=selected_band.band_id,
                scan_canvas_profile_id=(
                    selected_band.scan_canvas_profile_id
                ),
                frame_size_mm=selected_band.frame_size_mm,
            )
        )
    elif len(supported) > 1:
        state = EvidenceState.UNAVAILABLE
        facts = (PhotoEdgeFact.COMPETING_PAIRS_UNRESOLVED,)
        selected_pair_id = None
        physical_selection = None
    elif not ordered_candidates:
        state = EvidenceState.UNAVAILABLE
        facts = (PhotoEdgeFact.PATHS_UNAVAILABLE,)
        selected_pair_id = None
        physical_selection = None
    elif not hypotheses:
        state = EvidenceState.UNAVAILABLE
        candidate_facts = {
            fact
            for candidate in ordered_candidates
            for fact in candidate.facts
        }
        facts = _ordered_facts(
            candidate_facts
            or {PhotoEdgeFact.INSUFFICIENT_DISTRIBUTED_SUPPORT}
        )
        selected_pair_id = None
        physical_selection = None
    else:
        observed_facts = {
            fact for hypothesis in hypotheses for fact in hypothesis.facts
        }
        all_contradicted = all(
            hypothesis.state == EvidenceState.CONTRADICTED
            for hypothesis in hypotheses
        )
        state = (
            EvidenceState.CONTRADICTED
            if all_contradicted
            else EvidenceState.UNAVAILABLE
        )
        facts = _ordered_facts(observed_facts)
        selected_pair_id = None
        physical_selection = None
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(observation_id),
        dependencies=(
            MeasurementIdentity.BOUNDARY_PATHS,
            MeasurementIdentity.GRAY_WORK,
            MeasurementIdentity.IMAGE_MEASUREMENT_STATISTICS,
            *(
                (MeasurementIdentity.SCAN_CANVAS_GEOMETRY,)
                if search_bands
                else ()
            ),
        ),
        description="source-coordinate real-photo edge-pair evidence",
        boundary_anchors=tuple(
            anchor
            for candidate in retained_candidates
            for anchor in candidate.provenance.boundary_anchors
        ),
    )
    return PhotoEdgePairEvidence(
        candidates=retained_candidates,
        candidate_summaries=candidate_summaries,
        search_bands=search_bands,
        hypotheses=hypotheses,
        selected_pair_id=selected_pair_id,
        physical_selection=physical_selection,
        state=state,
        facts=facts,
        provenance=provenance,
    )


def _path_provenance(
    path: GrayBoundaryPathObservation,
    prefix: str,
    dependency: MeasurementIdentity,
) -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
        observation_id=ObservationId(
            f"{prefix}:{path.provenance.observation_id}"
        ),
        dependencies=tuple(
            dict.fromkeys((*path.provenance.dependencies, dependency))
        ),
        description="coordinate-mapped photo boundary path",
        boundary_anchors=(path.provenance.observation_id,),
    )


def _mapped_path(
    path: GrayBoundaryPathObservation,
    transform: AffineCoordinateTransform,
    layout: str,
    position_uncertainty_px: float,
) -> GrayBoundaryPathObservation:
    provenance = _path_provenance(
        path,
        "workspace",
        MeasurementIdentity.WORKSPACE_TRANSFORM,
    )
    work_width = (
        transform.output_extent.width
        if is_horizontal_layout(layout)
        else transform.output_extent.height
    )
    work_height = (
        transform.output_extent.height
        if is_horizontal_layout(layout)
        else transform.output_extent.width
    )
    orthogonal_domain = PixelInterval(0.0, float(work_width))
    position_domain = PixelInterval(0.0, float(work_height))
    samples: list[BoundaryPathSample] = []
    for sample in path.samples:
        if is_horizontal_layout(layout):
            orthogonal, position = transform.map_intervals(
                sample.orthogonal_interval,
                sample.position,
            )
        else:
            mapped_x, mapped_y = transform.map_intervals(
                sample.position,
                sample.orthogonal_interval,
            )
            orthogonal, position = mapped_y, mapped_x
        orthogonal = orthogonal.intersection(orthogonal_domain)
        position = position.expanded(position_uncertainty_px).intersection(
            position_domain
        )
        if orthogonal is None or position is None:
            raise ValueError("mapped photo-edge sample lies outside workspace")
        samples.append(BoundaryPathSample(orthogonal, position))
    return GrayBoundaryPathObservation(
        axis=path.axis,
        kind=path.kind,
        samples=tuple(
            sorted(samples, key=lambda item: item.orthogonal_interval.midpoint)
        ),
        lower_appearance=replace(path.lower_appearance, provenance=provenance),
        upper_appearance=replace(path.upper_appearance, provenance=provenance),
        provenance=provenance,
    )


def _translated_path(
    path: GrayBoundaryPathObservation,
    position_offset: int,
) -> GrayBoundaryPathObservation:
    provenance = _path_provenance(
        path,
        f"parent_lane_{position_offset}",
        MeasurementIdentity.CANVAS,
    )
    offset = PixelInterval.exact(float(position_offset))
    return GrayBoundaryPathObservation(
        axis=path.axis,
        kind=path.kind,
        samples=tuple(
            BoundaryPathSample(
                sample.orthogonal_interval,
                sample.position.plus(offset),
            )
            for sample in path.samples
        ),
        lower_appearance=replace(path.lower_appearance, provenance=provenance),
        upper_appearance=replace(path.upper_appearance, provenance=provenance),
        provenance=provenance,
    )


def _remap_evidence(
    evidence: PhotoEdgePairEvidence,
    path_mapper: Callable[[GrayBoundaryPathObservation], GrayBoundaryPathObservation],
    fit_mapper: Callable[
        [RobustBoundaryFit, GrayBoundaryPathObservation],
        RobustBoundaryFit,
    ],
    *,
    prefix: str,
    dependency: MeasurementIdentity,
) -> PhotoEdgePairEvidence:
    candidate_map: dict[ObservationId, PhotoEdgeCandidate] = {}
    for candidate in evidence.candidates:
        path = path_mapper(candidate.path)
        provenance = MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_EDGES,
            observation_id=ObservationId(f"{prefix}:{candidate.observation_id}"),
            dependencies=tuple(
                dict.fromkeys((*candidate.provenance.dependencies, dependency))
            ),
            description="coordinate-mapped photo-edge candidate",
            boundary_anchors=(path.provenance.observation_id,),
        )
        candidate_map[candidate.observation_id] = PhotoEdgeCandidate(
            path=path,
            fit=fit_mapper(candidate.fit, path),
            local_evidence=candidate.local_evidence,
            physical_band_ids=candidate.physical_band_ids,
            state=candidate.state,
            facts=candidate.facts,
            provenance=provenance,
        )
    hypothesis_map: dict[ObservationId, PhotoEdgePairHypothesis] = {}
    for hypothesis in evidence.hypotheses:
        top = candidate_map[hypothesis.top_candidate_id]
        bottom = candidate_map[hypothesis.bottom_candidate_id]
        common, height, separation_drift = _geometry_metrics(top, bottom)
        provenance = MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_EDGES,
            observation_id=ObservationId(f"{prefix}:{hypothesis.observation_id}"),
            dependencies=tuple(
                dict.fromkeys((*hypothesis.provenance.dependencies, dependency))
            ),
            description="coordinate-mapped photo-edge pair hypothesis",
            boundary_anchors=(
                top.path.provenance.observation_id,
                bottom.path.provenance.observation_id,
            ),
        )
        hypothesis_map[hypothesis.observation_id] = PhotoEdgePairHypothesis(
            top_candidate_id=top.observation_id,
            bottom_candidate_id=bottom.observation_id,
            physical_band_id=None,
            common_support=common,
            photo_height_px=height,
            separation_drift_ratio=separation_drift,
            photo_band_evidence=hypothesis.photo_band_evidence,
            state=hypothesis.state,
            facts=hypothesis.facts,
            provenance=provenance,
        )
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(f"{prefix}:{evidence.observation_id}"),
        dependencies=tuple(
            dict.fromkeys((*evidence.provenance.dependencies, dependency))
        ),
        description="coordinate-mapped real-photo edge-pair evidence",
        boundary_anchors=tuple(
            candidate.path.provenance.observation_id
            for candidate in candidate_map.values()
        ),
    )
    return PhotoEdgePairEvidence(
        candidates=tuple(candidate_map.values()),
        candidate_summaries=evidence.candidate_summaries,
        search_bands=(),
        hypotheses=tuple(hypothesis_map.values()),
        selected_pair_id=(
            None
            if evidence.selected_pair_id is None
            else hypothesis_map[evidence.selected_pair_id].observation_id
        ),
        physical_selection=evidence.physical_selection,
        state=evidence.state,
        facts=evidence.facts,
        provenance=provenance,
    )


def _mapped_fit(
    fit: RobustBoundaryFit,
    mapped_path: GrayBoundaryPathObservation,
    transform: AffineCoordinateTransform,
    layout: str,
    transform_uncertainty_px: float,
) -> RobustBoundaryFit:
    xx, xy, xt = transform.matrix[0]
    yx, yy, yt = transform.matrix[1]
    determinant = xx * yy - xy * yx

    def map_line(slope: float) -> tuple[float, float, float]:
        if is_horizontal_layout(layout):
            denominator = xx + xy * slope
            numerator = yx + yy * slope
            origin_orthogonal = xy * fit.intercept + xt
            origin_position = yy * fit.intercept + yt
        else:
            denominator = yx * slope + yy
            numerator = xx * slope + xy
            origin_orthogonal = yx * fit.intercept + yt
            origin_position = xx * fit.intercept + xt
        if abs(denominator) < AFFINE_INVERTIBILITY_FLOOR:
            raise ValueError("mapped photo-edge fit is not a function")
        mapped_slope = numerator / denominator
        mapped_intercept = origin_position - mapped_slope * origin_orthogonal
        uncertainty_scale = abs(determinant / denominator)
        return mapped_slope, mapped_intercept, uncertainty_scale

    central_slope, central_intercept, central_scale = map_line(fit.slope)
    endpoint_lines = tuple(
        map_line(slope)
        for slope in (
            fit.slope_interval.minimum,
            fit.slope_interval.maximum,
        )
    )
    slopes = tuple(item[0] for item in endpoint_lines)
    intercept_spread = max(
        abs(item[1] - central_intercept) for item in endpoint_lines
    )
    uncertainty_scale = max(
        central_scale,
        *(item[2] for item in endpoint_lines),
    )
    return RobustBoundaryFit(
        slope=central_slope,
        intercept=central_intercept,
        slope_interval=SlopeInterval(min(slopes), max(slopes)),
        position_uncertainty_px=(
            fit.position_uncertainty_px * uncertainty_scale
            + intercept_spread
            + transform_uncertainty_px
        ),
        residual_mad_px=fit.residual_mad_px * uncertainty_scale,
        orthogonal_extent=mapped_path.orthogonal_extent,
        inlier_indices=fit.inlier_indices,
        sample_count=fit.sample_count,
    )


def _translated_fit(
    fit: RobustBoundaryFit,
    mapped_path: GrayBoundaryPathObservation,
    position_offset: int,
) -> RobustBoundaryFit:
    return replace(
        fit,
        intercept=fit.intercept + float(position_offset),
        orthogonal_extent=mapped_path.orthogonal_extent,
    )


def map_photo_edge_pair_evidence(
    evidence: PhotoEdgePairEvidence,
    transform: AffineCoordinateTransform,
    layout: str,
    position_uncertainty_px: float,
) -> PhotoEdgePairEvidence:
    return _remap_evidence(
        evidence,
        lambda path: _mapped_path(
            path,
            transform,
            layout,
            position_uncertainty_px,
        ),
        lambda fit, path: _mapped_fit(
            fit,
            path,
            transform,
            layout,
            position_uncertainty_px,
        ),
        prefix="workspace",
        dependency=MeasurementIdentity.WORKSPACE_TRANSFORM,
    )


def translate_photo_edge_pair_evidence(
    evidence: PhotoEdgePairEvidence,
    position_offset: int,
) -> PhotoEdgePairEvidence:
    if position_offset == 0:
        return evidence
    return _remap_evidence(
        evidence,
        lambda path: _translated_path(path, position_offset),
        lambda fit, path: _translated_fit(fit, path, position_offset),
        prefix=f"parent_lane_{position_offset}",
        dependency=MeasurementIdentity.CANVAS,
    )
