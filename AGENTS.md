# Codex Agent Rules

This is the coordination file for this repository. Keep it short and binding:
standing rules, document roles, release rules, verification priorities, and the
latest handoff. Do not use this file for changelog entries or architecture
detail.

## First Moves

1. Read `README.md` and this handoff before editing.
2. Check branch and dirty state:

```bash
git branch --show-current
git status --short
```

3. Treat GitHub as authoritative for source and docs. NAS or local copied folders
   are only transport/testing surfaces.

Repository:

```text
git@github.com:rrriiicccooo/X5-Crop.git
https://github.com/rrriiicccooo/X5-Crop
```

## Document Roles

- `快速启动_Quick_Start.md`: Release quick-start guide.
- `README.md`: complete user manual for setup, launchers, Debug Analysis,
  outputs, review folders, and common command-line use.
- `ARCHITECTURE.md`: runtime-flow architecture and source-layer architecture.
- `CHANGELOG.md`: version summaries, behavior changes, validation notes, and
  rollback context.
- `AGENTS.md`: Codex coordination rules and current handoff only.

Do not duplicate long content across these documents. Link to the right document
instead.

Documentation quality bar is extreme cleanliness and elegance. Every document
change must leave the docs professional, concise, structurally clear, current,
and non-overlapping. Treat this as a standing acceptance criterion; do not wait
for the user to restate it.

## Current Scope

- Active entry point: `X5_Crop.py`.
- Active script version: V4.9.
- Current stable GitHub Release: `v4.2.8`.
- V4+ development source lives under `x5crop/`; Release builds may package a
  standalone `X5_Crop.py`.
- Keep active work focused on the standalone X5 Crop workflow unless the user
  explicitly resumes app/native packaging.
- There is no `docs/` mirror. Root `ARCHITECTURE.md` is the single architecture
  document.

## Coding Rules

- Preserve TIFF quality and metadata behavior unless the user explicitly asks
  otherwise. Cropped TIFF output must keep bit depth, channel structure,
  ICC/color space, resolution, metadata, and known lossless compression behavior.
- Structural cleanup does not preserve historical output parity. PASS/REVIEW,
  crop geometry, confidence, reasons, report/debug schema, and cache reuse may
  all change when the new structure is cleaner and more truthful.
- After structural closure, detection thresholds and behavior are calibrated
  from real samples. Do not broadly loosen PASS/REVIEW rules to fix one file.
- For detection changes, verify known-good formats before calling the change
  safe, especially `135`.
- Use `--deskew off` for fast detector regressions unless the task is about
  export or deskew behavior.
- Directional requests use horizontal-strip wording as baseline. Add rotated
  vertical-strip behavior when implementing.
- Update user docs when usage, setup, output folders, launcher behavior, or
  release packaging changes.
- Update `ARCHITECTURE.md` when runtime flow or source layering changes.
- Update `CHANGELOG.md` when behavior, release packaging, validation scope, or
  rollback context changes.

## Extreme Cleanliness Contract

Extreme cleanliness is a closed, testable architecture contract. It means there
are no known violations of the rules below; it does not mean that no alternative
implementation could ever be imagined.

Definition of extreme cleanliness and elegance:

- Every active concept has one canonical name, type, owner, and source of truth.
- Data and dependencies flow one way. Proposal, guidance, build, evidence,
  assessment, selection, decision, finalization, output, report, and debug do not
  borrow authority from one another.
- `CandidateGate` and `DecisionGate` are the only gates. Only `DecisionGate`
  creates final PASS/REVIEW status and `final_review_reasons`.
- Format names identify physical specs; they do not own algorithm branches.
  Physical facts, sample-tuned parameters, runtime policy, and report descriptions
  remain separate concepts.
- Policy and format resolution happen at the runtime boundary. Lower layers
  receive explicit specs, subpolicies, or plain parameter objects and never query
  registries or invent defaults.
- Foundation modules know only geometry, pixels, TIFF I/O, cache mechanics, and
  units. They do not know format/mode identity, decision state, or report schema.
- Report, debug, cache reuse, tests, and tools consume the current schema only and
  never reconstruct missing decisions or preserve superseded field shapes.
- Keep no compatibility of any kind with superseded source, APIs, schemas,
  fields, names, aliases, import paths, reducers, shims, branches, or test
  expectations. Migrate every active caller and delete the old surface in the
  same change.
