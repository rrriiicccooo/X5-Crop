# X5 Crop Changelog

This local changelog records detection and workflow decisions in more detail
than the user-facing README. It is meant for development, rollback, and future
debugging.

本地 changelog 记录比 README 更详细的检测逻辑和工作流变化，方便之后开发、回滚和复盘。

Current active script: `X5_Crop.py` V3.4.1

Current stable GitHub Release: `v3.3.1`

## Version Status

| Version | Status | Summary |
|---|---|---|
| V3.5 | Paused / rolled back | Hard-gap semantic validation experiment. Removed from active script after accuracy regressions. |
| V3.4.2 | Paused / rolled back | Local grid segment experiment. Removed from active script after accuracy regressions. |
| V3.4.1 | Current active development version | Strong hard separators stay authoritative when they conflict with robust grid. |
| V3.4 | Development baseline for simplified detection | Removed low-value enhanced separator logic and simplified candidate generation. |
| V3.3.2 | Development | Conservative overlap-like gap handling. |
| V3.3.1 | Stable Release | Stable packaged release based on V3/V3.2 style detection plus output-only bleed. |
| V3.3 | Development | Detection bleed and output bleed separated. |
| V3.2 | Development | Returned to V3-style detection after V3.1.x regressions. |
| V3.1.x | Experimental | Aggressive outer/gap rescue ideas. Not stable enough. |
| V3.0 | Baseline | Main X5 Crop script and user workflow foundation. |

## Current Active: V3.4.1

V3.4.1 is currently active because later experiments made several previously
good scans less accurate. The active script was temporarily rolled back to this
version after regressions were observed on scans including `X5_00051`,
`X5_00044`, `X5_00038`, and `X5_00022`.

Main detection behavior:

- Keeps the V3/V3.2 style ordinary outer / gap / candidate path.
- Keeps V3.4 detection simplification:
  - no enhanced separator layer;
  - no independent full-strip content candidate;
  - content is validation, not a competing full-strip candidate;
  - `equal-broad-region` is folded into ordinary `equal`.
- Preserves strong hard separator evidence when robust grid disagrees with it.
- Records hard/grid disagreements in `grid.hard_conflicts`.
- Keeps output bleed outside detection scoring.
- Keeps the rule that difficult or weak-evidence scans must not be auto-passed
  by fallback or rescue logic.

Why this version is preferred right now:

- It preserves accurate behavior on known-good scans better than V3.4.2/V3.5.
- It avoids allowing grid/local rescue to override correct red hard separator
  evidence too aggressively.
- It keeps the detection chain easier to reason about while future improvements
  are being redesigned.

Known limitations:

- It does not contain the later local-grid or hard-gap semantic validation
  experiments.
- Some true internal-edge false positives may still need future treatment.
- Future fixes should be narrower and should explicitly protect known-good
  scans before being made active again.

## V3.5: Hard-Gap Semantic Validation Experiment

Status: paused / rolled back from active script.

Goal:

- Make red hard separator boxes more trustworthy.
- Detect cases where a high-score red edge-pair is actually an internal image
  edge rather than a real film-frame separator.
- Let grid handle only clearly suspicious red gaps without loosening PASS/REVIEW.

Implementation idea:

- Run a lightweight validation layer after `edge_refine` and before robust grid.
- Reuse cached content evidence and edge-refine profiles.
- For each accepted hard gap, inspect small local windows around the gap:
  - gap content;
  - left/right content;
  - content continuity;
  - background/separator profile;
  - edge/activity profile.
- Label hard gaps as strong or suspect.
- Demote only very narrow, content-continuous, internal-edge-like hard gaps to
  model gaps.

Why it was paused:

- Although it helped explain at least one false hard separator pattern, the
  active V3.5 behavior made some previously accurate scans worse.
- The user observed regressions on important known-good scans, so this logic was
  removed from the active script.

Future notes:

- Do not reintroduce this as a broad rule.
- If revisited, it should start as report-only diagnostics before it can change
  gap methods.
- It needs stronger safeguards for known-good scans and maybe a per-gap
  confidence label that does not immediately alter geometry.

## V3.4.2: Local Grid Segment Experiment

Status: paused / rolled back from active script.

Goal:

- Improve behavior on irregular spacing, near-overlap, or partly unstable strip
  geometry.
- Let grid remain useful without letting global equal spacing overwrite good
  red hard separators.

Implementation idea:

- Use strong hard separators as local anchors.
- Reposition only model-only gaps (`grid` / `equal`) between or near those
  anchors using a local pitch.
- Do not move hard separators.
- Do not increase confidence merely because local grid adjusted a model gap.
- Record details in `local_grid`.

Why it was paused:

- It still changed geometry on scans that were previously accurate.
- The user found that several good images became less accurate after the
  V3.4.2/V3.5 direction.
- Local grid can be useful, but it needs stricter proof that the target model
  gap is genuinely wrong before it changes geometry.

Future notes:

- If revived, keep it limited to diagnostics first.
- Consider drawing local-grid suggestions in Debug Analysis without using them
  for output boxes.
- Require stronger evidence that local spacing is actually irregular and that
  the adjusted position aligns with visual separators.

## V3.4.1: Preserve Strong Hard Gaps

Status: current active development version.

Goal:

