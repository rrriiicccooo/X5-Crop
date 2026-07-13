from __future__ import annotations

from ...domain import (
    BoundaryMeasurementSet,
    BoundarySide,
    HolderBoundaryObservation,
    MeasurementIdentity,
    MeasurementProvenance,
)
from ...formats import FormatPhysicalSpec
from ...geometry.layout import is_horizontal_layout
from ...units import (
    PhysicalScaleObservation,
    PhysicalScaleScope,
    PhysicalScaleSource,
    ScanCalibrationResolution,
)
from ..physical.model import PhotoSequenceSolution
from .holder_boundary import HolderBoundaryEvidence


MINIMUM_FRAME_DIMENSION_CONSENSUS_OBSERVATIONS = 2


def _path_has_clear_inner_content(
    boundary: HolderBoundaryObservation | None,
    edge_texture_limit: float,
) -> bool:
    return bool(
        boundary is not None
        and boundary.outer_appearance.texture_median <= edge_texture_limit
        and boundary.inner_appearance.texture_median > edge_texture_limit
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
                    PhysicalScaleSource.FRAME_SHORT_AXIS,
                    PhysicalScaleScope.ROOT_MEASUREMENT,
                    MeasurementProvenance(
                        MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
                        "textured_inner_boundary_scale_lower_bound",
                        (
                            MeasurementIdentity.BOUNDARY_PATHS,
                            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
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
    if len(apertures) < MINIMUM_FRAME_DIMENSION_CONSENSUS_OBSERVATIONS:
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
            source=PhysicalScaleSource.FRAME_DIMENSION_CONSENSUS,
            scope=PhysicalScaleScope.CANDIDATE_GEOMETRY,
            provenance=MeasurementProvenance(
                MeasurementIdentity.PHOTO_EDGES,
                "frame_dimension_scale_observation",
                tuple(
                    dict.fromkeys(
                        (
                            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
                            aperture.leading.provenance.root_measurement,
                            aperture.trailing.provenance.root_measurement,
                        )
                    )
                ),
                (
                    f"photo:{aperture.index}:leading",
                    f"photo:{aperture.index}:trailing",
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
        source=PhysicalScaleSource.FRAME_SHORT_AXIS,
        scope=PhysicalScaleScope.CANDIDATE_GEOMETRY,
        provenance=MeasurementProvenance(
            MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
            "textured_inner_short_axis_scale_lower_bound",
            (
                MeasurementIdentity.BOUNDARY_PATHS,
                MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
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


def candidate_scan_calibration(
    context_calibration: ScanCalibrationResolution,
    geometry: PhotoSequenceSolution,
    holder_boundary: HolderBoundaryEvidence,
) -> ScanCalibrationResolution:
    observations = tuple(
        dict.fromkeys(
            (
                *context_calibration.physical_observations,
                *physical_scale_observations(geometry, holder_boundary),
            )
        )
    )
    return ScanCalibrationResolution.from_observations(
        context_calibration.metadata,
        observations,
    )


def candidate_scale_observations_match_geometry(
    geometry: PhotoSequenceSolution,
    holder_boundary: HolderBoundaryEvidence,
    calibration: ScanCalibrationResolution,
) -> bool:
    actual = tuple(
        observation
        for observation in calibration.physical_observations
        if observation.scope == PhysicalScaleScope.CANDIDATE_GEOMETRY
    )
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
            provenance.dependencies,
            provenance.boundary_anchors,
        )

    return tuple(map(identity, actual)) == tuple(map(identity, expected))
