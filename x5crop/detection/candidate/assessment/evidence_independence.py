from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from x5crop.domain import EvidenceState, MeasurementIdentity

if TYPE_CHECKING:
    from ...physical.model import SequenceSolution


@dataclass(frozen=True)
class EvidenceIndependenceEvidence:
    sequence_root_measurement: MeasurementIdentity
    supporting_root_measurements: tuple[MeasurementIdentity, ...]
    cyclic_measurements: tuple[MeasurementIdentity, ...]
    automatic_processing_supported: bool
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.sequence_root_measurement, MeasurementIdentity):
            raise ValueError("evidence independence requires a sequence identity")
        for values in (
            self.supporting_root_measurements,
            self.cyclic_measurements,
        ):
            if any(not isinstance(item, MeasurementIdentity) for item in values) or len(
                set(values)
            ) != len(values):
                raise ValueError(
                    "evidence measurement identities must be non-empty and unique"
                )
        root_reused = self.sequence_root_measurement in self.supporting_root_measurements
        if not self.automatic_processing_supported:
            if self.supporting_root_measurements or self.cyclic_measurements:
                raise ValueError(
                    "unsupported automatic processing cannot claim independence measurements"
                )
            state = EvidenceState.NOT_APPLICABLE
            reason = "automatic_processing_not_supported"
        elif root_reused:
            state = EvidenceState.CONTRADICTED
            reason = "sequence_and_separator_share_root_measurement"
        elif self.cyclic_measurements:
            state = EvidenceState.CONTRADICTED
            reason = "sequence_and_separator_share_measurement_dependency"
        elif not self.supporting_root_measurements:
            state = EvidenceState.UNAVAILABLE
            reason = "independent_separator_measurement_unavailable"
        else:
            state = EvidenceState.SUPPORTED
            reason = "independent_sequence_and_separator_measurements"
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def evidence_independence_evidence(
    geometry: SequenceSolution,
) -> EvidenceIndependenceEvidence:
    if not geometry.automatic_processing_supported:
        return EvidenceIndependenceEvidence(
            geometry.sequence_provenance.root_measurement,
            (),
            (),
            False,
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
            },
            key=lambda item: item.value,
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
        sorted(dependency_cycle, key=lambda item: item.value)
    )
    return EvidenceIndependenceEvidence(
        sequence_root_measurement=sequence_root,
        supporting_root_measurements=measurement_roots,
        cyclic_measurements=cyclic_measurements,
        automatic_processing_supported=True,
    )
