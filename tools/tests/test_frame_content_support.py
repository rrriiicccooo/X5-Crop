from __future__ import annotations

from dataclasses import replace
import unittest

import numpy as np

from tools.tests.physical_gate_support import (
    boundary_path_fixture,
    candidate_fixture,
)
from x5crop.configuration.content import ContentConfiguration
from x5crop.detection.evidence.content.external_frame_boundaries import (
    ExternalFrameBoundaryObservation,
)
from x5crop.detection.evidence.content.frame_content import (
    FrameBoundaryContentTrace,
    FrameContentEvidence,
    FrameContentObservation,
)
from x5crop.detection.evidence.content.activation import content_evidence_threshold
from x5crop.detection.evidence.content.internal_frame_boundaries import (
    InternalBoundaryContentContinuityObservation,
    measure_internal_boundary_content_continuity,
    internal_frame_boundary_preservation_evidence,
)
from x5crop.detection.evidence.content.regions import content_region_observation
from x5crop.detection.evidence.frame_coverage import FrameCoverageEvidence
from x5crop.detection.physical.model import (
    BoundaryAnchor,
    BoundaryRoleAuthority,
    FrameBoundarySource,
)
from x5crop.domain import (
    BoundaryKind,
    BoundarySide,
    Box,
    EvidenceState,
    InterFrameBoundaryReference,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from x5crop.image.evidence import make_content_evidence_gray
from x5crop.image.constants import UINT8_MAX_VALUE
from x5crop.image.content import ContentRegionObservation
from x5crop.image.statistics import (
    ImageMeasurementStatisticsParameters,
    image_measurement_statistics,
)


def _provenance(name: str) -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        observation_id=ObservationId(name),
        dependencies=(MeasurementIdentity.FRAME_DIMENSIONS,),
        description=name,
    )


def _frame_content(*, crossing: bool) -> FrameContentEvidence:
    traces = (
        (
            FrameBoundaryContentTrace(
                BoundarySide.TRAILING,
                ((10, 30),),
                2,
            ),
        ),
        (
            FrameBoundaryContentTrace(
                BoundarySide.LEADING,
                ((15, 35),),
                2,
            ),
        ),
    )
    return FrameContentEvidence(
        0.5,
        tuple(
            FrameContentObservation(
                frame_index=index,
                mean=0.8,
                coverage=0.7,
                content_present=True,
                boundary_traces=(traces[index - 1] if crossing else ()),
            )
            for index in (1, 2)
        ),
    )


def _content_measurement(
    gray: np.ndarray,
) -> tuple[np.ndarray, float]:
    parameters = ContentConfiguration().evidence
    evidence = (
        make_content_evidence_gray(gray).astype(np.float32)
        / UINT8_MAX_VALUE
    )
    threshold = content_evidence_threshold(evidence, parameters)
    if threshold is None:
        raise AssertionError("synthetic content measurement requires dynamic range")
    return evidence, float(threshold)


def _content_continuity(
    *,
    crossing: bool,
    boundary_index: int = 1,
) -> tuple[InternalBoundaryContentContinuityObservation, ...]:
    return (
        InternalBoundaryContentContinuityObservation(
            boundary=InterFrameBoundaryReference(None, boundary_index),
            shared_content_track_count=20 if crossing else 0,
            minimum_shared_content_tracks=2,
            long_axis_content_spans_boundary=crossing,
            content_bridge_track_count=20 if crossing else 0,
            minimum_content_bridge_tracks=5,
            gray_discontinuity_track_count=0,
            minimum_gray_discontinuity_tracks=5,
            provenance=MeasurementProvenance(
                MeasurementIdentity.CONTENT_EVIDENCE_IMAGE,
                ObservationId(f"synthetic_content_continuity:{boundary_index}"),
                (
                    MeasurementIdentity.GRAY_WORK,
                    MeasurementIdentity.FRAME_GEOMETRY,
                ),
                "synthetic internal-boundary content continuity",
            ),
        ),
    )


