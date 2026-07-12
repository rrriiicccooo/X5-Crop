from __future__ import annotations

import unittest
from dataclasses import fields
from inspect import signature
from pathlib import Path

import numpy as np

from x5crop.domain import EvidenceState
from x5crop.detection.physical.boundary import (
    BoundaryObservation,
    HolderOcclusionEvidence,
    visible_sequence_and_crop_envelope,
    holder_occlusion_evidence,
)
from x5crop.domain import PixelInterval
from x5crop.detection.physical.spacing import (
    observed_spacing_evidence,
    sequence_conservation_evidence,
    spacing_hypothesis,
)
from x5crop.detection.physical.separator.assignment import (
    assign_observation_to_boundary,
    dimension_constrained_boundary,
)
from x5crop.detection.physical.sequence_solver import solve_frame_sequence
from x5crop.detection.physical.separator.observations import (
    measure_focused_separator_band,
    measure_separator_bands,
)
from x5crop.domain import SeparatorBandObservation
from x5crop.policies.parameters.separator import SeparatorObservationParameters
from x5crop.domain import MeasurementProvenance
from x5crop.domain import Box
from x5crop.detection.physical.model import SequenceSolution
from x5crop.detection.evidence.separator_continuity import (
    separator_cross_axis_continuity_evidence,
)
from x5crop.geometry.detection_parameters import SeparatorContinuityParameters
from x5crop.domain import CropEnvelope, VisibleSequenceSpan
from tools.tests.physical_gate_support import (
    candidate_fixture,
    separator_constraints,
    separator_observation,
)
from dataclasses import replace
from x5crop.detection.evidence.frame_sequence import frame_sequence_evidence
from x5crop.detection.physical.separator.assignment import frame_boundary_from_assignment
from x5crop.domain import FrameDimensionPrior


ROOT = Path(__file__).resolve().parents[2]


