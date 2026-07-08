from __future__ import annotations

from typing import Optional

import numpy as np

from ...app_info import VERSION
from ...domain import Detection
from ...geometry.layout import work_gray
from ...cache import AnalysisCache
from ...gap_methods import gap_method_roles
from ...policies.runtime.diagnostics import RuntimeDiagnosticsPolicy
from ...policies.runtime.output_evidence import RuntimeOutputEvidencePolicy
from ...policies.runtime.separator import SeparatorPolicy
from .gap_diagnostics import gap_diagnostic_record


def attach_read_only_diagnostics(
    gray: np.ndarray,
    detection: Detection,
    cache: Optional[AnalysisCache] = None,
    *,
    separator_policy: SeparatorPolicy,
    diagnostics_policy: RuntimeDiagnosticsPolicy,
    output_evidence_policy: RuntimeOutputEvidencePolicy,
) -> None:
    gray_work = cache.gray_work if cache is not None and cache.layout == detection.layout else work_gray(gray, detection.layout)
    gap_records = [
        gap_diagnostic_record(
            gray_work,
            detection,
            gap,
            cache,
            separator_policy=separator_policy,
            nearby_policy=diagnostics_policy.nearby_separator,
            output_overlap_policy=output_evidence_policy.output_overlap,
        )
        for gap in detection.gaps
    ]
    hard_counts: dict[str, int] = {}
    for record in gap_records:
        trust = str(record.get("hard_trust", "not_hard_gap"))
        hard_counts[trust] = hard_counts.get(trust, 0) + 1
    output_overlap_count = sum(
        1 for record in gap_records if bool(record.get("output_overlap_like", False))
    )
    output_overlap_counts: dict[str, int] = {}
    for record in gap_records:
        output_overlap_class = str(record.get("output_overlap_class", "none"))
        output_overlap_counts[output_overlap_class] = (
            output_overlap_counts.get(output_overlap_class, 0) + 1
        )
    strong_hard = int(hard_counts.get("strong_separator", 0))
    suspicious_hard = sum(
        int(hard_counts.get(name, 0))
        for name in ("suspect_internal_edge", "suspect_frame_border", "nearby_separator_conflict", "geometry_conflict")
    )
    method_roles = gap_method_roles()
    detection.detail["diagnostics"] = {
        "version": VERSION,
        "diagnostic_only": True,
        "effects": {
            "output": False,
            "confidence": False,
            "decision": False,
        },
        "purpose": "observe hard-gap trust, output-overlap evidence, and evidence/model roles without changing crop output",
        "method_roles": method_roles,
        "gap_diagnostics": gap_records,
        "summary": {
            "gap_count": len(gap_records),
            "hard_trust_counts": hard_counts,
            "output_overlap_like_model_gaps": int(output_overlap_count),
            "output_overlap_counts": output_overlap_counts,
            "suspect_hard_gaps": int(hard_counts.get("suspect_internal_edge", 0)),
            "suspicious_hard_gaps": int(suspicious_hard),
            "strong_hard_gaps": int(strong_hard),
        },
    }
