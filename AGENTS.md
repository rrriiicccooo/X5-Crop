# Codex Agent Rules

This is the single Codex coordination file for this repository. Keep standing
rules, sync notes, and the current handoff here.

## First Moves

1. Read `README.md` and the current handoff at the bottom of this file.
2. Check the current branch and dirty state before editing:

```bash
git branch --show-current
git status --short
```

3. If the folder is NAS-synced or the branch is ahead/behind, inspect the
   situation before editing. GitHub is authoritative for source and docs; NAS is
   only a local-file transport layer.

Repository:

```text
git@github.com:rrriiicccooo/X5-Crop.git
https://github.com/rrriiicccooo/X5-Crop
```

## Current Scope

The app/native packaging direction is paused. Keep active work focused on the
standalone script workflow unless the user explicitly resumes the app direction:

```text
X5_Crop.py
archive/X5_Split_v17.py
archive/X5_Split_v18.py
```

Keep `X5_Crop.py` as the active script. Keep `X5_Split_v17.py` and
`X5_Split_v18.py` in `archive/` as preserved references. Keep user-facing
project documentation consolidated in `README.md`.

## Coding Rules

- Preserve TIFF metadata behavior unless the user explicitly asks to change it.
- Keep detection changes close to the script logic.
- Avoid broad refactors while solving a narrow detection or workflow task.
- Add or update docs when script usage, setup, or testing behavior changes.
- When the user describes directional behavior with left/right or top/bottom,
  treat that as the horizontal-strip baseline unless they say otherwise, and
  add the rotated vertical-strip behavior too.

## Git Rules

- Commit only intentional source/docs/config changes.
- If the working tree is NAS-synced, check `git status --short` before and
  after edits because another computer may have synchronized changes into the
  folder.
- Do not run two Codex sessions against the same NAS-synced working tree at the
  same time unless they are only reading.
- Do not commit local generated files or folders such as:
  - `.venv/`
  - `.venv-build/`
  - `build/`
  - `dist/`
  - `release/`
  - `__pycache__/`
  - `.DS_Store`
  - `downloaded_apps/`
  - `Test/`
  - generated `split_output/` folders
- Do not commit large TIFF samples unless the user explicitly decides they are
  official fixtures and Git LFS tracking is configured for them.

## Handoff Rule

When stopping work after source/docs changes, update the current handoff below.

Template:

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
Branch: main
Last commit: see `git log -1` after this handoff commit

Changed:
- Added per-image V2 analysis caching so `gray_work` and content evidence are
  computed once per image/layout and reused by content candidates and candidate
  calibration.
- Added a V2 full-strip shortcut: when a full-strip separator candidate passes
  the hard evidence and content-validation auto gate, same-format partial
  candidates are skipped. This keeps easy full strips fast without weakening
  difficult-image review behavior.
- Promoted the active script to X5 Crop V2 (`VERSION = "2.0"`).
- Reworked final detection into a multi-candidate scorer: V2 now generates
  separator and content candidates across plausible format/count/strip models,
  scores each candidate with geometry, separator, and content evidence, and
  records the top candidates under `v2_competition`.
- Added explicit `selected_candidate` and `selection_override` report fields so
  reports can show when a high-scoring partial content candidate lost to a
  plausible full-strip candidate.
- Limited auto-mode V2 partial candidates to useful counts and reduced partial
  offset probing to keep runtime closer to practical launcher use. Explicit
  `--strip partial` still keeps the fuller partial search.
- Updated README and launcher labels from V1 to V2.
- Tightened the final detector relationship into a joint evidence gate:
  separator evidence owns hard crop-line confirmation, content evidence validates
  the proposed photos, and format geometry constrains plausible frame shape and
  count.
- Added `separator_hard_evidence_ok(...)` so real detected, edge-pair, and
  enhanced separator marks can support auto-export, while grid/equal marks stay
  model evidence rather than hard separator evidence.
- Added a conservative content-only partial pass rule: partial strips may still
  auto-pass, but only when content confidence is very strong and there are no
  content run, coverage, or aspect ambiguity reasons.
- Added `joint_separator_not_confirmed` downgrading so a full-strip content
  candidate without hard separator confirmation falls back to `REVIEW` instead
  of auto-exporting from content alone.
- Analyzed all 79 TIFF samples under `Test/` as downsampled evidence material
  for the current detector.
