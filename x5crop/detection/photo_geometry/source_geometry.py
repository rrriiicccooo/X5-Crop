from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from ...formats import (
    FRAME_DIMENSION_TOLERANCE_SPEC,
    FramePhysicalSpec,
)


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def _intersection(
    left: FiniteInterval,
    right: FiniteInterval,
) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    return (
        None
        if maximum < minimum
        else FiniteInterval(minimum, maximum)
    )


def _common(values: tuple[FiniteInterval, ...]) -> FiniteInterval | None:
    if not values:
        return None
    minimum = max(value.minimum for value in values)
    maximum = min(value.maximum for value in values)
    return None if maximum < minimum else FiniteInterval(minimum, maximum)


def _clip_joint_polygon(
    polygon: tuple[tuple[float, float], ...],
    *,
    inside,
    intersect,
) -> tuple[tuple[float, float], ...]:
    if not polygon:
        return ()
    output: list[tuple[float, float]] = []
    previous = polygon[-1]
    previous_inside = inside(previous)
    for current in polygon:
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                output.append(intersect(previous, current))
            output.append(current)
        elif previous_inside:
            output.append(intersect(previous, current))
        previous = current
        previous_inside = current_inside
    return tuple(output)


def _intersect_horizontal(
    left: tuple[float, float],
    right: tuple[float, float],
    value: float,
) -> tuple[float, float]:
    delta_scale = right[0] - left[0]
    delta_normalized = right[1] - left[1]
    if abs(delta_normalized) <= 1.0e-15:
        return (left[0], value)
    factor = (value - left[1]) / delta_normalized
    return (left[0] + factor * delta_scale, value)


