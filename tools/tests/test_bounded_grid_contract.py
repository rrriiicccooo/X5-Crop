from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from tools.regression.safe_crop_acceptance import (
    AcceptancePreflightError,
    RESULT_FIELDS,
    RESULT_SCHEMA,
    SUMMARY_FIELDS,
    SUMMARY_SCHEMA,
    _validate_output_root,
    validate_acceptance_result_record,
    validate_acceptance_summary_record,
)
from x5crop.cache import MeasurementCache, MeasurementCacheKey
from x5crop.configuration.grid import frame_grid_search_prior
from x5crop.configuration.model import FrameCountMode
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.candidate.assessment.candidate_gate import (
    candidate_gate_assessment,
)
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.decision.vocabulary import (
    FINAL_REASON_CAPACITY_OUTPUT_SLOT_COUNT_UNFULFILLED,
    FINAL_REASON_REQUESTED_COUNT_UNFULFILLED,
    FINAL_REASON_SLOT_OWNERSHIP_UNBOUNDED,
)
from x5crop.detection.grid.model import (
    K_MAX,
    O_MAX,
    P_MAX,
    FrameGridWorkStatistics,
    FrameSlot,
    GridOmissionScope,
    GridOmissionSummary,
    GridOmittedAlternative,
    ResolvedOutputSlots,
    SafeCropEnvelope,
    SlotInteraction,
)
from x5crop.detection.grid.search import (
    _interaction,
    _proposal_equivalence_classes,
    search_lane_grid,
)
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.protection import (
    apply_fixed_output_protection,
    output_protection_spec,
)
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.domain import Box, EvidenceState, FiniteInterval
from x5crop.formats.scan_canvas import SCAN_CANVAS_PHYSICAL_SPECS
from x5crop.io.model import ImageProfile, TiffMetadata


def _profile(shape: tuple[int, int]) -> ImageProfile:
    return ImageProfile(
        shape=shape,
        dtype="uint8",
        axes="YX",
        photometric="MINISBLACK",
        compression="NONE",
        sample_format=None,
        bits_per_sample=(8,),
        samples_per_pixel=1,
        planar_config=None,
        resolution=None,
        resolution_unit=None,
        icc_profile=None,
        metadata=TiffMetadata(None, None, None, ()),
    )


def _rectangles(
    *,
    count: int,
    start: int,
    width: int = 112,
    pitch: int = 118,
    extent: int = 720,
) -> np.ndarray:
    pixels = np.zeros((100, extent), dtype=np.uint8)
    for ordinal in range(count):
        left = start + ordinal * pitch
        pixels[:, left : min(extent, left + width)] = 180
    return pixels


def _candidate(
    pixels: np.ndarray,
    *,
    format_id: str = "135",
    strip_mode: str = "partial",
    requested_count: int | None = None,
    layout: str = "horizontal",
):
    configuration = get_detection_configuration(
        format_id,
        strip_mode,
        requested_count,
    )
    workspace = prepare_detection_workspace(
        pixels,
        _profile(tuple(int(value) for value in pixels.shape)),
        layout,
        configuration,
        None,
    )
    return workspace, configuration, choose_detection(
        workspace,
        configuration,
        None,
    )


def _shift_proposal(proposal, delta: int, suffix: str):
    return replace(
        proposal,
        proposal_id=f"{proposal.proposal_id}:{suffix}",
        seed=replace(
            proposal.seed,
            seed_id=f"{proposal.seed.seed_id}:{suffix}",
            origin_px=FiniteInterval(
                proposal.seed.origin_px.minimum + delta,
                proposal.seed.origin_px.maximum + delta,
            ),
        ),
        slots=tuple(
            replace(
                slot,
                start_px=FiniteInterval(
                    slot.start_px.minimum + delta,
                    slot.start_px.maximum + delta,
                ),
                end_px=FiniteInterval(
                    slot.end_px.minimum + delta,
                    slot.end_px.maximum + delta,
                ),
            )
            for slot in proposal.slots
        ),
        safe_envelopes=tuple(
            replace(
                envelope,
                work_box=Box(
                    envelope.work_box.left + delta,
                    envelope.work_box.top,
                    envelope.work_box.right + delta,
                    envelope.work_box.bottom,
                ),
            )
            for envelope in proposal.safe_envelopes
        ),
    )


