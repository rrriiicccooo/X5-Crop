# X5 Crop 更新日志 / Changelog

本文件只记录版本级行为、验证范围和回滚背景。当前架构见 `ARCHITECTURE.md`，用户操作见
`README.md`，跨会话任务状态见 `PROJECT_MEMORY.md`。

This file records version-level behavior, validation scope, and rollback context
only. See `ARCHITECTURE.md` for the current design, `README.md` for user guidance,
and `PROJECT_MEMORY.md` for the rolling task checkpoint.

当前开发版本 / Active development: **V4.9**
当前稳定发布 / Stable release: **v4.2.8**

## V4.9 当前开发线 / Current Development Line

V4.9 是破坏性、current-only 的物理模型与源码重构。历史 PASS/REVIEW、报告字段和裁切几何不是
兼容目标；真实 TIFF、当前报告、Debug Analysis 与当前合同才是验证依据。

V4.9 is a breaking, current-only physical-model and source rewrite. Historical
PASS/REVIEW outcomes, report fields, and crop geometry are not compatibility
targets; real TIFFs, current reports, Debug Analysis, and current contracts are
the validation evidence.

### 2026-07-19 — 无环观测权限 / Acyclic Observation Authority

- 共同 frame width 现在要求实测宽度具有非空共享区间；不相交宽度不能再被宽 uncertainty
  envelope 合并并获得 dimension-sequence proof。`135/partial/review_X5_00002` 因而从错误的
  自动通过恢复为不可导出的 `REVIEW`。 / Common frame width now requires a non-empty
  shared interval across measured widths; disjoint widths can no longer be merged by a
  broad uncertainty envelope and gain dimension-sequence proof. Consequently,
  `135/partial/review_X5_00002` returned from a false automatic approval to
  non-exportable `REVIEW`.
- Candidate resolution 现在先验证 proposed gray-path boundary 的正 slot extent，再构造
  `FrameSlot`；宽度跨过 0 的 band 不能成为 separator binding/assignment。Common-width 与
  candidate-local content-continuity/spacing identity 也纳入完整物理输入与测量权限，避免不同
  观测或 authority 共用同一 ID。越过 holder 的可见 slot 会在 solver 内成为 typed
  constraints failure，不再流入最终模型触发 runtime error。 /
  Candidate resolution now verifies positive slot extent before constructing a
  `FrameSlot`, and a band whose width crosses zero cannot become a separator binding or
  assignment. Common-width and candidate-local content-continuity/spacing identities also
  include their complete physical inputs and measurement authority so distinct observations
  or authorities cannot share one ID. Visible slots outside the holder now become a typed
  solver constraint failure instead of reaching the final model as a runtime error.
- 真实样片期望现在分别记录人工 geometry reference、允许灰度观测的独立 proof 预期与自动
  decision 预期；文件名前缀只拥有 dataset intent，不能再作为 decision oracle。 /
  Real-sample expectations now record manual geometry reference, independent-proof
  expectation for allowed grayscale observations, and automatic-decision expectation
  separately; filename prefixes own dataset intent only and are no longer decision oracles.
- 新的 real-sample validator 对齐仓库相对人工记录与 runtime 绝对 source，并把 current report
  判定为 conforming、capability gap、evidence-contract conflict 或 physical violation；
  unresolved export、resolved-wrong、review-required 自动通过和 runtime/schema failure 均不能
  被标签掩盖。 / A new real-sample validator aligns repository-relative manual records with
  absolute runtime sources and classifies each current report as conforming, a capability
  gap, an evidence-contract conflict, or a physical violation; labels cannot hide unresolved
  export, resolved-wrong geometry, review-required auto approval, or runtime/schema failure.
- `MeasurementProvenance` 现在拒绝 root 同时出现在 dependencies 中；content、
  frame geometry、photo-edge role、spacing 和 dual-lane containment 的派生路径已清理同类
  自循环。 / `MeasurementProvenance` now rejects its root appearing again in
  dependencies; derived content, frame-geometry, photo-edge-role, spacing, and
  dual-lane-containment paths no longer create the same self-cycle.
