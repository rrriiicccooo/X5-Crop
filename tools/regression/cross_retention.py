"""Compare base Cross raw accounting across two current development reports.

This is an offline retention audit, not a physical-refutation proof or a Gate.
Both reports must first pass the ordinary current-report validator. A changed
measurement or a new association needs its own evidence; absence from a new
generator is never reported as physical exclusion.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import fields
import hashlib
import json
from pathlib import Path
import sys

from x5crop.detection.photo_geometry.measurement_model import PhotoBoundaryMeasurementSet
from x5crop.detection.photo_geometry.model import MINIMUM_INDEPENDENT_SUPPORT_REGIONS
from x5crop.report.read_models import typed_read_model

from .accuracy import DEVELOPMENT_GOLD_COHORT_PATH, PROJECT_ROOT
from .file_identity import sha256_file
from .report_validation import _read_common_proof, validate_current_report_record


AUDIT_SCHEMA = "x5crop_base_cross_retention_audit_v1"
_PURPOSES = {"top_corridor": "top", "bottom_corridor": "bottom"}


def _point_key(point: dict, groups: dict, *, purpose: str, source_sha256: str) -> str:
    """Keep recorded values, including missing proof; never grant peak identity."""
    reference = point["peak_source"]
    group = None if reference is None else groups[reference["group_id"]]
    if group is not None:
        group = {**group, "source": {**group["source"], "source_id": source_sha256}}
    value = {key: item for key, item in point.items()
             if key not in {"transition_id", "query_id", "trace_ordinal", "peak_source"}}
    native = value["native_background_texture"]
    if native is not None:
        value["native_background_texture"] = {
            **native, "query": {key: item for key, item in native["query"].items() if key != "query_id"},
        }
    value["peak_source"] = None if reference is None else {**reference, "group_id": group}
    payload = json.dumps((purpose, source_sha256, value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _snapshot(record: dict, lane: dict, source_sha256: str) -> dict:
    points, traces, indexes = {}, {}, defaultdict(list)
    for raw in record["development"]["measurement"]["queries"]:
        query = raw["query"]
        purpose = query["purpose"]
        if query["lane_id"] != lane["lane_id"] or purpose not in _PURPOSES:
            continue
        measured = _read_common_proof(
            {field.name: raw[field.name] for field in fields(PhotoBoundaryMeasurementSet)},
            PhotoBoundaryMeasurementSet,
        )
        groups = {group.primitive_id: typed_read_model(group) for group in measured.peak_source_groups}
        traces[_PURPOSES[purpose]] = set(query["trace_positions_px"])
        for point in raw["transitions"]:
            identity = point["transition_id"]
            key = _point_key(point, groups, purpose=purpose, source_sha256=source_sha256)
            if identity in points:
                raise ValueError("base Cross transition identity is registered twice")
            points[identity] = (key, point, _PURPOSES[purpose])
            indexes[key].append(identity)
    base = lane["base_cross_registration"]
    raw_by_observation, roles = {}, {}
    ledger = []

    def remember(identity, role, raw_ids):
        raw_set = frozenset(raw_ids)
        if not raw_set or any(raw not in points or points[raw][2] != role for raw in raw_set):
            raise ValueError("base Cross ledger lost its own measured raw points")
        if identity in raw_by_observation and (raw_by_observation[identity] != raw_set or roles[identity] != role):
            raise ValueError("base Cross observation identity changed its raw union")
        raw_by_observation[identity], roles[identity] = raw_set, role
        return raw_set

    for observation in base["observations"]:
        raw_set = remember(observation["observation_id"], observation["role"], observation["transition_ids"])
        ledger.append(("fitted", observation["role"], raw_set))
    for family in base["family_resolutions"]:
        role = family["role"]
        for identity, raw_ids in zip(family["member_observation_ids"], family["member_transition_groups"], strict=True):
            ledger.append(("family_atom", role, remember(identity, role, raw_ids)))
        ledger.append(("family_union", role, frozenset(family["member_transition_ids"])))
    membership = base["membership_receipt"]
    if membership is not None:
        for scope in membership["scopes"]:
            for members in scope["maximal_member_groups"]:
                ledger.append(("membership_union", scope["role"], frozenset(
                    raw for identity in members for raw in raw_by_observation[identity])))
    for run in lane["search"]["cross_profile"]["runs"]:
        ledger.append(("tracking", run["role_hint"], frozenset(run["transition_ids"])))
    bindings = [binding for name in ("top_bindings", "bottom_bindings") for binding in base[name]
                if not binding["conditional_family_ids"]
                and binding["independent_support_region_count"] >= MINIMUM_INDEPENDENT_SUPPORT_REGIONS]
    for binding in bindings:
        ledger.append(("base_solver", binding["role"], raw_by_observation[binding["observation_id"]]))
    return {"points": points, "traces": traces, "indexes": indexes, "ledger": tuple(set(ledger)),
            "bindings": bindings, "raw_by_observation": raw_by_observation}


def _compare_binding(binding: dict, before: dict, after: dict) -> dict:
    raw_ids = before["raw_by_observation"][binding["observation_id"]]
    mapped, gaps = set(), []
    unavailable_peak_provenance = 0
    for identity in sorted(raw_ids):
        key, point, role = before["points"][identity]
        unavailable_peak_provenance += point["peak_source"] is None
        matches = after["indexes"].get(key, ())
        if len(matches) == 1:
            mapped.add(matches[0])
            continue
        reason = ("non_unique_raw_identity" if matches else
                  "trace_not_registered" if point["trace_coordinate_px"] not in after["traces"].get(role, ())
                  else "measurement_changed_or_unavailable")
        gaps.append({"transition_id": identity, "trace_coordinate_px": point["trace_coordinate_px"],
                     "canonical_coordinate_px": point["canonical_coordinate_px"], "reason": reason})
    exact, containing = Counter(), Counter()
    if not gaps:
        for kind, role, raw_set in after["ledger"]:
            if role == binding["role"] and mapped <= raw_set:
                containing[kind] += 1
                if mapped == raw_set:
                    exact[kind] += 1
    state = ("measurement_not_comparable" if gaps else "exact_solver_raw_retained" if exact["base_solver"] else
             "extended_solver_raw_requires_association_proof" if containing["base_solver"] else
             "ledger_only_requires_qualification_proof" if any(kind != "tracking" for kind in containing) else
             "unrepresented_registered_interpretation")
    return {"before_observation_id": binding["observation_id"], "role": binding["role"],
            "before_role_authorized": binding["role_authorized"], "before_raw_count": len(raw_ids),
            "before_peak_provenance_unavailable_count": unavailable_peak_provenance,
            "state": state, "measurement_gaps": gaps,
            "exact_raw_representations": dict(sorted(exact.items())),
            "containing_raw_representations": dict(sorted(containing.items()))}


def compare_reports(before: dict, after: dict, *, source_sha256: str) -> dict:
    """Audit raw accounting only, after validating both complete current reports."""
    for record in (before, after):
        validate_current_report_record(record)
        if record["detail_level"] != "development":
            raise ValueError("Cross retention requires development report detail")
    if any(before[key] != after[key] for key in ("configuration", "input")):
        raise ValueError("Cross retention requires identical input and measurement contracts")
    if any(before["measurement"][key] != after["measurement"][key] for key in ("source_extent", "layout")):
        raise ValueError("Cross retention source geometry changed")
    if before["development"]["measurement"]["source_lanes"] != after["development"]["measurement"]["source_lanes"]:
        raise ValueError("Cross retention source lane or scale authority changed")
    before_lanes = {lane["lane_id"]: lane for lane in before["development"]["lanes"]}
    after_lanes = {lane["lane_id"]: lane for lane in after["development"]["lanes"]}
    if before_lanes.keys() != after_lanes.keys():
        raise ValueError("Cross retention lane universe changed")
    comparisons = []
    for identity, lane in before_lanes.items():
        old, new = _snapshot(before, lane, source_sha256), _snapshot(after, after_lanes[identity], source_sha256)
        comparisons.extend({"lane_id": identity, **_compare_binding(binding, old, new)} for binding in old["bindings"])
    counts = Counter(item["state"] for item in comparisons)
    gaps = len(comparisons) - counts["exact_solver_raw_retained"]
    return {"audit_schema": AUDIT_SCHEMA, "scope": "base_canonical_two_region_cross_bindings",
            "source_sha256": source_sha256, "physical_refutation_authority": False,
            "gate_authority": False, "candidate_universe_completeness_proved": False,
            "before_membership_states": {key: (None if lane["base_cross_registration"]["membership_receipt"] is None else
                lane["base_cross_registration"]["membership_receipt"]["state"]) for key, lane in before_lanes.items()},
            "after_membership_states": {key: (None if lane["base_cross_registration"]["membership_receipt"] is None else
                lane["base_cross_registration"]["membership_receipt"]["state"]) for key, lane in after_lanes.items()},
            "before_decision": before["decision"]["status"],
            "after_decision": after["decision"]["status"], "binding_count": len(comparisons),
            "state_counts": dict(sorted(counts.items())), "requires_review_count": gaps,
            "automatic_promotion_requires_retention_review": bool(gaps and
                before["decision"]["status"] != "approved_auto" and after["decision"]["status"] == "approved_auto"),
            "comparisons": comparisons}


def _read_bound_report(path: Path, task: dict, source: Path) -> dict:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(records) != 1:
        raise ValueError("Cross retention requires one source record per report")
    record = records[0]
    stat = source.stat()
    identity = record["runtime_identity"]["source"]
    if (Path(record["source"]).resolve() != source or identity["size"] != stat.st_size
            or identity["mtime_ns"] != stat.st_mtime_ns
            or record["configuration"]["format_id"] != task["format_id"]
            or record["configuration"]["slot_count_request"]["user_count"] != task["count"]):
        raise ValueError("Cross retention report does not match the current source task")
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--before-report", required=True, type=Path)
    parser.add_argument("--after-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        tasks = [json.loads(line) for line in DEVELOPMENT_GOLD_COHORT_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
        matches = [task for task in tasks if task["sample_id"] == args.sample_id]
        if len(matches) != 1:
            raise ValueError("Cross retention requires one current gold source task")
        task = matches[0]
        source = (PROJECT_ROOT / task["source_relative_path"]).resolve()
        if not source.is_relative_to(PROJECT_ROOT) or sha256_file(source) != task["source_sha256"]:
            raise ValueError("Cross retention gold source SHA changed")
        if args.output.exists() or args.output.resolve() in {
            source, args.before_report.resolve(), args.after_report.resolve(),
        }:
            raise ValueError("Cross retention output must be a new artifact")
        before, after = (_read_bound_report(path, task, source) for path in (args.before_report, args.after_report))
        result = compare_reports(before, after, source_sha256=task["source_sha256"])
        result["sample_id"] = args.sample_id
        result["report_sha256"] = {"before": sha256_file(args.before_report), "after": sha256_file(args.after_report)}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(f"Cross retention: INVALID: {error}", file=sys.stderr)
        return 2
    print(f"Cross retention: {result['binding_count']} bindings, {result['requires_review_count']} require review")
    return int(result["requires_review_count"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
