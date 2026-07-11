from __future__ import annotations

from dataclasses import dataclass

from ...cache import MeasurementCache
from ...policies.parameters.exposure_overlap import ExposureOverlapEvidenceParameters
from ...policies.runtime.separator import SeparatorPolicy
from ..geometry import CandidateGeometry
from .gap_evidence import GapEvidenceRecord, gap_evidence_record
from .state import EvidenceState


@dataclass(frozen=True)
class ExposureOverlapEvidence:
    state: EvidenceState
    reason: str
    detected: bool
    widest_overlap_band_px: float
    class_counts: tuple[tuple[str, int], ...]
    gaps: tuple[GapEvidenceRecord, ...]

def exposure_overlap_evidence(
    geometry: CandidateGeometry,
    cache: MeasurementCache,
    *,
    separator_policy: SeparatorPolicy,
    parameters: ExposureOverlapEvidenceParameters,
) -> ExposureOverlapEvidence:
    records = tuple(
        gap_evidence_record(
            cache.gray_work,
            geometry,
            observation,
            separator_policy=separator_policy,
            exposure_overlap_policy=parameters,
        )
        for observation in geometry.separators
    )
    counts: dict[str, int] = {}
    overlap = []
    for record in records:
        counts[record.exposure_overlap_class] = (
            counts.get(record.exposure_overlap_class, 0) + 1
        )
        if record.exposure_overlap_like:
            overlap.append(record)
    widest = max((record.width_px for record in overlap), default=0.0)
    return ExposureOverlapEvidence(
        state=(EvidenceState.SUPPORTED if records else EvidenceState.UNAVAILABLE),
        reason=("exposure_overlap_detected" if overlap else "no_exposure_overlap"),
        detected=bool(overlap),
        widest_overlap_band_px=float(widest),
        class_counts=tuple(sorted(counts.items())),
        gaps=records,
    )
