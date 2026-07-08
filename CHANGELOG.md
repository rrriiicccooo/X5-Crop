# X5 Crop 更新日志 / Changelog

本文件记录版本级变化、验证记录、发布策略和回滚线索。源码审核视角见
`ARCHITECTURE.md`；用户操作说明见 `README.md` 和 `快速启动_Quick_Start.md`。

This file records version-level changes, validation records, release policy, and
rollback context. Source-audit perspectives live in `ARCHITECTURE.md`; user
instructions live in `README.md` and `快速启动_Quick_Start.md`.

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

架构审核视角、层级边界和当前源码清洁规则写在 `ARCHITECTURE.md`；当前 handoff 写在
`AGENTS.md`。

### 当前开发线：V4.9

V4.9 是当前 active development 线。它继承 V4.7 的源码分层成果，并继续把检测逻辑整理为
可审核的 evidence / policy / decision 结构。

当前版本口径：

- V4.5.4 / V4.7 reference reports 是历史参考和 diff 定位工具，不是验收 oracle。
- 当前项目阶段允许任何历史 reference diff；diff 本身不阻断验收。
- `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps`、
  `detail.policy` 和 `report_schema` 都可以出现 diff；需要时记录原因和涉及的审核视角。
- reference classifier 和 raw compare 用于定位变化，不用于把历史 diff 自动判为失败。
- TIFF metadata、位深、ICC、resolution 和已知无损压缩行为仍属于用户输出质量边界。

### V4.9 结构摘要

- 入口和运行层收敛为 `entry`、`runtime.config`、`runtime.input_probe`、`runtime.app` 和
  `runtime.workflow`。
- format physical facts 由 `x5crop.formats` 承担；format-specific 参数覆盖限制在
  physical tolerance、content profile tolerance 和 search budget。
- format policy module 收敛为单一 `build_policy(strip_mode)` 构建入口；删除未使用的
  `full_policy()` / `partial_policy()` helper。
- runtime `DetectionPolicy`、policy assembly 和 final decision contract 分层。
- runtime decision policy 已从 finalization policy 中拆出；confidence cap、low-confidence context review
  reason 和 outer-content alignment evidence 开关归 decision surface。
- runtime risk policy 从 diagnostics policy module 拆出；overlap bleed 和 lucky-pass
  risk 参数进入 `DetectionPolicy.risk`，diagnostics policy 只保留可视化 / read-only
  diagnostics 参数。
- policy assembly 中 diagnostics policy 从 finalization assembly 拆出；finalization assembly
  只装配 finalization policy。
- runtime output policy 从 finalization policy module 拆出；finalization policy module 只保留
  approved geometry adjustment，output bleed 执行开关、output bleed 参数和 edge-bleed
  protection 归 runtime output policy。
- runtime report policy 从 diagnostics policy module 拆出；report assembly 也从 common
  assembly 拆出，report schema / sections 不再挂在 diagnostics 名下。
- detection 按 `modes`、`physical`、`guidance`、`evidence`、
  `candidate.{plan,proposal,build,assessment,selection,extension}`、`decision` 和
  `final` 分层。
- dual-lane lane candidate 的 build / assessment / selection 迁入 `candidate.plan`；
  `modes` 只保留 lane split / merge routing。
- `detection.evidence` 不再读取 `candidate_assessment`；assessment detail 的消费收敛到
  decision 和 report/read-model。
- final decision evidence、risk cap、confidence cap 和 PASS / REVIEW 收敛到
  `detection.decision`；`detection.final` 只做 output-adjacent geometry、bleed 和
  diagnostics attachment。
- `runtime.workflow` 显式执行 decision step，然后把已决策的 detection 交给 finalization。
- outer proposal planning 中的 content guidance 组合迁入 `candidate.plan`；`physical.outer`
  只保留物理 proposal / helper。
- 删除残留的 `detection.physical.outer.plan` 文件；outer plan helper 只保留在
  `detection.candidate.plan.outer_proposals`。
- content-model proposal 不再在 guidance 层计算最终 confidence / review reasons；这些由
  candidate assessment 统一处理。
- decision 包拆成 reason normalization、evidence summary、risk summary 和 PASS / REVIEW
  applier。
