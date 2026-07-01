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
- CLI、配置契约、交互式 launcher、input probe、app runner 和 workflow 职责分离。
- workflow 只承担单图处理编排职责。
- `x5crop.formats` 明确 format physical spec。
- detection 只承担 evidence generation、candidate build 和候选排序职责。
- geometry / image / io 提供低层能力。
- `x5crop.policies.decision_contract` 拥有 V4.9 ModePolicy、EvidencePolicy、
  RiskPolicy、CandidatePolicy、DecisionPolicy、OutputPolicy 和
  DecisionDiagnosticsPolicy。
- `x5crop.detection.final_decision` 统一执行 PASS / REVIEW 决策。
- analysis reuse、export、report / debug 消费稳定结果并解释 V4.9 决策；
  `tools/` 是开发期 release build / reference compare / safety classification
  工具，不属于 runtime package。

### 彻底干净定义

一个层级只有在所有公开入口都来自真实 owning module、没有旧 alias / shim /
bridge / re-export、import 方向可证明、特殊行为 policy 化、文档与代码一致时，
才算彻底干净。

| 维度 | 标准 |
| --- | --- |
| 职责 | 每个文件只有一个明确 ownership，不靠“顺手放这里”存在。 |
| API 面 | 不保留旧兼容 alias、barrel re-export、bridge module 或 shim module。 |
| Import 方向 | 只能按层级向下依赖；基础层不能反向依赖 workflow / detection / debug / report。 |
| 命名 | 文件名、类名、字段名表达当前职责，不带旧版本、旧行为或历史妥协语义。 |
| Policy | format / mode 特殊行为必须显式写入 policy，不能散落在 runtime 代码里靠隐式判断启用。 |
| 数据契约 | `RuntimeConfig`、`Detection`、`ProcessResult`、policy detail 和 report schema 各自边界稳定。 |
| Output surfaces | debug / report / export 只消费和解释结果，不参与候选选择、gate 或 PASS/REVIEW。 |
| 文档同步 | `ARCHITECTURE.md` 中声明的结构必须和真实文件、import 面、policy 面一致。 |

允许保留有明确语义的聚合层，例如 `registry.py`、`factory.py`、
`report_schema.py`。不允许保留仅为了旧 import 路径存在的兼容 re-export 层。

### 运行层级

本节编号按 dependency / ownership boundary 排列，不是 workflow 的逐行调用顺序。
`x5crop.geometry` / `x5crop.image` / `x5crop.io` 是 detection、export 和 debug
共享的基础能力层，因此排在 `x5crop.detection` 之前；它们不是 detection 的子层。

1. `X5_Crop.py`
   - 开发入口。
   - V4 Release 会由构建脚本生成单文件发布版。

2. `x5crop.cli` / `x5crop.config`
   - 只解析命令行参数并构造 `CliOptions`。
   - `x5crop.config` 只拥有 `CliOptions` 和 `RuntimeConfig`，是入口 /
     startup 与 workflow 之间的配置契约。
   - CLI choice 常量属于 `x5crop.formats`，不从 `x5crop.config` re-export。
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
   - 编排 read -> deskew -> detect -> finalization -> export -> report/debug。
   - 将单图报告复用、runtime deskew、输出目录、Debug Analysis、导出和结果组装
     委托给专门模块。
   - 不直接实现 scoring、candidate selection 或 TIFF 写入细节。

7. `x5crop.policies`
   - 通过 `get_detection_policy(format_id, strip_mode)` 解析 runtime policy。
   - `registry.py` 只做 resolve/cache。
   - `format_modules.py` 只负责 format id 到 `format_*` module 的命名和 import。
   - `format_135.py`、`format_120_66.py` 等 format profile module 同时拥有
     format / mode runtime preset 和该 format 的参数覆盖。
   - `ids.py` 统一拥有 policy id stem 和 report schema version。
   - `runtime_policy.py` 定义 runtime `DetectionPolicy` contract；runtime
     policy value object 按 `runtime_base.py`、`runtime_outer.py`、
     `runtime_separator.py`、`runtime_content.py`、`runtime_candidate.py`、
     `runtime_final.py`、`runtime_diagnostics.py` 分组。
   - source parameter group dataclass 按 `parameter_content.py`、`parameter_outer.py`、
     `parameter_separator.py`、`parameter_scoring.py`、`parameter_finalization.py`
     和 `parameter_diagnostics.py` 分组。
   - `parameter_aggregate.py` 保存 flat `FormatParameters` aggregate 和
     property views；`parameter_registry.py` 保存 120 共享默认 helper 和 format
     参数解析。
   - `factory_presets.py` 定义 format / mode preset contract；`factory.py` 只做
     runtime `DetectionPolicy` 总装，具体 builder 按 `factory_*` 文件分组。
   - `reporting.py` 只负责 runtime policy detail serializer，不拥有 detection
     result schema。
   - `decision_contract.py` 是 V4.9 public decision policy contract；
     `decision_overrides.py` 保存 format / mode decision evidence 覆盖。
   - `x5crop.__init__`、`x5crop.io.__init__`、`x5crop.export.__init__`、
     `x5crop.debug.__init__` 和 `x5crop.policies.__init__` 只标记 package，
     不作为 compatibility barrel 或 public re-export surface。

