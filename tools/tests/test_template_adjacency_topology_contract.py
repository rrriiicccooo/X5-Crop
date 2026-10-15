from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    phase_edge,
    phase_separator,
    phase_sequence_measurement,
    phase_template,
    placement_sequence,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.template_adjacency_coverage import assess_adjacency_observation_coverage
from x5crop.detection.photo_geometry.template_adjacency_topology import (
    AdjacencyContinuityBasis,
    AdjacencyContinuityFailureKind,
    AdjacencyContinuityKind,
    observe_adjacency_continuity,
    unbound_registered_adjacency_counterevidence,
)
from x5crop.detection.photo_geometry.template_contact import observe_contact_edges
from x5crop.detection.photo_geometry.model import BoundaryEvidenceState, BoundaryRole
from x5crop.detection.photo_geometry.observation_types import SeparatorMaterialRegionState
from x5crop.detection.photo_geometry.template_residual import (
    ResidualPattern,
    derive_adjacency_relations,
)
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_phase import fit_template_phase_with_adjacency_relations
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFailureKind,
    PhaseFitStatus,
    TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_model import (
    OverlapRelation,
    template_role_refinement_radius_px,
)
from x5crop.detection.photo_geometry.template_overlap import observe_overlap_edge_pairs
from x5crop.detection.photo_geometry.template_direct_role_authority import assess_direct_role_binding_authority
from x5crop.domain import EvidenceState, FiniteInterval


def _edges(*coordinates: float):
    return tuple(
        phase_edge(f"sequence:{index}", coordinate)
        for index, coordinate in enumerate(coordinates)
    )


def _observe(
    fit,
    edges,
    bands=(),
    *,
    complete: bool = True,
    register_overlap: bool = True,
):
    measurement = phase_sequence_measurement(
        "adjacency-continuity",
        FiniteInterval(0.0, 500.0),
        complete=complete,
    )
    coverage = assess_adjacency_observation_coverage(
        fit,
        (measurement,),
        directly_observed_ordinals=(),
    )
    overlap_pairs = (
        observe_overlap_edge_pairs(
            tuple(edges),
            tuple(bands),
            (measurement,),
            direction=fit.template.direction,
            maximum_overlap_px=template_role_refinement_radius_px(
                fit.template.pitch_px.maximum
            ),
        )
        if register_overlap
        else ()
    )
    return observe_adjacency_continuity(
        fit,
        tuple(edges),
        tuple(bands),
        coverage,
        overlap_pairs,
    )


def _contact_fit():
    edges = _edges(100.0, 200.0, 300.0)
    measurement = phase_sequence_measurement(
        "contact-candidate",
        FiniteInterval(0.0, 320.0),
    )
    contacts = observe_contact_edges(edges, (), (measurement,))
    result = fit_template_phase(
        edges,
        phase_template(2),
        contact_edge_observations=contacts,
    )
    assert result.best is not None
    return result.best, edges


def _unbound_separator_case(missing_role=2, *, direction=1, partner=None, regions=3):
    fit = placement_sequence(phase_template(2), missing=(missing_role,))
    coordinates = [100.0, 200.0, 220.0, 320.0]
    coordinates[missing_role] = 210.0 if partner is None else partner
    full = list(fit.model_full_role_intervals_px)
    full[1:3] = (FiniteInterval(180.0, 240.0),) * 2
    fit = replace(fit, model_full_role_intervals_px=tuple(full))
    if direction < 0:
        def reflect(interval):
            return FiniteInterval(600.0 - interval.maximum, 600.0 - interval.minimum)
        spec = replace(fit.template, direction=-1,
            phase_lattice_authority=replace(fit.template.phase_lattice_authority, cycle_origin_px=600.0))
        fit = replace(fit, template=spec,
            phase_lattice_fit=replace(fit.phase_lattice_fit, authority=spec.phase_lattice_authority,
                direction=-1, canonical_absolute_phase_px=500.0, absolute_phase_interval_px=FiniteInterval.exact(500.0)),
            model_role_positions_px=tuple(600.0 - value for value in fit.model_role_positions_px),
            model_role_intervals_px=tuple(map(reflect, fit.model_role_intervals_px)),
            model_full_role_intervals_px=tuple(map(reflect, fit.model_full_role_intervals_px)),
            role_bindings=tuple(None if b is None else replace(b,
                canonical_position_px=600.0 - b.canonical_position_px,
                fit_position_interval_px=reflect(b.fit_position_interval_px),
                full_position_interval_px=reflect(b.full_position_interval_px)) for b in fit.role_bindings))
        coordinates = [600.0 - value for value in coordinates]
    edges = _edges(*coordinates)
    left, right = (edges[1], edges[2]) if direction > 0 else (edges[2], edges[1])
    gap = abs(coordinates[2] - coordinates[1])
    band = phase_separator("native-partner", left, right, FiniteInterval(gap - .4, gap + .4), region_count=regions)
    measurement = phase_sequence_measurement("native-partner", FiniteInterval(0.0, 600.0))
    coverage = assess_adjacency_observation_coverage(fit, (measurement,), directly_observed_ordinals=())
    direct = assess_direct_role_binding_authority(fit, edges, (band,), (measurement,))
    return fit, edges, band, coverage, direct


