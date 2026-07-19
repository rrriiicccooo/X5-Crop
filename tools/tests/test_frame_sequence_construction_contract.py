from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.tests.frame_slot_solver_support import (
    content,
    path,
    scope,
    separator,
    sequence_search_index,
)
from x5crop.detection.physical import frame_sequence_candidates as candidate_builds
from x5crop.detection.physical import frame_sequence_common_width as width_resolution
from x5crop.detection.physical import frame_sequence_construction as construction
from x5crop.detection.physical import frame_sequence_measurements as measurements
from x5crop.detection.physical import (
    frame_sequence_separator_assignment as separator_assignment,
)
from x5crop.detection.physical import model as physical_model
from x5crop.detection.physical.frame_sequence_common_width import (
    CommonWidthHypothesis,
    DimensionPlacementHypothesis,
    measured_width_hypotheses,
)
from x5crop.detection.physical.frame_sequence_construction import (
    _dimension_frame_constraints,
    _measured_frame_search_space,
    _measured_sequence_build,
)
from x5crop.detection.physical.frame_sequence_measurements import (
    EdgeConstraint,
    MeasuredFrameConstraint,
)
from x5crop.detection.physical.model import (
    BoundaryGeometryState,
    FrameBoundarySource,
)
from x5crop.detection.physical.short_axis import shared_short_axis_plan
from x5crop.domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    InterFrameSpacingBasis,
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


