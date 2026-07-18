from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from x5crop.detection.physical import (
    frame_sequence_common_width as width_resolution,
)
from x5crop.detection.physical import (
    frame_sequence_measurements as measurement_facts,
)
from x5crop.detection.physical.frame_sequence_common_width import (
    CommonWidthHypothesis,
    measured_constraint_common_width,
    non_dominated_width_hypotheses,
    strict_majority_width_consensus,
)
from x5crop.detection.physical.frame_sequence_measurements import (
    largest_strict_intersection_indexes,
)
from x5crop.domain import (
    BoundarySide,
    EvidenceState,
    ObservationId,
    PixelInterval,
)


class FrameSequenceCommonWidthContractTest(unittest.TestCase):
    def test_measured_common_width_precedes_search_hint(self) -> None:
        measured = CommonWidthHypothesis(
            width_px=PixelInterval(100.0, 102.0),
            boundary_anchors=(ObservationId("measured_common_width"),),
            contributor_count=2,
        )
        hint = PixelInterval(110.0, 125.0)

        branches = width_resolution.dimension_placement_hypotheses(
            (measured,),
            (),
            (hint,),
            None,
        )

        self.assertEqual(branches[0].width_px, measured.width_px)
        self.assertEqual(branches[0].boundary_anchors, measured.boundary_anchors)
        self.assertEqual(branches[-1].width_px, hint)
        self.assertEqual(branches[-1].boundary_anchors, ())

    def test_recurring_boundary_width_precedes_search_hint(self) -> None:
        recurring = width_resolution.RecurringBoundaryWidthHypothesis(
            width_px=PixelInterval(100.0, 102.0),
            contributor_count=4,
        )
        hint = PixelInterval(110.0, 125.0)

        branches = width_resolution.dimension_placement_hypotheses(
            (),
            (recurring,),
            (hint,),
            None,
        )

        self.assertEqual(branches[0].width_px, recurring.width_px)
        self.assertEqual(branches[0].repeated_slot_count, 4)
        self.assertEqual(branches[-1].width_px, hint)
        self.assertEqual(branches[-1].repeated_slot_count, 0)

    def test_dominated_recurring_widths_share_one_search_branch(self) -> None:
        stronger = width_resolution.RecurringBoundaryWidthHypothesis(
            PixelInterval(100.0, 104.0),
            4,
        )
        weaker_overlap = width_resolution.RecurringBoundaryWidthHypothesis(
            PixelInterval(99.0, 105.0),
            3,
        )
        distinct = width_resolution.RecurringBoundaryWidthHypothesis(
            PixelInterval(120.0, 122.0),
            2,
        )

        branches = width_resolution.dimension_placement_hypotheses(
            (),
            (weaker_overlap, distinct, stronger),
            (),
            None,
        )

        self.assertEqual(
            tuple(
                (branch.width_px, branch.repeated_slot_count)
                for branch in branches
            ),
            (
                (stronger.width_px, stronger.contributor_count),
                (distinct.width_px, distinct.contributor_count),
            ),
        )

    def test_edge_overlapping_recurring_widths_remain_distinct(self) -> None:
        first = width_resolution.RecurringBoundaryWidthHypothesis(
            PixelInterval(3141.0, 3182.0),
            5,
        )
        second = width_resolution.RecurringBoundaryWidthHypothesis(
            PixelInterval(3101.0, 3143.0),
            5,
        )

        branches = width_resolution.dimension_placement_hypotheses(
            (),
            (first, second),
            (),
            None,
        )

        self.assertEqual(
            tuple(branch.width_px for branch in branches),
            (first.width_px, second.width_px),
        )

    def test_repeated_width_compatibility_is_materialized_once(self) -> None:
        def edge(position: float, identity: str) -> SimpleNamespace:
            return SimpleNamespace(
                position=PixelInterval.exact(position),
                provenance=SimpleNamespace(
                    observation_id=ObservationId(identity),
                ),
            )

        constraints = (
            SimpleNamespace(
                leading=edge(0.0, "leading_1"),
                trailing=edge(100.0, "trailing_1"),
                width_px=PixelInterval(98.0, 102.0),
            ),
            SimpleNamespace(
                leading=edge(110.0, "leading_2"),
                trailing=edge(211.0, "trailing_2"),
                width_px=PixelInterval(99.0, 103.0),
            ),
            SimpleNamespace(
                leading=edge(220.0, "leading_3"),
                trailing=edge(320.0, "trailing_3"),
                width_px=PixelInterval(97.0, 101.0),
            ),
        )
        compatibility = width_resolution.width_compatibility_matrix

        with patch.object(
            width_resolution,
            "width_compatibility_matrix",
            wraps=compatibility,
        ) as materialize:
            contributors = width_resolution.repeated_width_contributor_sets(
                constraints,
                2,
            )

        self.assertTrue(contributors)
        materialize.assert_called_once()

    def test_broad_uncertainty_cannot_bridge_disjoint_narrow_groups(self) -> None:
        constraints = tuple(
            SimpleNamespace(
                width_px=interval,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
            )
            for interval in (
                PixelInterval(95.0, 100.0),
                PixelInterval(90.0, 120.0),
                PixelInterval(110.0, 115.0),
            )
        )

        self.assertIsNone(measured_constraint_common_width(constraints, 3))

    def test_non_dominated_widths_preserve_disjoint_measurements(self) -> None:
        measured_width = CommonWidthHypothesis(
            PixelInterval(100.0, 110.0),
            (ObservationId("measured-a"), ObservationId("measured-b")),
            4,
        )
        weaker_overlapping_width = CommonWidthHypothesis(
            PixelInterval(102.0, 108.0),
            (ObservationId("measured-c"), ObservationId("measured-d")),
            2,
        )
        disjoint_width = CommonWidthHypothesis(
            PixelInterval(200.0, 210.0),
            (ObservationId("measured-e"), ObservationId("measured-f")),
            3,
        )

        self.assertEqual(
            non_dominated_width_hypotheses(
                (
                    measured_width,
                    weaker_overlapping_width,
                    disjoint_width,
                )
            ),
            (measured_width, disjoint_width),
        )

    def test_disjoint_exact_widths_have_no_strict_intersection(self) -> None:
        measurements = (
            PixelInterval.exact(100.0),
            PixelInterval.exact(102.0),
        )

        self.assertEqual(
            largest_strict_intersection_indexes(measurements, 2),
            (),
        )

    def test_search_width_majority_requires_a_real_shared_interval(self) -> None:
        measurements = (
            PixelInterval(90.0, 110.0),
            PixelInterval(111.0, 131.0),
            PixelInterval(132.0, 152.0),
        )

        self.assertIsNone(strict_majority_width_consensus(measurements))

    def test_holder_clipping_can_explain_one_underwidth_end_slot(self) -> None:
        slot = SimpleNamespace(
            width_px=PixelInterval.exact(40.0),
            leading=SimpleNamespace(
                position=PixelInterval.exact(10.0),
                independently_observed=False,
            ),
            trailing=SimpleNamespace(
                position=PixelInterval.exact(50.0),
                independently_observed=True,
            ),
        )
        holder_boundaries = {
            BoundarySide.LEADING: SimpleNamespace(
                position=PixelInterval.exact(10.0),
            ),
        }
        common_width = SimpleNamespace(
            state=EvidenceState.SUPPORTED,
            width_px=PixelInterval.exact(100.0),
        )

        with patch.object(
            measurement_facts,
            "boundary_matches_holder",
            return_value=True,
        ):
            compatible = (
                width_resolution.slots_do_not_contradict_supported_common_width(
                    (slot,),
                    holder_boundaries,
                    common_width,
                )
            )

        self.assertTrue(compatible)


if __name__ == "__main__":
    unittest.main()