- Current-report validation now rejects one `ObservationId` carrying conflicting
  provenance, so duplicated identity cannot silently merge different physical
  observations. / Current report 现在拒绝同一 `ObservationId` 对应不同
  provenance，不允许重复 identity 静默合并不同物理观测。
- Final frame-sequence identity now rejects a separator assignment whose matching
  signed spacing is not `OBSERVED`, positive, non-geometric, and traceable to the
  assigned band, or whose cross-axis continuity was measured on a different
  short-axis span. / 最终 frame-sequence identity 现在拒绝与 assigned band 不可追溯、
  不是正值 `OBSERVED`、仍由 geometry hypothesis 授权，或跨轴连续性来自其他短轴 span 的
  separator assignment。
- Holder occlusion now requires a positive hidden extent and is restricted to
  the first slot's leading side or final slot's trailing side. / Holder occlusion
  现在必须隐藏正宽度，并且只能作用于首 slot 的 leading side 或尾 slot 的 trailing side。
- Content continuity can corroborate overlap only across independently measured
  physical boundary roles; repeated-width geometry can no longer gain overlap
  output-protection authority through content. / Content continuity 只能佐证两侧
  physical role 已独立测得的 overlap；repeated-width geometry 不能再借 content 获得
  overlap 输出保护权限。
- Canonical measured-frame and graph-path selection now rank physical support,
  observation quality, and measurement uncertainty before search hints; hints
  can order work but cannot choose the retained observation identity or graph
  predecessor. / Measured-frame 规范化与 graph-path 选择现在先比较物理支持、
  观测质量和测量不确定度，再比较 search hint；hint 只能安排搜索顺序，不能决定保留哪条
  观测 identity 或 graph predecessor。
- Assignment consensus now treats measured-versus-inferred slot identity as a
  real topology disagreement even when both alternatives occupy the same
  coordinates. / 即使两个替代解坐标完全相同，assignment consensus 也会把 measured
  slot 与 sequence-inferred slot 的身份差异保留为真实 topology disagreement。
- Candidate geometry clustering now preserves sequence-inferred slot identity
  and mutually exclusive visible extents instead of merging them by nominal
  boundary coordinates alone. / Candidate geometry clustering 现在同时保留
  sequence-inferred slot 身份与互斥 visible extent，不再只按 nominal boundary 坐标合并。
- Repeated-width boundary roles are now excluded from single-frame proof,
  single-frame geometry resolution, evidence-independence support, and measured
  frame-scale observations. / Repeated-width boundary role 现在不能进入单帧 proof、
  单帧 geometry resolution、evidence-independence support 或 measured frame-scale
  observation。
- REVIEW 导出现在同时要求 resolved geometry 与 feasible `FrameBleedPlan`；
  `--export-review` 不能绕过 unresolved overlap protection。Report validation、Debug
  和实际 writer 共用同一 export eligibility，且 current report 拒绝不可导出状态下声称存在
  frame outputs。 / REVIEW export now requires both resolved geometry and a feasible
  `FrameBleedPlan`; `--export-review` cannot bypass unresolved overlap protection.
  Report validation, Debug, and the writer share one export eligibility,
  whose positive reason is `geometry_resolved_output_protected`; current reports
  reject claimed frame outputs while export is ineligible.
- Report-based analysis reuse 已删除：runtime 不再从旧 report 恢复 Candidate、Gate、Decision 或
  final geometry，`--no-reuse-analysis`、相关 config、FailureStage 与 schema 状态也同步删除。
  Current report 只保留 `analysis_identity` 供审计与 regression 定位；每次运行重新检测，只有运行内
  exact、count/offset-independent measurement 可以缓存。 / Report-based analysis reuse was
  removed: runtime no longer restores Candidate, Gate, Decision, or final geometry
  from an earlier report, and `--no-reuse-analysis` plus its config, FailureStage,
  and schema state were deleted in the same change. Current reports retain only
  `analysis_identity` for audit and regression identity; every run detects afresh,
  and only exact, count/offset-independent measurements may be cached in-run.
