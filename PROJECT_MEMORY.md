# Project Memory / 项目记忆

Updated / 更新：2026-07-19

This file is the concise cross-session checkpoint for the current long-running task. It is
a map, not an instruction source or completion proof. Current user intent, Git, source,
original TIFFs, manual references, current reports, Debug Analysis, and command output remain
authoritative.

本文件是当前长任务的简短跨会话检查点，不是指令来源或完成证明。当前用户目标、Git、源码、
原 TIFF、人工 reference、current report、Debug Analysis 与现场命令始终优先。

## Frozen Checkpoint / 冻结检查点

- Branch / 分支：`main`.
- Candidate / 候选提交：`d1a4f6ad` (`test: preserve raw sequence alternatives`), pushed to
  `origin/main`.
- Worktree / 工作树：tracked files were clean immediately after that push; local `Test/`
  references and generated diagnostics are intentionally ignored and untracked.
- Canonical verifier / 唯一验证入口：`tools/verify full` passed before commit and again in the
  push hook at this candidate: 799 tests, 14 format/mode configuration pairs, V4.9.
- Resume by checking `git log -1 --oneline`, `git status --short`, and current reports; do not
  assume this snapshot is still current. / 恢复时先核对当前提交、工作树和报告，不把本快照当作
  现场事实。

## Closed Work / 已关闭工作

- The protected dirty graph-witness and cross-axis continuity work was confirmed as two
  independent physical classes, verified, committed, and pushed separately.
- Graph search now preserves complete physical alternatives, separator cross-axis support
  preserves a continuous qualifying component, and frame-scale identities retain their
  anchor facts.
- `pass_X5_00006` and the file now classified as
  `Test/135/full/unknown_X5_00038.tif` no longer expose resolved-wrong/exportable geometry.
  The user explicitly classifies 00038 as `unknown`, not `pass`.
- The complete manual-reference audit added 111 geometry references for 113 TIFFs; the two
  `review_required` samples intentionally have no geometry reference. Current local data pass:

  ```bash
  python3 -m tools.regression.sample_expectations \
    Test/sample_expectations.jsonl \
    Test/frame_slot_references.jsonl \
    Test
  ```

- The first all-sample baseline at `d798898e` produced 113 current reports with zero runtime
  failures, 32 `approved_auto`, 81 `REVIEW`, and no outputs. Manual comparison found 21
  conforming resolved results, 79 typed unresolved results, and 11 resolved-wrong results.
- `a6d3295c` adds two current-only resolution contracts: every ordinary multi-slot width must
  intersect the supported common frame width, and nominal geometry outside the acquired
  workspace canvas cannot be resolved even through holder occlusion. Focused reruns confirmed
  all 11 formerly resolved-wrong samples now remain typed, non-exportable `REVIEW`; the full
  113-sample rerun is still pending and must not be inferred from focused evidence.
- `a8de0539` materializes each count-local graph fallback order once; `ba408749` preserves the
  construction-owned, frame-width-focused recurring order when there is no supported internal
  separator seed. Both changes reuse and reorder the complete physical search space; neither
  deletes hypotheses nor changes proof, Gate, or budget authority.
- `d1a4f6ad` makes raw sequence alternatives an explicit retained contract: a provisional
  separator incumbent cannot delete earlier raw builds because later common-width resolution
  and unique observation assignment can change their final physical roles. Two attempted
  optimizations were rejected rather than committed: retroactive raw-build filtering made
  `unknown_X5_00038` resolved-wrong and automatically approved; a raw separator-chain upper
  bound changed the complete-search `half/full/pass_X5_00001` frame-slot resolution and Debug.
- Current named diagnostics at the runtime-equivalent `d1a4f6ad` keep `pass_X5_00006` and
  `unknown_X5_00038` unresolved and non-exportable. Representative
  `120-66/partial/pass_X5_00005` and `half/full/pass_X5_00001` also remain unresolved and
  non-exportable; both still expose typed `execution_budget_exhausted`, so the performance phase
  is not closed.

- 已保护的 graph witness 与 cross-axis dirty work 属于两个独立物理类别，已分别验证、提交并
  推送；search alternatives、连续 cross-axis support 与 anchor-backed frame-scale identity 已收口。
- `pass_X5_00006` 与现已分类为 `unknown_X5_00038.tif` 的样片不再报告 resolved-wrong 或
  exportable geometry；00038 的用户事实是 `unknown`。
- 本地 113 张 TIFF 已有 111 条人工 geometry reference；两张 `review_required` 样片按设计无
  reference。`d798898e` 全量基线有 0 runtime failure、32 auto approval、81 REVIEW、0 output，
  人工比较为 21 matched、79 unresolved、11 violated。
- `a6d3295c` 已把这 11 个 violated 样片逐一降为 typed、不可导出的 REVIEW；仍必须用该冻结提交
  重跑全部 113 张，不能从局部结果外推全量通过。
