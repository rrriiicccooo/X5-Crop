"""Typed calibration and authority records for the one nominal Grid."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval


class NominalGridFailureKind(str, Enum):
    CALIBRATED_PRIOR_UNAVAILABLE = (
        "calibrated_nominal_grid_authority_unavailable"
    )
    PHASE_ANCHOR_UNAVAILABLE = "nominal_grid_phase_anchor_unavailable"
    ADJACENCY_COVERAGE_INCOMPLETE = (
        "adjacency_observation_coverage_incomplete"
    )
    COMPLETE_FRAME_UNOBSERVED = "complete_frame_unobserved"
    COUNTEREVIDENCE = "nominal_grid_counterevidence"
    OUTPUT_FOOTPRINT_UNAVAILABLE = "output_footprint_unavailable"


@dataclass(frozen=True)
class CalibratedNominalGridPrior:
    """One format calibration projected into the current source pixel scale."""

    prior_id: str
    state: EvidenceState
    format_id: str
    template_id: str
    calibration_cohort_sha256: str | None
    aperture_calibration_id: str | None
    pitch_calibration_id: str | None
    frame_width_mm: FiniteInterval | None
    frame_height_mm: FiniteInterval | None
    pitch_mm: FiniteInterval | None
    scale_px_per_mm: PositiveInterval
    frame_width_px: FiniteInterval | None
    frame_height_px: FiniteInterval | None
    pitch_px: FiniteInterval | None
    failure_kind: NominalGridFailureKind | None
    reason: str | None

    def __post_init__(self) -> None:
        supported = self.state == EvidenceState.SUPPORTED
        unavailable = self.state == EvidenceState.UNAVAILABLE
        intervals = (
            self.frame_width_mm,
            self.frame_height_mm,
            self.pitch_mm,
            self.frame_width_px,
            self.frame_height_px,
            self.pitch_px,
        )
        if (
            not self.prior_id
            or not self.format_id
            or not self.template_id
            or not isinstance(self.scale_px_per_mm, PositiveInterval)
            or not (supported or unavailable)
            or supported
            != (
                bool(self.calibration_cohort_sha256)
                and bool(self.aperture_calibration_id)
                and bool(self.pitch_calibration_id)
                and all(isinstance(item, FiniteInterval) for item in intervals)
                and self.failure_kind is None
                and self.reason is None
            )
            or unavailable
            != (
                self.calibration_cohort_sha256 is None
                and self.aperture_calibration_id is None
                and self.pitch_calibration_id is None
                and all(item is None for item in intervals)
                and self.failure_kind
                == NominalGridFailureKind.CALIBRATED_PRIOR_UNAVAILABLE
                and bool(self.reason)
            )
        ):
            raise ValueError("calibrated nominal Grid prior is invalid")
        if supported:
            assert self.calibration_cohort_sha256 is not None
            if (
                len(self.calibration_cohort_sha256) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in self.calibration_cohort_sha256
                )
            ):
                raise ValueError("nominal Grid calibration digest is invalid")


@dataclass(frozen=True)
class CalibratedNominalGridFitState:
    """Correlated prior state retained by one existing SequenceFit."""

    prior_id: str
    scale_px_per_mm: PositiveInterval
    frame_width_mm: FiniteInterval
    pitch_mm: FiniteInterval
    canonical_scale_px_per_mm: float
    phase_anchor_role_indices: tuple[int, ...]
    phase_anchor_observation_ids: tuple[ObservationId, ...]
    retained_direct_constraint_rank: int

    def __post_init__(self) -> None:
        if (
            not self.prior_id
            or not isinstance(self.scale_px_per_mm, PositiveInterval)
            or not isinstance(self.frame_width_mm, FiniteInterval)
            or not isinstance(self.pitch_mm, FiniteInterval)
            or not (
                self.scale_px_per_mm.minimum - 1.0e-9
                <= self.canonical_scale_px_per_mm
                <= self.scale_px_per_mm.maximum + 1.0e-9
            )
            or tuple(sorted(set(self.phase_anchor_role_indices)))
            != self.phase_anchor_role_indices
            or any(index < 0 for index in self.phase_anchor_role_indices)
            or not self.phase_anchor_role_indices
            or len(self.phase_anchor_role_indices)
            != len(self.phase_anchor_observation_ids)
            or len(set(self.phase_anchor_observation_ids))
            != len(self.phase_anchor_observation_ids)
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.phase_anchor_observation_ids
            )
            or not 0 <= self.retained_direct_constraint_rank <= 3
        ):
            raise ValueError("calibrated nominal Grid fit state is invalid")


@dataclass(frozen=True)
class CalibratedNominalGridEvidence:
    """Selected sequence-side proof before output footprint finalization."""

    evidence_id: str
    state: EvidenceState
    prior_id: str
    phase_anchor_role_indices: tuple[int, ...]
    phase_anchor_observation_ids: tuple[ObservationId, ...]
    inferred_adjacency_ordinals: tuple[int, ...]
    unobserved_frame_ordinals: tuple[int, ...]
    covering_query_ids: tuple[str, ...]
    failure_kind: NominalGridFailureKind | None
    reason: str | None

    def __post_init__(self) -> None:
        supported = self.state == EvidenceState.SUPPORTED
        failed = self.state in {
            EvidenceState.UNAVAILABLE,
            EvidenceState.CONTRADICTED,
        }
        if (
            not self.evidence_id
            or not self.prior_id
            or not (supported or failed)
            or tuple(sorted(set(self.phase_anchor_role_indices)))
            != self.phase_anchor_role_indices
            or len(self.phase_anchor_role_indices)
            != len(self.phase_anchor_observation_ids)
            or not self.phase_anchor_role_indices
            or len(set(self.phase_anchor_observation_ids))
            != len(self.phase_anchor_observation_ids)
            or tuple(sorted(set(self.inferred_adjacency_ordinals)))
            != self.inferred_adjacency_ordinals
            or any(ordinal <= 0 for ordinal in self.inferred_adjacency_ordinals)
            or tuple(sorted(set(self.unobserved_frame_ordinals)))
            != self.unobserved_frame_ordinals
            or any(ordinal <= 0 for ordinal in self.unobserved_frame_ordinals)
            or tuple(sorted(set(self.covering_query_ids)))
            != self.covering_query_ids
            or supported != (self.failure_kind is None and self.reason is None)
            or failed
            != (
                isinstance(self.failure_kind, NominalGridFailureKind)
                and bool(self.reason)
            )
            or bool(self.unobserved_frame_ordinals)
            != (
                self.failure_kind
                == NominalGridFailureKind.COMPLETE_FRAME_UNOBSERVED
            )
        ):
            raise ValueError("calibrated nominal Grid evidence is invalid")


@dataclass(frozen=True)
class CalibratedNominalGridAuthority:
    """Bind calibrated Grid evidence to the selected output footprints."""

    authority_id: str
    state: EvidenceState
    evidence_id: str | None
    placement_id: str | None
    output_geometry_ids: tuple[str, ...]
    failure_kind: NominalGridFailureKind | None
    reason: str | None

    def __post_init__(self) -> None:
        supported = self.state == EvidenceState.SUPPORTED
        not_applicable = self.state == EvidenceState.NOT_APPLICABLE
        failed = self.state in {
            EvidenceState.UNAVAILABLE,
            EvidenceState.CONTRADICTED,
        }
        if (
            not self.authority_id
            or not (supported or not_applicable or failed)
            or len(set(self.output_geometry_ids)) != len(self.output_geometry_ids)
            or supported
            != (
                bool(self.evidence_id)
                and bool(self.placement_id)
                and bool(self.output_geometry_ids)
                and self.failure_kind is None
                and self.reason is None
            )
            or not_applicable
            != (
                self.evidence_id is None
                and self.placement_id is None
                and not self.output_geometry_ids
                and self.failure_kind is None
                and self.reason is None
            )
            or failed
            != (
                bool(self.evidence_id)
                and (self.placement_id is None or bool(self.placement_id))
                and isinstance(self.failure_kind, NominalGridFailureKind)
                and bool(self.reason)
            )
        ):
            raise ValueError("calibrated nominal Grid authority is invalid")
