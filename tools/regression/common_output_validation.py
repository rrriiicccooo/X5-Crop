"""Validate serialized common H proofs without selecting or searching geometry."""

from __future__ import annotations

from dataclasses import fields
import math
from typing import Any

from x5crop.domain import Box, FiniteInterval, WorkspaceExtent
from x5crop.detection.gate_checks import (
    DetectionFailureFact, FailureRecovery, GateGap, MinimumMissingFact, RecoveryAction,
)
from x5crop.detection.photo_geometry.line_observations import SourceCoordinateLine
from x5crop.detection.photo_geometry.model import BoundaryAxis
from x5crop.detection.photo_geometry.output_model import (
    CommonOutputFootprint, CommonOutputMemberBudget, DirectUseBudgetAssessment,
    DirectUseBudgetEdgeAssessment, FootprintSaturationFact, FootprintSaturationKind,
    FrameBoundaryGeometry, JointPlacementEnvelope, OutputFootprint,
    footprint_outside_authority_sides, footprint_overflow_px,
    sampling_authority_bounds, source_boundary_sides,
)
from x5crop.detection.photo_geometry.template_common_output import CommonHOutput, CommonHOutputWork
from x5crop.detection.photo_geometry.template_placement import FormatPlacement, TemplateFrame
from x5crop.formats import OUTPUT_PROTECTION_SPEC
from x5crop.geometry.convex import clip_convex_polygon_to_bounds, convex_hull
from x5crop.report.read_models import typed_read_model


def _record(value: Any, cls: type) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {field.name for field in fields(cls)}:
        raise ValueError(f"common H {cls.__name__} fields are invalid")
    return value


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _budget(value, placement, native, common, projection) -> None:
    from x5crop.detection.photo_geometry.template_output import common_member_budget_assessment
    value = _record(value, CommonOutputMemberBudget)
    if value["placement_id"] != placement.placement_id or value["native_geometry_id"] != native.geometry_id:
        raise ValueError("common H member budget identity changed")
    expected = common_member_budget_assessment(placement, native,
        tuple(tuple(point) for point in common["requested_source_footprint"]),
        geometry_id=common["geometry_id"], projection=projection)
    if value["assessment"] != typed_read_model(expected):
        raise ValueError("common H member budget does not reproduce the common requested footprint")


