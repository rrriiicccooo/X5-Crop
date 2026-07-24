#!/bin/sh
set -eu

repository_root=$(git rev-parse --show-toplevel)
git -C "$repository_root" config core.hooksPath .githooks
printf 'Enabled X5 Crop Git hooks from %s/.githooks\n' "$repository_root"
