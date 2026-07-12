from __future__ import annotations

import ast
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import importlib
from pathlib import Path
from types import UnionType
from typing import Any, get_args, get_origin

from tools.tests.architecture_contracts import (
    PROJECT_ROOT,
    parsed_source,
    source_modules,
)
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
from x5crop.configuration.diagnostics import (
    DebugStyleParameters,
    SeparatorOverlayParameters,
)
from x5crop.configuration.separator import SeparatorObservationParameters
from x5crop.output.model import AxisBleedParameters
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
from x5crop.run_config import RunConfig
from x5crop.runtime.options import RuntimeOptions


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
    _group(BaseGrayParameters, ("maximum_percentile_samples",), ParameterRole.ADAPTIVE_MEASUREMENT, "sample_count", "preprocess", "Deterministic percentile sampling support."),
    _group(ImageMeasurementStatisticsParameters, ("intensity_percentiles", "noise_percentiles", "edge_texture_percentiles"), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "preprocess", "Robust image measurement statistics."),
    _group(ImageMeasurementStatisticsParameters, ("edge_sample_ratio",), ParameterRole.ADAPTIVE_MEASUREMENT, "ratio", "preprocess", "Scale-independent edge sampling."),
    _group(ImageMeasurementStatisticsParameters, ("edge_sample_min_px",), ParameterRole.ADAPTIVE_MEASUREMENT, "px", "preprocess", "Minimum sampling support."),
    _group(ImageMeasurementStatisticsParameters, ("maximum_percentile_samples",), ParameterRole.ADAPTIVE_MEASUREMENT, "sample_count", "preprocess", "Deterministic percentile sampling support."),
    _group(ContentEvidenceImageParameters, ("gradient_percentile", "texture_percentile", "local_contrast_percentile", "tonal_presence_percentile"), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "preprocess", "Per-image content evidence normalization."),
    _group(ContentEvidenceImageParameters, ("minimum_consensus_channels",), ParameterRole.ADAPTIVE_MEASUREMENT, "component_count", "preprocess", "Minimum independently active content-evidence components."),
    _group(ContentEvidenceImageParameters, ("numerical_floor",), ParameterRole.NUMERICAL_SAFETY, "normalized", "preprocess", "Content evidence normalization floor."),
    _group(ContentEvidenceImageParameters, ("maximum_percentile_samples",), ParameterRole.ADAPTIVE_MEASUREMENT, "sample_count", "preprocess", "Deterministic percentile sampling support."),
    _group(DeskewFallbackEvidenceParameters, ("low_percentile", "high_percentile"), ParameterRole.ADAPTIVE_MEASUREMENT, "percentile", "deskew", "Per-image fallback intensity normalization."),
    _group(DeskewFallbackEvidenceParameters, ("shadow_gamma", "edge_weight", "shadow_blend_weight", "edge_blend_weight", "gutter_extreme_min_fraction", "gutter_activity_max", "gutter_run_width_ratio"), ParameterRole.ADAPTIVE_MEASUREMENT, "normalized", "deskew", "Fallback deskew evidence measurement."),
    _group(DeskewFallbackEvidenceParameters, ("gutter_run_width_min",), ParameterRole.ADAPTIVE_MEASUREMENT, "px", "deskew", "Minimum gutter measurement support."),
    _group(DeskewFallbackEvidenceParameters, ("maximum_percentile_samples",), ParameterRole.ADAPTIVE_MEASUREMENT, "sample_count", "deskew", "Deterministic percentile sampling support."),
    _group(SeparatorEvidenceImageParameters, ("low_percentile", "high_percentile"), ParameterRole.DIAGNOSTICS_ONLY, "percentile", "debug", "Debug-only separator image normalization."),
    _group(SeparatorEvidenceImageParameters, ("tonal_low_percentile", "tonal_high_percentile"), ParameterRole.DIAGNOSTICS_ONLY, "percentile", "debug", "Debug-only adaptive tonal-tail visualization."),
    _group(SeparatorEvidenceImageParameters, ("vertical_edge_smooth_ratio", "local_weight", "vertical_edge_weight", "tonal_band_weight"), ParameterRole.DIAGNOSTICS_ONLY, "normalized", "debug", "Debug-only separator visualization."),
    _group(SeparatorEvidenceImageParameters, ("vertical_edge_smooth_min",), ParameterRole.DIAGNOSTICS_ONLY, "px", "debug", "Debug-only minimum smoothing support."),
    _group(SeparatorEvidenceImageParameters, ("numerical_floor",), ParameterRole.NUMERICAL_SAFETY, "normalized", "debug", "Debug-only numerical division floor."),
    _group(SeparatorEvidenceImageParameters, ("maximum_percentile_samples",), ParameterRole.DIAGNOSTICS_ONLY, "sample_count", "debug", "Debug-only percentile sampling support."),
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
    _group(ContentEvidenceParameters, ("maximum_percentile_samples",), ParameterRole.ADAPTIVE_MEASUREMENT, "sample_count", "content_evidence", "Deterministic percentile sampling support."),
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
    _group(DebugStyleParameters, tuple(field.name for field in fields(DebugStyleParameters)), ParameterRole.DIAGNOSTICS_ONLY, "rendering", "debug", "Debug-only canvas, color, text, and encoding style."),
    _group(AxisBleedParameters, ("long_axis", "short_axis"), ParameterRole.USER_PREFERENCE, "px", "output", "User-selected output margin."),
    _group(RuntimeOptions, ("requested_count",), ParameterRole.USER_PREFERENCE, "count", "runtime_input", "Optional user-selected frame count."),
    _group(RuntimeOptions, ("page",), ParameterRole.USER_PREFERENCE, "page_index", "input", "User-selected TIFF page."),
    _group(RuntimeOptions, ("bleed", "bleed_x", "bleed_y"), ParameterRole.USER_PREFERENCE, "px", "output", "Optional user-selected output margins."),
    _group(RuntimeOptions, ("deskew_min_angle", "deskew_max_angle"), ParameterRole.USER_PREFERENCE, "degrees", "deskew", "User-selected deskew application bounds."),
    _group(RuntimeOptions, ("copy_review_files", "export_review", "dry_run", "overwrite", "report", "reuse_analysis"), ParameterRole.USER_PREFERENCE, "boolean", "runtime", "User-selected runtime behavior."),
    _group(RuntimeOptions, ("debug", "debug_analysis", "diagnostics", "debug_errors"), ParameterRole.DIAGNOSTICS_ONLY, "boolean", "diagnostics", "User-selected diagnostics behavior."),
    _group(RuntimeOptions, ("jobs",), ParameterRole.EXECUTION_BUDGET, "worker_count", "runtime", "User-selected worker budget."),
    _group(RunConfig, ("layout_auto", "requested_count", "page", "bleed_x", "bleed_y", "deskew_min_angle", "deskew_max_angle", "copy_review_files", "export_review", "dry_run", "overwrite", "report", "reuse_analysis"), ParameterRole.USER_PREFERENCE, "resolved_runtime_input", "runtime", "Validated runtime inputs."),
    _group(RunConfig, ("debug", "debug_analysis", "diagnostics", "debug_errors"), ParameterRole.DIAGNOSTICS_ONLY, "boolean", "diagnostics", "Validated diagnostics inputs."),
    _group(RunConfig, ("jobs",), ParameterRole.EXECUTION_BUDGET, "worker_count", "runtime", "Validated worker budget."),
)


