# X5 Crop 架构说明 / Architecture Guide

本文件是开发者架构地图，范围限定为源码分层、policy 行为边界、
format / mode 隔离规则，以及行为保持型重构的验证要求。

This document is the developer architecture map. It describes source layers,
policy ownership, format / mode isolation, and behavior-preserving verification.

使用说明请参阅 `README.md`。版本历史请参阅 `CHANGELOG.md`。
Codex 协作规则请参阅 `AGENTS.md`。

For usage, read `README.md`. For version history, read `CHANGELOG.md`. For Codex
collaboration rules, read `AGENTS.md`.

## 中文说明

### 架构目标

V4.9 是一次 evidence-governed decision / policy reset。目标不是为了让更多困难样片
自动 PASS，而是在保留 TIFF I/O 和导出质量行为的前提下，让自动裁切只发生在
outer、separator、geometry、content 和 risk 证据能够组合解释时。

- 入口保持精简。
- CLI、交互式 launcher、input probe、app runner 和 workflow 职责分离。
- workflow 只承担单图处理编排职责。
- `x5crop.formats` 明确 format physical spec。
- detection 只承担 evidence generation、candidate build 和候选排序职责。
- geometry / image / io 提供低层能力。
- `x5crop.policies.decision_contract` 拥有 V4.9 ModePolicy、EvidencePolicy、
  RiskPolicy、CandidatePolicy、DecisionPolicy、OutputPolicy 和
  DecisionDiagnosticsPolicy。
- `x5crop.detection.decision` 统一执行 PASS / REVIEW 决策。
- analysis reuse、export、report / debug 消费稳定结果并解释 V4.9 决策；
  `tools/regression/` 是开发期 reference compare / safety classification 工具，
  不属于 runtime package。

### 运行层级

1. `X5_Crop.py`
   - 开发入口。
   - V4 Release 会由构建脚本生成单文件发布版。

2. `x5crop.cli`
   - 只解析命令行参数并构造 `CliOptions`。
   - 捕获入口层错误并返回 CLI exit code。
   - 不读取 TIFF，不推断 layout，不调度 worker。

3. `x5crop.interactive`
   - 拥有 Python 交互式启动器菜单。
   - Mac / Windows launcher 只负责找 Python 并调用 `--interactive` 或
     `--interactive-diagnostics`。
   - format/count 选择共享 `x5crop.formats.FORMATS`。

4. `x5crop.input_probe`
   - 扫描输入 TIFF。
   - 验证 page、读取第一张 TIFF shape、推断 layout。
   - 将 `CliOptions` 转成经过文件探测的 `RuntimeConfig`。

5. `x5crop.app`
   - 打印启动摘要和终端进度。
   - 调度单文件 / 批量 worker。
   - 连接入口配置和 workflow。
   - 不实现检测逻辑。

6. `x5crop.workflow`
   - 编排 read -> deskew -> detect -> postprocess -> export -> report/debug。
   - 将单图报告复用、输出目录、Debug Analysis、导出和结果组装委托给专门模块。
   - 不直接实现 scoring、candidate selection 或 TIFF 写入细节。

7. `x5crop.policies`
   - 通过 `get_detection_policy(format_id, strip_mode)` 解析 runtime policy。
   - `registry.py` 只做 resolve/cache。
   - `format_modules.py` 只负责 format id 到 `format_*` module 的命名和 import。
   - `format_135.py`、`format_120_66.py` 等 format profile module 同时拥有
     format / mode runtime preset 和该 format 的参数覆盖。
   - `ids.py` 统一拥有 policy id stem 和 report schema version。
   - `base.py` 定义 runtime `DetectionPolicy` contract；`reporting.py` 只负责
     runtime policy detail serializer，不拥有 detection result schema。
   - `parameter_types.py` 保存 source parameter group dataclass；`parameters.py`
     保存 `FormatParameters` aggregate、120 共享默认 helper 和 format 参数解析。
   - `factory_presets.py` 定义 format / mode preset contract；`factory.py` 只把
     preset + source parameters 编译成 runtime `DetectionPolicy`。
   - `decision_contract.py` 是 V4.9 public decision policy contract；
     `decision_overrides.py` 保存 format / mode decision evidence 覆盖。
   - `__init__.py` 只标记 package，不作为 compatibility barrel 或 public
     re-export surface。

