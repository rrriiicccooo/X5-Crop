from __future__ import annotations

from dataclasses import replace
from inspect import signature
from pathlib import Path
import unittest

import numpy as np

from tools.tests.physical_gate_support import (
    boundary_path_fixture,
    candidate_evidence_fixture,
    candidate_fixture,
    selection_fixture,
    unavailable_calibration_fixture,
)
from x5crop.detection.candidate.execution.model import CountHypothesisEvaluation
from x5crop.detection.candidate.plan.count_hypotheses import (
    CountHypothesis,
    CountHypothesisSource,
)
from x5crop.detection.geometry_resolution import GeometryResolution
from x5crop.detection.candidate.assessment.candidate import (
    candidate_gate_for_evidence,
)
from x5crop.detection.candidate.assessment.evidence_independence import (
    evidence_independence_evidence,
)
from x5crop.detection.candidate.model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
    boundary_proof_paths_for_geometry,
)
from x5crop.detection.candidate.selection.choose import select_candidates
from x5crop.detection.evidence.partial_edge import PartialEdgeSafetyEvidence
from x5crop.detection.evidence.partial_edge import partial_edge_safety_evidence
from x5crop.detection.evidence.frame_sequence import sequence_conservation_for_geometry
from x5crop.detection.evidence.physical_scale import candidate_scan_calibration
from x5crop.detection.evidence.holder_occupancy import holder_occupancy_evidence
from x5crop.detection.evidence.film_structure import (
    aperture_contact_evidence,
    film_base_reference,
    film_structure_evidence,
)
from x5crop.detection.evidence.holder_material import holder_material_evidence
from x5crop.detection.physical.photo_size import frame_dimension_evidence
from x5crop.domain import (
    BoundaryKind,
    BoundarySide,
    Box,
    EvidenceState,
    FrameBoundaryReference,
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
)
from x5crop.detection.physical.boundary import canvas_boundary_paths
from x5crop.detection.physical.model import PhotoInterval, SequenceSolution
from x5crop.detection.physical.spacing import (
    observed_spacing_evidence,
    spacing_hypothesis,
)
from x5crop.detection.physical.separator.assignment import dimension_constrained_boundary
from x5crop.cache import MeasurementCache
from x5crop.domain import HolderSpan, VisibleSequenceSpan
from x5crop.configuration.registry import get_detection_configuration
from x5crop.formats import format_spec
from x5crop.detection.final.finalize import finalize_detection
from x5crop.image.statistics import ImageMeasurementStatisticsParameters, image_measurement_statistics


def _single_frame_candidate(*, measured_boundaries: bool) -> BuiltCandidate:
    candidate = candidate_fixture()
    provenance = MeasurementProvenance(
        MeasurementIdentity.HOLDER_MATERIAL_PROFILE,
        "synthetic",
        (MeasurementIdentity.GRAY_WORK,),
    )
    kind = (
        BoundaryKind.TONAL_TRANSITION
        if measured_boundaries
        else BoundaryKind.CANVAS_CLIP
    )
    observations = (
        boundary_path_fixture(BoundarySide.LEADING, PixelInterval.exact(0.0), kind, provenance),
        boundary_path_fixture(BoundarySide.TRAILING, PixelInterval.exact(200.0), kind, provenance),
        boundary_path_fixture(BoundarySide.TOP, PixelInterval.exact(0.0), kind, provenance),
        boundary_path_fixture(BoundarySide.BOTTOM, PixelInterval.exact(100.0), kind, provenance),
    )
    geometry = replace(
        candidate.geometry,
        count=1,
        frames=(Box(0, 0, 200, 100),),
        photo_intervals=(
            PhotoInterval(
                1,
                PixelInterval.exact(0.0),
                PixelInterval.exact(200.0),
                provenance,
                provenance,
                measured_boundaries,
                measured_boundaries,
            ),
        ),
        separator_observations=(),
        separator_assignments=(),
        frame_boundaries=(),
        inter_frame_spacings=(),
        boundary_paths=observations,
        sequence_provenance=provenance,
    )
    return BuiltCandidate(
        geometry,
        replace(candidate.count_hypothesis, count=1),
        (),
    )


