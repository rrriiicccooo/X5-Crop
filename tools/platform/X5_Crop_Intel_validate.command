#!/bin/bash
set -euo pipefail

package_dir=$(cd "$(dirname "$0")" && pwd)
expected_file="$package_dir/X5_Crop_Intel_expected_commit.txt"
repository="$package_dir/X5-Crop"

if [ "$(uname -m)" != "x86_64" ]; then
  printf >&2 'This validation command requires an Intel Mac (x86_64).\n'
  exit 2
fi
if [ ! -f "$expected_file" ] || [ ! -d "$repository/.git" ]; then
  printf >&2 'Clone X5-Crop-V5.bundle as X5-Crop beside this command first.\n'
  exit 2
fi

expected_commit=$(tr -d '[:space:]' <"$expected_file")
cd "$repository"
if [ -n "$(git status --porcelain)" ]; then
  printf >&2 'Intel validation requires a clean worktree.\n'
  exit 2
fi
if [ "$(git rev-parse HEAD)" != "$expected_commit" ]; then
  printf >&2 'Intel validation checkout does not match the packaged commit.\n'
  exit 2
fi

exec bash tools/verify platform --expected-commit "$expected_commit"
