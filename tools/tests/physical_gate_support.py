from __future__ import annotations

from dataclasses import replace

from x5crop.detection.candidate.assessment.candidate_gate import (
    BoundaryProofPath,
    CandidateGateAssessment,
)
from x5crop.detection.candidate.assessment.candidate import (
    candidate_gate_for_evidence,
)
from x5crop.detection.candidate.assessment.evidence_independence import (
    EvidenceIndependenceEvidence,
    evidence_independence_evidence,
)
from x5crop.detection.evidence.separator_sequence import (
    SeparatorSequenceEvidence,
)
from x5crop.detection.candidate.model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
)
from x5crop.detection.candidate.plan.count_hypotheses import (
    CountHypothesis,
    CountHypothesisSource,
)
from x5crop.detection.candidate.selection.model import (
    GeometryCluster,
    SelectionConsensus,
    SelectionResult,
)
from x5crop.detection.geometry_resolution import GeometryResolution
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.decision.model import DecisionGateAssessment
from x5crop.detection.final.model import FinalDetection
from x5crop.detection.final.finalize import (
    finalization_plan_for_selection,
    finalize_detection,
)
from x5crop.detection.evidence.content.frame_support import (
    FrameContentEvidence,
    FrameContentObservation,
)
from x5crop.detection.evidence.content.internal_boundaries import (
    InternalBoundaryObservation,
    InternalBoundaryPreservationEvidence,
)
from x5crop.detection.evidence.holder_boundary import (
    HolderBoundaryEvidence,
)
from x5crop.detection.evidence.frame_coverage import FrameCoverageEvidence
from x5crop.detection.evidence.frame_sequence import sequence_conservation_for_geometry
from x5crop.detection.evidence.physical_scale import candidate_scan_calibration
from x5crop.detection.evidence.holder_occupancy import (
    HolderOccupancyEvidence,
    StripCompletenessEvidence,
)
from x5crop.detection.evidence.sequence_content_alignment import SequenceContentAlignmentEvidence
from x5crop.detection.evidence.partial_edge import (
    PartialEdgeSafetyEvidence,
    partial_edge_safety_evidence,
)
from x5crop.domain import EvidenceState, FrameBoundaryReference, WorkspaceExtent
from x5crop.detection.evidence.transform_geometry import (
    TransformGeometryEvidence,
    TransformOutcome,
)
from x5crop.image.deskew import DeskewMeasurementOutcome
from x5crop.detection.gate_checks import GateCheck, GateStage
from x5crop.detection.physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    PhotoInterval,
    SequenceResiduals,
    SequenceSolution,
)
from x5crop.detection.physical.photo_size import (
    FrameDimensionEvidence,
    frame_dimension_evidence,
)
from x5crop.detection.physical.boundary import (
    HolderOcclusionEvidence,
    HolderOcclusionSideEvidence,
    HolderOcclusionSideOutcome,
)
from x5crop.domain import PixelInterval
from x5crop.detection.physical.spacing import (
    SequenceConservationBasis,
    SequenceConservationEvidence,
    observed_spacing_evidence,
)
from x5crop.domain import (
    BoundaryKind,
    BoundaryPathObservation,
    BoundarySide,
    GrayIntensityTail,
    GrayAppearanceObservation,
)
from x5crop.domain import CropEnvelope, HolderSpan, VisibleSequenceSpan
from x5crop.detection.physical.separator.assignment import (
    assign_observation_to_boundary,
    frame_boundary_from_assignment,
)
from x5crop.domain import (
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
    SeparatorCrossAxisOutcome,
)
from x5crop.domain import (
    BoundaryPositionConstraint,
    Box,
    FrameDimensionPrior,
    FrameDimensionPriorSource,
    MeasurementIdentity,
    MeasurementProvenance,
    SeparatorWidthConstraint,
)
from x5crop.output.model import AxisBleedParameters, FrameBleedPlan, FrameSideBleed
from x5crop.units import (
    PhysicalScaleObservation,
    PhysicalScaleScope,
    PhysicalScaleSource,
    ResolutionMetadataObservation,
    ScanCalibrationResolution,
)


