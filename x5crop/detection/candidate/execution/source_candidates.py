from __future__ import annotations

from dataclasses import dataclass

from ....cache import MeasurementCache
from ....constants import CANDIDATE_SOURCE_SEPARATOR
from ....domain import Box
from ....formats import FormatPhysicalSpec
from ....policies.runtime.outer import OuterPolicy
from ....policies.runtime.separator import SeparatorPolicy
from ....units import ScanCalibration
from ...context import DetectionRequest
from ...physical.outer.common import unique_sequence_span_proposals
from ...physical.outer.separator import (
    FULL_WIDTH_SEPARATOR_OUTER,
    LOCAL_SEPARATOR_OUTER,
    separator_derived_outer_candidates,
)
from ...physical.spans import HolderSpan
from ...physical.outer.types import SequenceHypothesis
from ...physical.separator.hints import SeparatorGapHintSet
from ..build.detection import build_candidate_geometry
from ..model import BuiltCandidate
from ..plan.count_hypotheses import CountHypothesis
from ..proposal.outer import sequence_hypotheses, separator_sequence_rank


@dataclass(frozen=True)
class SeparatorSequencePlan:
    proposals: tuple[SequenceHypothesis, ...]
    comparison_proposals: tuple[SequenceHypothesis, ...]
    count_hypothesis: CountHypothesis


def _holder_span(cache: MeasurementCache) -> HolderSpan:
    height, width = cache.gray_work.shape
    return HolderSpan(Box(0, 0, width, height))


def build_separator_candidate_for_proposal(
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float,
    cache: MeasurementCache,
    outer_policy: OuterPolicy,
    separator_policy: SeparatorPolicy,
    scan_calibration: ScanCalibration,
    proposal: SequenceHypothesis,
    *,
    plan: SeparatorSequencePlan,
    gap_max_width_ratio_override: float | None,
) -> BuiltCandidate:
    gap_override = gap_max_width_ratio_override
    if proposal.strategy == "separator_dimension_span":
        configured = (
            outer_policy.proposal.geometry.separator.separator_gap_search_max_width_ratio
        )
        if (
            gap_override is None
            and configured
            > separator_policy.gap_search.max_width.fallback_ratio
        ):
            gap_override = configured
    return build_candidate_geometry(
        request,
        fmt,
        count,
        strip_mode,
        proposal.visible_sequence_span,
        proposal.crop_envelope,
        offset_fraction,
        _holder_span(cache),
        CANDIDATE_SOURCE_SEPARATOR,
        True,
        "physical_boundary_evidence",
        plan.count_hypothesis,
        proposal.name,
        proposal.strategy,
        proposal.provenance,
        proposal.boundary_observations,
        scan_calibration,
        gap_override,
        None,
        (),
        cache=cache,
        separator_policy=separator_policy,
    )


def _sequence_plan(
    sequence_hypotheses: list[SequenceHypothesis],
    comparison_proposals: list[SequenceHypothesis],
    count_hypothesis: CountHypothesis,
) -> SeparatorSequencePlan:
    return SeparatorSequencePlan(
        proposals=tuple(sequence_hypotheses),
        comparison_proposals=tuple(comparison_proposals),
        count_hypothesis=count_hypothesis,
    )


def separator_primary_sequence_plan(
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
) -> SeparatorSequencePlan:
    if cache.layout != request.layout:
        raise ValueError("sequence planning requires matching measurement cache")
    explicit_count = request.requested_count is not None
    candidates = sequence_hypotheses(
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
    return _sequence_plan(
        candidates,
        candidates,
        count_hypothesis,
    )


def separator_extension_sequence_plan(
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
    primary_sequence_hypotheses: tuple[SequenceHypothesis, ...],
) -> SeparatorSequencePlan:
    if cache.layout != request.layout:
        raise ValueError("sequence planning requires matching measurement cache")
    explicit_count = request.requested_count is not None
    family = outer_policy.proposal.geometry.separator.full_width
    eligible = bool(
        family.available_for(strip_mode, explicit_count)
        and family.mode in {"always", "conditional"}
    )
    extension_proposals: list[SequenceHypothesis] = []
    if eligible:
        proposed = separator_derived_outer_candidates(
            cache.gray_work,
            list(primary_sequence_hypotheses),
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
        primary_boxes = {
            proposal.crop_envelope.box for proposal in primary_sequence_hypotheses
        }
        extension_proposals = [
            proposal
            for proposal in proposed
            if proposal.crop_envelope.box not in primary_boxes
        ]
    all_proposals = unique_sequence_span_proposals(
        [*primary_sequence_hypotheses, *extension_proposals]
    )
    return _sequence_plan(
        extension_proposals,
        all_proposals,
        count_hypothesis,
    )


def build_separator_candidate_with_guidance(
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    count_hypothesis: CountHypothesis,
    *,
    offset_fraction: float,
    sequence_hypothesis: SequenceHypothesis,
    guidance: SeparatorGapHintSet,
    cache: MeasurementCache,
    separator_policy: SeparatorPolicy,
    scan_calibration: ScanCalibration,
) -> BuiltCandidate:
    return build_candidate_geometry(
        request,
        fmt,
        count,
        strip_mode,
        sequence_hypothesis.visible_sequence_span,
        sequence_hypothesis.crop_envelope,
        offset_fraction,
        _holder_span(cache),
        CANDIDATE_SOURCE_SEPARATOR,
        True,
        "physical_boundary_evidence",
        count_hypothesis,
        f"{sequence_hypothesis.name}_content_guidance",
        sequence_hypothesis.strategy,
        sequence_hypothesis.provenance,
        sequence_hypothesis.boundary_observations,
        scan_calibration,
        None,
        guidance,
        (),
        cache=cache,
        separator_policy=separator_policy,
    )