class BoundedGridContractTest(unittest.TestCase):
    def test_resolved_output_slots_have_one_derived_total(self) -> None:
        resolved = ResolvedOutputSlots((6, 6))
        self.assertEqual(resolved.output_slot_count, 12)
        self.assertEqual(
            tuple(item.name for item in fields(ResolvedOutputSlots)),
            ("lane_output_slot_counts",),
        )
        with self.assertRaises(ValueError):
            ResolvedOutputSlots(())

    def test_count_one_has_no_internal_corridor_or_dp_work(self) -> None:
        _workspace, _configuration, candidate = _candidate(
            _rectangles(count=1, start=250),
            requested_count=1,
        )
        selection = candidate.lane_selections[0]
        proposal = selection.selected_proposal
        assert proposal is not None
        self.assertEqual(proposal.output_slot_count, 1)
        self.assertEqual(proposal.corridor_candidates, ())
        self.assertEqual(proposal.anchor_class.value, "0")
        self.assertEqual(
            proposal.slots[0].previous_interaction,
            SlotInteraction.NOT_APPLICABLE,
        )
        self.assertEqual(
            proposal.slots[0].next_interaction,
            SlotInteraction.NOT_APPLICABLE,
        )
        self.assertTrue(
            all(
                item.dp_states == 0 and item.dp_transitions == 0
                for item in selection.work_by_component
            )
        )

    def test_auto_uses_selected_canvas_capacity_not_visible_count(self) -> None:
        _workspace, configuration, candidate = _candidate(
            _rectangles(count=4, start=120),
        )
        self.assertEqual(configuration.count_request.mode, FrameCountMode.AUTO)
        self.assertIsNone(configuration.count_request.authoritative_count)
        self.assertEqual(
            candidate.resolved_output_slots,
            ResolvedOutputSlots((6,)),
        )
        self.assertEqual(candidate.output_slot_count, 6)
        self.assertEqual(
            len(candidate.lane_selections[0].selected_proposal.slots),
            6,
        )

    def test_120_67_short_profile_capacity_is_two_other_profiles_three(
        self,
    ) -> None:
        rng = np.random.default_rng(23)
        _workspace, _configuration, short = _candidate(
            rng.integers(0, 256, size=(200, 594), dtype=np.uint8),
            format_id="120-67",
        )
        _workspace, _configuration, standard = _candidate(
            rng.integers(0, 256, size=(100, 377), dtype=np.uint8),
            format_id="120-67",
        )
        self.assertEqual(
            short.source_core.lanes[0].scan_canvas.selected_profile.profile_id,
            "120_wide_188_5",
        )
        self.assertEqual(short.resolved_output_slots, ResolvedOutputSlots((2,)))
        self.assertEqual(standard.resolved_output_slots, ResolvedOutputSlots((3,)))
        fits = {
            profile.profile_id: next(
                item.maximum_frame_count
                for item in profile.format_fits
                if item.format_id == "120-67"
            )
            for profile in SCAN_CANVAS_PHYSICAL_SPECS
            if any(item.format_id == "120-67" for item in profile.format_fits)
        }
        self.assertEqual(fits["120_wide_188_5"], 2)
        self.assertTrue(
            all(
                count == 3
                for profile_id, count in fits.items()
                if profile_id != "120_wide_188_5"
            )
        )

    def test_equivalent_proposals_union_and_scores_cannot_change_geometry(
        self,
    ) -> None:
        workspace, configuration, candidate = _candidate(
            _rectangles(count=2, start=120),
            requested_count=2,
        )
        proposal = candidate.lane_selections[0].selected_proposal
        assert proposal is not None
        close = replace(
            _shift_proposal(proposal, 1, "close"),
            scalar_ordering_score=-999.0,
            residual_mm=999.0,
        )
        classes = _proposal_equivalence_classes((proposal, close), 2.0)
        reversed_scores = _proposal_equivalence_classes(
            (
                replace(proposal, scalar_ordering_score=-999.0, residual_mm=999.0),
                replace(close, scalar_ordering_score=999.0, residual_mm=0.0),
            ),
            2.0,
        )
        self.assertEqual(len(classes), 1)
        self.assertEqual(len(reversed_scores), 1)
        merged = classes[0].merged_proposal
        reversed_merged = reversed_scores[0].merged_proposal
        self.assertEqual(merged.slots, reversed_merged.slots)
        self.assertEqual(merged.safe_envelopes, reversed_merged.safe_envelopes)
        self.assertLessEqual(
            merged.safe_envelopes[0].work_box.left,
            proposal.safe_envelopes[0].work_box.left,
        )
        self.assertGreaterEqual(
            merged.safe_envelopes[0].work_box.right,
            close.safe_envelopes[0].work_box.right,
        )
        self.assertIs(
            workspace.source_core.lanes[0].scan_canvas.axis_scales,
            workspace.source_core.lanes[0].axis_scale_intervals,
        )
        self.assertEqual(
            configuration.detector_kind,
            "bounded_safe_crop_capacity_grid",
        )

    def test_non_equivalent_whole_pitch_classes_do_not_select_a_winner(
        self,
    ) -> None:
        workspace, configuration, candidate = _candidate(
            _rectangles(count=2, start=120),
            requested_count=2,
        )
        proposal = candidate.lane_selections[0].selected_proposal
        assert proposal is not None
        whole_pitch = replace(
            _shift_proposal(proposal, 118, "whole-pitch"),
            scalar_ordering_score=10_000.0,
            residual_mm=0.0,
        )
        classes = _proposal_equivalence_classes(
            (proposal, whole_pitch),
            1.0,
        )
        self.assertEqual(len(classes), 2)
        prior = frame_grid_search_prior("135", "partial", 36.0)
        prior_work = candidate.lane_selections[0].work_by_component[0]
        with mock.patch(
            "x5crop.detection.grid.search._component_proposals",
            return_value=((proposal, whole_pitch), prior_work),
        ):
            selection = search_lane_grid(
                workspace.source_core.lanes[0],
                workspace.separator_fields[0],
                2,
                configuration.physical_spec.aperture_components,
                (prior,),
            )
        self.assertIsNone(selection.selected_proposal)
        self.assertEqual(
            selection.selection_reason,
            "non_equivalent_alternatives",
        )
        self.assertEqual(selection.ordinal_state, EvidenceState.CONTRADICTED)

    def test_omission_risk_is_derived_and_blocks_selection(self) -> None:
        workspace, configuration, candidate = _candidate(
            _rectangles(count=2, start=120),
            requested_count=2,
        )
        proposal = candidate.lane_selections[0].selected_proposal
        assert proposal is not None
        work = candidate.lane_selections[0].work_by_component[0]
        absorbed = GridOmissionSummary(
            scope_id="scope:absorbed",
            scope=GridOmissionScope.DP_FRONTIER,
            lane_id="lane:0",
            component_id=work.component_id,
            seed_id="seed:1",
            corridor_ordinal=1,
            discovered_count=2,
            retained_count=1,
            omitted_alternatives=(
                GridOmittedAlternative("path:2", "class:1"),
            ),
        )
        unresolved = replace(
            absorbed,
            scope_id="scope:unresolved",
            omitted_alternatives=(
                GridOmittedAlternative("path:2", None),
            ),
        )
        self.assertEqual(absorbed.unresolved_outcome_count, 0)
        self.assertEqual(unresolved.unresolved_outcome_count, 1)
        safe_work = replace(work, omission_summaries=(absorbed,))
        unsafe_work = replace(work, omission_summaries=(unresolved,))
        self.assertFalse(safe_work.omitted_outcome_risk)
        self.assertTrue(unsafe_work.omitted_outcome_risk)
        prior = frame_grid_search_prior("135", "partial", 36.0)
        with mock.patch(
            "x5crop.detection.grid.search._component_proposals",
            return_value=((proposal,), unsafe_work),
        ):
            selection = search_lane_grid(
                workspace.source_core.lanes[0],
                workspace.separator_fields[0],
                2,
                configuration.physical_spec.aperture_components,
                (prior,),
            )
        self.assertIsNone(selection.selected_proposal)
        self.assertEqual(
            selection.grid_search_coverage_state,
            EvidenceState.CONTRADICTED,
        )
        self.assertEqual(
            selection.selection_reason,
            "omitted_outcome_unresolved",
        )

    def test_structural_limits_are_per_lane_component(self) -> None:
        pixels = np.random.default_rng(8).integers(
            0,
            256,
            size=(100, 720),
            dtype=np.uint8,
        )
        _workspace, _configuration, candidate = _candidate(pixels)
        selection = candidate.lane_selections[0]
        for work in selection.work_by_component:
            self.assertLessEqual(work.seed_count, P_MAX)
            self.assertLessEqual(work.dp_states, work.state_upper)
            self.assertLessEqual(work.dp_transitions, work.transition_upper)
            self.assertFalse(work.budget_exhausted)
            self.assertTrue(
                all(summary.scope_id for summary in work.omission_summaries)
            )
        self.assertEqual(O_MAX, 2)
        self.assertEqual(K_MAX, 3)
        self.assertEqual(FrameGridWorkStatistics.state_limit(12), 198)
        self.assertEqual(FrameGridWorkStatistics.transition_limit(12), 558)

    def test_blank_capacity_contact_and_protection_saturation_are_safe(
        self,
    ) -> None:
        workspace, _configuration, candidate = _candidate(
            np.zeros((100, 720), dtype=np.uint8),
        )
        proposal = candidate.lane_selections[0].selected_proposal
        assert proposal is not None
        self.assertEqual(proposal.seed.provenance, "blank_center_model")
        self.assertEqual(len(proposal.slots), 6)
        self.assertTrue(
            all(
                slot.appearance_state == EvidenceState.UNAVAILABLE
                for slot in proposal.slots
            )
        )
        protected = candidate.protected_envelopes_by_lane[0]
        self.assertTrue(
            all(
                {"top", "bottom"}.issubset(item.saturated_sides)
                for item in protected
            )
        )
        self.assertGreater(
            protected[0].protected_work_box.right,
            protected[1].protected_work_box.left,
        )
        self.assertTrue(candidate.gate.passed)
        self.assertEqual(
            _interaction(
                FiniteInterval.exact(10.0),
                FiniteInterval.exact(10.0000001),
                0.001,
            ),
            SlotInteraction.CONTACT,
        )
        self.assertEqual(
            _interaction(
                FiniteInterval.exact(10.0),
                FiniteInterval.exact(9.0),
                0.001,
            ),
            SlotInteraction.OVERLAP,
        )
        lane = workspace.source_core.lanes[0]
        with self.assertRaises(ValueError):
            apply_fixed_output_protection(
                lane,
                (
                    SafeCropEnvelope(
                        "lane:0",
                        1,
                        Box(-1, 0, 100, 100),
                        "model_outward_union",
                    ),
                ),
                output_protection_spec("135"),
            )

    def test_positive_content_placement_covers_trailing_explicit_and_auto(
        self,
    ) -> None:
        rng = np.random.default_rng(91)
        pixels = np.zeros((100, 720), dtype=np.uint8)
        pixels[:, 300:700] = rng.integers(
            20,
            230,
            size=(100, 400),
            dtype=np.uint8,
        )
        for request, expected in ((7, 7), (None, 12)):
            with self.subTest(request=request):
                _workspace, _configuration, candidate = _candidate(
                    pixels,
                    format_id="half",
                    requested_count=request,
                )
                proposal = candidate.lane_selections[0].selected_proposal
                assert proposal is not None
                self.assertTrue(candidate.gate.passed)
                self.assertEqual(proposal.output_slot_count, expected)
                self.assertEqual(
                    proposal.seed.provenance,
                    "positive_content_placement",
                )
                self.assertLessEqual(
                    proposal.safe_envelopes[0].work_box.left,
                    300,
                )
                self.assertGreaterEqual(
                    proposal.safe_envelopes[-1].work_box.right,
                    700,
                )

    def test_vertical_and_two_120_components_use_the_same_flow(self) -> None:
        horizontal = _rectangles(count=2, start=120)
        _workspace, _configuration, vertical = _candidate(
            horizontal.T,
            requested_count=2,
            layout="vertical",
        )
        self.assertEqual(
            vertical.lane_selections[0].selected_proposal.output_slot_count,
            2,
        )
        _workspace, _configuration, medium = _candidate(
            np.zeros((100, 377), dtype=np.uint8),
            format_id="120-66",
        )
        self.assertEqual(
            {item.component_id for item in medium.lane_selections[0].work_by_component},
            {"component:0:54x54", "component:1:56x56"},
        )
        self.assertEqual(medium.output_slot_count, 3)

    def test_output_slot_gate_reasons_are_mode_specific(self) -> None:
        base = dict(
            scan_canvas_state=EvidenceState.SUPPORTED,
            source_content_state=EvidenceState.SUPPORTED,
            grid_search_coverage_state=EvidenceState.SUPPORTED,
            output_slot_count_state=EvidenceState.CONTRADICTED,
            slot_ordinal_state=EvidenceState.SUPPORTED,
            slot_ownership_state=EvidenceState.SUPPORTED,
            known_content_containment_state=EvidenceState.UNAVAILABLE,
            source_lane_geometry_state=EvidenceState.SUPPORTED,
            output_protection_state=EvidenceState.SUPPORTED,
            output_transform_state=EvidenceState.SUPPORTED,
        )
        gate = candidate_gate_assessment(**base)
        auto = apply_decision_gate(gate, FrameCountMode.AUTO)
        explicit = apply_decision_gate(gate, FrameCountMode.EXPLICIT)
        self.assertEqual(
            auto.final_review_reasons,
            (FINAL_REASON_CAPACITY_OUTPUT_SLOT_COUNT_UNFULFILLED,),
        )
        self.assertEqual(
            explicit.final_review_reasons,
            (FINAL_REASON_REQUESTED_COUNT_UNFULFILLED,),
        )
        unresolved = candidate_gate_assessment(
            **{
                **base,
                "scan_canvas_state": EvidenceState.UNAVAILABLE,
                "output_slot_count_state": EvidenceState.NOT_APPLICABLE,
            }
        )
        self.assertEqual(
            tuple(check.code for check in unresolved.blocking_checks),
            ("scan_canvas_authority",),
        )

    def test_typed_ownership_contradiction_and_cache_boundary(self) -> None:
        with self.assertRaises(ValueError):
            FrameSlot(
                lane_id="lane:0",
                lane_ordinal=1,
                start_px=FiniteInterval.exact(10.0),
                end_px=FiniteInterval.exact(10.0),
                appearance_state=EvidenceState.UNAVAILABLE,
                previous_interaction=SlotInteraction.NOT_APPLICABLE,
                next_interaction=SlotInteraction.NOT_APPLICABLE,
            )
        gate = candidate_gate_assessment(
            scan_canvas_state=EvidenceState.SUPPORTED,
            source_content_state=EvidenceState.SUPPORTED,
            grid_search_coverage_state=EvidenceState.SUPPORTED,
            output_slot_count_state=EvidenceState.SUPPORTED,
            slot_ordinal_state=EvidenceState.SUPPORTED,
            slot_ownership_state=EvidenceState.CONTRADICTED,
            known_content_containment_state=EvidenceState.UNAVAILABLE,
            source_lane_geometry_state=EvidenceState.SUPPORTED,
            output_protection_state=EvidenceState.SUPPORTED,
            output_transform_state=EvidenceState.SUPPORTED,
        )
        decision = apply_decision_gate(gate, FrameCountMode.EXPLICIT)
        self.assertEqual(
            decision.final_review_reasons,
            (FINAL_REASON_SLOT_OWNERSHIP_UNBOUNDED,),
        )
        workspace, _configuration, _value = _candidate(
            _rectangles(count=2, start=250),
            requested_count=2,
        )
        self.assertEqual(
            tuple(item.name for item in fields(MeasurementCache)),
            ("key", "gray_work", "image_statistics"),
        )
        self.assertEqual(
            tuple(item.name for item in fields(MeasurementCacheKey)),
            (
                "workspace_identity",
                "layout",
                "base_gray_parameters",
                "statistics_parameters",
            ),
        )
        forbidden = {
            "seed",
            "candidate",
            "proposal",
            "gate",
            "decision",
            "reason",
            "output_box",
            "count",
            "offset",
        }
        self.assertTrue(
            forbidden.isdisjoint(
                {item.name for item in fields(MeasurementCache)}
                | {item.name for item in fields(MeasurementCacheKey)}
            )
        )
        self.assertFalse(workspace.measurement_cache.gray_work.flags.writeable)


