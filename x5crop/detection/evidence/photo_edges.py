from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import math

import numpy as np

from ...domain import (
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from ...formats import FrameSizeMm
from ...geometry.affine import (
    AFFINE_INVERTIBILITY_FLOOR,
    AffineCoordinateTransform,
)
from ...geometry.layout import is_horizontal_layout


_PARALLEL_LINE_TOLERANCE = 1e-9


class LocalTransitionState(str, Enum):
    SUPPORTED = "supported"
    NEUTRAL = "neutral"


class PhotoEdgeFact(str, Enum):
    OBSERVATIONS_UNAVAILABLE = "observations_unavailable"
    CONTAINMENT_CONTRADICTED = "containment_contradicted"
    PAIR_GEOMETRY_UNAVAILABLE = "pair_geometry_unavailable"
    PAIR_GEOMETRY_CONTRADICTED = "pair_geometry_contradicted"
    COMPETING_PAIRS_UNRESOLVED = "competing_pairs_unresolved"


class PhotoEdgeCoordinateSpace(str, Enum):
    SOURCE = "source"
    MAPPED = "mapped"


class RegionSetRelation(str, Enum):
    DISJOINT = "disjoint"
    SUBSET = "subset"
    PARTIAL_INTERSECTION = "partial_intersection"
    NUMERICALLY_INDETERMINATE = "numerically_indeterminate"


@dataclass(frozen=True, order=True)
class NumericInterval:
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.minimum)
            or not math.isfinite(self.maximum)
            or self.maximum < self.minimum
        ):
            raise ValueError("numeric interval must be finite and ordered")

    @classmethod
    def exact(cls, value: float) -> "NumericInterval":
        return cls(float(value), float(value))

    @property
    def midpoint(self) -> float:
        return 0.5 * (self.minimum + self.maximum)

    @property
    def width(self) -> float:
        return self.maximum - self.minimum

    def expanded(self, radius: float) -> "NumericInterval":
        if not math.isfinite(radius) or radius < 0.0:
            raise ValueError("numeric interval expansion must be non-negative")
        return NumericInterval(self.minimum - radius, self.maximum + radius)


@dataclass(frozen=True)
class PhotoEdgeSideStatistics:
    intensity_median_u8: float
    intensity_mad_u8: float
    texture_median_u8: float
    gradient_median_u8: float

    def __post_init__(self) -> None:
        values = (
            self.intensity_median_u8,
            self.intensity_mad_u8,
            self.texture_median_u8,
            self.gradient_median_u8,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError(
                "photo-edge side statistics must be finite and non-negative"
            )


@dataclass(frozen=True)
class PhotoEdgeObservation:
    observation_id: ObservationId
    source_sha256: str
    long_axis_footprint: PixelInterval
    short_axis_position_interval: PixelInterval
    negative_side_statistics: PhotoEdgeSideStatistics
    positive_side_statistics: PhotoEdgeSideStatistics
    absolute_intensity_effect: float
    absolute_texture_effect: float
    absolute_gradient_effect: float
    local_noise_u8: float
    multiscale_position_interval: PixelInterval
    state: LocalTransitionState
    measurement_channels: tuple[str, ...]
    measurement_scales: tuple[float, ...]
    censored: bool
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.observation_id, ObservationId):
            raise TypeError("photo-edge observation requires a typed identity")
        if (
            len(self.source_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.source_sha256)
        ):
            raise ValueError("photo-edge observation requires a source SHA-256")
        if (
            self.long_axis_footprint.maximum
            <= self.long_axis_footprint.minimum
        ):
            raise ValueError(
                "photo-edge observation requires a positive long-axis footprint"
            )
        if not self.short_axis_position_interval.intersects(
            self.multiscale_position_interval
        ):
            raise ValueError(
                "photo-edge position must agree with its multiscale envelope"
            )
        effects = (
            self.absolute_intensity_effect,
            self.absolute_texture_effect,
            self.absolute_gradient_effect,
            self.local_noise_u8,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in effects):
            raise ValueError(
                "photo-edge effects and noise must be finite and non-negative"
            )
        if not isinstance(self.state, LocalTransitionState):
            raise TypeError("photo-edge observation requires a local state")
        if (
            not self.measurement_channels
            or tuple(sorted(set(self.measurement_channels)))
            != self.measurement_channels
        ):
            raise ValueError(
                "photo-edge measurement channels must be ordered and unique"
            )
        if (
            not self.measurement_scales
            or tuple(sorted(set(self.measurement_scales)))
            != self.measurement_scales
        ):
            raise ValueError(
                "photo-edge measurement scales must be ordered and unique"
            )
        if self.provenance.observation_id != self.observation_id:
            raise ValueError(
                "photo-edge observation identity must match its provenance"
            )
        if self.provenance.root_measurement != MeasurementIdentity.PHOTO_EDGES:
            raise ValueError("photo-edge observation requires photo-edge provenance")


