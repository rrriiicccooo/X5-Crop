from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Optional

import numpy as np

from ....domain import Box, OuterCandidate
from ....formats import FormatPhysicalSpec
from ....cache.separator import cached_separator_profile, cached_separator_width_profile
from ....geometry.separator_band import SeparatorBand
from ....geometry.separator_width_profile import collect_separator_width_bands
from ....policies.runtime.outer import (
    SeparatorGeometryProposalPolicy,
    SeparatorOuterFamilyPolicy,
)
from ....policies.parameters.outer import SeparatorOuterBandParameters
from ....policies.runtime.separator import SeparatorPolicy
from ....cache import AnalysisCache
from ...cache_keys import separator_outer_cache_key
from ..photo_size import PhotoSizeConsistency, photo_size_consistency_from_separator_bands
from .common import unique_outer_candidates
from .separator_bands import collect_separator_outer_bands, separator_outer_band_sequences


LOCAL_SEPARATOR_OUTER = "local"
FULL_WIDTH_SEPARATOR_OUTER = "full_width"

_SeparatorSequenceRanker = Callable[
    [PhotoSizeConsistency, float, float, float, float],
    float,
]


@dataclass(frozen=True)
class SeparatorOuterPlan:
    outer_scope: str
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
    uses_width_aware_bands: bool = False


@dataclass(frozen=True)
class SeparatorOuterSequenceRank:
    rank: float
    sequence: tuple[SeparatorBand, ...]
    expected_ratio: float
    photo_size_detail: dict
    sequence_score: float


def separator_outer_scopes(
    separator_geometry_policy: SeparatorGeometryProposalPolicy,
    strip_mode: str = "full",
    explicit_count: bool = True,
) -> tuple[str, ...]:
    scopes: list[str] = []
    if _mode_active(separator_geometry_policy.local, strip_mode, explicit_count):
        scopes.append(LOCAL_SEPARATOR_OUTER)
    if _mode_active(separator_geometry_policy.full_width, strip_mode, explicit_count):
        scopes.append(FULL_WIDTH_SEPARATOR_OUTER)
    return tuple(scopes)


def separator_derived_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache],
    *,
    separator_geometry_policy: SeparatorGeometryProposalPolicy,
    separator_policy: SeparatorPolicy,
    outer_scopes: tuple[str, ...] | None = None,
    explicit_count: bool = True,
    sequence_ranker: _SeparatorSequenceRanker,
) -> list[OuterCandidate]:
    if strip_mode not in {"full", "partial"} or count <= 1:
        return []
    aspect = float(fmt.horizontal_content_aspect)
    if aspect <= 0.0 or not base_candidates:
        return []

    selected_scopes = outer_scopes or separator_outer_scopes(
        separator_geometry_policy,
        strip_mode,
        explicit_count,
    )
    candidates: list[OuterCandidate] = []
    for outer_scope in selected_scopes:
        plan = _scope_plan(
            outer_scope,
            separator_geometry_policy,
            separator_policy,
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
                separator_geometry_policy,
                separator_policy,
                sequence_ranker,
            )
        )
    return unique_outer_candidates(candidates)


def _candidate_prefix(outer_scope: str) -> str | None:
    if outer_scope == LOCAL_SEPARATOR_OUTER:
        return "separator_local"
    if outer_scope == FULL_WIDTH_SEPARATOR_OUTER:
        return "separator_full_width"
    return None


def _width_profile_bands_available(
    separator_policy: SeparatorPolicy,
) -> bool:
    return separator_policy.width_profile.mode != "off"


