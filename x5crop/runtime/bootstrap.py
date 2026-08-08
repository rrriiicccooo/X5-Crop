from __future__ import annotations

from ..formats import format_spec
from ..configuration.bundle import DetectionConfigurationBundle
from ..configuration.model import FrameCountRequest
from ..output.naming import portable_source_stems
from ..run_config import RunConfig
from .app import run_runtime
from .input_probe import iter_input_files
from .identity import runtime_environment_identity
from .invocation import PlannedSource, RuntimeInvocation
from .limits import STANDARD_JOB_LIMIT
from .options import RuntimeOptions


def runtime_invocation_from_options(options: RuntimeOptions) -> RuntimeInvocation:
    files = iter_input_files(options.input_path)
    if not files:
        raise ValueError(f"No TIFF files found: {options.input_path}")
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
    layout = options.layout
    portable_stems = portable_source_stems(tuple(path.name for path in files))
    config = RunConfig(
        input_path=options.input_path,
        output_dir=options.output_dir,
        format_id=options.format_id,
        layout_auto=layout_auto,
        layout=layout,
        strip_mode=options.strip_mode,
        count_request=count_request,
        debug_analysis=options.debug_analysis,
        allow_best_effort_output=options.allow_best_effort_output,
        jobs=max(1, min(STANDARD_JOB_LIMIT, int(options.jobs))),
        interactive=options.interactive,
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
        configuration_bundle=configuration_bundle,
    )


def run_options(options: RuntimeOptions) -> int:
    invocation = runtime_invocation_from_options(options)
    runtime_environment_identity()
    return run_runtime(invocation)
