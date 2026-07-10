# X5 Crop 更新日志 / Changelog

本文件记录版本级变化、验证记录、发布策略和回滚线索。运行流程架构和源码分层架构见
`ARCHITECTURE.md`；用户操作说明见 `README.md` 和 `快速启动_Quick_Start.md`。

This file records version-level changes, validation records, release policy, and
rollback context. Runtime-flow and source-layer architecture live in
`ARCHITECTURE.md`; user instructions live in `README.md` and
`快速启动_Quick_Start.md`.

当前 active 脚本版本：V4.9

当前稳定发布版本：v4.2.8

Current active script version: V4.9

Current stable release: v4.2.8

## 中文更新日志

### 记录范围

本文件只记录对版本判断有价值的信息：

- 用户可见行为变化。
- 大的源码结构里程碑。
- 验证命令、验证范围和未完成验证项。
- 发布包策略和回滚线索。

源码层级和运行流程说明写在 `ARCHITECTURE.md`；当前 handoff 写在 `AGENTS.md`。

### 当前开发线：V4.9

V4.9 是当前 active development 线。它继承 V4.7 的源码分层成果，并继续把检测逻辑整理为
可审核的 evidence / policy / decision 结构。

当前版本口径：

- V4.5.4 / V4.7 reference reports 是历史参考和 diff 定位工具，不是验收 oracle。
- 当前项目阶段允许任何历史 reference diff；diff 本身不阻断验收。
- `status`、`confidence`、`final_review_reasons`、`outer_box`、`frame_boxes`、`gaps`、
  `runtime_policy_detail` 和 report record / schema fields 都可以出现 diff；需要时记录原因和涉及层级。
- current-schema raw compare 用于定位变化，不用于把 diff 自动判为失败。
- TIFF metadata、位深、ICC、resolution 和已知无损压缩行为仍属于用户输出质量边界。

### V4.9 结构摘要

- 入口和运行层收敛为 `entry`、`x5crop.run_config`、`runtime.input_probe`、`runtime.app` 和
  `runtime.workflow`。
- format physical facts 由 `x5crop.formats` 承担；唯一 `frame_geometry_profile` 由 physical
  facts 推导。
  旧 per-format 参数模块和 string override path 已删除，参数由 central typed factory 组装。
- format aspect 由底片 frame size mm 推导；half 已从历史 `2/3` 修正为物理
  `18x24mm = 3:4`，因此 half 检测输出允许出现破坏性 diff。
- 新增 `ScanCalibration` / `PhysicalLength` 单位模型；TIFF
  resolution 只用于物理长度解释和 report detail，不直接放宽 PASS / REVIEW。
- XPAN 和 120-66 增加 `complete_strip_can_be_underfilled` 物理 trait；partial
  入口可以表达“完整张数但未铺满片夹”，并在 report 中记录 `strip_completeness`
  和 `holder_occupancy`。
- runtime policy、policy assembly 和 final decision contract 分层；runtime 边界创建
  `DetectionPolicyBundle` 并一次性解析当前 policy 和 dual-lane 支撑项；每个 policy 直接持有
  唯一 `FormatPhysicalSpec`，不再复制 format-id/family/default-count，也不动态回查 registry。
- dual-lane 的 lane count 和 lane format 已从 detector policy 默认值迁入
  `FormatPhysicalSpec`，明确为胶片/片夹布局的物理事实；顶层 `DetectionPolicy` 的 output、
  diagnostics surface 也必须由 assembly 显式装配。
- detection 按 `modes`、`physical`、`guidance`、`evidence`、
  `candidate.{plan,proposal,build,execution,assessment,selection,extension}`、`decision`
  和 `final` 分层。
- candidate lifecycle 进一步拆清：`candidate.plan` 只声明 count、offset、source descriptors
  和 execution budget；proposal execution 迁入 `candidate.execution`，build 只负责未评分
  `DetectionCandidate`，geometry evidence enrichment 显式发生在 assessment 前。
- auto count 改为显式 `CountHypothesisPlan -> CountHypothesisEvaluation -> count selection`：
  runtime config 只保留 `requested_count`，不再用伪默认 count 表示自动模式；report 会记录
  search order、每个 count 的候选支持和停止原因。
- 候选与最终结果类型已拆成 `DetectionCandidate` / `FinalDetection`：candidate 不再携带
  status 或 final reasons；DecisionGate 是唯一转换点。旧 `FinalDecisionResult`、
  `DetectionFinalizationResult` 和 reason mutation helper 已删除，report / debug / export
  只消费 `FinalDetection` 的 canonical status 和 final reasons。实际构建 report record 的
  模块/接口也从含混的 `report.schema` 改为 `report.record`。