class AcceptanceSchemaContractTest(unittest.TestCase):
    def test_frozen_result_and_summary_schemas(self) -> None:
        result = dict.fromkeys(RESULT_FIELDS)
        result.update(
            {
                "result_schema": RESULT_SCHEMA,
                "decision_status": "terminal_failure",
                "passed": False,
            }
        )
        validate_acceptance_result_record(result)
        summary = dict.fromkeys(SUMMARY_FIELDS)
        summary.update(
            {
                "summary_schema": SUMMARY_SCHEMA,
                "real_holdout": "unavailable",
                "passed": False,
            }
        )
        validate_acceptance_summary_record(summary)
        with self.assertRaises(ValueError):
            validate_acceptance_result_record({**result, "legacy_alias": True})

    def test_preflight_requires_an_empty_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "existing").write_text("occupied", encoding="utf-8")
            with self.assertRaises(AcceptancePreflightError):
                _validate_output_root(root)

    def test_uncovered_formats_use_physical_rules_and_full_flow(self) -> None:
        cases = (
            ("xpan", np.zeros((100, 720), dtype=np.uint8), 3),
            ("120-645", np.zeros((100, 377), dtype=np.uint8), 4),
        )
        for format_id, pixels, expected_count in cases:
            with self.subTest(format_id=format_id):
                prior = frame_grid_search_prior(
                    format_id,
                    "partial",
                    65.0 if format_id == "xpan" else 42.0,
                )
                self.assertEqual(prior.provenance, "physical_rule")
                _workspace, _configuration, candidate = _candidate(
                    pixels,
                    format_id=format_id,
                )
                self.assertEqual(candidate.output_slot_count, expected_count)
                self.assertTrue(candidate.gate.passed)


if __name__ == "__main__":
    unittest.main()