CONSTANT_PARAMETER_CONTRACTS = (
    ParameterContract(
        "x5crop.debug.canvas.FRAME_FILL_COLORS",
        ParameterRole.DIAGNOSTICS_ONLY,
        "rgb",
        "debug",
        "Debug-only frame identity colors.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.configuration.diagnostics.JPEG_QUALITY_MAX",
        ParameterRole.STANDARD_TRANSFORM,
        "jpeg_quality",
        "debug",
        "Standard JPEG encoder quality maximum.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.formats.FORMATS",
        ParameterRole.PHYSICAL_FACT,
        "physical_registry",
        "format",
        "Canonical format physical facts.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.image.constants.UINT8_MAX_VALUE",
        ParameterRole.STANDARD_TRANSFORM,
        "uint8_value",
        "image",
        "Canonical uint8 normalization scale.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.image.constants.UINT8_ROUNDING_OFFSET",
        ParameterRole.STANDARD_TRANSFORM,
        "uint8_value",
        "image",
        "Nearest-integer offset for uint8 evidence encoding.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.image.constants.FOUR_NEIGHBOR_MEAN_WEIGHT",
        ParameterRole.STANDARD_TRANSFORM,
        "coefficient",
        "image",
        "Equal four-neighbor mean coefficient.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.image.constants.FIVE_POINT_MEAN_WEIGHT",
        ParameterRole.STANDARD_TRANSFORM,
        "coefficient",
        "image",
        "Equal center-plus-neighbor mean coefficient.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.image.transforms.ROTATION_IDENTITY_EPSILON_DEGREES",
        ParameterRole.NUMERICAL_SAFETY,
        "degrees",
        "image_transform",
        "Avoids numerically meaningless rotation work.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.image.transforms.ROTATION_ROW_CHUNK_SIZE",
        ParameterRole.EXECUTION_BUDGET,
        "rows",
        "image_transform",
        "Bounds temporary rotation-grid memory.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.io.tiff.TIFF_ICC_PROFILE_TAG",
        ParameterRole.STANDARD_TRANSFORM,
        "tiff_tag",
        "tiff_io",
        "Standard TIFF ICC profile tag identity.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.io.tiff.BITS_PER_BYTE",
        ParameterRole.STANDARD_TRANSFORM,
        "bits",
        "tiff_io",
        "Standard byte-to-bit conversion.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.io.tiff.TIFF_RESOLUTION_ABSOLUTE_TOLERANCE",
        ParameterRole.NUMERICAL_SAFETY,
        "resolution",
        "tiff_validation",
        "Compares equivalent rational TIFF resolution values.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.units.MILLIMETERS_PER_INCH",
        ParameterRole.STANDARD_TRANSFORM,
        "mm_per_inch",
        "units",
        "Exact inch-to-millimeter conversion.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.units.MILLIMETERS_PER_CENTIMETER",
        ParameterRole.STANDARD_TRANSFORM,
        "mm_per_centimeter",
        "units",
        "Exact centimeter-to-millimeter conversion.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.utils.PERCENTILE_MAX",
        ParameterRole.STANDARD_TRANSFORM,
        "percentile",
        "parameter_validation",
        "Canonical percentile domain maximum.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.utils.RGB_CHANNEL_COUNT",
        ParameterRole.STANDARD_TRANSFORM,
        "channel_count",
        "image",
        "Canonical RGB array channel count.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.utils.RGBA_CHANNEL_COUNT",
        ParameterRole.STANDARD_TRANSFORM,
        "channel_count",
        "image",
        "Canonical RGBA array channel count.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.image.evidence.CONTENT_EVIDENCE_COMPONENT_COUNT",
        ParameterRole.STANDARD_TRANSFORM,
        "component_count",
        "content_evidence",
        "Canonical number of independent content-evidence components.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.image.statistics.INTENSITY_QUANTILE_COUNT",
        ParameterRole.STANDARD_TRANSFORM,
        "quantile_count",
        "preprocess",
        "Canonical intensity statistics tuple shape.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.image.statistics.DISTRIBUTION_QUANTILE_COUNT",
        ParameterRole.STANDARD_TRANSFORM,
        "quantile_count",
        "preprocess",
        "Canonical noise and edge statistics tuple shape.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.entry.cli.CLI_USAGE_ERROR_EXIT_CODE",
        ParameterRole.STANDARD_TRANSFORM,
        "process_exit_code",
        "entry",
        "Canonical command-line usage failure exit code.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.detection.modes.dual_lane_split.DUAL_LANE_COUNT",
        ParameterRole.PHYSICAL_FACT,
        "lane_count",
        "dual_lane_proposal",
        "Canonical lane count supported by dual-lane physical composition.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.detection.physical.separator.assignment.BOUNDARY_ADJACENT_FRAME_COUNT",
        ParameterRole.PHYSICAL_FACT,
        "frame_count",
        "separator_assignment",
        "Each internal separator boundary must leave one physical frame on both sides.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.runtime.limits.STANDARD_JOB_LIMIT",
        ParameterRole.EXECUTION_BUDGET,
        "worker_count",
        "runtime",
        "Bounds standard process concurrency.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.runtime.limits.DIAGNOSTICS_JOB_LIMIT",
        ParameterRole.EXECUTION_BUDGET,
        "worker_count",
        "runtime",
        "Bounds diagnostics process concurrency.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.runtime.options.DEFAULT_DESKEW_MIN_ANGLE_DEGREES",
        ParameterRole.USER_PREFERENCE,
        "degrees",
        "deskew",
        "Default user-facing minimum deskew angle.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.runtime.options.DEFAULT_DESKEW_MAX_ANGLE_DEGREES",
        ParameterRole.USER_PREFERENCE,
        "degrees",
        "deskew",
        "Default user-facing maximum deskew angle.",
        "fixed_by_contract",
    ),
    ParameterContract(
        "x5crop.runtime.options.DEFAULT_OUTPUT_BLEED",
        ParameterRole.USER_PREFERENCE,
        "px",
        "output",
        "Default user-facing output margin.",
        "fixed_by_contract",
    ),
)


