from __future__ import annotations

from dataclasses import fields
from typing import get_type_hints
import unittest
from unittest.mock import patch
from dataclasses import replace

import numpy as np

from x5crop.cache import MeasurementCache, MeasurementRegionKey
from x5crop.cache.separator import cached_separator_profile_measurement
from x5crop.domain import (
    Box,
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from x5crop.image.separator_profile import (
    SeparatorProfileMeasurement,
    SeparatorProfileParameters,
)
from x5crop.image.content import ContentRegionObservation
from x5crop.geometry.layout import work_gray
from x5crop.image.statistics import ImageMeasurementStatisticsParameters, image_measurement_statistics
from x5crop.configuration.bundle import DetectionConfigurationBundle
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.evidence.content.frame_content import frame_content_evidence
from tools.tests.physical_gate_support import candidate_fixture
from x5crop.runtime.analysis_identity import detection_configuration_fingerprint
from x5crop.configuration.boundary import BoundaryPathParameters
from x5crop.detection.candidate.proposal.sequence import cached_boundary_measurements
from x5crop.detection.physical import frame_sequence_measurements as measurements
from x5crop.detection.physical import frame_sequence_search as sequence_search
from x5crop.detection.physical.model import (
    BoundaryGeometryState,
    FrameBoundarySource,
)


def _cache() -> MeasurementCache:
    gray = np.zeros((80, 240), dtype=np.uint8)
    return MeasurementCache(
        "horizontal",
        gray,
        gray,
        gray.astype(np.float32),
        image_measurement_statistics(gray, ImageMeasurementStatisticsParameters()),
        0.0,
    )


def _profile_measurement(width: int) -> SeparatorProfileMeasurement:
    score = np.arange(width, dtype=np.float32)
    return SeparatorProfileMeasurement(score, score.copy(), 1, 1)


class DetectionCachePerformanceContractTest(unittest.TestCase):
    def test_backward_graph_sweep_skips_prefix_unreachable_options(self) -> None:
        def edge(position: float, label: str):
            return measurements.EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic backward-sweep graph edge",
                ),
            )

        def frame(start: float, label: str):
            return measurements.MeasuredFrameConstraint(
                leading=edge(start, f"{label}:leading"),
                trailing=edge(start + 100.0, f"{label}:trailing"),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        ordered = (
            frame(0.0, "first"),
            frame(110.0, "reachable-middle"),
            frame(0.0, "prefix-unreachable-middle"),
            frame(220.0, "last"),
        )
        grouped = (
            ((0, ordered[0]),),
            ((1, ordered[1]), (2, ordered[2])),
            ((3, ordered[3]),),
        )
        context = sequence_search.sequence_graph_context(
            ordered,
            ContentRegionObservation(
                region=Box(0, 0, 320, 100),
                reliable_runs=(),
                position_uncertainty_px=0,
            ),
            allow_nominal_slot_sized_gap=True,
        )
        successor_inputs: list[tuple[int, ...]] = []
        reachable_successors = sequence_search._reachable_successors

        def capture_successor_inputs(current_indexes, *args):
            successor_inputs.append(current_indexes)
            return reachable_successors(current_indexes, *args)

        with patch.object(
            sequence_search,
            "_reachable_successors",
            side_effect=capture_successor_inputs,
        ):
            feasibility = sequence_search._sequence_graph_feasibility(
                grouped,
                ordered,
                context,
            )

        self.assertIsNotNone(feasibility)
        self.assertEqual(successor_inputs[0], (1,))

    def test_graph_edge_feasibility_uses_interval_bounds_without_allocations(
        self,
    ) -> None:
        def edge(position: float, label: str):
            return measurements.EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic allocation-free graph edge",
                ),
            )

        def frame(start: float, index: int):
            return measurements.MeasuredFrameConstraint(
                leading=edge(start, f"allocation-leading-{index}"),
                trailing=edge(start + 100.0, f"allocation-trailing-{index}"),
                width_px=PixelInterval(99.0, 101.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        ordered = (frame(0.0, 0), frame(110.0, 1))
        context = sequence_search.sequence_graph_context(
            ordered,
            ContentRegionObservation(
                region=Box(0, 0, 210, 100),
                reliable_runs=(),
                position_uncertainty_px=0,
            ),
            allow_nominal_slot_sized_gap=False,
        )

        with (
            patch.object(
                PixelInterval,
                "intersection",
                autospec=True,
                side_effect=PixelInterval.intersection,
            ) as intersection,
            patch.object(
                PixelInterval,
                "minus",
                autospec=True,
                side_effect=PixelInterval.minus,
            ) as minus,
        ):
            supported = sequence_search.sequence_graph_edge_is_interval_feasible(
                0,
                1,
                ordered,
                context,
            )

        self.assertTrue(supported)
        intersection.assert_not_called()
        minus.assert_not_called()

    def test_report_records_are_not_reused_as_detection_cache(self) -> None:
        from tools.tests.architecture_contracts import PROJECT_ROOT
        from x5crop.report.validation import CURRENT_REPORT_SECTIONS
        from x5crop.run_config import RunConfig
        from x5crop.runtime.options import RuntimeOptions

        workflow = (PROJECT_ROOT / "x5crop/runtime/workflow.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("result_from_reusable_analysis", workflow)
        self.assertNotIn("reuse_analysis", {field.name for field in fields(RunConfig)})
        self.assertNotIn(
            "reuse_analysis",
            {field.name for field in fields(RuntimeOptions)},
        )
        self.assertNotIn("analysis_reuse", CURRENT_REPORT_SECTIONS)

    def test_graph_layer_ranking_stops_after_a_unique_physical_predecessor(
        self,
    ) -> None:
        def edge(position: float, label: str):
            return measurements.EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic graph performance edge",
                ),
            )

        def frame(start: float, index: int):
            return measurements.MeasuredFrameConstraint(
                leading=edge(start, f"performance-leading-{index}"),
                trailing=edge(start + 100.0, f"performance-trailing-{index}"),
                width_px=PixelInterval(99.0, 101.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        previous_options = tuple(
            frame(float(index), index) for index in range(512)
        )
        current = frame(1_000.0, 512)
        ordered = (*previous_options, current)
        context = sequence_search.sequence_graph_context(
            ordered,
            ContentRegionObservation(
                region=Box(0, 0, 1_100, 100),
                reliable_runs=(),
                position_uncertainty_px=0,
            ),
            allow_nominal_slot_sized_gap=True,
        )
        states = {
            index: sequence_search.GraphPathState(
                observation_candidate_count=0,
                supported_separator_count=0,
                internal_measurement_quality=0.0,
                uncorroborated_overlap_extent_px=float(index),
                frame_sized_unexplained_gap_count=0,
                unexplained_spacing_extent_px=0.0,
                uncorroborated_contact_count=0,
                frame_width_hint_residual=0.0,
                boundary_uncertainty_px=0.0,
                external_leading_quality=0.0,
                coordinate_key=(-float(index),),
                predecessor=None,
            )
            for index in range(len(previous_options))
        }
        previous = sequence_search.graph_layer_state_index(
            states,
            ordered,
            context,
        )

        intersection_calls = 0
        original_intersection = PixelInterval.intersection

        def counted_intersection(
            left: PixelInterval,
            right: PixelInterval,
        ) -> PixelInterval | None:
            nonlocal intersection_calls
            intersection_calls += 1
            return original_intersection(left, right)

        with (
            patch.object(PixelInterval, "intersection", counted_intersection),
            patch.object(
                sequence_search,
                "_retain_graph_rank",
                wraps=sequence_search._retain_graph_rank,
            ) as rank_step,
        ):
            selected = sequence_search.best_graph_predecessors(
                (len(previous_options),),
                previous,
                ordered,
                context,
            )

        self.assertIn(len(previous_options), selected)
        self.assertLessEqual(intersection_calls, 2)
        self.assertEqual(rank_step.call_count, 1)
        self.assertFalse(hasattr(sequence_search, "best_graph_predecessor"))

    def test_graph_rank_materializes_only_still_ambiguous_rows(self) -> None:
        remaining = np.asarray(
            (
                (True, False, False),
                (True, True, False),
            ),
            dtype=bool,
        )
        values = np.asarray(
            (
                (0.0, 2.0, 1.0),
                (2.0, 1.0, 0.0),
            ),
            dtype=np.float64,
        )

        ambiguous_rows = np.asarray((1,), dtype=np.int64)
        with patch.object(np, "where", wraps=np.where) as materialize:
            retained, next_ambiguous_rows = sequence_search._retain_graph_rank(
                remaining,
                values,
                ambiguous_rows,
                maximize=True,
            )

        self.assertTrue(
            np.array_equal(
                retained,
                np.asarray(
                    (
                        (True, False, False),
                        (True, False, False),
                    ),
                    dtype=bool,
                ),
            )
        )
        self.assertEqual(len(next_ambiguous_rows), 0)
        self.assertEqual(materialize.call_args.args[0].shape, (1, 3))

    def test_reachability_reuses_identical_subset_order_within_one_pass(
        self,
    ) -> None:
        def edge(position: float, label: str):
            return measurements.EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic reachability-order edge",
                ),
            )

        def frame(start: float, label: str):
            return measurements.MeasuredFrameConstraint(
                leading=edge(start, f"{label}:leading"),
                trailing=edge(start + 100.0, f"{label}:trailing"),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        predecessor = frame(0.0, "predecessor")
        predecessor_currents = tuple(
            frame(110.0 + offset * 10.0, f"predecessor-current-{offset}")
            for offset in range(3)
        )
        successor_currents = tuple(
            frame(300.0 + offset * 10.0, f"successor-current-{offset}")
            for offset in range(3)
        )
        successor = frame(500.0, "successor")
        ordered = (
            predecessor,
            *predecessor_currents,
            *successor_currents,
            successor,
        )
        context = sequence_search.sequence_graph_context(
            ordered,
            ContentRegionObservation(
                region=Box(0, 0, 600, 100),
                reliable_runs=(),
                position_uncertainty_px=0,
            ),
            allow_nominal_slot_sized_gap=True,
        )
        separator_keys = {
            ObservationId(f"predecessor-current-{offset}:leading"):
                ObservationId(f"predecessor-separator-{offset}")
            for offset in range(3)
        } | {
            ObservationId(f"successor-current-{offset}:trailing"):
                ObservationId(f"successor-separator-{offset}")
            for offset in range(3)
        }
        original_sorted = sorted
        sort_calls = 0

        def counted_sorted(*args, **kwargs):
            nonlocal sort_calls
            sort_calls += 1
            return original_sorted(*args, **kwargs)

        def separator_key(boundary):
            return separator_keys.get(boundary.provenance.observation_id)

        with (
            patch("builtins.sorted", side_effect=counted_sorted),
            patch.object(
                sequence_search,
                "_separator_boundary_key",
                side_effect=separator_key,
            ),
        ):
            predecessors = sequence_search._reachable_predecessors(
                (0,),
                (1, 2, 3),
                ordered,
                context,
            )
            successors = sequence_search._reachable_successors(
                (4, 5, 6),
                (7,),
                ordered,
                context,
            )

        self.assertEqual(set(predecessors), {1, 2, 3})
        self.assertEqual(set(successors), {4, 5, 6})
        self.assertLessEqual(sort_calls, 14)

    def test_graph_reachability_uses_one_cached_feasibility_check_per_edge(
        self,
    ) -> None:
        def edge(position: float, label: str):
            return measurements.EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic graph reachability edge",
                ),
            )

        def frame(start: float, index: int):
            return measurements.MeasuredFrameConstraint(
                leading=edge(start, f"reachability-leading-{index}"),
                trailing=edge(start + 100.0, f"reachability-trailing-{index}"),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        ordered = (frame(0.0, 0), frame(110.0, 1))
        context = sequence_search.sequence_graph_context(
            ordered,
            ContentRegionObservation(
                region=Box(0, 0, 210, 100),
                reliable_runs=(),
                position_uncertainty_px=0,
            ),
            allow_nominal_slot_sized_gap=True,
        )

        with patch.object(
            sequence_search,
            "sequence_graph_edge_is_interval_feasible",
            wraps=sequence_search.sequence_graph_edge_is_interval_feasible,
        ) as feasibility:
            previous_order = sequence_search._predecessor_reachability_order(
                (0,), ordered, context
            )
            assert previous_order is not None
            reachable = sequence_search._reachable_predecessors_for_orders(
                previous_order,
                sequence_search._predecessor_current_order((1,), ordered),
                ordered,
                context,
            )

        self.assertEqual(reachable, {1: 0})
        self.assertEqual(feasibility.call_count, 1)

    def test_graph_fallback_order_is_materialized_once_per_boundary(self) -> None:
        def edge(position: float, label: str):
            return measurements.EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic graph fallback-order edge",
                ),
            )

        def frame(start: float, index: int):
            return measurements.MeasuredFrameConstraint(
                leading=edge(start, f"fallback-leading-{index}"),
                trailing=edge(start + 10.0, f"fallback-trailing-{index}"),
                width_px=PixelInterval.exact(10.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        preceding = tuple(frame(float(index), index) for index in range(8))
        following = tuple(
            frame(100.0 + float(index), index + len(preceding))
            for index in range(16)
        )
        ordered = (*preceding, *following)
        preceding_indexes = tuple(range(len(preceding)))
        following_indexes = tuple(range(len(preceding), len(ordered)))
        context = sequence_search.sequence_graph_context(
            ordered,
            ContentRegionObservation(
                region=Box(0, 0, 140, 100),
                reliable_runs=(),
                position_uncertainty_px=0,
            ),
            allow_nominal_slot_sized_gap=True,
        )

        with (
            patch.object(
                sequence_search,
                "sorted",
                wraps=sorted,
                create=True,
            ) as ordering,
            patch.object(
                sequence_search,
                "_cached_sequence_graph_edge_supported",
                return_value=False,
            ),
        ):
            previous_order = sequence_search._predecessor_reachability_order(
                preceding_indexes,
                ordered,
                context,
            )
            assert previous_order is not None
            self.assertEqual(
                sequence_search._reachable_predecessors_for_orders(
                    previous_order,
                    sequence_search._predecessor_current_order(
                        following_indexes,
                        ordered,
                    ),
                    ordered,
                    context,
                ),
                {},
            )
            self.assertLessEqual(ordering.call_count, 4)
            ordering.reset_mock()
            following_order = sequence_search._successor_reachability_order(
                following_indexes,
                ordered,
                context,
            )
            assert following_order is not None
            self.assertEqual(
                sequence_search._reachable_successors_for_orders(
                    sequence_search._successor_current_order(
                        preceding_indexes,
                        ordered,
                    ),
                    following_order,
                    ordered,
                    context,
                ),
                {},
            )
            self.assertLessEqual(ordering.call_count, 4)

    def test_contact_alternative_does_not_require_a_second_graph_optimization(
        self,
    ) -> None:
        def edge(position: float, label: str):
            return measurements.EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic graph contact edge",
                ),
            )

        def frame(start: float, label: str):
            return measurements.MeasuredFrameConstraint(
                leading=edge(start, f"{label}-leading"),
                trailing=edge(start + 100.0, f"{label}-trailing"),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        first = frame(0.0, "first")
        contact = frame(100.0, "contact")
        separated = frame(110.0, "separated")
        last = frame(220.0, "last")
        ordered = (first, contact, separated, last)
        grouped = (
            ((0, first),),
            ((1, contact), (2, separated)),
            ((3, last),),
        )
        context = sequence_search.sequence_graph_context(
            ordered,
            ContentRegionObservation(
                region=Box(0, 0, 320, 100),
                reliable_runs=(),
                position_uncertainty_px=0,
            ),
            allow_nominal_slot_sized_gap=True,
        )

        with patch.object(
            sequence_search,
            "sequence_graph_best_path",
            wraps=sequence_search.sequence_graph_best_path,
        ) as best_path:
            witnesses = sequence_search.sequence_graph_witnesses(
                grouped,
                ordered,
                context,
            )

        self.assertIn((first, contact, last), witnesses)
        self.assertIn((first, separated, last), witnesses)
        self.assertEqual(best_path.call_count, 1)

    def test_workspace_and_measurement_cache_reject_coordinate_drift(self) -> None:
        gray = np.zeros((80, 240), dtype=np.uint8)
        statistics = image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        )
        with self.assertRaises(ValueError):
            work_gray(gray, "diagonal")
        with self.assertRaises(ValueError):
            MeasurementCache(
                "diagonal",
                gray,
                gray,
                gray.astype(np.float32),
                statistics,
                0.0,
            )
        with self.assertRaises(ValueError):
            MeasurementCache(
                "horizontal",
                gray,
                gray[:, :-1],
                gray.astype(np.float32),
                statistics,
                0.0,
            )

    def test_analysis_identity_does_not_rebuild_detection_gray(self) -> None:
        from tools.tests.architecture_contracts import PROJECT_ROOT

        source = (
            PROJECT_ROOT / "x5crop/runtime/analysis_identity.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("make_base_gray_u8", source)

    def test_measurement_cache_uses_explicit_typed_keys(self) -> None:
        self.assertFalse(
            any(
                "Any" in str(annotation)
                for annotation in get_type_hints(MeasurementCache).values()
            )
        )

    def test_unavailable_content_threshold_is_cached_exactly_once(self) -> None:
        cache = _cache()
        geometry = candidate_fixture().geometry
        configuration = get_detection_configuration("135", "full").content
        with patch(
            "x5crop.detection.evidence.content.activation.content_evidence_threshold",
            return_value=None,
        ) as measurement:
            frame_content_evidence(geometry, cache, configuration)
            frame_content_evidence(geometry, cache, configuration)
        measurement.assert_called_once()

    def test_diagnostics_do_not_invalidate_detection_analysis(self) -> None:
        bundle = DetectionConfigurationBundle.for_format_mode("135", "full")
        configuration = bundle.initial_configuration
        changed_configuration = replace(
            configuration,
            diagnostics=replace(
                configuration.diagnostics,
                separator_overlay=replace(
                    configuration.diagnostics.separator_overlay,
                    tick_length_min=99,
                ),
            ),
        )
        changed = replace(
            bundle,
            resolved_configurations=(changed_configuration,),
        )
        self.assertEqual(
            detection_configuration_fingerprint(bundle),
            detection_configuration_fingerprint(changed),
        )

    def test_reuse_fingerprint_includes_every_resolved_configuration(self) -> None:
        bundle = DetectionConfigurationBundle.for_format_mode("135-dual", "full")
        lane_configuration = bundle.resolved_configurations[1]
        changed_lane = replace(
            lane_configuration,
            separator=replace(
                lane_configuration.separator,
                observation=replace(
                    lane_configuration.separator.observation,
                    maximum_observations=(
                        lane_configuration.separator.observation.maximum_observations
                        + 1
                    ),
                ),
            ),
        )
        changed = replace(
            bundle,
            resolved_configurations=(
                bundle.initial_configuration,
                changed_lane,
            ),
        )
        self.assertNotEqual(
            detection_configuration_fingerprint(bundle),
            detection_configuration_fingerprint(changed),
        )

    def test_separator_profile_is_cached_by_exact_corridor_and_parameters(self) -> None:
        cache = _cache()
        corridor = Box(0, 10, 240, 70)
        parameters = SeparatorProfileParameters()
        measured = _profile_measurement(240)
        with patch(
            "x5crop.cache.separator.measure_separator_profile",
            return_value=measured,
        ) as measurement:
            first = cached_separator_profile_measurement(cache, corridor, parameters)
            second = cached_separator_profile_measurement(cache, corridor, parameters)
        self.assertIs(first, second)
        measurement.assert_called_once()

    def test_measurement_cache_reports_exact_lookup_hits_and_misses(self) -> None:
        cache = _cache()
        corridor = Box(0, 10, 240, 70)
        parameters = SeparatorProfileParameters()

        cached_separator_profile_measurement(cache, corridor, parameters)
        cached_separator_profile_measurement(cache, corridor, parameters)

        self.assertEqual(cache.lookup_statistics.hits, 1)
        self.assertEqual(cache.lookup_statistics.misses, 1)

    def test_boundary_paths_are_measured_once_across_count_hypotheses(self) -> None:
        cache = _cache()
        parameters = BoundaryPathParameters()
        with patch(
            "x5crop.detection.candidate.proposal.sequence.boundary_measurements",
        ) as measurement:
            first = cached_boundary_measurements(cache, parameters)
            second = cached_boundary_measurements(cache, parameters)
        self.assertIs(first, second)
        measurement.assert_called_once()

    def test_different_corridors_do_not_share_profile_measurements(self) -> None:
        cache = _cache()
        parameters = SeparatorProfileParameters()
        with patch(
            "x5crop.cache.separator.measure_separator_profile",
            side_effect=lambda crop, _statistics, _params: _profile_measurement(
                crop.shape[1]
            ),
        ) as measurement:
            cached_separator_profile_measurement(cache, Box(0, 0, 240, 60), parameters)
            cached_separator_profile_measurement(cache, Box(0, 20, 240, 80), parameters)
        self.assertEqual(measurement.call_count, 2)

    def test_profile_cache_uses_the_canonical_measured_corridor(self) -> None:
        cache = _cache()
        parameters = SeparatorProfileParameters()
        with patch(
            "x5crop.cache.separator.measure_separator_profile",
            side_effect=lambda crop, _statistics, _params: _profile_measurement(
                crop.shape[1]
            ),
        ) as measurement:
            cached_separator_profile_measurement(cache, Box(-20, 0, 120, 80), parameters)

        key = next(iter(cache.separator_profile_measurements))
        self.assertEqual(key.region, Box(0, 0, 120, 80))
        self.assertEqual(measurement.call_args.args[0].shape, (80, 120))

    def test_profile_cache_rejects_corridor_outside_the_workspace(self) -> None:
        cache = _cache()
        with self.assertRaises(ValueError):
            cached_separator_profile_measurement(
                cache,
                Box(300, 0, 400, 80),
                SeparatorProfileParameters(),
            )
        self.assertEqual(cache.separator_profile_measurements, {})

    def test_cache_contains_measurements_not_candidates_or_decisions(self) -> None:
        names = {field.name for field in fields(MeasurementCache)}
        for forbidden in (
            "candidates",
            "candidate_gate",
            "decision_gate",
            "final_detection",
            "final_review_reasons",
        ):
            self.assertNotIn(forbidden, names)

    def test_removed_width_and_refinement_profiles_are_not_cached(self) -> None:
        names = {field.name for field in fields(MeasurementCache)}
        self.assertNotIn("separator_width_profiles", names)
        self.assertNotIn("edge_refine_profiles", names)

    def test_profile_cache_key_is_count_and_offset_independent(self) -> None:
        cache = _cache()
        parameters = SeparatorProfileParameters()
        cached_separator_profile_measurement(cache, Box(0, 0, 240, 80), parameters)
        key = next(iter(cache.separator_profile_measurements))
        self.assertEqual(
            key,
            MeasurementRegionKey(parameters, Box(0, 0, 240, 80)),
        )


if __name__ == "__main__":
    unittest.main()