- 在输出目录预置旧 report 后，00007 的普通运行仍执行 fresh detection（1 个 assessed candidate、
  13,557 次 assignment evaluation），并写入新的 `analysis_identity` report。六张冻结样片的
  selection、Decision、output 物理字段保持一致，Debug JPG 字节一致。 / With an earlier report
  pre-seeded in the output directory, a normal 00007 run still performed fresh
  detection (one assessed candidate and 13,557 assignment evaluations) and wrote a
  new `analysis_identity` report. The six frozen samples preserved selection,
  Decision, and physical output fields, with byte-identical Debug JPGs.
- 初始 provenance/sequence-conservation 波次使六张冻结 `135/full` 样片的循环
  provenance 由 55 降为 0，同时保持 canonical report 零差异和 Debug Analysis 字节一致。 /
  The initial provenance and sequence-conservation waves reduced cyclic
  provenances from 55 to zero across the six frozen `135/full` samples while
  preserving canonical reports and Debug Analysis bytes.
- 随后的 repeated-width 权限清理按物理事实移除了 00007/13/18/19/31 中依赖 pattern 的
  measured frame-scale/independence 记录；00031 新增 `evidence_independence_failed`，只有其
  Debug 标题改变，几何框未变。六张样片仍全部 `REVIEW` / 不导出。 / The later
  repeated-width authority cleanup removed pattern-dependent measured
  frame-scale and independence records from 00007/13/18/19/31; 00031 gained
  `evidence_independence_failed`, with only its Debug header changing and all
  geometry boxes preserved. All six samples remain `REVIEW` / non-exportable.
- 六张冻结 `135/full` 样片的 selection、DecisionGate、FrameBleedPlan、crop envelopes 与
  final boxes 保持逐字段一致；00007 仅修正 export eligibility 和 Debug 输出权限表达：保留
  FrameCropEnvelope，但不再绘制未受保护的 final boxes，真实 `--export-review` 运行没有写出
  frame TIFF；其余五张 Debug 只改变公共图例文字，几何像素一致。 / Across the six
  frozen `135/full` samples, selection, DecisionGate, FrameBleedPlan, crop
  envelopes, and final boxes remained field-identical; 00007 changed only export
  eligibility and Debug output-authority rendering, retaining FrameCropEnvelope
  while omitting unprotected final boxes, and an actual `--export-review` run wrote
  no frame TIFF. The other five Debug images changed only the shared legend text;
  their geometry pixels remained identical.
- 完整验证通过 769 项 current-only 测试和 14 组配置；旧 reuse/restoration 专属测试与死模块已删除。 /
  Full verification passed 769 current-only tests and 14 configuration pairs;
  obsolete reuse/restoration-only tests and the unreachable module were deleted.

### 2026-07-15 — 共享短轴与 Frame Slot / Shared Short Axis And Frame Slots

- 每条片条先解析一个共享安全短轴，再由全局 solver 联合解析有序 frame slots、共同宽度、
  separator assignments、片间关系与共识。 / Each strip resolves one shared safe short axis before
  the global solver resolves ordered frame slots, common width, separator assignments, spacing,
  and consensus.
- Full 序列最多允许一个由完整已解决序列唯一推导的空白 slot；缺少内容不能证明空白，也不能
  移动实测真实边界。 / A full sequence may contain at most one blank slot uniquely inferred from a
  resolved sequence; missing content neither proves the blank nor moves measured real boundaries.
- Report、Debug、cache reuse 和 regression reference 迁移到 current-only
  `frame_slot_sequence_resolution`。 / Reports, Debug, cache reuse, and regression references moved
  to the current-only `frame_slot_sequence_resolution` schema.
