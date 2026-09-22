"""Register the finite template inputs for one already measured lane."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from ...run_local_identity import source_identity_scope
from ...formats import FramePhysicalSpec
from .boundary_fitting import (
    BoundaryFamilyFit,
    complete_boundary_family_proposal,
    fit_boundary_family,
    fit_format_bound_boundary_observation,
)
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import (
    BoundaryAxis,
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
)
from .observation_types import BasicAxisProfile, ProfileRun
from .line_observations import (
    BoundaryFamilyFitReceipt,
    CompleteTransitionLineEvaluation,
    ConstrainedLineFitReceipt,
    PhotoBoundaryObservation,
)
from .robust_line_fit import physical_line_region
from .physical_identity import physical_fact_id, physical_observation_id
from .template_family_membership import (
    MAXIMUM_MEMBERSHIP_VISITS, MembershipAtom, MembershipFitBudget, MembershipProjectionCoverage,
    MembershipReceipt, MembershipState, MembershipTransition, enumerate_membership_scope,
    new_membership_groups,
)
from .source_geometry import SourceScanGeometry
from .template_cross_model import (
    CrossBoundaryFamilyFailureKind,
    CrossBoundaryFamilyResolution,
    CrossBoundaryFamilyUse,
    CrossEvidence,
    CrossRoleBinding,
)
from .template_cross_longitudinal import covers_all_template_domains
from .template_model import (
    PhaseLatticeAuthority,
    TemplateSpec,
    generic_separator_gap_interval_px,
)


def _add(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum + right.minimum,
        left.maximum + right.maximum,
    )

def membership_projection_coverage(
    receipt: MembershipReceipt | None,
    observations: tuple[PhotoBoundaryObservation, ...],
    solver_bindings: tuple[CrossRoleBinding, ...],
) -> tuple[MembershipProjectionCoverage, ...] | None:
    """Account for every searched interpretation without fitting or choosing it.

    COMPLETE is a search/batch receipt. A numerically unavailable union or an
    unsearched scope cannot disappear when output selection consumes it.
    """
    if receipt is None or receipt.state != MembershipState.COMPLETE or any(
        scope.state != MembershipState.COMPLETE for scope in receipt.scopes
    ):
        return None
    by_id = {item.observation_id: item for item in observations}
    represented = {}
    for binding in solver_bindings:
        observation = by_id.get(binding.observation_id)
        if observation is not None and binding.has_independent_spatial_support:
            union = tuple(sorted(observation.transition_ids, key=str))
            represented.setdefault((binding.role, union), []).append(binding.observation_id)
    coverage = []
    for scope in receipt.scopes:
        for members in scope.maximal_member_groups:
            if any(identity not in by_id for identity in members):
                return None
            union = tuple(sorted({raw for identity in members for raw in by_id[identity].transition_ids}, key=str))
            identities = tuple(sorted(represented.get((scope.role, union), ()), key=str))
            if not identities:
                return None
            coverage.append(MembershipProjectionCoverage(scope.parent_family_id, scope.role, members, union, identities))
    return tuple(coverage)


def project_cross_solver_bindings(
    bindings: tuple[CrossRoleBinding, ...],
) -> tuple[CrossRoleBinding, ...]:
    """Project the full ledger to independently supported solver lines.

    One-region fragments remain registered for family proof and diagnostics.
    Background-unknown two-region lines remain inputs: spatial support does
    not grant photo-role authority.
    """

    return tuple(item for item in bindings if item.has_independent_spatial_support)


def validate_cross_line_provenance(
    observations: tuple[PhotoBoundaryObservation, ...],
    bindings: tuple[CrossRoleBinding, ...],
) -> None:
    """A binding must preserve its measured joint region and raw departures."""
    by_id = {binding.observation_id: binding for binding in bindings}
    for observation in observations:
        binding = by_id.get(observation.observation_id)
        if binding is None or any(
            getattr(binding, field) != getattr(observation, field)
            for field in ('physical_line_region', 'trace_coordinates_px', 'trace_position_intervals_px')
        ):
            raise ValueError("Cross binding changed its measured line region or raw support")


def validate_cross_family_provenance(
    families: tuple[CrossBoundaryFamilyResolution, ...],
    observations: dict[ObservationId, tuple[BoundaryRole, tuple[ObservationId, ...]]],
    binding_families: dict[ObservationId, tuple[str, ...]],
) -> None:
    """Bind complete family unions and conditional permission to measured atoms."""

    if len({item.family_id for item in families}) != len(families):
        raise ValueError("cross boundary families must be registered once")
    if len({(item.role, item.use, item.member_observation_ids) for item in families}) != len(families):
        raise ValueError("cross boundary family members were registered twice")
    complete_family_evaluations(families)
    conditional_outputs = {
        identity for family in families
        if family.use == CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL
        for identity in family.final_observation_ids
    }
    known = dict(observations)
    expected: dict[ObservationId, set[str]] = {}
    by_id = {family.family_id: family for family in families}
    for family in families:
        conditional = family.use == CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL
        for parent_id in family.membership_parent_family_ids:
            parent = by_id.get(parent_id)
            if (
                parent is None or parent.membership_parent_family_ids
                or parent.use != CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL
                or parent.state != EvidenceState.UNAVAILABLE or parent.role != family.role
                or not set(family.member_observation_ids).issubset(parent.member_observation_ids)
            ):
                raise ValueError("membership proposal lost its unresolved whole-atom parent")
        if not conditional and family.state == EvidenceState.SUPPORTED and any(
            identity in observations and identity not in family.final_observation_ids
            for identity in family.member_observation_ids
        ):
            raise ValueError("canonical cross family did not consume its members")
        for identity, transitions in zip(
            family.member_observation_ids, family.member_transition_groups,
        ):
            fact = (family.role, transitions)
            if conditional and (
                identity not in observations or identity in conditional_outputs
            ):
                raise ValueError("conditional cross family lost its canonical atom")
            if identity in known and known[identity] != fact:
                raise ValueError("cross family changed a member transition group")
            known[identity] = fact
        for identity in family.final_observation_ids:
            if identity not in observations:
                raise ValueError("cross family lost its final observation")
            if family.state == EvidenceState.SUPPORTED and observations[identity] != (
                family.role, family.member_transition_ids,
            ):
                raise ValueError("cross family discarded a measured transition")
            if conditional:
                expected.setdefault(identity, set()).add(family.family_id)
    if any(
        tuple(sorted(expected.get(identity, ()))) != refs
        for identity, refs in binding_families.items()
    ) or not set(expected).issubset(binding_families):
        raise ValueError("cross binding changed conditional family permission")


def complete_family_evaluations(
    families: tuple[CrossBoundaryFamilyResolution, ...],
) -> tuple[CompleteTransitionLineEvaluation, ...]:
    """Count each evaluated full raw union once across permission records."""
    receipts: dict[tuple[BoundaryRole, tuple[ObservationId, ...]], BoundaryFamilyFitReceipt] = {}
    for family in families:
        key = (family.role, family.member_transition_ids)
        if key in receipts and receipts[key] != family.refit_receipt:
            raise ValueError("cross family changed a cached complete-union evaluation")
        receipts[key] = family.refit_receipt
    return tuple(
        receipt.constrained_evaluation for receipt in receipts.values()
        if receipt.constrained_evaluation is not None
    )


def validate_membership_registration(
    receipt: MembershipReceipt | None, families: tuple[CrossBoundaryFamilyResolution, ...],
    atoms: dict[ObservationId, MembershipAtom], roles: dict[ObservationId, BoundaryRole],
    run_counts: dict[BoundaryRole, int],
    refinement_observation_ids: frozenset[ObservationId],
    fit_attempt_count: int,
) -> None:
    """Bind the frozen search universe, all interpretations and preflight counts."""
    added = tuple(family for family in families if family.membership_parent_family_ids)
    if receipt is None:
        if added:
            raise ValueError("membership families require their complete search receipt")
        return
    original = tuple(family for family in families if not family.membership_parent_family_ids)
    frozen = set(receipt.original_observation_ids)
    outputs = {identity for family in added for identity in family.final_observation_ids}
    if frozen != set(atoms) - outputs - refinement_observation_ids:
        raise ValueError("membership search changed its frozen observations")
    original_fit_count = sum(run_counts.values()) + len({
        (family.role, family.member_transition_ids) for family in original})
    membership_fit_count = len({(family.role, family.member_transition_ids) for family in added})
    refinement_fit_count = fit_attempt_count - original_fit_count - membership_fit_count
    if not len(refinement_observation_ids) <= refinement_fit_count <= sum(run_counts.values()):
        raise ValueError("membership phase provenance disagrees with actual refinement work")
    parents = {family.family_id: family for family in original
               if family.use == CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL and family.state == EvidenceState.UNAVAILABLE}
    if set(parents) != {scope.parent_family_id for scope in receipt.scopes}:
        raise ValueError("membership search omitted an unresolved family")
    for scope in receipt.scopes:
        parent = parents[scope.parent_family_id]
        anchors = tuple(key for key in parent.member_observation_ids
                        if atoms[key].independent_support_region_count >= MINIMUM_INDEPENDENT_SUPPORT_REGIONS)
        if (
            scope.role != parent.role or scope.atom_count != len(parent.member_observation_ids)
            or not set(parent.member_observation_ids).issubset(frozen)
            or scope.anchor_observation_ids != anchors
            or scope.raw_transition_count != len(parent.member_transition_ids)
            or any(not set(group).issubset(parent.member_observation_ids) for group in scope.maximal_member_groups)
        ):
            raise ValueError("membership scope changed its indivisible measured atoms")
    if receipt.state == MembershipState.SEARCH_BOUND_EXCEEDED:
        if added:
            raise ValueError("incomplete membership enumeration emitted a proposal prefix")
        return
    existing = {(roles[key], atoms[key].transition_ids) for key in frozen}
    existing.update((family.role, family.member_transition_ids) for family in original)
    groups = new_membership_groups(receipt.scopes, atoms, existing)
    unions = {(role, union) for role, _members, union in groups}
    expected_budgets = []
    for role in (BoundaryRole.TOP, BoundaryRole.BOTTOM):
        old = {family.member_transition_ids: family for family in original if family.role == role}
        expected_budgets.append(MembershipFitBudget(
            role, run_counts[role], len(old),
            sum(family.refit_receipt.constrained_evaluation is not None for family in old.values()),
            sum(union_role == role for union_role, _union in unions)))
    if tuple(expected_budgets) != receipt.fit_budgets:
        raise ValueError("membership fit preflight changed original or proposed work")
    expected = groups if receipt.state == MembershipState.COMPLETE else {}
    actual = {(family.role, family.member_observation_ids, family.member_transition_ids): family.membership_parent_family_ids
              for family in added}
    if len(actual) != len(added) or actual != expected:
        raise ValueError("membership result lost a complete interpretation or emitted a withheld batch")


@dataclass(frozen=True)
class CrossRegistrationWorkReceipt:
    fit_attempt_count: int
    raw_observation_count: int
    local_fragment_count: int
    family_compatibility_evaluation_count: int = 0
    constrained_fit_attempt_count: int = 0
    constrained_fit_edge_count: int = 0
    constrained_fit_event_count: int = 0
    membership: MembershipReceipt | None = None
    local_refinement_scope_count: int = 0

    def __post_init__(self) -> None:
        if (
            any(type(value) is not int for value in (
                self.fit_attempt_count, self.raw_observation_count, self.local_fragment_count,
                self.family_compatibility_evaluation_count,
                self.constrained_fit_attempt_count, self.constrained_fit_edge_count,
                self.constrained_fit_event_count,
                self.local_refinement_scope_count,
            ))
            or not 0 <= self.local_fragment_count <= self.raw_observation_count <= self.fit_attempt_count
            or self.family_compatibility_evaluation_count < 0
            or not 0 <= self.constrained_fit_attempt_count <= self.fit_attempt_count
            or self.constrained_fit_edge_count < 0
            or self.constrained_fit_event_count < 0
            or self.local_refinement_scope_count < 0
            or (self.constrained_fit_attempt_count == 0 and (
                self.constrained_fit_edge_count or self.constrained_fit_event_count
            ))
        ):
            raise ValueError("cross registration work receipt is invalid")
        if self.membership is not None and not isinstance(self.membership, MembershipReceipt):
            raise TypeError("cross registration requires typed membership work")


def template_spec_from_physical_authority(
    *,
    frame_spec: FramePhysicalSpec,
    source_geometry: SourceScanGeometry,
    width_scale_px_per_mm: PositiveInterval,
    count: int,
    phase_lattice_authority: PhaseLatticeAuthority,
    template_id: str | None = None,
) -> TemplateSpec:
    """Scale the user's fixed format once; observations only refine it."""

    width = source_geometry.width_state.extent_projection_px()
    height = source_geometry.height_state.extent_projection_px()
    calibrated_scale = source_geometry.width_state.feasible_scale_interval()
    if frame_spec.format_gap_prior_mm is None:
        gap = generic_separator_gap_interval_px(width)
    else:
        gap = FiniteInterval(
            frame_spec.format_gap_prior_mm * calibrated_scale.minimum,
            frame_spec.format_gap_prior_mm * calibrated_scale.maximum,
        )
    return TemplateSpec(
        template_id=(
            template_id
            or f"template:{frame_spec.frame_spec_id}:direct:{count}"
        ),
        frame_width_px=width,
        frame_height_px=height,
        pitch_px=_add(width, gap),
        nominal_gap_px=gap,
        count=count,
        phase_lattice_authority=phase_lattice_authority.with_period(
            _add(width, gap)
        ),
    )


