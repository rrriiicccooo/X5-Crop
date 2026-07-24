from __future__ import annotations

from dataclasses import replace

import numpy as np

from x5crop.cache import MeasurementCacheStatistics
from x5crop.cache.analysis import make_measurement_cache

from x5crop.detection.candidate.assessment.candidate import (
    candidate_gate_for_evidence,
)
from x5crop.detection.candidate.assessment.candidate_gate import (
    candidate_gate_assessment,
)
from x5crop.detection.candidate.assessment.evidence_independence import (
    evidence_independence_evidence,
)
from x5crop.detection.candidate.assessment.model import (
    CandidateGateAssessment,
    CandidateGateInput,
    SequenceProofPath,
)
from x5crop.detection.candidate.assessment.review_only import (
    assess_review_only_candidate,
)
from x5crop.detection.candidate.model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
)
from x5crop.detection.candidate.plan.model import (
    CountHypothesis,
    CountHypothesisSource,
)
from x5crop.detection.candidate.selection.model import (
    GeometryCluster,
    SelectionConsensus,
    SelectionResult,
)
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.decision.model import DecisionGateAssessment
from x5crop.detection.evidence.content.external_frame_boundaries import (
    ExternalFrameBoundaryObservation,
    ExternalFramePreservationEvidence,
)
from x5crop.detection.evidence.content.frame_content import (
    FrameContentEvidence,
    FrameContentObservation,
)
from x5crop.detection.evidence.content.internal_frame_boundaries import (
    InternalBoundaryContentContinuityObservation,
    internal_frame_boundary_preservation_evidence,
)
from x5crop.detection.evidence.frame_coverage import FrameCoverageEvidence
from x5crop.detection.evidence.frame_slot_topology import (
    frame_slot_topology_evidence,
)
from x5crop.detection.evidence.holder_boundary import holder_boundary_evidence
from x5crop.detection.evidence.holder_occupancy import (
    HolderOccupancyEvidence,
    StripCompletenessEvidence,
)
from x5crop.detection.evidence.partial_edge import partial_edge_safety_evidence
from x5crop.detection.evidence.separator_sequence import separator_sequence_evidence
from x5crop.detection.evidence.transform_geometry import (
    TransformGeometryEvidence,
    TransformOutcome,
)
from x5crop.configuration.scan_canvas import ScanCanvasDetectionConfiguration
from x5crop.configuration.shared_short_axis import SharedShortAxisParameters
from x5crop.detection.evidence.photo_edges import (
    NumericInterval,
    map_photo_edge_pair_evidence,
)
from x5crop.detection.evidence.scan_canvas import observe_scan_canvas
from tools.tests.photo_edge_support import (
    photo_edge_pair_fixture,
    shared_short_axis_fixture_from_edges,
)
from x5crop.detection.final.finalize import (
    finalization_plan_for_selection,
    finalize_detection,
)
from x5crop.detection.final.model import FinalDetection
from x5crop.detection.geometry_resolution import GeometryResolution
from x5crop.detection.workspace import DetectionWorkspace
from x5crop.detection.physical.frame_dimensions import frame_dimension_evidence
from x5crop.detection.physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAnchor,
    BoundaryAssignmentConsensus,
    BoundaryGeometryState,
    BoundaryRoleAuthority,
    CommonFrameWidthResolution,
    ContentExtentConstraint,
    FrameContentOccupancy,
    HolderSpanScaleHint,
    FrameWidthMeasurementConstraint,
    FrameSequenceSolution,
    FrameSlot,
    FrameEdgeAssignment,
    FrameBoundarySource,
    ResolvedFrameBoundary,
    ReviewOnlyContainment,
    SeparatorBandAssignment,
    SequenceResiduals,
)
from x5crop.detection.physical.short_axis import (
    FrameWidthSearchHint,
    SharedShortAxisPlan,
    shared_short_axis_from_photo_edge_pair,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryPathSample,
    BoundarySide,
    Box,
    ContainmentFallback,
    CrossAxisPathMeasurement,
    CrossAxisPathOutcome,
    EvidenceState,
    FrameDimensionPrior,
    GrayAppearanceObservation,
    GrayBoundaryPathObservation,
    GrayIntensityTail,
    HolderBoundaryObservation,
    HolderSafetyEnvelope,
    InterFrameBoundaryReference,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
    PixelInterval,
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
    WorkspaceExtent,
)
from x5crop.geometry.affine import AffineCoordinateTransform
from x5crop.image.statistics import (
    ImageMeasurementStatisticsParameters,
    image_measurement_statistics,
)
from x5crop.output.model import AxisBleedParameters, FrameBleedPlan, FrameSideBleed


