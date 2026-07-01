from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .compare import compare_report_files


CORE_FIELDS = (
    "status",
    "confidence",
    "review_reasons",
    "outer_box",
    "frame_boxes",
    "gaps",
    "detail.policy",
    "report_schema",
)


@dataclass(frozen=True)
class ReferenceCase:
    name: str
    baseline_report: Path
    candidate_report: Path


REFERENCE_REPORTS = {
    "standard_strip_full": Path("Test/135/4.5.4/split_report.jsonl"),
    "wide_spacing_standard_strip_full": Path("Test/new_135/4.5.4/split_report.jsonl"),
    "medium_square_full": Path("Test/120/66/4.5.4/split_report.jsonl"),
    "medium_square_partial": Path("Test/120/66/4.5.4_partial/split_report.jsonl"),
    "medium_wide_full": Path("Test/120/67/4.5.4/split_report.jsonl"),
    "dense_half_frame_full": Path("Test/半格/full/4.5.4/split_report.jsonl"),
    "dense_half_frame_partial": Path("Test/半格/partial/4.5.4_partial/split_report.jsonl"),
}


def candidate_report_path(candidate_root: Path, baseline: Path) -> Path:
    parts = baseline.parts
    if parts and parts[0] == "Test":
        return candidate_root.joinpath(*parts[1:])
    return candidate_root / baseline


def reference_cases(repo_root: Path, candidate_root: Path) -> list[ReferenceCase]:
    return [
        ReferenceCase(
            name=name,
            baseline_report=repo_root / baseline,
            candidate_report=candidate_report_path(candidate_root, baseline),
        )
        for name, baseline in REFERENCE_REPORTS.items()
    ]


def compare_reference_cases(cases: Iterable[ReferenceCase], fields: Iterable[str] = CORE_FIELDS) -> int:
    total_diffs = 0
    for case in cases:
        if not case.baseline_report.exists():
            print(f"{case.name}: missing baseline {case.baseline_report}")
            total_diffs += 1
            continue
        if not case.candidate_report.exists():
            print(f"{case.name}: missing candidate {case.candidate_report}")
            total_diffs += 1
            continue
        diffs = compare_report_files(case.baseline_report, case.candidate_report, fields=fields)
        total_diffs += len(diffs)
        print(f"{case.name}: {len(diffs)} diff(s)")
        for diff in diffs[:20]:
            print(f"  {diff.source}: {diff.field}")
        if len(diffs) > 20:
            print(f"  ... {len(diffs) - 20} more")
    print(f"total diffs: {total_diffs}")
    return total_diffs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare candidate X5 Crop reports against V4.5.4 historical reference reports.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root containing Test/.")
    parser.add_argument("--candidate-root", type=Path, required=True, help="Root containing candidate reports laid out like Test/.")
    parser.add_argument("--field", action="append", dest="fields", help="Field to compare. Can be repeated.")
    args = parser.parse_args(argv)
    fields = tuple(args.fields) if args.fields else CORE_FIELDS
    cases = reference_cases(args.repo_root.resolve(), args.candidate_root.resolve())
    return 1 if compare_reference_cases(cases, fields=fields) else 0


if __name__ == "__main__":
    raise SystemExit(main())
