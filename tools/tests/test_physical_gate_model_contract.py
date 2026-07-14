from __future__ import annotations

from dataclasses import replace
from inspect import signature
from pathlib import Path
import unittest

from tools.tests.physical_gate_support import (
    candidate_evidence_fixture,
    candidate_fixture,
    frame_bleed_fixture,
    selection_fixture,
    transform_geometry_fixture,
)
from x5crop.detection.candidate.selection.model import (
    SelectionConsensus,
)
from x5crop.detection.geometry_resolution import GeometryResolution
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.evidence.separator_sequence import separator_sequence_evidence
from x5crop.detection.candidate.selection.choose import select_candidates
from x5crop.detection.candidate.selection.choose import geometry_clusters
from x5crop.detection.candidate.assessment.candidate import (
    candidate_gate_for_evidence,
)
from x5crop.detection.candidate.model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
)
from x5crop.domain import (
    BoundarySide,
    Box,
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
    PhotoApertureEdgeSource,
)
from x5crop.detection.physical.model import SequenceResiduals
from x5crop.entry.cli import build_parser
from x5crop.run_config import RunConfig
from x5crop.runtime.options import RuntimeOptions


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _independent_photo_edge(source: str) -> MeasurementProvenance:
    return MeasurementProvenance(
        MeasurementIdentity.PHOTO_EDGES,
        ObservationId(source),
        (MeasurementIdentity.GRAY_WORK,),
        "synthetic independent photo edge",
    )


def _candidate_with_geometry(candidate, geometry):
    evidence = candidate_evidence_fixture(geometry=geometry)
    built = BuiltCandidate(geometry, candidate.count_hypothesis, ())
    return AssessedCandidate(
        geometry,
        candidate.count_hypothesis,
        CandidateAssessment(
            evidence,
            candidate_gate_for_evidence(built, evidence),
        ),
    )


def _with_leading_interval(candidate, interval: PixelInterval, source: str):
    geometry = candidate.geometry
    leading = replace(
        geometry.photo_apertures[0].leading,
        position=interval,
        source=PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH,
        provenance=_independent_photo_edge(source),
    )
    first = replace(geometry.photo_apertures[0], leading=leading)
    updated = replace(
        geometry,
        photo_apertures=(first, *geometry.photo_apertures[1:]),
        aperture_edge_assignments=tuple(
            item
            for item in geometry.aperture_edge_assignments
            if not (
                item.photo_index == 1 and item.side == BoundarySide.LEADING
            )
        ),
    )
    return _candidate_with_geometry(candidate, updated)


def _with_shifted_short_axis(candidate, offset: float):
    geometry = candidate.geometry
    apertures = tuple(
        replace(
            aperture,
            top=replace(
                aperture.top,
                position=aperture.top.position.plus(PixelInterval.exact(offset)),
            ),
            bottom=replace(
                aperture.bottom,
                position=aperture.bottom.position.plus(PixelInterval.exact(offset)),
            ),
        )
        for aperture in geometry.photo_apertures
    )
    updated = replace(
        geometry,
        holder_span=replace(
            geometry.holder_span,
            box=Box(0, 0, 310, 120),
        ),
        photo_apertures=apertures,
        aperture_edge_assignments=tuple(
            item
            for item in geometry.aperture_edge_assignments
            if item.side not in {BoundarySide.TOP, BoundarySide.BOTTOM}
        ),
    )
    return _candidate_with_geometry(candidate, updated)


class PhysicalGateModelContractTest(unittest.TestCase):
    def _decision_for_resolution(
        self,
        resolution: GeometryResolution,
        *,
        consensus: SelectionConsensus = SelectionConsensus.UNCONTESTED,
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
        )

    def test_unresolved_count_does_not_duplicate_generic_geometry_reason(
        self,
    ) -> None:
        detection = self._decision_for_resolution(
            GeometryResolution(
                False,
                False,
                False,
                True,
                True,
                True,
                True,
                False,
            )
        )
        self.assertEqual(
            detection.final_review_reasons,
            ("count_resolution_unavailable",),
        )

    def test_selection_disagreement_owns_its_final_reason(self) -> None:
        detection = self._decision_for_resolution(
            GeometryResolution(
                True,
                True,
                True,
                True,
                True,
                False,
                True,
                False,
            ),
            consensus=SelectionConsensus.DISAGREED,
        )
        self.assertEqual(
            detection.final_review_reasons,
            ("selection_geometry_disagreement",),
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
                sequence_provenance=replace(
                    candidate.geometry.sequence_provenance,
                    observation_id=ObservationId(
                        "equivalent_independent_candidate"
                    ),
                    description="equivalent independent candidate",
                ),
            ),
        )
        result = select_candidates(
            (candidate, corroborating_candidate),
            larger_count_hypotheses_resolved=True,
            candidate_search_budget_exhausted=False,
        )
        self.assertEqual(result.consensus, SelectionConsensus.AGREED)
        self.assertEqual(len(result.clusters), 1)

    def test_failed_candidate_does_not_create_equal_rank_disagreement(self) -> None:
        good = candidate_fixture()
        bad = candidate_fixture(
            failed_candidate_check="boundary_proof",
        )
        bad = _with_leading_interval(
            bad,
            PixelInterval(10.0, 20.0),
            "failed_candidate_leading_edge",
        )
        result = select_candidates(
            (good, bad),
            larger_count_hypotheses_resolved=True,
            candidate_search_budget_exhausted=False,
        )
        self.assertNotEqual(result.consensus, SelectionConsensus.DISAGREED)

    def test_geometry_cluster_requires_common_interval_consensus(self) -> None:
        center = candidate_fixture()
        left = _with_leading_interval(
            center,
            PixelInterval(0.0, 4.0),
            "left_geometry_leading_edge",
        )
        right = _with_leading_interval(
            center,
            PixelInterval(12.0, 16.0),
            "right_geometry_leading_edge",
        )
        bridge = _with_leading_interval(
            center,
            PixelInterval(3.0, 13.0),
            "bridge_geometry_leading_edge",
        )
        self.assertEqual(len(geometry_clusters((bridge, left, right))), 2)

    def test_non_dominated_geometry_tradeoff_remains_disagreed(self) -> None:
        selected = candidate_fixture()
        alternative = _with_shifted_short_axis(selected, 10.0)
        alternative = replace(
            alternative,
            geometry=replace(
                alternative.geometry,
                residuals=SequenceResiduals(0.10, 0.01),
            ),
        )
        selected = replace(
            selected,
            geometry=replace(
                selected.geometry,
                residuals=SequenceResiduals(0.01, 0.10),
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
            larger_count_hypotheses_resolved=True,
            candidate_search_budget_exhausted=False,
        )
        self.assertEqual(result.consensus, SelectionConsensus.DISAGREED)
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

        self.assertEqual(len(FINAL_REVIEW_REASONS), 10)
        self.assertIn("content_preservation_unresolved", FINAL_REVIEW_REASONS)
        self.assertIn("boundary_evidence_insufficient", FINAL_REVIEW_REASONS)
        self.assertIn("count_resolution_unavailable", FINAL_REVIEW_REASONS)
        self.assertIn("geometry_resolution_unavailable", FINAL_REVIEW_REASONS)


if __name__ == "__main__":
    unittest.main()
