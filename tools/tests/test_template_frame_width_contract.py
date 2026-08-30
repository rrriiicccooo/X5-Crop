from __future__ import annotations

import unittest

from tools.tests.template_test_support import (
    phase_edge,
    phase_template,
    placement_sequence,
    placement_template,
)
from x5crop.detection.photo_geometry.template_frame_width import (
    apply_correlated_frame_width_inference,
    calibrate_source_frame_width,
)
from x5crop.detection.photo_geometry.template_model import (
    FrameWidthInferenceFailureKind,
)
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_model import PhaseFitStatus
from x5crop.formats import FramePhysicalSpec


class TemplateFrameWidthContractTest(unittest.TestCase):
    def test_non_adjacent_direct_frames_close_one_source_width_hull(self) -> None:
        observations = (
            phase_edge("frame-1-start", 40.0),
            phase_edge("frame-1-end", 139.0),
            phase_edge("frame-3-start", 280.0),
            phase_edge("frame-3-end", 381.0),
        )
        phase = fit_template_phase(observations, phase_template(3))
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        calibrated = calibrate_source_frame_width(
            source,
            phase,
            observations,
            holder_span_px=FiniteInterval(0.0, 400.0),
        )

        width = calibrated.width_state.extent_projection_px()
        self.assertLessEqual(width.minimum, 99.0)
        self.assertGreaterEqual(width.maximum, 101.0)
        self.assertEqual(len(calibrated.width_state.observation_ids), 4)

    def test_one_source_width_authority_infers_multiple_opposite_roles(self) -> None:
        template = placement_template(4)
        fit = placement_sequence(template, missing=(5, 7))
        authority_ids = tuple(
            ObservationId(f"sequence:{index}") for index in range(4)
        )

        assessed = apply_correlated_frame_width_inference(
            fit,
            frame_width_observation_ids=authority_ids,
        )

        inference = assessed.frame_width_inference
        self.assertIsNotNone(inference)
        assert inference is not None
        self.assertEqual(inference.state, EvidenceState.SUPPORTED)
        self.assertEqual(inference.inferred_role_indices, (5, 7))
        self.assertEqual(inference.supporting_frame_ordinals, (1, 2))
        self.assertEqual(inference.observation_ids, authority_ids)
        self.assertEqual(
            inference.width_px,
            fit.pitch_fit.frame_width_px,
        )
        self.assertEqual(assessed.pitch_fit, fit.pitch_fit)

    def test_grid_cannot_create_a_frame_with_both_roles_unobserved(self) -> None:
        template = placement_template(3)
        fit = placement_sequence(template, missing=(4, 5))

        assessed = apply_correlated_frame_width_inference(
            fit,
            frame_width_observation_ids=tuple(
                ObservationId(f"sequence:{index}") for index in range(4)
            ),
        )

        inference = assessed.frame_width_inference
        self.assertIsNotNone(inference)
        assert inference is not None
        self.assertEqual(inference.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            inference.failure_kind,
            FrameWidthInferenceFailureKind.COMPLETE_FRAME_UNOBSERVED,
        )

    def test_one_complete_frame_cannot_claim_source_common_width(self) -> None:
        template = placement_template(2)
        fit = placement_sequence(template, missing=(3,))

        assessed = apply_correlated_frame_width_inference(
            fit,
            frame_width_observation_ids=(
                ObservationId("sequence:0"),
                ObservationId("sequence:1"),
            ),
        )

        inference = assessed.frame_width_inference
        self.assertIsNotNone(inference)
        assert inference is not None
        self.assertEqual(inference.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            inference.failure_kind,
            FrameWidthInferenceFailureKind.COMMON_WIDTH_AUTHORITY_UNAVAILABLE,
        )


if __name__ == "__main__":
    unittest.main()
