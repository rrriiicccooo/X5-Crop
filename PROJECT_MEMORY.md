# Project Memory / 项目记忆

Updated / 更新：2026-07-21

This is a concise cross-session map, not an instruction source or completion
proof. Current user intent, Git, source, original TIFFs, manual references,
current reports, Debug Analysis, and live command output remain authoritative.

本文件只是简短的跨会话地图，不是指令或完成证明。当前用户目标、Git、源码、原 TIFF、
人工 reference、current report、Debug Analysis 与现场命令始终优先。

## Frozen Checkpoint / 冻结检查点

- Branch / 分支：`main`.
- Candidate / 候选提交：`e69d2175`
  (`fix: resolve photo-bounded separator consensus`), pushed to `origin/main`;
  it includes the preceding pushed performance commit `bfd259ee`
  (`perf: index graph option facts once`). / 当前候选为 `e69d2175`，已推送到
  `origin/main`；其中包含此前已推送的性能提交 `bfd259ee`。
- `HEAD` and `origin/main` are both `e69d2175`; the branch has no unpushed
  commits. / 当前 `HEAD` 与 `origin/main` 均为 `e69d2175`，没有未推送提交。
- The tracked worktree was clean immediately after the push. Local `Test/`
  TIFFs, references, expectations, diagnostics, and `Test/test 2` remain ignored
  and untracked. / 推送后 tracked worktree 为 clean；本地 `Test/` 样片、人工记录、
  diagnostics 与 `Test/test 2` 仍是 ignored/untracked 验证资产。
- `tools/verify full` passed before the memory update and again in the push hook:
  815 tests, 14 format/mode configuration pairs, V4.9. / 记忆更新前与 push hook
  均通过 815 项测试、14 组配置与 V4.9 检查。
- `Test/test 2` is still the prior ignored validation set and has not been replaced;
  it must be rebuilt only after a fresh all-113 current-schema run. / `Test/test 2`
  仍是此前的 ignored 验证集，尚未替换；必须在当前 schema 的 113 张全量诊断完成后再重建。
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
- Lexicographic graph ranking carries the exact still-ambiguous row indexes between
  criteria, so each criterion performs one ambiguity reduction rather than two. The helper
  has one current-only typed input/output shape; no compatibility branch remains. / Graph
  字典序 ranking 在 criterion 之间传递精确的仍并列 row index，使每项只做一次 ambiguity
  reduction；helper 只有一套 current-only typed 输入输出，没有兼容分支。
- Permanent contracts cover each optimization class and preserve graph witness,
  ordering, geometry, proof, and budget semantics. No execution budget was
  raised. / 永久合同覆盖上述各类，并保持 witness、排序、geometry、proof 与 budget
  语义；默认 execution budget 仍为 100,000。
- `e69d2175` canonicalizes separator-binding topology by boundary index and
  observation identity, and uses the actual binding count. Only a `full` strip
  with a photo-edge-bounded shared short axis, at most one missing internal
  separator, and strict-majority binding coverage may let the near-complete
  topology own consensus; holder-bounded, partial, and one-of-two cases retain
  alternatives. / `e69d2175` 按 boundary index 与 observation identity 规范化
  separator-binding topology，并使用真实 binding 数量；只有 `full`、photo-edge-bounded
  shared short axis、内部最多缺一个 separator 且覆盖严格多数时，近完整 topology 才能拥有
  consensus；holder-bounded、partial 与二选一情形继续保留替代解。

## Named Physical Truth / 具名物理事实

- Fresh diagnostics at `e69d2175` keep `pass_X5_00006.tif` typed geometry
  unavailable (`frame_slots_unresolved`, `assignment_consensus_unresolved`),
  `REVIEW`, non-exportable, with no frame outputs. Search completed without
  budget exhaustion; the sample remains a real `pass_required` capability gap.
  / 00006 已不再 resolved-wrong，但仍是 `pass_required` capability gap。
- Fresh `135/full` diagnostics at `e69d2175` promote
  `pass_X5_00001.tif` and `pass_X5_00003.tif` to reference-matched automatic
  PASS. The 48-sample run completed 48/48 with 11 approved and 37 review; the
  other provisional cases remained protected by REVIEW. / `e69d2175` 的新鲜
  `135/full` diagnostics 将 `00001` 与 `00003` 提升为符合人工 reference 的自动 PASS；
  48 张全部完成，其中 11 张 approved、37 张 review，其余 provisional 结果继续由 REVIEW 保护。
- The user-classified `Test/135/full/unknown_X5_00038.tif` is the canonical
  identity. Fresh diagnostics keep it typed geometry unavailable
  (`assignment_consensus_unresolved`), `REVIEW`, non-exportable, with no frame
  outputs; authority validation classifies it as conforming. / 00038 的当前事实是
  `unknown`，不是 `pass`；当前结果为 conforming 的 unresolved/REVIEW/不可导出。
- Cross-format controls remain unresolved and non-exportable after the same wave:
  `half/full/pass_X5_00007`, `120-67/full/pass_X5_00002`, and
  `135/partial/pass_X5_00001`; their reference checks show no violation. / 同一波次的
  跨格式控制样片仍为 unresolved、不可导出，且 reference 无 violation。
