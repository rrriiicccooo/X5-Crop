from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import unittest

from tools.tests.template_runtime_test_support import (
    prepared_template_lane as _prepared,
    runtime_measurement_set as _measurement_set,
)
from x5crop.detection.gate_checks import GateGap, TypedAssessment, failure_fact
from x5crop.detection.photo_geometry.model import (
    AuthoritySide,
    BoundaryRole,
)
from x5crop.detection.photo_geometry.output_model import (
    BoundaryProtectionFact,
    FootprintSaturationFact,
    JointPlacementEnvelope,
    OutputBoundaryUse,
    OutputFootprint,
)
from x5crop.detection.photo_geometry.template_model import (
    PhaseLatticeAuthority,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_runtime_model import (
    PhotoGeometryDetectionResult,
    PreparedTemplateLane,
    TemplateLaneReconstruction,
    TemplateMeasurementWorkReceipt,
    TemplatePlacementCompetition,
    TemplatePlacementWorkReceipt,
    TemplateSourceSelection,
)
from x5crop.domain import Box, EvidenceState
def _unresolved_result() -> PhotoGeometryDetectionResult:
    prepared = _prepared()
    competition = TemplatePlacementCompetition(
        placements=(),
        selected_placement_id=None,
        runner_up_placement_id=None,
        state=EvidenceState.UNAVAILABLE,
        failure=failure_fact(GateGap.PHASE_ANCHOR_UNAVAILABLE),
    )
    reconstruction = TemplateLaneReconstruction(
        lane_id="lane:0",
        prepared=prepared,
        placement_competition=competition,
        selected_placement=None,
        output_footprints=(),
        direct_use_budget_assessments=(),
        holder_fill_assessment=None,
        content_veto_facts=(),
        work=TemplatePlacementWorkReceipt(0, 0, 0, 0),
    )
    selection = TemplateSourceSelection(
        lane_ids=("lane:0",),
        selected_placement_ids=(None,),
        shared_scan_geometry=None,
        state=EvidenceState.UNAVAILABLE,
        failure=failure_fact(GateGap.PLACEMENT_UNRESOLVED),
        runner_up_placement_ids=(None,),
    )
    return PhotoGeometryDetectionResult(
        resolved_output_slots=None,
        lane_reconstructions=(reconstruction,),
        source_placement_selection=selection,
        output_slot_identities=(),
        assessment_facts={
            "selected_placement": TypedAssessment(
                EvidenceState.UNAVAILABLE, GateGap.PLACEMENT_UNRESOLVED
            )
        },
    )


class TemplateRuntimeModelContractTest(unittest.TestCase):
    def test_prepared_lane_is_fitted_and_mapping_is_frozen(self) -> None:
        prepared = _prepared()
        self.assertEqual(prepared.phase_competition.template, prepared.template_spec)
        with self.assertRaises(TypeError):
            prepared.transition_by_id["new"] = object()  # type: ignore[index]
        with self.assertRaises(ValueError):
            PreparedTemplateLane(
                **{
                    **prepared.__dict__,
                    "template_spec": TemplateSpec(
                        template_id="other",
                        frame_width_px=100.0,
                        pitch_px=120.0,
                        frame_height_px=240.0,
                        count=1,
                        phase_lattice_authority=PhaseLatticeAuthority(
                            period_px=120.0,
                            cycle_origin_px=0.0,
                            minimum_slot_offset=-1,
                            maximum_slot_offset=20,
                        ),
                        nominal_gap_px=20.0,
                    ),
                }
            )

    def test_measurement_queries_are_lane_local(self) -> None:
        prepared = _prepared()
        measurement = _measurement_set("lane:0", registration_index=2)
        measurements = (*prepared.measurement_sets, measurement)
        valid = replace(
            prepared,
            measurement_sets=measurements,
            measurement_work=TemplateMeasurementWorkReceipt(
                3,
                3,
                3,
                8,
                tuple(item.coverage for item in measurements),
            ),
        )
        self.assertEqual(valid.measurement_sets[-1].query.lane_id, "lane:0")
        foreign = _measurement_set("lane:foreign", registration_index=2)
        with self.assertRaises(ValueError):
            replace(
                prepared,
                measurement_sets=(*prepared.measurement_sets, foreign),
                measurement_work=TemplateMeasurementWorkReceipt(
                    3,
                    3,
                    3,
                    8,
                    tuple(
                        item.coverage
                        for item in (*prepared.measurement_sets, foreign)
                    ),
                ),
            )

    def test_unsupported_result_exposes_no_selected_outputs(self) -> None:
        result = _unresolved_result()
        self.assertEqual(result.output_footprints, ())
        self.assertEqual(result.direct_use_budget_assessments, ())
        with self.assertRaises(TypeError):
            result.assessment_facts["new"] = object()  # type: ignore[index]

    def test_output_footprints_are_selected_only(self) -> None:
        prepared = _prepared()
        competition = TemplatePlacementCompetition(
            placements=(),
            selected_placement_id=None,
            runner_up_placement_id=None,
            state=EvidenceState.UNAVAILABLE,
            failure=failure_fact(GateGap.PLACEMENT_UNRESOLVED),
        )
        output = _output_footprint()
        with self.assertRaises(ValueError):
            TemplateLaneReconstruction(
                lane_id="lane:0",
                prepared=prepared,
                placement_competition=competition,
                selected_placement=None,
                output_footprints=(output,),
                direct_use_budget_assessments=(),
                holder_fill_assessment=None,
                content_veto_facts=(),
                work=TemplatePlacementWorkReceipt(0, 0, 0, 0),
            )

    def test_source_selection_rejects_partial_authority(self) -> None:
        with self.assertRaises(ValueError):
            TemplateSourceSelection(
                lane_ids=("lane:0",),
                selected_placement_ids=("placement:0",),
                shared_scan_geometry=None,
                state=EvidenceState.SUPPORTED,
                failure=None,
            )

    def test_empty_source_selection_is_a_valid_unresolved_result(self) -> None:
        selection = TemplateSourceSelection(
            lane_ids=(),
            selected_placement_ids=(),
            shared_scan_geometry=None,
            state=EvidenceState.UNAVAILABLE,
            failure=failure_fact(GateGap.OUTPUT_SLOT_COUNT_UNAVAILABLE),
        )
        self.assertEqual(selection.lane_ids, ())

    def test_source_has_no_legacy_imports(self) -> None:
        path = Path(__file__).parents[2] / "x5crop/detection/photo_geometry/template_runtime_model.py"
        tree = ast.parse(path.read_text())
        imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        names = [
            alias.name
            for node in imports
            for alias in getattr(node, "names", ())
        ]
        forbidden = (
            "CompleteFormatChain",
            "chain_proposals",
            "materialization",
            "source_selection_model",
            "dominance",
            "cache",
        )
        self.assertFalse(any(any(token in name for token in forbidden) for name in names))


def _output_footprint():
    polygon = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))
    saturation = FootprintSaturationFact(
        authority_side=AuthoritySide.LEFT,
    )
    envelope = JointPlacementEnvelope(
        placement_id="placement:0",
        projection_id="projection:0",
        lane_id="lane:0",
        lane_ordinal=1,
        boundary_use=OutputBoundaryUse.APERTURE_PAIR,
        canonical_source_footprint=polygon,
        feasible_source_footprint=polygon,
        extreme_evaluation_count=8,
    )
    return OutputFootprint(
        geometry_id="geometry:0",
        envelope=envelope,
        required_source_footprint=polygon,
        boundary_protections=tuple(
            BoundaryProtectionFact(role, 0.0, 0.0, 0.0, 0.0)
            for role in (
                BoundaryRole.START,
                BoundaryRole.END,
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
            )
        ),
        saturation_facts=(saturation,),
        sampling_authority_box=Box(0, 0, 10, 10),
        authority_profile_id="135_standard",
    )


if __name__ == "__main__":
    unittest.main()