@dataclass(frozen=True)
class RegisteredCrossEvidence:
    top_bindings: tuple[CrossRoleBinding, ...]
    bottom_bindings: tuple[CrossRoleBinding, ...]
    observations: tuple[PhotoBoundaryObservation, ...]
    fit_attempt_count: int
    registered_top_run_count: int | None = None
    registered_bottom_run_count: int | None = None
    family_resolutions: tuple[CrossBoundaryFamilyResolution, ...] = ()
    family_compatibility_evaluation_count: int = 0
    membership_receipt: MembershipReceipt | None = None
    local_refinement_scope_count: int = 0

    @property
    def work_receipt(self) -> CrossRegistrationWorkReceipt:
        evaluations = complete_family_evaluations(self.family_resolutions)
        return CrossRegistrationWorkReceipt(
            fit_attempt_count=self.fit_attempt_count,
            raw_observation_count=len(self.observations),
            local_fragment_count=sum(
                item.independent_support_region_count < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
                for item in self.observations
            ),
            family_compatibility_evaluation_count=(
                self.family_compatibility_evaluation_count
            ),
            constrained_fit_attempt_count=len(evaluations),
            constrained_fit_edge_count=sum(item.work.edge_count for item in evaluations),
            constrained_fit_event_count=sum(item.work.event_count for item in evaluations),
            membership=self.membership_receipt,
            local_refinement_scope_count=self.local_refinement_scope_count,
        )

    def __post_init__(self) -> None:
        identities = tuple(item.observation_id for item in self.observations)
        if len(set(identities)) != len(identities):
            raise ValueError("cross observations must be registered once")
        validate_cross_line_provenance(self.observations, (*self.top_bindings, *self.bottom_bindings))
        family_ids = tuple(item.family_id for item in self.family_resolutions)
        if len(set(family_ids)) != len(family_ids):
            raise ValueError("cross boundary families must be registered once")
        validate_cross_family_provenance(
            self.family_resolutions,
            {item.observation_id: (item.role, item.transition_ids) for item in self.observations},
            {item.observation_id: item.conditional_family_ids
             for item in (*self.top_bindings, *self.bottom_bindings)},
        )
        if self.fit_attempt_count < len(self.observations):
            raise ValueError("cross fit-attempt receipt is incomplete")
        binding_top_run_count = len(
            {item.run_id for item in self.top_bindings if not item.conditional_family_ids}
        )
        binding_bottom_run_count = len(
            {item.run_id for item in self.bottom_bindings if not item.conditional_family_ids}
        )
        registered_top_run_count = (
            binding_top_run_count
            if self.registered_top_run_count is None
            else self.registered_top_run_count
        )
        registered_bottom_run_count = (
            binding_bottom_run_count
            if self.registered_bottom_run_count is None
            else self.registered_bottom_run_count
        )
        if (
            not isinstance(registered_top_run_count, int)
            or registered_top_run_count < 0
            or not isinstance(registered_bottom_run_count, int)
            or registered_bottom_run_count < 0
            or type(self.family_compatibility_evaluation_count) is not int
            or type(self.local_refinement_scope_count) is not int
            or self.local_refinement_scope_count < 0
            or not 0 <= self.family_compatibility_evaluation_count <= sum(
                2 * count * (count + 1)
                for count in (registered_top_run_count, registered_bottom_run_count)
            )
            or any(
                len(complete_family_evaluations(tuple(
                    family for family in self.family_resolutions if family.role == role
                ))) > 2 * count
                for role, count in (
                    (BoundaryRole.TOP, registered_top_run_count),
                    (BoundaryRole.BOTTOM, registered_bottom_run_count),
                )
            )
        ):
            raise ValueError("cross registration receipt is invalid")
        object.__setattr__(
            self,
            "registered_top_run_count",
            registered_top_run_count,
        )
        object.__setattr__(
            self,
            "registered_bottom_run_count",
            registered_bottom_run_count,
        )
        validate_membership_registration(
            self.membership_receipt, self.family_resolutions,
            {item.observation_id: MembershipAtom(item.observation_id, item.transition_ids,
                                               item.independent_support_region_count) for item in self.observations},
            {item.observation_id: item.role for item in self.observations},
            {BoundaryRole.TOP: registered_top_run_count, BoundaryRole.BOTTOM: registered_bottom_run_count},
            frozenset(binding.observation_id for binding in (*self.top_bindings, *self.bottom_bindings)
                      if binding.evidence == CrossEvidence.TEMPLATE_LOCAL_REFINEMENT),
            self.fit_attempt_count,
        )


