"""Review-only intrinsic phase refit for one retained native diagnostic.

This module owns one deliberately narrow geometry replay.  It consumes the
prepared phase input and one complete native endpoint diagnostic, rebuilds the
existing direct-fact ledger, and calls the existing bounded seed fitter at
most once.  The resulting record remains Review evidence: the original
projection and every original authority fact stay attached to the diagnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ...domain import FiniteInterval, ObservationId
from .model import PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .separator_material import normal_separator_material_bands
from .template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleAuthorityFact,
)
from .template_model import (
    SequenceBindingUse,
    SequenceFit,
    adjacency_relation_required_bindings,
    ordered_template_roles,
)
from . import template_phase_candidates as _phase_candidates
from .template_phase_candidates import (
    _BoundFit,
    _PhaseSeed,
    _facts,
    _projected_role_counterevidence_conflicts,
    _separator_pair_facts,
    _with_separator_role_authority,
)
from .template_phase_model import (
    NativeEndpointPhaseDiagnostic,
    TemplatePhaseInput,
)
from .template_separator_support import resolve_separator_support


_INTRINSIC_BASES = frozenset(
    {
        DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
        DirectRoleAuthorityBasis.AGGREGATE_UNION,
    }
)
_FIT_ITERATION_BOUND = 4


class IntrinsicPhaseRefitFailureKind(str, Enum):
    """Typed reasons why the single review refit could not be retained."""

    TEMPLATE_MISMATCH = "template_mismatch"
    ORIGINAL_LEDGER_UNAVAILABLE = "original_ledger_unavailable"
    NO_RETAINED_BINDINGS = "no_retained_bindings"
    NO_VALIDATION_ONLY_BINDINGS = "no_validation_only_bindings"
    RELATION_IDENTITY_UNAVAILABLE = "relation_identity_unavailable"
    INPUT_FACTS_UNAVAILABLE = "input_facts_unavailable"
    FIT_UNAVAILABLE = "fit_unavailable"
    FIT_TEMPLATE_CHANGED = "fit_template_changed"
    FIT_SLOT_CHANGED = "fit_slot_changed"
    FIT_RELATIONS_CHANGED = "fit_relations_changed"
    FIT_BINDINGS_CHANGED = "fit_bindings_changed"
    COUNTEREVIDENCE_UNAVAILABLE = "counterevidence_unavailable"


@dataclass(frozen=True)
class IntrinsicPhaseRefitFailure:
    """One typed failure owned by the review-only refit."""

    kind: IntrinsicPhaseRefitFailureKind
    reason: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, IntrinsicPhaseRefitFailureKind)
            or not isinstance(self.reason, str)
            or not self.reason
        ):
            raise ValueError("intrinsic phase refit failure is incomplete")


@dataclass(frozen=True)
class IntrinsicPhaseRefitWorkReceipt:
    """Logical work and conservative temporary storage for one replay."""

    input_observation_count: int
    input_direct_fact_count: int
    input_separator_pair_count: int
    role_count: int
    retained_intrinsic_count: int
    validation_only_fact_count: int
    fit_seed_call_count: int
    fit_iteration_bound: int
    counterevidence_check_count: int
    peak_temporary_bytes: int

    def __post_init__(self) -> None:
        values = (
            self.input_observation_count,
            self.input_direct_fact_count,
            self.input_separator_pair_count,
            self.role_count,
            self.retained_intrinsic_count,
            self.validation_only_fact_count,
            self.fit_seed_call_count,
            self.fit_iteration_bound,
            self.counterevidence_check_count,
            self.peak_temporary_bytes,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("intrinsic phase refit work is invalid")
        if self.fit_seed_call_count > 1:
            raise ValueError("intrinsic phase refit repeated _fit_seed")
        if self.fit_iteration_bound > _FIT_ITERATION_BOUND:
            raise ValueError("intrinsic phase refit fitter bound is too large")
        if self.fit_seed_call_count == 0 and self.fit_iteration_bound != 0:
            raise ValueError(
                "intrinsic phase refit without _fit_seed must have zero bound"
            )
        if self.counterevidence_check_count > self.validation_only_fact_count:
            raise ValueError("intrinsic phase refit counterevidence exceeds ledger")
        if self.fit_seed_call_count and self.fit_iteration_bound != _FIT_ITERATION_BOUND:
            raise ValueError("intrinsic phase refit must report the full fitter bound")
        if self.input_direct_fact_count > self.input_observation_count:
            raise ValueError("intrinsic phase refit direct count exceeds observations")
        if self.retained_intrinsic_count + self.validation_only_fact_count > self.role_count:
            raise ValueError("intrinsic phase refit ledger exceeds role count")
        if self.peak_temporary_bytes < _temporary_byte_bound(
            self.input_observation_count,
            self.input_direct_fact_count,
            self.input_separator_pair_count,
            self.role_count,
            self.validation_only_fact_count,
        ):
            raise ValueError("intrinsic phase refit peak is below its receipt bound")


def _temporary_byte_bound(
    observation_count: int,
    direct_count: int,
    pair_count: int,
    role_count: int,
    validation_count: int,
) -> int:
    """Bound live containers without claiming a Python heap/RSS measurement.

    The recipe keeps references to the registered observations, direct anchor
    tuple, pair tuple, role/fact identity maps, and the validation ledger.  A
    fixed per-entry allowance covers tuple slots and dictionary entries; the
    referenced observation/fact payloads are existing input objects and are
    not charged as copied geometry.  This is O(N + P + R), with validation
    facts bounded by the role ledger.
    """

    if any(
        type(value) is not int or value < 0
        for value in (
            observation_count,
            direct_count,
            pair_count,
            role_count,
            validation_count,
        )
    ):
        raise ValueError("intrinsic phase refit temporary counts are invalid")
    return (
        4096
        + observation_count * 96
        + direct_count * 96
        + pair_count * 192
        + role_count * 384
        + validation_count * 128
    )


@dataclass(frozen=True)
class IntrinsicPhaseReviewDiagnostic:
    """One geometry-only intrinsic refit with its complete counterevidence."""

    original_diagnostic: NativeEndpointPhaseDiagnostic
    fit: SequenceFit
    residual_compatible: bool
    retained_intrinsic_bindings: tuple[tuple[int, ObservationId], ...]
    validation_only_facts: tuple[DirectRoleAuthorityFact, ...]
    validation_conflicts: tuple[DirectRoleAuthorityFact, ...]
    scope: str = field(default="review_only", init=False)
    authority_projection_success: bool = field(default=False, init=False)
    geometry_outcome: str = field(
        default="intrinsic_refit_with_counterevidence",
        init=False,
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.original_diagnostic, NativeEndpointPhaseDiagnostic)
            or not isinstance(self.fit, SequenceFit)
            or not isinstance(self.residual_compatible, bool)
            or self.scope != "review_only"
            or self.authority_projection_success is not False
            or self.geometry_outcome != "intrinsic_refit_with_counterevidence"
            or tuple(sorted(set(self.retained_intrinsic_bindings)))
            != self.retained_intrinsic_bindings
            or any(
                not isinstance(role_index, int)
                or isinstance(role_index, bool)
                or role_index < 0
                or role_index >= len(self.fit.role_bindings)
                or not isinstance(observation_id, ObservationId)
                for role_index, observation_id in self.retained_intrinsic_bindings
            )
            or any(
                not isinstance(fact, DirectRoleAuthorityFact)
                for fact in self.validation_only_facts
            )
            or any(
                not isinstance(fact, DirectRoleAuthorityFact)
                for fact in self.validation_conflicts
            )
        ):
            raise ValueError("intrinsic phase review diagnostic is invalid")

        original_fit = self.original_diagnostic.fit
        original_facts = self.original_diagnostic.projection.input_direct_role_authority.facts
        fact_identities = {
            (fact.role_index, fact.observation_id) for fact in original_facts
        }
        if len(fact_identities) != len(original_facts):
            raise ValueError("intrinsic review authority ledger repeats an identity")

        expected_retained: list[tuple[int, ObservationId]] = []
        expected_validation: list[DirectRoleAuthorityFact] = []
        for fact in original_facts:
            if not 0 <= fact.role_index < len(original_fit.role_bindings):
                raise ValueError("intrinsic review authority role leaves its fit")
            binding = original_fit.role_bindings[fact.role_index]
            if binding is None or binding.observation_id != fact.observation_id:
                raise ValueError("intrinsic review authority lost its fit identity")
            identity = (fact.role_index, fact.observation_id)
            if (
                binding.use == SequenceBindingUse.PHASE_ANCHOR
                and _INTRINSIC_BASES.intersection(fact.bases)
            ):
                expected_retained.append(identity)
            else:
                expected_validation.append(fact)

        if (
            self.retained_intrinsic_bindings != tuple(expected_retained)
            or self.validation_only_facts != tuple(expected_validation)
            or any(fact not in self.validation_only_facts for fact in self.validation_conflicts)
            or len(set(self.validation_conflicts)) != len(self.validation_conflicts)
        ):
            raise ValueError("intrinsic review ledger partition changed")

        output_bindings = tuple(
            (role_index, binding.observation_id)
            for role_index, binding in enumerate(self.fit.role_bindings)
            if binding is not None
        )
        if (
            self.fit.template != original_fit.template
            or self.fit.phase_lattice_fit.integer_slot_offset
            != original_fit.phase_lattice_fit.integer_slot_offset
            or self.fit.adjacency_relations != original_fit.adjacency_relations
            or output_bindings != self.retained_intrinsic_bindings
            or any(
                binding is not None and binding.use != SequenceBindingUse.PHASE_ANCHOR
                for binding in self.fit.role_bindings
            )
        ):
            raise ValueError("intrinsic review fit changed fixed identity")

        expected_conflicts = _projected_role_counterevidence_conflicts(
            _BoundFit(self.fit, self.residual_compatible),
            _BoundFit(original_fit, self.original_diagnostic.residual_compatible),
            self.validation_only_facts,
        )
        if self.validation_conflicts != expected_conflicts:
            raise ValueError("intrinsic review conflicts changed full intervals")


@dataclass(frozen=True)
class IntrinsicPhaseRefitResult:
    """Result of one bounded intrinsic review refit attempt."""

    original_diagnostic: NativeEndpointPhaseDiagnostic
    diagnostic: IntrinsicPhaseReviewDiagnostic | None
    failure: IntrinsicPhaseRefitFailure | None
    work: IntrinsicPhaseRefitWorkReceipt

    def __post_init__(self) -> None:
        if (
            not isinstance(self.original_diagnostic, NativeEndpointPhaseDiagnostic)
            or not isinstance(self.work, IntrinsicPhaseRefitWorkReceipt)
            or (self.diagnostic is None) == (self.failure is None)
            or self.diagnostic is not None
            and (
                not isinstance(self.diagnostic, IntrinsicPhaseReviewDiagnostic)
                or self.diagnostic.original_diagnostic != self.original_diagnostic
            )
            or self.failure is not None
            and not isinstance(self.failure, IntrinsicPhaseRefitFailure)
            or self.diagnostic is not None
            and (
                self.work.retained_intrinsic_count
                != len(self.diagnostic.retained_intrinsic_bindings)
                or self.work.validation_only_fact_count
                != len(self.diagnostic.validation_only_facts)
                or self.work.counterevidence_check_count
                != len(self.diagnostic.validation_only_facts)
                or self.work.fit_seed_call_count != 1
                or self.work.fit_iteration_bound != _FIT_ITERATION_BOUND
                or self.work.role_count != len(self.diagnostic.fit.role_bindings)
            )
        ):
            raise ValueError("intrinsic phase refit result is invalid")


def _result(
    original: NativeEndpointPhaseDiagnostic,
    *,
    diagnostic: IntrinsicPhaseReviewDiagnostic | None,
    failure: IntrinsicPhaseRefitFailure | None,
    observation_count: int,
    direct_count: int,
    pair_count: int,
    role_count: int,
    retained_count: int,
    validation_count: int,
    fit_seed_call_count: int,
    counterevidence_check_count: int,
) -> IntrinsicPhaseRefitResult:
    return IntrinsicPhaseRefitResult(
        original_diagnostic=original,
        diagnostic=diagnostic,
        failure=failure,
        work=IntrinsicPhaseRefitWorkReceipt(
            input_observation_count=observation_count,
            input_direct_fact_count=direct_count,
            input_separator_pair_count=pair_count,
            role_count=role_count,
            retained_intrinsic_count=retained_count,
            validation_only_fact_count=validation_count,
            fit_seed_call_count=fit_seed_call_count,
            fit_iteration_bound=(_FIT_ITERATION_BOUND if fit_seed_call_count else 0),
            counterevidence_check_count=counterevidence_check_count,
            peak_temporary_bytes=_temporary_byte_bound(
                observation_count,
                direct_count,
                pair_count,
                role_count,
                validation_count,
            ),
        ),
    )


def _failed(
    original: NativeEndpointPhaseDiagnostic,
    kind: IntrinsicPhaseRefitFailureKind,
    reason: str,
    **counts: int,
) -> IntrinsicPhaseRefitResult:
    return _result(
        original,
        diagnostic=None,
        failure=IntrinsicPhaseRefitFailure(kind, reason),
        observation_count=counts.get("observation_count", 0),
        direct_count=counts.get("direct_count", 0),
        pair_count=counts.get("pair_count", 0),
        role_count=counts.get("role_count", len(original.fit.role_bindings)),
        retained_count=counts.get("retained_count", 0),
        validation_count=counts.get("validation_count", 0),
        fit_seed_call_count=counts.get("fit_seed_call_count", 0),
        counterevidence_check_count=counts.get("counterevidence_check_count", 0),
    )


def _template_pitch_authority(template) -> FiniteInterval:
    width = FiniteInterval(
        template.frame_width_px.minimum,
        template.frame_width_px.maximum,
    )
    gap_pitch = FiniteInterval(
        width.minimum + template.gap_prior_px.minimum,
        width.maximum + template.gap_prior_px.maximum,
    )
    minimum = max(gap_pitch.minimum, template.pitch_px.minimum)
    maximum = min(gap_pitch.maximum, template.pitch_px.maximum)
    if minimum > maximum:
        raise ValueError("template pitch authority has no legal intersection")
    return FiniteInterval(minimum, maximum)


def build_intrinsic_phase_refit(
    phase_input: TemplatePhaseInput,
    original: NativeEndpointPhaseDiagnostic,
) -> IntrinsicPhaseRefitResult:
    """Replay one retained diagnostic using the fixed intrinsic recipe."""

    if not isinstance(phase_input, TemplatePhaseInput):
        raise TypeError("intrinsic phase refit requires typed phase input")
    if not isinstance(original, NativeEndpointPhaseDiagnostic):
        raise TypeError("intrinsic phase refit requires a typed native diagnostic")

    template = phase_input.template
    original_fit = original.fit
    role_count = len(ordered_template_roles(template.count))
    if template != original_fit.template:
        return _failed(
            original,
            IntrinsicPhaseRefitFailureKind.TEMPLATE_MISMATCH,
            "prepared phase input and native diagnostic use different templates",
            observation_count=len(phase_input.observations),
            role_count=role_count,
        )

    original_facts = original.projection.input_direct_role_authority.facts
    registered_direct_observation_ids = frozenset(
        observation.observation_id for observation in phase_input.observations
    )
    fact_identities: set[tuple[int, ObservationId]] = set()
    for fact in original_facts:
        identity = (fact.role_index, fact.observation_id)
        if identity in fact_identities or not 0 <= fact.role_index < role_count:
            return _failed(
                original,
                IntrinsicPhaseRefitFailureKind.ORIGINAL_LEDGER_UNAVAILABLE,
                "native diagnostic authority ledger is not role-indexed",
                observation_count=len(phase_input.observations),
                role_count=role_count,
            )
        if fact.observation_id not in registered_direct_observation_ids:
            return _failed(
                original,
                IntrinsicPhaseRefitFailureKind.ORIGINAL_LEDGER_UNAVAILABLE,
                "native diagnostic fact leaves the registered phase observations",
                observation_count=len(phase_input.observations),
                role_count=role_count,
            )
        binding = original_fit.role_bindings[fact.role_index]
        if binding is None or binding.observation_id != fact.observation_id:
            return _failed(
                original,
                IntrinsicPhaseRefitFailureKind.ORIGINAL_LEDGER_UNAVAILABLE,
                "native diagnostic authority fact has no exact original binding",
                observation_count=len(phase_input.observations),
                role_count=role_count,
            )
        fact_identities.add(identity)

    retained: list[tuple[int, ObservationId]] = []
    validation_only: list[DirectRoleAuthorityFact] = []
    for fact in original_facts:
        binding = original_fit.role_bindings[fact.role_index]
        assert binding is not None
        if (
            binding.use == SequenceBindingUse.PHASE_ANCHOR
            and _INTRINSIC_BASES.intersection(fact.bases)
        ):
            retained.append((fact.role_index, fact.observation_id))
        else:
            validation_only.append(fact)
    retained_bindings = tuple(retained)
    validation_facts = tuple(validation_only)
    retained_set = frozenset(retained_bindings)
    required_relations = adjacency_relation_required_bindings(
        original_fit.adjacency_relations
    )
    if any(identity not in retained_set for identity in required_relations):
        return _failed(
            original,
            IntrinsicPhaseRefitFailureKind.RELATION_IDENTITY_UNAVAILABLE,
            "an original adjacency relation requires a non-retained identity",
            observation_count=len(phase_input.observations),
            role_count=role_count,
            retained_count=len(retained_bindings),
            validation_count=len(validation_facts),
        )
    if not retained_bindings:
        return _failed(
            original,
            IntrinsicPhaseRefitFailureKind.NO_RETAINED_BINDINGS,
            "the fixed diagnostic has no retained intrinsic phase anchors",
            observation_count=len(phase_input.observations),
            role_count=role_count,
            validation_count=len(validation_facts),
        )
    if not validation_facts:
        return _failed(
            original,
            IntrinsicPhaseRefitFailureKind.NO_VALIDATION_ONLY_BINDINGS,
            "the fixed diagnostic has no validation-only binding ledger",
            observation_count=len(phase_input.observations),
            role_count=role_count,
            retained_count=len(retained_bindings),
        )

    try:
        eligible_bands = normal_separator_material_bands(
            phase_input.separator_bands,
            maximum_material_gap_px=template.gap_prior_px.maximum,
        )
        support_resolution = resolve_separator_support(
            phase_input.observations,
            eligible_bands,
        )
        qualified_observations = _with_separator_role_authority(
            phase_input.observations,
            phase_input.separator_bands,
            maximum_material_gap_px=template.gap_prior_px.maximum,
        )
        registered_trace_positions = (
            phase_input.sequence_measurement_sets[0].query.trace_positions_px
            if phase_input.sequence_measurement_sets
            else ()
        )
        facts = _facts(
            qualified_observations,
            separator_support_ids=support_resolution.edge_component_ids,
            registered_trace_positions_px=registered_trace_positions,
        )
        direct = tuple(item for item in facts if item.direct)
        direct_by_id = {item.observation_id: item for item in direct}
        if any(identity[1] not in direct_by_id for identity in retained_bindings):
            return _failed(
                original,
                IntrinsicPhaseRefitFailureKind.INPUT_FACTS_UNAVAILABLE,
                "a retained native identity is absent from rebuilt direct facts",
                observation_count=len(phase_input.observations),
                direct_count=len(direct),
                role_count=role_count,
                retained_count=len(retained_bindings),
                validation_count=len(validation_facts),
            )
        retained_observation_ids = frozenset(
            identity[1] for identity in retained_bindings
        )
        separator_pairs = _separator_pair_facts(
            eligible_bands,
            direct,
            maximum_material_gap_px=template.gap_prior_px.maximum,
        )
        retained_separator_pairs = tuple(
            pair
            for pair in separator_pairs
            if all(item.observation_id in retained_observation_ids for item in pair)
        )
        pitch_authority = _template_pitch_authority(template)
        fit_residual_limit = (
            None
            if phase_input.scale_px_per_mm is None
            else PHOTO_BOUNDARY_MEASUREMENT_SPEC.line_connection_allowance_px(
                phase_input.scale_px_per_mm.maximum
            )
        )
    except ValueError as exc:
        return _failed(
            original,
            IntrinsicPhaseRefitFailureKind.INPUT_FACTS_UNAVAILABLE,
            str(exc),
            observation_count=len(phase_input.observations),
            role_count=role_count,
            retained_count=len(retained_bindings),
            validation_count=len(validation_facts),
        )

    phase_anchor_ceiling = frozenset(
        identity
        for identity in retained_bindings
        if original_fit.role_bindings[identity[0]] is not None
        and original_fit.role_bindings[identity[0]].use
        == SequenceBindingUse.PHASE_ANCHOR
    )
    seed = _PhaseSeed(
        phase_px=original_fit.phase_lattice_fit.canonical_absolute_phase_px,
        pitch_px=original_fit.pitch_fit.canonical_pitch_px,
        required_bindings=retained_bindings,
        adjacency_relations=original_fit.adjacency_relations,
    )
    fit_seed_call_count = 1
    try:
        proposal = _phase_candidates._fit_seed(
            seed,
            tuple(
                item
                for item in direct
                if item.observation_id in retained_observation_ids
            ),
            retained_separator_pairs,
            ordered_template_roles(template.count),
            template,
            original_fit.adjacency_relations,
            pitch_authority,
            phase_input.phase_authority_px,
            fit_residual_limit,
            phase_anchor_ceiling,
        )
    except ValueError as exc:
        return _failed(
            original,
            IntrinsicPhaseRefitFailureKind.FIT_UNAVAILABLE,
            str(exc),
            observation_count=len(phase_input.observations),
            direct_count=len(direct),
            pair_count=len(separator_pairs),
            role_count=role_count,
            retained_count=len(retained_bindings),
            validation_count=len(validation_facts),
            fit_seed_call_count=fit_seed_call_count,
        )
    if proposal is None:
        return _failed(
            original,
            IntrinsicPhaseRefitFailureKind.FIT_UNAVAILABLE,
            "the bounded intrinsic seed produced no fit",
            observation_count=len(phase_input.observations),
            direct_count=len(direct),
            pair_count=len(separator_pairs),
            role_count=role_count,
            retained_count=len(retained_bindings),
            validation_count=len(validation_facts),
            fit_seed_call_count=fit_seed_call_count,
        )
    if not isinstance(proposal, _BoundFit) or not isinstance(proposal.fit, SequenceFit):
        return _failed(
            original,
            IntrinsicPhaseRefitFailureKind.FIT_UNAVAILABLE,
            "the bounded intrinsic seed returned an untyped fit",
            observation_count=len(phase_input.observations),
            direct_count=len(direct),
            pair_count=len(separator_pairs),
            role_count=role_count,
            retained_count=len(retained_bindings),
            validation_count=len(validation_facts),
            fit_seed_call_count=fit_seed_call_count,
        )

    proposal_fit = proposal.fit
    output_bindings = tuple(
        (role_index, binding.observation_id)
        for role_index, binding in enumerate(proposal_fit.role_bindings)
        if binding is not None
    )
    if proposal_fit.template != original_fit.template:
        kind = IntrinsicPhaseRefitFailureKind.FIT_TEMPLATE_CHANGED
        reason = "bounded intrinsic seed changed template identity"
    elif (
        proposal_fit.phase_lattice_fit.integer_slot_offset
        != original_fit.phase_lattice_fit.integer_slot_offset
    ):
        kind = IntrinsicPhaseRefitFailureKind.FIT_SLOT_CHANGED
        reason = "bounded intrinsic seed changed integer slot offset"
    elif proposal_fit.adjacency_relations != original_fit.adjacency_relations:
        kind = IntrinsicPhaseRefitFailureKind.FIT_RELATIONS_CHANGED
        reason = "bounded intrinsic seed changed adjacency relations"
    elif output_bindings != retained_bindings or any(
        binding is not None and binding.use != SequenceBindingUse.PHASE_ANCHOR
        for binding in proposal_fit.role_bindings
    ):
        kind = IntrinsicPhaseRefitFailureKind.FIT_BINDINGS_CHANGED
        reason = "bounded intrinsic seed changed retained binding identities"
    else:
        kind = None
        reason = ""
    if kind is not None:
        return _failed(
            original,
            kind,
            reason,
            observation_count=len(phase_input.observations),
            direct_count=len(direct),
            pair_count=len(separator_pairs),
            role_count=role_count,
            retained_count=len(retained_bindings),
            validation_count=len(validation_facts),
            fit_seed_call_count=fit_seed_call_count,
        )

    try:
        original_bound = _BoundFit(original_fit, original.residual_compatible)
        validation_conflicts = _projected_role_counterevidence_conflicts(
            proposal,
            original_bound,
            validation_facts,
        )
    except ValueError as exc:
        return _failed(
            original,
            IntrinsicPhaseRefitFailureKind.COUNTEREVIDENCE_UNAVAILABLE,
            str(exc),
            observation_count=len(phase_input.observations),
            direct_count=len(direct),
            pair_count=len(separator_pairs),
            role_count=role_count,
            retained_count=len(retained_bindings),
            validation_count=len(validation_facts),
            fit_seed_call_count=fit_seed_call_count,
        )

    diagnostic = IntrinsicPhaseReviewDiagnostic(
        original_diagnostic=original,
        fit=proposal_fit,
        residual_compatible=proposal.residual_compatible,
        retained_intrinsic_bindings=retained_bindings,
        validation_only_facts=validation_facts,
        validation_conflicts=validation_conflicts,
    )
    return _result(
        original,
        diagnostic=diagnostic,
        failure=None,
        observation_count=len(phase_input.observations),
        direct_count=len(direct),
        pair_count=len(separator_pairs),
        role_count=role_count,
        retained_count=len(retained_bindings),
        validation_count=len(validation_facts),
        fit_seed_call_count=fit_seed_call_count,
        counterevidence_check_count=len(validation_facts),
    )


__all__ = [
    "IntrinsicPhaseRefitFailure",
    "IntrinsicPhaseRefitFailureKind",
    "IntrinsicPhaseRefitResult",
    "IntrinsicPhaseRefitWorkReceipt",
    "IntrinsicPhaseReviewDiagnostic",
    "build_intrinsic_phase_refit",
]