_HOLDER_BOX = Box(0, 0, 310, 100)
_SEPARATOR = (150.0, 160.0)


def _appearance(
    provenance: MeasurementProvenance,
    *,
    texture: float,
) -> GrayAppearanceObservation:
    return GrayAppearanceObservation(
        intensity_median=32.0,
        intensity_mad=1.0,
        texture_median=texture,
        gradient_median=1.0,
        spatial_continuity=1.0,
        intensity_tail=GrayIntensityTail.LOW,
        provenance=provenance,
    )


def boundary_path_fixture(
    side: BoundarySide,
    position: PixelInterval,
    kind: BoundaryKind,
    provenance: MeasurementProvenance,
) -> GrayBoundaryPathObservation:
    axis = (
        BoundaryAxis.LONG
        if side in {BoundarySide.LEADING, BoundarySide.TRAILING}
        else BoundaryAxis.SHORT
    )
    outer = _appearance(provenance, texture=0.0)
    inner = _appearance(provenance, texture=2.0)
    lower, upper = (
        (outer, inner)
        if side in {BoundarySide.LEADING, BoundarySide.TOP}
        else (inner, outer)
    )
    return GrayBoundaryPathObservation(
        axis=axis,
        kind=kind,
        samples=(
            BoundaryPathSample(
                PixelInterval(
                    0.0,
                    float(
                        _HOLDER_BOX.width
                        if axis == BoundaryAxis.SHORT
                        else _HOLDER_BOX.height
                    ),
                ),
                position,
            ),
        ),
        lower_appearance=lower,
        upper_appearance=upper,
        provenance=provenance,
    )


def _photo_edge_path_fixture(
    side: BoundarySide,
    position: float,
    source: str,
    *,
    orthogonal_length: float = float(_HOLDER_BOX.width),
) -> GrayBoundaryPathObservation:
    provenance = MeasurementProvenance(
        MeasurementIdentity.BOUNDARY_PATHS,
        ObservationId(source),
        (MeasurementIdentity.GRAY_WORK,),
        "synthetic real-photo edge",
    )
    outer = _appearance(provenance, texture=0.0)
    inner = replace(
        _appearance(provenance, texture=2.0),
        intensity_median=64.0,
        gradient_median=4.0,
        intensity_tail=GrayIntensityTail.MIDRANGE,
    )
    lower, upper = (outer, inner) if side == BoundarySide.TOP else (inner, outer)
    return GrayBoundaryPathObservation(
        axis=BoundaryAxis.SHORT,
        kind=BoundaryKind.TONAL_TRANSITION,
        samples=(
            BoundaryPathSample(
                PixelInterval(0.0, orthogonal_length),
                PixelInterval.exact(position),
            ),
        ),
        lower_appearance=lower,
        upper_appearance=upper,
        provenance=provenance,
    )


def candidate_boundary_paths() -> tuple[GrayBoundaryPathObservation, ...]:
    leading = boundary_path_fixture(
        BoundarySide.LEADING,
        PixelInterval.exact(float(_HOLDER_BOX.left)),
        BoundaryKind.EDGE_ADJACENT_TRANSITION,
        MeasurementProvenance(
            MeasurementIdentity.BOUNDARY_PATHS,
            ObservationId("synthetic_holder_boundary:leading"),
            (MeasurementIdentity.GRAY_WORK,),
            "synthetic holder boundary",
        ),
    )
    trailing = boundary_path_fixture(
        BoundarySide.TRAILING,
        PixelInterval.exact(float(_HOLDER_BOX.right)),
        BoundaryKind.EDGE_ADJACENT_TRANSITION,
        MeasurementProvenance(
            MeasurementIdentity.BOUNDARY_PATHS,
            ObservationId("synthetic_holder_boundary:trailing"),
            (MeasurementIdentity.GRAY_WORK,),
            "synthetic holder boundary",
        ),
    )
    top = _photo_edge_path_fixture(
        BoundarySide.TOP,
        float(_HOLDER_BOX.top),
        "synthetic_photo_edge:top",
    )
    bottom = _photo_edge_path_fixture(
        BoundarySide.BOTTOM,
        float(_HOLDER_BOX.bottom),
        "synthetic_photo_edge:bottom",
    )
    return leading, trailing, top, bottom


