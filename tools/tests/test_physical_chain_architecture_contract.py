from __future__ import annotations

import inspect
from types import SimpleNamespace
import unittest

from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from x5crop.configuration.model import HolderLayoutAuthority
from x5crop.formats import FRAME_DIMENSION_TOLERANCE_SPEC, FramePhysicalSpec
from x5crop.detection.photo_geometry.chain_authority import (
    placement_local_advance_authorized,
)
from x5crop.detection.photo_geometry.sequence_models import (
    LocalAdvanceKind,
    LocalAdvanceRelation,
    SequenceDiscoveryKind,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.observation_types import (
    BasicAxisProfile,
    OrdinalBoundaryRole,
    ProfileRun,
    SeparatorBandRoleProposal,
    SequenceRoleProposal,
)
from x5crop.detection.photo_geometry.sequence_separator_seeds import (
    direct_separator_groups,
)
from x5crop.detection.photo_geometry.sequence_role_proposals import (
    build_sequence_role_proposals,
    role_canonical_relative,
    role_relative_projection,
)
from x5crop.detection.photo_geometry.sequence_grouping import build_sequence_groups
from x5crop.detection.photo_geometry.chain_records import complete_chain_record
from x5crop.detection.photo_geometry.detector import reconstruct_photo_geometry
from x5crop.detection.photo_geometry.selected_source_output import (
    resolve_selected_source_output,
)
from x5crop.detection.photo_geometry.local_advance import (
    local_advance_delta_from_observed_gap,
    merge_local_advance_relations,
)
from x5crop.detection.photo_geometry.edge_family_identity import (
    disjoint_family_pairs,
)
from x5crop.detection.photo_geometry.holder_layout_authority import (
    long_axis_fill_authority,
)
from x5crop.detection.photo_geometry.source_chain_materialization import (
    materialize_lane_placements,
    materialize_source_placements,
)
from x5crop.detection.photo_geometry.cross_placement import (
    materialize_cross_placement,
)
from x5crop.detection.photo_geometry.joint_axis_geometry import (
    JointAxisGeometry,
)
from x5crop.detection.photo_geometry.lane_gap_model import LaneGapModel
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry


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
    def test_format_gap_prior_never_changes_role_or_phase_coordinates(self) -> None:
        role = OrdinalBoundaryRole(4, 3, BoundaryRole.START)
        width_state = _width_state()
        with_prior = FramePhysicalSpec(36.0, 24.0, 2.0)
        without_prior = FramePhysicalSpec(36.0, 24.0, None)

        self.assertEqual(
            role_relative_projection(role, with_prior, width_state),
            FiniteInterval.exact(720.0),
        )
        self.assertEqual(
            role_relative_projection(role, with_prior, width_state),
            role_relative_projection(role, without_prior, width_state),
        )
        self.assertEqual(
            role_canonical_relative(role, with_prior, width_state),
            role_canonical_relative(role, without_prior, width_state),
        )

    def test_profile_run_without_edge_observation_cannot_create_phase(self) -> None:
        run = ProfileRun(
            run_id="ambiguous-run",
            coordinate_interval_px=FiniteInterval.exact(100.0),
            transition_ids=(ObservationId("transition:ambiguous"),),
            trace_coordinates_px=(0, 50, 100),
            role_hint=None,
            qualified_anchor_roles=(BoundaryRole.START,),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            evidence_strength=10.0,
            pair_qualified=True,
        )
        lane = SimpleNamespace(
            sequence_profile=BasicAxisProfile(
                "sequence",
                1000,
                (0, 50, 100),
                (run,),
            ),
            sequence_edges=(),
            separator_bands=(),
        )
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(36.0, 24.0, 2.0),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        proposals = build_sequence_role_proposals(
            lane,
            geometry,
            (
                OrdinalBoundaryRole(0, 1, BoundaryRole.START),
                OrdinalBoundaryRole(1, 1, BoundaryRole.END),
            ),
            discovery_kind=SequenceDiscoveryKind.DIRECT_EXCEPTION,
        )

        self.assertEqual(proposals, ())

    def test_separated_segments_may_prove_one_common_physical_line(self) -> None:
        pairs = disjoint_family_pairs(
            (
                FiniteInterval(0.0, 20.0),
                FiniteInterval(40.0, 60.0),
                FiniteInterval(80.0, 100.0),
            ),
        )
        self.assertEqual(pairs, ((0, 1), (0, 2), (1, 2)))

    def test_conflicting_anomaly_kinds_remain_unclassified(self) -> None:
        left = LocalAdvanceRelation(
            relation_ordinal=1,
            kind=LocalAdvanceKind.WIDE,
            delta_interval_px=FiniteInterval(-1.0, 2.0),
            canonical_delta_px=0.5,
            observation_ids=(ObservationId("wide"),),
        )
        right = LocalAdvanceRelation(
            relation_ordinal=1,
            kind=LocalAdvanceKind.NARROW,
            delta_interval_px=FiniteInterval(-2.0, 1.0),
            canonical_delta_px=-0.5,
            observation_ids=(ObservationId("narrow"),),
        )

        merged = merge_local_advance_relations((left,), (right,))[0]

        self.assertEqual(merged.kind, LocalAdvanceKind.OBSERVED_UNCLASSIFIED)
        self.assertEqual(merged.delta_interval_px, FiniteInterval(-1.0, 1.0))

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
            PositiveInterval(9.5, 10.0),
        )
        self.assertFalse(hasattr(shared, "lane_id"))

    def test_observed_width_does_not_recalibrate_source_height(self) -> None:
        frame = FramePhysicalSpec(70.0, 56.0, None)
        geometry = SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=PositiveInterval(64.0, 69.0),
            height_scale_px_per_mm=PositiveInterval(64.0, 69.0),
        )
        original_height = geometry.height_state.extent_projection_px()
        narrowed_width = geometry.width_state.intersect_observed_extent(
            FiniteInterval(4520.0, 4560.0),
            observation_ids=(ObservationId("observed-width"),),
        )

        refined = SourceScanGeometry.from_axis_states(
            frame,
            narrowed_width,
            geometry.height_state,
        )

        self.assertEqual(
            refined.height_state.extent_projection_px(),
            original_height,
        )
        self.assertNotEqual(
            refined.width_state.extent_projection_px(),
            geometry.width_state.extent_projection_px(),
        )

    def test_gap_requires_two_compatible_pitch_segments(self) -> None:
        zero = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=(),
            direct_separator_gaps=(),
        )
        one = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=((_edge(1, 0.0, "a"), _edge(2, 380.0, "b")),),
            direct_separator_gaps=(),
        )
        two = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=((
                _edge(1, 0.0, "a"),
                _edge(2, 380.0, "b"),
                _edge(3, 760.0, "c"),
            ),),
            direct_separator_gaps=(),
        )
        self.assertIsNone(zero.gap_interval_px)
        self.assertIsNone(zero.placement_pitch_interval_px)
        self.assertIsNone(zero.canonical_placement_pitch_px)
        self.assertEqual(one.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(one.gap_interval_px, FiniteInterval.exact(20.0))
        self.assertIsNone(one.placement_pitch_interval_px)
        self.assertEqual(two.state, EvidenceState.SUPPORTED)
        self.assertEqual(two.gap_interval_px, FiniteInterval.exact(20.0))
        self.assertEqual(
            two.placement_pitch_interval_px,
            FiniteInterval.exact(380.0),
        )

    def test_conflicting_pitch_segments_remain_unresolved(self) -> None:
        model = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=((
                _edge(1, 0.0, "a"),
                _edge(2, 380.0, "b"),
                _edge(3, 800.0, "c"),
            ),),
            direct_separator_gaps=(),
        )
        self.assertEqual(model.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(model.gap_interval_px)

    def test_unique_repeated_normal_gaps_leave_direct_outlier_local(self) -> None:
        model = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=(),
            direct_separator_gaps=(
                (FiniteInterval(18.0, 22.0), ObservationId("normal-a")),
                (FiniteInterval(19.0, 23.0), ObservationId("normal-b")),
                (FiniteInterval(17.0, 21.0), ObservationId("normal-c")),
                (FiniteInterval(-2.0, 2.0), ObservationId("contact")),
            ),
        )
        self.assertEqual(model.state, EvidenceState.SUPPORTED)
        self.assertEqual(model.gap_interval_px, FiniteInterval(19.0, 21.0))
        self.assertEqual(
            model.unresolved_gap_proposals_px,
            (FiniteInterval(-2.0, 2.0),),
        )
        self.assertEqual(
            model.unresolved_observation_ids,
            (ObservationId("contact"),),
        )

    def test_equal_repeated_gap_explanations_remain_unresolved(self) -> None:
        model = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=(),
            direct_separator_gaps=(
                (FiniteInterval(18.0, 22.0), ObservationId("normal-a")),
                (FiniteInterval(19.0, 23.0), ObservationId("normal-b")),
                (FiniteInterval(48.0, 52.0), ObservationId("wide-a")),
                (FiniteInterval(49.0, 53.0), ObservationId("wide-b")),
            ),
        )
        self.assertEqual(model.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(model.gap_interval_px)

    def test_single_pitch_from_two_role_families_cannot_establish_gap(
        self,
    ) -> None:
        model = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=(
                (_edge(1, 0.0, "start-a"), _edge(2, 380.0, "start-b")),
                (_edge(1, 360.0, "end-a"), _edge(2, 740.0, "end-b")),
            ),
            direct_separator_gaps=(),
        )
        self.assertEqual(model.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(model.gap_interval_px)
        self.assertEqual(len(model.direct_gap_proposals_px), 2)

    def test_120_one_pitch_does_not_borrow_a_format_prior(self) -> None:
        model = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=((_edge(1, 0.0, "a"), _edge(2, 380.0, "b")),),
            direct_separator_gaps=(),
        )
        self.assertEqual(model.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(len(model.direct_gap_proposals_px), 1)
        self.assertIsNone(model.placement_pitch_interval_px)
        self.assertIsNone(model.canonical_placement_pitch_px)

    def test_equal_count_partial_does_not_gain_filled_holder_authority(
        self,
    ) -> None:
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(36.0, 24.0, 2.0),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        gap_model = LaneGapModel.from_ordinal_edges(
            geometry.width_state,
            lane_id="lane:test",
            edge_families=(),
            direct_separator_gaps=(
                (FiniteInterval.exact(20.0), ObservationId("gap-a")),
                (FiniteInterval.exact(20.0), ObservationId("gap-b")),
            ),
        )
        relations = tuple(
            LocalAdvanceRelation(
                relation_ordinal=ordinal,
                kind=LocalAdvanceKind.NOMINAL,
                delta_interval_px=FiniteInterval.exact(0.0),
                canonical_delta_px=0.0,
                observation_ids=(),
            )
            for ordinal in (1, 2)
        )
        common = dict(
            output_slot_count=3,
            measurement_slot_count=3,
            width_authority_px=FiniteInterval(0.0, 1120.0),
            holder_extent_tolerance_ratio=0.035,
        )
        full = long_axis_fill_authority(
            SimpleNamespace(
                **common,
                holder_layout_authority=(
                    HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
                ),
            ),
            geometry,
            gap_model,
            relations,
        )
        partial = long_axis_fill_authority(
            SimpleNamespace(
                **common,
                holder_layout_authority=(
                    HolderLayoutAuthority.USER_CONFIRMED_NONFILLING_LAYOUT
                ),
            ),
            geometry,
            gap_model,
            relations,
        )
        self.assertEqual(full.state, EvidenceState.SUPPORTED)
        self.assertEqual(partial.state, EvidenceState.UNAVAILABLE)

    def test_filled_layout_does_not_require_frames_to_equal_canvas_extent(
        self,
    ) -> None:
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(56.0, 56.0, None),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        gap_model = LaneGapModel.from_ordinal_edges(
            geometry.width_state,
            lane_id="lane:test",
            edge_families=(),
            direct_separator_gaps=(
                (FiniteInterval.exact(40.0), ObservationId("gap-a")),
                (FiniteInterval.exact(40.0), ObservationId("gap-b")),
            ),
        )
        relations = tuple(
            LocalAdvanceRelation(
                relation_ordinal=ordinal,
                kind=LocalAdvanceKind.NOMINAL,
                delta_interval_px=FiniteInterval.exact(0.0),
                canonical_delta_px=0.0,
                observation_ids=(),
            )
            for ordinal in (1, 2)
        )
        authority = long_axis_fill_authority(
            SimpleNamespace(
                output_slot_count=3,
                measurement_slot_count=3,
                holder_layout_authority=(
                    HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
                ),
                width_authority_px=FiniteInterval(0.0, 2260.0),
                holder_extent_tolerance_ratio=0.035,
            ),
            geometry,
            gap_model,
            relations,
        )
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        assert authority.chain_span_interval_px is not None
        self.assertLess(authority.chain_span_interval_px.maximum, 2260.0)

    def test_filled_layout_cannot_infer_an_unresolved_gap(self) -> None:
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(56.0, 56.0, None),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        gap_model = LaneGapModel.from_ordinal_edges(
            geometry.width_state,
            lane_id="lane:test",
            edge_families=(),
            direct_separator_gaps=(
                (FiniteInterval.exact(40.0), ObservationId("gap-a")),
            ),
        )
        authority = long_axis_fill_authority(
            SimpleNamespace(
                output_slot_count=3,
                measurement_slot_count=3,
                holder_layout_authority=(
                    HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
                ),
                width_authority_px=FiniteInterval(0.0, 2260.0),
                holder_extent_tolerance_ratio=0.035,
            ),
            geometry,
            gap_model,
            (
                LocalAdvanceRelation(
                    relation_ordinal=1,
                    kind=LocalAdvanceKind.OBSERVED_NORMAL,
                    delta_interval_px=FiniteInterval.exact(40.0),
                    canonical_delta_px=40.0,
                    observation_ids=(ObservationId("gap-a"),),
                ),
                LocalAdvanceRelation(
                    relation_ordinal=2,
                    kind=LocalAdvanceKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                    observation_ids=(),
                ),
            ),
        )
        self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)

    def test_filled_count_two_can_center_one_direct_normal_gap(self) -> None:
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(70.0, 56.0, None),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        gap_model = LaneGapModel.from_ordinal_edges(
            geometry.width_state,
            lane_id="lane:test",
            edge_families=(),
            direct_separator_gaps=(
                (FiniteInterval.exact(45.0), ObservationId("gap-a")),
            ),
        )
        authority = long_axis_fill_authority(
            SimpleNamespace(
                output_slot_count=2,
                measurement_slot_count=2,
                holder_layout_authority=(
                    HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
                ),
                width_authority_px=FiniteInterval(0.0, 1885.0),
                holder_extent_tolerance_ratio=0.035,
            ),
            geometry,
            gap_model,
            (
                LocalAdvanceRelation(
                    relation_ordinal=1,
                    kind=LocalAdvanceKind.OBSERVED_NORMAL,
                    delta_interval_px=FiniteInterval.exact(45.0),
                    canonical_delta_px=45.0,
                    observation_ids=(ObservationId("gap-a"),),
                ),
            ),
        )
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(gap_model.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(gap_model.placement_pitch_interval_px)

    def test_repeated_contact_or_overlap_cannot_become_normal_gap(self) -> None:
        model = LaneGapModel.from_ordinal_edges(
            _width_state(),
            lane_id="lane:0",
            edge_families=((
                _edge(1, 0.0, "a"),
                _edge(2, 350.0, "b"),
                _edge(3, 700.0, "c"),
            ),),
            direct_separator_gaps=(),
        )
        self.assertEqual(model.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(model.gap_interval_px)
        self.assertEqual(
            model.unresolved_gap_proposals_px,
            (FiniteInterval.exact(-10.0), FiniteInterval.exact(-10.0)),
        )

    def test_exception_proposals_are_not_hidden_by_normal_candidates(self) -> None:
        source = inspect.getsource(materialize_source_placements)
        self.assertNotIn("and layer", source)
        self.assertNotIn("break", source)

    def test_local_separator_angle_is_not_a_second_direction_gate(self) -> None:
        source = inspect.getsource(complete_chain_record)
        self.assertNotIn("joint_direction_compatibility", source)

    def test_safe_crop_envelope_is_built_only_after_source_selection(self) -> None:
        orchestration = inspect.getsource(reconstruct_photo_geometry)
        self.assertGreater(
            orchestration.index("resolve_selected_source_output"),
            orchestration.index("build_lane_candidate_reconstructions"),
        )
        source = inspect.getsource(resolve_selected_source_output)
        self.assertGreater(
            source.index("safe_crop_envelope_from_placement"),
            source.index("select_source_placement_clusters"),
        )
        self.assertNotIn("candidate_envelopes", source)
        self.assertNotIn("materialize_complete_chain", source)
        self.assertNotIn("chain_sampling_geometry", source)
        self.assertNotIn("complete_chain_record", source)
        self.assertIn("selected_chain_physical_signature", source)
        self.assertLess(
            orchestration.index("bind_shared_source_geometry_before_selection"),
            orchestration.index("build_lane_candidate_reconstructions"),
        )

    def test_complete_separator_chain_is_a_physical_directed_path(self) -> None:
        fit_positions: dict[str, FiniteInterval] = {}

        def band(
            name: str,
            left_position: float,
            relation_ordinal: int,
        ) -> SeparatorBandRoleProposal:
            observation_id = ObservationId(f"band:{name}")
            left_run = f"run:{name}:left"
            right_run = f"run:{name}:right"
            fit_positions[left_run] = FiniteInterval.exact(left_position)
            fit_positions[right_run] = FiniteInterval.exact(
                left_position + 10.0
            )
            left_role = OrdinalBoundaryRole(
                relation_ordinal * 2 - 1,
                relation_ordinal,
                BoundaryRole.END,
            )
            right_role = OrdinalBoundaryRole(
                relation_ordinal * 2,
                relation_ordinal + 1,
                BoundaryRole.START,
            )
            return SeparatorBandRoleProposal(
                proposal_id=f"proposal:{name}:{relation_ordinal}",
                band_observation_id=observation_id,
                relation_ordinal=relation_ordinal,
                phase_interval_px=FiniteInterval(-1000.0, 1000.0),
                gap_interval_px=FiniteInterval.exact(10.0),
                left_role_proposal=SequenceRoleProposal(
                    proposal_id=f"role:{name}:{relation_ordinal}:left",
                    run_id=left_run,
                    role=left_role,
                    phase_interval_px=FiniteInterval(-1000.0, 1000.0),
                    transition_ids=(ObservationId(f"transition:{name}:left"),),
                    role_coordinate_px=0.0,
                    separator_band_observation_id=observation_id,
                ),
                right_role_proposal=SequenceRoleProposal(
                    proposal_id=f"role:{name}:{relation_ordinal}:right",
                    run_id=right_run,
                    role=right_role,
                    phase_interval_px=FiniteInterval(-1000.0, 1000.0),
                    transition_ids=(ObservationId(f"transition:{name}:right"),),
                    role_coordinate_px=0.0,
                    separator_band_observation_id=observation_id,
                ),
            )

        proposals = tuple(
            band(name, position, ordinal)
            for name, position in (
                ("first", 100.0),
                ("internal-distractor", 150.0),
                ("second", 210.0),
            )
            for ordinal in (1, 2)
        )
        groups = direct_separator_groups(
            proposals,
            relation_count=2,
            width_interval_px=FiniteInterval.exact(100.0),
            canonical_width_px=100.0,
            fit_position_by_run=fit_positions,
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(
            tuple(
                str(item.band_observation_id)
                for item in groups[0].separator_band_proposals
            ),
            ("band:first", "band:second"),
        )
        self.assertEqual(
            tuple(
                item.relation_ordinal
                for item in groups[0].separator_band_proposals
            ),
            (1, 2),
        )

    def test_lane_edge_family_need_not_touch_two_different_slots(self) -> None:
        source = inspect.getsource(materialize_cross_placement)
        self.assertNotIn("supported_frame_count", source)
        self.assertNotIn("local cross line cannot own", source)

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
            direct_separator_gaps=(),
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
