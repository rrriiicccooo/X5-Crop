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

当前架构以 evidence-governed policy reset 为目标。目标不是为了让更多困难样片
自动 PASS，而是在保留 TIFF I/O 和导出质量行为的前提下，让自动裁切只发生在
outer、separator、geometry、content 和 risk 证据能够组合解释时。

- 入口保持精简。
- CLI、配置契约、交互式 launcher、input probe、app runner 和 workflow 职责分离。
- workflow 只承担单图处理编排职责。
- `x5crop.formats` 明确 format physical spec。
- detection 只承担 evidence generation、candidate build 和候选排序职责。
- geometry / image / io 提供低层能力。
- `x5crop.policies.decision_contract` 拥有 public decision contract：ModePolicy、EvidencePolicy、
  RiskPolicy、CandidatePolicy、DecisionPolicy、OutputPolicy 和
  DecisionDiagnosticsPolicy。
- `x5crop.detection.final.pass_review` 统一执行 PASS / REVIEW 决策。
- analysis reuse、export、report / debug 消费稳定结果并解释 evidence-governed
  PASS / REVIEW 决策；
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
| 版本号位置 | 版本号只能出现在 `VERSION` / `APP_VERSION`、release 历史、release artifact 名、历史 archive 路径和机器 schema 值中；当前 module / class / function / policy id / 架构标签必须使用语义命名。 |
| 可达性 | active runtime 源文件必须能从 `X5_Crop.py` 或明确的开发工具入口静态或显式动态到达；只含 docstring / `__all__` 的 package marker `__init__.py` 允许存在。 |
| Policy | format / mode 特殊行为必须显式写入 policy，不能散落在 runtime 代码里靠隐式判断启用。 |
| 数据契约 | `RuntimeConfig`、`Detection`、`ProcessResult`、policy detail 和 report schema 各自边界稳定。 |
| Output surfaces | debug / report / export 只消费和解释结果，不参与候选选择、gate 或 PASS/REVIEW。 |
| 文档同步 | `ARCHITECTURE.md` 中声明的结构必须和真实文件、import 面、policy 面一致。 |

允许保留有明确语义的聚合层，例如 `registry.py`、`factory.py`、
`report_schema.py`。不允许保留仅为了旧 import 路径存在的兼容 re-export 层。

### 命名规则

当前源码命名必须遵守同一套语义后缀：

- `*Options`: 尚未读取文件、尚未探测图片的入口参数，例如 `CliOptions`。
- `*Config`: 已解析的运行配置契约，仅用于 `RuntimeConfig` 这类跨层运行上下文。
- `*Spec`: 物理事实或格式规格，例如 `FormatSpec`。
- `*Parameters`: 数值参数和低层执行参数，例如 `FormatParameters`、
  `GapSearchParameters`、`AxisBleedParameters`。
- `*Policy`: format / mode 行为、gate、decision 或 output 规则。
- `*Assessment`: 候选阶段的评估结果或评估过程；候选层不得使用 `Decision`
  表达最终裁切决定。
- `*Decision*`: 只用于最终 PASS / REVIEW 语义，例如
  `DetectionDecisionContract` 和 `DecisionPolicy`。
- `*Result`: 已完成流程的返回对象，例如 `ProcessResult` 和
  `SelectionResult`。

模块名也必须表达 owning layer：`cli_options.py` 只放入口 option，
`runtime_config.py` 只放运行配置契约，`geometry/output_bleed.py` 只放 frame
bleed 几何映射；不使用 `config.py`、`decision.py`、`output_geometry.py` 这类
容易把多个层级混在一起的宽泛名字。

### 运行层级

本节编号按 dependency / ownership boundary 排列，不是 workflow 的逐行调用顺序。
`x5crop.geometry` / `x5crop.image` / `x5crop.io` 是 detection、export 和 debug
共享的基础能力层，因此排在 `x5crop.detection` 之前；它们不是 detection 的子层。

1. `X5_Crop.py`
   - 开发入口。
   - Release 会由构建脚本生成单文件发布版。