- `detection.decision.__init__` 收回为 package marker；runtime 直接从 owning module 调用
  final decision。
- policy assembly 不再用 `known_physical_risks` 字符串作为参数开关；这些风险描述只用于
  report/debug，runtime 参数由 family、count、aspect 等物理谓词推导。
- candidate assessment 的 reason 输出收敛为候选级 blockers / diagnostics / auto-gate inputs；
  最终用户可见 `review_reasons` 只由 decision contract 生成。
- base scoring 的候选级 assessment 输出改为显式 `BaseDetectionAssessment`
  结果对象，字段化 `confidence`、`candidate_reason_codes` 和 `detail`，避免匿名三元组解包
  弱化 assessment contract。
- content candidate assessment 输出改为显式 `ContentCandidateAssessment`
  结果对象，字段化 `confidence`、`diagnostics` 和 `detail`，让 content 候选诊断继续停留在
  candidate assessment 层。
- content candidate 的 metrics helper 改名为
  `content_candidate_assessment_from_metrics()`，与 proposal helper 的 assessment 命名统一。
- separator gate 的候选级输出改为显式 `SeparatorGateResult` 结果对象，字段化 `ok`
  和 `detail`，避免调用方用匿名 tuple 解包 gate 契约。
- `candidate_assessment.blockers` 不再包含 `auto_gate_not_satisfied`，因为它是 gate
  结果而不是 gate 输入；旧候选 reason 仍保留在 internal `candidate_reasons` 中。
- candidate 子层的候选级 reason 读写收敛到 `detection.candidate.reasons`；candidate
  assessment 不再把候选原因写入 final-looking `Detection.review_reasons`。
- candidate reason 存储从 `Detection.review_reasons` 拆出到
  `Detection.detail["candidate_reasons"]`；`Detection.review_reasons` 只保留给
  decision 之后的最终用户可见 reason。
- candidate reason reader 不再 fallback 到 `Detection.review_reasons`，避免候选层重新读取
  final reason 字段。
- dual-lane mode 的模式失败 / lane 合并原因也改为通过 `detection.candidate.reasons`
  读写；`detection.modes` 不再直接 mutate `Detection.review_reasons`。
- candidate blockers / diagnostics 在 decision input 中保留原始候选级名字；
  `content_only_evidence` 只表示 content-source candidate，content containment /
  harm 失败改为 `content_evidence_insufficient`。
- decision risk summary 新增 `candidate_source_detail`，明确区分
  `candidate_assessment.source` 和顶层 `candidate_source`；content-only risk 与
  safety / review-only risk 不再共享模糊 source。
- decision evidence summary 中 content quality 的 role 字段改为
  `content_quality_score_role`，避免和 content containment 的 `content_score_role`
  混淆。
- decision input 中旧候选 reason 的归并读模型改名为
  `legacy_reduced_candidate_reasons`，避免把它误读成 candidate assessment 的主输出。
- low-confidence context reasons 收进 `decision.contract_applier`，不再由
  `final_decision` 事后补写 `decision_summary`。
- 删除未使用的 `add_final_review_reason` helper；最终 reason 只保留 decision contract 的
  set-style 写入口。
- `overlap_risk` 和 `lucky_pass_risk` 在 decision contract 中拆成独立 final reasons；
  overlap 只表示物理/output-bleed 风险，lucky-pass 只表示证据组合侥幸通过风险。
- overlap risk evidence 前移到 decision 阶段生成；finalization 只消费已有 risk detail
  来调整 output bleed，不再在 PASS / REVIEW 之后补充裁决输入。
- candidate selection 不再提前写 `candidate_competition_uncertain` 或执行 competition cap；
  它只记录 `selection_risk_inputs`，最终 `candidate_competition_close` reason / cap 由
  decision contract 统一生成。
- content mismatch selector 的 policy、字段和 helper 名称收敛为 candidate-selection 语义；
  它只读取 candidate-level diagnostics / blockers 选择候选，不生成最终 review reason。
- content-model proposal policy/detail 不再使用 `review_only` 布尔或 `assessment_required`
  分支；改为中性的 `content_guidance_assessment_required`，避免把 content guidance 写成
  final REVIEW 裁决。