def _interval_distance(
    left: FiniteInterval,
    right: FiniteInterval,
) -> tuple[float, float]:
    """Return minimum and maximum separation of two physical intervals."""

    minimum = max(
        left.minimum - right.maximum,
        right.minimum - left.maximum,
        0.0,
    )
    maximum = max(
        abs(left.minimum - right.maximum),
        abs(left.maximum - right.minimum),
    )
    return minimum, maximum


def _project_cross_anchor(
    binding: CrossRoleBinding,
    *,
    trace_coordinate_px: int,
    lane_reference_trace_px: float,
    canonical_height_px: float,
) -> FiniteInterval:
    """Project one direct side to the expected opposite-side corridor."""

    direction = binding.full_direction_interval_degrees
    if direction is None:
        raise ValueError("cross refinement anchor needs direct direction")
    delta_trace = float(trace_coordinate_px) - lane_reference_trace_px
    slopes = tuple(
        math.tan(math.radians(value))
        for value in (direction.minimum, direction.maximum)
    )
    projected = tuple(
        coordinate + slope * delta_trace
        for coordinate in (
            binding.full_interval_px.minimum,
            binding.full_interval_px.maximum,
        )
        for slope in slopes
    )
    advance = (
        canonical_height_px
        if binding.role == BoundaryRole.TOP
        else -canonical_height_px
    )
    return FiniteInterval(min(projected) + advance, max(projected) + advance)


