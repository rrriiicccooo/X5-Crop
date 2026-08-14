"""Current-only runtime records for bounded template detection.

This module is the narrow hand-off between registered measurements, template
fits, source selection, and the existing gate/output path.  It deliberately
contains no search algorithm and no historical candidate representation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ...domain import EvidenceState, FiniteInterval
from ...geometry.affine import AffineCoordinateTransform
from ..gate_checks import DetectionFailureFact, TypedAssessment
from ..output_geometry import OutputTransformAssessment
from ..source_core import SourceLaneEvidence
from .content_veto_model import ContentVetoFact
from .line_observations import PhotoBoundaryObservation, SideTransitionRegion
from .measurement_model import (
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryTransition,
)
from .model import BoundaryAxis
from .observation_types import (
    BasicAxisProfile,
    BoundaryEdgeObservation,
    SeparatorBandObservation,
)
from .output_model import (
    DirectUseBudgetAssessment,
    OutputSlotIdentity,
    ResolvedOutputSlots,
    SafeCropEnvelope,
    SharedStripDirection,
)
from .search_model import SequenceAnchorDiscoveryDomain
from .source_geometry import SourceScanGeometry
from .template_cross_model import CrossFitCompetition, CrossRoleBinding
from .template_evidence import EvidenceUseFact
from .template_model import TemplateSpec
from .template_measurement_plan_model import TemplateMeasurementPlan
from .template_phase_model import PhaseFitResult
from .template_placement import FormatPlacement
from .template_precision import TemplatePrecisionLedger


@dataclass(frozen=True)
class TemplateMeasurementWorkReceipt:
    """Aggregate query, pixel, and peak-memory evidence for one lane."""

    measurement_query_count: int
    pixel_query_count: int
    completed_query_count: int
    peak_temporary_bytes: int
    coverage_receipts: tuple[PhotoBoundaryCoverageReceipt, ...]

    def __post_init__(self) -> None:
        values = (
            self.measurement_query_count,
            self.pixel_query_count,
            self.completed_query_count,
            self.peak_temporary_bytes,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("measurement work values must be non-negative")
        if self.completed_query_count > self.measurement_query_count:
            raise ValueError("completed measurements exceed registered queries")
        query_ids = tuple(item.query_id for item in self.coverage_receipts)
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("measurement coverage receipts must be unique")
        if self.measurement_query_count != len(self.coverage_receipts):
            raise ValueError("measurement receipt count must cover every query")
        if self.pixel_query_count != sum(item.pixel_query_count for item in self.coverage_receipts):
            raise ValueError("measurement pixel receipt does not match coverage")
        if self.completed_query_count != sum(item.complete for item in self.coverage_receipts):
            raise ValueError("measurement completion receipt does not match coverage")
        if self.peak_temporary_bytes != max(
            (item.peak_temporary_bytes for item in self.coverage_receipts),
            default=0,
        ):
            raise ValueError("measurement peak receipt does not match coverage")


@dataclass(frozen=True)
class RegisteredTemplateLane:
    """One lane's registered, candidate-independent measurement ledger."""

    lane: SourceLaneEvidence
    layout: str
    output_slot_count: int
    measurement_slot_count: int
    width_axis: BoundaryAxis
    height_axis: BoundaryAxis
    width_authority_px: FiniteInterval
    height_authority_px: FiniteInterval
    anchor_domain: SequenceAnchorDiscoveryDomain
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...]
    side_regions: tuple[SideTransitionRegion, ...]
    top_regions: tuple[SideTransitionRegion, ...]
    bottom_regions: tuple[SideTransitionRegion, ...]
    transition_by_id: Mapping[str, PhotoBoundaryTransition]
    sequence_profile: BasicAxisProfile
    cross_profile: BasicAxisProfile
    sequence_edges: tuple[BoundaryEdgeObservation, ...]
    separator_bands: tuple[SeparatorBandObservation, ...]
    top_cross_bindings: tuple[CrossRoleBinding, ...]
    bottom_cross_bindings: tuple[CrossRoleBinding, ...]
    raw_cross_observations: tuple[PhotoBoundaryObservation, ...]
    measurement_work: TemplateMeasurementWorkReceipt
    measurement_plan: TemplateMeasurementPlan

    def __post_init__(self) -> None:
        if not isinstance(self.lane, SourceLaneEvidence):
            raise TypeError("registered template lane requires source authority")
        if not isinstance(self.measurement_plan, TemplateMeasurementPlan):
            raise TypeError("registered template lane requires a compiled plan")
        if self.layout not in {"horizontal", "vertical"}:
            raise ValueError("registered template lane layout is invalid")
        if self.output_slot_count <= 0 or self.measurement_slot_count < self.output_slot_count:
            raise ValueError("template lane slot counts are inconsistent")
        if self.width_axis == self.height_axis:
            raise ValueError("template lane axes must be distinct")
        if not isinstance(self.width_authority_px, FiniteInterval) or not isinstance(
            self.height_authority_px, FiniteInterval
        ):
            raise TypeError("template lane authority must use finite intervals")
        lane_id = self.lane.domain.lane_id
        if (
            self.measurement_plan.lane_id != lane_id
            or self.measurement_plan.layout != self.layout
            or self.measurement_plan.count != self.output_slot_count
            or self.measurement_plan.full_count != self.measurement_slot_count
        ):
            raise ValueError("compiled plan disagrees with lane authority")
        if self.anchor_domain.lane_id != lane_id:
            raise ValueError("anchor domain belongs to another lane")
        queries = tuple(item.query for item in self.measurement_sets)
        query_ids = tuple(item.query_id for item in queries)
        if len(set(query_ids)) != len(query_ids) or any(
            item.lane_id != lane_id for item in queries
        ):
            raise ValueError("measurement queries must be unique and lane-local")
        receipt_ids = tuple(item.query_id for item in self.measurement_work.coverage_receipts)
        if receipt_ids != query_ids:
            raise ValueError("measurement receipts must cover registered queries once")
        transition_ids = tuple(self.transition_by_id)
        if len(set(transition_ids)) != len(transition_ids) or any(
            str(item.transition_id) != key
            for key, item in self.transition_by_id.items()
        ):
            raise ValueError("transition ledger keys must match transition identities")
        if self.sequence_profile.axis_name != "sequence" or self.cross_profile.axis_name != "cross":
            raise ValueError("template profiles must retain sequence and cross axes")
        if len({item.observation_id for item in self.sequence_edges}) != len(self.sequence_edges):
            raise ValueError("sequence edges must be registered once")
        if len({item.observation_id for item in self.separator_bands}) != len(self.separator_bands):
            raise ValueError("separator bands must be registered once")
        if any(
            binding.role.value != expected
            for bindings, expected in (
                (self.top_cross_bindings, "top"),
                (self.bottom_cross_bindings, "bottom"),
            )
            for binding in bindings
        ):
            raise ValueError("cross bindings must retain their registered role")
        binding_ids = tuple(
            item.observation_id
            for item in (*self.top_cross_bindings, *self.bottom_cross_bindings)
        )
        if len(set(binding_ids)) != len(binding_ids):
            raise ValueError("cross bindings must be registered once")
        if len({item.observation_id for item in self.raw_cross_observations}) != len(
            self.raw_cross_observations
        ):
            raise ValueError("cross observations must be registered once")
        if set(binding_ids) != {
            item.observation_id for item in self.raw_cross_observations
        }:
            raise ValueError("cross bindings and observations must share identity")
        object.__setattr__(self, "transition_by_id", MappingProxyType(dict(self.transition_by_id)))


