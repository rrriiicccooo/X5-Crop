from __future__ import annotations
from x5crop.detection.photo_geometry.broad_material_association import associate_registered_broad_material

from dataclasses import replace
from copy import deepcopy

from tools.tests.photo_geometry_support import *
from x5crop.detection.photo_geometry.cross_height_transition_measurement import (
    measure_cross_height_transition_regions,
)
from x5crop.detection.photo_geometry.broad_material_transition_measurement import (
    measure_broad_material_transitions,
    broad_material_trace_support_qualified,
)
from x5crop.detection.photo_geometry.coarse_enclosing_support import _observe_broad_coarse_short_axis
from x5crop.detection.photo_geometry.profile_adapters import sequence_profile_from_regions
from x5crop.detection.photo_geometry.observations import validate_broad_material_edge_provenance
from tools.regression.report_validation import _validate_broad_material_traces, _validate_sequence_physical_line_regions
from x5crop.report.read_models import typed_read_model
from x5crop.detection.photo_geometry.registered_transition_measurement import (
    TraceMeasurement,
    measure_trace,
    measured_broad_material_peaks,
    measured_transition_peaks,
)
from x5crop.detection.photo_geometry.transition_tracking import (
    track_broad_material_transition_regions,
    track_cross_height_transition_regions,
)
from x5crop.detection.robust_statistics import positive_mad_z
from x5crop.detection.photo_geometry.template_registration import (
    register_cross_evidence,
)