def _canonical_cross_run(
    observation: PhotoBoundaryObservation,
    measurement: PhotoBoundaryMeasurementSet,
) -> ProfileRun:
    transition_by_id = {
        transition.transition_id: transition
        for transition in measurement.transitions
    }
    transitions = tuple(
        transition_by_id[identity] for identity in observation.transition_ids
    )
    traces = tuple(sorted({item.trace_coordinate_px for item in transitions}))
    queried = measurement.query.trace_positions_px
    return ProfileRun(
        run_id=physical_fact_id(
            ("constrained-cross-run" if isinstance(observation.fit_receipt, ConstrainedLineFitReceipt)
             else "registered-cross-run"),
            observation.role.value,
            observation.observation_id,
        ),
        coordinate_interval_px=observation.offset_interval_px,
        transition_ids=observation.transition_ids,
        trace_coordinates_px=traces,
        role_hint=observation.role,
        qualified_anchor_roles=(observation.role,),
        support_fraction=len(traces) / len(queried),
        continuous_support_fraction=observation.continuous_support_fraction,
        fit_residual_px=observation.fit_residual_px,
        evidence_strength=sum(
            item.gradient_z + max(item.tone_z, item.texture_z)
            for item in transitions
        )
        / len(transitions),
        pair_qualified=True,
    )


def _cross_family_projection_interval(
    observation: PhotoBoundaryObservation,
    *,
    reference_trace_px: float,
    boundary_axis: BoundaryAxis,
    connection_allowance_px: float,
) -> FiniteInterval:
    """Project one local line's full measured direction at one shared trace."""

    line = observation.line
    anchor_trace_px = line.support_projection_px.center
    if boundary_axis == BoundaryAxis.Y:
        normal = line.normal_y
        other = line.normal_x
    else:
        normal = line.normal_x
        other = line.normal_y
    if abs(normal) <= 1.0e-12:
        raise ValueError("cross family line cannot project at shared trace")
    anchor_coordinates = tuple(
        (offset - other * anchor_trace_px) / normal
        for offset in (
            observation.offset_interval_px.minimum,
            observation.offset_interval_px.maximum,
        )
    )
    delta_trace_px = reference_trace_px - anchor_trace_px
    slopes = tuple(
        math.tan(math.radians(angle))
        for angle in (
            observation.angle_interval_degrees.minimum,
            observation.angle_interval_degrees.maximum,
        )
    )
    projected = tuple(
        coordinate + slope * delta_trace_px
        for coordinate in anchor_coordinates
        for slope in slopes
    )
    return FiniteInterval(
        min(projected) - connection_allowance_px,
        max(projected) + connection_allowance_px,
    )


def _cross_family_components(
    values: tuple[PhotoBoundaryObservation, ...],
    *,
    measurement: PhotoBoundaryMeasurementSet,
    height_scale_px_per_mm: PositiveInterval,
) -> tuple[tuple[int, ...], ...]:
    """Group only position- and direction-compatible local line fragments."""

    if not values:
        return ()
    reference_trace_px = (
        measurement.query.trace_positions_px[0]
        + measurement.query.trace_positions_px[-1]
    ) / 2.0
    allowance_px = PHOTO_BOUNDARY_MEASUREMENT_SPEC.line_connection_allowance_px(
        height_scale_px_per_mm.maximum
    )
    projections = tuple(
        _cross_family_projection_interval(
            observation,
            reference_trace_px=reference_trace_px,
            boundary_axis=measurement.query.boundary_axis,
            connection_allowance_px=allowance_px,
        )
        for observation in values
    )
    ordered = tuple(
        sorted(
            range(len(values)),
            key=lambda index: (
                projections[index].minimum,
                projections[index].maximum,
                str(values[index].observation_id),
            ),
        )
    )
    links: dict[int, set[int]] = {index: set() for index in ordered}
    active: list[int] = []
    for index in ordered:
        interval = projections[index]
        active = [
            candidate
            for candidate in active
            if projections[candidate].maximum >= interval.minimum
        ]
        for candidate in active:
            other_direction = values[candidate].angle_interval_degrees
            direction = values[index].angle_interval_degrees
            if (
                other_direction.maximum < direction.minimum
                or direction.maximum < other_direction.minimum
            ):
                continue
            links[index].add(candidate)
            links[candidate].add(index)
        active.append(index)

    components: list[tuple[int, ...]] = []
    remaining = set(ordered)
    while remaining:
        frontier = [min(remaining)]
        component: set[int] = set()
        while frontier:
            member = frontier.pop()
            if member in component:
                continue
            component.add(member)
            frontier.extend(links[member].intersection(remaining))
        remaining.difference_update(component)
        components.append(tuple(sorted(component)))
    return tuple(components)


def _partition_cross_families(
    values: tuple[PhotoBoundaryObservation, ...],
    components: tuple[tuple[int, ...], ...],
    *,
    measurement: PhotoBoundaryMeasurementSet,
    height_scale_px_per_mm: PositiveInterval,
    use: CrossBoundaryFamilyUse = CrossBoundaryFamilyUse.CANONICAL_REGISTRATION,
) -> tuple[tuple[tuple[int, ...], ...], int]:
    """Separate incompatible physical tracks before complete-union refitting.

    A successful old union fit is a witness for the first feasibility check,
    so an already coherent family is never split. In an inconsistent broad
    component, a local fragment can join only one independently measured line
    group. Ambiguous fragments remain in their own complete ledger. No fit
    residual, role preference or favorable subset selects family members.
    """
    by_id = {item.transition_id: item for item in measurement.transitions}
    conditional = use == CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL
    reference = (
        measurement.query.trace_positions_px[0]
        + measurement.query.trace_positions_px[-1]
    ) / 2.0
    # Match the original fitter's admitted bend and angular arithmetic error.
    allowance = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.inlier_minimum_threshold_mm
        * height_scale_px_per_mm.maximum
    )
    maximum_slope = math.tan(math.radians(
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_measurable_line_angle_degrees
        + 1.0e-9
    ))
    cache: dict[tuple[int, ...], bool] = {}

    def compatible(members: tuple[int, ...]) -> bool:
        key = tuple(sorted(members))
        if key not in cache:
            identities = tuple(sorted({
                identity for index in members for identity in values[index].transition_ids
            }, key=str))
            if conditional and len({by_id[identity].trace_coordinate_px for identity in identities}) != len(identities):
                cache[key] = False
                return False
            intervals = tuple(
                (float(by_id[identity].trace_coordinate_px), FiniteInterval(
                    by_id[identity].physical_position_interval_px.minimum - allowance,
                    by_id[identity].physical_position_interval_px.maximum + allowance,
                ))
                for identity in identities
            )
            cache[key] = physical_line_region(intervals, maximum_slope, reference) is not None
        return cache[key]

    result: list[tuple[int, ...]] = []
    for component in components:
        if len(component) == 1 or compatible(component):
            result.append(component)
            continue
        anchors = tuple(index for index in component if (
            values[index].independent_support_region_count >= MINIMUM_INDEPENDENT_SUPPORT_REGIONS
        ))
        if not anchors:
            result.append(component)
            continue
        links = {index: set() for index in anchors}
        for offset, left in enumerate(anchors):
            for right in anchors[offset + 1:]:
                if compatible((left, right)):
                    links[left].add(right)
                    links[right].add(left)
        groups: list[tuple[int, ...]] = []
        remaining = set(anchors)
        while remaining:
            pending = [min(remaining)]
            members: set[int] = set()
            while pending:
                index = pending.pop()
                if index not in members:
                    members.add(index)
                    pending.extend(links[index] - members)
            remaining.difference_update(members)
            group = tuple(sorted(members))
            # Pairwise compatibility is not transitive. A connected anchor
            # group must also have a common line; otherwise keep each anchor.
            groups.extend((group,) if compatible(group) else ((index,) for index in group))
        assigned = [list(group) for group in groups]
        residual = []
        for fragment in component:
            if fragment in anchors:
                continue
            matches = [index for index, group in enumerate(groups)
                       if compatible((*group, fragment))]
            if conditional:
                for match in matches:
                    assigned[match].append(fragment)
            elif len(matches) == 1:
                assigned[matches[0]].append(fragment)
            else:
                residual.append(fragment)
        result.extend(tuple(sorted(group)) for group in assigned)
        if residual and not conditional:
            result.append(tuple(residual))
    if len(cache) > len(values) * (len(values) + 1):
        raise AssertionError("cross family compatibility exceeded its quadratic bound")
    if not conditional and sorted(index for group in result for index in group) != list(range(len(values))):
        raise AssertionError("cross family partition lost or duplicated an observation")
    return tuple(result), len(cache)


