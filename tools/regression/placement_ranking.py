"""Source-grouped development ranking; never a probability or admission gate."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Sequence

import numpy as np

from x5crop.detection.photo_geometry.template_acceptability_features import (
    PLACEMENT_FEATURE_DEFINITIONS,
    PLACEMENT_FEATURE_SCHEMA,
)
from .file_identity import sha256_file
from .gold_analysis import (
    ANALYSIS_RECORD_SCHEMA, RETAINED_PLACEMENT_SCOPE,
    _analysis_identity, validate_gold_analysis_artifacts,
)
from .report_validation import validate_placement_feature_record


RANKING_SCHEMA = "x5crop_development_placement_ranking_v1"
MODEL_SPEC = "source_balanced_standardized_ridge_ranking_v1"
RANKING_RULE = "maximum_score_then_retained_order_v1"
FOLD_COUNT = 5
RIDGE_PENALTY = 0.1
FEATURE_NAMES = tuple(item.name for item in PLACEMENT_FEATURE_DEFINITIONS)
_FEATURE_COUNT = len(FEATURE_NAMES)
_SOURCE_SHA = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class RankingExample:
    sample_id: str
    source_sha256: str
    placement_id: str
    role: str
    gold_safe: bool
    features: tuple[float | None, ...]

    def __post_init__(self) -> None:
        if (
            not self.sample_id or not self.placement_id
            or not _SOURCE_SHA.fullmatch(self.source_sha256)
            or self.role not in {"primary", "runner"}
            or type(self.gold_safe) is not bool
            or len(self.features) != _FEATURE_COUNT
            or any(value is not None and (
                type(value) not in {int, float} or not math.isfinite(value) or value < 0.0
            ) for value in self.features)
        ):
            raise ValueError("development ranking example is invalid")


def _examples(records: Sequence[dict[str, Any]]) -> tuple[RankingExample, ...]:
    result = []
    for record in records:
        for candidate in record["retained_placement_gold_labels"]:
            conformance = candidate["geometry_conformance"]
            if conformance == "not_available":
                continue
            if conformance not in {"safe", "unsafe"} or candidate["generation_state"] != "generated":
                raise ValueError("ranking labels require generated gold-checked footprints")
            features = validate_placement_feature_record(
                candidate["acceptability_features"], placement_id=candidate["placement_id"],
                lane_id=candidate["lane_id"],
                output_geometry_ids=[item["geometry_id"] for item in candidate["output_footprints"]],
            )
            result.append(RankingExample(
                record["sample_id"], record["source_sha256"], candidate["placement_id"],
                candidate["role"], conformance == "safe", tuple(item.value for item in features.values),
            ))
    identities = [(item.sample_id, item.placement_id) for item in result]
    if len(set(identities)) != len(identities):
        raise ValueError("ranking candidates have duplicate task identities")
    return tuple(result)


def _source_weights(examples: Sequence[RankingExample]) -> np.ndarray:
    counts = Counter(item.source_sha256 for item in examples)
    if not counts:
        raise ValueError("ranking needs at least one generated candidate")
    return np.asarray([1.0 / (len(counts) * counts[item.source_sha256]) for item in examples])


def _raw_features(examples: Sequence[RankingExample]) -> np.ndarray:
    return np.asarray([
        [np.nan if value is None else value for value in item.features]
        for item in examples
    ], dtype=np.float64).reshape(len(examples), _FEATURE_COUNT)


def _training_transform(examples: Sequence[RankingExample]) -> dict[str, Any]:
    """Fit location/scale on training sources only; missingness stays explicit."""

    raw = _raw_features(examples)
    weights = _source_weights(examples)
    centers, scales, minimums, maximums, missing_seen = [], [], [], [], []
    for column in raw.T:
        observed = np.isfinite(column)
        missing_seen.append(bool(np.any(~observed)))
        if not np.any(observed):
            centers.append(0.0)
            scales.append(1.0)
            minimums.append(None)
            maximums.append(None)
            continue
        values = column[observed]
        observed_weights = weights[observed] / weights[observed].sum()
        minimum, maximum = float(values.min()), float(values.max())
        center = minimum if minimum == maximum else float(observed_weights @ values)
        variance = float(observed_weights @ ((values - center) ** 2))
        centers.append(center)
        scales.append(1.0 if minimum == maximum else math.sqrt(variance))
        minimums.append(minimum)
        maximums.append(maximum)
    return {"centers": centers, "scales": scales, "observed_minimums": minimums,
            "observed_maximums": maximums, "missing_seen": missing_seen}


def _design(examples: Sequence[RankingExample], model: dict[str, Any]) -> np.ndarray:
    raw = _raw_features(examples)
    observed = np.isfinite(raw)
    standardized = np.where(observed, (raw - model["centers"]) / model["scales"], 0.0)
    return np.column_stack((standardized, (~observed).astype(float), np.ones(len(examples))))


def _model_id(model: dict[str, Any]) -> str:
    payload = {key: value for key, value in model.items() if key != "model_id"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return f"{MODEL_SPEC}:{hashlib.sha256(encoded).hexdigest()}"


def _fit_model(examples: Sequence[RankingExample]) -> dict[str, Any]:
    model = {
        "model_spec": MODEL_SPEC, "feature_schema_id": PLACEMENT_FEATURE_SCHEMA,
        "feature_order": list(FEATURE_NAMES), "ridge_penalty": RIDGE_PENALTY,
        "training_source_sha256s": sorted({item.source_sha256 for item in examples}),
        "training_candidate_count": len(examples),
        **_training_transform(examples),
    }
    design = _design(examples, model)
    weights = _source_weights(examples)
    labels = np.asarray([float(item.gold_safe) for item in examples])
    penalty = np.eye(design.shape[1]) * RIDGE_PENALTY
    penalty[-1, -1] = 0.0  # The intercept is not regularized.
    parameters = np.linalg.solve(design.T @ (weights[:, None] * design) + penalty,
                                 design.T @ (weights * labels))
    model["coefficients"] = parameters[:-1].tolist()
    model["intercept"] = float(parameters[-1])
    residual = design @ parameters - labels
    model["weighted_squared_error"] = float(weights @ (residual ** 2))
    model["model_id"] = _model_id(model)
    _validate_fitted_model(model, examples)
    return model


def _scores(examples: Sequence[RankingExample], model: dict[str, Any]) -> np.ndarray:
    return _design(examples, model) @ np.asarray([*model["coefficients"], model["intercept"]])


def _validate_fitted_model(model: dict[str, Any], examples: Sequence[RankingExample]) -> None:
    """Check the training-only transform and ridge normal equations, without refitting."""

    transform = _training_transform(examples)
    if (
        model.get("model_spec") != MODEL_SPEC or model.get("feature_schema_id") != PLACEMENT_FEATURE_SCHEMA
        or model.get("feature_order") != list(FEATURE_NAMES)
        or model.get("ridge_penalty") != RIDGE_PENALTY
        or model.get("training_source_sha256s") != sorted({item.source_sha256 for item in examples})
        or model.get("training_candidate_count") != len(examples)
        or any(model.get(key) != value for key, value in transform.items())
        or model.get("model_id") != _model_id(model)
    ):
        raise ValueError("development ranking model provenance is invalid")
    parameters = np.asarray([*model["coefficients"], model["intercept"]], dtype=np.float64)
    if parameters.shape != (2 * _FEATURE_COUNT + 1,) or not np.all(np.isfinite(parameters)):
        raise ValueError("development ranking parameters are invalid")
    design = _design(examples, model)
    weights = _source_weights(examples)
    residual = design @ parameters - np.asarray([float(item.gold_safe) for item in examples])
    gradient = design.T @ (weights * residual)
    gradient[:-1] += RIDGE_PENALTY * parameters[:-1]
    if (
        float(np.max(np.abs(gradient))) > 1.0e-8
        or not math.isclose(float(weights @ (residual ** 2)), model["weighted_squared_error"], rel_tol=1.0e-10, abs_tol=1.0e-12)
    ):
        raise ValueError("development ranking model does not solve its declared training objective")


def _fold_assignments(records: Sequence[dict[str, Any]]) -> dict[str, int]:
    sources = sorted({record["source_sha256"] for record in records})
    if any(not isinstance(source, str) or not _SOURCE_SHA.fullmatch(source) for source in sources):
        raise ValueError("development ranking requires valid source SHA identities")
    if len({record["sample_id"] for record in records}) != len(records):
        raise ValueError("development ranking requires unique task identities")
    if len(sources) < FOLD_COUNT:
        raise ValueError(f"development ranking requires at least {FOLD_COUNT} source groups")
    return {source: index % FOLD_COUNT for index, source in enumerate(sources)}


def _support_issues(example: RankingExample, model: dict[str, Any]) -> list[dict[str, str]]:
    issues = []
    for index, value in enumerate(example.features):
        lower, upper = model["observed_minimums"][index], model["observed_maximums"][index]
        reason = (
            "missing_without_training_support" if value is None and not model["missing_seen"][index]
            else "observed_without_training_support" if value is not None and lower is None
            else "outside_training_range" if value is not None and not lower <= value <= upper
            else None
        )
        if reason is not None:
            issues.append({"feature": FEATURE_NAMES[index], "reason": reason})
    return issues


def _evaluate(
    records: Sequence[dict[str, Any]], examples: Sequence[RankingExample],
    model_by_source: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    by_task: dict[str, list[RankingExample]] = {record["sample_id"]: [] for record in records}
    for example in examples:
        by_task[example.sample_id].append(example)
    tasks = []
    for record in records:
        candidates = by_task[record["sample_id"]]
        model = model_by_source[record["source_sha256"]]
        scores = _scores(candidates, model)
        # max returns the first equal score: the original primary/runner order.
        ranked_index = max(range(len(candidates)), key=lambda index: scores[index]) if candidates else None
        ranked = None if ranked_index is None else candidates[ranked_index]
        primary = next((item for item in candidates if item.role == "primary"), None)
        tasks.append({
            "sample_id": record["sample_id"], "source_sha256": record["source_sha256"],
            "cohort_role": record["cohort_role"], "model_id": model["model_id"],
            "ranked_placement_id": None if ranked is None else ranked.placement_id,
            "primary_geometry_conformance": "not_available" if primary is None else "safe" if primary.gold_safe else "unsafe",
            "ranked_geometry_conformance": "not_available" if ranked is None else "safe" if ranked.gold_safe else "unsafe",
            "at_least_one_safe_retained": any(item.gold_safe for item in candidates),
            "margin": None if len(scores) < 2 else float(sorted(scores)[-1] - sorted(scores)[-2]),
            "candidates": [{
                "placement_id": item.placement_id, "role": item.role, "ranking_score": float(score),
                "geometry_conformance": "safe" if item.gold_safe else "unsafe",
                "development_support_issues": _support_issues(item, model),
            } for item, score in zip(candidates, scores, strict=True)],
            "unavailable_placement_ids": [item["placement_id"] for item in record["retained_placement_gold_labels"]
                                          if item["geometry_conformance"] == "not_available"],
        })
    summary = {
        "task_count": len(tasks),
        "primary_geometry_conformance_counts": dict(sorted(Counter(item["primary_geometry_conformance"] for item in tasks).items())),
        "ranked_geometry_conformance_counts": dict(sorted(Counter(item["ranked_geometry_conformance"] for item in tasks).items())),
        "at_least_one_safe_retained_task_count": sum(item["at_least_one_safe_retained"] for item in tasks),
        "safe_ranked_with_support_issue_task_ids": [item["sample_id"] for item in tasks if item["ranked_geometry_conformance"] == "safe"
            and any(candidate["placement_id"] == item["ranked_placement_id"] and candidate["development_support_issues"] for candidate in item["candidates"])],
        "improvement_task_ids": [item["sample_id"] for item in tasks if item["primary_geometry_conformance"] != "safe" and item["ranked_geometry_conformance"] == "safe"],
        "regression_task_ids": [item["sample_id"] for item in tasks if item["primary_geometry_conformance"] == "safe" and item["ranked_geometry_conformance"] != "safe"],
    }
    return {"summary": summary, "tasks": tasks}


def build_development_ranking(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    examples = _examples(records)
    folds = _fold_assignments(records)
    fold_models = [_fit_model([item for item in examples if folds[item.source_sha256] != fold]) for fold in range(FOLD_COUNT)]
    full_model = _fit_model(examples)
    return {
        "ranking_schema": RANKING_SCHEMA, "validation_role": "development_ranking_not_independent_acceptance",
        "feature_schema_id": PLACEMENT_FEATURE_SCHEMA, "label_record_schema": ANALYSIS_RECORD_SCHEMA,
        "retained_placement_scope": RETAINED_PLACEMENT_SCOPE,
        "score_semantics": "unbounded_linear_ranking_score_not_probability",
        "calibration_id": None, "admission_enabled": False, "formal_ood_evaluated": False,
        "support_check_scope": "numeric_feature_ranges_and_missingness_only",
        "ranking_rule_id": RANKING_RULE, "fold_count": FOLD_COUNT,
        "weighting": "equal_source_total_weight_then_equal_generated_candidate_weight_within_source",
        "fold_assignment": folds, "fold_models": fold_models, "development_fit_model": full_model,
        "source_grouped_oof": _evaluate(records, examples, {source: fold_models[fold] for source, fold in folds.items()}),
        "in_sample": _evaluate(records, examples, {source: full_model for source in folds}),
    }


def validate_development_ranking(artifact: dict[str, Any], records: Sequence[dict[str, Any]]) -> None:
    examples = _examples(records)
    folds = _fold_assignments(records)
    if (
        artifact.get("ranking_schema") != RANKING_SCHEMA
        or artifact.get("validation_role") != "development_ranking_not_independent_acceptance"
        or artifact.get("retained_placement_scope") != RETAINED_PLACEMENT_SCOPE
        or artifact.get("support_check_scope") != "numeric_feature_ranges_and_missingness_only"
        or artifact.get("weighting") != "equal_source_total_weight_then_equal_generated_candidate_weight_within_source"
        or artifact.get("feature_schema_id") != PLACEMENT_FEATURE_SCHEMA
        or artifact.get("label_record_schema") != ANALYSIS_RECORD_SCHEMA
        or artifact.get("score_semantics") != "unbounded_linear_ranking_score_not_probability"
        or artifact.get("calibration_id") is not None or artifact.get("admission_enabled") is not False
        or artifact.get("formal_ood_evaluated") is not False
        or artifact.get("ranking_rule_id") != RANKING_RULE
        or artifact.get("fold_count") != FOLD_COUNT or artifact.get("fold_assignment") != folds
        or len(artifact.get("fold_models", ())) != FOLD_COUNT
    ):
        raise ValueError("development ranking artifact contract is invalid")
    for fold, model in enumerate(artifact["fold_models"]):
        _validate_fitted_model(model, [item for item in examples if folds[item.source_sha256] != fold])
    _validate_fitted_model(artifact["development_fit_model"], examples)
    if (
        artifact["source_grouped_oof"] != _evaluate(records, examples, {source: artifact["fold_models"][fold] for source, fold in folds.items()})
        or artifact["in_sample"] != _evaluate(records, examples, {source: artifact["development_fit_model"] for source in folds})
    ):
        raise ValueError("development ranking artifact predictions or aggregation changed")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--analysis-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = validate_gold_analysis_artifacts(args.analysis_root)
        current = _analysis_identity()
        identity = summary["analysis_identity"]
        if summary["analysis_error_count"] or any(identity[key] != current[key] for key in (
            "detector_source_manifest_sha256", "comparator_source_manifest_sha256", "development_gold_cohort_sha256",
        )) or not identity["detector_paths_match_head"] or not identity["comparator_paths_match_head"]:
            raise ValueError("ranking requires complete current-source gold analysis")
        records_path = args.analysis_root / "gold_analysis_records.jsonl"
        records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        artifact = build_development_ranking(records)
        artifact["input_identity"] = {
            "analysis_identity": identity, "records_sha256": sha256_file(records_path),
            "summary_sha256": sha256_file(args.analysis_root / "gold_analysis_summary.json"),
            "ranking_tool_sha256": sha256_file(Path(__file__)),
        }
        validate_development_ranking(artifact, records)
        args.output_root.mkdir(parents=True, exist_ok=False)
        output = args.output_root / "placement_ranking.json"
        output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        validate_development_ranking(json.loads(output.read_text(encoding="utf-8")), records)
        print(json.dumps({"output": str(output), "source_grouped_oof": artifact["source_grouped_oof"]["summary"],
                          "in_sample": artifact["in_sample"]["summary"], "admission_enabled": False}, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"development placement ranking: FAIL: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
