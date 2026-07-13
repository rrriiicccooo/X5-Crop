from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from x5crop.domain import (
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    PhotoApertureEdgeSource,
)

if TYPE_CHECKING:
    from ...physical.model import PhotoSequenceSolution


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
            reason = "sequence_and_boundary_share_root_measurement"
        elif self.cyclic_measurements:
            state = EvidenceState.CONTRADICTED
            reason = "sequence_and_boundary_share_measurement_dependency"
        elif not self.supporting_root_measurements:
            state = EvidenceState.UNAVAILABLE
            reason = "independent_boundary_measurement_unavailable"
        else:
            state = EvidenceState.SUPPORTED
            reason = "independent_sequence_and_boundary_measurements"
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def _measured_internal_boundary_provenances(
    geometry: PhotoSequenceSolution,
) -> tuple[MeasurementProvenance, ...]:
    if geometry.count == 1:
        aperture = geometry.photo_apertures[0]
        boundaries = (aperture.leading, aperture.trailing)
        return (
            tuple(item.provenance for item in boundaries)
            if all(
                item.source == PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
                and item.independently_observed
                for item in boundaries
            )
            else ()
        )
    provenances: list[MeasurementProvenance] = []
    for left, right in zip(
        geometry.photo_apertures,
        geometry.photo_apertures[1:],
    ):
        boundaries = (left.trailing, right.leading)
        if all(
            item.source == PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
            and item.independently_observed
            for item in boundaries
        ):
            provenances.extend(item.provenance for item in boundaries)
    return tuple(dict.fromkeys(provenances))


def _supporting_boundary_provenances(
    geometry: PhotoSequenceSolution,
) -> tuple[MeasurementProvenance, ...]:
    separator_provenances = tuple(
        assignment.observation.provenance
        for assignment in geometry.separator_assignments
        if assignment.independent
    )
    return tuple(
        dict.fromkeys(
            (*separator_provenances, *_measured_internal_boundary_provenances(geometry))
        )
    )


def evidence_independence_evidence(
    geometry: PhotoSequenceSolution,
) -> EvidenceIndependenceEvidence:
    if not geometry.automatic_processing_supported:
        return EvidenceIndependenceEvidence(
            geometry.sequence_provenance.root_measurement,
            (),
            (),
            False,
        )
    supporting_provenances = _supporting_boundary_provenances(geometry)
    supporting_roots = tuple(
        sorted(
            {
                provenance.root_measurement
                for provenance in supporting_provenances
            },
            key=lambda item: item.value,
        )
    )
    sequence_root = geometry.sequence_provenance.root_measurement
    sequence_dependencies = set(geometry.sequence_provenance.dependencies)
    measurement_roots = supporting_roots
    measurement_dependencies = {
        dependency
        for provenance in supporting_provenances
        for dependency in provenance.dependencies
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