2. `x5crop.cli` / `x5crop.cli_options` / `x5crop.runtime_config`
   - `x5crop.cli` 只解析命令行参数并构造 `CliOptions`。
   - `x5crop.cli_options` 只拥有入口参数契约 `CliOptions`。
   - `x5crop.runtime_config` 只拥有跨 workflow / detection / export / debug
     共享的运行配置契约 `RuntimeConfig`。
   - CLI choice 常量属于 `x5crop.formats`，不从入口配置模块 re-export。
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
     `runtime_final.py`、`runtime_diagnostics.py` 分组；低层 geometry parameter
     类型不通过 `runtime_policy.py` 转出口。
   - source parameter group dataclass 按 `parameter_content.py`、`parameter_outer.py`、
     `parameter_separator.py`、`parameter_scoring.py`、`parameter_finalization.py`
     和 `parameter_diagnostics.py` 分组。
   - `parameter_aggregate.py` 保存 flat `FormatParameters` aggregate；
     `parameter_views.py` 保存 derived views；`parameter_registry.py` 保存
     120 共享默认 helper 和 format 参数解析。
   - `factory_presets.py` 定义 format / mode preset contract；`factory.py` 只做
     runtime `DetectionPolicy` 总装，具体 builder 按 `factory_*` 文件分组。
   - `reporting.py` 只负责 runtime policy detail serializer，不拥有 detection
     result schema。
   - `decision_contract.py` 是 public decision policy contract；
     `decision_overrides.py` 保存 format / mode decision evidence 覆盖。
   - `x5crop.__init__`、`x5crop.io.__init__`、`x5crop.export.__init__`、
     `x5crop.debug.__init__` 和 `x5crop.policies.__init__` 只标记 package，
     不作为 compatibility barrel 或 public re-export surface。

8. `x5crop.formats`
   - 是 format identity、physical spec、count/aspect facts 和 CLI choice 的唯一
     source of truth。
   - `FormatSpec` 可被 runtime detection、interactive / CLI 和 decision
     contract 共享。
   - 不导入 `x5crop.policies`，不承载 threshold、gate 或候选策略。

9. `x5crop.runtime` / `x5crop.analysis_cache` / `x5crop.geometry` /
   `x5crop.image` / `x5crop.io`
   - `runtime.py` 拥有 `AnalysisCache` 和 report-record cache 数据容器。
   - `analysis_cache.py` 只构建 per-image `AnalysisCache`，供 workflow、
     detection 和 Debug Analysis 共享。
   - 提供 box、layout、outer primitive、separator profile/cache、gap search、
     hard-gap trust、nearby separator correction、robust grid、edge-pair refine、
     enhanced separator、frame fit、output bleed frame geometry、deskew angle、
     pixel transforms、crop pixel validation、证据图和 TIFF I/O helper。
   - 是 detection、export 和 debug 共享的基础能力层。
   - 需要 format 上下文的 helper 应显式接收 format、config 或 params；基础层
     不得自行读取 policy registry。
   - `geometry.__init__` 只标记 package；runtime 应从具体 owning module import。
   - `geometry.outer_boxes` 只返回 `Box` / `Box | None`；`OuterCandidate`
     包装、candidate name、strategy 和去重归属
     `x5crop.detection.outer.base` 的 `base_outer_candidates` /
     `unique_outer_candidates`。
   - `geometry.detection_parameters` 拥有低层 outer / separator / gap / grid
     parameter 类型；这些类型统一使用 `*Parameters`，不使用 runtime policy 命名。
   - `geometry.output_bleed` 拥有 detection/output bleed 的 frame geometry 映射、
     overlap output bleed 判断和 cached output bleed 重放；它不导入 runtime
     policy 类型，只接收显式参数。
   - `image.deskew` 只负责 deskew angle 选择，并通过显式传入的
     `image.deskew_parameters.DeskewParameters` 工作；旋转和裁切像素工具分别归属
     `image.transforms` 和 `image.crop_pixels`。
   - `io.tiff.read_tiff` 只返回 array、gray、profile 和 warnings；TIFF page object
     不沿 runtime/export 链路传播。
   - 这些层不应依赖 detection pipeline，也不应拥有 candidate、gate、
     finalization、export/report 或 PASS/REVIEW 语义。