class FrameSequenceGeometryContractTests(unittest.TestCase):
    def test_unused_weak_band_does_not_reduce_selected_separator_proof(self) -> None:
        geometry = candidate_fixture().geometry
        unused = separator_observation(35.0, start=30.0, end=40.0)
        geometry = replace(
            geometry,
            separator_observations=(*geometry.separator_observations, unused),
        )
        gray = np.full((100, 200), 128, dtype=np.uint8)
        gray[:, 95:105] = 255
        evidence = separator_cross_axis_continuity_evidence(
            gray,
            geometry,
            SeparatorContinuityParameters(),
        )
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_raw_separator_observation_is_count_independent(self) -> None:
        names = {field.name for field in fields(SeparatorBandObservation)}
        self.assertNotIn("index", names)
        self.assertNotIn("method", names)
        parameters = signature(measure_separator_bands).parameters
        self.assertNotIn("count", parameters)
        self.assertNotIn("pitch", parameters)

    def test_raw_measurement_keeps_oversized_tonal_run(self) -> None:
        profile = np.zeros(200, dtype=np.float32)
        profile[70:130] = 0.95
        observations = measure_separator_bands(
            profile,
            corridor_start=0.0,
            parameters=SeparatorObservationParameters(
                profile_threshold=0.5,
                minimum_run_px=1,
                maximum_observations=8,
            ),
        )
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].width, 60.0)

    def test_only_fully_contained_band_is_independent_separator_assignment(self) -> None:
        provenance = MeasurementProvenance(
            "separator_profile",
            "synthetic",
            ("gray_work",),
        )
        contained = SeparatorBandObservation(40.0, 50.0, 45.0, 0.9, provenance)
        partial = SeparatorBandObservation(50.0, 70.0, 60.0, 0.9, provenance)
        allowed = PixelInterval(35.0, 55.0)
        constraints = separator_constraints(1, allowed, PixelInterval(0.0, 25.0))
        accepted = assign_observation_to_boundary(1, contained, *constraints)
        dependent = assign_observation_to_boundary(1, partial, *constraints)
        self.assertTrue(accepted.independent)
        self.assertFalse(dependent.independent)
        self.assertTrue(dependent.geometry_dependent)

    def test_width_contradicted_raw_band_remains_a_candidate_assignment(self) -> None:
        observation = separator_observation(
            175.0,
            score=0.95,
            start=160.0,
            end=190.0,
        )
        result = solve_frame_sequence(
            (observation,),
            (),
            VisibleSequenceSpan(Box(0, 0, 210, 100)),
            2,
            FrameDimensionPrior(
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                ((36.0, 24.0),),
                "synthetic",
                MeasurementProvenance(
                    "frame_dimensions",
                    "synthetic",
                    ("physical_frame_size",),
                ),
            ),
            HolderOcclusionEvidence.not_applicable(),
            (),
        )
        self.assertEqual(len(result.assignments), 1)
        self.assertEqual(result.assignments[0].state, EvidenceState.CONTRADICTED)
        self.assertFalse(result.assignments[0].used_for_boundary)

    def test_selected_observation_boundaries_are_monotonic(self) -> None:
        result = solve_frame_sequence(
            (
                separator_observation(180.0, score=0.99, start=175.0, end=185.0),
                separator_observation(120.0, score=0.80, start=115.0, end=125.0),
            ),
            (),
            VisibleSequenceSpan(Box(0, 0, 300, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval(50.0, 150.0),
                PixelInterval.exact(100.0),
                ((36.0, 24.0),),
                "synthetic",
                MeasurementProvenance(
                    "frame_dimensions",
                    "synthetic",
                    ("physical_frame_size",),
                ),
            ),
            HolderOcclusionEvidence.not_applicable(),
            (),
        )
        coordinates = tuple(boundary.coordinate for boundary in result.boundaries)
        self.assertEqual(coordinates, tuple(sorted(coordinates)))

    def test_focused_measurement_is_geometry_dependent_not_hard_evidence(self) -> None:
        profile = np.zeros(200, dtype=np.float32)
        profile[70:130] = 0.95
        observation = measure_focused_separator_band(
            profile,
            PixelInterval(90.0, 110.0),
            corridor_start=0.0,
            parameters=SeparatorObservationParameters(
                profile_threshold=0.5,
                minimum_run_px=1,
                maximum_observations=8,
            ),
        )
        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual((observation.start, observation.end), (90.0, 110.0))
        self.assertIn("frame_dimensions", observation.provenance.dependencies)

    def test_dimension_constrained_boundary_is_never_hard_separator(self) -> None:
        boundary = dimension_constrained_boundary(
            1,
            PixelInterval(95.0, 105.0),
            MeasurementProvenance(
                "frame_dimensions",
                "bidirectional_constraint",
                ("frame_size", "sequence_boundaries"),
            ),
        )
        self.assertFalse(boundary.hard_separator)
        self.assertEqual(boundary.source, "dimension_constrained")

    def test_boundary_uncertainty_separates_visible_span_and_crop_envelope(self) -> None:
        provenance = MeasurementProvenance(
            "holder_boundary_profile",
            "synthetic",
            ("gray_work",),
        )
        observations = (
            BoundaryObservation("leading", PixelInterval(9.0, 11.0), "white_holder_transition", provenance),
            BoundaryObservation("trailing", PixelInterval(189.0, 191.0), "white_holder_transition", provenance),
            BoundaryObservation("top", PixelInterval(4.0, 6.0), "tonal_transition", provenance),
            BoundaryObservation("bottom", PixelInterval(94.0, 96.0), "tonal_transition", provenance),
        )
        visible, envelope = visible_sequence_and_crop_envelope(
            observations,
            canvas_width=200,
            canvas_height=100,
        )
        self.assertEqual(visible, VisibleSequenceSpan(Box(10, 5, 190, 95)))
        self.assertEqual(envelope, CropEnvelope(Box(9, 4, 191, 96)))

    def test_candidate_geometry_has_distinct_sequence_and_crop_fields(self) -> None:
        names = {field.name for field in fields(SequenceSolution)}
        self.assertIn("visible_sequence_span", names)
        self.assertIn("crop_envelope", names)
        self.assertNotIn("film" + "_span", names)
        self.assertNotIn("image_crop_envelope", names)

    def test_active_source_has_no_generic_outer_or_film_span_identity(self) -> None:
        active = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "x5crop").rglob("*.py")
        )
        self.assertNotIn("Film" + "Span", active)
        self.assertNotIn("Outer" + "Proposal", active)

    def test_irregular_positive_spacing_satisfies_sequence_conservation(self) -> None:
        evidence = sequence_conservation_evidence(
            visible_length_px=PixelInterval.exact(315.0),
            count=3,
            frame_width_px=PixelInterval.exact(100.0),
            spacings=(
                observed_spacing_evidence(
                    1,
                    PixelInterval.exact(5.0),
                    MeasurementProvenance("separator_profile", "synthetic", ()),
                ),
                observed_spacing_evidence(
                    2,
                    PixelInterval.exact(10.0),
                    MeasurementProvenance("separator_profile", "synthetic", ()),
                ),
            ),
            holder_occlusion=HolderOcclusionEvidence.not_applicable(),
        )
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_overlap_can_balance_positive_separator_width(self) -> None:
        evidence = sequence_conservation_evidence(
            visible_length_px=PixelInterval.exact(302.0),
            count=3,
            frame_width_px=PixelInterval.exact(100.0),
            spacings=(
                observed_spacing_evidence(
                    1,
                    PixelInterval.exact(5.0),
                    MeasurementProvenance("separator_profile", "synthetic", ()),
                ),
                observed_spacing_evidence(
                    2,
                    PixelInterval.exact(-3.0),
                    MeasurementProvenance("photo_edges", "synthetic", ()),
                ),
            ),
            holder_occlusion=HolderOcclusionEvidence.not_applicable(),
        )
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_leading_holder_occlusion_explains_short_visible_edge_frame(self) -> None:
        boundary = BoundaryObservation(
            side="leading",
            position=PixelInterval.exact(20.0),
            kind="white_holder_transition",
            provenance=MeasurementProvenance(
                "holder_boundary_profile",
                "white_holder_transition",
                ("gray_work",),
                ("leading",),
            ),
        )
        evidence = holder_occlusion_evidence(
            leading_boundary=boundary,
            trailing_boundary=None,
            leading_visible_frame_width=PixelInterval.exact(94.0),
            trailing_visible_frame_width=None,
            frame_width_px=PixelInterval.exact(100.0),
        )
        self.assertEqual(evidence.leading.state, EvidenceState.SUPPORTED)
        self.assertEqual(evidence.leading.hidden_width_px, PixelInterval.exact(6.0))

    def test_missing_spacing_remains_an_explicit_hypothesis(self) -> None:
        candidate = candidate_fixture()
        observed = separator_observation(102.5, start=100.0, end=105.0)
        assignment = assign_observation_to_boundary(
            1,
            observed,
            *separator_constraints(
                1,
                PixelInterval(95.0, 110.0),
                PixelInterval(0.0, 10.0),
            ),
        )
        assignment = replace(assignment, used_for_boundary=True)
        boundaries = (
            frame_boundary_from_assignment(assignment),
            dimension_constrained_boundary(
                2,
                PixelInterval.exact(210.0),
                MeasurementProvenance(
                    "frame_dimensions",
                    "bidirectional_constraint",
                    ("frame_size", "sequence_boundaries"),
                ),
            ),
        )
        geometry = replace(
            candidate.geometry,
            count=3,
            visible_sequence_span=VisibleSequenceSpan(Box(0, 0, 315, 100)),
            crop_envelope=CropEnvelope(Box(0, 0, 315, 100)),
            frame_boundaries=boundaries,
            separator_observations=(observed,),
            separator_assignments=(assignment,),
            frame_dimension_prior=FrameDimensionPrior(
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                ((36.0, 24.0),),
                "test",
                MeasurementProvenance("frame_dimensions", "test", ()),
            ),
            inter_frame_relations=(
                observed_spacing_evidence(
                    1,
                    PixelInterval.exact(5.0),
                    observed.provenance,
                ),
                spacing_hypothesis(
                    2,
                    PixelInterval.exact(10.0),
                    MeasurementProvenance(
                        "frame_geometry",
                        "test_hypothesis",
                        ("frame_dimensions",),
                    ),
                ),
            ),
        )
        evidence = frame_sequence_evidence(geometry)
        self.assertEqual(evidence.spacings[0].signed_width_px, PixelInterval.exact(5.0))
        self.assertEqual(evidence.spacings[1].signed_width_px, PixelInterval.exact(10.0))
        self.assertEqual(evidence.spacings[1].state, EvidenceState.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