def _output(value: Any, placements: list[dict], ordinal: int, extent: WorkspaceExtent, typed, projections) -> None:
    # Local import keeps report_validation free to call this helper.
    from .report_validation import validate_output_footprint_authority, _validate_polygon

    value = _record(value, CommonOutputFootprint)
    members = value["members"]
    budgets = value["member_budgets"]
    if (not isinstance(members, list) or len(members) != len(placements)
            or not isinstance(budgets, list) or len(budgets) != len(placements)
            or not _identity(value["geometry_id"])
            or not _identity(value["authority_profile_id"])):
        raise ValueError("common H output lost native members or their budgets")
    native_ids = set()
    for placement, member in zip(placements, members, strict=True):
        member = _record(member, OutputFootprint)
        envelope = _record(member["envelope"], JointPlacementEnvelope)
        validate_output_footprint_authority(member, expected_source_extent=extent)
        frame = placement["frames"][ordinal - 1]
        if (not _identity(member["geometry_id"]) or member["geometry_id"] in native_ids
                or member["geometry_id"] == value["geometry_id"]
                or envelope["placement_id"] != placement["placement_id"]
                or envelope["lane_id"] != placement["lane_id"]
                or type(envelope["lane_ordinal"]) is not int or envelope["lane_ordinal"] != ordinal
                or envelope["boundary_use"] != placements[0]["cross_fit"]["boundary_use"]
                or envelope["boundary_use"] != placement["cross_fit"]["boundary_use"]
                or envelope["canonical_source_footprint"] != typed_read_model(convex_hull(tuple(
                    tuple(point) for point in _validate_polygon(
                        frame["canonical_source_polygon"], "common H member frame"))))
                or any(member[key] != value[key] for key in (
                    "sampling_authority_box", "source_extent", "authority_profile_id"))):
            raise ValueError("common H native member identity, slot or source authority changed")
        native_ids.add(member["geometry_id"])
    for key in ("mandatory_source_footprint", "requested_source_footprint"):
        polygon = _validate_polygon(value[key], f"common H {key}")
        expected = convex_hull(tuple(tuple(point) for member in members for point in
            _validate_polygon(member[key], f"native {key}")))
        if typed_read_model(polygon) != typed_read_model(expected):
            raise ValueError("common H footprint does not cover the complete native union")
    requested = tuple(tuple(point) for point in value["requested_source_footprint"])
    mandatory = tuple(tuple(point) for point in value["mandatory_source_footprint"])
    authority = Box(**value["sampling_authority_box"])
    source_sides = source_boundary_sides(authority, extent)
    saturation = []
    for side in footprint_outside_authority_sides(requested, authority, extent):
        overflow = footprint_overflow_px(requested, authority, side, extent)
        mandatory_overflow = footprint_overflow_px(mandatory, authority, side, extent)
        if side in source_sides:
            kind = (FootprintSaturationKind.SOURCE_BOUNDARY_JOINT_PROTECTION if mandatory_overflow > 0
                    else FootprintSaturationKind.SOURCE_BOUNDARY_OPTIONAL_BLEED)
        else:
            kind = (FootprintSaturationKind.LANE_BOUNDARY_JOINT_PROTECTION if mandatory_overflow > 0
                    else FootprintSaturationKind.LANE_BOUNDARY_OPTIONAL_BLEED)
        saturation.append(FootprintSaturationFact(side, kind, overflow, mandatory_overflow))
    required = clip_convex_polygon_to_bounds(requested, sampling_authority_bounds(authority, extent)) if (
        saturation and all(fact.source_boundary for fact in saturation)) else requested
    if (value["saturation_facts"] != typed_read_model(saturation)
            or value["required_source_footprint"] != typed_read_model(required)):
        raise ValueError("common H source clipping or saturation changed")
    for index, budget in enumerate(budgets):
        _budget(budget, typed.placements[index], typed.output_footprints[ordinal - 1].members[index],
                value, projections[index] if projections else None)


def validate_common_h_output(
    value: Any, *, expected_source_extent: WorkspaceExtent,
    cross_competition: Any = None, cross_registration_work: Any = None, phase_best: Any = None,
) -> None:
    """Check the supplied proof and optional development links; grant no authority."""
    if value is None:
        return
    try:
        _validate_common_h_output(value, expected_source_extent, cross_competition,
                                  cross_registration_work, phase_best)
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError("common H output is malformed") from error


