from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .domain import Gap, OuterCandidate


REPORT_RECORD_CACHE: dict[Path, tuple[int, int, list[dict[str, Any]]]] = {}


@dataclass
class AnalysisCache:
    layout: str
    gray_work: np.ndarray
    content_evidence_work: np.ndarray
    content_evidence_float_work: np.ndarray
    separator_evidence_work_full: Optional[np.ndarray] = None
    separator_profiles: dict[tuple[Any, ...], np.ndarray] = field(default_factory=dict)
    separator_profiles_full: dict[tuple[Any, ...], np.ndarray] = field(default_factory=dict)
    enhanced_separator_profiles: dict[tuple[Any, ...], np.ndarray] = field(default_factory=dict)
    enhanced_separator_profiles_full: dict[tuple[Any, ...], np.ndarray] = field(default_factory=dict)
    separator_evidence_crops: dict[tuple[int, int, int, int], np.ndarray] = field(default_factory=dict)
    edge_refine_profiles: dict[tuple[Any, ...], tuple[np.ndarray, np.ndarray, np.ndarray]] = field(default_factory=dict)
    preview_rgb_cache: dict[tuple[str, int], tuple[np.ndarray, float]] = field(default_factory=dict)
    panel_label_cache: dict[tuple[str, str, int], np.ndarray] = field(default_factory=dict)
    nearby_separator_details: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    enhanced_separator_merges: dict[tuple[Any, ...], tuple[list[Gap], dict[str, Any]]] = field(default_factory=dict)
    content_mask_details: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    content_profile_runs: dict[tuple[Any, ...], tuple[list[tuple[int, int]], dict[str, Any]]] = field(default_factory=dict)
    content_evidence_details: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    outer_alignment_details: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    separator_first_outer_candidates: dict[tuple[Any, ...], list[OuterCandidate]] = field(default_factory=dict)
    separator_geometry_outer_candidates: dict[tuple[Any, ...], list[OuterCandidate]] = field(default_factory=dict)
    long_axis_edge_anchor_outer_candidates: dict[tuple[Any, ...], list[OuterCandidate]] = field(default_factory=dict)


__all__ = ["AnalysisCache", "REPORT_RECORD_CACHE"]
