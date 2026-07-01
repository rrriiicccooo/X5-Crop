# X5 Crop 更新日志 / Changelog

本文件记录版本变化、行为边界、验证结果和回滚线索。它不承担用户操作说明、
源码架构说明或 Codex 协作 handoff 职责。

This file records version changes, behavior boundaries, validation results, and
rollback context. It is not a user manual, architecture guide, or Codex handoff.

当前 active 脚本版本：V4.7

当前稳定发布版本：v4.2.8

Current active script version: V4.7

Current stable release: v4.2.8

## 中文更新日志

### 文档整理说明

2026-07-01 起，历史工作日志已压缩为版本摘要。详细逐步实验记录仍可通过 Git
历史追溯；当前文档只保留继续开发、验证和回滚需要的信息。

### 当前重点

- V4.7 是 clean-room source rewrite，不是检测阈值放宽版本。
- V4.7 以 V4.5.4 golden 输出为行为基线。
- 135 默认行为必须保持稳定。
- 120-66 dark-band / square-frame / separator-derived outer 风险模型必须保持格式隔离。
- weak grid、equal、content-only 证据不能因结构整理获得自动 PASS 权限。
- TIFF metadata、位深、ICC、resolution 和 compression 行为保持不变。

### 版本摘要

| 版本 | 状态 | 摘要 |
|---|---|---|
| V4.7 | 当前 active 开发版 | Clean-room source rewrite。移除旧兼容层，保留 `X5_Crop.py` 薄入口和 `x5crop/` 分层实现；format / mode 行为由 `x5crop/policies/` 管理；`workflow.py` 负责编排；`detection/pipeline.py` 收敛为 orchestration；candidate、dual-lane、partial-holder、fallback、outer retry、calibration 等职责拆入专门模块；geometry 拆分为 focused helpers。目标是保持 V4.5.4 行为，同时让源码边界清晰。 |
| V4.6 | 开发版 | 建立 `DetectionPolicy` 架构，将 detector、count、outer、separator、content、scoring、selection、postprocess、diagnostics 和 output 行为按 format / strip mode 注册。新增 workflow 层和 golden regression helper。 |
| V4.5.4 | 开发版 | 加强 120-66 full / partial 的宽黑条和 strict holder 处理；目标是更稳地解释 120-66 样片，不推广到其它格式。 |
| V4.5.3 | 开发版 | 修复半格 full gate 对 `width_cv=0.0` 的误读；恢复既有 half geometry support 行为。 |
| V4.5.2 | 开发版 | 将只读诊断计算从 Debug 渲染层移入 detection 层，减少 UI 对检测后处理的反向依赖。 |
| V4.5.1 | 开发版 | 增加 policy view 分组，拆分 detection 后处理、候选生成和候选选择职责。 |
| V4.5 | 开发版 | 将 separator-geometry outer 整理为通用能力，但默认只在验证过的 format / mode 中启用。 |
| V4.4.x | 开发版 | 收敛 full / partial outer proposal、output folder 命名、Debug Analysis 可读性、partial safe-extra-frames 和缓存效率。默认输出目录定为 `x5_crop_output/`。 |
| V4.3.x | 开发版 | 建立 full-mode outer proposal layer，并为 partial mode 增加 conservative safe-extra-frames gate。 |
| V4.2.8 | 当前稳定发布版 | 启动器交互改进：仅在 partial mode 开启后询问 count；回车或 `auto` 表示自动判断。检测逻辑不变。 |
| V4.2.x | 开发版 | 建立 120 family geometry model、separator-first outer proposal、120-66 / 120-67 保守修复和半格 full geometry support。 |
| V4.1.x | 开发版 | 120-66 / 120-67 参数校准、outer retry 收敛和 120 共享 policy 整理。 |
| V4.0.1 | 历史稳定发布版 | 135 宽片距兼容调整；默认窄分隔行为保持稳定。 |
| V4.0 | 历史稳定发布版 | 模块化重写：根入口变薄，检测、I/O、几何、证据、Debug、report、deskew 和 CLI 拆入 `x5crop/`。 |
| V3.9 | 开发版 | 结构清理版，将更多配置收进 format-aware policy / tuning 层。 |
| V3.7 | 开发版 | 合并 frame-size fit 管线，统一 edge-evidence fit 与 geometry fallback。 |
| V3.6.x | 开发版 / 部分稳定版 | 诊断层、hard-gap trust、nearby separator、overlap risk 和 edge-pair format-aware 化。 |
| V3.5 / V3.4.x | 暂停或回滚实验 | hard gap 语义校验、局部 grid、强 hard separator 保护等实验方向。 |
| V3.3.1 | 稳定发布版 / V3.6 输出基线 | 稳定打包版本，基于 V3/V3.2 风格检测链路，并加入 output-only bleed。 |
| V3.0 - V3.3 | 历史基线 | 建立 X5 Crop 主流程、输出 bleed 和 V3 风格检测链路。 |

