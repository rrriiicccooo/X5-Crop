"""Bounded independent reconstruction of retained phase explanations.

Each complete retained diagnostic owns one bounded Review attempt. Canonical
lane competition and Gate records remain outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from ...domain import EvidenceState
from ...run_local_identity import run_local_id
from ..gate_checks import GateGap, failure_fact
from .template_acceptability_features import (
    PLACEMENT_FEATURE_DEFINITIONS,
    PlacementAcceptabilityFeatures,
    build_placement_acceptability_features,
)
from .template_aspect_ratio_model import unavailable_aperture_aspect_ratio_authority
from .template_cross import fit_template_cross
from .template_cross_model import (
    CrossEvidence,
    CrossFailureKind,
    CrossFit,
    CrossFitCompetition,
    CrossFitStatus,
    CrossSearchReceipt,
    TemplateCrossInput,
)
from .template_feasible_geometry import project_format_placement
from .template_model import SequenceFit
from .template_measurement_plan_model import MAX_CROSS_PAIRS
from .template_output import (
    output_footprint_from_template_placement,
    template_direct_use_budget_assessment,
)
from .template_phase_model import (
    NativeEndpointPhaseDiagnostic,
    NativePhaseRetention,
    NATIVE_PHASE_RETENTION_CLASS_COUNT,
)
from .template_intrinsic_review_refit import (
    IntrinsicPhaseRefitResult,
    IntrinsicPhaseReviewDiagnostic,
    build_intrinsic_phase_refit,
)
from .template_source_clipped import (
    SourceClippedPhaseDiagnostic,
    SourceClippedPhaseRetention,
    SOURCE_CLIPPED_CLASS_COUNT,
)
from .template_placement import (
    FormatPlacement,
    compose_format_placement,
    resolved_cross_support_domains_px,
)
from .template_runtime_model import (
    PreparedTemplateLane,
    TemplatePlacementProposal,
    TemplateProposalState,
)
from .source_geometry import SourceScanGeometry


# Conservative receipt proxy for one temporary output geometry record.  The
# value is a fixed per-slot accounting constant, not a Cross search bound.
_REVIEW_OUTPUT_TEMPORARY_BYTES = 4096
MAX_INDEPENDENT_PHASE_REVIEWS = (
    2 * NATIVE_PHASE_RETENTION_CLASS_COUNT + SOURCE_CLIPPED_CLASS_COUNT
)


def _review_peak_temporary_bound(
    *,
    cross_call_count: int,
    cross_evaluated_fit_count: int,
    placement_projection_count: int,
    output_evaluation_count: int,
) -> int:
    """Return the conservative live-structure bound for one review run."""

    cross_bound = (
        MAX_CROSS_PAIRS + cross_evaluated_fit_count * 1024
        if cross_call_count
        else 0
    )
    placement_bound = (
        2048 + output_evaluation_count * _REVIEW_OUTPUT_TEMPORARY_BYTES
        if placement_projection_count
        else 0
    )
    return max(cross_bound, placement_bound)


class IndependentPhaseReviewKind(str, Enum):
    NATIVE_ENDPOINT = "native_endpoint"
    SOURCE_CLIPPED_TERMINAL = "source_clipped_terminal"
    INTRINSIC_REFIT = "intrinsic_refit"


PhaseReviewDiagnostic = (
    NativeEndpointPhaseDiagnostic
    | SourceClippedPhaseDiagnostic
    | IntrinsicPhaseReviewDiagnostic
)


def _phase_review_kind(diagnostic: PhaseReviewDiagnostic) -> IndependentPhaseReviewKind:
    if isinstance(diagnostic, NativeEndpointPhaseDiagnostic):
        return IndependentPhaseReviewKind.NATIVE_ENDPOINT
    if isinstance(diagnostic, SourceClippedPhaseDiagnostic):
        return IndependentPhaseReviewKind.SOURCE_CLIPPED_TERMINAL
    if isinstance(diagnostic, IntrinsicPhaseReviewDiagnostic):
        return IndependentPhaseReviewKind.INTRINSIC_REFIT
    raise TypeError("independent phase review diagnostic is invalid")


def _review_placement_prefix(kind: IndependentPhaseReviewKind) -> str:
    return {
        IndependentPhaseReviewKind.NATIVE_ENDPOINT: "native-endpoint-review-placement",
        IndependentPhaseReviewKind.SOURCE_CLIPPED_TERMINAL: "source-clipped-review-placement",
        IndependentPhaseReviewKind.INTRINSIC_REFIT: "intrinsic-phase-review-placement",
    }[kind]


class IndependentPhaseReviewFailureKind(str, Enum):
    """Independent failure reasons owned by one phase Review attempt."""

    INITIAL_HEIGHT_DEPENDENCY_UNAVAILABLE = "initial_height_dependency_unavailable"
    CROSS_INPUT_UNAVAILABLE = "cross_input_unavailable"
    CROSS_BOUND_EXCEEDED = "cross_bound_exceeded"
    CROSS_BEST_UNAVAILABLE = "cross_best_unavailable"
    COMPOSE_UNAVAILABLE = "compose_unavailable"
    PLACEMENT_PROJECTION_UNAVAILABLE = "placement_projection_unavailable"
    PLACEMENT_PROJECTION_BOUND_EXCEEDED = (
        "placement_projection_bound_exceeded"
    )
    OUTPUT_UNAVAILABLE = "output_unavailable"


@dataclass(frozen=True)
class IndependentPhaseReviewFailure:
    """One typed failure from the independent review path."""

    kind: IndependentPhaseReviewFailureKind
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, IndependentPhaseReviewFailureKind) or not self.detail:
            raise ValueError("independent phase review failure is incomplete")


@dataclass(frozen=True)
class IndependentPhaseReviewWorkReceipt:
    """Logical work and bounded temporary storage for one review attempt."""

    cross_call_count: int
    cross_evaluated_fit_count: int
    compose_call_count: int
    placement_projection_count: int
    extreme_evaluation_count: int
    output_evaluation_count: int
    output_count: int
    budget_evaluation_count: int
    feature_evaluation_count: int
    output_slot_count: int
    peak_temporary_bytes: int

    def __post_init__(self) -> None:
        values = (
            self.cross_call_count,
            self.cross_evaluated_fit_count,
            self.compose_call_count,
            self.placement_projection_count,
            self.extreme_evaluation_count,
            self.output_evaluation_count,
            self.output_count,
            self.budget_evaluation_count,
            self.feature_evaluation_count,
            self.output_slot_count,
            self.peak_temporary_bytes,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("independent phase review work is invalid")
        if self.output_slot_count <= 0:
            raise ValueError("independent phase review requires output slots")
        if self.cross_call_count > 1 or self.compose_call_count > 1:
            raise ValueError("independent phase review repeats a bounded call")
        if self.placement_projection_count > 1:
            raise ValueError("independent phase review repeats placement projection")
        if self.cross_call_count == 0 and self.cross_evaluated_fit_count:
            raise ValueError("independent phase review counted an absent Cross call")
        if self.cross_evaluated_fit_count and self.cross_call_count != 1:
            raise ValueError("independent phase review Cross work lacks its call")
        if self.output_count > self.output_evaluation_count:
            raise ValueError("independent phase review retained too many outputs")
        if self.output_evaluation_count > self.output_slot_count:
            raise ValueError("independent phase review output work exceeds its slots")
        if self.output_count > self.output_slot_count:
            raise ValueError("independent phase review output count exceeds its slots")
        if self.budget_evaluation_count > self.output_evaluation_count:
            raise ValueError("independent phase review budget work exceeds outputs")
        if self.feature_evaluation_count not in {
            0,
            len(PLACEMENT_FEATURE_DEFINITIONS),
        }:
            raise ValueError("independent phase review feature work is not one vector")
        if self.extreme_evaluation_count > 130 * self.output_slot_count + 64:
            raise ValueError("independent phase review projection exceeds its bound")


class _IndependentPhaseCrossInputError(ValueError):
    """A constructor error that the builder maps to its typed own failure."""

    def __init__(self, kind: IndependentPhaseReviewFailureKind, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind


def independent_phase_cross_input(
    original: TemplateCrossInput,
    source: SourceScanGeometry,
    fit: SequenceFit,
) -> TemplateCrossInput:
    """Build the independent DIRECT-only Cross input from one retained fit."""

    if not isinstance(original, TemplateCrossInput):
        raise TypeError("native endpoint Cross input requires TemplateCrossInput")
    if not isinstance(source, SourceScanGeometry):
        raise TypeError("native endpoint Cross input requires fresh source geometry")
    if not isinstance(fit, SequenceFit):
        raise TypeError("native endpoint Cross input requires SequenceFit")
    if original.template != fit.template:
        raise ValueError("native endpoint Cross input changed template identity")
    if (
        original.maximum_compatible_pairs > MAX_CROSS_PAIRS
        or original.maximum_evaluated_fits > MAX_CROSS_PAIRS
    ):
        raise _IndependentPhaseCrossInputError(
            IndependentPhaseReviewFailureKind.CROSS_INPUT_UNAVAILABLE,
            "original Cross bound exceeds the compiled owner bound",
        )
    initial_height = source.height_state.extent_projection_px()
    if (
        original.fixed_height_px != initial_height
        or original.canonical_fixed_height_px != initial_height.center
    ):
        raise _IndependentPhaseCrossInputError(
            IndependentPhaseReviewFailureKind.INITIAL_HEIGHT_DEPENDENCY_UNAVAILABLE,
            "original Cross fixed H or center differs from fresh source H",
        )
    try:
        review_domains = resolved_cross_support_domains_px(fit)
    except ValueError as error:
        raise _IndependentPhaseCrossInputError(
            IndependentPhaseReviewFailureKind.CROSS_INPUT_UNAVAILABLE,
            str(error),
        ) from error
    # Conditional DIRECT bindings remain in the provenance ledger.  The Cross
    # owner decides whether their family dependency leaves the result
    # unresolved; this constructor must not erase that explanation.
    direct = lambda binding: binding.evidence == CrossEvidence.DIRECT
    top_bindings = tuple(item for item in original.top_bindings if direct(item))
    bottom_bindings = tuple(
        item for item in original.bottom_bindings if direct(item)
    )
    return replace(
        original,
        fixed_height_px=initial_height,
        canonical_fixed_height_px=initial_height.center,
        top_bindings=top_bindings,
        bottom_bindings=bottom_bindings,
        longitudinal_support_domain_groups_px=(),
        review_support_domain_groups_px=(review_domains,),
        fitted_observation_count=len(top_bindings) + len(bottom_bindings),
        aperture_aspect_ratio_authority=unavailable_aperture_aspect_ratio_authority(),
    )


def _review_placement_id(
    lane: PreparedTemplateLane,
    source: SourceScanGeometry,
    fit: SequenceFit,
    diagnostic: PhaseReviewDiagnostic,
    cross_input: TemplateCrossInput,
    cross_fit: CrossFit,
) -> str:
    if not isinstance(diagnostic, NativeEndpointPhaseDiagnostic):
        return run_local_id(
            _review_placement_prefix(_phase_review_kind(diagnostic)),
            lane.lane.domain.lane_id,
            repr(source),
            repr(diagnostic),
            repr(cross_input),
            repr(cross_fit),
        )
    return run_local_id(
        "native-endpoint-review-placement",
        lane.lane.domain.lane_id,
        repr(source),
        repr(fit),
        repr(diagnostic.projection),
        (
            diagnostic.residual_compatible,
            diagnostic.terminal_role_indices,
            diagnostic.selection_basis.value,
        ),
        repr(cross_input),
        repr(cross_fit),
    )


def _proposal_gap(kind: IndependentPhaseReviewFailureKind) -> GateGap:
    return {
        IndependentPhaseReviewFailureKind.INITIAL_HEIGHT_DEPENDENCY_UNAVAILABLE: (
            GateGap.CROSS_AUTHORITY_UNAVAILABLE
        ),
        IndependentPhaseReviewFailureKind.CROSS_INPUT_UNAVAILABLE: (
            GateGap.CROSS_AUTHORITY_UNAVAILABLE
        ),
        IndependentPhaseReviewFailureKind.CROSS_BOUND_EXCEEDED: (
            GateGap.PRODUCER_BOUND_EXCEEDED
        ),
        IndependentPhaseReviewFailureKind.CROSS_BEST_UNAVAILABLE: (
            GateGap.CROSS_AUTHORITY_UNAVAILABLE
        ),
        IndependentPhaseReviewFailureKind.COMPOSE_UNAVAILABLE: (
            GateGap.COMPLETE_PLACEMENT_UNAVAILABLE
        ),
        IndependentPhaseReviewFailureKind.PLACEMENT_PROJECTION_UNAVAILABLE: (
            GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE
        ),
        IndependentPhaseReviewFailureKind.PLACEMENT_PROJECTION_BOUND_EXCEEDED: (
            GateGap.PRODUCER_BOUND_EXCEEDED
        ),
        IndependentPhaseReviewFailureKind.OUTPUT_UNAVAILABLE: (
            GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE
        ),
    }[kind]


def _unavailable_proposal(
    lane_id: str,
    placement: FormatPlacement | None,
    failure: IndependentPhaseReviewFailure,
    features: PlacementAcceptabilityFeatures | None,
) -> TemplatePlacementProposal:
    placement_id = None if placement is None or features is None else placement.placement_id
    return TemplatePlacementProposal(
        lane_id=lane_id,
        state=TemplateProposalState.UNAVAILABLE,
        placement_id=placement_id,
        output_footprints=(),
        direct_use_budget_assessments=(),
        acceptability_features=features if placement_id is not None else None,
        failure=failure_fact(_proposal_gap(failure.kind), detail=failure.detail),
    )


@dataclass(frozen=True)
class IndependentPhaseReview:
    """Typed output of one independent phase reconstruction."""

    phase_diagnostic: PhaseReviewDiagnostic
    source_scan_geometry: SourceScanGeometry
    cross_input: TemplateCrossInput | None
    cross_best: CrossFit | None
    cross_status: CrossFitStatus | None
    cross_failure_kind: CrossFailureKind | None
    cross_receipt: CrossSearchReceipt | None
    placement: FormatPlacement | None
    proposal: TemplatePlacementProposal
    failure: IndependentPhaseReviewFailure | None
    work: IndependentPhaseReviewWorkReceipt
    kind: IndependentPhaseReviewKind = field(init=False)
    scope: str = field(default="review_only", init=False)

    def __post_init__(self) -> None:
        if self.scope != "review_only":
            raise ValueError("independent phase review scope is invalid")
        diagnostic = self.phase_diagnostic
        object.__setattr__(self, "kind", _phase_review_kind(diagnostic))
        if not isinstance(self.source_scan_geometry, SourceScanGeometry):
            raise TypeError("independent phase review source geometry is invalid")
        if not isinstance(self.proposal, TemplatePlacementProposal):
            raise TypeError("independent phase review proposal is invalid")
        if not isinstance(self.work, IndependentPhaseReviewWorkReceipt):
            raise TypeError("independent phase review work is invalid")
        if self.work.output_slot_count != diagnostic.fit.template.count:
            raise ValueError("independent phase review changed template count")
        if self.work.peak_temporary_bytes < _review_peak_temporary_bound(
            cross_call_count=self.work.cross_call_count,
            cross_evaluated_fit_count=self.work.cross_evaluated_fit_count,
            placement_projection_count=self.work.placement_projection_count,
            output_evaluation_count=self.work.output_evaluation_count,
        ):
            raise ValueError("independent phase review peak receipt is below its bound")
        if self.cross_input is not None and not isinstance(
            self.cross_input,
            TemplateCrossInput,
        ):
            raise TypeError("independent phase review Cross input is invalid")
        if self.cross_input is not None and (
            self.cross_input.maximum_compatible_pairs > MAX_CROSS_PAIRS
            or self.cross_input.maximum_evaluated_fits > MAX_CROSS_PAIRS
        ):
            raise ValueError("independent phase review Cross input exceeds its owner bound")
        if self.cross_best is not None and not isinstance(self.cross_best, CrossFit):
            raise TypeError("independent phase review Cross best is invalid")
        if self.cross_status is not None and not isinstance(
            self.cross_status,
            CrossFitStatus,
        ):
            raise TypeError("independent phase review Cross status is invalid")
        if self.cross_failure_kind is not None and not isinstance(
            self.cross_failure_kind,
            CrossFailureKind,
        ):
            raise TypeError("independent phase review Cross failure is invalid")
        if self.cross_receipt is not None and not isinstance(
            self.cross_receipt,
            CrossSearchReceipt,
        ):
            raise TypeError("independent phase review Cross receipt is invalid")
        if self.failure is not None and not isinstance(
            self.failure,
            IndependentPhaseReviewFailure,
        ):
            raise TypeError("independent phase review failure is invalid")
        overflow_is_bound_failure = (
            self.cross_status == CrossFitStatus.BOUND_EXCEEDED
            and self.failure is not None
            and self.failure.kind == IndependentPhaseReviewFailureKind.CROSS_BOUND_EXCEEDED
        )
        if self.cross_input is not None and self.cross_receipt is not None:
            if (
                self.cross_receipt.evaluated_fit_bound
                > self.cross_input.maximum_evaluated_fits
                or self.cross_receipt.evaluated_fit_bound > MAX_CROSS_PAIRS
                or (
                    self.cross_receipt.evaluated_fit_count
                    > self.cross_input.maximum_evaluated_fits
                    and not overflow_is_bound_failure
                )
                or (
                    self.cross_receipt.evaluated_fit_count > MAX_CROSS_PAIRS
                    and not overflow_is_bound_failure
                )
            ):
                raise ValueError("independent phase review Cross receipt exceeds its bound")
        if (
            self.work.cross_evaluated_fit_count > MAX_CROSS_PAIRS
            and not overflow_is_bound_failure
        ):
            raise ValueError("independent phase review Cross work exceeds its bound")

        fit = diagnostic.fit
        initial_height = self.source_scan_geometry.height_state.extent_projection_px()
        if self.cross_input is not None:
            if self.cross_input.template != fit.template:
                raise ValueError("independent phase review Cross changed template")
            if self.cross_input.fixed_height_px != initial_height or (
                self.cross_input.canonical_fixed_height_px != initial_height.center
            ):
                raise ValueError("independent phase review Cross changed initial H")
            if self.cross_input.longitudinal_support_domain_groups_px:
                raise ValueError("independent phase review retained longitudinal authority")
            if self.cross_input.review_support_domain_groups_px != (
                resolved_cross_support_domains_px(fit),
            ):
                raise ValueError("independent phase review changed support domains")
            if self.cross_input.fitted_observation_count != (
                len(self.cross_input.top_bindings)
                + len(self.cross_input.bottom_bindings)
            ):
                raise ValueError("independent phase review changed fitted binding count")
            if self.cross_input.aperture_aspect_ratio_authority.state != EvidenceState.UNAVAILABLE:
                raise ValueError("independent phase review retained aspect authority")
            if any(
                binding.evidence != CrossEvidence.DIRECT
                for binding in (
                    *self.cross_input.top_bindings,
                    *self.cross_input.bottom_bindings,
                )
            ):
                raise ValueError("independent phase review Cross retained a non-direct binding")
            if self.cross_status is None:
                if any(
                    value is not None
                    for value in (
                        self.cross_best,
                        self.cross_failure_kind,
                        self.cross_receipt,
                    )
                ):
                    raise ValueError("independent phase review counted an absent Cross result")
            elif self.cross_receipt is None:
                raise ValueError("independent phase review Cross result lacks receipt")
        elif any(
            value is not None
            for value in (
                self.cross_best,
                self.cross_status,
                self.cross_failure_kind,
                self.cross_receipt,
            )
        ):
            raise ValueError("independent phase review Cross fields lack input")

        if self.cross_status == CrossFitStatus.RESOLVED:
            if self.cross_best is None or self.cross_failure_kind is not None:
                raise ValueError("resolved native endpoint Cross lacks a best fit")
            if self.cross_best.conditional_family_ids:
                raise ValueError("conditional native endpoint Cross cannot be resolved")
        elif self.cross_status is not None and self.cross_best is not None:
            if self.cross_best.template_id != fit.template.template_id:
                raise ValueError("native endpoint Cross best changed template")
        if self.cross_best is not None:
            if self.cross_best.template_id != fit.template.template_id or any(
                binding.evidence != CrossEvidence.DIRECT
                for binding in self.cross_best.direct_bindings
            ):
                raise ValueError("native endpoint Cross best changed direct identity")
            if self.cross_input is None or any(
                (binding.role, binding.observation_id)
                not in {
                    (item.role, item.observation_id)
                    for item in (
                        *self.cross_input.top_bindings,
                        *self.cross_input.bottom_bindings,
                    )
                }
                for binding in self.cross_best.direct_bindings
            ):
                raise ValueError("native endpoint Cross best escaped its input IDs")

        if self.placement is not None:
            if not isinstance(self.placement, FormatPlacement):
                raise TypeError("independent phase review placement is invalid")
            if (
                self.placement.sequence_fit != fit
                or self.placement.source_scan_geometry != self.source_scan_geometry
                or self.placement.global_lattice_authority is not None
                or self.cross_best is None
                or self.placement.cross_fit != self.cross_best
                or not self.placement.placement_id.startswith(
                    _review_placement_prefix(self.kind)
                )
            ):
                raise ValueError("independent phase review placement changed authority")
            if self.proposal.lane_id != self.placement.lane_id:
                raise ValueError("independent phase review proposal changed lane")
            if self.proposal.placement_id not in {
                None,
                self.placement.placement_id,
            }:
                raise ValueError("independent phase review proposal changed placement")
        elif self.proposal.placement_id is not None:
            raise ValueError("independent phase review retained an absent placement")

        if self.failure is None:
            if self.placement is None or self.proposal.state != TemplateProposalState.GENERATED:
                raise ValueError("independent phase review failure state is incomplete")
            if (
                self.work.cross_call_count != 1
                or self.work.compose_call_count != 1
                or self.work.placement_projection_count != 1
                or self.cross_receipt is None
            ):
                raise ValueError("generated independent phase review lacks one bounded call")
            if (
                len(self.proposal.output_footprints) != fit.template.count
                or len(self.proposal.direct_use_budget_assessments)
                != fit.template.count
                or self.proposal.acceptability_features is None
            ):
                raise ValueError("generated independent phase review lacks complete output")
        elif self.proposal.state != TemplateProposalState.UNAVAILABLE:
            raise ValueError("failed independent phase review generated a proposal")
        if self.failure is not None:
            kind = self.failure.kind
            if kind in {
                IndependentPhaseReviewFailureKind.INITIAL_HEIGHT_DEPENDENCY_UNAVAILABLE,
                IndependentPhaseReviewFailureKind.CROSS_INPUT_UNAVAILABLE,
            }:
                expected_calls = (0, 0, 0)
            elif kind in {
                IndependentPhaseReviewFailureKind.CROSS_BOUND_EXCEEDED,
                IndependentPhaseReviewFailureKind.CROSS_BEST_UNAVAILABLE,
            }:
                expected_calls = (1, 0, 0)
            elif kind == IndependentPhaseReviewFailureKind.COMPOSE_UNAVAILABLE:
                expected_calls = (1, 1, 0)
            else:
                expected_calls = (1, 1, 1)
            if (
                (self.work.cross_call_count, self.work.compose_call_count,
                 self.work.placement_projection_count) != expected_calls
                or (self.placement is not None) != bool(expected_calls[2])
                or expected_calls[1] and self.cross_best is None
                or kind == IndependentPhaseReviewFailureKind.CROSS_BEST_UNAVAILABLE
                and self.cross_best is not None
                or kind == IndependentPhaseReviewFailureKind.CROSS_BOUND_EXCEEDED
                and self.cross_status != CrossFitStatus.BOUND_EXCEEDED
                or kind != IndependentPhaseReviewFailureKind.OUTPUT_UNAVAILABLE
                and self.work.output_evaluation_count != 0
                or kind == IndependentPhaseReviewFailureKind.OUTPUT_UNAVAILABLE
                and self.work.output_evaluation_count == 0
            ):
                raise ValueError("independent phase review failure changed its bounded stage")

        if self.cross_receipt is None:
            if self.work.cross_evaluated_fit_count:
                raise ValueError("independent phase review lost Cross receipt")
        elif self.work.cross_evaluated_fit_count != self.cross_receipt.evaluated_fit_count:
            raise ValueError("independent phase review Cross work disagrees with receipt")
        if self.cross_status is None and self.work.cross_call_count:
            raise ValueError("independent phase review counted an absent Cross call")
        if self.cross_status is not None and self.work.cross_call_count != 1:
            raise ValueError("independent phase review lost its Cross call")
        if not self.work.placement_projection_count and self.work.extreme_evaluation_count:
            raise ValueError("independent phase review counted absent projection work")
        if (
            (self.proposal.acceptability_features is None)
            != (self.work.feature_evaluation_count == 0)
        ):
            raise ValueError("independent phase review feature receipt disagrees")
        if self.proposal.acceptability_features is not None and len(
            self.proposal.acceptability_features.values
        ) != len(PLACEMENT_FEATURE_DEFINITIONS):
            raise ValueError("independent phase review feature vector is incomplete")
        if self.proposal.state == TemplateProposalState.GENERATED:
            if self.work.output_count != fit.template.count or (
                self.work.output_evaluation_count != fit.template.count
                or self.work.budget_evaluation_count != fit.template.count
                or self.work.feature_evaluation_count
                != len(PLACEMENT_FEATURE_DEFINITIONS)
            ):
                raise ValueError("generated independent phase review work is incomplete")
        elif self.work.output_count:
            raise ValueError("failed independent phase review retained outputs")


def _build_independent_phase_review(
    lane: PreparedTemplateLane,
    diagnostic: PhaseReviewDiagnostic,
) -> IndependentPhaseReview:
    """Run one bounded independent review reconstruction for a prepared lane."""

    if not isinstance(lane, PreparedTemplateLane):
        raise TypeError("independent phase review requires PreparedTemplateLane")
    fit = diagnostic.fit
    if fit.template != lane.template_spec:
        raise ValueError("independent phase review phase fit changed lane template")

    scales = lane.lane.scan_canvas.axis_scales
    if scales is None:
        raise ValueError("independent phase review requires scan-canvas scales")
    source = SourceScanGeometry.create(
        lane.source_scan_geometry.frame_spec,
        width_scale_px_per_mm=scales.width_axis_px_per_mm,
        height_scale_px_per_mm=scales.height_axis_px_per_mm,
    )
    cross_input: TemplateCrossInput | None = None
    cross_best: CrossFit | None = None
    cross_status: CrossFitStatus | None = None
    cross_failure_kind: CrossFailureKind | None = None
    cross_receipt: CrossSearchReceipt | None = None
    placement: FormatPlacement | None = None
    failure: IndependentPhaseReviewFailure | None = None
    output_evaluation_count = 0
    output_count = 0
    budget_evaluation_count = 0
    feature_evaluation_count = 0
    cross_call_count = 0
    cross_evaluated_fit_count = 0
    compose_call_count = 0
    placement_projection_count = 0
    extreme_evaluation_count = 0
    features: PlacementAcceptabilityFeatures | None = None
    proposal: TemplatePlacementProposal | None = None

    try:
        cross_input = independent_phase_cross_input(
            lane.cross_input,
            source,
            fit,
        )
    except _IndependentPhaseCrossInputError as error:
        failure = IndependentPhaseReviewFailure(error.kind, str(error))

    if failure is None:
        assert cross_input is not None
        cross_call_count = 1
        cross_competition = fit_template_cross(cross_input)
        if not isinstance(cross_competition, CrossFitCompetition):
            raise TypeError(
                "independent Cross owner returned an invalid competition"
            )
        cross_status = cross_competition.status
        cross_failure_kind = cross_competition.failure_kind
        cross_receipt = cross_competition.receipt
        cross_best = cross_competition.best
        cross_evaluated_fit_count = cross_receipt.evaluated_fit_count
        if cross_status == CrossFitStatus.BOUND_EXCEEDED:
            failure = IndependentPhaseReviewFailure(
                IndependentPhaseReviewFailureKind.CROSS_BOUND_EXCEEDED,
                cross_competition.reason or "independent Cross bound exceeded",
            )
        overflow_is_bound_failure = (
            cross_status == CrossFitStatus.BOUND_EXCEEDED
            and failure is not None
            and failure.kind == IndependentPhaseReviewFailureKind.CROSS_BOUND_EXCEEDED
        )
        if (
            cross_receipt.evaluated_fit_bound > cross_input.maximum_evaluated_fits
            or cross_receipt.evaluated_fit_bound > MAX_CROSS_PAIRS
            or (
                cross_receipt.evaluated_fit_count
                > cross_input.maximum_evaluated_fits
                and not overflow_is_bound_failure
            )
            or (
                cross_receipt.evaluated_fit_count > MAX_CROSS_PAIRS
                and not overflow_is_bound_failure
            )
        ):
            raise ValueError("independent Cross receipt exceeds its input or owner bound")
        if failure is None and cross_best is None:
            failure = IndependentPhaseReviewFailure(
                IndependentPhaseReviewFailureKind.CROSS_BEST_UNAVAILABLE,
                cross_competition.reason or "independent Cross has no best fit",
            )
        elif failure is None:
            compose_call_count = 1
            try:
                placement = compose_format_placement(
                    lane_id=lane.lane.domain.lane_id,
                    frame_spec=source.frame_spec,
                    source_scan_geometry=source,
                    sequence_fit=fit,
                    global_lattice_authority=None,
                    cross_fit=cross_best,
                    width_axis=lane.width_axis,
                    height_axis=lane.height_axis,
                    width_authority_px=lane.width_authority_px,
                    height_authority_px=lane.height_authority_px,
                    template=fit.template,
                    placement_id=_review_placement_id(
                        lane,
                        source,
                        fit,
                        diagnostic,
                        cross_input,
                        cross_best,
                    ),
                )
            except ValueError as error:
                failure = IndependentPhaseReviewFailure(
                    IndependentPhaseReviewFailureKind.COMPOSE_UNAVAILABLE,
                    str(error),
                )
            if failure is None:
                placement_projection_count = 1
                try:
                    projection = project_format_placement(placement)
                    extreme_evaluation_count = projection.extreme_evaluation_count
                except ValueError as error:
                    failure = IndependentPhaseReviewFailure(
                        IndependentPhaseReviewFailureKind.PLACEMENT_PROJECTION_UNAVAILABLE,
                        str(error),
                    )
                if failure is None and extreme_evaluation_count > 130 * fit.template.count + 64:
                    failure = IndependentPhaseReviewFailure(
                        IndependentPhaseReviewFailureKind.PLACEMENT_PROJECTION_BOUND_EXCEEDED,
                        "independent placement projection exceeded 130F+64",
                    )
                elif failure is None:
                    outputs = []
                    try:
                        for ordinal in range(1, fit.template.count + 1):
                            output_evaluation_count += 1
                            outputs.append(
                                output_footprint_from_template_placement(
                                    placement,
                                    projection,
                                    lane=lane.lane,
                                    lane_ordinal=ordinal,
                                    layout=lane.layout,
                                )
                            )
                    except ValueError as error:
                        failure = IndependentPhaseReviewFailure(
                            IndependentPhaseReviewFailureKind.OUTPUT_UNAVAILABLE,
                            str(error),
                        )
                    if failure is None:
                        budgets = []
                        for output in outputs:
                            budget_evaluation_count += 1
                            budgets.append(
                                template_direct_use_budget_assessment(
                                    placement,
                                    output,
                                )
                            )
                        output_count = len(outputs)
                        features = build_placement_acceptability_features(
                            placement,
                            tuple(outputs),
                            tuple(budgets),
                        )
                        feature_evaluation_count = len(features.values)
                        proposal = TemplatePlacementProposal(
                            lane_id=lane.lane.domain.lane_id,
                            state=TemplateProposalState.GENERATED,
                            placement_id=placement.placement_id,
                            output_footprints=tuple(outputs),
                            direct_use_budget_assessments=tuple(budgets),
                            acceptability_features=features,
                            failure=None,
                        )
    if proposal is None:
        assert failure is not None
        proposal = _unavailable_proposal(
            lane.lane.domain.lane_id,
            placement,
            failure,
            features,
        )

    peak_temporary_bytes = _review_peak_temporary_bound(
        cross_call_count=cross_call_count,
        cross_evaluated_fit_count=cross_evaluated_fit_count,
        placement_projection_count=placement_projection_count,
        output_evaluation_count=output_evaluation_count,
    )
    work = IndependentPhaseReviewWorkReceipt(
        cross_call_count=cross_call_count,
        cross_evaluated_fit_count=cross_evaluated_fit_count,
        compose_call_count=compose_call_count,
        placement_projection_count=placement_projection_count,
        extreme_evaluation_count=extreme_evaluation_count,
        output_evaluation_count=output_evaluation_count,
        output_count=output_count,
        budget_evaluation_count=budget_evaluation_count,
        feature_evaluation_count=feature_evaluation_count,
        output_slot_count=fit.template.count,
        peak_temporary_bytes=peak_temporary_bytes,
    )
    return IndependentPhaseReview(
        phase_diagnostic=diagnostic,
        source_scan_geometry=source,
        cross_input=cross_input,
        cross_best=cross_best,
        cross_status=cross_status,
        cross_failure_kind=cross_failure_kind,
        cross_receipt=cross_receipt,
        placement=placement,
        proposal=proposal,
        failure=failure,
        work=work,
    )


@dataclass(frozen=True)
class IndependentPhaseReviewPortfolio:
    """Complete class attempts and conditional intrinsic refits, all Review-only."""

    native_phase_retention: NativePhaseRetention | None
    reviews: tuple[IndependentPhaseReview, ...]
    source_clipped_phase_retention: SourceClippedPhaseRetention | None = None
    intrinsic_refits: tuple[IntrinsicPhaseRefitResult, ...] = ()
    scope: str = field(default="review_only", init=False)
    peak_temporary_bytes: int = field(init=False)

    def __post_init__(self) -> None:
        native = self.native_phase_retention
        clipped = self.source_clipped_phase_retention
        if native is not None and not isinstance(native, NativePhaseRetention):
            raise TypeError("independent phase portfolio native retention is invalid")
        if clipped is not None and not isinstance(clipped, SourceClippedPhaseRetention):
            raise TypeError("independent phase portfolio source retention is invalid")
        if (
            not isinstance(self.reviews, tuple)
            or not 1 <= len(self.reviews) <= MAX_INDEPENDENT_PHASE_REVIEWS
            or any(not isinstance(item, IndependentPhaseReview) for item in self.reviews)
            or not isinstance(self.intrinsic_refits, tuple)
            or len(self.intrinsic_refits) > NATIVE_PHASE_RETENTION_CLASS_COUNT
            or any(not isinstance(item, IntrinsicPhaseRefitResult) for item in self.intrinsic_refits)
        ):
            raise ValueError("independent phase portfolio exceeds its typed attempts")
        base_diagnostics = (
            (() if native is None else native.diagnostics)
            + (() if clipped is None else clipped.diagnostics)
        )
        expected_refit_origins = tuple(
            item.phase_diagnostic
            for item in self.reviews
            if item.kind == IndependentPhaseReviewKind.NATIVE_ENDPOINT
            and item.failure is not None
            and item.failure.kind == IndependentPhaseReviewFailureKind.COMPOSE_UNAVAILABLE
        )
        if tuple(item.original_diagnostic for item in self.intrinsic_refits) != expected_refit_origins:
            raise ValueError("intrinsic refit lost its original failed composition")
        expected_diagnostics = base_diagnostics + tuple(
            item.diagnostic for item in self.intrinsic_refits if item.diagnostic is not None
        )
        if tuple(item.phase_diagnostic for item in self.reviews) != expected_diagnostics:
            raise ValueError("independent phase portfolio lost complete class representatives")
        placement_ids = tuple(
            item.placement.placement_id
            for item in self.reviews if item.placement is not None
        )
        if len(set(placement_ids)) != len(placement_ids):
            raise ValueError("independent phase portfolio repeats a placement identity")
        # Completed attempts remain referenced while the next one runs. Count
        # their output records and phase facts conservatively in addition to
        # the largest temporary Cross/projection structure, without repeating
        # the phase classification receipt for every attempt.
        retained_bytes = sum(
            2048
            + len(item.phase_diagnostic.fit.role_bindings) * 256
            + item.work.output_count * _REVIEW_OUTPUT_TEMPORARY_BYTES
            for item in self.reviews
        )
        object.__setattr__(self, "peak_temporary_bytes", max(
            0 if native is None else native.peak_temporary_bytes,
            0 if clipped is None else clipped.peak_temporary_bytes,
            retained_bytes + max(
                tuple(item.work.peak_temporary_bytes for item in self.reviews)
                + tuple(item.work.peak_temporary_bytes for item in self.intrinsic_refits)
            ),
        ))


def build_independent_phase_review(
    lane: PreparedTemplateLane,
) -> IndependentPhaseReviewPortfolio | None:
    """Materialize fixed classes, then refit only failed native compositions."""

    if not isinstance(lane, PreparedTemplateLane):
        raise TypeError("independent phase review requires PreparedTemplateLane")
    native = lane.phase_competition._native_phase_retention
    clipped = lane.phase_competition._source_clipped_phase_retention
    native = native if native is not None and native.diagnostics else None
    clipped = clipped if clipped is not None and clipped.diagnostics else None
    if native is None and clipped is None:
        return None
    native_reviews = tuple(
        _build_independent_phase_review(lane, diagnostic)
        for diagnostic in (() if native is None else native.diagnostics)
    )
    clipped_reviews = tuple(
        _build_independent_phase_review(lane, diagnostic)
        for diagnostic in (() if clipped is None else clipped.diagnostics)
    )
    refits = tuple(
        build_intrinsic_phase_refit(lane.phase_input, item.phase_diagnostic)
        for item in native_reviews
        if item.failure is not None
        and item.failure.kind == IndependentPhaseReviewFailureKind.COMPOSE_UNAVAILABLE
    )
    refit_reviews = tuple(
        _build_independent_phase_review(lane, item.diagnostic)
        for item in refits if item.diagnostic is not None
    )
    return IndependentPhaseReviewPortfolio(
        native_phase_retention=native,
        source_clipped_phase_retention=clipped,
        intrinsic_refits=refits,
        reviews=native_reviews + clipped_reviews + refit_reviews,
    )


__all__ = [
    "IndependentPhaseReview",
    "IndependentPhaseReviewPortfolio",
    "IndependentPhaseReviewKind",
    "IndependentPhaseReviewFailure",
    "IndependentPhaseReviewFailureKind",
    "IndependentPhaseReviewWorkReceipt",
    "build_independent_phase_review",
    "independent_phase_cross_input",
]
