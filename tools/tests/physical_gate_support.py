from __future__ import annotations

from x5crop.detection.candidate.assessment.candidate import (
    candidate_gate_for_evidence,
)
from x5crop.detection.candidate.assessment.model import (
    BoundaryProofPath,
    CandidateGateAssessment,
)
from x5crop.detection.candidate.assessment.evidence_independence import (
    evidence_independence_evidence,
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
from x5crop.detection.evidence.content.external_boundaries import (
    ExternalApertureBoundaryObservation,
    ExternalAperturePreservationEvidence,
)
from x5crop.detection.evidence.photo_aperture_coverage import (
    PhotoApertureCoverageEvidence,
)
from x5crop.detection.evidence.content.internal_boundaries import (
    inter_photo_boundary_preservation_evidence,
)
from x5crop.detection.evidence.content.photo_content import (
    PhotoContentEvidence,
    PhotoContentObservation,
)
from x5crop.detection.evidence.holder_boundary import holder_boundary_evidence
from x5crop.detection.evidence.holder_occupancy import (
    HolderOccupancyEvidence,
    StripCompletenessEvidence,
)
from x5crop.detection.evidence.partial_edge import partial_edge_safety_evidence
from x5crop.detection.evidence.physical_scale import physical_scale_observations
from x5crop.detection.evidence.separator_sequence import separator_sequence_evidence
from x5crop.detection.evidence.transform_geometry import (
    TransformGeometryEvidence,
    TransformOutcome,
)
from x5crop.detection.final.finalize import (
    finalization_plan_for_selection,
    finalize_detection,
)
from x5crop.detection.final.model import FinalDetection
from x5crop.detection.gate_checks import GateCheck, GateStage
from x5crop.detection.geometry_resolution import GeometryResolution
from x5crop.detection.physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    PhotoSequenceSolution,
    SequenceResiduals,
)
from x5crop.detection.physical.photo_size import frame_dimension_evidence
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundarySide,
    Box,
    EvidenceState,
    FrameDimensionPrior,
    FrameDimensionPriorSource,
    GrayAppearanceObservation,
    GrayBoundaryPathObservation,
    GrayIntensityTail,
    HolderBoundaryObservation,
    HolderSpan,
    InterPhotoBoundaryReference,
    InterPhotoSpacing,
    InterPhotoSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhotoAperture,
    PhotoApertureBoundaryResolution,
    PhotoApertureCrossAxisHypothesis,
    PhotoApertureEdgeAssignment,
    PhotoApertureEdgeSource,
    PixelInterval,
    SeparatorBandAssignment,
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
    SeparatorCrossAxisOutcome,
    WorkspaceExtent,
)
from x5crop.image.deskew import DeskewMeasurementOutcome
from x5crop.output.model import AxisBleedParameters, FrameBleedPlan, FrameSideBleed
from x5crop.units import (
    PhysicalScaleObservation,
    PhysicalScaleScope,
    PhysicalScaleSource,
    ResolutionMetadataObservation,
    ScanCalibrationResolution,
)


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
        position=position,
        kind=kind,
        local_positions=(position,),
        lower_appearance=lower,
        upper_appearance=upper,
        provenance=provenance,
    )


def candidate_boundary_paths() -> tuple[GrayBoundaryPathObservation, ...]:
    return tuple(
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
            (BoundarySide.LEADING, float(_HOLDER_BOX.left)),
            (BoundarySide.TRAILING, float(_HOLDER_BOX.right)),
            (BoundarySide.TOP, float(_HOLDER_BOX.top)),
            (BoundarySide.BOTTOM, float(_HOLDER_BOX.bottom)),
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
    observations = tuple(
        PhysicalScaleObservation(
            axis,
            value,
            value,
            PhysicalScaleSource.HOLDER_SHORT_AXIS,
            PhysicalScaleScope.ROOT_MEASUREMENT,
            MeasurementProvenance(
                MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
                ObservationId(f"test_scale:{axis}"),
                (MeasurementIdentity.BOUNDARY_PATHS,),
                "synthetic scale observation",
            ),
        )
        for axis, value in (("x", x_px_per_mm), ("y", y_px_per_mm))
    )
    return ScanCalibrationResolution.from_observations(metadata, observations)


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
        start=start,
        end=end,
        tonal_evidence=float(tonal_evidence),
        appearance=_appearance(provenance, texture=0.0),
        provenance=provenance,
    )


