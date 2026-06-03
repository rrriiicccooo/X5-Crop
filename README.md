# X5 Crop Script Workspace

This repository is currently kept as a clean script workspace for splitting
Hasselblad/Imacon X5 style long TIFF film scans into individual frames.

The desktop app and native packaging branch is paused for now. App-specific
source, packaging files, build workflows, and generated app outputs should stay
out of this working tree unless that direction is resumed later.

## Files To Keep

The original v17 script is preserved as the reference implementation:

```text
X5_Split_v17.py
README_X5_Split_v17.md
```

The current standalone script workflow is:

```text
X5_Split_v18.py
README_X5_Split_v18.md
README_X5_Split_v18_DoubleClick.md
X5_Split_v18_macOS_DoubleClick.command
X5_Split_v18_macOS_Debug_DoubleClick.command
X5_Split_v18_macOS_DebugAnalysis_DoubleClick.command
X5_Split_v18_Windows_DoubleClick.bat
X5_Split_v18_Windows_Debug_DoubleClick.bat
X5_Split_v18_Windows_DebugAnalysis_DoubleClick.bat
```

## Local Files

Local TIFF samples and output folders are useful for testing, but they are not
committed by default:

```text
Test/
downloaded_apps/
split_output/
__pycache__/
```

Large TIFF fixtures should only be added after an explicit decision and Git LFS
tracking is configured.

## Coordination

This folder may be synchronized by NAS between computers. Use GitHub as the
source of truth for source files and documentation, and treat NAS as a local
file transport layer.

Before editing from another Codex session or computer:

```bash
git status --short
git branch --show-current
git fetch origin
```

See `AGENTS.md` for Codex rules, sync notes, and the current handoff.
