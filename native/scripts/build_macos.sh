#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")/../.."

ARCH="${X5CROP_ARCH:-$(uname -m)}"
BUILD_DIR="native/build-${ARCH}"

cmake -S native -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES="${ARCH}"
cmake --build "${BUILD_DIR}" --config Release

echo "Built ${BUILD_DIR}/X5 Crop.app"