- 新模型使此前的 architecture-closure candidate 失效；必须重新完成物理验证、性能对比和两轮
  冻结清单审计。 / The new model invalidated the earlier architecture-closure candidate and requires
  fresh physical validation, performance comparison, and two frozen-checklist audits.

### 2026-07-14 — 权限、证据与性能收敛 / Authority, Evidence, And Performance

- 配置只在 runtime boundary 解析；检测下层不再读取 registry、scan calibration 或隐式默认值。 /
  Configuration resolves only at the runtime boundary; lower detection layers no longer query
  registries, scan calibration, or implicit defaults.
- TIFF resolution 只保留为输入/报告 metadata；候选内比例诊断不能反向证明生成它的同一几何。 /
  TIFF resolution remains input/report metadata only; candidate-local scale diagnostics cannot prove
  the geometry that produced them.
- 搜索结果区分 resolved、物理矛盾、测量不可用与 budget exhaustion；预算状态不再伪装成可靠性。 /
  Search distinguishes resolved geometry, physical contradiction, unavailable measurement, and budget
  exhaustion; execution state no longer masquerades as reliability.
- Pareto 归约只删除真正被逐边收窄的 geometry；宽 uncertainty 不能桥接并吞掉互斥窄解。 /
  Pareto reduction removes only genuinely refined geometry; broad uncertainty cannot bridge and erase
  mutually exclusive narrow solutions.
- Exact measurement 可按 typed identity 复用；candidate、Gate、decision 和近似几何不缓存。 /
  Exact measurements may be reused by typed identity; candidates, gates, decisions, and approximate
  geometry are never cached.
- 代表性热点在保持 unresolved 语义和 current-schema 输出的前提下显著降时；性能变化不授予物理
  权限。 / Representative hotspots were reduced while preserving unresolved semantics and current-schema
  output; performance never grants physical authority.

### 2026-07-13 — 灰度物理观测与联合序列 / Grayscale Observation And Joint Sequence

- Detection 收敛为一个 canonical grayscale workspace；颜色、材料标签和穿孔不参与检测证明。 /
  Detection converged on one canonical grayscale workspace; color, material labels, and perforations
  do not participate in proof.
- Boundary paths 成为带轨迹和 uncertainty 的二维观测；separator start/end 分别约束相邻 frame
  边界。 / Boundary paths became two-dimensional tracked observations with uncertainty; separator
  start/end constrain the adjacent frame boundaries separately.
- Content 只反证遗漏或裁断，不能创建、移动或收缩几何；同一观测与覆盖计算供 solver 和最终
  evidence 使用。 / Content may reject omission or clipping but cannot create, move, or shrink geometry;
  the solver and final evidence share the same observation and coverage calculation.
- Holder identity、assignment consensus 和 overlap support 都要求真实共同空间区间；单条宽路径不能
  抹平互斥 transition。 / Holder identity, assignment consensus, and overlap support require genuine
  shared spatial intervals; one broad path cannot erase mutually exclusive transitions.

### 2026-07-12 — 物理序列与决定合同 / Physical Sequence And Decision Contracts

- Candidate assessment、geometry resolution、selection、final decision 和 output finalization 分离；
  最终状态只由最终 decision 层创建。 / Candidate assessment, geometry resolution, selection, final
  decision, and output finalization are separate; only the final decision layer creates status.
- Format 只表达物理规格，不拥有算法分支；adaptive measurement 参数、runtime configuration 与报告
  描述保持分离。 / Formats describe physical specifications rather than algorithm branches; adaptive
  measurement parameters, runtime configuration, and report descriptions remain separate.
- 未解决 geometry 不可导出；`--export-review` 只允许已有 resolved geometry 的 REVIEW 输出。 /
  Unresolved geometry is never exportable; `--export-review` applies only to REVIEW results with resolved
  geometry.