@dataclass(frozen=True)
class PreparedTemplateLane(RegisteredTemplateLane):
    """A registered lane paired with one fixed template and its fit ledgers."""

    template_spec: TemplateSpec
    source_scan_geometry: SourceScanGeometry
    phase_competition: PhaseFitResult
    cross_competition: CrossFitCompetition
    evidence_use_ledger: tuple[EvidenceUseFact, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.template_spec, TemplateSpec):
            raise TypeError("prepared template lane requires a template spec")
        if self.template_spec.count != self.output_slot_count:
            raise ValueError("template count must equal lane output count")
        if self.template_spec.template_id != self.measurement_plan.template_spec.template_id:
            raise ValueError("prepared template must retain compiled identity")
        if not isinstance(self.source_scan_geometry, SourceScanGeometry):
            raise TypeError("prepared template lane requires source geometry")
        if not isinstance(self.phase_competition, PhaseFitResult):
            raise TypeError("phase competition must be the canonical phase fit")
        if self.phase_competition.template != self.template_spec:
            raise ValueError("phase fit and template spec disagree")
        if not isinstance(self.cross_competition, CrossFitCompetition):
            raise TypeError("cross competition must be the canonical cross fit")
        if self.cross_competition.template_id != self.template_spec.template_id:
            raise ValueError("cross fit and template spec disagree")
        if len({item.observation_id for item in self.evidence_use_ledger}) != len(
            self.evidence_use_ledger
        ):
            raise ValueError("one observation must have one fit/validation use")