def _validate_common_h_output(value, extent, cross, registration, phase) -> None:
    value = _record(value, CommonHOutput)
    work = CommonHOutputWork(**_record(value["work"], CommonHOutputWork))
    placements = value["placements"]
    if not isinstance(extent, WorkspaceExtent) or not isinstance(placements, list) or len(placements) != work.member_count:
        raise ValueError("common H placements or source extent are invalid")
    for placement in placements:
        _record(placement, FormatPlacement)
    first = placements[0]
    count = first["output_slot_count"]
    identities = [placement["placement_id"] for placement in placements]
    if (type(count) is not int or count <= 0 or not _identity(value["placement_id"])
            or not _identity(first["lane_id"])
            or any(not _identity(identity) for identity in identities)
            or len(set(identities)) != len(identities) or value["placement_id"] in identities):
        raise ValueError("common H placement identities or slot count are invalid")
    fixed_fields = ("lane_id", "frame_spec", "output_slot_count", "sequence_fit", "source_scan_geometry",
                    "global_lattice_authority", "width_axis", "height_axis", "width_authority_px", "height_authority_px")
    for placement in placements:
        frames = placement["frames"]
        if (any(placement[key] != first[key] for key in fixed_fields)
                or not isinstance(frames, list) or len(frames) != count
                or any(type(_record(frame, TemplateFrame)["lane_ordinal"]) is not int
                       or frame["lane_ordinal"] != ordinal
                       for ordinal, frame in enumerate(frames, 1))):
            raise ValueError("common H requires fixed W, source identity and complete slots")
        if phase is not None and placement["sequence_fit"] != phase:
            raise ValueError("common H changed the retained phase fit")
    mapping = value["group_member_indices"]
    if (not isinstance(mapping, list) or len(mapping) != 2
            or any(not isinstance(view, list) for view in mapping)
            or any(type(i) is not int or not 0 <= i < len(placements) for view in mapping for i in view)
            or {i for view in mapping for i in view} != set(range(len(placements)))):
        raise ValueError("common H lost its complete group mapping")
    if cross is not None:
        if not isinstance(cross, dict):
            raise ValueError("common H Cross competition is invalid")
        if first["cross_fit"]["boundary_use"] == "enclosing_support_pair":
            from .report_validation import _read_common_proof, _read_membership_receipt
            from x5crop.detection.photo_geometry.template_cross_model import CrossFitCompetition
            from x5crop.detection.photo_geometry.template_common_output import common_h_fit_members
            from x5crop.detection.photo_geometry.template_registration import CrossRegistrationWorkReceipt
            if registration is None:
                raise ValueError("common H Cross proof requires its complete registration")
            typed_registration = CrossRegistrationWorkReceipt(**{
                **registration, "membership": _read_membership_receipt(registration["membership"])})
            expected = common_h_fit_members(_read_common_proof(cross, CrossFitCompetition), typed_registration)
            if expected is None or mapping != typed_read_model(expected[1]) or [p["cross_fit"] for p in placements] != typed_read_model(expected[0]):
                raise ValueError("common H changed or omitted a retained Cross group")
        else:
            fits, expected_mapping = [], []
            for key in ("fit_groups", "conditional_fit_groups"):
                groups = cross[key]
                if not isinstance(groups, list):
                    raise ValueError("common H Cross groups are invalid")
                indices = []
                for group in groups:
                    # Full fit equality is essential: unsupported groups are not filtered.
                    fit = group["fit"]
                    if not isinstance(fit, dict):
                        raise ValueError("common H Cross fit is invalid")
                    if fit not in fits:
                        fits.append(fit)
                    indices.append(fits.index(fit))
                expected_mapping.append(indices)
            if mapping != expected_mapping or [p["cross_fit"] for p in placements] != fits:
                raise ValueError("common H changed or omitted a retained Cross group")
    if registration is not None and (
        not isinstance(registration, dict)
        or type(registration.get("local_refinement_scope_count")) is not int
        or registration["local_refinement_scope_count"] != 0
        or not isinstance(registration.get("membership"), dict)
        or registration["membership"].get("state") != "complete"
    ):
        raise ValueError("common H registration has no complete unrefined membership")
    outputs = value["output_footprints"]
    if (not isinstance(outputs, list)
            or work.output_evaluation_count > work.projection_count * count
            or work.common_output_evaluation_count > count):
        raise ValueError("common H output work exceeds its member slots")
    if value["failure"] is not None:
        failure = _record(value["failure"], DetectionFailureFact)
        DetectionFailureFact(GateGap(failure["gap"]), FailureRecovery(failure["recovery"]),
            MinimumMissingFact(failure["minimum_missing_fact"]), RecoveryAction(failure["recommended_action"]),
            failure["detail"])
        if outputs:
            raise ValueError("failed common H output exposes a partial crop")
        return
    if (len(outputs) != count or work.common_output_evaluation_count != count
            or work.output_evaluation_count != work.projection_count * count
            or work.projection_count + work.reused_projection_count != len(placements)):
        raise ValueError("common H output does not cover every member and slot")
    from .report_validation import _read_common_proof
    from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
    typed = _read_common_proof(value, CommonHOutput)
    from x5crop.detection.photo_geometry.template_common_output import common_member_center_authority
    if any(p.enclosing_support_aperture_authority != common_member_center_authority(p.cross_fit)
           for p in typed.placements):
        raise ValueError("common H member center authority does not reproduce its physical support")
    projections = tuple(project_format_placement(p) for p in typed.placements) if (
        first["cross_fit"]["boundary_use"] == "enclosing_support_pair") else ()
    for ordinal, output in enumerate(outputs, 1):
        _output(output, placements, ordinal, extent, typed, projections)
