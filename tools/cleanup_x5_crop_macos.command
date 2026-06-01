#!/bin/zsh
# X5 Crop residual cleanup for macOS
# Run after removing X5 Crop.app. This removes app-generated configuration,
# cache, logs, temporary files, saved state, and optional project cache.

set -u

echo "X5 Crop residual cleanup"
echo "This removes X5 Crop app data/cache/logs. It does NOT delete split_output TIFF files."
printf "Continue? Type YES to proceed: "
read answer
if [[ "$answer" != "YES" ]]; then
  echo "Canceled."
  exit 0
fi

paths=(
  "$HOME/Library/Application Support/X5 Crop"
  "$HOME/Library/Caches/X5 Crop"
  "$HOME/Library/Logs/X5 Crop"
  "$HOME/Library/Preferences/com.x5crop.X5-Crop.plist"
  "$HOME/Library/Saved Application State/com.x5crop.X5-Crop.savedState"
  "$TMPDIR/X5 Crop"
)

for p in "${paths[@]}"; do
  if [[ -e "$p" ]]; then
    echo "Removing $p"
    rm -rf "$p"
  fi
done

echo ""
echo "Optional project cache cleanup:"
echo "X5 Crop may create .x5crop folders inside project folders if project caching is enabled."
printf "Enter a project folder to remove its .x5crop cache, or press Enter to skip: "
read project
if [[ -n "$project" ]]; then
  cache="$project/.x5crop"
  if [[ -e "$cache" ]]; then
    echo "Removing $cache"
    rm -rf "$cache"
  else
    echo "No .x5crop folder found at $cache"
  fi
fi

echo "Cleanup complete."
