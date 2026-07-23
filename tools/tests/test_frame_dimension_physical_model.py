from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.physical.frame_dimensions import (
    FrameDimensionEvidence,
    frame_dimension_evidence,
    frame_dimension_priors,
    frame_dimension_search_priors,
)
from x5crop.detection.physical.short_axis import SharedShortAxisOutcome
from x5crop.domain import EvidenceState, PixelInterval
from x5crop.formats import FORMATS


class FrameDimensionPhysicalModelTest(unittest.TestCase):
    def test_frame_dimension_priors_derive_only_from_physical_specs(self) -> None:
        for physical_spec in FORMATS.values():
            with self.subTest(format_id=physical_spec.format_id):
                priors = frame_dimension_priors(physical_spec)
                self.assertEqual(
                    tuple(prior.frame_size_mm for prior in priors),
                    tuple(
                        (float(option.width_mm), float(option.height_mm))
                        for option in physical_spec.frame.frame_size_mm_options
                    ),
                )

    def test_geometry_search_requires_photo_edge_size_binding(self) -> None:
        self.assertEqual(
            frame_dimension_search_priors(FORMATS["120-66"], None),
            (),
        )

        selected = frame_dimension_search_priors(
            FORMATS["120-66"],
            FORMATS["120-66"].frame.frame_size_mm_options[1],
        )
        self.assertEqual(
            tuple(prior.frame_size_mm for prior in selected),
            ((56.0, 56.0),),
        )
        self.assertEqual(
            tuple(
                prior.frame_size_mm
                for prior in frame_dimension_search_priors(
                    FORMATS["135"],
                    None,
                )
            ),
            ((36.0, 24.0),),
        )

    def test_separator_width_variation_does_not_contradict_frame_dimensions(
        self,
    ) -> None:
        evidence = FrameDimensionEvidence(
            frame_width_mm=36.0,
            frame_height_mm=24.0,
            common_width_px=PixelInterval(99.0, 101.0),
            measured_width_intervals_px=(
                PixelInterval(99.5, 100.5),
                PixelInterval(100.0, 101.0),
                PixelInterval(99.0, 100.0),
            ),
            separator_widths_px=(2.0, 18.0),
            common_width_state=EvidenceState.SUPPORTED,
            observed_aspect=1.5,
            expected_width_px=None,
            expected_height_px=None,
            observed_height_px=PixelInterval(99.0, 101.0),
        )

        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)
        self.assertIsNotNone(evidence.separator_width_cv)

    def test_unresolved_short_axis_has_no_photo_height(self) -> None:
        candidate = candidate_fixture()
        geometry_value = candidate.geometry
        short_axis = geometry_value.shared_short_axis
        unresolved = replace(
            short_axis,
            span=None,
            outcome=SharedShortAxisOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE,
            position_uncertainty_px=None,
        )

        evidence = frame_dimension_evidence(
            SimpleNamespace(
                frame_dimension_prior=geometry_value.frame_dimension_prior,
                common_frame_width=geometry_value.common_frame_width,
                shared_short_axis=unresolved,
                separator_assignments=geometry_value.separator_assignments,
            ),
            None,
            None,
        )

        self.assertIsNone(evidence.observed_aspect)


if __name__ == "__main__":
    unittest.main()