- content candidate assessment helper 和局部变量改用 diagnostics 命名；
  content-run / grid-fallback / aspect 观察不再暴露为 `content_candidate_*_reasons`
  这类 final-looking 名称。
- base scoring 的局部输出命名改为 `candidate_reason_codes`，明确它只写候选级 reason
  read model，不是最终 `review_reasons`。
- candidate table / selected candidate detail 的候选级原因字段改为 `candidate_reasons`、
  `candidate_blockers`、`candidate_diagnostics`；decision 写入 `final_review_reasons` 和
  `final_confidence`。
- candidate plan / execution budget detail 的可靠性条件改为 `candidate_reasons` 和
  `candidate_reasons_ok`，runtime policy 字段改为 `requires_no_candidate_reasons`。
- candidate plan detail 删除旧 `gap_profiles` 别名；gap 搜索 family 只用
  `gap_search_profiles` 表达，避免同一 width-aware search 同时暴露两个名字。
- dual-lane lane content / outer-alignment 检查从 `candidate.plan` 移入
  `candidate.assessment`，plan 只负责 lane candidate 生命周期编排；lane candidate
  限分写入 `candidate_confidence_caps`。
- safety candidate 的 candidate auto-gate blocker、candidate cap 和 auto-gate 改写从
  `candidate.plan` 移入 `candidate.assessment`。
- content candidate assessment detail 的 owner 统一为 `candidate.assessment`；
  corrected outer candidate reassessment detail 的 owner 统一为 `candidate.extension`。
- safety candidate detail 删除旧 `auto_pass_eligible` 字段，改为
  `candidate_auto_gate_eligible`，避免候选级 gate 被误读成最终 PASS 资格。
- safety candidate detail 不再使用 `review_only` / `changes_pass_review` 这类 final-looking
  字段；候选阻断写为 `safety_candidate_auto_gate_blocked`。
- hard safety candidate 删除误导性的 `changes_final_decision` detail，改用
  `candidate_contract` 和 `candidate_auto_gate_eligible` 表达候选契约。
- read-only diagnostics 删除 `changes_final_decision` 等顶层变化字段，改用
  `effects` 结构说明 output、confidence 和 decision 均无副作用。
- read-only diagnostics 将 `single_anchor_pass_risk` 改为
  `single_anchor_evidence_risk`，避免 evidence 层字段被误读为最终 PASS 判断。
- review-only / dual-lane mode detail 的模式级诊断改为 `mode_diagnostics` 和
  `candidate_reasons`，不再在 mode detail 中输出 final-looking `review_reasons` 字段。
- review-only mode 不再在构造 `Detection` 时写入最终 `review_reasons`；模式失败原因保留为
  candidate / mode diagnostics，最终 REVIEW 原因仍由 decision contract 生成。
- close competition 的风险阈值从 runtime candidate selection policy 汇入 decision
  contract，避免 selection 和 decision 各自持有不同 margin。
- guidance / candidate-plan detail 不再使用 `decision_contract` 命名；content proposal 用
  `candidate_contract`，content-guided separator 用 `evidence_contract`。
- decision summary 不再输出旧 `review_reasons_added` / `final_review_reasons_added`
  增量字段；decision 生成的最终原因写入 `decision_generated_review_reasons`，
  最终全量原因写入 `final_review_reasons`。
- decision 子层的 final reason 归一化和写入收敛到 `detection.decision.reasons`；
  low-confidence context reason 不再直接 append `Detection.review_reasons`。
- workflow final status 不再只按 confidence 推导；`approved_auto` 必须同时满足 confidence
  达到阈值且 `final_review_reasons` 为空，避免低自定义阈值越过 final review reason。
- report / debug / export 作为 output read-model 清理：它们只读取 `ProcessResult` 或
  `decision_summary.status`，不再根据 confidence / reason 自行推导 PASS / REVIEW；裸
  Detection 没有 decision summary 时显示 `unknown` / `UNKNOWN`。
- report schema 中 risk / deskew 可见细节从旧的 `finalization` 语义收敛到
  `diagnostics` section；finalization 继续只表示输出相邻几何和 bleed 调整。
- report schema 默认 sections 正式包含 `evidence` 和 `gates`，让已经构造好的审核
  read-model 出现在报告中。