def _merge_registered_cross_families(
    values: tuple[PhotoBoundaryObservation, ...],
    *,
    measurement: PhotoBoundaryMeasurementSet,
    role: BoundaryRole,
    width_axis: BoundaryAxis,
    height_scale_px_per_mm: PositiveInterval,
) -> tuple[
    tuple[PhotoBoundaryObservation, ...],
    int,
    tuple[CrossBoundaryFamilyResolution, ...],
    int,
]:
    """Merge only a complete transition union that refits as one line.

    Transition tracking deliberately emits local segments.  Their raster
    support need not be connected: the family owner proves physical identity
    by requiring one robust refit to retain the exact transition union.  A
    refit that discards even one member transition is not identity evidence.
    """

    if len(values) < 2:
        return values, 0, (), 0
    fit_cache: dict[tuple[str, ...], BoundaryFamilyFit] = {}
    attempts = 0

    def fit(members: tuple[PhotoBoundaryObservation, ...]) -> BoundaryFamilyFit:
        nonlocal attempts
        identities = tuple(
            sorted(
                {
                    identity
                    for member in members
                    for identity in member.transition_ids
                },
                key=str,
            )
        )
        key = tuple(map(str, identities))
        if key not in fit_cache:
            attempts += 1
            fit_cache[key] = fit_boundary_family(
                measurement,
                transition_ids=identities,
                role=role,
                source_axis_long=width_axis,
                boundary_axis_scale_px_per_mm=height_scale_px_per_mm,
            )
        return fit_cache[key]

    merged: list[PhotoBoundaryObservation] = []
    resolutions: list[CrossBoundaryFamilyResolution] = []
    compatibility_count = 0
    for use in (
        CrossBoundaryFamilyUse.CANONICAL_REGISTRATION,
        CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL,
    ):
        conditional = use == CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL
        # Existing complete families are indivisible measured inputs. New
        # interpretations add proposals; they never repartition those facts.
        inputs = tuple(merged) if conditional else values
        existing_unions = {item.transition_ids for item in inputs}
        components = _cross_family_components(
            inputs, measurement=measurement,
            height_scale_px_per_mm=height_scale_px_per_mm,
        )
        groups, count = _partition_cross_families(
            inputs, components, measurement=measurement,
            height_scale_px_per_mm=height_scale_px_per_mm, use=use,
        )
        compatibility_count += count
        for group in groups:
            if len(group) == 1:
                if not conditional:
                    merged.append(inputs[group[0]])
                continue
            members = tuple(sorted(
                (inputs[index] for index in group),
                key=lambda item: str(item.observation_id),
            ))
            member_observation_ids = tuple(item.observation_id for item in members)
            member_transition_ids = tuple(sorted({
                identity for item in members for identity in item.transition_ids
            }, key=str))
            if conditional and (
                member_transition_ids in existing_unions
                or tuple(map(str, member_transition_ids)) in fit_cache
            ):
                continue
            family_id = physical_fact_id(
                "cross-boundary-family", role.value, use.value,
                *(str(identity) for identity in member_observation_ids),
            )
            evaluation = fit(members)
            observation = evaluation.canonical_observation
            if observation is not None:
                merged.append(observation)
            elif not conditional:
                merged.extend(members)
            resolutions.append(
                CrossBoundaryFamilyResolution(
                    family_id=family_id,
                    role=role,
                    use=use,
                    state=(EvidenceState.SUPPORTED if observation is not None else EvidenceState.UNAVAILABLE),
                    member_observation_ids=member_observation_ids,
                    member_transition_ids=member_transition_ids,
                    member_transition_groups=tuple(item.transition_ids for item in members),
                    refit_receipt=evaluation.receipt,
                    final_observation_ids=(
                        (observation.observation_id,) if observation is not None
                        else () if conditional else member_observation_ids
                    ),
                    failure_kind=(None if observation is not None else
                        CrossBoundaryFamilyFailureKind.COMPLETE_TRANSITION_UNION_REFIT_REJECTED),
                )
            )
    # Freeze both original registration passes before producing a constrained
    # estimate. New observation identities cannot enter canonical grouping or
    # change the order in which any original observation is materialized.
    conditional_results: dict[
        tuple[str, ...], tuple[PhotoBoundaryObservation | None, BoundaryFamilyFitReceipt]
    ] = {}
    additional_observations: dict[ObservationId, PhotoBoundaryObservation] = {}
    original_ids = {item.observation_id for item in merged}
    final_resolutions: list[CrossBoundaryFamilyResolution] = []
    for family in resolutions:
        if family.state == EvidenceState.SUPPORTED:
            final_resolutions.append(family)
            continue
        key = tuple(map(str, family.member_transition_ids))
        if key not in conditional_results:
            conditional_results[key] = complete_boundary_family_proposal(fit_cache[key])
        proposal, refit_receipt = conditional_results[key]
        if proposal is None:
            final_resolutions.append(replace(family, refit_receipt=refit_receipt))
            continue
        if proposal.observation_id in original_ids:
            raise ValueError("conditional refit changed an existing observation's permission")
        additional_observations[proposal.observation_id] = proposal
        conditional = family.use == CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL
        if not conditional:
            final_resolutions.append(replace(family, refit_receipt=refit_receipt))
        final_resolutions.append(replace(
            family,
            refit_receipt=refit_receipt,
            family_id=(family.family_id if conditional else physical_fact_id(
                "constrained-cross-family", role.value,
                CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL.value,
                *(str(identity) for identity in family.member_observation_ids),
            )),
            use=CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL,
            state=EvidenceState.SUPPORTED,
            final_observation_ids=(proposal.observation_id,),
            failure_kind=None,
        ))
    merged.extend(additional_observations.values())
    return tuple(merged), attempts, tuple(final_resolutions), compatibility_count


