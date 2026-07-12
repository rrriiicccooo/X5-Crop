from __future__ import annotations

import ast
from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Any, get_args, get_origin

from tools.tests.architecture_contracts import PROJECT_ROOT
from x5crop.configuration.boundary import BoundaryObservationParameters
from x5crop.configuration.candidate import (
    DualLaneDividerParameters,
    SequenceHypothesisParameters,
    SequenceSolverParameters,
)
from x5crop.configuration.content import (
    ContentEvidenceParameters,
    ContentProfileParameters,
)
from x5crop.configuration.diagnostics import SeparatorOverlayParameters
from x5crop.configuration.separator import SeparatorObservationParameters
from x5crop.domain import AxisBleedParameters
from x5crop.formats import FormatPhysicalSpec, FrameSizeMm
from x5crop.geometry.detection_parameters import SeparatorProfileParameters
from x5crop.image.deskew_parameters import DeskewParameters
from x5crop.image.evidence import (
    ContentEvidenceImageParameters,
    DeskewFallbackEvidenceParameters,
    SeparatorEvidenceImageParameters,
)
from x5crop.image.gray import BaseGrayParameters
from x5crop.image.statistics import ImageMeasurementStatisticsParameters


class ParameterRole(str, Enum):
    PHYSICAL_FACT = "physical_fact"
    STANDARD_TRANSFORM = "standard_transform"
    ADAPTIVE_MEASUREMENT = "adaptive_measurement"
    NUMERICAL_SAFETY = "numerical_safety"
    EXECUTION_BUDGET = "execution_budget"
    USER_PREFERENCE = "user_preference"
    DIAGNOSTICS_ONLY = "diagnostics_only"


@dataclass(frozen=True)
class ParameterContract:
    owner: str
    role: ParameterRole
    unit: str
    stage: str
    rationale: str
    calibration_status: str


@dataclass(frozen=True)
class ParameterGroup:
    model: type
    field_names: tuple[str, ...]
    role: ParameterRole
    unit: str
    stage: str
    rationale: str


def _group(
    model: type,
    field_names: tuple[str, ...],
    role: ParameterRole,
    unit: str,
    stage: str,
    rationale: str,
) -> ParameterGroup:
    return ParameterGroup(model, field_names, role, unit, stage, rationale)


