# X5 Crop 更新日志 / Changelog

本文件记录版本变化、行为边界、验证结果和回滚线索。它不承担用户操作说明、
源码架构说明或 Codex 协作 handoff 职责。

This file records version changes, behavior boundaries, validation results, and
rollback context. It is not a user manual, architecture guide, or Codex handoff.

当前 active 脚本版本：V4.9

当前稳定发布版本：v4.2.8

Current active script version: V4.9

Current stable release: v4.2.8

## 中文更新日志

### 文档整理说明

2026-07-01 起，历史工作日志已压缩为版本摘要。详细逐步实验记录仍可通过 Git
历史追溯；当前文档只保留继续开发、验证和回滚需要的信息。

### 当前重点

- V4.9 是 evidence-governed decision / policy reset，不是检测阈值放宽版本。
- V4.5.4 / V4.7 reference reports 是 historical baseline，不再是必须 0 diff 的 oracle。
- 自动 PASS 必须由 outer、separator、geometry、content 和 risk 组合证据共同解释。
- weak grid、equal、content-only、fallback 或 partial edge 不可信的候选默认进入 REVIEW。
- TIFF metadata、位深、ICC、resolution 和 compression 行为保持不变。

### 版本摘要

| 版本 | 状态 | 摘要 |
|---|---|---|
| V4.9 | 当前 active 开发版 | Evidence-governed decision / policy reset。新增 explicit format physical spec、clean entry layer（`CliOptions` / `RuntimeConfig`、`input_probe.py`、Python interactive launcher）、`x5crop/policies/decision_contract.py` V4.9 policy contract、`x5crop/detection/final/decision.py` conservative PASS/REVIEW gate、`v4_9_policy_schema_1` report schema、policy-controlled three-panel Debug Analysis，以及 `tools/regression/` reference classifier。目标是 0 新错误 PASS，并允许可解释的 conservative diff。 |
| V4.7 | 旧 active 开发版 | Source-layout rewrite。移除旧桥接层，保留 `X5_Crop.py` 薄入口和 `x5crop/` 分层实现；format / mode 行为由 `x5crop/policies/` 管理；`workflow.py` 负责编排；`detection/pipeline.py` 收敛为 orchestration；candidate、dual-lane、partial-holder、fallback、outer retry、calibration 等职责拆入专门模块；geometry 拆分为 focused helpers。目标是保持 V4.5.4 行为，同时让源码边界清晰。 |
| V4.6 | 开发版 | 建立 `DetectionPolicy` 架构，将 detector、count、outer、separator、content、scoring、selection、postprocess、diagnostics 和 output 行为按 format / strip mode 注册。新增 workflow 层和 historical reference compare helper。 |
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
| V4.0.1 | 历史稳定发布版 | 135 宽片距支持调整；默认窄分隔行为保持稳定。 |
| V4.0 | 历史稳定发布版 | 模块化重写：根入口变薄，检测、I/O、几何、证据、Debug、report、deskew 和 CLI 拆入 `x5crop/`。 |
| V3.9 | 开发版 | 结构清理版，将更多配置收进 format-aware policy / tuning 层。 |
| V3.7 | 开发版 | 合并 frame-size fit 管线，统一 edge-evidence fit 与 geometry fallback。 |
| V3.6.x | 开发版 / 部分稳定版 | 诊断层、hard-gap trust、nearby separator、overlap risk 和 edge-pair format-aware 化。 |
| V3.5 / V3.4.x | 暂停或回滚实验 | hard gap 语义校验、局部 grid、强 hard separator 保护等实验方向。 |
| V3.3.1 | 稳定发布版 / V3.6 输出基线 | 稳定打包版本，基于 V3/V3.2 风格检测链路，并加入 output-only bleed。 |
| V3.0 - V3.3 | 历史基线 | 建立 X5 Crop 主流程、输出 bleed 和 V3 风格检测链路。 |

### V4.9 验证摘要

已验证：

- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.9`。
- V4.9 package py_compile 通过。
- `git diff --check` 通过。
- Mac 主启动器和 diagnostics 启动器 `bash -n` 通过。
- 入口层拆分通过 smoke：`x5crop.cli` 只解析 CLI，`x5crop.app` 负责运行调度，
  `x5crop.input_probe` 负责 TIFF 输入探测，`x5crop.interactive` 负责启动器菜单。
- Workflow / output 边界清理通过 smoke：`workflow.py` 保留单图编排，
  `analysis_reuse` 负责 report cache 复用，`export` 负责输出路径 / review copy /
  TIFF crop 写出，`result_builder` 统一 fresh / cached `ProcessResult` 组装，
  `report_outputs` 只写 JSONL / CSV。
- Detection 第 10 层清理完成：`x5crop.detection` 已拆为 `outer/`、`evidence/`、
  `candidate/`、`modes/` 和 `final/` 子包；旧平铺 `outer.py`、`outer_retry.py`、
  `candidate_run.py`、`content.py`、`diagnostics.py`、`finalizer.py` 等模块已移除；
  package `__init__` 只保留 marker，不再 re-export 旧入口。
- Detection 层 smoke 通过：递归 `compileall`、runtime import smoke，以及
  135/full、120-66/partial、half/full 三张本地样片 dry-run report 均完成。
- 命名边界清理完成：candidate-level gate / decision 现在由
  `candidate/gates.py` 和 `candidate/decision.py` 表达；最终 PASS/REVIEW 与输出前
  收口由 `final/decision.py` 和 `final/finalize.py` 表达；runtime policy 字段统一为
  `finalization`。
- 稳定数据契约层清理通过 smoke：report schema serializer 从 `x5crop.detection`
  移至 `x5crop.report_schema`，`x5crop.detection_detail` 集中记录
  `Detection.detail` 的稳定消费键。
- Runtime report 输出文件名统一为 `x5_crop_report.jsonl` 和
  `x5_crop_summary.csv`；historical reference baseline 仍可读取旧
  `split_report.jsonl`。
- Format 层清理完成：删除旧 `x5crop.format_specs`，`x5crop.formats` 成为
  format identity、physical spec、count/aspect facts 和 CLI choices 的唯一入口；
  基础 format 层不再反向依赖 policy 参数层。
- Policy profile 层清理完成：删除旧 runtime preset / parameter preset 双拆，
  7 个 `format_*` 文件现在同时拥有 format / mode runtime preset 和对应参数覆盖；
  source parameter group dataclass 按 `parameter_*.py` owning module 分组，
  `parameter_aggregate.py` 只保留 flat `FormatParameters` aggregate，
  `parameter_registry.py` 只保留 120 共享默认 helper 和 format 参数解析。
- Policy 入口层清理完成：`x5crop.policies.__init__` 不再 re-export runtime
  policy 类型；runtime policy 解析只通过 `x5crop.policies.registry.get_detection_policy`。
- Policy 合同子层清理完成：`x5crop.policies.ids` 统一拥有 policy id stem 和
  report schema version；`factory_presets.py` 拥有 format / mode preset contract；
  `runtime_policy.py` 承接 runtime `DetectionPolicy` contract；`factory.py`
  只编译 runtime `DetectionPolicy`；`decision_overrides.py` 拥有 format / mode
  decision evidence 覆盖；`x5crop.policies.reporting` 承接 runtime
  `DetectionPolicy` detail serializer；runtime debug policy 命名为
  `RuntimeDiagnosticsPolicy`，decision/report diagnostics 命名为
  `DecisionDiagnosticsPolicy`。
- Geometry / Image / IO 基础能力层清理完成：删除旧 `geometry.core` 总线和
  `geometry.output_adjustment` 混层文件；separator cache、edge-pair refine、
  enhanced separator 和 final geometry adjustment 已拆入明确 owning modules；
  runtime 内部不再通过 `geometry.__init__` 宽入口导入底层能力；analysis cache
  初始化移出 geometry，TIFF I/O helper 也不再依赖完整 runtime `Config`。
- Geometry / Image / IO 基础能力层二次打磨完成：旧 `geometry.gaps` 大工具箱拆为
  `gap_search`、`gap_trust`、`nearby_separator` 和 `robust_grid`；`image.deskew`
  只保留 deskew angle 选择，像素旋转和 crop validation 分别移入
  `image.transforms` / `image.crop_pixels`；`read_tiff` 不再把 TIFF page object
  传入 workflow/export。
- Outer primitive 边界进一步收紧：`geometry.outer_boxes` 只返回 `Box` /
  `Box | None`，`OuterCandidate` 包装、候选命名、strategy 和去重全部移到
  `x5crop.detection.outer.base.base_outer_candidates` /
  `x5crop.detection.outer.base.unique_outer_candidates`。
- Workflow / Report / Debug / Policy 结构继续收紧：`workflow.py` 只保留单图主流程，
  runtime deskew、cached analysis、review/export 和 Debug outputs 已下放到 owning
  modules；Debug Analysis 渲染拆为 canvas、gap overlays、panels、status 和 writer；
  `report_sections.py` 承接 candidate/gate section builder；空的 `x5crop.diagnostics`
  占位包已删除；runtime policy types、factory builders、parameter types 和 parameter
  registry 已按职责分组。
- 非 Detection 层旧兼容面进一步删除：`x5crop.config` 不再 re-export format choices
  或提供 `Config` 旧别名；`x5crop`、`x5crop.io`、`x5crop.export`、`x5crop.debug`
  的 package `__init__` 不再 re-export runtime helper；`parameters.py` 和
  `parameter_types.py` 两个 policy compatibility re-export 文件已删除。
- Dev tools 层完成清理：`tools/build_standalone.py` 删除旧静态 V4 module list，
  改为自动收集当前 `x5crop/**/*.py` 并生成 embedded import hook；
  `tools/regression` 保持开发期 report compare / safety classifier。
- 14 个 format / strip mode V4.9 decision contract policy smoke 通过。
- 单文件 Debug Analysis smoke 生成 V4.9 three-panel debug JPG。
- Cached analysis reuse smoke 覆盖 approved 自动导出和 needs_review 跳过导出两条路径。
- 七组本地 V4.5.4 reference reports 通过 reference classifier：

```text
candidate root: /private/tmp/x5_reference_validation_run1
rows compared: 103
standard_strip_full: {'same': 43, 'metadata/schema diff': 5}
wide_spacing_standard_strip_full: {'same': 4}
medium_square_full: {'same': 16}
medium_square_partial: {'same': 16}
medium_wide_full: {'same': 3, 'metadata/schema diff': 1}
dense_half_frame_full: {'same': 10}
dense_half_frame_partial: {'same': 5}
unacceptable_wrong_pass: 0
risky_regression: 0
```

对应 reference sets：

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
- 本次 6 个 `metadata/schema diff` 都发生在既有 REVIEW 行，主要来自
  `v4_9_policy_schema_1`、V4.9 reason vocabulary 和 policy detail 变化。
- 本次本地环境 process worker 不可用，验证自动 fallback 到 thread workers。

尚未作为 V4.9 release 验证完成：

- default-deskew export timing。
- `xpan`、`120-645` 和 `135-dual` full sample reference comparison。
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

- V4.9 is an evidence-governed decision / policy reset, not a detector-threshold loosening.
- V4.5.4 / V4.7 reference reports are historical baselines, not required 0-diff oracles.
- Automatic PASS must be explained by combined outer, separator, geometry,
  content, and risk evidence.
- Weak grid, equal, content-only, fallback, or untrusted partial-edge candidates
  default to REVIEW.
- TIFF metadata, bit depth, ICC, resolution, and compression behavior remain
  unchanged.

### Version Summary

| Version | Status | Summary |
|---|---|---|
| V4.9 | Current active development | Evidence-governed decision / policy reset. Adds explicit format physical specs, a clean entry layer (`CliOptions` / `RuntimeConfig`, `input_probe.py`, Python interactive launcher), the `x5crop/policies/decision_contract.py` V4.9 policy contract, the `x5crop/detection/final/decision.py` conservative PASS/REVIEW gate, `v4_9_policy_schema_1`, policy-controlled three-panel Debug Analysis, and a `tools/regression/` reference classifier. The goal is 0 new wrong PASS with explainable conservative diffs. |
| V4.7 | Previous active development | Source-layout rewrite. Removes old bridge layers, keeps a thin `X5_Crop.py` entry and layered `x5crop/` implementation, moves format/mode behavior into `x5crop/policies/`, keeps `workflow.py` as orchestration, narrows `detection/pipeline.py`, and splits candidate, dual-lane, partial-holder, fallback, outer-retry, calibration, and geometry helpers into focused modules. The goal is V4.5.4 behavior with clearer source boundaries. |
| V4.6 | Development | Introduces the `DetectionPolicy` architecture for detector, count, outer, separator, content, scoring, selection, postprocess, diagnostics, and output behavior by format / strip mode. Adds workflow separation and a historical reference compare helper. |
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
| V4.0.1 | Historical stable release | Adds 135 wide-spacing support while preserving default narrow-separator behavior. |
| V4.0 | Historical stable release | Modular rewrite: thin root entry, with detection, I/O, geometry, evidence, Debug, report, deskew, and CLI moved into `x5crop/`. |
| V3.9 | Development | Structural cleanup moving more configuration into format-aware policy / tuning layers. |
| V3.7 | Development | Unifies frame-size fitting through edge-evidence fit and geometry fallback. |
| V3.6.x | Development / partial stable | Builds diagnostics, hard-gap trust, nearby separator checks, overlap risk, and format-aware edge-pair work. |
| V3.5 / V3.4.x | Paused or reverted experiments | Experiments around hard-gap semantic validation, local grid, and strong hard-separator protection. |
| V3.3.1 | Stable release / V3.6 output baseline | Stable package based on the V3/V3.2 detection chain with output-only bleed. |
| V3.0 - V3.3 | Historical baseline | Establishes the main workflow, output bleed, and V3-style detection chain. |

### V4.9 Validation Summary

Verified:

- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.9`.
- V4.9 package py_compile passes.
- `git diff --check` passes.
- The main Mac launcher and diagnostics launcher pass `bash -n`.
- Entry-layer smoke passes: `x5crop.cli` only parses CLI, `x5crop.app` owns run
  dispatch, `x5crop.input_probe` owns TIFF input probing, and
  `x5crop.interactive` owns launcher prompts.