@dataclass(frozen=True)
class JointAxisGeometry:
    """Correlated positive `(scale, normalized extent)` source state."""

    axis_name: str
    design_extent_mm: float
    scale_authority: PositiveInterval
    factor_authority: PositiveInterval
    observed_normalized_extent: FiniteInterval | None
    observation_ids: tuple[ObservationId, ...]
    vertices: tuple[tuple[float, float], ...]

    @classmethod
    def create(
        cls,
        *,
        axis_name: str,
        design_extent_mm: float,
        scale_interval_px_per_mm: PositiveInterval,
        factor_interval: PositiveInterval,
    ) -> "JointAxisGeometry":
        if axis_name not in {"width", "height"}:
            raise ValueError("joint axis geometry requires width or height")
        if not math.isfinite(design_extent_mm) or design_extent_mm <= 0.0:
            raise ValueError("joint axis design extent must be positive")
        return cls._from_constraints(
            axis_name=axis_name,
            design_extent_mm=design_extent_mm,
            scale_authority=scale_interval_px_per_mm,
            factor_authority=factor_interval,
            observed_normalized_extent=None,
            observation_ids=(),
        )

    @classmethod
    def _from_constraints(
        cls,
        *,
        axis_name: str,
        design_extent_mm: float,
        scale_authority: PositiveInterval,
        factor_authority: PositiveInterval,
        observed_normalized_extent: FiniteInterval | None,
        observation_ids: tuple[ObservationId, ...],
    ) -> "JointAxisGeometry":
        scale_minimum, scale_maximum = (
            scale_authority.minimum,
            scale_authority.maximum,
        )
        factor_minimum, factor_maximum = (
            factor_authority.minimum,
            factor_authority.maximum,
        )
        polygon: tuple[tuple[float, float], ...] = (
            (scale_minimum, factor_minimum * scale_minimum),
            (scale_maximum, factor_minimum * scale_maximum),
            (scale_maximum, factor_maximum * scale_maximum),
            (scale_minimum, factor_maximum * scale_minimum),
        )
        if observed_normalized_extent is not None:
            observed_minimum = observed_normalized_extent.minimum
            observed_maximum = observed_normalized_extent.maximum
            polygon = _clip_joint_polygon(
                polygon,
                inside=lambda point: point[1] >= observed_minimum - 1.0e-12,
                intersect=lambda left, right: _intersect_horizontal(
                    left,
                    right,
                    observed_minimum,
                ),
            )
            polygon = _clip_joint_polygon(
                polygon,
                inside=lambda point: point[1] <= observed_maximum + 1.0e-12,
                intersect=lambda left, right: _intersect_horizontal(
                    left,
                    right,
                    observed_maximum,
                ),
            )
        if not polygon:
            raise ValueError("joint axis geometry is infeasible")
        vertices: list[tuple[float, float]] = []
        for scale, normalized in polygon:
            point = (float(scale), float(normalized))
            if not vertices or any(
                abs(left - right) > 1.0e-10
                for left, right in zip(vertices[-1], point, strict=True)
            ):
                vertices.append(point)
        if len(vertices) > 1 and all(
            abs(left - right) <= 1.0e-10
            for left, right in zip(vertices[0], vertices[-1], strict=True)
        ):
            vertices.pop()
        return cls(
            axis_name=axis_name,
            design_extent_mm=design_extent_mm,
            scale_authority=scale_authority,
            factor_authority=factor_authority,
            observed_normalized_extent=observed_normalized_extent,
            observation_ids=observation_ids,
            vertices=tuple(vertices),
        )

    def __post_init__(self) -> None:
        if (
            self.axis_name not in {"width", "height"}
            or self.design_extent_mm <= 0.0
            or not self.vertices
            or len(set(self.observation_ids)) != len(self.observation_ids)
            or any(
                not (
                    self.scale_authority.minimum - 1.0e-9 <= scale
                    <= self.scale_authority.maximum + 1.0e-9
                    and self.factor_authority.minimum * scale - 1.0e-9
                    <= normalized
                    <= self.factor_authority.maximum * scale + 1.0e-9
                )
                for scale, normalized in self.vertices
            )
        ):
            raise ValueError("joint axis geometry is invalid")

    def intersect_observed_extent(
        self,
        extent_interval_px: FiniteInterval,
        *,
        observation_ids: tuple[ObservationId, ...],
    ) -> "JointAxisGeometry":
        if not observation_ids:
            raise ValueError("observed extent requires pixel provenance")
        normalized = FiniteInterval(
            extent_interval_px.minimum / self.design_extent_mm,
            extent_interval_px.maximum / self.design_extent_mm,
        )
        combined = (
            normalized
            if self.observed_normalized_extent is None
            else _intersection(self.observed_normalized_extent, normalized)
        )
        if combined is None:
            raise ValueError("observed extent contradicts source geometry")
        identities = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    *(str(identity) for identity in self.observation_ids),
                    *(str(identity) for identity in observation_ids),
                }
            )
        )
        return self._from_constraints(
            axis_name=self.axis_name,
            design_extent_mm=self.design_extent_mm,
            scale_authority=self.scale_authority,
            factor_authority=self.factor_authority,
            observed_normalized_extent=combined,
            observation_ids=identities,
        )

    def intersect_state(self, other: "JointAxisGeometry") -> "JointAxisGeometry":
        if (
            self.axis_name != other.axis_name
            or self.design_extent_mm != other.design_extent_mm
        ):
            raise ValueError("joint axis states describe different physics")
        scale_minimum = max(
            self.scale_authority.minimum,
            other.scale_authority.minimum,
        )
        scale_maximum = min(
            self.scale_authority.maximum,
            other.scale_authority.maximum,
        )
        factor_minimum = max(
            self.factor_authority.minimum,
            other.factor_authority.minimum,
        )
        factor_maximum = min(
            self.factor_authority.maximum,
            other.factor_authority.maximum,
        )
        if scale_maximum < scale_minimum or factor_maximum < factor_minimum:
            raise ValueError("source-wide joint axis states do not intersect")
        observed_values = tuple(
            value
            for value in (
                self.observed_normalized_extent,
                other.observed_normalized_extent,
            )
            if value is not None
        )
        observed = _common(observed_values) if observed_values else None
        if observed_values and observed is None:
            raise ValueError("source-wide observed extents do not intersect")
        identities = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    *(str(identity) for identity in self.observation_ids),
                    *(str(identity) for identity in other.observation_ids),
                }
            )
        )
        return self._from_constraints(
            axis_name=self.axis_name,
            design_extent_mm=self.design_extent_mm,
            scale_authority=PositiveInterval(scale_minimum, scale_maximum),
            factor_authority=PositiveInterval(factor_minimum, factor_maximum),
            observed_normalized_extent=observed,
            observation_ids=identities,
        )

    def feasible_scale_interval(self) -> PositiveInterval:
        values = tuple(point[0] for point in self.vertices)
        return PositiveInterval(min(values), max(values))

    def normalized_extent_projection(self) -> FiniteInterval:
        values = tuple(point[1] for point in self.vertices)
        return FiniteInterval(min(values), max(values))

    def extent_projection_px(self) -> FiniteInterval:
        normalized = self.normalized_extent_projection()
        return FiniteInterval(
            self.design_extent_mm * normalized.minimum,
            self.design_extent_mm * normalized.maximum,
        )

    def factor_projection(self) -> PositiveInterval:
        values = tuple(normalized / scale for scale, normalized in self.vertices)
        return PositiveInterval(
            max(self.factor_authority.minimum, min(values)),
            min(self.factor_authority.maximum, max(values)),
        )

    def canonical_state(self) -> tuple[float, float, float]:
        scale_projection = self.feasible_scale_interval()
        scale = (scale_projection.minimum + scale_projection.maximum) / 2.0
        lower = self.factor_authority.minimum * scale
        upper = self.factor_authority.maximum * scale
        if self.observed_normalized_extent is not None:
            lower = max(lower, self.observed_normalized_extent.minimum)
            upper = min(upper, self.observed_normalized_extent.maximum)
        if upper < lower:
            scale, normalized = min(
                self.vertices,
                key=lambda point: (
                    abs(point[0] - scale),
                    point[0],
                    point[1],
                ),
            )
        else:
            normalized = (lower + upper) / 2.0
        return scale, normalized, normalized / scale

    def project_affine(
        self,
        *,
        q_coefficient: float,
        scale_coefficient: float,
    ) -> FiniteInterval:
        if not all(
            math.isfinite(value)
            for value in (q_coefficient, scale_coefficient)
        ):
            raise ValueError("joint projection coefficients must be finite")
        values = tuple(
            q_coefficient * normalized + scale_coefficient * scale
            for scale, normalized in self.vertices
        )
        return FiniteInterval(min(values), max(values))

    def design_budget_px(self, ratio_per_side: float) -> FiniteInterval:
        if not math.isfinite(ratio_per_side) or ratio_per_side <= 0.0:
            raise ValueError("direct-use ratio must be positive")
        scale = self.feasible_scale_interval()
        return FiniteInterval(
            self.design_extent_mm * ratio_per_side * scale.minimum,
            self.design_extent_mm * ratio_per_side * scale.maximum,
        )

    def worst_case_mm(self, distance_px: float) -> float:
        if not math.isfinite(distance_px) or distance_px < 0.0:
            raise ValueError("pixel distance must be finite and non-negative")
        return distance_px / self.feasible_scale_interval().minimum


