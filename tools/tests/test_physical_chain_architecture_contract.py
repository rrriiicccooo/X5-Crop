from __future__ import annotations

import inspect
import unittest

from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from x5crop.formats import FRAME_DIMENSION_TOLERANCE_SPEC, FramePhysicalSpec
from x5crop.detection.photo_geometry.chains import (
    LocalAdvanceKind,
    LocalAdvanceRelation,
)
from x5crop.detection.photo_geometry.observations import build_sequence_groups
from x5crop.detection.photo_geometry.selection import placement_local_advance_authorized
from x5crop.detection.photo_geometry.solver import (
    local_advance_delta_from_observed_gap,
    local_advance_prefix,
    materialize_lane_placements,
)
from x5crop.detection.photo_geometry.source_geometry import (
    JointAxisGeometry,
    LaneGapModel,
    SourceScanGeometry,
)


def _width_state() -> JointAxisGeometry:
    return JointAxisGeometry.create(
        axis_name="width",
        design_extent_mm=36.0,
        scale_interval_px_per_mm=PositiveInterval(10.0, 10.0),
        factor_interval=PositiveInterval(1.0, 1.0),
    )


def _edge(ordinal: int, position: float, name: str):
    return (
        ordinal,
        FiniteInterval.exact(position),
        (ObservationId(name),),
    )


class PhysicalChainArchitectureContractTest(unittest.TestCase):
    def test_fixed_frame_tolerances_are_source_shared(self) -> None:
        self.assertEqual(
            FRAME_DIMENSION_TOLERANCE_SPEC.frame_width_tolerance_ratio,
            0.0125,
        )
        self.assertEqual(
            FRAME_DIMENSION_TOLERANCE_SPEC.frame_height_tolerance_ratio,
            0.0040,
        )
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(36.0, 24.0, 2.0),
            width_scale_px_per_mm=PositiveInterval(9.9, 10.1),
            height_scale_px_per_mm=PositiveInterval(9.9, 10.1),
        )
        self.assertEqual(geometry.frame_spec.frame_spec_id.split(":", 1)[0], "frame-spec")
        self.assertFalse(hasattr(geometry, "lane_id"))

    def test_dual_lane_scale_evidence_intersects_at_source_level(self) -> None:
        frame = FramePhysicalSpec(36.0, 24.0, 2.0)
        first = SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=PositiveInterval(9.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(9.0, 10.0),
        )
        second = SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=PositiveInterval(9.5, 10.5),
            height_scale_px_per_mm=PositiveInterval(9.25, 10.25),
        )
        shared = first.intersect_source_state(second)
        self.assertEqual(
            shared.width_state.feasible_scale_interval(),
            PositiveInterval(9.5, 10.0),
        )
        self.assertEqual(
            shared.height_state.feasible_scale_interval(),
            PositiveInterval(9.25, 10.0),
        )
        self.assertFalse(hasattr(shared, "lane_id"))

    def test_gap_requires_two_compatible_pitch_segments(self) -> None:
        zero = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=(),
            format_gap_prior_mm=2.0,
        )
        one = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=((_edge(1, 0.0, "a"), _edge(2, 380.0, "b")),),
            format_gap_prior_mm=2.0,
        )
        two = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=((
                _edge(1, 0.0, "a"),
                _edge(2, 380.0, "b"),
                _edge(3, 760.0, "c"),
            ),),
            format_gap_prior_mm=2.0,
        )
        self.assertIsNone(zero.gap_interval_px)
        self.assertEqual(one.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(one.gap_interval_px, FiniteInterval.exact(20.0))
        self.assertEqual(two.state, EvidenceState.SUPPORTED)
        self.assertEqual(two.gap_interval_px, FiniteInterval.exact(20.0))

    def test_conflicting_pitch_segments_remain_unresolved(self) -> None:
        model = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=((
                _edge(1, 0.0, "a"),
                _edge(2, 380.0, "b"),
                _edge(3, 800.0, "c"),
            ),),
            format_gap_prior_mm=2.0,
        )
        self.assertEqual(model.state, EvidenceState.CONTRADICTED)
        self.assertIsNone(model.gap_interval_px)

    def test_120_one_pitch_does_not_borrow_a_format_prior(self) -> None:
        model = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=((_edge(1, 0.0, "a"), _edge(2, 380.0, "b")),),
            format_gap_prior_mm=None,
        )
        self.assertEqual(model.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(len(model.direct_gap_proposals_px), 1)

    def test_one_local_anomaly_moves_later_phase_once(self) -> None:
        relation = LocalAdvanceRelation(
            relation_ordinal=1,
            kind=LocalAdvanceKind.WIDE,
            delta_interval_px=FiniteInterval.exact(25.0),
            canonical_delta_px=25.0,
            observation_ids=(ObservationId("wide-gap"),),
        )
        self.assertEqual(local_advance_prefix((relation,), lane_ordinal=1)[1], 0.0)
        self.assertEqual(local_advance_prefix((relation,), lane_ordinal=2)[1], 25.0)
        self.assertEqual(local_advance_prefix((relation,), lane_ordinal=3)[1], 25.0)

    def test_contact_overlap_and_large_gap_have_no_fixed_gap_window(self) -> None:
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(36.0, 24.0, 2.0),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        gap_model = LaneGapModel.from_ordinal_edges(
            geometry.width_state,
            lane_id="lane:test",
            edge_families=(),
            format_gap_prior_mm=2.0,
        )
        contact = local_advance_delta_from_observed_gap(
            FiniteInterval.exact(0.0), geometry, gap_model
        )
        overlap = local_advance_delta_from_observed_gap(
            FiniteInterval.exact(-20.0), geometry, gap_model
        )
        wide = local_advance_delta_from_observed_gap(
            FiniteInterval.exact(200.0), geometry, gap_model
        )
        self.assertIsNotNone(contact)
        self.assertIsNotNone(overlap)
        self.assertIsNotNone(wide)

    def test_complete_chain_materializer_has_no_first_n_truncation(self) -> None:
        source = inspect.getsource(materialize_lane_placements)
        self.assertNotIn("top", source.lower())
        self.assertNotIn("[:MAX_", source)

    def test_empty_phase_input_creates_no_evidence(self) -> None:
        groups, work = build_sequence_groups((), ())
        self.assertEqual(groups, ())
        self.assertEqual(work.ordinal_role_lookup_count, 0)
        self.assertEqual(work.ordinal_role_match_count, 0)

    def test_local_advance_authority_is_a_hard_chain_fact(self) -> None:
        source = inspect.getsource(placement_local_advance_authorized)
        self.assertIn("lane_gap_model.state == EvidenceState.SUPPORTED", source)
        self.assertIn("observed_roles", source)


if __name__ == "__main__":
    unittest.main()
