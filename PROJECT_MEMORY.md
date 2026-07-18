# Project Memory / 项目记忆

Updated / 更新：2026-07-19

This file is the rolling, cross-session checkpoint for the current long-running
task. It is a map, not an instruction source or proof. Read it only when the user
explicitly resumes or updates this task; current user intent, tracked files,
reports, Debug Analysis, and command output remain authoritative.

本文件是当前长任务的跨会话滚动检查点，不是指令来源或证据。只有在用户明确恢复或更新本任务时
才读取；当前用户意图、受跟踪文件、报告、Debug Analysis 和命令输出始终优先。

## Checkpoint / 检查点

- Branch / 分支：`main`.
- Pre-migration base / 迁移前基线：`dda0e33a`.
- Resume baseline / 恢复基线：使用包含本文件的当前提交；先运行 `git log -1 --oneline` 和
  `git status --short` 确认，不依赖这里保存的旧提交号。
- State / 状态：Shared Short Axis / Frame Slot 破坏性迁移已经进入受跟踪源码、测试、报告、
  Debug 和文档；broad-uncertainty common-width contributor 分组合同已经补齐。Auditability /
  Ownership Gate 前九波已建立独立的 measurement-interval、common-width、search graph /
  reachability / budget、candidate state / physical Pareto，以及 assignment-consensus canonical
  owners；candidate-specific separator assignment、boundary-role corroboration 与 candidate
  physical resolution（含唯一 gray-path assignment）也已有唯一 owner；blank/occlusion /
  completion 现在统一由既有 `sequence_completion.py` 拥有。但其余 candidate construction /
  solver orchestration、剩余物理校准、完整样片复核、性能对比和双轮架构审计尚未完成。
- Safety / 安全：不得 reset、restore 或恢复旧 `PhotoAperture`、旧 sequence solver、旧 schema
  或任何兼容层；不要把当前检查点误称为物理或架构闭环。

## Durable Decisions / 长期决定

- One shared safe short-axis span is resolved for the strip; the global solver
  then resolves ordered frame slots and their long-axis boundaries.
- Gray paths and separator bands are count-independent observations. Geometry
  support, search state, candidate assessment, final decision, output protection,
  report, and debug remain separate authorities.
- One blank slot may be inferred only from a uniquely solved complete sequence.
  Missing content, blank appearance, and repeated width are never independent
  proof and never move measured real-frame edges.
- Search budgets and hints do not prove geometry. Ambiguity remains typed
  unresolved; physical Pareto replaces weighted residual scoring.
- Cache only exact count/offset-independent measurements. Named TIFFs, current
  reports, and Debug Analysis outrank aggregate PASS counts.

- 每条片条先解析一个共享安全短轴，再由全局 solver 联合解析有序 frame slots 和长轴边界。
- 灰度路径与 separator band 是独立观测；几何、搜索、候选评估、最终决定、输出保护、报告和
  Debug 的权限彼此分离。
- 只有完整序列唯一成立时才允许推导一个空白 slot；缺少内容、空白外观和重复宽度都不是独立
  证明，也不能移动真实实测边界。
- 搜索预算和 hint 不能证明几何；歧义保持 typed unresolved，以物理 Pareto 代替加权残差评分。

## Verification State / 验证状态

- Fresh checkpoint verification / 当前检查点新验证：`tools/verify full` passed on 2026-07-19
  with 752 unit/contract tests, 14 format/mode configuration pairs, compile,
  macOS shell syntax, diff hygiene, release-package construction, and version
  checks. Confirm the current commit and clean status at resume time.
- The verifier proves source and contract consistency only. It does not prove
  named-sample geometry, performance closure, visual Debug correctness, or the
  two required architecture audits.
- `tools.tests.test_sample_expectation_contract` verifies loader/contract code;
  it does not validate the ignored local `Test/sample_expectations.jsonl` data.
  The current local record for `pass_X5_00038.tif` still lacks its required own
  geometry reference and must be repaired from real evidence before that dataset
  can be called validated.