8. `x5crop.formats`
   - 是 format identity、physical spec、count/aspect facts 和 CLI choice 的唯一
     source of truth。
   - `FormatSpec` 可被 runtime detection、interactive / CLI 和 V4.9 decision
     contract 共享。
   - 不导入 `x5crop.policies`，不承载 threshold、gate 或候选策略。

9. `x5crop.detection`
   - 负责 outer proposal、separator/content evidence、candidate build/run、
     scoring、gates、selection、fallback 和 postprocess。
   - `pipeline.py` 应保持主流程 orchestration。
   - `decision.py` 在 postprocess 中统一执行 V4.9 conservative PASS/REVIEW。
   - 专门模块承接具体职责，例如 `candidate_build.py`、`candidate_run.py`、
     `dual_lane.py`、`partial_holder.py`、`outer_retry.py`、`calibration.py`、
     `gates.py`、`selection.py` 和 `postprocess.py`。

10. `x5crop.geometry` / `x5crop.image` / `x5crop.io`
   - 提供 box、layout、gap、separator profile、frame fit、output adjustment、
     deskew、证据图和 TIFF I/O helper。
   - 需要 format 上下文的 helper 应显式接收 format 或 policy。
   - 这些层不应依赖 detection pipeline。

11. `x5crop.analysis_reuse` / `x5crop.export` / `x5crop.result_builder` /
    `x5crop.report_schema` / `x5crop.reports` / `x5crop.debug`
   - `analysis_reuse` 负责 Debug Analysis report cache 匹配和 cached detection 恢复。
   - `export` 负责输出路径、review copy 和 metadata-safe TIFF crop 写入。
   - `result_builder` 统一将 fresh / cached detection 转成 `ProcessResult`。
   - `report_schema` 将 `Detection` / `ProcessResult` 序列化为稳定 report schema。
   - `reports` 只写 JSONL / CSV report；`debug` 只写 Debug Analysis / preview。
   - 不参与候选生成和 PASS/REVIEW 决策。

12. `tools/regression`
   - 开发期 report diff、reference baseline compare 和 V4.9 safety
     classification 工具。
   - 不被 `X5_Crop.py` 或 runtime package 导入。

### Policy 归属

V4.9 public policy contract 由 `DetectionDecisionContract` 表达：

- `FormatSpec`: physical facts，不承载检测策略。
- `ModePolicy`: full / partial count、outer、stop condition 和 edge trust。
- `EvidencePolicy`: outer / separator / geometry / content 的最低组合证据。
- `RiskPolicy`: overlap、outer-content mismatch、candidate competition、partial edge
  uncertainty 等 REVIEW 风险。
- `CandidatePolicy`: content-only、fallback、weak-grid、equal-gap 候选默认不直接 PASS。
- `DecisionPolicy`: V4.9 PASS / REVIEW reason ids 和 confidence cap。
- `OutputPolicy`: TIFF metadata/export 行为和输出 bleed。
- `DecisionDiagnosticsPolicy`: decision/report 中记录的 diagnostics panel 和
  overlay 说明。

旧 `DetectionPolicy` 仍作为 evidence generation 的内部 wiring surface。它应拥有或连接这些能力：

- `DetectorPolicy`: detector kind、135-dual lane metadata、unsupported partial reason。
- `CountPolicy`: full / partial count planning 和 partial offsets。
- `OuterPolicy`: base outer、separator-derived outer、dark-band outer、outer retry。
- `SeparatorPolicy`: gate、gap search、edge-pair、wide retry、profile、enhanced separator、hard-gap trust、nearby correction、geometry support。
- `ContentPolicy`: content evidence、profile、mask、content candidate、content-support scoring。
- `ScoringPolicy`: base detection score、candidate calibration、content/geometry/separator support score、no-auto caps。
- `CandidateRunPolicy`: content candidate skip、separator-geometry competition、equal-first wide retry、dark-band retry、partial stop。
- `PartialHolderPolicy`: partial safe-extra-frames 和 strict holder safety。
- `SelectionPolicy`: candidate competition 和 content mismatch review fallback。
- `PostprocessPolicy`: final caps、postprocess reason ids、approved geometry adjustment。
- `RuntimeDiagnosticsPolicy`: Debug Analysis panels、gap overlay、nearby separator diagnostics、overlap-risk diagnostics。
- `ReportPolicy`: report schema version 和 section order。
- `OutputPolicy`: detection bleed、output bleed、edge bleed protection。

