from __future__ import annotations

from ..formats import format_spec
from ..geometry.layout import infer_layout
from ..configuration.bundle import DetectionConfigurationBundle
from ..configuration.model import FrameCountRequest
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
    fmt = format_spec(options.format_id)
    count_request = FrameCountRequest.from_user_input(
        fmt,
        options.strip_mode,
        options.requested_count,
    )
    configuration_bundle = DetectionConfigurationBundle.for_format_mode(
        options.format_id,
        options.strip_mode,
        options.requested_count,
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
        count_request=count_request,
        page=options.page,
        review_dir=options.review_dir,
        copy_review_files=options.copy_review_files,
        compression=options.compression,
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
