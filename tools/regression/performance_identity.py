"""Validate the local 24-source performance identity outside product timing."""

from __future__ import annotations

from .benchmark_workload import (
    FIXED_SOURCE_COUNT,
    FIXED_WORKLOAD_COUNT,
    load_performance_sources,
    load_workload_records,
)


def main() -> int:
    sources = load_performance_sources(verify_source_files=True)
    workload = load_workload_records()
    if len(sources) != FIXED_SOURCE_COUNT or len(workload) != FIXED_WORKLOAD_COUNT:
        raise ValueError("performance identity is incomplete")
    print(
        f"performance identity: {len(sources)} sources, "
        f"{len(workload)} tasks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