10. `x5crop.detection`
   - 负责 outer proposal、separator/content evidence、candidate build/run、
     scoring、candidate gates、selection、fallback 和 finalization。
   - 依赖 format / policy contract 和 geometry / image / io 基础能力。
   - `pipeline.py` 只保留主流程 orchestration，不提供旧入口 alias。
   - `outer/` 只提出 outer proposal：`base.py`、`content_outer.py`、
     `edge_anchor.py`、`separator_first.py`、`separator_geometry.py`、
     `dark_band.py`、`alignment.py`、`outer_correction.py` 和 retry 子模块分别拥有各自策略。
   - `evidence/` 只生成结构化证据：content evidence/profile、separator gap
     evidence、read-only gap diagnostics 和 risk evidence。
   - `candidate/` 只负责候选生命周期：count plan、source build、candidate run、
     candidate-level gates、candidate_assessment、scoring、selection、partial holder
     和 fallback；content-driven candidate 归属 `content_candidate.py`。
   - `modes/` 承接专用 detector，例如 135-dual lane 和 unsupported review-only。
   - `final/pass_review.py` 在 finalization 中统一执行 PASS/REVIEW。
   - `final/geometry.py` 负责输出前 finalization 内部几何调整，包括 edge bleed
     protection 和 approved geometry adjustment。
   - `final/finalize.py` 负责输出前最终收口，包括 outer retry、risk caps 和调用
     final geometry adjustment。
   - `detection.__init__` 和各子包 `__init__` 只标记 package，不作为 compatibility
     barrel 或 public re-export surface。

11. `x5crop.analysis_reuse` / `x5crop.export` / `x5crop.result_builder` /
    `x5crop.report_schema` / `x5crop.report_outputs` / `x5crop.debug`
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
| 1-5 Entry / startup：`X5_Crop.py`、`x5crop.cli`、`x5crop.cli_options`、`x5crop.runtime_config`、`x5crop.interactive`、`x5crop.input_probe`、`x5crop.app` | 已人工审核并清理 | 彻底干净 | 薄入口、参数解析、入口 option、runtime config 契约、交互菜单、输入探测和 app 调度边界清楚；后续避免把 TIFF 读取、layout 推断或 detection 放回入口。 |
| 6 Workflow：`x5crop.workflow`、`x5crop.profile_runtime`、`x5crop.deskew_runtime` | 已人工审核并清理 | 彻底干净 | `workflow.py` 只保留单图主流程；cached analysis、runtime deskew、review/export、Debug outputs 和 report 写入均由 owning module 承接。 |
| 7 Policy：`x5crop.policies` | 已人工审核并清理 | 彻底干净 | runtime policy types、factory builders、parameter modules、format registry 和 parameter registry 已按职责分组；旧 `parameters.py` / `parameter_types.py` 兼容 re-export 层已删除。`runtime_policy.py` 不再转出口低层 geometry parameters；`parameter_aggregate.py` 只承担 flat `FormatParameters` aggregate 一个职责。 |
| 8 Format：`x5crop.formats` | 已人工审核并清理 | 彻底干净 | format identity、physical spec、count/aspect facts 和 CLI choice 已集中为唯一 source of truth；不反向依赖 policy。 |
| 9 Runtime Cache / Geometry / Image / IO | 已深度审核并清理 | 彻底干净 | 基础能力边界清楚：runtime / analysis_cache 只拥有共享缓存容器和构建器，geometry 返回低层 box / gap / frame / output bleed geometry helper，image 负责灰度/deskew/像素变换，io 负责 TIFF profile；不拥有 candidate、gate、PASS/REVIEW 或 export/report 语义。 |
| 10 Detection：`x5crop.detection` | 已人工审核并清理 | 彻底干净 | Detection 已拆为 `outer/`、`evidence/`、`candidate/`、`modes/` 和 `final/` 子包；旧平铺 `outer.py`、`outer_retry.py`、`candidate_run.py`、`content.py`、`diagnostics.py`、`finalizer.py` 等 compatibility surface 已移除；package `__init__` 只保留 marker；candidate assessment 与 final decision 命名已分离。 |
| 11 Output / Report / Debug：`analysis_reuse`、`export`、`result_builder`、`report_schema`、`report_sections`、`report_outputs`、`debug` | 已人工审核并清理 | 彻底干净 | cached reuse 不再依赖 detection final 内部；Debug 已拆为 canvas、gap overlays、panels、status 和 writer；`report_schema` 只组装稳定 schema，candidate/gate section builder 归属 `report_sections.py`。空的 `x5crop.diagnostics` 占位包已删除。 |
| 12 Dev tools：`tools` | 已人工审核并清理 | 彻底干净 | `build_standalone.py` 已脱离旧静态 module list，改为自动收集当前 `x5crop` 包；`tools/regression` 保持开发期 report compare / safety classifier，不进入 runtime package。 |
| Shared primitives：`domain`、`utils`、`constants`、`app_info`、`detection_detail` | 已独立人工审核 | 彻底干净 | 基础 dataclass、通用 helper、常量、版本/报告文件名和 stable detail key surface 均无反向依赖 workflow/debug/policy builder/detection pipeline。 |

