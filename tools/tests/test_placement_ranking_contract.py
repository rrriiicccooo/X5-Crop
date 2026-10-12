from __future__ import annotations

from copy import deepcopy
import unittest

from tools.regression.placement_ranking import (
    INDEPENDENT_PHASE_ROLE_SCOPE, RANKING_SCHEMA,
    FEATURE_NAMES, RankingExample, _examples, _fit_model, _fold_assignments,
    _model_id, _scores, _source_weights, _training_transform,
    build_development_ranking, validate_development_ranking,
)
from tools.tests.template_runtime_test_support import retained_proposal_fixture
from x5crop.report.read_models import typed_read_model


class PlacementRankingContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposals = {
            role: typed_read_model(retained_proposal_fixture(f"placement:{role}"))
            for role in ("primary", "runner")
        }

    def _records(self):
        records = []
        for index in range(10):
            candidates = []
            for role, value in (("primary", 0.0), ("runner", 1.0)):
                proposal = deepcopy(self.proposals[role])
                proposal["acceptability_features"]["values"][0]["value"] = value
                candidates.append({
                    "placement_id": proposal["placement_id"], "lane_id": proposal["lane_id"],
                    "role": role, "generation_state": "generated",
                    "geometry_conformance": "safe" if value else "unsafe",
                    "acceptability_features": proposal["acceptability_features"],
                    "output_footprints": proposal["output_footprints"],
                })
            records.append({"sample_id": f"S{index:03}", "source_sha256": f"{index:064x}",
                            "cohort_role": "nominal", "retained_placement_gold_labels": candidates})
        return records

    def _example(self, source, value, safe, *, task=None):
        return RankingExample(task or f"S{source}", f"{source:064x}", f"P{value}",
                              "primary", safe, (value,) + (None,) * (len(FEATURE_NAMES) - 1))

    def test_same_source_count_variants_share_fold_and_source_weight(self):
        records = self._records()
        variant = deepcopy(records[0])
        variant["sample_id"] = "count-variant"
        records.append(variant)
        folds = _fold_assignments(records)
        self.assertEqual(len(folds), 10)
        examples = _examples(records)
        weights = _source_weights(examples)
        for source in folds:
            self.assertAlmostEqual(sum(weight for item, weight in zip(examples, weights)
                                       if item.source_sha256 == source), 0.1)
        artifact = build_development_ranking(records)
        validate_development_ranking(artifact, records)
        for fold, model in enumerate(artifact["fold_models"]):
            self.assertFalse(set(model["training_source_sha256s"]) &
                             {source for source, assigned in folds.items() if assigned == fold})

    def test_transform_and_fold_fit_do_not_consume_heldout_features_or_labels(self):
        records = self._records()
        before = build_development_ranking(records)
        fold = before["fold_assignment"][records[0]["source_sha256"]]
        records[0]["retained_placement_gold_labels"][0]["acceptability_features"]["values"][0]["value"] = 0.7
        records[0]["retained_placement_gold_labels"][0]["geometry_conformance"] = "safe"
        after = build_development_ranking(records)
        self.assertEqual(before["fold_models"][fold], after["fold_models"][fold])
        self.assertNotEqual(before["development_fit_model"], after["development_fit_model"])
        transform = _training_transform([self._example(1, 1.0, False), self._example(2, 3.0, True)])
        self.assertEqual(transform["centers"][:2], [2.0, 0.0])
        self.assertEqual(transform["scales"][:2], [1.0, 1.0])
        self.assertEqual(transform["observed_minimums"][:2], [1.0, None])
        self.assertEqual(transform["missing_seen"][:2], [False, True])

    def test_ridge_separates_candidates_without_probability_claim(self):
        train = [self._example(1, 0.0, False), self._example(2, 1.0, True)]
        model = _fit_model(train)
        scores = _scores(train, model)
        self.assertLess(scores[0], scores[1])
        self.assertGreater(_scores([self._example(3, 10.0, True)], model)[0], 1.0)
        artifact = build_development_ranking(self._records())
        self.assertEqual(artifact["source_grouped_oof"]["summary"]["ranked_geometry_conformance_counts"], {"safe": 10})
        self.assertFalse(artifact["admission_enabled"])
        self.assertIsNone(artifact["calibration_id"])

    def test_multiple_positive_unavailable_and_ties_preserve_semantics(self):
        records = self._records()
        for record in records:
            for candidate in record["retained_placement_gold_labels"]:
                candidate["geometry_conformance"] = "safe"
                candidate["acceptability_features"]["values"][0]["value"] = 0.5
        unknown = records[-1]["retained_placement_gold_labels"][1]
        unknown["generation_state"] = "unavailable"
        unknown["geometry_conformance"] = "not_available"
        unknown["acceptability_features"] = None
        unknown["output_footprints"] = []
        artifact = build_development_ranking(records)
        self.assertEqual(artifact["development_fit_model"]["training_candidate_count"], 19)
        self.assertEqual(artifact["source_grouped_oof"]["summary"]["at_least_one_safe_retained_task_count"], 10)
        for task in artifact["source_grouped_oof"]["tasks"]:
            self.assertEqual(task["ranked_placement_id"], "placement:primary")
        self.assertEqual(artifact["source_grouped_oof"]["tasks"][-1]["unavailable_placement_ids"], ["placement:runner"])
        validate_development_ranking(artifact, records)

    def test_metadata_is_not_a_feature(self):
        records = self._records()
        before = build_development_ranking(records)
        for record in records:
            record["sample_id"] += "-renamed"
            record["cohort_role"] = "challenge"
        after = build_development_ranking(records)
        self.assertEqual(before["fold_models"], after["fold_models"])
        self.assertEqual(before["development_fit_model"], after["development_fit_model"])

    def test_conditional_scores_stay_separate_from_canonical_selection(self):
        records = self._records()
        for record in records:
            for candidate in record["retained_placement_gold_labels"]:
                candidate["geometry_conformance"] = "unsafe"
            conditional = deepcopy(record["retained_placement_gold_labels"][1])
            conditional["role"] = "conditional"
            conditional["placement_id"] = "placement:conditional"
            conditional["acceptability_features"]["placement_id"] = "placement:conditional"
            conditional["acceptability_features"]["values"][0]["value"] = 1.0
            record["retained_placement_gold_labels"][1]["acceptability_features"]["values"][0]["value"] = 0.5
            conditional["geometry_conformance"] = "safe"
            record["retained_placement_gold_labels"].append(conditional)
        artifact = build_development_ranking(records)
        for task in artifact["source_grouped_oof"]["tasks"]:
            self.assertEqual(task["ranked_role"], "conditional")
            self.assertEqual(task["ranked_geometry_conformance"], "safe")
            self.assertEqual(task["canonical_ranked_role"], "runner")
            self.assertEqual(task["canonical_ranked_geometry_conformance"], "unsafe")
            self.assertFalse(task["canonical_at_least_one_safe_retained"])
        self.assertEqual(artifact["development_fit_model"]["training_candidate_count"], 30)
        self.assertFalse(artifact["admission_enabled"])
        validate_development_ranking(artifact, records)

    def test_conditional_scope_and_canonical_results_cannot_be_relabelled(self):
        records = self._records()
        baseline = build_development_ranking(records)
        altered = deepcopy(baseline)
        altered["conditional_role_scope"] = "automatic_output"
        with self.assertRaises(ValueError):
            validate_development_ranking(altered, records)
        altered = deepcopy(baseline)
        altered["source_grouped_oof"]["tasks"][0]["canonical_ranked_placement_id"] = "different"
        with self.assertRaises(ValueError):
            validate_development_ranking(altered, records)

    def test_native_endpoint_scores_are_development_only_and_keep_canonical_metrics(self):
        records = self._records()
        for record in records:
            for candidate in record["retained_placement_gold_labels"]:
                candidate["geometry_conformance"] = "unsafe"
            native = deepcopy(record["retained_placement_gold_labels"][1])
            native["role"] = "native_endpoint"
            native["placement_id"] = "placement:native"
            native["acceptability_features"]["placement_id"] = "placement:native"
            native["acceptability_features"]["values"][0]["value"] = 1.0
            native["geometry_conformance"] = "safe"
            record["retained_placement_gold_labels"][1]["acceptability_features"]["values"][0]["value"] = 0.5
            record["retained_placement_gold_labels"].append(native)
        artifact = build_development_ranking(records)
        self.assertEqual(artifact["ranking_schema"], RANKING_SCHEMA)
        self.assertEqual(RANKING_SCHEMA, "x5crop_development_placement_ranking_v4")
        self.assertEqual(
            artifact["independent_phase_role_scope"],
            INDEPENDENT_PHASE_ROLE_SCOPE,
        )
        self.assertFalse(artifact["admission_enabled"])
        for task in artifact["source_grouped_oof"]["tasks"]:
            self.assertEqual(task["ranked_role"], "native_endpoint")
            self.assertEqual(task["ranked_geometry_conformance"], "safe")
            self.assertEqual(task["canonical_ranked_role"], "runner")
            self.assertEqual(task["canonical_ranked_geometry_conformance"], "unsafe")
            self.assertFalse(task["canonical_at_least_one_safe_retained"])
        self.assertEqual(artifact["source_grouped_oof"]["summary"]["native_endpoint_ranked_task_ids"],
                         [record["sample_id"] for record in records])
        validate_development_ranking(artifact, records)
        for field, value in (
            ("independent_phase_role_scope", "automatic_output"),
            ("ranking_schema", "x5crop_development_placement_ranking_v2"),
            ("label_record_schema", "x5crop_development_gold_analysis_record_v23"),
            ("retained_placement_scope", "retained_canonical_pair_and_conditional_cross_proposal"),
        ):
            altered = deepcopy(artifact)
            altered[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_development_ranking(altered, records)

    def test_independent_phase_review_roles_rank_without_changing_canonical_metrics(self):
        for role in ("source_clipped_terminal", "intrinsic_refit"):
            with self.subTest(role=role):
                records = self._records()
                for record in records:
                    for candidate in record["retained_placement_gold_labels"]:
                        candidate["geometry_conformance"] = "unsafe"
                    record["retained_placement_gold_labels"][1][
                        "acceptability_features"
                    ]["values"][0]["value"] = 0.5
                    review = deepcopy(
                        record["retained_placement_gold_labels"][1]
                    )
                    review["role"] = role
                    review["placement_id"] = f"placement:{role}"
                    review["acceptability_features"]["placement_id"] = (
                        f"placement:{role}"
                    )
                    review["acceptability_features"]["values"][0]["value"] = 1.0
                    review["geometry_conformance"] = "safe"
                    record["retained_placement_gold_labels"].append(review)

                artifact = build_development_ranking(records)
                self.assertEqual(
                    artifact["independent_phase_role_scope"],
                    INDEPENDENT_PHASE_ROLE_SCOPE,
                )
                for task in artifact["source_grouped_oof"]["tasks"]:
                    self.assertEqual(task["ranked_role"], role)
                    self.assertEqual(task["ranked_geometry_conformance"], "safe")
                    self.assertEqual(task["canonical_ranked_role"], "runner")
                    self.assertEqual(
                        task["canonical_ranked_geometry_conformance"],
                        "unsafe",
                    )
                    self.assertFalse(task["canonical_at_least_one_safe_retained"])
                self.assertEqual(
                    artifact["source_grouped_oof"]["summary"][
                        f"{role}_ranked_task_ids"
                    ],
                    [record["sample_id"] for record in records],
                )
                validate_development_ranking(artifact, records)

    def test_unknown_review_role_and_legacy_scope_alias_are_rejected(self):
        records = self._records()
        invalid = deepcopy(records[0]["retained_placement_gold_labels"][0])
        invalid["role"] = "intrinsic_refit_typo"
        invalid["placement_id"] = "placement:invalid-review-role"
        invalid["acceptability_features"]["placement_id"] = invalid["placement_id"]
        records[0]["retained_placement_gold_labels"].append(invalid)
        with self.assertRaises(ValueError):
            build_development_ranking(records)

        records = self._records()
        artifact = build_development_ranking(records)
        legacy = deepcopy(artifact)
        del legacy["independent_phase_role_scope"]
        legacy["native_endpoint_role_scope"] = "development_label_and_score_only"
        with self.assertRaises(ValueError):
            validate_development_ranking(legacy, records)

    def test_validator_rejects_rehashed_wrong_fit_predictions_and_contract_tampering(self):
        records = self._records()
        baseline = build_development_ranking(records)
        mutations = (
            lambda item: item.update(admission_enabled=True),
            lambda item: item.update(calibration_id="pretend-calibrated"),
            lambda item: item.update(weighting="equal_candidate"),
            lambda item: item.update(validation_role="sealed"),
            lambda item: item.update(formal_ood_evaluated=True),
            lambda item: item["fold_assignment"].update({records[0]["source_sha256"]: 4}),
            lambda item: item["source_grouped_oof"]["summary"].update(task_count=99),
        )
        for mutate in mutations:
            altered = deepcopy(baseline)
            mutate(altered)
            with self.assertRaises(ValueError):
                validate_development_ranking(altered, records)
        altered = deepcopy(baseline)
        model = altered["fold_models"][0]
        model["coefficients"][0] += 0.1
        model["model_id"] = _model_id(model)
        with self.assertRaisesRegex(ValueError, "training objective"):
            validate_development_ranking(altered, records)
        with self.assertRaises(ValueError):
            build_development_ranking(records[:4])
        with self.assertRaises(ValueError):
            build_development_ranking([*records, records[0]])


if __name__ == "__main__":
    unittest.main()
