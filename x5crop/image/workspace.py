from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..domain import WorkspaceExtent


@dataclass(frozen=True)
class WorkspaceIdentity:
    extent: WorkspaceExtent


def workspace_identity_for_gray(gray: np.ndarray) -> WorkspaceIdentity:
    if not isinstance(gray, np.ndarray) or gray.ndim != 2:
        raise ValueError("canonical workspace gray must be a two-dimensional array")
    return WorkspaceIdentity(
        extent=WorkspaceExtent(
            width=int(gray.shape[1]),
            height=int(gray.shape[0]),
        ),
    )
