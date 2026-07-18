from __future__ import annotations

from x5crop.detection.physical.frame_sequence_solver import (
    FrameSequenceSearchIndex,
    prepare_frame_sequence_search_index,
    solve_frame_sequence,
)
from x5crop.detection.physical.frame_sequence_result import (
    FrameSequenceSolveFailure,
    FrameSequenceSolveResult,
)
from x5crop.detection.physical.short_axis import (
    SharedShortAxisPlan,
    shared_short_axis_plan,
)
from x5crop.detection.physical.model import FrameSequenceSolution
from x5crop.detection.physical.separator.observations import SeparatorSupportSet
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryPathSample,
    BoundarySide,
    Box,
    ContainmentFallback,
    CrossAxisPathMeasurement,
    CrossAxisPathOutcome,
    FrameDimensionPrior,
    FrameSequenceSearchScope,
    GrayAppearanceObservation,
    GrayBoundaryPathObservation,
    GrayIntensityTail,
    HolderBoundaryObservation,
    HolderSafetyEnvelope,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
    SeparatorBandCrossAxisSupport,
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
)
from x5crop.image.content import ContentRegionObservation


def provenance(
    identity: MeasurementIdentity,
    source: str,
) -> MeasurementProvenance:
    return MeasurementProvenance(
        identity,
        ObservationId(source),
        (MeasurementIdentity.GRAY_WORK,),
        "synthetic frame-slot solver observation",
    )


def appearance(provenance: MeasurementProvenance) -> GrayAppearanceObservation:
    return GrayAppearanceObservation(
        intensity_median=64.0,
        intensity_mad=2.0,
        texture_median=2.0,
        gradient_median=4.0,
        spatial_continuity=1.0,
        intensity_tail=GrayIntensityTail.MIDRANGE,
        provenance=provenance,
    )


def path(
    axis: BoundaryAxis,
    position: float,
    source: str,
    *,
    kind: BoundaryKind = BoundaryKind.TONAL_TRANSITION,
    orthogonal_extent: float = 1_000_000.0,
) -> GrayBoundaryPathObservation:
    measurement_provenance = provenance(MeasurementIdentity.BOUNDARY_PATHS, source)
    interval = PixelInterval.exact(position)
    measurement_appearance = appearance(measurement_provenance)
    return GrayBoundaryPathObservation(
        axis=axis,
        kind=kind,
        samples=(
            BoundaryPathSample(
                PixelInterval(0.0, orthogonal_extent),
                interval,
            ),
        ),
        lower_appearance=measurement_appearance,
        upper_appearance=measurement_appearance,
        provenance=measurement_provenance,
    )


def scope(
    *,
    width: int,
    height: int,
    leading: float,
    trailing: float,
    top: float,
    bottom: float,
    internal_paths: tuple[float, ...] = (),
    holder_sides: tuple[BoundarySide, ...] = (),
    holder_positions: dict[BoundarySide, float] | None = None,
) -> FrameSequenceSearchScope:
    holder_positions = holder_positions or {}
    endpoint_positions = {
        BoundarySide.LEADING: (BoundaryAxis.LONG, leading),
        BoundarySide.TRAILING: (BoundaryAxis.LONG, trailing),
        BoundarySide.TOP: (BoundaryAxis.SHORT, top),
        BoundarySide.BOTTOM: (BoundaryAxis.SHORT, bottom),
    }
    endpoints = {
        side: path(
            axis,
            position,
            f"{side.value}_frame_path",
            kind=(
                BoundaryKind.EDGE_ADJACENT_TRANSITION
                if side in holder_sides and side not in holder_positions
                else BoundaryKind.TONAL_TRANSITION
            ),
        )
        for side, (axis, position) in endpoint_positions.items()
    }
    holder_paths = {
        side: path(
            endpoint_positions[side][0],
            position,
            f"holder_{side.value}_path",
            kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        )
        for side, position in holder_positions.items()
    }
    paths = (
        endpoints[BoundarySide.LEADING],
        endpoints[BoundarySide.TRAILING],
        endpoints[BoundarySide.TOP],
        endpoints[BoundarySide.BOTTOM],
        *tuple(
            path(BoundaryAxis.LONG, position, f"internal_path:{position:.3f}")
            for position in internal_paths
        ),
        *holder_paths.values(),
    )
    holder_path_by_side = {
        side: holder_paths.get(side, endpoints[side]) for side in holder_sides
    }
    fallback = ContainmentFallback(
        Box(0, 0, width, height),
        MeasurementProvenance(
            MeasurementIdentity.CANVAS,
            ObservationId("synthetic_containment"),
            (MeasurementIdentity.CANVAS,),
            "synthetic containment fallback",
        ),
    )
    holder_boundaries = tuple(
            HolderBoundaryObservation(
                side,
                holder_path_by_side[side].position,
                (holder_path_by_side[side],),
            )
            for side in holder_sides
        )
    return FrameSequenceSearchScope(
        holder_safety=HolderSafetyEnvelope(holder_boundaries, fallback),
        raw_boundary_paths=paths,
        provenance=MeasurementProvenance(
            MeasurementIdentity.BOUNDARY_PATHS,
            ObservationId("synthetic_frame_sequence_search_scope"),
            (MeasurementIdentity.GRAY_WORK,),
            "synthetic frame-sequence search scope",
        ),
    )