8. `x5crop.formats`
   - 是 format identity、physical spec、count/aspect facts 和 CLI choice 的唯一
     source of truth。
   - `FormatSpec` 可被 runtime detection、interactive / CLI 和 V4.9 decision
     contract 共享。
   - 不导入 `x5crop.policies`，不承载 threshold、gate 或候选策略。

9. `x5crop.geometry` / `x5crop.image` / `x5crop.io`
   - 提供 box、layout、outer primitive、separator profile/cache、gap search、
     hard-gap trust、nearby separator correction、robust grid、edge-pair refine、
     enhanced separator、frame fit、deskew angle、pixel transforms、crop pixel
     validation、证据图和 TIFF I/O helper。
   - 是 detection、export 和 debug 共享的基础能力层。
   - 需要 format 上下文的 helper 应显式接收 format 或 policy。
   - `geometry.__init__` 只标记 package；runtime 应从具体 owning module import。
   - `geometry.outer_boxes` 只返回 `Box` / `Box | None`；`OuterCandidate`
     包装、candidate name、strategy 和去重归属 `x5crop.detection.outer`
     的 `base_outer_candidates` / `unique_outer_candidates`。
   - `image.deskew` 只负责 deskew angle 选择；旋转和裁切像素工具分别归属
     `image.transforms` 和 `image.crop_pixels`。
   - `io.tiff.read_tiff` 只返回 array、gray、profile 和 warnings；TIFF page object
     不沿 runtime/export 链路传播。
   - 这些层不应依赖 detection pipeline，也不应拥有 candidate、gate、finalization、
     output bleed 或 PASS/REVIEW 语义。

10. `x5crop.detection`
   - 负责 outer proposal、separator/content evidence、candidate build/run、
     scoring、candidate gates、selection、fallback 和 finalization。
   - 依赖 format / policy contract 和 geometry / image / io 基础能力。
   - `pipeline.py` 应保持主流程 orchestration。
   - `candidate_gates.py` 只负责候选级 separator evidence gate。
   - `candidate_decision.py` 只负责候选级 auto_gate / confidence / review reason。
   - `final_decision.py` 在 finalization 中统一执行 V4.9 conservative PASS/REVIEW。
   - `final_geometry.py` 负责输出前最终几何调整，包括 detection/output bleed、
     edge bleed protection 和 approved geometry adjustment。
   - `finalizer.py` 负责输出前最终收口，包括 outer retry、risk caps 和调用
     final geometry adjustment。
   - 专门模块承接具体职责，例如 `candidate_build.py`、`candidate_run.py`、
     `dual_lane.py`、`partial_holder.py`、`outer_retry.py`、`candidate_gates.py`、
     `candidate_decision.py`、`selection.py`、`final_decision.py`、`final_geometry.py`
     和 `finalizer.py`。

11. `x5crop.analysis_cache` / `x5crop.analysis_reuse` / `x5crop.export` /
    `x5crop.result_builder` / `x5crop.report_schema` / `x5crop.report_outputs` /
    `x5crop.debug`
   - `analysis_cache` 负责构建 detection/debug 共用的 per-image analysis cache。
   - `analysis_reuse` 负责 Debug Analysis report cache 匹配和 cached detection 恢复。
   - `export` 负责输出路径、review copy 和 metadata-safe TIFF crop 写入。
   - `result_builder` 统一将 fresh / cached detection 转成 `ProcessResult`。
   - `report_schema` 将 `Detection` / `ProcessResult` 序列化为稳定 report schema。
   - `report_outputs` 只写 JSONL / CSV report outputs；`debug` 只写 Debug Analysis / preview。
   - 不参与候选生成和 PASS/REVIEW 决策。

