"""Bounded Review-only retention of existing source-clipped phase records."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ...domain import EvidenceState, ObservationId
from .template_direct_role_authority import DirectRoleAuthorityBasis
from .template_model import SequenceBindingUse, SequenceFit, TemplateSpec
from .template_source_domain import PhaseSourceDomain, source_clipped_terminal_roles


# First START ranks 1, 2, 3, then last END ranks 1, 2, 3.
SOURCE_CLIPPED_CLASS_COUNT = 6
_INTRINSIC_BASES = frozenset({
    DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
    DirectRoleAuthorityBasis.AGGREGATE_UNION,
})


def _temporary_byte_bound(role_count: int, *, carry: bool = False) -> int:
    """Conservative logical allowance, not a process-memory measurement.

    Six role-sized validation/rank/fact indices, the current record, three
    class maps and complete-equality deduplication references fit O(6R).
    Full immutable fits and authority ledgers are referenced, never copied.
    """

    return (
        1024
        + SOURCE_CLIPPED_CLASS_COUNT * (256 + role_count * 256)
        + (12 if carry else 7) * 1024
        + 3 * SOURCE_CLIPPED_CLASS_COUNT * 128
        + 256 + SOURCE_CLIPPED_CLASS_COUNT * 128
    )


def _intrinsic_phase_roles(
    fit: SequenceFit,
    projection: phase_model.PhaseCandidateAuthorityProjection,
) -> tuple[int, ...]:
    return tuple(
        fact.role_index
        for fact in projection.input_direct_role_authority.facts
        if fact.state == EvidenceState.SUPPORTED
        and _INTRINSIC_BASES.intersection(fact.bases)
        and 0 <= fact.role_index < len(fit.role_bindings)
        and (binding := fit.role_bindings[fact.role_index]) is not None
        and binding.use == SequenceBindingUse.PHASE_ANCHOR
        and binding.observation_id == fact.observation_id
    )


def _outer_material_terminal(
    fit: SequenceFit,
    projection: phase_model.PhaseCandidateAuthorityProjection,
) -> bool:
    terminal_indices = {0, 1, len(fit.role_bindings) - 2, len(fit.role_bindings) - 1}
    return any(
        fact.role_index in terminal_indices
        and _INTRINSIC_BASES.intersection(fact.bases)
        and DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY in fact.bases
        and (binding := fit.role_bindings[fact.role_index]) is not None
        and binding.observation_id == fact.observation_id
        for fact in projection.input_direct_role_authority.facts
    )


@dataclass(frozen=True)
class SourceClippedPhaseDiagnostic:
    """One unchanged effective fit, its entire projection and real source domain."""

    fit: SequenceFit
    projection: phase_model.PhaseCandidateAuthorityProjection
    residual_compatible: bool
    source_domain: PhaseSourceDomain
    clipped_role_indices: tuple[int, ...]
    constraint_rank: int

    def __post_init__(self) -> None:
        from .template_lattice_authority import direct_role_constraint_rank

        if (
            not isinstance(self.fit, SequenceFit)
            or not isinstance(self.projection, phase_model.PhaseCandidateAuthorityProjection)
            or type(self.residual_compatible) is not bool
            or not isinstance(self.source_domain, PhaseSourceDomain)
            or not isinstance(self.clipped_role_indices, tuple)
            or any(type(index) is not int for index in self.clipped_role_indices)
            or type(self.constraint_rank) is not int
            or self.constraint_rank not in (1, 2, 3)
        ):
            raise ValueError("source-clipped phase diagnostic is invalid")
        phase_model._validate_native_projection_fit_mapping(self.fit, self.projection)
        clipped = source_clipped_terminal_roles(self.fit, self.source_domain)
        if not clipped or clipped != self.clipped_role_indices:
            raise ValueError("source-clipped diagnostic has no valid source terminal")
        if not _intrinsic_phase_roles(self.fit, self.projection):
            raise ValueError("source-clipped diagnostic lacks a supported intrinsic phase anchor")
        if (
            self.constraint_rank != self.projection.retained_direct_constraint_rank
            or self.constraint_rank != direct_role_constraint_rank(
                self.fit,
                self.projection.input_direct_role_authority.supported_role_indices,
            )
        ):
            raise ValueError("source-clipped diagnostic changed its retained direct rank")

    @property
    def class_memberships(self) -> tuple[int, ...]:
        last = len(self.fit.role_bindings) - 1
        return tuple(
            offset + self.constraint_rank - 1
            for terminal, offset in ((0, 0), (last, 3))
            if terminal in self.clipped_role_indices
        )

    @property
    def selection_key(self) -> tuple[object, ...]:
        from .template_phase_candidates import _BoundFit, _rank

        return (
            int(_outer_material_terminal(self.fit, self.projection)),
            int(self.projection.eligible),
            *_rank(_BoundFit(self.fit, self.residual_compatible)),
        )


@dataclass(frozen=True)
class SourceClippedPhaseRetention:
    """At most six complete diagnostics, in first-class reference order.

    Receipts count producer scans/comparisons. Typed construction rechecks the
    same predicates in O(MR); it introduces no search or geometry mutation.
    ``source_role_check_count`` charges one R-sized source-domain check per
    scanned record, including records rejected by an early geometry exit.
    """

    diagnostics: tuple[SourceClippedPhaseDiagnostic, ...] = ()
    class_indices: tuple[int | None, int | None, int | None, int | None, int | None, int | None] = (
        None, None, None, None, None, None,
    )
    record_scan_count: int = 0
    source_role_check_count: int = 0
    fact_check_count: int = 0
    constraint_rank_check_count: int = 0
    class_membership_count: int = 0
    class_comparison_count: int = 0
    carry_comparison_count: int = 0
    deduplication_comparison_count: int = 0
    peak_temporary_bytes: int = 0
    role_count: int = 0
    template: TemplateSpec | None = None
    source_domain: PhaseSourceDomain | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, SourceClippedPhaseDiagnostic) for item in self.diagnostics
        ):
            raise TypeError("source-clipped retention diagnostics are invalid")
        if len(self.diagnostics) > SOURCE_CLIPPED_CLASS_COUNT:
            raise ValueError("source-clipped retention exceeds six diagnostics")
        if not isinstance(self.class_indices, tuple) or len(self.class_indices) != SOURCE_CLIPPED_CLASS_COUNT:
            raise ValueError("source-clipped retention requires six classes")
        referenced: set[int] = set()
        for role_class, index in enumerate(self.class_indices):
            if index is None:
                continue
            if type(index) is not int or not 0 <= index < len(self.diagnostics):
                raise ValueError("source-clipped retention class index is invalid")
            if role_class not in self.diagnostics[index].class_memberships:
                raise ValueError("source-clipped retention invented a class")
            if index not in referenced:
                if index != len(referenced):
                    raise ValueError("source-clipped retention changed first-class order")
                referenced.add(index)
        if len(referenced) != len(self.diagnostics):
            raise ValueError("source-clipped retention has an unreferenced diagnostic")
        for index, diagnostic in enumerate(self.diagnostics):
            if any(diagnostic == prior for prior in self.diagnostics[:index]):
                raise ValueError("source-clipped retention repeats a complete diagnostic")
            if diagnostic.fit.template != self.template or diagnostic.source_domain != self.source_domain:
                raise ValueError("source-clipped retention mixed registered domains")
            if any(self.class_indices[member] is None for member in diagnostic.class_memberships):
                raise ValueError("source-clipped retention lost a represented class")
        values = (
            self.record_scan_count, self.source_role_check_count, self.fact_check_count,
            self.constraint_rank_check_count, self.class_membership_count,
            self.class_comparison_count, self.carry_comparison_count,
            self.deduplication_comparison_count, self.peak_temporary_bytes, self.role_count,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("source-clipped retention receipt is invalid")
        if not self.record_scan_count:
            if self.diagnostics or any(values) or any(index is not None for index in self.class_indices) or self.template is not None or self.source_domain is not None:
                raise ValueError("empty source-clipped retention receipt is invalid")
            return
        if (
            not isinstance(self.template, TemplateSpec)
            or not isinstance(self.source_domain, PhaseSourceDomain)
            or self.role_count != 2 * self.template.count
            or self.source_role_check_count != self.record_scan_count * self.role_count
            or self.fact_check_count > self.record_scan_count * self.role_count
            or self.constraint_rank_check_count > self.record_scan_count
        ):
            raise ValueError("source-clipped retention scan bound is invalid")
        if (
            self.class_membership_count > 2 * self.record_scan_count
            or self.class_membership_count > 2 * self.constraint_rank_check_count
            or self.class_comparison_count > self.class_membership_count
            or self.class_membership_count < sum(index is not None for index in self.class_indices)
            or bool(self.diagnostics) != bool(self.class_membership_count)
            or len(self.diagnostics) > self.constraint_rank_check_count
        ):
            raise ValueError("source-clipped retention membership bound is invalid")
        if self.carry_comparison_count > 6 * (self.record_scan_count - 1):
            raise ValueError("source-clipped retention carry bound is invalid")
        if self.deduplication_comparison_count > 15 * (2 * self.record_scan_count - 1):
            raise ValueError("source-clipped retention deduplication bound is invalid")
        if not _temporary_byte_bound(self.role_count) <= self.peak_temporary_bytes <= _temporary_byte_bound(self.role_count, carry=True):
            raise ValueError("source-clipped retention memory allowance is invalid")


def _deduplicate_classes(
    selected: Sequence[SourceClippedPhaseDiagnostic | None],
) -> tuple[tuple[SourceClippedPhaseDiagnostic, ...], tuple[int | None, ...], int]:
    if len(selected) != SOURCE_CLIPPED_CLASS_COUNT:
        raise ValueError("source-clipped retention requires six representatives")
    diagnostics: list[SourceClippedPhaseDiagnostic] = []
    indices: list[int | None] = []
    comparisons = 0
    for diagnostic in selected:
        if diagnostic is None:
            indices.append(None)
            continue
        for index, existing in enumerate(diagnostics):
            comparisons += 1
            if diagnostic == existing:
                indices.append(index)
                break
        else:
            indices.append(len(diagnostics))
            diagnostics.append(diagnostic)
    return tuple(diagnostics), tuple(indices), comparisons


def select_source_clipped_phase_retention(
    projection_records: Sequence[tuple] | None,
    *,
    source_domain: PhaseSourceDomain | None,
    template: TemplateSpec | None = None,
) -> SourceClippedPhaseRetention:
    """Select fixed clipped-side/rank classes without searching or refitting."""

    from .template_lattice_authority import direct_role_constraint_rank
    from .template_native_retention import _effective_record_fit

    if source_domain is not None and not isinstance(source_domain, PhaseSourceDomain):
        raise TypeError("source-clipped retention source domain is invalid")
    if template is not None and not isinstance(template, TemplateSpec):
        raise TypeError("source-clipped retention template is invalid")
    if source_domain is None or not projection_records:
        return SourceClippedPhaseRetention()
    selected: list[SourceClippedPhaseDiagnostic | None] = [None] * SOURCE_CLIPPED_CLASS_COUNT
    records = source_checks = fact_checks = rank_checks = memberships = comparisons = 0
    expected_template = template
    for record in projection_records:
        if not isinstance(record, tuple) or len(record) != 3:
            raise TypeError("source-clipped record requires input/output/projection")
        candidate = _effective_record_fit(*record)
        fit, projection = candidate.fit, record[2]
        if expected_template is None:
            expected_template = fit.template
        if fit.template != expected_template:
            raise ValueError("source-clipped retention mixed templates")
        roles = len(fit.role_bindings)
        records += 1
        source_checks += roles
        facts = projection.input_direct_role_authority.facts
        if len(facts) > roles:
            raise ValueError("source-clipped authority exceeds role bound")
        fact_checks += len(facts)
        clipped = source_clipped_terminal_roles(fit, source_domain)
        rank = projection.retained_direct_constraint_rank
        if (
            not clipped
            or type(rank) is not int
            or rank not in (1, 2, 3)
            or not _intrinsic_phase_roles(fit, projection)
        ):
            continue
        rank_checks += 1
        if direct_role_constraint_rank(fit, projection.input_direct_role_authority.supported_role_indices) != rank:
            continue
        diagnostic = SourceClippedPhaseDiagnostic(
            fit, projection, candidate.residual_compatible,
            source_domain, clipped, rank,
        )
        for role_class in diagnostic.class_memberships:
            memberships += 1
            previous = selected[role_class]
            if previous is None:
                selected[role_class] = diagnostic
            else:
                comparisons += 1
                if diagnostic.selection_key > previous.selection_key:
                    selected[role_class] = diagnostic
    diagnostics, indices, deduplication = _deduplicate_classes(selected)
    return SourceClippedPhaseRetention(
        diagnostics=diagnostics,
        class_indices=indices,
        record_scan_count=records,
        source_role_check_count=source_checks,
        fact_check_count=fact_checks,
        constraint_rank_check_count=rank_checks,
        class_membership_count=memberships,
        class_comparison_count=comparisons,
        deduplication_comparison_count=deduplication,
        peak_temporary_bytes=_temporary_byte_bound(2 * expected_template.count),
        role_count=2 * expected_template.count,
        template=expected_template,
        source_domain=source_domain,
    )


def carry_source_clipped_phase_retention(
    prior: SourceClippedPhaseRetention | None,
    current: SourceClippedPhaseRetention | None,
    *,
    template: TemplateSpec | None = None,
    registered_direct_observation_ids: tuple[ObservationId, ...] | None = None,
) -> SourceClippedPhaseRetention:
    """Carry only same-template/domain class representatives; prior wins ties."""

    if template is not None and not isinstance(template, TemplateSpec):
        raise TypeError("source-clipped carry template is invalid")
    if registered_direct_observation_ids is not None and (
        len(set(registered_direct_observation_ids)) != len(registered_direct_observation_ids)
        or any(not isinstance(identity, ObservationId) for identity in registered_direct_observation_ids)
    ):
        raise ValueError("source-clipped carry registered observations are invalid")
    retentions = tuple(item for item in (prior, current) if item is not None)
    if any(not isinstance(item, SourceClippedPhaseRetention) for item in retentions):
        raise TypeError("source-clipped carry retention is invalid")
    active = tuple(item for item in retentions if item.record_scan_count)
    if not active:
        return SourceClippedPhaseRetention()
    expected_template = template or active[0].template
    domain = active[0].source_domain
    for retention in active:
        if retention.template != expected_template or retention.source_domain != domain:
            raise ValueError("source-clipped carry mixed registered domains")
        for diagnostic in retention.diagnostics:
            if registered_direct_observation_ids is not None and not set(diagnostic.fit.bound_observation_ids).issubset(registered_direct_observation_ids):
                raise ValueError("source-clipped carry escaped registered observations")
    if len(active) == 1:
        return active[0]
    prior, current = active
    selected, comparisons = [], 0
    for role_class in range(SOURCE_CLIPPED_CLASS_COUNT):
        left_index, right_index = prior.class_indices[role_class], current.class_indices[role_class]
        left = None if left_index is None else prior.diagnostics[left_index]
        right = None if right_index is None else current.diagnostics[right_index]
        representative = left or right
        if left is not None and right is not None:
            comparisons += 1
            if right.selection_key > left.selection_key:
                representative = right
        selected.append(representative)
    diagnostics, indices, deduplication = _deduplicate_classes(selected)
    return SourceClippedPhaseRetention(
        diagnostics=diagnostics, class_indices=indices,
        record_scan_count=sum(item.record_scan_count for item in active),
        source_role_check_count=sum(item.source_role_check_count for item in active),
        fact_check_count=sum(item.fact_check_count for item in active),
        constraint_rank_check_count=sum(item.constraint_rank_check_count for item in active),
        class_membership_count=sum(item.class_membership_count for item in active),
        class_comparison_count=sum(item.class_comparison_count for item in active),
        carry_comparison_count=comparisons + sum(item.carry_comparison_count for item in active),
        deduplication_comparison_count=deduplication + sum(item.deduplication_comparison_count for item in active),
        peak_temporary_bytes=max(_temporary_byte_bound(prior.role_count, carry=True), *(item.peak_temporary_bytes for item in active)),
        role_count=prior.role_count, template=expected_template, source_domain=domain,
    )


# Resolve the model module only after these types exist. This permits either
# module to be the import root while keeping concrete annotations resolvable.
from . import template_phase_model as phase_model
