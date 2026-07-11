from __future__ import annotations

from ....domain import MeasurementProvenance
from ....gap_methods import is_hard_gap_method
from ...context import DetectionContext
from ...physical.outer.correction.content_containment import (
    content_containment_correction_proposal,
)
from ...physical.outer.correction.geometry import (
    geometry_consistency_correction_proposals,
)
from ...physical.outer.correction.types import OuterCorrectionProposal
from ..assessment.candidate import assess_candidate
from ..build.detection import build_detection_geometry_for_outer
from ..model import AssessedCandidate
from ..selection.model import SelectionResult


def _eligible_families(
    candidate: AssessedCandidate,
    context: DetectionContext,
) -> frozenset[str]:
    geometry = candidate.geometry
    if (
        geometry.source != "separator"
        or not geometry.automatic_processing_supported
        or geometry.lane_boxes
    ):
        return frozenset()
    if (
        geometry.strip_mode == "partial"
        and context.request.requested_count is None
    ):
        return frozenset()
    correction = context.policy.outer.correction
    families = {
        "long_axis_geometry": correction.geometry_consistency.long_axis.family,
        "short_axis_geometry": correction.geometry_consistency.short_axis.family,
        "content_containment": correction.content_containment.family,
    }
    return frozenset(
        name for name, family in families.items() if family.mode != "off"
    )


def _correction_provenance(
    source: AssessedCandidate,
    proposal: OuterCorrectionProposal,
) -> MeasurementProvenance:
    original = source.geometry.outer_provenance
    dependencies = set(original.dependencies)
    if proposal.family in {"long_axis_geometry", "short_axis_geometry"}:
        dependencies.update(
            observation.provenance.root_measurement
            for observation in source.geometry.separators
            if is_hard_gap_method(observation.method)
        )
    elif proposal.family == "content_containment":
        dependencies.add("content_evidence")
    return MeasurementProvenance(
        root_measurement=original.root_measurement,
        source=f"outer_correction:{proposal.family}",
        dependencies=tuple(sorted(dependencies)),
        boundary_anchors=original.boundary_anchors,
    )


def _build_corrected_candidate(
    source: AssessedCandidate,
    proposal: OuterCorrectionProposal,
    context: DetectionContext,
) -> AssessedCandidate:
    geometry = source.geometry
    built = build_detection_geometry_for_outer(
        context.source_gray,
        context.request,
        context.policy.physical_spec,
        geometry.count,
        geometry.strip_mode,
        proposal.box,
        geometry.offset_fraction,
        geometry.holder_span,
        geometry.source,
        geometry.automatic_processing_supported,
        geometry.contract,
        source.count_hypothesis,
        f"{proposal.family}_outer",
        "outer_correction",
        _correction_provenance(source, proposal),
        context.scan_calibration,
        None,
        None,
        (f"outer_correction:{proposal.family}:{proposal.reason}",),
        cache=context.measurement_cache,
        separator_policy=context.policy.separator,
    )
    return assess_candidate(built, context)


def outer_correction_candidate_extensions(
    selection: SelectionResult,
    context: DetectionContext,
) -> tuple[AssessedCandidate, ...]:
    if selection.geometry_resolution.supported:
        return ()
    selected = selection.selected
    eligible = _eligible_families(selected, context)
    if not eligible:
        return ()
    evidence = selected.assessment.evidence
    proposals = list(
        geometry_consistency_correction_proposals(
            selected.geometry,
            evidence.frame_dimensions,
            evidence.outer_alignment,
            context.policy.physical_spec,
            context.policy.outer.correction.geometry_consistency,
            canvas_width=context.measurement_cache.gray_work.shape[1],
            canvas_height=context.measurement_cache.gray_work.shape[0],
            eligible_families=eligible,
        )
    )
    if "content_containment" in eligible:
        proposal = content_containment_correction_proposal(
            selected.geometry,
            evidence.outer_alignment,
            context.measurement_cache.gray_work.shape[1],
            context.measurement_cache.gray_work.shape[0],
            context.policy.outer.correction.content_containment,
        )
        if proposal is not None:
            proposals.append(proposal)
    return tuple(
        _build_corrected_candidate(selected, proposal, context)
        for proposal in proposals
    )
