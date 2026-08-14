"""Development-only leave-one-anchor-out stability check."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import ObservationId
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_model import PhaseAnchor, SequenceFit, TemplateSpec
from .template_phase import PhaseFitResult, PhaseFitStatus, fit_template_phase


class AnchorDependencyEffect(str, Enum):
    STABLE = "stable"
    CONTINUOUS_SHIFT = "continuous_shift"
    DISCRETE_SLOT_JUMP = "discrete_slot_jump"
    UNRESOLVED_WITHOUT_ANCHOR = "unresolved_without_anchor"


@dataclass(frozen=True)
class AnchorDependencyFact:
    observation_id: ObservationId
    effect: AnchorDependencyEffect
    absolute_phase_shift_px: float | None
    integer_slot_offset_change: int | None


@dataclass(frozen=True)
class TemplateStabilityReceipt:
    evaluated_anchor_count: int
    refit_count: int
    maximum_refits: int

    def __post_init__(self) -> None:
        if (
            min(self.evaluated_anchor_count, self.refit_count, self.maximum_refits) < 0
            or self.evaluated_anchor_count != self.refit_count
            or self.refit_count > self.maximum_refits
        ):
            raise ValueError("template stability work bound is invalid")


@dataclass(frozen=True)
class TemplateStabilityAnalysis:
    baseline_placement_signature: tuple[int, tuple[ObservationId | None, ...]]
    dependencies: tuple[AnchorDependencyFact, ...]
    receipt: TemplateStabilityReceipt


def _signature(fit: SequenceFit) -> tuple[int, tuple[ObservationId | None, ...]]:
    return (
        fit.phase_lattice_fit.integer_slot_offset,
        fit.role_observation_ids,
    )


def leave_one_anchor_out_phase_stability(
    result: PhaseFitResult,
    observations: tuple[BoundaryEdgeObservation | PhaseAnchor, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    template: TemplateSpec,
    *,
    holder_span_px=None,
) -> TemplateStabilityAnalysis:
    """Refit once per winner-bound independent anchor, never per raw pixel."""

    if result.status != PhaseFitStatus.RESOLVED or result.best is None:
        raise ValueError("stability analysis requires a resolved phase fit")
    baseline = result.best
    ids = tuple(
        sorted(
            {item for item in baseline.role_observation_ids if item is not None},
            key=str,
        )
    )
    by_id = {item.observation_id: item for item in observations}
    if not set(ids).issubset(by_id):
        raise ValueError("stability inputs do not cover winner anchors")
    dependencies: list[AnchorDependencyFact] = []
    for identity in ids:
        reduced = tuple(
            item for item in observations if item.observation_id != identity
        )
        reduced_bands = tuple(
            band
            for band in separator_bands
            if identity
            not in (
                band.left_edge_observation_id,
                band.right_edge_observation_id,
            )
        )
        refit = fit_template_phase(
            reduced,
            template,
            separator_bands=reduced_bands,
            holder_span_px=holder_span_px,
        )
        if refit.status != PhaseFitStatus.RESOLVED or refit.best is None:
            dependencies.append(
                AnchorDependencyFact(
                    identity,
                    AnchorDependencyEffect.UNRESOLVED_WITHOUT_ANCHOR,
                    None,
                    None,
                )
            )
            continue
        offset_change = (
            refit.best.phase_lattice_fit.integer_slot_offset
            - baseline.phase_lattice_fit.integer_slot_offset
        )
        shift = abs(
            refit.best.phase_lattice_fit.canonical_absolute_phase_px
            - baseline.phase_lattice_fit.canonical_absolute_phase_px
        )
        effect = (
            AnchorDependencyEffect.DISCRETE_SLOT_JUMP
            if offset_change
            else AnchorDependencyEffect.STABLE
            if shift <= 1.0
            else AnchorDependencyEffect.CONTINUOUS_SHIFT
        )
        dependencies.append(
            AnchorDependencyFact(identity, effect, shift, offset_change)
        )
    receipt = TemplateStabilityReceipt(len(ids), len(ids), 2 * template.count)
    return TemplateStabilityAnalysis(
        baseline_placement_signature=_signature(baseline),
        dependencies=tuple(dependencies),
        receipt=receipt,
    )


__all__ = [
    "AnchorDependencyEffect",
    "AnchorDependencyFact",
    "TemplateStabilityAnalysis",
    "TemplateStabilityReceipt",
    "leave_one_anchor_out_phase_stability",
]
