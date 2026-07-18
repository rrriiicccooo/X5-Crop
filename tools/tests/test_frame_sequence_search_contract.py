from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.tests.frame_slot_solver_support import (
    content,
    dimensions,
    path,
    scope,
    separator,
    sequence_search_index,
)
from x5crop.detection.physical import frame_sequence_search as sequence_search
from x5crop.detection.physical import (
    frame_sequence_separator_assignment as separator_assignment,
)
from x5crop.detection.physical.frame_sequence_measurements import (
    EdgeConstraint,
    MeasuredFrameConstraint,
)
from x5crop.detection.physical.frame_sequence_solver import solve_frame_sequence
from x5crop.detection.physical.model import (
    BoundaryGeometryState,
    FrameBoundarySource,
)
from x5crop.detection.physical.short_axis import shared_short_axis_plan
from x5crop.domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)

_ALL_HOLDER_SIDES = (
    BoundarySide.LEADING,
    BoundarySide.TRAILING,
    BoundarySide.TOP,
    BoundarySide.BOTTOM,
)

class FrameSequenceSearchContractTest(unittest.TestCase):
    def test_graph_layer_state_index_is_built_once_per_transition(self) -> None:
        def edge(position: float) -> EdgeConstraint:
            return EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"layer_index_edge:{position}"),
                    (),
                    "synthetic graph layer edge",
                ),
            )

        def frame(start: float, end: float) -> MeasuredFrameConstraint:
            return MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(end),
                width_px=PixelInterval.exact(end - start),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        ordered = (
            frame(0.0, 100.0),
            frame(110.0, 210.0),
            frame(220.0, 320.0),
        )
        grouped = tuple(((index, option),) for index, option in enumerate(ordered))
        context = sequence_search.sequence_graph_context(
            ordered,
            content(width=320, height=100, runs=()),
            allow_nominal_slot_sized_gap=True,
        )
        build_index = sequence_search.graph_layer_state_index

        with patch.object(
            sequence_search,
            "graph_layer_state_index",
            wraps=build_index,
        ) as indexed:
            sequence = sequence_search.sequence_graph_best_path(
                grouped,
                ordered,
                context,
            )

        self.assertEqual(sequence, ordered)
        self.assertEqual(indexed.call_count, len(grouped) - 1)

    def test_blank_search_retains_a_witness_for_every_feasible_anchor(self) -> None:
        def edge(position: float) -> EdgeConstraint:
            return EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"blank_witness_edge:{position}"),
                    (),
                    "synthetic blank-search edge",
                ),
            )

        def frame(start: float) -> MeasuredFrameConstraint:
            return MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(start + 100.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        ordered = tuple(
            frame(start)
            for start in (0.0, 110.0, 220.0, 330.0, 650.0)
        )
        grouped = (
            ((0, ordered[0]),),
            tuple((index, ordered[index]) for index in (1, 2, 3)),
            ((4, ordered[4]),),
        )
        context = sequence_search.sequence_graph_context(
            ordered,
            content(width=750, height=100, runs=()),
            allow_nominal_slot_sized_gap=True,
        )

        witnesses = sequence_search.sequence_graph_witnesses(
            grouped,
            ordered,
            context,
        )

        witnessed_middle_options = {
            ordered.index(sequence[1]) for sequence in witnesses
        }
        self.assertEqual(witnessed_middle_options, {1, 2, 3})

    def test_blank_search_retains_frame_sized_anchor_pair_alternative(self) -> None:
        def edge(position: float) -> EdgeConstraint:
            return EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"blank_pair_edge:{position}"),
                    (),
                    "synthetic blank-pair edge",
                ),
            )

        def frame(start: float) -> MeasuredFrameConstraint:
            return MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(start + 100.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        ordered = tuple(
            frame(start)
            for start in (0.0, 110.0, 220.0, 330.0, 330.0, 440.0, 550.0)
        )
        grouped = (
            ((0, ordered[0]),),
            ((1, ordered[1]),),
            ((2, ordered[2]), (3, ordered[3])),
            ((4, ordered[4]), (5, ordered[5])),
            ((6, ordered[6]),),
        )
        context = sequence_search.sequence_graph_context(
            ordered,
            content(width=650, height=100, runs=()),
            allow_nominal_slot_sized_gap=True,
        )

        witnesses = sequence_search.sequence_graph_witnesses(
            grouped,
            ordered,
            context,
        )

        self.assertIn(
            (ordered[0], ordered[1], ordered[2], ordered[5], ordered[6]),
            witnesses,
        )

    def test_sequence_graph_conservation_precedes_separator_support(self) -> None:
        search_scope = scope(
            width=5_200,
            height=100,
            leading=0.0,
            trailing=5_200.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        separator_support = separator(1_100.0, 1_110.0, plan, supported=True)
        bad_first_trailing, bad_second_leading = (
            separator_assignment.observed_band_edges(separator_support)
        )

        def dimension(position: float, label: str) -> EdgeConstraint:
            return EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic dimension edge",
                ),
            )

        def frame(
            leading: EdgeConstraint,
            trailing: EdgeConstraint,
        ) -> MeasuredFrameConstraint:
            return MeasuredFrameConstraint(
                leading=leading,
                trailing=trailing,
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        conserved = (
            frame(dimension(0.0, "good-1-leading"), dimension(100.0, "good-1-trailing")),
            frame(dimension(110.0, "good-2-leading"), dimension(210.0, "good-2-trailing")),
            frame(dimension(220.0, "good-3-leading"), dimension(320.0, "good-3-trailing")),
        )
        fragmented = (
            frame(dimension(1_000.0, "bad-1-leading"), bad_first_trailing),
            frame(bad_second_leading, dimension(1_210.0, "bad-2-trailing")),
            frame(dimension(5_000.0, "bad-3-leading"), dimension(5_100.0, "bad-3-trailing")),
        )
        ordered = (*conserved, *fragmented)
        grouped = tuple(
            (
                (layer, conserved[layer]),
                (layer + len(conserved), fragmented[layer]),
            )
            for layer in range(len(conserved))
        )

        selected = sequence_search.sequence_graph_best_path(
            grouped,
            ordered,
            sequence_search.sequence_graph_context(
                ordered,
                content(width=5_200, height=100, runs=()),
                allow_nominal_slot_sized_gap=True,
            ),
        )

        self.assertEqual(selected, conserved)

    def test_small_width_alternative_does_not_cap_larger_sequence_spacing(
        self,
    ) -> None:
        def edge(position: float) -> EdgeConstraint:
            return EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"mixed_width_edge:{position}"),
                    (),
                    "synthetic mixed-width graph edge",
                ),
            )

        def frame(start: float) -> MeasuredFrameConstraint:
            return MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(start + 100.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        expected = tuple(frame(start) for start in (0.0, 130.0, 260.0))

        result = sequence_search.measured_frame_sequences(
            expected,
            3,
            content(width=360, height=100, runs=()),
            100,
            (
                PixelInterval(20.0, 25.0),
                PixelInterval(95.0, 105.0),
            ),
            allow_nominal_slot_sized_gap=False,
        )

        self.assertFalse(result.budget_exhausted)
        self.assertIn(expected, result.sequences)

    def test_blank_pair_witness_uses_physical_prefix_and_suffix(self) -> None:
        def edge(position: float) -> EdgeConstraint:
            return EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"blank_pair_path_edge:{position}"),
                    (),
                    "synthetic dimension edge",
                ),
            )

        def frame(start: float) -> MeasuredFrameConstraint:
            return MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(start + 100.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        correct = tuple(frame(start) for start in (0.0, 110.0, 220.0, 530.0, 640.0))
        prefix_distractor = frame(200.0)
        suffix_distractor = frame(550.0)
        alternate = tuple(
            frame(start) for start in (1_000.0, 1_110.0, 1_220.0, 1_330.0, 1_440.0)
        )
        ordered = (
            correct[0],
            alternate[0],
            correct[1],
            prefix_distractor,
            alternate[1],
            correct[2],
            alternate[2],
            correct[3],
            alternate[3],
            correct[4],
            suffix_distractor,
            alternate[4],
        )
        grouped = (
            ((0, correct[0]), (1, alternate[0])),
            (
                (2, correct[1]),
                (3, prefix_distractor),
                (4, alternate[1]),
            ),
            ((5, correct[2]), (6, alternate[2])),
            ((7, correct[3]), (8, alternate[3])),
            (
                (9, correct[4]),
                (10, suffix_distractor),
                (11, alternate[4]),
            ),
        )

        witnesses = sequence_search.sequence_graph_witnesses(
            grouped,
            ordered,
            sequence_search.sequence_graph_context(
                ordered,
                content(width=1_540, height=100, runs=()),
                allow_nominal_slot_sized_gap=True,
            ),
        )

        self.assertIn(correct, witnesses)

    def test_common_width_group_requires_an_explicit_width_hypothesis(self) -> None:
        def option(width: PixelInterval, source: str) -> SimpleNamespace:
            def supported_edge(side: str) -> SimpleNamespace:
                return SimpleNamespace(
                    state=EvidenceState.UNAVAILABLE,
                    separator_cross_axis=SimpleNamespace(
                        state=EvidenceState.SUPPORTED,
                    ),
                    provenance=SimpleNamespace(
                        observation_id=ObservationId(f"{source}:{side}"),
                    ),
                )

            return SimpleNamespace(
                width_px=width,
                leading=supported_edge("leading"),
                trailing=supported_edge("trailing"),
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
            )

        options_by_frame = (
            ((0, option(PixelInterval(98.0, 102.0), "frame_1")),),
            ((1, option(PixelInterval(99.0, 103.0), "frame_2")),),
            ((2, option(PixelInterval(100.0, 104.0), "frame_3")),),
        )

        index = sequence_search._common_width_option_index(
            options_by_frame,
            3,
            (PixelInterval(80.0, 140.0),),
        )

        self.assertEqual(index.group_masks, ())

    def test_single_supported_edge_cannot_seed_common_width(self) -> None:
        supported_edge = SimpleNamespace(
            state=EvidenceState.UNAVAILABLE,
            separator_cross_axis=SimpleNamespace(
                state=EvidenceState.SUPPORTED,
            ),
            provenance=SimpleNamespace(
                observation_id=ObservationId("supported_edge"),
            ),
        )
        unavailable_edge = SimpleNamespace(
            state=EvidenceState.UNAVAILABLE,
            separator_cross_axis=None,
            provenance=SimpleNamespace(
                observation_id=ObservationId("unavailable_edge"),
            ),
        )
        option = SimpleNamespace(
            width_px=PixelInterval.exact(200.0),
            leading=supported_edge,
            trailing=unavailable_edge,
            leading_holder_clip_supported=False,
            trailing_holder_clip_supported=False,
        )

        index = sequence_search._common_width_option_index(
            (((0, option),), ((1, option),)),
            2,
            (PixelInterval.exact(100.0),),
        )

        self.assertEqual(index.group_masks, ())

    def test_same_observation_cannot_seed_frame_width(self) -> None:
        shared_provenance = SimpleNamespace(
            observation_id=ObservationId("one_separator_band"),
        )
        supported_edge = SimpleNamespace(
            state=EvidenceState.UNAVAILABLE,
            separator_cross_axis=SimpleNamespace(
                state=EvidenceState.SUPPORTED,
            ),
            provenance=shared_provenance,
        )
        option = SimpleNamespace(
            width_px=PixelInterval.exact(200.0),
            leading=supported_edge,
            trailing=supported_edge,
            leading_holder_clip_supported=False,
            trailing_holder_clip_supported=False,
        )

        index = sequence_search._common_width_option_index(
            (((0, option),), ((1, option),)),
            2,
            (PixelInterval.exact(100.0),),
        )

        self.assertEqual(index.group_masks, ())

    def test_common_width_group_respects_measurement_uncertainty(self) -> None:
        def option(width: PixelInterval, source: str) -> SimpleNamespace:
            def supported_edge(side: str) -> SimpleNamespace:
                return SimpleNamespace(
                    state=EvidenceState.UNAVAILABLE,
                    separator_cross_axis=SimpleNamespace(
                        state=EvidenceState.SUPPORTED,
                    ),
                    provenance=SimpleNamespace(
                        observation_id=ObservationId(f"{source}:{side}"),
                    ),
                )

            return SimpleNamespace(
                width_px=width,
                leading=supported_edge("leading"),
                trailing=supported_edge("trailing"),
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
            )

        index = sequence_search._common_width_option_index(
            (
                ((0, option(PixelInterval(98.0, 100.0), "frame_1")),),
                ((1, option(PixelInterval(101.0, 103.0), "frame_2")),),
            ),
            2,
            (PixelInterval(90.0, 110.0),),
        )

        self.assertIn((1, 2), index.group_masks)

    def test_common_width_groups_remove_strictly_contained_search_surfaces(
        self,
    ) -> None:
        groups = (
            (0b001, 0b001),
            (0b011, 0b101),
            (0b100, 0b010),
        )

        self.assertEqual(
            sequence_search._maximal_common_width_group_masks(groups),
            (groups[1], groups[2]),
        )

    def test_search_budget_is_checked_before_graph_witness_generation(
        self,
    ) -> None:
        search_scope = scope(
            width=210,
            height=100,
            leading=0.0,
            trailing=210.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        paths = {
            path.position.midpoint: path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
        }

        def edge(position: float) -> EdgeConstraint:
            observation = paths[position]
            return EdgeConstraint(
                position=observation.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                path=observation,
            )

        constraints = (
            MeasuredFrameConstraint(
                leading=edge(0.0),
                trailing=edge(100.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            MeasuredFrameConstraint(
                leading=edge(110.0),
                trailing=edge(210.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
        )
        with patch.object(
            sequence_search,
            "sequence_graph_witnesses",
            wraps=sequence_search.sequence_graph_witnesses,
        ) as graph_witnesses:
            result = sequence_search.measured_frame_sequences(
                constraints,
                2,
                content(width=210, height=100),
                0,
                (PixelInterval.exact(100.0),),
                allow_nominal_slot_sized_gap=False,
            )

        self.assertEqual(result.assignment_evaluations, 0)
        self.assertTrue(result.budget_exhausted)
        graph_witnesses.assert_not_called()

    def test_separator_incumbent_prunes_only_groups_without_matching_support(
        self,
    ) -> None:
        search_scope = scope(
            width=210,
            height=100,
            leading=0.0,
            trailing=210.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(50.0, 100.0, 110.0, 160.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        support = separator(100.0, 110.0, plan, supported=True)
        preceding_trailing, following_leading = (
            separator_assignment.observed_band_edges(support)
        )
        paths = {
            path.position.midpoint: path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
        }

        def edge(position: float) -> EdgeConstraint:
            observation = paths[position]
            return EdgeConstraint(
                position=observation.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                path=observation,
            )

        def frame(
            leading: EdgeConstraint,
            trailing: EdgeConstraint,
            width: float,
        ) -> MeasuredFrameConstraint:
            return MeasuredFrameConstraint(
                leading=leading,
                trailing=trailing,
                width_px=PixelInterval.exact(width),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        options = (
            frame(edge(0.0), preceding_trailing, 100.0),
            frame(following_leading, edge(210.0), 100.0),
            frame(edge(0.0), edge(50.0), 50.0),
            frame(edge(160.0), edge(210.0), 50.0),
        )
        widths = (PixelInterval.exact(100.0), PixelInterval.exact(50.0))
        visible_content = content(
            width=210,
            height=100,
            runs=((0, 100), (110, 210)),
        )

        unbounded = sequence_search.measured_frame_sequences(
            options,
            2,
            visible_content,
            10_000,
            widths,
            allow_nominal_slot_sized_gap=False,
        )
        bounded = sequence_search.measured_frame_sequences(
                options,
                2,
                visible_content,
                10_000,
                widths,
                allow_nominal_slot_sized_gap=False,
                minimum_supported_separator_count=1,
        )

        self.assertTrue(bounded.sequences)
        self.assertFalse(bounded.budget_exhausted)
        self.assertLessEqual(
            bounded.assignment_evaluations,
            unbounded.assignment_evaluations,
        )
        self.assertTrue(
            all(
                sequence[0].trailing.separator is not None
                and sequence[0].trailing.separator
                is sequence[1].leading.separator
                for sequence in bounded.sequences
            )
        )

        with patch.object(
            sequence_search,
            "sequence_graph_witnesses",
            return_value=(options[2:], options[:2]),
        ):
            bounded = sequence_search.measured_frame_sequences(
                options,
                2,
                visible_content,
                10_000,
                widths,
                allow_nominal_slot_sized_gap=False,
                minimum_supported_separator_count=1,
            )

        self.assertEqual(bounded.sequences, (options[:2],))

    def test_graph_witnesses_keep_measured_edge_alternative_to_geometry_contact(
        self,
    ) -> None:
        search_scope = scope(
            width=330,
            height=100,
            leading=0.0,
            trailing=330.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(230.0,),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        internal_separator = separator(100.0, 110.0, plan, supported=True)
        trailing_holder_band = separator(320.0, 330.0, plan, supported=True)
        first_trailing, second_leading = separator_assignment.observed_band_edges(
            internal_separator
        )
        holder_trailing, _ = separator_assignment.observed_band_edges(
            trailing_holder_band
        )
        holder_trailing = replace(
            holder_trailing,
            external_side=BoundarySide.TRAILING,
        )
        raw_path = next(
            path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
            and path.position == PixelInterval.exact(230.0)
        )

        def dimension(position: float, label: str) -> EdgeConstraint:
            return EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic dimension edge",
                ),
            )

        def frame(
            leading: EdgeConstraint,
            trailing: EdgeConstraint,
        ) -> MeasuredFrameConstraint:
            return MeasuredFrameConstraint(
                leading=leading,
                trailing=trailing,
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        first = frame(dimension(0.0, "first-leading"), first_trailing)
        second = frame(second_leading, dimension(210.0, "second-trailing"))
        measured_last = frame(
            EdgeConstraint(
                position=raw_path.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=raw_path.provenance,
                path=raw_path,
            ),
            holder_trailing,
        )
        contact_last = frame(
            dimension(210.0, "contact-leading"),
            dimension(310.0, "contact-trailing"),
        )
        ordered = (first, second, measured_last, contact_last)
        grouped = (
            ((0, first),),
            ((1, second),),
            ((2, measured_last), (3, contact_last)),
        )

        witnesses = sequence_search.sequence_graph_witnesses(
            grouped,
            ordered,
            sequence_search.sequence_graph_context(
                ordered,
                content(width=330, height=100, runs=()),
                allow_nominal_slot_sized_gap=True,
            ),
        )

        self.assertTrue(
            any(sequence[-1] is measured_last for sequence in witnesses)
        )

    def test_sequence_graph_keeps_the_physical_best_non_extreme_path(self) -> None:
        def edge(position: float) -> EdgeConstraint:
            return EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
                    observation_id=ObservationId(f"graph-edge:{position}"),
                    dependencies=(),
                    description="synthetic dimension-constrained graph edge",
                ),
            )

        def frame(start: float, end: float) -> MeasuredFrameConstraint:
            return MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(end),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        left = (
            frame(0.0, 100.0),
            frame(120.0, 220.0),
            frame(240.0, 340.0),
        )
        middle = (
            frame(10.0, 110.0),
            frame(110.0, 210.0),
            frame(210.0, 310.0),
        )
        right = (
            frame(20.0, 120.0),
            frame(140.0, 240.0),
            frame(260.0, 360.0),
        )
        ordered = tuple(
            frame_option
            for layer in zip(left, middle, right, strict=True)
            for frame_option in layer
        )
        grouped = tuple(
            tuple((layer * 3 + route, ordered[layer * 3 + route]) for route in range(3))
            for layer in range(3)
        )
        visible_content = content(width=360, height=100, runs=())
        graph_context = sequence_search.sequence_graph_context(
            ordered,
            visible_content,
            allow_nominal_slot_sized_gap=True,
        )

        witnesses = sequence_search.sequence_graph_witnesses(
            grouped,
            ordered,
            graph_context,
        )

        self.assertIn(middle, witnesses)

    def test_frame_width_hint_cannot_outrank_supported_external_boundary(
        self,
    ) -> None:
        search_scope = scope(
            width=240,
            height=100,
            leading=0.0,
            trailing=240.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        holder_band = separator(0.0, 10.0, plan, supported=True)
        _, external_leading = separator_assignment.observed_band_edges(holder_band)
        external_leading = replace(
            external_leading,
            external_side=BoundarySide.LEADING,
            state=EvidenceState.SUPPORTED,
        )
        raw_path = path(
            BoundaryAxis.LONG,
            0.0,
            "unsupported-leading-path",
        )
        unsupported_leading = EdgeConstraint(
            position=raw_path.position,
            basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            state=EvidenceState.UNAVAILABLE,
            geometry_state=BoundaryGeometryState.RESOLVED,
            provenance=raw_path.provenance,
            path=raw_path,
        )

        def dimension(position: PixelInterval, label: str) -> EdgeConstraint:
            return EdgeConstraint(
                position=position,
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic dimension edge",
                ),
            )

        shared_trailing = dimension(PixelInterval.exact(110.0), "first-trailing")
        supported_first = MeasuredFrameConstraint(
            leading=external_leading,
            trailing=shared_trailing,
            width_px=PixelInterval.exact(100.0),
            full_width_hypothesis_admissible=True,
            leading_holder_clip_supported=True,
            trailing_holder_clip_supported=False,
            search_order_residual=0.0,
            frame_width_hint_residual=10.0,
        )
        hinted_first = MeasuredFrameConstraint(
            leading=unsupported_leading,
            trailing=shared_trailing,
            width_px=PixelInterval.exact(110.0),
            full_width_hypothesis_admissible=True,
            leading_holder_clip_supported=False,
            trailing_holder_clip_supported=False,
            search_order_residual=0.0,
            frame_width_hint_residual=0.0,
        )
        second = MeasuredFrameConstraint(
            leading=dimension(PixelInterval.exact(120.0), "second-leading"),
            trailing=dimension(PixelInterval(220.0, 230.0), "second-trailing"),
            width_px=PixelInterval(100.0, 110.0),
            full_width_hypothesis_admissible=True,
            leading_holder_clip_supported=False,
            trailing_holder_clip_supported=False,
            search_order_residual=0.0,
            frame_width_hint_residual=0.0,
        )
        ordered = (supported_first, hinted_first, second)

        selected = sequence_search.sequence_graph_best_path(
            (
                ((0, supported_first), (1, hinted_first)),
                ((2, second),),
            ),
            ordered,
            sequence_search.sequence_graph_context(
                ordered,
                content(width=240, height=100, runs=()),
                allow_nominal_slot_sized_gap=True,
            ),
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertIs(selected[0], supported_first)

    def test_sequence_graph_skips_nodes_outside_complete_paths(
        self,
    ) -> None:
        def edge(position: float) -> EdgeConstraint:
            return EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"feasible-edge:{position}"),
                    (),
                    "synthetic graph edge",
                ),
            )

        def frame(start: float, end: float) -> MeasuredFrameConstraint:
            return MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(end),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        valid = (
            frame(0.0, 100.0),
            frame(110.0, 210.0),
            frame(220.0, 320.0),
        )
        dead_middle = tuple(
            frame(-300.0 - offset, -200.0 - offset)
            for offset in range(50)
        )
        dead_trailing = tuple(
            frame(-600.0 - offset, -500.0 - offset)
            for offset in range(50)
        )
        ordered = (*valid, *dead_middle, *dead_trailing)
        grouped = (
            ((0, valid[0]),),
            (
                (1, valid[1]),
                *tuple(
                    (3 + offset, option)
                    for offset, option in enumerate(dead_middle)
                ),
            ),
            (
                (2, valid[2]),
                *tuple(
                    (3 + len(dead_middle) + offset, option)
                    for offset, option in enumerate(dead_trailing)
                ),
            ),
        )
        context = sequence_search.sequence_graph_context(
            ordered,
            content(width=320, height=100, runs=()),
            allow_nominal_slot_sized_gap=True,
        )

        with patch.object(
            sequence_search,
            "best_graph_predecessor",
            wraps=sequence_search.best_graph_predecessor,
        ) as best_predecessor:
            witnesses = sequence_search.sequence_graph_witnesses(
                grouped,
                ordered,
                context,
            )

        self.assertIn(valid, witnesses)
        self.assertLessEqual(best_predecessor.call_count, 4)

    def test_graph_search_preserves_independent_separator_measurements(self) -> None:
        search_scope = scope(
            width=400,
            height=100,
            leading=0.0,
            trailing=400.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        band_leading, band_trailing = separator_assignment.observed_band_edges(
            separator(100.0, 110.0, plan, supported=True)
        )

        def inferred_edge(position: float, label: str) -> EdgeConstraint:
            return EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic graph boundary",
                ),
            )

        def constraint(
            leading: EdgeConstraint,
            trailing: EdgeConstraint,
        ) -> MeasuredFrameConstraint:
            return MeasuredFrameConstraint(
                leading=leading,
                trailing=trailing,
                width_px=trailing.position.minus(leading.position),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        measured_sequence = (
            constraint(inferred_edge(0.0, "measured_1_leading"), band_leading),
            constraint(band_trailing, inferred_edge(210.0, "measured_2_trailing")),
            constraint(
                inferred_edge(260.0, "measured_3_leading"),
                inferred_edge(360.0, "measured_3_trailing"),
            ),
        )
        compact_without_measurement = tuple(
            constraint(
                inferred_edge(start, f"compact_{index}_leading"),
                inferred_edge(start + 100.0, f"compact_{index}_trailing"),
            )
            for index, start in enumerate((0.0, 101.0, 202.0), start=1)
        )

        self.assertGreater(
            sequence_search._graph_sequence_rank(measured_sequence),
            sequence_search._graph_sequence_rank(compact_without_measurement),
        )

    def test_common_width_grouping_does_not_scan_every_option_per_coordinate(
        self,
    ) -> None:
        unavailable_edge = SimpleNamespace(
            state=EvidenceState.UNAVAILABLE,
            separator_cross_axis=None,
        )
        width_hypotheses = tuple(
            PixelInterval.exact(float(width)) for width in range(1, 31)
        )
        options_by_frame = tuple(
            tuple(
                (
                    option_index,
                    SimpleNamespace(
                        width_px=PixelInterval(1.0, 30.0),
                        leading=unavailable_edge,
                        trailing=unavailable_edge,
                        leading_holder_clip_supported=False,
                        trailing_holder_clip_supported=False,
                    ),
                )
                for option_index in range(30)
            )
            for _ in range(12)
        )

        with patch.object(
            sequence_search,
            "_common_width_coordinate_span",
            wraps=sequence_search._common_width_coordinate_span,
        ) as coordinate_span:
            width_index = sequence_search._common_width_option_index(
                options_by_frame,
                12,
                width_hypotheses,
            )

        self.assertEqual(len(width_index.group_masks), 1)
        self.assertEqual(coordinate_span.call_count, 360)

    def test_reachability_index_does_not_discard_a_valid_predecessor(self) -> None:
        def option(
            leading: float,
            trailing: float,
            width: PixelInterval,
        ) -> SimpleNamespace:
            def edge(position: float) -> SimpleNamespace:
                return SimpleNamespace(
                    position=PixelInterval.exact(position),
                    separator=None,
                    external_side=None,
                )

            return SimpleNamespace(
                leading=edge(leading),
                trailing=edge(trailing),
                width_px=width,
            )

        ordered = (
            option(0.0, 10.0, PixelInterval.exact(30.0)),
            option(1.0, 20.0, PixelInterval.exact(5.0)),
            option(30.0, 40.0, PixelInterval(5.0, 30.0)),
        )
        context = SimpleNamespace(
            run_starts=(),
            run_ends=(),
            coverages=((0, 10), (1, 20), (30, 40)),
            allow_nominal_slot_sized_gap=False,
        )

        with patch.object(
            sequence_search,
            "_cached_sequence_graph_edge_supported",
            side_effect=lambda left, right, _ordered, _context: (left, right)
            == (0, 2),
        ) as edge_supported:
            reachable = sequence_search.reachable_predecessors_for_boundary(
                (0, 1),
                (2,),
                ordered,
                context,
            )

        self.assertEqual(reachable, {2: 0})

    def test_reachability_index_does_not_discard_a_valid_successor(self) -> None:
        def option(
            leading: float,
            trailing: float,
            width: PixelInterval,
        ) -> SimpleNamespace:
            def edge(position: float) -> SimpleNamespace:
                return SimpleNamespace(
                    position=PixelInterval.exact(position),
                    separator=None,
                    external_side=None,
                )

            return SimpleNamespace(
                leading=edge(leading),
                trailing=edge(trailing),
                width_px=width,
            )

        ordered = (
            option(0.0, 10.0, PixelInterval(5.0, 30.0)),
            option(20.0, 30.0, PixelInterval.exact(5.0)),
            option(30.0, 40.0, PixelInterval.exact(30.0)),
        )
        context = SimpleNamespace(
            run_starts=(),
            run_ends=(),
            coverages=((0, 10), (20, 30), (30, 40)),
            allow_nominal_slot_sized_gap=False,
        )

        with patch.object(
            sequence_search,
            "_cached_sequence_graph_edge_supported",
            side_effect=lambda left, right, _ordered, _context: (left, right)
            == (0, 2),
        ) as edge_supported:
            reachable = sequence_search._reachable_successors_for_boundary(
                (0,),
                (1, 2),
                ordered,
                context,
            )

        self.assertEqual(reachable, {0: 2})

    def test_graph_budget_charges_only_physically_supported_transitions(
        self,
    ) -> None:
        feasible = ((0, 1), (2, 3, 4), (5, 6, 7, 8))

        with patch.object(
            sequence_search,
            "_cached_sequence_graph_edge_supported",
            side_effect=lambda left, right, _ordered, _context: (left, right)
            in {(0, 2), (2, 5), (3, 6)},
        ):
            evaluations = sequence_search._sequence_graph_evaluations(
                feasible,
                (),
                SimpleNamespace(
                    allow_nominal_slot_sized_gap=True,
                    edge_support_cache={},
                ),
            )

        empty = sequence_search.SequenceGraphEvaluations(
            frozenset(),
            frozenset(),
            frozenset(),
        )
        self.assertEqual(evaluations.incremental_cost(empty), 12)

    def test_direct_graph_budget_charges_only_inspected_transition_facts(
        self,
    ) -> None:
        feasible = ((0, 1), (2, 3, 4))
        context = SimpleNamespace(
            allow_nominal_slot_sized_gap=False,
            edge_support_cache={(0, 2): True},
        )

        evaluations = sequence_search._sequence_graph_evaluations(
            feasible,
            (),
            context,
        )

        empty = sequence_search.SequenceGraphEvaluations(
            frozenset(),
            frozenset(),
            frozenset(),
        )
        self.assertEqual(evaluations.incremental_cost(empty), 6)

    def test_cached_graph_edge_is_charged_once_across_frame_layers(self) -> None:
        context = SimpleNamespace(
            allow_nominal_slot_sized_gap=False,
            edge_support_cache={(0, 1): True},
        )

        evaluations = sequence_search._sequence_graph_evaluations(
            ((0,), (1,), (0,), (1,)),
            (),
            context,
        )

        empty = sequence_search.SequenceGraphEvaluations(
            frozenset(),
            frozenset(),
            frozenset(),
        )
        self.assertEqual(evaluations.incremental_cost(empty), 5)

    def test_overlapping_width_groups_charge_shared_graph_facts_once(
        self,
    ) -> None:
        context = SimpleNamespace(
            allow_nominal_slot_sized_gap=False,
            edge_support_cache={(0, 2): True, (1, 3): False},
        )
        first = sequence_search._sequence_graph_evaluations(
            ((0, 1), (2, 3)),
            (),
            context,
        )
        context.edge_support_cache[(0, 4)] = True
        second = sequence_search._sequence_graph_evaluations(
            ((0, 1), (2, 3, 4)),
            (),
            context,
        )

        empty = sequence_search.SequenceGraphEvaluations(
            frozenset(),
            frozenset(),
            frozenset(),
        )
        self.assertEqual(first.incremental_cost(empty), 5)
        self.assertEqual(second.incremental_cost(empty), 7)
        self.assertEqual(second.incremental_cost(first), 2)

    def test_graph_edge_cache_retains_unsupported_results(self) -> None:
        context = SimpleNamespace(edge_support_cache={})

        with patch.object(
            sequence_search,
            "sequence_graph_edge_is_interval_feasible",
            return_value=False,
        ) as measure:
            first = sequence_search._cached_sequence_graph_edge_supported(
                1,
                2,
                (),
                context,
            )
            second = sequence_search._cached_sequence_graph_edge_supported(
                1,
                2,
                (),
                context,
            )

        self.assertFalse(first)
        self.assertFalse(second)
        measure.assert_called_once()

    def test_search_hint_only_drives_focused_dimension_options(self) -> None:
        search_scope = scope(
            width=900,
            height=100,
            leading=0.0,
            trailing=900.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(73.0, 191.0, 338.0, 529.0, 761.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        search_index = replace(
            sequence_search_index(search_scope, ()),
            width_hypotheses=(),
        )
        captured: list[tuple[MeasuredFrameConstraint, ...]] = []

        def capture(options, *_args, **_kwargs):
            captured.append(options)
            return sequence_search.MeasuredFrameSequenceSearchResult(
                (),
                0,
                False,
            )

        with patch.object(
            sequence_search,
            "measured_frame_sequences",
            side_effect=capture,
        ):
            solve_frame_sequence(
                search_index,
                search_scope,
                shared_short_axis_plan(search_scope),
                3,
                dimensions(3.0, 1.0),
                content(width=900, height=100, runs=((0, 900),)),
                10_000,
                strip_mode="partial",
                nominal_count=6,
            )

        self.assertTrue(captured)
        self.assertTrue(
            all(
                any(
                    edge.basis == FrameBoundarySource.DIMENSION_CONSTRAINED
                    for option in options
                    for edge in (option.leading, option.trailing)
                )
                for options in captured
            )
        )

if __name__ == "__main__":
    unittest.main()