EXPLICIT_PARAMETER_MODELS = frozenset(
    {
        FormatPhysicalSpec,
        FrameSizeMm,
        RunConfig,
        RuntimeOptions,
    }
)


def _is_numeric_annotation(annotation: Any) -> bool:
    if isinstance(annotation, str):
        return any(token in annotation for token in ("int", "float", "bool"))
    if annotation in {int, float, bool}:
        return True
    origin = get_origin(annotation)
    if origin in {tuple, list, set, frozenset, UnionType}:
        return any(_is_numeric_annotation(item) for item in get_args(annotation))
    return False


def parameter_models() -> frozenset[type]:
    models: set[type] = set()
    for module_name in source_modules():
        module = importlib.import_module(module_name)
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and value.__module__ == module_name
                and is_dataclass(value)
                and (
                    value.__name__.endswith(("Parameters", "Configuration"))
                    or value in EXPLICIT_PARAMETER_MODELS
                )
                and any(_is_numeric_annotation(field.type) for field in fields(value))
            ):
                models.add(value)
    return frozenset(models)


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
    for contract in CONSTANT_PARAMETER_CONTRACTS:
        if contract.owner in contracts:
            raise AssertionError(f"duplicate parameter contract: {contract.owner}")
        contracts[contract.owner] = contract
    return contracts


