# Codex Sync Guide

This repository may be edited and tested from more than one computer and more
than one Codex session.

## Source Of Truth

GitHub is the source of truth for scripts, launchers, and documentation.

Repository:

```text
git@github.com:rrriiicccooo/X5-Crop.git
https://github.com/rrriiicccooo/X5-Crop
```

NAS sync may move local files between computers, but it is not a replacement
for Git history.

## Current Scope

The app packaging branch is paused. Keep the working tree focused on the
standalone script workflow:

```text
X5_Split_v17.py
X5_Split_v18.py
```

Do not resume app packaging, native UI work, or release workflow changes unless
the user explicitly asks for that again.

## Before Editing

Run:

```bash
git status --short
git branch --show-current
git fetch origin
```

If there are local uncommitted changes or the branch is ahead/behind, inspect
before editing. Avoid simultaneous writes from two Codex sessions in the same
NAS-synced folder.

## Usually Do Not Commit

```text
.DS_Store
__pycache__/
.venv/
.venv-build/
build/
dist/
release/
downloaded_apps/
split_output/
Test/
```

Large TIFF samples should only be committed after an explicit decision and Git
LFS tracking is configured.

## Handoff Template

Use this at the end of a session:

```text
Date:
Computer:
Branch:
Last commit:

Changed:
- 

Verified:
- 

Not verified:
- 

Known local-only files:
- 

Next recommended step:
- 
```

## Current Handoff

Date: 2026-06-03
Computer: primary macOS machine
Branch: integrate-web-app
Last commit: a79907d Document v18 script in Chinese

Changed:
- Paused the app/native packaging direction.
- Kept v17 as the preserved reference script.
- Kept v18 as the current standalone script workflow.
- Cleaned project documentation so future Codex sessions do not continue the
  app branch by default.

Verified:
- Confirmed the local branch was one commit ahead of origin, and the ahead
  commit documents the v18 standalone script workflow.

Not verified:
- No image-processing tests were run during this cleanup.

Known local-only files:
- `Test/`

Next recommended step:
- Use the v18 script workflow for further detection improvements unless the app
  direction is explicitly resumed later.
