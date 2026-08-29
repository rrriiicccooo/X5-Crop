"""Canonical result records for bounded sequence phase fitting."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_model import (
    SequenceFit,
    TemplateSearchReceipt,
    TemplateSpec,
)


@dataclass(frozen=True)
class TemplatePhaseInput:
    """Exact registered input to the bounded phase/advance solver."""

    observations: tuple[BoundaryEdgeObservation, ...]
    separator_bands: tuple[SeparatorBandObservation, ...]
    template: TemplateSpec
    scale_px_per_mm: PositiveInterval | None
    holder_span_px: FiniteInterval | None
    phase_authority_px: FiniteInterval | None
    max_observations: int = 512

    def __post_init__(self) -> None:
        if not isinstance(self.template, TemplateSpec):
            raise TypeError("phase input requires a fixed template")
        if self.scale_px_per_mm is not None and not isinstance(
            self.scale_px_per_mm,
            PositiveInterval,
        ):
            raise TypeError("phase input scale must be a positive interval")
        for value, name in (
            (self.holder_span_px, "holder span"),
            (self.phase_authority_px, "phase authority"),
        ):
            if value is not None and not isinstance(value, FiniteInterval):
                raise TypeError(f"phase input {name} must be a finite interval")
        identities = tuple(item.observation_id for item in self.observations)
        band_ids = tuple(item.observation_id for item in self.separator_bands)
        if (
            len(set(identities)) != len(identities)
            or len(set(band_ids)) != len(band_ids)
            or not isinstance(self.max_observations, int)
            or self.max_observations <= 0
        ):
            raise ValueError("phase input identities or bound are invalid")


class PhaseFitStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"
    BOUND_EXCEEDED = "bound_exceeded"


class PhaseFailureKind(str, Enum):
    OBSERVATION_BOUND_EXCEEDED = "observation_bound_exceeded"
    HYPOTHESIS_BOUND_EXCEEDED = "hypothesis_bound_exceeded"
    DIRECT_PHASE_ANCHOR_UNAVAILABLE = "direct_phase_anchor_unavailable"
    PHASE_SUPPORT_DISCONTINUITY = "phase_support_discontinuity"
    FIXED_TEMPLATE_MISMATCH = "fixed_template_mismatch"
    DISCRETE_PHASE_AMBIGUOUS = "discrete_phase_ambiguous"
    LOCAL_ADVANCE_AMBIGUOUS = "local_advance_ambiguous"


class PhaseWinnerBasis(str, Enum):
    ONLY_PHYSICAL_FIT = "only_physical_fit"
    RESIDUAL_COMPATIBILITY = "residual_compatibility"
    INDEPENDENT_SUPPORT = "independent_support"
    INDEPENDENT_COVERAGE = "independent_coverage"
    RESIDUAL_SEPARATION = "residual_separation"
    CALIBRATED_RUNNER_REJECTED = "calibrated_runner_rejected"


@dataclass(frozen=True)
class PhaseFitResult:
    template: TemplateSpec
    best: SequenceFit | None
    runner_up: SequenceFit | None
    status: PhaseFitStatus
    ambiguity_reason: str | None
    receipt: TemplateSearchReceipt
    registered_direct_observation_ids: tuple[ObservationId, ...]
    failure_kind: PhaseFailureKind | None = None
    winner_basis: PhaseWinnerBasis | None = None

    def __post_init__(self) -> None:
        if (
            len(set(self.registered_direct_observation_ids))
            != len(self.registered_direct_observation_ids)
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.registered_direct_observation_ids
            )
        ):
            raise ValueError("registered direct observation ledger is invalid")
        if self.status == PhaseFitStatus.RESOLVED and self.best is None:
            raise ValueError("resolved phase fit requires a placement")
        if self.status == PhaseFitStatus.BOUND_EXCEEDED and self.best is not None:
            raise ValueError("bound-exceeded phase fit cannot authorize placement")
        if self.ambiguity_reason is not None and not self.ambiguity_reason:
            raise ValueError("phase ambiguity reason must not be empty")
        if (self.status == PhaseFitStatus.RESOLVED) != (self.failure_kind is None):
            raise ValueError("phase failure kind must match fit status")
        if (self.status == PhaseFitStatus.RESOLVED) != isinstance(
            self.winner_basis, PhaseWinnerBasis
        ):
            raise ValueError("phase winner basis must match resolved status")

    def with_calibrated_template(self, template: TemplateSpec) -> "PhaseFitResult":
        """Narrow the continuous template without rerunning role selection."""

        if template.template_id != self.template.template_id:
            raise ValueError("calibrated template changes phase identity")
        best = (
            None
            if self.best is None
            else self.best.with_calibrated_template(template)
        )
        try:
            runner = (
                None
                if self.runner_up is None
                else self.runner_up.with_calibrated_template(template)
            )
        except ValueError:
            # A discrete runner that fails the calibrated W+gap closure is
            # physically illegal; this is a hard filter, not score pruning.
            runner = None
        status = self.status
        reason = self.ambiguity_reason
        winner_basis = self.winner_basis
        if best is not None and runner is None and status == PhaseFitStatus.AMBIGUOUS:
            status = PhaseFitStatus.RESOLVED
            reason = None
            winner_basis = PhaseWinnerBasis.CALIBRATED_RUNNER_REJECTED
        return PhaseFitResult(
            template=template,
            best=best,
            runner_up=runner,
            status=status,
            ambiguity_reason=reason,
            receipt=self.receipt,
            registered_direct_observation_ids=(
                self.registered_direct_observation_ids
            ),
            failure_kind=(None if status == PhaseFitStatus.RESOLVED else self.failure_kind),
            winner_basis=winner_basis,
        )
