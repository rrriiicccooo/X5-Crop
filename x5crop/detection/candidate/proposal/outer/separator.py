from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .....domain import Box, OuterCandidate
from .....formats import CONTENT_ASPECTS_HORIZONTAL, FormatSpec
from .....geometry.separator_cache import cached_separator_profile
from .....policies.registry import get_detection_policy
from .....policies.runtime.outer import SeparatorOuterBandPolicy, SeparatorOuterFamilyPolicy
from .....policies.runtime.policy import DetectionPolicy
from .....policies.runtime.separator import SeparatorWidthProfilePolicy
from .....cache import AnalysisCache
from .....utils import clamp_float, clamp_int, runs_from_mask, sampled_percentile, smooth_1d
from ....cache_keys import separator_outer_cache_key
from ....gap_profiles import BROAD_WIDTH_GAP_PROFILE, STANDARD_GAP_PROFILE, is_broad_width_gap_profile
from ..separator.bands import collect_separator_outer_bands, separator_outer_band_sequences
from .common import unique_outer_candidates


LOCAL_SEPARATOR_OUTER = "local"
FULL_WIDTH_SEPARATOR_OUTER = "full_width"


@dataclass(frozen=True)
class SeparatorOuterPlan:
    outer_scope: str
    gap_search_profile: str
    name: str
    candidate_prefix: str
    full_width: bool
    margin_ratios: tuple[float, ...]
    source_candidate_count: int
    band_candidate_count: int
    sequence_candidate_count: int
    max_candidates: int
    spacing_min_ratio: float
    spacing_max_ratio: float
    frame_error_max: float | None
    sequence_score_weight: float
    uses_broad_width_profile: bool = False


def separator_outer_scopes_for_policy(
    policy: DetectionPolicy,
    strip_mode: str = "full",
    explicit_count: bool = True,
    safety_only: bool = False,
) -> tuple[str, ...]:
    separator_policy = policy.outer.proposal.geometry.separator
    scopes: list[str] = []
    if _mode_active(separator_policy.local, strip_mode, explicit_count, safety_only):
        scopes.append(LOCAL_SEPARATOR_OUTER)
    if _mode_active(separator_policy.full_width, strip_mode, explicit_count, safety_only):
        scopes.append(FULL_WIDTH_SEPARATOR_OUTER)
    return tuple(scopes)


def separator_derived_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
    outer_scopes: tuple[str, ...] | None = None,
    gap_search_profiles: tuple[str, ...] | None = None,
    explicit_count: bool = True,
) -> list[OuterCandidate]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    if strip_mode not in {"full", "partial"} or count <= 1:
        return []
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0 or not base_candidates:
        return []

    selected_scopes = outer_scopes or separator_outer_scopes_for_policy(policy, strip_mode, explicit_count)
    selected_gap_profiles = gap_search_profiles or (STANDARD_GAP_PROFILE,)
    candidates: list[OuterCandidate] = []
    for outer_scope in selected_scopes:
        for gap_search_profile in selected_gap_profiles:
            plan = _scope_profile_plan(
                outer_scope,
                gap_search_profile,
                policy,
                fmt,
                count,
                strip_mode,
                explicit_count,
            )
            if plan is None:
                continue
            candidates.extend(
                _separator_outer_candidates_for_plan(
                    gray_work,
                    base_candidates,
                    fmt,
                    count,
                    strip_mode,
                    float(aspect),
                    plan,
                    cache,
                    policy,
                )
            )
    return unique_outer_candidates(candidates)


def _candidate_prefix(outer_scope: str, gap_search_profile: str) -> str | None:
    if outer_scope == LOCAL_SEPARATOR_OUTER:
        base = "separator_local"
    elif outer_scope == FULL_WIDTH_SEPARATOR_OUTER:
        base = "separator_full_width"
    else:
        return None
    if is_broad_width_gap_profile(gap_search_profile):
        return f"{base}_{BROAD_WIDTH_GAP_PROFILE}"
    if gap_search_profile == STANDARD_GAP_PROFILE:
        return base
    return None


def _broad_width_profile_available(
    policy: DetectionPolicy,
    count: int,
    strip_mode: str,
    explicit_count: bool,
) -> bool:
    separator_policy = policy.outer.proposal.geometry.separator
    family = separator_policy.width_profile_family
    width_policy = policy.separator.width_profile
    required_count = int(width_policy.required_count)
    return bool(
        family.available_for(strip_mode, explicit_count)
        and width_policy.mode != "off"
        and (required_count <= 0 or count == required_count)
    )


