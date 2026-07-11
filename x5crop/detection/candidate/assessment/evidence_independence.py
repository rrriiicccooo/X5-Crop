from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ....gap_methods import is_hard_gap_method
from ...evidence.state import EvidenceState

if TYPE_CHECKING:
    from ...geometry import CandidateGeometry


@dataclass(frozen=True)
class EvidenceIndependenceEvidence:
    state: EvidenceState
    reason: str
    outer_root_measurement: str
    separator_root_measurements: tuple[str, ...]
    cyclic_measurements: tuple[str, ...]

def evidence_independence_evidence(
    geometry: CandidateGeometry,
) -> EvidenceIndependenceEvidence:
    if geometry.source != "separator":
        return EvidenceIndependenceEvidence(
            EvidenceState.NOT_APPLICABLE,
            "non_separator_candidate",
            geometry.sequence_provenance.root_measurement,
            (),
            (),
        )
    hard_observations = tuple(
        observation
        for observation in geometry.separators
        if is_hard_gap_method(observation.method)
    )
    hard_roots = tuple(
        sorted(
            {
                observation.provenance.root_measurement
                for observation in hard_observations
            }
        )
    )
    outer_root = geometry.sequence_provenance.root_measurement
    outer_dependencies = set(geometry.sequence_provenance.dependencies)
    separator_dependencies = {
        dependency
        for observation in hard_observations
        for dependency in observation.provenance.dependencies
    }
    dependency_cycle = {
        dependency
        for dependency in (
            *((outer_root,) if outer_root in separator_dependencies else ()),
            *(root for root in hard_roots if root in outer_dependencies),
        )
    }
    cyclic_measurements = tuple(
        sorted(dependency_cycle)
    )
    root_reused = outer_root in set(hard_roots)
    if root_reused:
        state = EvidenceState.CONTRADICTED
        reason = "outer_and_separator_share_root_measurement"
    elif cyclic_measurements:
        state = EvidenceState.CONTRADICTED
        reason = "outer_and_separator_share_measurement_dependency"
    elif not hard_roots:
        state = EvidenceState.UNAVAILABLE
        reason = "hard_separator_measurement_unavailable"
    else:
        state = EvidenceState.SUPPORTED
        reason = "independent_outer_and_separator_measurements"
    return EvidenceIndependenceEvidence(
        state=state,
        reason=reason,
        outer_root_measurement=outer_root,
        separator_root_measurements=hard_roots,
        cyclic_measurements=cyclic_measurements,
    )
