from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..image.workspace import WorkspaceIdentity, workspace_identity_for_gray


@dataclass(frozen=True)
class PreparedWorkspace:
    pixels: np.ndarray
    gray: np.ndarray
    transform_geometry: TransformGeometryEvidence
    identity: WorkspaceIdentity = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.pixels, np.ndarray):
            raise TypeError("prepared workspace pixels must be an array")
        if not isinstance(self.gray, np.ndarray) or self.gray.ndim != 2:
            raise ValueError("prepared workspace gray must be two-dimensional")
        object.__setattr__(self, "identity", workspace_identity_for_gray(self.gray))
