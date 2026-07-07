# X5 Crop 更新日志 / Changelog

本文件记录版本级变化、行为边界、验证结论、发布策略和回滚线索。当前架构契约见
`ARCHITECTURE.md`；用户操作说明见 `README.md` 和 `快速启动_Quick_Start.md`。

This file records version-level changes, behavior boundaries, validation
conclusions, release policy, and rollback context. The active architecture
contract lives in `ARCHITECTURE.md`; user instructions live in `README.md` and
`快速启动_Quick_Start.md`.

当前 active 脚本版本：V4.9

当前稳定发布版本：v4.2.8

Current active script version: V4.9

Current stable release: v4.2.8

## 中文更新日志

### 记录范围

本文件只记录对版本判断有价值的信息：

- 用户可见行为变化。
- 检测安全边界和回滚依据。
- 发布包、验证范围和未完成验证项。
- 大的源码结构里程碑。

实现细节、人工审核台账和当前架构规则不写在这里；这些内容分别属于源码、handoff
和 `ARCHITECTURE.md`。

### 当前开发线：V4.9

V4.9 是 evidence-governed policy reset，不是检测阈值放宽版本。它继承 V4.7 的源码
分层成果，并把自动 PASS 收敛为明确的证据契约。

关键边界：

- V4.5.4 / V4.7 reference reports 是 historical baseline，不再是 mandatory 0-diff
  oracle。
- 新增 wrong PASS 不可接受；保守 REVIEW、schema diff 和 reason diff 必须解释。
- 自动 PASS 必须由 outer、separator、geometry、content 和 risk 证据共同解释。
- weak grid、equal、content-only、safety、review-only 和不可信 partial-edge 候选默认
  REVIEW。
- content 是 soft evidence + guidance family；它可以提示 outer / separator search，
  也可以生成 review-only content-model candidate，但不拥有 physical result 或 PASS /
  REVIEW。
- content scoring 改为内容保护语义：full 和 partial 都允许安全多切空 frame；评分和 gate
  关注真实图像是否完整包含，而不是要求每个 frame 都有内容。
- content support score 和 content quality score 拆清：前者表示真实内容完整包含的支持度，
  后者只表示影像证据强弱并供 diagnostics / independence / partial-holder 解释。
  当 detail 明确给出 `content_harm_risk` 时，content support score 不再读取旧
  `support` summary 作为 containment 证据。
- outer area、content quality 和 width instability 的评分语义继续物理化：raw outer area
  不再单独制造 hard review；content quality 只作为 evidence-strength detail；lucky-pass
  width instability 只信任 `photo_edges` 来源的照片宽度证据；partial-holder 和
  evidence-dependency validation 不再把低 content quality score 当作独立失败原因。
- global contrast 从 base confidence weight 和独立 review reason 中移除，只保留为
  image-quality detail；基础评分现在只由 separator/gap support 和照片宽度稳定性组成。
- raw outer area 从 base confidence weight 中移除；outer area 继续写入 profile detail，
  并由 final outer-content alignment / decision contract 判断是否真的有害。
- geometry support score 不再消费 raw `outer_area_ratio`，也不再在缺失 content
  aspect evidence 时用默认低分扣分；它只消费 frame count、显式 `photo_width_cv`
  和可用的 aspect evidence。
- partial mode 不再因为 count 小于默认满卷 count 被通用压分；只有单张 partial 或
  35mm 两张 partial 这类天然无法充分解释物理结构的情况继续标记
  `partial_too_ambiguous`。三张及以上 partial 改由 separator、content containment、
  照片宽度稳定性、holder-edge safety 和 final decision 共同判断。
- frame-box width detail 不再触发 `photo_width_unstable`、support score、
  gate-support、partial-holder 照片宽度阻断、risk credit 或 final photo-width gate；
  这些路径只消费 `photo_edges` 来源的照片宽度证据。
- `width_cv` 不再补充 `photo_width_cv`；照片宽度证据必须显式写入
  `photo_width_cv`。
- scoring / gate / partial-holder / decision contract 的宽度稳定性 policy 字段改为
  `photo_width_*` 命名；`width_cv` 仅保留为 generic diagnostic aggregate 或
  separator / gap 几何测量。
- lucky-pass risk 的宽度风险 policy、component 和 detail key 也收敛为
  `photo_width_*` 语义，避免把 frame-box 或 separator 宽度误读成风险来源。
