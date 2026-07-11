from __future__ import annotations

from .....domain import Box
from .....policies.runtime.outer import ContentContainmentCorrectionPolicy
from .....utils import clamp_int
from ....geometry import CandidateGeometry
from ....evidence.outer_alignment import OuterAlignmentEvidence
from ...spans import CropEnvelope
from .constraints import correction_axes_allowed
from .types import SequenceAdjustmentHypothesis


def content_containment_correction_proposal(
    geometry: CandidateGeometry,
    alignment: OuterAlignmentEvidence,
    canvas_width: int,
    canvas_height: int,
    policy: ContentContainmentCorrectionPolicy,
) -> SequenceAdjustmentHypothesis | None:
    family = policy.family
    content = alignment.content_span
    original = geometry.crop_envelope.box
    if (
        family.mode == "off"
        or content is None
        or not content.valid()
        or not alignment.confirmed_undercrop
    ):
        return None
    parameters = policy.parameters
    pitch = float(original.width) / float(max(1, geometry.count))
    long_margin = clamp_int(
        pitch * parameters.long_margin_ratio,
        parameters.long_margin_cap_min,
        parameters.long_margin_cap_max,
    )
    short_margin = clamp_int(
        float(original.height) * parameters.short_margin_ratio,
        parameters.short_margin_cap_min,
        parameters.short_margin_cap_max,
    )
    corrected = Box(
        max(0, min(original.left, content.left - long_margin)),
        max(0, min(original.top, content.top - short_margin)),
        min(canvas_width, max(original.right, content.right + long_margin)),
        min(canvas_height, max(original.bottom, content.bottom + short_margin)),
    )
    if not corrected.valid() or corrected == original:
        return None
    if corrected.width < original.width or corrected.height < original.height:
        raise AssertionError("content containment correction must only expand")
    long_expansion = float(corrected.width - original.width) / max(
        1.0,
        float(original.width),
    )
    short_expansion = float(corrected.height - original.height) / max(
        1.0,
        float(original.height),
    )
    if family.max_expand_ratio > 0.0 and max(
        long_expansion,
        short_expansion,
    ) > family.max_expand_ratio:
        return None
    if not correction_axes_allowed(family, original, corrected):
        return None
    return SequenceAdjustmentHypothesis(
        visible_sequence_span=geometry.visible_sequence_span,
        crop_envelope=CropEnvelope(corrected),
        family="content_containment",
        reason=alignment.reason,
    )