`RuntimeDiagnosticsPolicy`、`DecisionDiagnosticsPolicy`、`ReportPolicy` 和
`DecisionPolicy` detail 不应合并成一个大桶：Debug 面向人工快速读图，
Report 面向机器回归 / 审计，Decision detail 解释 PASS / REVIEW。
`x5crop.policies.reporting` 只序列化 runtime policy detail；`x5crop.report_schema`
只负责 detection/result serializer，不拥有 policy；`x5crop.detection_detail`
集中记录 `Detection.detail` 中被 report / debug / result builder 消费的稳定
detail keys。

所有影响 V4.9 decision 的参数必须写入 `report_schema.decision_policy_detail`。

### 必须隔离的行为

- 135 full 的稳定完整片条假设不能被其它 format 偷用。
- 135-dual full 走 dual-lane detector；135-dual partial 保守复核。
- half geometry support 是通用 capability，但默认只给 `half/full` 开启。
- 120-66 dark-band、square-frame、wide-like separator 和 strict holder checks
  只给 120-66 full / partial。
- 120-67 可以有自己的 short-axis / wide separator retry，但不能继承 120-66 dark-band。
- weak grid、equal 或 content-only evidence 不能因为重构获得自动 PASS 权限。

### 数据和报告契约

- `OuterCandidate.strategy` 是 candidate kind 契约。runtime 不应靠 name prefix 推断行为。
- `CliOptions` 是未探测输入文件前的用户选项；`RuntimeConfig` 是绑定具体
  TIFF profile / layout 后的运行配置。
- `Detection` 和 `ProcessResult` 是 report/debug/export 的稳定输入。
- report row 顶层包含 `version` 和 `policy_id`。
- `report_schema` 使用 `v4_9_policy_schema_1`，并包含 `evidence_summary`、
  `risk_summary`、`decision_policy_detail` 和 `selected_candidate`。
- V4.5.4 reference reports 是 historical baseline，不再是必须 0 diff 的 oracle。
  conservative PASS -> REVIEW 需要按原因解释，新增错误 PASS 不可接受。

### 验证边界

结构或 policy 改动后至少运行：

