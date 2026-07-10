from __future__ import annotations

from pathlib import Path

from x5crop.policies.decision.contract import decision_contract_for_policy
from x5crop.policies.registry import get_detection_policy
from x5crop.run_config import RunConfig


def decision_test_config(*, threshold: float = 0.85) -> RunConfig:
    return RunConfig(
        input_path=Path("synthetic.tif"),
        output_dir=None,
        format_id="135",
        layout_auto=False,
        layout="horizontal",
        strip_mode="full",
        requested_count=1,
        page=0,
        bleed_x=0,
        bleed_y=0,
        deskew="off",
        deskew_fallback="off",
        deskew_min_angle=-2.0,
        deskew_max_angle=2.0,
        confidence_threshold=threshold,
        review_dir=None,
        copy_review_files=False,
        export_review=False,
        diagnostics=False,
        compression="auto",
        debug=False,
        debug_analysis=False,
        dry_run=True,
        overwrite=True,
        report=True,
        debug_errors=False,
        reuse_analysis=False,
        jobs=1,
    )


def content_ok_detail() -> dict[str, bool | str]:
    return {
        "used": True,
        "support": "ok",
        "content_containment_ok": True,
        "content_integrity_failed": False,
    }


def decision_contract(format_id: str = "135", strip_mode: str = "full"):
    return decision_contract_for_policy(get_detection_policy(format_id, strip_mode))


def candidate_gate_detail(
    passed: bool,
    *,
    blockers: list[str] | None = None,
    diagnostics: list[str] | None = None,
) -> dict:
    return {
        "passed": bool(passed),
        "checks": [],
        "blockers": list(blockers or []),
        "diagnostics": list(diagnostics or []),
        "confidence_caps": [],
    }