def _measured_overlap_slots(*, width_pattern_roles: bool):
    left, right = candidate_fixture().geometry.frame_slots

    def boundary(
        template,
        *,
        side: BoundarySide,
        position: float,
        name: str,
    ):
        measurement = MeasurementProvenance(
            MeasurementIdentity.BOUNDARY_PATHS,
            ObservationId(name),
            (MeasurementIdentity.GRAY_WORK,),
            "measured overlap edge",
        )
        path = boundary_path_fixture(
            side,
            PixelInterval.exact(position),
            BoundaryKind.TONAL_TRANSITION,
            measurement,
        )
        role = (
            MeasurementProvenance(
                MeasurementIdentity.PHOTO_EDGES,
                ObservationId(f"{name}:width-pattern-role"),
                (
                    MeasurementIdentity.BOUNDARY_PATHS,
                    MeasurementIdentity.FRAME_WIDTH_PATTERN,
                ),
                "overlap-edge role assigned only by repeated width geometry",
                (measurement.observation_id,),
            )
            if width_pattern_roles
            else measurement
        )
        return replace(
            template,
            position=path.position,
            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            boundary_anchor=BoundaryAnchor(
                path,
                side,
                EvidenceState.SUPPORTED,
                (
                    BoundaryRoleAuthority.MEASUREMENT_CORROBORATED
                    if width_pattern_roles
                    else BoundaryRoleAuthority.DIRECT_MEASUREMENT
                ),
                role,
            ),
            inference_provenance=None,
        )

    return (
        replace(
            left,
            trailing=boundary(
                left.trailing,
                side=BoundarySide.TRAILING,
                position=165.0,
                name="left_overlap_edge",
            ),
            visible_long_axis=PixelInterval(0.0, 165.0),
        ),
        replace(
            right,
            leading=boundary(
                right.leading,
                side=BoundarySide.LEADING,
                position=155.0,
                name="right_overlap_edge",
            ),
            visible_long_axis=PixelInterval(155.0, 310.0),
        ),
    )


