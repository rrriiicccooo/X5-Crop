from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.frame_slot_solver_support import (
    content,
    dimensions,
    geometry,
    separator,
    sequence_search_index,
    scope,
)
from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.evidence.frame_scale import (
    FrameScaleSource,
    frame_scale_observations,
)
from x5crop.detection.physical.frame_dimensions import (
    FrameDimensionEvidence,
    frame_dimension_evidence,
    frame_dimension_priors,
)
from x5crop.detection.physical.frame_sequence_solver import (
    FrameSequenceSolveResult,
    solve_frame_sequence,
)
from x5crop.detection.physical.model import (
    PhotoHeightEvidence,
    SharedShortAxisBasis,
    SharedShortAxisSafetySpan,
)
from x5crop.detection.physical.short_axis import shared_short_axis_plan
from x5crop.domain import BoundarySide, EvidenceState, PixelInterval
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

    def test_separator_width_variation_does_not_contradict_frame_dimensions(self) -> None:
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
        )

        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)
        self.assertIsNotNone(evidence.separator_width_cv)

    def test_holder_bounded_short_axis_is_not_photo_height_evidence(self) -> None:
        candidate = candidate_fixture()
        geometry_value = candidate.geometry
        short_axis = geometry_value.shared_short_axis
        holder_bounded = SharedShortAxisSafetySpan(
            top=short_axis.top,
            bottom=short_axis.bottom,
            basis=SharedShortAxisBasis.HOLDER_EDGE_BOUNDED,
            state=EvidenceState.SUPPORTED,
            provenance=short_axis.provenance,
        )

        evidence = frame_dimension_evidence(
            replace(
                geometry_value,
                shared_short_axis=holder_bounded,
                photo_height_evidence=PhotoHeightEvidence(
                    None,
                    EvidenceState.UNAVAILABLE,
                    holder_bounded.provenance,
                ),
            )
        )

        self.assertIsNone(evidence.observed_aspect)

    def test_blank_slot_is_excluded_from_scale_measurements(self) -> None:
        search_scope = scope(
            width=660,
            height=120,
            leading=0.0,
            trailing=540.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(
                100.0,
                110.0,
                210.0,
                220.0,
                320.0,
                330.0,
                430.0,
                440.0,
            ),
            holder_sides=(
                BoundarySide.LEADING,
                BoundarySide.TRAILING,
                BoundarySide.TOP,
                BoundarySide.BOTTOM,
            ),
            holder_positions={
                BoundarySide.LEADING: 0.0,
                BoundarySide.TRAILING: 660.0,
                BoundarySide.TOP: 0.0,
                BoundarySide.BOTTOM: 120.0,
            },
        )
        visible_content = content(
            width=660,
            height=120,
            runs=((0, 100), (110, 210), (220, 320), (330, 430), (440, 540)),
        )
        prior = dimensions(1.0, 1.0)
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in ((100, 110), (210, 220), (320, 330), (430, 440))
        )
        solved = solve_frame_sequence(
            sequence_search_index(search_scope, supports),
            search_scope,
            plan,
            6,
            prior,
            visible_content,
            100_000,
            strip_mode="full",
            nominal_count=6,
        )
        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        sequence = geometry(
            search_scope,
            supports,
            prior,
            solved,
            nominal_count=6,
        )

        observations = frame_scale_observations(sequence)

        width_observations = tuple(
            item
            for item in observations
            if item.source == FrameScaleSource.FRAME_WIDTH_INTERVAL
        )
        self.assertEqual(sequence.sequence_inferred_frame_indexes, (6,))
        self.assertEqual(
            tuple(
                str(item.provenance.observation_id)
                for item in width_observations
            ),
            tuple(f"frame_width_scale:{index}" for index in range(2, 6)),
        )
        self.assertNotIn(
            "frame_width_scale:6",
            tuple(
                str(item.provenance.observation_id)
                for item in width_observations
            ),
        )

    def test_frame_scale_is_evidence_output_not_geometry_input(self) -> None:
        source = frame_scale_observations.__module__

        self.assertEqual(source, "x5crop.detection.evidence.frame_scale")


if __name__ == "__main__":
    unittest.main()