- Workflow / output boundary cleanup smoke passes: `workflow.py` keeps one-image
  orchestration, `analysis_reuse` owns report-cache reuse, `export` owns output
  paths / review copies / TIFF crop writes, `result_builder` builds fresh /
  cached `ProcessResult` rows, and `report_outputs` only writes JSONL / CSV.
- Detection layer 10 cleanup is complete: `x5crop.detection` is split into
  `outer/`, `evidence/`, `candidate/`, `modes/`, and `final/` subpackages. The
  old flat `outer.py`, `outer_retry.py`, `candidate_run.py`, `content.py`,
  `diagnostics.py`, `finalizer.py`, and related modules are removed; package
  `__init__` files are markers only and no longer re-export old entry points.
- Detection-layer smoke passes: recursive `compileall`, runtime import smoke,
  and local 135/full, 120-66/partial, and half/full dry-run report samples all
  complete.
- Naming boundary cleanup is complete: candidate-level gates / decisions are now
  expressed by `candidate/gates.py` and `candidate/decision.py`; final
  PASS/REVIEW and pre-output finalization are expressed by `final/decision.py`
  and `final/finalize.py`; the runtime policy field is consistently named
  `finalization`.
- Stable data-contract cleanup smoke passes: report schema serialization moved
  from `x5crop.detection` to `x5crop.report_schema`, and
  `x5crop.detection_detail` centralizes the stable `Detection.detail` keys
  consumed by reports / debug / result builders.