```bash
python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py x5crop/policies/*.py x5crop/geometry/*.py x5crop/io/*.py x5crop/image/*.py x5crop/export/*.py x5crop/diagnostics/*.py tools/regression/*.py
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

检测行为改动需要比较核心字段：

```text
status
confidence
review_reasons
outer_box
frame_boxes
gaps
```

常用 reference sets：

```text
Test/135/4.5.4/split_report.jsonl
Test/new_135/4.5.4/split_report.jsonl
Test/120/66/4.5.4/split_report.jsonl
Test/120/66/4.5.4_partial/split_report.jsonl
Test/120/67/4.5.4/split_report.jsonl
Test/半格/full/4.5.4/split_report.jsonl
Test/半格/partial/4.5.4_partial/split_report.jsonl
```

V4.9 验收目标不是 0 core diff。使用
`python3 -m tools.regression.reference_classify --candidate-root <root>` 分类：

```text
same
safer_review
improved_crop
metadata/schema diff
risky_regression
unacceptable_wrong_pass
```

目标是 0 `unacceptable_wrong_pass`；所有 PASS -> REVIEW 和 geometry diff 都必须能解释。

## English Guide

### Architecture Goal

V4.9 is an evidence-governed decision / policy reset. It is not intended to make more
difficult samples auto-PASS. Automatic crop export is allowed only when outer,
separator, geometry, content, and risk evidence can explain the decision
together, while TIFF I/O and export-quality behavior remain preserved.

- Thin entry.
- CLI, interactive launcher, input probe, app runner, and workflow are separate.
- Workflow only orchestrates one-image processing.
- `x5crop.formats` owns physical format specs.
- Detection owns evidence generation, candidate build, and candidate ranking.
- Geometry / image / io provide lower-level capabilities.
- `x5crop.policies.decision_contract` owns the V4.9 ModePolicy, EvidencePolicy,
  RiskPolicy, CandidatePolicy, DecisionPolicy, OutputPolicy, and
  DecisionDiagnosticsPolicy.
- `x5crop.detection.decision` applies the unified PASS / REVIEW decision.
- Analysis reuse, export, report / debug consume stable results and explain V4.9
  decisions; `tools/regression/` contains developer-only reference compare /
  safety classification tools outside the runtime package.

### Runtime Layers

1. `X5_Crop.py`
   - Development entry.
   - V4 Release builds produce a standalone single-file script.

2. `x5crop.cli`
   - Only parses CLI arguments into `CliOptions`.
   - Catches entry-layer errors and returns CLI exit codes.
   - Does not read TIFFs, infer layout, or schedule workers.

3. `x5crop.interactive`
   - Owns the Python interactive launcher menu.
   - Mac / Windows launchers only find Python and call `--interactive` or
     `--interactive-diagnostics`.
   - Format/count choices share `x5crop.formats.FORMATS`.

4. `x5crop.input_probe`
   - Scans input TIFF files.
   - Validates page, reads the first TIFF shape, and resolves layout.
   - Converts `CliOptions` into probed `RuntimeConfig`.

5. `x5crop.app`
   - Prints startup summary and terminal progress.
   - Schedules single-file / batch workers.
   - Connects entry configuration to workflow.
   - Does not implement detector logic.

6. `x5crop.workflow`
   - Orchestrates read -> deskew -> detect -> postprocess -> export -> report/debug.
   - Delegates per-image report reuse, output folders, Debug Analysis, export,
     and result assembly to focused modules.

7. `x5crop.policies`
   - Resolves runtime policy through `get_detection_policy(format_id, strip_mode)`.
   - `registry.py` only resolves and caches.
   - `format_modules.py` only maps format ids to `format_*` module names and imports.
   - Format profile modules such as `format_135.py` and `format_120_66.py`
     own both format / mode runtime presets and that format's parameter
     overrides.
   - `ids.py` owns shared policy id stems and the report schema version.
   - `base.py` defines the runtime `DetectionPolicy` contract; `reporting.py`
     only serializes runtime policy detail and does not own the detection result schema.
   - `parameter_types.py` stores source parameter group dataclasses; `parameters.py`
     stores the `FormatParameters` aggregate, shared 120 defaults, and format
     parameter resolution.
   - `factory_presets.py` defines the format / mode preset contract; `factory.py`
     only compiles presets plus source parameters into runtime `DetectionPolicy`.
   - `decision_contract.py` is the V4.9 public decision policy contract;
     `decision_overrides.py` stores format / mode decision evidence overrides.
   - `__init__.py` is only a package marker, not a compatibility barrel or
     public re-export surface.

8. `x5crop.formats`
   - Is the single source of truth for format identity, physical specs,
     count/aspect facts, and CLI choices.
   - `FormatSpec` is shared by runtime detection, interactive / CLI, and the
     V4.9 decision contract.
   - Does not import `x5crop.policies` and does not own thresholds, gates, or
     candidate strategy.

9. `x5crop.detection`
   - Owns outer proposals, separator/content evidence, candidate build/run,
     scoring, gates, selection, fallback, and postprocess.
   - `pipeline.py` should stay orchestration-focused.
   - `decision.py` applies conservative V4.9 PASS/REVIEW rules in postprocess.

10. `x5crop.geometry` / `x5crop.image` / `x5crop.io`
   - Provide boxes, layout, gaps, separator profiles, frame fit, output
     adjustment, deskew, evidence images, and TIFF I/O.
   - Helpers that need format context should receive format or policy explicitly.
   - These layers should not depend on the detection pipeline.

11. `x5crop.analysis_reuse` / `x5crop.export` / `x5crop.result_builder` /
    `x5crop.report_schema` / `x5crop.reports` / `x5crop.debug`
   - `analysis_reuse` matches Debug Analysis report caches and restores cached
     detections.
   - `export` owns output paths, review copies, and metadata-safe TIFF crop writes.
   - `result_builder` converts fresh / cached detections into `ProcessResult`.
   - `report_schema` serializes `Detection` / `ProcessResult` into the stable
     report schema.
   - `reports` only writes JSONL / CSV reports; `debug` only writes Debug
     Analysis / previews.
   - Do not generate candidates or decide PASS/REVIEW.

12. `tools/regression`
   - Developer-only report diff, reference baseline compare, and V4.9 safety
     classification tools.
   - Not imported by `X5_Crop.py` or the runtime package.

### Policy Ownership

The V4.9 public policy contract is `DetectionDecisionContract`:

- `FormatSpec`: physical facts, not detection strategy.
- `ModePolicy`: full / partial count, outer, stop condition, and edge trust.
- `EvidencePolicy`: minimum combined outer / separator / geometry / content evidence.
- `RiskPolicy`: overlap, outer-content mismatch, candidate competition, and
  partial-edge review risks.
- `CandidatePolicy`: content-only, fallback, weak-grid, and equal-gap candidates
  are review-only by default.
- `DecisionPolicy`: V4.9 PASS / REVIEW reason ids and confidence cap.
- `OutputPolicy`: TIFF metadata/export behavior and output bleed.
- `DecisionDiagnosticsPolicy`: diagnostics panel and overlay detail recorded in
  the decision/report contract.

The older `DetectionPolicy` remains an internal evidence-generation wiring
surface. Decision-affecting V4.9 parameters must be written to
`report_schema.decision_policy_detail`.

`RuntimeDiagnosticsPolicy`, `DecisionDiagnosticsPolicy`, `ReportPolicy`, and
`DecisionPolicy` detail stay separate: Debug is for fast human image review,
Report is for machine regression / audit, and Decision detail explains PASS /
REVIEW. `x5crop.policies.reporting` only serializes runtime policy detail;
`x5crop.report_schema` serializes detection/result rows and does not own policy;
`x5crop.detection_detail` centralizes the stable `Detection.detail` keys consumed
by report / debug / result builders.

### Behavior That Must Stay Isolated

- 135 full-strip assumptions must not leak into other formats.
- 135-dual full uses the dual-lane detector; 135-dual partial stays conservative.
- Half-frame geometry support is generic, but currently enabled only for
  `half/full`.
- 120-66 dark-band, square-frame, wide-like separator, and strict-holder checks
  stay limited to 120-66 full / partial.
- 120-67 may have its own short-axis / wide-separator retry, but must not inherit
  120-66 dark-band behavior.
- Weak grid, equal, or content-only evidence must not gain auto-PASS authority
  through refactoring.

### Data And Report Contracts

- `OuterCandidate.strategy` is the candidate-kind contract. Runtime should not
  infer behavior from name prefixes.
- `CliOptions` contains user options before input probing. `RuntimeConfig` is the
  file-probed runtime configuration with concrete TIFF profile / layout context.
- `Detection` and `ProcessResult` are stable inputs for report/debug/export.
- Report rows include top-level `version` and `policy_id`.
- `report_schema` uses `v4_9_policy_schema_1` and includes `evidence_summary`,
  `risk_summary`, `decision_policy_detail`, and `selected_candidate`.
- V4.5.4 reference reports are a historical baseline, not a required 0-diff oracle.
  Conservative PASS -> REVIEW changes must be explained; new wrong PASS results
  are unacceptable.

### Verification

After structure or policy changes, run:

```bash
python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py x5crop/policies/*.py x5crop/geometry/*.py x5crop/io/*.py x5crop/image/*.py x5crop/export/*.py x5crop/diagnostics/*.py tools/regression/*.py
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

For detector behavior changes, protect:

```text
status
confidence
review_reasons
outer_box
frame_boxes
gaps
```

V4.9 acceptance is not 0 core diff. Use
`python3 -m tools.regression.reference_classify --candidate-root <root>` to classify:

```text
same
safer_review
improved_crop
metadata/schema diff
risky_regression
unacceptable_wrong_pass
```

The target is 0 `unacceptable_wrong_pass`; every PASS -> REVIEW and geometry
diff must be explainable.
