from __future__ import annotations


def sampling_step_for_limit(length: int, sample_limit: int) -> int:
    limit = max(1, int(sample_limit))
    return max(1, (max(0, int(length)) + limit - 1) // limit)