- Keep no dead files, unreachable helpers, pass-through wrappers, duplicate data
  models, hidden constants that affect crop/decision/output, or abstractions that
  merely relocate complexity.
- Prefer the smallest coherent model: delete rather than alias, pass an existing
  typed object rather than translate it twice, and add an abstraction only when
  it removes real duplication or responsibility ambiguity.
- Names must state the physical fact or lifecycle responsibility they represent;
  comments and documents must not compensate for misleading code names.
- Code, contract tests, `ARCHITECTURE.md`, and current report/debug output must
  describe the same system without duplicated or stale explanations.

Enforcement and closure:

- When any new residue is found, first add a contract test that fails on that
  exact class of violation, then fix the code. Keep the test permanently so the
  same residue cannot return.
- Architecture audits use this frozen contract. Do not invent a new aesthetic
  standard midway through the same closure audit.
- Architecture cleanup is complete only after the full verification suite passes
  and two consecutive read-only audits using the same checklist find zero known
  violations.
- After closure, reopen architecture only for a demonstrated contract violation,
  a new capability that cannot fit the current ownership model, or a physical fact
  the current model cannot express. A sample-specific crop or threshold issue goes
  to calibration, not another project-wide architecture rewrite.

## Performance And Detection Work

- Profile one fixed real sample before optimizing. Record total and detection time,
  candidate builds, repeated measurements, and the actual call-stack hotspot.
- Separate necessary one-time measurement, repeated pure measurement, and avoidable
  candidate expansion. Optimize the latter two without moving decision authority.
- Add a failing contract test for every newly found residue before fixing its root
  cause; search and remove the whole class of residue in the same change.
- Early-stop only from explicit physical resolution or typed execution-budget
  reliability. Keep physical resolution separate from CandidateGate and DecisionGate.
- Cache only exact, count/offset-independent measurements with typed keys. Never
  cache candidates, gates, decisions, final reasons, or approximate geometry.
- Re-profile the same sample after each optimization wave, then run full contracts,
  representative format/mode smokes, current-schema validation, and visual Debug
  Analysis inspection. Treat output diffs as later calibration material.

## Completion And Sync

- When the user asks Codex to change repository source, docs, config, launchers,
  or release metadata, finish by verifying, committing, and pushing to GitHub
  unless the user explicitly says not to.
- Do not require the user to restate "push" or "sync" in later sessions.
- Treat this as standing authorization for verified pushes to the current branch;
  do not ask for a separate chat confirmation before `git push`. Use the platform
  approval flow directly if it is required.
- Before committing, run the relevant checks and confirm `git status --short`
  contains only intentional changes.
- Push the current branch to `origin` after a successful commit.
- If commit or push cannot complete, report the blocker clearly and leave the
  working tree in the safest possible state.

## Git And Local Files

- Commit only intentional source/docs/config changes.
- Check `git status --short` before and after edits.
- Other Codex sessions may have changed files. Do not revert user or
  other-session changes unless explicitly asked.
- Keep `.gitignore` visible. If `.github/` appears, keep it visible too.
- Intended sparse checkout:

```text
/*
!/archive/
!/install/
!/release/
!/LICENSE
```

- Keep `tools/` available locally; it contains regression and build utilities
  used by active verification. Keep `LICENSE`, `archive/`, `install/`, and
  `release/` cloud/GitHub only locally unless the user asks to expand them.
- Do not commit generated/local files:
  - `.venv/`, `.venv-build/`, `build/`, `dist/`, `release/`
  - `__pycache__/`, `.DS_Store`, `downloaded_apps/`
  - `Test/`
  - generated `x5_crop_output/`
  - large TIFF samples unless explicitly made official fixtures with Git LFS

## Release Package Rules

