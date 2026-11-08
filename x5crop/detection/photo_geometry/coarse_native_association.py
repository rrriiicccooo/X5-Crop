"""Link coarse support to independent base lines without a candidate template."""

from .coarse_enclosing_model import CoarseEnclosingMeasurementBasis
from .coarse_native_association_model import (
    CoarseNativeAssociationUnavailable, CoarseNativeAssociationWork, CoarseNativeLineAssociation,
    NativeLineAlternative, OriginalPeakCorrespondence,
)
from .model import BoundaryRole, QueryPurpose
from .template_family_membership import MembershipState
from .template_cross_model import CrossEvidence
from .transition_peak_source import same_transition_peak


def native_line_alternatives(base):
    """Include failed unions and every searched maximal whole-atom union."""
    membership = base.membership_receipt
    if membership is None or membership.state != MembershipState.COMPLETE or any(
            scope.state != MembershipState.COMPLETE for scope in membership.scopes):
        return None
    alternatives = [NativeLineAlternative("observation", str(item.observation_id), item.role,
                        tuple(sorted(item.transition_ids, key=str))) for item in base.observations]
    alternatives.extend(NativeLineAlternative("family", item.family_id, item.role,
                            item.member_transition_ids) for item in base.family_resolutions)
    atoms = {item.observation_id: item.transition_ids for item in base.observations}
    for family in base.family_resolutions:
        for identity, group in zip(family.member_observation_ids, family.member_transition_groups, strict=True):
            if identity in atoms and atoms[identity] != group:
                raise ValueError("native association changed an original family atom")
            atoms[identity] = group
    roles = {item.observation_id: item.role for item in base.observations}
    roles.update((identity, family.role) for family in base.family_resolutions
                 for identity in family.member_observation_ids)
    alternatives.extend(NativeLineAlternative("atom", str(identity), roles[identity],
                            tuple(sorted(group, key=str))) for identity, group in atoms.items())
    for scope in membership.scopes:
        for index, members in enumerate(scope.maximal_member_groups):
            union = tuple(sorted({raw for identity in members for raw in atoms[identity]}, key=str))
            alternatives.append(NativeLineAlternative("membership", f"{scope.parent_family_id}:{index}",
                                                      scope.role, union))
    return tuple(alternatives)


def association_work_bound(measurement_sets, base):
    """Conservative logical visits/storage, using only frozen ledger lengths.

    There are at most two source tracks. Include all source/reference indices,
    full raw unions and maximal membership unions, and the O(N squared) clips
    needed to compile each shared physical region once.
    """
    membership = base.membership_receipt
    points = sum(len(item.transitions) for item in measurement_sets
                 if item.query.purpose in {QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR})
    source_measurements = tuple(item for item in measurement_sets if item.query.purpose in {
        QueryPurpose.COARSE_STRIP_SHORT, QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR})
    groups = sum(len(item.peak_source_groups) for item in source_measurements)
    group_coordinates = sum(sum(len(run) for _, run in group.reliable_gradient_partitions)
                            for item in source_measurements for group in item.peak_source_groups)
    raw = sum(len(item.transition_ids) for item in base.observations)
    raw += sum(len(item.member_transition_ids) + sum(len(group) for group in item.member_transition_groups)
               for item in base.family_resolutions)
    raw += (0 if membership is None else sum(scope.raw_transition_count * len(scope.maximal_member_groups)
                                             for scope in membership.scopes))
    maximum = max((len(item.transition_ids) for item in base.observations), default=0)
    units = points + groups + group_coordinates + raw
    return 4096 + 128 * units + 64 * (maximum + 8) ** 2, 8192 + 256 * units + 2048 * maximum


