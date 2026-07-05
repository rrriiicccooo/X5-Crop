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
  `geometry/separator_width_profile.py`，参数归 `SeparatorPolicy`，outer policy
  只保留 separator-derived outer family / band 参数。
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
  `detection/candidate/build/separator_gaps.py`：candidate build 现在先生成
  origin/pitch、standard/broad-width gaps、edge-pair、grid、enhanced 和 nearby
  refinement 结果，再由 `detection.py` 负责 frame fit、score 和 detail assembly。
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