@dataclass(frozen=True)
class TemplatePlacementCompetition:
    """A bounded placement set retaining only winner and runner metadata."""

    placements: tuple[FormatPlacement, ...]
    selected_placement_id: str | None
    runner_up_placement_id: str | None
    state: EvidenceState
    failure: DetectionFailureFact | None

    def __post_init__(self) -> None:
        if not isinstance(self.state, EvidenceState):
            raise TypeError("placement competition requires a typed state")
        ids = tuple(item.placement_id for item in self.placements)
        if len(set(ids)) != len(ids) or any(not isinstance(item, FormatPlacement) for item in self.placements):
            raise ValueError("placement competition identities are invalid")
        if self.selected_placement_id not in ({None} | set(ids)):
            raise ValueError("selected placement is outside its competition")
        if self.runner_up_placement_id not in ({None} | set(ids)):
            raise ValueError("runner-up placement is outside its competition")
        if self.selected_placement_id is not None and self.selected_placement_id == self.runner_up_placement_id:
            raise ValueError("winner and runner-up must differ")
        if (self.state == EvidenceState.SUPPORTED) != (self.selected_placement_id is not None):
            raise ValueError("placement state and selected identity disagree")
        if self.state == EvidenceState.SUPPORTED:
            if self.failure is not None:
                raise ValueError("supported placement has no failure")
        elif not isinstance(self.failure, DetectionFailureFact):
            raise ValueError("unsupported placement requires a typed failure")


