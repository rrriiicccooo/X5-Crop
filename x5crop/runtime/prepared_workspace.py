from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..domain import WorkspaceExtent


@dataclass(frozen=True)
class PreparedWorkspace:
    pixels: np.ndarray
    gray: np.ndarray
    extent: WorkspaceExtent
    transform_geometry: TransformGeometryEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.pixels, np.ndarray):
            raise TypeError("prepared workspace pixels must be an array")
        if not isinstance(self.gray, np.ndarray) or self.gray.ndim != 2:
            raise ValueError("prepared workspace gray must be two-dimensional")
        if self.extent != workspace_extent_for_gray(self.gray):
            raise ValueError("prepared workspace extent must match gray pixels")


def workspace_extent_for_gray(gray: np.ndarray) -> WorkspaceExtent:
    if gray.ndim != 2:
        raise ValueError("canonical workspace gray must be two-dimensional")
    return WorkspaceExtent(width=int(gray.shape[1]), height=int(gray.shape[0]))