- 当前 `tools/verify full` 已通过 752 项 unit/contracts、14 组配置、compile、macOS shell syntax、
  diff hygiene、发布包构建和版本检查；它仍不能证明具名样片几何、性能闭环、Debug 视觉正确性或
  两轮架构审计。
- sample-expectation 单元测试只验证加载器和契约代码；当前本地 `pass_X5_00038.tif` 记录仍缺少
  必需的自身 geometry reference，在获得真实证据前不得称该本地数据集已验证。

## Remaining Physical Work / 未完成物理工作

- `pass_X5_00007`: sequence proof unavailable and output protection unresolved.
- `pass_X5_00013`, `pass_X5_00018`, `pass_X5_00019`, `pass_X5_00032`:
  assignment consensus remains unresolved. The focused `00018` contract now
  rejects a broad width interval that would bridge mutually incompatible narrow
  contributor groups, but the current selected geometry still has four distinct
  assignments and therefore correctly remains non-exportable.
- `pass_X5_00031`: common frame width and frame slots remain unresolved.
- Representative geometry that looks visually correct is not enough when another
  non-dominated, weaker dimension-heavy explanation remains.

- Phase 1 and the first nine Phase 2 ownership waves were behavior-neutral on the
  same six frozen samples (`00007/13/18/19/31/32`): every adjacent current-schema
  comparison had zero report diffs and all six Debug Analysis JPEGs were
  byte-identical. The latest fresh visual inspection kept all six `REVIEW` /
  non-exportable; `00018` and `00031` still show incomplete provisional geometry
  and must not be upgraded.

以上样片仍需当前报告和 Debug Analysis 逐张复核；肉眼正确的代表解不能覆盖仍存在的非支配、
dimension-heavy 替代解释。

## Next Actions / 下一步

1. Continue the Auditability / Ownership Gate before further broad sample
   calibration. Measurement intervals and common-width resolution now have
   canonical owners; search graph/reachability/budget and candidate state/Pareto
   are separate too, as are assignment consensus and separator assignment. Next
   separate result facts and the remaining candidate construction without wrappers,
   re-exports, or duplicate models, then leave `solve_frame_sequence` as a thin
   orchestration facade. Boundary roles, candidate physical resolution, and sequence
   completion now each have one owner.
2. Keep reducing `solve_frame_sequence` to a thin orchestration facade and extend
   the machine-checked authority/import boundaries for each coherent ownership wave.
3. After each green ownership wave, recheck current-schema reports and relevant
   Debug Analysis before committing and pushing.
4. Then finish the remaining physical contracts, all format-mode samples,
   fixed-sample performance comparison, and Test/test 2.
5. Audit active runtime, tests, fixtures, helpers, reports, and Debug twice with
   the same frozen checklist: forward Audit A, then a fresh-context reverse-order
   Audit B.
6. Only after physical validation and both audits, update the rolling checkpoint,
   docs, commit, and push. Never manufacture PASS from unresolved geometry.

1. 下一步继续 Auditability / Ownership Gate；measurement intervals、common-width、search
   graph/reachability/budget、candidate state/Pareto 与 assignment consensus 已有唯一 owner，
   separator assignment、boundary roles、candidate physical resolution 与 sequence completion
   也已独立；接着拆 result facts 与剩余 candidate construction，并把
   `solve_frame_sequence` 收敛为薄编排 facade，不增加 wrapper、re-export、重复模型或行为阈值。
2. 每个 ownership wave 都要复核 current-schema report 与相关 Debug，完整验证后独立提交并推送。
3. 之后再完成剩余物理合同、全格式样片、性能、Test/test 2 与双轮审计。
4. 未解决几何继续保持 REVIEW / 不导出；只有物理验证与双轮审计完成后才能宣称闭环。