def _scope_plan(
    outer_scope: str,
    separator_geometry_policy: SeparatorGeometryProposalPolicy,
    separator_policy: SeparatorPolicy,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    explicit_count: bool,
) -> SeparatorOuterPlan | None:
    band_policy = separator_geometry_policy.band
    width_policy = separator_policy.width_profile
    uses_width_aware_bands = _width_profile_bands_available(
        separator_policy,
    )
    if outer_scope == LOCAL_SEPARATOR_OUTER:
        family = separator_geometry_policy.local
        if not family.available_for(strip_mode, explicit_count):
            return None
        if strip_mode == "full" and count != fmt.default_count:
            return None
        candidate_prefix = _candidate_prefix(outer_scope)
        if candidate_prefix is None:
            return None
        return SeparatorOuterPlan(
            outer_scope=LOCAL_SEPARATOR_OUTER,
            name=LOCAL_SEPARATOR_OUTER,
            candidate_prefix=candidate_prefix,
            full_width=False,
            margin_ratios=(0.0,),
            source_candidate_count=max(1, int(band_policy.source_candidate_count)),
            band_candidate_count=max(1, int(max(band_policy.band_candidate_count, width_policy.parameters.band_candidate_count))),
            sequence_candidate_count=max(1, int(max(band_policy.pair_candidate_count, width_policy.parameters.sequence_candidate_count))),
            max_candidates=max(1, int(family.max_candidates or max(band_policy.max_candidates, width_policy.parameters.max_candidates))),
            spacing_min_ratio=float(band_policy.spacing_min_ratio),
            spacing_max_ratio=float(band_policy.spacing_max_ratio),
            frame_error_max=float(band_policy.frame_error_max),
            sequence_score_weight=float(band_policy.sequence_pair_score_weight),
            uses_width_aware_bands=uses_width_aware_bands,
        )
    if outer_scope == FULL_WIDTH_SEPARATOR_OUTER:
        family = separator_geometry_policy.full_width
        geometry_policy = separator_geometry_policy.full_width_outer
        if not family.available_for(strip_mode, explicit_count):
            return None
        candidate_prefix = _candidate_prefix(outer_scope)
        if candidate_prefix is None:
            return None
        return SeparatorOuterPlan(
            outer_scope=FULL_WIDTH_SEPARATOR_OUTER,
            name=FULL_WIDTH_SEPARATOR_OUTER,
            candidate_prefix=candidate_prefix,
            full_width=True,
            margin_ratios=tuple(float(value) for value in geometry_policy.margin_ratios),
            source_candidate_count=max(1, int(geometry_policy.source_candidate_count)),
            band_candidate_count=max(1, int(max(band_policy.band_candidate_count, width_policy.parameters.band_candidate_count))),
            sequence_candidate_count=max(1, int(max(geometry_policy.max_candidates, width_policy.parameters.sequence_candidate_count))),
            max_candidates=max(1, int(family.max_candidates or max(geometry_policy.max_candidates, width_policy.parameters.max_candidates))),
            spacing_min_ratio=float(band_policy.spacing_min_ratio),
            spacing_max_ratio=float(band_policy.spacing_max_ratio),
            frame_error_max=float(band_policy.frame_error_max),
            sequence_score_weight=float(band_policy.sequence_pair_score_weight),
            uses_width_aware_bands=uses_width_aware_bands,
        )
    return None


def _mode_active(
    family: SeparatorOuterFamilyPolicy,
    strip_mode: str,
    explicit_count: bool,
) -> bool:
    if not family.available_for(strip_mode, explicit_count):
        return False
    return family.phase == "primary" and family.mode in {"always", "conditional"}


def _separator_outer_candidates_for_plan(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    aspect: float,
    plan: SeparatorOuterPlan,
    cache: Optional[AnalysisCache],
    separator_geometry_policy: SeparatorGeometryProposalPolicy,
    separator_policy: SeparatorPolicy,
    sequence_ranker: _SeparatorSequenceRanker,
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
    band_policy = separator_geometry_policy.band

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

        profile = cached_separator_profile(cache, gray_work, outer, separator_policy.profile)
        band_collection = collect_separator_outer_bands(
            profile,
            short_axis,
            float(outer.width),
            band_policy,
            separator_policy.gap_search,
        )
        bands = list(band_collection.bands)
        edge_margin = band_collection.edge_margin
        if plan.uses_width_aware_bands:
            width_profile = cached_separator_width_profile(
                cache,
                gray_work,
                outer,
                separator_policy.width_profile_search,
            )
            width_band_collection = collect_separator_width_bands(
                width_profile,
                short_axis,
                float(outer.width),
                separator_policy.width_profile_search,
            )
            bands.extend(width_band_collection.bands)
            edge_margin = max(float(edge_margin), float(width_band_collection.edge_margin))

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
            sequence_ranker,
        )
        for rank, ranked_sequence in enumerate(
            ranked_sequences[: plan.sequence_candidate_count],
            start=1,
        ):
            sequence = ranked_sequence.sequence
            expected_ratio = ranked_sequence.expected_ratio
            first_band = sequence[0]
            last_band = sequence[-1]
            separator_total = sum(float(band.width) for band in sequence)
            margin = max(
                0.0,
                (expected_ratio - (float(count) * aspect + separator_total / max(1.0, short_axis)))
                * short_axis
                * 0.5,
            )
            proposed_left = int(round(float(outer.left) + float(first_band.start) - frame_long - margin))
            proposed_right = int(round(float(outer.left) + float(last_band.end) + frame_long + margin))
            if proposed_right <= proposed_left:
                continue
            left_loss = max(0, -proposed_left)
            right_loss = max(0, proposed_right - w)
            if left_loss > edge_margin or right_loss > edge_margin:
                continue
            proposed = Box(proposed_left, outer.top, proposed_right, outer.bottom).clamp(w, h)
            if not proposed.valid():
                continue
            ratio_suffix = f"_r{expected_ratio:.3f}"
            candidates.append(
                OuterCandidate(
                    f"{plan.candidate_prefix}_{source.name}_{rank}{ratio_suffix}",
                    proposed,
                    "separator_outer",
                    {
                        "family": "separator_derived_outer",
                        "outer_scope": plan.outer_scope,
                        "separator_gap_search": "standard_and_observed_width",
                        "source_outer": source.name,
                        "photo_size_consistency": ranked_sequence.photo_size_detail,
                        "separator_sequence_score": float(ranked_sequence.sequence_score),
                        "separator_bands": [
                            {
                                "start": float(band.start),
                                "end": float(band.end),
                                "center": float(band.center),
                                "width": float(band.width),
                                "score": float(band.score),
                            }
                            for band in sequence
                        ],
                    },
                )
            )

    result = unique_outer_candidates(candidates)[: plan.max_candidates]
    if cache is not None:
        cache.separator_outer_candidates[candidate_key] = list(result)
    return result