- Fresh targeted Debug Analysis keeps the two new PASS cases physically aligned;
  `unknown_X5_00038` remains marked `NOT EXPORTABLE` with provisional slots only. /
  新 PASS 的 Debug Analysis 与物理边界一致；`unknown_X5_00038` 仍明确标注
  `NOT EXPORTABLE`，只显示 provisional slots。

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
- The latest assembled candidate authority check reports
  `samples=113 conforming=53 capability_gap=58 evidence_contract_conflict=2
  violation=0`. It combines fresh current `135/full` reports with the existing
  `Test/test 2` rows for the other configurations, so it is directional evidence,
  not the final all-113 freeze proof. A fresh all-113 current-schema run is still
  required before replacing `Test/test 2`. / 当前拼接候选权限检查为
  `113 / conforming 53 / capability gap 58 / evidence conflict 2 / violation 0`；
  其中 `135/full` 是当前新报告，其余配置仍使用现有 `Test/test 2` 行，因此只能作为方向性证据，
  不能作为最终 113 张冻结证明；替换 `Test/test 2` 前仍需用当前 schema 全量重跑。

## Performance State / 性能状态

- Frozen command / 固定命令：

  ```bash
  python3 X5_Crop.py Test/half/partial/pass_X5_00001.tif \
    --format half --strip partial --count 11 --deskew off \
    --diagnostics --jobs 1 -o <output>
  ```

- Isolated same-condition 113-sample benchmark: release `v4.2.8` took
  276.63 s with 60 automatic PASS cases, of which 44 matched geometry and 16
  were wrong; V4.9 baseline took 495.17 s with 29 automatic PASS cases, all 29
  geometrically correct and 82 unresolved. / 同条件 113 张隔离实测：发布版
  `v4.2.8` 用时 276.63 秒、60 张自动 PASS，其中 44 张几何正确、16 张错误；V4.9 基线
  用时 495.17 秒、29 张自动 PASS，29 张均几何正确，另有 82 张 unresolved。
- `bfd259ee` records a 2.6% real speedup on the fixed half/partial sample by
  indexing exact graph option facts once. The e69 correctness wave makes no
  unmeasured performance claim; full performance acceptance remains open. /
  `bfd259ee` 在固定 half/partial 样片上通过一次索引 exact graph option facts 获得 2.6% 实测
  加速；e69 正确性波次未宣称未经测量的性能收益，全量性能验收仍未关闭。
- The following exact-search timings are historical provenance from earlier
  optimization waves, not measurements of current `HEAD`. / 以下 exact-search 用时是
  早期性能波次的历史证据，不代表当前 `HEAD` 的新实测。

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
- On the same complete fixed count-11 search, detection fell from 66.34 s to 63.02 s while
  preserving 750,766 total assignment evaluations, current selection/Decision/output, and a
  byte-identical Debug Analysis JPG. The default-budget run remains 5.96 s detection and
  101,127 evaluations, so this exact wall-time wave does not close budget acceptance. / 同一
  count-11 完整搜索的 detection 从 66.34 s 降至 63.02 s，保持 750,766 次总 evaluation、
  current selection/Decision/output 与字节一致 Debug；默认预算仍为 5.96 s、101,127 次，
  因此本轮 exact 墙钟优化尚未关闭 budget 验收。
- Rejected probes: unioning all width hypotheses reduced evaluations but changed provisional
  slots/common width/Debug; reverse-first or per-graph direction choice saved too little;
  whole-branch and monotonic prefilters either cost more than they saved or removed only 53 of
  19,039 options; cross-branch option/edge/path-state identities had no exact reusable matches.
  / 已否决：全宽度联合会改变 provisional geometry/Debug；反向或逐图方向选择收益不足；
  whole-branch 与单调预筛成本过高或仅移除 19,039 项中的 53 项；跨分支 option/edge/path
  state 没有可合法复用的精确重复。
- Rejected routes remain rejected: heuristic branch caps, witness removal,
  candidate/decision caching, Gate loosening, or treating budget/appearance/grid
  as proof. / 继续禁止 heuristic branch cap、删除 witness、缓存 candidate/decision、
  放宽 Gate，或把 budget/appearance/grid 当作证明。

## Next Actions / 下一步

1. Classify and close the remaining 58 capability gaps without promoting the 30
   provisional geometries that already compare wrong against manual references;
   keep the two evidence-contract conflicts explicit. / 分类并关闭剩余 58 个 capability
   gaps，但不得提升与人工 reference 冲突的 30 个 provisional geometry；两项 evidence-contract
   conflict 继续显式保留。
2. Re-run the fixed performance samples, 00006/00038, cross-format controls,
   reference validation, Debug inspection, and `tools/verify full` after every
   accepted wave. / 每个接受波次都复核固定性能样片、00006/00038、跨格式控制、reference、
   Debug 与 full verifier。
3. After the physical and performance candidate is frozen, run a fresh complete
   113-TIFF current-schema diagnostics set and replace `Test/test 2` while
   preserving `Test/test 1`. / 物理与性能候选冻结后，用当前 schema 全量重跑 113 张 diagnostics，
   再替换 `Test/test 2`，保持 `Test/test 1` 不变。
4. Start Audit A only from a clean, verified, committed, pushed candidate; any
   root fix invalidates it. Then run the independent Audit B freeze review. /
   Audit A 只能从 clean/verified/committed/pushed 候选开始；任何根修复都会使其失效，之后再运行
   独立 Audit B 冻结审查。