@dataclass(frozen=True)
class PhotoEdgePhysicalLabel:
    scan_canvas_profile_id: str | None
    source_corridor_id: str | None
    frame_size_mm: FrameSizeMm

    def __post_init__(self) -> None:
        if (self.scan_canvas_profile_id is None) != (
            self.source_corridor_id is None
        ):
            raise ValueError(
                "fixed-canvas physical labels require both source identities"
            )
        if self.scan_canvas_profile_id == "" or self.source_corridor_id == "":
            raise ValueError("photo-edge physical identities cannot be empty")

    @property
    def identity(self) -> str:
        if self.source_corridor_id is not None:
            return self.source_corridor_id
        return (
            "dual_lane:"
            f"{self.frame_size_mm.width_mm:g}x"
            f"{self.frame_size_mm.height_mm:g}"
        )


@dataclass(frozen=True)
class PhotoEdgeSearchCorridor:
    physical_label: PhotoEdgePhysicalLabel
    work_long_axis_px: int
    work_short_axis_px: int
    nominal_top_px: float
    nominal_bottom_px: float
    maximum_center_offset_px: float
    maximum_dimension_deviation_px: float
    maximum_search_angle_degrees: float
    measurement_halo_short_px: int
    measurement_halo_long_px: int

    def __post_init__(self) -> None:
        if self.physical_label.source_corridor_id is None:
            raise ValueError("fixed-canvas search corridors require an identity")
        if min(self.work_long_axis_px, self.work_short_axis_px) <= 0:
            raise ValueError("photo-edge corridor requires positive extents")
        values = (
            self.nominal_top_px,
            self.nominal_bottom_px,
            self.maximum_center_offset_px,
            self.maximum_dimension_deviation_px,
            self.maximum_search_angle_degrees,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("photo-edge corridor values must be finite")
        if not (
            0.0 <= self.nominal_top_px
            < self.nominal_bottom_px
            <= float(self.work_short_axis_px - 1)
        ):
            raise ValueError("photo-edge corridor must lie inside the canvas")
        if min(
            self.maximum_center_offset_px,
            self.maximum_dimension_deviation_px,
            self.maximum_search_angle_degrees,
        ) <= 0.0:
            raise ValueError("photo-edge corridor allowances must be positive")
        if min(
            self.measurement_halo_short_px,
            self.measurement_halo_long_px,
        ) <= 0:
            raise ValueError("photo-edge measurement halo must be positive")

    @property
    def corridor_id(self) -> str:
        assert self.physical_label.source_corridor_id is not None
        return self.physical_label.source_corridor_id

    def side_interval_at(
        self,
        long_axis_coordinate: float,
        *,
        top: bool,
    ) -> PixelInterval:
        center = 0.5 * float(self.work_long_axis_px - 1)
        angle_allowance = abs(float(long_axis_coordinate) - center) * math.tan(
            math.radians(self.maximum_search_angle_degrees)
        )
        allowance = (
            self.maximum_center_offset_px
            + 0.5 * self.maximum_dimension_deviation_px
            + angle_allowance
        )
        nominal = self.nominal_top_px if top else self.nominal_bottom_px
        return PixelInterval(
            max(0.0, nominal - allowance),
            min(float(self.work_short_axis_px - 1), nominal + allowance),
        )


@dataclass(frozen=True)
class PhotoEdgeFragmentSummary:
    fragment_id: ObservationId
    long_axis_footprint: PixelInterval
    short_axis_position_interval: PixelInterval
    canonical_observation_count: int
    ordered_constraint_sha256: str
    censored: bool
    active_observation_ids: tuple[ObservationId, ...]
    minimum_support_witness_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if self.long_axis_footprint.maximum <= self.long_axis_footprint.minimum:
            raise ValueError("photo-edge fragment requires a positive footprint")
        if self.canonical_observation_count <= 0:
            raise ValueError("photo-edge fragment requires observations")
        if (
            len(self.ordered_constraint_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.ordered_constraint_sha256
            )
        ):
            raise ValueError("photo-edge fragment requires a constraint hash")
        for identities in (
            self.active_observation_ids,
            self.minimum_support_witness_ids,
        ):
            if len(set(identities)) != len(identities):
                raise ValueError(
                    "photo-edge fragment observation identities must be unique"
                )


@dataclass(frozen=True)
class PhotoEdgeMeasurementSummary:
    raw_anchor_count: int
    supported_transition_count: int
    neutral_anchor_count: int
    censored_component_count: int
    merged_duplicate_count: int
    fragment_count: int
    canonical_observation_count: int
    chunk_size_px: int
    peak_temporary_buffer_bytes: int

    def __post_init__(self) -> None:
        values = (
            self.raw_anchor_count,
            self.supported_transition_count,
            self.neutral_anchor_count,
            self.censored_component_count,
            self.merged_duplicate_count,
            self.fragment_count,
            self.canonical_observation_count,
            self.chunk_size_px,
            self.peak_temporary_buffer_bytes,
        )
        if any(value < 0 for value in values):
            raise ValueError(
                "photo-edge measurement summary values cannot be negative"
            )
        if self.chunk_size_px <= 0:
            raise ValueError("photo-edge measurement chunks must be positive")


@dataclass(frozen=True)
class NormalRegionWitness:
    physical_angle_radians: float
    top_normal_offset_mm: float
    bottom_normal_offset_mm: float
    physical_label: PhotoEdgePhysicalLabel

    def __post_init__(self) -> None:
        values = (
            self.physical_angle_radians,
            self.top_normal_offset_mm,
            self.bottom_normal_offset_mm,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("normal-region witness must be finite")
        if self.bottom_normal_offset_mm <= self.top_normal_offset_mm:
            raise ValueError("normal-region witness must preserve top/bottom order")


@dataclass(frozen=True)
class NormalRegionCell:
    theta_binary_path: str
    physical_angle_radians: NumericInterval
    top_normal_offset_mm: NumericInterval
    bottom_normal_offset_mm: NumericInterval
    possible_physical_labels: tuple[PhotoEdgePhysicalLabel, ...]
    verified_witnesses: tuple[NormalRegionWitness, ...]
    active_constraint_ids: tuple[ObservationId, ...]
    canonical_signature: str

    def __post_init__(self) -> None:
        if any(character not in "01" for character in self.theta_binary_path):
            raise ValueError("normal-region theta path must be binary")
        if not self.possible_physical_labels:
            raise ValueError("normal-region cells require possible labels")
        label_ids = tuple(
            label.identity for label in self.possible_physical_labels
        )
        if tuple(sorted(set(label_ids))) != label_ids:
            raise ValueError(
                "normal-region physical labels must be ordered and unique"
            )
        witness_ids = tuple(
            witness.physical_label.identity
            for witness in self.verified_witnesses
        )
        if len(set(witness_ids)) != len(witness_ids):
            raise ValueError(
                "normal-region witnesses must be unique per physical label"
            )
        if not set(witness_ids).issubset(label_ids):
            raise ValueError(
                "normal-region witnesses must use possible physical labels"
            )
        if not self.canonical_signature:
            raise ValueError("normal-region cell requires a signature")


@dataclass(frozen=True)
class PhotoEdgeNormalFeasibleRegion:
    cells: tuple[NormalRegionCell, ...]
    set_relation: RegionSetRelation
    numerically_indeterminate: bool
    consumed_region_cells: int
    consumed_consensus_states: int

    def __post_init__(self) -> None:
        if not isinstance(self.set_relation, RegionSetRelation):
            raise TypeError("normal feasible region requires a set relation")
        signatures = tuple(cell.canonical_signature for cell in self.cells)
        if len(set(signatures)) != len(signatures):
            raise ValueError("normal feasible-region cells must be canonical")
        if min(
            self.consumed_region_cells,
            self.consumed_consensus_states,
        ) < 0:
            raise ValueError("geometry work counters cannot be negative")
        if (
            self.set_relation == RegionSetRelation.DISJOINT
            and self.cells
        ):
            raise ValueError("disjoint normal regions cannot retain cells")
        if (
            self.set_relation == RegionSetRelation.NUMERICALLY_INDETERMINATE
        ) != self.numerically_indeterminate:
            raise ValueError(
                "normal-region indeterminate state must match its relation"
            )

    @property
    def canonical_signature(self) -> str:
        payload = "|".join(
            cell.canonical_signature for cell in self.cells
        ).encode("utf-8")
        return sha256(payload).hexdigest()


@dataclass(frozen=True)
class PhotoEdgeLineWitness:
    pixel_slope: float
    top_intercept_px: float
    bottom_intercept_px: float
    top_intercept_feasible_px: NumericInterval
    bottom_intercept_feasible_px: NumericInterval
    physical_label: PhotoEdgePhysicalLabel

    def __post_init__(self) -> None:
        values = (
            self.pixel_slope,
            self.top_intercept_px,
            self.bottom_intercept_px,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("photo-edge line witness must be finite")
        if self.bottom_intercept_px <= self.top_intercept_px:
            raise ValueError("photo-edge line witness must preserve order")
        if not (
            self.top_intercept_feasible_px.minimum
            <= self.top_intercept_px
            <= self.top_intercept_feasible_px.maximum
            and self.bottom_intercept_feasible_px.minimum
            <= self.bottom_intercept_px
            <= self.bottom_intercept_feasible_px.maximum
        ):
            raise ValueError(
                "photo-edge line witness must lie in its feasible slice"
            )


@dataclass(frozen=True)
class PhotoEdgeLineRegionCell:
    source_cell_signature: str
    pixel_slope: NumericInterval
    top_intercept_px: NumericInterval
    bottom_intercept_px: NumericInterval
    possible_physical_labels: tuple[PhotoEdgePhysicalLabel, ...]
    verified_witnesses: tuple[PhotoEdgeLineWitness, ...]
    active_constraint_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if not self.source_cell_signature:
            raise ValueError("photo-edge line cell requires a source signature")
        if not self.possible_physical_labels:
            raise ValueError("photo-edge line cell requires physical labels")

    def position_interval_at(
        self,
        coordinate: float,
        *,
        top: bool,
        extra_uncertainty_px: float = 0.0,
    ) -> PixelInterval:
        intercept = (
            self.top_intercept_px if top else self.bottom_intercept_px
        )
        predictions = (
            intercept.minimum + self.pixel_slope.minimum * float(coordinate),
            intercept.minimum + self.pixel_slope.maximum * float(coordinate),
            intercept.maximum + self.pixel_slope.minimum * float(coordinate),
            intercept.maximum + self.pixel_slope.maximum * float(coordinate),
        )
        return PixelInterval(
            min(predictions) - extra_uncertainty_px,
            max(predictions) + extra_uncertainty_px,
        )


@dataclass(frozen=True)
class PhotoEdgePairGeometry:
    cells: tuple[PhotoEdgeLineRegionCell, ...]
    normal_region: PhotoEdgeNormalFeasibleRegion | None
    work_long_axis_extent_px: int
    work_short_axis_extent_px: int
    interpolation_position_uncertainty_px: float
    coordinate_space: PhotoEdgeCoordinateSpace
    numerically_indeterminate: bool

    def __post_init__(self) -> None:
        if not self.cells:
            raise ValueError(
                "photo-edge pair geometry requires retained line cells"
            )
        if min(
            self.work_long_axis_extent_px,
            self.work_short_axis_extent_px,
        ) <= 0:
            raise ValueError("photo-edge geometry requires positive extents")
        if (
            not math.isfinite(self.interpolation_position_uncertainty_px)
            or self.interpolation_position_uncertainty_px < 0.0
        ):
            raise ValueError(
                "photo-edge interpolation uncertainty must be non-negative"
            )
        if not isinstance(self.coordinate_space, PhotoEdgeCoordinateSpace):
            raise TypeError("photo-edge geometry requires a coordinate space")
        signatures = tuple(cell.source_cell_signature for cell in self.cells)
        if len(set(signatures)) != len(signatures):
            raise ValueError("photo-edge line cells must be canonical")

    def edge_position_interval(
        self,
        coordinate: float,
        *,
        top: bool,
    ) -> PixelInterval:
        if not self.cells:
            raise ValueError("unresolved photo-edge geometry has no positions")
        intervals = tuple(
            cell.position_interval_at(
                coordinate,
                top=top,
                extra_uncertainty_px=(
                    self.interpolation_position_uncertainty_px
                ),
            )
            for cell in self.cells
        )
        return PixelInterval(
            min(interval.minimum for interval in intervals),
            max(interval.maximum for interval in intervals),
        )

    @property
    def pixel_slope_interval(self) -> NumericInterval:
        if not self.cells:
            raise ValueError("unresolved photo-edge geometry has no slope")
        return NumericInterval(
            min(cell.pixel_slope.minimum for cell in self.cells),
            max(cell.pixel_slope.maximum for cell in self.cells),
        )

    @property
    def photo_height_px(self) -> PixelInterval:
        if not self.cells:
            raise ValueError("unresolved photo-edge geometry has no height")
        intervals: list[PixelInterval] = []
        for cell in self.cells:
            axial_height = PixelInterval(
                max(
                    0.0,
                    cell.bottom_intercept_px.minimum
                    - cell.top_intercept_px.maximum,
                ),
                cell.bottom_intercept_px.maximum
                - cell.top_intercept_px.minimum,
            )
            closest_slope_to_zero = (
                0.0
                if cell.pixel_slope.minimum
                <= 0.0
                <= cell.pixel_slope.maximum
                else min(
                    abs(cell.pixel_slope.minimum),
                    abs(cell.pixel_slope.maximum),
                )
            )
            farthest_slope_from_zero = max(
                abs(cell.pixel_slope.minimum),
                abs(cell.pixel_slope.maximum),
            )
            intervals.append(
                PixelInterval(
                    axial_height.minimum
                    / math.sqrt(1.0 + farthest_slope_from_zero**2),
                    axial_height.maximum
                    / math.sqrt(1.0 + closest_slope_to_zero**2),
                )
            )
        return PixelInterval(
            min(interval.minimum for interval in intervals),
            max(interval.maximum for interval in intervals),
        )


@dataclass(frozen=True)
class DualLaneJointCell:
    first_pair_id: ObservationId
    second_pair_id: ObservationId
    pixel_slope: NumericInterval
    perpendicular_height_px: NumericInterval
    verified_pixel_slope: float
    verified_perpendicular_height_px: float
    verified_first_top_intercept_px: float
    verified_second_top_intercept_px: float
    source_cell_signatures: tuple[str, str]

    def __post_init__(self) -> None:
        if self.first_pair_id == self.second_pair_id:
            raise ValueError("dual-lane joint cells require two lane pairs")
        if (
            not self.pixel_slope.minimum
            <= self.verified_pixel_slope
            <= self.pixel_slope.maximum
            or not self.perpendicular_height_px.minimum
            <= self.verified_perpendicular_height_px
            <= self.perpendicular_height_px.maximum
        ):
            raise ValueError(
                "dual-lane verified values must lie in their joint cell"
            )
        if (
            self.perpendicular_height_px.minimum < 0.0
            or self.perpendicular_height_px.maximum <= 0.0
        ):
            raise ValueError(
                "dual-lane photo height must be positive"
            )
        if any(
            not math.isfinite(value)
            for value in (
                self.verified_first_top_intercept_px,
                self.verified_second_top_intercept_px,
            )
        ):
            raise ValueError(
                "dual-lane verified lane offsets must be finite"
            )
        if len(self.source_cell_signatures) != 2:
            raise ValueError("dual-lane joint cells require two source cells")


@dataclass(frozen=True)
class DualLanePhotoEdgeJointRegion:
    cells: tuple[DualLaneJointCell, ...]
    selected_pair_ids: tuple[ObservationId, ObservationId] | None
    state: EvidenceState
    facts: tuple[PhotoEdgeFact, ...]
    numerically_indeterminate: bool

    def __post_init__(self) -> None:
        if self.state == EvidenceState.SUPPORTED:
            if (
                not self.cells
                or self.selected_pair_ids is None
                or self.facts
                or self.numerically_indeterminate
            ):
                raise ValueError(
                    "supported dual-lane geometry requires one selected joint region"
                )
        else:
            if self.selected_pair_ids is not None or not self.facts:
                raise ValueError(
                    "unresolved dual-lane geometry cannot select lane pairs"
                )
        if self.state not in {
            EvidenceState.SUPPORTED,
            EvidenceState.UNAVAILABLE,
            EvidenceState.CONTRADICTED,
        }:
            raise ValueError("dual-lane geometry uses current states only")


@dataclass(frozen=True)
class PhotoEdgePairHypothesis:
    observation_id: ObservationId
    top_fragment_ids: tuple[ObservationId, ...]
    bottom_fragment_ids: tuple[ObservationId, ...]
    geometry: PhotoEdgePairGeometry | None
    physical_labels: tuple[PhotoEdgePhysicalLabel, ...]
    state: EvidenceState
    facts: tuple[PhotoEdgeFact, ...]
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if (
            not self.top_fragment_ids
            or not self.bottom_fragment_ids
            or set(self.top_fragment_ids) & set(self.bottom_fragment_ids)
        ):
            raise ValueError(
                "photo-edge hypothesis requires disjoint top/bottom fragments"
            )
        for identities in (
            self.top_fragment_ids,
            self.bottom_fragment_ids,
        ):
            if tuple(sorted(set(identities), key=str)) != identities:
                raise ValueError(
                    "photo-edge fragment identities must be ordered and unique"
                )
        if self.state == EvidenceState.SUPPORTED:
            if (
                self.geometry is None
                or not self.geometry.cells
                or self.geometry.numerically_indeterminate
                or len(self.physical_labels) != 1
                or self.facts
            ):
                raise ValueError(
                    "supported photo-edge hypotheses require one resolved geometry"
                )
        elif not self.facts:
            raise ValueError(
                "unresolved photo-edge hypotheses require typed facts"
            )
        if self.state not in {
            EvidenceState.SUPPORTED,
            EvidenceState.UNAVAILABLE,
            EvidenceState.CONTRADICTED,
        }:
            raise ValueError("photo-edge hypotheses use current states only")
        if any(not isinstance(fact, PhotoEdgeFact) for fact in self.facts):
            raise TypeError("photo-edge hypothesis facts must be typed")
        if self.provenance.observation_id != self.observation_id:
            raise ValueError(
                "photo-edge hypothesis identity must match its provenance"
            )


@dataclass(frozen=True)
class PhotoEdgePhysicalSelection:
    scan_canvas_profile_id: str | None
    source_corridor_id: str | None
    frame_size_mm: FrameSizeMm

    @classmethod
    def from_label(
        cls,
        label: PhotoEdgePhysicalLabel,
    ) -> "PhotoEdgePhysicalSelection":
        return cls(
            scan_canvas_profile_id=label.scan_canvas_profile_id,
            source_corridor_id=label.source_corridor_id,
            frame_size_mm=label.frame_size_mm,
        )


@dataclass(frozen=True)
class PhotoEdgePairEvidence:
    source_sha256: str
    search_corridors: tuple[PhotoEdgeSearchCorridor, ...]
    measurement_summary: PhotoEdgeMeasurementSummary
    fragment_summaries: tuple[PhotoEdgeFragmentSummary, ...]
    audit_observations: tuple[PhotoEdgeObservation, ...]
    hypotheses: tuple[PhotoEdgePairHypothesis, ...]
    selected_pair_id: ObservationId | None
    physical_selection: PhotoEdgePhysicalSelection | None
    state: EvidenceState
    facts: tuple[PhotoEdgeFact, ...]
    coordinate_space: PhotoEdgeCoordinateSpace
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if (
            len(self.source_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.source_sha256)
        ):
            raise ValueError("photo-edge evidence requires a source SHA-256")
        corridor_ids = tuple(
            corridor.corridor_id for corridor in self.search_corridors
        )
        fragment_ids = tuple(
            fragment.fragment_id for fragment in self.fragment_summaries
        )
        observation_ids = tuple(
            observation.observation_id
            for observation in self.audit_observations
        )
        hypothesis_ids = tuple(
            hypothesis.observation_id for hypothesis in self.hypotheses
        )
        for name, identities in (
            ("corridor", corridor_ids),
            ("fragment", fragment_ids),
            ("observation", observation_ids),
            ("hypothesis", hypothesis_ids),
        ):
            if len(set(identities)) != len(identities):
                raise ValueError(f"photo-edge {name} identities must be unique")
        if any(
            observation.source_sha256 != self.source_sha256
            for observation in self.audit_observations
        ):
            raise ValueError(
                "photo-edge audit observations must preserve source identity"
            )
        selected = tuple(
            hypothesis
            for hypothesis in self.hypotheses
            if hypothesis.observation_id == self.selected_pair_id
        )
        if self.state == EvidenceState.SUPPORTED:
            if (
                len(selected) != 1
                or selected[0].state != EvidenceState.SUPPORTED
                or len(selected[0].physical_labels) != 1
                or self.physical_selection
                != PhotoEdgePhysicalSelection.from_label(
                    selected[0].physical_labels[0]
                )
                or self.facts
            ):
                raise ValueError(
                    "supported photo-edge evidence requires one selected pair"
                )
        else:
            if selected or self.physical_selection is not None or not self.facts:
                raise ValueError(
                    "unresolved photo-edge evidence cannot select physical facts"
                )
        if self.state not in {
            EvidenceState.SUPPORTED,
            EvidenceState.UNAVAILABLE,
            EvidenceState.CONTRADICTED,
        }:
            raise ValueError("photo-edge evidence uses current states only")
        if any(not isinstance(fact, PhotoEdgeFact) for fact in self.facts):
            raise TypeError("photo-edge evidence facts must be typed")
        if (
            self.coordinate_space == PhotoEdgeCoordinateSpace.MAPPED
            and self.search_corridors
        ):
            raise ValueError(
                "mapped photo-edge evidence cannot retain source corridors"
            )
        if self.provenance.root_measurement != MeasurementIdentity.PHOTO_EDGES:
            raise ValueError("photo-edge evidence requires photo-edge provenance")

    @property
    def observation_id(self) -> ObservationId:
        return self.provenance.observation_id

    @property
    def selected_pair(self) -> PhotoEdgePairHypothesis | None:
        if self.selected_pair_id is None:
            return None
        return next(
            hypothesis
            for hypothesis in self.hypotheses
            if hypothesis.observation_id == self.selected_pair_id
        )

    @property
    def selected_geometry(self) -> PhotoEdgePairGeometry | None:
        pair = self.selected_pair
        return None if pair is None else pair.geometry


def ordered_photo_edge_facts(
    facts: set[PhotoEdgeFact],
) -> tuple[PhotoEdgeFact, ...]:
    return tuple(fact for fact in PhotoEdgeFact if fact in facts)


def fragment_constraint_hash(
    observations: tuple[PhotoEdgeObservation, ...],
) -> str:
    payload = "|".join(
        (
            f"{observation.observation_id}:"
            f"{observation.long_axis_footprint.minimum:.8f}:"
            f"{observation.long_axis_footprint.maximum:.8f}:"
            f"{observation.short_axis_position_interval.minimum:.8f}:"
            f"{observation.short_axis_position_interval.maximum:.8f}"
        )
        for observation in observations
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _work_line_to_image_line(
    slope: float,
    intercept: float,
    layout: str,
) -> np.ndarray:
    if is_horizontal_layout(layout):
        return np.asarray((-slope, 1.0, -intercept), dtype=np.float64)
    return np.asarray((1.0, -slope, -intercept), dtype=np.float64)


def _image_line_to_work_line(
    line: np.ndarray,
    layout: str,
) -> tuple[float, float]:
    a, b, c = (float(value) for value in line)
    denominator = b if is_horizontal_layout(layout) else a
    if abs(denominator) < AFFINE_INVERTIBILITY_FLOOR:
        raise ValueError("mapped photo edge is not a work-axis function")
    if is_horizontal_layout(layout):
        return -a / b, -c / b
    return -b / a, -c / a


def _map_work_line(
    slope: float,
    intercept: float,
    transform: AffineCoordinateTransform,
    layout: str,
) -> tuple[float, float]:
    source_line = _work_line_to_image_line(slope, intercept, layout)
    inverse_transpose = np.linalg.inv(
        np.asarray(transform.matrix, dtype=np.float64)
    ).T
    return _image_line_to_work_line(inverse_transpose @ source_line, layout)


def _map_line_cell(
    cell: PhotoEdgeLineRegionCell,
    transform: AffineCoordinateTransform,
    layout: str,
) -> PhotoEdgeLineRegionCell:
    mapped_top = tuple(
        _map_work_line(slope, intercept, transform, layout)
        for slope in (cell.pixel_slope.minimum, cell.pixel_slope.maximum)
        for intercept in (
            cell.top_intercept_px.minimum,
            cell.top_intercept_px.maximum,
        )
    )
    mapped_bottom = tuple(
        _map_work_line(slope, intercept, transform, layout)
        for slope in (cell.pixel_slope.minimum, cell.pixel_slope.maximum)
        for intercept in (
            cell.bottom_intercept_px.minimum,
            cell.bottom_intercept_px.maximum,
        )
    )

    def mapped_intercept_interval(
        source_slope: float,
        source_intercept: NumericInterval,
    ) -> NumericInterval:
        values = tuple(
            _map_work_line(
                source_slope,
                intercept,
                transform,
                layout,
            )[1]
            for intercept in (
                source_intercept.minimum,
                source_intercept.maximum,
            )
        )
        return NumericInterval(min(values), max(values))

    mapped_witnesses: list[PhotoEdgeLineWitness] = []
    for witness in cell.verified_witnesses:
        top_slope, top_intercept = _map_work_line(
            witness.pixel_slope,
            witness.top_intercept_px,
            transform,
            layout,
        )
        bottom_slope, bottom_intercept = _map_work_line(
            witness.pixel_slope,
            witness.bottom_intercept_px,
            transform,
            layout,
        )
        if abs(top_slope - bottom_slope) > _PARALLEL_LINE_TOLERANCE:
            raise ValueError(
                "affine mapping must preserve parallel photo edges"
            )
        mapped_witnesses.append(
            PhotoEdgeLineWitness(
                pixel_slope=0.5 * (top_slope + bottom_slope),
                top_intercept_px=top_intercept,
                bottom_intercept_px=bottom_intercept,
                top_intercept_feasible_px=mapped_intercept_interval(
                    witness.pixel_slope,
                    witness.top_intercept_feasible_px,
                ),
                bottom_intercept_feasible_px=mapped_intercept_interval(
                    witness.pixel_slope,
                    witness.bottom_intercept_feasible_px,
                ),
                physical_label=witness.physical_label,
            )
        )
    slopes = tuple(item[0] for item in (*mapped_top, *mapped_bottom))
    return PhotoEdgeLineRegionCell(
        source_cell_signature=cell.source_cell_signature,
        pixel_slope=NumericInterval(min(slopes), max(slopes)),
        top_intercept_px=NumericInterval(
            min(item[1] for item in mapped_top),
            max(item[1] for item in mapped_top),
        ),
        bottom_intercept_px=NumericInterval(
            min(item[1] for item in mapped_bottom),
            max(item[1] for item in mapped_bottom),
        ),
        possible_physical_labels=cell.possible_physical_labels,
        verified_witnesses=tuple(mapped_witnesses),
        active_constraint_ids=tuple(
            ObservationId(f"workspace:{identity}")
            for identity in cell.active_constraint_ids
        ),
    )


def _map_observation(
    observation: PhotoEdgeObservation,
    transform: AffineCoordinateTransform,
    layout: str,
    *,
    prefix: str,
) -> PhotoEdgeObservation:
    if is_horizontal_layout(layout):
        mapped_long, mapped_short = transform.map_intervals(
            observation.long_axis_footprint,
            observation.short_axis_position_interval,
        )
    else:
        mapped_x, mapped_y = transform.map_intervals(
            observation.short_axis_position_interval,
            observation.long_axis_footprint,
        )
        mapped_long, mapped_short = mapped_y, mapped_x
    observation_id = ObservationId(f"{prefix}{observation.observation_id}")
    return replace(
        observation,
        observation_id=observation_id,
        long_axis_footprint=mapped_long,
        short_axis_position_interval=mapped_short,
        multiscale_position_interval=mapped_short,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_EDGES,
            observation_id=observation_id,
            dependencies=tuple(
                dict.fromkeys(
                    (
                        *observation.provenance.dependencies,
                        MeasurementIdentity.WORKSPACE_TRANSFORM,
                    )
                )
            ),
            description="coordinate-mapped photo-edge observation",
            boundary_anchors=(observation.observation_id,),
        ),
    )


def _map_fragment_summary(
    fragment: PhotoEdgeFragmentSummary,
    transform: AffineCoordinateTransform,
    layout: str,
    *,
    prefix: str,
) -> PhotoEdgeFragmentSummary:
    if is_horizontal_layout(layout):
        mapped_long, mapped_short = transform.map_intervals(
            fragment.long_axis_footprint,
            fragment.short_axis_position_interval,
        )
    else:
        mapped_x, mapped_y = transform.map_intervals(
            fragment.short_axis_position_interval,
            fragment.long_axis_footprint,
        )
        mapped_long, mapped_short = mapped_y, mapped_x
    return replace(
        fragment,
        fragment_id=ObservationId(f"{prefix}{fragment.fragment_id}"),
        long_axis_footprint=mapped_long,
        short_axis_position_interval=mapped_short,
        active_observation_ids=tuple(
            ObservationId(f"{prefix}{identity}")
            for identity in fragment.active_observation_ids
        ),
        minimum_support_witness_ids=tuple(
            ObservationId(f"{prefix}{identity}")
            for identity in fragment.minimum_support_witness_ids
        ),
    )


def map_photo_edge_pair_evidence(
    evidence: PhotoEdgePairEvidence,
    transform: AffineCoordinateTransform,
    layout: str,
    interpolation_position_uncertainty_px: float,
) -> PhotoEdgePairEvidence:
    if interpolation_position_uncertainty_px < 0.0:
        raise ValueError(
            "mapped photo-edge uncertainty must be non-negative"
        )
    prefix = "workspace:"
    mapped_hypotheses: list[PhotoEdgePairHypothesis] = []
    for hypothesis in evidence.hypotheses:
        geometry = hypothesis.geometry
        mapped_geometry = (
            None
            if geometry is None
            else PhotoEdgePairGeometry(
                cells=tuple(
                    _map_line_cell(cell, transform, layout)
                    for cell in geometry.cells
                ),
                normal_region=None,
                work_long_axis_extent_px=(
                    transform.output_extent.width
                    if is_horizontal_layout(layout)
                    else transform.output_extent.height
                ),
                work_short_axis_extent_px=(
                    transform.output_extent.height
                    if is_horizontal_layout(layout)
                    else transform.output_extent.width
                ),
                interpolation_position_uncertainty_px=(
                    interpolation_position_uncertainty_px
                ),
                coordinate_space=PhotoEdgeCoordinateSpace.MAPPED,
                numerically_indeterminate=geometry.numerically_indeterminate,
            )
        )
        hypothesis_id = ObservationId(
            f"{prefix}{hypothesis.observation_id}"
        )
        mapped_hypotheses.append(
            replace(
                hypothesis,
                observation_id=hypothesis_id,
                top_fragment_ids=tuple(
                    ObservationId(f"{prefix}{identity}")
                    for identity in hypothesis.top_fragment_ids
                ),
                bottom_fragment_ids=tuple(
                    ObservationId(f"{prefix}{identity}")
                    for identity in hypothesis.bottom_fragment_ids
                ),
                geometry=mapped_geometry,
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.PHOTO_EDGES,
                    observation_id=hypothesis_id,
                    dependencies=tuple(
                        dict.fromkeys(
                            (
                                *hypothesis.provenance.dependencies,
                                MeasurementIdentity.WORKSPACE_TRANSFORM,
                            )
                        )
                    ),
                    description="coordinate-mapped photo-edge pair hypothesis",
                    boundary_anchors=(hypothesis.observation_id,),
                ),
            )
        )
    evidence_id = ObservationId(f"{prefix}{evidence.observation_id}")
    return PhotoEdgePairEvidence(
        source_sha256=evidence.source_sha256,
        search_corridors=(),
        measurement_summary=evidence.measurement_summary,
        fragment_summaries=tuple(
            _map_fragment_summary(fragment, transform, layout, prefix=prefix)
            for fragment in evidence.fragment_summaries
        ),
        audit_observations=tuple(
            _map_observation(observation, transform, layout, prefix=prefix)
            for observation in evidence.audit_observations
        ),
        hypotheses=tuple(mapped_hypotheses),
        selected_pair_id=(
            None
            if evidence.selected_pair_id is None
            else ObservationId(f"{prefix}{evidence.selected_pair_id}")
        ),
        physical_selection=evidence.physical_selection,
        state=evidence.state,
        facts=evidence.facts,
        coordinate_space=PhotoEdgeCoordinateSpace.MAPPED,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_EDGES,
            observation_id=evidence_id,
            dependencies=tuple(
                dict.fromkeys(
                    (
                        *evidence.provenance.dependencies,
                        MeasurementIdentity.WORKSPACE_TRANSFORM,
                    )
                )
            ),
            description="coordinate-mapped photo-edge pair evidence",
            boundary_anchors=(evidence.observation_id,),
        ),
    )


def translate_photo_edge_pair_evidence(
    evidence: PhotoEdgePairEvidence,
    position_offset: int,
    coordinate_space: PhotoEdgeCoordinateSpace,
) -> PhotoEdgePairEvidence:
    offset = float(position_offset)

    def translate_geometry(
        geometry: PhotoEdgePairGeometry | None,
    ) -> PhotoEdgePairGeometry | None:
        if geometry is None:
            return None
        return replace(
            geometry,
            cells=tuple(
                replace(
                    cell,
                    top_intercept_px=NumericInterval(
                        cell.top_intercept_px.minimum + offset,
                        cell.top_intercept_px.maximum + offset,
                    ),
                    bottom_intercept_px=NumericInterval(
                        cell.bottom_intercept_px.minimum + offset,
                        cell.bottom_intercept_px.maximum + offset,
                    ),
                    verified_witnesses=tuple(
                        replace(
                            witness,
                            top_intercept_px=(
                                witness.top_intercept_px + offset
                            ),
                            bottom_intercept_px=(
                                witness.bottom_intercept_px + offset
                            ),
                            top_intercept_feasible_px=NumericInterval(
                                witness.top_intercept_feasible_px.minimum
                                + offset,
                                witness.top_intercept_feasible_px.maximum
                                + offset,
                            ),
                            bottom_intercept_feasible_px=NumericInterval(
                                witness.bottom_intercept_feasible_px.minimum
                                + offset,
                                witness.bottom_intercept_feasible_px.maximum
                                + offset,
                            ),
                        )
                        for witness in cell.verified_witnesses
                    ),
                )
                for cell in geometry.cells
            ),
            coordinate_space=coordinate_space,
        )

    return replace(
        evidence,
        fragment_summaries=tuple(
            replace(
                fragment,
                short_axis_position_interval=PixelInterval(
                    fragment.short_axis_position_interval.minimum + offset,
                    fragment.short_axis_position_interval.maximum + offset,
                ),
            )
            for fragment in evidence.fragment_summaries
        ),
        audit_observations=tuple(
            replace(
                observation,
                short_axis_position_interval=PixelInterval(
                    observation.short_axis_position_interval.minimum + offset,
                    observation.short_axis_position_interval.maximum + offset,
                ),
                multiscale_position_interval=PixelInterval(
                    observation.multiscale_position_interval.minimum + offset,
                    observation.multiscale_position_interval.maximum + offset,
                ),
            )
            for observation in evidence.audit_observations
        ),
        hypotheses=tuple(
            replace(
                hypothesis,
                geometry=translate_geometry(hypothesis.geometry),
            )
            for hypothesis in evidence.hypotheses
        ),
        coordinate_space=coordinate_space,
    )