### V4.7 验证摘要

已验证：

- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.7`。
- V4.7 package py_compile 通过。
- `git diff --check` 通过。
- 旧兼容残留扫描未命中 `common`、`FormatTuning`、`format_tuning`、
  `separator_gate_mode`、`score_gate_135`、`separator_135`、`separator_half`、
  `import *`、`edge_pair_params_for_format`、`frame_fit_policy`。
- 14 个 format / strip mode policy smoke 通过。
- 七组本地 V4.5.4 golden core comparison 在以下字段上为 0 diff：

```text
status
confidence
review_reasons
outer_box
frame_boxes
gaps
```

对应 golden sets：

```text
Test/135/4.5.4/split_report.jsonl
Test/new_135/4.5.4/split_report.jsonl
Test/120/66/4.5.4/split_report.jsonl
Test/120/66/4.5.4_partial/split_report.jsonl
Test/120/67/4.5.4/split_report.jsonl
Test/半格/full/4.5.4/split_report.jsonl
Test/半格/partial/4.5.4_partial/split_report.jsonl
```

预期 metadata-only diff：

- V4.5.4 golden reports 没有 V4.7 的 `detail.policy` 和 `report_schema`。
- 因此比较这些字段时会出现 metadata-only diff。
- 这些 diff 不代表裁切框、状态、置信度或 gap 行为变化。

尚未作为 V4.7 release 验证完成：

- default-deskew export timing。
- `xpan`、`120-645` 和 `135-dual` full sample golden comparison。
- Release package generation。

### 发布策略

- GitHub Releases 是普通用户下载入口。
- `main` 是开发分支，可以领先稳定发布版。
- 发布包只包含用户运行需要的单文件脚本、启动器、TXT 用户文档和安装/卸载器。
- 普通用户发布包不包含 `x5crop/`、`archive/`、`CHANGELOG.md`、`AGENTS.md`、
  `LICENSE`、`.github/`、diagnostics launcher、Test 文件或生成输出。

## English Changelog

### Documentation Cleanup Note

As of 2026-07-01, detailed work-log material has been condensed into version
summaries. Raw step-by-step history remains available through Git history. This
file keeps only information needed for continued development, validation, and
rollback.

### Current Focus

- V4.7 is a clean-room source rewrite, not a detector-threshold loosening.
- V4.7 treats V4.5.4 golden output as the behavior baseline.
- Default 135 behavior must remain stable.
- 120-66 dark-band / square-frame / separator-derived outer risk modeling must
  remain format-isolated.
- Weak grid, equal, or content-only evidence must not gain auto-PASS authority
  through refactoring.
- TIFF metadata, bit depth, ICC, resolution, and compression behavior remain
  unchanged.

### Version Summary

| Version | Status | Summary |
|---|---|---|
| V4.7 | Current active development | Clean-room source rewrite. Removes old compatibility layers, keeps a thin `X5_Crop.py` entry and layered `x5crop/` implementation, moves format/mode behavior into `x5crop/policies/`, keeps `workflow.py` as orchestration, narrows `detection/pipeline.py`, and splits candidate, dual-lane, partial-holder, fallback, outer-retry, calibration, and geometry helpers into focused modules. The goal is V4.5.4 behavior with clearer source boundaries. |
| V4.6 | Development | Introduces the `DetectionPolicy` architecture for detector, count, outer, separator, content, scoring, selection, postprocess, diagnostics, and output behavior by format / strip mode. Adds workflow separation and golden regression helper. |
| V4.5.4 | Development | Strengthens 120-66 full / partial wide-dark-band and strict-holder handling while keeping that risk model isolated to 120-66. |
| V4.5.3 | Development | Fixes half-frame full gate handling for `width_cv=0.0`, restoring the intended half geometry support behavior. |
| V4.5.2 | Development | Moves read-only diagnostics from Debug rendering into detection to reduce reverse dependencies. |
| V4.5.1 | Development | Adds policy-view grouping and separates detection postprocess, candidate generation, and candidate selection responsibilities. |
| V4.5 | Development | Organizes separator-geometry outer as a generic capability, enabled only in verified format / mode policies. |
| V4.4.x | Development | Refines full / partial outer proposal responsibilities, output-folder naming, Debug Analysis readability, partial safe-extra-frames, and cache efficiency. Default output folder becomes `x5_crop_output/`. |
| V4.3.x | Development | Builds full-mode outer proposal layering and conservative partial safe-extra-frames support. |
| V4.2.8 | Current stable release | Improves launcher interaction: count is requested only when partial mode is enabled; Return or `auto` keeps automatic count estimation. Detection logic is unchanged. |
| V4.2.x | Development | Builds 120 family geometry model, separator-first outer proposal, conservative 120-66 / 120-67 fixes, and half-frame full geometry support. |
| V4.1.x | Development | Calibrates 120-66 / 120-67 parameters, converges outer retry, and introduces shared 120 policy structure. |
| V4.0.1 | Historical stable release | Adds 135 wide-spacing compatibility while preserving default narrow-separator behavior. |
| V4.0 | Historical stable release | Modular rewrite: thin root entry, with detection, I/O, geometry, evidence, Debug, report, deskew, and CLI moved into `x5crop/`. |
| V3.9 | Development | Structural cleanup moving more configuration into format-aware policy / tuning layers. |
| V3.7 | Development | Unifies frame-size fitting through edge-evidence fit and geometry fallback. |
| V3.6.x | Development / partial stable | Builds diagnostics, hard-gap trust, nearby separator checks, overlap risk, and format-aware edge-pair work. |
| V3.5 / V3.4.x | Paused or reverted experiments | Experiments around hard-gap semantic validation, local grid, and strong hard-separator protection. |
| V3.3.1 | Stable release / V3.6 output baseline | Stable package based on the V3/V3.2 detection chain with output-only bleed. |
| V3.0 - V3.3 | Historical baseline | Establishes the main workflow, output bleed, and V3-style detection chain. |

### V4.7 Validation Summary

Verified:

- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.7`.
- V4.7 package py_compile passes.
- `git diff --check` passes.
- Legacy residue scans have no hits for `common`, `FormatTuning`,
  `format_tuning`, `separator_gate_mode`, `score_gate_135`, `separator_135`,
  `separator_half`, `import *`, `edge_pair_params_for_format`, or
  `frame_fit_policy`.
- 14 format / strip-mode policy smoke tests pass.
- Seven local V4.5.4 golden comparisons have 0 core diff for:

```text
status
confidence
review_reasons
outer_box
frame_boxes
gaps
```

Expected metadata-only diff:

- V4.5.4 golden reports do not contain V4.7 `detail.policy` or `report_schema`.
- Diffs in those fields do not indicate crop, status, confidence, or gap
  behavior changes.

Not yet completed as V4.7 release validation:

- Default-deskew export timing.
- `xpan`, `120-645`, and `135-dual` full sample golden comparison.
- Release package generation.

### Release Policy

- GitHub Releases are the user-facing download channel.
- `main` is the development branch and may be ahead of the stable release.
- User release packages contain only the standalone script, launchers, TXT user
  docs, and install/uninstall launchers.
- Do not include `x5crop/`, `archive/`, `CHANGELOG.md`, `AGENTS.md`, `LICENSE`,
  `.github/`, diagnostics launchers, Test files, or generated outputs in the
  normal user package.