def _register_membership_proposals(
    registered: RegisteredCrossEvidence, *,
    top_measurement: PhotoBoundaryMeasurementSet, bottom_measurement: PhotoBoundaryMeasurementSet,
    width_axis: BoundaryAxis, height_axis: BoundaryAxis,
    height_scale_px_per_mm: PositiveInterval, lane_reference_trace_px: float,
) -> RegisteredCrossEvidence:
    """Add the complete finite interpretation batch after canonical identity freezes."""
    observations = {item.observation_id: item for item in registered.observations}
    atoms = {key: MembershipAtom(key, item.transition_ids, item.independent_support_region_count)
             for key, item in observations.items()}
    measurements = {BoundaryRole.TOP: top_measurement, BoundaryRole.BOTTOM: bottom_measurement}
    raw = {role: tuple(MembershipTransition(point.transition_id, float(point.trace_coordinate_px),
                                          point.physical_position_interval_px)
                       for point in measurement.transitions)
           for role, measurement in measurements.items()}
    scopes = []
    remaining = MAXIMUM_MEMBERSHIP_VISITS
    frozen_ids = tuple(sorted(observations, key=str))
    for family in registered.family_resolutions:
        if family.use != CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL or family.state != EvidenceState.UNAVAILABLE:
            continue
        scope = enumerate_membership_scope(
            parent_family_id=family.family_id, role=family.role,
            atoms=tuple(atoms[key] for key in family.member_observation_ids),
            transitions=raw[family.role],
            query_trace_positions_px=measurements[family.role].query.trace_positions_px,
            scale_px_per_mm=height_scale_px_per_mm.maximum, remaining_visits=remaining,
        )
        scopes.append(scope)
        remaining -= scope.work.visited_count
    scope_records = tuple(scopes)
    if any(scope.state == MembershipState.SEARCH_BOUND_EXCEEDED for scope in scopes):
        return replace(registered, membership_receipt=MembershipReceipt(
            MembershipState.SEARCH_BOUND_EXCEEDED, scope_records, (), frozen_ids))
    existing = {(item.role, item.transition_ids) for item in registered.observations}
    existing.update((family.role, family.member_transition_ids) for family in registered.family_resolutions)
    groups = new_membership_groups(scope_records, atoms, existing)
    new_unions = {(role, union) for role, _members, union in groups}
    budgets = []
    for role, count in ((BoundaryRole.TOP, registered.registered_top_run_count),
                        (BoundaryRole.BOTTOM, registered.registered_bottom_run_count)):
        original = {family.member_transition_ids: family for family in registered.family_resolutions if family.role == role}
        budgets.append(MembershipFitBudget(
            role, count, len(original),
            sum(family.refit_receipt.constrained_evaluation is not None for family in original.values()),
            sum(union_role == role for union_role, _union in new_unions),
        ))
    if registered.fit_attempt_count != sum(item.registered_run_count + item.original_family_fit_count for item in budgets):
        raise ValueError("membership preflight lost original fit attempts")
    admitted = all(item.admits_all for item in budgets)
    receipt = MembershipReceipt(MembershipState.COMPLETE if admitted else MembershipState.FIT_BOUND_EXCEEDED,
                                scope_records, tuple(budgets), frozen_ids)
    if not admitted:
        return replace(registered, membership_receipt=receipt)
    cache = {}
    families = list(registered.family_resolutions)
    bindings = list((*registered.top_bindings, *registered.bottom_bindings))
    binding_parents: dict[ObservationId, set[str]] = {}
    for (role, members, union), parents in groups.items():
        key = (role, union)
        if key not in cache:
            # Numerical materialization must not consume original line/run
            # ordinals used by later canonical refinement and sorting.
            with source_identity_scope():
                fitted = fit_boundary_family(measurements[role], transition_ids=union, role=role,
                                             source_axis_long=width_axis,
                                             boundary_axis_scale_px_per_mm=height_scale_px_per_mm)
                proposal, numerical = fitted.canonical_observation, fitted.receipt
                if proposal is None:
                    proposal, numerical = complete_boundary_family_proposal(fitted)
                run = None if proposal is None else _canonical_cross_run(proposal, measurements[role])
            if proposal is not None:
                identity = physical_observation_id("membership-proposal-line", role.value, *union)
                proposal = replace(proposal, observation_id=identity)
                run = replace(run, run_id=physical_fact_id("membership-proposal-run", role.value, identity))
                observations[identity] = proposal
                bindings.append(CrossRoleBinding.from_measurement(
                    run, proposal, lane_reference_trace_px=lane_reference_trace_px, boundary_axis=height_axis))
            cache[key] = proposal, numerical
        proposal, numerical = cache[key]
        family_id = physical_fact_id("membership-proposal-family", role.value, *members)
        families.append(CrossBoundaryFamilyResolution(
            family_id=family_id, role=role, use=CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL,
            state=EvidenceState.SUPPORTED if proposal is not None else EvidenceState.UNAVAILABLE,
            member_observation_ids=members, member_transition_ids=union,
            member_transition_groups=tuple(atoms[member].transition_ids for member in members),
            final_observation_ids=() if proposal is None else (proposal.observation_id,),
            failure_kind=None if proposal is not None else CrossBoundaryFamilyFailureKind.COMPLETE_TRANSITION_UNION_REFIT_REJECTED,
            refit_receipt=numerical, membership_parent_family_ids=parents,
        ))
        if proposal is not None:
            binding_parents.setdefault(proposal.observation_id, set()).add(family_id)
    bindings = [replace(binding, conditional_family_ids=tuple(sorted(binding_parents[binding.observation_id])))
                if binding.observation_id in binding_parents else binding for binding in bindings]
    return replace(registered,
                   top_bindings=tuple(binding for binding in bindings if binding.role == BoundaryRole.TOP),
                   bottom_bindings=tuple(binding for binding in bindings if binding.role == BoundaryRole.BOTTOM),
                   observations=tuple(observations.values()), family_resolutions=tuple(families),
                   fit_attempt_count=registered.fit_attempt_count + len(cache), membership_receipt=receipt)


