from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math

from ..domain import EvidenceState, FiniteInterval
from ..geometry.affine import AffineCoordinateTransform
from .photo_geometry.model import (
    BoundaryRole,
    MAXIMUM_OUTPUT_ROTATION_DEGREES,
    PhotoBoundaryObservation,
    SharedStripDirection,
)


def observed_strip_angle_estimate_degrees(
    observations: tuple[PhotoBoundaryObservation, ...],
) -> float:
    """Return the support-weighted raw strip-angle estimate.

    The estimate describes pixel evidence only.  It does not create the
    canonical output direction and therefore does not apply the zero-angle
    preference used by :func:`resolve_shared_strip_direction`.
    """

    if not observations:
        raise ValueError("strip-angle estimate requires observations")
    weighted_sum = sum(
        item.fit_angle_interval_degrees.center
        * max(1.0, float(item.trace_support_count))
        / (1.0 + item.fit_residual_px)
        for item in observations
    )
    total_weight = sum(
        max(1.0, float(item.trace_support_count))
        / (1.0 + item.fit_residual_px)
        for item in observations
    )
    estimate = weighted_sum / total_weight
    if not math.isfinite(estimate):
        raise ValueError("strip-angle estimate is not finite")
    return estimate


@dataclass(frozen=True)
class SharedStripDirectionResolution:
    direction: SharedStripDirection | None
    state: EvidenceState
    named_gap: str | None

    def __post_init__(self) -> None:
        supported = self.state == EvidenceState.SUPPORTED
        if (
            supported != (self.direction is not None)
            or supported == (self.named_gap is not None)
        ):
            raise ValueError("shared strip direction resolution is inconsistent")


@dataclass(frozen=True)
class OutputTransformAssessment:
    transform: AffineCoordinateTransform | None
    outcome: str
    state: EvidenceState
    named_gap: str | None
    observed_angle_interval_degrees: FiniteInterval | None
    applied_source_rotation_degrees: float | None
    authority: str | None

    def __post_init__(self) -> None:
        if self.outcome not in {
            "identity",
            "shared_rotation",
            "unavailable",
        }:
            raise ValueError("unknown output-transform outcome")
        if self.authority not in {
            None,
            "shared_strip_direction",
        }:
            raise ValueError("unknown output-transform authority")
        supported = self.state == EvidenceState.SUPPORTED
        if supported:
            if (
                self.transform is None
                or self.named_gap is not None
                or self.observed_angle_interval_degrees is None
                or self.applied_source_rotation_degrees is None
                or self.authority is None
            ):
                raise ValueError("supported transform assessment is incomplete")
            if (
                self.outcome == "identity"
                and (
                    not self.transform.is_identity
                    or self.applied_source_rotation_degrees != 0.0
                    or not self.observed_angle_interval_degrees.contains(0.0)
                )
            ):
                raise ValueError("identity transform lacks zero-angle evidence")
            if (
                self.outcome == "shared_rotation"
                and (
                    self.authority != "shared_strip_direction"
                    or
                    self.transform.is_identity
                    or self.applied_source_rotation_degrees == 0.0
                )
            ):
                raise ValueError("shared rotation must be non-identity")
        elif (
            self.outcome != "unavailable"
            or self.transform is not None
            or self.named_gap is None
            or self.applied_source_rotation_degrees is not None
            or self.authority is not None
        ):
            raise ValueError("unavailable transform assessment is inconsistent")


