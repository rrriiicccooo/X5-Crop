from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ....constants import CANDIDATE_SOURCE_CONTENT
from ....domain import DetectionCandidate
from ....formats import FormatPhysicalSpec
from ....geometry.boxes import map_work_box
from ....run_config import RunConfig
from ...guidance.content_model import (
    CONTENT_CANDIDATE_CONTRACT,
    CONTENT_GAP_EVIDENCE_KIND,
    CONTENT_PROPOSAL_FAMILY,
    CONTENT_PROPOSAL_ROLE,
    ContentCandidateProposal,
)


def build_content_candidate(
    proposal: ContentCandidateProposal,
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float,
) -> DetectionCandidate:
    work_height, work_width = (
        gray.shape
        if config.layout == "horizontal"
        else (gray.shape[1], gray.shape[0])
    )
    frames_work = [
        box.expand(config.bleed_x, config.bleed_y, work_width, work_height)
        for box in proposal.frames
    ]
    frames = [
        map_work_box(box, config.layout, gray.shape[1], gray.shape[0])
        for box in frames_work
    ]
    outer = map_work_box(
        proposal.outer,
        config.layout,
        gray.shape[1],
        gray.shape[0],
    )
    gaps = list(proposal.gaps)
    return DetectionCandidate(
        format_id=fmt.format_id,
        layout=config.layout,
        strip_mode=strip_mode,
        count=count,
        outer=outer,
        frames=frames,
        gaps=gaps,
        confidence=0.0,
        detail={
            "proposal_family": CONTENT_PROPOSAL_FAMILY,
            "proposal_role": CONTENT_PROPOSAL_ROLE,
            "candidate_contract": CONTENT_CANDIDATE_CONTRACT,
            "content_gap_evidence_kind": CONTENT_GAP_EVIDENCE_KIND,
            "candidate_source": CANDIDATE_SOURCE_CONTENT,
            "candidate_count": count,
            "offset_fraction": float(offset_fraction),
            "layout": config.layout,
            "outer_candidate": "content_evidence",
            "work_outer": asdict(proposal.outer),
            "content_proposal": dict(proposal.detail),
            "gap_centers": [gap.center for gap in gaps],
            "gap_scores": [gap.score for gap in gaps],
            "gap_methods": [gap.method for gap in gaps],
        },
    )
