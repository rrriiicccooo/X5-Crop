from __future__ import annotations

from .....geometry.edge_pairs import refine_gaps_by_edge_pairs
from .....geometry.enhanced_separator import promote_enhanced_separator_gaps, should_run_enhanced_gap_promotion
from .....geometry.nearby_separator import apply_nearby_separator_corrections
from .....geometry.robust_grid import apply_robust_grid


refine_with_edge_pairs = refine_gaps_by_edge_pairs
refine_with_nearby_separator = apply_nearby_separator_corrections
apply_grid_gap_model = apply_robust_grid
promote_enhanced_separator_gaps_for_candidate = promote_enhanced_separator_gaps
should_run_enhanced_gap_promotion_for_candidate = should_run_enhanced_gap_promotion


__all__ = [
    "apply_grid_gap_model",
    "promote_enhanced_separator_gaps_for_candidate",
    "refine_with_edge_pairs",
    "refine_with_nearby_separator",
    "should_run_enhanced_gap_promotion_for_candidate",
]
