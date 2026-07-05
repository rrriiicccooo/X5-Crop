# X5 Crop 更新日志 / Changelog

本文件记录版本变化、行为边界、验证结论和回滚线索。用户操作说明见 `README.md`
和 `快速启动_Quick_Start.md`；架构说明见 `ARCHITECTURE.md`。

This file records version changes, behavior boundaries, validation conclusions,
and rollback context. For usage, read `README.md` and `快速启动_Quick_Start.md`;
for architecture, read `ARCHITECTURE.md`.

当前 active 脚本版本：V4.9

当前稳定发布版本：v4.2.8

Current active script version: V4.9

Current stable release: v4.2.8

## 中文更新日志

### 当前原则

- V4.9 是 evidence-governed policy reset，不是检测阈值放宽版本。
- V4.5.4 / V4.7 reference reports 是 historical baseline，不再是必须 0 diff 的 oracle。
- 自动 PASS 必须由 outer、separator、geometry、content 和 risk 组合证据解释。
- weak grid、equal、content-only、safety candidate 或 partial edge 不可信的候选默认进入 REVIEW。
- active retry architecture 已退休；broad-width gap search profile、safety candidate 和 corrected outer 都作为候选计划或候选扩展统一 assessment。
- separator-derived outer family 已通用化：标准 strip 的 full 默认启用 local、full-width 和 broad-width gap profile；partial 只有显式 count 时启用 extension variants，format 只提供 width / spacing / budget 参数。
- candidate execution budget 将 “eligible” 与 “executed” 分开：可靠 primary separator 已通过 assessment 时，可跳过 full-width 和 broad-width gap profile；outer correction 还要求 outer alignment ok 才跳过。
- detection 分层已对齐为 pipeline / modes / candidate proposal lifecycle /
  evidence / decision / final；outer proposal / correction 是 candidate proposal
  family，不再作为 detection 一级子层。PASS / REVIEW 属于 decision 层，
  finalization 只做 output-adjacent 调整。
- source package layout 已对齐到显式边界：`entry`、`runtime`、`cache`、
  `report`、`formats`、`detection.candidate.{plan,proposal,build,assessment,selection,extension}`
  和 `policies.{formats,parameters,runtime,decision,assembly,reporting}`。
- 基础灰度入口已与证据灰度拆开：`image.gray.make_base_gray_u8` 只负责
  TIFF / deskew 后的 base gray；`image.evidence` 只负责现有 content /
  separator / deskew analysis evidence。当前不保留 color contrast 或 heavy
  texture evidence 接口，未来如引入 OpenCV 等大依赖再重新评估。
- Gap / Separator 族群已按 candidate proposal 模型收敛入口：
  `detection.candidate.proposal.separator` 承接 separator proposal、refinement、
  width evidence 和 separator-derived outer band evidence；`geometry` 保留底层
  profile/search/trust 数学能力；width profile 纯数学归
  `geometry/separator_width_profile.py`，搜索参数归
  `SeparatorPolicy.width_profile_search`，启用 / 候选 / selection 策略归
  `SeparatorPolicy.width_profile`，outer policy 只保留 separator-derived outer
  family / band 参数；broad-width gap proposal
  的采样上限、搜索窗口、距离惩罚和基础分数已外显到 report detail。
- gap method vocabulary 已统一由 `constants.py` 提供；candidate assessment、
  decision summary、risk diagnostics、read-only diagnostics 和 frame edge fitting
  只消费 `detected / edge-pair / enhanced-detected / grid / equal / content`
  常量，不再手写 method 字符串。
- ordinary gap search 的 band threshold、弱 prominence 门槛和 detected-candidate
  quality 权重已外显到 `GapSearchParameters`；默认值保持旧行为。
- ordinary gap search 已拆成 hard-only `find_detected_gap`：它只返回
  `GapSearchResult` 中的 detected hard gap、fallback score 和 reason；standard
  separator proposal 负责在没有 hard gap 时调用 model proposal 生成 explicit
  `equal` fallback。band evidence measurement、prominence support 与
  width-profile support 也已拆成可审核 helper，方便审核 hard separator 与 model
  gap 的边界。
- equal / grid / content model-gap proposal 已集中到 `geometry.model_gaps`，
  profile 等分模型归 `detection.candidate.proposal.separator.model`；
  build / safety / refinement / content candidate 路径不再手写 `"equal"` /
  `"grid"` / `"content"` method 字符串。
- separator profile / edge-refine / enhanced profile cache key 已从 format identity
  解耦，改为只使用 geometry box 与参数对象；nearby diagnostic cache key 补入
  diagnostic policy。
