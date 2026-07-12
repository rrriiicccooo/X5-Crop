from __future__ import annotations

from dataclasses import replace
from inspect import signature
import unittest

import numpy as np

from tools.tests.physical_gate_support import candidate_evidence_fixture, candidate_fixture
from x5crop.detection.candidate.assessment.candidate import _boundary_proof_paths
from x5crop.detection.candidate.model import BuiltCandidate
from x5crop.detection.candidate.selection.choose import select_candidates
from x5crop.domain import (
    BoundaryObservation,
    Box,
    EvidenceState,
    MeasurementProvenance,
    PixelInterval,
)
from x5crop.detection.physical.boundary import canvas_boundary_observations
from x5crop.detection.physical.separator.assignment import dimension_constrained_boundary
from x5crop.cache import MeasurementCache
from x5crop.domain import HolderSpan, VisibleSequenceSpan
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.final.finalize import finalize_detection
from x5crop.image.statistics import ImageMeasurementStatisticsParameters, image_measurement_statistics


def _single_frame_candidate(*, measured_boundaries: bool) -> BuiltCandidate:
    candidate = candidate_fixture()
    provenance = MeasurementProvenance(
        "boundary_measurement",
        "synthetic",
        ("gray_work",),
    )
    kind = "tonal_transition" if measured_boundaries else "canvas_clip"
    observations = (
        BoundaryObservation("leading", PixelInterval.exact(0.0), kind, provenance),
        BoundaryObservation("trailing", PixelInterval.exact(200.0), kind, provenance),
        BoundaryObservation("top", PixelInterval.exact(0.0), kind, provenance),
        BoundaryObservation("bottom", PixelInterval.exact(100.0), kind, provenance),
    )
    geometry = replace(
        candidate.geometry,
        count=1,
        frames=(Box(0, 0, 200, 100),),
        separator_observations=(),
        separator_assignments=(),
        frame_boundaries=(),
        boundary_observations=observations,
        sequence_provenance=provenance,
    )
    return BuiltCandidate(geometry, candidate.count_hypothesis, ())


class PhysicalDetectionResolutionContractTest(unittest.TestCase):
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
        paths = _boundary_proof_paths(built, candidate_evidence_fixture())
        geometry_path = next(path for path in paths if path.code == "geometry_led")
        self.assertEqual(geometry_path.state, EvidenceState.UNAVAILABLE)

    def test_two_measured_sides_can_support_single_frame_geometry(self) -> None:
        built = _single_frame_candidate(measured_boundaries=True)
        paths = _boundary_proof_paths(built, candidate_evidence_fixture())
        geometry_path = next(path for path in paths if path.code == "geometry_led")
        self.assertEqual(geometry_path.state, EvidenceState.SUPPORTED)

    def test_full_canvas_never_becomes_a_physical_proof_path(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            sequence_provenance=MeasurementProvenance(
                "holder_canvas",
                "full_canvas",
                ("canvas",),
            ),
            boundary_observations=canvas_boundary_observations(200, 100),
        )
        built = BuiltCandidate(geometry, candidate.count_hypothesis, ())
        evidence = candidate_evidence_fixture()
        evidence = replace(
            evidence,
            separator_sequence=replace(
                evidence.separator_sequence,
                state=EvidenceState.UNAVAILABLE,
                hard_count=0,
                hard_boundary_indexes=(),
                missing_boundary_indexes=(1,),
            ),
        )
        paths = _boundary_proof_paths(built, evidence)
        self.assertFalse(
            any(path.state == EvidenceState.SUPPORTED for path in paths)
        )

    def test_one_canvas_sequence_edge_cannot_prove_placement(self) -> None:
        candidate = candidate_fixture()
        observations = tuple(
            replace(
                observation,
                kind=("canvas_clip" if observation.side == "leading" else observation.kind),
            )
            for observation in candidate.geometry.boundary_observations
        )
        geometry = replace(candidate.geometry, boundary_observations=observations)
        built = BuiltCandidate(geometry, candidate.count_hypothesis, ())
        paths = _boundary_proof_paths(built, candidate_evidence_fixture())
        self.assertFalse(
            any(path.state == EvidenceState.SUPPORTED for path in paths)
        )

    def test_geometry_resolution_requires_sequence_conservation(self) -> None:
        candidate = candidate_fixture()
        conservation = replace(
            candidate.assessment.evidence.frame_sequence.conservation,
            state=EvidenceState.UNAVAILABLE,
        )
        evidence = replace(
            candidate.assessment.evidence,
            frame_sequence=replace(
                candidate.assessment.evidence.frame_sequence,
                conservation=conservation,
            ),
        )
        candidate = replace(
            candidate,
            assessment=replace(candidate.assessment, evidence=evidence),
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
                        "physical_frame_aspect",
                        "bidirectional_boundary_constraint",
                        ("format_physical_spec", "sequence_boundaries"),
                    ),
                ),
            ),
        )
        built = BuiltCandidate(geometry, candidate.count_hypothesis, ())
        evidence = candidate_evidence_fixture()
        evidence = replace(
            evidence,
            separator_sequence=replace(
                evidence.separator_sequence,
                state=EvidenceState.UNAVAILABLE,
                hard_count=0,
                hard_boundary_indexes=(),
                missing_boundary_indexes=(1,),
            ),
        )
        paths = _boundary_proof_paths(built, evidence)
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
            ("detection", "image_width", "image_height"),
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


if __name__ == "__main__":
    unittest.main()