- `outer_alignment` evidence policy 与 `content_containment` correction policy 拆清；
  evidence 层不再读取 correction policy，也不生成 corrected outer。
- `FormatPhysicalSpec` 成为唯一物理规格类型；旧 `FormatSpec` 别名和 format-name aspect map
  已删除。`frame_geometry_profile` 由 physical spec 自身从 physical facts 派生，assembly
  消费该分类，reporting 只读描述。
- report/debug/export final reason 读取改成纯 read；缺失 current decision schema 时由 report
  schema 输出 `schema_validation` diagnostic，不再写回 detection detail 或从旧位置兜底拼字段。
- report schema revision 更新为 `canonical_result_and_decision`；cached analysis reuse
  只接受 schema、输入/config identity、active policy fingerprint 均匹配，且含 current count
  selection、exposure evidence、output protection plan、decision summary 和 output geometry 的 record。
- decision layer 生成 canonical final status、final confidence 和
  `final_review_reasons`；`DecisionGate` 也是唯一 `FinalDetection` factory。旧
  `contract_applier` 已删除，decision contract 由上层显式传入，decision 不再从完整
  runtime policy 自行组装 contract。
- report / debug / cache reuse 只读当前 schema；旧 decision contract helper、旧 policy detail
  fallback、旧 cached final reason fallback 和缺 decision summary 时的 final reason fallback 已删除。
- report schema identity 从版本号式命名收敛为 `schema_id` + `schema_revision`，
  并由 `x5crop.report.identity` 单一拥有，避免脚本版本、policy 和 report schema 混在
  同一个名称或 policy detail 里。
- 叠片链路拆成纯 `exposure_overlap_evidence` 与 `OutputProtectionPlan`：evidence 只测量
  model boundary 上的连续影像和 overlap band；output 层计算 required / available bleed 与
  feasibility；DecisionGate 只阻断 `exposure_overlap_unresolved`，finalization 执行同一个 plan。
  该物理能力对所有 format/mode 通用，不再由 format trait 或恒真 capability 开关控制；即使 plan 不完全可行，
  REVIEW 输出也会使用当前可用的最大保护 bleed。
- output bleed 和 approved geometry adjustment 已与最终决策输入分开；finalization 对
  output detection 副本做几何调整，并同时记录 `decision_geometry` 与 `output_geometry`。
- decision evidence policy 已从 format-id override 表收敛为 physical trait 推导；format 名字只作为
  `FormatPhysicalSpec` 查询入口。
- policy 参数 topology 已从扁平 `FormatParameters` 收敛为固定分组：
  `preprocess`、`content`、`outer`、`separator`、`candidate`、`decision`、`output` 和
  `diagnostics`。`FormatParameters` 只作为装配入口，不再提供扁平 property view。
- policy registry 只解析一次 `FormatPhysicalSpec`，随后将同一 spec 和 concrete
  `FormatParameters` 单向传给 assembly；parameter factory 和 mode preset 不再回查
  format registry。
- physical separator count、outer candidate strategy、frame aspect 和 separator band
  collection 均只保留 canonical owner；旧别名、string reducer、纯转发 wrapper 和重复
  collection model 已删除。
- image / geometry / cache foundation helper 改为显式参数对象；base gray、content evidence、
  separator evidence、deskew fallback 和 scan calibration trust 参数由 runtime policy assembly 提供。
- frame-fit foundation API 删除 optional config 路径；调用方必须显式传入 frame-fit parameters，
  geometry model 固定生成基础 frame，edge evidence 在可用时进一步拟合。
- approved geometry adjustment 迁到 output-adjacent helper，硬编码检测常数已进入 runtime
  finalization policy。
- 输出路径计算归 `x5crop.output.surface`；`x5crop.export` 只负责写 crop / review copy。
- workflow 不再在读取 TIFF 前创建输出目录；output surface 只在实际写出 crop、review copy、
  debug 或 report 时创建目录。
- regression compare 工具只作为 diff 审计工具；reference diff 不改变命令退出状态。
- Debug Analysis 默认保持三联图；更细 evidence / gate / decision signal 信息写入 report detail。

### 已验证记录

近期已验证过的项目状态包括：

- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.9`。
- package compile 通过。
- `python3 -m x5crop.policies.consistency` 对 14 个 format / strip-mode 组合通过。
- `git diff --check` 通过。
- Mac 主启动器和 diagnostics 启动器 `bash -n` 通过。
- Entry、workflow、policy、foundation、detection、report/debug/export 和 tools 分层 smoke
  通过。
- Debug Analysis 单样本 smoke 生成 V4.9 三联 JPG。
- Cached analysis reuse smoke 覆盖 approved auto export 和 needs_review skip-export。
- 七组本地 V4.5.4 reference reports 曾完成 comparison / classification，用于定位差异。

说明：

- 这些验证记录说明当时命令和样本覆盖范围，不代表历史 diff 阻断条件。
- 后续行为变化以当前审核目标判断，不以旧 reference 的字段一致性判断。
- 本地验证可能从 process worker fallback 到 thread worker。

V4.9 release validation 尚未完成：

- 默认 deskew export timing。
- `xpan`、`120-645` 和 `135-dual` full sample reference comparison。
- Release package generation。

### 版本摘要

| Version | 状态 | 摘要 |
|---|---|---|
| V4.9 | 当前 active development | 继续推进 evidence / policy / decision 分层；reference diff 作为审查材料，不作为历史一致性 gate。 |
| V4.7 | 上一个 active development | 源码布局重构；移除旧 bridge，保留薄入口和分层 `x5crop/` implementation，并把 format / mode 行为迁入 policy。 |
| V4.6 | development | 引入 `DetectionPolicy` 管理 detector、count、outer、separator、content、scoring、selection、postprocess、diagnostics 和 output 行为。 |
| V4.5.x | development | 收敛 120-66 broad separator width / strict-holder 行为、half geometry support、policy views、postprocess 和 separator-geometry outer。 |
| V4.4.x | development | 改进 full / partial outer proposal、output folder naming、Debug Analysis readability、partial safe-extra-frames 和 cache efficiency。 |
| V4.3.x | development | 建立 full-mode outer proposal layer，并为 partial mode 增加 conservative safe-extra-frames gate。 |
| V4.2.8 | 当前 stable release | 改进启动器交互：只在 partial mode 开启后询问 count；Return 或 `auto` 表示自动判断。检测逻辑不变。 |
| V4.2.x | development | 建立 120 family geometry model、separator-first outer proposal、120-66 / 120-67 保守修复和 half-frame full geometry support。 |
| V4.1.x | development | 120-66 / 120-67 参数校准、outer retry 收敛和 120 shared policy 整理。 |
| V4.0.x | historical stable / development | 模块化重写和 135 wide-spacing support；根入口变薄，主要职责迁入 `x5crop/`。 |
| V3.6 - V3.9 | historical development | format-aware policy / tuning、frame fit、diagnostics、hard-gap trust、nearby separator、overlap risk 和 edge-pair 工作。 |
| V3.0 - V3.5 | historical baseline / experiments | 建立主流程、output-only bleed 和 V3 风格检测链路；若干 hard-gap / grid 实验已暂停或回滚。 |

### 发布策略

- GitHub Releases 是用户下载入口。
- `main` 是开发分支，可以领先稳定发布版。
- 用户 Release zip 只包含 standalone script、launchers、TXT user docs 和 install /
  uninstall launchers。
- 用户发布包不包含 `x5crop/`、`archive/`、`CHANGELOG.md`、`AGENTS.md`、`LICENSE`、
  `.github/`、diagnostics launchers、Test files 或 generated outputs。

## English Changelog

### Scope

This file records only version-relevant information:

- User-visible behavior changes.
- Major source-structure milestones.
- Verification commands, verification scope, and missing validation.
- Release package policy and rollback context.

Source layering and runtime-flow details live in `ARCHITECTURE.md`; current
handoff lives in `AGENTS.md`.

### Current Development Line: V4.9

V4.9 is the current active development line. It builds on the V4.7 source layout
and continues organizing detection as reviewable evidence / policy / decision
structure.

Current version stance:

- V4.5.4 / V4.7 reference reports are historical references and diff-location
  tools, not acceptance oracles.
- In the current project phase, any historical reference diff can be accepted;
  a diff does not block acceptance by itself.
- `status`, `confidence`, `final_review_reasons`, `outer_box`, `frame_boxes`,
  `gaps`, `runtime_policy_detail`, and report record / schema fields may all differ; when useful,
  record why and which layer the change touches.
- Current-schema raw comparison locates changes; it does not automatically turn
  diffs into failures.
- TIFF metadata, bit depth, ICC, resolution, and known lossless compression
  behavior remain user-facing output-quality boundaries.

### V4.9 Structure Summary

- Entry and runtime are split into `entry`, `x5crop.run_config`,
  `runtime.input_probe`, `runtime.app`, and `runtime.workflow`.
- Format physical facts belong to `x5crop.formats`; the canonical
  `frame_geometry_profile` is derived from physical facts. The old per-format parameter modules and string
  override path have been removed, and parameters are assembled by a central
  typed factory.
- Format aspect is derived from film frame size in millimeters; half-frame was
  corrected from the historical `2/3` value to the physical `18x24mm = 3:4`,
  so half-frame detection output diffs are accepted.
- `ScanCalibration` / `PhysicalLength` now define unit ownership;
  TIFF resolution is used for physical-length explanation and report detail, not
  to loosen PASS / REVIEW.
- XPAN and 120-66 now expose the `complete_strip_can_be_underfilled` physical
  trait. Partial mode can represent a complete frame sequence that does not fill
  the holder, with `strip_completeness` and `holder_occupancy` recorded in the
  report.
- Runtime policy, policy assembly, and final decision contract are separated.
  Runtime resolves the active policy and dual-lane support entries into a
  `DetectionPolicyBundle`. Each policy directly owns one `FormatPhysicalSpec`;
  duplicated format-id/family/default-count fields and downstream registry
  queries have been removed.
- Detection is layered as `modes`, `physical`, `guidance`, `evidence`,
  `candidate.{plan,proposal,build,execution,assessment,selection,extension}`,
  `decision`, and `final`.
- Candidate lifecycle is stricter: `candidate.plan` only declares count, offset,
  source descriptors, and execution budget; proposal execution now lives in
  `candidate.execution`, build only creates an unscored `DetectionCandidate`, and
  geometry evidence enrichment explicitly happens before assessment.
- Auto count now follows an explicit `CountHypothesisPlan -> CountHypothesisEvaluation
  -> count selection` flow. Runtime config carries only `requested_count` instead
  of a placeholder default count, and reports expose search order, support, and
  stopping evidence for every evaluated count.
- Candidate and final result types are now distinct. `DetectionCandidate` has no
  status or final reasons; DecisionGate is the sole conversion to
  `FinalDetection`. The old decision/finalization wrappers and reason mutation
  helper were removed, and report/debug/export only consume final detections.
- `outer_alignment` evidence policy is separated from `content_containment`
  correction policy; the evidence layer no longer reads correction policy or
  generates corrected outer boxes.
- `FormatPhysicalSpec` is the sole physical-spec type. The old `FormatSpec` alias
  and format-name aspect map are gone. `frame_geometry_profile` is derived by the
  physical spec; assembly consumes it and reporting only describes it.
- The decision layer produces canonical final status, final confidence, and
  `final_review_reasons`; `DecisionGate` is also the sole `FinalDetection`
  factory. The old `contract_applier` is gone, the decision contract is passed
  explicitly, and decision no longer assembles it from the full runtime policy.
- Report / debug / cache reuse read the current schema only; final-reason reads
  are pure reads, missing current decision schema is reported through
  `schema_validation`, and report code no longer fills canonical fields from
  old fallback locations.
- Report schema revision is now `canonical_result_and_decision`; cached
  analysis reuse requires matching schema, input/config identity, active policy
  fingerprint, current count selection, exposure evidence, output protection
  plan, decision summary, and output geometry.
- Report schema identity now uses `schema_id` + `schema_revision` and is owned
  solely by `x5crop.report.identity`, keeping script version, policy, policy
  detail, and report schema separate.
- Exposure overlap is split into pure `exposure_overlap_evidence` and an
  `OutputProtectionPlan`. Evidence measures continuous image content at model
  boundaries and overlap-band width; output planning owns required/available bleed
  and feasibility. DecisionGate only blocks `exposure_overlap_unresolved`, and
  finalization executes the same plan. The capability is universal across
  format/mode combinations and has no trait or always-true capability switch; an infeasible REVIEW output
  still receives the greatest available protective bleed.
- Output bleed and approved geometry adjustment are separate from final decision
  inputs. Finalization adjusts an output detection clone and records
  `decision_geometry` separately from `output_geometry`.
- Decision evidence policy is derived from physical traits instead of a
  format-id override table; the format name is only a `FormatPhysicalSpec` lookup key.
- Policy parameters now use grouped `FormatParameters`: `preprocess`, `content`,
  `outer`, `separator`, `candidate`, `decision`, `output`, and `diagnostics`.
  `FormatParameters` remains only the assembly entry and no longer exposes flat
  property views.
- The policy registry resolves `FormatPhysicalSpec` once, then passes that same
  spec and concrete `FormatParameters` one-way through assembly. Parameter and
  mode preset code no longer queries the format registry again.
- Physical separator count, outer candidate strategy, frame aspect, and separator
  band collection now each have one canonical owner; aliases, string reducers,
  pure forwarding wrappers, and duplicate collection models are removed.
- Image / geometry / cache foundation helpers now use explicit parameter
  objects; base gray, content evidence, separator evidence, deskew fallback, and
  scan-calibration trust parameters are supplied by runtime policy assembly.
- The frame-fit foundation API no longer accepts an optional config path. Callers
  explicitly pass frame-fit parameters; geometry supplies baseline frames and
  edge evidence refines them when available.
- Approved geometry adjustment moved to an output-adjacent helper, and its
  hard-coded detector constants now belong to runtime finalization policy.
- Output path calculation belongs to `x5crop.output.surface`; `x5crop.export`
  only writes crops and review copies.
- Workflow no longer creates the output directory before reading TIFF input; the
  output surface creates directories only when crop, review copy, debug, or
  report output is actually written.
- Regression compare tools are audit-only; reference diffs do not change the
  command exit status.
- Debug Analysis keeps a three-panel default; richer evidence / gate / decision
  signal detail is written to report detail.

### Verified Records

Recent verified project state included:

- `python3 X5_Crop.py --version` printed `X5_Crop.py 4.9`.
- Package compile passed.
- `python3 -m x5crop.policies.consistency` passed across 14 format /
  strip-mode combinations.
- `git diff --check` passed.
- Main Mac launcher and diagnostics launcher passed `bash -n`.
- Entry, workflow, policy, foundation, detection, report/debug/export, and tools
  layer smoke checks passed.
- Single-file Debug Analysis smoke wrote a V4.9 three-panel JPG.
- Cached analysis reuse smoke covered approved auto export and needs_review
  skip-export paths.
- Seven local V4.5.4 reference reports were compared / classified to locate
  differences.

Notes:

- These records document command and sample coverage at the time; they do not
  represent historical-diff blocking criteria.
- Future behavior changes are judged by the current audit goal, not by field
  parity with old references.
- Local verification may fall back from process workers to thread workers.

Not yet completed as V4.9 release validation:

- Default-deskew export timing.
- `xpan`, `120-645`, and `135-dual` full sample reference comparison.
- Release package generation.

### Version Summary

| Version | Status | Summary |
|---|---|---|
| V4.9 | Current active development | Continues the evidence / policy / decision structure. Reference diffs are audit material, not historical-parity gates. |
| V4.7 | Previous active development | Source-layout rewrite. Removes old bridges, keeps a thin entry and layered `x5crop/` implementation, and moves format / mode behavior into policy. |
| V4.6 | Development | Introduces `DetectionPolicy` for detector, count, outer, separator, content, scoring, selection, postprocess, diagnostics, and output behavior. |
| V4.5.x | Development | Converges 120-66 broad separator width / strict-holder behavior, half geometry support, policy views, postprocess, and separator-geometry outer. |
| V4.4.x | Development | Refines full / partial outer proposal responsibilities, output-folder naming, Debug Analysis readability, partial safe-extra-frames, and cache efficiency. |
| V4.3.x | Development | Builds full-mode outer proposal layering and conservative partial safe-extra-frames support. |
| V4.2.8 | Current stable release | Improves launcher interaction: count is requested only when partial mode is enabled; Return or `auto` keeps automatic count estimation. Detection logic is unchanged. |
| V4.2.x | Development | Builds 120 family geometry model, separator-first outer proposal, conservative 120-66 / 120-67 fixes, and half-frame full geometry support. |
| V4.1.x | Development | Calibrates 120-66 / 120-67 parameters, converges outer retry, and introduces shared 120 policy structure. |
| V4.0.x | Historical stable / development | Modular rewrite and 135 wide-spacing support; root entry becomes thin and main responsibilities move into `x5crop/`. |
| V3.6 - V3.9 | Historical development | Format-aware policy / tuning, frame fit, diagnostics, hard-gap trust, nearby separator, overlap risk, and edge-pair work. |
| V3.0 - V3.5 | Historical baseline / experiments | Establishes the main workflow, output-only bleed, and V3-style detection chain; several hard-gap / grid experiments are paused or reverted. |

### Release Policy

- GitHub Releases are the user-facing download channel.
- `main` is the development branch and may be ahead of the stable release.
- User Release zips contain only the standalone script, launchers, TXT user docs,
  and install/uninstall launchers.
- User packages exclude `x5crop/`, `archive/`, `CHANGELOG.md`, `AGENTS.md`,
  `LICENSE`, `.github/`, diagnostics launchers, Test files, and generated outputs.
