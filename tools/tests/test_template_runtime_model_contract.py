from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.tests.template_runtime_test_support import (
    prepared_template_lane as _prepared,
    runtime_measurement_set as _measurement_set,
)
from tools.tests.template_test_support import (
    placement_compose,
    placement_cross,
    placement_direction,
    placement_sequence,
    placement_template,
)
from x5crop.detection.gate_checks import GateGap, TypedAssessment, failure_fact
from x5crop.detection.photo_geometry.detector import _materialize_placement_proposal
from x5crop.detection.photo_geometry.template_acceptability_features import (
    PLACEMENT_FEATURE_DEFINITIONS,
    build_placement_acceptability_features,
)
from x5crop.detection.photo_geometry.template_output import (
    output_footprint_from_template_placement,
    template_direct_use_budget_assessment,
)
from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
from x5crop.detection.photo_geometry.model import (
    BoundaryRole,
)
from x5crop.detection.photo_geometry.output_model import (
    BoundaryProtectionFact,
    JointPlacementEnvelope,
    OutputBoundaryUse,
    OutputFootprint,
    SequenceProjectionConstraintBasis,
)
from x5crop.detection.photo_geometry.template_model import (
    PhaseLatticeAuthority,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_enclosing_support_aperture import (
    not_applicable_enclosing_support_aperture_authority,
)
from x5crop.detection.photo_geometry.template_nominal_grid_authority import (
    assess_calibrated_nominal_grid_authority,
)
from x5crop.detection.photo_geometry.template_nominal_grid_model import (
    CalibratedNominalGridAuthority,
    NominalGridFailureKind,
)
from x5crop.detection.photo_geometry.template_runtime_model import (
    PhotoGeometryDetectionResult,
    PreparedTemplateLane,
    TemplateLaneReconstruction,
    TemplateMeasurementWorkReceipt,
    TemplatePlacementCompetition,
    TemplatePlacementProposal,
    TemplatePlacementWorkReceipt,
    TemplateProposalState,
    TemplateSourceProposal,
    TemplateSourceSelection,
)
from x5crop.domain import Box, EvidenceState, WorkspaceExtent
def _unresolved_result() -> PhotoGeometryDetectionResult:
    prepared = _prepared()
    competition = TemplatePlacementCompetition(
        placements=(),
        selected_placement_id=None,
        runner_up_placement_id=None,
        state=EvidenceState.UNAVAILABLE,
        failure=failure_fact(GateGap.PHASE_ANCHOR_UNAVAILABLE),
    )
    proposal = TemplatePlacementProposal(
        lane_id="lane:0",
        state=TemplateProposalState.UNAVAILABLE,
        placement_id=None,
        output_footprints=(),
        direct_use_budget_assessments=(),
        acceptability_features=None,
        failure=failure_fact(GateGap.PHASE_ANCHOR_UNAVAILABLE),
    )
    reconstruction = TemplateLaneReconstruction(
        lane_id="lane:0",
        prepared=prepared,
        placement_competition=competition,
        placement_proposal=proposal,
        alternative_placement_proposals=(),
        selected_placement=None,
        output_footprints=(),
        calibrated_nominal_grid_authority=(
            assess_calibrated_nominal_grid_authority(
                None,
                placement_id=None,
                output_geometry_ids=(),
            )
        ),
        enclosing_support_aperture_authority=(
            not_applicable_enclosing_support_aperture_authority()
        ),
        direct_use_budget_assessments=(),
        holder_fill_assessment=None,
        content_veto_facts=(),
        work=TemplatePlacementWorkReceipt(0, 0, 0, 0, 0, 0, 0, 0),
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
        source_placement_proposal=TemplateSourceProposal(
            lane_ids=("lane:0",),
            placement_ids=(None,),
            state=TemplateProposalState.UNAVAILABLE,
            failure=failure_fact(GateGap.PHASE_ANCHOR_UNAVAILABLE),
        ),
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

    def test_each_retained_proposal_projects_once_and_counts_partial_failure(self) -> None:
        prepared = _prepared()
        template = placement_template(2)
        placement = placement_compose(
            template, placement_sequence(template),
            placement_cross(template, direction=placement_direction()), lane_id="lane:0",
        )
        projection = project_format_placement(placement)
        outputs = tuple(
            output_footprint_from_template_placement(
                placement, projection, lane=prepared.lane, lane_ordinal=ordinal, layout="horizontal",
            ) for ordinal in (1, 2)
        )
        for failure_at in (None, 0, 2):
            with self.subTest(failure_at=failure_at), patch(
                "x5crop.detection.photo_geometry.detector.project_format_placement",
                side_effect=ValueError("projection unavailable") if failure_at == 0 else None,
            ) as project, patch(
                "x5crop.detection.photo_geometry.detector.output_footprint_from_template_placement",
                side_effect=(outputs[0], ValueError("slot unavailable")) if failure_at == 2 else outputs,
            ) as footprint, patch(
                "x5crop.detection.photo_geometry.detector.template_direct_use_budget_assessment",
                wraps=template_direct_use_budget_assessment,
            ) as budget:
                proposal, evaluations = _materialize_placement_proposal(prepared, placement, layout="horizontal")
                project.assert_called_once_with(placement)
                self.assertEqual(evaluations, 0 if failure_at == 0 else 2)
                self.assertEqual(footprint.call_count, evaluations)
                self.assertEqual(proposal.placement_id, placement.placement_id)
                self.assertEqual(proposal.output_footprints, outputs if failure_at is None else ())
                self.assertEqual(proposal.state, TemplateProposalState.GENERATED if failure_at is None else TemplateProposalState.UNAVAILABLE)
                self.assertEqual(budget.call_count, len(proposal.output_footprints))
                self.assertEqual(len(proposal.acceptability_features.values), len(PLACEMENT_FEATURE_DEFINITIONS))

    def test_generated_proposal_survives_withheld_eligibility(self) -> None:
        prepared = _prepared()
        template = placement_template(1)
        placement = placement_compose(
            template,
            placement_sequence(template),
            placement_cross(template, direction=placement_direction()),
            lane_id="lane:0",
        )
        output = output_footprint_from_template_placement(
            placement, project_format_placement(placement),
            lane=prepared.lane, lane_ordinal=1, layout="horizontal",
        )
        failure = failure_fact(GateGap.PLACEMENT_UNRESOLVED)
        budgets = (template_direct_use_budget_assessment(placement, output),)
        proposal = TemplatePlacementProposal(
            lane_id="lane:0",
            state=TemplateProposalState.GENERATED,
            placement_id=placement.placement_id,
            output_footprints=(output,),
            direct_use_budget_assessments=budgets,
            acceptability_features=build_placement_acceptability_features(placement, (output,), budgets),
            failure=None,
        )
        reconstruction = TemplateLaneReconstruction(
            lane_id="lane:0",
            prepared=prepared,
            placement_competition=TemplatePlacementCompetition(
                placements=(placement,),
                selected_placement_id=None,
                runner_up_placement_id=None,
                state=EvidenceState.UNAVAILABLE,
                failure=failure,
            ),
            placement_proposal=proposal,
            alternative_placement_proposals=(),
            selected_placement=None,
            output_footprints=(),
            calibrated_nominal_grid_authority=(
                assess_calibrated_nominal_grid_authority(
                    None,
                    placement_id=None,
                    output_geometry_ids=(),
                )
            ),
            enclosing_support_aperture_authority=(
                not_applicable_enclosing_support_aperture_authority()
            ),
            direct_use_budget_assessments=(),
            holder_fill_assessment=None,
            content_veto_facts=(),
            work=TemplatePlacementWorkReceipt(1, 4, 0, 0, 1, 1, 1, len(PLACEMENT_FEATURE_DEFINITIONS)),
        )
        result = PhotoGeometryDetectionResult(
            resolved_output_slots=None,
            lane_reconstructions=(reconstruction,),
            source_placement_proposal=TemplateSourceProposal(
                lane_ids=("lane:0",),
                placement_ids=(placement.placement_id,),
                state=TemplateProposalState.GENERATED,
                failure=None,
            ),
            source_placement_selection=TemplateSourceSelection(
                lane_ids=("lane:0",),
                selected_placement_ids=(None,),
                shared_scan_geometry=None,
                state=EvidenceState.UNAVAILABLE,
                failure=failure,
                runner_up_placement_ids=(None,),
            ),
            output_slot_identities=(),
            assessment_facts={
                "selected_placement": TypedAssessment(
                    EvidenceState.UNAVAILABLE,
                    GateGap.PLACEMENT_UNRESOLVED,
                )
            },
        )

        self.assertEqual(
            result.source_placement_proposal.state,
            TemplateProposalState.GENERATED,
        )
        self.assertEqual(result.output_footprints, ())

        runner = replace(placement, placement_id="placement:runner")
        runner_output = replace(output, envelope=replace(output.envelope, placement_id=runner.placement_id))
        runner_budgets = (template_direct_use_budget_assessment(runner, runner_output),)
        runner_proposal = replace(
            proposal, placement_id=runner.placement_id, output_footprints=(runner_output,),
            direct_use_budget_assessments=runner_budgets,
            acceptability_features=build_placement_acceptability_features(runner, (runner_output,), runner_budgets),
        )
        retained = replace(
            reconstruction,
            placement_competition=replace(
                reconstruction.placement_competition,
                placements=(placement, runner), runner_up_placement_id=runner.placement_id,
            ),
            alternative_placement_proposals=(runner_proposal,),
            work=replace(
                reconstruction.work, proposal_projection_count=2, proposal_output_evaluation_count=2,
                proposal_budget_evaluation_count=2, placement_feature_evaluation_count=2 * len(PLACEMENT_FEATURE_DEFINITIONS),
            ),
        )
        self.assertEqual(retained.output_footprints, ())
        self.assertIs(retained.placement_proposal, proposal)
        with self.assertRaisesRegex(ValueError, "exactly one proposal"):
            replace(retained, alternative_placement_proposals=())
        with self.assertRaisesRegex(ValueError, "retain the lane runner"):
            replace(retained, alternative_placement_proposals=(proposal,))
        with self.assertRaisesRegex(ValueError, "work exceeds"):
            replace(retained, work=replace(retained.work, proposal_projection_count=1))
        with self.assertRaisesRegex(ValueError, "work exceeds"):
            replace(retained, work=replace(retained.work, proposal_output_evaluation_count=3))
        for field in ("proposal_budget_evaluation_count", "placement_feature_evaluation_count"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "work exceeds"):
                replace(retained, work=replace(retained.work, **{field: getattr(retained.work, field) + 1}))
        unavailable_runner = replace(
            runner_proposal, state=TemplateProposalState.UNAVAILABLE,
            output_footprints=(), failure=failure_fact(GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE),
            direct_use_budget_assessments=(),
            acceptability_features=build_placement_acceptability_features(runner, (), ()),
        )
        replace(
            retained, alternative_placement_proposals=(unavailable_runner,),
            work=replace(retained.work, proposal_budget_evaluation_count=1),
        )

    def test_unresolved_lane_retains_nominal_grid_counterevidence(self) -> None:
        prepared = _prepared()
        competition = TemplatePlacementCompetition(
            placements=(),
            selected_placement_id=None,
            runner_up_placement_id=None,
            state=EvidenceState.UNAVAILABLE,
            failure=failure_fact(GateGap.PLACEMENT_UNRESOLVED),
        )

        reconstruction = TemplateLaneReconstruction(
            lane_id="lane:0",
            prepared=prepared,
            placement_competition=competition,
            placement_proposal=TemplatePlacementProposal(
                lane_id="lane:0",
                state=TemplateProposalState.UNAVAILABLE,
                placement_id=None,
                output_footprints=(),
                direct_use_budget_assessments=(),
                acceptability_features=None,
                failure=failure_fact(GateGap.PLACEMENT_UNRESOLVED),
            ),
            alternative_placement_proposals=(),
            selected_placement=None,
            output_footprints=(),
            calibrated_nominal_grid_authority=(
                CalibratedNominalGridAuthority(
                    authority_id="nominal-grid-authority:contradicted",
                    state=EvidenceState.CONTRADICTED,
                    evidence_id="nominal-grid-evidence:contradicted",
                    placement_id=None,
                    output_geometry_ids=(),
                    failure_kind=NominalGridFailureKind.COUNTEREVIDENCE,
                    reason="direct counterevidence rejects the nominal Grid",
                )
            ),
            enclosing_support_aperture_authority=(
                not_applicable_enclosing_support_aperture_authority()
            ),
            direct_use_budget_assessments=(),
            holder_fill_assessment=None,
            content_veto_facts=(),
            work=TemplatePlacementWorkReceipt(0, 0, 0, 0, 0, 0, 0, 0),
        )

        self.assertEqual(
            reconstruction.calibrated_nominal_grid_authority.state,
            EvidenceState.CONTRADICTED,
        )

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
                placement_proposal=TemplatePlacementProposal(
                    lane_id="lane:0",
                    state=TemplateProposalState.UNAVAILABLE,
                    placement_id=None,
                    output_footprints=(),
                    direct_use_budget_assessments=(),
                    acceptability_features=None,
                    failure=failure_fact(GateGap.PLACEMENT_UNRESOLVED),
                ),
                alternative_placement_proposals=(),
                selected_placement=None,
                output_footprints=(output,),
                calibrated_nominal_grid_authority=(
                    assess_calibrated_nominal_grid_authority(
                        None,
                        placement_id=None,
                        output_geometry_ids=(),
                    )
                ),
                enclosing_support_aperture_authority=(
                    not_applicable_enclosing_support_aperture_authority()
                ),
                direct_use_budget_assessments=(),
                holder_fill_assessment=None,
                content_veto_facts=(),
                work=TemplatePlacementWorkReceipt(0, 0, 0, 0, 0, 0, 0, 0),
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

def _output_footprint():
    polygon = ((0.0, 0.0), (9.0, 0.0), (9.0, 9.0), (0.0, 9.0))
    envelope = JointPlacementEnvelope(
        placement_id="placement:0",
        projection_id="projection:0",
        lane_id="lane:0",
        lane_ordinal=1,
        boundary_use=OutputBoundaryUse.APERTURE_PAIR,
        canonical_source_footprint=polygon,
        feasible_source_footprint=polygon,
        extreme_evaluation_count=8,
        sequence_constraint_basis=(
            SequenceProjectionConstraintBasis.MODEL_INTERVALS
        ),
        global_lattice_constraint_ids=(),
    )
    return OutputFootprint(
        geometry_id="geometry:0",
        envelope=envelope,
        mandatory_source_footprint=polygon,
        requested_source_footprint=polygon,
        required_source_footprint=polygon,
        boundary_protections=tuple(
            BoundaryProtectionFact(role, 0.0, 0.0, 0.0, None, 0.0, 0.0)
            for role in (
                BoundaryRole.START,
                BoundaryRole.END,
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
            )
        ),
        maximum_same_state_cross_alignment_padding_px=None,
        enclosing_support_aperture_risk=None,
        saturation_facts=(),
        sampling_authority_box=Box(0, 0, 10, 10),
        source_extent=WorkspaceExtent(10, 10),
        authority_profile_id="135_standard",
    )


if __name__ == "__main__":
    unittest.main()
