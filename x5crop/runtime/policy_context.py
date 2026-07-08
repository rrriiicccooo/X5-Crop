from __future__ import annotations

from dataclasses import dataclass

from ..policies.registry import get_detection_policy
from ..policies.runtime.policy import DetectionPolicy


@dataclass(frozen=True)
class RuntimePolicyContext:
    initial_policy: DetectionPolicy

    @classmethod
    def for_format_mode(cls, format_id: str, strip_mode: str) -> "RuntimePolicyContext":
        return cls(initial_policy=get_detection_policy(format_id, strip_mode))

    def policy_for(self, format_id: str, strip_mode: str) -> DetectionPolicy:
        if format_id == self.initial_policy.format_id and strip_mode == self.initial_policy.strip_mode:
            return self.initial_policy
        return get_detection_policy(format_id, strip_mode)


__all__ = ["RuntimePolicyContext"]