- candidate-plan / outer family 的展开阶段命名从 `late` / `auxiliary` 收敛为
  `extension` / `supplemental`；这是 report/detail 语义清理，不调整阈值。
- separator build / refinement 命名继续收敛：`late_separator_refinement` 改为
  `nearby_separator_refinement` chain，pending reason 也改为职责名。
- `content_support_score` 去掉旧式未使用的 format / policy 参数，只接收 containment detail。
- `tools/tests/test_source_naming_contract.py` 修正项目根路径，移动到 `tools/tests/`
  后仍能真实扫描 active `x5crop/` source，并覆盖 late / auxiliary flow 词回流。
- 120-66 partial 的 separator-width 安全检查在 active detail / reason 中收敛为
  holder-edge disambiguation，避免把“宽 separator”当成唯一物理身份。
- separator 语义收敛为单一 `width_aware` proposal。observed width 是中性实测宽度证据；
  broad separator width 只是 gate / partial safety 消费的 evidence summary。
- separator width profile 不再拥有自己的 confidence cap；宽/窄 separator 本身不是风险，
  证据自举、候选竞争和 final decision 才能把候选拉回 REVIEW。
- retry / rescue 风格控制流已退休；safety candidate、content-guided separator 和
  corrected outer 都进入候选计划或候选扩展，再统一 assessment 和 selection。
- final PASS / REVIEW 属于 decision contract；finalization 只做 output-adjacent
  geometry、bleed、confidence cap 和只读 diagnostics attachment。
- TIFF metadata、位深、ICC、resolution 和已知无损压缩行为保持不变。

### V4.9 结构里程碑

- 入口和运行层收敛为 `entry`、`runtime.config`、`runtime.input_probe`、
  `runtime.app` 和 `runtime.workflow`。
- format physical facts 由 `x5crop.formats` 承担；format-specific 参数覆盖被限制在
  physical tolerance、content profile tolerance 和 search budget。
- runtime `DetectionPolicy` 和 final `DetectionDecisionContract` 分层；report 使用
  `v4_9_policy_schema_1` 公开 policy、evidence、risk、decision 和 selected candidate detail。
- detection 按 `modes`、`physical`、`guidance`、`evidence`、
  `candidate.{plan,proposal,build,assessment,selection,extension}`、`decision` 和
  `final` 分层。
- 开发用 unit tests 从根 `tests/` 收敛到 `tools/tests/`；根目录不再保留 active
  test package。
- candidate assessment 已进一步拆清：`assessment.scoring` 只保留 support score
  和 joint score；`assessment.base_scoring` 负责 base confidence / review reasons；
  `assessment.gate_support` 负责 hard-full calibration 和 separator geometry
  support 判断。
- width scoring 现在区分 `photo_width_cv`、`frame_box_width_cv` 和
  `separator_width_cv`：照片影像区域尺寸稳定性是 scoring / gate 证据；
  separator 宽度变化只作为 evidence detail，不再被误当成照片尺寸不稳。
- 新增共享 photo-size consistency 物理模型：separator proposal、separator-derived outer
  和 base scoring 现在消费同一套“照片尺寸一致、separator 宽度可变”的 detail。
  separator-derived outer 的 sequence ranking 优先解释为等照片尺寸，observed-width
  搜索不再因为偏离理论 separator 宽度而扣核心分。
- base outer 新增 side-independent holder-boundary candidate：每一边独立解释为
  holder-to-black-rim、holder-to-content 或 weak side，黑边不再被当作 outer 的必要定义。
- final decision 和 outer-content alignment 现在区分安全 overcut 与 undercrop：安全包住内容
  不再构成风险，真实内容越出 outer 才会触发 content harm risk。
- `135-dual/full` 使用独立 dual-lane mode detector；`135-dual/partial` 走通用
  review-only 保守路径。
- separator method vocabulary 集中到 `constants.py` 和 `gap_methods.py`；active hard
  gap method 为 `detected` 和 `edge-pair`，model methods 为 `grid`、`equal` 和 `content`。
- Debug Analysis 默认保持三联图；更细的 evidence / gate / risk 解释写入 report detail。

### V4.9 已验证状态

已验证：

- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.9`。
- V4.9 package compile 通过。
- `python3 -m x5crop.policies.consistency` 对 14 个 format / strip-mode 组合通过。
- `git diff --check` 通过。
- Mac 主启动器和 diagnostics 启动器 `bash -n` 通过。
- Entry、workflow、policy、foundation、detection、report/debug/export 和 tools 分层 smoke
  通过。
- Debug Analysis 单样本 smoke 生成 V4.9 三联 JPG。
- Cached analysis reuse smoke 覆盖 approved auto export 和 needs_review skip-export。
- 七组本地 V4.5.4 reference reports 通过 safety classification：

```text
rows compared: 103
unacceptable_wrong_pass: 0
risky_regression: 0
```

说明：

- V4.9 不以 0 diff 为目标；验收重点是 0 `unacceptable_wrong_pass`。
- 已知 metadata / schema diff 来自 V4.9 schema、reason vocabulary 和 policy detail。
- 本地验证可能从 process worker fallback 到 thread worker。

V4.9 release validation 尚未完成：

- 默认 deskew export timing。
- `xpan`、`120-645` 和 `135-dual` full sample reference comparison。
- Release package generation。

### 版本摘要

| Version | 状态 | 摘要 |
|---|---|---|
| V4.9 | 当前 active development | Evidence-governed policy reset；建立 final decision contract、保守 PASS/REVIEW gate、`v4_9_policy_schema_1`、policy-controlled Debug Analysis 和 reference classifier。目标是 0 new wrong PASS，并解释保守 diff。 |
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
- Detection safety boundaries and rollback context.
- Release package policy, validation scope, and missing validation.
- Major source-structure milestones.

Implementation detail, audit ledgers, and active architecture rules do not belong
here; they belong in source, handoff, and `ARCHITECTURE.md`.

### Current Development Line: V4.9

V4.9 is an evidence-governed policy reset, not a detector-threshold loosening. It
builds on the V4.7 source layout and turns automatic PASS into an explicit
evidence contract.

Key boundaries:

- V4.5.4 / V4.7 reference reports are historical baselines, not mandatory
  0-diff oracles.
- New wrong PASS is unacceptable; conservative REVIEW, schema diffs, and reason
  diffs must be explained.
- Automatic PASS must be explained by combined outer, separator, geometry,
  content, and risk evidence.
- Weak grid, equal, content-only, safety, review-only, and untrusted partial-edge
  candidates default to REVIEW.
- Content is a soft-evidence and guidance family. It may guide outer / separator
  search and may create review-only content-model candidates, but it does not
  own physical results or PASS / REVIEW.
- Content support score and content quality score are now separated: support
  means intact real-content containment, while quality only describes evidence
  strength for diagnostics, independence validation, and partial-holder detail.
  When detail explicitly reports `content_harm_risk`, content support score is
  no longer derived from the old `support` summary.
- Geometry support score no longer consumes raw `outer_area_ratio` and no
  longer substitutes a default low score when content-aspect evidence is
  missing. It consumes only frame count, explicit `photo_width_cv`, and
  available aspect evidence.
- `width_cv` no longer supplements `photo_width_cv`; photo-width
  evidence must be explicit in `photo_width_cv`.
- Partial mode is no longer generally confidence-capped just because count is
  below the default full-strip count. Only intrinsically ambiguous cases, such
  as a single-frame partial or two-frame 35mm partial, keep
  `partial_too_ambiguous`; three-frame-and-larger partial strips are judged by
  separator, content containment, photo-width stability, holder-edge safety,
  and final decision evidence.
- Separator semantics are consolidated into the single `width_aware` proposal.
  Observed width is neutral measured-width evidence; broad separator width is
  only an evidence summary consumed by gates and partial safety.
- Separator width profile no longer owns a confidence cap. Wide or narrow
  separators are not risk by themselves; evidence dependency, candidate
  competition, and final decision own any pullback to REVIEW.
- Retry / rescue-style control flow is retired. Safety candidates,
  content-guided separators, and corrected outers enter the candidate plan or
  candidate extension path, then share assessment and selection.
- Final PASS / REVIEW belongs to the decision contract; finalization only handles
  output-adjacent geometry, bleed, confidence caps, and read-only diagnostics
  attachment.
- TIFF metadata, bit depth, ICC, resolution, and known lossless compression
  behavior are unchanged.

### V4.9 Structural Milestones

- Entry and runtime are split into `entry`, `runtime.config`,
  `runtime.input_probe`, `runtime.app`, and `runtime.workflow`.
- Format physical facts belong to `x5crop.formats`; format-specific overrides
  are limited to physical tolerance, content profile tolerance, and search budget.
- Runtime `DetectionPolicy` and final `DetectionDecisionContract` are separate;
  reports use `v4_9_policy_schema_1` for policy, evidence, risk, decision, and
  selected candidate detail.
- Detection is layered as `modes`, `physical`, `guidance`, `evidence`,
  `candidate.{plan,proposal,build,assessment,selection,extension}`, `decision`,
  and `final`.
- Developer unit tests have moved from root `tests/` into `tools/tests/`; the
  root no longer carries an active test package.
- Candidate assessment is split further: `assessment.scoring` contains support
  scores and joint score only; `assessment.base_scoring` owns base confidence /
  review reasons; `assessment.gate_support` owns hard-full calibration and
  separator geometry support checks.
- Width scoring now separates `photo_width_cv`, `frame_box_width_cv`, and
  `separator_width_cv`: only explicit `photo_edges` photo-width evidence may
  feed support scores, gate support, risk credit, or final photo-width gates;
  frame-box width and separator-width variation remain diagnostic detail.
- A shared photo-size consistency model now feeds separator proposal,
  separator-derived outer, and base scoring with the same physical rule:
  photo image regions should be consistent, while separator width may vary.
  Separator-derived outer sequence ranking prefers equal photo size, and
  observed-width search no longer subtracts core score for diverging from the
  theoretical separator width.
- Base outer now includes a side-independent holder-boundary candidate. Each
  side can be explained as holder-to-black-rim, holder-to-content, or weak; a
  black rim is evidence for a side, not a required definition of outer.
- Scoring / gate / partial-holder / decision-contract width-stability policy
  fields now use `photo_width_*` names; plain `width_cv` remains a generic
  diagnostic aggregate or separator / gap geometry measurement wording.
- Lucky-pass width-risk policy fields, component names, and detail keys now use
  `photo_width_*` semantics to avoid implying frame-box or separator width risk.
- Candidate-plan / outer-family expansion phase names now use `extension` /
  `supplemental` instead of `late` / `auxiliary`; this is report/detail wording
  cleanup, not threshold tuning.
- Separator build / refinement naming continues the same cleanup:
  `late_separator_refinement` is now a `nearby_separator_refinement` chain, and
  pending detail uses responsibility wording.
- `content_support_score` no longer accepts unused format / policy parameters;
  it consumes containment detail only.
- `tools/tests/test_source_naming_contract.py` now resolves the project root
  correctly after moving under `tools/tests/`, so it scans active `x5crop/`
  source for late / auxiliary flow wording regressions.
- `135-dual/full` uses a dedicated dual-lane mode detector; `135-dual/partial`
  uses the generic conservative review-only path.
- Separator method vocabulary is centralized in `constants.py` and
  `gap_methods.py`. Active hard gap methods are `detected` and `edge-pair`;
  model methods are `grid`, `equal`, and `content`.
- Debug Analysis keeps a three-panel default; richer evidence / gate / risk
  explanation is written to report detail.

### V4.9 Verified State

Verified:

- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.9`.
- V4.9 package compile passes.
- `python3 -m x5crop.policies.consistency` passes across 14 format /
  strip-mode combinations.
