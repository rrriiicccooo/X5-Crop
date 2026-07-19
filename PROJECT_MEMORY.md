# Project Memory / 项目记忆

Updated / 更新：2026-07-20

This is a concise cross-session checkpoint, not an instruction source or completion
proof. Current user intent, Git, source, original TIFFs, manual references, current
reports, Debug Analysis, and live command output remain authoritative.

本文件只是简短的跨会话检查点，不是指令或完成证明。当前用户目标、Git、源码、原 TIFF、
人工 reference、current report、Debug Analysis 与现场命令始终优先。

## Frozen Checkpoint / 冻结检查点

- Branch / 分支：`main`.
- Candidate / 候选提交：`577b18fa`
  (`fix: refute holder clipping with workspace content`), pushed to
  `origin/main`.
- Tracked worktree was clean immediately after that push. Local `Test/` TIFFs,
  references, generated diagnostics, and `Test/test 2` remain ignored and
  untracked.
- `tools/verify full` passed before commit and again in the push hook:
  803 tests, 14 format/mode configuration pairs, V4.9.
- Resume by checking `git log -1 --oneline`, `git status --short`, and current
  reports. Do not treat this snapshot as live truth.

## Closed Physical Work / 已关闭物理工作

- Full-workspace reliable content now refutes only a long-axis holder boundary
  it physically crosses before the sequence search scope is built. Short-axis
  holder boundaries are unaffected; content still cannot prove holder, count,
  frame edge, or decision.
- `FrameCoverageEvidence` merges exact cached full-workspace and holder-local
  reliable runs, so a false holder clip cannot hide omitted photos.
- A geometry-corroborated observation wider than the interval allowed by an
  independent common width and the opposite anchor becomes their
  dimension-constrained intersection. Direct and measurement-corroborated
  boundaries remain measured facts.
- Three frozen-`11ff1b7d` contracts reproduced these classes before the fix:
  crossed holder retention, holder-clipped content coverage, and an unnarrowed
  geometry-corroborated endpoint.
- Named `120-66/partial` 00014, 00026, and 00031 now remain typed unresolved,
  `REVIEW`, and non-exportable instead of resolved-wrong. The user-classified
  `Test/135/full/unknown_X5_00038.tif` also remains geometry unavailable,
  `REVIEW`, and non-exportable.

- 完整 workspace 的 reliable content 只反证实际穿过的长轴 holder boundary；
  `FrameCoverageEvidence` 合并 workspace 与 holder-local reliable runs，错误
  holder clipping 不能再隐藏遗漏照片。
- geometry-corroborated 宽观测区间会被独立 common width 与对侧 anchor 收敛为
  dimension-constrained 交集；direct 与 measurement-corroborated 实测不变。
- 旧 HEAD 上三项失败合同均稳定为红。120-66 partial 的 00014、00026、00031
  已从 resolved-wrong 降为 typed unresolved / REVIEW / 不可导出；00038 的用户事实仍是
  `unknown`，不是 `pass`。

## Current Real-Sample Authority / 当前真实样片权限

- Local dataset: 113 TIFFs, 113 expectations, 111 manual geometry references.
  The two `review_required` samples intentionally have no geometry reference.
- Fresh diagnostics at the code committed as `577b18fa` completed all 113
  inputs: 0 runtime/schema failures, 29 `approved_auto`, 84 `REVIEW`,
  29 supported/export-eligible geometries, 84 unavailable/non-exportable
  geometries, and 0 unresolved exports.
- Authority validation after source-pixel review:
  51 conforming, 62 capability gaps, 0 evidence-contract conflicts,
  0 physical violations.
- Two `135/partial` files (`pass_X5_00003` and `unknown_X5_00008`) are
  byte-identical. Their shared manual intervals were widened from the original
  TIFF coordinate view to include visible slanted/overlapping transitions.
  `120-66/partial/pass_X5_00029` frame-1 trailing was likewise widened to
  include its visible 6030-6308 slanted span. These local reference corrections
  were not copied from detector output.
- Re-run authority with:

  ```bash
  python3 -m tools.regression.sample_expectations \
    Test/sample_expectations.jsonl \
    Test/frame_slot_references.jsonl \
    Test

  python3 -m tools.regression.sample_validation \
    Test/sample_expectations.jsonl \
    Test/frame_slot_references.jsonl \
    Test \
    <all seven current x5_crop_report.jsonl files>
  ```

## Frozen Physical Rules / 冻结物理权限

- Geometry, evidence, CandidateGate, GeometryResolution, selection,
  DecisionGate, output protection, report, and Debug remain separate one-way
  authorities.
- Hints, budgets, scores, blank appearance, repeated widths, grids, content
  appearance, and self-consistent geometry are not proof. Budget exhaustion is
  typed unavailable.
- Content may refute omitted coverage or a crossed long-axis holder boundary;
  it cannot create, move, or prove a frame boundary.
- Common width comes only from intersecting independent measurements.
  Separator assignments remain candidate-specific and conserve topology,
  cross-axis continuity, signed spacing, and provenance.
- At most one blank may be derived from a unique complete sequence. Holder
  occlusion is endpoint-only and cannot resolve geometry outside the canvas.
- Only exact count/offset-independent measurements may be cached. Unresolved or
  provisional geometry is never exportable, including with `--export-review`.

## Performance State / 性能状态

- Frozen sample: `Test/half/partial/pass_X5_00001.tif`, auto count,
  `--deskew off --diagnostics --jobs 1`.
- Accepted path to `11ff1b7d`: 199.28 s -> 129.16 s -> 80.71 s ->
  74.71 s -> 50.27 s detection. The latest frozen run retained 971,842
  assignment evaluations, 11 candidates, cache 41/6, a zero-diff report, and
  byte-identical Debug.
- The new physical candidate `577b18fa` has not yet been re-profiled in an
  isolated performance run. The concurrent 113-sample diagnostics are not a
  performance baseline.
- Current authority still has six typed budget-exhausted samples; five are
  `pass_required`: `half/full/pass_X5_00001`,
  `half/partial/pass_X5_00001`, and `66/partial` 00005, 00010, 00011.
  Performance acceptance is therefore open.
- Rejected routes remain rejected: raw-build incumbent filtering,
  separator-chain pruning, boundary caps, skipping graph best paths/witnesses,
  candidate/result caching, or raising budget as reliability evidence.

## Next Actions / 下一步

1. Re-profile the fixed half/partial sample from clean `577b18fa` and continue
   only with exact transient reuse, physically complete interval/anchor pruning,
   branch-and-bound, delayed blank branching, or focused ordering. Re-run named
   reports, references, Debug, and `tools/verify full` after every accepted wave.
2. Close all five `pass_required` budget-exhausted cases without moving proof,
   Gate, selection, or decision authority.
3. Rebuild stale `Test/test 2` only after the physical/performance candidate is
   frozen. Preserve `Test/test 1`; include terminal manifests, all 113 current
   reports, Debug Analysis, summaries, authority validation, runtime/solver/
   budget/cache metrics, and the test-1 performance comparison.
4. Start Audit A only from a clean, verified, committed, pushed candidate. Any
   root fix invalidates it. After zero known violations, leave a
   context-independent reverse-order Audit B prompt for a new Codex task; do not
   execute Audit B in this task.