- Fix cases where robust grid overwrote an accurate red hard separator.
- Make red hard evidence authoritative when it is strong and plausible.

Main changes:

- Strong `detected` / `edge-pair` gaps are preserved even if robust grid
  predicts a different center.
- Grid can still fill missing or weak model gaps.
- Grid/hard conflicts are recorded in `grid.hard_conflicts`.
- If full geometry is already accepted, the same evidence is not double-counted
  as `unstable_frame_width`.

Why it matters:

- The separator evidence panel becomes easier to interpret because a correct red
  hard separator remains red.
- The grid is treated as model support, not as a stronger source than real
  separator evidence.

## V3.4: Detection Simplification

Status: development baseline retained by V3.4.1.

Goal:

- Remove low-value or confusing detection layers.
- Make Debug Analysis easier to read.
- Reduce maintenance cost and duplicated logic.

Main changes:

- Removed the enhanced separator layer from active separator detection.
- `--analysis` no longer drives enhanced separator acceptance; it remains
  relevant to analysis/deskew behavior.
- Removed `enhanced-detected` from active gap methods and README color
  semantics.
- Folded `equal-broad-region` into ordinary `equal`.
- Full-strip detection no longer creates a separate content candidate when the
  separator/geometric candidate is already the main path; content is validation.
- The fallback path remains small and conservative.

Effect:

- Debug evidence uses fewer overlapping colors and concepts.
- Full-strip logic is easier to maintain.
- Fewer old-chain decisions compete with the active V2 candidate scoring path.

## V3.3.2: Conservative Overlap-Aware Gap Handling

Status: development, not active after rollback except as historical reference.

Goal:

- Improve near-overlap or continuous-content cases without making them pass more
  easily.

Main changes:

- Model gaps that look overlap-like can be marked `overlap_like=true`.
- Overlap-like gaps are not used as strong same-frame-size anchors.
- This is intended to reduce geometry correction based on suspect model gaps.

Important principle:

- Overlap handling should explain or restrain geometry correction. It should not
  increase confidence or push difficult scans into auto-pass.

## V3.3.1: Stable Release

Status: stable GitHub Release.

Release asset:

- `X5-Crop-v3.3.1.zip`

Main behavior:

- Keeps the stable V3/V3.2 ordinary outer / gap / candidate chain.
- Keeps output-only bleed separation.
- Preserves conservative PASS/REVIEW behavior.
- Includes bilingual README, launchers, install scripts, archive snapshots, and
  MIT License.
- GitHub Release notes include bilingual quick start and changes since `v3`.

Why it is stable:

- It was packaged as the user-facing release before later development
  experiments.
- It favors conservative known-good behavior over newer unproven detection
  ideas.

## V3.3: Output-Only Bleed Separation

Status: development ancestor of stable release behavior.

Goal:

- Prevent bleed from changing detection decisions.

Main changes:

- Detection uses no bleed internally.
- Output/report/Debug Analysis frame boxes apply output bleed afterward.
- Default output bleed is long axis 20px and short axis 10px.
- Horizontal strips use left/right as long-axis bleed; vertical strips rotate
  the interpretation accordingly.

Why it matters:

- Increasing output safety margin no longer changes outer boxes, gap selection,
  confidence, or PASS/REVIEW.

## V3.2: Return To V3 Detection Chain

Status: development rollback from V3.1.x experiments.

Goal:

- Restore the more stable V3-style ordinary outer/gap/candidate path.
- Keep safety improvements that prevent weak-evidence scans from auto-passing.

Main changes:

- Removed aggressive V3.1-style outer/gap competition from active path.
- Kept a narrow safety gate for leading low-score grid failures.
- Kept launcher, docs, reuse, output, and terminal UX improvements that were not
  part of risky detection changes.

## V3.1.x: Aggressive Correction Experiments

Status: experimental, not stable.

Ideas tested:

- More aggressive content-aligned outer expansion.
- Separator-derived outer competition.
- Local separator rescue near expected grid gaps.
- Additional frame/edge fitting behavior.

Why it was not kept:

- Some target cases improved, but several already-good scans became less
  accurate.
- The project goal is high-confidence automatic cropping only, so risky rescue
  logic must not become the main path.

Lessons:

- New rescue logic should be constrained to report-only or review-only until it
  proves it does not harm known-good scans.
- PASS/REVIEW should not be improved by fallback alone.

## V3.0: Baseline X5 Crop Script

Status: baseline.

Main capabilities:

- `X5_Crop.py` became the active script.
- Supports `135`, `135-dual`, `half`, `xpan`, `120-645`, `120-66`, and
  `120-67`.
- Full strip uses fixed counts by format.
- Partial mode uses auto count.
- Debug Analysis dry run writes JPG analysis and reports.
- Low-confidence files are sent to review instead of forced through.
- TIFF output attempts to preserve pixel data and metadata behavior as much as
  practical.

## Development Testing Notes

- For detection development and regression dry-runs, use `--deskew off` unless
  testing deskew itself.
- Focus targets after detection changes should include:
  - `X5_00007`
  - `X5_00022`
  - `X5_00032`
  - `X5_00036`
  - `X5_00038`
  - `X5_00044`
  - `X5_00051`
  - `X5_00052`
- The core rule remains: only high-confidence detections should auto-crop.
  Rescue, fallback, grid, or validation layers must not make hard images pass by
  accident.
