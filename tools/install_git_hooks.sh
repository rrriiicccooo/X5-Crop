#!/bin/sh
set -eu

root=$(git rev-parse --show-toplevel)
git -C "$root" config core.hooksPath .githooks
printf 'Enabled X5 Crop Git hooks from %s/.githooks\n' "$root"
