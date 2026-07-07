"""Reference comparison classification for X5 Crop reports."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from x5crop.app_info import REPORT_JSONL_NAME, VERSION
from .compare import load_jsonl_report, report_key


GEOMETRY_FIELDS = ("outer_box", "frame_boxes", "gaps")


REFERENCE_CASES = {
    "standard_strip_full": (
        Path("Test/135/4.5.4/split_report.jsonl"),
        Path("135") / VERSION / REPORT_JSONL_NAME,
    ),
    "wide_spacing_standard_strip_full": (
        Path("Test/new_135/4.5.4/split_report.jsonl"),
        Path("new_135") / VERSION / REPORT_JSONL_NAME,
    ),
    "medium_square_full": (
        Path("Test/120/66/4.5.4/split_report.jsonl"),
        Path("120/66") / VERSION / REPORT_JSONL_NAME,
    ),
    "medium_square_partial": (
        Path("Test/120/66/4.5.4_partial/split_report.jsonl"),
        Path("120/66") / f"{VERSION}_partial" / REPORT_JSONL_NAME,
    ),
    "medium_wide_full": (
        Path("Test/120/67/4.5.4/split_report.jsonl"),
        Path("120/67") / VERSION / REPORT_JSONL_NAME,
    ),
    "dense_half_frame_full": (
        Path("Test/半格/full/4.5.4/split_report.jsonl"),
        Path("半格/full") / VERSION / REPORT_JSONL_NAME,
    ),
    "dense_half_frame_partial": (
        Path("Test/半格/partial/4.5.4_partial/split_report.jsonl"),
        Path("半格/partial") / f"{VERSION}_partial" / REPORT_JSONL_NAME,
    ),
}


@dataclass(frozen=True)
class ClassifiedDiff:
    source: str
    classification: str
    reason_summary: str


def geometry_equal(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return all(before.get(field) == after.get(field) for field in GEOMETRY_FIELDS)


def reason_summary(row: dict[str, Any]) -> str:
    reasons = row.get("review_reasons", [])
    if isinstance(reasons, list) and reasons:
        return ",".join(str(reason) for reason in reasons[:6])
    detail = row.get("detail", {})
    if isinstance(detail, dict):
        decision = detail.get("decision_summary", {})
        if isinstance(decision, dict):
            added = decision.get("final_review_reasons_added", [])
            if isinstance(added, list) and added:
                return ",".join(str(reason) for reason in added[:6])
            final = decision.get("final_review_reasons", [])
            if isinstance(final, list) and final:
                return ",".join(str(reason) for reason in final[:6])
    return "none"


def classify_pair(before: dict[str, Any], after: dict[str, Any]) -> str:
    before_status = str(before.get("status", ""))
    after_status = str(after.get("status", ""))
    if before_status == "approved_auto" and after_status == "needs_review":
        return "safer_review"
    if before_status == "needs_review" and after_status == "approved_auto":
        return "unacceptable_wrong_pass"
    if before_status == after_status and geometry_equal(before, after):
        core_same = (
            before.get("confidence") == after.get("confidence")
            and before.get("review_reasons") == after.get("review_reasons")
        )
        return "same" if core_same else "metadata/schema diff"
    if after_status == "needs_review":
        return "safer_review"
    if before_status == "approved_auto" and after_status == "approved_auto":
        return "risky_regression"
    return "risky_regression"


def classify_reports(baseline_path: Path, candidate_path: Path) -> list[ClassifiedDiff]:
    baseline = {report_key(row): row for row in load_jsonl_report(baseline_path)}
    candidate = {report_key(row): row for row in load_jsonl_report(candidate_path)}
    diffs: list[ClassifiedDiff] = []
    for key in sorted(set(baseline) | set(candidate)):
        if key not in baseline:
            diffs.append(ClassifiedDiff(key, "risky_regression", "added row"))
            continue
        if key not in candidate:
            diffs.append(ClassifiedDiff(key, "risky_regression", "missing candidate row"))
            continue
        classification = classify_pair(baseline[key], candidate[key])
        diffs.append(
            ClassifiedDiff(
                key,
                classification,
                reason_summary(candidate[key]),
            )
        )
    return diffs


def run_cases(repo_root: Path, candidate_root: Path, json_output: bool = False) -> int:
    all_counts: dict[str, int] = {}
    payload: dict[str, Any] = {}
    unacceptable = 0
    risky = 0
    for name, (baseline_rel, candidate_rel) in REFERENCE_CASES.items():
        baseline = repo_root / baseline_rel
        candidate = candidate_root / candidate_rel
        if not baseline.exists() or not candidate.exists():
            missing = []
            if not baseline.exists():
                missing.append(str(baseline))
            if not candidate.exists():
                missing.append(str(candidate))
            payload[name] = {"missing": missing}
            risky += 1
            continue
        rows = classify_reports(baseline, candidate)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.classification] = counts.get(row.classification, 0) + 1
        unacceptable += counts.get("unacceptable_wrong_pass", 0)
        risky += counts.get("risky_regression", 0)
        all_counts[name] = len(rows)
        payload[name] = {
            "rows": len(rows),
            "counts": counts,
            "safer_review": [
                {
                    "source": row.source,
                    "reason_summary": row.reason_summary,
                }
                for row in rows
                if row.classification == "safer_review"
            ],
            "unacceptable_wrong_pass": [
                {
                    "source": row.source,
                    "reason_summary": row.reason_summary,
                }
                for row in rows
                if row.classification == "unacceptable_wrong_pass"
            ],
            "risky_regression": [
                {
                    "source": row.source,
                    "reason_summary": row.reason_summary,
                }
                for row in rows
                if row.classification == "risky_regression"
            ],
        }
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        total_rows = sum(all_counts.values())
        print(f"candidate root: {candidate_root}")
        print(f"rows compared: {total_rows}")
        for name, data in payload.items():
            if "missing" in data:
                print(f"{name}: missing {data['missing']}")
                continue
            print(f"{name}: {data['counts']}")
            for item in data["safer_review"][:20]:
                print(f"  safer_review: {Path(item['source']).name}: {item['reason_summary']}")
            if len(data["safer_review"]) > 20:
                print(f"  ... {len(data['safer_review']) - 20} more safer_review")
            for item in data["unacceptable_wrong_pass"]:
                print(f"  unacceptable_wrong_pass: {Path(item['source']).name}: {item['reason_summary']}")
            for item in data["risky_regression"]:
                print(f"  risky_regression: {Path(item['source']).name}: {item['reason_summary']}")
        print(f"unacceptable_wrong_pass: {unacceptable}")
        print(f"risky_regression: {risky}")
    return 1 if unacceptable or risky else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify candidate reports against reference reports.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    return run_cases(args.repo_root.resolve(), args.candidate_root.resolve(), args.json)


if __name__ == "__main__":
    raise SystemExit(main())
