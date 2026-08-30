"""Development-only leave-one-anchor-out stability check."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from ...domain import ObservationId
from .template_model import SequenceFit
from .template_phase import fit_template_phase_with_local_advance
from .template_phase_model import (
    GlobalLatticeAuthorityEvidence,
    PhaseFitResult,
    PhaseFitStatus,
    TemplatePhaseInput,
)
from .template_evidence import separator_support_authority


class AnchorDependencyEffect(str, Enum):
    STABLE = "stable"
    CONTINUOUS_SHIFT = "continuous_shift"
    DISCRETE_SLOT_JUMP = "discrete_slot_jump"
    UNRESOLVED_WITHOUT_ANCHOR = "unresolved_without_anchor"


@dataclass(frozen=True)
class AnchorDependencyFact:
    support_atom_id: ObservationId
    observation_ids: tuple[ObservationId, ...]
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
        fit.binding_observation_ids,
    )


def leave_one_anchor_out_phase_stability(
    result: PhaseFitResult,
    phase_input: TemplatePhaseInput,
) -> TemplateStabilityAnalysis:
    """Refit once per winner-bound independent anchor, never per raw pixel."""

    if result.status != PhaseFitStatus.RESOLVED or result.best is None:
        raise ValueError("stability analysis requires a resolved phase fit")
    if not isinstance(phase_input, TemplatePhaseInput):
        raise TypeError("stability analysis requires the exact phase input")
    baseline = result.best
    observations = phase_input.observations
    separator_bands = phase_input.separator_bands
    ids = tuple(
        sorted(
            set(baseline.phase_anchor_observation_ids),
            key=str,
        )
    )
    by_id = {item.observation_id: item for item in observations}
    if not set(ids).issubset(by_id):
        raise ValueError("stability inputs do not cover winner anchors")
    separator_atoms = separator_support_authority(separator_bands)
    separator_members: dict[ObservationId, set[ObservationId]] = {}
    for band in separator_bands:
        atom = separator_atoms.get(band.left_edge_observation_id)
        if atom is None:
            continue
        separator_members.setdefault(atom, set()).update(
            (
                band.left_edge_observation_id,
                band.right_edge_observation_id,
            )
        )
    grouped: dict[ObservationId, list[ObservationId]] = {}
    for identity in ids:
        atom = separator_atoms.get(identity, identity)
        members = separator_members.get(atom, {identity})
        grouped.setdefault(atom, []).extend(members)
    atoms = tuple(
        (atom, tuple(sorted(set(values), key=str)))
        for atom, values in sorted(grouped.items(), key=lambda item: str(item[0]))
    )
    dependencies: list[AnchorDependencyFact] = []
    for atom_id, atom_ids in atoms:
        removed = set(atom_ids)
        reduced = tuple(
            item for item in observations if item.observation_id not in removed
        )
        reduced_bands = tuple(
            band
            for band in separator_bands
            if not removed.intersection(
                (
                band.left_edge_observation_id,
                band.right_edge_observation_id,
                )
            )
        )
        reduced_ledger_ids = {
            item.observation_id for item in reduced
        }.union(
            band.observation_id for band in reduced_bands
        )
        refit = fit_template_phase_with_local_advance(
            replace(
                phase_input,
                observations=reduced,
                separator_bands=reduced_bands,
                # The final search authority may itself have been estimated
                # from the removed atom.  Reusing it would make the
                # leave-one-out check circular.
                phase_authority_px=None,
                global_lattice_evidence=GlobalLatticeAuthorityEvidence(
                    frame_width_observation_ids=tuple(
                        identity
                        for identity in (
                            phase_input.global_lattice_evidence
                            .frame_width_observation_ids
                        )
                        if identity in reduced_ledger_ids
                    ),
                    pitch_observation_ids=tuple(
                        identity
                        for identity in (
                            phase_input.global_lattice_evidence
                            .pitch_observation_ids
                        )
                        if identity in reduced_ledger_ids
                    ),
                ),
            )
        )
        if refit.status != PhaseFitStatus.RESOLVED or refit.best is None:
            dependencies.append(
                AnchorDependencyFact(
                    atom_id,
                    atom_ids,
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
            AnchorDependencyFact(
                atom_id,
                atom_ids,
                effect,
                shift,
                offset_change,
            )
        )
    receipt = TemplateStabilityReceipt(
        len(atoms),
        len(atoms),
        2 * phase_input.template.count,
    )
    return TemplateStabilityAnalysis(
        baseline_placement_signature=_signature(baseline),
        dependencies=tuple(dependencies),
        receipt=receipt,
    )