PARAMETER_GROUPS = (
    _group(FrameSizeMm, ("width_mm", "height_mm"), ParameterRole.PHYSICAL_FACT, "mm", "format", "Nominal physical frame dimensions."),
    _group(FormatPhysicalSpec, ("default_count", "allowed_counts", "complete_strip_can_be_underfilled", "lane_count"), ParameterRole.PHYSICAL_FACT, "physical_identity", "format", "Physical strip layout and count facts."),
    _group(BaseGrayParameters, ("red_weight", "green_weight", "blue_weight"), ParameterRole.STANDARD_TRANSFORM, "coefficient", "preprocess", "Standard linear-light luma transform."),
    _group(BaseGrayParameters, ("low_percentile", "high_percentile"), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "preprocess", "Per-image intensity normalization."),
    _group(ImageMeasurementStatisticsParameters, ("intensity_percentiles", "noise_percentiles"), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "preprocess", "Robust image measurement statistics."),
    _group(ImageMeasurementStatisticsParameters, ("edge_sample_ratio",), ParameterRole.ADAPTIVE_MEASUREMENT, "ratio", "preprocess", "Scale-independent edge sampling."),
    _group(ImageMeasurementStatisticsParameters, ("edge_sample_min_px",), ParameterRole.ADAPTIVE_MEASUREMENT, "px", "preprocess", "Minimum sampling support."),
    _group(ContentEvidenceImageParameters, ("gradient_percentile", "texture_percentile", "local_contrast_percentile", "tonal_presence_percentile"), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "preprocess", "Per-image content evidence normalization."),
    _group(ContentEvidenceImageParameters, ("minimum_active_pixels",), ParameterRole.ADAPTIVE_MEASUREMENT, "px_count", "preprocess", "Minimum content measurement support."),
    _group(DeskewFallbackEvidenceParameters, ("low_percentile", "high_percentile"), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "deskew", "Per-image fallback intensity normalization."),
    _group(DeskewFallbackEvidenceParameters, ("shadow_gamma", "edge_weight", "shadow_blend_weight", "edge_blend_weight", "gutter_extreme_min_fraction", "gutter_activity_max", "gutter_run_width_ratio"), ParameterRole.ADAPTIVE_MEASUREMENT, "normalized", "deskew", "Fallback deskew evidence measurement."),
    _group(DeskewFallbackEvidenceParameters, ("gutter_run_width_min",), ParameterRole.ADAPTIVE_MEASUREMENT, "px", "deskew", "Minimum gutter measurement support."),
    _group(SeparatorEvidenceImageParameters, ("low_percentile", "high_percentile"), ParameterRole.DIAGNOSTICS_ONLY, "percentile", "debug", "Debug-only separator image normalization."),
    _group(SeparatorEvidenceImageParameters, ("tonal_low_percentile", "tonal_high_percentile"), ParameterRole.DIAGNOSTICS_ONLY, "percentile", "debug", "Debug-only adaptive tonal-tail visualization."),
    _group(SeparatorEvidenceImageParameters, ("vertical_edge_smooth_ratio", "local_weight", "vertical_edge_weight", "tonal_band_weight"), ParameterRole.DIAGNOSTICS_ONLY, "normalized", "debug", "Debug-only separator visualization."),
    _group(SeparatorEvidenceImageParameters, ("vertical_edge_smooth_min",), ParameterRole.DIAGNOSTICS_ONLY, "px", "debug", "Debug-only minimum smoothing support."),
    _group(SeparatorEvidenceImageParameters, ("numerical_floor",), ParameterRole.NUMERICAL_SAFETY, "normalized", "debug", "Debug-only numerical division floor."),
    _group(SeparatorProfileParameters, ("top_ratio", "bottom_ratio", "smooth_ratio"), ParameterRole.ADAPTIVE_MEASUREMENT, "ratio", "separator_observation", "Scale-independent separator profile measurement."),
    _group(SeparatorProfileParameters, ("consistency_percentile",), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "separator_observation", "Robust cross-axis profile aggregation."),
    _group(SeparatorProfileParameters, ("segments", "sample_short_axis_max", "smooth_min"), ParameterRole.ADAPTIVE_MEASUREMENT, "count_or_px", "separator_observation", "Separator profile sampling support."),
    _group(SeparatorProfileParameters, ("numerical_floor",), ParameterRole.NUMERICAL_SAFETY, "normalized", "separator_observation", "Numerical division floor."),
    _group(SeparatorObservationParameters, ("activation_percentile",), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "separator_observation", "Adaptive separator observation activation."),
    _group(SeparatorObservationParameters, ("minimum_profile_range",), ParameterRole.NUMERICAL_SAFETY, "normalized", "separator_observation", "Rejects numerically flat profiles."),
    _group(SeparatorObservationParameters, ("minimum_run_px",), ParameterRole.ADAPTIVE_MEASUREMENT, "px", "separator_observation", "Minimum measured separator support."),
    _group(SeparatorObservationParameters, ("maximum_observations",), ParameterRole.EXECUTION_BUDGET, "count", "candidate_plan", "Bounds observation expansion."),
    _group(ContentEvidenceParameters, ("activation_percentile",), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "content_evidence", "Adaptive content activation."),
    _group(ContentEvidenceParameters, ("minimum_evidence_range",), ParameterRole.NUMERICAL_SAFETY, "normalized", "content_evidence", "Rejects numerically flat evidence."),
    _group(ContentEvidenceParameters, ("minimum_active_pixels", "boundary_band_min_px"), ParameterRole.ADAPTIVE_MEASUREMENT, "px_count", "content_evidence", "Minimum content measurement support."),
    _group(ContentEvidenceParameters, ("boundary_band_ratio",), ParameterRole.ADAPTIVE_MEASUREMENT, "ratio", "content_evidence", "Scale-independent boundary sampling."),
    _group(ContentProfileParameters, ("activation_percentile",), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "content_guidance", "Adaptive content-run activation."),
    _group(ContentProfileParameters, ("smooth_ratio",), ParameterRole.ADAPTIVE_MEASUREMENT, "ratio", "content_guidance", "Scale-independent content profile smoothing."),
    _group(ContentProfileParameters, ("smooth_min_px", "min_run_width_px"), ParameterRole.ADAPTIVE_MEASUREMENT, "px", "content_guidance", "Minimum content-run support."),
    _group(DualLaneDividerParameters, ("search_min_ratio", "search_max_ratio", "band_width_ratio", "minimum_center_separation_ratio"), ParameterRole.ADAPTIVE_MEASUREMENT, "ratio", "dual_lane_proposal", "Scale-independent holder-gutter proposal measurement."),
    _group(DualLaneDividerParameters, ("residual_scale_percentile",), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "dual_lane_proposal", "Robust holder-gutter residual normalization."),
    _group(DualLaneDividerParameters, ("numerical_floor",), ParameterRole.NUMERICAL_SAFETY, "normalized", "dual_lane_proposal", "Numerical division floor."),
    _group(DualLaneDividerParameters, ("band_width_min_px", "band_width_max_px"), ParameterRole.ADAPTIVE_MEASUREMENT, "px", "dual_lane_proposal", "Gutter measurement support bounds."),
    _group(DualLaneDividerParameters, ("proposal_count",), ParameterRole.EXECUTION_BUDGET, "count", "dual_lane_proposal", "Bounds lane-divider candidate expansion."),
    _group(SequenceHypothesisParameters, ("observation_budget", "maximum_hypotheses"), ParameterRole.EXECUTION_BUDGET, "count", "candidate_plan", "Bounds sequence hypothesis expansion."),
    _group(SequenceSolverParameters, ("maximum_assignment_evaluations",), ParameterRole.EXECUTION_BUDGET, "count", "sequence_solver", "Bounds global assignment search."),
    _group(BoundaryObservationParameters, ("holder_reference_percentile", "change_point_percentile"), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "boundary_observation", "Robust per-image holder and change-point measurement."),
    _group(DeskewParameters, tuple(field.name for field in fields(DeskewParameters)), ParameterRole.ADAPTIVE_MEASUREMENT, "mixed_measurement", "deskew", "Deskew sampling and robust fit parameters."),
    _group(SeparatorOverlayParameters, tuple(field.name for field in fields(SeparatorOverlayParameters)), ParameterRole.DIAGNOSTICS_ONLY, "rendering", "debug", "Debug-only separator overlay rendering."),
    _group(AxisBleedParameters, ("long_axis", "short_axis"), ParameterRole.USER_PREFERENCE, "px", "output", "User-selected output margin."),
)


