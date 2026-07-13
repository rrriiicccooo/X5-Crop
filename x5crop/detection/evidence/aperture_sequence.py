from __future__ import annotations

from dataclasses import dataclass, field

from ...domain import EvidenceState, PixelInterval, sum_pixel_intervals
from ..physical.model import PhotoSequenceSolution


@dataclass(frozen=True)
class PhotoSequenceConservationEvidence:
    sequence_span_px: PixelInterval
    aperture_total_px: PixelInterval
    spacing_total_px: PixelInterval
    all_boundaries_measured: bool
    all_spacings_observed: bool
    reconstructed_span_px: PixelInterval = field(init=False)
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        reconstructed = self.aperture_total_px.plus(self.spacing_total_px)
        if not self.all_boundaries_measured or not self.all_spacings_observed:
            state = EvidenceState.UNAVAILABLE
            reason = "photo_sequence_measurements_incomplete"
        elif self.sequence_span_px.intersects(reconstructed):
            state = EvidenceState.SUPPORTED
            reason = "measured_photo_sequence_conserved"
        else:
            state = EvidenceState.CONTRADICTED
            reason = "measured_photo_sequence_not_conserved"
        object.__setattr__(self, "reconstructed_span_px", reconstructed)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def sequence_conservation_for_geometry(
    geometry: PhotoSequenceSolution,
) -> PhotoSequenceConservationEvidence:
    apertures = geometry.photo_apertures
    return PhotoSequenceConservationEvidence(
        sequence_span_px=apertures[-1].trailing.position.minus(
            apertures[0].leading.position
        ),
        aperture_total_px=sum_pixel_intervals(
            tuple(
                aperture.trailing.position.minus(aperture.leading.position)
                for aperture in apertures
            )
        ),
        spacing_total_px=sum_pixel_intervals(
            tuple(spacing.signed_width_px for spacing in geometry.inter_photo_spacings)
        ),
        all_boundaries_measured=all(
            aperture.leading.independently_observed
            and aperture.trailing.independently_observed
            for aperture in apertures
        ),
        all_spacings_observed=all(
            spacing.independently_observed
            for spacing in geometry.inter_photo_spacings
        ),
    )
