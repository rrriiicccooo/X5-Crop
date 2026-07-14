from __future__ import annotations

from ...domain import (
    BoundaryMeasurementSet,
    BoundarySide,
    HolderBoundaryObservation,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)
from ...formats import FormatPhysicalSpec
from ...geometry.layout import is_horizontal_layout
from ...units import (
    PhysicalScaleObservation,
    PhysicalScaleScope,
    PhysicalScaleSource,
)
from ..physical.model import PhotoSequenceSolution
from .holder_boundary import HolderBoundaryEvidence


MINIMUM_PHOTO_APERTURE_DIMENSION_CONSENSUS_OBSERVATIONS = 2


def _path_has_clear_inner_content(
    boundary: HolderBoundaryObservation | None,
    edge_texture_limit: float,
) -> bool:
    return bool(
        boundary is not None
        and all(
            appearance.texture_median <= edge_texture_limit
            for appearance in boundary.outer_appearances
        )
        and all(
            appearance.texture_median > edge_texture_limit
            for appearance in boundary.inner_appearances
        )
    )


def boundary_scale_observations(
    measurements: BoundaryMeasurementSet,
    physical_spec: FormatPhysicalSpec,
    layout: str,
    *,
    edge_texture_limit: float,
) -> tuple[PhysicalScaleObservation, ...]:
    frame_heights = tuple(
        float(option.height_mm) for option in physical_spec.frame_size_mm_options
    )
    source_axis = "y" if is_horizontal_layout(layout) else "x"
    observations: list[PhysicalScaleObservation] = []
    boundaries = {item.side: item for item in measurements.holder_boundaries}
    top = boundaries.get(BoundarySide.TOP)
    bottom = boundaries.get(BoundarySide.BOTTOM)
    if _path_has_clear_inner_content(
        top,
        edge_texture_limit,
    ) and _path_has_clear_inner_content(bottom, edge_texture_limit):
        assert top is not None and bottom is not None
        span = bottom.position.minus(top.position)
        lower = max(0.0, span.minimum) / max(frame_heights)
        if lower > 0.0:
            observations.append(
                PhysicalScaleObservation(
                    source_axis,
                    lower,
                    None,
                    PhysicalScaleSource.HOLDER_SHORT_AXIS,
                    PhysicalScaleScope.ROOT_MEASUREMENT,
                    MeasurementProvenance(
                        root_measurement=MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
                        observation_id=ObservationId(
                            "holder_aperture_short_axis_lower_bound"
                        ),
                        dependencies=(
                            MeasurementIdentity.BOUNDARY_PATHS,
                            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
                        ),
                        description="textured inner boundary scale lower bound",
                        boundary_anchors=(
                            top.provenance.observation_id,
                            bottom.provenance.observation_id,
                        ),
                    ),
                )
            )
    return tuple(dict.fromkeys(observations))


def _dimension_consensus_observations(
    geometry: PhotoSequenceSolution,
) -> tuple[PhysicalScaleObservation, ...]:
    frame_width_mm = float(geometry.frame_dimension_prior.frame_size_mm[0])
    long_axis = "x" if is_horizontal_layout(geometry.layout) else "y"
    apertures = tuple(
        item
        for item in geometry.photo_apertures
        if item.leading.independently_observed
        and item.trailing.independently_observed
    )
    if len(apertures) < MINIMUM_PHOTO_APERTURE_DIMENSION_CONSENSUS_OBSERVATIONS:
        return ()
    return tuple(
        PhysicalScaleObservation(
            axis=long_axis,
            minimum_px_per_mm=(
                aperture.trailing.position.minus(aperture.leading.position).minimum
                / frame_width_mm
            ),
            maximum_px_per_mm=(
                aperture.trailing.position.minus(aperture.leading.position).maximum
                / frame_width_mm
            ),
            source=PhysicalScaleSource.PHOTO_APERTURE_DIMENSION_CONSENSUS,
            scope=PhysicalScaleScope.CANDIDATE_GEOMETRY,
            provenance=MeasurementProvenance(
                root_measurement=MeasurementIdentity.PHOTO_EDGES,
                observation_id=ObservationId(
                    f"photo_aperture_dimension_scale:{aperture.index}"
                ),
                dependencies=tuple(
                    dict.fromkeys(
                        (
                            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
                            aperture.leading.provenance.root_measurement,
                            aperture.trailing.provenance.root_measurement,
                        )
                    )
                ),
                description="photo aperture dimension scale observation",
                boundary_anchors=(
                    aperture.leading.provenance.observation_id,
                    aperture.trailing.provenance.observation_id,
                ),
            ),
        )
        for aperture in apertures
    )