def _rank_separator_sequences(
    bands: list[SeparatorBand],
    expected_gaps: int,
    frame_long: float,
    short_axis: float,
    count: float,
    aspect: float,
    band_policy: SeparatorOuterBandParameters,
    plan: SeparatorOuterPlan,
    sequence_ranker: _SeparatorSequenceRanker,
) -> list[SeparatorOuterSequenceRank]:
    candidate_bands = sorted(
        bands,
        key=lambda band: (-float(band.score), float(band.center)),
    )[: max(expected_gaps, plan.band_candidate_count)]
    ranked: list[SeparatorOuterSequenceRank] = []
    sequence_policy = _sequence_band_policy(band_policy, plan)
    for sequence in separator_outer_band_sequences(candidate_bands, expected_gaps, frame_long, sequence_policy):
        previous: Optional[SeparatorBand] = None
        valid = True
        for band in sequence:
            if previous is not None:
                inner_width = float(band.start) - float(previous.end)
                if inner_width <= 0:
                    valid = False
                    break
            previous = band
        if not valid:
            continue
        photo_size = photo_size_consistency_from_separator_bands(
            sequence,
            target_photo_width=frame_long,
        )
        max_frame_error = photo_size.max_photo_width_error_ratio
        if (
            plan.frame_error_max is not None
            and max_frame_error is not None
            and max_frame_error > plan.frame_error_max
        ):
            continue

        separator_total = sum(float(band.width) for band in sequence)
        expected_ratio_base = count * aspect + separator_total / max(1.0, short_axis)
        sequence_score = sum(float(band.score) for band in sequence) / max(1, len(sequence))
        for margin_ratio in plan.margin_ratios:
            expected_ratio = expected_ratio_base + 2.0 * float(margin_ratio)
            first_band = sequence[0]
            last_band = sequence[-1]
            margin = float(margin_ratio) * short_axis
            proposed_width = float(last_band.end) + frame_long + margin - (
                float(first_band.start) - frame_long - margin
            )
            actual_ratio = proposed_width / max(1.0, short_axis)
            rank = sequence_ranker(
                photo_size,
                abs(actual_ratio - expected_ratio),
                sequence_score,
                plan.sequence_score_weight,
                band_policy.photo_width_cv_rank_weight,
            )
            ranked.append(
                SeparatorOuterSequenceRank(
                    rank=float(rank),
                    sequence=sequence,
                    expected_ratio=float(expected_ratio),
                    photo_size_detail=photo_size.detail(),
                    sequence_score=float(sequence_score),
                )
            )
    return sorted(ranked, key=lambda item: item.rank)


def _sequence_band_policy(
    band_policy: SeparatorOuterBandParameters,
    plan: SeparatorOuterPlan,
) -> SeparatorOuterBandParameters:
    return replace(
        band_policy,
        spacing_min_ratio=plan.spacing_min_ratio,
        spacing_max_ratio=plan.spacing_max_ratio,
        frame_error_max=plan.frame_error_max if plan.frame_error_max is not None else band_policy.frame_error_max,
        band_candidate_count=plan.band_candidate_count,
        pair_candidate_count=plan.sequence_candidate_count,
        max_candidates=plan.max_candidates,
    )