def _width_profile_plan(
    *,
    outer_scope: str,
    full_width: bool,
    policy: DetectionPolicy,
) -> SeparatorOuterPlan | None:
    separator_policy = policy.outer.proposal.geometry.separator
    family = separator_policy.width_profile_family
    width_policy = policy.separator.width_profile
    candidate_prefix = _candidate_prefix(outer_scope, BROAD_WIDTH_GAP_PROFILE)
    if candidate_prefix is None:
        return None
    return SeparatorOuterPlan(
        outer_scope=outer_scope,
        gap_search_profile=BROAD_WIDTH_GAP_PROFILE,
        name=f"{outer_scope}:{BROAD_WIDTH_GAP_PROFILE}",
        candidate_prefix=candidate_prefix,
        full_width=full_width,
        margin_ratios=(0.0,),
        source_candidate_count=max(1, int(width_policy.source_candidate_count)),
        band_candidate_count=max(1, int(width_policy.band_candidate_count)),
        sequence_candidate_count=max(1, int(width_policy.sequence_candidate_count)),
        max_candidates=max(1, int(family.max_candidates or width_policy.max_candidates)),
        spacing_min_ratio=float(width_policy.spacing_min_ratio),
        spacing_max_ratio=float(width_policy.spacing_max_ratio),
        frame_error_max=None,
        sequence_score_weight=float(width_policy.sequence_score_weight),
        uses_broad_width_profile=True,
    )


def _scope_profile_plan(
    outer_scope: str,
    gap_search_profile: str,
    policy: DetectionPolicy,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    explicit_count: bool,
) -> SeparatorOuterPlan | None:
    separator_policy = policy.outer.proposal.geometry.separator
    band_policy = separator_policy.band
    broad_width_profile = is_broad_width_gap_profile(gap_search_profile)
    if broad_width_profile and not _broad_width_profile_available(policy, count, strip_mode, explicit_count):
        return None
    if outer_scope == LOCAL_SEPARATOR_OUTER:
        family = separator_policy.local
        if not family.available_for(strip_mode, explicit_count):
            return None
        if strip_mode == "full" and count != fmt.default_count:
            return None
        if broad_width_profile:
            return _width_profile_plan(outer_scope=outer_scope, full_width=False, policy=policy)
        candidate_prefix = _candidate_prefix(outer_scope, STANDARD_GAP_PROFILE)
        if candidate_prefix is None:
            return None
        return SeparatorOuterPlan(
            outer_scope=LOCAL_SEPARATOR_OUTER,
            gap_search_profile=STANDARD_GAP_PROFILE,
            name=f"{LOCAL_SEPARATOR_OUTER}:{STANDARD_GAP_PROFILE}",
            candidate_prefix=candidate_prefix,
            full_width=False,
            margin_ratios=(0.0,),
            source_candidate_count=max(1, int(band_policy.source_candidate_count)),
            band_candidate_count=max(1, int(band_policy.band_candidate_count)),
            sequence_candidate_count=max(1, int(band_policy.pair_candidate_count)),
            max_candidates=max(1, int(family.max_candidates or band_policy.max_candidates)),
            spacing_min_ratio=float(band_policy.spacing_min_ratio),
            spacing_max_ratio=float(band_policy.spacing_max_ratio),
            frame_error_max=float(band_policy.frame_error_max),
            sequence_score_weight=0.02,
        )
    if outer_scope == FULL_WIDTH_SEPARATOR_OUTER:
        family = separator_policy.full_width
        geometry_policy = separator_policy.full_width_outer
        if not family.available_for(strip_mode, explicit_count):
            return None
        expected_count = int(geometry_policy.required_count)
        if expected_count > 0 and count != expected_count:
            return None
        if broad_width_profile:
            return _width_profile_plan(outer_scope=outer_scope, full_width=True, policy=policy)
        candidate_prefix = _candidate_prefix(outer_scope, STANDARD_GAP_PROFILE)
        if candidate_prefix is None:
            return None
        return SeparatorOuterPlan(
            outer_scope=FULL_WIDTH_SEPARATOR_OUTER,
            gap_search_profile=STANDARD_GAP_PROFILE,
            name=f"{FULL_WIDTH_SEPARATOR_OUTER}:{STANDARD_GAP_PROFILE}",
            candidate_prefix=candidate_prefix,
            full_width=True,
            margin_ratios=tuple(float(value) for value in geometry_policy.margin_ratios),
            source_candidate_count=max(1, int(geometry_policy.source_candidate_count)),
            band_candidate_count=max(1, int(band_policy.band_candidate_count)),
            sequence_candidate_count=max(1, int(geometry_policy.max_candidates)),
            max_candidates=max(1, int(family.max_candidates or geometry_policy.max_candidates)),
            spacing_min_ratio=float(band_policy.spacing_min_ratio),
            spacing_max_ratio=float(band_policy.spacing_max_ratio),
            frame_error_max=float(band_policy.frame_error_max),
            sequence_score_weight=0.02,
        )
    return None


