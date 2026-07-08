from __future__ import annotations

from ....formats import FormatSpec
from ....policies.runtime.policy import DetectionPolicy
from ....runtime.config import RuntimeConfig

def candidate_counts_for_format(
    config: RuntimeConfig,
    fmt: FormatSpec,
    policy: DetectionPolicy,
) -> list[tuple[int, str, tuple[float, ...]]]:
    return policy.counts.count_specs(
        fmt,
        config.strip_mode,
        int(config.count),
        config.count_override,
    )

__all__ = [
    "candidate_counts_for_format",
]