def numeric_module_constant_owners() -> frozenset[str]:
    owners: set[str] = set()
    for module_name, module in source_modules().items():
        for node in parsed_source(module).body:
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.AnnAssign):
                targets = (node.target,)
                value = node.value
            else:
                continue
            if value is None or not any(
                isinstance(child, ast.Constant)
                and isinstance(child.value, (int, float))
                and not isinstance(child.value, bool)
                for child in ast.walk(value)
            ):
                continue
            owners.update(
                f"{module_name}.{target.id}"
                for target in targets
                if isinstance(target, ast.Name)
                and target.id.isupper()
                and not target.id.startswith("_")
            )
    return frozenset(owners)


def declared_parameter_owners() -> frozenset[str]:
    fields_owners = {
        f"{model.__module__}.{model.__name__}.{field.name}"
        for model in parameter_models()
        for field in fields(model)
        if _is_numeric_annotation(field.type)
    }
    return frozenset(fields_owners) | numeric_module_constant_owners()


def unclassified_parameter_owners() -> list[str]:
    classified = set(parameter_contracts())
    declared = declared_parameter_owners()
    return sorted(declared - classified)


def stale_parameter_contracts() -> list[str]:
    declared = declared_parameter_owners()
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


def hidden_runtime_percentiles() -> list[str]:
    offenders: list[str] = []
    root = PROJECT_ROOT / "x5crop"
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


