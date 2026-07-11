from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ....cache import MeasurementCache
from ....constants import CANDIDATE_SOURCE_SEPARATOR
from ....domain import Box
from ....formats import FormatPhysicalSpec
from ....policies.runtime.outer import OuterPolicy
from ....policies.runtime.separator import SeparatorPolicy
from ....units import ScanCalibration
from ...context import DetectionRequest
from ...physical.outer.common import unique_outer_proposals
from ...physical.outer.separator import (
    FULL_WIDTH_SEPARATOR_OUTER,
    LOCAL_SEPARATOR_OUTER,
    separator_derived_outer_candidates,
)
from ...physical.spans import HolderSpan
from ...physical.outer.types import OuterProposal
from ...physical.separator.hints import SeparatorGapHintSet
from ..build.detection import build_detection_geometry_for_outer
from ..model import BuiltCandidate
from ..plan.count_hypotheses import CountHypothesis
from ..proposal.outer import outer_proposal_candidates, separator_sequence_rank


@dataclass(frozen=True)
class SeparatorOuterProposalPlan:
    proposals: tuple[OuterProposal, ...]
    comparison_proposals: tuple[OuterProposal, ...]
    count_hypothesis: CountHypothesis


def _holder_span(cache: MeasurementCache) -> HolderSpan:
    height, width = cache.gray_work.shape
    return HolderSpan(Box(0, 0, width, height))


def build_separator_candidate_for_proposal(
    gray: np.ndarray,
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float,
    cache: MeasurementCache,
    outer_policy: OuterPolicy,
    separator_policy: SeparatorPolicy,
    scan_calibration: ScanCalibration,
    proposal: OuterProposal,
    *,
    plan: SeparatorOuterProposalPlan,
    gap_max_width_ratio_override: float | None,
) -> BuiltCandidate:
    gap_override = gap_max_width_ratio_override
    if proposal.strategy == "separator_outer":
        configured = (
            outer_policy.proposal.geometry.separator.separator_gap_search_max_width_ratio
        )
        if (
            gap_override is None
            and configured
            > separator_policy.gap_search.max_width.fallback_ratio
        ):
            gap_override = configured
    return build_detection_geometry_for_outer(
        gray,
        request,
        fmt,
        count,
        strip_mode,
        proposal.box,
        offset_fraction,
        _holder_span(cache),
        CANDIDATE_SOURCE_SEPARATOR,
        True,
        "physical_boundary_evidence",
        plan.count_hypothesis,
        proposal.name,
        proposal.strategy,
        proposal.provenance,
        scan_calibration,
        gap_override,
        None,
        (),
        cache=cache,
        separator_policy=separator_policy,
    )


def _outer_proposal_plan(
    outer_proposals: list[OuterProposal],
    comparison_proposals: list[OuterProposal],
    count_hypothesis: CountHypothesis,
) -> SeparatorOuterProposalPlan:
    return SeparatorOuterProposalPlan(
        proposals=tuple(outer_proposals),
        comparison_proposals=tuple(comparison_proposals),
        count_hypothesis=count_hypothesis,
    )


def separator_primary_outer_plan(
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    count_hypothesis: CountHypothesis,
    *,
    cache: MeasurementCache,
    outer_policy: OuterPolicy,
    separator_policy: SeparatorPolicy,
    scan_calibration: ScanCalibration,
) -> SeparatorOuterProposalPlan:
    if cache.layout != request.layout:
        raise ValueError("outer proposal requires matching analysis cache")
    explicit_count = request.requested_count is not None
    candidates = outer_proposal_candidates(
        cache.gray_work,
        fmt,
        count,
        strip_mode,
        cache,
        scan_calibration,
        "x" if request.layout == "horizontal" else "y",
        outer_policy=outer_policy,
        separator_policy=separator_policy,
        separator_scopes=(LOCAL_SEPARATOR_OUTER,),
        explicit_count=explicit_count,
    )
    return _outer_proposal_plan(
        candidates,
        candidates,
        count_hypothesis,
    )


def separator_extension_outer_plan(
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    count_hypothesis: CountHypothesis,
    *,
    cache: MeasurementCache,
    outer_policy: OuterPolicy,
    separator_policy: SeparatorPolicy,
    scan_calibration: ScanCalibration,
    primary_outer_proposals: tuple[OuterProposal, ...],
) -> SeparatorOuterProposalPlan:
    if cache.layout != request.layout:
        raise ValueError("outer proposal requires matching analysis cache")
    explicit_count = request.requested_count is not None
    family = outer_policy.proposal.geometry.separator.full_width
    eligible = bool(
        family.available_for(strip_mode, explicit_count)
        and family.mode in {"always", "conditional"}
    )
    extension_proposals: list[OuterProposal] = []
    if eligible:
        proposed = separator_derived_outer_candidates(
            cache.gray_work,
            list(primary_outer_proposals),
            fmt,
            count,
            strip_mode,
            cache,
            scan_calibration,
            "x" if request.layout == "horizontal" else "y",
            separator_geometry_policy=outer_policy.proposal.geometry.separator,
            separator_policy=separator_policy,
            outer_scopes=(FULL_WIDTH_SEPARATOR_OUTER,),
            explicit_count=explicit_count,
            sequence_ranker=separator_sequence_rank,
        )
        primary_boxes = {proposal.box for proposal in primary_outer_proposals}
        extension_proposals = [
            proposal
            for proposal in proposed
            if proposal.box not in primary_boxes
        ]
    all_proposals = unique_outer_proposals(
        [*primary_outer_proposals, *extension_proposals]
    )
    return _outer_proposal_plan(
        extension_proposals,
        all_proposals,
        count_hypothesis,
    )


def build_separator_candidate_with_guidance(
    gray: np.ndarray,
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    count_hypothesis: CountHypothesis,
    *,
    offset_fraction: float,
    outer_proposal: OuterProposal,
    guidance: SeparatorGapHintSet,
    cache: MeasurementCache,
    separator_policy: SeparatorPolicy,
    scan_calibration: ScanCalibration,
) -> BuiltCandidate:
    return build_detection_geometry_for_outer(
        gray,
        request,
        fmt,
        count,
        strip_mode,
        outer_proposal.box,
        offset_fraction,
        _holder_span(cache),
        CANDIDATE_SOURCE_SEPARATOR,
        True,
        "physical_boundary_evidence",
        count_hypothesis,
        f"{outer_proposal.name}_content_guidance",
        outer_proposal.strategy,
        outer_proposal.provenance,
        scan_calibration,
        None,
        guidance,
        (),
        cache=cache,
        separator_policy=separator_policy,
    )
