from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from x5crop.detection.photo_geometry.model import BoundaryAxis
from x5crop.detection.photo_geometry.transition_peak_source import (
    TRANSITION_PEAK_SOURCE_BASIS,
    TransitionPeakGroupSource,
    TransitionPeakReference,
    TransitionPeakTraceSource,
    same_transition_peak,
)
from x5crop.domain import WorkspaceExtent


class TransitionPeakSourceContractTest(unittest.TestCase):
    def _source(self, **changes) -> TransitionPeakTraceSource:
        values = dict(
            source_id="field:1",
            source_extent=WorkspaceExtent(width=32, height=48),
            boundary_axis=BoundaryAxis.Y,
            trace_coordinate_px=9,
            normalization_domain_px=(5, 42),
            window_px=3,
            gap_px=2,
            gradient_z_minimum=3.0,
            tone_or_texture_z_minimum=3.0,
            signal_sha256="a" * 64,
        )
        values.update(changes)
        return TransitionPeakTraceSource(**values)

    def _gradient_group(self, source=None, **changes) -> TransitionPeakGroupSource:
        values = dict(
            source=source or self._source(),
            measurement_domain_px=(7, 40),
            credible_group_domain_px=(12, 35),
            reliable_gradient_partitions=(
                (1, (12, 13, 16)),
                (-1, (20, 21, 35)),
            ),
            candidate_peak_coordinates_px=(13, 20),
            selection_basis="gradient",
            split_gradient_reversals=True,
        )
        values.update(changes)
        return TransitionPeakGroupSource(**values)

    def test_complete_group_and_different_complete_views_share_absolute_peak(self) -> None:
        left = self._gradient_group(measurement_domain_px=(7, 40))
        right = self._gradient_group(measurement_domain_px=(8, 39))
        self.assertTrue(left.complete)
        self.assertTrue(right.complete)
        self.assertEqual(left.primitive_key, right.primitive_key)
        self.assertEqual(left.primitive_id, right.primitive_id)
        left_ref = TransitionPeakReference(left.primitive_id, 0, 13, 1)
        right_ref = TransitionPeakReference(right.primitive_id, 0, 13, 1)
        self.assertTrue(same_transition_peak(left_ref, left, right_ref, right))

    def test_group_touching_measurement_view_boundary_is_not_complete(self) -> None:
        touching = self._gradient_group(
            credible_group_domain_px=(7, 35),
            candidate_peak_coordinates_px=(13, 20),
        )
        complete = self._gradient_group()
        touching_ref = TransitionPeakReference(touching.primitive_id, 0, 13, 1)
        complete_ref = TransitionPeakReference(complete.primitive_id, 0, 13, 1)
        self.assertFalse(touching.complete)
        self.assertFalse(
            same_transition_peak(touching_ref, touching, complete_ref, complete)
        )

    def test_every_trace_source_identity_field_separates_groups(self) -> None:
        variants = (
            {"source_id": "field:2"},
            {"source_extent": WorkspaceExtent(width=33, height=48)},
            {
                "source_extent": WorkspaceExtent(width=48, height=32),
                "boundary_axis": BoundaryAxis.X,
            },
            {"trace_coordinate_px": 10},
            {"normalization_domain_px": (6, 41)},
            {"window_px": 4, "normalization_domain_px": (6, 41)},
            {"gap_px": 3, "normalization_domain_px": (6, 41)},
            {"gradient_z_minimum": 4.0},
            {"tone_or_texture_z_minimum": 4.0},
            {"signal_sha256": "b" * 64},
        )
        baseline = self._gradient_group()
        baseline_ref = TransitionPeakReference(baseline.primitive_id, 0, 13, 1)
        for changes in variants:
            with self.subTest(changes=changes):
                candidate = self._gradient_group(source=self._source(**changes))
                candidate_ref = TransitionPeakReference(
                    candidate.primitive_id,
                    0,
                    13,
                    1,
                )
                self.assertNotEqual(baseline.primitive_key, candidate.primitive_key)
                self.assertFalse(
                    same_transition_peak(
                        baseline_ref,
                        baseline,
                        candidate_ref,
                        candidate,
                    )
                )

    def test_split_and_unsplit_multi_polarity_groups_are_distinct(self) -> None:
        split = self._gradient_group()
        unsplit = self._gradient_group(
            candidate_peak_coordinates_px=(13,),
            split_gradient_reversals=False,
        )
        split_ref = TransitionPeakReference(split.primitive_id, 0, 13, 1)
        unsplit_ref = TransitionPeakReference(unsplit.primitive_id, 0, 13, 1)
        self.assertNotEqual(split.primitive_key, unsplit.primitive_key)
        self.assertFalse(same_transition_peak(split_ref, split, unsplit_ref, unsplit))

    def test_split_gradient_candidates_follow_ordered_runs(self) -> None:
        group = self._gradient_group(
            reliable_gradient_partitions=(
                (1, (12, 13)),
                (-1, (20, 21)),
                (1, (30, 31)),
            ),
            candidate_peak_coordinates_px=(13, 20, 30),
        )
        self.assertEqual(group.candidate_peak_coordinates_px, (13, 20, 30))
        with self.assertRaises(ValueError):
            self._gradient_group(
                reliable_gradient_partitions=(
                    (1, (12, 13)),
                    (-1, (20, 21)),
                    (1, (30, 31)),
                ),
                candidate_peak_coordinates_px=(13, 21, 32),
            )

    def test_secondary_group_cannot_invent_gradient_sign(self) -> None:
        secondary = TransitionPeakGroupSource(
            source=self._source(),
            measurement_domain_px=(7, 40),
            credible_group_domain_px=(12, 35),
            reliable_gradient_partitions=(),
            candidate_peak_coordinates_px=(18,),
            selection_basis="secondary",
            split_gradient_reversals=False,
        )
        valid = TransitionPeakReference(secondary.primitive_id, 0, 18, 0)
        valid.validate_group(secondary)
        forged = TransitionPeakReference(secondary.primitive_id, 0, 18, 1)
        with self.assertRaises(ValueError):
            forged.validate_group(secondary)

    def test_forged_candidate_ordinal_coordinate_sign_and_group_id_are_rejected(self) -> None:
        group = self._gradient_group()
        forged_values = (
            TransitionPeakReference(group.primitive_id, 0, 20, 1),
            TransitionPeakReference(group.primitive_id, 1, 13, 1),
            TransitionPeakReference(group.primitive_id, 0, 13, -1),
            TransitionPeakReference("native-peak-group:" + "0" * 64, 0, 13, 1),
        )
        for forged in forged_values:
            with self.subTest(forged=forged):
                with self.assertRaises(ValueError):
                    forged.validate_group(group)
        with self.assertRaises(ValueError):
            TransitionPeakReference(group.primitive_id, 2, 13, 1).validate_group(group)

    def test_negative_reference_fields_are_rejected_at_construction(self) -> None:
        group = self._gradient_group()
        with self.assertRaises(ValueError):
            TransitionPeakReference(group.primitive_id, -1, 13, 1)
        with self.assertRaises(ValueError):
            TransitionPeakReference(group.primitive_id, 0, -1, 1)

    def test_strict_types_and_frozen_records(self) -> None:
        with self.assertRaises(TypeError):
            self._source(trace_coordinate_px=True)
        with self.assertRaises(TypeError):
            self._source(normalization_domain_px=[5, 42])
        with self.assertRaises(TypeError):
            self._source(gradient_z_minimum=3)
        with self.assertRaises(TypeError):
            self._source(window_px=False)
        with self.assertRaises(ValueError):
            self._source(basis="other-basis")
        self.assertEqual(TRANSITION_PEAK_SOURCE_BASIS, "registered-u8-peak-source-v1")
        source = self._source()
        with self.assertRaises(FrozenInstanceError):
            source.source_id = "field:2"

    def test_kernel_domain_bytes_and_visit_receipts_are_exact(self) -> None:
        source = self._source(normalization_domain_px=(5, 42))
        self.assertEqual(source.normalization_coordinate_count, 38)
        self.assertEqual(source.retained_bytes, 1024)
        self.assertEqual(source.signal_value_visit_count, 190)
        group = self._gradient_group(source=source)
        run_coordinate_count = 3 + 3
        candidate_count = 2
        group_coordinate_count = 35 - 12 + 1
        self.assertEqual(
            group.retained_bytes,
            2048 + 256 * (run_coordinate_count + candidate_count),
        )
        self.assertEqual(
            group.logical_value_visit_count,
            32 + 8 * (group_coordinate_count + run_coordinate_count + candidate_count),
        )
        self.assertEqual(group.primitive_id, group.primitive_id)
        self.assertEqual(
            TransitionPeakReference(group.primitive_id, 0, 13, 1).retained_bytes,
            512,
        )


if __name__ == "__main__":
    unittest.main()
