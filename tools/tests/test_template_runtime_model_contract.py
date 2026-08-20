from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import unittest

from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.evidence.scan_canvas import observe_scan_canvas
from x5crop.detection.gate_checks import GateGap, TypedAssessment, failure_fact
from x5crop.detection.output_geometry import (
    SharedStripDirectionResolution,
    output_transform_assessment,
)
from x5crop.detection.photo_geometry.model import (
    AuthoritySide,
    BoundaryAxis,
    BoundaryRole,
)
from x5crop.detection.photo_geometry.model import QueryPurpose
from x5crop.detection.photo_geometry.coarse_strip_support import (
    CoarseAxisSupport,
    CoarseStripSupport,
    CoarseStripSupportReceipt,
    CoarseSupportAuthority,
)
from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
)
from x5crop.detection.photo_geometry.output_model import (
    BoundaryProtectionFact,
    FootprintSaturationFact,
    JointPlacementEnvelope,
    OutputBoundaryUse,
    OutputFootprint,
)
from x5crop.detection.photo_geometry.search_model import (
    SequenceAnchorDiscoveryDomain,
    SequenceAnchorWindow,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import (
    TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_model import (
    PhaseLatticeAuthority,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_measurement_plan import (
    compile_template_measurement_plan,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_model import TemplatePhaseInput
from x5crop.detection.photo_geometry.template_runtime_model import (
    PhotoGeometryDetectionResult,
    PreparedTemplateLane,
    RegisteredTemplateLane,
    TemplateLaneReconstruction,
    TemplateMeasurementWorkReceipt,
    TemplatePlacementCompetition,
    TemplatePlacementWorkReceipt,
    TemplateSourceSelection,
)
from x5crop.detection.source_core import SourceLaneEvidence, SourceStripValidationDomain
from x5crop.domain import Box, EvidenceState, FiniteInterval, PositiveInterval
from x5crop.detection.photo_geometry.model import ClippedRequirement
from x5crop.formats import FramePhysicalSpec


def _lane() -> SourceLaneEvidence:
    configuration = get_detection_configuration("135")
    canvas = observe_scan_canvas(2320, 322, "horizontal", configuration.scan_canvas)
    return SourceLaneEvidence(
        SourceStripValidationDomain(
            lane_id="lane:0",
            work_box=Box(0, 0, 2320, 322),
            source_axis_long="x",
            authority_profile_id="135_standard",
        ),
        canvas,
    )


def _prepared() -> PreparedTemplateLane:
    lane = _lane()
    configuration = get_detection_configuration("135")
    scales = lane.scan_canvas.axis_scales
    assert scales is not None
    plan = compile_template_measurement_plan(
        format_spec=configuration.physical_spec,
        frame_spec=configuration.physical_spec.frame,
        count=1,
        full_count=6,
        holder_full_count=6,
        lane_authority=lane.domain,
        layout="horizontal",
        scale_authority=scales,
    )
    template = plan.template_spec
    coarse_long = _measurement_set(
        "lane:0",
        registration_index=0,
        purpose=QueryPurpose.COARSE_STRIP_LONG,
    )
    coarse_short = _measurement_set(
        "lane:0",
        registration_index=1,
        purpose=QueryPurpose.COARSE_STRIP_SHORT,
    )
    registered = RegisteredTemplateLane(
        lane=lane,
        layout="horizontal",
        output_slot_count=1,
        measurement_slot_count=6,
        width_axis=BoundaryAxis.X,
        height_axis=BoundaryAxis.Y,
        width_authority_px=FiniteInterval(0.0, 2320.0),
        height_authority_px=FiniteInterval(0.0, 322.0),
        coarse_support=CoarseStripSupport(
            "lane:0",
            CoarseAxisSupport(
                FiniteInterval(0.0, 2319.0),
                None,
                CoarseSupportAuthority.HOLDER_CONSERVATIVE,
                (),
            ),
            CoarseAxisSupport(
                FiniteInterval(0.0, 321.0),
                None,
                CoarseSupportAuthority.HOLDER_CONSERVATIVE,
                (),
            ),
            None,
            None,
            CoarseStripSupportReceipt(2, 2, 2, 2, 8, 2, 2),
        ),
        anchor_domain=SequenceAnchorDiscoveryDomain(
            domain_id="domain:runtime",
            lane_id="lane:0",
            long_axis_extent_px=2320,
            support_interval_px=FiniteInterval(0.0, 2319.0),
            authoritative_sequence_length=6,
            windows=(
                SequenceAnchorWindow(
                    window_id="anchor-window:lane:0:conservative",
                    core_px=FiniteInterval(0.0, 2320.0),
                    measurement_px=FiniteInterval(0.0, 2319.0),
                ),
            ),
            query_execution_order=("anchor-window:lane:0:conservative",),
        ),
        measurement_sets=(coarse_long, coarse_short),
        side_regions=(),
        top_regions=(),
        bottom_regions=(),
        transition_by_id={},
        sequence_profile=_profile("sequence"),
        cross_profile=_profile("cross"),
        sequence_edges=(),
        separator_bands=(),
        top_cross_bindings=(),
        bottom_cross_bindings=(),
        raw_cross_observations=(),
        measurement_work=TemplateMeasurementWorkReceipt(
            2,
            2,
            2,
            8,
            (coarse_long.coverage, coarse_short.coverage),
        ),
        measurement_plan=plan,
    )
    source = SourceScanGeometry.create(
        FramePhysicalSpec(36.0, 24.0, 2.0),
        width_scale_px_per_mm=PositiveInterval.exact(10.0),
        height_scale_px_per_mm=PositiveInterval.exact(10.0),
    )
    phase_input = TemplatePhaseInput(
        observations=(),
        separator_bands=(),
        template=template,
        scale_px_per_mm=None,
        holder_span_px=None,
        phase_authority_px=None,
    )
    cross_input = TemplateCrossInput(template=template, fixed_height_px=240.0)
    return PreparedTemplateLane(
        **registered.__dict__,
        template_spec=template,
        source_scan_geometry=source,
        phase_input=phase_input,
        cross_input=cross_input,
        phase_competition=fit_template_phase((), template),
        cross_competition=fit_template_cross(cross_input),
    )


def _profile(axis_name: str):
    from x5crop.detection.photo_geometry.observation_types import BasicAxisProfile

    return BasicAxisProfile(
        axis_name=axis_name,
        coordinate_count=1,
        trace_coordinates_px=(0,),
        runs=(),
    )


def _unavailable_transform():
    return output_transform_assessment(
        SharedStripDirectionResolution(
            direction=None,
            state=EvidenceState.UNAVAILABLE,
            named_gap="placement_unresolved",
        ),
        layout="horizontal",
        source_width=2320,
        source_height=322,
    )


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
        shared_direction=None,
        state=EvidenceState.UNAVAILABLE,
        failure=failure_fact(GateGap.PLACEMENT_UNRESOLVED),
        runner_up_placement_ids=(None,),
    )
    return PhotoGeometryDetectionResult(
        resolved_output_slots=None,
        lane_reconstructions=(reconstruction,),
        source_placement_selection=selection,
        output_slot_identities=(),
        source_transform_assessment=_unavailable_transform(),
        lane_transform_assessments=(_unavailable_transform(),),
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
        self.assertEqual(result.output_transforms, ())
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
                shared_direction=None,
                state=EvidenceState.SUPPORTED,
                failure=None,
            )

    def test_empty_source_selection_is_a_valid_unresolved_result(self) -> None:
        selection = TemplateSourceSelection(
            lane_ids=(),
            selected_placement_ids=(),
            shared_scan_geometry=None,
            shared_direction=None,
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
        clipped_requirements=(ClippedRequirement.VISIBLE_PLACEMENT,),
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
        sampling_source_footprint=None,
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
        mapped_output_box=None,
    )


def _measurement_set(
    lane_id: str,
    *,
    registration_index: int,
    purpose: QueryPurpose = QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
) -> PhotoBoundaryMeasurementSet:
    query = PhotoBoundaryMeasurementQuery(
        query_id=f"query:{lane_id}:{registration_index}:{purpose.value}",
        registration_index=registration_index,
        lane_id=lane_id,
        purpose=purpose,
        boundary_axis=BoundaryAxis.X,
        trace_positions_px=(0,),
        search_intervals_px=(FiniteInterval(0.0, 10.0),),
        transition_ownership_intervals_px=(FiniteInterval(0.0, 10.0),),
        expected_support_px=1.0,
        boundary_axis_scale_px_per_mm=PositiveInterval.exact(1.0),
        trace_axis_scale_px_per_mm=PositiveInterval.exact(1.0),
        measurement_halo_px=1,
        registration_provenance_ids=(f"intent:{lane_id}",),
    )
    coverage = PhotoBoundaryCoverageReceipt(
        query_id=query.query_id,
        registered_trace_count=1,
        completed_trace_count=1,
        registered_coordinate_count=1,
        completed_coordinate_count=1,
        pixel_query_count=1,
        streaming_block_count=1,
        peak_temporary_bytes=8,
        complete=True,
    )
    return PhotoBoundaryMeasurementSet(
        query=query,
        state=EvidenceState.SUPPORTED,
        transitions=(),
        coverage=coverage,
    )


if __name__ == "__main__":
    unittest.main()
