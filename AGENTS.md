# Codex Working Notes

These instructions are for Codex agents working on this repository from any machine.

## First Moves

1. Read `README.md`, `docs/CODEX_SYNC.md`, and `docs/PROJECT_CONTEXT.md`.
2. Check the current branch and dirty state:

```bash
git branch --show-current
git status --short
```

3. Do not delete or revert untracked user files such as `Test/`, `downloaded_apps/`, or local build outputs.
4. Keep `X5_Split_v17.py` and `README_X5_Split_v17.md` in the repository. They are the preserved original v17 reference.

## Project Intent

The target app is a professional film-scan crop review tool, not only a wrapper around one script.

The key direction is:

```text
easy scans: automatic
difficult scans: flagged for review
manual edits: fast and visible
export: based on approved crop plans
```

Important difficult cases:

- underexposed scans
- incomplete leaders or tails
- fewer than six frames
- unstable frame spacing
- overlapping frames
- weak or missing separators

## Coding Rules

- Prefer existing PySide6 and Python patterns in `x5crop/`.
- Keep detection logic in or near `x5crop/core/`.
- Keep GUI orchestration in `x5crop/app.py` and bridge code in `x5crop/core_bridge.py`.
- Preserve TIFF metadata behavior unless the user explicitly asks to change it.
- Avoid broad refactors while solving a narrow detection, UI, or packaging task.
- Add or update docs when workflow, setup, build, or test behavior changes.

## Git Rules

- Commit only intentional source/docs/config changes.
- Do not commit local generated folders:
  - `.venv/`
  - `.venv-build/`
  - `build/`
  - `dist/`
  - `release/`
  - `__pycache__/`
  - `.DS_Store`
  - `downloaded_apps/`
  - generated `split_output/` folders
- Do not commit large TIFF samples unless the user explicitly decides they are official fixtures and Git LFS tracking is configured for them.

## Handoff Rule

When stopping work, update or create a short handoff note using the template in `docs/CODEX_SYNC.md`.