class TemplateAdjacencyTopologyContractTests(unittest.TestCase):
    def test_unbound_separator_rejects_only_unavoidable_native_width_excess(self):
        for missing in (1, 2):
            for direction in (-1, 1):
                with self.subTest(missing=missing, direction=direction):
                    fit, edges, band, coverage, direct = _unbound_separator_case(missing, direction=direction)
                    original_bindings = fit.role_bindings
                    conflicts = unbound_registered_adjacency_counterevidence(fit, edges, coverage,
                        separator_bands=(band,), direct_role_authority=direct)
                    self.assertEqual(conflicts, ((1, band),))
                    (fact,) = observe_adjacency_continuity(fit, edges, (band,), coverage,
                        direct_role_authority=direct)
                    self.assertEqual(fact.failure_kind, AdjacencyContinuityFailureKind.UNBOUND_SEPARATOR_WIDTH_CONFLICT)
                    self.assertEqual(fact.separator_band_observation_ids, (band.observation_id,))
                    self.assertEqual(fit.role_bindings, original_bindings)
                    compatible = _unbound_separator_case(missing, direction=direction,
                        partner=200.0 if missing == 1 else 225.0)
                    good_fit, good_edges, good_band, good_coverage, good_direct = compatible
                    self.assertEqual(unbound_registered_adjacency_counterevidence(
                        good_fit, good_edges, good_coverage, separator_bands=(good_band,),
                        direct_role_authority=good_direct), ())

    def test_separator_counterevidence_requires_own_authority_and_full_intervals(self):
        fit, edges, band, coverage, direct = _unbound_separator_case()
        widened = list(edges)
        widened[2] = replace(edges[2], full_position_interval_px=FiniteInterval(209.8, 230.0))
        partial = _unbound_separator_case(regions=2)
        alternative = phase_edge("other-partner", 211.0)
        competing = phase_separator("competing-partner", edges[1], alternative, FiniteInterval(10.6, 11.4))
        incomplete = assess_adjacency_observation_coverage(fit,
            (phase_sequence_measurement("incomplete", FiniteInterval(0.0, 600.0), complete=False),),
            directly_observed_ordinals=())
        mismatched = replace(direct, facts=tuple(replace(fact, evidence_group_id=alternative.observation_id)
            if fact.role_index == 3 else fact for fact in direct.facts))
        for candidate_edges, bands, cov, authority in (
            (edges, (band,), coverage, None),
            (edges, (band,), coverage, mismatched),
            (tuple(widened), (band,), coverage, direct),
            (partial[1], (partial[2],), partial[3], partial[4]),
            ((*edges, alternative), (band, competing), coverage, direct),
            (edges, (band,), incomplete, direct),
        ):
            with self.subTest(bands=tuple(b.observation_id for b in bands), authority=authority):
                self.assertEqual(unbound_registered_adjacency_counterevidence(fit, tuple(candidate_edges), cov,
                    separator_bands=bands, direct_role_authority=authority), ())

    def test_continuity_report_reuses_typed_provenance_checks(self):
        from copy import deepcopy
        from tools.regression.report_sequence_validation import _validate_adjacency_continuity
        from tools.regression.report_sequence_validation import _validate_adjacency_coverage
        from tools.regression.report_validation import _read_common_proof
        from x5crop.report.read_models import typed_read_model

        fit, edges, band, coverage, direct = _unbound_separator_case()
        records = typed_read_model(observe_adjacency_continuity(fit, edges, (band,), coverage,
            direct_role_authority=direct))
        _validate_adjacency_continuity(records, read_proof=_read_common_proof)
        coverage_record = typed_read_model(coverage)
        _validate_adjacency_coverage(coverage_record, read_proof=_read_common_proof)
        forged_coverage = deepcopy(coverage_record)
        forged_coverage[0]["trace_coverage"][0]["covered_intervals_px"][0]["maximum"] = 601.0
        with self.assertRaises(ValueError):
            _validate_adjacency_coverage(forged_coverage, read_proof=_read_common_proof)
        for key, invalid in (("separator_band_observation_ids", []),
                             ("signed_gap_interval_px", {"minimum": -1.0, "maximum": 0.0}),
                             ("relation_ordinal", True), ("end_observation_id", "")):
            forged = deepcopy(records)
            forged[0][key] = invalid
            with self.subTest(key=key), self.assertRaises(ValueError):
                _validate_adjacency_continuity(forged, read_proof=_read_common_proof)

    def test_unbound_native_overlap_is_counterevidence_without_a_new_binding(
        self,
    ) -> None:
        edges = tuple(
            replace(edge, qualified_anchor_roles=(role,))
            for edge, role in zip(
                _edges(100.0, 200.0, 195.0, 295.0),
                (BoundaryRole.START, BoundaryRole.END,
                 BoundaryRole.START, BoundaryRole.END),
                strict=True,
            )
        )
        for bound_role in (1, 2):
            with self.subTest(bound_role=bound_role):
                fit = placement_sequence(
                    phase_template(2),
                    missing=tuple(index for index in range(4) if index != bound_role),
                )
                intervals = list(fit.model_full_role_intervals_px)
                intervals[1:3] = (FiniteInterval(180.0, 240.0),) * 2
                fit = replace(fit, model_full_role_intervals_px=tuple(intervals))
                original_bindings = fit.role_bindings
                (observation,) = _observe(fit, edges)
                self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
                self.assertEqual(
                    observation.failure_kind,
                    AdjacencyContinuityFailureKind.UNBOUND_REGISTERED_OVERLAP,
                )
                self.assertIsNotNone(observation.overlap_observation_id)
                self.assertLess(observation.signed_gap_interval_px.maximum, 0.0)
                self.assertEqual(fit.role_bindings, original_bindings)
                (incomplete,) = _observe(fit, edges, complete=False)
                self.assertNotEqual(incomplete.failure_kind, observation.failure_kind)
                with self.assertRaises(ValueError):
                    replace(observation, overlap_observation_id=None)

        measurement = phase_sequence_measurement(
            "overlap-counterevidence", FiniteInterval(0.0, 500.0),
        )
        coverage = assess_adjacency_observation_coverage(
            fit, (measurement,), directly_observed_ordinals=(),
        )
        pairs = observe_overlap_edge_pairs(
            edges, (), (measurement,), direction=1, maximum_overlap_px=12.0,
        )
        self.assertEqual(len(pairs), 1)
        self.assertEqual(
            unbound_registered_adjacency_counterevidence(
                fit, edges, coverage, (pairs[0], pairs[0]),
            ),
            (),
        )
        restricted = tuple(replace(item,
            required_interval_px=FiniteInterval(210.0, 240.0),
            trace_coverage=tuple(replace(trace,
                covered_intervals_px=(FiniteInterval(210.0, 240.0),),
                required_coordinate_count=31, covered_coordinate_count=31)
                for trace in item.trace_coverage),
            required_coordinate_count=31 * item.required_trace_count,
            covered_coordinate_count=31 * item.covered_trace_count) for item in coverage)
        self.assertEqual(unbound_registered_adjacency_counterevidence(fit, edges, restricted, pairs), ())

    def test_overlap_is_refit_in_the_single_grid_and_prefix_model(self) -> None:
        edges = tuple(
            replace(
                phase_edge(f"overlap:{index}", coordinate),
                qualified_anchor_roles=(role,),
                canonical_direction_degrees=0.0,
                fit_direction_interval_degrees=FiniteInterval.exact(0.0),
                full_direction_interval_degrees=FiniteInterval.exact(0.0),
            )
            for index, (coordinate, role) in enumerate(
                (
                    (100.0, BoundaryRole.START),
                    (200.0, BoundaryRole.END),
                    (195.0, BoundaryRole.START),
                    (295.0, BoundaryRole.END),
                    (300.0, BoundaryRole.START),
                    (400.0, BoundaryRole.END),
                )
            )
        )
        base = phase_template(3)
        spec = replace(
            base,
            pitch_px=105.0,
            nominal_gap_px=5.0,
            phase_lattice_authority=replace(
                base.phase_lattice_authority,
                period_px=105.0,
            ),
        )
        measurement = phase_sequence_measurement(
            "overlap-end-to-end",
            FiniteInterval(0.0, 420.0),
        )
        overlap_pairs = observe_overlap_edge_pairs(
            edges,
            (),
            (measurement,),
            direction=1,
            maximum_overlap_px=12.0,
        )
        self.assertEqual(len(overlap_pairs), 1)

        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=edges,
                separator_bands=(),
                template=spec,
                calibrated_nominal_grid_prior=(
                    unavailable_nominal_grid_prior(spec)
                ),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=FiniteInterval.exact(100.0),
                sequence_measurement_sets=(measurement,),
                overlap_edge_pair_observations=overlap_pairs,
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.model_role_positions_px,
            (100.0, 200.0, 195.0, 295.0, 300.0, 400.0),
        )
        self.assertEqual(len(result.best.adjacency_relations), 1)
        self.assertIsInstance(
            result.best.adjacency_relations[0],
            OverlapRelation,
        )
        self.assertEqual(
            result.adjacency_continuity_observations[0].kind,
            AdjacencyContinuityKind.OVERLAP,
        )

    def test_one_all_overlap_adjacency_does_not_fabricate_pitch_rank(
        self,
    ) -> None:
        edges = tuple(
            replace(
                phase_edge(f"rank-two-overlap:{index}", coordinate),
                qualified_anchor_roles=(role,),
                canonical_direction_degrees=0.0,
                fit_direction_interval_degrees=FiniteInterval.exact(0.0),
                full_direction_interval_degrees=FiniteInterval.exact(0.0),
            )
            for index, (coordinate, role) in enumerate(
                (
                    (100.0, BoundaryRole.START),
                    (200.0, BoundaryRole.END),
                    (195.0, BoundaryRole.START),
                    (295.0, BoundaryRole.END),
                )
            )
        )
        base = phase_template(2)
        spec = replace(
            base,
            pitch_px=105.0,
            nominal_gap_px=5.0,
            phase_lattice_authority=replace(
                base.phase_lattice_authority,
                period_px=105.0,
            ),
        )
        measurement = phase_sequence_measurement(
            "rank-two-overlap",
            FiniteInterval(0.0, 320.0),
        )
        overlap_pairs = observe_overlap_edge_pairs(
            edges,
            (),
            (measurement,),
            direction=1,
            maximum_overlap_px=12.0,
        )

        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=edges,
                separator_bands=(),
                template=spec,
                calibrated_nominal_grid_prior=(
                    unavailable_nominal_grid_prior(spec)
                ),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=FiniteInterval.exact(100.0),
                sequence_measurement_sets=(measurement,),
                overlap_edge_pair_observations=overlap_pairs,
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.CALIBRATED_NOMINAL_GRID_AUTHORITY_UNAVAILABLE,
        )
        assert result.global_lattice_authority is not None
        self.assertEqual(result.global_lattice_authority.joint_constraint_rank, 2)

    def test_selected_shared_edge_is_typed_contact(self) -> None:
        fit, edges = _contact_fit()

        (observation,) = _observe(fit, edges)
        analysis = derive_adjacency_relations(fit, (observation,))

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertEqual(observation.kind, AdjacencyContinuityKind.CONTACT)
        self.assertEqual(
            observation.basis,
            AdjacencyContinuityBasis.SHARED_PHYSICAL_EDGE,
        )
        self.assertEqual(
            observation.end_observation_id,
            observation.next_start_observation_id,
        )
        self.assertEqual(
            observation.signed_gap_interval_px,
            FiniteInterval.exact(0.0),
        )
        self.assertEqual(analysis.pattern, ResidualPattern.MEASURED_RELATIONS)
        self.assertEqual(analysis.relations, fit.adjacency_relations)

    def test_contact_requires_complete_registered_corridor(self) -> None:
        fit, edges = _contact_fit()

        (observation,) = _observe(fit, edges, complete=False)

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
        )
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.REGISTERED_COVERAGE_INCOMPLETE,
        )

    def test_unique_positive_material_band_supports_normal_separator(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 220.0, 320.0)
        band = phase_separator(
            "separator:normal",
            edges[1],
            edges[2],
            FiniteInterval(19.8, 20.2),
        )

        (observation,) = _observe(fit, edges, (band,))

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.SEPARATOR_MATERIAL,
        )
        self.assertEqual(
            observation.basis,
            AdjacencyContinuityBasis.POSITIVE_SEPARATOR_BAND,
        )
        self.assertTrue(observation.directly_observed_separator)

    def test_complete_corridor_records_only_absence_of_counterevidence(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 220.0, 320.0)

        (observation,) = _observe(fit, edges)

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.NO_COUNTEREVIDENCE_OBSERVED,
        )
        self.assertEqual(
            observation.basis,
            AdjacencyContinuityBasis.COMPLETE_REGISTERED_CORRIDOR,
        )
        self.assertFalse(observation.directly_observed_separator)

    def test_registered_material_conflict_stays_unresolved(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 220.0, 320.0)
        band = phase_separator(
            "separator:conflict",
            edges[1],
            edges[2],
            FiniteInterval(19.8, 20.2),
        )
        band = replace(
            band,
            material_support_region_count=1,
            material_regions=tuple(
                region
                if region.region_index == 0
                else replace(
                    region,
                    state=SeparatorMaterialRegionState.TONE_UNRESOLVED,
                )
                for region in band.material_regions
            ),
            evidence_state=BoundaryEvidenceState.CONTRADICTION,
        )

        (observation,) = _observe(fit, edges, (band,))

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.SEPARATOR_MATERIAL_UNRESOLVED,
        )
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.SEPARATOR_MATERIAL_UNRESOLVED,
        )
        self.assertEqual(
            observation.separator_band_observation_ids,
            (band.observation_id,),
        )

    def test_multiple_separator_bands_preserve_provenance_and_block(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 220.0, 320.0)
        bands = tuple(
            phase_separator(
                f"separator:{index}",
                edges[1],
                edges[2],
                FiniteInterval(19.8, 20.2),
            )
            for index in range(2)
        )

        (observation,) = _observe(fit, edges, bands)

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(observation.kind, AdjacencyContinuityKind.UNRESOLVED)
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.MULTIPLE_SEPARATOR_BANDS,
        )
        self.assertEqual(
            observation.separator_band_observation_ids,
            tuple(sorted(band.observation_id for band in bands)),
        )

    def test_reversed_direct_edges_with_complete_coverage_prove_overlap(
        self,
    ) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 195.0, 295.0)

        (observation,) = _observe(fit, edges)
        analysis = derive_adjacency_relations(fit, (observation,))

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.OVERLAP,
        )
        self.assertEqual(
            observation.basis,
            AdjacencyContinuityBasis.INDEPENDENT_REVERSED_EDGES,
        )
        self.assertEqual(analysis.pattern, ResidualPattern.MEASURED_RELATIONS)
        self.assertIsInstance(analysis.relations[0], OverlapRelation)
        relation = analysis.relations[0]
        assert isinstance(relation, OverlapRelation)
        self.assertEqual(
            relation.supporting_observation_ids,
            (edges[1].observation_id, edges[2].observation_id),
        )
        self.assertLess(relation.canonical_signed_gap_px, 0.0)

    def test_reversed_edges_without_registered_pair_stay_unresolved(
        self,
    ) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 195.0, 295.0)

        (observation,) = _observe(
            fit,
            edges,
            register_overlap=False,
        )

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(observation.kind, AdjacencyContinuityKind.UNRESOLVED)
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.OVERLAP_OBSERVATION_UNAVAILABLE,
        )

    def test_material_conflict_blocks_reversed_edge_overlap(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 195.0, 295.0)
        band = phase_separator(
            "separator:conflict",
            edges[1],
            edges[2],
            FiniteInterval(4.8, 5.2),
        )
        band = replace(
            band,
            material_support_region_count=1,
            material_regions=tuple(
                region
                if region.region_index == 0
                else replace(
                    region,
                    state=SeparatorMaterialRegionState.TONE_UNRESOLVED,
                )
                for region in band.material_regions
            ),
            evidence_state=BoundaryEvidenceState.CONTRADICTION,
        )

        (observation,) = _observe(fit, edges, (band,))

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.SEPARATOR_MATERIAL_UNRESOLVED,
        )

    def test_reversed_edges_without_complete_coverage_do_not_prove_overlap(
        self,
    ) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 195.0, 295.0)

        (observation,) = _observe(fit, edges, complete=False)

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
        )
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.REGISTERED_COVERAGE_INCOMPLETE,
        )

    def test_gap_uncertainty_crossing_zero_remains_unresolved(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 200.0, 300.0)

        (observation,) = _observe(fit, edges)

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.UNRESOLVED,
        )
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.SIGNED_GAP_CROSSES_ZERO,
        )

    def test_incomplete_corridor_cannot_claim_no_counterevidence(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 220.0, 320.0)

        (observation,) = _observe(fit, edges, complete=False)

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
        )
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.REGISTERED_COVERAGE_INCOMPLETE,
        )


if __name__ == "__main__":
    unittest.main()
