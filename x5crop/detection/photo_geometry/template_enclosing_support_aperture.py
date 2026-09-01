"""Calibrate the aperture center inside one selected enclosing support pair."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import EvidenceState, FiniteInterval, ObservationId
from ...formats import (
    ENCLOSING_SUPPORT_APERTURE_CALIBRATION_SPEC,
    EnclosingSupportApertureCalibrationSpec,
)
from .interval_math import intersect
from .output_model import OutputBoundaryUse
from .physical_identity import physical_fact_id
from .template_cross_model import CrossFit


class EnclosingSupportApertureFailureKind(str, Enum):
    CALIBRATION_UNAVAILABLE = (
        "enclosing_support_aperture_calibration_unavailable"
    )
    CALIBRATED_CENTER_OUTSIDE_SUPPORT = (
        "enclosing_support_aperture_center_conflict"
    )


@dataclass(frozen=True)
class EnclosingSupportApertureAuthority:
    """Rank-zero center authority for a selected enclosing support pair.

    The authority retains the aperture-center offset relative to the support
    midpoint.  It neither changes the selected support geometry nor promotes
    either support line to a direct photo-aperture boundary.
    """

    authority_id: str
    state: EvidenceState
    calibration_id: str | None
    calibration_cohort_sha256: str | None
    eligibility_revision: str | None
    support_observation_ids: tuple[ObservationId, ...]
    support_span_px: FiniteInterval | None
    canonical_height_px: float | None
    calibrated_center_offset_ratio: FiniteInterval | None
    calibrated_center_offset_px: FiniteInterval | None
    physical_center_offset_px: FiniteInterval | None
    effective_center_offset_px: FiniteInterval | None
    failure_kind: EnclosingSupportApertureFailureKind | None
    failure_detail: str | None
    correlated_inference: bool = True
    independent_constraint_rank: int = 0

    def __post_init__(self) -> None:
        if (
            not self.authority_id
            or not isinstance(self.state, EvidenceState)
            or not self.correlated_inference
            or self.independent_constraint_rank != 0
            or len(set(self.support_observation_ids))
            != len(self.support_observation_ids)
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.support_observation_ids
            )
        ):
            raise ValueError("enclosing-support aperture authority is invalid")
        optional_values = (
            self.calibration_id,
            self.calibration_cohort_sha256,
            self.eligibility_revision,
            self.support_span_px,
            self.canonical_height_px,
            self.calibrated_center_offset_ratio,
            self.calibrated_center_offset_px,
            self.physical_center_offset_px,
            self.effective_center_offset_px,
        )
        if self.state == EvidenceState.NOT_APPLICABLE:
            if (
                any(value is not None for value in optional_values)
                or self.support_observation_ids
                or self.failure_kind is not None
                or self.failure_detail is not None
            ):
                raise ValueError(
                    "non-enclosing placement cannot carry aperture authority"
                )
            return
        if (
            len(self.support_observation_ids) < 2
            or not isinstance(self.support_span_px, FiniteInterval)
            or self.canonical_height_px is None
            or not math.isfinite(self.canonical_height_px)
            or self.canonical_height_px <= 0.0
            or not isinstance(self.physical_center_offset_px, FiniteInterval)
            or self.support_span_px.minimum <= self.canonical_height_px
        ):
            raise ValueError(
                "enclosing-support authority lost its physical support"
            )
        if self.state == EvidenceState.UNAVAILABLE:
            if (
                any(
                    value is not None
                    for value in (
                        self.calibration_id,
                        self.calibration_cohort_sha256,
                        self.eligibility_revision,
                        self.calibrated_center_offset_ratio,
                        self.calibrated_center_offset_px,
                        self.effective_center_offset_px,
                    )
                )
                or self.failure_kind
                != EnclosingSupportApertureFailureKind.CALIBRATION_UNAVAILABLE
                or not self.failure_detail
            ):
                raise ValueError(
                    "unavailable enclosing-support calibration is invalid"
                )
            return
        calibrated = (
            self.calibration_id,
            self.calibration_cohort_sha256,
            self.eligibility_revision,
            self.calibrated_center_offset_ratio,
            self.calibrated_center_offset_px,
        )
        if any(value is None for value in calibrated):
            raise ValueError(
                "enclosing-support calibration provenance is incomplete"
            )
        assert self.calibration_cohort_sha256 is not None
        if (
            len(self.calibration_cohort_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.calibration_cohort_sha256
            )
        ):
            raise ValueError("enclosing-support calibration digest is invalid")
        if self.state == EvidenceState.SUPPORTED:
            if (
                not isinstance(self.effective_center_offset_px, FiniteInterval)
                or self.failure_kind is not None
                or self.failure_detail is not None
            ):
                raise ValueError(
                    "supported enclosing-support authority is incomplete"
                )
            assert self.calibrated_center_offset_px is not None
            assert self.physical_center_offset_px is not None
            if (
                self.effective_center_offset_px.minimum
                < self.calibrated_center_offset_px.minimum - 1.0e-9
                or self.effective_center_offset_px.maximum
                > self.calibrated_center_offset_px.maximum + 1.0e-9
                or self.effective_center_offset_px.minimum
                < self.physical_center_offset_px.minimum - 1.0e-9
                or self.effective_center_offset_px.maximum
                > self.physical_center_offset_px.maximum + 1.0e-9
            ):
                raise ValueError(
                    "effective aperture center leaves its joint authority"
                )
        elif self.state == EvidenceState.CONTRADICTED:
            if (
                self.effective_center_offset_px is not None
                or self.failure_kind
                != EnclosingSupportApertureFailureKind
                .CALIBRATED_CENTER_OUTSIDE_SUPPORT
                or not self.failure_detail
            ):
                raise ValueError(
                    "contradicted enclosing-support authority is invalid"
                )
        else:
            raise ValueError("unsupported enclosing-support authority state")


def not_applicable_enclosing_support_aperture_authority(
) -> EnclosingSupportApertureAuthority:
    return EnclosingSupportApertureAuthority(
        authority_id="enclosing-support-aperture:not-applicable",
        state=EvidenceState.NOT_APPLICABLE,
        calibration_id=None,
        calibration_cohort_sha256=None,
        eligibility_revision=None,
        support_observation_ids=(),
        support_span_px=None,
        canonical_height_px=None,
        calibrated_center_offset_ratio=None,
        calibrated_center_offset_px=None,
        physical_center_offset_px=None,
        effective_center_offset_px=None,
        failure_kind=None,
        failure_detail=None,
    )


def unavailable_enclosing_support_aperture_authority(
    cross_fit: CrossFit,
    *,
    detail: str = "enclosing-support aperture calibration was not registered",
) -> EnclosingSupportApertureAuthority:
    support = cross_fit.enclosing_support_pair
    if support is None:
        raise ValueError("unavailable aperture authority requires support")
    height = cross_fit.bottom_canonical_px - cross_fit.top_canonical_px
    slack = 0.5 * (support.observed_span_px.minimum - height)
    observations = (
        *support.top_provenance_ids,
        *support.bottom_provenance_ids,
    )
    return EnclosingSupportApertureAuthority(
        authority_id=physical_fact_id(
            "enclosing-support-aperture-unavailable",
            observations,
            support.observed_span_px,
            height,
        ),
        state=EvidenceState.UNAVAILABLE,
        calibration_id=None,
        calibration_cohort_sha256=None,
        eligibility_revision=None,
        support_observation_ids=observations,
        support_span_px=support.observed_span_px,
        canonical_height_px=height,
        calibrated_center_offset_ratio=None,
        calibrated_center_offset_px=None,
        physical_center_offset_px=FiniteInterval(-slack, slack),
        effective_center_offset_px=None,
        failure_kind=(
            EnclosingSupportApertureFailureKind.CALIBRATION_UNAVAILABLE
        ),
        failure_detail=detail,
    )


def derive_enclosing_support_aperture_authority(
    cross_fit: CrossFit,
    *,
    calibration: EnclosingSupportApertureCalibrationSpec | None = (
        ENCLOSING_SUPPORT_APERTURE_CALIBRATION_SPEC
    ),
) -> EnclosingSupportApertureAuthority:
    """Intersect one frozen center calibration with direct support geometry."""

    if cross_fit.boundary_use != OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR:
        return not_applicable_enclosing_support_aperture_authority()
    support = cross_fit.enclosing_support_pair
    if support is None:
        raise ValueError("enclosing-support fit lost its support pair")
    if calibration is None:
        return unavailable_enclosing_support_aperture_authority(cross_fit)
    height = cross_fit.bottom_canonical_px - cross_fit.top_canonical_px
    ratio = FiniteInterval(
        calibration.minimum_center_offset_ratio,
        calibration.maximum_center_offset_ratio,
    )
    calibrated_px = FiniteInterval(
        ratio.minimum * height,
        ratio.maximum * height,
    )
    slack = 0.5 * (support.observed_span_px.minimum - height)
    physical_px = FiniteInterval(-slack, slack)
    effective = intersect(calibrated_px, physical_px)
    observations = (
        *support.top_provenance_ids,
        *support.bottom_provenance_ids,
    )
    authority_id = physical_fact_id(
        "enclosing-support-aperture-authority",
        calibration.identity_fields,
        observations,
        support.observed_span_px,
        height,
        calibrated_px,
        physical_px,
    )
    common = dict(
        authority_id=authority_id,
        calibration_id=calibration.calibration_id,
        calibration_cohort_sha256=(
            calibration.development_gold_cohort_sha256
        ),
        eligibility_revision=calibration.eligibility_revision,
        support_observation_ids=observations,
        support_span_px=support.observed_span_px,
        canonical_height_px=height,
        calibrated_center_offset_ratio=ratio,
        calibrated_center_offset_px=calibrated_px,
        physical_center_offset_px=physical_px,
    )
    if effective is None:
        return EnclosingSupportApertureAuthority(
            **common,
            state=EvidenceState.CONTRADICTED,
            effective_center_offset_px=None,
            failure_kind=(
                EnclosingSupportApertureFailureKind
                .CALIBRATED_CENTER_OUTSIDE_SUPPORT
            ),
            failure_detail=(
                "calibrated aperture center does not intersect the direct "
                "enclosing-support containment interval"
            ),
        )
    return EnclosingSupportApertureAuthority(
        **common,
        state=EvidenceState.SUPPORTED,
        effective_center_offset_px=effective,
        failure_kind=None,
        failure_detail=None,
    )


__all__ = [
    "EnclosingSupportApertureAuthority",
    "EnclosingSupportApertureFailureKind",
    "derive_enclosing_support_aperture_authority",
    "not_applicable_enclosing_support_aperture_authority",
    "unavailable_enclosing_support_aperture_authority",
]