def _with_candidate_evidence(
    candidate: AssessedCandidate,
    evidence: CandidateEvidence,
    *,
    geometry: SequenceSolution | None = None,
    count_hypothesis: CountHypothesis | None = None,
) -> AssessedCandidate:
    resolved_geometry = candidate.geometry if geometry is None else geometry
    resolved_hypothesis = (
        candidate.count_hypothesis
        if count_hypothesis is None
        else count_hypothesis
    )
    texture_limit = evidence.film_structure.film_base_reference.texture_limit
    holder_material = holder_material_evidence(
        resolved_geometry,
        texture_limit,
    )
    film_base = film_base_reference(
        resolved_geometry,
        holder_material,
        edge_texture_limit=texture_limit,
    )
    aperture_contact = aperture_contact_evidence(
        resolved_geometry,
        film_base,
    )
    scan_calibration = candidate_scan_calibration(
        unavailable_calibration_fixture(),
        resolved_geometry,
        aperture_contact,
    )
    dimensions = frame_dimension_evidence(
        resolved_geometry,
        scan_calibration,
    )
    visible = resolved_geometry.visible_sequence_span.box
    holder = resolved_geometry.holder_span.box
    coverage = replace(
        evidence.frame_coverage,
        holder_long_axis_interval=(holder.left, holder.right),
        visible_sequence_interval=(visible.left, visible.right),
        frame_intervals=((visible.left, visible.right),),
        candidate_frame_count=resolved_geometry.count,
    )
    frame_content = replace(
        evidence.frame_content,
        observations=evidence.frame_content.observations[: resolved_geometry.count],
    )
    evidence = replace(
        evidence,
        frame_coverage=coverage,
        sequence_conservation=sequence_conservation_for_geometry(
            resolved_geometry
        ),
        frame_dimensions=dimensions,
        holder_material=holder_material,
        film_structure=film_structure_evidence(resolved_geometry, film_base),
        aperture_contact=aperture_contact,
        scan_calibration=scan_calibration,
        holder_occupancy=holder_occupancy_evidence(
            layout=resolved_geometry.layout,
            count=resolved_geometry.count,
            holder_span=resolved_geometry.holder_span,
            visible_sequence_span=resolved_geometry.visible_sequence_span,
            frames=resolved_geometry.frames,
            frame_boundaries=resolved_geometry.frame_boundaries,
            separator_assignments=resolved_geometry.separator_assignments,
            physical_spec=format_spec(resolved_geometry.format_id),
            content_support_available=frame_content.support_available,
            frame_coverage=coverage,
            frame_dimensions=dimensions,
            calibration=scan_calibration,
        ),
        partial_edge_safety=partial_edge_safety_evidence(
            resolved_geometry,
            coverage,
            dimensions,
            frame_content,
        ),
        frame_content=frame_content,
        sequence_content_alignment=replace(
            evidence.sequence_content_alignment,
            visible_sequence_span=visible,
        ),
        independence=evidence_independence_evidence(resolved_geometry),
    )
    built = BuiltCandidate(resolved_geometry, resolved_hypothesis, ())
    return AssessedCandidate(
        geometry=resolved_geometry,
        count_hypothesis=resolved_hypothesis,
        assessment=CandidateAssessment(
            evidence=evidence,
            gate=candidate_gate_for_evidence(built, evidence),
        ),
    )


def _without_content_measurements(evidence: CandidateEvidence) -> CandidateEvidence:
    return replace(
        evidence,
        frame_coverage=replace(evidence.frame_coverage, content_runs=()),
        sequence_content_alignment=replace(
            evidence.sequence_content_alignment,
            content_span=None,
        ),
    )


