"""Raw material provenance must precede any terminal/ordinal hypothesis."""
from copy import deepcopy
from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    phase_edge, phase_separator, phase_template, unavailable_nominal_grid_prior,
)
from tools.tests.photo_geometry_support import make_side_measurement_set
from tools.regression.material_registration_validation import _derived_physical_records, validate_registered_material_evidence
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.observation_types import (
    BasicAxisProfile, ProfileRun, SeparatorBandMeasurementBasis, SeparatorMaterialPolarity,
)
from x5crop.detection.photo_geometry.outer_material import observe_outer_material_boundaries, validate_material_band_sources
from x5crop.detection.photo_geometry.template_phase_model import TemplatePhaseInput
from x5crop.domain import FiniteInterval, ObservationId, PositiveInterval
from x5crop.report.read_models import typed_read_model


def _measurement():
    measured = make_side_measurement_set(((10., 20.),) * 3)
    return replace(measured, transitions=tuple(
        replace(point, polarity=(-1 if point.canonical_coordinate_px == 10. else 1))
        for point in measured.transitions))


def _profiles(edges):
    runs = tuple(ProfileRun(edge.run_id, edge.discovery_interval_px, edge.transition_ids, edge.trace_coordinates_px,
                            None, edge.qualified_anchor_roles, edge.support_fraction, edge.continuous_support_fraction,
                            edge.fit_residual_px, 10., True) for edge in edges)
    return {basis: BasicAxisProfile("sequence", 200, (0, 10, 20) if basis == SeparatorBandMeasurementBasis.DIRECT_TRACE else (),
                                   runs if basis == SeparatorBandMeasurementBasis.DIRECT_TRACE else ())
            for basis in SeparatorBandMeasurementBasis}


def _source_kwargs(edges):
    profiles = _profiles(edges)
    return {"transition_by_id": {str(point.transition_id): point for point in _measurement().transitions},
            "profiles": profiles,
            "registered_region_transition_ids": {basis: tuple(run.transition_ids for run in profile.runs)
                                                  for basis, profile in profiles.items()}}


def _fixture():
    measured = _measurement()
    edges = tuple(replace(phase_edge(name, position), qualified_anchor_roles=(BoundaryRole.START,),
                          polarity=polarity,
                          transition_ids=tuple(point.transition_id for point in measured.transitions
                                               if point.canonical_coordinate_px == position))
                  for name, position, polarity in (("native:exterior", 10., -1), ("native:inner", 20., 1)))
    gap = FiniteInterval(edges[1].fit_position_interval_px.minimum-edges[0].fit_position_interval_px.maximum,
                         edges[1].fit_position_interval_px.maximum-edges[0].fit_position_interval_px.minimum)
    band = phase_separator("native:raw-material", *edges, gap)
    band = replace(band, transition_ids=tuple(sorted((*edges[0].transition_ids, *edges[1].transition_ids))),
                   material_regions=tuple(replace(region, sample_count=1) for region in band.material_regions))
    outer = observe_outer_material_boundaries((band,), (), edges, direction=1,
        maximum_material_width_px=20., intrinsic_authority_edge_ids=frozenset(e.observation_id for e in edges))
    template = phase_template(2)
    phase = TemplatePhaseInput(observations=edges, template=template, separator_bands=(band,),
        scale_px_per_mm=PositiveInterval.exact(1.), holder_span_px=None, phase_authority_px=None,
        calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template),
        outer_material_boundaries=outer,
        sequence_measurement_sets=(measured,))
    profiles = _profiles(edges)
    lane = {"phase_input":typed_read_model(phase),
        "search":{key: typed_read_model(profiles[basis]) for basis, key in (
            (SeparatorBandMeasurementBasis.DIRECT_TRACE, "sequence_profile"),
            (SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE, "cross_height_profile"),
            (SeparatorBandMeasurementBasis.BROAD_MATERIAL_TRACE, "broad_material_profile"))}, "observations":{
        "sequence_edges":typed_read_model(edges), "separator_bands":typed_read_model((band,)),
        "raw_material_bands":typed_read_model((band,)), "outer_material_boundaries":typed_read_model(outer),
        "cross_height_edges":[], "broad_material_edges":[],
        "side_transition_regions":[{"transition_ids": list(map(str, edge.transition_ids))} for edge in edges],
        "cross_height_transition_regions":[], "broad_material_transition_regions":[],
        "cross_height_edge_resolutions":[], "broad_material_edge_resolutions":[]}}
    return edges, band, outer, lane


