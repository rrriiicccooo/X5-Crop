from __future__ import annotations

from dataclasses import dataclass
import math

from ..domain import EvidenceState, FiniteInterval
from ..geometry.affine import AffineCoordinateTransform
from .photo_geometry.model import PhotoBoundaryObservation


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
            "observed_rotation",
            "unavailable",
        }:
            raise ValueError("unknown output-transform outcome")
        if self.authority not in {
            None,
            "observed_photo_lines",
            "grid_blank_no_photo_geometry",
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
                self.outcome == "observed_rotation"
                and (
                    self.authority != "observed_photo_lines"
                    or
                    self.transform.is_identity
                    or self.applied_source_rotation_degrees == 0.0
                )
            ):
                raise ValueError("observed rotation must be non-identity")
        elif (
            self.outcome != "unavailable"
            or self.transform is not None
            or self.named_gap is None
            or self.applied_source_rotation_degrees is not None
            or self.authority is not None
        ):
            raise ValueError("unavailable transform assessment is inconsistent")


def observed_output_transform_assessment(
    observations: tuple[PhotoBoundaryObservation, ...],
    *,
    layout: str,
    source_width: int,
    source_height: int,
    allow_grid_blank_identity: bool = False,
) -> OutputTransformAssessment:
    """Resolve one transform from the exact intersection of observed angles."""

    if layout not in {"horizontal", "vertical"}:
        raise ValueError(f"unsupported transform layout: {layout}")
    if min(source_width, source_height) <= 0:
        raise ValueError("output transform requires positive source extent")
    if not observations:
        if allow_grid_blank_identity:
            return OutputTransformAssessment(
                transform=AffineCoordinateTransform.identity(
                    source_width,
                    source_height,
                ),
                outcome="identity",
                state=EvidenceState.SUPPORTED,
                named_gap=None,
                observed_angle_interval_degrees=FiniteInterval.exact(0.0),
                applied_source_rotation_degrees=0.0,
                authority="grid_blank_no_photo_geometry",
            )
        return OutputTransformAssessment(
            transform=None,
            outcome="unavailable",
            state=EvidenceState.UNAVAILABLE,
            named_gap="observed_rotation_unavailable",
            observed_angle_interval_degrees=None,
            applied_source_rotation_degrees=None,
            authority=None,
        )
    unique_all = tuple(
        {
            str(item.observation_id): item
            for item in observations
        }.values()
    )
    # Top/bottom observations measure the common strip rotation along the
    # photo long axis.  Start/end lines remain observed polygon boundaries,
    # but individual aperture cuts may be non-orthogonal and therefore cannot
    # establish or widen the shared deskew angle.
    unique = tuple(
        item
        for item in unique_all
        if item.role.value in {"top", "bottom"}
    )
    if not unique:
        return OutputTransformAssessment(
            transform=None,
            outcome="unavailable",
            state=EvidenceState.UNAVAILABLE,
            named_gap="observed_long_edge_rotation_unavailable",
            observed_angle_interval_degrees=None,
            applied_source_rotation_degrees=None,
            authority=None,
        )
    common_minimum = max(
        item.angle_interval_degrees.minimum for item in unique
    )
    common_maximum = min(
        item.angle_interval_degrees.maximum for item in unique
    )
    if common_minimum > common_maximum:
        return OutputTransformAssessment(
            transform=None,
            outcome="unavailable",
            state=EvidenceState.UNAVAILABLE,
            named_gap="shared_observed_rotation_interval_unavailable",
            observed_angle_interval_degrees=None,
            applied_source_rotation_degrees=None,
            authority=None,
        )
    common = FiniteInterval(common_minimum, common_maximum)
    weighted_sum = sum(
        item.angle_interval_degrees.center
        * max(1.0, float(item.trace_support_count))
        / (1.0 + item.fit_residual_px)
        for item in unique
    )
    total_weight = sum(
        max(1.0, float(item.trace_support_count))
        / (1.0 + item.fit_residual_px)
        for item in unique
    )
    estimate = weighted_sum / total_weight
    if common.contains(0.0):
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
            authority="observed_photo_lines",
        )
    canonical_angle = min(
        common.maximum,
        max(common.minimum, estimate),
    )
    if abs(canonical_angle) > 2.0 or not math.isfinite(canonical_angle):
        return OutputTransformAssessment(
            transform=None,
            outcome="unavailable",
            state=EvidenceState.UNAVAILABLE,
            named_gap="observed_rotation_exceeds_two_degrees",
            observed_angle_interval_degrees=common,
            applied_source_rotation_degrees=None,
            authority=None,
        )
    source_rotation = (
        -canonical_angle
        if layout == "horizontal"
        else canonical_angle
    )
    return OutputTransformAssessment(
        transform=AffineCoordinateTransform.expanded_rotation(
            source_width,
            source_height,
            source_rotation,
            guard_px=1.0,
        ),
        outcome="observed_rotation",
        state=EvidenceState.SUPPORTED,
        named_gap=None,
        observed_angle_interval_degrees=common,
        applied_source_rotation_degrees=source_rotation,
        authority="observed_photo_lines",
    )