@dataclass(frozen=True)
class TemplatePlacementWorkReceipt:
    """Bounded work for one lane's placement assessment."""

    placement_evaluation_count: int
    boundary_evaluation_count: int
    content_evaluation_count: int
    peak_temporary_bytes: int
    bound_exceeded: bool = False

    def __post_init__(self) -> None:
        values = (
            self.placement_evaluation_count,
            self.boundary_evaluation_count,
            self.content_evaluation_count,
            self.peak_temporary_bytes,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("template placement work values must be non-negative")
        if not isinstance(self.bound_exceeded, bool):
            raise TypeError("placement bound status must be boolean")


@dataclass(frozen=True)
class TemplateLaneReconstruction:
    """One lane's bounded placement competition and selected-only outputs."""

    lane_id: str
    prepared: PreparedTemplateLane
    placement_competition: TemplatePlacementCompetition
    selected_placement: FormatPlacement | None
    safe_crop_envelopes: tuple[SafeCropEnvelope, ...]
    direct_use_budget_assessments: tuple[DirectUseBudgetAssessment, ...]
    content_veto_facts: tuple[ContentVetoFact, ...]
    work: TemplatePlacementWorkReceipt
    precision_ledger: TemplatePrecisionLedger | None = None

    def __post_init__(self) -> None:
        if not self.lane_id or self.prepared.lane.domain.lane_id != self.lane_id:
            raise ValueError("template reconstruction lane authority is invalid")
        placements = self.placement_competition.placements
        if any(item.lane_id != self.lane_id for item in placements):
            raise ValueError("placement competition crosses lane authority")
        selected_id = self.placement_competition.selected_placement_id
        if (self.selected_placement is None) != (selected_id is None):
            raise ValueError("selected placement and competition state disagree")
        if self.selected_placement is not None and self.selected_placement.placement_id != selected_id:
            raise ValueError("selected placement is not competition winner")
        if self.safe_crop_envelopes:
            if self.selected_placement is None or len(self.safe_crop_envelopes) != self.selected_placement.output_slot_count:
                raise ValueError("safe envelopes must cover the selected template slots")
            ordinals = tuple(item.lane_ordinal for item in self.safe_crop_envelopes)
            if ordinals != tuple(range(1, len(ordinals) + 1)):
                raise ValueError("safe envelope ordinals must be contiguous")
            if any(item.lane_id != self.lane_id for item in self.safe_crop_envelopes):
                raise ValueError("safe envelope crosses lane authority")
            if len(self.direct_use_budget_assessments) != len(self.safe_crop_envelopes):
                raise ValueError("every selected envelope requires one direct-use assessment")
        elif self.direct_use_budget_assessments:
            raise ValueError("direct-use assessments require selected envelopes")
        if any(not isinstance(item, ContentVetoFact) for item in self.content_veto_facts):
            raise TypeError("content veto ledger requires typed facts")
        if self.precision_ledger is not None and (
            self.selected_placement is None
            or self.precision_ledger.placement_id
            != self.selected_placement.placement_id
        ):
            raise ValueError("precision ledger requires the selected placement")


@dataclass(frozen=True)
class TemplateSourceSelection:
    """Source-level winner, shared geometry, direction, and runner metadata."""

    lane_ids: tuple[str, ...]
    selected_placement_ids: tuple[str | None, ...]
    shared_scan_geometry: SourceScanGeometry | None
    shared_direction: SharedStripDirection | None
    state: EvidenceState
    failure: DetectionFailureFact | None
    runner_up_placement_ids: tuple[str | None, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.state, EvidenceState):
            raise TypeError("source selection requires a typed state")
        if len(set(self.lane_ids)) != len(self.lane_ids):
            raise ValueError("source selection lane identities must be unique")
        if not self.lane_ids:
            if (
                self.state == EvidenceState.SUPPORTED
                or self.selected_placement_ids
                or self.runner_up_placement_ids
                or self.shared_scan_geometry is not None
                or self.shared_direction is not None
                or not isinstance(self.failure, DetectionFailureFact)
            ):
                raise ValueError("empty source selection can only be unresolved")
            return
        if len(self.selected_placement_ids) != len(self.lane_ids):
            raise ValueError("source selection winners must cover every lane")
        runners = self.runner_up_placement_ids
        if runners and len(runners) != len(self.lane_ids):
            raise ValueError("source selection runners must cover every lane")
        if any(value is not None and not value for value in (*self.selected_placement_ids, *runners)):
            raise ValueError("source placement identities must not be empty")
        if runners and any(
            selected is not None and runner == selected
            for selected, runner in zip(self.selected_placement_ids, runners, strict=True)
        ):
            raise ValueError("source winner and runner must differ")
        supported = self.state == EvidenceState.SUPPORTED
        complete = all(value is not None for value in self.selected_placement_ids)
        if supported != (complete and self.shared_scan_geometry is not None and self.shared_direction is not None):
            raise ValueError("source selection authority is incomplete")
        if supported:
            if self.failure is not None:
                raise ValueError("supported source selection has no failure")
        elif not isinstance(self.failure, DetectionFailureFact):
            raise ValueError("unsupported source selection requires a typed failure")


@dataclass(frozen=True)
class PhotoGeometryDetectionResult:
    """Pipeline-facing result with selected-only output properties."""

    resolved_output_slots: ResolvedOutputSlots | None
    lane_reconstructions: tuple[TemplateLaneReconstruction, ...]
    source_placement_selection: TemplateSourceSelection
    output_slot_identities: tuple[OutputSlotIdentity, ...]
    source_transform_assessment: OutputTransformAssessment
    lane_transform_assessments: tuple[OutputTransformAssessment, ...]
    assessment_facts: Mapping[str, TypedAssessment]

    def __post_init__(self) -> None:
        lane_ids = tuple(item.lane_id for item in self.lane_reconstructions)
        if len(set(lane_ids)) != len(lane_ids):
            raise ValueError("detection result lane identities must be unique")
        if self.resolved_output_slots is not None:
            if len(self.output_slot_identities) != self.resolved_output_slots.output_slot_count:
                raise ValueError("resolved output slots require exact identities")
            expected_counts = self.resolved_output_slots.lane_output_slot_counts
            actual_counts = tuple(
                sum(1 for item in self.output_slot_identities if item.lane_id == lane_id)
                for lane_id in lane_ids
            )
            if actual_counts != expected_counts:
                raise ValueError("output identities disagree with lane slot counts")
        elif self.output_slot_identities:
            raise ValueError("unresolved output slots cannot have identities")
        if len(self.lane_transform_assessments) != len(self.lane_reconstructions):
            raise ValueError("each template lane requires one transform assessment")
        if self.source_placement_selection.lane_ids != lane_ids:
            raise ValueError("source selection lane order disagrees with result")
        selected_ids = tuple(
            None
            if item.selected_placement is None
            else item.selected_placement.placement_id
            for item in self.lane_reconstructions
        )
        if selected_ids != self.source_placement_selection.selected_placement_ids:
            raise ValueError("source selection winners disagree with lane results")
        lane_supported = bool(lane_ids) and all(
            item.placement_competition.state == EvidenceState.SUPPORTED
            for item in self.lane_reconstructions
        )
        if lane_supported != (self.source_placement_selection.state == EvidenceState.SUPPORTED):
            raise ValueError("source and lane placement states disagree")
        if self.source_placement_selection.state == EvidenceState.SUPPORTED:
            shared = self.source_placement_selection.shared_scan_geometry
            direction = self.source_placement_selection.shared_direction
            assert shared is not None and direction is not None
            if any(
                item.selected_placement is None
                or item.selected_placement.source_scan_geometry != shared
                or item.selected_placement.direction != direction
                for item in self.lane_reconstructions
            ):
                raise ValueError("selected lanes disagree with shared source authority")
        if self.source_placement_selection.state != EvidenceState.SUPPORTED and any(
            item.safe_crop_envelopes or item.direct_use_budget_assessments or item.selected_placement is not None
            for item in self.lane_reconstructions
        ):
            raise ValueError("unsupported source result cannot expose selected outputs")
        if not isinstance(self.assessment_facts, Mapping) or any(
            not isinstance(key, str) or not isinstance(value, TypedAssessment)
            for key, value in self.assessment_facts.items()
        ):
            raise TypeError("detection assessment facts must be typed")
        object.__setattr__(self, "assessment_facts", MappingProxyType(dict(self.assessment_facts)))

    @property
    def safe_crop_envelopes(self) -> tuple[SafeCropEnvelope, ...]:
        return tuple(
            envelope
            for lane in self.lane_reconstructions
            for envelope in lane.safe_crop_envelopes
        )

    @property
    def direct_use_budget_assessments(self) -> tuple[DirectUseBudgetAssessment, ...]:
        return tuple(
            assessment
            for lane in self.lane_reconstructions
            for assessment in lane.direct_use_budget_assessments
        )

    @property
    def output_transforms(self) -> tuple[AffineCoordinateTransform, ...]:
        transforms: list[AffineCoordinateTransform] = []
        for lane, assessment in zip(
            self.lane_reconstructions,
            self.lane_transform_assessments,
            strict=True,
        ):
            if assessment.transform is None:
                continue
            transforms.extend(assessment.transform for _ in lane.safe_crop_envelopes)
        return tuple(transforms)


__all__ = [
    "PhotoGeometryDetectionResult",
    "PreparedTemplateLane",
    "RegisteredTemplateLane",
    "TemplateLaneReconstruction",
    "TemplateMeasurementWorkReceipt",
    "TemplatePlacementCompetition",
    "TemplatePlacementWorkReceipt",
    "TemplateSourceSelection",
]
