from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from ..domain import OuterCandidate
from .content_statistics import ContentColumnStatistics

@dataclass
class AnalysisCache:
    layout: str
    gray_work: np.ndarray
    content_evidence_work: np.ndarray
    content_evidence_float_work: np.ndarray
    separator_evidence_work_full: Optional[np.ndarray] = None
    separator_profiles: dict[tuple[Any, ...], np.ndarray] = field(default_factory=dict)
    separator_profiles_full: dict[tuple[Any, ...], np.ndarray] = field(default_factory=dict)
    separator_evidence_crops: dict[tuple[int, int, int, int], np.ndarray] = field(default_factory=dict)
    edge_refine_profiles: dict[tuple[Any, ...], tuple[np.ndarray, np.ndarray, np.ndarray]] = field(default_factory=dict)
    preview_rgb_cache: dict[tuple[str, int], tuple[np.ndarray, float]] = field(default_factory=dict)
    panel_label_cache: dict[tuple[str, str, int], np.ndarray] = field(default_factory=dict)
    nearby_separator_details: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    content_mask_details: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    content_region_runs: dict[tuple[Any, ...], tuple[list[tuple[int, int]], dict[str, Any]]] = field(default_factory=dict)
    content_evidence_details: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    content_evidence_thresholds: dict[tuple[Any, ...], float] = field(default_factory=dict)
    content_column_statistics: dict[tuple[Any, ...], ContentColumnStatistics] = field(
        default_factory=dict
    )
    outer_alignment_details: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    separator_outer_candidates: dict[tuple[Any, ...], list[OuterCandidate]] = field(default_factory=dict)
    edge_anchored_outer_candidates: dict[tuple[Any, ...], list[OuterCandidate]] = field(default_factory=dict)
    base_outer_candidates: dict[tuple[Any, ...], list[OuterCandidate]] = field(default_factory=dict)
    outer_proposal_candidates: dict[tuple[Any, ...], list[OuterCandidate]] = field(default_factory=dict)
    separator_width_profiles: dict[tuple[Any, ...], np.ndarray] = field(default_factory=dict)