def _mode_active(
    family: SeparatorOuterFamilyPolicy,
    strip_mode: str,
    explicit_count: bool,
    safety_only: bool,
) -> bool:
    if not family.available_for(strip_mode, explicit_count):
        return False
    if safety_only:
        return family.mode == "safety"
    return family.phase == "primary" and family.mode in {"always", "conditional"}


def _separator_outer_candidates_for_plan(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    aspect: float,
    plan: SeparatorOuterPlan,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> list[OuterCandidate]:
    if cache is not None:
        candidate_key = separator_outer_cache_key(plan.name, base_candidates, fmt, count, strip_mode)
        cached_candidates = cache.separator_outer_candidates.get(candidate_key)
        if cached_candidates is not None:
            return list(cached_candidates)

    h, w = gray_work.shape
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[: plan.source_candidate_count]
    candidates: list[OuterCandidate] = []
    expected_gaps = count - 1
    separator_policy = policy.outer.proposal.geometry.separator
    band_policy = separator_policy.band

    for source in source_candidates:
        source_box = source.box.clamp(w, h)
        if not source_box.valid() or source_box.height <= 0:
            continue
        outer = Box(0, source_box.top, w, source_box.bottom) if plan.full_width else source_box
        if not outer.valid() or outer.height <= 0 or outer.width <= 0:
            continue
        short_axis = float(outer.height)
        frame_long = short_axis * aspect
        if frame_long <= 1.0:
            continue

        if plan.uses_broad_width_profile:
            crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
            profile = _adaptive_separator_width_profile(crop, policy.separator.width_profile)
            bands, edge_margin = _collect_separator_width_profile_bands(
                profile,
                short_axis,
                float(outer.width),
                policy.separator.width_profile,
            )
        else:
            profile = cached_separator_profile(cache, gray_work, outer, fmt.name, policy.separator.profile)
            bands, edge_margin = collect_separator_outer_bands(
                profile,
                short_axis,
                float(outer.width),
                band_policy,
                policy.separator.gap_search,
                separator_policy,
            )

        if profile.size <= 0 or len(bands) < expected_gaps:
            continue
        ranked_sequences = _rank_separator_sequences(
            bands,
            expected_gaps,
            frame_long,
            short_axis,
            float(count),
            aspect,
            band_policy,
            plan,
        )
        for rank, (_sequence_rank, sequence, expected_ratio) in enumerate(
            ranked_sequences[: plan.sequence_candidate_count],
            start=1,
        ):
            first_band = sequence[0]
            last_band = sequence[-1]
            separator_total = sum(float(band["width"]) for band in sequence)
            margin = max(
                0.0,
                (expected_ratio - (float(count) * aspect + separator_total / max(1.0, short_axis)))
                * short_axis
                * 0.5,
            )
            proposed_left = int(round(float(outer.left) + float(first_band["start"]) - frame_long - margin))
            proposed_right = int(round(float(outer.left) + float(last_band["end"]) + frame_long + margin))
            if proposed_right <= proposed_left:
                continue
            left_loss = max(0, -proposed_left)
            right_loss = max(0, proposed_right - w)
            if left_loss > edge_margin or right_loss > edge_margin:
                continue
            proposed = Box(proposed_left, outer.top, proposed_right, outer.bottom).clamp(w, h)
            if not proposed.valid():
                continue
            ratio_suffix = f"_r{expected_ratio:.3f}" if not plan.uses_broad_width_profile else ""
            candidates.append(
                OuterCandidate(
                    f"{plan.candidate_prefix}_{source.name}_{rank}{ratio_suffix}",
                    proposed,
                    "separator_outer",
                )
            )

    result = unique_outer_candidates(candidates)[: plan.max_candidates]
    if cache is not None:
        cache.separator_outer_candidates[candidate_key] = list(result)
    return result


def _rank_separator_sequences(
    bands: list[dict[str, float]],
    expected_gaps: int,
    frame_long: float,
    short_axis: float,
    count: float,
    aspect: float,
    band_policy: SeparatorOuterBandPolicy,
    plan: SeparatorOuterPlan,
) -> list[tuple[float, tuple[dict[str, float], ...], float]]:
    candidate_bands = sorted(
        bands,
        key=lambda band: (-float(band["score"]), float(band["center"])),
    )[: max(expected_gaps, plan.band_candidate_count)]
    ranked: list[tuple[float, tuple[dict[str, float], ...], float]] = []
    sequence_policy = _sequence_band_policy(band_policy, plan)
    for sequence in separator_outer_band_sequences(candidate_bands, expected_gaps, frame_long, sequence_policy):
        frame_widths: list[float] = []
        previous: Optional[dict[str, float]] = None
        valid = True
        for band in sequence:
            if previous is not None:
                inner_width = float(band["start"]) - float(previous["end"])
                if inner_width <= 0:
                    valid = False
                    break
                frame_widths.append(inner_width)
            previous = band
        if not valid:
            continue
        if frame_widths:
            frame_errors = [abs(width - frame_long) / max(1.0, frame_long) for width in frame_widths]
            max_frame_error = max(frame_errors)
            mean_frame_error = float(sum(frame_errors) / len(frame_errors))
        else:
            max_frame_error = 0.0
            mean_frame_error = 0.0
        if plan.frame_error_max is not None and max_frame_error > plan.frame_error_max:
            continue

        separator_total = sum(float(band["width"]) for band in sequence)
        expected_ratio_base = count * aspect + separator_total / max(1.0, short_axis)
        sequence_score = sum(float(band["score"]) for band in sequence) / max(1, len(sequence))
        for margin_ratio in plan.margin_ratios:
            expected_ratio = expected_ratio_base + 2.0 * float(margin_ratio)
            rank = mean_frame_error - plan.sequence_score_weight * sequence_score
            if not plan.uses_broad_width_profile:
                first_band = sequence[0]
                last_band = sequence[-1]
                margin = float(margin_ratio) * short_axis
                proposed_width = float(last_band["end"]) + frame_long + margin - (
                    float(first_band["start"]) - frame_long - margin
                )
                actual_ratio = proposed_width / max(1.0, short_axis)
                rank += abs(actual_ratio - expected_ratio)
            ranked.append((rank, sequence, expected_ratio))
    return sorted(ranked, key=lambda item: item[0])


def _sequence_band_policy(
    band_policy: SeparatorOuterBandPolicy,
    plan: SeparatorOuterPlan,
) -> SeparatorOuterBandPolicy:
    return SeparatorOuterBandPolicy(
        min_score=band_policy.min_score,
        band_score=band_policy.band_score,
        min_width_ratio=band_policy.min_width_ratio,
        max_width_ratio=band_policy.max_width_ratio,
        spacing_min_ratio=plan.spacing_min_ratio,
        spacing_max_ratio=plan.spacing_max_ratio,
        frame_error_max=plan.frame_error_max if plan.frame_error_max is not None else 999.0,
        edge_margin_ratio=band_policy.edge_margin_ratio,
        source_candidate_count=band_policy.source_candidate_count,
        band_candidate_count=plan.band_candidate_count,
        pair_candidate_count=plan.sequence_candidate_count,
        max_candidates=plan.max_candidates,
    )


def _adaptive_separator_width_profile(
    crop: np.ndarray,
    width_policy: SeparatorWidthProfilePolicy,
) -> np.ndarray:
    if crop.size == 0:
        return np.array([], dtype=np.float32)
    sample = crop[:: max(1, crop.shape[0] // 500), :: max(1, crop.shape[1] // 2000)]
    p01, p99 = sampled_percentile(sample, [1, 99])
    span = max(1.0, float(p99 - p01))
    threshold = float(p01) + span * width_policy.threshold_span_ratio
    profile = (crop <= threshold).mean(axis=0).astype(np.float32)
    return smooth_1d(
        profile,
        max(
            width_policy.profile_smooth_min,
            int(round(crop.shape[0] * width_policy.profile_smooth_short_axis_ratio)),
        ),
    )


def _collect_separator_width_profile_bands(
    profile: np.ndarray,
    short_axis: float,
    coordinate_limit: float,
    width_policy: SeparatorWidthProfilePolicy,
) -> tuple[list[dict[str, float]], float]:
    if profile.size <= 0:
        return [], 0.0
    edge_margin = clamp_float(
        short_axis * width_policy.edge_margin_ratio,
        width_policy.edge_margin_min,
        max(width_policy.edge_margin_min, short_axis * width_policy.edge_margin_cap_ratio),
    )
    min_width = clamp_int(
        short_axis * width_policy.min_width_ratio,
        width_policy.min_width_min,
        width_policy.min_width_max,
    )
    max_width = clamp_int(
        short_axis * width_policy.max_width_ratio,
        min_width + 1,
        max(width_policy.max_width_floor, int(short_axis * width_policy.max_width_cap_ratio)),
    )
    bands: list[dict[str, float]] = []
    for run_start, run_end in runs_from_mask(profile >= width_policy.threshold_ratio):
        width = int(run_end - run_start)
        if width < min_width or width > max_width:
            continue
        center = (float(run_start) + float(run_end) - 1.0) * 0.5
        if center < edge_margin or center > coordinate_limit - edge_margin:
            continue
        bands.append(
            {
                "start": float(run_start),
                "end": float(run_end),
                "center": center,
                "width": float(width),
                "score": float(profile[run_start:run_end].mean()),
            }
        )
    return bands, edge_margin


__all__ = [
    "FULL_WIDTH_SEPARATOR_OUTER",
    "LOCAL_SEPARATOR_OUTER",
    "separator_derived_outer_candidates",
    "separator_outer_scopes_for_policy",
]
