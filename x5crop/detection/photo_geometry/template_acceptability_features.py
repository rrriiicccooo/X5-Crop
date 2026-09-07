"""Bounded, label-free physical features for retained-placement development."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math

from ...domain import EvidenceState, ObservationId
from .output_model import DirectUseBudgetAssessment, OutputFootprint
from .template_cross_model import CrossLineProjectionBasis
from .template_model import ContactRelation, OverlapRelation, SequenceBindingUse
from .template_placement import FormatPlacement


PLACEMENT_FEATURE_SCHEMA = "x5crop_placement_acceptability_features_v1"


class PlacementFeatureUnit(str, Enum):
    FRACTION = "fraction"
    RATIO = "ratio"
    COUNT = "count"
    DEGREES = "degrees"
    INDICATOR = "indicator"


class PlacementFeatureMissingReason(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    EVIDENCE_UNAVAILABLE = "evidence_unavailable"
    PROPOSAL_UNAVAILABLE = "proposal_unavailable"


@dataclass(frozen=True)
class PlacementFeatureDefinition:
    name: str
    unit: PlacementFeatureUnit
    source_fields: tuple[str, ...]


# This order is the model input contract. Identities and provenance are never
# encoded as numeric features; count/format/profile remain separate task facts.
PLACEMENT_FEATURE_DEFINITIONS = (
    PlacementFeatureDefinition("phase_anchor_group_fraction", PlacementFeatureUnit.FRACTION, ("sequence_fit.role_bindings.use", "sequence_fit.role_bindings.evidence_group_id", "output_slot_count")),
    PlacementFeatureDefinition("local_role_fraction", PlacementFeatureUnit.FRACTION, ("sequence_fit.role_bindings.use", "output_slot_count")),
    PlacementFeatureDefinition("unobserved_frame_fraction", PlacementFeatureUnit.FRACTION, ("sequence_fit.role_bindings", "output_slot_count")),
    PlacementFeatureDefinition("one_sided_frame_fraction", PlacementFeatureUnit.FRACTION, ("sequence_fit.role_bindings", "output_slot_count")),
    PlacementFeatureDefinition("phase_support_coverage_fraction", PlacementFeatureUnit.FRACTION, ("sequence_fit.phase_support_coverage", "output_slot_count")),
    PlacementFeatureDefinition("sequence_residual_relative", PlacementFeatureUnit.RATIO, ("sequence_fit.residual_sum_px", "sequence_fit.role_bindings", "sequence_fit.pitch_fit.canonical_frame_width_px")),
    PlacementFeatureDefinition("sequence_contradiction_count", PlacementFeatureUnit.COUNT, ("sequence_fit.contradicted_observation_count",)),
    PlacementFeatureDefinition("width_absolute_relative_deviation", PlacementFeatureUnit.RATIO, ("sequence_fit.pitch_fit.canonical_frame_width_px", "source_scan_geometry.width_state.scale_authority", "frame_spec.frame_width_mm")),
    PlacementFeatureDefinition("width_relative_uncertainty", PlacementFeatureUnit.RATIO, ("sequence_fit.pitch_fit.frame_width_px", "sequence_fit.pitch_fit.canonical_frame_width_px")),
    PlacementFeatureDefinition("cross_span_absolute_relative_deviation", PlacementFeatureUnit.RATIO, ("cross_fit.top_canonical_px", "cross_fit.bottom_canonical_px", "source_scan_geometry.height_state.scale_authority", "frame_spec.frame_height_mm")),
    PlacementFeatureDefinition("cross_height_relative_uncertainty", PlacementFeatureUnit.RATIO, ("cross_fit.fixed_height_px", "cross_fit.top_canonical_px", "cross_fit.bottom_canonical_px")),
    PlacementFeatureDefinition("pitch_absolute_relative_deviation", PlacementFeatureUnit.RATIO, ("sequence_fit.pitch_fit.canonical_pitch_px", "sequence_fit.template.pitch_px")),
    PlacementFeatureDefinition("pitch_relative_uncertainty", PlacementFeatureUnit.RATIO, ("sequence_fit.pitch_fit.pitch_interval_px", "sequence_fit.pitch_fit.canonical_pitch_px")),
    PlacementFeatureDefinition("cross_direct_role_fraction", PlacementFeatureUnit.FRACTION, ("cross_fit.direct_bindings",)),
    PlacementFeatureDefinition("cross_shared_trace_support_count", PlacementFeatureUnit.COUNT, ("cross_fit.shared_trace_support_count",)),
    PlacementFeatureDefinition("cross_independent_support_region_count", PlacementFeatureUnit.COUNT, ("cross_fit.independent_support_region_count",)),
    PlacementFeatureDefinition("cross_continuous_support_fraction", PlacementFeatureUnit.FRACTION, ("cross_fit.continuous_support_fraction",)),
    PlacementFeatureDefinition("cross_residual_relative", PlacementFeatureUnit.RATIO, ("cross_fit.residual_sum_px", "cross_fit.direct_bindings", "cross_fit.top_canonical_px", "cross_fit.bottom_canonical_px")),
    PlacementFeatureDefinition("contact_relation_fraction", PlacementFeatureUnit.FRACTION, ("sequence_fit.adjacency_relations", "output_slot_count")),
    PlacementFeatureDefinition("overlap_relation_fraction", PlacementFeatureUnit.FRACTION, ("sequence_fit.adjacency_relations", "output_slot_count")),
    PlacementFeatureDefinition("output_maximum_budget_ratio", PlacementFeatureUnit.RATIO, ("direct_use_budget_assessments.edge_assessments.expansion_mm", "direct_use_budget_assessments.edge_assessments.limit_mm")),
    PlacementFeatureDefinition("output_supported_budget_fraction", PlacementFeatureUnit.FRACTION, ("direct_use_budget_assessments.state",)),
    PlacementFeatureDefinition("output_saturation_count", PlacementFeatureUnit.COUNT, ("output_footprints.saturation_facts",)),
    PlacementFeatureDefinition("cross_statistical_projection", PlacementFeatureUnit.INDICATOR, ("cross_fit.line_projection_basis",)),
    PlacementFeatureDefinition("source_w_inference_supported", PlacementFeatureUnit.INDICATOR, ("sequence_fit.frame_width_inference.state",)),
    PlacementFeatureDefinition("cross_longitudinal_supported", PlacementFeatureUnit.INDICATOR, ("cross_fit.longitudinal_projection_authority.state",)),
    PlacementFeatureDefinition("cross_direction_span_degrees", PlacementFeatureUnit.DEGREES, ("cross_fit.selected_direction.full_angle_interval_degrees",)),
    PlacementFeatureDefinition("cross_uses_enclosing_support", PlacementFeatureUnit.INDICATOR, ("cross_fit.enclosing_support_pair",)),
)
_DEFINITIONS_BY_NAME = {item.name: item for item in PLACEMENT_FEATURE_DEFINITIONS}


@dataclass(frozen=True)
class PlacementFeature:
    name: str
    unit: PlacementFeatureUnit
    value: float | None
    missing_reason: PlacementFeatureMissingReason | None
    source_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        definition = _DEFINITIONS_BY_NAME.get(self.name)
        if (
            definition is None
            or not isinstance(self.unit, PlacementFeatureUnit)
            or self.unit != definition.unit
            or self.source_fields != definition.source_fields
            or (self.value is None) != (self.missing_reason is not None)
            or self.missing_reason is not None
            and not isinstance(self.missing_reason, PlacementFeatureMissingReason)
        ):
            raise ValueError("placement feature definition or missingness is invalid")
        if self.value is None:
            return
        if type(self.value) not in {float, int} or not math.isfinite(self.value) or self.value < 0.0:
            raise ValueError("placement feature value must be finite and nonnegative")
        if self.unit in {PlacementFeatureUnit.FRACTION, PlacementFeatureUnit.INDICATOR} and self.value > 1.0 + 1.0e-9:
            raise ValueError("placement feature fraction exceeds one")
        if self.unit == PlacementFeatureUnit.INDICATOR and self.value not in {0.0, 1.0}:
            raise ValueError("placement feature indicator is not binary")
        if self.unit == PlacementFeatureUnit.COUNT and int(self.value) != self.value:
            raise ValueError("placement feature count must be integral")


@dataclass(frozen=True)
class PlacementAcceptabilityFeatures:
    placement_id: str
    lane_id: str
    source_geometry_id: str
    template_id: str
    output_geometry_ids: tuple[str, ...]
    observation_ids: tuple[ObservationId, ...]
    evidence_group_ids: tuple[ObservationId, ...]
    values: tuple[PlacementFeature, ...]
    schema_id: str = field(default=PLACEMENT_FEATURE_SCHEMA, init=False)

    def __post_init__(self) -> None:
        if (
            any(not isinstance(item, str) or not item for item in (self.placement_id, self.lane_id, self.source_geometry_id, self.template_id))
            or any(not isinstance(items, tuple) for items in (self.output_geometry_ids, self.observation_ids, self.evidence_group_ids, self.values))
            or any(not isinstance(item, PlacementFeature) for item in self.values)
            or tuple(item.name for item in self.values)
            != tuple(item.name for item in PLACEMENT_FEATURE_DEFINITIONS)
            or len(set(self.output_geometry_ids)) != len(self.output_geometry_ids)
            or len(set(self.observation_ids)) != len(self.observation_ids)
            or len(set(self.evidence_group_ids)) != len(self.evidence_group_ids)
            or any(not isinstance(item, str) or not item for item in self.output_geometry_ids)
            or not self.observation_ids or not self.evidence_group_ids
            or any(not isinstance(item, ObservationId) for item in (*self.observation_ids, *self.evidence_group_ids))
        ):
            raise ValueError("placement feature identity or compiled vector is invalid")


def build_placement_acceptability_features(
    placement: FormatPlacement,
    outputs: tuple[OutputFootprint, ...],
    budgets: tuple[DirectUseBudgetAssessment, ...],
) -> PlacementAcceptabilityFeatures:
    """Read existing candidate facts; never query pixels, project, rank or admit."""

    if (
        len(outputs) not in {0, placement.output_slot_count}
        or tuple(item.geometry_id for item in outputs) != tuple(item.geometry_id for item in budgets)
        or any(item.envelope.placement_id != placement.placement_id for item in outputs)
        or any(edge.limit_mm <= 0.0 for item in budgets for edge in item.edge_assessments)
    ):
        raise ValueError("placement features require the same complete proposal and budget")
    sequence = placement.sequence_fit
    cross = placement.cross_fit
    pitch = sequence.pitch_fit
    count = placement.output_slot_count
    bound = tuple(item for item in sequence.role_bindings if item is not None)
    anchor_groups = {
        item.evidence_group_id for item in bound if item.use == SequenceBindingUse.PHASE_ANCHOR
    }
    width = pitch.canonical_frame_width_px
    height = cross.bottom_canonical_px - cross.top_canonical_px
    scale_authority = placement.source_scan_geometry.width_state.scale_authority
    scale = (scale_authority.minimum + scale_authority.maximum) / 2.0
    template_pitch = (sequence.template.pitch_px.minimum + sequence.template.pitch_px.maximum) / 2.0
    if height <= 0.0:
        raise ValueError("placement features require a positive cross span")
    missing: dict[str, PlacementFeatureMissingReason] = {}

    def absent(name: str, reason: PlacementFeatureMissingReason) -> None:
        missing[name] = reason
        return None

    no_proposal = PlacementFeatureMissingReason.PROPOSAL_UNAVAILABLE
    not_applicable = PlacementFeatureMissingReason.NOT_APPLICABLE
    unavailable = PlacementFeatureMissingReason.EVIDENCE_UNAVAILABLE
    inference = sequence.frame_width_inference
    longitudinal = cross.longitudinal_projection_authority
    values: dict[str, float | None] = {
        "phase_anchor_group_fraction": len(anchor_groups) / (2 * count),
        "local_role_fraction": sum(item.use == SequenceBindingUse.LOCAL_REFINEMENT for item in bound) / (2 * count),
        "unobserved_frame_fraction": len(sequence.completely_unobserved_frame_ordinals) / count,
        "one_sided_frame_fraction": len(sequence.opposite_inference_role_indices) / count,
        "phase_support_coverage_fraction": sequence.phase_support_coverage / (count + 1),
        "sequence_residual_relative": sequence.residual_sum_px / (len(bound) * width),
        "sequence_contradiction_count": float(sequence.contradicted_observation_count),
        "width_absolute_relative_deviation": abs(width / (scale * placement.frame_spec.frame_width_mm) - 1.0),
        "width_relative_uncertainty": (pitch.frame_width_px.maximum - pitch.frame_width_px.minimum) / width,
        "cross_span_absolute_relative_deviation": abs(height / (scale * placement.frame_spec.frame_height_mm) - 1.0),
        "cross_height_relative_uncertainty": cross.fixed_height_px.width / height,
        "pitch_absolute_relative_deviation": abs(pitch.canonical_pitch_px / template_pitch - 1.0),
        "pitch_relative_uncertainty": (pitch.pitch_interval_px.maximum - pitch.pitch_interval_px.minimum) / pitch.canonical_pitch_px,
        "cross_direct_role_fraction": len(cross.direct_bindings) / 2,
        "cross_shared_trace_support_count": float(cross.shared_trace_support_count),
        "cross_independent_support_region_count": float(cross.independent_support_region_count),
        "cross_continuous_support_fraction": cross.continuous_support_fraction,
        "cross_residual_relative": (
            cross.residual_sum_px / (len(cross.direct_bindings) * height)
            if cross.direct_bindings else absent("cross_residual_relative", unavailable)
        ),
        "contact_relation_fraction": (
            sum(isinstance(item, ContactRelation) for item in sequence.adjacency_relations) / (count - 1)
            if count > 1 else absent("contact_relation_fraction", not_applicable)
        ),
        "overlap_relation_fraction": (
            sum(isinstance(item, OverlapRelation) for item in sequence.adjacency_relations) / (count - 1)
            if count > 1 else absent("overlap_relation_fraction", not_applicable)
        ),
        "output_maximum_budget_ratio": (
            max(edge.expansion_mm / edge.limit_mm for item in budgets for edge in item.edge_assessments)
            if budgets else absent("output_maximum_budget_ratio", no_proposal)
        ),
        "output_supported_budget_fraction": (
            sum(item.state == EvidenceState.SUPPORTED for item in budgets) / len(budgets)
            if budgets else absent("output_supported_budget_fraction", no_proposal)
        ),
        "output_saturation_count": (
            float(sum(len(item.saturation_facts) for item in outputs))
            if outputs else absent("output_saturation_count", no_proposal)
        ),
        "cross_statistical_projection": float(cross.line_projection_basis == CrossLineProjectionBasis.RETAINED_REVIEW_STATISTICAL_FIT),
        "source_w_inference_supported": (
            float(inference.state == EvidenceState.SUPPORTED)
            if inference is not None else absent("source_w_inference_supported", not_applicable)
        ),
        "cross_longitudinal_supported": (
            float(longitudinal.state == EvidenceState.SUPPORTED)
            if longitudinal.state != EvidenceState.UNAVAILABLE else absent("cross_longitudinal_supported", unavailable)
        ),
        "cross_direction_span_degrees": (
            cross.selected_direction.full_angle_interval_degrees.width
            if cross.selected_direction is not None else absent("cross_direction_span_degrees", unavailable)
        ),
        "cross_uses_enclosing_support": float(cross.enclosing_support_pair is not None),
    }
    return PlacementAcceptabilityFeatures(
        placement_id=placement.placement_id,
        lane_id=placement.lane_id,
        source_geometry_id=placement.source_scan_geometry.geometry_id,
        template_id=sequence.template.template_id,
        output_geometry_ids=tuple(item.geometry_id for item in outputs),
        observation_ids=tuple(sorted(set((
            *sequence.bound_observation_ids, *cross.direct_provenance_ids,
            *cross.direction_provenance_ids,
            *(item.observation_id for item in cross.direct_bindings),
            *pitch.observation_ids,
            *placement.source_scan_geometry.width_state.observation_ids,
            *placement.source_scan_geometry.height_state.observation_ids,
            *(() if inference is None else inference.observation_ids),
        )))),
        evidence_group_ids=sequence.evidence_group_ids,
        values=tuple(
            PlacementFeature(item.name, item.unit, values[item.name], missing.get(item.name), item.source_fields)
            for item in PLACEMENT_FEATURE_DEFINITIONS
        ),
    )
