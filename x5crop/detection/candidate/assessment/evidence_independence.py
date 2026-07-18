from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from x5crop.domain import (
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
)

if TYPE_CHECKING:
    from ...physical.model import FrameSequenceSolution


@dataclass(frozen=True)
class EvidenceIndependenceEvidence:
    geometry_root_measurement: MeasurementIdentity
    supporting_measurement_roots: tuple[MeasurementIdentity, ...]
    geometry_dependent_measurements: tuple[MeasurementIdentity, ...]
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if self.geometry_root_measurement != MeasurementIdentity.FRAME_GEOMETRY:
            raise ValueError("evidence independence requires frame geometry identity")
        for values in (
            self.supporting_measurement_roots,
            self.geometry_dependent_measurements,
        ):
            if any(not isinstance(item, MeasurementIdentity) for item in values) or len(
                set(values)
            ) != len(values):
                raise ValueError(
                    "evidence measurement identities must be typed and unique"
                )
        if self.geometry_dependent_measurements:
            state = EvidenceState.CONTRADICTED
            reason = "supporting_measurement_depends_on_geometry"
        elif not self.supporting_measurement_roots:
            state = EvidenceState.UNAVAILABLE
            reason = "independent_geometry_support_unavailable"
        else:
            state = EvidenceState.SUPPORTED
            reason = "supporting_measurements_independent_of_geometry"
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def _supporting_measurement_provenances(
    geometry: FrameSequenceSolution,
) -> tuple[MeasurementProvenance, ...]:
    frame_boundary_provenances = tuple(
        assignment.observation.provenance
        for assignment in geometry.long_axis_assignments
        if assignment.resolution.independently_observed
    )
    separator_provenances = tuple(
        assignment.observation.provenance
        for assignment in geometry.separator_assignments
    )
    return tuple(
        dict.fromkeys((*frame_boundary_provenances, *separator_provenances))
    )


def evidence_independence_evidence(
    geometry: FrameSequenceSolution,
) -> EvidenceIndependenceEvidence:
    supporting_provenances = _supporting_measurement_provenances(geometry)
    supporting_roots = tuple(
        sorted(
            {
                provenance.root_measurement
                for provenance in supporting_provenances
            },
            key=lambda item: item.value,
        )
    )
    geometry_root = geometry.sequence_provenance.root_measurement
    geometry_dependent_measurements = tuple(
        sorted(
            {
                provenance.root_measurement
                for provenance in supporting_provenances
                if provenance.root_measurement == geometry_root
                or geometry_root in provenance.dependencies
            },
            key=lambda item: item.value,
        )
    )
    return EvidenceIndependenceEvidence(
        geometry_root_measurement=geometry_root,
        supporting_measurement_roots=supporting_roots,
        geometry_dependent_measurements=geometry_dependent_measurements,
    )
