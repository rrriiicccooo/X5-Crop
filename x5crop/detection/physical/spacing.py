from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from x5crop.domain import (
    BoundaryObservation,
    EvidenceState,
    FrameBoundaryReference,
    FrameDimensionPriorSource,
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
    sum_pixel_intervals,
)
from .boundary import HolderOcclusionEvidence


SPACING_KINDS = frozenset({"separator", "contact", "overlap", "unresolved"})


def _spacing_kind(interval: PixelInterval) -> str:
    if interval.minimum > 0.0:
        return "separator"
    if interval.maximum < 0.0:
        return "overlap"
    if interval.minimum == 0.0 and interval.maximum == 0.0:
        return "contact"
    return "unresolved"


def _validate_spacing_identity(
    boundary: FrameBoundaryReference,
    kind: str,
    signed_width_px: PixelInterval,
) -> None:
    if not isinstance(boundary, FrameBoundaryReference):
        raise TypeError("inter-frame spacing requires a frame boundary reference")
    if kind not in SPACING_KINDS:
        raise ValueError(f"unsupported inter-frame spacing: {kind}")
    if kind != _spacing_kind(signed_width_px):
        raise ValueError("inter-frame spacing kind must match its signed interval")


@dataclass(frozen=True)
class ObservedSpacingEvidence:
    boundary: FrameBoundaryReference
    kind: str
    signed_width_px: PixelInterval
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        _validate_spacing_identity(
            self.boundary,
            self.kind,
            self.signed_width_px,
        )

    @property
    def reason(self) -> str:
        return f"observed_{self.kind}_spacing"

    @property
    def state(self) -> EvidenceState:
        return (
            EvidenceState.UNAVAILABLE
            if self.kind == "unresolved"
            else EvidenceState.SUPPORTED
        )

    @property
    def independently_observed(self) -> bool:
        return self.state == EvidenceState.SUPPORTED

    @property
    def supports_sequence_conservation(self) -> bool:
        return self.state == EvidenceState.SUPPORTED

    @property
    def supports_output_protection(self) -> bool:
        return bool(self.state == EvidenceState.SUPPORTED and self.kind == "overlap")


@dataclass(frozen=True)
class CorroboratedSpacingEvidence:
    boundary: FrameBoundaryReference
    kind: str
    signed_width_px: PixelInterval
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        _validate_spacing_identity(
            self.boundary,
            self.kind,
            self.signed_width_px,
        )
        if self.kind != "overlap" or self.signed_width_px.maximum >= 0.0:
            raise ValueError("corroborated spacing evidence must be an overlap")

    @property
    def reason(self) -> str:
        return "independent_constraints_require_overlap"

    @property
    def state(self) -> EvidenceState:
        return EvidenceState.SUPPORTED

    @property
    def independently_observed(self) -> bool:
        return False

    @property
    def supports_sequence_conservation(self) -> bool:
        return False

    @property
    def supports_output_protection(self) -> bool:
        return True


@dataclass(frozen=True)
class SpacingHypothesis:
    boundary: FrameBoundaryReference
    kind: str
    signed_width_px: PixelInterval
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        _validate_spacing_identity(
            self.boundary,
            self.kind,
            self.signed_width_px,
        )

    @property
    def reason(self) -> str:
        return f"{self.kind}_spacing_hypothesis"

    @property
    def state(self) -> EvidenceState:
        return EvidenceState.UNAVAILABLE

    @property
    def independently_observed(self) -> bool:
        return False

    @property
    def supports_sequence_conservation(self) -> bool:
        return False

    @property
    def supports_output_protection(self) -> bool:
        return False


InterFrameSpacing = (
    ObservedSpacingEvidence
    | CorroboratedSpacingEvidence
    | SpacingHypothesis
)


class SequenceConservationBasis(str, Enum):
    INDEPENDENT_SPACING = "independent_spacing"
    CORROBORATED_SPACING = "corroborated_spacing"
    SPACING_HYPOTHESIS = "spacing_hypothesis"
    INCOMPLETE_SEQUENCE = "incomplete_sequence"


@dataclass(frozen=True)
class SequenceConservationEvidence:
    visible_length_px: PixelInterval
    holder_occlusion_px: PixelInterval
    frame_total_px: PixelInterval
    spacing_total_px: PixelInterval
    basis: SequenceConservationBasis
    physical_sequence_px: PixelInterval = field(init=False)
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.basis, SequenceConservationBasis):
            raise TypeError("sequence conservation requires a typed basis")
        modeled = self.frame_total_px.plus(self.spacing_total_px)
        if self.basis == SequenceConservationBasis.INCOMPLETE_SEQUENCE:
            state = EvidenceState.UNAVAILABLE
            reason = "count_or_spacing_sequence_incomplete"
        elif self.basis == SequenceConservationBasis.CORROBORATED_SPACING:
            state = EvidenceState.UNAVAILABLE
            reason = "conservation_derived_spacing_not_independent"
        elif self.basis == SequenceConservationBasis.SPACING_HYPOTHESIS:
            state = EvidenceState.UNAVAILABLE
            reason = "signed_spacing_unresolved"
        else:
            observed = self.visible_length_px.plus(self.holder_occlusion_px)
            supported = observed.intersects(modeled)
            state = (
                EvidenceState.SUPPORTED
                if supported
                else EvidenceState.CONTRADICTED
            )
            reason = (
                "frame_sequence_conserved"
                if supported
                else "frame_sequence_not_conserved"
            )
        object.__setattr__(self, "physical_sequence_px", modeled)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def observed_spacing_evidence(
    boundary: FrameBoundaryReference,
    signed_width_px: PixelInterval,
    provenance: MeasurementProvenance,
) -> ObservedSpacingEvidence:
    kind = _spacing_kind(signed_width_px)
    return ObservedSpacingEvidence(
        boundary=boundary,
        kind=kind,
        signed_width_px=signed_width_px,
        provenance=provenance,
    )