def content(
    *,
    width: int,
    height: int,
    runs: tuple[tuple[int, int], ...] = (),
    position_uncertainty_px: int = 0,
    guidance_runs: tuple[tuple[int, int], ...] = (),
) -> ContentRegionObservation:
    return ContentRegionObservation(
        Box(0, 0, width, height),
        runs,
        position_uncertainty_px,
        guidance_runs,
    )


def dimensions(width_mm: float, height_mm: float) -> FrameDimensionPrior:
    return FrameDimensionPrior(
        frame_size_mm=(width_mm, height_mm),
        provenance=MeasurementProvenance(
            MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
            ObservationId("synthetic_dimensions"),
            (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
            "synthetic physical dimensions",
        ),
    )


def separator(
    start: float,
    end: float,
    short_axis: SharedShortAxisPlan,
    *,
    supported: bool = False,
    leading_supported: bool | None = None,
    trailing_supported: bool | None = None,
    band_supported: bool | None = None,
) -> SeparatorBandCrossAxisSupport:
    measurement_provenance = provenance(
        MeasurementIdentity.SEPARATOR_PROFILE,
        f"separator_band:{start:.3f}:{end:.3f}",
    )
    observation = SeparatorBandObservation(
        leading_edge=PixelInterval.exact(start),
        trailing_edge=PixelInterval.exact(end),
        tonal_evidence=1.0,
        appearance=appearance(measurement_provenance),
        provenance=measurement_provenance,
    )
    def path(is_supported: bool) -> CrossAxisPathMeasurement:
        return CrossAxisPathMeasurement(
            (
                CrossAxisPathOutcome.PATH_SUPPORTED
                if is_supported
                else CrossAxisPathOutcome.CONTINUITY_WEAK
            ),
            1.0 if is_supported else 0.25,
            1.0 if is_supported else 0.25,
            0 if is_supported else 2,
        )

    leading_path = path(
        supported if leading_supported is None else leading_supported
    )
    trailing_path = path(
        supported if trailing_supported is None else trailing_supported
    )
    band_path = path(supported if band_supported is None else band_supported)
    return SeparatorBandCrossAxisSupport(
        observation=observation,
        measurement=SeparatorCrossAxisMeasurement(
            observation_id=measurement_provenance.observation_id,
            short_axis_span=short_axis.span.measurement_span,
            leading_edge_path=leading_path,
            trailing_edge_path=trailing_path,
            band_path=band_path,
            appearance_coherence_ratio=1.0 if supported else 0.5,
        ),
    )


def sequence_search_index(
    search_scope: FrameSequenceSearchScope,
    supports: tuple[SeparatorBandCrossAxisSupport, ...] = (),
    *,
    support_budget_exhausted: bool = False,
) -> FrameSequenceSearchIndex:
    return prepare_frame_sequence_search_index(
        search_scope,
        SeparatorSupportSet(supports, support_budget_exhausted),
    )


def solve_sequence(
    *,
    search_scope: FrameSequenceSearchScope,
    visible_content: ContentRegionObservation,
    count: int,
    frame_dimensions: FrameDimensionPrior,
    supports: tuple[SeparatorBandCrossAxisSupport, ...] = (),
    strip_mode: str = "full",
    nominal_count: int | None = None,
    maximum_assignment_evaluations: int = 100_000,
) -> FrameSequenceSolveResult | FrameSequenceSolveFailure:
    plan = shared_short_axis_plan(search_scope)
    return solve_frame_sequence(
        sequence_search_index(search_scope, supports),
        search_scope,
        plan,
        count,
        frame_dimensions,
        visible_content,
        maximum_assignment_evaluations,
        strip_mode=strip_mode,
        nominal_count=count if nominal_count is None else nominal_count,
    )


def geometry(
    search_scope: FrameSequenceSearchScope,
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    frame_dimensions: FrameDimensionPrior,
    solved: FrameSequenceSolveResult,
    *,
    format_id: str = "synthetic",
    strip_mode: str = "full",
    nominal_count: int | None = None,
) -> FrameSequenceSolution:
    count = len(solved.frame_slots)
    return FrameSequenceSolution(
        format_id=format_id,
        layout="horizontal",
        strip_mode=strip_mode,
        count=count,
        nominal_count=count if nominal_count is None else nominal_count,
        holder_safety=search_scope.holder_safety,
        shared_short_axis=solved.shared_short_axis,
        photo_height_evidence=solved.photo_height_evidence,
        frame_width_search_hint=solved.frame_width_search_hint,
        holder_span_scale_hint=solved.holder_span_scale_hint,
        content_extent_constraint=solved.content_extent_constraint,
        indexed_anchor_distance_constraints=(
            solved.indexed_anchor_distance_constraints
        ),
        frame_slots=solved.frame_slots,
        long_axis_assignments=solved.long_axis_assignments,
        separator_observations=tuple(support.observation for support in supports),
        separator_assignments=solved.separator_assignments,
        inter_frame_spacings=solved.inter_frame_spacings,
        frame_dimension_prior=frame_dimensions,
        common_frame_width=solved.common_frame_width,
        residuals=solved.residuals,
        assignment_consensus=solved.assignment_consensus,
        raw_boundary_paths=search_scope.raw_boundary_paths,
    )
