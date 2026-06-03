# Codex Sync Guide

This file is the cross-machine sync and handoff log. The standing rules for
Codex agents live in `AGENTS.md`; keep them there instead of duplicating them
here.

## Source Of Truth

GitHub is the source of truth for scripts, launchers, and documentation. NAS
sync may move local files between computers, but it is not a replacement for Git
history.

Repository:

```text
git@github.com:rrriiicccooo/X5-Crop.git
https://github.com/rrriiicccooo/X5-Crop
```

## Sync Protocol

Run:

```bash
git status --short
git branch --show-current
git fetch origin
```

If there are local uncommitted changes or the branch is ahead/behind, inspect
before editing. Avoid simultaneous writes from two Codex sessions in the same
NAS-synced folder. Follow `AGENTS.md` for commit exclusions and coding scope.

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
Last commit: e7131c0 Pause app branch and clean workspace

Changed:
- Reduced overlap between `AGENTS.md` and `docs/CODEX_SYNC.md`.
- Made `AGENTS.md` the short standing rulebook for Codex agents.
- Made `docs/CODEX_SYNC.md` the cross-machine sync protocol and handoff log.
- Kept the current scope in `AGENTS.md`: app/native packaging paused, v17/v18
  standalone script workflow active.

Verified:
- Read `AGENTS.md` and `docs/CODEX_SYNC.md` before editing.
- Confirmed the branch is `integrate-web-app` and the worktree was clean before
  this documentation cleanup.

Not verified:
- No image-processing tests were run because this change only reorganizes agent
  documentation.

Known local-only files:
- `Test/`

Next recommended step:
- Continue using `AGENTS.md` for rules and update this file only for sync state
  and handoff notes.