12. `tools`
   - `build_standalone.py` 是 Release 单文件构建 helper，会自动收集当前
     `x5crop/**/*.py` 并生成嵌入 import hook。
   - `tools/regression` 是开发期 report diff、reference baseline compare 和
     V4.9 safety classification 工具。
   - 不被 `X5_Crop.py` 或 runtime package 导入。

### 人工审核状态

本表记录截至 2026-07-02 的人工分层审核状态。它不是发布验收清单；
检测行为改动仍需要按“验证边界”执行 reference compare / safety classification。

| 层级 | 人工审核状态 | 当前清洁度 | 说明 / 下一步 |
| --- | --- | --- | --- |
| 1-5 Entry / startup：`X5_Crop.py`、`x5crop.cli`、`x5crop.config`、`x5crop.interactive`、`x5crop.input_probe`、`x5crop.app` | 已人工审核并清理 | 彻底干净 | 薄入口、参数解析、配置契约、交互菜单、输入探测和 app 调度边界清楚；后续避免把 TIFF 读取、layout 推断或 detection 放回入口。 |
| 6 Workflow：`x5crop.workflow`、`x5crop.source_config`、`x5crop.deskew_runtime` | 已人工审核并清理 | 彻底干净 | `workflow.py` 只保留单图主流程；cached analysis、runtime deskew、review/export、Debug outputs 和 report 写入均由 owning module 承接。 |
| 7 Policy：`x5crop.policies` | 已人工审核并清理 | 彻底干净 | runtime policy types、factory builders、parameter modules、format registry 和 parameter registry 已按职责分组；旧 `parameters.py` / `parameter_types.py` 兼容 re-export 层已删除。`parameter_aggregate.py` 仍较大，但只承担 flat `FormatParameters` aggregate 一个职责。 |
| 8 Format：`x5crop.formats` | 已人工审核并清理 | 彻底干净 | format identity、physical spec、count/aspect facts 和 CLI choice 已集中为唯一 source of truth；不反向依赖 policy。 |
| 9 Geometry / Image / IO | 已深度审核并清理 | 彻底干净 | 基础能力边界清楚：geometry 返回低层 box / gap / frame helper，image 负责灰度/deskew/像素变换，io 负责 TIFF profile；不拥有 candidate、gate、PASS/REVIEW 或 output bleed 语义。 |
| 10 Detection：`x5crop.detection` | 已高层审核，细分审核暂缓 | 未彻底干净 | 这是当前最大复杂源；`outer.py`、`outer_retry.py`、`candidate_run.py`、`content.py`、`diagnostics.py` 仍偏大，`detection.__init__` 仍是第 10 层 re-export 面。下一轮应按 outer、candidate、evidence、gate、decision、finalization 子层继续人工审核。 |
| 11 Output / Report / Debug：`analysis_cache`、`analysis_reuse`、`export`、`result_builder`、`report_schema`、`report_sections`、`report_outputs`、`debug` | 已人工审核并清理 | 彻底干净 | Debug 已拆为 canvas、gap overlays、panels、status 和 writer；Debug status 优先消费最终 decision summary。`report_schema` 只组装稳定 schema，candidate/gate section builder 归属 `report_sections.py`。空的 `x5crop.diagnostics` 占位包已删除。 |
| 12 Dev tools：`tools` | 已人工审核并清理 | 彻底干净 | `build_standalone.py` 已脱离旧静态 V4 module list，改为自动收集当前 `x5crop` 包；`tools/regression` 保持开发期 report compare / safety classifier，不进入 runtime package。 |
| Shared primitives：`domain`、`runtime`、`utils`、`constants`、`app_info`、`detection_detail` | 已独立人工审核 | 彻底干净 | 基础 dataclass、运行缓存、通用 helper、常量、版本/报告文件名和 stable detail key surface 均无反向依赖 workflow/debug/policy builder/detection pipeline。 |

### 最近清理层详细复审

