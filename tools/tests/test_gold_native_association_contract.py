"""Keep measurement, conditioned membership and reference authority distinct."""

from copy import deepcopy
from dataclasses import replace
import unittest

from tools.regression.gold_native_association import native_association_diagnostic
from tools.regression.report_validation import _read_common_proof
from tools.tests.photo_geometry_support import make_side_measurement_set
from tools.tests.template_test_support import phase_edge
from x5crop.domain import ObservationId
from x5crop.report.read_models import typed_read_model


def _fixture():
    measurement = make_side_measurement_set(((10., 20.),) * 3)
    edges = [replace(phase_edge(name, position), transition_ids=tuple(
        point.transition_id for point in measurement.transitions if point.canonical_coordinate_px == position))
        for name, position in (("edge:start", 10.), ("edge:end", 20.))]
    bindings = [{"observation_id": str(edge.observation_id)} for edge in edges]
    members = [{"record_ordinal": index, "input_fit": {"role_bindings": group}}
        for index, group in enumerate((bindings + [None, None], [None, None] + bindings))]
    proofs = [{"scope_id": "scope:complete", "record_ordinal": index, "gaps": [] if index == 0 else ["unqualified"],
               "native_grid_association": None, "admission": None} for index in range(2)]
    lane = {"phase_input": {"sequence_measurement_sets": typed_read_model((measurement,))},
        "base_cross_registration": {"observations": []},
        "observations": {"sequence_edges": typed_read_model(tuple(edges)), "cross_height_edges": [],
                         "broad_material_edges": [], "raw_top_bottom_lines": []},
        "phase_competition": {"competition_scopes": [{"scope_id": "scope:complete", "members": members}]},
        "complete_phase_output": {"members": proofs, "state": "unavailable", "common_outputs": [],
                                  "refuted_member_keys": [], "common_member_keys": [["scope:complete", 0], ["scope:complete", 1]]}}
    references = [{"ordinal": 1, "role": role, "line_id": "gold:" + role, "review_basis": "directly_visible",
                   "position_at_trace_zero_px": position, "slope": 0.} for role, position in (("start", 10.), ("end", 20.))]
    return lane, references


def _audit(lane, references):
    return native_association_diagnostic(lane, references, count=2, read_proof=_read_common_proof)


