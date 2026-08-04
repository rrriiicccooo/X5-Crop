from __future__ import annotations

from hashlib import sha256
import json
from typing import Any


REPORT_SCHEMA_ID = "detection_report"
REPORT_SCHEMA_REVISION = "source_coordinate_format_placement_v2"


def core_facts_sha256(record: dict[str, Any]) -> str:
    payload = {
        "schema_id": record["schema_id"],
        "schema_revision": record["schema_revision"],
        "script_version": record["script_version"],
        "source": record["source"],
        "input": record["input"],
        "configuration": record["configuration"],
        "measurement": record["measurement"],
        "photo_geometry": record["photo_geometry"],
        "candidate_gate": record["candidate_gate"],
        "decision": record["decision"],
        "finalization": record["output"]["finalization"],
        "analysis_identity": record["analysis_identity"],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def bind_core_facts(record: dict[str, Any]) -> dict[str, Any]:
    record["core_facts_sha256"] = core_facts_sha256(record)
    return record