| 范围 | 当前文件 | 复审结论 | 后续约束 |
| --- | --- | --- | --- |
| Workflow / runtime glue | `workflow.py`、`source_config.py`、`deskew_runtime.py`、`analysis_reuse.py`、`debug/outputs.py`、`export/actions.py` | 彻底干净。`workflow.py` 保持约 110 行，只做 read -> deskew -> detect -> finalization -> export -> report/debug 编排；cached analysis、profile-to-config、deskew、review copy、crop writing、Debug output 和 report writing 均已交给 owning module。 | 不把 scoring、candidate selection、TIFF metadata 写入细节、Debug 渲染或 report section 组装放回 workflow。 |
| Policy runtime / factory / parameters | `runtime_*.py`、`factory_*.py`、`parameter_*.py`、`format_*.py`、`registry.py`、`ids.py`、`decision_contract.py`、`decision_overrides.py`、`reporting.py` | 彻底干净。runtime contract、factory builder、source parameter type、format preset、decision contract 和 policy report serializer 已分开；`factory.py` 只做总装，`runtime_policy.py` 只定义 DetectionPolicy contract / re-export；旧 `parameters.py` 与 `parameter_types.py` 已删除。`parameter_aggregate.py` 仍大，但职责单一：flat `FormatParameters` aggregate 和 property views。 | 新参数必须先判断是 physical fact、runtime evidence wiring、source parameter、decision policy 还是 report/debug policy，不允许塞回一个大 bucket。 |
| Output / Report / Debug | `analysis_cache.py`、`analysis_reuse.py`、`result_builder.py`、`report_schema.py`、`report_sections.py`、`report_outputs.py`、`export/*`、`debug/*` | 彻底干净。`report_schema.py` 只做稳定 schema assembly；candidate table、selected candidate 和 gate records 在 `report_sections.py`；Debug 已拆成 canvas、gap overlays、panels、status、writer、outputs，空的 `x5crop.diagnostics` 包已删除。 | `detection/diagnostics.py` 仍属于 detection 内部只读诊断，不是 output/debug 层；如果继续清 detection，应同时考虑是否改名降低歧义。 |
| Shared primitives | `domain.py`、`runtime.py`、`utils.py`、`constants.py`、`app_info.py`、`detection_detail.py` | 彻底干净。基础 dataclass、analysis cache runtime object、通用 helper、常量、版本/报告文件名和 stable detail key surface 没有反向依赖 workflow、debug、policy builder 或 detection pipeline。 | 只能放无上层语义的共享 primitive；不能承载 candidate、gate、policy factory、report rendering 或 PASS/REVIEW 规则。 |

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
- `FinalizationPolicy`: finalization caps、finalization reason ids、approved geometry adjustment。
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
python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py x5crop/policies/*.py x5crop/geometry/*.py x5crop/io/*.py x5crop/image/*.py x5crop/export/*.py
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

如果当前 checkout 展开了 `tools/`，再额外编译 `tools/regression/*.py`。
Release build 工具改动还应运行 `tools/build_standalone.py` 并对生成的单文件做
`--version` smoke。

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
- CLI, configuration contract, interactive launcher, input probe, app runner,
  and workflow are separate.
- Workflow only orchestrates one-image processing.
- `x5crop.formats` owns physical format specs.
- Detection owns evidence generation, candidate build, and candidate ranking.
- Geometry / image / io provide lower-level capabilities.
- `x5crop.policies.decision_contract` owns the V4.9 ModePolicy, EvidencePolicy,
  RiskPolicy, CandidatePolicy, DecisionPolicy, OutputPolicy, and
  DecisionDiagnosticsPolicy.
- `x5crop.detection.final_decision` applies the unified PASS / REVIEW decision.
- Analysis reuse, export, report / debug consume stable results and explain V4.9
  decisions; `tools/` contains developer-only release build / reference compare /
  safety classification tools outside the runtime package.

### Fully Clean Definition

A layer is fully clean only when every public entry comes from the true owning
module, old aliases / shims / bridges / re-exports are removed, import direction
is provable, format- or mode-specific behavior is policy-owned, and
documentation matches the real code.

| Dimension | Standard |
| --- | --- |
| Responsibility | Each file has one clear ownership reason and is not a convenient dumping place. |
| API surface | No legacy aliases, barrel re-exports, bridge modules, or shim modules remain. |
| Import direction | Dependencies flow downward by layer; foundation layers do not depend back on workflow / detection / debug / report. |
| Naming | File, class, and field names describe current responsibility, not old versions, old behavior, or historical compromise. |
| Policy | Format / mode special behavior is explicit in policy and is not scattered through runtime code as implicit checks. |
| Data contracts | `RuntimeConfig`, `Detection`, `ProcessResult`, policy detail, and report schema keep stable boundaries. |
| Output surfaces | debug / report / export consume and explain results; they do not select candidates, run gates, or decide PASS/REVIEW. |
| Documentation sync | Structures described in `ARCHITECTURE.md` must match the real files, import surfaces, and policy surfaces. |

Semantic aggregation layers such as `registry.py`, `factory.py`, and
`report_schema.py` are allowed. Compatibility re-export layers that exist only
to preserve old import paths are not allowed.

### Runtime Layers

1. `X5_Crop.py`
   - Development entry.
   - V4 Release builds produce a standalone single-file script.

2. `x5crop.cli` / `x5crop.config`
   - Only parses CLI arguments into `CliOptions`.
   - `x5crop.config` owns only `CliOptions` and `RuntimeConfig` as the
     configuration contract between entry / startup and workflow.
   - CLI choice constants belong to `x5crop.formats` and are not re-exported
     from `x5crop.config`.
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
   - Orchestrates read -> deskew -> detect -> finalization -> export -> report/debug.
   - Delegates per-image report reuse, runtime deskew, output folders, Debug
     Analysis, export, and result assembly to focused modules.

7. `x5crop.policies`
   - Resolves runtime policy through `get_detection_policy(format_id, strip_mode)`.
   - `registry.py` only resolves and caches.
   - `format_modules.py` only maps format ids to `format_*` module names and imports.
   - Format profile modules such as `format_135.py` and `format_120_66.py`
     own both format / mode runtime presets and that format's parameter
     overrides.
   - `ids.py` owns shared policy id stems and the report schema version.
   - `runtime_policy.py` defines the runtime `DetectionPolicy` contract; runtime
     policy value objects are grouped into `runtime_base.py`, `runtime_outer.py`,
     `runtime_separator.py`, `runtime_content.py`, `runtime_candidate.py`,
     `runtime_final.py`, and `runtime_diagnostics.py`.
   - Source parameter group dataclasses are grouped into `parameter_content.py`,
     `parameter_outer.py`, `parameter_separator.py`, `parameter_scoring.py`,
     `parameter_finalization.py`, and `parameter_diagnostics.py`.
   - `parameter_aggregate.py` stores the flat `FormatParameters` aggregate and
     property views; `parameter_registry.py` stores shared 120 defaults and
     format parameter resolution.
   - `factory_presets.py` defines the format / mode preset contract; `factory.py`
     only assembles runtime `DetectionPolicy`, while concrete builders live in
     `factory_*` modules.
   - `reporting.py` only serializes runtime policy detail and does not own the
     detection result schema.
   - `decision_contract.py` is the V4.9 public decision policy contract;
     `decision_overrides.py` stores format / mode decision evidence overrides.
   - `x5crop.__init__`, `x5crop.io.__init__`, `x5crop.export.__init__`,
     `x5crop.debug.__init__`, and `x5crop.policies.__init__` are only package
     markers, not compatibility barrels or public re-export surfaces.

8. `x5crop.formats`
   - Is the single source of truth for format identity, physical specs,
     count/aspect facts, and CLI choices.
   - `FormatSpec` is shared by runtime detection, interactive / CLI, and the
     V4.9 decision contract.
   - Does not import `x5crop.policies` and does not own thresholds, gates, or
     candidate strategy.

9. `x5crop.geometry` / `x5crop.image` / `x5crop.io`
   - Provide boxes, layout, outer primitives, separator profile/cache, gap
     search, hard-gap trust, nearby separator correction, robust grid,
     edge-pair refine, enhanced separator, frame fit, deskew angle, pixel
     transforms, crop pixel validation, evidence images, and TIFF I/O.
   - These are shared lower-level capabilities used by detection, export, and
     debug.
   - Helpers that need format context should receive format or policy explicitly.
   - `geometry.__init__` is only a package marker; runtime code should import
     concrete helpers from their owning modules.
   - `geometry.outer_boxes` returns only `Box` / `Box | None`; `OuterCandidate`
     wrapping, candidate names, strategies, and deduplication belong to
     `x5crop.detection.outer` via `base_outer_candidates` /
     `unique_outer_candidates`.
   - `image.deskew` owns only deskew angle selection; rotation and crop pixel
     helpers live in `image.transforms` and `image.crop_pixels`.
   - `io.tiff.read_tiff` returns only array, gray, profile, and warnings; TIFF page
     objects do not flow through runtime/export.
   - These layers should not depend on the detection pipeline and should not own
     candidate, gate, finalization, output bleed, or PASS/REVIEW semantics.

10. `x5crop.detection`
   - Owns outer proposals, separator/content evidence, candidate build/run,
     scoring, candidate gates, selection, fallback, and finalization.
   - Depends on format / policy contracts and geometry / image / io lower-level
     capabilities.
   - `pipeline.py` should stay orchestration-focused.
   - `candidate_gates.py` owns candidate-level separator evidence gates.
   - `candidate_decision.py` owns candidate-level auto_gate / confidence / review reasons.
   - `final_decision.py` applies conservative V4.9 PASS/REVIEW rules during finalization.
   - `final_geometry.py` owns final pre-output geometry adjustment, including
     detection/output bleed, edge bleed protection, and approved geometry adjustment.
   - `finalizer.py` owns final pre-output handling, including outer retry, risk
     caps, and calls into final geometry adjustment.

11. `x5crop.analysis_cache` / `x5crop.analysis_reuse` / `x5crop.export` /
    `x5crop.result_builder` / `x5crop.report_schema` / `x5crop.report_outputs` /
    `x5crop.debug`
   - `analysis_cache` builds per-image analysis caches shared by detection/debug.
   - `analysis_reuse` matches Debug Analysis report caches and restores cached
     detections.
   - `export` owns output paths, review copies, and metadata-safe TIFF crop writes.
   - `result_builder` converts fresh / cached detections into `ProcessResult`.
   - `report_schema` serializes `Detection` / `ProcessResult` into the stable
     report schema.
   - `report_outputs` only writes JSONL / CSV report outputs; `debug` only writes Debug
     Analysis / previews.
   - Do not generate candidates or decide PASS/REVIEW.

12. `tools`
   - `build_standalone.py` is the Release single-file build helper. It
     automatically collects the current `x5crop/**/*.py` files and generates an
     embedded import hook.
   - `tools/regression` contains developer-only report diff, reference baseline
     compare, and V4.9 safety classification tools.
   - Not imported by `X5_Crop.py` or the runtime package.

### Manual Review Status

This table records the layer-by-layer manual review state as of 2026-07-02.
It is not a release acceptance checklist; detector behavior changes still need
the reference compare / safety classification described in the verification
section.

| Layer | Manual review state | Current cleanliness | Notes / next step |
| --- | --- | --- | --- |
| 1-5 Entry / startup: `X5_Crop.py`, `x5crop.cli`, `x5crop.config`, `x5crop.interactive`, `x5crop.input_probe`, `x5crop.app` | Reviewed and cleaned | Fully clean | Thin entry, argument parsing, configuration contract, interactive menu, input probing, and app scheduling have clear boundaries; keep TIFF reads, layout inference, and detection out of this layer. |
| 6 Workflow: `x5crop.workflow`, `x5crop.source_config`, `x5crop.deskew_runtime` | Reviewed and cleaned | Fully clean | `workflow.py` now keeps only the single-image main flow; cached analysis, runtime deskew, review/export, Debug outputs, and report writing are delegated to owning modules. |
| 7 Policy: `x5crop.policies` | Reviewed and cleaned | Fully clean | Runtime policy types, factory builders, parameter modules, format registry, and parameter registry are grouped by responsibility; the old `parameters.py` / `parameter_types.py` compatibility re-export layers are removed. `parameter_aggregate.py` remains large, but owns only the flat `FormatParameters` aggregate. |
| 8 Format: `x5crop.formats` | Reviewed and cleaned | Fully clean | Format identity, physical specs, count/aspect facts, and CLI choices are centralized as the single source of truth; this layer does not import policy. |
| 9 Geometry / Image / IO | Deep-reviewed and cleaned | Fully clean | Lower-level capability boundaries are clear: geometry owns box/gap/frame helpers, image owns grayscale/deskew/pixel transforms, and io owns TIFF profile handling; no candidate, gate, PASS/REVIEW, or output bleed semantics belong here. |
| 10 Detection: `x5crop.detection` | High-level reviewed, detailed review deferred | Not fully clean | This is the largest complexity source. `outer.py`, `outer_retry.py`, `candidate_run.py`, `content.py`, and `diagnostics.py` remain large, and `detection.__init__` remains the layer-10 re-export surface. Continue with outer, candidate, evidence, gate, decision, and finalization sublayer reviews. |
| 11 Output / Report / Debug: `analysis_cache`, `analysis_reuse`, `export`, `result_builder`, `report_schema`, `report_sections`, `report_outputs`, `debug` | Reviewed and cleaned | Fully clean | Debug is split into canvas, gap overlays, panels, status, and writer modules; Debug status prefers the final decision summary. `report_schema` only assembles the stable schema, candidate/gate section builders live in `report_sections.py`, and the empty `x5crop.diagnostics` placeholder package has been removed. |
| 12 Dev tools: `tools` | Reviewed and cleaned | Fully clean | `build_standalone.py` no longer uses the old static V4 module list and now auto-collects the current `x5crop` package; `tools/regression` remains developer-only report compare / safety classifier code outside the runtime package. |
| Shared primitives: `domain`, `runtime`, `utils`, `constants`, `app_info`, `detection_detail` | Independently reviewed | Fully clean | Base dataclasses, runtime caches, generic helpers, constants, version/report filenames, and stable detail-key surface have no reverse dependency on workflow/debug/policy builders/detection pipeline. |

### Recent Cleanup Detailed Review

| Scope | Current files | Review result | Constraint |
| --- | --- | --- | --- |
| Workflow / runtime glue | `workflow.py`, `source_config.py`, `deskew_runtime.py`, `analysis_reuse.py`, `debug/outputs.py`, `export/actions.py` | Fully clean. `workflow.py` stays around 110 lines and only orchestrates read -> deskew -> detect -> finalization -> export -> report/debug. Cached analysis, profile-to-config, deskew, review copies, crop writing, Debug output, and report writing are delegated to owning modules. | Do not move scoring, candidate selection, TIFF metadata write details, Debug rendering, or report section assembly back into workflow. |
| Policy runtime / factory / parameters | `runtime_*.py`, `factory_*.py`, `parameter_*.py`, `format_*.py`, `registry.py`, `ids.py`, `decision_contract.py`, `decision_overrides.py`, `reporting.py` | Fully clean. Runtime contracts, factory builders, source parameter types, format presets, decision contracts, and policy report serialization are separated. `factory.py` only assembles policies, `runtime_policy.py` only defines the DetectionPolicy contract / re-export surface, and the old `parameters.py` / `parameter_types.py` files are removed. `parameter_aggregate.py` remains large but has one job: the flat `FormatParameters` aggregate and property views. | Classify new parameters as physical facts, runtime evidence wiring, source parameters, decision policy, or report/debug policy before adding them; do not rebuild a single mixed bucket. |
| Output / Report / Debug | `analysis_cache.py`, `analysis_reuse.py`, `result_builder.py`, `report_schema.py`, `report_sections.py`, `report_outputs.py`, `export/*`, `debug/*` | Fully clean. `report_schema.py` only assembles the stable schema. Candidate table, selected candidate, and gate records live in `report_sections.py`. Debug is split into canvas, gap overlays, panels, status, writer, and outputs, and the empty `x5crop.diagnostics` package is removed. | `detection/diagnostics.py` is still detection-internal read-only diagnostics, not the output/debug layer. When detection cleanup resumes, consider renaming or splitting it to reduce ambiguity. |
| Shared primitives | `domain.py`, `runtime.py`, `utils.py`, `constants.py`, `app_info.py`, `detection_detail.py` | Fully clean. Base dataclasses, analysis-cache runtime objects, generic helpers, constants, version/report filenames, and stable detail-key surface have no reverse dependency on workflow, debug, policy builders, or the detection pipeline. | Keep this layer free of upper-layer semantics: no candidates, gates, policy factory behavior, report rendering, or PASS/REVIEW rules. |

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
python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py x5crop/policies/*.py x5crop/geometry/*.py x5crop/io/*.py x5crop/image/*.py x5crop/export/*.py
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

If `tools/` is expanded in the current checkout, also compile `tools/regression/*.py`.
Release build tool changes should also run `tools/build_standalone.py` and a
`--version` smoke on the generated single-file script.

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