def separator_cross_axis_measurement(
    observation: SeparatorBandObservation,
    aperture_cross_axis: PhotoApertureCrossAxisHypothesis,
    state: EvidenceState = EvidenceState.SUPPORTED,
) -> SeparatorCrossAxisMeasurement:
    outcome = (
        SeparatorCrossAxisOutcome.PATH_SUPPORTED
        if state == EvidenceState.SUPPORTED
        else SeparatorCrossAxisOutcome.CONTINUITY_WEAK
    )
    return SeparatorCrossAxisMeasurement(
        observation_id=observation.provenance.observation_id,
        aperture_cross_axis=aperture_cross_axis,
        outcome=outcome,
        coverage_ratio=1.0 if state == EvidenceState.SUPPORTED else 0.0,
        longest_supported_ratio=(
            1.0 if state == EvidenceState.SUPPORTED else 0.0
        ),
        break_count=0,
        appearance_coherence_ratio=(
            1.0 if state == EvidenceState.SUPPORTED else 0.0
        ),
    )


def _measured_resolution(
    photo_index: int,
    side: BoundarySide,
    path: GrayBoundaryPathObservation,
) -> PhotoApertureBoundaryResolution:
    return PhotoApertureBoundaryResolution(
        photo_index,
        side,
        path.position,
        EvidenceState.SUPPORTED,
        PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH,
        path.provenance,
    )


def _separator_resolution(
    photo_index: int,
    side: BoundarySide,
    position: float,
    observation: SeparatorBandObservation,
) -> PhotoApertureBoundaryResolution:
    return PhotoApertureBoundaryResolution(
        photo_index,
        side,
        PixelInterval.exact(position),
        EvidenceState.SUPPORTED,
        PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE,
        observation.provenance,
    )