PARAMETER_MODELS = frozenset(group.model for group in PARAMETER_GROUPS)


def _is_numeric_annotation(annotation: Any) -> bool:
    if isinstance(annotation, str):
        return any(token in annotation for token in ("int", "float", "bool"))
    if annotation in {int, float, bool}:
        return True
    origin = get_origin(annotation)
    if origin in {tuple, list, set, frozenset, UnionType}:
        return any(_is_numeric_annotation(item) for item in get_args(annotation))
    return False


def parameter_contracts() -> dict[str, ParameterContract]:
    contracts: dict[str, ParameterContract] = {}
    for group in PARAMETER_GROUPS:
        calibration_status = (
            "pending_real_sample_calibration"
            if group.role == ParameterRole.ADAPTIVE_MEASUREMENT
            else "fixed_by_contract"
        )
        for field_name in group.field_names:
            owner = f"{group.model.__module__}.{group.model.__name__}.{field_name}"
            if owner in contracts:
                raise AssertionError(f"duplicate parameter contract: {owner}")
            contracts[owner] = ParameterContract(
                owner=owner,
                role=group.role,
                unit=group.unit,
                stage=group.stage,
                rationale=group.rationale,
                calibration_status=calibration_status,
            )
    return contracts


def unclassified_parameter_fields() -> list[str]:
    classified = set(parameter_contracts())
    declared = {
        f"{model.__module__}.{model.__name__}.{field.name}"
        for model in PARAMETER_MODELS
        for field in fields(model)
        if _is_numeric_annotation(field.type)
    }
    return sorted(declared - classified)


def stale_parameter_contracts() -> list[str]:
    declared = {
        f"{model.__module__}.{model.__name__}.{field.name}"
        for model in PARAMETER_MODELS
        for field in fields(model)
        if _is_numeric_annotation(field.type)
    }
    return sorted(set(parameter_contracts()) - declared)


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _contains_numeric_literal(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Constant)
        and not isinstance(child.value, bool)
        and isinstance(child.value, (int, float))
        for child in ast.walk(node)
    )


def hidden_detection_percentiles() -> list[str]:
    offenders: list[str] = []
    root = PROJECT_ROOT / "x5crop/detection"
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) not in {
                "percentile",
                "sampled_percentile",
            }:
                continue
            percentile_arguments = node.args[1:]
            if any(_contains_numeric_literal(argument) for argument in percentile_arguments):
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT).as_posix()}:{node.lineno}"
                )
    return sorted(offenders)