- Output bleed 成为逐 boundary 计划，不再用全局最大值扩大无关 frame。 / Output bleed became a
  per-boundary plan rather than a global maximum applied to unrelated frames.

### 2026-07-11 — 模块化源码与 current-only schema / Modular Source And Current-Only Schema

- `X5_Crop.py` 保持薄入口，V4+ 开发源码迁移到分层 `x5crop/`；发布构建仍生成单文件脚本。 /
  `X5_Crop.py` remains a thin entry while V4+ development lives in layered `x5crop/`; release builds
  still generate one standalone script.
- Report、Debug、tests、tools 和 cache reuse 使用同一 current schema，不再重建缺失决定或保留旧字段。 /
  Reports, Debug, tests, tools, and cache reuse consume one current schema and no longer reconstruct
  missing decisions or retain superseded fields.
- Repository-owned hooks enforce staged-file hygiene and full pre-push validation while preserving Git
  LFS behavior. / 仓库自有 Hook 在保留 Git LFS 行为的同时执行 staged-file hygiene 与完整 pre-push
  验证。

## 当前验证边界 / Current Validation Boundary

- `tools/verify full` 是 unit contracts、compile、configuration consistency、macOS shell syntax、diff
  hygiene 和版本检查的统一入口。 / `tools/verify full` is the single entry for unit contracts, compile,
  configuration consistency, macOS shell syntax, diff hygiene, and version checks.
- GitHub Actions、pre-commit 与 pre-push 只调用该入口或其 staged/pre-push 模式。 / GitHub Actions,
  pre-commit, and pre-push are thin adapters around that verifier.
- 绿色测试不能代替具名 TIFF 的当前报告与 Debug 复核；精确暂停状态和剩余样片见
  `PROJECT_MEMORY.md`。 / Green tests do not replace current-report and Debug review of named TIFFs;
  the precise checkpoint and remaining samples live in `PROJECT_MEMORY.md`.
- 旧的 architecture-closure、测试数量和样片统计只描述对应提交与运行产物，不自动适用于当前
  checkout。 / Previous closure labels, test counts, and sample totals apply only to their identified
  commit and run artifacts, never automatically to the current checkout.

## 版本摘要 / Version Summary

| Version / 版本 | Status / 状态 | Summary / 摘要 |
|---|---|---|
| V4.9 | Active development / 当前开发 | Typed physical frame-sequence model and current-only architecture / typed 物理 frame sequence 与 current-only 架构 |
| V4.7 | Previous development / 旧开发线 | Thin entry and modular `x5crop/` layering / 薄入口与模块化源码分层 |
| V4.6 | Historical development / 历史开发 | Policy-driven detection structure / policy 驱动检测结构 |
| V4.3–V4.5 | Historical development / 历史开发 | Full/partial, 120, half-frame, diagnostics, and candidate experiments / 模式、格式、诊断与候选实验 |
| V4.2.8 | Stable release / 稳定发布 | Partial-only count prompt; Return/`auto` enables automatic count / 仅 partial 询问张数，回车或 `auto` 自动判断 |
| V3–V4.2 | Historical / 历史 | Early workflow, format parameters, and geometry experiments / 早期流程、格式参数与几何实验 |

## 发布政策 / Release Policy

- GitHub Releases 是用户下载渠道；`main` 可以领先稳定发布。 / GitHub Releases are the user
  download channel; `main` may lead the stable release.
- `tools/release_manifest.py` 是发布包内容的唯一清单，`tools.build_release` 生成 standalone script
  和 UTF-8 zip。 / `tools/release_manifest.py` is the single package manifest; `tools.build_release`
  generates the standalone script and UTF-8 zip.
- 用户包不含模块化源码、测试、内部文档、诊断启动器、本地样片或生成输出。 / User packages exclude
  modular source, tests, internal docs, diagnostics launchers, local samples, and generated output.
