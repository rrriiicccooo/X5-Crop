"""Prove that Grid inference did not invent an unanchored outer frame."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import EvidenceState, ObservationId
from .template_model import SequenceFit


@dataclass(frozen=True)
class OuterFrameObservationAuthority:
    """Direct long-axis ownership for the first and last output frames."""

    state: EvidenceState
    first_frame_ordinal: int
    last_frame_ordinal: int
    first_frame_observation_ids: tuple[ObservationId, ...]
    last_frame_observation_ids: tuple[ObservationId, ...]
    reason: str | None

    def __post_init__(self) -> None:
        groups = (
            self.first_frame_observation_ids,
            self.last_frame_observation_ids,
        )
        if (
            self.state not in {EvidenceState.SUPPORTED, EvidenceState.UNAVAILABLE}
            or self.first_frame_ordinal != 1
            or self.last_frame_ordinal < self.first_frame_ordinal
            or any(
                tuple(dict.fromkeys(group)) != group
                or any(not isinstance(identity, ObservationId) for identity in group)
                for group in groups
            )
        ):
            raise ValueError("outer-frame observation authority is invalid")
        supported = self.state == EvidenceState.SUPPORTED
        if supported != all(groups) or supported != (self.reason is None):
            raise ValueError("outer-frame authority state disagrees with provenance")


def assess_outer_frame_observation_authority(
    fit: SequenceFit,
) -> OuterFrameObservationAuthority:
    """Require one direct role on each frame adjacent to the source exterior."""

    if not isinstance(fit, SequenceFit):
        raise TypeError("outer-frame authority requires a sequence fit")
    bindings = fit.binding_observation_ids
    first = tuple(
        dict.fromkeys(identity for identity in bindings[:2] if identity is not None)
    )
    last = tuple(
        dict.fromkeys(identity for identity in bindings[-2:] if identity is not None)
    )
    missing: list[str] = []
    if not first:
        missing.append("first")
    if not last:
        missing.append("last")
    return OuterFrameObservationAuthority(
        state=(
            EvidenceState.SUPPORTED
            if not missing
            else EvidenceState.UNAVAILABLE
        ),
        first_frame_ordinal=1,
        last_frame_ordinal=fit.template.count,
        first_frame_observation_ids=first,
        last_frame_observation_ids=last,
        reason=(
            None
            if not missing
            else "outer frame has no directly bound long-axis role: "
            + ", ".join(missing)
        ),
    )


__all__ = [
    "OuterFrameObservationAuthority",
    "assess_outer_frame_observation_authority",
]