class NativeMaterialRegistrationContractTest(unittest.TestCase):
    def test_complete_original_material_replays_without_claiming_a_photo_ordinal(self):
        edges, band, outer, lane = _fixture()
        validate_material_band_sources((band,), edges, (), (), (), outer, **_source_kwargs(edges))
        validate_registered_material_evidence(lane)
        self.assertEqual(len(outer), 1)
        self.assertFalse(hasattr(outer[0], "lane_ordinal"))
        self.assertFalse(hasattr(outer[0], "terminal_role_index"))

    def test_nonexistent_support_id_cannot_be_shared_by_consistent_copies(self):
        _edges, _band, _outer, lane = _fixture()
        for parent in (lane["observations"], lane["phase_input"]):
            parent["outer_material_boundaries"][0]["supporting_band_observation_ids"] = ["separator-band:999"]
        with self.assertRaisesRegex(ValueError, "registered raw material pair"):
            validate_registered_material_evidence(lane)

    def test_raw_ledger_cannot_be_omitted_or_emptied(self):
        for value in (None, []):
            _edges, _band, _outer, lane = _fixture()
            lane["observations"]["raw_material_bands"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_registered_material_evidence(lane)

    def test_source_basis_run_gap_and_transition_cannot_be_substituted(self):
        edges, band, outer, _lane = _fixture()
        for changed in (
            replace(band, measurement_basis=SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE),
            replace(band, left_run_id="foreign:run"),
            replace(band, gap_interval_px=FiniteInterval(8., 12.)),
            replace(band, transition_ids=(ObservationId("foreign:transition"),)),
        ):
            with self.subTest(band=changed), self.assertRaises(ValueError):
                validate_material_band_sources((changed,), edges, (), (), (), outer, **_source_kwargs(edges))

    def test_duplicate_raw_material_does_not_create_another_independent_fact(self):
        edges, band, outer, _lane = _fixture()
        with self.assertRaisesRegex(ValueError, "registered once"):
            validate_material_band_sources((band, band), edges, (), (), (), outer, **_source_kwargs(edges))
        renamed = replace(band, observation_id=ObservationId("separator-band:999"))
        with self.assertRaisesRegex(ValueError, "registered once"):
            validate_material_band_sources((band, renamed), edges, (), (), (), outer, **_source_kwargs(edges))

    def test_other_physical_pair_cannot_supply_the_original_outer_material(self):
        edges, band, outer, _lane = _fixture()
        foreign = replace(edges[1], observation_id=ObservationId("foreign:edge"))
        changed = replace(band, right_edge_observation_id=foreign.observation_id)
        with self.assertRaisesRegex(ValueError, "registered raw material pair"):
            validate_material_band_sources((changed,), (*edges, foreign), (), (), (), outer, **_source_kwargs(edges))

    def test_existing_material_does_not_authorize_forged_outer_metadata(self):
        _edges, _band, _outer, lane = _fixture()
        changed = deepcopy(lane)
        changed["observations"]["outer_material_boundaries"][0]["material_interval_px"]["maximum"] += 1.
        with self.assertRaisesRegex(ValueError, "original registered evidence"):
            validate_registered_material_evidence(changed)

    def test_consistent_copies_cannot_drop_one_end_or_part_of_a_paired_trace(self):
        edges, band, _outer, original = _fixture()
        for transition_ids in ((edges[0].transition_ids[0],), edges[0].transition_ids, band.transition_ids[:-1]):
            lane = deepcopy(original)
            for parent, key in ((lane["observations"], "raw_material_bands"),
                                (lane["observations"], "separator_bands"),
                                (lane["phase_input"], "separator_bands")):
                parent[key][0]["transition_ids"] = list(map(str, transition_ids))
            with self.subTest(ids=transition_ids), self.assertRaisesRegex(ValueError, "paired trace"):
                validate_registered_material_evidence(lane)

    def test_complete_pairs_cannot_claim_material_in_an_unobserved_region(self):
        edges, band, _outer, lane = _fixture()
        keep = [str(identity) for identity in band.transition_ids
                if _source_kwargs(edges)["transition_by_id"][str(identity)].trace_coordinate_px != 20]
        for parent, key in ((lane["observations"], "raw_material_bands"),
                            (lane["observations"], "separator_bands"),
                            (lane["phase_input"], "separator_bands")):
            parent[key][0]["transition_ids"] = keep
        with self.assertRaisesRegex(ValueError, "paired trace"):
            validate_registered_material_evidence(lane)

    def test_consistent_material_polarity_cannot_override_original_edge_polarities(self):
        _edges, _band, _outer, lane = _fixture()
        for parent, key in ((lane["observations"], "raw_material_bands"),
                            (lane["observations"], "separator_bands"),
                            (lane["phase_input"], "separator_bands")):
            parent[key][0]["material_polarity"] = SeparatorMaterialPolarity.LIGHT.value
        for parent in (lane["observations"], lane["phase_input"]):
            parent["outer_material_boundaries"][0]["material_polarities"] = [SeparatorMaterialPolarity.LIGHT.value]
        with self.assertRaisesRegex(ValueError, "polarity"):
            validate_registered_material_evidence(lane)

    def test_reversed_raw_source_pair_is_rejected(self):
        edges, band, outer, _lane = _fixture()
        changed = replace(band, left_edge_observation_id=edges[1].observation_id,
                          right_edge_observation_id=edges[0].observation_id,
                          left_run_id=edges[1].run_id, right_run_id=edges[0].run_id,
                          gap_interval_px=FiniteInterval.exact(0.))
        with self.assertRaisesRegex(ValueError, "geometry or polarity"):
            validate_material_band_sources((changed,), edges, (), (), (), outer, **_source_kwargs(edges))

    def test_unfitted_registered_run_still_blocks_native_material_adjacency(self):
        edges, _band, _outer, lane = _fixture()
        measurement = lane["phase_input"]["sequence_measurement_sets"][0]
        middle_ids = []
        for point in _measurement().transitions:
            if point.canonical_coordinate_px != 10.:
                continue
            middle = replace(point, transition_id=ObservationId(f"middle:{point.trace_ordinal}"),
                             canonical_coordinate_px=15., localization_interval_px=FiniteInterval(14.8, 15.2),
                             physical_position_interval_px=FiniteInterval(14.5, 15.5))
            measurement["transitions"].append(typed_read_model(middle))
            middle_ids.append(middle.transition_id)
        middle_run = replace(_profiles(edges)[SeparatorBandMeasurementBasis.DIRECT_TRACE].runs[0],
                             run_id="unfitted:middle", coordinate_interval_px=FiniteInterval(14.8, 15.2),
                             transition_ids=tuple(middle_ids))
        lane["search"]["sequence_profile"]["runs"].insert(1, typed_read_model(middle_run))
        lane["observations"]["side_transition_regions"].append({"transition_ids": list(map(str, middle_ids))})
        with self.assertRaisesRegex(ValueError, "native adjacency"):
            validate_registered_material_evidence(lane)
        lane["search"]["sequence_profile"]["runs"].pop(1)
        with self.assertRaisesRegex(ValueError, "complete registered region transitions"):
            validate_registered_material_evidence(lane)

    def test_only_legal_derived_run_local_names_may_be_remapped(self):
        _edges, _band, _outer, original = _fixture()
        for identity in ("foreign-authority-name", "outer-material-boundary:0", "outer-material-boundary:01"):
            lane = deepcopy(original)
            for parent in (lane["observations"], lane["phase_input"]):
                parent["outer_material_boundaries"][0].update(observation_id=identity, evidence_group_id=identity)
            with self.subTest(identity=identity), self.assertRaisesRegex(ValueError, "run-local name"):
                validate_registered_material_evidence(lane)
        for parent in (original["observations"], original["phase_input"]):
            parent["outer_material_boundaries"][0].update(
                observation_id="outer-material-boundary:999", evidence_group_id="outer-material-boundary:999")
        validate_registered_material_evidence(original)

    def test_profile_cannot_skip_a_registered_trace_with_consistently_shortened_material(self):
        edges, _band, _outer, lane = _fixture()
        points = _source_kwargs(edges)["transition_by_id"]
        lane["search"]["sequence_profile"]["trace_coordinates_px"] = [0, 20]
        for parent, key in ((lane["observations"], "raw_material_bands"),
                            (lane["observations"], "separator_bands"),
                            (lane["phase_input"], "separator_bands")):
            band = parent[key][0]
            band["transition_ids"] = [identity for identity in band["transition_ids"]
                                      if points[identity].trace_coordinate_px != 10]
            band["material_regions"] = [region for region in band["material_regions"] if region["region_index"] != 1]
            band["material_support_region_count"] = 2
        for parent in (lane["observations"], lane["phase_input"]):
            parent["outer_material_boundaries"][0]["independent_support_region_count"] = 2
        with self.assertRaisesRegex(ValueError, "complete registered trace inventory"):
            validate_registered_material_evidence(lane)

    def test_derived_names_are_unique_and_physical_multiplicity_is_preserved(self):
        _edges, band, outer, _lane = _fixture()
        with self.assertRaisesRegex(ValueError, "one-to-one"):
            _derived_physical_records((outer[0], outer[0]), outer=True)
        renamed = replace(outer[0], observation_id=ObservationId("outer-material-boundary:999"),
                          evidence_group_id=ObservationId("outer-material-boundary:999"))
        records = _derived_physical_records((outer[0], renamed), outer=True)
        self.assertEqual(sum(records.values()), 2)
        self.assertNotEqual(records, _derived_physical_records(outer, outer=True))
        aggregate = replace(band, measurement_basis=SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE)
        with self.assertRaisesRegex(ValueError, "run-local name"):
            _derived_physical_records((aggregate,))


if __name__ == "__main__":
    unittest.main()