- policy / report 可见 gate stage 名称收敛为 `candidate_blocker_gate`、
  `candidate_auto_gate` 和 `decision_contract_gate`；移除旧的 finalization / auto-pass
  gate 命名。
- runtime `GatePolicy` 移除未被消费的 `hard_review_reasons_block_auto` 字段；候选阻断
  由 candidate assessment detail 表达，最终 REVIEW 由 decision contract 表达。
- review copy warning 从 “low confidence” 改为中性的 “review required”，避免把所有
  REVIEW 误写成低置信度。
- partial safe extra frames detail 只保留 `partial_safe_extra_frames` canonical key；
  删除旧 `partial_extra_holder_frames` 别名。
- confidence cap detail 统一记录 owner、reason、cap value 和前后 confidence；candidate cap
  和 decision cap 分别归 assessment / decision。
- decision contract 移除未被实际裁决消费的 `candidate_policy` 报告字段；content-only /
  safety / review-only 规则由 risk summary 和 PASS / REVIEW applier 表达。
- decision contract 不再携带 output / diagnostics policy 报告字段；output bleed、debug panels
  和 report sections 留在各自 runtime policy。
- output bleed helper 从 `detection.final` 移到中性 `x5crop.output` 层；workflow、
  analysis reuse 和 finalization 共同消费该 output-adjacent helper，避免从 runtime 反向依赖
  detection final 私有模块。
- `detection.final.finalize_detection()` 不再自行查 policy registry；workflow 将已选中的
  runtime policy 显式传入 finalization，保持 format / mode policy 选择只有一个上游来源。
- decision risk policy 移除未被实际裁决消费的 content-only / safety review-only 布尔字段；
  candidate source -> risk summary -> decision applier 是唯一表达路径。
- `candidate_build` detail 删除跨层的 base scoring 状态字段；base scoring 可见性只保留在
  `base_candidate_scoring`。
- candidate auto-gate blocker 词表从通用 `utils` 移入 `candidate.assessment`，并移除
  hard review reason 命名残留。
- 内层 PASS / REVIEW 契约应用文件从 `pass_review.py` 改名为
  `contract_applier.py`；外层 `final_decision.py` 继续负责 decision 编排。
- evidence-independence policy 的 candidate 阻断字段从 `review_reason` 改为
  `candidate_blocker`，避免 candidate gate 输入被命名成最终 REVIEW reason。
- candidate selection risk input 删除 `recommended_final_review_reason` 字段；selection
  只记录风险 signal，最终 reason 仍由 decision contract 生成。
- report / debug / export / finalization 读取最终 reason 时统一走
  `final_review_reasons_from_detail()`，优先读取 decision summary。
- decision 后的 `candidate_competition.selected_candidate` / selected top-candidate
  final fields 会随 low-confidence context reason 同步刷新，避免 report 中 selected
  candidate 的 `final_review_reasons` 与最终 result 不一致。
- `Detection.detail` 的稳定读取 helper 迁入 `detection.detail`，根包不再承载
  report/debug read-model。
- candidate assessment 拆为 support scoring、base scoring 和 gate support。
- photo-size consistency 成为共享物理模型；`photo_width_*` 表示照片影像区域尺寸证据，
  separator 宽度变化保留为 observed detail。
- content scoring 使用内容保护语义：安全 overcut 和空 frame 不是负面证据，真实内容损伤才是风险。
- separator 语义收敛为单一 `width_aware` proposal；observed width 是中性实测宽度证据。
- candidate / report 可见的 gap 搜索详情收敛为单一 `gap_search_profile`；
  删除重复的 `separator_width_profile` runtime detail 和已合并的 gap-search 空壳字段。
- format / mode 审核口径从固定隔离清单转为 capability composition：format 提供物理事实，
  mode 提供执行姿态，policy assembly 决定默认启用，evidence / decision 解释结果。
- `135-dual/full` 使用独立 dual-lane mode detector；`135-dual/partial` 走通用
  review-only 保守路径。
- Debug Analysis 默认保持三联图；更细 evidence / gate / risk 解释写入 report detail。

### 已验证记录

近期已验证过的项目状态包括：

- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.9`。
- package compile 通过。
- `python3 -m x5crop.policies.consistency` 对 14 个 format / strip-mode 组合通过。
- `python3 -m unittest discover -s tools/tests` 通过 90 个 unit / contract tests。
- `git diff --check` 通过。
- Mac 主启动器和 diagnostics 启动器 `bash -n` 通过。
- diagnostics smoke 覆盖 `135/full`、`120-66/partial -n 3`、`half/full` 和
  `135-dual/full` code path；dual-lane path 在非 dual 样片上保守 REVIEW。
- Entry、workflow、policy、foundation、detection、report/debug/export 和 tools 分层 smoke
  通过。
- Debug Analysis 单样本 smoke 生成 V4.9 三联 JPG。
- Cached analysis reuse smoke 覆盖 approved auto export 和 needs_review skip-export。
- 七组本地 V4.5.4 reference reports 曾完成 comparison / classification，用于定位差异。

说明：

- 这些验证记录说明当时命令和样本覆盖范围，不再代表历史 diff 阻断条件。
- 后续行为变化以当前审核目标判断，不以旧 reference 的字段一致性判断。
- 本地验证可能从 process worker fallback 到 thread worker。

V4.9 release validation 尚未完成：

- 默认 deskew export timing。
- `xpan`、`120-645` 和 `135-dual` full sample reference comparison。
- Release package generation。

### 版本摘要

| Version | 状态 | 摘要 |
|---|---|---|
| V4.9 | 当前 active development | 继续推进可审核的 evidence / policy / decision 结构；reference diff 作为审查材料，不作为历史一致性 gate。 |
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

Architecture review perspectives, layer boundaries, and current source-cleanup
rules live in `ARCHITECTURE.md`; current handoff lives in `AGENTS.md`.

### Current Development Line: V4.9

V4.9 is the current active development line. It builds on the V4.7 source layout
and continues organizing detection as reviewable evidence / policy / decision
structure.

Current version stance:

- V4.5.4 / V4.7 reference reports are historical references and diff-location
  tools, not acceptance oracles.
- In the current project phase, any historical reference diff can be accepted;
  a diff does not block acceptance by itself.
- `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, `gaps`,
  `detail.policy`, and `report_schema` may all differ; when useful, record why
  and which audit perspective the change touches.
- Reference classifier and raw compare locate changes; they do not automatically
  turn historical diffs into failures.
- TIFF metadata, bit depth, ICC, resolution, and known lossless compression
  behavior remain user-facing output-quality boundaries.

### V4.9 Structure Summary

- Entry and runtime are split into `entry`, `runtime.config`,
  `runtime.input_probe`, `runtime.app`, and `runtime.workflow`.
- Format physical facts belong to `x5crop.formats`; format-specific overrides
  are limited to physical tolerance, content profile tolerance, and search budget.
- Format policy modules now expose the single `build_policy(strip_mode)` build
  entry; unused `full_policy()` / `partial_policy()` helpers have been removed.
- Runtime `DetectionPolicy`, policy assembly, and final decision contract are
  separated.
- Runtime decision policy has been split out of finalization policy. Confidence
  caps, low-confidence context review reasons, and the outer-content alignment
  evidence switch now belong to the decision surface.
- Runtime risk policy has been split out of diagnostics policy. Overlap-bleed
  and lucky-pass risk parameters now live under `DetectionPolicy.risk`; diagnostics
  policy keeps visualization and read-only diagnostics settings.
- Runtime output policy has been split out of the finalization policy module.
  Finalization policy keeps approved geometry adjustment; the output-bleed
  execution switch, output-bleed parameters, and edge-bleed protection belong to
  runtime output policy.
- Detection is layered as `modes`, `physical`, `guidance`, `evidence`,
  `candidate.{plan,proposal,build,assessment,selection,extension}`, `decision`,
  and `final`.
- Dual-lane lane candidate build / assessment / selection now belongs to
  `candidate.plan`; `modes` keeps only lane split / merge routing.
- `detection.evidence` no longer reads `candidate_assessment`; assessment detail
  is consumed by decision and report/read-model code.
- Final decision evidence, risk caps, confidence caps, and PASS / REVIEW belong
  to `detection.decision`; `detection.final` handles only output-adjacent
  geometry, bleed application, and diagnostics attachment.