def register_cross_evidence(
    *,
    profile: BasicAxisProfile,
    top_measurement: PhotoBoundaryMeasurementSet,
    bottom_measurement: PhotoBoundaryMeasurementSet,
    width_axis: BoundaryAxis,
    height_axis: BoundaryAxis,
    height_scale_px_per_mm: PositiveInterval,
    lane_reference_trace_px: float,
    maximum_runs_per_role: int = 256,
) -> RegisteredCrossEvidence:
    """Fit every registered top/bottom run once, without placement queries."""

    if maximum_runs_per_role <= 0:
        raise ValueError("cross registration bound must be positive")
    qualified = tuple(
        run
        for run in profile.runs
        if run.role_hint in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        and (run.pair_qualified or run.anchor_qualified_for(run.role_hint))
    )
    qualified_top = tuple(
        run for run in qualified if run.role_hint == BoundaryRole.TOP
    )
    qualified_bottom = tuple(
        run for run in qualified if run.role_hint == BoundaryRole.BOTTOM
    )
    if (
        len(qualified_top) > maximum_runs_per_role
        or len(qualified_bottom) > maximum_runs_per_role
    ):
        return RegisteredCrossEvidence(
            top_bindings=(),
            bottom_bindings=(),
            observations=(),
            fit_attempt_count=0,
            registered_top_run_count=len(qualified_top),
            registered_bottom_run_count=len(qualified_bottom),
        )
    observations_by_role: dict[BoundaryRole, dict[str, PhotoBoundaryObservation]] = {
        BoundaryRole.TOP: {},
        BoundaryRole.BOTTOM: {},
    }
    fit_attempt_count = 0
    for run in qualified:
        measurement = (
            top_measurement
            if run.role_hint == BoundaryRole.TOP
            else bottom_measurement
        )
        observation = fit_format_bound_boundary_observation(
            measurement,
            transition_ids=run.transition_ids,
            role=run.role_hint,
            source_axis_long=width_axis,
            boundary_axis_scale_px_per_mm=height_scale_px_per_mm,
            # A local line is measurement, not template-wide authority.
            # Family refitting must receive these fragments so it can prove
            # the complete transition union across independent regions.
            minimum_independent_support_regions=1,
        )
        fit_attempt_count += 1
        if observation is None:
            continue
        key = str(observation.observation_id)
        observations_by_role[run.role_hint].setdefault(key, observation)
    merged_observations: list[PhotoBoundaryObservation] = []
    family_resolutions: list[CrossBoundaryFamilyResolution] = []
    family_compatibility_count = 0
    for role, measurement in (
        (BoundaryRole.TOP, top_measurement),
        (BoundaryRole.BOTTOM, bottom_measurement),
    ):
        values, attempts, resolutions, compatibility_count = _merge_registered_cross_families(
            tuple(observations_by_role[role].values()),
            measurement=measurement,
            role=role,
            width_axis=width_axis,
            height_scale_px_per_mm=height_scale_px_per_mm,
        )
        fit_attempt_count += attempts
        family_compatibility_count += compatibility_count
        merged_observations.extend(values)
        family_resolutions.extend(resolutions)
    conditional_ids: dict[ObservationId, set[str]] = {}
    for family in family_resolutions:
        if family.use == CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL:
            for identity in family.final_observation_ids:
                conditional_ids.setdefault(identity, set()).add(family.family_id)
    registered = {
        str(observation.observation_id): (
            replace(CrossRoleBinding.from_measurement(
                _canonical_cross_run(
                    observation,
                    top_measurement
                    if observation.role == BoundaryRole.TOP
                    else bottom_measurement,
                ),
                observation,
                lane_reference_trace_px=lane_reference_trace_px,
                boundary_axis=height_axis,
            ), conditional_family_ids=tuple(sorted(conditional_ids.get(observation.observation_id, ())))),
            observation,
        )
        for observation in merged_observations
    }
    ordered = tuple(
        registered[key]
        for key in sorted(
            registered,
            key=lambda identity: (
                registered[identity][0].coordinate_interval_px.center,
                identity,
            ),
        )
    )
    registered = RegisteredCrossEvidence(
        top_bindings=tuple(
            binding
            for binding, _observation in ordered
            if binding.role == BoundaryRole.TOP
        ),
        bottom_bindings=tuple(
            binding
            for binding, _observation in ordered
            if binding.role == BoundaryRole.BOTTOM
        ),
        observations=tuple(observation for _binding, observation in ordered),
        fit_attempt_count=fit_attempt_count,
        registered_top_run_count=len(qualified_top),
        registered_bottom_run_count=len(qualified_bottom),
        family_resolutions=tuple(
            sorted(family_resolutions, key=lambda item: item.family_id)
        ),
        family_compatibility_evaluation_count=family_compatibility_count,
    )
    return _register_membership_proposals(
        registered, top_measurement=top_measurement, bottom_measurement=bottom_measurement,
        width_axis=width_axis, height_axis=height_axis, height_scale_px_per_mm=height_scale_px_per_mm,
        lane_reference_trace_px=lane_reference_trace_px,
    )


