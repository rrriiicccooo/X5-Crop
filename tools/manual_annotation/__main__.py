"""Command-line entry point for the local golden-baseline annotator."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import webbrowser

from x5crop.runtime.threading import configure_numeric_threads


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m tools.manual_annotation",
        description=(
            "Prepare and review source-SHA-bound crop geometry in a loopback-only "
            "single-image annotator. Machine proposals never become gold without "
            "explicit confirmation."
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=(
            "start",
            "prepare",
            "serve",
            "audit",
            "reconcile-context",
            "refine",
        ),
        default="start",
        help="start prepares missing proposals and opens the annotator (default)",
    )
    parser.add_argument(
        "--sample-id",
        action="append",
        dest="sample_ids",
        help="limit preparation to one sample identity; repeat as needed",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="loopback port; 0 selects an available port",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="print the local URL without opening the default browser",
    )
    parser.add_argument(
        "--force-machine",
        action="store_true",
        help="replace only existing untouched machine proposals; never replaces human work",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="evaluate refinement without changing annotation records",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=_repository_root(),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        help=argparse.SUPPRESS,
    )
    return parser


def _progress(
    index: int,
    total: int,
    members: list[dict[str, object]],
    state: str,
) -> None:
    identities = "/".join(str(row["sample_id"]) for row in members)
    print(f"[{index:03d}/{total:03d}] {identities}: {state}", flush=True)


def _refinement_progress(
    index: int,
    total: int,
    members: list[dict[str, object]],
    result: dict[str, object],
) -> None:
    identities = "/".join(str(row["sample_id"]) for row in members)
    print(
        f"[{index:03d}/{total:03d}] {identities}: {result['status']} · "
        f"moved={result['moved_line_count']} · retained={result['retained_line_count']}",
        flush=True,
    )


def _prepare(workspace: object, arguments: argparse.Namespace) -> None:
    counts = workspace.prepare(
        identities=arguments.sample_ids,
        force_machine=arguments.force_machine,
        progress=_progress,
    )
    print(
        "Prepared {prepared}; existing {existing}; recovered red drafts "
        "{red_drafts}.".format(**counts),
        flush=True,
    )


def _serve(workspace: object, arguments: argparse.Namespace) -> None:
    from .server import create_server

    index = workspace.index()
    missing = int(index["states"].get("not_prepared", 0))
    if missing:
        raise RuntimeError(
            f"{missing} source annotations are not prepared; run the prepare command first"
        )
    server = create_server(workspace, port=arguments.port)
    host, port = server.server_address
    url = f"http://{host}:{port}/?token={server.token}"
    print("X5 Crop local annotator", flush=True)
    print(url, flush=True)
    print("Press Control-C to stop. Source TIFFs remain read-only.", flush=True)
    if not arguments.no_open:
        webbrowser.open(url, new=1, autoraise=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    configure_numeric_threads()
    arguments = _parser().parse_args(argv)
    try:
        from .workspace import ReviewWorkspace

        workspace = ReviewWorkspace(
            arguments.repository_root,
            state_root=arguments.state_root,
        )
        if arguments.command in {"start", "prepare"}:
            _prepare(workspace, arguments)
        if arguments.command in {"start", "serve"}:
            _serve(workspace, arguments)
        if arguments.command == "audit":
            summary = workspace.index()
            print(
                f"{summary['total_unique_sources']} unique sources · "
                + " · ".join(
                    f"{key}={value}" for key, value in summary["states"].items()
                )
            )
        if arguments.command == "reconcile-context":
            counts = workspace.reconcile_review_context(
                identities=arguments.sample_ids,
            )
            print(
                "Reconciled {changed_lines} line bases and {changed_slots} slot kinds across "
                "{changed_sources} sources.".format(**counts)
            )
        if arguments.command == "refine":
            counts = workspace.refine(
                identities=arguments.sample_ids,
                dry_run=arguments.dry_run,
                progress=_refinement_progress,
            )
            print(
                "Refinement {mode}: {refined_sources}/{sources} evaluated; "
                "moved {moved_lines} lines; retained {retained_lines}; "
                "existing {unchanged_existing}; human-modified skipped "
                "{skipped_modified_after_refinement}; confirmed skipped "
                "{skipped_confirmed}.".format(
                    mode="dry run" if counts["dry_run"] else "applied",
                    **counts,
                ),
                flush=True,
            )
        return 0
    except (RuntimeError, ValueError, OSError) as error:
        print(f"manual annotation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
