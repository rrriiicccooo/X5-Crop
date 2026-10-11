"""Bounded retention of existing native terminal-frame phase proposals.

This module is deliberately a consumer of the production phase projection
ledger.  It does not fit, seed, rematch, or query observations.  A projection
record contributes one effective ``_BoundFit``: the existing projected output
when the projection is eligible, otherwise the existing input together with
the failed projection that explains why it stopped.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

from ...domain import ObservationId
from .template_direct_role_authority import DirectRoleAuthorityBasis
from .template_model import TemplateSpec
from .template_phase_candidates import _BoundFit
from .template_phase_model import (
    NativeEndpointPhaseDiagnostic,
    NativeEndpointSelectionBasis,
    NativePhaseRetention,
    PhaseCandidateAuthorityProjection,
)


NativeProjectionRecord: TypeAlias = tuple[
    _BoundFit,
    _BoundFit | None,
    PhaseCandidateAuthorityProjection,
]

_INTRINSIC_BASES = frozenset(
    {
        DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
        DirectRoleAuthorityBasis.AGGREGATE_UNION,
    }
)

# This is a conservative logical allocation bound, not a process-memory
# measurement.  During one diagnostic construction the classifier's fact index
# and the typed diagnostic validator's index can both be live.  The entry
# constants cover the identity tuple, mapping slot, and retained fact/object
# references; the fixed terms cover each index container, at most one retained
# diagnostic, and the four terminal role indices.  ``fact_count <= role_count``
# is checked by the selector, so this remains O(R) without copying fact payloads.
_FACT_INDEX_CONTAINER_BYTES = 256
_FACT_INDEX_ENTRY_BYTES = 128
_VALIDATION_INDEX_CONTAINER_BYTES = 256
_VALIDATION_INDEX_ENTRY_BYTES = 128
_RETAINED_DIAGNOSTIC_BYTES = 1024
_TERMINAL_INDEX_COUNT = 4
_TERMINAL_INDEX_BYTES = 64


def _temporary_byte_bound(role_count: int, fact_count: int) -> int:
    """Return the bounded temporary structure allowance for one record."""

    if fact_count > role_count:
        raise ValueError("native retention fact count exceeds role budget")
    return (
        _FACT_INDEX_CONTAINER_BYTES
        + fact_count * _FACT_INDEX_ENTRY_BYTES
        + _VALIDATION_INDEX_CONTAINER_BYTES
        + fact_count * _VALIDATION_INDEX_ENTRY_BYTES
        + _RETAINED_DIAGNOSTIC_BYTES
        + _TERMINAL_INDEX_COUNT * _TERMINAL_INDEX_BYTES
    )


def _empty_retention() -> NativePhaseRetention:
    """Return the receipt for a legacy pure-unit path with no projections."""

    return NativePhaseRetention()


def _effective_record_fit(
    input_fit: _BoundFit,
    output_fit: _BoundFit | None,
    projection: PhaseCandidateAuthorityProjection,
) -> _BoundFit:
    """Validate one record and select exactly one existing fit from it."""

    if not isinstance(input_fit, _BoundFit):
        raise TypeError("native projection record input is not a bounded fit")
    if output_fit is not None and not isinstance(output_fit, _BoundFit):
        raise TypeError("native projection record output is not a bounded fit")
    if not isinstance(projection, PhaseCandidateAuthorityProjection):
        raise TypeError("native projection record projection is invalid")
    if output_fit is not None and output_fit.fit.template != input_fit.fit.template:
        raise ValueError("native projection record changed template identity")
    if projection.eligible:
        if output_fit is None:
            raise ValueError("eligible native projection lost its output fit")
        return output_fit
    if output_fit is not None:
        raise ValueError("failed native projection carries an output fit")
    return input_fit


def _terminal_diagnostic(
    candidate: _BoundFit,
    projection: PhaseCandidateAuthorityProjection,
) -> tuple[NativeEndpointPhaseDiagnostic | None, int]:
    """Build a diagnostic only when both terminal Frames have intrinsic proof."""

    fit = candidate.fit
    facts = projection.input_direct_role_authority.facts
    if len(facts) > len(fit.role_bindings):
        raise ValueError("native projection authority exceeds fit role bound")
    temporary_bytes = _temporary_byte_bound(
        len(fit.role_bindings),
        len(facts),
    )
    facts_by_identity = {
        (fact.role_index, fact.observation_id): fact
        for fact in facts
    }
    terminal_roles = tuple(fit.template.roles[:2]) + tuple(fit.template.roles[-2:])
    terminal_role_set = {role.role_index for role in terminal_roles}
    qualifying: set[int] = set()
    outer: set[int] = set()
    first_roles = {role.role_index for role in terminal_roles[:2]}
    last_roles = {role.role_index for role in terminal_roles[-2:]}
    for role_index in terminal_role_set:
        binding = fit.role_bindings[role_index]
        if binding is None:
            continue
        fact = facts_by_identity.get((role_index, binding.observation_id))
        if fact is None or not _INTRINSIC_BASES.intersection(fact.bases):
            continue
        qualifying.add(role_index)
        if DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY in fact.bases:
            outer.add(role_index)

    if not qualifying.intersection(first_roles) or not qualifying.intersection(last_roles):
        return None, temporary_bytes
    basis = (
        NativeEndpointSelectionBasis.OUTER_MATERIAL_TERMINAL
        if outer
        else NativeEndpointSelectionBasis.INTRINSIC_TERMINAL
    )
    return (
        NativeEndpointPhaseDiagnostic(
            fit=fit,
            projection=projection,
            residual_compatible=candidate.residual_compatible,
            terminal_role_indices=tuple(sorted(qualifying)),
            selection_basis=basis,
        ),
        temporary_bytes,
    )


def select_native_phase_retention(
    projection_records: Sequence[NativeProjectionRecord] | None,
    *,
    template: TemplateSpec | None = None,
) -> NativePhaseRetention:
    """Select at most one terminal-native diagnostic from existing records.

    Records are scanned once in their existing order.  Equal complete keys
    retain the first record, so no input ordering or authority provenance is
    rewritten by this diagnostic-only pass.
    """

    if projection_records is None or not projection_records:
        return _empty_retention()
    if template is not None and not isinstance(template, TemplateSpec):
        raise TypeError("native retention template is invalid")

    selected: NativeEndpointPhaseDiagnostic | None = None
    record_scan_count = 0
    fact_check_count = 0
    peak_temporary_bytes = 0
    role_count = 0
    expected_template = template

    for raw_record in projection_records:
        record_scan_count += 1
        if not isinstance(raw_record, tuple) or len(raw_record) != 3:
            raise TypeError("native projection record must contain input/output/projection")
        input_fit, output_fit, projection = raw_record
        candidate = _effective_record_fit(input_fit, output_fit, projection)
        if expected_template is None:
            expected_template = candidate.fit.template
        if candidate.fit.template != expected_template:
            raise ValueError("native retention mixed template identities")
        role_count = len(candidate.fit.role_bindings)

        facts = projection.input_direct_role_authority.facts
        fact_check_count += len(facts)
        # The authority ledger is role-indexed and cannot exceed the fixed
        # fit's role budget.  This also makes the receipt's M*R bound explicit.
        if len(facts) > role_count:
            raise ValueError("native retention authority fact count exceeds role budget")
        diagnostic, temporary_bytes = _terminal_diagnostic(candidate, projection)
        peak_temporary_bytes = max(peak_temporary_bytes, temporary_bytes)
        if diagnostic is not None and (
            selected is None or diagnostic.selection_key > selected.selection_key
        ):
            selected = diagnostic

    return NativePhaseRetention(
        diagnostic=selected,
        record_scan_count=record_scan_count,
        fact_check_count=fact_check_count,
        carry_comparison_count=0,
        peak_temporary_bytes=peak_temporary_bytes,
        role_count=role_count,
    )


def _validate_carry_context(
    retentions: tuple[NativePhaseRetention, ...],
    *,
    template: TemplateSpec | None,
    registered_direct_observation_ids: tuple[ObservationId, ...] | None,
) -> TemplateSpec | None:
    """Validate carry context without combining candidate payloads."""

    for retention in retentions:
        if not isinstance(retention, NativePhaseRetention):
            raise TypeError("native carry retention is invalid")
    expected_template = template
    for retention in retentions:
        diagnostic = retention.diagnostic
        if diagnostic is None:
            continue
        if expected_template is None:
            expected_template = diagnostic.fit.template
        if diagnostic.fit.template != expected_template:
            raise ValueError("native carry mixed template identities")
        if registered_direct_observation_ids is not None and not {
            identity
            for identity in diagnostic.fit.binding_observation_ids
            if identity is not None
        }.issubset(registered_direct_observation_ids):
            raise ValueError("native carry escaped registered observations")
    if registered_direct_observation_ids is not None and (
        len(set(registered_direct_observation_ids))
        != len(registered_direct_observation_ids)
        or any(
            not isinstance(identity, ObservationId)
            for identity in registered_direct_observation_ids
        )
    ):
        raise ValueError("native carry registered observations are invalid")
    return expected_template


def carry_native_phase_retention(
    prior: NativePhaseRetention | None,
    current: NativePhaseRetention | None,
    *,
    template: TemplateSpec | None = None,
    registered_direct_observation_ids: tuple[ObservationId, ...] | None = None,
) -> NativePhaseRetention:
    """Carry one complete diagnostic between same-template phase results.

    Only the two supplied diagnostics are compared.  An exact tie retains the
    earlier ``prior`` diagnostic and its complete fit/projection pair.
    """

    retentions = tuple(item for item in (prior, current) if item is not None)
    expected_template = _validate_carry_context(
        retentions,
        template=template,
        registered_direct_observation_ids=registered_direct_observation_ids,
    )
    prior_diagnostic = None if prior is None else prior.diagnostic
    current_diagnostic = None if current is None else current.diagnostic
    selected = prior_diagnostic or current_diagnostic
    comparisons = 0
    if prior_diagnostic is not None and current_diagnostic is not None:
        comparisons = 1
        if current_diagnostic.selection_key > prior_diagnostic.selection_key:
            selected = current_diagnostic

    scan_count = sum(item.record_scan_count for item in retentions)
    fact_count = sum(item.fact_check_count for item in retentions)
    carry_count = sum(item.carry_comparison_count for item in retentions)
    carry_count += comparisons
    peak_bytes = max(
        (item.peak_temporary_bytes for item in retentions),
        default=0,
    )
    role_count = max(
        (item.role_count for item in retentions),
        default=0,
    )
    if selected is not None:
        if expected_template is None:
            expected_template = selected.fit.template
        role_count = len(selected.fit.role_bindings)
    return NativePhaseRetention(
        diagnostic=selected,
        record_scan_count=scan_count,
        fact_check_count=fact_count,
        carry_comparison_count=carry_count,
        peak_temporary_bytes=peak_bytes,
        role_count=role_count,
    )


__all__ = [
    "NativeProjectionRecord",
    "carry_native_phase_retention",
    "select_native_phase_retention",
]
