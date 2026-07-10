from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ContentColumnStatistics:
    mean_prefix: np.ndarray
    coverage_prefix: np.ndarray
    row_count: int
    column_count: int

    @classmethod
    def from_evidence(
        cls,
        evidence: np.ndarray,
        threshold: float,
    ) -> "ContentColumnStatistics":
        if evidence.ndim != 2:
            raise ValueError("content evidence must be a two-dimensional array")
        rows, columns = evidence.shape
        mean_sums = evidence.sum(axis=0, dtype=np.float64)
        coverage_sums = (evidence >= float(threshold)).sum(axis=0, dtype=np.float64)
        return cls(
            mean_prefix=np.concatenate(
                (np.zeros(1, dtype=np.float64), np.cumsum(mean_sums, dtype=np.float64))
            ),
            coverage_prefix=np.concatenate(
                (
                    np.zeros(1, dtype=np.float64),
                    np.cumsum(coverage_sums, dtype=np.float64),
                )
            ),
            row_count=int(rows),
            column_count=int(columns),
        )

    def interval(self, left: int, right: int) -> tuple[float, float]:
        start = max(0, min(int(left), self.column_count))
        end = max(start, min(int(right), self.column_count))
        area = int(self.row_count) * int(end - start)
        if area <= 0:
            raise ValueError("content statistics interval must have positive area")
        mean = float(self.mean_prefix[end] - self.mean_prefix[start]) / float(area)
        coverage = float(
            self.coverage_prefix[end] - self.coverage_prefix[start]
        ) / float(area)
        return mean, coverage