class FrameContentSupportTest(unittest.TestCase):
    def test_smooth_content_across_an_inferred_cut_is_continuous(self) -> None:
        geometry = candidate_fixture().geometry
        rows, columns = 60, 310
        y, x = np.mgrid[:rows, :columns]
        gray = np.clip(
            110.0
            + 30.0 * np.sin(x / 3.0)
            + 20.0 * np.sin(y / 4.0)
            + 10.0 * np.sin((x + y) / 2.0),
            0.0,
            255.0,
        ).astype(np.uint8)
        coverage = FrameCoverageEvidence(
            (0, columns),
            ((0, 150), (160, columns)),
            ((0, columns),),
            0,
        )
        content_evidence, threshold = _content_measurement(gray)

        observations = measure_internal_boundary_content_continuity(
            geometry.frame_slots,
            replace(_frame_content(crossing=True), threshold=threshold),
            coverage,
            content_evidence,
            gray,
            image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
            ContentConfiguration().evidence,
        )

        self.assertEqual(observations[0].state, EvidenceState.SUPPORTED)
        self.assertTrue(observations[0].continuous_content_crossing)

    def test_low_activity_corridor_is_not_continuous_content(self) -> None:
        geometry = candidate_fixture().geometry
        rows, columns = 60, 310
        y, x = np.mgrid[:rows, :columns]
        gray = np.clip(
            110.0
            + 30.0 * np.sin(x / 3.0)
            + 20.0 * np.sin(y / 4.0)
            + 10.0 * np.sin((x + y) / 2.0),
            0.0,
            255.0,
        )
        gray[:, 140:170] = 100.0
        gray = gray.astype(np.uint8)
        coverage = FrameCoverageEvidence(
            (0, columns),
            ((0, 150), (160, columns)),
            ((0, columns),),
            0,
        )
        content_evidence, threshold = _content_measurement(gray)

        observations = measure_internal_boundary_content_continuity(
            geometry.frame_slots,
            replace(_frame_content(crossing=True), threshold=threshold),
            coverage,
            content_evidence,
            gray,
            image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
            ContentConfiguration().evidence,
        )

        self.assertEqual(observations[0].state, EvidenceState.UNAVAILABLE)
        self.assertFalse(observations[0].continuous_content_crossing)

    def test_sparse_corridor_noise_does_not_form_a_content_bridge(self) -> None:
        geometry = candidate_fixture().geometry
        rows, columns = 60, 310
        content_evidence = np.zeros((rows, columns), dtype=np.float32)
        content_evidence[:, 145:150] = 1.0
        content_evidence[:, 160:165] = 1.0
        for row in range(rows):
            content_evidence[row, 150 + row % 10] = 1.0
        gray = np.full((rows, columns), 100, dtype=np.uint8)
        coverage = FrameCoverageEvidence(
            (0, columns),
            ((0, 150), (160, columns)),
            ((0, columns),),
            0,
        )

        observations = measure_internal_boundary_content_continuity(
            geometry.frame_slots,
            _frame_content(crossing=True),
            coverage,
            content_evidence,
            gray,
            image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
            ContentConfiguration().evidence,
        )

        self.assertEqual(observations[0].state, EvidenceState.UNAVAILABLE)
        self.assertFalse(observations[0].continuous_content_crossing)

    def test_disjoint_track_activity_does_not_form_a_content_bridge(self) -> None:
        geometry = candidate_fixture().geometry
        rows, columns = 60, 310
        content_evidence = np.zeros((rows, columns), dtype=np.float32)
        for offset, column in enumerate(range(145, 165)):
            for track_offset in range(4):
                row = 15 + (offset * 4 + track_offset) % 15
                content_evidence[row, column] = 1.0
        gray = np.full((rows, columns), 100, dtype=np.uint8)
        coverage = FrameCoverageEvidence(
            (0, columns),
            ((0, 150), (160, columns)),
            ((0, columns),),
            0,
        )

        observations = measure_internal_boundary_content_continuity(
            geometry.frame_slots,
            _frame_content(crossing=True),
            coverage,
            content_evidence,
            gray,
            image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
            ContentConfiguration().evidence,
        )

        self.assertEqual(observations[0].state, EvidenceState.UNAVAILABLE)
        self.assertFalse(observations[0].continuous_content_crossing)

    def test_tonal_step_without_content_bridge_is_not_continuous(self) -> None:
        geometry = candidate_fixture().geometry
        rows, columns = 60, 310
        y, x = np.mgrid[:rows, :columns]
        texture = 20.0 * np.sin(x / 3.0) + 15.0 * np.sin(y / 4.0)
        gray = np.clip(70.0 + texture, 0.0, 255.0)
        gray[:, 155:] = np.clip(
            180.0 + texture[:, 155:],
            0.0,
            255.0,
        )
        gray = gray.astype(np.uint8)
        coverage = FrameCoverageEvidence(
            (0, 310),
            ((0, 150), (160, 310)),
            ((0, 310),),
            0,
        )
        content_evidence, threshold = _content_measurement(gray)

        observations = measure_internal_boundary_content_continuity(
            geometry.frame_slots,
            replace(_frame_content(crossing=True), threshold=threshold),
            coverage,
            content_evidence,
            gray,
            image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
            ContentConfiguration().evidence,
        )

        self.assertEqual(observations[0].state, EvidenceState.UNAVAILABLE)
        self.assertFalse(observations[0].continuous_content_crossing)

    def test_content_inside_endpoint_uncertainty_does_not_cross_interval(
        self,
    ) -> None:
        observation = ContentRegionObservation(
            Box(0, 0, 1000, 200),
            ((495, 650),),
            10,
        )

        self.assertFalse(
            observation.reliable_content_intersects(
                PixelInterval(0.0, 500.0)
            )
        )
        self.assertTrue(
            observation.reliable_content_intersects(
                PixelInterval(0.0, 520.0)
            )
        )

    def test_uniform_film_noise_does_not_create_reliable_content_runs(self) -> None:
        rng = np.random.default_rng(7)
        gray = np.clip(
            24.0 + rng.normal(0.0, 1.0, (200, 1000)),
            0.0,
            255.0,
        ).astype(np.uint8)
        evidence = make_content_evidence_gray(gray)

        observation = content_region_observation(
            evidence,
            Box(0, 0, 1000, 200),
            content_configuration=ContentConfiguration(),
        )

        self.assertEqual(observation.reliable_runs, ())

    def test_coherent_photo_texture_remains_visible_content(self) -> None:
        rng = np.random.default_rng(11)
        gray = np.full((200, 1000), 24, dtype=np.uint8)
        gray[:, 700:900] = rng.integers(
            40,
            220,
            size=(200, 200),
            dtype=np.uint8,
        )
        evidence = make_content_evidence_gray(gray)

        observation = content_region_observation(
            evidence,
            Box(0, 0, 1000, 200),
            content_configuration=ContentConfiguration(),
        )

        self.assertTrue(
            any(start < 800 < end for start, end in observation.reliable_runs),
            observation.reliable_runs,
        )

    def test_strip_wide_two_dimensional_texture_is_reliable_content(self) -> None:
        rng = np.random.default_rng(17)
        gray = np.full((200, 1000), 24, dtype=np.uint8)
        frame_intervals = (
            (20, 170),
            (180, 330),
            (340, 490),
            (500, 650),
            (660, 810),
            (820, 970),
        )
        for start, end in frame_intervals:
            gray[:, start:end] = rng.integers(
                40,
                220,
                size=(200, end - start),
                dtype=np.uint8,
            )
        evidence = make_content_evidence_gray(gray)

        observation = content_region_observation(
            evidence,
            Box(0, 0, 1000, 200),
            content_configuration=ContentConfiguration(),
        )

        for start, end in frame_intervals:
            center = (start + end) // 2
            self.assertTrue(
                any(
                    run_start < center < run_end
                    for run_start, run_end in observation.reliable_runs
                ),
                (center, observation.reliable_runs),
            )

    def test_flat_interval_between_textured_frames_is_not_reliable_content(
        self,
    ) -> None:
        rng = np.random.default_rng(23)
        gray = np.full((200, 1000), 24, dtype=np.uint8)
        gray[:, 40:360] = rng.integers(
            40,
            220,
            size=(200, 320),
            dtype=np.uint8,
        )
        gray[:, 640:960] = rng.integers(
            40,
            220,
            size=(200, 320),
            dtype=np.uint8,
        )
        evidence = make_content_evidence_gray(gray)

        observation = content_region_observation(
            evidence,
            Box(0, 0, 1000, 200),
            content_configuration=ContentConfiguration(),
        )

        self.assertTrue(
            any(start < 200 < end for start, end in observation.reliable_runs),
            observation.reliable_runs,
        )
        self.assertFalse(
            any(start < 500 < end for start, end in observation.reliable_runs),
            observation.reliable_runs,
        )
        self.assertTrue(
            any(start < 800 < end for start, end in observation.reliable_runs),
            observation.reliable_runs,
        )

    def test_underexposed_trailing_photo_remains_content_guidance(self) -> None:
        rng = np.random.default_rng(19)
        gray = np.full((200, 1000), 24, dtype=np.uint8)
        for start, end in (
            (20, 170),
            (180, 330),
            (340, 490),
            (500, 650),
            (660, 810),
        ):
            gray[:, start:end] = rng.integers(
                40,
                220,
                size=(200, end - start),
                dtype=np.uint8,
            )
        gray[:, 820:970] = rng.integers(
            24,
            80,
            size=(200, 150),
            dtype=np.uint8,
        )
        evidence = make_content_evidence_gray(gray)

        observation = content_region_observation(
            evidence,
            Box(0, 0, 1000, 200),
            content_configuration=ContentConfiguration(),
        )

        self.assertFalse(
            any(start < 895 < end for start, end in observation.reliable_runs),
            observation.reliable_runs,
        )
        self.assertTrue(
            any(start < 895 < end for start, end in observation.guidance_runs),
            observation.guidance_runs,
        )

    def test_one_dimensional_material_transition_is_not_photo_content(self) -> None:
        gray = np.full((200, 1000), 24, dtype=np.uint8)
        gray[:, 500:] = 220
        evidence = make_content_evidence_gray(gray)

        observation = content_region_observation(
            evidence,
            Box(0, 0, 1000, 200),
            content_configuration=ContentConfiguration(),
        )

        self.assertEqual(observation.reliable_runs, ())

    def test_one_dimensional_film_streaks_are_not_reliable_photo_content(
        self,
    ) -> None:
        gray = np.full((200, 1000), 24, dtype=np.uint8)
        for position in range(450, 550, 4):
            gray[:, position : position + 2] = 220
        evidence = make_content_evidence_gray(gray)

        observation = content_region_observation(
            evidence,
            Box(0, 0, 1000, 200),
            content_configuration=ContentConfiguration(),
        )

        self.assertEqual(observation.reliable_runs, ())

    def test_sparse_film_defects_remain_guidance_beside_strong_photo_texture(
        self,
    ) -> None:
        rng = np.random.default_rng(19)
        gray = np.full((200, 1000), 24, dtype=np.uint8)
        film_transition = np.tile(
            np.linspace(200, 24, 400, dtype=np.float32),
            (200, 1),
        )
        defects = rng.random((200, 400)) < 0.08
        film_transition[defects] = rng.integers(
            0,
            256,
            int(np.count_nonzero(defects)),
        )
        gray[:, :400] = np.clip(film_transition, 0, 255).astype(np.uint8)
        gray[:, 400:] = rng.integers(
            40,
            220,
            size=(200, 600),
            dtype=np.uint8,
        )

        observation = content_region_observation(
            make_content_evidence_gray(gray),
            Box(0, 0, 1000, 200),
            content_configuration=ContentConfiguration(),
        )

        self.assertFalse(
            any(start < 300 < end for start, end in observation.reliable_runs),
            observation.reliable_runs,
        )
        self.assertTrue(
            any(start < 300 < end for start, end in observation.guidance_runs),
            observation.guidance_runs,
        )

    def test_content_run_must_exceed_smoothing_endpoint_uncertainty(self) -> None:
        rng = np.random.default_rng(13)
        gray = np.full((200, 1000), 24, dtype=np.uint8)
        gray[:, 500:540] = rng.integers(
            40,
            220,
            size=(200, 40),
            dtype=np.uint8,
        )
        evidence = make_content_evidence_gray(gray)
        configuration = replace(
            ContentConfiguration(),
            profile=replace(
                ContentConfiguration().profile,
                smooth_ratio=0.1,
            ),
        )

        observation = content_region_observation(
            evidence,
            Box(0, 0, 1000, 200),
            content_configuration=configuration,
        )

        self.assertEqual(observation.reliable_runs, ())

    def test_missing_content_is_unavailable_not_blank_support(self) -> None:
        evidence = FrameContentEvidence(None, (), "content_evidence_unavailable")

        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertFalse(evidence.support_available)

    def test_frame_coverage_rejects_reliable_content_outside_all_slots(self) -> None:
        coverage = FrameCoverageEvidence(
            holder_long_axis_interval=(0, 400),
            frame_slot_intervals=((0, 100), (120, 220)),
            content_runs=((10, 90), (260, 320)),
            content_position_uncertainty_px=0,
        )

        self.assertEqual(coverage.state, EvidenceState.CONTRADICTED)
        self.assertEqual(coverage.uncovered_content, ((260, 320),))

    def test_overlapping_frame_slots_can_cover_visible_content(self) -> None:
        coverage = FrameCoverageEvidence(
            holder_long_axis_interval=(0, 310),
            frame_slot_intervals=((0, 160), (150, 310)),
            content_runs=((10, 300),),
            content_position_uncertainty_px=0,
        )

        self.assertEqual(coverage.state, EvidenceState.SUPPORTED)

    def test_one_dimensional_content_run_cannot_reject_internal_spacing(
        self,
    ) -> None:
        coverage = FrameCoverageEvidence(
            holder_long_axis_interval=(0, 310),
            frame_slot_intervals=((0, 150), (160, 310)),
            content_runs=((10, 300),),
            content_position_uncertainty_px=0,
        )

        self.assertEqual(coverage.state, EvidenceState.SUPPORTED)
        self.assertEqual(coverage.uncovered_content, ())

    def test_observed_separator_explains_internal_boundary(self) -> None:
        geometry = candidate_fixture().geometry
        coverage = FrameCoverageEvidence(
            (0, 310),
            ((0, 150), (160, 310)),
            ((0, 310),),
            0,
        )

        evidence = internal_frame_boundary_preservation_evidence(
            geometry.frame_slots,
            geometry.inter_frame_spacings,
            _content_continuity(crossing=True),
        )

        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_positive_spacing_hypothesis_cannot_justify_cutting_continuous_content(
        self,
    ) -> None:
        geometry = candidate_fixture().geometry
        spacing = InterFrameSpacing(
            InterFrameBoundaryReference(None, 1),
            PixelInterval.exact(10.0),
            _provenance("spacing_hypothesis"),
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )
        coverage = FrameCoverageEvidence(
            (0, 310),
            ((0, 150), (160, 310)),
            ((0, 310),),
            0,
        )

        evidence = internal_frame_boundary_preservation_evidence(
            geometry.frame_slots,
            (spacing,),
            _content_continuity(crossing=True),
        )

        self.assertEqual(evidence.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            evidence.observations[0].reason,
            "internal_boundary_cuts_continuous_content",
        )

    def test_geometry_hypothesis_without_crossing_remains_unavailable(self) -> None:
        geometry = candidate_fixture().geometry
        spacing = InterFrameSpacing(
            InterFrameBoundaryReference(None, 1),
            PixelInterval.exact(10.0),
            _provenance("spacing_hypothesis"),
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )
        coverage = FrameCoverageEvidence(
            (0, 310),
            ((0, 150), (160, 310)),
            ((10, 140), (170, 300)),
            0,
        )

        evidence = internal_frame_boundary_preservation_evidence(
            geometry.frame_slots,
            (spacing,),
            _content_continuity(crossing=False),
        )

        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            evidence.observations[0].reason,
            "internal_frame_boundary_preservation_unresolved",
        )

    def test_unresolved_spacing_hypothesis_cannot_justify_cutting_content(
        self,
    ) -> None:
        geometry = candidate_fixture().geometry
        spacing = InterFrameSpacing(
            InterFrameBoundaryReference(None, 1),
            PixelInterval(-5.0, 10.0),
            _provenance("unresolved_spacing_hypothesis"),
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )
        coverage = FrameCoverageEvidence(
            (0, 310),
            ((0, 150), (145, 310)),
            ((0, 310),),
            0,
        )

        evidence = internal_frame_boundary_preservation_evidence(
            geometry.frame_slots,
            (spacing,),
            _content_continuity(crossing=True),
        )

        self.assertEqual(evidence.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            evidence.observations[0].reason,
            "internal_boundary_cuts_continuous_content",
        )

    def test_independent_content_tracks_can_corroborate_measured_overlap(self) -> None:
        overlapped_left, overlapped_right = _measured_overlap_slots(
            width_pattern_roles=False,
        )
        spacing = InterFrameSpacing(
            InterFrameBoundaryReference(None, 1),
            PixelInterval.exact(-10.0),
            _provenance("overlap_hypothesis"),
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )

        evidence = internal_frame_boundary_preservation_evidence(
            (overlapped_left, overlapped_right),
            (spacing,),
            _content_continuity(crossing=True),
        )

        measured = evidence.observations[0].spacing_evidence
        self.assertEqual(measured.basis, InterFrameSpacingBasis.CORROBORATED_OVERLAP)
        self.assertTrue(measured.supports_output_protection)

    def test_content_cannot_corroborate_width_pattern_overlap(self) -> None:
        overlapped_left, overlapped_right = _measured_overlap_slots(
            width_pattern_roles=True,
        )
        spacing = InterFrameSpacing(
            InterFrameBoundaryReference(None, 1),
            PixelInterval.exact(-10.0),
            _provenance("width_pattern_overlap_hypothesis"),
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )

        evidence = internal_frame_boundary_preservation_evidence(
            (overlapped_left, overlapped_right),
            (spacing,),
            _content_continuity(crossing=True),
        )

        measured = evidence.observations[0].spacing_evidence
        self.assertEqual(
            measured.basis,
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )
        self.assertFalse(measured.supports_output_protection)

    def test_blank_boundary_crossing_is_identified_as_inferred_geometry(self) -> None:
        observation = ExternalFrameBoundaryObservation(
            frame_index=1,
            side=BoundarySide.LEADING,
            boundary_basis=FrameBoundarySource.SEQUENCE_INFERENCE,
            inside_region=Box(10, 0, 20, 20),
            outside_region=Box(0, 0, 10, 20),
            active_inside_pixels=20,
            active_outside_pixels=20,
            crossing_track_count=10,
            minimum_active_pixels=1,
            minimum_crossing_tracks=1,
            long_axis_content_spans_boundary=True,
        )

        self.assertEqual(observation.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            observation.reason,
            "continuous_content_crosses_inferred_frame_boundary",
        )

    def test_local_activation_without_content_run_does_not_prove_undercrop(
        self,
    ) -> None:
        observation = ExternalFrameBoundaryObservation(
            frame_index=1,
            side=BoundarySide.LEADING,
            boundary_basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            inside_region=Box(10, 0, 20, 20),
            outside_region=Box(0, 0, 10, 20),
            active_inside_pixels=20,
            active_outside_pixels=20,
            crossing_track_count=10,
            minimum_active_pixels=1,
            minimum_crossing_tracks=1,
            long_axis_content_spans_boundary=False,
        )

        self.assertFalse(observation.content_crossing_detected)
        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
