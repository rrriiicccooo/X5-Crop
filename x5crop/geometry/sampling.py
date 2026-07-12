from __future__ import annotations


def sampling_step_for_limit(length: int, sample_limit: int) -> int:
    limit = int(sample_limit)
    if limit <= 0:
        raise ValueError("sample limit must be positive")
    return max(1, (max(0, int(length)) + limit - 1) // limit)
