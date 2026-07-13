from __future__ import annotations

import unittest
from dataclasses import fields
from inspect import signature
from pathlib import Path
from unittest.mock import patch

import numpy as np

from x5crop.domain import (
    BoundaryKind,
    BoundarySide,
    EvidenceState,
    FrameBoundarySource,
    FrameBoundaryReference,
    FrameDimensionPriorSource,
    MeasurementIdentity,
)
from x5crop.detection.physical.boundary import (
    HolderOcclusionConstraint,
    HolderOcclusionSideEvidence,
    HolderOcclusionSideOutcome,
    visible_sequence_and_crop_envelope,
    holder_occlusion_evidence,
    holder_occlusion_for_sequence,
)
from x5crop.domain import PixelInterval
from x5crop.detection.physical.spacing import (
    observed_spacing_evidence,
    sequence_conservation_evidence,
    spacing_hypothesis,
)
from x5crop.detection.physical.separator.assignment import (
    assign_observation_to_boundary,
    boundary_position_constraint,
    dimension_constrained_boundary,
)
from x5crop.detection.physical.sequence_solver import solve_frame_sequence
from x5crop.detection.physical.separator.observations import (
    measure_focused_separator_band,
    measure_separator_bands,
)
from x5crop.domain import SeparatorBandObservation
from x5crop.configuration.separator import SeparatorObservationParameters
from x5crop.domain import MeasurementProvenance
from x5crop.domain import Box
from x5crop.detection.physical.model import PhotoInterval, SequenceSolution
from x5crop.detection.evidence.film_structure import (
    separator_sequence_evidence,
)
from x5crop.image.statistics import (
    ImageMeasurementStatistics,
)
from x5crop.domain import CropEnvelope, VisibleSequenceSpan
from tools.tests.physical_gate_support import (
    boundary_path_fixture,
    candidate_fixture,
    holder_occlusion_not_applicable,
    separator_constraints,
    separator_observation,
    unavailable_calibration_fixture,
)
from dataclasses import replace
from x5crop.detection.evidence.frame_sequence import (
    sequence_conservation_for_geometry,
)
from x5crop.detection.physical.separator.assignment import frame_boundary_from_assignment
from x5crop.domain import FrameDimensionPrior
from x5crop.cache import MeasurementCache
from x5crop.configuration.candidate import SequenceHypothesisParameters
from x5crop.configuration.separator import SeparatorConfiguration
from x5crop.detection.candidate.proposal.sequence import (
    _separator_dimension_hypotheses,
)
from x5crop.detection.physical.separator.observations import (
    SeparatorObservationSet,
)
from x5crop.formats import format_spec
from x5crop.image.statistics import (
    ImageMeasurementStatisticsParameters,
    image_measurement_statistics,
)
from x5crop.domain import SequenceHypothesis


ROOT = Path(__file__).resolve().parents[2]


def _statistics() -> ImageMeasurementStatistics:
    return ImageMeasurementStatistics(
        intensity_quantiles=(0.0, 32.0, 128.0, 224.0, 255.0),
        intensity_mad=32.0,
        gradient_quantiles=(0.0, 32.0, 128.0),
        gradient_mad=1.0,
        texture_quantiles=(0.0, 32.0, 128.0),
        texture_mad=1.0,
        edge_texture_quantiles=(0.0, 32.0, 128.0),
    )