def _short_axis_observation(
    geometry: PhotoSequenceSolution,
    holder_boundary: HolderBoundaryEvidence,
) -> PhysicalScaleObservation | None:
    boundaries = {
        boundary.side: boundary for boundary in holder_boundary.boundaries
    }
    if not (
        _path_has_clear_inner_content(
            boundaries.get(BoundarySide.TOP),
            holder_boundary.edge_texture_limit,
        )
        and _path_has_clear_inner_content(
            boundaries.get(BoundarySide.BOTTOM),
            holder_boundary.edge_texture_limit,
        )
    ):
        return None
    frame_height_mm = float(geometry.frame_dimension_prior.frame_size_mm[1])
    measured_heights = tuple(
        aperture.bottom.position.minus(aperture.top.position).midpoint
        for aperture in geometry.photo_apertures
        if aperture.top.independently_observed
        and aperture.bottom.independently_observed
    )
    if not measured_heights:
        return None
    visible_short_axis_px = sum(measured_heights) / len(measured_heights)
    scale = visible_short_axis_px / frame_height_mm
    source_axis = "y" if is_horizontal_layout(geometry.layout) else "x"
    return PhysicalScaleObservation(
        axis=source_axis,
        minimum_px_per_mm=scale,
        maximum_px_per_mm=None,
        source=PhysicalScaleSource.PHOTO_APERTURE_SHORT_AXIS,
        scope=PhysicalScaleScope.CANDIDATE_GEOMETRY,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
            observation_id=ObservationId(
                "photo_aperture_short_axis_scale_lower_bound"
            ),
            dependencies=(
                MeasurementIdentity.BOUNDARY_PATHS,
                MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
            ),
            description="textured inner short-axis scale lower bound",
            boundary_anchors=(
                boundaries[BoundarySide.TOP].provenance.observation_id,
                boundaries[BoundarySide.BOTTOM].provenance.observation_id,
            ),
        ),
    )


def physical_scale_observations(
    geometry: PhotoSequenceSolution,
    holder_boundary: HolderBoundaryEvidence,
) -> tuple[PhysicalScaleObservation, ...]:
    dimension_observations = _dimension_consensus_observations(geometry)
    short_axis = _short_axis_observation(geometry, holder_boundary)
    return (
        dimension_observations
        if short_axis is None
        else (*dimension_observations, short_axis)
    )


def candidate_scale_observations_match_geometry(
    geometry: PhotoSequenceSolution,
    holder_boundary: HolderBoundaryEvidence,
    observations: tuple[PhysicalScaleObservation, ...],
) -> bool:
    expected = physical_scale_observations(geometry, holder_boundary)

    def identity(observation: PhysicalScaleObservation) -> tuple[object, ...]:
        provenance = observation.provenance
        return (
            observation.axis,
            observation.minimum_px_per_mm,
            observation.maximum_px_per_mm,
            observation.source,
            observation.scope,
            provenance.root_measurement,
            provenance.observation_id,
            provenance.dependencies,
            provenance.boundary_anchors,
        )

    return tuple(map(identity, observations)) == tuple(map(identity, expected))
