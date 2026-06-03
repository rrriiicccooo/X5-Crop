# Codex Working Notes

These instructions are for Codex agents working on this repository from any
machine.

## First Moves

1. Read `README.md` and `docs/CODEX_SYNC.md`.
2. Check the current branch and dirty state:

```bash
git branch --show-current
git status --short
```

3. Do not delete or revert untracked user files such as `Test/`,
   `downloaded_apps/`, local build outputs, or generated scan results.
4. Keep `X5_Split_v17.py` and `README_X5_Split_v17.md` in the repository. They
   are the preserved original v17 reference.
5. This working folder may be synchronized by NAS in both directions. Treat
   GitHub as authoritative for source/docs, and NAS as a local-file transport
   layer.

## Current Direction

The desktop app and native packaging branch is paused for now.

Keep the repository focused on the standalone Python scripts:

```text
X5_Split_v17.py
X5_Split_v18.py
```

Do not reintroduce app packaging, PySide6 GUI, Qt native UI, PyInstaller,
GitHub Actions release workflows, or generated app artifacts unless the user
explicitly resumes that direction.

## Coding Rules

- Preserve TIFF metadata behavior unless the user explicitly asks to change it.
- Keep detection changes close to the script logic.
- Avoid broad refactors while solving a narrow detection or workflow task.
- Add or update docs when script usage, setup, or testing behavior changes.

## Git Rules

- Commit only intentional source/docs/config changes.
- If the working tree is NAS-synced, check `git status --short` before and
  after edits because another computer may have synchronized changes into the
  folder.
- Do not run two Codex sessions against the same NAS-synced working tree at the
  same time unless they are only reading.
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
- Do not commit large TIFF samples unless the user explicitly decides they are
  official fixtures and Git LFS tracking is configured for them.

## Handoff Rule

When stopping work, update or create a short handoff note using the template in
`docs/CODEX_SYNC.md`.
