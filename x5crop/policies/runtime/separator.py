from __future__ import annotations

from dataclasses import dataclass

from ...geometry.detection_parameters import (
    SeparatorProfileParameters,
)
from ..parameters.separator import (
    SeparatorObservationParameters,
)


@dataclass(frozen=True)
class SeparatorPolicy:
    observation: SeparatorObservationParameters
    profile: SeparatorProfileParameters