- Runtime report output filenames are standardized as `x5_crop_report.jsonl`
  and `x5_crop_summary.csv`; historical reference baselines can still read the
  old `split_report.jsonl` name.
- Policy profile layout is consolidated: the old split between runtime preset
  modules and parameter preset modules is removed, and the 7 `format_*` files
  now own both each format / mode runtime preset and that format's parameter
  overrides. Source parameter group dataclasses are grouped by owning
  `parameter_*.py` modules, `parameter_aggregate.py` only keeps the flat
  `FormatParameters` aggregate, and `parameter_registry.py` owns shared 120
  defaults plus format parameter resolution.
- The policy contract sublayer is cleaned up: `x5crop.policies.ids` owns shared
  policy id stems and the report schema version, `factory_presets.py` owns the
  format / mode preset contract, `runtime_policy.py` owns the runtime
  `DetectionPolicy` contract, `factory.py` only compiles runtime
  `DetectionPolicy`, `decision_overrides.py` owns format / mode decision
  evidence overrides, `x5crop.policies.reporting` owns runtime `DetectionPolicy`
  detail serialization, runtime debug policy is named `RuntimeDiagnosticsPolicy`,
  and decision/report diagnostics is named `DecisionDiagnosticsPolicy`.
- The Geometry / Image / IO foundation layer is cleaned up: the old
  `geometry.core` bus and mixed `geometry.output_adjustment` file are removed;
  separator cache, edge-pair refine, enhanced separator, and final geometry
  adjustment now live in explicit owning modules; runtime internals no longer
  import lower-level helpers through the wide `geometry.__init__` surface;
  analysis-cache initialization moved out of geometry, and TIFF I/O helpers no
  longer depend on the full runtime `Config`.
