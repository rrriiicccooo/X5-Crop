from __future__ import annotations

from dataclasses import replace
from inspect import signature
from pathlib import Path
import unittest

from tools.tests.physical_gate_support import (
    candidate_fixture,
    frame_bleed_fixture,
    selection_fixture,
    transform_geometry_fixture,
)
from x5crop.detection.candidate.selection.model import GeometryResolution
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.candidate.assessment.separator_support import separator_sequence_evidence
from x5crop.detection.candidate.selection.choose import select_candidates
from x5crop.detection.candidate.selection.choose import geometry_clusters
from x5crop.domain import Box, EvidenceState, PixelInterval
from x5crop.detection.physical.model import SequenceResiduals
from x5crop.entry.cli import build_parser
from x5crop.configuration.registry import get_detection_configuration
from x5crop.run_config import RunConfig
from x5crop.runtime.options import RuntimeOptions
from x5crop.units import ScanCalibration


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PhysicalGateModelContractTest(unittest.TestCase):
    def _decision_for_resolution(
        self,
        resolution: GeometryResolution,
        *,
        consensus: str = "uncontested",
    ):
        selection = replace(
            selection_fixture(),
            consensus=consensus,
            geometry_resolution=resolution,
        )
        return apply_decision_gate(
            selection,
            frame_bleed_fixture(),
            transform_geometry_fixture(),
            ScanCalibration(None, None, "unavailable", False),
            image_width=200,
            image_height=100,
        )

    def test_unresolved_count_does_not_duplicate_generic_geometry_reason(
        self,
    ) -> None:
        detection = self._decision_for_resolution(
            GeometryResolution(
                EvidenceState.UNAVAILABLE,
                False,
                False,
                False,
                True,
                True,
                True,
                ("count_unresolved", "placement_unresolved"),
            )
        )
        self.assertEqual(
            detection.final_review_reasons,
            ("count_resolution_unavailable",),
        )

    def test_selection_disagreement_owns_its_final_reason(self) -> None:
        detection = self._decision_for_resolution(
            GeometryResolution(
                EvidenceState.UNAVAILABLE,
                True,
                True,
                True,
                True,
                True,
                False,
                ("geometry_clusters_disagree",),
            ),
            consensus="disagreed",
        )
        self.assertEqual(
            detection.final_review_reasons,
            ("selection_geometry_disagreement",),
        )

    def test_candidate_physical_failure_owns_its_final_reason(self) -> None:
        candidate = candidate_fixture(
            failed_candidate_check="frame_topology_integrity",
        )
        selection = replace(
            selection_fixture(candidate),
            geometry_resolution=GeometryResolution(
                EvidenceState.UNAVAILABLE,
                False,
                False,
                False,
                False,
                True,
                True,
                ("count_unresolved", "placement_unresolved"),
            ),
        )
        detection = apply_decision_gate(
            selection,
            frame_bleed_fixture(feasible=False),
            transform_geometry_fixture(EvidenceState.CONTRADICTED),
            ScanCalibration(None, None, "unavailable", False),
            image_width=200,
            image_height=100,
        )

        self.assertEqual(
            detection.final_review_reasons,
            ("frame_topology_invalid",),
        )

    def test_evidence_state_has_explicit_non_failure_states(self) -> None:
        self.assertEqual(
            {state.value for state in EvidenceState},
            {"supported", "contradicted", "unavailable", "not_applicable"},
        )

    def test_separator_support_does_not_accept_confidence(self) -> None:
        self.assertNotIn("confidence", signature(separator_sequence_evidence).parameters)

    def test_selection_does_not_accept_format_spec(self) -> None:
        self.assertNotIn("fmt", signature(select_candidates).parameters)

    def test_equivalent_geometry_is_consensus(self) -> None:
        candidate = candidate_fixture()
        corroborating_candidate = replace(
            candidate,
            geometry=replace(
                candidate.geometry,
                sequence_hypothesis_name="equivalent_independent_candidate",
            ),
        )
        result = select_candidates(
            (candidate, corroborating_candidate),
            larger_counts_evaluated=True,
        )
        self.assertEqual(result.consensus, "agreed")
        self.assertEqual(len(result.clusters), 1)

    def test_failed_candidate_does_not_create_equal_rank_disagreement(self) -> None:
        good = candidate_fixture()
        bad = candidate_fixture(
            failed_candidate_check="boundary_proof",
        )
        bad = replace(
            bad,
            geometry=replace(
                bad.geometry,
                visible_sequence_span=replace(
                    bad.geometry.visible_sequence_span,
                box=Box(
                    bad.geometry.visible_sequence_span.box.left - 20,
                    bad.geometry.visible_sequence_span.box.top,
                    bad.geometry.visible_sequence_span.box.right + 20,
                    bad.geometry.visible_sequence_span.box.bottom,
                ).clamp(240, 100),
                ),
            ),
        )
        result = select_candidates(
            (good, bad),
            larger_counts_evaluated=True,
        )
        self.assertNotEqual(result.consensus, "disagreed")

    def test_geometry_cluster_requires_common_interval_consensus(self) -> None:
        center = candidate_fixture()
        left = replace(
            center,
            geometry=replace(
                center.geometry,
                photo_intervals=(
                    replace(
                        center.geometry.photo_intervals[0],
                        start=PixelInterval(-5.0, 1.0),
                    ),
                    *center.geometry.photo_intervals[1:],
                ),
            ),
        )
        right = replace(
            center,
            geometry=replace(
                center.geometry,
                photo_intervals=(
                    replace(
                        center.geometry.photo_intervals[0],
                        start=PixelInterval(9.0, 15.0),
                    ),
                    *center.geometry.photo_intervals[1:],
                ),
            ),
        )
        bridge = replace(
            center,
            geometry=replace(
                center.geometry,
                photo_intervals=(
                    replace(
                        center.geometry.photo_intervals[0],
                        start=PixelInterval(0.0, 10.0),
                    ),
                    *center.geometry.photo_intervals[1:],
                ),
            ),
        )
        self.assertEqual(len(geometry_clusters((bridge, left, right))), 2)

    def test_non_dominated_geometry_tradeoff_remains_disagreed(self) -> None:
        selected = candidate_fixture()
        alternative = replace(
            selected,
            geometry=replace(
                selected.geometry,
                visible_sequence_span=replace(
                    selected.geometry.visible_sequence_span,
                    box=Box(10, 0, 210, 100),
                ),
                crop_envelope=replace(
                    selected.geometry.crop_envelope,
                    box=Box(10, 0, 210, 100),
                ),
                photo_intervals=tuple(
                    replace(
                        photo,
                        start=photo.start.plus(PixelInterval.exact(10.0)),
                        end=photo.end.plus(PixelInterval.exact(10.0)),
                    )
                    for photo in selected.geometry.photo_intervals
                ),
                frames=(Box(10, 0, 110, 100), Box(110, 0, 210, 100)),
                residuals=SequenceResiduals(0.10, 0.0, 0.01),
            ),
        )
        selected = replace(
            selected,
            geometry=replace(
                selected.geometry,
                residuals=SequenceResiduals(0.01, 0.0, 0.10),
            ),
        )
        self.assertEqual(
            selected.evidence_quality.physical_residuals,
            selected.geometry.residuals,
        )
        self.assertEqual(
            alternative.evidence_quality.physical_residuals,
            alternative.geometry.residuals,
        )
        result = select_candidates(
            (selected, alternative),
            larger_counts_evaluated=True,
        )
        self.assertEqual(result.consensus, "disagreed")
        self.assertFalse(result.geometry_resolution.alternative_geometries_resolved)

    def test_gate_flow_has_no_confidence_caps_or_generic_fallback(self) -> None:
        source = "\n".join(
            path.read_text()
            for path in (PROJECT_ROOT / "x5crop/detection").rglob("*.py")
        )
        for forbidden in (
            "apply_confidence_cap",
            "confidence_floor",
            "candidate_signal_gate_checks",
            "candidate_gate_failed",
        ):
            self.assertNotIn(forbidden, source)

    def test_runtime_has_no_auto_confidence_threshold(self) -> None:
        self.assertNotIn("confidence_threshold", RunConfig.__dataclass_fields__)
        self.assertNotIn("confidence_threshold", RuntimeOptions.__dataclass_fields__)
        self.assertNotIn("--confidence-threshold", build_parser().format_help())

    def test_final_reason_vocabulary_is_finite_and_physical(self) -> None:
        from x5crop.detection.decision.vocabulary import FINAL_REVIEW_REASONS

        self.assertEqual(len(FINAL_REVIEW_REASONS), 12)
        self.assertIn("content_preservation_unresolved", FINAL_REVIEW_REASONS)
        self.assertIn("boundary_evidence_insufficient", FINAL_REVIEW_REASONS)
        self.assertIn("frame_sequence_not_conserved", FINAL_REVIEW_REASONS)
        self.assertIn("count_resolution_unavailable", FINAL_REVIEW_REASONS)
        self.assertIn("geometry_resolution_unavailable", FINAL_REVIEW_REASONS)


if __name__ == "__main__":
    unittest.main()
