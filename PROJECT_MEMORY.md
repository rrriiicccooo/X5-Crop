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
  Debug 和文档，但物理校准、样片复核、性能对比和双轮架构审计尚未完成。
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
  with 739 unit/contract tests, 14 format/mode configuration pairs, compile,
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

- 当前 `tools/verify full` 已通过 739 项 unit/contracts、14 组配置、compile、macOS shell syntax、
  diff hygiene、发布包构建和版本检查；它仍不能证明具名样片几何、性能闭环、Debug 视觉正确性或
  两轮架构审计。
- sample-expectation 单元测试只验证加载器和契约代码；当前本地 `pass_X5_00038.tif` 记录仍缺少
  必需的自身 geometry reference，在获得真实证据前不得称该本地数据集已验证。

## Remaining Physical Work / 未完成物理工作

- `pass_X5_00007`: sequence proof unavailable and output protection unresolved.
- `pass_X5_00013`, `pass_X5_00018`, `pass_X5_00019`, `pass_X5_00032`:
  assignment consensus remains unresolved. `00018` is the representative
  common-width grouping failure; broad uncertainty must not bridge mutually
  exclusive narrow width groups.
- `pass_X5_00031`: common frame width and frame slots remain unresolved.
- Representative geometry that looks visually correct is not enough when another
  non-dominated, weaker dimension-heavy explanation remains.

以上样片仍需当前报告和 Debug Analysis 逐张复核；肉眼正确的代表解不能覆盖仍存在的非支配、
dimension-heavy 替代解释。

## Next Actions / 下一步

1. Re-anchor from the clean checkpoint: read `AGENTS.md`, this file,
   `ARCHITECTURE.md`, current source, and the latest report/Debug artifacts; do
   not reconstruct the old model from chat history.
2. Add a focused failing contract for broad uncertainty bridging mutually
   exclusive narrow common-width groups, then fix canonical contributor
   selection without format-specific thresholds or weighted scores.
3. Recheck `pass_X5_00013/18/19/32`, then `pass_X5_00007/31`, using geometry,
   current reports, and Debug Analysis—not PASS totals alone.
4. Run the full contracts, all 14 configurations, representative/all available
   format-mode samples, current-schema validation, and a fixed-sample performance
   comparison.
5. Audit active runtime, tests, fixtures, helpers, reports, and Debug twice with
   the same frozen checklist: forward Audit A, then a fresh-context reverse-order
   Audit B.
6. Only after physical validation and both audits, update the rolling checkpoint,
   docs, commit, and push. Never manufacture PASS from unresolved geometry.

1. 从干净检查点重新锚定当前文件和产物，不从旧聊天重建旧模型。
2. 先锁定宽 uncertainty 桥接互斥窄宽度组的失败合同，再修复 canonical contributor selection；
   不得加入格式专用阈值或 weighted score。
3. 逐张复核指定样片及其当前报告和 Debug，然后完成全套配置、格式样片、schema、性能和双轮审计。
4. 只有物理验证与两轮审计都完成后，才能更新检查点并宣称闭环。