def _candidate_geometry(
    *,
    automatic_processing_supported: bool = True,
    boundary_proof_supported: bool = True,
) -> PhotoSequenceSolution:
    paths = candidate_boundary_paths()
    leading_path, trailing_path, top_path, bottom_path = paths
    cross_axis = PhotoApertureCrossAxisHypothesis(top_path, bottom_path)
    observation = separator_observation(
        sum(_SEPARATOR) / 2.0,
        start=_SEPARATOR[0],
        end=_SEPARATOR[1],
    )
    separator_measurement = separator_cross_axis_measurement(
        observation,
        cross_axis,
    )
    first_leading = _measured_resolution(1, BoundarySide.LEADING, leading_path)
    first_trailing = _separator_resolution(
        1,
        BoundarySide.TRAILING,
        _SEPARATOR[0],
        observation,
    )
    second_leading = _separator_resolution(
        2,
        BoundarySide.LEADING,
        _SEPARATOR[1],
        observation,
    )
    second_trailing = _measured_resolution(2, BoundarySide.TRAILING, trailing_path)
    first_top = _measured_resolution(1, BoundarySide.TOP, top_path)
    first_bottom = _measured_resolution(1, BoundarySide.BOTTOM, bottom_path)
    second_top = _measured_resolution(2, BoundarySide.TOP, top_path)
    second_bottom = _measured_resolution(2, BoundarySide.BOTTOM, bottom_path)
    apertures = (
        PhotoAperture(
            1,
            first_leading,
            first_trailing,
            first_top,
            first_bottom,
        ),
        PhotoAperture(
            2,
            second_leading,
            second_trailing,
            second_top,
            second_bottom,
        ),
    )
    edge_assignments = tuple(
        PhotoApertureEdgeAssignment(index, side, path, resolution)
        for index, side, path, resolution in (
            (1, BoundarySide.LEADING, leading_path, first_leading),
            (1, BoundarySide.TOP, top_path, first_top),
            (1, BoundarySide.BOTTOM, bottom_path, first_bottom),
            (2, BoundarySide.TRAILING, trailing_path, second_trailing),
            (2, BoundarySide.TOP, top_path, second_top),
            (2, BoundarySide.BOTTOM, bottom_path, second_bottom),
        )
    )
    separator_assignments = (
        (
            SeparatorBandAssignment(
                1,
                observation,
                separator_measurement,
                first_trailing,
                second_leading,
            ),
        )
        if boundary_proof_supported
        else ()
    )
    spacing = InterPhotoSpacing(
        InterPhotoBoundaryReference(None, 1),
        PixelInterval.exact(_SEPARATOR[1] - _SEPARATOR[0]),
        observation.provenance,
        (
            InterPhotoSpacingBasis.OBSERVED
            if boundary_proof_supported
            else InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS
        ),
    )
    return PhotoSequenceSolution(
        format_id="135",
        layout="horizontal",
        strip_mode="full",
        count=2,
        holder_span=HolderSpan(_HOLDER_BOX),
        photo_apertures=apertures,
        aperture_edge_assignments=edge_assignments,
        separator_observations=(observation,),
        separator_assignments=separator_assignments,
        inter_photo_spacings=(spacing,),
        frame_dimension_prior=FrameDimensionPrior(
            frame_size_mm=(36.0, 24.0),
            source=FrameDimensionPriorSource.PHYSICAL_ASPECT,
            provenance=MeasurementProvenance(
                MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
                ObservationId("synthetic_frame_dimension_prior"),
                (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                "synthetic frame dimension prior",
            ),
        ),
        photo_width_constraint_px=PixelInterval.exact(150.0),
        photo_height_constraint_px=PixelInterval.exact(100.0),
        residuals=SequenceResiduals(0.0, 0.0),
        assignment_consensus=BoundaryAssignmentConsensus(
            AssignmentConsensusOutcome.UNCONTESTED,
            1,
            (),
        ),
        search_budget_exhausted=False,
        automatic_processing_supported=automatic_processing_supported,
        sequence_provenance=MeasurementProvenance(
            MeasurementIdentity.BOUNDARY_PATHS,
            ObservationId("synthetic_photo_aperture_sequence"),
            (MeasurementIdentity.GRAY_WORK,),
            "synthetic photo aperture sequence",
            tuple(path.provenance.observation_id for path in paths),
        ),
        raw_boundary_paths=paths,
        holder_boundaries=tuple(
            HolderBoundaryObservation(side, path.position, path)
            for side, path in zip(
                (
                    BoundarySide.LEADING,
                    BoundarySide.TRAILING,
                    BoundarySide.TOP,
                    BoundarySide.BOTTOM,
                ),
                paths,
                strict=True,
            )
        ),
    )


def candidate_gate_fixture(
    *,
    passed: bool = True,
    failed_check: str = "boundary_proof",
) -> CandidateGateAssessment:
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
        for code in (
            "content_preservation",
            "photo_geometry_consistency",
            "evidence_independence",
            "boundary_proof",
        )
    )
    return CandidateGateAssessment(
        checks=checks,
        proof_paths=(
            BoundaryProofPath(
                "separator_sequence_led",
                (
                    EvidenceState.CONTRADICTED
                    if not passed and failed_check == "boundary_proof"
                    else EvidenceState.SUPPORTED
                ),
                ("synthetic_separator_sequence",),
            ),
            BoundaryProofPath(
                "geometry_led",
                EvidenceState.UNAVAILABLE,
                ("synthetic_photo_dimensions",),
            ),
            BoundaryProofPath(
                "partial_occupancy_led",
                EvidenceState.NOT_APPLICABLE,
                ("synthetic_full_strip",),
            ),
        ),
        diagnostics=(),
    )