def resolve_shared_strip_direction(
    observations: tuple[PhotoBoundaryObservation, ...],
) -> SharedStripDirectionResolution:
    """Resolve the sole canonical direction from selected top/bottom evidence."""

    unique_all = tuple(
        {
            str(item.observation_id): item
            for item in observations
        }.values()
    )
    unique = tuple(
        item
        for item in unique_all
        if item.role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
    )
    if not unique:
        return SharedStripDirectionResolution(
            direction=None,
            state=EvidenceState.UNAVAILABLE,
            named_gap="observed_long_edge_rotation_unavailable",
        )
    fit_intervals = tuple(
        item.fit_angle_interval_degrees for item in unique
    )
    if any(item is None for item in fit_intervals):
        raise ValueError("direction observation lacks fit angle interval")
    common_minimum = max(item.minimum for item in fit_intervals if item)
    common_maximum = min(item.maximum for item in fit_intervals if item)
    if common_minimum > common_maximum:
        return SharedStripDirectionResolution(
            direction=None,
            state=EvidenceState.UNAVAILABLE,
            named_gap="shared_observed_rotation_interval_unavailable",
        )
    common = FiniteInterval(common_minimum, common_maximum)
    full = FiniteInterval(
        min(item.angle_interval_degrees.minimum for item in unique),
        max(item.angle_interval_degrees.maximum for item in unique),
    )
    estimate = observed_strip_angle_estimate_degrees(unique)
    canonical_angle = (
        0.0
        if common.contains(0.0)
        else min(common.maximum, max(common.minimum, estimate))
    )
    if (
        abs(canonical_angle) > MAXIMUM_OUTPUT_ROTATION_DEGREES
        or not math.isfinite(canonical_angle)
    ):
        return SharedStripDirectionResolution(
            direction=None,
            state=EvidenceState.UNAVAILABLE,
            named_gap="observed_rotation_exceeds_two_degrees",
        )
    observation_ids = tuple(
        sorted((item.observation_id for item in unique), key=str)
    )
    direction_payload = "\x1f".join(
        (
            *(str(identity) for identity in observation_ids),
            f"{common.minimum:.12f}",
            f"{common.maximum:.12f}",
            f"{canonical_angle:.12f}",
        )
    ).encode("utf-8")
    return SharedStripDirectionResolution(
        direction=SharedStripDirection(
            direction_id=(
                "shared-strip-direction:"
                + sha256(direction_payload).hexdigest()[:24]
            ),
            selected_observation_ids=observation_ids,
            full_angle_interval_degrees=full,
            canonical_angle_degrees=canonical_angle,
        ),
        state=EvidenceState.SUPPORTED,
        named_gap=None,
    )


def output_transform_assessment(
    direction_resolution: SharedStripDirectionResolution,
    *,
    layout: str,
    source_width: int,
    source_height: int,
) -> OutputTransformAssessment:
    """Build one transform directly from the resolved canonical direction."""

    if layout not in {"horizontal", "vertical"}:
        raise ValueError(f"unsupported transform layout: {layout}")
    if min(source_width, source_height) <= 0:
        raise ValueError("output transform requires positive source extent")
    direction = direction_resolution.direction
    if direction is None:
        return OutputTransformAssessment(
            transform=None,
            outcome="unavailable",
            state=EvidenceState.UNAVAILABLE,
            named_gap=direction_resolution.named_gap,
            observed_angle_interval_degrees=None,
            applied_source_rotation_degrees=None,
            authority=None,
        )
    canonical_angle = direction.canonical_angle_degrees
    common = direction.full_angle_interval_degrees
    if canonical_angle == 0.0:
        return OutputTransformAssessment(
            transform=AffineCoordinateTransform.identity(
                source_width,
                source_height,
            ),
            outcome="identity",
            state=EvidenceState.SUPPORTED,
            named_gap=None,
            observed_angle_interval_degrees=common,
            applied_source_rotation_degrees=0.0,
            authority="shared_strip_direction",
        )
    source_rotation = -canonical_angle
    return OutputTransformAssessment(
        transform=AffineCoordinateTransform.expanded_rotation(
            source_width,
            source_height,
            source_rotation,
            guard_px=1.0,
        ),
        outcome="shared_rotation",
        state=EvidenceState.SUPPORTED,
        named_gap=None,
        observed_angle_interval_degrees=common,
        applied_source_rotation_degrees=source_rotation,
        authority="shared_strip_direction",
    )
