from __future__ import annotations

from pathlib import Path

from ..configuration.model import DetectionConfiguration
from ..configuration.registry import get_detection_configuration
from ..configuration.model import SlotCountRequest
from ..output.naming import portable_source_stems
from ..run_config import RunConfig
from .app import run_runtime
from .input_probe import iter_input_files
from .invocation import PlannedSource, RuntimeInvocation
from .limits import STANDARD_JOB_LIMIT
from .options import RuntimeOptions
from ..detection.evidence.scan_canvas import (
    matched_holder_from_evidence,
    observe_scan_canvas,
)
from ..geometry.layout import infer_layout, is_horizontal_layout
from ..io.tiff import read_tiff_profile
from ..utils import spatial_shape_from_shape


class SlotCountPreflightError(ValueError):
    pass


def _preflight_batch_count(
    files: list[Path],
    options: RuntimeOptions,
    configuration: DetectionConfiguration,
) -> None:
    if options.requested_count is None:
        return
    conflicts: list[str] = []
    for path in files:
        try:
            profile, _warnings = read_tiff_profile(path)
        except Exception:
            # Input-domain failures remain per-source runtime errors.  This
            # preflight owns only matched-holder count authority.
            continue
        height, width = spatial_shape_from_shape(profile.shape)
        layout = (
            infer_layout(width, height)
            if options.layout == "auto"
            else options.layout
        )
        work_width, work_height = (
            (width, height) if is_horizontal_layout(layout) else (height, width)
        )
        evidence = observe_scan_canvas(
            work_width,
            work_height,
            layout,
            configuration.scan_canvas,
        )
        holder = matched_holder_from_evidence(
            evidence,
            configuration.physical_spec,
        )
        if holder is not None and options.requested_count > holder.full_count:
            conflicts.append(
                f"{path.name}: count {options.requested_count} must be "
                f"no greater than {holder.full_count} for "
                f"{holder.profile.profile_id}"
            )
    if conflicts:
        raise SlotCountPreflightError(
            "matched-holder count preflight failed:\n"
            + "\n".join(conflicts)
        )


def runtime_invocation_from_options(options: RuntimeOptions) -> RuntimeInvocation:
    files = iter_input_files(options.input_path)
    if not files:
        raise ValueError(f"No TIFF files found: {options.input_path}")
    count_request = SlotCountRequest(options.requested_count)
    configuration = get_detection_configuration(
        options.format_id,
        options.requested_count,
    )
    _preflight_batch_count(files, options, configuration)

    layout_auto = options.layout == "auto"
    layout = options.layout
    portable_stems = portable_source_stems(tuple(path.name for path in files))
    config = RunConfig(
        input_path=options.input_path,
        output_dir=options.output_dir,
        format_id=options.format_id,
        layout_auto=layout_auto,
        layout=layout,
        count_request=count_request,
        debug_analysis=options.debug_analysis,
        jobs=max(1, min(STANDARD_JOB_LIMIT, int(options.jobs))),
        deskew_mode=options.deskew_mode,
        interactive=options.interactive,
        development_detail=(
            options.debug_analysis or options.development_detail
        ),
    )
    return RuntimeInvocation(
        config=config,
        sources=tuple(
            PlannedSource(ordinal, path.resolve(), stem.value)
            for ordinal, (path, stem) in enumerate(
                zip(files, portable_stems, strict=True),
                1,
            )
        ),
        configuration=configuration,
    )


def run_options(options: RuntimeOptions) -> int:
    invocation = runtime_invocation_from_options(options)
    return run_runtime(invocation)