- `a8de0539` 复用 count-local graph fallback 顺序；`ba408749` 在没有 supported internal
  separator seed 时保留 construction 已聚焦的 recurring-width 顺序。两者都不删 hypothesis，
  也不改变 proof、Gate 或 budget 权限。当前具名 diagnostics 均保持 unresolved、不可导出；
  `120-66/partial/pass_X5_00005` 与 `half/full/pass_X5_00001` 仍有 typed budget exhaustion，
  因此性能阶段尚未关闭。
- `d1a4f6ad` 固定 raw alternative 不得被 provisional separator incumbent 提前删除。
  回溯过滤曾使 `unknown_X5_00038` 重新 resolved-wrong 且自动通过；raw separator-chain
  上界曾改变 `half/full/pass_X5_00001` 的完整搜索结果与 Debug。两者均已否决，
  没有保留 runtime 改动。

## Frozen Physical Rules / 冻结物理权限

- Geometry, evidence, CandidateGate, GeometryResolution, selection, DecisionGate, output
  protection, report, and Debug remain separate one-way authorities.
- Hints, budgets, scores, blank appearance, repeated widths, grids, and self-consistent
  geometry are not physical proof. Budget exhaustion is typed unavailable.
- Common width comes only from intersecting independent measurements. Separator assignments
  are candidate-specific and preserve topology, cross-axis continuity, signed spacing, and
  provenance.
- At most one blank slot may be derived from a unique complete sequence. Holder occlusion is
  endpoint-only and cannot resolve unobservable geometry outside the acquired canvas.
- Only exact count/offset-independent measurements may be cached. Unresolved or provisional
  geometry is never exportable, including under `--export-review`.

- 几何、evidence、各 gate、selection、output、report 与 Debug 权限单向分离；hint、budget、
  score、blank appearance、重复宽度、grid 和几何自洽都不是物理证明。
- common width 只来自相交的独立实测；separator 必须保持 candidate-specific topology、连续性、
  signed spacing 与 provenance。最多推导一个唯一完整序列中的 blank；holder occlusion 只能在
  端点，且不能解决画布外不可观测几何。任何 unresolved/provisional geometry 永不导出。

## Performance Baseline / 性能基线

- Frozen diagnostic / 冻结样片：`Test/half/partial/pass_X5_00001.tif`, `half/partial`,
  horizontal, auto count, `--deskew off --diagnostics --jobs 1`.
- `1c798dd6`: 199.28 s detection, 933,677 assignment evaluations, 11 candidates, cache 41/6.
- `a8de0539`: 129.16 s detection with the same evaluations, candidates, and cache counts.
- `ba408749`: 80.71 s detection, 971,842 assignment evaluations, 11 candidates, cache 41/6.
  The selected result remains typed unresolved `REVIEW` and non-exportable. The latest ordering
  makes useful branches earlier but does not eliminate budget exhaustion.
- `d1a4f6ad` does not change runtime behavior from `ba408749`. A real macOS sample identified
  repeated reachability subset ordering as the next measured wall-time cost, but candidate or
  raw-build result caching remains forbidden; continue only with exact transient deduplication
  or a physically complete graph reduction.
- Continue from measured call-stack costs. Only exact reuse/deduplication, physically complete
  interval or anchor pruning, branch-and-bound, delayed blank branching, and focused ordering
  are legal; performance, budget, Gate, or confidence cannot change physical authority.

## Next Actions / 下一步

1. Continue profiling the fixed `half/partial/pass_X5_00001.tif` sample from `d1a4f6ad`; first
   investigate exact within-call reachability-order deduplication or physically complete graph
   reduction. Do not reintroduce provisional raw-build incumbent or separator-chain pruning.
2. Re-profile after each legal optimization wave; run focused contracts, `tools/verify full`,
   named reports, reference comparison, and Debug Analysis before an independent commit/push.
3. Rerun all 113 TIFFs from a clean frozen commit. Require zero runtime/schema failure, zero
   resolved-wrong, zero unresolved export, zero wrong automatic export, and no pass-required
   budget exhaustion.
4. Rebuild stale `Test/test 2` only after physical and performance candidates freeze. Preserve
   `Test/test 1`; include terminal manifest, current reports, Debug Analysis, summaries,
   reference/proof validation, runtime/solver/budget/cache metrics, and test-1 comparison.
5. Start Audit A only from a clean verified pushed candidate. Any root fix invalidates it and
   requires a fresh forward audit. After zero known violations, prepare a context-independent
   reverse-order Audit B prompt for a new Codex task; do not execute Audit B in this task.

1. 从 `ba408749` 继续剖析固定最慢样片；每个新残留类别都先增加失败合同，再做对应优化。
2. 每轮只做合法优化，并复核合同、全量 verifier、具名 report/reference 与 Debug 后独立提交推送。
3. clean frozen commit 上重跑 113 张，要求 0 runtime/schema failure、0 resolved-wrong、
   0 unresolved export、0 wrong automatic export，且 pass-required 不得 budget exhausted。
4. 物理与性能冻结后才重建旧 `Test/test 2`，再从 clean pushed candidate 执行 Audit A；Audit B
   只留下全新任务 prompt，不在本任务中执行。
