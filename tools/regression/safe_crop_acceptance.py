"""Run the blocking nine-source, fourteen-scenario gold acceptance."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

from x5crop.io.tiff import read_tiff
from x5crop.report.validation import validate_current_report_record

from .golden_baseline import (
    compare_gold_record_to_report,
    load_gold_records,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_NAME = "gold_accuracy_results.jsonl"
SUMMARY_NAME = "gold_accuracy_summary.json"
RESULT_SCHEMA = "x5crop_gold_accuracy_result_v3"
SUMMARY_SCHEMA = "x5crop_gold_accuracy_summary_v3"


class AcceptancePreflightError(ValueError):
    pass


@dataclass(frozen=True)
class AcceptanceScenario:
    record: dict[str, Any]
    source_path: Path
    count_mode: str
    expectation: str

    @property
    def sample_id(self) -> str:
        return str(self.record["sample_id"])

    @property
    def scenario_id(self) -> str:
        return f"{self.sample_id}:{self.count_mode}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_output_root(output_root: Path) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        raise AcceptancePreflightError(
            f"gold output root must be empty: {output_root}"
        )


def acceptance_preflight(
    output_root: Path,
) -> tuple[AcceptanceScenario, ...]:
    _validate_output_root(output_root)
    project_root = PROJECT_ROOT.resolve()
    scenarios: list[AcceptanceScenario] = []
    for record in load_gold_records():
        relative = Path(str(record["source_relative_path"]))
        source_path = (PROJECT_ROOT / relative).resolve()
        geometry = record["confirmed_geometry"]
        if (
            relative.is_absolute()
            or not source_path.is_relative_to(project_root)
            or not source_path.is_file()
            or _sha256(source_path) != record["source_sha256"]
        ):
            raise AcceptancePreflightError(
                f"gold source identity is unavailable: {record['sample_id']}"
            )
        array, _profile, _warnings = read_tiff(source_path, 0)
        if (
            int(array.shape[1]) != int(geometry["raw_width_px"])
            or int(array.shape[0]) != int(geometry["raw_height_px"])
        ):
            raise AcceptancePreflightError(
                f"gold source extent changed: {record['sample_id']}"
            )
        for count_mode in record["count_modes"]:
            scenarios.append(
                AcceptanceScenario(
                    record=record,
                    source_path=source_path,
                    count_mode=count_mode,
                    expectation=record["decision_expectations"][
                        count_mode
                    ],
                )
            )
    if len(scenarios) != 14:
        raise AcceptancePreflightError(
            "gold acceptance requires exactly fourteen scenarios"
        )
    if (
        sum(
            scenario.expectation == "must_approve_safe"
            for scenario in scenarios
        )
        != 12
        or sum(
            scenario.expectation
            == "must_review_with_competition"
            for scenario in scenarios
        )
        != 2
    ):
        raise AcceptancePreflightError(
            "gold decision expectations must be twelve approved and two review"
        )
    return tuple(scenarios)


def _load_single_report(path: Path) -> dict[str, Any]:
    rows = tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if len(rows) != 1:
        raise RuntimeError(f"{path} must contain exactly one report")
    validate_current_report_record(rows[0])
    return rows[0]


def _validated_tiff_outputs(
    report: dict[str, Any],
    scenario_root: Path,
) -> tuple[bool, tuple[str, ...]]:
    output_files = tuple(
        Path(path) for path in report["output"]["output_files"]
    )
    if report["decision"]["status"] == "needs_review":
        return not output_files, ()
    validated: list[str] = []
    for path in output_files:
        resolved = path if path.is_absolute() else scenario_root / path
        if not resolved.is_file():
            return False, tuple(validated)
        try:
            array, _profile, _warnings = read_tiff(resolved, 0)
        except Exception:
            return False, tuple(validated)
        if array.size <= 0:
            return False, tuple(validated)
        validated.append(str(resolved))
    expected = report["output"]["finalization"]["output_slot_count"]
    return (
        isinstance(expected, int)
        and len(validated) == expected,
        tuple(validated),
    )


def _terminal_failure(
    scenario: AcceptanceScenario,
    failure: str,
) -> dict[str, Any]:
    return {
        "result_schema": RESULT_SCHEMA,
        "scenario_id": scenario.scenario_id,
        "sample_id": scenario.sample_id,
        "source_sha256": scenario.record["source_sha256"],
        "count_mode": scenario.count_mode,
        "expectation": scenario.expectation,
        "decision_status": "terminal_failure",
        "final_review_reasons": [],
        "candidate_gate_blocking_codes": [],
        "comparison": None,
        "official_tiff_count": 0,
        "tiff_readback_validated": False,
        "passed": False,
        "failure": failure,
    }


def _run_scenario(
    scenario: AcceptanceScenario,
    output_root: Path,
) -> dict[str, Any]:
    scenario_root = (
        output_root
        / "scenarios"
        / scenario.scenario_id.replace(":", "_")
    )
    scenario_root.mkdir(parents=True, exist_ok=False)
    geometry = scenario.record["confirmed_geometry"]
    command = [
        sys.executable,
        str(PROJECT_ROOT / "X5_Crop.py"),
        str(scenario.source_path),
        "--output",
        str(scenario_root),
        "--format",
        str(scenario.record["format_id"]),
        "--strip",
        str(scenario.record["strip_mode"]),
        "--layout",
        str(geometry["strip_orientation"]),
        "--compression",
        "same",
        "--jobs",
        "1",
        "--report",
        "--debug-analysis",
        "--debug-errors",
        "--no-copy-review-files",
    ]
    if scenario.count_mode == "explicit":
        command.extend(
            (
                "--count",
                str(scenario.record["confirmed_photo_count"]),
            )
        )
    elif scenario.count_mode == "auto":
        command.extend(("--count", "auto"))
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    report_path = scenario_root / "x5_crop_report.jsonl"
    if completed.returncode != 0 or not report_path.is_file():
        return _terminal_failure(
            scenario,
            (
                f"runtime exit {completed.returncode}: "
                f"{completed.stdout[-2000:]}"
            ),
        )
    try:
        report = _load_single_report(report_path)
        comparison = compare_gold_record_to_report(
            scenario.record,
            report,
            count_mode=scenario.count_mode,
        )
        tiff_valid, validated_outputs = _validated_tiff_outputs(
            report,
            scenario_root,
        )
    except Exception as exc:
        return _terminal_failure(
            scenario,
            f"{type(exc).__name__}: {exc}",
        )
    status = report["decision"]["status"]
    finalization = report["output"]["finalization"]
    review_has_no_official_output = (
        status != "needs_review"
        or (
            finalization["official_tiff_expected"] is False
            and finalization["official_tiff_count"] == 0
            and not report["output"]["output_files"]
            and not finalization["resolved_output_geometries"]
        )
    )
    gate_blocking = tuple(
        item["code"]
        for item in report["candidate_gate"]["checks"]
        if item["blocks"]
    )
    passed = (
        bool(comparison["passed"])
        and tiff_valid
        and review_has_no_official_output
    )
    return {
        "result_schema": RESULT_SCHEMA,
        "scenario_id": scenario.scenario_id,
        "sample_id": scenario.sample_id,
        "source_sha256": scenario.record["source_sha256"],
        "count_mode": scenario.count_mode,
        "expectation": scenario.expectation,
        "decision_status": status,
        "final_review_reasons": list(
            report["decision"]["final_review_reasons"]
        ),
        "candidate_gate_blocking_codes": list(gate_blocking),
        "comparison": comparison,
        "official_tiff_count": finalization["official_tiff_count"],
        "tiff_readback_validated": tiff_valid,
        "validated_tiff_outputs": list(validated_outputs),
        "passed": passed,
        "failure": None if passed else "gold_acceptance_contract_failed",
    }


def validate_acceptance_result_record(record: dict[str, Any]) -> None:
    if (
        record.get("result_schema") != RESULT_SCHEMA
        or record.get("decision_status")
        not in {"approved_auto", "needs_review", "terminal_failure"}
        or not isinstance(record.get("passed"), bool)
        or record.get("expectation")
        not in {
            "must_approve_safe",
            "must_review_with_competition",
        }
    ):
        raise ValueError("gold result does not use the current schema")


def validate_acceptance_summary_record(record: dict[str, Any]) -> None:
    if (
        record.get("summary_schema") != SUMMARY_SCHEMA
        or record.get("accuracy_authority")
        != "nine_source_sha_bound_user_confirmed_gold"
        or record.get("diagnostic_111_accuracy_verdict")
        != "not_applicable"
        or not isinstance(record.get("passed"), bool)
    ):
        raise ValueError("gold summary does not use the current schema")


def run_acceptance(
    output_root: Path,
) -> tuple[bool, dict[str, Any]]:
    scenarios = acceptance_preflight(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    results = tuple(
        _run_scenario(scenario, output_root)
        for scenario in scenarios
    )
    for result in results:
        validate_acceptance_result_record(result)
    (output_root / RESULTS_NAME).write_text(
        "".join(
            json.dumps(result, ensure_ascii=False) + "\n"
            for result in results
        ),
        encoding="utf-8",
    )
    passed = all(result["passed"] for result in results)
    summary = {
        "summary_schema": SUMMARY_SCHEMA,
        "accuracy_authority": (
            "nine_source_sha_bound_user_confirmed_gold"
        ),
        "scenario_count": len(results),
        "approved_expectation_count": sum(
            result["expectation"] == "must_approve_safe"
            for result in results
        ),
        "review_expectation_count": sum(
            result["expectation"]
            == "must_review_with_competition"
            for result in results
        ),
        "passed_scenario_count": sum(
            bool(result["passed"]) for result in results
        ),
        "failed_scenario_count": sum(
            not bool(result["passed"]) for result in results
        ),
        "nominal_sample_count": sum(
            record["calibration_role"] == "nominal"
            for record in load_gold_records()
        ),
        "stress_excluded_sample_count": sum(
            record["calibration_role"] == "stress_excluded"
            for record in load_gold_records()
        ),
        "diagnostic_111_accuracy_verdict": "not_applicable",
        "passed": passed,
    }
    validate_acceptance_summary_record(summary)
    (output_root / SUMMARY_NAME).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return passed, summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run tracked V4.9 gold accuracy acceptance"
    )
    parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        passed, summary = run_acceptance(
            args.output_root.expanduser().resolve()
        )
    except AcceptancePreflightError as exc:
        print(f"preflight error: {exc}", file=sys.stderr)
        return 2
    print(
        f"gold accuracy: {summary['passed_scenario_count']}/"
        f"{summary['scenario_count']} passed"
    )
    print(f"artifacts: {args.output_root.expanduser().resolve()}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
