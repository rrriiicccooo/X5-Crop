from __future__ import annotations

from dataclasses import dataclass

from .registry import get_detection_policy
from .runtime.policy import DetectionPolicy


@dataclass(frozen=True)
class RuntimePolicyContext:
    initial_policy: DetectionPolicy

    @classmethod
    def for_format_mode(cls, format_id: str, strip_mode: str) -> "RuntimePolicyContext":
        return cls(initial_policy=get_detection_policy(format_id, strip_mode))

    def policy_for(self, format_id: str, strip_mode: str) -> DetectionPolicy:
        policy = self.initial_policy
        if policy.format_id == format_id and policy.strip_mode == strip_mode:
            return policy
        return get_detection_policy(format_id, strip_mode)


__all__ = ["RuntimePolicyContext"]