class RegisteredMeasurementContractTest(unittest.TestCase):
    @staticmethod
    def _registered_step(edge: int, *, mirrored: bool, texture: bool):
        scale = PositiveInterval(81.514422, 81.514422)
        traces = tuple(range(0, 901, 100))
        source = np.full((200, 901), 220, dtype=np.uint8)
        source[:edge] = 20
        if texture:
            source[edge:] = 220 + np.arange(200 - edge)[:, None] % 2
        if mirrored:
            source = source[::-1].copy()
        search = FiniteInterval(0.0, 199.0)
        query = PhotoBoundaryMeasurementQuery(
            query_id="query:source-edge",
            registration_index=0,
            lane_id="lane:0",
            purpose=(QueryPurpose.BOTTOM_CORRIDOR if mirrored else QueryPurpose.TOP_CORRIDOR),
            boundary_axis=BoundaryAxis.Y,
            trace_positions_px=traces,
            search_intervals_px=(search,) * len(traces),
            transition_ownership_intervals_px=(search,) * len(traces),
            expected_support_px=900.0,
            boundary_axis_scale_px_per_mm=scale,
            trace_axis_scale_px_per_mm=scale,
            measurement_halo_px=PHOTO_BOUNDARY_MEASUREMENT_SPEC.local_measurement_work_radius_px(scale.maximum),
            registration_provenance_ids=("synthetic-source",),
        )
        measured = measure_registered_queries(
            PhotoBoundaryMeasurementField(source, "horizontal"),
            (query, replace(
                query, query_id="query:source-edge:baseline", registration_index=1,
                purpose=QueryPurpose.CROSS_BASELINE,
            )),
        )[0]
        regions = track_side_transition_regions(
            (measured,), reference_trace_px=450.0,
            boundary_axis_scale_px_per_mm=scale,
        )
        profile = cross_profile_from_regions(
            () if mirrored else regions,
            regions if mirrored else (),
            coordinate_count=200,
            transition_by_id={str(item.transition_id): item for item in measured.transitions},
        )
        registered = register_cross_evidence(
            profile=profile, top_measurement=measured, bottom_measurement=measured,
            width_axis=BoundaryAxis.X, height_axis=BoundaryAxis.Y,
            height_scale_px_per_mm=scale, lane_reference_trace_px=450.0,
        )
        bindings = registered.bottom_bindings if mirrored else registered.top_bindings
        return measured, bindings

    def test_source_cut_localization_peak_cannot_gain_direct_cross_authority(self) -> None:
        for mirrored in (False, True):
            for texture in (False, True):
                with self.subTest(mirrored=mirrored, texture=texture):
                    measured, bindings = self._registered_step(
                        25, mirrored=mirrored, texture=texture,
                    )
                    self.assertTrue(measured.coverage.complete)
                    self.assertEqual(bindings, ())

    def test_complete_source_edge_keeps_its_direct_cross_authority(self) -> None:
        for mirrored in (False, True):
            with self.subTest(mirrored=mirrored):
                _measured, bindings = self._registered_step(
                    50, mirrored=mirrored, texture=True,
                )
                self.assertEqual(len(bindings), 1)
                self.assertTrue(bindings[0].role_authorized)
                self.assertTrue(bindings[0].full_interval_px.contains(
                    149.5 if mirrored else 49.5, epsilon=1.0e-8,
                ))

    def test_uniform_sides_do_not_gain_background_role_from_baseline(self) -> None:
        for mirrored in (False, True):
            with self.subTest(mirrored=mirrored):
                _measured, bindings = self._registered_step(
                    50, mirrored=mirrored, texture=False,
                )
                self.assertTrue(all(not binding.role_authorized for binding in bindings))

    def test_peak_completeness_uses_localization_not_the_whole_signal_group(self) -> None:
        values = np.full(200, 220, dtype=np.uint8)
        values[:50] = 20
        for search, expected_count in (
            (FiniteInterval(50.0, 80.0), 0),
            (FiniteInterval(20.0, 50.0), 0),
            (FiniteInterval(40.0, 60.0), 1),
        ):
            with self.subTest(search=search):
                measured = measure_trace(values, search, 81.514422, PHOTO_BOUNDARY_MEASUREMENT_SPEC)
                peaks = measured_transition_peaks(
                    measured, PHOTO_BOUNDARY_MEASUREMENT_SPEC,
                    split_gradient_reversals=True,
                )
                self.assertEqual(len(peaks), expected_count)
                if peaks:
                    self.assertEqual(peaks[0].canonical_coordinate, 50.0)

    def test_complete_peak_is_not_cut_by_sequence_ownership_boundary(self) -> None:
        source = np.full((81, 101), 220, dtype=np.uint8)
        source[:, :50] = 20
        baseline = replace(
            self._cross_height_query(), query_id="baseline",
            purpose=QueryPurpose.SEQUENCE_BASELINE,
        )
        windows = tuple(
            replace(
                baseline, query_id=f"window:{index}", registration_index=index,
                purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
                search_intervals_px=(FiniteInterval(40.0, 60.0),) * 9,
                transition_ownership_intervals_px=(ownership,) * 9,
            )
            for index, ownership in enumerate(
                (FiniteInterval(40.0, 49.0), FiniteInterval(50.0, 60.0)), start=1,
            )
        )
        _baseline, left, right = measure_registered_queries(
            PhotoBoundaryMeasurementField(source, "horizontal"),
            (baseline, *windows),
        )
        self.assertEqual(left.transitions, ())
        self.assertEqual(len(right.transitions), 9)
        self.assertTrue(all(item.coordinate_px == 50.0 for item in right.transitions))

    def test_complete_opposite_polarity_peaks_survive_domain_check(self) -> None:
        values = np.full(200, 20, dtype=np.uint8)
        values[50:90] = 220
        measured = measure_trace(
            values, FiniteInterval(0.0, 199.0), 81.514422,
            PHOTO_BOUNDARY_MEASUREMENT_SPEC,
        )
        peaks = tuple(
            peak for peak in measured_transition_peaks(
                measured, PHOTO_BOUNDARY_MEASUREMENT_SPEC,
                split_gradient_reversals=True,
            )
            if peak.gradient_z >= PHOTO_BOUNDARY_MEASUREMENT_SPEC.gradient_z_minimum
        )
        self.assertEqual([item.canonical_coordinate for item in peaks], [50.0, 90.0])
        self.assertEqual([item.polarity for item in peaks], [1, -1])

    def test_broad_peak_needs_observed_flanks_not_masked_zeroes(self) -> None:
        for edge, expected_count in ((45, 0), (75, 1)):
            for mirrored in (False, True):
                with self.subTest(edge=edge, mirrored=mirrored):
                    values = np.full(200, 20, dtype=np.uint8)
                    values[edge:] = 220 + 4 * (np.arange(200 - edge) % 2)
                    if mirrored:
                        values = values[::-1].copy()
                    measured = measure_trace(
                        values, FiniteInterval(0.0, 199.0), 81.514422,
                        PHOTO_BOUNDARY_MEASUREMENT_SPEC,
                        include_broad_material=True,
                    )
                    peaks = tuple(
                        peak for peak in measured_broad_material_peaks(
                            measured, PHOTO_BOUNDARY_MEASUREMENT_SPEC,
                        )
                        if peak.background_side == (1 if mirrored else -1)
                    )
                    self.assertEqual(len(peaks), expected_count)
                    if peaks:
                        self.assertTrue(peaks[0].physical_position_interval.contains(
                            199.5 - edge if mirrored else edge - 0.5,
                            epsilon=1.0e-8,
                        ))

    def test_weak_tail_checks_real_domain_without_merging_credible_groups(self) -> None:
        for edge in (30, 60):
            for signal in ([22, 24, 24, 22], [22, 24, 24, 22, 22, 24, 24, 22]):
                for mirrored in (False, True):
                    with self.subTest(edge=edge, signal=signal, mirrored=mirrored):
                        values = np.full(200, 20, dtype=np.uint8)
                        values[edge : edge + len(signal)] = signal
                        if mirrored:
                            values = values[::-1].copy()
                        measured = measure_trace(
                            values, FiniteInterval(0.0, 199.0), 81.514422,
                            PHOTO_BOUNDARY_MEASUREMENT_SPEC,
                        )
                        peaks = measured_transition_peaks(
                            measured, PHOTO_BOUNDARY_MEASUREMENT_SPEC,
                            split_gradient_reversals=True,
                        )
                        negative = [edge + 6.5 + offset for offset in range(0, len(signal), 4)]
                        positive = [edge - 2.5 + offset for offset in range(0, len(signal), 4)]
                        expected = negative if edge == 30 else positive + negative
                        if mirrored:
                            expected = [200.0 - value for value in expected]
                        self.assertEqual(
                            [peak.canonical_coordinate for peak in peaks], sorted(expected),
                        )
                        self.assertTrue(all(peak.peak_width_px == 2.0 for peak in peaks))

    def test_broad_weak_tail_checks_observable_domain_not_credible_threshold(self) -> None:
        measured = self._broad_material_trace()
        material = measured.broad_material
        self.assertIsNotNone(material)
        for truncated, expected_count in ((False, 1), (True, 0)):
            with self.subTest(truncated=truncated):
                contrast = np.zeros(measured.coordinates.size)
                contrast[50:54] = [2, 4, 4, 2]
                observable = np.ones(contrast.size, dtype=bool)
                if truncated:
                    observable[:50] = False
                broad = replace(
                    material, contrast_z=contrast,
                    supported=np.ones(contrast.size, dtype=bool),
                    observable=observable,
                    polarity=np.ones(contrast.size, dtype=np.int8),
                    background_side=-np.ones(contrast.size, dtype=np.int8),
                )
                peaks = measured_broad_material_peaks(
                    replace(measured, broad_material=broad),
                    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
                )
                self.assertEqual(len(peaks), expected_count)

    @staticmethod
    def _cross_height_query() -> PhotoBoundaryMeasurementQuery:
        traces = tuple(range(0, 81, 10))
        return PhotoBoundaryMeasurementQuery(
            query_id="query:cross-height",
            registration_index=0,
            lane_id="lane:0",
            purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
            boundary_axis=BoundaryAxis.X,
            trace_positions_px=traces,
            search_intervals_px=(FiniteInterval(0.0, 100.0),) * len(traces),
            transition_ownership_intervals_px=(
                FiniteInterval(0.0, 100.0),
            )
            * len(traces),
            expected_support_px=100.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            trace_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            measurement_halo_px=4,
            registration_provenance_ids=("anchor-domain:cross-height",),
        )

    @staticmethod
    def _weak_trace(seed: int, signal: float) -> TraceMeasurement:
        coordinates = np.arange(101, dtype=np.int32)
        signed_gradient = np.random.default_rng(seed).integers(
            -4,
            5,
            size=coordinates.size,
        ).astype(np.float64)
        signed_gradient[50] = signal
        gradient_z = positive_mad_z(
            np.abs(signed_gradient),
            minimum_scale=1.0,
        )
        texture_difference = np.random.default_rng(seed + 1000).integers(
            0,
            9,
            size=coordinates.size,
        ).astype(np.float64)
        texture_difference[50] = 11.0
        zeros = np.zeros(coordinates.size, dtype=np.float64)
        left_tone = np.full(coordinates.size, 10.0)
        right_tone = np.full(coordinates.size, 20.0)
        left_texture = np.full(coordinates.size, 1.0)
        right_texture = left_texture + texture_difference
        texture_z = positive_mad_z(
            texture_difference,
            minimum_scale=1.0,
        )
        return TraceMeasurement(
            coordinates=coordinates,
            gradient_z=gradient_z,
            tone_z=zeros,
            texture_z=texture_z,
            signed_gradient=signed_gradient,
            left_tone=left_tone,
            right_tone=right_tone,
            left_texture=left_texture,
            right_texture=right_texture,
            temporary_bytes=sum(
                item.nbytes
                for item in (
                    coordinates,
                    gradient_z,
                    zeros,
                    texture_z,
                    signed_gradient,
                    left_tone,
                    right_tone,
                    left_texture,
                    right_texture,
                )
            ),
        )

    @staticmethod
    def _broad_material_trace(
        *,
        reverse_background: bool = False,
    ) -> TraceMeasurement:
        coordinates = np.arange(151)
        values = np.full(151, 100.0)
        if not reverse_background:
            values += np.where(coordinates % 2, 2.0, -2.0)
        left_ramp = (coordinates >= 40) & (coordinates <= 60)
        values[left_ramp] = (
            100.0 - (coordinates[left_ramp] - 40) * 4.0
        )
        values[(coordinates > 60) & (coordinates < 90)] = 20.0
        right_ramp = (coordinates >= 90) & (coordinates <= 110)
        values[right_ramp] = (
            20.0 + (coordinates[right_ramp] - 90) * 4.0
        )
        if reverse_background:
            separator = (coordinates > 60) & (coordinates < 90)
            values[separator] += np.where(
                coordinates[separator] % 2,
                2.0,
                -2.0,
            )
        return measure_trace(
            np.clip(np.rint(values), 0, 255).astype(np.uint8),
            FiniteInterval(0.0, 150.0),
            10.0,
            PHOTO_BOUNDARY_MEASUREMENT_SPEC,
            include_broad_material=True,
        )

    @staticmethod
    def _broad_material_query() -> PhotoBoundaryMeasurementQuery:
        traces = tuple(range(0, 81, 10))
        return PhotoBoundaryMeasurementQuery(
            query_id="query:broad-material",
            registration_index=0,
            lane_id="lane:0",
            purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
            boundary_axis=BoundaryAxis.X,
            trace_positions_px=traces,
            search_intervals_px=(FiniteInterval(0.0, 150.0),) * len(traces),
            transition_ownership_intervals_px=(
                FiniteInterval(0.0, 150.0),
            )
            * len(traces),
            expected_support_px=150.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            trace_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            measurement_halo_px=(
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.measurement_halo_px(10.0)
            ),
            registration_provenance_ids=("anchor-domain:broad-material",),
        )

    @staticmethod
    def _broad_material_measurement_set(
        query: PhotoBoundaryMeasurementQuery,
        traces: tuple[TraceMeasurement, ...],
    ) -> PhotoBoundaryMeasurementSet:
        transitions, peak_temporary = (
            measure_broad_material_transitions(query, traces)
        )
        coordinate_count = 151 * len(traces)
        return PhotoBoundaryMeasurementSet(
            query=query,
            state=EvidenceState.SUPPORTED,
            transitions=(),
            cross_height_transitions=(),
            coverage=PhotoBoundaryCoverageReceipt(
                query_id=query.query_id,
                registered_trace_count=len(traces),
                completed_trace_count=len(traces),
                registered_coordinate_count=coordinate_count,
                completed_coordinate_count=coordinate_count,
                pixel_query_count=coordinate_count,
                streaming_block_count=1,
                peak_temporary_bytes=peak_temporary,
                complete=True,
            ),
            broad_material_transitions=transitions,
            broad_material_association=associate_registered_broad_material(query, transitions),
        )
    def test_cross_height_union_recovers_one_common_subthreshold_line(
        self,
    ) -> None:
        query = self._cross_height_query()
        traces = tuple(self._weak_trace(100 + index, 6.0) for index in range(9))
        self.assertTrue(
            all(
                all(
                    abs(item.canonical_coordinate - 50.0) > 0.5
                    for item in measured_transition_peaks(
                        trace,
                        PHOTO_BOUNDARY_MEASUREMENT_SPEC,
                        split_gradient_reversals=False,
                    )
                )
                for trace in traces
            )
        )

        transitions, peak_temporary = measure_cross_height_transition_regions(
            query,
            traces,
        )
        common = tuple(
            item
            for item in transitions
            if abs(item.canonical_coordinate_px - 50.0) <= 0.5
        )
        self.assertEqual(len(common), 3)
        self.assertEqual(
            tuple(item.spatial_region_index for item in common),
            (0, 1, 2),
        )
        self.assertTrue(all(item.polarity == 1 for item in common))
        self.assertGreater(peak_temporary, 0)

        coverage = PhotoBoundaryCoverageReceipt(
            query_id=query.query_id,
            registered_trace_count=9,
            completed_trace_count=9,
            registered_coordinate_count=909,
            completed_coordinate_count=909,
            pixel_query_count=909,
            streaming_block_count=1,
            peak_temporary_bytes=peak_temporary,
            complete=True,
        )
        regions = track_cross_height_transition_regions(
            (
                PhotoBoundaryMeasurementSet(
                    query=query,
                    state=EvidenceState.SUPPORTED,
                    transitions=(),
                    cross_height_transitions=transitions,
                    coverage=coverage,
                ),
            ),
            reference_trace_px=40.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].independent_support_region_count, 3)

    def test_cross_height_union_rejects_opposite_region_polarity(self) -> None:
        query = self._cross_height_query()
        traces = tuple(
            self._weak_trace(
                200 + index,
                -6.0 if 3 <= index < 6 else 6.0,
            )
            for index in range(9)
        )
        transitions, peak_temporary = measure_cross_height_transition_regions(
            query,
            traces,
        )
        coverage = PhotoBoundaryCoverageReceipt(
            query_id=query.query_id,
            registered_trace_count=9,
            completed_trace_count=9,
            registered_coordinate_count=909,
            completed_coordinate_count=909,
            pixel_query_count=909,
            streaming_block_count=1,
            peak_temporary_bytes=peak_temporary,
            complete=True,
        )

        regions = track_cross_height_transition_regions(
            (
                PhotoBoundaryMeasurementSet(
                    query=query,
                    state=EvidenceState.SUPPORTED,
                    transitions=(),
                    cross_height_transitions=transitions,
                    coverage=coverage,
                ),
            ),
            reference_trace_px=40.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        self.assertEqual(regions, ())

    def test_broad_material_recovers_two_slow_separator_sides(self) -> None:
        query = self._broad_material_query()
        traces = tuple(
            self._broad_material_trace()
            for _trace in query.trace_positions_px
        )
        local = measured_transition_peaks(
            traces[0],
            PHOTO_BOUNDARY_MEASUREMENT_SPEC,
            split_gradient_reversals=False,
        )
        self.assertTrue(
            all(
                item.gradient_z
                < PHOTO_BOUNDARY_MEASUREMENT_SPEC.gradient_z_minimum
                for item in local
                if 35.0 < item.canonical_coordinate < 115.0
            )
        )
        self.assertEqual(
            len(measured_broad_material_peaks(
                traces[0], PHOTO_BOUNDARY_MEASUREMENT_SPEC
            )),
            2,
        )

        measurement_set = self._broad_material_measurement_set(query, traces)
        regions = track_broad_material_transition_regions(
            (measurement_set,),
            reference_trace_px=40.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        self.assertEqual(len(measurement_set.broad_material_transitions), 18)
        self.assertTrue(all(
            sum(item.trace_ordinal == ordinal for item in measurement_set.broad_material_transitions) == 2
            for ordinal in range(len(traces))
        ))
        self.assertEqual(len(regions), 2)
        self.assertTrue(
            all(item.independent_support_region_count == 3 for item in regions)
        )

    def test_broad_material_rejects_background_side_conflict(self) -> None:
        query = self._broad_material_query()
        traces = tuple(
            self._broad_material_trace(
                reverse_background=3 <= index < 6,
            )
            for index, _trace in enumerate(query.trace_positions_px)
        )
        measurement_set = self._broad_material_measurement_set(query, traces)

        regions = track_broad_material_transition_regions(
            (measurement_set,),
            reference_trace_px=40.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        self.assertEqual(regions, ())

    @classmethod
    def _sloping_broad_strip(cls, *, mirrored=False, blank_ordinals=()):
        traces = tuple(range(0, 8001, 1000))
        domain = FiniteInterval(0.0, 1000.0)
        query = replace(
            cls._broad_material_query(), purpose=QueryPurpose.COARSE_STRIP_SHORT,
            trace_positions_px=traces, search_intervals_px=(domain,) * 9,
            transition_ownership_intervals_px=(domain,) * 9,
            expected_support_px=8000.0,
        )
        measured = []
        for ordinal in range(9):
            low, high = 198 + ordinal * 2, 798 + ordinal * 2
            values = np.full(1001, 230, dtype=np.uint8)
            if ordinal not in blank_ordinals:
                inside = 70 if ordinal % 3 == 0 else 210
                values[low:high] = inside + np.where(np.arange(low, high) % 2, 4, -4)
            if mirrored:
                values = values[::-1].copy()
            measured.append(measure_trace(values, domain, 10.0,
                PHOTO_BOUNDARY_MEASUREMENT_SPEC, include_broad_material=True))
        result = cls._broad_material_measurement_set(query, tuple(measured))
        return replace(result, coverage=replace(result.coverage,
            registered_coordinate_count=9009, completed_coordinate_count=9009,
            pixel_query_count=9009))

    def test_broad_geometry_uses_actual_traces_with_unequal_contrast(self) -> None:
        for mirrored in (False, True):
            with self.subTest(mirrored=mirrored):
                measured = self._sloping_broad_strip(mirrored=mirrored)
                outward = tuple(item for item in measured.broad_material_transitions
                    if (item.background_side.value == "left") == (item.polarity < 0))
                self.assertEqual(len(outward), 18)
                for item in outward:
                    ordinal = item.trace_ordinal
                    low, high = 197.5 + 2 * ordinal, 797.5 + 2 * ordinal
                    if mirrored:
                        low, high = 1000.0 - high, 1000.0 - low
                    self.assertEqual(item.trace_coordinate_px, ordinal * 1000)
                    self.assertTrue(item.physical_position_interval_px.contains(
                        low if item.polarity < 0 else high), item)

    def test_broad_pair_keeps_true_parallel_boundaries_with_unequal_contrast(self) -> None:
        for mirrored in (False, True):
            with self.subTest(mirrored=mirrored):
                measured = self._sloping_broad_strip(mirrored=mirrored)
                top, bottom = (194.5, 794.5) if mirrored else (205.5, 805.5)
                _direction, support = _observe_broad_coarse_short_axis(
                    measured, aggregate_interval_px=FiniteInterval(top, bottom),
                    expected_height_px=FiniteInterval(580.0, 580.0), reference_trace_px=4000.0,
                )
                self.assertIsNotNone(support)
                assert support is not None
                self.assertTrue(support.minimum_track.full_position_interval_px.contains(top))
                self.assertTrue(support.maximum_track.full_position_interval_px.contains(bottom))
                self.assertEqual(support.minimum_track.trace_coordinates_px,
                    measured.query.trace_positions_px)

    def test_complete_physical_broad_competitor_survives_curved_localization(self) -> None:
        from tools.tests.test_broad_material_association_contract import _broad_point

        query = self._broad_material_query()
        traces = query.trace_positions_px
        curved = tuple(_broad_point(
            traces, ordinal, 50.0 + 2.5 * (4 - abs(ordinal - 4)),
            identity=f"curved:{ordinal}", physical=(45.0, 65.0),
            query_id=query.query_id,
        ).transition for ordinal in range(len(traces)))
        straight = tuple(_broad_point(
            traces, ordinal, 100.0, identity=f"straight:{ordinal}",
            query_id=query.query_id,
        ).transition for ordinal in range(len(traces)))
        raw = curved + straight
        measured = self._broad_material_measurement_set(query,
            tuple(self._broad_material_trace() for _ in traces))
        measured = replace(measured, broad_material_transitions=raw,
            broad_material_association=associate_registered_broad_material(query, raw))
        expected = {frozenset(item.transition_id for item in family)
                    for family in (curved, straight)}
        for reference in (0.0, 40.0, 80.0):
            with self.subTest(reference=reference):
                regions = track_broad_material_transition_regions((measured,),
                    reference_trace_px=reference,
                    boundary_axis_scale_px_per_mm=query.boundary_axis_scale_px_per_mm)
                self.assertEqual({frozenset(region.transition_ids) for region in regions}, expected)
                self.assertTrue(all(region.trace_support_count == len(traces)
                                    for region in regions))
                curved_region = next(region for region in regions
                    if str(region.transition_ids[0]).startswith("curved:"))
                self.assertTrue(curved_region.position_interval_px.contains(50.0))

        lane = {"lane_id": query.lane_id, "observations": {
            "sequence_edges": [], "cross_height_edges": [], "broad_material_edges": [],
            "broad_material_transition_regions": typed_read_model(regions),
        }}
        queries = [{"query": typed_read_model(query), "transitions": [],
            "cross_height_transitions": [], "broad_material_transitions": typed_read_model(raw),
            "broad_material_association": typed_read_model(measured.broad_material_association)}]
        _validate_sequence_physical_line_regions(lane, queries)
        changed = deepcopy(lane)
        changed["observations"]["broad_material_transition_regions"][0]["transition_ids"].pop()
        with self.assertRaisesRegex(ValueError, "complete association"):
            _validate_sequence_physical_line_regions(changed, queries)

    def test_broad_missing_traces_cannot_shrink_the_majority_denominator(self) -> None:
        for blanks, qualified in (((1,), True), ((0, 1), False)):
            with self.subTest(blanks=blanks):
                measured = self._sloping_broad_strip(blank_ordinals=blanks)
                members = tuple(item.trace_coordinate_px for item in measured.broad_material_transitions)
                self.assertTrue(all(item.trace_ordinal not in blanks
                    for item in measured.broad_material_transitions))
                self.assertEqual(broad_material_trace_support_qualified(
                    measured.query.trace_positions_px, members), qualified)
                regions = track_broad_material_transition_regions((measured,),
                    reference_trace_px=4000.0, boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0))
                self.assertEqual(bool(regions), qualified)

    def test_broad_trace_schema_rejects_invented_region_and_old_aggregate_fields(self) -> None:
        measured = self._sloping_broad_strip()
        raw = {"broad_material_transitions": typed_read_model(measured.broad_material_transitions),
               "broad_material_transition_count": len(measured.broad_material_transitions),
               "broad_material_association": typed_read_model(measured.broad_material_association),
               "coverage": typed_read_model(measured.coverage)}
        _validate_broad_material_traces(raw, measured.query)
        with self.assertRaisesRegex(ValueError, "association receipt"):
            replace(measured, broad_material_association=None)
        for mutation in ("missing", "path", "inputs", "work", "bound"):
            changed = deepcopy(raw)
            association = changed["broad_material_association"]
            if mutation == "missing":
                del changed["broad_material_association"]
            elif mutation == "path":
                association["paths"] = association["paths"][1:]
            elif mutation == "inputs":
                association["input_transition_ids"] = association["input_transition_ids"][1:]
            elif mutation == "work":
                association["work"]["seed_count"] = True
            else:
                association.update(state="bound_exceeded", paths=[], failure_reason="charged_work_bound")
            with self.subTest(association_mutation=mutation), self.assertRaises(ValueError):
                _validate_broad_material_traces(changed, measured.query)
        for mutation in ("region", "trace", "legacy", "duplicate"):
            changed = deepcopy(raw)
            point = changed["broad_material_transitions"][0]
            if mutation == "region":
                point["spatial_region_index"] = 2
            elif mutation == "trace":
                point["trace_coordinate_px"] += 1
            elif mutation == "legacy":
                point["contributing_trace_ordinals"] = [0, 1, 2]
            else:
                changed["broad_material_transitions"].append(deepcopy(point))
                changed["broad_material_transition_count"] += 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                _validate_broad_material_traces(changed, measured.query)

    def test_broad_final_edge_cannot_mix_queries_or_lose_regional_majority(self) -> None:
        query = self._broad_material_query()
        measured = self._broad_material_measurement_set(query,
            tuple(self._broad_material_trace() for _ in query.trace_positions_px))
        transitions = {str(item.transition_id): item for item in measured.broad_material_transitions}
        regions = track_broad_material_transition_regions((measured,),
            reference_trace_px=40.0, boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0))
        profile = sequence_profile_from_regions(regions, coordinate_count=151, transition_by_id=transitions)
        edges = build_sequence_edge_observations(profile, transitions, reference_trace_px=40.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            measurement_basis=BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_TRACE,
            queried_trace_coordinates_px=query.trace_positions_px)
        self.assertEqual(len(edges), 2)
        edge = edges[0]
        queries = {query.query_id: query}
        validate_broad_material_edge_provenance(edge, transitions, queries)
        dropped = replace(edge, transition_ids=edge.transition_ids[2:],
            trace_coordinates_px=edge.trace_coordinates_px[2:])
        with self.assertRaisesRegex(ValueError, "regional majority"):
            validate_broad_material_edge_provenance(dropped, transitions, queries)
        foreign = replace(query, query_id="query:other-window")
        mixed = dict(transitions)
        first_id = str(edge.transition_ids[0])
        mixed[first_id] = replace(mixed[first_id], query_id=foreign.query_id)
        with self.assertRaisesRegex(ValueError, "measurement source"):
            validate_broad_material_edge_provenance(edge, mixed, {**queries, foreign.query_id: foreign})
        lane = {"lane_id": query.lane_id, "observations": {
            "sequence_edges": [], "cross_height_edges": [], "broad_material_edges": [typed_read_model(edge)],
            "broad_material_transition_regions": typed_read_model(regions)}}
        raw_queries = [{"query": typed_read_model(query), "transitions": [], "cross_height_transitions": [],
            "broad_material_transitions": typed_read_model(measured.broad_material_transitions),
            "broad_material_association": typed_read_model(measured.broad_material_association)}]
        _validate_sequence_physical_line_regions(lane, raw_queries)
        for undirected in (False, True):
            changed = deepcopy(lane)
            target = changed["observations"]["broad_material_edges"][0]
            target["transition_ids"] = target["transition_ids"][2:]
            target["trace_coordinates_px"] = target["trace_coordinates_px"][2:]
            if undirected:
                target["canonical_direction_degrees"] = None
                target["physical_line_region"] = None
            with self.subTest(undirected=undirected), self.assertRaisesRegex(ValueError, "regional majority"):
                _validate_sequence_physical_line_regions(changed, raw_queries)

    def test_measurement_spec_contains_only_production_values(self) -> None:
        spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
        self.assertEqual(spec.lattice_spacing_mm(12.0), 2.0)
        self.assertEqual(spec.lattice_spacing_mm(36.0), 3.0)
        self.assertEqual(spec.lattice_spacing_mm(120.0), 4.0)
        self.assertEqual(spec.local_window_mm, 0.25)
        self.assertEqual(spec.broad_material_window_mm, 0.5)
        self.assertEqual(spec.transition_gap_mm, 0.05)
        self.assertEqual(spec.measurement_halo_px(10.0), 4)
        self.assertEqual(spec.broad_material_window_px(10.0), 5)
        self.assertEqual(spec.local_measurement_work_radius_px(86.0), 26)
        self.assertEqual(spec.measurement_halo_px(86.0), 27)
        self.assertEqual(spec.maximum_measurable_line_angle_degrees, 4.0)
        self.assertEqual(spec.robust_loss_minimum_scale_mm, 0.05)
        self.assertEqual(spec.robust_fit_maximum_evaluations, 128)
        self.assertEqual(spec.robust_fit_tolerance, 1.0e-8)
        self.assertEqual(spec.maximum_streaming_block_pixels, 1_048_576)

    def test_measurement_field_is_immutable_and_partial_query_is_unavailable(
        self,
    ) -> None:
        gray = np.zeros((20, 30), dtype=np.uint8)
        field = PhotoBoundaryMeasurementField(gray, "horizontal")
        self.assertFalse(field.source_gray.flags.writeable)
        query = PhotoBoundaryMeasurementQuery(
            query_id="query:test",
            registration_index=0,
            lane_id="lane:0",
            purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
            boundary_axis=BoundaryAxis.X,
            trace_positions_px=(2, 4, 6, 8),
            search_intervals_px=(FiniteInterval(0.0, 29.0),) * 4,
            transition_ownership_intervals_px=(
                FiniteInterval(0.0, 29.0),
            )
            * 4,
            expected_support_px=20.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(1.0, 1.1),
            trace_axis_scale_px_per_mm=PositiveInterval(1.0, 1.1),
            measurement_halo_px=2,
            registration_provenance_ids=("anchor-domain:test",),
        )
        coverage = PhotoBoundaryCoverageReceipt(
            query_id=query.query_id,
            registered_trace_count=4,
            completed_trace_count=3,
            registered_coordinate_count=120,
            completed_coordinate_count=90,
            pixel_query_count=90,
            streaming_block_count=1,
            peak_temporary_bytes=4096,
            complete=False,
        )
        measurement = PhotoBoundaryMeasurementSet(
            query=query,
            state=EvidenceState.UNAVAILABLE,
            transitions=(),
            cross_height_transitions=(),
            coverage=coverage,
        )
        self.assertEqual(measurement.state, EvidenceState.UNAVAILABLE)
        with self.assertRaises(ValueError):
            PhotoBoundaryMeasurementSet(
                query=query,
                state=EvidenceState.SUPPORTED,
                transitions=(),
                cross_height_transitions=(),
                coverage=coverage,
            )

    def test_overlapping_query_halos_emit_transition_once(self) -> None:
        gray = np.zeros((4, 30), dtype=np.uint8)
        gray[:, 15:] = 255
        field = PhotoBoundaryMeasurementField(gray, "horizontal")
        common = dict(
            lane_id="lane:0",
            purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
            boundary_axis=BoundaryAxis.X,
            trace_positions_px=(0, 1, 2, 3),
            expected_support_px=20.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            trace_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            measurement_halo_px=10,
        )
        queries = (
            PhotoBoundaryMeasurementQuery(
                query_id="query:baseline",
                registration_index=0,
                search_intervals_px=(FiniteInterval(0.0, 29.0),) * 4,
                transition_ownership_intervals_px=(FiniteInterval(0.0, 29.0),)
                * 4,
                registration_provenance_ids=("baseline",),
                purpose=QueryPurpose.SEQUENCE_BASELINE,
                **{
                    key: value
                    for key, value in common.items()
                    if key != "purpose"
                },
            ),
            PhotoBoundaryMeasurementQuery(
                query_id="query:left",
                registration_index=1,
                search_intervals_px=(FiniteInterval(0.0, 20.0),) * 4,
                transition_ownership_intervals_px=(FiniteInterval(0.0, 9.0),)
                * 4,
                registration_provenance_ids=("tile:left",),
                **common,
            ),
            PhotoBoundaryMeasurementQuery(
                query_id="query:right",
                registration_index=2,
                search_intervals_px=(FiniteInterval(9.0, 29.0),) * 4,
                transition_ownership_intervals_px=(FiniteInterval(10.0, 29.0),)
                * 4,
                registration_provenance_ids=("tile:right",),
                **common,
            ),
        )
        baseline, left, right = measure_registered_queries(field, queries)
        self.assertEqual(baseline.transitions, ())
        self.assertEqual(left.transitions, ())
        self.assertEqual(
            {item.query_id for item in right.transitions},
            {"query:right"},
        )

    def test_cross_corridor_preserves_opposite_physical_transitions_only(
        self,
    ) -> None:
        gray = np.full((40, 6), 200, dtype=np.uint8)
        gray[15:17, :] = 0
        field = PhotoBoundaryMeasurementField(gray, "horizontal")

        def query(purpose: QueryPurpose, registration_index: int):
            return PhotoBoundaryMeasurementQuery(
                query_id=f"query:{purpose.value}",
                registration_index=registration_index,
                lane_id="lane:0",
                purpose=purpose,
                boundary_axis=BoundaryAxis.Y,
                trace_positions_px=tuple(range(6)),
                search_intervals_px=(FiniteInterval(4.0, 34.0),) * 6,
                transition_ownership_intervals_px=(
                    FiniteInterval(4.0, 34.0),
                )
                * 6,
                expected_support_px=30.0,
                boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
                trace_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
                measurement_halo_px=4,
                registration_provenance_ids=(f"corridor:{purpose.value}",),
            )

        cross, baseline, sequence, cross_baseline = measure_registered_queries(
            field,
            (
                query(QueryPurpose.TOP_CORRIDOR, 0),
                query(QueryPurpose.SEQUENCE_BASELINE, 1),
                query(QueryPurpose.SEQUENCE_ANCHOR_WINDOW, 2),
                query(QueryPurpose.CROSS_BASELINE, 3),
            ),
        )
        self.assertEqual(baseline.transitions, ())
        self.assertEqual(cross_baseline.transitions, ())

        cross_by_trace = {
            trace: tuple(
                item
                for item in cross.transitions
                if item.trace_coordinate_px == trace
            )
            for trace in range(6)
        }
        self.assertTrue(
            all(
                {item.polarity for item in values} == {-1, 1}
                for values in cross_by_trace.values()
            ),
            cross_by_trace,
        )
        self.assertTrue(
            all(
                len(
                    {
                        item.polarity
                        for item in sequence.transitions
                        if item.trace_coordinate_px == trace
                    }
                )
                <= 1
                for trace in range(6)
            )
        )

    def test_side_tracking_keeps_close_separator_sides_distinct(self) -> None:
        regions = track_side_transition_regions(
            (make_side_measurement_set(((100.0, 104.0),) * 5),),
            reference_trace_px=20.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        self.assertEqual(len(regions), 2)
        self.assertNotEqual(regions[0].transition_ids, regions[1].transition_ids)

    def test_side_tracking_allows_one_missing_step_not_two(self) -> None:
        scale = PositiveInterval(10.0, 10.0)
        one_missing = make_side_measurement_set(
            ((100.0,), (100.0,), (), (100.0,), (100.0,), (100.0,))
        )
        two_missing = make_side_measurement_set(
            ((100.0,), (100.0,), (), (), (100.0,), (100.0,))
        )
        self.assertEqual(
            len(
                track_side_transition_regions(
                    (one_missing,),
                    reference_trace_px=25.0,
                    boundary_axis_scale_px_per_mm=scale,
                )
            ),
            1,
        )
        self.assertEqual(
            track_side_transition_regions(
                (two_missing,),
                reference_trace_px=25.0,
                boundary_axis_scale_px_per_mm=scale,
            ),
            (),
        )


if __name__ == "__main__":
    unittest.main()
