"""Structural work bounds for the indexed template phase pass."""

from __future__ import annotations

from dataclasses import dataclass

from .template_model import TemplateSearchReceipt


@dataclass(frozen=True)
class TemplateWorkBound:
    """Proof terms for one registered observation/role pass.

    ``H`` is the number of direct registered observations and ``R`` is the
    number of fixed theoretical roles.  No field represents a materialized
    chain or a cache; those concepts are outside template work ownership.
    """

    observation_count: int
    role_count: int
    slot_count: int

    def __post_init__(self) -> None:
        if self.observation_count < 0:
            raise ValueError("template observation bound cannot be negative")
        if self.role_count <= 0 or self.role_count != 2 * self.slot_count:
            raise ValueError("template role/slot bound is inconsistent")
        if self.slot_count <= 0:
            raise ValueError("template slot bound must be positive")

    @property
    def phase_lookup_bound(self) -> int:
        return self.observation_count * self.role_count

    @property
    def role_binding_bound(self) -> int:
        return self.observation_count * self.role_count

    @property
    def local_relation_bound(self) -> int:
        return max(0, self.slot_count - 1)

    @property
    def asymptotic_order(self) -> str:
        return "O(H*R)"


def validate_template_work(
    receipt: TemplateSearchReceipt,
    *,
    observation_count: int,
    role_count: int,
    slot_count: int,
) -> TemplateWorkBound:
    """Validate a receipt against the fixed indexed work contract.

    Dimensions are explicit so a caller cannot silently validate a receipt
    against a smaller first-N subset.  Any overflow raises ``ValueError``.
    """

    bound = TemplateWorkBound(
        observation_count=observation_count,
        role_count=role_count,
        slot_count=slot_count,
    )
    receipt.validate_bounds(
        observation_count=observation_count,
        role_count=role_count,
        slot_count=slot_count,
    )
    if (
        receipt.phase_lookup_count > bound.phase_lookup_bound
        or receipt.role_binding_count > bound.role_binding_bound
        or receipt.local_relation_evaluation_count > bound.local_relation_bound
    ):
        raise ValueError("template indexed work exceeded its O(H*R) bound")
    return bound


__all__ = ["TemplateWorkBound", "validate_template_work"]