### 最近清理层详细复审

| 范围 | 当前文件 | 复审结论 | 后续约束 |
| --- | --- | --- | --- |
| Detection core | `detection/pipeline.py`、`detection/outer/*`、`detection/evidence/*`、`detection/candidate/*`、`detection/modes/*`、`detection/final/*` | 彻底干净。第 10 层已按 outer proposal、evidence、candidate lifecycle、dedicated modes 和 finalization 子包拆分；旧平铺 detection 模块和 package-level re-export 面已删除；`pipeline.py` 只编排，不保留 `detect_image` 旧别名。 | Detection 清理应继续保持行为搬迁优先，不在结构迁移中调整阈值或放宽 PASS；新增 format/mode 特殊行为必须先进入 policy，再由对应子包消费。 |
| Workflow / runtime glue | `workflow.py`、`profile_runtime.py`、`deskew_runtime.py`、`analysis_reuse.py`、`debug/outputs.py`、`export/actions.py` | 彻底干净。`workflow.py` 保持约 110 行，只做 read -> deskew -> detect -> finalization -> export -> report/debug 编排；cached analysis、profile-to-runtime、deskew、review copy、crop writing、Debug output 和 report writing 均已交给 owning module。 | 不把 scoring、candidate selection、TIFF metadata 写入细节、Debug 渲染或 report section 组装放回 workflow。 |
| Policy runtime / factory / parameters | `runtime_*.py`、`factory_*.py`、`parameter_*.py`、`format_*.py`、`registry.py`、`ids.py`、`decision_contract.py`、`decision_overrides.py`、`reporting.py` | 彻底干净。runtime contract、factory builder、source parameter type、format preset、decision contract 和 policy report serializer 已分开；`factory.py` 只做总装，`runtime_policy.py` 只定义 DetectionPolicy contract / runtime re-export；旧 `parameters.py` 与 `parameter_types.py` 已删除。`parameter_aggregate.py` 只保留 flat `FormatParameters` aggregate，derived views 归属 `parameter_views.py`。 | 新参数必须先判断是 physical fact、runtime evidence wiring、source parameter、decision policy 还是 report/debug policy，不允许塞回一个大 bucket。 |
| Runtime cache / foundation | `runtime_config.py`、`runtime.py`、`analysis_cache.py`、`geometry/*`、`image/*`、`io/*` | 彻底干净。`runtime_config.py` 只定义 shared runtime contract，`runtime.py` 只定义 shared cache containers，`analysis_cache.py` 只构建 per-image cache；geometry / image / io 保持低层能力边界，低层参数使用 `*Parameters` 命名，不承载 candidate、gate、PASS/REVIEW 或 export/report 语义。 | 需要新增共享 cache 字段时先确认它是 detection/debug 共用数据，不把 final decision 或 report rendering 状态塞进 cache。 |
| Output / Report / Debug | `analysis_reuse.py`、`result_builder.py`、`report_schema.py`、`report_sections.py`、`report_outputs.py`、`export/*`、`debug/*` | 彻底干净。`report_schema.py` 只做稳定 schema assembly；candidate table、selected candidate 和 gate records 在 `report_sections.py`；Debug 已拆成 canvas、gap overlays、panels、status、writer、outputs，空的 `x5crop.diagnostics` 包已删除。 | Detection 内部只读诊断已改归 `x5crop.detection.evidence.read_only` / `gap_diagnostics` / `risk`，不再使用容易和 output/debug 混淆的 `detection/diagnostics.py`。 |
| Shared primitives | `domain.py`、`utils.py`、`constants.py`、`app_info.py`、`detection_detail.py` | 彻底干净。基础 dataclass、通用 helper、常量、版本/报告文件名和 stable detail key surface 没有反向依赖 workflow、debug、policy builder 或 detection pipeline。 | 只能放无上层语义的共享 primitive；不能承载 candidate、gate、policy factory、report rendering 或 PASS/REVIEW 规则。 |

### Policy 归属

Public decision policy contract 由 `DetectionDecisionContract` 表达：

