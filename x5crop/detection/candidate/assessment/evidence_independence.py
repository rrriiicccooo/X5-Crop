from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from x5crop.domain import EvidenceState

if TYPE_CHECKING:
    from ...physical.model import SequenceSolution


@dataclass(frozen=True)
class EvidenceIndependenceEvidence:
    state: EvidenceState
    reason: str
    sequence_root_measurement: str
    supporting_root_measurements: tuple[str, ...]
    cyclic_measurements: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.reason or not self.sequence_root_measurement:
            raise ValueError("evidence independence requires identity and reason")
        for values in (
            self.supporting_root_measurements,
            self.cyclic_measurements,
        ):
            if any(not item for item in values) or len(set(values)) != len(values):
                raise ValueError(
                    "evidence measurement identities must be non-empty and unique"
                )
        root_reused = (
            self.sequence_root_measurement in self.supporting_root_measurements
        )
        contradicted = bool(root_reused or self.cyclic_measurements)
        if contradicted != (self.state == EvidenceState.CONTRADICTED):
            raise ValueError(
                "independence contradiction requires shared measurement provenance"
            )
        if self.state == EvidenceState.SUPPORTED and not self.supporting_root_measurements:
            raise ValueError("supported independence requires supporting measurements")
        if self.state == EvidenceState.NOT_APPLICABLE and self.supporting_root_measurements:
            raise ValueError(
                "not-applicable independence cannot claim supporting measurements"
            )

def evidence_independence_evidence(
    geometry: SequenceSolution,
) -> EvidenceIndependenceEvidence:
    if not geometry.automatic_processing_supported:
        return EvidenceIndependenceEvidence(
            EvidenceState.NOT_APPLICABLE,
            "automatic_processing_not_supported",
            geometry.sequence_provenance.root_measurement,
            (),
            (),
        )
    hard_observations = tuple(
        assignment.observation
        for assignment in geometry.separator_assignments
        if assignment.used_for_boundary and assignment.independent
    )
    hard_roots = tuple(
        sorted(
            {
                observation.provenance.root_measurement
                for observation in hard_observations
            }
        )
    )
    sequence_root = geometry.sequence_provenance.root_measurement
    sequence_dependencies = set(geometry.sequence_provenance.dependencies)
    measurement_roots = hard_roots
    measurement_dependencies = {
        dependency
        for observation in hard_observations
        for dependency in observation.provenance.dependencies
    }
    dependency_cycle = {
        dependency
        for dependency in (
            *((sequence_root,) if sequence_root in measurement_dependencies else ()),
            *(root for root in measurement_roots if root in sequence_dependencies),
        )
    }
    cyclic_measurements = tuple(
        sorted(dependency_cycle)
    )
    root_reused = sequence_root in set(measurement_roots)
    if root_reused:
        state = EvidenceState.CONTRADICTED
        reason = "sequence_and_separator_share_root_measurement"
    elif cyclic_measurements:
        state = EvidenceState.CONTRADICTED
        reason = "sequence_and_separator_share_measurement_dependency"
    elif not hard_roots:
        state = EvidenceState.UNAVAILABLE
        reason = "independent_separator_measurement_unavailable"
    else:
        state = EvidenceState.SUPPORTED
        reason = "independent_sequence_and_separator_measurements"
    return EvidenceIndependenceEvidence(
        state=state,
        reason=reason,
        sequence_root_measurement=sequence_root,
        supporting_root_measurements=measurement_roots,
        cyclic_measurements=cyclic_measurements,
    )
