from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.regression.report_validation import validate_placement_feature_record
from tools.tests.affine_tiff_support import sampling_footprint
from tools.tests.template_runtime_test_support import prepared_template_lane
from tools.tests.template_test_support import (
    placement_compose, placement_cross, placement_direction,
    placement_sequence, placement_template,
)
from x5crop.detection.photo_geometry.template_acceptability_features import (
    PLACEMENT_FEATURE_DEFINITIONS, PlacementFeatureMissingReason,
    _source_clipped_length_fractions, build_placement_acceptability_features,
)
from x5crop.detection.photo_geometry.model import BoundaryAxis
from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
from x5crop.detection.photo_geometry.template_output import (
    output_footprint_from_template_placement, template_direct_use_budget_assessment,
)
from x5crop.report.read_models import typed_read_model
from x5crop.domain import Box, WorkspaceExtent
from x5crop.geometry.convex import convex_hull


class PlacementAcceptabilityFeaturesContractTest(unittest.TestCase):
    def _placement(self, count=2, missing=()):
        template = placement_template(count)
        return placement_compose(
            template, placement_sequence(template, missing=missing),
            placement_cross(template, direction=placement_direction()), lane_id="lane:0",
        )

    def _outputs(self, placement):
        lane = prepared_template_lane().lane
        projection = project_format_placement(placement)
        outputs = tuple(
            output_footprint_from_template_placement(
                placement, projection, lane=lane, lane_ordinal=ordinal, layout="horizontal",
            )
            for ordinal in range(1, placement.output_slot_count + 1)
        )
        return outputs, tuple(template_direct_use_budget_assessment(placement, item) for item in outputs)

    def test_features_read_existing_physics_and_budget_without_reprojection(self):
        placement = self._placement()
        outputs, budgets = self._outputs(placement)
        with patch(
            "x5crop.detection.photo_geometry.template_feasible_geometry.project_format_placement",
            side_effect=AssertionError("features must not project"),
        ), patch(
            "x5crop.detection.photo_geometry.template_output.template_direct_use_budget_assessment",
            side_effect=AssertionError("features must reuse budgets"),
        ):
            features = build_placement_acceptability_features(placement, outputs, budgets)
        values = {item.name: item for item in features.values}
        self.assertEqual(len(features.values), len(PLACEMENT_FEATURE_DEFINITIONS))
        self.assertEqual(values["phase_anchor_group_fraction"].value, 1.0)
        self.assertEqual(values["cross_direct_role_fraction"].value, 1.0)
        self.assertEqual(values["unobserved_frame_fraction"].value, 0.0)
        self.assertEqual(values["output_maximum_budget_ratio"].value, max(
            edge.required_extent_px / edge.available_extent_px for item in budgets for edge in item.edge_assessments
        ))
        self.assertTrue(set(placement.sequence_fit.bound_observation_ids) <= set(features.observation_ids))
        self.assertTrue(all(item.observation_id in features.observation_ids for item in placement.cross_fit.direct_bindings))
        self.assertEqual(features.evidence_group_ids, placement.sequence_fit.evidence_group_ids)
        self.assertEqual(features.output_geometry_ids, tuple(item.geometry_id for item in outputs))
        clipped = _source_clipped_length_fractions(outputs)
        self.assertEqual(values["source_minimum_clipped_length_fraction"].value, clipped[0])
        self.assertEqual(values["source_maximum_clipped_length_fraction"].value, clipped[1])

    def test_source_clipping_uses_pixel_cells_and_length_weighting_without_direction_bias(self):
        def output(low, high):
            return sampling_footprint(
                Box(0, 0, 100, 80), WorkspaceExtent(100, 80),
                mandatory=((low, 10.0), (high, 10.0), (high, 60.0), (low, 60.0)),
            )

        full = output(-0.5, 99.5)
        clipped = output(-25.5, 149.5)
        self.assertEqual(_source_clipped_length_fractions((full,)), (0.0, 0.0))
        self.assertEqual(_source_clipped_length_fractions((clipped, full)), (25 / 275, 50 / 275))
        reflected = output(99 - 149.5, 99 + 25.5)
        self.assertEqual(_source_clipped_length_fractions((clipped,)),
                         _source_clipped_length_fractions((replace(reflected, sequence_direction=-1),)))
        transpose = lambda polygon: convex_hull(tuple((y, x) for x, y in polygon))
        transposed = replace(
            clipped, width_axis=BoundaryAxis.Y, source_extent=WorkspaceExtent(80, 100),
            sampling_authority_box=Box(0, 0, 80, 100),
            envelope=replace(clipped.envelope,
                canonical_source_footprint=transpose(clipped.envelope.canonical_source_footprint),
                feasible_source_footprint=transpose(clipped.envelope.feasible_source_footprint)),
            mandatory_source_footprint=transpose(clipped.mandatory_source_footprint),
            requested_source_footprint=transpose(clipped.requested_source_footprint),
            required_source_footprint=transpose(clipped.required_source_footprint),
        )
        self.assertEqual(_source_clipped_length_fractions((clipped,)),
                         _source_clipped_length_fractions((transposed,)))

    def test_missing_frames_and_unavailable_proposal_are_not_zero_evidence(self):
        placement = self._placement(count=3, missing=(2, 3, 5))
        features = build_placement_acceptability_features(placement, (), ())
        values = {item.name: item for item in features.values}
        self.assertEqual(values["unobserved_frame_fraction"].value, 1 / 3)
        self.assertEqual(values["one_sided_frame_fraction"].value, 1 / 3)
        for name in ("output_maximum_budget_ratio", "output_supported_budget_fraction", "output_saturation_count",
                     "source_minimum_clipped_length_fraction", "source_maximum_clipped_length_fraction"):
            self.assertIsNone(values[name].value)
            self.assertEqual(values[name].missing_reason, PlacementFeatureMissingReason.PROPOSAL_UNAVAILABLE)
        single = build_placement_acceptability_features(self._placement(count=1), (), ())
        self.assertEqual(next(item for item in single.values if item.name == "contact_relation_fraction").missing_reason,
                         PlacementFeatureMissingReason.NOT_APPLICABLE)

    def test_anchor_rank_feature_deduplicates_physical_groups(self):
        placement = self._placement()
        sequence = placement.sequence_fit
        bindings = tuple(replace(item, evidence_group_id=sequence.role_bindings[0].evidence_group_id) for item in sequence.role_bindings)
        grouped = replace(placement, sequence_fit=replace(sequence, role_bindings=bindings))
        values = {item.name: item.value for item in build_placement_acceptability_features(grouped, (), ()).values}
        self.assertEqual(values["phase_anchor_group_fraction"], 0.25)

    def test_serialized_feature_contract_rejects_leaks_missingness_and_unit_drift(self):
        placement = self._placement()
        outputs, budgets = self._outputs(placement)
        record = typed_read_model(build_placement_acceptability_features(placement, outputs, budgets))
        arguments = {"placement_id": placement.placement_id, "lane_id": placement.lane_id,
                     "output_geometry_ids": [item.geometry_id for item in outputs]}
        self.assertEqual(typed_read_model(validate_placement_feature_record(record, **arguments)), record)
        mutations = (
            lambda value: value.update(sample_id="S001"),
            lambda value: value["values"][0].update(name="cohort_role"),
            lambda value: value["values"][0].update(unit="count"),
            lambda value: value["values"][0].update(value=None),
            lambda value: value["values"][0].update(value=True),
            lambda value: value["values"][0].update(source_fields=["confirmed_geometry"]),
            lambda value: value["values"].pop(),
            lambda value: value.update(output_geometry_ids=["foreign"]),
        )
        for mutate in mutations:
            invalid = deepcopy(record)
            mutate(invalid)
            with self.assertRaisesRegex(ValueError, "feature record"):
                validate_placement_feature_record(invalid, **arguments)


if __name__ == "__main__":
    unittest.main()
