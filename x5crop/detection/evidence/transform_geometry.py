from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math

from x5crop.domain import EvidenceState
from x5crop.image.deskew import DeskewMeasurementOutcome


class TransformOutcome(str, Enum):
    DISABLED = "deskew_disabled"
    SPAN_BELOW_THRESHOLD = "span_below_threshold"
    APPLIED = "deskew_applied"
    ANGLE_OUT_OF_RANGE = "angle_out_of_range"


@dataclass(frozen=True)
class TransformGeometryEvidence:
    outcome: TransformOutcome
    estimated_angle_degrees: float
    span_px: float | None
    span_threshold_px: float | None
    measurement_outcome: DeskewMeasurementOutcome | None = None
    state: EvidenceState = field(init=False)
    applied: bool = field(init=False)
    applied_angle_degrees: float = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, TransformOutcome):
            raise TypeError("transform geometry requires a typed outcome")
        if not math.isfinite(self.estimated_angle_degrees):
            raise ValueError("transform geometry angle must be finite")
        if (self.span_px is None) != (self.span_threshold_px is None):
            raise ValueError("transform span and threshold must be present together")
        if self.span_px is not None:
            if (
                not math.isfinite(self.span_px)
                or not math.isfinite(self.span_threshold_px)
                or self.span_px < 0.0
                or self.span_threshold_px <= 0.0
            ):
                raise ValueError("transform span measurements must be finite and valid")
        if self.outcome == TransformOutcome.DISABLED:
            if (
                self.estimated_angle_degrees != 0.0
                or self.span_px is not None
                or self.measurement_outcome is not None
            ):
                raise ValueError("disabled deskew cannot carry transform measurements")
        elif self.span_px is None:
            raise ValueError("measured deskew outcome requires span measurements")
        elif not isinstance(self.measurement_outcome, DeskewMeasurementOutcome):
            raise TypeError("measured transform requires a typed measurement outcome")
        if self.outcome in {
            TransformOutcome.APPLIED,
            TransformOutcome.ANGLE_OUT_OF_RANGE,
        } and self.measurement_outcome != DeskewMeasurementOutcome.MEASURED:
            raise ValueError(
                "applied or out-of-range transform requires a measured deskew angle"
            )
        applied = self.outcome == TransformOutcome.APPLIED
        object.__setattr__(
            self,
            "state",
            (
                EvidenceState.CONTRADICTED
                if self.outcome == TransformOutcome.ANGLE_OUT_OF_RANGE
                else EvidenceState.SUPPORTED
            ),
        )
        object.__setattr__(self, "applied", applied)
        object.__setattr__(
            self,
            "applied_angle_degrees",
            -self.estimated_angle_degrees if applied else 0.0,
        )
        object.__setattr__(
            self,
            "reason",
            (
                self.measurement_outcome.value
                if self.outcome == TransformOutcome.SPAN_BELOW_THRESHOLD
                and self.measurement_outcome != DeskewMeasurementOutcome.MEASURED
                else self.outcome.value
            ),
        )