class FrameSequenceConstructionContractTest(unittest.TestCase):
    def test_search_hint_cannot_select_canonical_observation_provenance(
        self,
    ) -> None:
        def edge(quality: float) -> SimpleNamespace:
            return SimpleNamespace(
                position=PixelInterval.exact(0.0),
                external_side=None,
                state=EvidenceState.UNAVAILABLE,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                separator=None,
                path=object(),
                observation_quality=quality,
            )

        def option(*, quality: float, hint_residual: float) -> SimpleNamespace:
            leading = edge(quality)
            trailing = SimpleNamespace(
                **{
                    **vars(leading),
                    "position": PixelInterval.exact(100.0),
                }
            )
            return SimpleNamespace(
                leading=leading,
                trailing=trailing,
                full_width_hypothesis_admissible=True,
                search_order_residual=hint_residual,
                frame_width_hint_residual=hint_residual,
            )

        measured = option(quality=1.0, hint_residual=10.0)
        merely_hinted = option(quality=0.1, hint_residual=0.0)

        canonical = construction._canonical_measured_frame_constraints(
            (measured, merely_hinted)
        )

        self.assertEqual(canonical, (measured,))

    def test_weak_separator_edges_are_geometry_hypotheses_not_hard_support(
        self,
    ) -> None:
        search_scope = scope(
            width=320,
            height=100,
            leading=0.0,
            trailing=320.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        weak = separator(100.0, 120.0, plan, supported=False)

        geometry_leading, geometry_trailing = (
            construction._separator_geometry_edge_candidates(
                (weak,),
                search_scope,
            )
        )
        hard_leading, hard_trailing = construction._separator_edge_candidates(
            (weak,),
            search_scope,
        )

        self.assertEqual(hard_leading, ())
        self.assertEqual(hard_trailing, ())
        self.assertEqual(
            geometry_leading[0][0].position,
            PixelInterval.exact(120.0),
        )
        self.assertEqual(
            geometry_trailing[0][0].position,
            PixelInterval.exact(100.0),
        )
        self.assertEqual(geometry_leading[0][0].state, EvidenceState.UNAVAILABLE)
        self.assertEqual(geometry_trailing[0][0].state, EvidenceState.UNAVAILABLE)

    def test_frame_width_hint_orders_but_does_not_delete_recurring_widths(
        self,
    ) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plausible = width_resolution.RecurringBoundaryWidthHypothesis(
            PixelInterval(100.0, 102.0),
            4,
        )
        frequent_texture = width_resolution.RecurringBoundaryWidthHypothesis(
            PixelInterval(20.0, 21.0),
            9,
        )
        search_index = replace(
            sequence_search_index(search_scope),
            recurring_width_hypotheses=(frequent_texture, plausible),
        )

        search_space = _measured_frame_search_space(
            search_index,
            (PixelInterval.exact(120.0), PixelInterval(98.0, 104.0)),
            PixelInterval(98.0, 104.0),
            None,
        )

        self.assertEqual(search_space.recurring_width_hypotheses[0], plausible)
        self.assertEqual(
            set(search_space.recurring_width_hypotheses),
            {plausible, frequent_texture},
        )
        placements = construction._ordered_dimension_placement_hypotheses(
            search_space,
            (),
            None,
            supported_separator_seed_available=False,
        )
        self.assertEqual(placements[0].width_px, plausible.width_px)

    def test_separator_spacing_hint_precedes_short_axis_width_hint(
        self,
    ) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        separator_aligned = width_resolution.RecurringBoundaryWidthHypothesis(
            PixelInterval(100.0, 104.0),
            4,
        )
        short_axis_aligned = width_resolution.RecurringBoundaryWidthHypothesis(
            PixelInterval(126.0, 132.0),
            5,
        )
        search_index = replace(
            sequence_search_index(search_scope),
            recurring_width_hypotheses=(
                short_axis_aligned,
                separator_aligned,
            ),
        )

        search_space = _measured_frame_search_space(
            search_index,
            (PixelInterval(98.0, 105.0), PixelInterval(124.0, 134.0)),
            PixelInterval(124.0, 134.0),
            None,
        )

        self.assertEqual(
            search_space.recurring_width_hypotheses[0],
            separator_aligned,
        )

    def test_separator_run_width_is_search_only_until_slots_are_bound(self) -> None:
        search_scope = scope(
            width=440,
            height=100,
            leading=0.0,
            trailing=440.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (100.0, 110.0),
                (210.0, 220.0),
                (320.0, 330.0),
            )
        )

        self.assertEqual(
            construction._raw_separator_frame_width_search_hints(
                supports,
                search_scope,
                4,
            ),
            (PixelInterval.exact(100.0),),
        )
        self.assertEqual(
            sequence_search_index(search_scope, supports).width_hypotheses,
            (),
        )

    def test_sparse_separator_subset_does_not_claim_adjacent_width_hint(
        self,
    ) -> None:
        search_scope = scope(
            width=650,
            height=100,
            leading=0.0,
            trailing=650.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        sparse_supports = tuple(
            separator(start, start + 10.0, plan, supported=True)
            for start in (100.0, 320.0, 540.0)
        )

        self.assertEqual(
            construction._raw_separator_frame_width_search_hints(
                sparse_supports,
                search_scope,
                6,
            ),
            (),
        )

    def test_width_contributor_index_is_reused_across_count_hypotheses(
        self,
    ) -> None:
        search_scope = scope(
            width=650,
            height=100,
            leading=0.0,
            trailing=650.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        repeated = width_resolution.repeated_width_contributor_sets

        with patch.object(
            width_resolution,
            "repeated_width_contributor_sets",
            wraps=repeated,
        ) as contributor_search:
            search_index = sequence_search_index(search_scope)
            preparation_calls = contributor_search.call_count
            _measured_frame_search_space(
                search_index,
                (PixelInterval.exact(100.0),),
                PixelInterval.exact(100.0),
                None,
            )
            _measured_frame_search_space(
                search_index,
                (PixelInterval.exact(100.0),),
                PixelInterval.exact(100.0),
                None,
            )

        self.assertGreater(preparation_calls, 0)
        self.assertEqual(contributor_search.call_count, preparation_calls)

    def test_dimension_search_uses_observed_separator_incumbent(self) -> None:
        class Build:
            __hash__ = object.__hash__

            def __init__(self) -> None:
                leading = SimpleNamespace(position=PixelInterval.exact(0.0))
                trailing = SimpleNamespace(position=PixelInterval.exact(100.0))
                self.slots = (
                    SimpleNamespace(leading=leading, trailing=trailing),
                )
                self.objectives = candidate_builds.SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=4,
                    internal_boundary_measurement_quality=4.0,
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                )

        search_scope = scope(
            width=100,
            height=100,
            leading=0.0,
            trailing=100.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        prepared_search_index = sequence_search_index(search_scope)
        search_space = construction._MeasuredFrameSearchSpace(
            leading_candidates=(),
            trailing_candidates=(),
            observed_constraints=(),
            width_hypotheses=(
                CommonWidthHypothesis(
                    PixelInterval.exact(100.0),
                    (ObservationId("measured_width"),),
                    2,
                ),
            ),
            recurring_width_hypotheses=(),
        )
        incumbent_inputs: list[int] = []

        def measured_builds(*args, **kwargs):
            incumbent_inputs.append(kwargs["minimum_supported_separator_count"])
            return (
                ((Build(),) if len(incumbent_inputs) == 1 else ()),
                1,
                False,
            )

        with (
            patch.object(
                construction,
                "_measured_frame_search_space",
                return_value=search_space,
            ),
            patch.object(
                construction,
                "_dimension_frame_constraints",
                return_value=(SimpleNamespace(),),
            ),
            patch.object(
                construction,
                "_canonical_measured_frame_constraints",
                return_value=(SimpleNamespace(),),
            ),
            patch.object(
                construction,
                "_complete_separator_sequence_builds_dominate_dimension_inference",
                return_value=False,
            ),
            patch.object(
                construction,
                "_measured_builds_for_options",
                side_effect=measured_builds,
            ),
        ):
            construction._measured_path_builds(
                search_scope,
                prepared_search_index,
                (plan.span,),
                (PixelInterval.exact(100.0),),
                PixelInterval.exact(100.0),
                6,
                content(width=100, height=100),
                100,
                (
                    PixelInterval.exact(100.0),
                    PixelInterval.exact(101.0),
                ),
                physical_scale_constraint=None,
                allow_nominal_slot_sized_gap=False,
            )

        self.assertEqual(incumbent_inputs[0], 0)
        self.assertTrue(all(value == 4 for value in incumbent_inputs[1:]))

    def test_separator_incumbent_prevents_raw_seed_fallback(self) -> None:
        class Build:
            __hash__ = object.__hash__

            def __init__(self) -> None:
                leading = SimpleNamespace(position=PixelInterval.exact(0.0))
                trailing = SimpleNamespace(position=PixelInterval.exact(100.0))
                self.slots = (
                    SimpleNamespace(leading=leading, trailing=trailing),
                )
                self.objectives = candidate_builds.SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=1,
                    internal_boundary_measurement_quality=1.0,
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                )

        search_scope = scope(
            width=220,
            height=100,
            leading=0.0,
            trailing=220.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        support = separator(100.0, 110.0, plan, supported=True)
        prepared_search_index = sequence_search_index(
            search_scope,
            (support,),
        )
        geometry_leading, geometry_trailing = (
            construction._separator_geometry_edge_candidates(
                prepared_search_index.separator_supports.canonical_supports,
                search_scope,
            )
        )
        search_space = construction._MeasuredFrameSearchSpace(
            leading_candidates=geometry_leading,
            trailing_candidates=geometry_trailing,
            observed_constraints=(),
            width_hypotheses=(),
            recurring_width_hypotheses=(
                width_resolution.RecurringBoundaryWidthHypothesis(
                    PixelInterval.exact(100.0),
                    2,
                ),
                width_resolution.RecurringBoundaryWidthHypothesis(
                    PixelInterval.exact(105.0),
                    2,
                ),
            ),
        )
        calls: list[int] = []

        def measured_builds(*args, **kwargs):
            calls.append(kwargs["minimum_supported_separator_count"])
            return (((Build(),) if len(calls) == 1 else ()), 1, False)

        with (
            patch.object(
                construction,
                "_measured_frame_search_space",
                return_value=search_space,
            ),
            patch.object(
                construction,
                "_dimension_frame_constraints",
                return_value=(SimpleNamespace(),),
            ),
            patch.object(
                construction,
                "_canonical_measured_frame_constraints",
                return_value=(SimpleNamespace(),),
            ),
            patch.object(
                construction,
                "_complete_separator_sequence_builds_dominate_dimension_inference",
                return_value=False,
            ),
            patch.object(
                construction,
                "_measured_builds_for_options",
                side_effect=measured_builds,
            ),
        ):
            construction._measured_path_builds(
                search_scope,
                prepared_search_index,
                (plan.span,),
                (PixelInterval.exact(100.0),),
                PixelInterval.exact(100.0),
                2,
                content(width=220, height=100),
                100,
                (),
                physical_scale_constraint=None,
                allow_nominal_slot_sized_gap=False,
            )

        self.assertEqual(calls, [0, 1])

    def test_dimension_width_hypotheses_use_separate_bounded_graph_branches(
        self,
    ) -> None:
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
        prepared_search_index = sequence_search_index(search_scope)
        search_space = construction._MeasuredFrameSearchSpace(
            leading_candidates=(),
            trailing_candidates=(),
            observed_constraints=(),
            width_hypotheses=(
                CommonWidthHypothesis(
                    PixelInterval.exact(300.0),
                    (ObservationId("measured_width"),),
                    2,
                ),
            ),
            recurring_width_hypotheses=(),
        )
        branch_widths: list[tuple[PixelInterval, ...]] = []

        def measured_builds(*args, **kwargs):
            branch_widths.append(args[6])
            return (), 1, False

        with (
            patch.object(
                construction,
                "_measured_frame_search_space",
                return_value=search_space,
            ),
            patch.object(
                construction,
                "_dimension_frame_constraints",
                return_value=(SimpleNamespace(),),
            ),
            patch.object(
                construction,
                "_canonical_measured_frame_constraints",
                return_value=(SimpleNamespace(),),
            ),
            patch.object(
                construction,
                "_measured_builds_for_options",
                side_effect=measured_builds,
            ),
        ):
            construction._measured_path_builds(
                search_scope,
                prepared_search_index,
                (plan.span,),
                (PixelInterval.exact(100.0),),
                PixelInterval.exact(100.0),
                4,
                content(width=400, height=100),
                100,
                (PixelInterval.exact(400.0),),
                physical_scale_constraint=None,
                allow_nominal_slot_sized_gap=False,
            )

        self.assertEqual(
            branch_widths,
            [
                (PixelInterval.exact(300.0),),
                (PixelInterval.exact(300.0),),
                (PixelInterval.exact(400.0),),
            ],
        )

    def test_frame_sized_unexplained_gap_cannot_form_direct_sequence(self) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 400.0),
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

        constraints = tuple(
            MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(end),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )
            for start, end in ((0.0, 100.0), (110.0, 210.0), (400.0, 500.0))
        )

        self.assertIsNone(
            _measured_sequence_build(
                constraints,
                shared_short_axis_plan(search_scope).span,
                search_scope.holder_safety.box,
                allow_nominal_slot_sized_gap=False,
            )
        )

    def test_dimension_inference_does_not_translate_one_anchor_across_slots(
        self,
    ) -> None:
        search_scope = scope(
            width=300,
            height=100,
            leading=0.0,
            trailing=300.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 200.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        long_paths = {
            path.position.midpoint: path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
        }

        def edge(position: float) -> EdgeConstraint:
            observation = long_paths[position]
            return EdgeConstraint(
                position=observation.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                path=observation,
            )

        leading = edge(0.0)
        first_trailing = edge(100.0)
        focused_trailing = edge(200.0)
        hypothesis = DimensionPlacementHypothesis(
            width_px=PixelInterval.exact(100.0),
            boundary_anchors=(
                leading.provenance.observation_id,
                first_trailing.provenance.observation_id,
            ),
        )

        constraints = _dimension_frame_constraints(
            ((leading, True),),
            ((first_trailing, False), (focused_trailing, False)),
            ((leading, True),),
            ((first_trailing, False), (focused_trailing, False)),
            (hypothesis,),
            PixelInterval(0.0, 300.0),
            (PixelInterval.exact(100.0),),
            PixelInterval.exact(100.0),
        )

        self.assertTrue(
            any(
                constraint.leading.position == PixelInterval.exact(0.0)
                and constraint.trailing.position == PixelInterval.exact(100.0)
                for constraint in constraints
            )
        )
        focused = next(
            constraint
            for constraint in constraints
            if constraint.leading.position == PixelInterval.exact(100.0)
            and constraint.trailing.position == PixelInterval.exact(200.0)
        )
        self.assertEqual(focused.leading.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(focused.leading.basis, FrameBoundarySource.DIMENSION_CONSTRAINED)
        self.assertEqual(focused.trailing.state, EvidenceState.UNAVAILABLE)

    def test_focused_raw_boundary_does_not_delete_dimension_hypothesis(
        self,
    ) -> None:
        inferred = EdgeConstraint(
            position=PixelInterval(95.0, 105.0),
            basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
            state=EvidenceState.UNAVAILABLE,
            geometry_state=BoundaryGeometryState.RESOLVED,
            provenance=MeasurementProvenance(
                MeasurementIdentity.FRAME_GEOMETRY,
                ObservationId("focused_dimension_edge"),
                (),
                "synthetic focused dimension edge",
            ),
        )
        raw_path = next(
            path
            for path in scope(
                width=200,
                height=100,
                leading=0.0,
                trailing=200.0,
                top=0.0,
                bottom=100.0,
                internal_paths=(100.0,),
                holder_sides=_ALL_HOLDER_SIDES,
            ).raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
            and path.position == PixelInterval.exact(100.0)
        )
        observed = EdgeConstraint(
            position=raw_path.position,
            basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            state=EvidenceState.UNAVAILABLE,
            geometry_state=BoundaryGeometryState.RESOLVED,
            provenance=raw_path.provenance,
            path=raw_path,
        )

        focused = construction._focused_edge_constraints(
            inferred,
            ((observed, False),),
        )

        self.assertEqual(focused, (observed, inferred))

    def test_unassigned_gray_paths_cannot_create_frame_width_search_authority(
        self,
    ) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 200.0, 300.0, 400.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        paths = {
            path.position.midpoint: path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
        }

        def edge(position: float) -> EdgeConstraint:
            path = paths[position]
            return EdgeConstraint(
                position=path.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=path.provenance,
                path=path,
            )

        constraints = (
            MeasuredFrameConstraint(
                leading=edge(100.0),
                trailing=edge(200.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            MeasuredFrameConstraint(
                leading=edge(300.0),
                trailing=edge(400.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
        )

        self.assertEqual(measured_width_hypotheses(constraints), ())
        search_space = _measured_frame_search_space(
            sequence_search_index(search_scope),
            (PixelInterval.exact(100.0),),
            PixelInterval.exact(100.0),
            None,
        )
        self.assertEqual(search_space.width_hypotheses, ())
        self.assertFalse(
            hasattr(search_space, "observation_width_placement_hypotheses")
        )
        self.assertFalse(
            hasattr(search_space, "observation_width_search_intervals")
        )

    def test_disjoint_observed_frame_width_is_not_dimension_compatible(self) -> None:
        def observed_edge(
            minimum: float,
            maximum: float,
            label: str,
        ) -> EdgeConstraint:
            observation = path(
                BoundaryAxis.LONG,
                (minimum + maximum) / 2.0,
                label,
            )
            return EdgeConstraint(
                position=PixelInterval(minimum, maximum),
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                path=observation,
            )

        frame_width = PixelInterval(3_101.6, 3_170.0)
        refined = construction._refine_frame_edges(
            observed_edge(13_323.0, 13_352.0, "narrow_frame_leading"),
            observed_edge(16_390.0, 16_419.0, "narrow_frame_trailing"),
            frame_width,
            allow_underwidth=False,
        )

        self.assertIsNotNone(refined)
        assert refined is not None
        leading, trailing = refined
        constraint = MeasuredFrameConstraint(
            leading=leading,
            trailing=trailing,
            width_px=trailing.position.minus(leading.position),
            full_width_hypothesis_admissible=True,
            leading_holder_clip_supported=False,
            trailing_holder_clip_supported=False,
            search_order_residual=0.0,
        )
        self.assertFalse(
            construction._sequence_constraints_fit_physical_scale(
                (constraint,),
                physical_model.FrameWidthPhysicalScaleConstraint(
                    width_px=frame_width,
                    provenance=MeasurementProvenance(
                        root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
                        observation_id=ObservationId(
                            "physical_scale:disjoint_observed_width"
                        ),
                        dependencies=(
                            MeasurementIdentity.PHOTO_EDGES,
                            MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
                        ),
                        description="independent synthetic physical scale",
                    ),
                ),
            )
        )

    def test_unmeasured_overlapping_widths_remain_geometry_alternatives(
        self,
    ) -> None:
        search_scope = scope(
            width=340,
            height=100,
            leading=0.0,
            trailing=340.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )

        def edge(minimum: float, maximum: float, label: str) -> EdgeConstraint:
            return EdgeConstraint(
                position=PixelInterval(minimum, maximum),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic dimension boundary",
                ),
            )

        def constraint(
            leading: tuple[float, float],
            trailing: tuple[float, float],
            label: str,
        ) -> MeasuredFrameConstraint:
            width = PixelInterval(*trailing).minus(PixelInterval(*leading))
            return MeasuredFrameConstraint(
                leading=edge(*leading, f"{label}:leading"),
                trailing=edge(*trailing, f"{label}:trailing"),
                width_px=width,
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        shared = (
            constraint((0.0, 0.0), (100.0, 102.0), "first"),
            constraint((110.0, 110.0), (210.0, 212.0), "second"),
        )
        aligned = _measured_sequence_build(
            (*shared, constraint((220.0, 220.0), (318.0, 324.0), "aligned")),
            shared_short_axis_plan(search_scope).span,
            search_scope.holder_safety.box,
            allow_nominal_slot_sized_gap=False,
        )
        overcontained = _measured_sequence_build(
            (*shared, constraint((220.0, 220.0), (320.0, 328.0), "wide")),
            shared_short_axis_plan(search_scope).span,
            search_scope.holder_safety.box,
            allow_nominal_slot_sized_gap=False,
        )

        self.assertIsNotNone(aligned)
        self.assertIsNotNone(overcontained)
        assert aligned is not None
        assert overcontained is not None
        self.assertEqual(
            aligned.objectives.dimension_residual,
            0.0,
        )
        self.assertEqual(
            overcontained.objectives.dimension_residual,
            0.0,
        )
        alternatives = candidate_builds.physically_preferred_builds((overcontained, aligned))
        self.assertEqual(alternatives, (overcontained, aligned))

    def test_holder_contact_support_does_not_depend_on_width_search_hint(self) -> None:
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
        search_space = _measured_frame_search_space(
            sequence_search_index(search_scope),
            (PixelInterval.exact(50.0),),
            PixelInterval.exact(50.0),
            None,
        )
        holder_adjacent = next(
            constraint
            for constraint in search_space.observed_constraints
            if constraint.leading.position.intersects(PixelInterval.exact(0.0))
            and constraint.trailing.position.intersects(PixelInterval.exact(100.0))
        )

        self.assertTrue(holder_adjacent.leading_holder_clip_supported)
        self.assertEqual(
            holder_adjacent.leading.external_side,
            BoundarySide.LEADING,
        )

    def test_holder_endpoint_cannot_seed_interior_dimension_boundaries(self) -> None:
        search_scope = scope(
            width=330,
            height=100,
            leading=0.0,
            trailing=330.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        holder_band = separator(320.0, 330.0, plan, supported=True)
        trailing_endpoint, _ = separator_assignment.observed_band_edges(holder_band)
        trailing_endpoint = replace(
            trailing_endpoint,
            external_side=BoundarySide.TRAILING,
        )

        constraints = _dimension_frame_constraints(
            (),
            ((trailing_endpoint, True),),
            (),
            ((trailing_endpoint, True),),
            (
                DimensionPlacementHypothesis(
                    PixelInterval.exact(100.0),
                    (),
                ),
            ),
            PixelInterval(0.0, 330.0),
            (PixelInterval.exact(100.0),),
            PixelInterval.exact(100.0),
        )

        self.assertEqual(len(constraints), 1)
        self.assertEqual(constraints[0].leading.position, PixelInterval.exact(220.0))
        self.assertIs(constraints[0].trailing, trailing_endpoint)

    def test_unassigned_gray_paths_do_not_seed_supported_separator_search(
        self,
    ) -> None:
        search_scope = scope(
            width=660,
            height=100,
            leading=0.0,
            trailing=660.0,
            top=0.0,
            bottom=100.0,
            internal_paths=tuple(
                sorted(
                    {
                        *(float(value) for value in range(20, 641, 10)),
                        100.0,
                        110.0,
                        210.0,
                        220.0,
                        320.0,
                        330.0,
                        430.0,
                        440.0,
                        550.0,
                        650.0,
                    }
                )
            ),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (100.0, 110.0),
                (210.0, 220.0),
                (320.0, 330.0),
                (430.0, 440.0),
            )
        )

        search_index = sequence_search_index(search_scope, supports)
        search_space = _measured_frame_search_space(
            search_index,
            (PixelInterval.exact(100.0),),
            PixelInterval.exact(100.0),
            None,
        )
        geometry_leading, geometry_trailing = (
            construction._separator_geometry_edge_candidates(
                search_index.separator_supports.canonical_supports,
                search_scope,
            )
        )
        leading_candidates = tuple(
            dict.fromkeys((*search_space.leading_candidates, *geometry_leading))
        )
        trailing_candidates = tuple(
            dict.fromkeys((*search_space.trailing_candidates, *geometry_trailing))
        )
        seeds = construction._dimension_seed_candidates(
            (*leading_candidates, *trailing_candidates)
        )

        self.assertLess(
            len(seeds),
            len(leading_candidates) + len(trailing_candidates),
        )
        self.assertTrue(
            all(
                edge.external_side is not None
                or (
                    edge.separator_cross_axis is not None
                    and measurements.separator_edge_path_is_supported(edge)
                )
                for edge, _ in seeds
            )
        )

    def test_unproven_observation_edge_does_not_prune_dimension_search(
        self,
    ) -> None:
        leading = SimpleNamespace(
            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            independently_observed=True,
            position=PixelInterval.exact(0.0),
        )
        trailing = SimpleNamespace(
            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            independently_observed=False,
            position=PixelInterval.exact(100.0),
        )
        build = SimpleNamespace(
            slots=(SimpleNamespace(leading=leading, trailing=trailing),),
            spacings=(),
            separator_bindings=(),
        )

        self.assertFalse(
            construction._complete_separator_sequence_builds_dominate_dimension_inference(
                (build,),
                content(width=100, height=100),
            )
        )

    def test_unresolved_internal_spacing_does_not_prune_dimension_search(
        self,
    ) -> None:
        def boundary(position: float) -> SimpleNamespace:
            return SimpleNamespace(
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                independently_observed=True,
                position=PixelInterval.exact(position),
            )

        build = SimpleNamespace(
            slots=(
                SimpleNamespace(leading=boundary(0.0), trailing=boundary(40.0)),
                SimpleNamespace(leading=boundary(60.0), trailing=boundary(100.0)),
            ),
            spacings=(
                SimpleNamespace(
                    basis=InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
                ),
            ),
            separator_bindings=(),
        )

        self.assertFalse(
            construction._complete_separator_sequence_builds_dominate_dimension_inference(
                (build,),
                content(width=100, height=100),
            )
        )

    def test_observed_spacing_without_separator_sequence_keeps_dimension_search(
        self,
    ) -> None:
        def boundary(position: float) -> SimpleNamespace:
            return SimpleNamespace(
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                independently_observed=True,
                position=PixelInterval.exact(position),
            )

        build = SimpleNamespace(
            slots=(
                SimpleNamespace(leading=boundary(0.0), trailing=boundary(40.0)),
                SimpleNamespace(leading=boundary(60.0), trailing=boundary(100.0)),
            ),
            spacings=(
                SimpleNamespace(basis=InterFrameSpacingBasis.OBSERVED),
            ),
            separator_bindings=(),
        )

        self.assertFalse(
            construction._complete_separator_sequence_builds_dominate_dimension_inference(
                (build,),
                content(width=100, height=100),
            )
        )