- `FormatSpec`: physical facts，不承载检测策略。
- `ModePolicy`: full / partial count、outer、stop condition 和 edge trust。
- `EvidencePolicy`: outer / separator / geometry / content 的最低组合证据。
- `RiskPolicy`: overlap、outer-content mismatch、candidate competition、partial edge
  uncertainty 等 REVIEW 风险。
- `CandidatePolicy`: content-only、fallback、weak-grid、equal-gap 候选默认不直接 PASS。
- `DecisionPolicy`: PASS / REVIEW reason ids 和 confidence cap。
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

所有影响 active final decision 的参数必须写入 `report_schema.decision_policy_detail`。

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

V4.9 is an evidence-governed policy reset. It is not intended to make more
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
- `x5crop.policies.decision_contract` owns the public decision contract:
  ModePolicy, EvidencePolicy,
  RiskPolicy, CandidatePolicy, DecisionPolicy, OutputPolicy, and
  DecisionDiagnosticsPolicy.
- `x5crop.detection.final.pass_review` applies the unified PASS / REVIEW decision.
- Analysis reuse, export, report / debug consume stable results and explain
  evidence-governed PASS / REVIEW decisions; `tools/` contains developer-only
  release build / reference compare / safety classification tools outside the
  runtime package.

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
| Version tags | Version tags may appear only in `VERSION` / `APP_VERSION`, release history, release artifact names, historical archive paths, and machine schema values; current module / class / function / policy id / architecture labels must be semantic. |
| Reachability | Active runtime source files must be reachable from `X5_Crop.py` or an explicit developer-tool entry through static imports or documented dynamic imports; package marker `__init__.py` files with only a docstring / `__all__` are allowed. |
| Policy | Format / mode special behavior is explicit in policy and is not scattered through runtime code as implicit checks. |
| Data contracts | `RuntimeConfig`, `Detection`, `ProcessResult`, policy detail, and report schema keep stable boundaries. |
| Output surfaces | debug / report / export consume and explain results; they do not select candidates, run gates, or decide PASS/REVIEW. |
| Documentation sync | Structures described in `ARCHITECTURE.md` must match the real files, import surfaces, and policy surfaces. |

Semantic aggregation layers such as `registry.py`, `factory.py`, and
`report_schema.py` are allowed. Compatibility re-export layers that exist only
to preserve old import paths are not allowed.

### Naming Rules

Current source names must use one semantic suffix system:

- `*Options`: entry arguments before file probing, such as `CliOptions`.
- `*Config`: resolved runtime configuration contracts, limited to shared
  runtime context such as `RuntimeConfig`.
- `*Spec`: physical facts or format specifications, such as `FormatSpec`.
- `*Parameters`: numeric source parameters and low-level execution parameters,
  such as `FormatParameters`, `GapSearchParameters`, and `AxisBleedParameters`.
- `*Policy`: format / mode behavior, gates, decisions, or output rules.
- `*Assessment`: candidate-stage evaluation; candidate code must not use
  `Decision` for non-final crop decisions.
- `*Decision*`: final PASS / REVIEW semantics only, such as
  `DetectionDecisionContract` and `DecisionPolicy`.
- `*Result`: completed process return objects, such as `ProcessResult` and
  `SelectionResult`.

Module names must also name their owning layer: `cli_options.py` owns entry
options only, `runtime_config.py` owns the runtime configuration contract only,
and `geometry/output_bleed.py` owns frame bleed geometry only. Avoid broad names
such as `config.py`, `decision.py`, and `output_geometry.py` because they blur
layer boundaries.

### Runtime Layers

1. `X5_Crop.py`
   - Development entry.
   - Release builds produce a standalone single-file script.

