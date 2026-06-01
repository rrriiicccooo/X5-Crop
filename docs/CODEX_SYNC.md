# Codex Sync Guide

This project is expected to be edited and tested from more than one computer and more than one Codex session.

Use this file as the shared operating agreement.

## Shared Source of Truth

GitHub is the source of truth for code, docs, packaging scripts, and release workflow changes.

Local machines may also contain:

- large TIFF test scans
- generated debug images
- downloaded GitHub Actions artifacts
- local virtual environments
- packaged app outputs

Those local files are useful, but they are not automatically part of the shared project state.

## Before Starting on Any Computer

Run:

```bash
git status --short
git branch --show-current
git fetch origin
```

Then compare with the remote branch you intend to work on:

```bash
git log --oneline --decorate --max-count=8 --all
```

If there are local uncommitted changes, inspect them before pulling. Do not overwrite another machine's work.

## Recommended Work Loop

1. Pull or fetch the latest remote state.
2. Read the newest handoff note in this file or in the chat.
3. Make a focused change.
4. Run the smallest useful verification.
5. Commit only intentional files.
6. Push the branch.
7. Leave a handoff note.

Useful commands:

```bash
git status --short
git diff --stat
git diff
git add README.md docs AGENTS.md
git commit -m "Document Codex collaboration workflow"
git push origin HEAD
```

Adjust the `git add` paths to match the actual files changed.

## Branch Strategy

Use `main` for stable shared state.

Use short-lived branches for active work:

```text
codex/<topic>
```

If work already exists on a branch such as `integrate-web-app`, continue there until it is merged or intentionally replaced.

Do not force-push unless both computers have confirmed that no local work will be lost.

## What To Commit

Commit:

- Python source in `x5crop/`
- packaging files in `packaging/`
- build scripts in `tools/`
- GitHub Actions workflows in `.github/workflows/`
- docs in `README.md`, `AGENTS.md`, and `docs/`
- preserved original script files:
  - `X5_Split_v17.py`
  - `README_X5_Split_v17.md`

Usually do not commit:

- `.DS_Store`
- `__pycache__/`
- `.venv/`
- `.venv-build/`
- `build/`
- `dist/`
- `release/`
- `downloaded_apps/`
- generated `split_output/` folders
- generated debug JPGs
- large TIFF samples in `Test/`

Large TIFF samples should only be committed after an explicit decision to make them official fixtures and after Git LFS tracking is configured.

## Git LFS

Git LFS is installed and globally enabled on the primary macOS machine.

Recommended tracking if official TIFF fixtures are later added:

```bash
git lfs track "*.tif"
git lfs track "*.tiff"
git add .gitattributes
```

Do not add all local test TIFFs by accident.

## GitHub CLI And SSH

The preferred GitHub transport is SSH.

Check:

```bash
ssh -T git@github.com
gh auth status
git remote -v
```

Expected remote shape:

```text
git@github.com:rrriiicccooo/X5-Crop.git
```

If `gh auth status` fails on a new computer, run:

```bash
gh auth login --hostname github.com --git-protocol ssh --web
```

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

Date: 2026-06-01
Computer: primary macOS machine
Branch: integrate-web-app

Changed:
- Added collaboration and setup docs for multi-computer Codex work.

Verified:
- Homebrew Git and Git LFS are installed and active on the primary macOS machine.
- GitHub CLI is authenticated as `rrriiicccooo` with SSH protocol.

Known local-only files:
- `Test/`
- `downloaded_apps/`
- `__pycache__/`
- `.DS_Store`

Next recommended step:
- Commit and push these docs so the second computer can pull the same workflow notes.