class FrameSequenceGeometryContractTests(unittest.TestCase):
    def test_sequence_observation_budget_is_never_raised_by_count(self) -> None:
        gray = np.zeros((100, 300), dtype=np.uint8)
        cache = MeasurementCache(
            "horizontal",
            gray,
            gray,
            gray.astype(np.float32),
            image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
        )
        box = Box(0, 0, 300, 100)
        source = SequenceHypothesis(
            VisibleSequenceSpan(box),
            CropEnvelope(box),
            MeasurementProvenance(
                MeasurementIdentity.HOLDER_MATERIAL_PROFILE,
                "synthetic",
                (MeasurementIdentity.GRAY_WORK,),
            ),
            (),
        )
        observations = SeparatorObservationSet(
            (
                separator_observation(100.0, start=98.0, end=102.0),
                separator_observation(200.0, start=198.0, end=202.0),
            ),
            False,
        )
        with patch(
            "x5crop.detection.candidate.proposal.sequence.cached_separator_profile",
            return_value=np.zeros(300, dtype=np.float32),
        ), patch(
            "x5crop.detection.candidate.proposal.sequence.measure_separator_bands",
            return_value=observations,
        ):
            result = _separator_dimension_hypotheses(
                [source],
                format_spec("135"),
                3,
                cache,
                unavailable_calibration_fixture(),
                "horizontal",
                SeparatorConfiguration(),
                SequenceHypothesisParameters(
                    observation_budget=1,
                    maximum_hypotheses=12,
                ),
            )

        self.assertEqual(result.hypotheses, ())
        self.assertTrue(result.budget_exhausted)

    def test_not_applicable_holder_occlusion_cannot_hide_frame_width(self) -> None:
        with self.assertRaises(ValueError):
            HolderOcclusionSideEvidence(
                BoundarySide.LEADING,
                HolderOcclusionSideOutcome.BOUNDARY_NOT_HOLDER_MATERIAL,
                PixelInterval(1.0, 2.0),
                None,
            )

    def test_nonintersecting_boundary_constraints_have_no_fabricated_midpoint(
        self,
    ) -> None:
        occlusion = HolderOcclusionConstraint(
            PixelInterval.exact(1_000.0),
            PixelInterval.zero(),
        )
        dimensions = FrameDimensionPrior(
            PixelInterval.exact(200.0),
            PixelInterval.exact(100.0),
            (36.0, 24.0),
            FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
            MeasurementProvenance(
                MeasurementIdentity.FRAME_DIMENSIONS,
                "synthetic",
                (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
            ),
        )

        with self.assertRaises(ValueError):
            boundary_position_constraint(
                VisibleSequenceSpan(Box(0, 0, 100, 100)),
                1,
                2,
                dimensions,
                occlusion,
            )

    def test_separator_requires_a_connected_cross_axis_pixel_path(self) -> None:
        gray = np.full((100, 200), 128, dtype=np.uint8)
        gray[::2, 95] = 0
        gray[1::2, 104] = 0
        profile = np.zeros(200, dtype=np.float32)
        profile[95:105] = 1.0
        parameters = SeparatorObservationParameters(
            activation_percentile=99.0,
            minimum_run_px=1,
            maximum_observations=8,
        )
        observation = measure_focused_separator_band(
            profile,
            PixelInterval(95.0, 105.0),
            gray_work=gray,
            corridor=Box(0, 0, 200, 100),
            statistics=_statistics(),
            parameters=parameters,
        )
        assert observation is not None
        self.assertEqual(
            observation.cross_axis.state,
            EvidenceState.CONTRADICTED,
        )

        gray[:, 100] = 0
        observation = measure_focused_separator_band(
            profile,
            PixelInterval(95.0, 105.0),
            gray_work=gray,
            corridor=Box(0, 0, 200, 100),
            statistics=_statistics(),
            parameters=parameters,
        )
        assert observation is not None
        self.assertEqual(observation.cross_axis.state, EvidenceState.SUPPORTED)

    def test_separator_path_allows_small_blank_interruptions_without_jumping(self) -> None:
        gray = np.full((100, 200), 128, dtype=np.uint8)
        gray[:, 100] = 0
        gray[49:51, 100] = 128
        profile = np.zeros(200, dtype=np.float32)
        profile[95:105] = 1.0
        observation = measure_focused_separator_band(
            profile,
            PixelInterval(95.0, 105.0),
            gray_work=gray,
            corridor=Box(0, 0, 200, 100),
            statistics=_statistics(),
            parameters=SeparatorObservationParameters(
                activation_percentile=99.0,
                minimum_run_px=1,
                maximum_observations=8,
                maximum_cross_axis_break_ratio=0.03,
            ),
        )
        assert observation is not None
        self.assertEqual(observation.cross_axis.state, EvidenceState.SUPPORTED)

    def test_unused_weak_band_does_not_reduce_selected_separator_proof(self) -> None:
        geometry = candidate_fixture().geometry
        unused = separator_observation(
            35.0,
            start=30.0,
            end=40.0,
            cross_axis_state=EvidenceState.CONTRADICTED,
        )
        geometry = replace(
            geometry,
            separator_observations=(*geometry.separator_observations, unused),
        )
        evidence = separator_sequence_evidence(geometry)
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
            gray_work=np.zeros((100, 200), dtype=np.uint8),
            corridor=Box(0, 0, 200, 100),
            statistics=_statistics(),
            parameters=SeparatorObservationParameters(
                activation_percentile=70.0,
                minimum_run_px=1,
                maximum_observations=8,
            ),
        )
        self.assertEqual(len(observations.observations), 1)
        self.assertEqual(observations.observations[0].width, 60.0)

    def test_separator_observation_budget_exhaustion_is_explicit(self) -> None:
        profile = np.zeros(100, dtype=np.float32)
        for start in (10, 30, 50, 70):
            profile[start : start + 2] = 1.0
        result = measure_separator_bands(
            profile,
            gray_work=np.zeros((100, 100), dtype=np.uint8),
            corridor=Box(0, 0, 100, 100),
            statistics=_statistics(),
            parameters=SeparatorObservationParameters(
                activation_percentile=95.0,
                minimum_run_px=1,
                maximum_observations=2,
            ),
        )
        self.assertEqual(len(result.observations), 2)
        self.assertTrue(result.budget_exhausted)

    def test_only_fully_contained_band_is_independent_separator_assignment(self) -> None:
        provenance = MeasurementProvenance(
            MeasurementIdentity.SEPARATOR_PROFILE,
            "synthetic",
            (MeasurementIdentity.GRAY_WORK,),
        )
        contained_source = separator_observation(45.0, start=40.0, end=50.0)
        contained = replace(
            contained_source,
            material=replace(contained_source.material, provenance=provenance),
            provenance=provenance,
        )
        partial_source = separator_observation(60.0, start=50.0, end=70.0)
        partial = replace(
            partial_source,
            material=replace(partial_source.material, provenance=provenance),
            provenance=provenance,
        )
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
            tonal_evidence=0.95,
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
                (36.0, 24.0),
                FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
                MeasurementProvenance(
                    MeasurementIdentity.FRAME_DIMENSIONS,
                    "synthetic",
                    (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                ),
            ),
            (),
            10_000,
            edge_texture_limit=1.0,
        )
        self.assertEqual(len(result.assignments), 1)
        self.assertEqual(result.assignments[0].state, EvidenceState.CONTRADICTED)
        self.assertFalse(result.assignments[0].used_for_boundary)

    def test_selected_observation_boundaries_are_monotonic(self) -> None:
        result = solve_frame_sequence(
            (
                separator_observation(180.0, tonal_evidence=0.99, start=175.0, end=185.0),
                separator_observation(120.0, tonal_evidence=0.80, start=115.0, end=125.0),
            ),
            (),
            VisibleSequenceSpan(Box(0, 0, 300, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval(50.0, 150.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
                MeasurementProvenance(
                    MeasurementIdentity.FRAME_DIMENSIONS,
                    "synthetic",
                    (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                ),
            ),
            (),
            10_000,
            edge_texture_limit=1.0,
        )
        coordinates = tuple(boundary.coordinate for boundary in result.boundaries)
        self.assertEqual(coordinates, tuple(sorted(coordinates)))

    def test_focused_measurement_is_geometry_dependent_not_hard_evidence(self) -> None:
        profile = np.zeros(200, dtype=np.float32)
        profile[70:130] = 0.95
        observation = measure_focused_separator_band(
            profile,
            PixelInterval(90.0, 110.0),
            gray_work=np.zeros((100, 200), dtype=np.uint8),
            corridor=Box(0, 0, 200, 100),
            statistics=_statistics(),
            parameters=SeparatorObservationParameters(
                activation_percentile=70.0,
                minimum_run_px=1,
                maximum_observations=8,
            ),
        )
        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual((observation.start, observation.end), (90.0, 110.0))
        self.assertIn(
            MeasurementIdentity.FRAME_DIMENSIONS,
            observation.provenance.dependencies,
        )
        result = solve_frame_sequence(
            (),
            ((1, observation),),
            VisibleSequenceSpan(Box(0, 0, 200, 100)),
            2,
            FrameDimensionPrior(
                PixelInterval(80.0, 100.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
                MeasurementProvenance(
                    MeasurementIdentity.FRAME_DIMENSIONS,
                    "synthetic",
                    (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                ),
            ),
            (),
            10_000,
            edge_texture_limit=1.0,
        )
        self.assertEqual(len(result.assignments), 1)
        self.assertEqual(result.assignments[0].state, EvidenceState.UNAVAILABLE)
        self.assertTrue(result.assignments[0].geometry_dependent)
        self.assertFalse(result.assignments[0].independent)
        self.assertFalse(result.boundaries[0].hard_separator)

    def test_dimension_constrained_boundary_is_never_hard_separator(self) -> None:
        boundary = dimension_constrained_boundary(
            1,
            PixelInterval(95.0, 105.0),
            MeasurementProvenance(
                MeasurementIdentity.FRAME_DIMENSIONS,
                "bidirectional_constraint",
                (
                    MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
                    MeasurementIdentity.SEQUENCE_BOUNDARIES,
                ),
            ),
        )
        self.assertFalse(boundary.hard_separator)
        self.assertEqual(
            boundary.source,
            FrameBoundarySource.DIMENSION_CONSTRAINED,
        )

    def test_boundary_uncertainty_separates_visible_span_and_crop_envelope(self) -> None:
        provenance = MeasurementProvenance(
            MeasurementIdentity.HOLDER_MATERIAL_PROFILE,
            "synthetic",
            (MeasurementIdentity.GRAY_WORK,),
        )
        observations = (
            boundary_path_fixture(BoundarySide.LEADING, PixelInterval(9.0, 11.0), BoundaryKind.HOLDER_MATERIAL_TRANSITION, provenance),
            boundary_path_fixture(BoundarySide.TRAILING, PixelInterval(189.0, 191.0), BoundaryKind.HOLDER_MATERIAL_TRANSITION, provenance),
            boundary_path_fixture(BoundarySide.TOP, PixelInterval(4.0, 6.0), BoundaryKind.TONAL_TRANSITION, provenance),
            boundary_path_fixture(BoundarySide.BOTTOM, PixelInterval(94.0, 96.0), BoundaryKind.TONAL_TRANSITION, provenance),
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
                    FrameBoundaryReference(None, 1),
                    PixelInterval.exact(5.0),
                    MeasurementProvenance(
                        MeasurementIdentity.SEPARATOR_PROFILE,
                        "synthetic",
                        (),
                    ),
                ),
                observed_spacing_evidence(
                    FrameBoundaryReference(None, 2),
                    PixelInterval.exact(10.0),
                    MeasurementProvenance(
                        MeasurementIdentity.SEPARATOR_PROFILE,
                        "synthetic",
                        (),
                    ),
                ),
            ),
            holder_occlusion=holder_occlusion_not_applicable(),
        )
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_overlap_can_balance_positive_separator_width(self) -> None:
        evidence = sequence_conservation_evidence(
            visible_length_px=PixelInterval.exact(302.0),
            count=3,
            frame_width_px=PixelInterval.exact(100.0),
            spacings=(
                observed_spacing_evidence(
                    FrameBoundaryReference(None, 1),
                    PixelInterval.exact(5.0),
                    MeasurementProvenance(
                        MeasurementIdentity.SEPARATOR_PROFILE,
                        "synthetic",
                        (),
                    ),
                ),
                observed_spacing_evidence(
                    FrameBoundaryReference(None, 2),
                    PixelInterval.exact(-3.0),
                    MeasurementProvenance(
                        MeasurementIdentity.PHOTO_EDGES,
                        "synthetic",
                        (),
                    ),
                ),
            ),
            holder_occlusion=holder_occlusion_not_applicable(),
        )
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_leading_holder_occlusion_explains_short_visible_edge_frame(self) -> None:
        boundary = boundary_path_fixture(
            side=BoundarySide.LEADING,
            position=PixelInterval.exact(20.0),
            kind=BoundaryKind.HOLDER_MATERIAL_TRANSITION,
            provenance=MeasurementProvenance(
                MeasurementIdentity.HOLDER_MATERIAL_PROFILE,
                "holder_material_transition",
                (MeasurementIdentity.GRAY_WORK,),
                ("leading",),
            ),
        )
        evidence = holder_occlusion_evidence(
            leading_boundary=boundary,
            trailing_boundary=None,
            leading_visible_frame_width=PixelInterval.exact(94.0),
            trailing_visible_frame_width=None,
            frame_width_px=PixelInterval.exact(100.0),
            edge_texture_limit=1.0,
        )
        self.assertEqual(evidence.leading.state, EvidenceState.SUPPORTED)
        self.assertEqual(evidence.leading.hidden_width_px, PixelInterval.exact(6.0))

    def test_single_frame_two_sided_occlusion_does_not_duplicate_hidden_width(
        self,
    ) -> None:
        provenance = MeasurementProvenance(
            MeasurementIdentity.HOLDER_MATERIAL_PROFILE,
            "holder_material_transition",
            (MeasurementIdentity.GRAY_WORK,),
        )
        evidence = holder_occlusion_for_sequence(
            (
                boundary_path_fixture(
                    BoundarySide.LEADING,
                    PixelInterval.exact(0.0),
                    BoundaryKind.HOLDER_MATERIAL_TRANSITION,
                    provenance,
                ),
                boundary_path_fixture(
                    BoundarySide.TRAILING,
                    PixelInterval.exact(94.0),
                    BoundaryKind.HOLDER_MATERIAL_TRANSITION,
                    provenance,
                ),
            ),
            VisibleSequenceSpan(Box(0, 0, 94, 100)),
            (),
            PixelInterval.exact(100.0),
            edge_texture_limit=1.0,
        )

        self.assertEqual(evidence.leading.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(evidence.trailing.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(evidence.leading.hidden_width_px, PixelInterval(0.0, 6.0))
        self.assertEqual(evidence.trailing.hidden_width_px, PixelInterval(0.0, 6.0))
        self.assertEqual(evidence.combined_hidden_width_px, PixelInterval.exact(6.0))

    def test_high_texture_edge_rules_out_holder_material_occlusion(self) -> None:
        boundary_source = boundary_path_fixture(
            side=BoundarySide.LEADING,
            position=PixelInterval.exact(20.0),
            kind=BoundaryKind.TEXTURE_TRANSITION,
            provenance=MeasurementProvenance(
                MeasurementIdentity.HOLDER_MATERIAL_PROFILE,
                "texture_transition",
                (MeasurementIdentity.GRAY_WORK,),
                ("leading",),
            ),
        )
        boundary = replace(
            boundary_source,
            outer_material=replace(
                boundary_source.outer_material,
                texture_median=2.0,
            ),
        )

        evidence = holder_occlusion_evidence(
            leading_boundary=boundary,
            trailing_boundary=None,
            leading_visible_frame_width=PixelInterval.exact(94.0),
            trailing_visible_frame_width=None,
            frame_width_px=PixelInterval.exact(100.0),
            edge_texture_limit=1.0,
        )

        self.assertEqual(evidence.leading.state, EvidenceState.NOT_APPLICABLE)
        self.assertEqual(evidence.leading.hidden_width_px, PixelInterval.zero())

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
                    MeasurementIdentity.FRAME_DIMENSIONS,
                    "bidirectional_constraint",
                    (
                        MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
                        MeasurementIdentity.SEQUENCE_BOUNDARIES,
                    ),
                ),
            ),
        )
        geometry = replace(
            candidate.geometry,
            count=3,
            visible_sequence_span=VisibleSequenceSpan(Box(0, 0, 315, 100)),
            crop_envelope=CropEnvelope(Box(0, 0, 315, 100)),
            frames=(
                Box(0, 0, 102, 100),
                Box(102, 0, 210, 100),
                Box(210, 0, 315, 100),
            ),
            photo_intervals=(
                PhotoInterval(
                    1,
                    PixelInterval.exact(0.0),
                    PixelInterval.exact(100.0),
                    observed.provenance,
                    observed.provenance,
                    True,
                    True,
                ),
                PhotoInterval(
                    2,
                    PixelInterval.exact(105.0),
                    PixelInterval.exact(205.0),
                    observed.provenance,
                    observed.provenance,
                    True,
                    True,
                ),
                PhotoInterval(
                    3,
                    PixelInterval.exact(215.0),
                    PixelInterval.exact(315.0),
                    observed.provenance,
                    observed.provenance,
                    True,
                    True,
                ),
            ),
            frame_boundaries=boundaries,
            separator_observations=(observed,),
            separator_assignments=(assignment,),
            frame_dimension_prior=FrameDimensionPrior(
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
                MeasurementProvenance(
                    MeasurementIdentity.FRAME_DIMENSIONS,
                    "test",
                    (),
                ),
            ),
            inter_frame_spacings=(
                observed_spacing_evidence(
                    FrameBoundaryReference(None, 1),
                    PixelInterval.exact(5.0),
                    observed.provenance,
                ),
                spacing_hypothesis(
                    FrameBoundaryReference(None, 2),
                    PixelInterval.exact(10.0),
                    MeasurementProvenance(
                        MeasurementIdentity.FRAME_GEOMETRY,
                        "test_hypothesis",
                        (MeasurementIdentity.FRAME_DIMENSIONS,),
                    ),
                ),
            ),
        )
        evidence = sequence_conservation_for_geometry(geometry)
        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