def boundary_path_fixture(
    side: BoundarySide,
    position: PixelInterval,
    kind: BoundaryKind,
    provenance: MeasurementProvenance,
) -> BoundaryPathObservation:
    outer_appearance = (
        GrayAppearanceObservation(
            intensity_median=0.0,
            intensity_mad=0.0,
            texture_median=(
                0.0
                if kind == BoundaryKind.HOLDER_BOUNDARY_TRANSITION
                else 2.0
            ),
            gradient_median=0.0,
            spatial_continuity=1.0,
            intensity_tail=GrayIntensityTail.LOW,
            provenance=provenance,
        )
        if kind != BoundaryKind.CANVAS_CLIP
        else None
    )
    return BoundaryPathObservation(
        side=side,
        position=position,
        kind=kind,
        local_positions=(position,),
        outer_appearance=outer_appearance,
        inner_appearance=(
            GrayAppearanceObservation(
                intensity_median=1.0,
                intensity_mad=0.0,
                texture_median=0.0,
                gradient_median=0.0,
                spatial_continuity=1.0,
                intensity_tail=GrayIntensityTail.LOW,
                provenance=provenance,
            )
            if kind != BoundaryKind.CANVAS_CLIP
            else None
        ),
        provenance=provenance,
    )


def candidate_boundary_paths() -> tuple[BoundaryPathObservation, ...]:
    return tuple(
        boundary_path_fixture(
            side,
            PixelInterval.exact(position),
            BoundaryKind.HOLDER_BOUNDARY_TRANSITION,
            MeasurementProvenance(
                MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
                "synthetic_boundary",
                (MeasurementIdentity.GRAY_WORK,),
                (side.value,),
            ),
        )
        for side, position in (
            (BoundarySide.LEADING, 0.0),
            (BoundarySide.TRAILING, 200.0),
            (BoundarySide.TOP, 0.0),
            (BoundarySide.BOTTOM, 100.0),
        )
    )


def unavailable_calibration_fixture() -> ScanCalibrationResolution:
    return ScanCalibrationResolution.from_observations(
        ResolutionMetadataObservation(None, None, ("test_metadata_unavailable",)),
        (),
    )