def spacing_hypothesis(
    boundary: FrameBoundaryReference,
    signed_width_px: PixelInterval,
    provenance: MeasurementProvenance,
) -> SpacingHypothesis:
    kind = _spacing_kind(signed_width_px)
    return SpacingHypothesis(
        boundary=boundary,
        kind=kind,
        signed_width_px=signed_width_px,
        provenance=provenance,
    )


def corroborate_single_missing_overlap(
    *,
    visible_length_px: PixelInterval,
    count: int,
    frame_width_px: PixelInterval,
    spacings: tuple[InterFrameSpacing, ...],
    holder_occlusion: HolderOcclusionEvidence,
    boundary_observations: tuple[BoundaryObservation, ...],
    dimension_source: FrameDimensionPriorSource,
) -> tuple[InterFrameSpacing, ...]:
    if dimension_source != FrameDimensionPriorSource.SCAN_CALIBRATION:
        return spacings
    edge_observations = {
        observation.side: observation
        for observation in boundary_observations
        if observation.side in {"leading", "trailing"}
    }
    if any(
        side not in edge_observations
        or edge_observations[side].kind == "canvas_clip"
        for side in ("leading", "trailing")
    ):
        return spacings
    occlusion_sides = (holder_occlusion.leading, holder_occlusion.trailing)
    if any(
        side.state not in {EvidenceState.SUPPORTED, EvidenceState.NOT_APPLICABLE}
        for side in occlusion_sides
    ):
        return spacings
    missing = tuple(
        (index, spacing)
        for index, spacing in enumerate(spacings)
        if isinstance(spacing, SpacingHypothesis)
    )
    observed = tuple(
        spacing
        for spacing in spacings
        if isinstance(spacing, ObservedSpacingEvidence)
    )
    if len(missing) != 1 or len(observed) != len(spacings) - 1 or not observed:
        return spacings
    occlusion = holder_occlusion.combined_hidden_width_px
    residual = (
        visible_length_px.plus(occlusion)
        .minus(frame_width_px.scaled(float(count)))
        .minus(
            sum_pixel_intervals(
                tuple(spacing.signed_width_px for spacing in observed)
            )
        )
    )
    missing_position, missing_spacing = missing[0]
    overlap = PixelInterval(
        max(residual.minimum, missing_spacing.signed_width_px.minimum),
        min(residual.maximum, missing_spacing.signed_width_px.maximum),
    ) if residual.intersects(missing_spacing.signed_width_px) else None
    if (
        overlap is None
        or overlap.maximum >= 0.0
        or overlap.minimum <= -frame_width_px.minimum
    ):
        return spacings
    leading = edge_observations["leading"]
    trailing = edge_observations["trailing"]
    corroborated = CorroboratedSpacingEvidence(
        boundary=missing_spacing.boundary,
        kind="overlap",
        signed_width_px=overlap,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.CALIBRATED_SEQUENCE_CONSTRAINTS,
            source="single_missing_overlap_corroboration",
            dependencies=tuple(
                dict.fromkeys(
                    (
                        MeasurementIdentity.SCAN_CALIBRATION,
                        leading.provenance.root_measurement,
                        trailing.provenance.root_measurement,
                        *(item.provenance.root_measurement for item in observed),
                    )
                )
            ),
        ),
    )
    result = list(spacings)
    result[missing_position] = corroborated
    return tuple(result)


def sequence_conservation_evidence(
    *,
    visible_length_px: PixelInterval,
    count: int,
    frame_width_px: PixelInterval,
    spacings: tuple[InterFrameSpacing, ...],
    holder_occlusion: HolderOcclusionEvidence,
) -> SequenceConservationEvidence:
    if count <= 0 or len(spacings) != max(0, count - 1):
        return SequenceConservationEvidence(
            visible_length_px,
            PixelInterval.zero(),
            PixelInterval.zero(),
            PixelInterval.zero(),
            SequenceConservationBasis.INCOMPLETE_SEQUENCE,
        )
    if any(not spacing.supports_sequence_conservation for spacing in spacings):
        return SequenceConservationEvidence(
            visible_length_px,
            PixelInterval.zero(),
            frame_width_px.scaled(float(count)),
            sum_pixel_intervals(tuple(item.signed_width_px for item in spacings)),
            (
                SequenceConservationBasis.CORROBORATED_SPACING
                if any(
                    isinstance(spacing, CorroboratedSpacingEvidence)
                    for spacing in spacings
                )
                else SequenceConservationBasis.SPACING_HYPOTHESIS
            ),
        )
    occlusion = holder_occlusion.combined_hidden_width_px
    frame_total = frame_width_px.scaled(float(count))
    spacing_total = sum_pixel_intervals(
        tuple(item.signed_width_px for item in spacings)
    )
    return SequenceConservationEvidence(
        visible_length_px,
        occlusion,
        frame_total,
        spacing_total,
        SequenceConservationBasis.INDEPENDENT_SPACING,
    )