@dataclass(frozen=True)
class SourceFrameGeometry:
    geometry_id: str
    component: FramePhysicalSpec
    width_state: JointAxisGeometry
    height_state: JointAxisGeometry

    @classmethod
    def create(
        cls,
        component: FramePhysicalSpec,
        *,
        width_scale_px_per_mm: PositiveInterval,
        height_scale_px_per_mm: PositiveInterval,
    ) -> "SourceFrameGeometry":
        tolerance = FRAME_DIMENSION_TOLERANCE_SPEC
        width = JointAxisGeometry.create(
            axis_name="width",
            design_extent_mm=component.frame_width_mm,
            scale_interval_px_per_mm=width_scale_px_per_mm,
            factor_interval=PositiveInterval(
                1.0 - tolerance.frame_width_tolerance_ratio,
                1.0 + tolerance.frame_width_tolerance_ratio,
            ),
        )
        height = JointAxisGeometry.create(
            axis_name="height",
            design_extent_mm=component.frame_height_mm,
            scale_interval_px_per_mm=height_scale_px_per_mm,
            factor_interval=PositiveInterval(
                1.0 - tolerance.frame_height_tolerance_ratio,
                1.0 + tolerance.frame_height_tolerance_ratio,
            ),
        )
        return cls(
            geometry_id=_stable_id(
                "source-frame-geometry",
                component.component_id,
                width_scale_px_per_mm,
                height_scale_px_per_mm,
            ),
            component=component,
            width_state=width,
            height_state=height,
        )

    def __post_init__(self) -> None:
        if (
            not self.geometry_id
            or self.width_state.axis_name != "width"
            or self.height_state.axis_name != "height"
            or self.width_state.design_extent_mm != self.component.frame_width_mm
            or self.height_state.design_extent_mm
            != self.component.frame_height_mm
        ):
            raise ValueError("source frame geometry is invalid")

    def intersect_source_state(
        self,
        other: "SourceFrameGeometry",
    ) -> "SourceFrameGeometry":
        if self.component != other.component:
            raise ValueError("source geometries use different components")
        width = self.width_state.intersect_state(other.width_state)
        height = self.height_state.intersect_state(other.height_state)
        return SourceFrameGeometry(
            geometry_id=_stable_id(
                "source-frame-geometry",
                self.component.component_id,
                width.vertices,
                height.vertices,
                width.observation_ids,
                height.observation_ids,
            ),
            component=self.component,
            width_state=width,
            height_state=height,
        )


@dataclass(frozen=True)
class NominalPitch:
    nominal_gap_mm: float
    joint_width_geometry_id: str
    pitch_interval_px: FiniteInterval
    canonical_pitch_px: float

    @classmethod
    def from_geometry(
        cls,
        width_state: JointAxisGeometry,
        *,
        nominal_gap_mm: float,
    ) -> "NominalPitch":
        if width_state.axis_name != "width" or nominal_gap_mm < 0.0:
            raise ValueError("nominal pitch requires width geometry")
        pitch = width_state.project_affine(
            q_coefficient=width_state.design_extent_mm,
            scale_coefficient=nominal_gap_mm,
        )
        scale, normalized, _factor = width_state.canonical_state()
        canonical = (
            width_state.design_extent_mm * normalized
            + nominal_gap_mm * scale
        )
        return cls(
            nominal_gap_mm=nominal_gap_mm,
            joint_width_geometry_id=_stable_id(
                "joint-width-state",
                width_state.vertices,
                width_state.observation_ids,
            ),
            pitch_interval_px=pitch,
            canonical_pitch_px=canonical,
        )

    def __post_init__(self) -> None:
        if (
            not self.joint_width_geometry_id
            or not math.isfinite(self.nominal_gap_mm)
            or self.nominal_gap_mm < 0.0
            or not self.pitch_interval_px.contains(
                self.canonical_pitch_px,
                epsilon=1.0e-9,
            )
        ):
            raise ValueError("nominal pitch is invalid")