2. `x5crop.cli` / `x5crop.cli_options` / `x5crop.runtime_config`
   - `x5crop.cli` only parses CLI arguments into `CliOptions`.
   - `x5crop.cli_options` owns only the entry argument contract `CliOptions`.
   - `x5crop.runtime_config` owns only the shared runtime configuration contract
     consumed by workflow, detection, export, and debug.
   - CLI choice constants belong to `x5crop.formats` and are not re-exported
     from entry configuration modules.
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
     `runtime_final.py`, and `runtime_diagnostics.py`; low-level geometry parameter
     types are not re-exported through `runtime_policy.py`.
   - Source parameter group dataclasses are grouped into `parameter_content.py`,
     `parameter_outer.py`, `parameter_separator.py`, `parameter_scoring.py`,
     `parameter_finalization.py`, and `parameter_diagnostics.py`.
   - `parameter_aggregate.py` stores the flat `FormatParameters` aggregate,
     `parameter_views.py` stores derived views, and `parameter_registry.py`
     stores shared 120 defaults plus format parameter resolution.
   - `factory_presets.py` defines the format / mode preset contract; `factory.py`
     only assembles runtime `DetectionPolicy`, while concrete builders live in
     `factory_*` modules.
   - `reporting.py` only serializes runtime policy detail and does not own the
     detection result schema.
   - `decision_contract.py` is the public decision policy contract;
     `decision_overrides.py` stores format / mode decision evidence overrides.
   - `x5crop.__init__`, `x5crop.io.__init__`, `x5crop.export.__init__`,
     `x5crop.debug.__init__`, and `x5crop.policies.__init__` are only package
     markers, not compatibility barrels or public re-export surfaces.

8. `x5crop.formats`
   - Is the single source of truth for format identity, physical specs,
     count/aspect facts, and CLI choices.
   - `FormatSpec` is shared by runtime detection, interactive / CLI, and the
     decision contract.
   - Does not import `x5crop.policies` and does not own thresholds, gates, or
     candidate strategy.

9. `x5crop.runtime` / `x5crop.analysis_cache` / `x5crop.geometry` /
   `x5crop.image` / `x5crop.io`
   - `runtime.py` owns `AnalysisCache` and report-record cache containers.
   - `analysis_cache.py` only builds the per-image `AnalysisCache` shared by
     workflow, detection, and Debug Analysis.
   - Provide boxes, layout, outer primitives, separator profile/cache, gap
     search, hard-gap trust, nearby separator correction, robust grid,
     edge-pair refine, enhanced separator, frame fit, output bleed frame
     geometry, deskew angle, pixel transforms, crop pixel validation, evidence
     images, and TIFF I/O.
   - These are shared lower-level capabilities used by detection, export, and
     debug.
   - Helpers that need format context should receive format, config, or params explicitly.
   - `geometry.__init__` is only a package marker; runtime code should import
     concrete helpers from their owning modules.
   - `geometry.outer_boxes` returns only `Box` / `Box | None`; `OuterCandidate`
     wrapping, candidate names, strategies, and deduplication belong to
     `x5crop.detection.outer.base` via `base_outer_candidates` /
     `unique_outer_candidates`.
   - `geometry.detection_parameters` owns low-level outer / separator / gap /
     grid parameter types; these types consistently use `*Parameters` and do
     not use runtime policy naming.
   - `geometry.output_bleed` owns detection/output bleed frame-geometry mapping,
     overlap output bleed checks, and cached output bleed replay; it does not
     import runtime policy types and receives explicit parameters.
   - `image.deskew` owns only deskew angle selection; rotation and crop pixel
     helpers live in `image.transforms` and `image.crop_pixels`.
   - `io.tiff.read_tiff` returns only array, gray, profile, and warnings; TIFF page
     objects do not flow through runtime/export.
   - These layers should not depend on the detection pipeline and should not own
     candidate, gate, finalization, export/report, or PASS/REVIEW semantics.

10. `x5crop.detection`
   - Owns outer proposals, separator/content evidence, candidate build/run,
     scoring, candidate gates, selection, fallback, and finalization.
   - Depends on format / policy contracts and geometry / image / io lower-level
     capabilities.
   - `pipeline.py` stays orchestration-focused and does not provide old entry aliases.
   - `outer/` only proposes outer boxes. `base.py`, `content_outer.py`,
     `edge_anchor.py`, `separator_first.py`, `separator_geometry.py`,
     `dark_band.py`, `alignment.py`, `outer_correction.py`, and retry modules own their specific
     proposal / correction strategies.
   - `evidence/` only generates structured evidence: content evidence/profile,
     separator gap evidence, read-only gap diagnostics, and risk evidence.
   - `candidate/` owns the candidate lifecycle: count planning, source build,
     candidate run, candidate-level gates, candidate_assessment, scoring,
     selection, partial holder, and fallback; content-driven candidates live in
     `content_candidate.py`.
   - `modes/` owns dedicated detectors, such as 135-dual lane and unsupported
     review-only paths.
   - `final/pass_review.py` applies PASS/REVIEW rules during finalization.
   - `final/geometry.py` owns finalization-internal geometry adjustment,
     including edge bleed protection and approved geometry adjustment.
   - `final/finalize.py` owns final pre-output handling, including outer retry, risk
     caps, and calls into final geometry adjustment.
   - `detection.__init__` and subpackage `__init__` files are package markers
     only, not compatibility barrels or public re-export surfaces.

