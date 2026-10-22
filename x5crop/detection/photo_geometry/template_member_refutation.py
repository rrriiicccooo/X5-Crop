"""Physical counterevidence for one recorded interpretation.

Missing permission, failed fitting and rejected output budgets are not physical
refutations. Only the native owners' explicit, replayable contradictions can
remove a record from a common-output obligation. The original record and all
qualification gaps remain present. This never chooses a canonical placement.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import EvidenceState
from .template_adjacency_topology import (
    PhaseCandidateAdjacencyAssessment, RegisteredAdjacencyRoleAssociation,
)
from .template_native_grid_association import NativeGridAssociationProof, NativeGridGapFact


@dataclass(frozen=True)
class PhaseMemberPhysicalRefutation:
    registered_partner_conflicts: tuple[RegisteredAdjacencyRoleAssociation, ...]
    native_grid_conflicts: tuple[NativeGridGapFact, ...]

    def __post_init__(self) -> None:
        if (not (self.registered_partner_conflicts or self.native_grid_conflicts)
                or len(set(self.registered_partner_conflicts)) != len(self.registered_partner_conflicts)
                or len(set(self.native_grid_conflicts)) != len(self.native_grid_conflicts)
                or any(not isinstance(fact, RegisteredAdjacencyRoleAssociation)
                       for fact in self.registered_partner_conflicts)
                or any(not isinstance(fact, NativeGridGapFact)
                       or fact.state != EvidenceState.CONTRADICTED
                       or not fact.end.coordinate_authorized
                       or not fact.next_start.coordinate_authorized
                       for fact in self.native_grid_conflicts)):
            raise ValueError("member refutation requires explicit native physical counterevidence")


def phase_member_physical_refutation(
    adjacency: PhaseCandidateAdjacencyAssessment | None,
    native_grid: NativeGridAssociationProof | None,
) -> PhaseMemberPhysicalRefutation | None:
    """Consume the member's own already evaluated physical owners, once.

    An unrelated unqualified role does not erase a proved contradiction. However,
    a Grid prerequisite failure, a mixed-sign bound or an unevaluated LP cannot
    serve as one. Replaying the complete member supplies the identity/authority
    checks; this reduction does not fit, infer a partner or read pixels.
    """
    if (adjacency is not None and not isinstance(adjacency, PhaseCandidateAdjacencyAssessment)
            or native_grid is not None and not isinstance(native_grid, NativeGridAssociationProof)):
        raise TypeError("member refutation requires typed member-owned physical proofs")
    partners = (() if adjacency is None else adjacency.registered_role_associations)
    conflicts = (() if native_grid is None or native_grid.grid_authority_failure is not None
                 else tuple(fact for fact in native_grid.facts
                            if fact.state == EvidenceState.CONTRADICTED
                            and fact.end.coordinate_authorized and fact.next_start.coordinate_authorized))
    return PhaseMemberPhysicalRefutation(partners, conflicts) if partners or conflicts else None