- Confirmed raw content-run count is unstable on real samples: internal scene
  texture can split one frame into several content peaks, while low-texture or
  dark frames can merge several frames into one weak content run.
- Kept content evidence as the primary direction, but made the selector more
  explicitly joint: a separator candidate can win when it passes threshold, is
  supported by content evidence, and the content-primary candidate is ambiguous,
  below threshold, or smaller.
- Added a conservative auto-mode safeguard so a high-scoring partial candidate
  cannot automatically steal the result from a still-plausible full-strip
  candidate. In that case the full-strip model is returned for review with
  `partial_competes_with_plausible_full_strip`.
- Created active `X5_Crop.py` V1 from the latest v18 baseline.
- Added a conservative content-evidence layer using a composite score from local
  gradient, neighbor texture, local contrast, and tonal presence.
- DebugAnalysis is now a four-panel JPG: debug boxes, original gray, separator
  evidence, and content evidence.
- Removed standalone Debug launchers; keep normal launchers and DebugAnalysis
  launchers only.
- Plain debug previews now show only the status bar, green outer box, and
  semi-transparent crop-area fills. Colored separator marks are drawn in the
  DebugAnalysis Separator evidence panel.
- DebugAnalysis order is now Original gray, Debug boxes, Separator evidence,
  Content evidence.
- Debug boxes now use different semi-transparent fills for each crop area instead
  of blue outlines.
- Moved v17/v18 reference scripts into `archive/`.
- Simplified launcher names to `X5_Crop_Mac.command`,
  `X5_Crop_Mac_debug.command`, `X5_Crop_win.bat`, and
  `X5_Crop_win_debug.bat`.
- Default bleed is now long-axis 15px and short-axis 10px: horizontal strips are
  left/right 15px and top/bottom 10px; vertical strips are top/bottom 15px and
  left/right 10px.
- Detection is now content-primary: content evidence builds the crop candidate
  first, while the older separator-based detector is retained as
  `separator_assist` report data and fallback.
- Content candidate ranking now prefers more complete frame models when
  candidates are above threshold, so a tiny high-scoring partial does not steal
  the result from a plausible larger sequence.
- Partial strips are no longer capped below the auto-export threshold just for
  being partial; they can pass when content, aspect, and supporting evidence are
  strong enough.
- Content-primary candidates with mismatched content run counts are capped below
  the auto-export threshold and marked for review.
- Content evidence is written into reports and can conservatively downgrade
  clear content/aspect conflicts, but it does not raise difficult files into
  automatic export.
- Removed v18 launchers and added cleaner `X5_Crop_*` macOS and Windows
  launchers.
- Rewrote `README.md` as the current Chinese user guide for X5 Crop.

Verified:
- Profiled V2 before optimization: `Test/135/X5_00019.tif` took about 23 seconds
  under `cProfile`, dominated by repeated content evidence generation.
- After content caching, `Test/135/X5_00019.tif` dropped to about 12.6 seconds
  and `Test/120/X5_test_43.tif` / `X5_test_58.tif` were about 10.3 seconds.
- After the full-strip shortcut, `Test/135/X5_00019.tif` ran in about 6.2
  seconds, `Test/135/X5_00025.tif` in about 6.0 seconds, `Test/120/X5_test_43.tif`
  in about 9.9 seconds, and `Test/120/X5_test_58.tif` in about 9.6 seconds.
- Confirmed `Test/135/X5_00019.tif` and `X5_00025.tif` still remain
  `approved_auto` 6-frame `135` results after the speed changes.
- Confirmed `Test/120/X5_test_43.tif` and `X5_test_58.tif` still remain
  `needs_review` after the speed changes.
- Generated DebugAnalysis for `Test/120/X5_test_43.tif` after the speed changes;
  ordinary detection stayed under 10 seconds, while DebugAnalysis took about
  10.3 seconds because it also writes the combined JPG.
- `python3 X5_Crop.py --version` prints `X5_Crop.py 2.0`.
- Confirmed `Test/135/X5_00019.tif` remains `approved_auto` as a 6-frame `135`
  model after the V2 scorer. Runtime was about 25 seconds on this machine.
- Confirmed `Test/135/X5_00025.tif` remains `approved_auto` as a 6-frame `135`
  model after the V2 scorer.
- Confirmed `Test/120/X5_test_43.tif` remains `needs_review` as a 3-frame
  `120-66` model, even though 2-frame content partial candidates score highly.
- Confirmed `Test/120/X5_test_58.tif` remains `needs_review` because content is
  plausible but hard separator support is weak.