def associate_coarse_native_lines(coarse_support, measurement_sets, base, *,
                                 maximum_value_visits, maximum_temporary_bytes):
    """At most two original sharp tracks; no fits, pixels or role changes."""
    enclosing = coarse_support.enclosing_support
    if enclosing is None:
        return (), CoarseNativeAssociationWork(0, 0, 0, False)
    visits, temporary = association_work_bound(measurement_sets, base)
    if visits > maximum_value_visits or temporary > maximum_temporary_bytes:
        # The length-only preflight does not retain an authorized prefix.
        return (), CoarseNativeAssociationWork(4096, 0, 4096, True)
    alternatives = native_line_alternatives(base)
    if base.local_refinement_scope_count or base.local_refinement_scopes:
        alternatives = None
    if alternatives is None:
        return (), CoarseNativeAssociationWork(visits, 0, temporary, False)
    measurements = {item.query.purpose: item for item in measurement_sets}
    corridors = tuple(measurements[purpose] for purpose in (QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR))
    if not all(item.coverage.complete for item in corridors):
        return (), CoarseNativeAssociationWork(visits, 0, temporary, False)
    coarse = measurements[QueryPurpose.COARSE_STRIP_SHORT]
    if not coarse.coverage.complete or coarse.coverage.peak_source_bound_exceeded:
        return (), CoarseNativeAssociationWork(visits, 0, temporary, False)
    coarse_groups = {item.primitive_id: item for item in coarse.peak_source_groups}
    observations = {item.observation_id: item for item in base.observations}
    proofs = []
    for track, role, purpose, bindings in (
        (enclosing.minimum_track, BoundaryRole.TOP, QueryPurpose.TOP_CORRIDOR, base.top_bindings),
        (enclosing.maximum_track, BoundaryRole.BOTTOM, QueryPurpose.BOTTOM_CORRIDOR, base.bottom_bindings),
    ):
        if track.measurement_basis != CoarseEnclosingMeasurementBasis.SHARP_TRANSITION or not track.retained_transitions:
            continue
        native = measurements[purpose]
        if not native.coverage.complete or native.coverage.peak_source_bound_exceeded:
            continue
        groups = {item.primitive_id: item for item in native.peak_source_groups}
        # A primitive id includes the full source/kernel/signal/group context.
        # Keep all matches so an ambiguous source reference cannot choose a line.
        by_peak = {}
        for transition in native.transitions:
            reference = transition.peak_source
            if reference is not None:
                by_peak.setdefault((reference.group_id, reference.source_coordinate_px,
                                    reference.candidate_ordinal, reference.polarity), []).append(transition)
        links = []
        for transition in track.retained_transitions:
            reference = transition.peak_source
            if reference is None or reference.group_id not in coarse_groups:
                break
            matches = by_peak.get((reference.group_id, reference.source_coordinate_px,
                                   reference.candidate_ordinal, reference.polarity), ())
            if len(matches) != 1:
                break
            point = matches[0]
            group = groups[point.peak_source.group_id]
            if not same_transition_peak(reference, coarse_groups[reference.group_id], point.peak_source, group):
                break
            links.append(OriginalPeakCorrespondence(transition, point, coarse_groups[reference.group_id], group))
        if len(links) != len(track.retained_transitions):
            continue
        mapped = frozenset(item.native_transition.transition_id for item in links)
        candidates = tuple(binding for binding in bindings if binding.role_authorized
                           and binding.evidence == CrossEvidence.DIRECT
                           and not binding.conditional_family_ids
                           and mapped.issubset(observations[binding.observation_id].transition_ids))
        if len(candidates) != 1:
            continue
        observation = observations[candidates[0].observation_id]
        try:
            traces = frozenset(track.trace_coordinates_px)
            proof = CoarseNativeLineAssociation(track, observation, native.query, tuple(links), alternatives,
                tuple(item.query for item in corridors), tuple(item.coverage for item in corridors),
                tuple(point for item in corridors for point in item.transitions if point.trace_coordinate_px in traces))
            proof.constraint  # Compile its complete region once, before any candidate consumes it.
            proofs.append(proof)
        except CoarseNativeAssociationUnavailable:
            # Missing continuity or a different complete continuation is a real
            # proof gap, not permission to use the partial association.
            continue
    return tuple(proofs), CoarseNativeAssociationWork(visits, temporary if proofs else 0, temporary, False)