- Diagnostics policy assembly has been split out of finalization assembly;
  finalization assembly now builds finalization policy only.
- Runtime report policy has been split out of diagnostics policy, and report
  assembly has been split out of common assembly.
- `runtime.workflow` now runs an explicit decision step before finalization.
- Content-guidance composition for outer proposal planning now belongs to
  `candidate.plan`; `physical.outer` keeps physical proposals and helpers only.
- The stale `detection.physical.outer.plan` module has been removed; outer plan
  helpers live only in `detection.candidate.plan.outer_proposals`.
- Content-model proposals no longer compute final confidence / review reasons in
  guidance; candidate assessment owns that scoring.
- The decision package is split into reason normalization, evidence summary,
  risk summary, and the PASS / REVIEW applier.
- `detection.decision.__init__` is now a package marker only; runtime calls the
  final decision owning module directly.
- Policy assembly no longer uses `known_physical_risks` strings as parameter
  switches. Those descriptors remain for report/debug visibility, while runtime
  parameters are derived from physical predicates such as family, count, and
  aspect.
- Candidate assessment reason output is now candidate-level blockers /
  diagnostics / auto-gate inputs; user-visible final `review_reasons` are
  generated only by the decision contract.
- Base scoring candidate assessment now returns an explicit
  `BaseDetectionAssessment` result with `confidence`, `candidate_reason_codes`,
  and `detail` fields, so the assessment contract no longer depends on anonymous
  tuple unpacking.
- Content candidate assessment now returns an explicit
  `ContentCandidateAssessment` result with `confidence`, `diagnostics`, and
  `detail` fields, keeping content diagnostics in the candidate-assessment layer.
- The content-candidate metrics helper is now named
  `content_candidate_assessment_from_metrics()` to match the proposal helper's
  assessment naming.
- Separator gate candidate output now returns an explicit `SeparatorGateResult`
  with `ok` and `detail` fields, so callers no longer depend on anonymous tuple
  unpacking for the gate contract.
- Candidate sublayers now route candidate-level reason reads and writes through
  `detection.candidate.reasons`; candidate assessment no longer stores
  candidate reasons in final-looking `Detection.review_reasons`.
- Candidate reason storage moved from `Detection.review_reasons` to
  `Detection.detail["candidate_reasons"]`; `Detection.review_reasons` is now
  reserved for final user-visible reasons after the decision step.
- Candidate reason readers no longer fall back to `Detection.review_reasons`, so
  candidate layers cannot re-read final reason fields as candidate reasons.
- Dual-lane mode failure and lane-merge reasons also route through
  `detection.candidate.reasons`; `detection.modes` no longer directly mutates
  `Detection.review_reasons`.
- Candidate blockers / diagnostics keep their raw candidate-level names in
  decision inputs. `content_only_evidence` now only means a content-source
  candidate; failed content containment / harm checks use
  `content_evidence_insufficient`.
- Decision risk summary now exposes `candidate_source_detail`, separating
  `candidate_assessment.source` from top-level `candidate_source`, so
  content-only risk and safety / review-only risk do not share a vague source.
- Decision evidence summary now reports content-quality score role as
  `content_quality_score_role`, separate from the content-containment
  `content_score_role`.
- The legacy candidate-reason reduction read model in decision inputs is named
  `legacy_reduced_candidate_reasons`, so it is not mistaken for the primary
  candidate-assessment output.
- Overlap risk evidence is now attached during the decision step. Finalization
  only consumes existing risk detail for output bleed and no longer adds
  PASS / REVIEW inputs after the decision.
- Candidate selection no longer writes `candidate_competition_uncertain` or
  applies the competition cap early. It only records `selection_risk_inputs`;
  final `candidate_competition_close` reason / cap are generated by the decision
  contract.
- Candidate table / selected-candidate detail now uses `candidate_reasons`,
  `candidate_blockers`, and `candidate_diagnostics` for candidate-level
  explanations. Decision writes `final_review_reasons` and `final_confidence`.
- Content-candidate assessment helpers and local variables now use diagnostic
  naming. Content-run, grid-fallback, and aspect observations are no longer
  exposed through final-looking `content_candidate_*_reasons` names.
