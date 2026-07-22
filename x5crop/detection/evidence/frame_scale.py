from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math

from ...domain import (
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)
from ...geometry.layout import is_horizontal_layout
from ..physical.frame_dimensions import MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS
from ..physical.model import (
    FrameSequenceSolution,
    boundary_role_is_independent_physical_measurement,
)


class FrameScaleSource(str, Enum):
    FRAME_WIDTH_INTERVAL = "frame_width_interval"
    FRAME_HEIGHT_INTERVAL = "frame_height_interval"


@dataclass(frozen=True)
class FrameScaleObservation:
    axis: str
    minimum_px_per_mm: float
    maximum_px_per_mm: float
    source: FrameScaleSource
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.axis not in {"x", "y"}:
            raise ValueError("frame scale observation axis must be x or y")
        if not isinstance(self.source, FrameScaleSource):
            raise TypeError("frame scale observation requires a typed source")
        if any(
            not math.isfinite(value) or value <= 0.0
            for value in (self.minimum_px_per_mm, self.maximum_px_per_mm)
        ):
            raise ValueError("frame scale must be finite and positive")
        if self.maximum_px_per_mm < self.minimum_px_per_mm:
            raise ValueError("frame scale maximum must not be below minimum")
        if self.provenance.root_measurement != MeasurementIdentity.FRAME_DIMENSIONS:
            raise ValueError("frame scale source must match measurement provenance")


def _scale_observation_id(
    label: str,
    *,
    source: FrameScaleSource,
    axis: str,
    physical_dimension_mm: float,
    dependencies: tuple[MeasurementIdentity, ...],
    boundary_anchors: tuple[ObservationId, ...],
) -> ObservationId:
    signature = "\x1f".join(
        (
            source.value,
            axis,
            format(physical_dimension_mm, ".17g"),
            *(dependency.value for dependency in dependencies),
            *(str(anchor) for anchor in boundary_anchors),
        )
    )
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    return ObservationId(f"{label}:{digest}")


def _frame_width_observations(
    geometry: FrameSequenceSolution,
) -> tuple[FrameScaleObservation, ...]:
    width_mm = float(geometry.frame_dimension_prior.frame_size_mm[0])
    axis = "x" if is_horizontal_layout(geometry.layout) else "y"
    slots = tuple(
        slot
        for slot in geometry.frame_slots
        if all(
            boundary_role_is_independent_physical_measurement(boundary)
            for boundary in (slot.leading, slot.trailing)
        )
        and not slot.sequence_inferred
    )
    if len(slots) < MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
        return ()
    observations: list[FrameScaleObservation] = []
    for slot in slots:
        dependencies = tuple(
            dict.fromkeys(
                (
                    MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
                    slot.leading.role_provenance.root_measurement,
                    slot.trailing.role_provenance.root_measurement,
                )
            )
        )
        boundary_anchors = (
            slot.leading.measurement_provenance.observation_id,
            slot.trailing.measurement_provenance.observation_id,
        )
        observations.append(
            FrameScaleObservation(
                axis=axis,
                minimum_px_per_mm=slot.width_px.minimum / width_mm,
                maximum_px_per_mm=slot.width_px.maximum / width_mm,
                source=FrameScaleSource.FRAME_WIDTH_INTERVAL,
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
                    observation_id=_scale_observation_id(
                        f"frame_width_scale:{slot.index}",
                        source=FrameScaleSource.FRAME_WIDTH_INTERVAL,
                        axis=axis,
                        physical_dimension_mm=width_mm,
                        dependencies=dependencies,
                        boundary_anchors=boundary_anchors,
                    ),
                    dependencies=dependencies,
                    description=(
                        "independently measured frame-width scale interval"
                    ),
                    boundary_anchors=boundary_anchors,
                ),
            )
        )
    return tuple(observations)


def _frame_height_observation(
    geometry: FrameSequenceSolution,
) -> FrameScaleObservation | None:
    evidence = geometry.shared_short_axis
    if not evidence.supports_safe_crop:
        return None
    height_mm = float(geometry.frame_dimension_prior.frame_size_mm[1])
    axis = "y" if is_horizontal_layout(geometry.layout) else "x"
    height_px = evidence.height_px
    dependencies = (
        MeasurementIdentity.BOUNDARY_PATHS,
        MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
    )
    boundary_anchors = evidence.provenance.boundary_anchors
    return FrameScaleObservation(
        axis=axis,
        minimum_px_per_mm=height_px.minimum / height_mm,
        maximum_px_per_mm=height_px.maximum / height_mm,
        source=FrameScaleSource.FRAME_HEIGHT_INTERVAL,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
            observation_id=_scale_observation_id(
                "shared_frame_height_scale",
                source=FrameScaleSource.FRAME_HEIGHT_INTERVAL,
                axis=axis,
                physical_dimension_mm=height_mm,
                dependencies=dependencies,
                boundary_anchors=boundary_anchors,
            ),
            dependencies=dependencies,
            description="shared photo-bounded frame-height scale interval",
            boundary_anchors=boundary_anchors,
        ),
    )


def frame_scale_observations(
    geometry: FrameSequenceSolution,
) -> tuple[FrameScaleObservation, ...]:
    widths = _frame_width_observations(geometry)
    height = _frame_height_observation(geometry)
    return widths if height is None else (*widths, height)


def frame_scale_observations_match_geometry(
    geometry: FrameSequenceSolution,
    observations: tuple[FrameScaleObservation, ...],
) -> bool:
    return observations == frame_scale_observations(geometry)
