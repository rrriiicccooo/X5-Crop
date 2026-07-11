from __future__ import annotations

import ast
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT
from x5crop.detection.candidate.assessment.evidence_independence import (
    evidence_independence_detail,
)
from x5crop.domain import Box, DetectionCandidate
from x5crop.policies.parameters.candidate import EvidenceIndependenceParameters


def _candidate(*, photo_edges: bool = True) -> DetectionCandidate:
    detail = {
        "outer_candidate_strategy": "separator_outer",
        "standard_gap_search": {
            "entries": [
                {"selected_source": "standard_detected"},
                {"selected_source": "observed_width_profile"},
            ]
        },
    }
    if photo_edges:
        detail.update(
            {
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
            }
        )
    else:
        detail.update(
            {
                "width_cv": 0.20,
                "width_cv_source": "frame_boxes",
                "frame_box_width_cv": 0.20,
            }
        )
    return DetectionCandidate(
        format_id="120-66",
        layout="horizontal",
        strip_mode="full",
        count=3,
        outer=Box(0, 0, 300, 100),
        frames=[],
        gaps=[],
        confidence=0.90,
        detail=detail,
    )


class PhysicalEvidenceIndependenceContractTest(unittest.TestCase):
    def test_evidence_strings_do_not_claim_gate_or_review_authority(self) -> None:
        offenders: list[str] = []
        root = PROJECT_ROOT / "x5crop/detection/evidence"
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                value = node.value.lower()
                if any(term in value for term in ("gate", "blocker", "review", "pass")):
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{node.value}")
        self.assertEqual(offenders, [])

    def test_guidance_does_not_own_final_scoring_or_decision(self) -> None:
        banned = (
            "final_review_reasons",
            "DecisionGate",
            "CandidateGate",
            "approved_auto",
            "needs_review",
        )
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop/detection/guidance").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            offenders.extend(
                f"{path.relative_to(PROJECT_ROOT)}:{term}"
                for term in banned
                if term in source
            )
        self.assertEqual(offenders, [])

    def test_dependent_separator_geometry_requires_independent_validation(self) -> None:
        detail = evidence_independence_detail(
            _candidate(),
            source="separator",
            frame_content_support_available=True,
            photo_geometry_supported=True,
            policy=EvidenceIndependenceParameters(),
        )
        self.assertTrue(detail["requires_validation"])
        self.assertTrue(detail["ok"])
        self.assertEqual(detail["state"], "supported")

    def test_dependency_cycle_is_a_physical_contradiction(self) -> None:
        detail = evidence_independence_detail(
            _candidate(),
            source="separator",
            frame_content_support_available=False,
            photo_geometry_supported=False,
            policy=EvidenceIndependenceParameters(),
        )
        self.assertFalse(detail["ok"])
        self.assertEqual(detail["state"], "contradicted")
        self.assertEqual(detail["reason"], "evidence_dependency_cycle_detected")

    def test_frame_box_width_does_not_validate_photo_geometry(self) -> None:
        detail = evidence_independence_detail(
            _candidate(photo_edges=False),
            source="separator",
            frame_content_support_available=True,
            photo_geometry_supported=False,
            policy=EvidenceIndependenceParameters(),
        )
        self.assertFalse(detail["photo_width_stability"]["used"])
        self.assertFalse(detail["geometry_ok"])
        self.assertFalse(detail["ok"])

    def test_non_separator_source_is_not_applicable(self) -> None:
        detail = evidence_independence_detail(
            _candidate(),
            source="content",
            frame_content_support_available=True,
            photo_geometry_supported=True,
            policy=EvidenceIndependenceParameters(),
        )
        self.assertEqual(detail["state"], "not_applicable")
        self.assertTrue(detail["ok"])

    def test_partial_edge_safety_has_no_composite_score_inputs(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop/detection/candidate/assessment/partial_holder.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "joint_score",
            "geometry_score",
            "content_score",
            "min_content_score",
        ):
            self.assertNotIn(forbidden, source)

    def test_separator_width_variation_is_not_a_gate_requirement(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                PROJECT_ROOT / "x5crop/detection/candidate/assessment"
            ).rglob("*.py")
        )
        self.assertNotIn("separator_width_cv >", source)
        self.assertNotIn("separator_width_unstable", source)


if __name__ == "__main__":
    unittest.main()