- The outer primitive boundary is tightened: `geometry.outer_boxes` returns only
  `Box` / `Box | None`, while `OuterCandidate` wrapping, candidate names,
  strategies, and deduplication now belong to
  `x5crop.detection.outer.base.base_outer_candidates` /
  `x5crop.detection.outer.base.unique_outer_candidates`.
- Workflow / Report / Debug / Policy structure is tightened: `workflow.py` keeps
  only the single-image main flow, while runtime deskew, cached analysis,
  review/export, and Debug outputs are delegated to owning modules; Debug
  Analysis rendering is split into canvas, gap overlays, panels, status, and
  writer modules; `report_sections.py` owns candidate/gate section builders; the
  empty `x5crop.diagnostics` placeholder package is removed; runtime policy
  types, factory builders, parameter types, and the parameter registry are
  grouped by responsibility.
- Non-detection compatibility surfaces are further removed: `x5crop.config` no
  longer re-exports format choices or provides the old `Config` alias; the
  `x5crop`, `x5crop.io`, `x5crop.export`, and `x5crop.debug` package
  `__init__` files no longer re-export runtime helpers; the `parameters.py` and
  `parameter_types.py` policy compatibility re-export files are removed.
- The dev-tool layer is cleaned up: `tools/build_standalone.py` removes the old
  static V4 module list and now auto-collects the current `x5crop/**/*.py` files
  into an embedded import hook; `tools/regression` remains developer-only report
  compare / safety classifier code.
- 14 format / strip-mode V4.9 decision contract policy smoke tests pass.
- One-file Debug Analysis smoke writes the V4.9 three-panel debug JPG.
- Cached analysis reuse smoke covers both approved auto-export and needs_review
  skip-export paths.
- Seven local V4.5.4 reference reports pass the reference classifier:

```text
candidate root: /private/tmp/x5_reference_validation_run1
rows compared: 103
standard_strip_full: {'same': 43, 'metadata/schema diff': 5}
wide_spacing_standard_strip_full: {'same': 4}
medium_square_full: {'same': 16}
medium_square_partial: {'same': 16}
medium_wide_full: {'same': 3, 'metadata/schema diff': 1}
dense_half_frame_full: {'same': 10}
dense_half_frame_partial: {'same': 5}
unacceptable_wrong_pass: 0
risky_regression: 0
```

Notes:

- V4.9 does not target 0 diff; the acceptance priority is 0
  `unacceptable_wrong_pass`.
- The 6 `metadata/schema diff` rows are existing REVIEW rows whose V4.9 schema,
  reason vocabulary, and policy detail changed without a crop-geometry change.
- This local environment could not use process workers and automatically fell
  back to thread workers.

Not yet completed as V4.9 release validation:

- Default-deskew export timing.
- `xpan`, `120-645`, and `135-dual` full sample reference comparison.
- Release package generation.

### Release Policy

- GitHub Releases are the user-facing download channel.
- `main` is the development branch and may be ahead of the stable release.
- User release packages contain only the standalone script, launchers, TXT user
  docs, and install/uninstall launchers.
- Do not include `x5crop/`, `archive/`, `CHANGELOG.md`, `AGENTS.md`, `LICENSE`,
  `.github/`, diagnostics launchers, Test files, or generated outputs in the
  normal user package.
