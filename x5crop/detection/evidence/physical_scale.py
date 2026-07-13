from __future__ import annotations

from ...formats import FormatPhysicalSpec
from ...geometry.layout import is_horizontal_layout
from ...units import (
    PhysicalScaleObservation,
    PhysicalScaleScope,
    PhysicalScaleSource,
    ScanCalibrationResolution,
)
from ...domain import (
    BoundaryPathGroup,
    BoundarySide,
    MeasurementIdentity,
    MeasurementProvenance,
)
from ..physical.model import SequenceSolution
from .film_structure import (
    ApertureContactEvidence,
    ApertureContactOutcome,
    aperture_contact_outcome,
)


MINIMUM_FRAME_DIMENSION_CONSENSUS_OBSERVATIONS = 2


def boundary_scale_observations(
    groups: tuple[BoundaryPathGroup, ...],
    physical_spec: FormatPhysicalSpec,
    layout: str,
    *,
    edge_texture_limit: float,
) -> tuple[PhysicalScaleObservation, ...]:
    frame_heights = tuple(
        float(option.height_mm)
        for option in physical_spec.frame_size_mm_options
    )
    source_axis = "y" if is_horizontal_layout(layout) else "x"
    observations: list[PhysicalScaleObservation] = []
    for group in groups:
        by_side = {path.side: path for path in group.paths}
        top = by_side.get(BoundarySide.TOP)
        bottom = by_side.get(BoundarySide.BOTTOM)
        top_outcome = aperture_contact_outcome(top, edge_texture_limit)
        bottom_outcome = aperture_contact_outcome(bottom, edge_texture_limit)
        if (
            top_outcome != ApertureContactOutcome.HOLDER_TO_IMAGE
            or bottom_outcome != ApertureContactOutcome.HOLDER_TO_IMAGE
        ):
            continue
        if top is None or bottom is None:
            continue
        span = bottom.position.minus(top.position)
        provenance = MeasurementProvenance(
            MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
            "boundary_path_scale_observation",
            (
                MeasurementIdentity.BOUNDARY_PATHS,
                MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
            ),
        )
        lower = max(0.0, span.minimum) / max(frame_heights)
        if lower <= 0.0:
            continue
        observations.append(
            PhysicalScaleObservation(
                source_axis,
                lower,
                None,
                PhysicalScaleSource.FRAME_SHORT_AXIS,
                PhysicalScaleScope.ROOT_MEASUREMENT,
                provenance,
            )
        )
    return tuple(dict.fromkeys(observations))


def _dimension_consensus_observations(
    geometry: SequenceSolution,
) -> tuple[PhysicalScaleObservation, ...]:
    frame_width_mm = float(geometry.frame_dimension_prior.frame_size_mm[0])
    long_axis = "x" if is_horizontal_layout(geometry.layout) else "y"
    leading_occluded = (
        geometry.holder_occlusion.leading.hidden_width_px.maximum > 0.0
    )
    trailing_occluded = (
        geometry.holder_occlusion.trailing.hidden_width_px.maximum > 0.0
    )
    intervals = tuple(
        interval
        for interval in geometry.photo_intervals
        if interval.independently_observed
        and not (interval.index == 1 and leading_occluded)
        and not (interval.index == geometry.count and trailing_occluded)
    )
    if len(intervals) < MINIMUM_FRAME_DIMENSION_CONSENSUS_OBSERVATIONS:
        return ()
    return tuple(
        PhysicalScaleObservation(
            axis=long_axis,
            minimum_px_per_mm=interval.width_px.minimum / frame_width_mm,
            maximum_px_per_mm=interval.width_px.maximum / frame_width_mm,
            source=PhysicalScaleSource.FRAME_DIMENSION_CONSENSUS,
            scope=PhysicalScaleScope.CANDIDATE_GEOMETRY,
            provenance=MeasurementProvenance(
                MeasurementIdentity.PHOTO_EDGES,
                "frame_dimension_scale_observation",
                tuple(
                    dict.fromkeys(
                        (
                            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
                            interval.start_provenance.root_measurement,
                            interval.end_provenance.root_measurement,
                        )
                    )
                ),
                (
                    f"frame:{interval.index}:start",
                    f"frame:{interval.index}:end",
                ),
            ),
        )
        for interval in intervals
    )


def _short_axis_observation(
    geometry: SequenceSolution,
    aperture_contact: ApertureContactEvidence,
) -> PhysicalScaleObservation | None:
    contacts = {item.side: item.outcome for item in aperture_contact.sides}
    top = contacts[BoundarySide.TOP]
    bottom = contacts[BoundarySide.BOTTOM]
    if top != bottom or top not in {
        ApertureContactOutcome.HOLDER_TO_IMAGE,
        ApertureContactOutcome.HOLDER_TO_FILM_BASE,
    }:
        return None
    frame_height_mm = float(geometry.frame_dimension_prior.frame_size_mm[1])
    visible_short_axis_px = float(geometry.visible_sequence_span.box.height)
    scale = visible_short_axis_px / frame_height_mm
    source_axis = "y" if is_horizontal_layout(geometry.layout) else "x"
    return PhysicalScaleObservation(
        axis=source_axis,
        minimum_px_per_mm=(
            scale if top == ApertureContactOutcome.HOLDER_TO_IMAGE else None
        ),
        maximum_px_per_mm=(
            scale if top == ApertureContactOutcome.HOLDER_TO_FILM_BASE else None
        ),
        source=PhysicalScaleSource.FRAME_SHORT_AXIS,
        scope=PhysicalScaleScope.CANDIDATE_GEOMETRY,
        provenance=MeasurementProvenance(
            MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
            "aperture_short_axis_scale_observation",
            (
                MeasurementIdentity.BOUNDARY_PATHS,
                MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
            ),
        ),
    )


def physical_scale_observations(
    geometry: SequenceSolution,
    aperture_contact: ApertureContactEvidence,
) -> tuple[PhysicalScaleObservation, ...]:
    dimension_observations = _dimension_consensus_observations(geometry)
    short_axis = _short_axis_observation(geometry, aperture_contact)
    return (
        dimension_observations
        if short_axis is None
        else (*dimension_observations, short_axis)
    )


def candidate_scan_calibration(
    context_calibration: ScanCalibrationResolution,
    geometry: SequenceSolution,
    aperture_contact: ApertureContactEvidence,
) -> ScanCalibrationResolution:
    observations = tuple(
        dict.fromkeys(
            (
                *context_calibration.physical_observations,
                *physical_scale_observations(
                    geometry,
                    aperture_contact,
                ),
            )
        )
    )
    return ScanCalibrationResolution.from_observations(
        context_calibration.metadata,
        observations,
    )


def candidate_scale_observations_match_geometry(
    geometry: SequenceSolution,
    aperture_contact: ApertureContactEvidence,
    calibration: ScanCalibrationResolution,
) -> bool:
    actual = tuple(
        observation
        for observation in calibration.physical_observations
        if observation.scope == PhysicalScaleScope.CANDIDATE_GEOMETRY
    )
    expected = physical_scale_observations(geometry, aperture_contact)

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
