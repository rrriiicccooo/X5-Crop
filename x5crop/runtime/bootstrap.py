from __future__ import annotations

from ..geometry.layout import infer_layout
from ..strip_modes import FULL, PARTIAL
from ..configuration.bundle import DetectionConfigurationBundle
from ..run_config import RunConfig
from .app import print_run_header, run_runtime
from .input_probe import iter_input_files
from ..io.tiff import read_tiff_page_shape
from .invocation import RuntimeInvocation
from .limits import DIAGNOSTICS_JOB_LIMIT, STANDARD_JOB_LIMIT
from .options import RuntimeOptions


def runtime_invocation_from_options(options: RuntimeOptions) -> RuntimeInvocation:
    files = iter_input_files(options.input_path)
    first_file = next(iter(files), None)
    if first_file is None:
        raise ValueError(f"No TIFF files found: {options.input_path}")

    height, width = read_tiff_page_shape(first_file, options.page)
    configuration_bundle = DetectionConfigurationBundle.for_format_mode(
        options.format_id,
        options.strip_mode,
    )
    fmt = configuration_bundle.initial_configuration.physical_spec
    if options.requested_count is not None:
        if options.strip_mode == FULL:
            if options.requested_count != fmt.strip.default_count:
                raise ValueError(
                    f"--format {fmt.format_id} full mode requires --count "
                    f"{fmt.strip.default_count}"
                )
        elif options.strip_mode == PARTIAL:
            if options.requested_count not in fmt.strip.allowed_partial_counts:
                allowed = ", ".join(
                    str(count) for count in fmt.strip.allowed_partial_counts
                )
                raise ValueError(
                    f"--format {fmt.format_id} partial mode allows --count "
                    f"values: {allowed}"
                )

    layout_auto = options.layout == "auto"
    layout = infer_layout(width, height) if layout_auto else options.layout
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
        review_dir=options.review_dir,
        copy_review_files=options.copy_review_files,
        compression=options.compression,
        debug=options.debug,
        debug_analysis=options.debug_analysis,
        diagnostics=options.diagnostics,
        overwrite=options.overwrite,
        report=options.report,
        debug_errors=options.debug_errors,
        jobs=max(1, min(jobs_cap, int(options.jobs))),
    )
    return RuntimeInvocation(
        config=config,
        files=tuple(files),
        configuration_bundle=configuration_bundle,
    )


def run_options(options: RuntimeOptions) -> int:
    invocation = runtime_invocation_from_options(options)
    print_run_header(invocation)
    return run_runtime(invocation)