- `git diff --check` passes.
- Main Mac launcher and diagnostics launcher pass `bash -n`.
- Entry, workflow, policy, foundation, detection, report/debug/export, and tools
  layer smoke checks pass.
- Single-file Debug Analysis smoke writes a V4.9 three-panel JPG.
- Cached analysis reuse smoke covers approved auto export and needs_review
  skip-export paths.
- Seven local V4.5.4 reference reports pass safety classification:

```text
rows compared: 103
unacceptable_wrong_pass: 0
risky_regression: 0
```

Notes:

- V4.9 does not target 0 diff; acceptance centers on 0 `unacceptable_wrong_pass`.
- Known metadata / schema diffs come from V4.9 schema, reason vocabulary, and
  policy detail.
- Local verification may fall back from process workers to thread workers.

Not yet completed as V4.9 release validation:

- Default-deskew export timing.
- `xpan`, `120-645`, and `135-dual` full sample reference comparison.
- Release package generation.

### Version Summary

| Version | Status | Summary |
|---|---|---|
| V4.9 | Current active development | Evidence-governed policy reset. Adds the final decision contract, conservative PASS/REVIEW gate, `v4_9_policy_schema_1`, policy-controlled Debug Analysis, and reference classifier. The goal is 0 new wrong PASS with explainable conservative diffs. |
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