def candidate_evidence_fixture(
    *,
    content_preservation: EvidenceState = EvidenceState.SUPPORTED,
    geometry: PhotoSequenceSolution | None = None,
) -> CandidateEvidence:
    if content_preservation not in {
        EvidenceState.SUPPORTED,
        EvidenceState.CONTRADICTED,
    }:
        raise ValueError("candidate evidence fixture requires resolved content state")
    geometry = geometry or _candidate_geometry()
    aperture_intervals = tuple(
        (item.box.left, item.box.right) for item in geometry.frame_crop_envelopes
    )
    supported_content_runs = tuple(
        (start + min(10, max(1, (end - start) // 4)), end - min(10, max(1, (end - start) // 4)))
        for start, end in aperture_intervals
    )
    content_runs = supported_content_runs
    if content_preservation == EvidenceState.CONTRADICTED:
        first_start, first_end = supported_content_runs[0]
        next_start = aperture_intervals[1][0]
        content_runs = (
            (first_start, min(next_start, aperture_intervals[0][1] + 5)),
            *supported_content_runs[1:],
        )
    coverage = PhotoApertureCoverageEvidence(
        holder_long_axis_interval=(
            geometry.holder_span.box.left,
            geometry.holder_span.box.right,
        ),
        photo_aperture_intervals=aperture_intervals,
        content_runs=content_runs,
        content_position_uncertainty_px=0,
    )
    content = PhotoContentEvidence(
        0.5,
        tuple(
            PhotoContentObservation(index, 0.8, 0.8, True, ())
            for index in range(1, geometry.count + 1)
        ),
    )
    dimensions = frame_dimension_evidence(
        geometry,
        unavailable_calibration_fixture(),
    )
    holder = holder_boundary_evidence(geometry, 1.0)
    candidate_scale = physical_scale_observations(
        geometry,
        holder,
    )
    completeness = StripCompletenessEvidence(
        geometry.count,
        geometry.count,
        len(geometry.photo_apertures),
        sum(
            left.trailing.independently_observed
            and right.leading.independently_observed
            for left, right in zip(
                geometry.photo_apertures,
                geometry.photo_apertures[1:],
            )
        ),
        sum(item.independent for item in geometry.separator_assignments),
    )
    sequence = geometry.photo_sequence_envelope
    workspace = Box(
        sequence.left,
        sequence.top,
        sequence.right + 1,
        sequence.bottom + 1,
    )
    external_observations: list[ExternalApertureBoundaryObservation] = []
    for aperture in geometry.photo_apertures:
        box = aperture.frame_crop_envelope.box
        sides = (
            *((BoundarySide.LEADING,) if aperture.index == 1 else ()),
            BoundarySide.TOP,
            BoundarySide.BOTTOM,
            *(
                (BoundarySide.TRAILING,)
                if aperture.index == geometry.count
                else ()
            ),
        )
        for side in sides:
            if side == BoundarySide.LEADING:
                inside = Box(box.left, box.top, box.left + 1, box.bottom)
                outside = None
            elif side == BoundarySide.TRAILING:
                inside = Box(box.right - 1, box.top, box.right, box.bottom)
                outside = Box(box.right, box.top, box.right + 1, box.bottom)
            elif side == BoundarySide.TOP:
                inside = Box(box.left, box.top, box.right, box.top + 1)
                outside = None
            else:
                inside = Box(box.left, box.bottom - 1, box.right, box.bottom)
                outside = Box(box.left, box.bottom, box.right, box.bottom + 1)
            contradicted = bool(
                content_preservation == EvidenceState.CONTRADICTED
                and side == BoundarySide.TRAILING
            )
            external_observations.append(
                ExternalApertureBoundaryObservation(
                    aperture.index,
                    side,
                    (
                        PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS
                        if contradicted
                        else PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
                    ),
                    inside,
                    outside,
                    16 if contradicted else 0,
                    16 if contradicted else 0,
                    4 if contradicted else 0,
                    16,
                    4,
                )
            )
    return CandidateEvidence(
        photo_aperture_coverage=coverage,
        separator_sequence=separator_sequence_evidence(geometry),
        frame_dimensions=dimensions,
        photo_content=content,
        inter_photo_boundary_preservation=(
            inter_photo_boundary_preservation_evidence(
                geometry.count,
                geometry.photo_apertures,
                geometry.inter_photo_spacings,
                content,
            )
        ),
        holder_boundary=holder,
        physical_scale_observations=candidate_scale,
        external_aperture_preservation=ExternalAperturePreservationEvidence(
            workspace,
            sequence,
            geometry.count,
            tuple(external_observations),
            0.5,
        ),
        holder_occupancy=HolderOccupancyEvidence(
            strip_completeness=completeness,
            content_support_available=content.support_available,
            photo_aperture_coverage_state=coverage.state,
            frame_dimension_state=dimensions.state,
            complete_strip_can_be_underfilled=False,
            holder_span=geometry.holder_span,
            photo_sequence_envelope=geometry.photo_sequence_envelope,
        ),
        partial_edge_safety=partial_edge_safety_evidence(
            geometry,
            coverage,
            dimensions,
            content,
        ),
        independence=evidence_independence_evidence(geometry),
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
    geometry = _candidate_geometry(
        automatic_processing_supported=automatic_processing_supported,
        boundary_proof_supported=failed_candidate_check != "boundary_proof",
    )
    evidence = candidate_evidence_fixture(
        content_preservation=(
            EvidenceState.CONTRADICTED
            if failed_candidate_check == "content_preservation"
            else content_preservation
        ),
        geometry=geometry,
    )
    hypothesis = CountHypothesis(
        2,
        "full",
        CountHypothesisSource.FORMAT_DEFAULT,
    )
    built = BuiltCandidate(geometry, hypothesis, ())
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=hypothesis,
        assessment=CandidateAssessment(
            evidence=evidence,
            gate=candidate_gate_for_evidence(built, evidence),
        ),
    )


def selection_fixture(
    candidate: AssessedCandidate | None = None,
    *,
    geometry_disagreement: bool = False,
) -> SelectionResult:
    selected = candidate or candidate_fixture()
    cluster = GeometryCluster((selected,), selected)
    return SelectionResult(
        selected=selected,
        ranked_candidates=(selected,),
        clusters=(cluster,),
        consensus=(
            SelectionConsensus.DISAGREED
            if geometry_disagreement
            else SelectionConsensus.UNCONTESTED
        ),
        geometry_resolution=GeometryResolution(
            count_resolved=True,
            placement_resolved=True,
            boundaries_resolved=True,
            content_preservation_compatible=True,
            larger_count_hypotheses_resolved=True,
            alternative_geometries_resolved=not geometry_disagreement,
            assignment_geometry_resolved=True,
            search_budget_exhausted=False,
        ),
    )


def frame_bleed_fixture(*, feasible: bool = True) -> FrameBleedPlan:
    return FrameBleedPlan(
        user_bleed=AxisBleedParameters(20, 10),
        frame_output_bounds=(_HOLDER_BOX, _HOLDER_BOX),
        frame_sides=(
            FrameSideBleed(0, 20, 20, 10),
            FrameSideBleed(1, 20, 20, 10),
        ),
        overlap_protection=(),
        unresolved_overlap_boundaries=(
            () if feasible else (InterPhotoBoundaryReference(None, 1),)
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
        selection_fixture(candidate, geometry_disagreement=geometry_disagreement),
        frame_bleed_fixture(feasible=output_protection_feasible),
        transform_geometry_fixture(transform_state),
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
        apply_decision_gate(selection, bleed, transform_geometry_fixture()),
        bleed,
        finalization_plan_for_selection(
            selection,
            workspace_extent=WorkspaceExtent(_HOLDER_BOX.right, _HOLDER_BOX.bottom),
        ),
    )