def register_template_local_cross_refinements(
    registered: RegisteredCrossEvidence,
    *,
    top_measurement: PhotoBoundaryMeasurementSet,
    bottom_measurement: PhotoBoundaryMeasurementSet,
    width_axis: BoundaryAxis,
    height_axis: BoundaryAxis,
    height_scale_px_per_mm: PositiveInterval,
    lane_reference_trace_px: float,
    fixed_height_px: FiniteInterval,
    canonical_height_px: float,
    longitudinal_support_domain_groups_px: tuple[tuple[FiniteInterval, ...], ...],
) -> RegisteredCrossEvidence:
    """Refine the missing cross side inside a template-projected local window.

    The measurements were registered and completed before placement fitting.
    A source-wide, role-authorized direct side plus fixed H predicts one finite
    corridor on the opposite measurement.  At each trace only a uniquely
    nearest physical transition may enter the single robust refit.  Therefore
    this pass neither rereads pixels nor turns the template into evidence.
    """

    if not isinstance(registered, RegisteredCrossEvidence):
        raise TypeError("cross refinement requires registered evidence")
    if fixed_height_px.minimum <= 0.0:
        raise ValueError("cross refinement height must be positive")
    if not fixed_height_px.contains(canonical_height_px, epsilon=1.0e-9):
        raise ValueError("canonical cross height leaves physical authority")
    domains = tuple(longitudinal_support_domain_groups_px)
    if not domains:
        return registered

    anchors = tuple(
        binding
        for binding in (*registered.top_bindings, *registered.bottom_bindings)
        if binding.role_authorized
        and not binding.conditional_family_ids
        and binding.canonical_direction_degrees is not None
        and binding.full_direction_interval_degrees is not None
        and binding.has_independent_spatial_support
        and (
            binding.source_spanning_continuous
            or covers_all_template_domains(
                binding.trace_coordinates_px,
                domains,
            )
        )
    )
    if not anchors:
        return registered

    def has_direct_opposite_closure(anchor: CrossRoleBinding) -> bool:
        opposites = (
            registered.bottom_bindings
            if anchor.role == BoundaryRole.TOP
            else registered.top_bindings
        )
        expected = (
            _add(anchor.full_interval_px, fixed_height_px)
            if anchor.role == BoundaryRole.TOP
            else FiniteInterval(
                anchor.full_interval_px.minimum - fixed_height_px.maximum,
                anchor.full_interval_px.maximum - fixed_height_px.minimum,
            )
        )
        for opposite in opposites:
            if (
                opposite.evidence != CrossEvidence.DIRECT
                or opposite.conditional_family_ids
                or not opposite.role_authorized
                or not opposite.has_independent_spatial_support
                or len(
                    set(anchor.trace_coordinates_px).intersection(
                        opposite.trace_coordinates_px
                    )
                )
                < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
                or expected.maximum < opposite.full_interval_px.minimum
                or opposite.full_interval_px.maximum < expected.minimum
            ):
                continue
            anchor_direction = anchor.full_direction_interval_degrees
            opposite_direction = opposite.full_direction_interval_degrees
            if (
                anchor_direction is not None
                and opposite_direction is not None
                and (
                    anchor_direction.maximum < opposite_direction.minimum
                    or opposite_direction.maximum < anchor_direction.minimum
                )
            ):
                continue
            return True
        return False

    height_radius_px = max(
        canonical_height_px - fixed_height_px.minimum,
        fixed_height_px.maximum - canonical_height_px,
    )
    local_radius_px = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.local_window_mm
        * height_scale_px_per_mm.maximum
    )
    refinement_radius_px = height_radius_px + local_radius_px
    observations = {
        str(item.observation_id): item for item in registered.observations
    }
    bindings = {
        str(item.observation_id): item
        for item in (*registered.top_bindings, *registered.bottom_bindings)
    }
    fit_attempt_count = registered.fit_attempt_count
    local_refinement_scope_count = registered.local_refinement_scope_count

    for anchor in anchors:
        # This pass only fills a physically missing opposite side.  Re-fitting
        # transitions after a direct top+bottom closure already exists would
        # duplicate the same structure under a new observation identity and
        # manufacture a discrete runner-up from non-independent evidence.
        if has_direct_opposite_closure(anchor):
            continue
        local_refinement_scope_count += 1
        opposite_role = (
            BoundaryRole.BOTTOM
            if anchor.role == BoundaryRole.TOP
            else BoundaryRole.TOP
        )
        measurement = (
            bottom_measurement
            if opposite_role == BoundaryRole.BOTTOM
            else top_measurement
        )
        by_trace: dict[int, list[object]] = {}
        for transition in measurement.transitions:
            by_trace.setdefault(transition.trace_coordinate_px, []).append(
                transition
            )
        selected = []
        for trace in measurement.query.trace_positions_px:
            expected = _project_cross_anchor(
                anchor,
                trace_coordinate_px=trace,
                lane_reference_trace_px=lane_reference_trace_px,
                canonical_height_px=canonical_height_px,
            )
            local = []
            for transition in by_trace.get(trace, ()):
                distance = _interval_distance(
                    transition.physical_position_interval_px,
                    expected,
                )
                if distance[0] <= refinement_radius_px:
                    local.append((distance, transition))
            distances = tuple(
                sorted(
                    local,
                    key=lambda item: (
                        item[0][0],
                        item[0][1],
                        str(item[1].transition_id),
                    ),
                )
            )
            if not distances:
                continue
            if (
                len(distances) > 1
                and distances[0][0][1] >= distances[1][0][0] - 1.0e-9
            ):
                continue
            selected.append(distances[0][1].transition_id)
        if not selected:
            continue
        fit_attempt_count += 1
        observation = fit_format_bound_boundary_observation(
            measurement,
            transition_ids=tuple(selected),
            role=opposite_role,
            source_axis_long=width_axis,
            boundary_axis_scale_px_per_mm=height_scale_px_per_mm,
            minimum_independent_support_regions=(
                MINIMUM_INDEPENDENT_SUPPORT_REGIONS
            ),
        )
        if observation is None:
            continue
        run = _canonical_cross_run(observation, measurement)
        binding = CrossRoleBinding.from_measurement(
            run,
            observation,
            lane_reference_trace_px=lane_reference_trace_px,
            boundary_axis=height_axis,
        )
        if (
            not binding.role_authorized
            or binding.full_direction_interval_degrees is None
            or max(
                binding.full_direction_interval_degrees.minimum,
                anchor.full_direction_interval_degrees.minimum,
            )
            > min(
                binding.full_direction_interval_degrees.maximum,
                anchor.full_direction_interval_degrees.maximum,
            )
            + 1.0e-9
        ):
            continue
        binding = replace(
            binding,
            evidence=CrossEvidence.TEMPLATE_LOCAL_REFINEMENT,
        )
        key = str(observation.observation_id)
        observations.setdefault(key, observation)
        bindings.setdefault(key, binding)

    ordered = tuple(
        bindings[key]
        for key in sorted(
            bindings,
            key=lambda identity: (
                bindings[identity].coordinate_interval_px.center,
                identity,
            ),
        )
    )
    ordered_observations = tuple(
        observations[key] for key in sorted(observations)
    )
    return RegisteredCrossEvidence(
        top_bindings=tuple(
            item for item in ordered if item.role == BoundaryRole.TOP
        ),
        bottom_bindings=tuple(
            item for item in ordered if item.role == BoundaryRole.BOTTOM
        ),
        observations=ordered_observations,
        fit_attempt_count=fit_attempt_count,
        registered_top_run_count=registered.registered_top_run_count,
        registered_bottom_run_count=registered.registered_bottom_run_count,
        family_resolutions=registered.family_resolutions,
        family_compatibility_evaluation_count=(
            registered.family_compatibility_evaluation_count
        ),
        membership_receipt=registered.membership_receipt,
        local_refinement_scope_count=local_refinement_scope_count,
    )
