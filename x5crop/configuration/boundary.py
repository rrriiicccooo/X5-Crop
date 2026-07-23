from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import require_positive, require_unit_interval
from .path_sampling import BoundaryPathSamplingParameters


@dataclass(frozen=True)
class BoundaryPathParameters:
    path_sampling: BoundaryPathSamplingParameters = field(
        default_factory=BoundaryPathSamplingParameters
    )
    edge_reference_mad_multiplier: float = 3.0
    minimum_path_support_ratio: float = 0.60
    edge_transition_persistence_ratio: float = 0.80
    path_inlier_mad_multiplier: float = 3.0
    maximum_path_fit_residual_ratio: float = 0.06

    def __post_init__(self) -> None:
        if not isinstance(
            self.path_sampling,
            BoundaryPathSamplingParameters,
        ):
            raise TypeError(
                "boundary path parameters require typed sampling parameters"
            )
        require_positive(
            "canvas-edge reference MAD multiplier",
            self.edge_reference_mad_multiplier,
        )
        require_unit_interval(
            "boundary minimum path support",
            self.minimum_path_support_ratio,
        )
        if self.minimum_path_support_ratio <= 0.0:
            raise ValueError("boundary path support must be positive")
        require_unit_interval(
            "boundary edge transition persistence",
            self.edge_transition_persistence_ratio,
        )
        if self.edge_transition_persistence_ratio <= 0.0:
            raise ValueError("boundary edge transition persistence must be positive")
        require_positive(
            "boundary path inlier MAD multiplier",
            self.path_inlier_mad_multiplier,
        )
        require_unit_interval(
            "boundary maximum path-fit residual ratio",
            self.maximum_path_fit_residual_ratio,
        )
        if self.maximum_path_fit_residual_ratio <= 0.0:
            raise ValueError("boundary path-fit residual ratio must be positive")
