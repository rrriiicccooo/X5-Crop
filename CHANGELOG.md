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
- runtime `DetectionPolicy`、policy assembly 和 final decision contract 分层。
- detection 按 `modes`、`physical`、`guidance`、`evidence`、
  `candidate.{plan,proposal,build,assessment,selection,extension}`、`decision` 和
  `final` 分层。
- candidate assessment 拆为 support scoring、base scoring 和 gate support。
- photo-size consistency 成为共享物理模型；`photo_width_*` 表示照片影像区域尺寸证据，
  separator 宽度变化保留为 observed detail。
- content scoring 使用内容保护语义：安全 overcut 和空 frame 不是负面证据，真实内容损伤才是风险。
- separator 语义收敛为单一 `width_aware` proposal；observed width 是中性实测宽度证据。
- 120-66 partial 的 separator-width 安全检查表述为 holder-edge disambiguation，不把宽
  separator 写成唯一物理身份。
- `135-dual/full` 使用独立 dual-lane mode detector；`135-dual/partial` 走通用
  review-only 保守路径。
- Debug Analysis 默认保持三联图；更细 evidence / gate / risk 解释写入 report detail。

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
- Runtime `DetectionPolicy`, policy assembly, and final decision contract are
  separated.
- Detection is layered as `modes`, `physical`, `guidance`, `evidence`,
  `candidate.{plan,proposal,build,assessment,selection,extension}`, `decision`,
  and `final`.
- Candidate assessment is split into support scoring, base scoring, and gate
  support.
- Photo-size consistency is a shared physical model. `photo_width_*` names refer
  to photo image-region size evidence; separator width variation remains observed
  detail.
- Content scoring uses content-protection semantics: safe overcut and empty
  frames are not negative evidence; harm to real content is risk.
- Separator semantics are consolidated into the single `width_aware` proposal;
  observed width is neutral measured evidence.
- 120-66 partial separator-width safety is expressed as holder-edge
  disambiguation, not as broad separator identity.
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