def separator_observation(
    center: float,
    tonal_evidence: float = 1.0,
    start: float | None = None,
    end: float | None = None,
) -> SeparatorBandObservation:
    start = float(center - 1.0 if start is None else start)
    end = float(center + 1.0 if end is None else end)
    provenance = MeasurementProvenance(
        MeasurementIdentity.SEPARATOR_PROFILE,
        ObservationId(f"synthetic_separator_band:{start:.6f}:{end:.6f}"),
        (MeasurementIdentity.GRAY_WORK,),
        "synthetic separator band",
    )
    return SeparatorBandObservation(
        leading_edge=PixelInterval.exact(start),
        trailing_edge=PixelInterval.exact(end),
        tonal_evidence=float(tonal_evidence),
        appearance=_appearance(provenance, texture=0.0),
        provenance=provenance,
    )


def separator_cross_axis_measurement(
    observation: SeparatorBandObservation,
    shared_short_axis: SharedShortAxisPlan,
    state: EvidenceState = EvidenceState.SUPPORTED,
) -> SeparatorCrossAxisMeasurement:
    path = CrossAxisPathMeasurement(
        (
            CrossAxisPathOutcome.PATH_SUPPORTED
            if state == EvidenceState.SUPPORTED
            else CrossAxisPathOutcome.CONTINUITY_WEAK
        ),
        1.0 if state == EvidenceState.SUPPORTED else 0.0,
        1.0 if state == EvidenceState.SUPPORTED else 0.0,
        0,
    )
    return SeparatorCrossAxisMeasurement(
        observation_id=observation.provenance.observation_id,
        short_axis_span=shared_short_axis.measurement_span,
        leading_edge_path=path,
        trailing_edge_path=path,
        band_path=path,
        appearance_coherence_ratio=(
            1.0 if state == EvidenceState.SUPPORTED else 0.0
        ),
    )


def _measured_boundary(
    position: float,
    path: GrayBoundaryPathObservation,
    side: BoundarySide,
) -> ResolvedFrameBoundary:
    return ResolvedFrameBoundary(
        position=PixelInterval.exact(position),
        source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=BoundaryAnchor(
            path,
            side,
            EvidenceState.SUPPORTED,
            BoundaryRoleAuthority.DIRECT_MEASUREMENT,
            path.provenance,
        ),
        inference_provenance=None,
    )


def _separator_boundary(
    position: float,
    observation: SeparatorBandObservation,
    side: BoundarySide,
) -> ResolvedFrameBoundary:
    return ResolvedFrameBoundary(
        position=PixelInterval.exact(position),
        source=FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=BoundaryAnchor(
            observation,
            side,
            EvidenceState.SUPPORTED,
            BoundaryRoleAuthority.DIRECT_MEASUREMENT,
            observation.provenance,
        ),
        inference_provenance=None,
    )


def _dimension_boundary(
    frame_index: int,
    side: BoundarySide,
    position: float,
) -> ResolvedFrameBoundary:
    provenance = MeasurementProvenance(
        MeasurementIdentity.FRAME_GEOMETRY,
        ObservationId(f"synthetic_dimension_edge:{frame_index}:{side.value}"),
        (MeasurementIdentity.FRAME_DIMENSIONS,),
        "synthetic dimension-only frame edge",
    )
    return ResolvedFrameBoundary(
        position=PixelInterval.exact(position),
        source=FrameBoundarySource.DIMENSION_CONSTRAINED,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=None,
        inference_provenance=provenance,
    )