- Generated DebugAnalysis for `Test/120/X5_test_43.tif` and visually confirmed
  the final 3-frame review result still renders correctly.
- Confirmed `Test/135/X5_00019.tif` remains `approved_auto` as a 6-frame `135`
  model, with joint decision `separator_hard_evidence_passed_and_content_validated`.
- Confirmed `Test/135/X5_00025.tif` remains `approved_auto` as a 6-frame `135`
  model, with hard separator evidence plus content validation.
- Confirmed `Test/120/X5_test_43.tif` and `X5_test_44.tif` remain
  `needs_review` as 3-frame `120-66` models instead of false 2-frame partial
  auto-passes.
- Confirmed `Test/120/X5_test_58.tif` is downgraded to `needs_review` with
  `joint_separator_not_confirmed` when content is plausible but hard separator
  evidence is not strong enough.
- Confirmed `Test/135/X5_00060.tif`, `X5_00063.tif`, and
  `Test/120/X5_test_48.tif` remain `needs_review` because content evidence is
  ambiguous or incomplete.
- Built a Test contact sheet at `/private/tmp/x5crop_test_contact_sheet.jpg` for
  representative samples including `X5_test_1.tif`, `2.tif`, `3.tif`, `5.tif`,
  `9.tif`, `11.tif`, `19.tif`, `20.tif`, `22.tif`, `25.tif`, `43.tif`,
  `44.tif`, `48.tif`, `53.tif`, `72.tif`, `73.tif`, `74.tif`, `75.tif`,
  `77.tif`, and `79.tif`.
- Wrote the all-Test downsampled content summary to
  `/private/tmp/x5crop_test_content_run_summary.json`.
- Confirmed `Test/X5_test_43.tif` now returns `needs_review` for a 3-frame
  `120-66` model instead of falsely passing a 2-frame partial model.
- Confirmed `Test/X5_test_44.tif` now returns `needs_review` for a 3-frame
  `120-66` model instead of falsely passing a 2-frame partial model.
- Confirmed `Test/X5_test_19.tif` remains `approved_auto` as a 6-frame `135`
  model after joint separator/content selection.
- Confirmed `Test/X5_test_25.tif` remains `approved_auto` as a 6-frame `135`
  model after joint separator/content selection.
- Confirmed narrow/difficult `Test/X5_test_72.tif` and `X5_test_74.tif` remain
  `needs_review` rather than being promoted by content evidence.
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `bash -n X5_Crop_Mac.command X5_Crop_Mac_debug.command`
- `python3 X5_Crop.py --version`
- `python3 X5_Crop.py --help`
- Verified vertical bleed mapping with `Box.expand(15, 10, ...)` plus
  `map_work_box(..., "vertical", ...)`: long-axis bleed maps to original
  top/bottom, short-axis bleed maps to original left/right.
- Ran content-primary dry-runs on `Test/X5_test_19.tif`, `25.tif`, `31.tif`,
  `20.tif`, `22.tif`, `23.tif`, and `30.tif`; reports show
  `analysis_source=content_primary` with separator data under
  `separator_assist`.
- Confirmed `X5_test_25.tif` is forced to `needs_review` when content detects 7
  usable runs for a 6-frame target (`content_run_count_mismatch`), even though
  separator assist passes.
- After removing the partial-strip cap and adding content-specific ranking,
  confirmed `X5_test_19.tif` selects 3 frames and passes, `X5_test_20.tif`
  selects 5 frames and passes, while `X5_test_25.tif` remains review for run
  count mismatch.
- Ran DebugAnalysis dry-runs on `Test/135负片/正常/001.tif`, `11.tif`, and
  `X5 022.tif`.
- Confirmed `001.tif` remains `needs_review` at confidence `0.676` and produces
  a four-panel DebugAnalysis JPG.
- Re-ran DebugAnalysis for `001.tif` and visually confirmed colored separator
  marks moved to the Separator evidence panel while Debug boxes stayed clean.
- Re-ran DebugAnalysis for `001.tif` after panel reordering and visually
  confirmed the order is Original gray, Debug boxes, Separator evidence, Content
  evidence, with semi-transparent crop fills in Debug boxes.
- Ran `--debug` on `001.tif` and visually confirmed the standalone debug JPG now
  only shows the status bar, outer box, and crop boxes.
