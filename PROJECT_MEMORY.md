# Project Memory / 项目记忆

Updated / 更新：2026-07-19

This is a concise cross-session map, not an instruction source or completion
proof. Current user intent, Git, source, original TIFFs, manual references,
current reports, Debug Analysis, and live command output remain authoritative.

本文件只是简短的跨会话地图，不是指令或完成证明。当前用户目标、Git、源码、原 TIFF、
人工 reference、current report、Debug Analysis 与现场命令始终优先。

## Frozen Checkpoint / 冻结检查点

- Branch / 分支：`main`.
- Candidate / 候选提交：`ab5a91c9`
  (`perf: reuse exact boundary window measurements`), pushed to `origin/main`.
- The tracked worktree was clean immediately after the push. Local `Test/`
  TIFFs, references, expectations, diagnostics, and `Test/test 2` remain ignored
  and untracked. / 推送后 tracked worktree 为 clean；本地 `Test/` 样片、人工记录、
  diagnostics 与 `Test/test 2` 仍是 ignored/untracked 验证资产。
- `tools/verify full` passed before commit and again in the push hook: 812 tests,
  14 format/mode configuration pairs, V4.9. / 提交前与 push hook 均通过 812 项测试、
  14 组配置与 V4.9 检查。
- Resume by checking `git log -1 --oneline`, `git status --short`, and fresh
  reports. Do not treat this snapshot as live truth. / 恢复时先核对 Git 与现场报告，
  不得把本快照当作当前证明。

## Closed Work / 已关闭工作

- The exact-search wave deduplicates equal physical aspect priors, reuses one
  boundary resolution and one role map per build, limits boundary-path matching
  by a mathematically conservative interval window, and skips full-strip-only
  completion work in partial mode. / 本轮对相同 physical aspect 去重，每个 build
  只解析一次 boundary 与 role map，以保守区间窗口筛选 boundary path，并在 partial
  模式跳过 full-only completion。
- Graph reachability now drops prefix-unreachable nodes from its backward sweep;
  lexicographic ranking stops after every row is unique; transition and
  independent-edge witnesses now share one cached best-prefix/best-suffix path
  index per graph. Direct interval comparisons replace temporary
  `PixelInterval` objects. / Graph backward sweep 只处理 prefix-reachable 节点；
  每行唯一后停止余下 rank；transition 与 independent-edge witness 在每张 graph 内
  共用一套 best-prefix/best-suffix path index；临时 interval 分配已改为等价数值比较。
- Focused dimension ordering is used only when no complete two-sided separator
  seed exists. This preserves the canonical physical order when separator proof
  is available and prevents an earlier weak grid from displacing it. / 仅在没有
  complete two-sided separator seed 时使用 focused dimension order；有 separator
  证明时保留 canonical physical order，避免弱 grid 抢先占位。
- Boundary appearance now reuses an exact local window statistic only within one
  `boundary_measurements` call. The typed key contains axis-local section,
  direction, start, and end; no count, offset, candidate, Gate, or decision is
  cached. / Boundary appearance 只在单次 `boundary_measurements` 内复用 exact
  window statistic；typed key 由 axis-local section、direction、start/end 组成，
  不缓存 count、offset、candidate、Gate 或 decision。
- Permanent contracts cover each optimization class and preserve graph witness,
  ordering, geometry, proof, and budget semantics. No execution budget was
  raised. / 永久合同覆盖上述各类，并保持 witness、排序、geometry、proof 与 budget
  语义；默认 execution budget 仍为 100,000。

## Named Physical Truth / 具名物理事实

- Fresh diagnostics at `ab5a91c9` keep `pass_X5_00006.tif` typed geometry
  unavailable (`frame_slots_unresolved`, `assignment_consensus_unresolved`),
  `REVIEW`, non-exportable, with no frame outputs. Search completed without
  budget exhaustion; the sample remains a real `pass_required` capability gap.
  / 00006 已不再 resolved-wrong，但仍是 `pass_required` capability gap。
- The user-classified `Test/135/full/unknown_X5_00038.tif` is the canonical
  identity. Fresh diagnostics keep it typed geometry unavailable
  (`assignment_consensus_unresolved`), `REVIEW`, non-exportable, with no frame
  outputs; authority validation classifies it as conforming. / 00038 的当前事实是
  `unknown`，不是 `pass`；当前结果为 conforming 的 unresolved/REVIEW/不可导出。
- Both fresh Debug Analysis images say `NOT EXPORTABLE` and show provisional
  slots only. / 两张 Debug Analysis 均明确标注 `NOT EXPORTABLE`，只展示 provisional
  slots。

## Real-Sample Authority / 真实样片权限