_STRUCTURAL_NUMERIC_LITERALS = frozenset({-1, 0, 1})


def _structural_compare(node: ast.Constant, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    while parent is not None and not isinstance(
        parent,
        (ast.Compare, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
    ):
        parent = parents.get(parent)
    if not isinstance(parent, ast.Compare):
        return False
    expression = ast.unparse(parent)
    return any(
        marker in expression
        for marker in ("len(", "shape", ".ndim", "lane_count")
    )


def _structural_subscript_or_slice(
    node: ast.Constant,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    parent = parents.get(node)
    if isinstance(parent, (ast.Subscript, ast.Slice)):
        return True
    if (
        isinstance(parent, ast.Tuple)
        and isinstance(parents.get(parent), ast.Subscript)
        and parents[parent].slice is parent
    ):
        return True
    return bool(
        isinstance(parent, ast.UnaryOp)
        and isinstance(parents.get(parent), ast.Subscript)
        and parents[parent].slice is parent
    )


def _structural_keyword(node: ast.Constant, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    return bool(
        isinstance(parent, ast.keyword)
        and parent.arg in {"axis", "start"}
    )


def _structural_formula(node: ast.Constant, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    if not isinstance(parent, ast.BinOp):
        return False
    if isinstance(parent.op, ast.Pow) and parent.right is node:
        return node.value in {2, 0.5}
    other = parent.left if parent.right is node else parent.right
    if (
        isinstance(parent.op, (ast.Div, ast.FloorDiv))
        and parent.right is node
        and node.value in {2, 2.0}
    ) or (
        isinstance(parent.op, ast.Mult)
        and node.value == 0.5
    ):
        names = {
            item.id
            for item in ast.walk(other)
            if isinstance(item, ast.Name)
        } | {
            item.attr
            for item in ast.walk(other)
            if isinstance(item, ast.Attribute)
        }
        coordinate_terms = {
            "center",
            "center_y",
            "position",
            "midpoint",
            "start",
            "end",
            "left",
            "right",
            "top",
            "bottom",
            "width",
            "height",
            "minimum",
            "maximum",
            "w",
            "h",
            "out_w",
            "out_h",
            "t",
            "band_width",
        }
        return bool(
            names & coordinate_terms
            or any(
                name.endswith(
                    (
                        "_start",
                        "_end",
                        "_left",
                        "_right",
                        "_top",
                        "_bottom",
                        "_width",
                        "_height",
                    )
                )
                for name in names
            )
        )
    return False


def _is_structural_numeric_literal(
    node: ast.Constant,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    return bool(
        node.value in _STRUCTURAL_NUMERIC_LITERALS
        or _structural_subscript_or_slice(node, parents)
        or _structural_keyword(node, parents)
        or _structural_compare(node, parents)
        or _structural_formula(node, parents)
    )


def hidden_runtime_numeric_literals() -> list[str]:
    offenders: list[str] = []
    root = PROJECT_ROOT / "x5crop"
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if (
                not isinstance(node, ast.Constant)
                or isinstance(node.value, bool)
                or not isinstance(node.value, (int, float))
                or _is_structural_numeric_literal(node, parents)
            ):
                continue
            parent = parents.get(node)
            while parent is not None and not isinstance(
                parent,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
            ):
                parent = parents.get(parent)
            if parent is not None:
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT).as_posix()}:{node.lineno}:{node.value}"
                )
    return sorted(offenders)
