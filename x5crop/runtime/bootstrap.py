from __future__ import annotations

from ..geometry.layout import infer_layout
from ..output.protection import DEFAULT_OUTPUT_BLEED
from ..policies.runtime.bundle import DetectionPolicyBundle
from ..run_config import RunConfig
from .app import print_run_header, run_runtime
from .input_probe import first_tiff_shape, iter_input_files
from .invocation import RuntimeInvocation
from .limits import DIAGNOSTICS_JOB_LIMIT, STANDARD_JOB_LIMIT
from .options import RuntimeOptions


def runtime_invocation_from_options(options: RuntimeOptions) -> RuntimeInvocation:
    files = iter_input_files(options.input_path)
    first_file = next(iter(files), None)
    if first_file is None:
        raise ValueError(f"No TIFF files found: {options.input_path}")

    height, width = first_tiff_shape(first_file, options.page)
    policy_bundle = DetectionPolicyBundle.for_format_mode(
        options.format_id,
        options.strip_mode,
    )
    fmt = policy_bundle.initial_policy.physical_spec
    if options.requested_count is not None and options.requested_count not in fmt.allowed_counts:
        allowed = ", ".join(str(count) for count in fmt.allowed_counts)
        raise ValueError(
            f"--format {fmt.format_id} allows --count values: {allowed}"
        )

    layout_auto = options.layout == "auto"
    layout = infer_layout(width, height) if layout_auto else options.layout
    bleed_x_default = (
        DEFAULT_OUTPUT_BLEED.long_axis if options.bleed is None else int(options.bleed)
    )
    bleed_y_default = (
        DEFAULT_OUTPUT_BLEED.short_axis if options.bleed is None else int(options.bleed)
    )
    bleed_x = int(bleed_x_default if options.bleed_x is None else options.bleed_x)
    bleed_y = int(bleed_y_default if options.bleed_y is None else options.bleed_y)
    if bleed_x < 0 or bleed_y < 0:
        raise ValueError("Bleed cannot be negative")

    jobs_cap = DIAGNOSTICS_JOB_LIMIT if options.diagnostics else STANDARD_JOB_LIMIT
    config = RunConfig(
        input_path=options.input_path,
        output_dir=options.output_dir,
        format_id=options.format_id,
        layout_auto=layout_auto,
        layout=layout,
        strip_mode=options.strip_mode,
        requested_count=options.requested_count,
        page=options.page,
        bleed_x=bleed_x,
        bleed_y=bleed_y,
        deskew=options.deskew,
        deskew_fallback=options.deskew_fallback,
        deskew_min_angle=options.deskew_min_angle,
        deskew_max_angle=options.deskew_max_angle,
        review_dir=options.review_dir,
        copy_review_files=options.copy_review_files,
        export_review=options.export_review,
        compression=options.compression,
        debug=options.debug,
        debug_analysis=options.debug_analysis,
        dry_run=options.dry_run,
        diagnostics=options.diagnostics,
        overwrite=options.overwrite,
        report=options.report,
        debug_errors=options.debug_errors,
        reuse_analysis=options.reuse_analysis,
        jobs=max(1, min(jobs_cap, int(options.jobs))),
    )
    return RuntimeInvocation(
        config=config,
        files=tuple(files),
        policy_bundle=policy_bundle,
    )


def run_options(options: RuntimeOptions) -> int:
    invocation = runtime_invocation_from_options(options)
    print_run_header(invocation)
    return run_runtime(invocation)