11. `x5crop.analysis_reuse` / `x5crop.export` / `x5crop.result_builder` /
    `x5crop.report_schema` / `x5crop.report_outputs` / `x5crop.debug`
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
     compare, and safety classification tools.
   - Not imported by `X5_Crop.py` or the runtime package.

### Manual Review Status

This table records the layer-by-layer manual review state as of 2026-07-02.
It is not a release acceptance checklist; detector behavior changes still need
the reference compare / safety classification described in the verification
section.

| Layer | Manual review state | Current cleanliness | Notes / next step |
| --- | --- | --- | --- |
| 1-5 Entry / startup: `X5_Crop.py`, `x5crop.cli`, `x5crop.cli_options`, `x5crop.runtime_config`, `x5crop.interactive`, `x5crop.input_probe`, `x5crop.app` | Reviewed and cleaned | Fully clean | Thin entry, argument parsing, entry options, runtime config contract, interactive menu, input probing, and app scheduling have clear boundaries; keep TIFF reads, layout inference, and detection out of this layer. |
| 6 Workflow: `x5crop.workflow`, `x5crop.profile_runtime`, `x5crop.deskew_runtime` | Reviewed and cleaned | Fully clean | `workflow.py` now keeps only the single-image main flow; cached analysis, runtime deskew, review/export, Debug outputs, and report writing are delegated to owning modules. |
| 7 Policy: `x5crop.policies` | Reviewed and cleaned | Fully clean | Runtime policy types, factory builders, parameter modules, format registry, and parameter registry are grouped by responsibility; the old `parameters.py` / `parameter_types.py` compatibility re-export layers are removed. `runtime_policy.py` no longer re-exports low-level geometry parameter types. `parameter_aggregate.py` owns only flat defaults, while `parameter_views.py` owns derived parameter views. |
| 8 Format: `x5crop.formats` | Reviewed and cleaned | Fully clean | Format identity, physical specs, count/aspect facts, and CLI choices are centralized as the single source of truth; this layer does not import policy. |
| 9 Runtime Cache / Geometry / Image / IO | Deep-reviewed and cleaned | Fully clean | Lower-level capability boundaries are clear: runtime / analysis_cache only own shared cache containers and builders, geometry owns box/gap/frame/output-bleed geometry helpers plus low-level detection parameter types, image owns grayscale/deskew/pixel transforms plus deskew parameters, and io owns TIFF profile handling; no candidate, gate, PASS/REVIEW, or export/report semantics belong here. |
| 10 Detection: `x5crop.detection` | Reviewed and cleaned | Fully clean | Detection is split into `outer/`, `evidence/`, `candidate/`, `modes/`, and `final/` subpackages. The old flat `outer.py`, `outer_retry.py`, `candidate_run.py`, `content.py`, `diagnostics.py`, `finalizer.py`, and related compatibility surfaces are removed; package `__init__` files are markers only; candidate assessment and final decision naming are separated. |
| 11 Output / Report / Debug: `analysis_reuse`, `export`, `result_builder`, `report_schema`, `report_sections`, `report_outputs`, `debug` | Reviewed and cleaned | Fully clean | Cached reuse no longer depends on detection final internals. Debug is split into canvas, gap overlays, panels, status, and writer modules. `report_schema` only assembles the stable schema, candidate/gate section builders live in `report_sections.py`, and the empty `x5crop.diagnostics` placeholder package has been removed. |
| 12 Dev tools: `tools` | Reviewed and cleaned | Fully clean | `build_standalone.py` auto-collects the current `x5crop` package and uses semantic source-tree wording; `tools/regression` remains developer-only report compare / safety classifier code outside the runtime package. |
| Shared primitives: `domain`, `utils`, `constants`, `app_info`, `detection_detail` | Independently reviewed | Fully clean | Base dataclasses, generic helpers, constants, version/report filenames, and stable detail-key surface have no reverse dependency on workflow/debug/policy builders/detection pipeline. |

### Recent Cleanup Detailed Review