def supported_calibration_fixture(
    x_px_per_mm: float,
    y_px_per_mm: float,
) -> ScanCalibrationResolution:
    metadata = ResolutionMetadataObservation(x_px_per_mm, y_px_per_mm)
    observations = (
        PhysicalScaleObservation(
            "x",
            x_px_per_mm,
            x_px_per_mm,
            PhysicalScaleSource.FRAME_DIMENSION_CONSENSUS,
            PhysicalScaleScope.ROOT_MEASUREMENT,
            MeasurementProvenance(
                MeasurementIdentity.PHOTO_EDGES,
                "test_scale",
                (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
            ),
        ),
        PhysicalScaleObservation(
            "y",
            y_px_per_mm,
            y_px_per_mm,
            PhysicalScaleSource.FRAME_DIMENSION_CONSENSUS,
            PhysicalScaleScope.ROOT_MEASUREMENT,
            MeasurementProvenance(
                MeasurementIdentity.PHOTO_EDGES,
                "test_scale",
                (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
            ),
        ),
    )
    return ScanCalibrationResolution.from_observations(metadata, observations)


def separator_observation(
    center: float,
    tonal_evidence: float = 1.0,
    start: float | None = None,
    end: float | None = None,
    cross_axis_state: EvidenceState = EvidenceState.SUPPORTED,
) -> SeparatorBandObservation:
    start = float(center - 1.0 if start is None else start)
    end = float(center + 1.0 if end is None else end)
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.SEPARATOR_PROFILE,
        source="test_fixture",
        dependencies=(MeasurementIdentity.GRAY_WORK,),
    )
    return SeparatorBandObservation(
        start=start,
        end=end,
        center=center,
        tonal_evidence=tonal_evidence,
        appearance=GrayAppearanceObservation(
            intensity_median=0.0,
            intensity_mad=0.0,
            texture_median=0.0,
            gradient_median=0.0,
            spatial_continuity=(
                1.0 if cross_axis_state == EvidenceState.SUPPORTED else 0.0
            ),
            intensity_tail=GrayIntensityTail.LOW,
            provenance=provenance,
        ),
        provenance=provenance,
        cross_axis=SeparatorCrossAxisMeasurement(
            outcome=(
                SeparatorCrossAxisOutcome.PATH_SUPPORTED
                if cross_axis_state == EvidenceState.SUPPORTED
                else SeparatorCrossAxisOutcome.CONTINUITY_WEAK
            ),
            coverage_ratio=(
                1.0 if cross_axis_state == EvidenceState.SUPPORTED else 0.0
            ),
            continuity_ratio=(
                1.0 if cross_axis_state == EvidenceState.SUPPORTED else 0.0
            ),
            break_count=0,
            straightness=(
                1.0 if cross_axis_state == EvidenceState.SUPPORTED else 0.0
            ),
        ),
    )


def holder_occlusion_not_applicable() -> HolderOcclusionEvidence:
    def side(name: BoundarySide) -> HolderOcclusionSideEvidence:
        boundary = boundary_path_fixture(
            name,
            PixelInterval.exact(
                0.0 if name == BoundarySide.LEADING else 200.0
            ),
            BoundaryKind.TONAL_TRANSITION,
            MeasurementProvenance(
                MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
                "synthetic_non_holder_boundary_edge",
                (MeasurementIdentity.GRAY_WORK,),
            ),
        )
        return HolderOcclusionSideEvidence(
            name,
            HolderOcclusionSideOutcome.BOUNDARY_NOT_HOLDER_REGION,
            PixelInterval.zero(),
            boundary,
        )

    return HolderOcclusionEvidence(
        side(BoundarySide.LEADING),
        side(BoundarySide.TRAILING),
    )


def separator_constraints(
    index: int,
    position: PixelInterval,
    width: PixelInterval = PixelInterval(0.0, 1000.0),
) -> tuple[BoundaryPositionConstraint, SeparatorWidthConstraint]:
    provenance = MeasurementProvenance(
        MeasurementIdentity.FRAME_DIMENSIONS,
        "test_constraint",
        (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
    )
    return (
        BoundaryPositionConstraint(index, position, provenance),
        SeparatorWidthConstraint(index, width, provenance),
    )


def candidate_gate_fixture(
    *,
    passed: bool = True,
    failed_check: str = "boundary_proof",
) -> CandidateGateAssessment:
    codes = (
        "content_preservation",
        "photo_geometry_consistency",
        "frame_sequence_conservation",
        "evidence_independence",
        "boundary_proof",
    )
    checks = tuple(
        GateCheck(
            code=code,
            stage=GateStage.CANDIDATE,
            state=(
                EvidenceState.CONTRADICTED
                if not passed and code == failed_check
                else EvidenceState.SUPPORTED
            ),
        )
        for code in codes
    )
    boundary_supported = passed or failed_check != "boundary_proof"
    proof_paths = (
        BoundaryProofPath(
            code="separator_sequence_led",
            state=(
                EvidenceState.SUPPORTED
                if boundary_supported
                else EvidenceState.UNAVAILABLE
            ),
            supporting_evidence=("test_fixture",),
        ),
        BoundaryProofPath(
            code="geometry_led",
            state=EvidenceState.UNAVAILABLE,
            supporting_evidence=("test_fixture",),
        ),
        BoundaryProofPath(
            code="partial_occupancy_led",
            state=EvidenceState.NOT_APPLICABLE,
            supporting_evidence=("test_fixture",),
        ),
    )
    return CandidateGateAssessment(
        checks=checks,
        proof_paths=proof_paths,
        diagnostics=(),
    )


def candidate_evidence_fixture(
    *,
    content_preservation: EvidenceState = EvidenceState.SUPPORTED,
) -> CandidateEvidence:
    if content_preservation not in {
        EvidenceState.SUPPORTED,
        EvidenceState.CONTRADICTED,
    }:
        raise ValueError("candidate evidence fixture requires resolved content state")
    sequence_box = Box(0, 0, 200, 100)
    holder_box = (
        Box(0, 0, 210, 100)
        if content_preservation == EvidenceState.CONTRADICTED
        else sequence_box
    )
    frames = (Box(0, 0, 100, 100), Box(100, 0, 200, 100))
    holder_span = HolderSpan(holder_box)
    visible_sequence_span = VisibleSequenceSpan(sequence_box)
    completeness = StripCompletenessEvidence(2, 2, 2, 1, 1)
    coverage = FrameCoverageEvidence(
        holder_long_axis_interval=(holder_box.left, holder_box.right),
        visible_sequence_interval=(0, 200),
        frame_intervals=((0, 200),),
        content_runs=(
            ((10, 205),)
            if content_preservation == EvidenceState.CONTRADICTED
            else ((10, 190),)
        ),
        candidate_frame_count=2,
    )
    paths = candidate_boundary_paths()
    content = FrameContentEvidence(
        0.5,
        (
            FrameContentObservation(1, 0.8, 0.8, True, ()),
            FrameContentObservation(2, 0.8, 0.8, True, ()),
        ),
    )
    return CandidateEvidence(
        frame_coverage=coverage,
        sequence_conservation=SequenceConservationEvidence(
            PixelInterval.exact(200.0),
            PixelInterval.zero(),
            PixelInterval.exact(190.0),
            PixelInterval.exact(10.0),
            SequenceConservationBasis.INDEPENDENT_SPACING,
        ),
        separator_sequence=SeparatorSequenceEvidence(
            1,
            1,
            0,
            (FrameBoundaryReference(None, 1),),
            (),
            (1.0,),
        ),
        frame_dimensions=FrameDimensionEvidence(
            frame_width_mm=36.0,
            frame_height_mm=24.0,
            frame_width_prior_px=PixelInterval.exact(95.0),
            photo_width_intervals_px=(
                PixelInterval.exact(95.0),
                PixelInterval.exact(95.0),
            ),
            separator_widths_px=(10.0,),
            observed_width_mm=None,
            observed_height_mm=None,
            observed_aspect=1.5,
            aspect_error_ratio=0.0,
            calibration_used=False,
        ),
        frame_content=content,
        internal_boundary_preservation=InternalBoundaryPreservationEvidence(
            (
                InternalBoundaryObservation(
                    FrameBoundaryReference(None, 1),
                    True,
                    False,
                    False,
                    False,
                ),
            )
        ),
        holder_boundary=HolderBoundaryEvidence(paths, 1.0),
        scan_calibration=unavailable_calibration_fixture(),
        sequence_content_alignment=SequenceContentAlignmentEvidence(
            sequence_box,
            Box(10, 10, 190, 90),
        ),
        holder_occupancy=HolderOccupancyEvidence(
            strip_completeness=completeness,
            content_support_available=True,
            frame_coverage_state=coverage.state,
            frame_dimension_state=EvidenceState.SUPPORTED,
            complete_strip_can_be_underfilled=False,
            holder_span=holder_span,
            visible_sequence_span=visible_sequence_span,
            source_long_axis="x",
            long_axis_px_per_mm=None,
        ),
        partial_edge_safety=PartialEdgeSafetyEvidence(
            is_partial=False,
            hard_separator_count=1,
            expected_separator_count=1,
            frame_coverage_state=coverage.state,
            frame_dimension_state=EvidenceState.SUPPORTED,
            diagnostics=(),
        ),
        independence=EvidenceIndependenceEvidence(
            MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
            (MeasurementIdentity.SEPARATOR_PROFILE,),
            (),
            True,
        ),
    )


def candidate_fixture(
    *,
    failed_candidate_check: str | None = None,
    automatic_processing_supported: bool = True,
    content_preservation: EvidenceState = EvidenceState.SUPPORTED,
) -> AssessedCandidate:
    if failed_candidate_check not in {
        None,
        "boundary_proof",
        "content_preservation",
    }:
        raise ValueError("candidate fixture requires a physical failed check")
    sequence_box = Box(0, 0, 200, 100)
    holder_box = (
        Box(0, 0, 210, 100)
        if content_preservation == EvidenceState.CONTRADICTED
        else sequence_box
    )
    frames = (Box(0, 0, 100, 100), Box(100, 0, 200, 100))
    observation = separator_observation(100.0, start=95.0, end=105.0)
    assignment = assign_observation_to_boundary(
        1,
        observation,
        *separator_constraints(1, PixelInterval(80.0, 120.0)),
    )
    assignment = replace(assignment, used_for_boundary=True)
    boundary = frame_boundary_from_assignment(assignment)
    relation = observed_spacing_evidence(
        FrameBoundaryReference(None, 1),
        PixelInterval.exact(observation.width),
        observation.provenance,
    )
    boundary_paths = candidate_boundary_paths()
    geometry = SequenceSolution(
        format_id="135",
        layout="horizontal",
        strip_mode="full",
        count=2,
        holder_span=HolderSpan(holder_box),
        visible_sequence_span=VisibleSequenceSpan(sequence_box),
        crop_envelope=CropEnvelope(sequence_box),
        photo_intervals=(
            PhotoInterval(
                1,
                PixelInterval.exact(0.0),
                PixelInterval.exact(95.0),
                boundary_paths[0].provenance,
                observation.provenance,
                True,
                True,
            ),
            PhotoInterval(
                2,
                PixelInterval.exact(105.0),
                PixelInterval.exact(200.0),
                observation.provenance,
                boundary_paths[1].provenance,
                True,
                True,
            ),
        ),
        frames=frames,
        separator_observations=(observation,),
        separator_assignments=(assignment,),
        frame_boundaries=(boundary,),
        inter_frame_spacings=(relation,),
        holder_occlusion=holder_occlusion_not_applicable(),
        frame_dimension_prior=FrameDimensionPrior(
            PixelInterval.exact(95.0),
            PixelInterval.exact(100.0),
            (36.0, 24.0),
            FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
            MeasurementProvenance(
                MeasurementIdentity.FRAME_DIMENSIONS,
                "test_fixture",
                (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
            ),
        ),
        residuals=SequenceResiduals(0.05, 0.0, 0.0),
        assignment_consensus=BoundaryAssignmentConsensus(
            AssignmentConsensusOutcome.AGREED,
            1,
            (),
        ),
        search_budget_exhausted=False,
        automatic_processing_supported=automatic_processing_supported,
        sequence_provenance=MeasurementProvenance(
            MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
            "synthetic_sequence_boundary",
            (MeasurementIdentity.GRAY_WORK,),
            ("leading", "trailing"),
        ),
        boundary_paths=boundary_paths,
    )
    evidence = candidate_evidence_fixture(
        content_preservation=content_preservation,
    )
    if failed_candidate_check == "boundary_proof":
        geometry = replace(
            geometry,
            sequence_provenance=MeasurementProvenance(
                MeasurementIdentity.HOLDER_CANVAS,
                "test_canvas_geometry",
                (MeasurementIdentity.CANVAS,),
            ),
        )
    dimensions = frame_dimension_evidence(
        geometry,
        unavailable_calibration_fixture(),
    )
    evidence = replace(
        evidence,
        sequence_conservation=sequence_conservation_for_geometry(geometry),
        frame_dimensions=dimensions,
        scan_calibration=candidate_scan_calibration(
            unavailable_calibration_fixture(),
            geometry,
            evidence.holder_boundary,
        ),
        partial_edge_safety=partial_edge_safety_evidence(
            geometry,
            evidence.frame_coverage,
            dimensions,
            evidence.frame_content,
        ),
        independence=evidence_independence_evidence(geometry),
    )
    hypothesis = CountHypothesis(
        count=2,
        strip_mode="full",
        source=CountHypothesisSource.FORMAT_DEFAULT,
    )
    built = BuiltCandidate(geometry, hypothesis, ())
    gate = candidate_gate_for_evidence(built, evidence)
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=hypothesis,
        assessment=CandidateAssessment(
            evidence=evidence,
            gate=gate,
        ),
    )


def selection_fixture(
    candidate: AssessedCandidate | None = None,
    *,
    geometry_disagreement: bool = False,
) -> SelectionResult:
    selected = candidate or candidate_fixture()
    cluster = GeometryCluster((selected,), selected)
    resolution = GeometryResolution(
        True,
        True,
        True,
        True,
        True,
        not geometry_disagreement,
        True,
        False,
    )
    return SelectionResult(
        selected=selected,
        ranked_candidates=(selected,),
        clusters=(cluster,),
        consensus=(
            SelectionConsensus.DISAGREED
            if geometry_disagreement
            else SelectionConsensus.UNCONTESTED
        ),
        geometry_resolution=resolution,
    )


def frame_bleed_fixture(*, feasible: bool = True) -> FrameBleedPlan:
    return FrameBleedPlan(
        user_bleed=AxisBleedParameters(20, 10),
        frame_output_bounds=(
            Box(0, 0, 200, 100),
            Box(0, 0, 200, 100),
        ),
        frame_sides=(
            FrameSideBleed(0, 20, 20, 10),
            FrameSideBleed(1, 20, 20, 10),
        ),
        overlap_protection=(),
        unresolved_overlap_boundaries=(
            () if feasible else (FrameBoundaryReference(None, 1),)
        ),
    )


def transform_geometry_fixture(
    state: EvidenceState = EvidenceState.SUPPORTED,
) -> TransformGeometryEvidence:
    return TransformGeometryEvidence(
        (
            TransformOutcome.SPAN_BELOW_THRESHOLD
            if state == EvidenceState.SUPPORTED
            else TransformOutcome.ANGLE_OUT_OF_RANGE
        ),
        0.0,
        0.0,
        1.0,
        DeskewMeasurementOutcome.MEASURED,
    )


def decide_candidate(
    candidate: AssessedCandidate | None = None,
    *,
    geometry_disagreement: bool = False,
    output_protection_feasible: bool = True,
    transform_state: EvidenceState = EvidenceState.SUPPORTED,
) -> DecisionGateAssessment:
    return apply_decision_gate(
        selection_fixture(
            candidate,
            geometry_disagreement=geometry_disagreement,
        ),
        frame_bleed_fixture(feasible=output_protection_feasible),
        transform_geometry_fixture(transform_state),
    )


def final_detection_fixture(
    *,
    failed_candidate_check: str | None = None,
) -> FinalDetection:
    selection = selection_fixture(
        candidate_fixture(
            failed_candidate_check=failed_candidate_check,
        )
    )
    bleed = frame_bleed_fixture()
    decision = apply_decision_gate(
        selection,
        bleed,
        transform_geometry_fixture(),
    )
    return finalize_detection(
        decision,
        finalization_plan_for_selection(
            selection,
            bleed,
            workspace_extent=WorkspaceExtent(200, 100),
        ),
    )