def _candidate_geometry(
    *,
    boundary_proof_supported: bool = True,
) -> FrameSequenceSolution:
    paths = candidate_boundary_paths()
    leading_path, trailing_path, top_path, bottom_path = paths
    shared_short_axis = shared_short_axis_fixture_from_edges(
        top_path,
        bottom_path,
    )
    observation = separator_observation(
        sum(_SEPARATOR) / 2.0,
        start=_SEPARATOR[0],
        end=_SEPARATOR[1],
    )
    separator_measurement = separator_cross_axis_measurement(
        observation,
        shared_short_axis,
    )
    first_leading = _measured_boundary(0.0, leading_path, BoundarySide.LEADING)
    second_trailing = _measured_boundary(
        310.0,
        trailing_path,
        BoundarySide.TRAILING,
    )
    if boundary_proof_supported:
        first_trailing = _separator_boundary(
            _SEPARATOR[0],
            observation,
            BoundarySide.TRAILING,
        )
        second_leading = _separator_boundary(
            _SEPARATOR[1],
            observation,
            BoundarySide.LEADING,
        )
    else:
        first_trailing = _dimension_boundary(1, BoundarySide.TRAILING, _SEPARATOR[0])
        second_leading = _dimension_boundary(2, BoundarySide.LEADING, _SEPARATOR[1])
    slots = (
        FrameSlot(
            1,
            PixelInterval(0.0, 150.0),
            first_leading,
            first_trailing,
            FrameContentOccupancy.CONTENT_OBSERVED,
            None,
        ),
        FrameSlot(
            2,
            PixelInterval(160.0, 310.0),
            second_leading,
            second_trailing,
            FrameContentOccupancy.CONTENT_OBSERVED,
            None,
        ),
    )
    separator_assignments = (
        (
            SeparatorBandAssignment(
                1,
                observation,
                separator_measurement,
                PixelInterval.exact(150.0),
                first_trailing,
                second_leading,
            ),
        )
        if boundary_proof_supported
        else ()
    )
    spacing = InterFrameSpacing(
        InterFrameBoundaryReference(None, 1),
        PixelInterval.exact(_SEPARATOR[1] - _SEPARATOR[0]),
        (
            observation.provenance
            if boundary_proof_supported
            else MeasurementProvenance(
                MeasurementIdentity.FRAME_GEOMETRY,
                ObservationId("synthetic_dimension_spacing:1"),
                (MeasurementIdentity.FRAME_DIMENSIONS,),
                "synthetic dimension-only spacing",
            )
        ),
        (
            InterFrameSpacingBasis.OBSERVED
            if boundary_proof_supported
            else InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
        ),
    )
    width_provenance = MeasurementProvenance(
        MeasurementIdentity.FRAME_DIMENSIONS,
        ObservationId("synthetic_common_frame_width"),
        (MeasurementIdentity.PHOTO_EDGES,),
        "synthetic common frame width",
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    first_leading.measurement_provenance.observation_id,
                    first_trailing.measurement_provenance.observation_id,
                    second_leading.measurement_provenance.observation_id,
                    second_trailing.measurement_provenance.observation_id,
                )
            )
        ),
    )
    holder_paths = (
        leading_path,
        trailing_path,
        *(
            boundary_path_fixture(
                side,
                PixelInterval.exact(position),
                BoundaryKind.EDGE_ADJACENT_TRANSITION,
                MeasurementProvenance(
                    MeasurementIdentity.BOUNDARY_PATHS,
                    ObservationId(f"synthetic_holder_boundary:{side.value}"),
                    (MeasurementIdentity.GRAY_WORK,),
                    "synthetic holder boundary",
                ),
            )
            for side, position in (
                (BoundarySide.TOP, float(_HOLDER_BOX.top)),
                (BoundarySide.BOTTOM, float(_HOLDER_BOX.bottom)),
            )
        ),
    )
    holder_boundaries = tuple(
        HolderBoundaryObservation(side, path.position, (path,))
        for side, path in zip(
            (
                BoundarySide.LEADING,
                BoundarySide.TRAILING,
                BoundarySide.TOP,
                BoundarySide.BOTTOM,
            ),
            holder_paths,
            strict=True,
        )
    )
    containment = ContainmentFallback(
        _HOLDER_BOX,
        MeasurementProvenance(
            MeasurementIdentity.CANVAS,
            ObservationId("synthetic_holder_containment"),
            (),
            "synthetic holder containment",
        ),
    )
    holder_safety = HolderSafetyEnvelope(holder_boundaries, containment)
    width_constraints = tuple(
        FrameWidthMeasurementConstraint(
            slot.index,
            slot.leading,
            slot.trailing,
        )
        for slot in slots
        if slot.leading.independently_observed
        and slot.trailing.independently_observed
    )
    common_width_supported = len(width_constraints) >= 2
    return FrameSequenceSolution(
        format_id="135",
        layout="horizontal",
        strip_mode="partial",
        count=2,
        nominal_count=6,
        holder_safety=holder_safety,
        shared_short_axis=shared_short_axis,
        frame_width_search_hint=FrameWidthSearchHint(
            shared_short_axis.height_px.scaled(1.5),
            shared_short_axis.provenance,
        ),
        holder_span_scale_hint=HolderSpanScaleHint(
            PixelInterval.exact(float(holder_safety.box.width)),
            2,
            containment.provenance,
        ),
        content_extent_constraint=ContentExtentConstraint(
            PixelInterval(float(_HOLDER_BOX.left), float(_HOLDER_BOX.right)),
            (),
            0,
            MeasurementProvenance(
                MeasurementIdentity.CONTENT_EVIDENCE_IMAGE,
                ObservationId("synthetic_content_extent_constraint"),
                (MeasurementIdentity.GRAY_WORK,),
                "synthetic visible-content extent constraint",
            ),
        ),
        indexed_anchor_distance_constraints=(),
        frame_slots=slots,
        long_axis_assignments=(
            FrameEdgeAssignment(
                1,
                BoundarySide.LEADING,
                leading_path,
                first_leading,
            ),
            FrameEdgeAssignment(
                2,
                BoundarySide.TRAILING,
                trailing_path,
                second_trailing,
            ),
        ),
        separator_observations=(observation,),
        separator_assignments=separator_assignments,
        inter_frame_spacings=(spacing,),
        frame_dimension_prior=FrameDimensionPrior(
            (36.0, 24.0),
            MeasurementProvenance(
                MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
                ObservationId("synthetic_frame_dimension_prior"),
                (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                "synthetic frame dimension prior",
            ),
        ),
        common_frame_width=CommonFrameWidthResolution(
            PixelInterval.exact(150.0) if common_width_supported else None,
            width_constraints if common_width_supported else (),
            None,
            (
                EvidenceState.SUPPORTED
                if common_width_supported
                else EvidenceState.UNAVAILABLE
            ),
            width_provenance,
        ),
        residuals=SequenceResiduals(0.0, 0.0),
        assignment_consensus=BoundaryAssignmentConsensus(
            AssignmentConsensusOutcome.UNCONTESTED,
            1,
            (),
        ),
        raw_boundary_paths=(*holder_paths, top_path, bottom_path),
    )


def candidate_gate_fixture(
    *,
    passed: bool = True,
    failed_check: str = "sequence_proof",
) -> CandidateGateAssessment:
    states = {
        "frame_slot_topology": EvidenceState.SUPPORTED,
        "content_preservation": EvidenceState.SUPPORTED,
        "frame_dimension_consistency": EvidenceState.SUPPORTED,
        "evidence_independence": EvidenceState.SUPPORTED,
    }
    if not passed and failed_check in states:
        states[failed_check] = EvidenceState.CONTRADICTED
    proof_state = (
        EvidenceState.CONTRADICTED
        if not passed and failed_check == "sequence_proof"
        else EvidenceState.SUPPORTED
    )
    return candidate_gate_assessment(
        CandidateGateInput(
            frame_slot_topology=states["frame_slot_topology"],
            content_preservation=states["content_preservation"],
            frame_dimensions=states["frame_dimension_consistency"],
            evidence_independence=states["evidence_independence"],
            proof_paths=(
                SequenceProofPath(
                    "separator_sequence_led",
                    proof_state,
                    ("synthetic_separator_sequence",),
                ),
                SequenceProofPath(
                    "dimension_sequence_led",
                    EvidenceState.UNAVAILABLE,
                    ("synthetic_frame_dimensions",),
                ),
                SequenceProofPath(
                    "partial_occupancy_led",
                    EvidenceState.NOT_APPLICABLE,
                    ("synthetic_full_strip",),
                ),
            ),
        )
    )


def candidate_evidence_fixture(
    *,
    content_preservation: EvidenceState = EvidenceState.SUPPORTED,
    geometry: FrameSequenceSolution | None = None,
) -> CandidateEvidence:
    if content_preservation not in {
        EvidenceState.SUPPORTED,
        EvidenceState.CONTRADICTED,
    }:
        raise ValueError("candidate evidence fixture requires resolved content state")
    geometry = geometry or _candidate_geometry()
    intervals = tuple(
        (item.box.left, item.box.right) for item in geometry.frame_crop_envelopes
    )
    content_runs = ((10, 140), (170, 300))
    coverage = FrameCoverageEvidence(
        (_HOLDER_BOX.left, _HOLDER_BOX.right),
        intervals,
        content_runs,
        0,
    )
    content = FrameContentEvidence(
        0.5,
        tuple(
            FrameContentObservation(index, 0.8, 0.8, True, ())
            for index in range(1, geometry.count + 1)
        ),
    )
    dimensions = frame_dimension_evidence(geometry, None, None)
    holder = holder_boundary_evidence(geometry, 1.0)
    continuity = tuple(
        InternalBoundaryContentContinuityObservation(
            boundary=InterFrameBoundaryReference(None, boundary_index),
            shared_content_track_count=0,
            minimum_shared_content_tracks=1,
            long_axis_content_spans_boundary=False,
            content_bridge_track_count=1,
            minimum_content_bridge_tracks=1,
            gray_discontinuity_track_count=0,
            minimum_gray_discontinuity_tracks=1,
            provenance=MeasurementProvenance(
                MeasurementIdentity.CONTENT_EVIDENCE_IMAGE,
                ObservationId(
                    f"synthetic_internal_content_continuity:{boundary_index}"
                ),
                (
                    MeasurementIdentity.GRAY_WORK,
                    MeasurementIdentity.FRAME_GEOMETRY,
                ),
                "synthetic internal-boundary content continuity",
            ),
        )
        for boundary_index in range(1, geometry.count)
    )
    internal = internal_frame_boundary_preservation_evidence(
        geometry.frame_slots,
        geometry.inter_frame_spacings,
        continuity,
    )
    external = ExternalFramePreservationEvidence(
        Box(0, 0, 311, 101),
        geometry.frame_sequence_envelope,
        geometry.count,
        (
            ExternalFrameBoundaryObservation(
                1,
                BoundarySide.LEADING,
                geometry.frame_slots[0].leading.source,
                Box(0, 0, 1, 100),
                None,
                0,
                0,
                0,
                1,
                1,
                False,
            ),
            ExternalFrameBoundaryObservation(
                geometry.count,
                BoundarySide.TRAILING,
                geometry.frame_slots[-1].trailing.source,
                Box(309, 0, 310, 100),
                Box(310, 0, 311, 100),
                int(content_preservation == EvidenceState.CONTRADICTED),
                int(content_preservation == EvidenceState.CONTRADICTED),
                int(content_preservation == EvidenceState.CONTRADICTED),
                1,
                1,
                content_preservation == EvidenceState.CONTRADICTED,
            ),
        ),
        0.5,
    )
    completeness = StripCompletenessEvidence(
        geometry.count,
        geometry.nominal_count,
        len(geometry.frame_slots),
        geometry.count - 1,
        len(geometry.separator_assignments),
    )
    partial = partial_edge_safety_evidence(
        geometry,
        coverage,
        dimensions,
        content,
    )
    return CandidateEvidence(
        frame_slot_topology=frame_slot_topology_evidence(geometry),
        frame_coverage=coverage,
        separator_sequence=separator_sequence_evidence(geometry),
        frame_dimensions=dimensions,
        frame_content=content,
        internal_frame_boundary_preservation=internal,
        holder_boundary=holder,
        external_frame_preservation=external,
        holder_occupancy=HolderOccupancyEvidence(
            completeness,
            content.support_available,
            coverage.state,
            dimensions.state,
            False,
            geometry.holder_safety,
            geometry.frame_slots[0].leading.position,
            geometry.frame_slots[-1].trailing.position,
        ),
        partial_edge_safety=partial,
        independence=evidence_independence_evidence(geometry),
    )


def candidate_fixture(
    *,
    failed_candidate_check: str | None = None,
    content_preservation: EvidenceState = EvidenceState.SUPPORTED,
) -> AssessedCandidate:
    if failed_candidate_check not in {
        None,
        "sequence_proof",
        "content_preservation",
    }:
        raise ValueError("candidate fixture requires a physical failed check")
    geometry = _candidate_geometry(
        boundary_proof_supported=failed_candidate_check != "sequence_proof",
    )
    evidence = candidate_evidence_fixture(
        content_preservation=(
            EvidenceState.CONTRADICTED
            if failed_candidate_check == "content_preservation"
            else content_preservation
        ),
        geometry=geometry,
    )
    hypothesis = CountHypothesis(2, "partial", CountHypothesisSource.REQUESTED)
    built = BuiltCandidate(geometry, hypothesis, ())
    return AssessedCandidate(
        geometry,
        hypothesis,
        CandidateAssessment(
            evidence,
            candidate_gate_for_evidence(built, evidence),
        ),
    )


def review_only_candidate_fixture() -> AssessedCandidate:
    source = _candidate_geometry()
    geometry = ReviewOnlyContainment(
        source.format_id,
        source.layout,
        source.strip_mode,
        source.count,
        source.holder_safety,
        source.frame_dimension_prior,
        source.residuals,
        BoundaryAssignmentConsensus(
            AssignmentConsensusOutcome.NOT_APPLICABLE,
            0,
            (),
        ),
        source.sequence_provenance,
        source.raw_boundary_paths,
    )
    return assess_review_only_candidate(
        BuiltCandidate(
            geometry,
            CountHypothesis(
                geometry.count,
                geometry.strip_mode,
                CountHypothesisSource.HARD_SAFETY,
            ),
            ("frame_slot_geometry_unresolved",),
        )
    )


def selection_fixture(
    candidate: AssessedCandidate | None = None,
    *,
    geometry_disagreement: bool = False,
) -> SelectionResult:
    selected = candidate or candidate_fixture()
    geometry_resolved = not isinstance(selected.geometry, ReviewOnlyContainment)
    cluster = GeometryCluster((selected,), selected)
    return SelectionResult(
        selected,
        (selected,),
        (cluster,),
        (
            SelectionConsensus.DISAGREED
            if geometry_disagreement
            else SelectionConsensus.UNCONTESTED
        ),
        GeometryResolution(
            count_resolved=geometry_resolved,
            frame_slots_resolved=geometry_resolved,
            shared_short_axis_safe=geometry_resolved,
            content_preservation_compatible=geometry_resolved,
            larger_count_search_complete=True,
            alternative_geometries_resolved=not geometry_disagreement,
            assignment_consensus_resolved=geometry_resolved,
            physical_search=PhysicalSearchOutcome(
                (PhysicalSearchFact.SOLUTION_FOUND,),
            ),
        ),
    )


def frame_bleed_fixture(*, feasible: bool = True) -> FrameBleedPlan:
    return FrameBleedPlan(
        AxisBleedParameters(20, 10),
        (_HOLDER_BOX, _HOLDER_BOX),
        (
            FrameSideBleed(0, 20, 20, 10),
            FrameSideBleed(1, 20, 20, 10),
        ),
        (),
        (() if feasible else (InterFrameBoundaryReference(None, 1),)),
    )


def transform_geometry_fixture(
    state: EvidenceState = EvidenceState.SUPPORTED,
    *,
    width: int = _HOLDER_BOX.width,
    height: int = _HOLDER_BOX.height,
) -> TransformGeometryEvidence:
    outcome = {
        EvidenceState.SUPPORTED: TransformOutcome.IDENTITY_WITHIN_TOLERANCE,
        EvidenceState.UNAVAILABLE: TransformOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE,
        EvidenceState.CONTRADICTED: TransformOutcome.ANGLE_OUT_OF_RANGE,
    }.get(state)
    if outcome is None:
        raise ValueError("transform fixture requires a decision-relevant state")
    measured = outcome == TransformOutcome.IDENTITY_WITHIN_TOLERANCE
    return TransformGeometryEvidence(
        outcome=outcome,
        estimated_angle_degrees=(
            0.0 if measured else None
        ),
        pixel_angle_interval_degrees=(
            NumericInterval.exact(0.0) if measured else None
        ),
        projected_edge_drift_px=0.0 if measured else None,
        identity_drift_threshold_px=1.0 if measured else None,
        position_uncertainty_px=0.0,
        coordinate_transform=AffineCoordinateTransform.identity(
            width,
            height,
        ),
    )


def detection_workspace_fixture(
    transform_state: EvidenceState = EvidenceState.SUPPORTED,
    *,
    width: int = _HOLDER_BOX.width,
    height: int = _HOLDER_BOX.height,
    gray_override: np.ndarray | None = None,
) -> DetectionWorkspace:
    gray = (
        np.zeros((height, width), dtype=np.uint8)
        if gray_override is None
        else np.asarray(gray_override, dtype=np.uint8)
    )
    if gray.ndim != 2:
        raise ValueError("detection workspace fixture gray must be two-dimensional")
    height, width = gray.shape
    statistics = image_measurement_statistics(
        gray,
        ImageMeasurementStatisticsParameters(),
    )
    cache = make_measurement_cache(
        gray,
        "horizontal",
        statistics,
        0.0,
        MeasurementCacheStatistics(),
    )
    top_path = _photo_edge_path_fixture(
        BoundarySide.TOP,
        0.0,
        "synthetic_workspace_photo_edge:top",
        orthogonal_length=float(width),
    )
    bottom_path = _photo_edge_path_fixture(
        BoundarySide.BOTTOM,
        min(float(_HOLDER_BOX.bottom), float(height)),
        "synthetic_workspace_photo_edge:bottom",
        orthogonal_length=float(width),
    )
    photo_edge_pairs = photo_edge_pair_fixture(top_path, bottom_path)
    transform = transform_geometry_fixture(
        transform_state,
        width=width,
        height=height,
    )
    mapped_photo_edge_pairs = map_photo_edge_pair_evidence(
        photo_edge_pairs,
        transform.coordinate_transform,
        "horizontal",
        transform.position_uncertainty_px,
    )
    plan = shared_short_axis_from_photo_edge_pair(
        mapped_photo_edge_pairs,
        transform,
        width,
        SharedShortAxisParameters(),
    )
    return DetectionWorkspace(
        pixels=gray,
        source_gray=gray,
        gray=gray,
        measurement_cache=cache,
        scan_canvas_evidence=observe_scan_canvas(
            width,
            height,
            "horizontal",
            ScanCanvasDetectionConfiguration(()),
        ),
        source_photo_edge_pairs=(photo_edge_pairs,),
        dual_lane_photo_edge_geometry=None,
        mapped_photo_edge_pairs=(mapped_photo_edge_pairs,),
        shared_short_axes=(plan,),
        source_lane_divider=None,
        lane_divider=None,
        transform_geometry=transform,
    )


def decide_candidate(
    candidate: AssessedCandidate | None = None,
    *,
    geometry_disagreement: bool = False,
    output_protection_feasible: bool = True,
    transform_state: EvidenceState = EvidenceState.SUPPORTED,
    automatic_processing_eligible: bool = True,
) -> DecisionGateAssessment:
    selection = selection_fixture(
        candidate,
        geometry_disagreement=geometry_disagreement,
    )
    frame_bleed = (
        frame_bleed_fixture(feasible=output_protection_feasible)
        if selection.selected.assessment.gate is not None
        else FrameBleedPlan(AxisBleedParameters(20, 10), (), (), (), ())
    )
    return apply_decision_gate(
        selection,
        frame_bleed,
        detection_workspace_fixture().scan_canvas_evidence,
        transform_geometry_fixture(transform_state),
        automatic_processing_eligibility=(
            EvidenceState.SUPPORTED
            if automatic_processing_eligible
            else EvidenceState.CONTRADICTED
        ),
    )


def final_detection_fixture(
    *,
    failed_candidate_check: str | None = None,
) -> FinalDetection:
    selection = selection_fixture(
        candidate_fixture(failed_candidate_check=failed_candidate_check)
    )
    bleed = frame_bleed_fixture()
    return finalize_detection(
        apply_decision_gate(
            selection,
            bleed,
            detection_workspace_fixture().scan_canvas_evidence,
            transform_geometry_fixture(),
            automatic_processing_eligibility=EvidenceState.SUPPORTED,
        ),
        bleed,
        finalization_plan_for_selection(
            selection,
            workspace_extent=WorkspaceExtent(
                _HOLDER_BOX.right,
                _HOLDER_BOX.bottom,
            ),
        ),
    )
