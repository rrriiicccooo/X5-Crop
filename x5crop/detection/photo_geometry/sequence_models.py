"""Sequence relation and discovery data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import EvidenceState, FiniteInterval, ObservationId


class LocalAdvanceKind(str, Enum):
    NOMINAL = "nominal"
    OBSERVED_NORMAL = "observed_normal"
    WIDE = "wide"
    NARROW = "narrow"
    CONTACT = "contact"
    OVERLAP = "overlap"
    OBSERVED_UNCLASSIFIED = "observed_unclassified"


class SequenceDiscoveryKind(str, Enum):
    NORMAL_DEFAULT = "normal_default"
    DIRECT_EXCEPTION = "direct_exception"


@dataclass(frozen=True)
class LongAxisFillAuthority:
    """Conditional authority for a holder-filling normal sequence."""

    state: EvidenceState
    chain_span_interval_px: FiniteInterval | None
    centered_midpoint_authority_px: FiniteInterval | None
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        supported = self.state == EvidenceState.SUPPORTED
        if (
            supported != (self.chain_span_interval_px is not None)
            or supported != (self.centered_midpoint_authority_px is not None)
            or len(set(self.observation_ids)) != len(self.observation_ids)
            or self.state
            not in {EvidenceState.SUPPORTED, EvidenceState.UNAVAILABLE}
            or (not supported and self.observation_ids)
        ):
            raise ValueError("long-axis fill authority is invalid")

    @classmethod
    def unavailable(cls) -> "LongAxisFillAuthority":
        return cls(EvidenceState.UNAVAILABLE, None, None, ())


@dataclass(frozen=True)
class LocalAdvanceRelation:
    relation_ordinal: int
    kind: LocalAdvanceKind
    delta_interval_px: FiniteInterval
    canonical_delta_px: float
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if (
            self.relation_ordinal <= 0
            or not self.delta_interval_px.contains(
                self.canonical_delta_px,
                epsilon=1.0e-9,
            )
            or len(set(self.observation_ids)) != len(self.observation_ids)
            or (
                self.kind == LocalAdvanceKind.NOMINAL
                and (
                    self.delta_interval_px != FiniteInterval.exact(0.0)
                    or self.canonical_delta_px != 0.0
                )
            )
            or (
                self.kind != LocalAdvanceKind.NOMINAL
                and not self.observation_ids
            )
        ):
            raise ValueError("local advance relation is invalid")
