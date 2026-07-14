from __future__ import annotations

from x5crop.detection.physical.model import PhotoSequenceSolution
from x5crop.detection.physical.sequence_solver import (
    PhotoSequenceSolveResult,
    photo_aperture_cross_axis_plan,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryPathSample,
    BoundarySide,
    Box,
    ContainmentFallback,
    FrameDimensionPrior,
    FrameDimensionPriorSource,
    GrayAppearanceObservation,
    GrayBoundaryPathObservation,
    GrayIntensityTail,
    HolderBoundaryObservation,
    HolderSpan,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhotoApertureCrossAxisHypothesis,
    PhotoSequenceSearchScope,
    PixelInterval,
    SeparatorBandCrossAxisSupport,
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
    SeparatorCrossAxisOutcome,
)


def provenance(
    identity: MeasurementIdentity,
    source: str,
) -> MeasurementProvenance:
    return MeasurementProvenance(
        identity,
        ObservationId(source),
        (MeasurementIdentity.GRAY_WORK,),
        "synthetic solver observation",
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


def separator(
    start: float,
    end: float,
    *,
    supported: bool = False,
    cross_axis: PhotoApertureCrossAxisHypothesis | None = None,
) -> SeparatorBandCrossAxisSupport:
    measurement_provenance = provenance(
        MeasurementIdentity.SEPARATOR_PROFILE,
        f"separator_band:{start:.3f}:{end:.3f}",
    )
    if cross_axis is None:
        cross_axis = PhotoApertureCrossAxisHypothesis(
            path(BoundaryAxis.SHORT, 10.0, "top_aperture_path"),
            path(BoundaryAxis.SHORT, 110.0, "bottom_aperture_path"),
        )
    observation = SeparatorBandObservation(
        start=start,
        end=end,
        tonal_evidence=1.0,
        appearance=appearance(measurement_provenance),
        provenance=measurement_provenance,
    )
    return SeparatorBandCrossAxisSupport(
        observation=observation,
        measurements=(
            SeparatorCrossAxisMeasurement(
                observation_id=measurement_provenance.observation_id,
                aperture_cross_axis=cross_axis,
                outcome=(
                    SeparatorCrossAxisOutcome.PATH_SUPPORTED
                    if supported
                    else SeparatorCrossAxisOutcome.CONTINUITY_WEAK
                ),
                coverage_ratio=1.0 if supported else 0.25,
                longest_supported_ratio=1.0 if supported else 0.25,
                break_count=0 if supported else 2,
                appearance_coherence_ratio=1.0 if supported else 0.5,
            ),
        ),
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
) -> PhotoSequenceSearchScope:
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
            f"{side.value}_aperture_path",
            kind=(
                BoundaryKind.EDGE_ADJACENT_TRANSITION
                if side in holder_sides
                else BoundaryKind.TONAL_TRANSITION
            ),
        )
        for side, (axis, position) in endpoint_positions.items()
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
    )
    return PhotoSequenceSearchScope(
        holder_span=HolderSpan(Box(0, 0, width, height)),
        raw_boundary_paths=paths,
        holder_boundaries=tuple(
            HolderBoundaryObservation(side, endpoints[side].position, endpoints[side])
            for side in holder_sides
        ),
        containment_fallback=ContainmentFallback(
            Box(0, 0, width, height),
            MeasurementProvenance(
                MeasurementIdentity.CANVAS,
                ObservationId("synthetic_containment"),
                (MeasurementIdentity.CANVAS,),
                "synthetic containment fallback",
            ),
        ),
        measurement_budget_exhausted=False,
        provenance=MeasurementProvenance(
            MeasurementIdentity.BOUNDARY_CORRIDOR,
            ObservationId("synthetic_search_scope"),
            (MeasurementIdentity.BOUNDARY_PATHS,),
            "synthetic search scope",
        ),
    )


def dimensions(width_mm: float, height_mm: float) -> FrameDimensionPrior:
    return FrameDimensionPrior(
        frame_size_mm=(width_mm, height_mm),
        source=FrameDimensionPriorSource.PHYSICAL_ASPECT,
        provenance=MeasurementProvenance(
            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
            ObservationId("synthetic_dimensions"),
            (),
            "synthetic physical dimensions",
        ),
    )


def plan(search_scope: PhotoSequenceSearchScope):
    return photo_aperture_cross_axis_plan(
        search_scope,
        dimensions(1.0, 1.0),
        1,
        maximum_hypotheses=8,
    )


def geometry(
    search_scope: PhotoSequenceSearchScope,
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    frame_dimensions: FrameDimensionPrior,
    solved: PhotoSequenceSolveResult,
) -> PhotoSequenceSolution:
    return PhotoSequenceSolution(
        format_id="synthetic",
        layout="horizontal",
        strip_mode="full",
        count=len(solved.photo_apertures),
        holder_span=search_scope.holder_span,
        photo_apertures=solved.photo_apertures,
        aperture_edge_assignments=solved.aperture_edge_assignments,
        separator_observations=tuple(
            support.observation for support in supports
        ),
        separator_assignments=solved.separator_assignments,
        inter_photo_spacings=solved.inter_photo_spacings,
        frame_dimension_prior=frame_dimensions,
        photo_width_constraint_px=solved.photo_width_constraint_px,
        photo_height_constraint_px=solved.photo_height_constraint_px,
        residuals=solved.residuals,
        assignment_consensus=solved.assignment_consensus,
        raw_boundary_paths=search_scope.raw_boundary_paths,
        holder_boundaries=search_scope.holder_boundaries,
    )
