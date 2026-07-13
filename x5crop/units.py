from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .domain import MeasurementIdentity, MeasurementProvenance


MILLIMETERS_PER_INCH = 25.4
MILLIMETERS_PER_CENTIMETER = 10.0
CALIBRATION_INTERVAL_ENDPOINT_COUNT = 2


class CalibrationState(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    APPROXIMATE = "approximate"
    UNAVAILABLE = "unavailable"


class PhysicalScaleSource(str, Enum):
    FRAME_SHORT_AXIS = "frame_short_axis"
    FRAME_DIMENSION_CONSENSUS = "frame_dimension_consensus"


class PhysicalScaleScope(str, Enum):
    ROOT_MEASUREMENT = "root_measurement"
    CANDIDATE_GEOMETRY = "candidate_geometry"


@dataclass(frozen=True)
class ResolutionMetadataObservation:
    x_px_per_mm: float | None
    y_px_per_mm: float | None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        values = (self.x_px_per_mm, self.y_px_per_mm)
        if any(
            value is not None
            and (not math.isfinite(value) or value <= 0.0)
            for value in values
        ):
            raise ValueError("resolution metadata scale must be finite and positive")
        if len(set(self.diagnostics)) != len(self.diagnostics):
            raise ValueError("resolution metadata diagnostics must be unique")

    def px_per_mm(self, axis: str) -> float | None:
        if axis not in {"x", "y"}:
            raise ValueError(f"unsupported resolution metadata axis: {axis}")
        return self.y_px_per_mm if axis == "y" else self.x_px_per_mm


@dataclass(frozen=True)
class PhysicalScaleObservation:
    axis: str
    minimum_px_per_mm: float | None
    maximum_px_per_mm: float | None
    source: PhysicalScaleSource
    scope: PhysicalScaleScope
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.axis not in {"x", "y"}:
            raise ValueError("physical scale observation axis must be x or y")
        if not isinstance(self.source, PhysicalScaleSource):
            raise TypeError("physical scale observation requires a typed source")
        if not isinstance(self.scope, PhysicalScaleScope):
            raise TypeError("physical scale observation requires a typed scope")
        if not isinstance(self.provenance, MeasurementProvenance):
            raise TypeError("physical scale observation requires typed provenance")
        expected_root = {
            PhysicalScaleSource.FRAME_SHORT_AXIS: (
                MeasurementIdentity.SHORT_AXIS_BOUNDARIES
            ),
            PhysicalScaleSource.FRAME_DIMENSION_CONSENSUS: (
                MeasurementIdentity.PHOTO_EDGES
            ),
        }[self.source]
        if self.provenance.root_measurement != expected_root:
            raise ValueError("physical scale source must match measurement provenance")
        values = (self.minimum_px_per_mm, self.maximum_px_per_mm)
        if any(
            value is not None
            and (not math.isfinite(value) or value <= 0.0)
            for value in values
        ):
            raise ValueError("physical scale must be finite and positive")
        if self.minimum_px_per_mm is None and self.maximum_px_per_mm is None:
            raise ValueError("physical scale observation requires at least one bound")
        if (
            self.minimum_px_per_mm is not None
            and self.maximum_px_per_mm is not None
            and self.maximum_px_per_mm < self.minimum_px_per_mm
        ):
            raise ValueError("physical scale maximum must not be below minimum")


@dataclass(frozen=True)
class CalibrationAxisResolution:
    axis: str
    state: CalibrationState
    minimum_px_per_mm: float | None
    maximum_px_per_mm: float | None
    sources: tuple[PhysicalScaleSource, ...]
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.axis not in {"x", "y"}:
            raise ValueError("calibration axis must be x or y")
        if not isinstance(self.state, CalibrationState):
            raise TypeError("calibration axis requires a typed state")
        values = (self.minimum_px_per_mm, self.maximum_px_per_mm)
        if any(
            value is not None
            and (not math.isfinite(value) or value <= 0.0)
            for value in values
        ):
            raise ValueError("calibration axis scale must be finite and positive")
        available = (
            self.minimum_px_per_mm is not None
            or self.maximum_px_per_mm is not None
        )
        if available != (
            self.state
            in {CalibrationState.SUPPORTED, CalibrationState.APPROXIMATE}
        ):
            raise ValueError("calibration state must match scale availability")
        if (
            self.maximum_px_per_mm is not None
            and self.minimum_px_per_mm is not None
            and self.maximum_px_per_mm < self.minimum_px_per_mm
        ):
            raise ValueError("calibration maximum must not be below minimum")
        if self.state == CalibrationState.SUPPORTED and (
            self.minimum_px_per_mm is None or self.maximum_px_per_mm is None
        ):
            raise ValueError("supported calibration requires a bounded scale")
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("calibration sources must be unique")
        if len(set(self.diagnostics)) != len(self.diagnostics):
            raise ValueError("calibration diagnostics must be unique")

    @property
    def px_per_mm(self) -> float | None:
        if self.state != CalibrationState.SUPPORTED:
            return None
        if self.minimum_px_per_mm is None or self.maximum_px_per_mm is None:
            return None
        return (
            self.minimum_px_per_mm + self.maximum_px_per_mm
        ) / CALIBRATION_INTERVAL_ENDPOINT_COUNT


@dataclass(frozen=True)
class ScanCalibrationResolution:
    metadata: ResolutionMetadataObservation
    physical_observations: tuple[PhysicalScaleObservation, ...]
    x: CalibrationAxisResolution
    y: CalibrationAxisResolution

    def __post_init__(self) -> None:
        if self.x.axis != "x" or self.y.axis != "y":
            raise ValueError("scan calibration requires ordered x/y resolutions")
        expected_x = _resolve_axis("x", self.metadata, self.physical_observations)
        expected_y = _resolve_axis("y", self.metadata, self.physical_observations)
        if self.x != expected_x or self.y != expected_y:
            raise ValueError("scan calibration axes must derive from observations")

    @classmethod
    def from_observations(
        cls,
        metadata: ResolutionMetadataObservation,
        physical_observations: tuple[PhysicalScaleObservation, ...],
    ) -> "ScanCalibrationResolution":
        observations = tuple(physical_observations)
        return cls(
            metadata=metadata,
            physical_observations=observations,
            x=_resolve_axis("x", metadata, observations),
            y=_resolve_axis("y", metadata, observations),
        )

    @property
    def fully_supported(self) -> bool:
        return (
            self.x.state == CalibrationState.SUPPORTED
            and self.y.state == CalibrationState.SUPPORTED
        )

    def px_per_mm(self, axis: str) -> float | None:
        if axis not in {"x", "y"}:
            raise ValueError(f"unsupported scan calibration axis: {axis}")
        return self.y.px_per_mm if axis == "y" else self.x.px_per_mm


def _resolve_axis(
    axis: str,
    metadata: ResolutionMetadataObservation,
    observations: tuple[PhysicalScaleObservation, ...],
) -> CalibrationAxisResolution:
    relevant = tuple(item for item in observations if item.axis == axis)
    metadata_value = metadata.px_per_mm(axis)
    if not relevant:
        diagnostics = tuple(
            dict.fromkeys((*metadata.diagnostics, "physical_scale_observation_unavailable"))
        )
        return CalibrationAxisResolution(
            axis,
            CalibrationState.UNAVAILABLE,
            None,
            None,
            (),
            diagnostics,
        )
    lower_bounds = tuple(
        item.minimum_px_per_mm
        for item in relevant
        if item.minimum_px_per_mm is not None
    )
    lower = max(lower_bounds) if lower_bounds else None
    bounded = tuple(
        item.maximum_px_per_mm
        for item in relevant
        if item.maximum_px_per_mm is not None
    )
    upper = min(bounded) if bounded else None
    sources = tuple(dict.fromkeys(item.source for item in relevant))
    if lower is not None and upper is not None and upper < lower:
        return CalibrationAxisResolution(
            axis,
            CalibrationState.CONTRADICTED,
            None,
            None,
            sources,
            ("physical_scale_observations_conflict",),
        )
    diagnostics = list(metadata.diagnostics)
    metadata_compatible = bool(
        metadata_value is not None
        and (lower is None or metadata_value >= lower)
        and (upper is None or metadata_value <= upper)
    )
    if metadata_value is not None and not metadata_compatible:
        diagnostics.append("tiff_resolution_contradicted_by_physical_scale")
    if lower is None or upper is None:
        diagnostics.append(
            "physical_scale_is_lower_bound_only"
            if lower is not None
            else "physical_scale_is_upper_bound_only"
        )
        return CalibrationAxisResolution(
            axis,
            CalibrationState.APPROXIMATE,
            lower,
            upper,
            sources,
            tuple(dict.fromkeys(diagnostics)),
        )
    if metadata_compatible and metadata_value is not None:
        lower = upper = float(metadata_value)
    elif metadata_value is None:
        diagnostics.append("tiff_resolution_unavailable")
    return CalibrationAxisResolution(
        axis,
        CalibrationState.SUPPORTED,
        lower,
        upper,
        sources,
        tuple(dict.fromkeys(diagnostics)),
    )


def _resolution_unit_name(value: int | str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"2", "inch", "inches"}:
        return "inch"
    if raw in {"3", "centimeter", "centimetre", "cm"}:
        return "centimeter"
    if raw in {"1", "none", "no_absolute_unit"}:
        return "none"
    return raw or "missing"


def resolution_metadata_observation(
    resolution: tuple[float, float] | None,
    resolution_unit: int | str | None,
) -> ResolutionMetadataObservation:
    if not resolution:
        return ResolutionMetadataObservation(None, None, ("missing_tiff_resolution",))
    unit = _resolution_unit_name(resolution_unit)
    if unit == "inch":
        divisor = MILLIMETERS_PER_INCH
    elif unit == "centimeter":
        divisor = MILLIMETERS_PER_CENTIMETER
    elif unit == "none":
        return ResolutionMetadataObservation(
            None,
            None,
            ("resolution_unit_has_no_absolute_length",),
        )
    else:
        return ResolutionMetadataObservation(
            None,
            None,
            (f"unsupported_resolution_unit:{unit}",),
        )
    x_res, y_res = resolution
    if x_res <= 0.0 or y_res <= 0.0:
        return ResolutionMetadataObservation(None, None, ("invalid_tiff_resolution",))
    x_px_per_mm = float(x_res) / divisor
    y_px_per_mm = float(y_res) / divisor
    if not math.isfinite(x_px_per_mm) or not math.isfinite(y_px_per_mm):
        return ResolutionMetadataObservation(None, None, ("non_finite_tiff_resolution",))
    return ResolutionMetadataObservation(x_px_per_mm, y_px_per_mm)


def resolution_metadata_after_rotation(
    metadata: ResolutionMetadataObservation,
    angle_degrees: float,
) -> ResolutionMetadataObservation:
    if (
        float(angle_degrees) == 0.0
        or metadata.x_px_per_mm is None
        or metadata.y_px_per_mm is None
        or metadata.x_px_per_mm == metadata.y_px_per_mm
    ):
        return metadata
    return ResolutionMetadataObservation(
        None,
        None,
        tuple(
            dict.fromkeys(
                (*metadata.diagnostics, "anisotropic_resolution_invalid_after_rotation")
            )
        ),
    )


def transposed_scan_calibration(
    calibration: ScanCalibrationResolution,
) -> ScanCalibrationResolution:
    metadata = ResolutionMetadataObservation(
        calibration.metadata.y_px_per_mm,
        calibration.metadata.x_px_per_mm,
        calibration.metadata.diagnostics,
    )
    observations = tuple(
        PhysicalScaleObservation(
            "y" if item.axis == "x" else "x",
            item.minimum_px_per_mm,
            item.maximum_px_per_mm,
            item.source,
            item.scope,
            item.provenance,
        )
        for item in calibration.physical_observations
    )
    return ScanCalibrationResolution.from_observations(metadata, observations)