class PhysicalDetectionResolutionContractTest(unittest.TestCase):
    def test_resolved_count_excludes_larger_unresolved_candidates_from_selection(
        self,
    ) -> None:
        from x5crop.detection.pipeline import _candidate_pool_for_count_resolution

        higher_hypothesis = CountHypothesis(
            2,
            "partial",
            CountHypothesisSource.AUTOMATIC,
        )
        higher_fixture = candidate_fixture()
        higher = _with_candidate_evidence(
            higher_fixture,
            higher_fixture.assessment.evidence,
            geometry=replace(higher_fixture.geometry, strip_mode="partial"),
            count_hypothesis=higher_hypothesis,
        )
        lower_built = _single_frame_candidate(measured_boundaries=True)
        lower_hypothesis = CountHypothesis(
            1,
            "partial",
            CountHypothesisSource.AUTOMATIC,
        )
        lower_fixture = candidate_fixture()
        lower = _with_candidate_evidence(
            lower_fixture,
            lower_fixture.assessment.evidence,
            geometry=replace(lower_built.geometry, strip_mode="partial"),
            count_hypothesis=lower_hypothesis,
        )
        unresolved = replace(
            selection_fixture(higher),
            geometry_resolution=GeometryResolution(
                False,
                False,
                False,
                True,
                True,
                True,
                True,
                False,
            ),
        )
        resolved = selection_fixture(lower)
        evaluations = (
            CountHypothesisEvaluation(
                higher_hypothesis,
                (higher,),
                unresolved,
            ),
            CountHypothesisEvaluation(
                lower_hypothesis,
                (lower,),
                resolved,
            ),
        )

        self.assertEqual(
            _candidate_pool_for_count_resolution(evaluations),
            (lower,),
        )

    def test_dual_lane_parent_does_not_erase_search_budget_exhaustion(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = (root / "x5crop/detection/modes/dual_lane.py").read_text()
        self.assertNotIn("search_budget_exhausted=False", source)

    def test_independently_proved_geometry_does_not_require_observed_spacing(self) -> None:
        candidate = candidate_fixture()
        hypothesis_provenance = MeasurementProvenance(
            MeasurementIdentity.FRAME_GEOMETRY,
            "synthetic_spacing_hypothesis",
            (MeasurementIdentity.SEQUENCE_CUTS,),
        )
        geometry = replace(
            candidate.geometry,
            inter_frame_spacings=(
                spacing_hypothesis(
                    FrameBoundaryReference(None, 1),
                    PixelInterval.exact(10.0),
                    hypothesis_provenance,
                ),
            ),
        )
        candidate = replace(
            candidate,
            count_hypothesis=replace(
                candidate.count_hypothesis,
                source=CountHypothesisSource.REQUESTED,
            ),
        )
        candidate = _with_candidate_evidence(
            candidate,
            candidate.assessment.evidence,
            geometry=geometry,
        )
        selection = select_candidates(
            (candidate,),
            larger_counts_evaluated=True,
        )
        self.assertTrue(selection.geometry_resolution.count_resolved)
        self.assertTrue(selection.geometry_resolution.placement_resolved)

    def test_search_budget_exhaustion_prevents_geometry_resolution(self) -> None:
        candidate = candidate_fixture()
        candidate = replace(
            candidate,
            geometry=replace(
                candidate.geometry,
                search_budget_exhausted=True,
            ),
        )
        selection = select_candidates(
            (candidate,),
            larger_counts_evaluated=True,
        )
        self.assertFalse(selection.geometry_resolution.supported)
        self.assertIn(
            "search_budget_exhausted",
            selection.geometry_resolution.reasons,
        )

    def test_full_canvas_does_not_prove_single_frame_geometry(self) -> None:
        built = _single_frame_candidate(measured_boundaries=False)
        paths = boundary_proof_paths_for_geometry(
            built.geometry,
            candidate_evidence_fixture(),
        )
        geometry_path = next(path for path in paths if path.code == "geometry_led")
        self.assertEqual(geometry_path.state, EvidenceState.UNAVAILABLE)

    def test_two_measured_sides_can_support_single_frame_geometry(self) -> None:
        built = _single_frame_candidate(measured_boundaries=True)
        paths = boundary_proof_paths_for_geometry(
            built.geometry,
            candidate_evidence_fixture(),
        )
        geometry_path = next(path for path in paths if path.code == "geometry_led")
        self.assertEqual(geometry_path.state, EvidenceState.SUPPORTED)

    def test_filled_geometry_cannot_support_partial_occupancy_proof(self) -> None:
        candidate = candidate_fixture()
        built = BuiltCandidate(
            replace(candidate.geometry, strip_mode="partial"),
            replace(candidate.count_hypothesis, strip_mode="partial"),
            (),
        )
        evidence = replace(
            candidate_evidence_fixture(),
            partial_edge_safety=PartialEdgeSafetyEvidence(
                is_partial=True,
                hard_separator_count=1,
                expected_separator_count=1,
                frame_coverage_state=EvidenceState.SUPPORTED,
                frame_dimension_state=EvidenceState.SUPPORTED,
                diagnostics=(),
            ),
        )

        path = next(
            item
            for item in boundary_proof_paths_for_geometry(built.geometry, evidence)
            if item.code == "partial_occupancy_led"
        )
        self.assertEqual(path.state, EvidenceState.UNAVAILABLE)

    def test_unavailable_content_does_not_veto_complete_separator_proof(
        self,
    ) -> None:
        candidate = candidate_fixture()
        built = BuiltCandidate(
            candidate.geometry,
            candidate.count_hypothesis,
            (),
        )
        evidence = candidate_evidence_fixture()
        evidence = _without_content_measurements(evidence)

        paths = boundary_proof_paths_for_geometry(built.geometry, evidence)
        separator_path = next(
            path for path in paths if path.code == "film_structure_led"
        )
        self.assertEqual(separator_path.state, EvidenceState.SUPPORTED)

    def test_fixed_count_geometry_accepts_uncontradicted_unavailable_content(
        self,
    ) -> None:
        candidate = candidate_fixture()
        evidence = _without_content_measurements(candidate.assessment.evidence)
        candidate = replace(
            candidate,
            count_hypothesis=replace(
                candidate.count_hypothesis,
                source=CountHypothesisSource.FORMAT_DEFAULT,
            ),
        )
        candidate = _with_candidate_evidence(candidate, evidence)

        selection = select_candidates(
            (candidate,),
            larger_counts_evaluated=True,
        )
        self.assertTrue(selection.geometry_resolution.supported)

    def test_full_canvas_never_becomes_a_physical_proof_path(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            sequence_provenance=MeasurementProvenance(
                MeasurementIdentity.HOLDER_CANVAS,
                "full_canvas",
                (MeasurementIdentity.CANVAS,),
            ),
            boundary_paths=canvas_boundary_paths(200, 100),
        )
        built = BuiltCandidate(geometry, candidate.count_hypothesis, ())
        evidence = candidate_evidence_fixture()
        evidence = replace(
            evidence,
            film_structure=replace(
                evidence.film_structure,
                separator_sequence=replace(
                    evidence.film_structure.separator_sequence,
                    hard_count=0,
                    hard_boundaries=(),
                    missing_boundaries=(FrameBoundaryReference(None, 1),),
                    hard_tonal_evidence=(),
                ),
            ),
        )
        paths = boundary_proof_paths_for_geometry(built.geometry, evidence)
        self.assertFalse(
            any(path.state == EvidenceState.SUPPORTED for path in paths)
        )

    def test_one_canvas_sequence_edge_cannot_prove_placement(self) -> None:
        candidate = candidate_fixture()
        observations = tuple(
            replace(
                observation,
                kind=(
                    BoundaryKind.CANVAS_CLIP
                    if observation.side == BoundarySide.LEADING
                    else observation.kind
                ),
                outer_material=(
                    None
                    if observation.side == BoundarySide.LEADING
                    else observation.outer_material
                ),
                inner_material=(
                    None
                    if observation.side == BoundarySide.LEADING
                    else observation.inner_material
                ),
            )
            for observation in candidate.geometry.boundary_paths
        )
        independent_leading = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            "independent_leading_photo_edge",
            (MeasurementIdentity.GRAY_WORK,),
        )
        geometry = replace(
            candidate.geometry,
            boundary_paths=observations,
            photo_intervals=(
                replace(
                    candidate.geometry.photo_intervals[0],
                    start_provenance=independent_leading,
                ),
                *candidate.geometry.photo_intervals[1:],
            ),
        )
        built = BuiltCandidate(geometry, candidate.count_hypothesis, ())
        paths = boundary_proof_paths_for_geometry(
            built.geometry,
            candidate_evidence_fixture(),
        )
        self.assertFalse(
            any(path.state == EvidenceState.SUPPORTED for path in paths)
        )

    def test_geometry_resolution_rejects_contradicted_sequence_conservation(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            inter_frame_spacings=(
                observed_spacing_evidence(
                    FrameBoundaryReference(None, 1),
                    PixelInterval.exact(210.0),
                    MeasurementProvenance(
                        MeasurementIdentity.PHOTO_EDGES,
                        "synthetic_nonconserved_spacing",
                        (MeasurementIdentity.GRAY_WORK,),
                    ),
                ),
            ),
        )
        candidate = replace(
            candidate,
            count_hypothesis=replace(
                candidate.count_hypothesis,
                source=CountHypothesisSource.AUTOMATIC,
            ),
        )
        candidate = _with_candidate_evidence(
            candidate,
            candidate.assessment.evidence,
            geometry=geometry,
        )
        selection = select_candidates(
            (candidate,),
            larger_counts_evaluated=True,
        )
        self.assertFalse(selection.geometry_resolution.supported)
        self.assertIn("count_unresolved", selection.geometry_resolution.reasons)

    def test_multi_frame_geometry_requires_an_independent_internal_anchor(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            separator_observations=(),
            separator_assignments=(),
            frame_boundaries=(
                dimension_constrained_boundary(
                    1,
                    PixelInterval.exact(100.0),
                    MeasurementProvenance(
                        MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
                        "bidirectional_boundary_constraint",
                        (
                            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
                            MeasurementIdentity.SEQUENCE_BOUNDARIES,
                        ),
                    ),
                ),
            ),
        )
        built = BuiltCandidate(geometry, candidate.count_hypothesis, ())
        evidence = candidate_evidence_fixture()
        evidence = replace(
            evidence,
            film_structure=replace(
                evidence.film_structure,
                separator_sequence=replace(
                    evidence.film_structure.separator_sequence,
                    hard_count=0,
                    hard_boundaries=(),
                    missing_boundaries=(FrameBoundaryReference(None, 1),),
                    hard_tonal_evidence=(),
                ),
            ),
        )
        paths = boundary_proof_paths_for_geometry(built.geometry, evidence)
        geometry_path = next(path for path in paths if path.code == "geometry_led")
        self.assertEqual(geometry_path.state, EvidenceState.UNAVAILABLE)

    def test_geometry_resolution_requires_larger_counts_to_be_evaluated(self) -> None:
        candidate = candidate_fixture()
        selection = select_candidates(
            (candidate,),
            larger_counts_evaluated=False,
        )
        self.assertFalse(selection.geometry_resolution.supported)
        self.assertIn(
            "larger_counts_not_evaluated",
            selection.geometry_resolution.reasons,
        )

    def test_finalization_has_no_pixel_input(self) -> None:
        parameters = signature(finalize_detection).parameters
        self.assertNotIn("gray", parameters)
        self.assertEqual(
            tuple(parameters),
            ("decision", "finalization_plan"),
        )

    def test_content_region_measurement_is_count_independent(self) -> None:
        from x5crop.detection.evidence.content.regions import content_region_runs
        from x5crop.detection.evidence.frame_coverage import frame_coverage_evidence

        self.assertNotIn("count", signature(content_region_runs).parameters)
        self.assertNotIn("fmt", signature(frame_coverage_evidence).parameters)
        self.assertNotIn(
            "frame_width_reference_px",
            signature(frame_coverage_evidence).parameters,
        )

    def test_two_frames_cannot_cover_three_independent_content_regions(self) -> None:
        from x5crop.detection.evidence.frame_coverage import frame_coverage_evidence

        content = np.zeros((60, 450), dtype=np.uint8)
        for start, end in ((20, 120), (160, 260), (320, 420)):
            content[:, start:end] = 255
        cache = MeasurementCache(
            "horizontal",
            np.full_like(content, 255),
            content,
            content.astype(np.float32) / 255.0,
            image_measurement_statistics(
                np.full_like(content, 255),
                ImageMeasurementStatisticsParameters(),
            ),
        )
        evidence = frame_coverage_evidence(
            HolderSpan(Box(0, 0, 450, 60)),
            VisibleSequenceSpan(Box(0, 0, 450, 60)),
            (Box(0, 0, 140, 60), Box(140, 0, 290, 60)),
            cache,
            get_detection_configuration("135", "partial").content,
        )
        self.assertEqual(evidence.state, EvidenceState.CONTRADICTED)
        self.assertEqual(evidence.unexplained_content_region_count, 1)

    def test_any_measured_uncovered_content_remains_a_contradiction(self) -> None:
        from unittest.mock import patch

        from x5crop.detection.evidence.frame_coverage import frame_coverage_evidence

        content = np.zeros((20, 100), dtype=np.uint8)
        cache = MeasurementCache(
            "horizontal",
            np.full_like(content, 255),
            content,
            content.astype(np.float32),
            image_measurement_statistics(
                np.full_like(content, 255),
                ImageMeasurementStatisticsParameters(),
            ),
        )
        with patch(
            "x5crop.detection.evidence.frame_coverage.content_region_runs",
            return_value=((10, 21),),
        ):
            evidence = frame_coverage_evidence(
                HolderSpan(Box(0, 0, 100, 20)),
                VisibleSequenceSpan(Box(0, 0, 100, 20)),
                (Box(10, 0, 20, 20),),
                cache,
                get_detection_configuration("135", "partial").content,
            )
        self.assertEqual(evidence.uncovered_content, ((20, 21),))
        self.assertEqual(evidence.state, EvidenceState.CONTRADICTED)


if __name__ == "__main__":
    unittest.main()