User Release zip should contain only:

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.txt
快速启动_Quick_Start.txt
install/X5_Crop_Mac_install.command
install/X5_Crop_win_install.bat
install/X5_Crop_Mac_uninstall.command
install/X5_Crop_win_uninstall.bat
```

Do not package `x5crop/`, `archive/`, `CHANGELOG.md`, `AGENTS.md`, `LICENSE`,
`.github/`, diagnostics launchers, Test files, or generated outputs unless the
user changes this policy.

Use Python `zipfile` for release zips so Chinese filenames are stored with
UTF-8 metadata.

macOS installer behavior:

- `chmod +x` the main macOS launcher and installer.
- Remove `com.apple.quarantine` from the current Release folder when `xattr` is
  available.
- This is per-folder preparation, not permanent global trust registration.

## Regression Priorities

When detection changes are made, use
`python3 -m tools.regression.compare <baseline> <candidate>` to locate changes
between current-schema reports. Diffs are audit material, not parity blockers.

Common fields to inspect:

```text
status
confidence
final_review_reasons
visible_sequence_span
crop_envelope
output_geometry.frame_boxes
separator_observations
frame_boundaries
inter_frame_spacing
sequence_conservation
```

Local `Test/` fixtures are untracked and their directory layout is not a source
contract. Discover available TIFFs at verification time:

```bash
find Test -type f \( -iname '*.tif' -o -iname '*.tiff' \) | sort
```

When present, cover representative `135/full`, `120-66/partial`, `half/full`,
and `120-67/full` inputs. Treat additional sets as audit material.

For source or policy changes, also run:

```bash
python3 -m unittest discover -s tools/tests
python3 -m compileall -q X5_Crop.py x5crop
python3 -m x5crop.policies.consistency
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

Also compile `tools/regression/*.py`.

For docs-only changes, `git diff --check` and a final status review are enough
unless the edit changes commands or release behavior.

## Current Handoff

Date: 2026-07-11
Computer: primary macOS machine
Branch: main
Latest documentation state: root documents have distinct responsibilities.
`ARCHITECTURE.md` now keeps only runtime-flow architecture and source-layer
architecture; no `docs/` mirror is kept.

Current state:

- Active script is `X5_Crop.py` V4.9.
- Detection follows the typed frame-sequence flow documented in
  `ARCHITECTURE.md`: boundary/separator observations -> count and sequence
  hypotheses -> candidate geometry/evidence -> CandidateGate ->
  GeometryResolution -> selection -> OutputBleedPlan -> DecisionGate.
- `HolderSpan`, `VisibleSequenceSpan`, and `CropEnvelope` are distinct canonical
  identities. Signed inter-frame spacing represents separator, contact, or
  overlap under one sequence-conservation model.
- Raw separator bands are count-independent. Only physically assigned,
  cross-axis-continuous observations become hard separator evidence;
  dimension-constrained boundaries remain geometry-dependent.
- `GeometryResolution` is the only execution early-stop input. CandidateGate
  and confidence do not own execution budget.
- Report serialization, validation, and current-schema restoration all belong
  to `x5crop.report`; debug rendering does not touch detection measurement cache.
- Runtime flow and source-layer structure live in `ARCHITECTURE.md`.
- Version history and validation summaries live in `CHANGELOG.md`.
- User setup and usage live in `README.md` and `快速启动_Quick_Start.md`.

Recent verified baseline:

- The previous closure candidate is superseded by the physical detection model
  refactor. Architecture is not closed; the fixed two-audit closure plan must
  restart from the resulting commit.
- The architecture suite covers 157 active modules and 513 acyclic internal
  import edges; all active modules are reachable and uniquely layered.
- 212 contract and behavior tests pass. Full package and regression compile,
  policy consistency, launcher syntax, version, and whitespace checks pass.
- `135/full`, `135/partial auto`, `135/partial -n 3`, `120-66/partial auto`,
  `half/full`, and `120-67/full|partial` real samples produced valid
  `frame_sequence_geometry` reports. Horizontal and vertical Debug Analysis
  images were visually confirmed as three-panel output.
- `X5_00034 partial auto` evaluated counts from 5 down and selected count 5;
  explicit count 3 exercised the independent fixed-count path.
- The 120-66 sample selected nominal count 3 but kept
  `complete_underfilled_strip=False` because frame coverage was contradicted;
  holder occupancy did not suppress content-preservation evidence.
- Synthetic off-center `135-dual/full` produced measured gutter hypotheses away
  from the canvas center and twelve frames through the common lane pipeline.
- Current-schema cache reuse completed the same review/export actions as a fresh
  result. Exported TIFFs retained uint16 RGB data, ICC profile, 2000 dpi
  resolution metadata, and source `NONE` compression. A native two-worker
  ProcessPool completed without fallback.
- Current representative samples are REVIEW after the structural rewrite. This
  does not block architecture work; proof thresholds and sample calibration are a
  separate project.
- The largest representative partial-auto smoke built 73 candidates. Optimize
  this later through GeometryResolution-aware candidate planning and exact
  measurement reuse, never through CandidateGate, DecisionGate, or confidence
  shortcuts.
