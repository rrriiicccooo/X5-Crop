#!/bin/sh
set -eu

case "${1:-}" in
  pre-commit)
    git diff --cached --check
    git diff --cached --name-only --diff-filter=ACMR | while IFS= read -r path; do
      case "/$path" in
        */.DS_Store|/.venv/*|/.venv-build/*|/build/*|/dist/*|/release/*|/downloaded_apps/*|/Test/*|/x5_crop_output/*)
          printf >&2 'Refusing generated or local file: %s\n' "$path"
          exit 1
          ;;
      esac
      case "$path" in
        *.[Tt][Ii][Ff]|*.[Tt][Ii][Ff][Ff])
          [ "$(git check-attr filter -- "$path")" = "$path: filter: lfs" ] || {
            printf >&2 'TIFF fixtures must be explicitly tracked by Git LFS: %s\n' "$path"
            exit 1
          }
          ;;
      esac
    done
    ;;
  pre-push)
    [ -z "$(git status --porcelain)" ] || {
      printf >&2 'Refusing push from a dirty worktree. Commit or stash intentional changes first.\n'
      exit 1
    }
    python3 -m unittest discover -s tools/tests
    python3 -m compileall -q X5_Crop.py x5crop tools/regression
    python3 -m x5crop.configuration.consistency
    bash -n X5_Crop_Mac.command
    bash -n X5_Crop_Mac_diagnostics.command
    git diff --check
    python3 X5_Crop.py --version
    ;;
  *)
    printf >&2 'usage: %s pre-commit|pre-push\n' "$0"
    exit 2
    ;;
esac