class GoldNativeAssociationContractTest(unittest.TestCase):
    def test_candidate_local_cross_refinements_do_not_enter_independent_spatial_probe(self):
        lane, references = _fixture()
        baseline = _audit(lane, references)["native_spatial_incidence"]
        lane["observations"]["raw_top_bottom_lines"] = [{"observation_id": "candidate-local:1"}]
        self.assertEqual(_audit(lane, references)["native_spatial_incidence"], baseline)

    def test_same_native_pair_keeps_all_conditioned_ordinals_and_their_qualification(self):
        lane, references = _fixture()
        original = deepcopy(lane)
        audit = _audit(lane, references)
        self.assertEqual(audit["member_count"], 2)
        self.assertEqual(audit["qualified_member_count"], 1)
        assignments = audit["reference_pairs"][0]["conditioned_input_pairs"][0]["assignments"]
        self.assertEqual([item["ordinal"] for item in assignments], [1, 2])
        self.assertEqual(assignments[0]["qualified_member_keys"], [["scope:complete", 0]])
        self.assertEqual(assignments[1]["qualified_member_keys"], [])
        self.assertEqual(audit["reference_pairs"][0]["pair_identity_origin"], "user_reference_only")
        self.assertEqual(audit["evidence_scope"], "gold_only_not_runtime_authority")
        self.assertEqual(lane, original)

    def test_marginal_hull_cannot_hide_one_incompatible_raw_transition(self):
        lane, references = _fixture()
        references[0].update(position_at_trace_zero_px=8., slope=.2)  # Matches the marginal at reference trace 10.
        result = _audit(lane, references)["reference_boundaries"][0]
        match = next(item for item in result["matches"] if item["observation_id"] == "edge:start")
        self.assertTrue(match["native_interval_match"])
        self.assertFalse(match["complete_raw_transition_match"])
        self.assertTrue(match["incompatible_transition_ids"])
        self.assertNotEqual(result["signal_class"], "intrinsic_coordinate_observed")

    def test_all_raw_aggregate_alternatives_are_retained_without_coordinate_grants(self):
        lane, references = _fixture()
        raw = lane["observations"]["sequence_edges"].pop()
        raw["measurement_basis"] = "broad_material_trace"
        lane["observations"]["broad_material_edges"] = [raw, {**raw, "observation_id": "edge:alternative"}]
        result = _audit(lane, references)["reference_boundaries"][1]
        self.assertEqual(result["signal_class"], "aggregate_raw_only")
        self.assertEqual(len(result["matches"]), 2)
        self.assertTrue(all(not item["intrinsic_coordinate_bases"] for item in result["matches"]))
        self.assertFalse(_audit(lane, references)["reference_pairs"][0]["conditioned_input_pairs"])

    def test_width_estimate_reference_does_not_become_direct_evidence(self):
        lane, references = _fixture()
        references[0]["review_basis"] = "human_width_estimate"
        self.assertEqual(_audit(lane, references)["reference_boundaries"][0]["signal_class"], "reference_not_direct")

    def test_missing_edge_is_distinct_from_an_observed_unbound_role(self):
        lane, references = _fixture()
        references[1]["position_at_trace_zero_px"] = 80.
        result = _audit(lane, references)
        self.assertEqual(result["reference_boundaries"][1]["signal_class"], "no_registered_edge_match")
        self.assertEqual(result["reference_boundaries"][0]["signal_class"], "intrinsic_coordinate_observed")

    def test_raw_points_survive_when_no_complete_edge_was_fitted(self):
        lane, references = _fixture()
        lane["observations"]["sequence_edges"].pop()
        boundary = _audit(lane, references)["reference_boundaries"][1]
        self.assertEqual(boundary["signal_class"], "no_registered_edge_match")
        raw = next(item for item in boundary["raw_reference_point_candidates"] if item["basis"] == "transitions")
        self.assertEqual(len(raw["points"]), 3)
        self.assertEqual(raw["union_spatial_support_region_count"], 3)
        self.assertEqual([query["spatial_support_region_count"] for query in raw["query_support"]], [3])
        self.assertFalse(boundary["matches"])

    def test_raw_query_support_is_not_replaced_by_cross_query_union(self):
        lane, references = _fixture()
        queries = lane["phase_input"]["sequence_measurement_sets"]
        second = deepcopy(queries[0])
        second["query"]["query_id"] = "query:second"
        second["coverage"]["query_id"] = "query:second"
        first_points = queries[0]["transitions"]
        second["transitions"] = [{**point, "transition_id": point["transition_id"] + ":second", "query_id": "query:second"}
            for point in first_points if point["canonical_coordinate_px"] == 20. and point["trace_coordinate_px"] != 0]
        queries[0]["transitions"] = [point for point in first_points
            if point["canonical_coordinate_px"] != 20. or point["trace_coordinate_px"] == 0]
        lane["observations"]["sequence_edges"].pop()
        queries.append(second)
        result = _audit(lane, references)["reference_boundaries"][1]
        raw = next(item for item in result["raw_reference_point_candidates"] if item["basis"] == "transitions")
        self.assertEqual([query["query_id"] for query in raw["query_support"]],
                         [queries[0]["query"]["query_id"], "query:second"])
        self.assertEqual([query["spatial_support_region_count"] for query in raw["query_support"]], [1, 2])
        self.assertEqual(raw["union_spatial_support_region_count"], 3)
        self.assertEqual(result["signal_class"], "no_registered_edge_match")

    def test_legal_shared_contact_roles_are_not_an_ordinal_conflict(self):
        lane, references = _fixture()
        shared = {"observation_id": "edge:end"}
        lane["phase_competition"]["competition_scopes"][0]["members"] = [{"record_ordinal": 0,
            "input_fit": {"role_bindings": [{"observation_id": "edge:start"}, shared, shared, None]}}]
        lane["complete_phase_output"]["members"].pop()
        references.append({**references[1], "ordinal": 2, "role": "start", "line_id": "gold:shared-start"})
        result = _audit(lane, references)
        self.assertEqual(result["conditioned_ordinal_conflicts"], [])
        self.assertEqual(result["shared_contact_uses"], [{"member_key": ["scope:complete", 0],
            "relation_ordinal": 1, "observation_id": "edge:end"}])
        for boundary in result["reference_boundaries"][1:]:
            assignments = boundary["matches"][0]["conditioned_input_ordinals"]
            self.assertEqual([item["ordinal"] for item in assignments], [boundary["ordinal"]])

    def test_historical_member_cannot_be_dropped_from_the_audit(self):
        lane, references = _fixture()
        lane["complete_phase_output"]["members"].pop()
        with self.assertRaisesRegex(ValueError, "historical membership"):
            _audit(lane, references)

    def test_optional_complete_proof_preserves_history_without_inventing_a_verdict(self):
        lane, references = _fixture()
        lane["complete_phase_output"] = None
        result = _audit(lane, references)
        self.assertEqual(result["member_count"], 2)
        self.assertIsNone(result["qualified_member_count"])
        self.assertEqual(result["member_output_evaluation_state"], "not_evaluated")
        self.assertIsNone(result["complete_output_state"])
        self.assertIsNone(result["complete_common_output_count"])
        self.assertEqual(result["reference_boundaries"][0]["signal_class"], "intrinsic_coordinate_observed")
        assignments = result["reference_pairs"][0]["conditioned_input_pairs"][0]["assignments"]
        self.assertEqual([item["ordinal"] for item in assignments], [1, 2])
        self.assertTrue(all(item["qualified_member_keys"] is None for item in assignments))

    def test_missing_or_duplicated_native_transition_fails_loudly(self):
        for duplicate in (False, True):
            lane, references = _fixture()
            if duplicate:
                points = lane["phase_input"]["sequence_measurement_sets"][0]["transitions"]
                points.append(deepcopy(points[0]))
                error = ValueError
            else:
                lane["observations"]["sequence_edges"][0]["transition_ids"] = [str(ObservationId("missing:point"))]
                error = KeyError
            with self.subTest(duplicate=duplicate), self.assertRaises(error):
                _audit(lane, references)

    def test_gap_groups_keep_overlapping_members_and_original_model_coordinates(self):
        lane, references = _fixture()
        member = lane["complete_phase_output"]["members"][1]
        member["native_grid_association"] = {"grid_authority_failure": "nominal_grid_state_missing",
            "uncompiled_grid_anchor_role_indices": [0], "unqualified_grid_anchor_role_indices": [0],
            "facts": [{"signed_gap_interval_px": {"minimum": -4., "maximum": 6.}}]}
        member["admission"] = {"current_holder_admitted": False, "current_holder_violations": [
            {"role_index": 0, "observation_id": None, "model_coordinate_px": -50.}]}
        result = _audit(lane, references)
        self.assertTrue(result["member_gap_groups_may_overlap"])
        for group in ("coordinate_or_coverage_members", "mixed_sign_members", "unbound_holder_terminal_members"):
            self.assertEqual([item["member_key"] for item in result[group]], [["scope:complete", 1]])
        self.assertEqual(result["unbound_holder_terminal_members"][0]["violations"][0]["model_coordinate_px"], -50.)

    def test_bound_or_nonterminal_holder_violation_is_not_called_an_unbound_terminal(self):
        for role, identity in ((1, None), (0, "edge:start")):
            lane, references = _fixture()
            lane["complete_phase_output"]["members"][0]["admission"] = {
                "current_holder_admitted": False,
                "current_holder_violations": [{"role_index": role, "observation_id": identity}]}
            with self.subTest(role=role, identity=identity):
                self.assertEqual(_audit(lane, references)["unbound_holder_terminal_members"], [])


if __name__ == "__main__":
    unittest.main()