- Confirmed `11.tif` remains `approved_auto` at confidence `0.963`.
- Confirmed `X5 022.tif` remains `needs_review` at confidence `0.679`.
- Inspected the generated `001.tif` DebugAnalysis JPG and confirmed the fourth
  `Content evidence` panel is present.

Not verified:
- Did not run Windows `.bat` launchers on Windows.
- Did not run a non-dry-run TIFF export after creating X5 Crop V2.
- Did not create hand-labeled ground-truth fixtures for all `Test/` images; this
  pass used visual inspection plus representative dry-runs.
- Did not run the V2 scorer across all 79 Test TIFFs yet. Current V2 runtime is
  slower than V1 because it scores multiple candidates per file.

Known local-only files:
- `Test/`
- `/private/tmp/x5crop_v1_debug_001`
- `/private/tmp/x5crop_v1_debug_11`
- `/private/tmp/x5crop_v1_debug_11b`
- `/private/tmp/x5crop_v1_debug_x5022`
- `/private/tmp/x5crop_debuganalysis_only_001`
- `/private/tmp/x5crop_clean_debug_001`
- `/private/tmp/x5crop_reordered_panels_001`
- `/private/tmp/x5crop_content_primary_19`
- `/private/tmp/x5crop_content_primary_25`
- `/private/tmp/x5crop_content_primary_31`
- `/private/tmp/x5crop_content_primary_19b`
- `/private/tmp/x5crop_content_primary_25b`
- `/private/tmp/x5crop_content_primary_batch`
- `/private/tmp/x5crop_joint_score_19`
- `/private/tmp/x5crop_joint_score_20`
- `/private/tmp/x5crop_joint_score_25`
- `/private/tmp/x5crop_joint_score_19b`
- `/private/tmp/x5crop_joint_score_20b`
- `/private/tmp/x5crop_joint_score_25c`
- `/private/tmp/x5crop_test_contact_sheet.jpg`
- `/private/tmp/x5crop_test_content_run_summary.json`
- `/private/tmp/x5crop_joint_model_19b`
- `/private/tmp/x5crop_joint_model_25b`
- `/private/tmp/x5crop_joint_model_43c_debug`
- `/private/tmp/x5crop_joint_model_44b`
- `/private/tmp/x5crop_joint_model_72b`
- `/private/tmp/x5crop_joint_model_74b`
- `/private/tmp/x5crop_joint_gate_19`
- `/private/tmp/x5crop_joint_gate_25`
- `/private/tmp/x5crop_joint_gate_43`
- `/private/tmp/x5crop_joint_gate_44`
- `/private/tmp/x5crop_joint_gate_48`
- `/private/tmp/x5crop_joint_gate_58`
- `/private/tmp/x5crop_joint_gate_60`
- `/private/tmp/x5crop_joint_gate_63`
- `/private/tmp/x5crop_v2_19`
- `/private/tmp/x5crop_v2_19b`
- `/private/tmp/x5crop_v2_19c`
- `/private/tmp/x5crop_v2_19d`
- `/private/tmp/x5crop_v2_25`
- `/private/tmp/x5crop_v2_25b`
- `/private/tmp/x5crop_v2_25c`
- `/private/tmp/x5crop_v2_25d`
- `/private/tmp/x5crop_v2_43`
- `/private/tmp/x5crop_v2_43b`
- `/private/tmp/x5crop_v2_43c`
- `/private/tmp/x5crop_v2_43d`
- `/private/tmp/x5crop_v2_43_debug`
- `/private/tmp/x5crop_v2_58b`
- `/private/tmp/x5crop_v2_58c`
- `/private/tmp/x5crop_v2_58d`
- `/private/tmp/x5crop_profile_19`
- `/private/tmp/x5crop_profile_43`
- `/private/tmp/x5crop_profile_19_cached`
- `/private/tmp/x5crop_profile_43_cached`
- `/private/tmp/x5crop_speed_19a`
- `/private/tmp/x5crop_speed_19b`
- `/private/tmp/x5crop_speed_25b`
- `/private/tmp/x5crop_speed_43a`
- `/private/tmp/x5crop_speed_43b`
- `/private/tmp/x5crop_speed_43_debug`
- `/private/tmp/x5crop_speed_58a`
- `/private/tmp/x5crop_speed_58b`

Next recommended step:
- Run V2 over a broader Test batch and use `v2_competition` to identify which
  candidate families are still too aggressive. If more speed is needed, the next
  likely target is caching separator outer candidates/profiles per image/layout.
