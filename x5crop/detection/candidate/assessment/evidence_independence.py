from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ....constants import CANDIDATE_SOURCE_FRAME_SEQUENCE
from x5crop.domain import EvidenceState

if TYPE_CHECKING:
    from ...geometry import CandidateGeometry


@dataclass(frozen=True)
class EvidenceIndependenceEvidence:
    state: EvidenceState
    reason: str
    sequence_root_measurement: str
    supporting_root_measurements: tuple[str, ...]
    cyclic_measurements: tuple[str, ...]

def evidence_independence_evidence(
    geometry: CandidateGeometry,
) -> EvidenceIndependenceEvidence:
    if geometry.source != CANDIDATE_SOURCE_FRAME_SEQUENCE:
        return EvidenceIndependenceEvidence(
            EvidenceState.NOT_APPLICABLE,
            "non_separator_candidate",
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
    dimension_provenance = geometry.frame_dimension_estimate.provenance
    measurement_roots = (
        hard_roots
        if hard_roots
        else (dimension_provenance.root_measurement,)
    )
    measurement_dependencies = (
        {
            dependency
            for observation in hard_observations
            for dependency in observation.provenance.dependencies
        }
        if hard_roots
        else set(dimension_provenance.dependencies)
    )
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
        state = EvidenceState.SUPPORTED
        reason = "independent_sequence_and_dimension_measurements"
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
