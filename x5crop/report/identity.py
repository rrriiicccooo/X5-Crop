from __future__ import annotations

from hashlib import sha256
import json
from typing import Any


REPORT_SCHEMA_ID = "detection_report"
REPORT_SCHEMA_REVISION = "frame_slot_sequence_resolution"


_IMMUTABLE_OUTPUT_FIELDS = (
    "frame_bleed_plan",
    "finalization_plan",
    "final_geometry",
    "export_eligibility",
)


def runtime_facts_sha256(record: dict[str, Any]) -> str:
    output = record["output"]
    payload = {
        "schema_id": record["schema_id"],
        "schema_revision": record["schema_revision"],
        "script_version": record["script_version"],
        "source": record["source"],
        "input": record["input"],
        "configuration": record["configuration"],
        "selection": record["selection"],
        "decision": record["decision"],
        "output": {field: output[field] for field in _IMMUTABLE_OUTPUT_FIELDS},
        "analysis_identity": record["analysis_identity"],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def bind_runtime_facts(record: dict[str, Any]) -> dict[str, Any]:
    record["runtime_facts_sha256"] = runtime_facts_sha256(record)
    return record
