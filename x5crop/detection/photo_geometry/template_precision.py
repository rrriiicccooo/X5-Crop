"""Explain selected-template uncertainty against the final output budget.

This ledger never selects a placement and never replaces the selected-only
``DirectUseBudgetAssessment``.  It attributes the continuous uncertainty of
one already-selected placement so Debug Analysis can say which physical
unknown consumes the available 5%/3% output budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from .template_measurement_plan import TemplateMeasurementPlan
from .template_placement import FormatPlacement


class PrecisionComponent(str, Enum):
    PHASE = "phase"
    PITCH = "pitch"
    LOCAL_GAP = "local_gap_delta"
    DIRECTION = "direction"
    CROSS_POSITION = "cross_position"
    SAMPLING = "sampling"


@dataclass(frozen=True)
class PrecisionContribution:
    component: PrecisionComponent
    sequence_px: float
    cross_px: float
    conditional_sequence_limit_px: float
    conditional_cross_limit_px: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.component, PrecisionComponent)
            or any(
                not math.isfinite(value) or value < 0.0
                for value in (self.sequence_px, self.cross_px)
            )
            or any(
                not math.isfinite(value)
                for value in (
                    self.conditional_sequence_limit_px,
                    self.conditional_cross_limit_px,
                )
            )
        ):
            raise ValueError("template precision contribution is invalid")


@dataclass(frozen=True)
class TemplatePrecisionLedger:
    placement_id: str
    budget_id: str
    contributions: tuple[PrecisionContribution, ...]
    total_sequence_px: float
    total_cross_px: float
    sequence_limit_px: float
    cross_limit_px: float

    def __post_init__(self) -> None:
        if (
            not self.placement_id
            or not self.budget_id
            or tuple(item.component for item in self.contributions)
            != tuple(PrecisionComponent)
            or not math.isclose(
                self.total_sequence_px,
                sum(item.sequence_px for item in self.contributions),
                abs_tol=1.0e-9,
            )
            or not math.isclose(
                self.total_cross_px,
                sum(item.cross_px for item in self.contributions),
                abs_tol=1.0e-9,
            )
            or min(self.sequence_limit_px, self.cross_limit_px) <= 0.0
        ):
            raise ValueError("template precision ledger is inconsistent")

    @property
    def within_compiled_solo_budget(self) -> bool:
        return (
            self.total_sequence_px <= self.sequence_limit_px
            and self.total_cross_px <= self.cross_limit_px
        )


def _radius(interval: object, canonical: float) -> float:
    return max(
        abs(float(interval.minimum) - canonical),
        abs(float(interval.maximum) - canonical),
    )


def template_precision_ledger(
    placement: FormatPlacement,
    plan: TemplateMeasurementPlan,
    *,
    sampling_uncertainty_px: float = 0.5,
) -> TemplatePrecisionLedger:
    """Attribute continuous uncertainty for one selected placement."""

    if (
        not isinstance(placement, FormatPlacement)
        or not isinstance(plan, TemplateMeasurementPlan)
        or placement.lane_id != plan.lane_id
        or placement.sequence_fit.template.template_id
        != plan.template_spec.template_id
        or not math.isfinite(sampling_uncertainty_px)
        or sampling_uncertainty_px < 0.0
    ):
        raise ValueError("precision ledger requires the selected compiled placement")
    sequence = placement.sequence_fit
    phase = _radius(
        sequence.phase_lattice_fit.absolute_phase_interval_px,
        sequence.phase_lattice_fit.canonical_absolute_phase_px,
    )
    pitch = max(0, placement.output_slot_count - 1) * _radius(
        sequence.pitch_fit.pitch_interval_px,
        sequence.pitch_fit.canonical_pitch_px,
    )
    local_gap = sum(
        _radius(item.delta_interval_px, item.canonical_delta_px)
        for item in sequence.local_advance_relations
        if item.is_anomaly
    )
    angle_radius = math.radians(
        _radius(
            placement.direction.full_angle_interval_degrees,
            placement.direction.canonical_angle_degrees,
        )
    )
    direction_sequence = abs(math.tan(angle_radius)) * (
        placement.height_authority_px.width / 2.0
    )
    direction_cross = abs(math.tan(angle_radius)) * (
        placement.width_authority_px.width / 2.0
    )
    cross = max(
        _radius(
            placement.cross_fit.top_full_interval_px,
            placement.cross_fit.top_canonical_px,
        ),
        _radius(
            placement.cross_fit.bottom_full_interval_px,
            placement.cross_fit.bottom_canonical_px,
        ),
    )
    raw = (
        (PrecisionComponent.PHASE, phase, 0.0),
        (PrecisionComponent.PITCH, pitch, 0.0),
        (PrecisionComponent.LOCAL_GAP, local_gap, 0.0),
        (PrecisionComponent.DIRECTION, direction_sequence, direction_cross),
        (PrecisionComponent.CROSS_POSITION, 0.0, cross),
        (
            PrecisionComponent.SAMPLING,
            sampling_uncertainty_px,
            sampling_uncertainty_px,
        ),
    )
    total_sequence = sum(item[1] for item in raw)
    total_cross = sum(item[2] for item in raw)
    budget = plan.precision_budget
    contributions = tuple(
        PrecisionContribution(
            component,
            sequence_px,
            cross_px,
            budget.sequence_side_limit_px - (total_sequence - sequence_px),
            budget.cross_side_limit_px - (total_cross - cross_px),
        )
        for component, sequence_px, cross_px in raw
    )
    return TemplatePrecisionLedger(
        placement_id=placement.placement_id,
        budget_id=budget.budget_id,
        contributions=contributions,
        total_sequence_px=total_sequence,
        total_cross_px=total_cross,
        sequence_limit_px=budget.sequence_side_limit_px,
        cross_limit_px=budget.cross_side_limit_px,
    )


__all__ = [
    "PrecisionComponent",
    "PrecisionContribution",
    "TemplatePrecisionLedger",
    "template_precision_ledger",
]