- Local dataset: 113 TIFFs, 113 expectations, 111 manual geometry references;
  the two `review_required` samples intentionally have no reference. The manifest
  validator reports `samples=113 references=111 expectations=valid`. / 本地数据为
  113 张 TIFF、113 条 expectation、111 条人工 geometry reference；两张
  `review_required` 有意保持 reference 为空。
- `half/partial/pass_X5_00001` and `120-66/partial/pass_X5_00005` are still
  `pass_required`, but their allowed observations cannot independently prove the
  manual geometry even after complete high-budget searches. Their
  `observation_proof_expectation` is therefore
  `independent_proof_unavailable`; validators must report an explicit
  evidence-contract conflict rather than loosen a Gate. / 这两张仍保持
  `pass_required`，但允许观测无法独立证明人工 geometry，必须显式报告
  evidence-contract conflict，不得放宽 Gate。
- The prior 113-report authority summary predates those two expectation
  corrections and is stale. Generate a fresh complete diagnostics set before
  quoting aggregate conforming/gap/conflict counts. / 旧的 113-report 汇总早于上述
  两项事实修正，已经过时；引用全量统计前必须重新生成当前报告。

## Performance State / 性能状态

- Frozen command / 固定命令：

  ```bash
  python3 X5_Crop.py Test/half/partial/pass_X5_00001.tif \
    --format half --strip partial --count 11 --deskew off \
    --diagnostics --jobs 1 -o <output>
  ```

- With the unchanged 100,000 budget, frozen HEAD `7c38962c` took 9.04 s
  detection and 102,974 assignment evaluations; `4c48147c` took 5.95 s and
  101,127 evaluations, about 34% faster. The current report comparison is zero
  diff and Debug Analysis is byte-identical. / 同一 10 万预算下 detection 从
  9.04 s 降至 5.95 s（约 34%）；report 0 diff，Debug Analysis 字节一致。
- On fixed `120-66/partial/pass_X5_00011`, count 3 and the same 100,000
  budget, comparable cProfile detection fell from 10.52 s to 9.00 s. Graph
  witness cumulative time fell from 2.58 s to 0.96 s and function calls from
  39.00 M to 33.66 M; assignment evaluations remain exactly 106,989, the report
  has zero diff, and Debug is byte-identical. / 固定 00011/count 3 的同预算 profile
  中，detection 从 10.52 s 降至 9.00 s，graph witness 从 2.58 s 降至 0.96 s，
  function calls 从 39.00 M 降至 33.66 M；evaluation、report 与 Debug 均未改变。
- On the same 00011 profile, typed exact-window reuse reduced physical window
  measurements from 2,920 to 2,782 and detection from 9.00 s to 8.90 s.
  Assignment evaluations remain 106,989; report and Debug remain identical. /
  同一 00011 profile 的 window measurement 从 2,920 降至 2,782，detection 从
  9.00 s 降至 8.90 s；evaluation、report 与 Debug 不变。该小波次不关闭预算问题。
- The fixed sample remains typed `search_budget_exhausted`, geometry unavailable,
  `REVIEW`, and non-exportable. A complete 742,637-evaluation probe still had no
  independent proof, so more budget is not reliability evidence. / 固定样片仍为
  typed budget exhaustion；完整搜索也没有独立 proof，增加预算不能成为可靠性证据。
- Rejected routes remain rejected: heuristic branch caps, witness removal,
  candidate/decision caching, Gate loosening, or treating budget/appearance/grid
  as proof. / 继续禁止 heuristic branch cap、删除 witness、缓存 candidate/decision、
  放宽 Gate，或把 budget/appearance/grid 当作证明。

## Next Actions / 下一步

1. Continue exact performance closure on the remaining `pass_required`
   budget-exhausted samples. Distinguish a completed-search evidence conflict
   from an optimization opportunity; do not alter proof authority. / 继续关闭其余
   `pass_required` budget exhaustion，并区分完整搜索后的证据冲突与可优化空间。
2. Re-run the frozen sample and named 00006/00038 reports, reference validation,
   Debug inspection, and `tools/verify full` after every accepted wave. / 每个
   接受波次都复核固定样片、00006/00038、reference、Debug 与 full verifier。
3. Generate a fresh complete 113-TIFF diagnostics set only after the physical and
   performance candidate is frozen. Rebuild stale `Test/test 2` afterward while
   preserving `Test/test 1`. / 物理与性能候选冻结后再生成 113 张当前 diagnostics，
   随后重建 `Test/test 2`，保持 `Test/test 1` 不变。
4. Start Audit A only from a clean, verified, committed, pushed candidate. Any
   root fix invalidates it. Leave Audit B as a context-independent prompt for a
   new task; do not execute it here. / Audit A 只能从 clean/pushed 候选开始；任何
   根修复都会使其失效。Audit B 只留下新任务 Prompt，本任务不得执行。