- nearby separator correction 只返回修正后的 gap evidence、correction detail 和
  pre-correction gaps；confidence cap / scoring 保留在 detection build 与
  assessment 消费层。
- active gap search profile vocabulary 只保留 `standard` 与 `broad_width`；
  `broad_width` profile detail helper 只消费 separator policy。
- broad-width detected gap 生成已拆出 width-profile gap window、run scoring、
  best candidate selection 和 core-width clipped detected-gap output；输出仍是
  普通 `detected` hard gap，不引入独立 gap method。
- width-profile 搜索参数与候选策略已拆开：geometry 只消费
  `SeparatorWidthProfileSearchParameters`，`SeparatorWidthProfilePolicy` 只保留
  mode / required count / candidate budget / full-selection 语义，report 同时输出
  综合 `width_profile` 视图和纯 `width_profile_search` 参数。
- separator width evidence requirement 已收敛为 detail 消费：candidate build
  生成 `separator_width_evidence`，partial-safe / gate 只根据各自 requirement
  复核已有 evidence，不重新生成 separator evidence。
- `all_internal_gaps_hard` gate 已拆出 full/default-count supplemental
  broad-width requirement 与 edge-pair min-score helper；失败 reason 保持原语义，
  成功 reason 仍归主 hard-gap profile。
- leading grid failure gate 已拆出 leading grid score、late hard-gap sequence
  和 enhanced promotion guard helper；最终 reason 保持
  `leading_grid_separator_failure`。
- separator gate 已新增 `SeparatorGateEvidence` 摘要对象，集中汇总
  hard / model / width / leading-grid evidence；各 gate profile 只消费该摘要
  和 policy 参数，输出 detail key 保持不变。
- separator gate dispatch 已收敛到 `SeparatorGateAssessment`：single-frame、
  confidence threshold、leading-grid failure 和 gate profile 选择统一在该 helper
  中完成，外层入口只负责 evidence -> assessment -> detail。
- separator gate profile vocabulary 已集中到中性 policy vocabulary 模块，format
  presets、默认参数、scoring 和 gate dispatch 共享同一组常量；policy assembly
  会拒绝未知 profile，不再隐式回落到 strict profile。
- separator gate active entry 已从旧的 `candidate_has_hard_separator_evidence`
  重命名为 `assess_separator_gate`；调用方局部变量同步改为
  `separator_gate_ok/detail`，report key 保持 `separator_hard_evidence` 不变。
- 未使用的 `CandidateGateOutcome` gate 占位类型已删除，减少无调用方接口。
- robust grid model gap refinement 已移除未使用的 format identity 参数；
  primary separator refinement 不再接收完整 `FormatSpec`。
- grid-derived outer box 计算已从 separator gap lifecycle 移到
  `detection.candidate.proposal.outer.grid_refine`；separator lifecycle 只消费
  grid detail 并在需要时重新生成 gaps，不拥有 outer 修正规则。
- grid-derived outer refine 的编排已上移到 `build_detection_for_outer`：
  `separator_gaps.py` 只提供 primary gap build 与 late separator refinements，
  candidate build 在两段之间决定是否用 refined outer 重新 build gaps。
- enhanced separator 内部语义收敛为 enhanced gap promotion：active detail key
  改为 `enhanced_gap_promotion`，gate 从该 detail 读取 promotion count，内部
  gap method 判断统一使用常量。
- edge-pair refinement 已明确为 edge-pair gap correction：active detail key
  改为 `edge_pair_correction`，debug gap overlay 也改为消费 gap method 常量。
- edge-pair 参数边界已收紧：format preset 仍可用
  `SeparatorEdgePairPolicy` 表达语义，policy assembly 会在 runtime policy 中
  转换为 `EdgePairParameters`，`geometry/edge_pairs.py` 不再 duck-type
  policy-like 对象。
- edge-pair 专用 edge-refine profile 已从基础 `separator_profile.py` 拆出到
  `geometry/edge_refine_profile.py`；基础 separator profile 只保留 separator
  signal 与通用 profile helper。
- edge-pair correction 已与 runtime cache 解耦：candidate build 负责取得 cached
  edge/background profile，`geometry/edge_pairs.py` 只消费 profile arrays 并返回
  gap correction detail。
- separator refinement 的纯转发 facade 已删除：candidate build 直接调用
  `geometry.edge_pairs`、`geometry.robust_grid`、`geometry.enhanced_separator`
  和 `geometry.nearby_separator`，避免 `proposal/separator/refinement.py`
  成为没有独立职责的假层级。
- standard gap search 已与 gap geometry helper 拆开：`geometry/gap_search.py`
  只负责 profile window / width / threshold / candidate ranking；
  `geometry/gap_geometry.py` 负责 gap 几何约束、width CV 和局部几何误差。