- Base-scoring local output naming now uses `candidate_reason_codes`, making it
  explicit that base scoring writes the candidate-level reason read model, not
  final `review_reasons`.
- Candidate plan / execution-budget reliability detail now uses
  `candidate_reasons` and `candidate_reasons_ok`; runtime policy uses
  `requires_no_candidate_reasons`.
- Candidate-plan detail no longer emits the old `gap_profiles` alias; gap search
  families are exposed only as `gap_search_profiles`.
- Dual-lane lane content / outer-alignment checks moved from `candidate.plan` to
  `candidate.assessment`; plan now only orchestrates lane-candidate lifecycle.
  Lane-candidate caps are recorded in `candidate_confidence_caps`.
- Safety-candidate auto-gate blocker, candidate cap, and auto-gate rewrite
  moved from `candidate.plan` to `candidate.assessment`.
- Content-candidate assessment detail now reports owner `candidate.assessment`;
  corrected outer candidate reassessment detail reports owner
  `candidate.extension`.
- Safety-candidate detail no longer emits the old `auto_pass_eligible` field;
  it uses `candidate_auto_gate_eligible` so candidate-level gate detail is not
  mistaken for final PASS eligibility.
- Safety-candidate detail no longer uses final-looking `review_only` /
  `changes_pass_review` fields; the candidate blocker is reported as
  `safety_candidate_auto_gate_blocked`.
- Hard-safety candidate detail no longer emits the misleading
  `changes_final_decision`; it uses `candidate_contract` and
  `candidate_auto_gate_eligible` to describe the candidate contract.
- Read-only diagnostics no longer emit top-level change flags such as
  `changes_final_decision`; they use an `effects` object to show output,
  confidence, and decision are unchanged.
- Review-only / dual-lane mode detail now uses `mode_diagnostics` and
  `candidate_reasons` for mode-level diagnostics, instead of final-looking
  `review_reasons` fields inside mode detail.
- Review-only mode no longer writes final `review_reasons` while constructing
  `Detection`; mode failure reasons remain candidate / mode diagnostics until
  the decision contract generates final REVIEW reasons.
- The close-competition risk threshold now flows from runtime candidate
  selection policy into the decision contract, avoiding separate selection and
  decision margins.
- Guidance and candidate-plan detail no longer use `decision_contract` naming:
  content proposals report `candidate_contract`, and content-guided separator
  reports `evidence_contract`.
- Content-model proposal policy/detail no longer uses a `review_only` boolean
  or bare `assessment_required` branch. It now reports the neutral
  `content_guidance_assessment_required` contract, so content guidance is not
  named like a final REVIEW decision.
- Decision summary no longer emits the old `review_reasons_added` /
  `final_review_reasons_added` incremental fields. Decision-generated final
  reasons are reported as `decision_generated_review_reasons`, and the final
  full list remains `final_review_reasons`.
- Decision sublayers now route final reason normalization and writes through
  `detection.decision.reasons`; low-confidence context reasons no longer append
  `Detection.review_reasons` directly.
- Workflow final status is no longer derived from confidence alone:
  `approved_auto` requires threshold-level confidence and empty
  `final_review_reasons`, so low custom thresholds cannot bypass final review
  reasons.
- Report, debug, and export are now explicit output read-models. They consume
  `ProcessResult` or `decision_summary.status` and no longer infer PASS / REVIEW
  from confidence or reasons; a bare Detection without decision summary is shown
  as `unknown` / `UNKNOWN`.
- Report-visible risk / deskew details now live under the `diagnostics` section
  instead of the old finalization-shaped read-model name.
- Report schema default sections now include `evidence` and `gates`, making the
  already-constructed audit read-model visible in reports.
- Policy/report-visible gate stage names now use `candidate_blocker_gate`,
  `candidate_auto_gate`, and `decision_contract_gate`, retiring finalization /
  auto-pass shaped gate names.
- Runtime `GatePolicy` no longer carries the unused
  `hard_review_reasons_block_auto` field; candidate blockers live in candidate
  assessment detail, and final REVIEW remains owned by the decision contract.
- Review-copy warnings now use neutral `review required` wording instead of
  implying every REVIEW is caused by low confidence.
