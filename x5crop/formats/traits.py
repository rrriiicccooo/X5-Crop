from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormatRuntimeTraits:
    separator_width_profile: str
    frame_fit_profile: str
    edge_pair_profile: str
    geometry_support_profile: str
    output_overlap_profile: str


def runtime_traits_for_format(
    *,
    family: str,
    default_count: int,
    aspect: float,
    physical_layout: str,
) -> FormatRuntimeTraits:
    if physical_layout == "dual_lane":
        return FormatRuntimeTraits(
            separator_width_profile="standard",
            frame_fit_profile="dual_lane",
            edge_pair_profile="standard_35mm",
            geometry_support_profile="none",
            output_overlap_profile="standard",
        )
    if family == "35mm" and default_count > 6 and aspect < 1.0:
        return FormatRuntimeTraits(
            separator_width_profile="standard",
            frame_fit_profile="dense_half",
            edge_pair_profile="dense_half",
            geometry_support_profile="stable_dense_grid",
            output_overlap_profile="sensitive",
        )
    if family == "35mm" and aspect > 2.0:
        return FormatRuntimeTraits(
            separator_width_profile="standard",
            frame_fit_profile="panoramic_35mm",
            edge_pair_profile="panoramic_35mm",
            geometry_support_profile="none",
            output_overlap_profile="standard",
        )
    if family == "120" and aspect < 1.0:
        return FormatRuntimeTraits(
            separator_width_profile="standard",
            frame_fit_profile="medium_rectangle",
            edge_pair_profile="medium_rectangle",
            geometry_support_profile="none",
            output_overlap_profile="sensitive",
        )
    if family == "120" and abs(aspect - 1.0) <= 0.05:
        return FormatRuntimeTraits(
            separator_width_profile="broad",
            frame_fit_profile="medium_square",
            edge_pair_profile="medium_square",
            geometry_support_profile="none",
            output_overlap_profile="sensitive",
        )
    if family == "120" and aspect > 1.0:
        return FormatRuntimeTraits(
            separator_width_profile="broad",
            frame_fit_profile="medium_wide",
            edge_pair_profile="medium_square",
            geometry_support_profile="none",
            output_overlap_profile="sensitive",
        )
    return FormatRuntimeTraits(
        separator_width_profile="standard",
        frame_fit_profile="standard_strip",
        edge_pair_profile="standard_35mm",
        geometry_support_profile="none",
        output_overlap_profile="standard",
    )


def runtime_traits_for_spec(spec) -> FormatRuntimeTraits:
    return runtime_traits_for_format(
        family=spec.family,
        default_count=spec.default_count,
        aspect=spec.horizontal_content_aspect,
        physical_layout=spec.physical_layout,
    )


__all__ = ["FormatRuntimeTraits", "runtime_traits_for_format", "runtime_traits_for_spec"]