- separator-derived outer band 与 broad-width band 已统一为
  `geometry.separator_band.SeparatorBand`；outer proposal 不再消费裸 dict band，
  宽度只作为同一 separator band 的属性和 evidence detail。
- 新增错误 PASS 不可接受；保守 REVIEW 和 schema / reason diff 必须解释。
- TIFF metadata、位深、ICC、resolution 和 compression 行为保持不变。

### 版本摘要

| 版本 | 状态 | 摘要 |
|---|---|---|
| V4.9 | 当前 active 开发版 | Evidence-governed policy reset。新增 explicit format physical spec、clean entry layer、semantic decision contract、conservative PASS/REVIEW gate、`v4_9_policy_schema_1`、policy-controlled three-panel Debug Analysis 和 `tools/regression/` reference classifier。目标是 0 新错误 PASS，并允许可解释的 conservative diff。 |
| V4.7 | 旧 active 开发版 | Source-layout rewrite。移除旧桥接层，保留薄入口和 `x5crop/` 分层实现；format / mode 行为由 policy 管理；workflow 编排，detection / geometry / candidate 等职责拆入专门模块。目标是保持 V4.5.4 行为，同时让源码边界清晰。 |
| V4.6 | 开发版 | 建立 `DetectionPolicy` 架构，将 detector、count、outer、separator、content、scoring、selection、postprocess、diagnostics 和 output 行为按 format / strip mode 注册。 |
| V4.5.x | 开发版 | 120-66 broad separator width / strict-holder、half geometry support、policy view、postprocess 和 separator-geometry outer 收敛。 |
| V4.4.x | 开发版 | 收敛 full / partial outer proposal、output folder 命名、Debug Analysis 可读性、partial safe-extra-frames 和缓存效率；默认输出目录定为 `x5_crop_output/`。 |
| V4.3.x | 开发版 | 建立 full-mode outer proposal layer，并为 partial mode 增加 conservative safe-extra-frames gate。 |
| V4.2.8 | 当前稳定发布版 | 启动器交互改进：仅在 partial mode 开启后询问 count；Return 或 `auto` 表示自动判断。检测逻辑不变。 |
| V4.2.x | 开发版 | 建立 120 family geometry model、separator-first outer proposal、120-66 / 120-67 保守修复和 half-frame full geometry support。 |
| V4.1.x | 开发版 | 120-66 / 120-67 参数校准、outer retry 收敛和 120 共享 policy 整理。 |
| V4.0.x | 历史稳定 / 开发版 | 模块化重写和 135 wide-spacing 支持；根入口变薄，主要职责迁入 `x5crop/`。 |
| V3.6 - V3.9 | 历史开发版 | format-aware policy / tuning、frame fit、diagnostics、hard-gap trust、nearby separator、overlap risk 和 edge-pair 相关工作。 |
| V3.0 - V3.5 | 历史基线 / 实验 | 建立主流程、output-only bleed 和 V3 风格检测链路；若干 hard-gap / grid 实验已暂停或回滚。 |

### V4.9 验证摘要

已验证：

- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.9`。
- V4.9 package compile 通过。
- `python3 -m x5crop.policies.consistency` 对 14 个 format / strip mode 的
  runtime policy 与 final decision contract 同步关系通过。
- `git diff --check` 通过。
- Mac 主启动器和 diagnostics 启动器 `bash -n` 通过。
- Entry、workflow、policy、foundation、detection、report/debug/export 和 tools 分层 smoke 通过。
- `135-dual/full` mode detector 内部拆为 thin orchestrator、policy/spec context、
  lane split、lane detect 和 lane merge；lane format / count / total format /
  review-only reason 从 active policy 与 format spec 读取，不再隐藏在子模块中。
- `135-dual/full` lane split 固定使用 work image 的 height / 2；相关文件、policy id、
  analysis source 和 review reason 统一使用 `dual_lane` 命名，不再使用泛化的并行 lane 命名。
- `review_only` mode 已推广为通用 mode detector 接口；`135-dual/partial` 只是
  该接口的当前使用者，不再通过 dual-lane detector 或旧的专用模块旁路。
- outer 源码层级已降入 `detection/candidate/proposal/outer/` 与
  `detection/candidate/proposal/correction/`；outer 只作为 candidate proposal
  family 负责 proposal / correction，separator bands、outer-content alignment
  和 cache key 分别归入 evidence / detection cache 层。
- 源码包边界进一步收敛：entry、runtime、cache、report、formats、candidate lifecycle
  和 policies 子层均以真实 package 表达，不再依赖根层平铺文件或旧 policy
  文件名前缀表达职责。
- outer runtime policy 已收敛为 `proposal` 与 `correction` 两块：
  `proposal.base` 负责基础外框候选，`proposal.geometry` 统一管理 partial
  placement、separator geometry 与 broad-width gap profile variants；
  `correction.geometry_consistency` 合并原 short-axis 与 format-geometry retry，
  `correction.content_containment` 替代原 content-aligned retry 命名。
- corrected outer 不再在 correction helper 内直接完成重建与评估；统一通过
  `detection/candidate/build/corrected_outer.py` 重新 build detection、重算 evidence
  并重新 apply candidate assessment。outer correction 只改变候选输入，PASS /
  REVIEW 仍只由 candidate gate 和 final decision contract 决定。
- separator-derived outer policy 不再由各 format 单独打开 local/full-width/broad-width profile；
  `SeparatorOuterFamilyPolicy` 统一声明 phase、mode 和 partial 显式 count 门控，
  full 启用全部 separator-derived families，auto-count partial 保持保守。
- outer correction policy 已通用化为 `OuterCorrectionFamilyPolicy`：标准 full 可用
  long-axis、short-axis 和 content-containment correction；partial 只有显式 count
  时可用 strict long-axis、short-axis 和 content-containment correction；partial auto 不生成
  corrected outer candidate。
- outer correction proposal type 已归入
  `detection/candidate/proposal/correction/types.py`；candidate 层只消费
  `OuterCorrectionProposal`，outer correction 不再 import candidate reassessment 类型。
- `outer_correction_extension` 现在只表示 standard-strip candidate lifecycle 允许
  corrected-candidate extension；实际开启面由 correction family 的 mode、strip mode
  和 partial 显式 count 门控决定。
- outer correction candidate extension 已从 finalization 移入 detection pipeline /
  candidate lifecycle：outer correction proposal 只生成 corrected box，candidate 层负责
  重新 build detection、重新 assessment，pipeline 将 corrected candidate 追加回候选池后
  统一 selection。
- final PASS / REVIEW 实现已从 `detection/final/` 移到 `detection/decision/`；
  finalization 不再生成候选，只做 output bleed、approved geometry adjustment 和
  read-only diagnostics attachment。
- separator-derived outer 已收敛为统一
  `detection/candidate/proposal/outer/separator.py` 引擎；
  outer scope（local / full-width）与 gap search profile（standard / broad_width）
  组合生成候选；broad_width 不再作为 outer variant。full 默认启用全部
  separator-derived scope/profile 组合，partial 显式 count 才启用 extension profiles，
  active code 不再保留独立 broad-width outer 分支。
- separator width 语义已降级为 gap search profile：`standard` 与 `broad_width`
  属于同一候选计划，最终 gap method 仍是普通 `detected` hard separator；
  broad width 只写入 `gap_search_profile`、`separator_width_evidence`、gate detail
  和 partial holder detail。
- separator gap lifecycle 已从 `build_detection_for_outer` 抽到
  `detection/candidate/build/separator_gaps.py`：separator gap lifecycle 生成
  origin/pitch、standard/broad-width gaps、edge-pair、grid、enhanced 和 nearby
  refinement 结果，再由 `detection.py` 负责编排 refined-outer rebuild、frame fit、
  score 和 detail assembly。
- 普通 separator profile / gap search 已做行为等价拆分：
  `geometry/separator_profile.py` 将中段采样、分段极端亮/暗、uniform soft score
  和列向梯度分开；`geometry/gap_search.py` 将 window、width limits、thresholds、
  band expansion 和 detected-candidate ranking 分开，方便人工审核普通 separator
  是如何被看见的。
- separator refinement 已做行为等价拆分：candidate build 直接调用 geometry
  refinement helpers，避免保留只做别名转发的 proposal refinement facade；
  `geometry/edge_pairs.py` 将 search limits、candidate generation、best-pair
  selection 和 replacement eligibility 分开；
  `geometry/robust_grid.py` 将 reliable anchor selection、grid fit、predicted center
  和 hard-gap protection / override adjustment 分开，方便继续审核 model evidence
  何时可以移动 gap。
- hard-gap trust 已做行为等价收敛：`geometry/gap_trust.py` 统一保存像素 signal、
  runtime hard-gap trust classifier 和 diagnostic hard-gap trust classifier；
  `detection/evidence/gap_diagnostics.py` 不再重复 trust 分类条件，只负责生成
  read-only diagnostic record。
- enhanced / nearby separator refinement 已做行为等价拆分：
  `geometry/enhanced_separator.py` 将 detected gap validation、enhanced promotion
  和 merge detail 分开；`geometry/nearby_separator.py` 将 search context、
  candidate ranking、stronger test 和 geometry acceptance 分开，方便继续人工审核
  separator refinement 的阈值策略。
- separator refinement 的 policy surface 已补齐：`enhanced.min_score` 和
  `nearby_correction.width_cv_slack` 从 `FormatParameters` 显式流入 runtime
  `SeparatorPolicy`，并出现在 policy/report detail 中；默认值保持旧行为。
- separator method vocabulary 已对齐：runtime `SeparatorPolicy.hard_methods`
  使用真实 gap method `detected / edge-pair / enhanced-detected`，
  `model_methods` 使用 `grid / equal / content`，并在 policy/report detail 中可见。
- `.gitignore` 显式保留 `x5crop/detection/candidate/build/*.py`，避免源码层级被
  通用 `build/` 输出规则误隐藏。
- candidate source orchestration 已去 retry 化：standard / broad-width gap profiles、
  separator-derived outer、content candidate 和 safety candidate 都进入一次性
  candidate plan，所有候选统一经过 candidate assessment 与 final decision contract。
- candidate execution budget 已加入 candidate lifecycle：primary separator candidate
  先经过 assessment；若 auto gate、content support、hard separator、confidence
  margin 和 review reason 均证明可靠，则 extension profiles / outer scope-profile combinations
  只记录 skipped detail；outer correction 还会确认 outer alignment ok
  后才跳过额外候选计算。
- execution budget detail 增加 `action`、`reason`、`stage` 和可靠性摘要，方便
  report 人工审核 primary-only、expanded-after-primary 与 outer-correction skip。
- partial placement outer 已收敛到 `policy.outer.proposal.geometry.partial_placement`：标准
  partial 先尝试 edge-anchored 位置候选，edge 候选达到 trust 门槛时跳过
  floating 位置候选；full 与 review-only mode 不启用。edge-anchor 只负责
  提出候选，最终 PASS 仍必须经过 hard separator、content 和 geometry gate。
- 14 个 format / strip mode decision contract policy smoke 通过；final contract
  由 active runtime `DetectionPolicy` 派生，避免 geometry support、partial edge
  和 diagnostics/output policy 漂移。
- 单文件 Debug Analysis smoke 生成 V4.9 three-panel debug JPG。
- Cached analysis reuse smoke 覆盖 approved 自动导出和 needs_review 跳过导出。
- 七组本地 V4.5.4 reference reports 通过 safety classifier：

```text
rows compared: 103
unacceptable_wrong_pass: 0
risky_regression: 0
```

reference sets：

```text
Test/135/4.5.4/split_report.jsonl
Test/new_135/4.5.4/split_report.jsonl
Test/120/66/4.5.4/split_report.jsonl
Test/120/66/4.5.4_partial/split_report.jsonl
Test/120/67/4.5.4/split_report.jsonl
Test/半格/full/4.5.4/split_report.jsonl
Test/半格/partial/4.5.4_partial/split_report.jsonl
```

说明：

- V4.9 不追求 0 diff；验收重点是 0 `unacceptable_wrong_pass`。
- 已知 metadata/schema diff 来自 V4.9 schema、reason vocabulary 和 policy detail 变化。
- 本地验证环境 process worker 不可用时会 fallback 到 thread workers。

尚未作为 V4.9 release 验证完成：

- default-deskew export timing。
- `xpan`、`120-645` 和 `135-dual` full sample reference comparison。
- Release package generation。

### 发布策略

- GitHub Releases 是用户下载入口。
- `main` 是开发分支，可以领先稳定发布版。
- 发布包只包含用户运行需要的单文件脚本、启动器、TXT 用户文档和安装/卸载器。
- 用户发布包不包含 `x5crop/`、`archive/`、`CHANGELOG.md`、`AGENTS.md`、
  `LICENSE`、`.github/`、diagnostics launcher、Test 文件或生成输出。

## English Changelog

### Current Principles

- V4.9 is an evidence-governed policy reset, not a detector-threshold loosening.
- V4.5.4 / V4.7 reference reports are historical baselines, not required 0-diff oracles.
- Automatic PASS must be explained by combined outer, separator, geometry,
  content, and risk evidence.
- Weak grid, equal, content-only, safety, or untrusted partial-edge candidates
  default to REVIEW.
- Active retry architecture is retired; broad-width gap search profiles, safety
  candidates, and corrected outers are assessed as candidate-plan entries or
  candidate extensions.
- Separator-derived outer families are generalized: standard full strips enable
  local, full-width, and broad-width gap profile variants; partial strips enable
  extension variants only when count is explicit.
- Candidate execution budget separates eligibility from execution: reliable
  primary separator assessment may skip full-width and broad-width gap profile;
  outer correction also requires ok outer alignment before it skips.
- Detection layering is aligned as pipeline / modes / candidate proposal
  lifecycle / evidence / decision / final. Outer / separator / content / safety
  are candidate proposal families, not top-level detection sublayers. PASS /
  REVIEW belongs to the decision layer, and finalization is output-adjacent only.
- The Gap / Separator logic family now follows the same lifecycle model as outer:
  `detection.candidate.proposal.separator` owns separator proposal, correction,
  width evidence, and separator-derived outer band evidence; `geometry` keeps
  the lower-level profile/search/trust math.
- New wrong PASS is unacceptable; conservative REVIEW and schema / reason diffs
  require explanation.
- TIFF metadata, bit depth, ICC, resolution, and compression behavior remain unchanged.

### Version Summary

| Version | Status | Summary |
|---|---|---|
| V4.9 | Current active development | Evidence-governed policy reset. Adds explicit format physical specs, a clean entry layer, semantic decision contract, conservative PASS/REVIEW gate, `v4_9_policy_schema_1`, policy-controlled three-panel Debug Analysis, and `tools/regression/` reference classifier. The goal is 0 new wrong PASS with explainable conservative diffs. |
| V4.7 | Previous active development | Source-layout rewrite. Removes old bridge layers, keeps a thin entry and layered `x5crop/` implementation, moves format/mode behavior into policy, and splits workflow, detection, geometry, and candidate responsibilities into focused modules. |
| V4.6 | Development | Introduces `DetectionPolicy` for detector, count, outer, separator, content, scoring, selection, postprocess, diagnostics, and output behavior by format / strip mode. |
| V4.5.x | Development | Converges 120-66 broad separator width / strict-holder behavior, half geometry support, policy views, postprocess, and separator-geometry outer. |
| V4.4.x | Development | Refines full / partial outer proposal responsibilities, output-folder naming, Debug Analysis readability, partial safe-extra-frames, and cache efficiency. |
| V4.3.x | Development | Builds full-mode outer proposal layering and conservative partial safe-extra-frames support. |
| V4.2.8 | Current stable release | Improves launcher interaction: count is requested only when partial mode is enabled; Return or `auto` keeps automatic count estimation. Detection logic is unchanged. |
| V4.2.x | Development | Builds 120 family geometry model, separator-first outer proposal, conservative 120-66 / 120-67 fixes, and half-frame full geometry support. |
| V4.1.x | Development | Calibrates 120-66 / 120-67 parameters, converges outer retry, and introduces shared 120 policy structure. |
| V4.0.x | Historical stable / development | Modular rewrite and 135 wide-spacing support; root entry becomes thin and main responsibilities move into `x5crop/`. |
| V3.6 - V3.9 | Historical development | Format-aware policy / tuning, frame fit, diagnostics, hard-gap trust, nearby separator, overlap risk, and edge-pair work. |
| V3.0 - V3.5 | Historical baseline / experiments | Establishes the main workflow, output-only bleed, and V3-style detection chain; several hard-gap / grid experiments are paused or reverted. |

### V4.9 Validation Summary

Verified:

- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.9`.
- V4.9 package compile passes.
- `python3 -m x5crop.policies.consistency` passes for the runtime policy and
  final decision contract sync across 14 format / strip-mode combinations.
- `git diff --check` passes.
- Main Mac launcher and diagnostics launcher pass `bash -n`.
- Entry, workflow, policy, foundation, detection, report/debug/export, and tools layer smoke checks pass.
- The `135-dual/full` mode detector is split into a thin orchestrator,
  policy/spec context, lane split, lane detect, and lane merge; lane format /
  count / total format / review-only reason now come from the active
  policy and format spec instead of hidden submodule constants.
- `135-dual/full` lane split now uses the work-image height / 2 midpoint; related
  files, policy ids, analysis source, and review reasons use `dual_lane` naming
  instead of generic lane wording.
- `review_only` mode is now a generic mode-detector interface; `135-dual/partial`
  is only the current user of that interface and no longer routes through the
  dual-lane detector or the old dedicated module.
- Outer source layout now lives under `detection/candidate/proposal/outer/` and
  `detection/candidate/proposal/correction/`; outer is a candidate proposal
  family only, while separator bands live in
  `detection/candidate/proposal/separator`; outer-content alignment and cache
  keys live in evidence / detection cache layers.
- Separator-derived outer proposals are consolidated into the single
  `detection/candidate/proposal/outer/separator.py` engine; outer scope (local /
  full-width) and gap search profile (standard / broad_width) combine to
  generate candidates. `broad_width` is no longer an outer variant. Full strips
  enable all separator-derived scope/profile combinations, explicit-count
  partial strips enable extension profiles, and active code no longer keeps
  a separate broad-width outer branch.
- Separator width semantics are downgraded to gap search profiles: `standard`
  and `broad_width` belong to the same candidate plan, final gap methods remain
  ordinary `detected` hard separators, and broad-width support is reported
  through `gap_search_profile`, `separator_width_evidence`, gate detail, and
  partial-holder detail.
- Separator gap lifecycle is extracted from `build_detection_for_outer` into
  `detection/candidate/build/separator_gaps.py`: candidate build now produces
  origin/pitch, standard/broad-width gaps, edge-pair, grid, enhanced, and nearby
  refinement results before `detection.py` handles frame fit, scoring, and
  detail assembly.
- Edge-pair parameter ownership is tightened: format presets may still use
  `SeparatorEdgePairPolicy` for semantic declaration, policy assembly converts
  those presets into `EdgePairParameters`, and `geometry/edge_pairs.py` no
  longer duck-types policy-like objects.
- Ordinary separator profile / gap search code is split without behavior changes:
  `geometry/separator_profile.py` separates vertical sampling, segmented extreme
  evidence, uniform soft score, and column gradient signals; `geometry/gap_search.py`
  is now hard-only `find_detected_gap`, returning a `GapSearchResult` with a
  detected hard gap or fallback score / reason. Standard separator proposal owns
  the explicit `equal` fallback when no hard gap is found. Window, width limits,
  thresholds, band expansion, detected-candidate collection, best-candidate
  selection, band evidence measurement, prominence support, and width-profile
  support are split so ordinary separator detection can be reviewed step by step.
- Equal / grid / content model-gap proposal is centralized in `geometry.model_gaps`,
  with profile equal-split proposal in `detection.candidate.proposal.separator.model`;
  build, safety, refinement, and content-candidate paths no longer hand-write
  `"equal"` / `"grid"` / `"content"` method strings.
- Separator refinement is split without behavior changes: candidate build calls
  geometry refinement helpers directly instead of keeping a re-export-only
  proposal refinement facade; `geometry/edge_pairs.py` separates search limits,
  typed candidate generation, best-pair selection, and replacement eligibility;
  candidate build owns cached edge/background profile retrieval, while
  `geometry/edge_pairs.py` consumes profile arrays and pure parameter objects;
  `geometry/robust_grid.py` separates reliable anchor
  selection, grid fit, predicted center, and hard-gap protection / override
  adjustment so model evidence movement can be reviewed directly. Grid-derived
  outer-box calculation now lives in `detection.candidate.proposal.outer.grid_refine`;
  the separator gap lifecycle consumes grid detail and may rebuild gaps, but it
  does not own the outer-box adjustment rule.
- The pure separator-refinement facade has been removed: candidate build now
  calls `geometry.edge_pairs`, `geometry.robust_grid`,
  `geometry.enhanced_separator`, and `geometry.nearby_separator` directly instead
  of keeping `proposal/separator/refinement.py` as a re-export-only layer.
- Grid-derived outer refine orchestration now lives in `build_detection_for_outer`:
  `separator_gaps.py` provides primary gap build and late separator refinements
  only, while candidate build decides whether to rebuild gaps with a refined
  outer between those stages.
- Broad-width detected gap generation now separates the width-profile gap window,
  run scoring, best candidate selection, and core-width clipped detected-gap
  output. The output remains an ordinary `detected` hard gap and does not add a
  separate gap method.
- Width-profile search parameters and candidate strategy are split:
  geometry consumes only `SeparatorWidthProfileSearchParameters`, while
  `SeparatorWidthProfilePolicy` keeps mode / required count / candidate budget /
  full-selection semantics. Reports expose both the combined `width_profile`
  view and the pure `width_profile_search` parameters.
- Separator width evidence requirements are now detail consumers: candidate
  build creates `separator_width_evidence`, while partial-safe / gate logic only
  applies their own requirements to existing evidence instead of regenerating
  separator evidence.
- The `all_internal_gaps_hard` gate now separates full/default-count
  supplemental broad-width and edge-pair min-score helpers. Failure reasons keep
  their existing semantics, while successful decisions still report the main
  hard-gap profile.
- The leading-grid failure gate now separates leading grid scores, late hard-gap
  sequence checks, and enhanced promotion guard helpers. The final reason remains
  `leading_grid_separator_failure`.
- The separator gate now builds a `SeparatorGateEvidence` summary for hard,
  model, width, and leading-grid evidence. Gate profiles consume that summary
  plus policy parameters, while output detail keys remain unchanged.
- Separator gate dispatch now goes through `SeparatorGateAssessment`: single-frame,
  confidence threshold, leading-grid failure, and gate-profile selection are
  handled by that helper, while the outer entry only performs evidence ->
  assessment -> detail.
- Separator gate profile vocabulary is centralized in a neutral policy vocabulary
  module. Format presets, defaults, scoring, and gate dispatch share the same
  constants, and policy assembly rejects unknown profiles instead of implicitly
  falling back to the strict profile.
- The active separator gate entry has been renamed from
  `candidate_has_hard_separator_evidence` to `assess_separator_gate`; caller
  locals now use `separator_gate_ok/detail`, while the report key remains
  `separator_hard_evidence`.
- The unused `CandidateGateOutcome` gate placeholder type has been removed.
- Hard-gap trust is centralized without behavior changes: `geometry/gap_trust.py`
  now owns pixel signals, the runtime hard-gap trust classifier, and the
  diagnostic hard-gap trust classifier; `detection/evidence/gap_diagnostics.py`
  records diagnostics without duplicating trust classification conditions.
- Enhanced / nearby separator refinement is split without behavior changes:
  `geometry/enhanced_separator.py` separates detected gap validation, enhanced
  promotion, and merge detail; `geometry/nearby_separator.py` separates search
  context, candidate ranking, stronger test, and geometry acceptance so separator
  refinement thresholds can be reviewed directly.
- The separator refinement policy surface now exposes `enhanced.min_score` and
  `nearby_correction.width_cv_slack` from `FormatParameters` through runtime
  `SeparatorPolicy` and policy/report detail; defaults preserve existing behavior.
- Separator method vocabulary is aligned: runtime `SeparatorPolicy.hard_methods`
  uses real gap methods `detected / edge-pair / enhanced-detected`,
  `model_methods` uses `grid / equal / content`, and both are visible in
  policy/report detail.
- `.gitignore` explicitly keeps `x5crop/detection/candidate/build/*.py` visible
  so source layers are not hidden by the generic `build/` output rule.
- Candidate source orchestration no longer uses active retry control flow:
  standard / broad-width gap profiles, separator-derived outers,
  content candidates, and safety candidates enter one candidate plan and pass
  through the same candidate assessment and final decision contract.
- Candidate execution budget now assesses the primary separator candidate before
  running extension profiles / outer scope-profile combinations; reliable primary results
  record skipped detail instead of paying for extra candidate computation.
  Correction computation skips only after reliable selection and ok outer
  alignment.
- Execution budget detail now records `action`, `reason`, `stage`, and reliability
  summary fields so reports can show primary-only, expanded-after-primary, and
  outer-correction skip decisions directly.
- Corrected outer extension now runs inside the detection pipeline before final
  selection: proposal creates only corrected boxes, candidate code rebuilds and
  reassesses them, and finalization no longer creates candidates.
- Outer correction policy is generalized as `OuterCorrectionFamilyPolicy`: standard
  full strips can use long-axis, short-axis, and content-containment correction;
  explicit-count partial strips can use strict long-axis, short-axis, and
  content-containment correction; auto-count partial strips do not generate
  corrected outer candidates.
- The outer correction proposal type now lives in
  `detection/candidate/proposal/correction/types.py`; candidate code consumes
  `OuterCorrectionProposal` instead of outer correction importing candidate
  reassessment types.
- Final PASS / REVIEW implementation lives under `detection/decision/`; final
  code only handles output bleed, approved geometry adjustment, and read-only
  diagnostic attachment.
- 14 format / strip-mode decision contract policy smoke checks pass; the final
  contract is derived from the active runtime `DetectionPolicy` to prevent
  geometry support, partial-edge, diagnostics, and output-policy drift.
- Single-file Debug Analysis smoke writes a V4.9 three-panel debug JPG.
- Cached analysis reuse smoke covers approved auto export and needs_review skip-export paths.
- Seven local V4.5.4 reference reports pass safety classification:

```text
rows compared: 103
unacceptable_wrong_pass: 0
risky_regression: 0
```

Notes:

- V4.9 does not target 0 diff; acceptance focuses on 0 `unacceptable_wrong_pass`.
- Known metadata/schema diffs come from V4.9 schema, reason vocabulary, and policy detail changes.
- Local verification may fall back from process workers to thread workers.

Not yet completed as V4.9 release validation:

- Default-deskew export timing.
- `xpan`, `120-645`, and `135-dual` full sample reference comparison.
- Release package generation.

### Release Policy

- GitHub Releases are the user-facing download channel.
- `main` is the development branch and may be ahead of the stable release.
- User release packages contain only the standalone script, launchers, TXT user
  docs, and install/uninstall launchers.
- Normal user packages exclude `x5crop/`, `archive/`, `CHANGELOG.md`,
  `AGENTS.md`, `LICENSE`, `.github/`, diagnostics launchers, Test files, and
  generated outputs.
