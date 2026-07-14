from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

import numpy as np

from ..domain import WorkspaceExtent


@dataclass(frozen=True)
class WorkspaceIdentity:
    extent: WorkspaceExtent
    gray_sha256: str

    def __post_init__(self) -> None:
        if len(self.gray_sha256) != 64:
            raise ValueError("workspace gray identity must be a SHA-256 digest")


def workspace_identity_for_gray(gray: np.ndarray) -> WorkspaceIdentity:
    if not isinstance(gray, np.ndarray) or gray.ndim != 2:
        raise ValueError("canonical workspace gray must be a two-dimensional array")
    contiguous = np.ascontiguousarray(gray)
    digest = sha256()
    digest.update(contiguous.dtype.str.encode("ascii"))
    digest.update(str(contiguous.shape).encode("ascii"))
    digest.update(memoryview(contiguous).cast("B"))
    return WorkspaceIdentity(
        extent=WorkspaceExtent(
            width=int(contiguous.shape[1]),
            height=int(contiguous.shape[0]),
        ),
        gray_sha256=digest.hexdigest(),
    )