| Scope | Current files | Review result | Constraint |
| --- | --- | --- | --- |
| Detection core | `detection/pipeline.py`, `detection/outer/*`, `detection/evidence/*`, `detection/candidate/*`, `detection/modes/*`, `detection/final/*` | Fully clean. Layer 10 is split into outer proposal, evidence, candidate lifecycle, dedicated modes, and finalization subpackages; old flat detection modules and package-level re-export surfaces are removed; `pipeline.py` only orchestrates and no longer keeps the old `detect_image` alias. | Keep detection cleanup behavior-preserving; do not tune thresholds or loosen PASS during structure moves. New format/mode-specific behavior must enter policy first and be consumed by the owning subpackage. |
| Workflow / runtime glue | `workflow.py`, `profile_runtime.py`, `deskew_runtime.py`, `analysis_reuse.py`, `debug/outputs.py`, `export/actions.py` | Fully clean. `workflow.py` stays around 110 lines and only orchestrates read -> deskew -> detect -> finalization -> export -> report/debug. Cached analysis, profile-to-runtime, deskew, review copies, crop writing, Debug output, and report writing are delegated to owning modules. | Do not move scoring, candidate selection, TIFF metadata write details, Debug rendering, or report section assembly back into workflow. |
| Policy runtime / factory / parameters | `runtime_*.py`, `factory_*.py`, `parameter_*.py`, `format_*.py`, `registry.py`, `ids.py`, `decision_contract.py`, `decision_overrides.py`, `reporting.py` | Fully clean. Runtime contracts, factory builders, source parameter types, format presets, decision contracts, and policy report serialization are separated. `factory.py` only assembles policies, `runtime_policy.py` only defines the DetectionPolicy contract / runtime re-export surface, and the old `parameters.py` / `parameter_types.py` files are removed. `parameter_aggregate.py` keeps only the flat `FormatParameters` aggregate, while derived views belong to `parameter_views.py`. | Classify new parameters as physical facts, runtime evidence wiring, source parameters, decision policy, or report/debug policy before adding them; do not rebuild a single mixed bucket. |
| Runtime cache / foundation | `runtime_config.py`, `runtime.py`, `analysis_cache.py`, `geometry/*`, `image/*`, `io/*` | Fully clean. `runtime_config.py` only defines the shared runtime contract, `runtime.py` only defines shared cache containers, `analysis_cache.py` only builds per-image cache, and geometry / image / io keep low-level capability boundaries with `*Parameters` naming and without candidate, gate, PASS/REVIEW, or export/report semantics. | Before adding a shared cache field, confirm it is data shared by detection/debug and not final decision or report-rendering state. |
| Output / Report / Debug | `analysis_reuse.py`, `result_builder.py`, `report_schema.py`, `report_sections.py`, `report_outputs.py`, `export/*`, `debug/*` | Fully clean. `report_schema.py` only assembles the stable schema. Candidate table, selected candidate, and gate records live in `report_sections.py`. Debug is split into canvas, gap overlays, panels, status, writer, and outputs, and the empty `x5crop.diagnostics` package is removed. | Detection-internal read-only diagnostics now live in `x5crop.detection.evidence.read_only` / `gap_diagnostics` / `risk`, avoiding confusion with the output/debug layer. |
| Shared primitives | `domain.py`, `utils.py`, `constants.py`, `app_info.py`, `detection_detail.py` | Fully clean. Base dataclasses, generic helpers, constants, version/report filenames, and stable detail-key surface have no reverse dependency on workflow, debug, policy builders, or the detection pipeline. | Keep this layer free of upper-layer semantics: no candidates, gates, policy factory behavior, report rendering, or PASS/REVIEW rules. |

### Policy Ownership

The public decision policy contract is `DetectionDecisionContract`:

- `FormatSpec`: physical facts, not detection strategy.
- `ModePolicy`: full / partial count, outer, stop condition, and edge trust.
- `EvidencePolicy`: minimum combined outer / separator / geometry / content evidence.
- `RiskPolicy`: overlap, outer-content mismatch, candidate competition, and
  partial-edge review risks.
- `CandidatePolicy`: content-only, fallback, weak-grid, and equal-gap candidates
  are review-only by default.
- `DecisionPolicy`: PASS / REVIEW reason ids and confidence cap.
- `OutputPolicy`: TIFF metadata/export behavior and output bleed.
- `DecisionDiagnosticsPolicy`: diagnostics panel and overlay detail recorded in
  the decision/report contract.

The older `DetectionPolicy` remains an internal evidence-generation wiring
surface. Parameters that affect the active final decision must be written to
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
