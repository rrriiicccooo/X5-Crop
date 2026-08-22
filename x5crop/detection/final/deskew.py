"""Decision-independent assessment for optional output deskew."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import EvidenceState
from ...geometry.affine import AffineCoordinateTransform
from ..output_deskew import (
    DeskewSkipReason,
    LightweightDeskewObservation,
)


DESKEW_MINIMUM_ENDPOINT_DISPLACEMENT_PX = 3.0


@dataclass(frozen=True)
class OutputDeskewAssessment:
    """One cosmetic output transform assessed only after DecisionGate."""

    deskew_applied: bool
    observed_angle_degrees: float | None
    applied_source_rotation_degrees: float | None
    skip_reason: DeskewSkipReason | None
    transform: AffineCoordinateTransform

    def __post_init__(self) -> None:
        if not isinstance(self.transform, AffineCoordinateTransform):
            raise TypeError("deskew assessment requires one affine transform")
        if self.deskew_applied:
            if (
                self.observed_angle_degrees is None
                or not math.isfinite(self.observed_angle_degrees)
                or self.applied_source_rotation_degrees is None
                or not math.isfinite(self.applied_source_rotation_degrees)
                or self.applied_source_rotation_degrees == 0.0
                or self.skip_reason is not None
                or self.transform.is_identity
            ):
                raise ValueError("applied deskew assessment is incomplete")
            return
        if not self.transform.is_identity:
            raise ValueError("skipped deskew must preserve source orientation")
        measurement_unavailable = self.observed_angle_degrees is None
        if measurement_unavailable:
            if (
                self.applied_source_rotation_degrees is not None
                or not isinstance(self.skip_reason, DeskewSkipReason)
                or self.skip_reason == DeskewSkipReason.ROTATION_NOT_NEEDED
            ):
                raise ValueError("unavailable deskew assessment is inconsistent")
        elif (
            not math.isfinite(self.observed_angle_degrees)
            or self.applied_source_rotation_degrees != 0.0
            or self.skip_reason != DeskewSkipReason.ROTATION_NOT_NEEDED
        ):
            raise ValueError("unneeded deskew assessment is inconsistent")


def assess_output_deskew(
    observation: LightweightDeskewObservation | None,
    *,
    layout: str,
    source_width: int,
    source_height: int,
) -> OutputDeskewAssessment:
    """Turn one optional observation into an identity or expanded rotation."""

    if layout not in {"horizontal", "vertical"}:
        raise ValueError(f"unsupported deskew layout: {layout}")
    if min(source_width, source_height) <= 0:
        raise ValueError("output deskew requires a positive source extent")
    identity = AffineCoordinateTransform.identity(source_width, source_height)
    if observation is None:
        return OutputDeskewAssessment(
            deskew_applied=False,
            observed_angle_degrees=None,
            applied_source_rotation_degrees=None,
            skip_reason=DeskewSkipReason.OUTPUT_NOT_ELIGIBLE,
            transform=identity,
        )
    if not isinstance(observation, LightweightDeskewObservation):
        raise TypeError("output deskew requires its canonical observation")
    if observation.state == EvidenceState.UNAVAILABLE:
        if observation.skip_reason is None:
            raise ValueError("unavailable deskew lacks its typed skip reason")
        return OutputDeskewAssessment(
            deskew_applied=False,
            observed_angle_degrees=None,
            applied_source_rotation_degrees=None,
            skip_reason=observation.skip_reason,
            transform=identity,
        )
    if observation.state != EvidenceState.SUPPORTED:
        raise ValueError("output deskew observation has an invalid state")
    observed_angle = observation.angle_degrees
    if observed_angle is None:
        raise ValueError("supported deskew lacks its observed angle")
    long_extent = (
        source_width - 1 if layout == "horizontal" else source_height - 1
    )
    endpoint_displacement = abs(
        math.tan(math.radians(observed_angle)) * long_extent
    )
    if endpoint_displacement < DESKEW_MINIMUM_ENDPOINT_DISPLACEMENT_PX:
        return OutputDeskewAssessment(
            deskew_applied=False,
            observed_angle_degrees=observed_angle,
            applied_source_rotation_degrees=0.0,
            skip_reason=DeskewSkipReason.ROTATION_NOT_NEEDED,
            transform=identity,
        )
    source_rotation = (
        -observed_angle if layout == "horizontal" else observed_angle
    )
    return OutputDeskewAssessment(
        deskew_applied=True,
        observed_angle_degrees=observed_angle,
        applied_source_rotation_degrees=source_rotation,
        skip_reason=None,
        transform=AffineCoordinateTransform.expanded_rotation(
            source_width,
            source_height,
            source_rotation,
        ),
    )
