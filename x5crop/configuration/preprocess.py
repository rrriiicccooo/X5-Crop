from __future__ import annotations

from dataclasses import dataclass, field

from ..image.gray import BaseGrayParameters


@dataclass(frozen=True)
class PreprocessConfiguration:
    base_gray: BaseGrayParameters = field(default_factory=BaseGrayParameters)
