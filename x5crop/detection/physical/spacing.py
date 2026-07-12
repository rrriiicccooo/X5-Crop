from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import (
    BoundaryObservation,
    EvidenceState,
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
    index: int,
    kind: str,
    signed_width_px: PixelInterval,
    reason: str,
    lane_index: int | None,
) -> None:
    if index <= 0:
        raise ValueError("inter-frame spacing index must be positive")
    if kind not in SPACING_KINDS:
        raise ValueError(f"unsupported inter-frame spacing: {kind}")
    if kind != _spacing_kind(signed_width_px):
        raise ValueError("inter-frame spacing kind must match its signed interval")
    if not reason:
        raise ValueError("inter-frame spacing requires a reason")
    if lane_index is not None and lane_index <= 0:
        raise ValueError("lane index must be positive")


@dataclass(frozen=True)
class ObservedSpacingEvidence:
    index: int
    kind: str
    signed_width_px: PixelInterval
    provenance: MeasurementProvenance
    reason: str
    lane_index: int | None = None

    def __post_init__(self) -> None:
        _validate_spacing_identity(
            self.index,
            self.kind,
            self.signed_width_px,
            self.reason,
            self.lane_index,
        )

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
    index: int
    kind: str
    signed_width_px: PixelInterval
    provenance: MeasurementProvenance
    reason: str
    lane_index: int | None = None

    def __post_init__(self) -> None:
        _validate_spacing_identity(
            self.index,
            self.kind,
            self.signed_width_px,
            self.reason,
            self.lane_index,
        )
        if self.kind != "overlap" or self.signed_width_px.maximum >= 0.0:
            raise ValueError("corroborated spacing evidence must be an overlap")

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
    index: int
    kind: str
    signed_width_px: PixelInterval
    provenance: MeasurementProvenance
    reason: str
    lane_index: int | None = None

    def __post_init__(self) -> None:
        _validate_spacing_identity(
            self.index,
            self.kind,
            self.signed_width_px,
            self.reason,
            self.lane_index,
        )

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


@dataclass(frozen=True)
class SequenceConservationEvidence:
    state: EvidenceState
    reason: str
    visible_length_px: PixelInterval
    holder_occlusion_px: PixelInterval
    frame_total_px: PixelInterval
    spacing_total_px: PixelInterval
    physical_sequence_px: PixelInterval


def observed_spacing_evidence(
    index: int,
    signed_width_px: PixelInterval,
    provenance: MeasurementProvenance,
) -> ObservedSpacingEvidence:
    kind = _spacing_kind(signed_width_px)
    return ObservedSpacingEvidence(
        index=index,
        kind=kind,
        signed_width_px=signed_width_px,
        provenance=provenance,
        reason=f"observed_{kind}_spacing",
    )


def spacing_hypothesis(
    index: int,
    signed_width_px: PixelInterval,
    provenance: MeasurementProvenance,
) -> SpacingHypothesis:
    kind = _spacing_kind(signed_width_px)
    return SpacingHypothesis(
        index=index,
        kind=kind,
        signed_width_px=signed_width_px,
        provenance=provenance,
        reason=f"{kind}_spacing_hypothesis",
    )


def corroborate_single_missing_overlap(
    *,
    visible_length_px: PixelInterval,
    count: int,
    frame_width_px: PixelInterval,
    spacings: tuple[InterFrameSpacing, ...],
    holder_occlusion: HolderOcclusionEvidence,
    boundary_observations: tuple[BoundaryObservation, ...],
    dimension_source: str,
) -> tuple[InterFrameSpacing, ...]:
    if dimension_source != "scan_calibration":
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
    occlusion = holder_occlusion.leading.hidden_width_px.plus(
        holder_occlusion.trailing.hidden_width_px
    )
    residual = (
        visible_length_px.plus(occlusion)
        .minus(frame_width_px.scaled(float(count)))
        .minus(
            sum_pixel_intervals(
                tuple(spacing.signed_width_px for spacing in observed)
            )
        )
    )
    if residual.maximum >= 0.0:
        return spacings
    missing_position, missing_spacing = missing[0]
    leading = edge_observations["leading"]
    trailing = edge_observations["trailing"]
    corroborated = CorroboratedSpacingEvidence(
        index=missing_spacing.index,
        kind="overlap",
        signed_width_px=residual,
        provenance=MeasurementProvenance(
            root_measurement="calibrated_sequence_constraints",
            source="single_missing_overlap_corroboration",
            dependencies=tuple(
                dict.fromkeys(
                    (
                        "scan_calibration",
                        leading.provenance.root_measurement,
                        trailing.provenance.root_measurement,
                        *(item.provenance.root_measurement for item in observed),
                    )
                )
            ),
        ),
        reason="independent_constraints_require_overlap",
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
            EvidenceState.UNAVAILABLE,
            "count_or_spacing_sequence_incomplete",
            visible_length_px,
            PixelInterval.zero(),
            PixelInterval.zero(),
            PixelInterval.zero(),
            PixelInterval.zero(),
        )
    if any(not spacing.supports_sequence_conservation for spacing in spacings):
        return SequenceConservationEvidence(
            EvidenceState.UNAVAILABLE,
            (
                "conservation_derived_spacing_not_independent"
                if any(
                    isinstance(spacing, CorroboratedSpacingEvidence)
                    for spacing in spacings
                )
                else "signed_spacing_unresolved"
            ),
            visible_length_px,
            PixelInterval.zero(),
            frame_width_px.scaled(float(count)),
            sum_pixel_intervals(tuple(item.signed_width_px for item in spacings)),
            PixelInterval.zero(),
        )
    occlusion = holder_occlusion.leading.hidden_width_px.plus(
        holder_occlusion.trailing.hidden_width_px
    )
    frame_total = frame_width_px.scaled(float(count))
    spacing_total = sum_pixel_intervals(
        tuple(item.signed_width_px for item in spacings)
    )
    observed_physical = visible_length_px.plus(occlusion)
    modeled_physical = frame_total.plus(spacing_total)
    supported = observed_physical.intersects(modeled_physical)
    return SequenceConservationEvidence(
        EvidenceState.SUPPORTED if supported else EvidenceState.CONTRADICTED,
        "frame_sequence_conserved" if supported else "frame_sequence_not_conserved",
        visible_length_px,
        occlusion,
        frame_total,
        spacing_total,
        modeled_physical,
    )