- Partial safe extra frames detail now keeps only the canonical
  `partial_safe_extra_frames` key; the old `partial_extra_holder_frames` alias
  has been removed.
- Confidence cap detail now records owner, reason, cap value, and before/after
  confidence. Candidate caps and decision caps remain owned by assessment and
  decision respectively.
- The decision contract no longer reports the unused `candidate_policy` field;
  content-only, safety, and review-only behavior is expressed by risk summary and
  the PASS / REVIEW applier.
- The decision contract no longer carries output / diagnostics policy report
  fields; output bleed, debug panels, and report sections remain in their own
  runtime policies.
- Decision risk policy no longer carries unused content-only / safety
  review-only boolean fields. Candidate source -> risk summary -> decision
  applier is the single expression path.
- `candidate_build` detail no longer carries cross-layer base-scoring state;
  base-scoring visibility lives only in `base_candidate_scoring`.
- Candidate auto-gate blocker vocabulary moved from generic `utils` into
  `candidate.assessment`, removing hard-review-reason naming residue.
- The inner PASS / REVIEW contract application module was renamed from
  `pass_review.py` to `contract_applier.py`; outer `final_decision.py` remains
  the decision orchestration entry.
- The evidence-independence policy field for candidate blocking was renamed from
  `review_reason` to `candidate_blocker`, so candidate gate inputs are not named
  as final REVIEW reasons.
- Candidate selection risk input no longer carries
  `recommended_final_review_reason`; selection records only risk signals, and
  final reasons remain generated by the decision contract.
- Report / debug / export / finalization now read final reasons through
  `final_review_reasons_from_detail()`, preferring decision summary.
- After decision, `candidate_competition.selected_candidate` and the selected
  top-candidate final fields are refreshed when low-confidence context reasons
  are added, so report selected-candidate `final_review_reasons` stays aligned
  with the final result.
- Stable `Detection.detail` readers moved into `detection.detail`, so the root
  package no longer carries report/debug read-model helpers.
- Candidate assessment is split into support scoring, base scoring, and gate
  support.
- Photo-size consistency is a shared physical model. `photo_width_*` names refer
  to photo image-region size evidence; separator width variation remains observed
  detail.
- Content scoring uses content-protection semantics: safe overcut and empty
  frames are not negative evidence; harm to real content is risk.
- Separator semantics are consolidated into the single `width_aware` proposal;
  observed width is neutral measured evidence.
- Candidate/report-visible gap-search detail is consolidated into
  `gap_search_profile`; duplicate `separator_width_profile` runtime detail and
  the already-merged gap-search placeholder field are removed.
- Format / mode review has moved from fixed isolation lists to capability
  composition: format supplies physical facts, mode supplies execution posture,
  policy assembly chooses default enablement, and evidence / decision layers
  explain results.
- `135-dual/full` uses a dedicated dual-lane mode detector; `135-dual/partial`
  uses the generic conservative review-only path.
- Debug Analysis keeps a three-panel default; richer evidence / gate / risk
  explanation is written to report detail.

### Verified Records

Recent verified project state included:

- `python3 X5_Crop.py --version` printed `X5_Crop.py 4.9`.
- Package compile passed.
- `python3 -m x5crop.policies.consistency` passed across 14 format /
  strip-mode combinations.
- `python3 -m unittest discover -s tools/tests` passed 90 unit / contract tests.
- `git diff --check` passed.
- Main Mac launcher and diagnostics launcher passed `bash -n`.
- Diagnostics smoke covered `135/full`, `120-66/partial -n 3`, `half/full`, and
  the `135-dual/full` code path; the dual-lane path stayed conservative REVIEW
  on a non-dual sample.
- Entry, workflow, policy, foundation, detection, report/debug/export, and tools
  layer smoke checks passed.
- Single-file Debug Analysis smoke wrote a V4.9 three-panel JPG.
- Cached analysis reuse smoke covered approved auto export and needs_review
  skip-export paths.
- Seven local V4.5.4 reference reports were compared / classified to locate
  differences.

Notes:

- These records document command and sample coverage at the time; they no longer
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
| V4.9 | Current active development | Continues the reviewable evidence / policy / decision structure. Reference diffs are audit material, not historical-parity gates. |
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
