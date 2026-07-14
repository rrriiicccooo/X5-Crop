from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import (
    BoundarySide,
    HolderBoundaryObservation,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)
from ...geometry.layout import is_horizontal_layout
from ..physical.model import PhotoSequenceSolution
from .holder_boundary import HolderBoundaryEvidence


MINIMUM_APERTURE_DIMENSION_OBSERVATIONS = 2


class PhotoScaleSource(str, Enum):
    SHORT_AXIS_LOWER_BOUND = "short_axis_lower_bound"
    APERTURE_DIMENSION_INTERVAL = "aperture_dimension_interval"


@dataclass(frozen=True)
class PhotoScaleObservation:
    axis: str
    minimum_px_per_mm: float
    maximum_px_per_mm: float | None
    source: PhotoScaleSource
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.axis not in {"x", "y"}:
            raise ValueError("photo scale observation axis must be x or y")
        if not isinstance(self.source, PhotoScaleSource):
            raise TypeError("photo scale observation requires a typed source")
        if not isinstance(self.provenance, MeasurementProvenance):
            raise TypeError("photo scale observation requires typed provenance")
        values = (self.minimum_px_per_mm, self.maximum_px_per_mm)
        if any(
            value is not None
            and (not math.isfinite(value) or value <= 0.0)
            for value in values
        ):
            raise ValueError("photo scale must be finite and positive")
        if (
            self.maximum_px_per_mm is not None
            and self.maximum_px_per_mm < self.minimum_px_per_mm
        ):
            raise ValueError("photo scale maximum must not be below minimum")
        expected_root = {
            PhotoScaleSource.SHORT_AXIS_LOWER_BOUND: (
                MeasurementIdentity.SHORT_AXIS_BOUNDARIES
            ),
            PhotoScaleSource.APERTURE_DIMENSION_INTERVAL: (
                MeasurementIdentity.PHOTO_EDGES
            ),
        }[self.source]
        if self.provenance.root_measurement != expected_root:
            raise ValueError("photo scale source must match measurement provenance")
        if (
            self.source == PhotoScaleSource.SHORT_AXIS_LOWER_BOUND
            and self.maximum_px_per_mm is not None
        ):
            raise ValueError("short-axis photo scale is a lower bound")
        if (
            self.source == PhotoScaleSource.APERTURE_DIMENSION_INTERVAL
            and self.maximum_px_per_mm is None
        ):
            raise ValueError("dimension consensus requires a bounded scale")


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


def _aperture_dimension_observations(
    geometry: PhotoSequenceSolution,
) -> tuple[PhotoScaleObservation, ...]:
    frame_width_mm = float(geometry.frame_dimension_prior.frame_size_mm[0])
    long_axis = "x" if is_horizontal_layout(geometry.layout) else "y"
    apertures = tuple(
        item
        for item in geometry.photo_apertures
        if item.leading.independently_observed
        and item.trailing.independently_observed
    )
    if len(apertures) < MINIMUM_APERTURE_DIMENSION_OBSERVATIONS:
        return ()
    return tuple(
        PhotoScaleObservation(
            axis=long_axis,
            minimum_px_per_mm=(
                aperture.trailing.position.minus(aperture.leading.position).minimum
                / frame_width_mm
            ),
            maximum_px_per_mm=(
                aperture.trailing.position.minus(aperture.leading.position).maximum
                / frame_width_mm
            ),
            source=PhotoScaleSource.APERTURE_DIMENSION_INTERVAL,
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
) -> PhotoScaleObservation | None:
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
    return PhotoScaleObservation(
        axis=source_axis,
        minimum_px_per_mm=scale,
        maximum_px_per_mm=None,
        source=PhotoScaleSource.SHORT_AXIS_LOWER_BOUND,
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


def photo_scale_observations(
    geometry: PhotoSequenceSolution,
    holder_boundary: HolderBoundaryEvidence,
) -> tuple[PhotoScaleObservation, ...]:
    dimension_observations = _aperture_dimension_observations(geometry)
    short_axis = _short_axis_observation(geometry, holder_boundary)
    return (
        dimension_observations
        if short_axis is None
        else (*dimension_observations, short_axis)
    )


def photo_scale_observations_match_geometry(
    geometry: PhotoSequenceSolution,
    holder_boundary: HolderBoundaryEvidence,
    observations: tuple[PhotoScaleObservation, ...],
) -> bool:
    expected = photo_scale_observations(geometry, holder_boundary)

    def identity(observation: PhotoScaleObservation) -> tuple[object, ...]:
        provenance = observation.provenance
        return (
            observation.axis,
            observation.minimum_px_per_mm,
            observation.maximum_px_per_mm,
            observation.source,
            provenance.root_measurement,
            provenance.observation_id,
            provenance.dependencies,
            provenance.boundary_anchors,
        )

    return tuple(map(identity, observations)) == tuple(map(identity, expected))
