from __future__ import annotations

from .....geometry.edge_pairs import refine_gaps_by_edge_pairs
from .....geometry.enhanced_separator import merge_enhanced_separator_gaps, should_run_enhanced_separator_analysis
from .....geometry.nearby_separator import apply_nearby_separator_corrections
from .....geometry.robust_grid import apply_robust_grid


refine_with_edge_pairs = refine_gaps_by_edge_pairs
refine_with_nearby_separator = apply_nearby_separator_corrections
apply_grid_gap_model = apply_robust_grid
merge_enhanced_separator_proposals = merge_enhanced_separator_gaps
should_run_enhanced_separator_proposals = should_run_enhanced_separator_analysis


__all__ = [
    "apply_grid_gap_model",
    "merge_enhanced_separator_proposals",
    "refine_with_edge_pairs",
    "refine_with_nearby_separator",
    "should_run_enhanced_separator_proposals",
]
