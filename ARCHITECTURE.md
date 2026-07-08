# X5 Crop 架构说明 / Architecture Guide

本文件只保留两个视角：运行流程架构和源码分层架构。版本历史见 `CHANGELOG.md`；
用户说明见 `README.md`；Codex 规则和 handoff 见 `AGENTS.md`。

This file keeps only two views: runtime-flow architecture and source-layer
architecture. Version history lives in `CHANGELOG.md`; user instructions live in
`README.md`; Codex rules and handoff live in `AGENTS.md`.

## 中文说明

### 1. 运行流程架构

运行流程描述一次任务从入口到输出如何流动。它不描述版本历史，也不列审计台账。

```text
X5_Crop.py / launchers
  -> entry options
  -> runtime bootstrap
  -> workflow
  -> detection
  -> decision
  -> finalization
  -> export / report / debug
```

#### 1.1 顶层阶段

| 阶段 | 主要职责 | 主要位置 |
|---|---|---|
| Entry | 解析 CLI / interactive 输入，形成入口选项。 | `X5_Crop.py`, `x5crop.entry`, launchers |
| Runtime bootstrap | 探测输入、解析 layout、装配 runtime config 和 active policy。 | `x5crop.runtime.config`, `input_probe`, `app`, `policy_context` |
| Workflow | 编排单图处理顺序，不拥有检测策略。 | `x5crop.runtime.workflow` |
| Preprocess | 读取 TIFF、生成基础灰度、执行 deskew、准备证据输入和 cache。 | `x5crop.io`, `x5crop.image`, `x5crop.cache`, `x5crop.runtime.deskew` |
| Detection | 生成候选、证据、候选评估、候选扩展和候选选择。 | `x5crop.detection` |
| Decision | 将候选级证据转成最终 PASS / REVIEW、最终原因和 confidence cap。 | `x5crop.detection.decision` |
| Finalization | 对已决策结果做 output-adjacent 几何调整、bleed 和只读 diagnostics attachment。 | `x5crop.detection.final`, `x5crop.output` |
| Export | 写出裁切 TIFF 或 review copy，保持 TIFF 输出质量边界。 | `x5crop.export` |
| Report / Debug | 写机器报告、人类摘要和 Debug Analysis，不反向参与候选选择。 | `x5crop.report`, `x5crop.debug` |

#### 1.2 Entry 到 Runtime

入口层只负责把用户输入变成明确选项：

- CLI 参数由 `x5crop.entry.cli` 解析。
- 双击启动器只负责找到 Python 并进入交互流程。
- interactive 菜单由 `x5crop.entry.interactive` 处理。
- runtime bootstrap 将入口选项、输入路径、layout、format、strip mode 和 active policy 绑定成运行上下文。

入口层不读取图像内容，不做候选判断，不决定 PASS / REVIEW。

#### 1.3 Workflow 到 Detection

`workflow` 是编排层：

```text
read TIFF
  -> build base gray / evidence input
  -> deskew when enabled
  -> reuse compatible analysis when available
  -> run detection
  -> apply decision
  -> finalize
  -> export / report / debug
```

workflow 可以决定是否复用已匹配的 analysis report，但不能把复用结果解释成新的检测策略。
检测策略必须来自 active runtime policy，并通过 detection / decision 层执行。
workflow 只计算输出 surface 路径；只有 crop、review copy、debug 或 report 真的写出时才创建输出目录。

#### 1.4 Detection 到 Decision

detection 内部按候选生命周期流动：

```text
candidate plan
  -> physical proposal
  -> guidance
  -> candidate build
  -> candidate assessment
  -> candidate extension
  -> candidate selection
  -> decision
```

| 子阶段 | 主要职责 |
|---|---|
| Physical proposal | 产生 outer、separator、photo-size 等物理候选或证据。 |
| Guidance | 使用 content-derived hint 辅助 outer / separator search。 |
| Candidate plan | 只声明 count、offset、candidate source descriptors 和 execution budget。 |
| Candidate build | 将 source descriptor、outer、separator gaps 和 frame geometry 组装成未评分 Detection。 |
| Candidate assessment | 计算 candidate support、candidate gate、candidate blockers、diagnostics 和 confidence caps。 |
| Candidate extension | 对 corrected outer、content-guided separator 等候选重新 build / reassess。 |
| Candidate selection | 在已评估候选之间选择 selected candidate，并记录 competition detail。 |
| Decision | 生成 final evidence summary、decision signals、decision gate、final review reasons 和最终 status。 |

candidate assessment 只产生候选级解释；最终用户可见原因只由 decision 产生。

#### 1.5 Decision 到 Output

decision 之后的层级只消费结果：

- `detection.final` 只编排已决策结果的 output-adjacent finalization。
- `x5crop.output` 提供 output surface、approved geometry adjustment、bleed 和 overlap helper。
- `x5crop.export` 写自动裁切 TIFF 或 `needs_review/` copy。
- `x5crop.report` 写 JSONL / CSV / report sections。
- `x5crop.debug` 生成 Debug Analysis 面板。

这些层级不能重新判断 PASS / REVIEW，也不能根据 confidence 自行推导最终状态。

### 2. 源码分层架构

源码分层描述每个 package 拥有什么知识，以及它不能拥有的东西。

#### 2.1 顶层分层

| 层级 | 主要职责 |
|---|---|
| `x5crop.entry` | 用户入口和选项解析。 |
| `x5crop.runtime` | 运行配置、输入探测、workflow、deskew runtime、policy context、analysis reuse。 |
| `x5crop.formats` | format identity、family、count、aspect 和物理 facts。 |
| `x5crop.policies` | runtime policy、parameter ownership、policy assembly、decision contract、policy reporting。 |
| `x5crop.cache` | analysis / separator cache adapters。 |
| `x5crop.geometry` | box、gap、separator profile、edge pair、frame fit、layout、outer box 等纯几何能力。 |
| `x5crop.image` | gray、deskew、evidence image、pixel transforms 和 crop pixels。 |
| `x5crop.io` | TIFF 读取和写入相关 I/O。 |
| `x5crop.detection` | 候选、证据、assessment、selection、decision、finalization。 |
| `x5crop.output` | output-adjacent bleed / overlap read model 和输出几何 helper。 |
| `x5crop.export` | crop 写出、review copy 和 export actions。 |
| `x5crop.report` | report result、schema、sections、outputs。 |
| `x5crop.debug` | Debug Analysis canvas、panels、gap overlay、writer、status。 |
| `tools` | regression、build、unit tests 和开发辅助工具；不进入 runtime package。 |

#### 2.2 Runtime 子层

| 子层 | 职责 |
|---|---|
| `runtime.config` | 运行配置模型。 |
| `runtime.input_probe` | 输入 TIFF 探测和 layout 识别。 |
| `runtime.app` | 批处理启动、worker 调度和用户可见启动摘要。 |
| `runtime.workflow` | 单图处理主流程。 |
| `runtime.deskew` | deskew runtime 调度和 detail 组装。 |
| `runtime.analysis_reuse` | 匹配已有 Debug Analysis report 并复用已决策结果。 |
| `runtime.policy_context` | 当前 format / strip mode 的 runtime policy context。 |
| `runtime.profile` | runtime profiling / timing read model。 |

runtime 可以编排，但不拥有底层几何算法、候选算法或最终 decision contract。

#### 2.3 Policies 子层

| 子层 | 职责 |
|---|---|
| `policies.formats` | format-specific physical tolerance、content tolerance 和 search budget override。 |
| `policies.parameters` | 分组参数对象、registry、ownership validation 和 format override path mapping。 |
| `policies.runtime` | active `DetectionPolicy` 和 runtime subpolicy dataclass，包括 preprocess / physical / candidate / decision / output / diagnostics。 |
| `policies.assembly` | 从 format facts、mode posture、分组参数和受限 override 组装 runtime policy。 |
| `policies.decision` | final PASS / REVIEW decision contract，以及由 physical traits 推导的 final evidence policy。 |
| `policies.reporting` | policy detail serialization。 |
| `policies.registry` / `consistency` / `ids` | policy lookup、consistency smoke、policy id 和 schema id。 |

format 文件不承载算法开关；能力启用由 assembly 和 runtime policy 表达。
decision evidence policy 不使用 format-id override 表；format 名称只作为 `FormatSpec`
查询入口，实际差异来自 family、aspect、physical layout、separator width profile、
geometry support profile 等物理 trait。

#### 2.4 Detection 子层

| 子层 | 职责 |
|---|---|
| `detection.pipeline` | 候选流程 orchestration。 |
| `detection.modes` | special mode routing，例如 dual-lane split / merge 和 review-only。 |
| `detection.physical` | outer、separator、photo-size 等物理 proposal / evidence helper。 |
| `detection.guidance` | content-derived outer / separator hints 和 content-model proposal inputs。 |
| `detection.evidence` | content、separator、photo-width、frame topology、outer alignment、output overlap、read-only diagnostics 等证据。 |
| `detection.candidate.plan` | count / offset / source descriptors / execution budget；不 build、不 assessment、不 selection。 |
| `detection.candidate.proposal` | safety 等非物理候选入口。 |
| `detection.candidate.build` | outer + gaps + frames -> unscored Detection。 |
| `detection.candidate.assessment` | support scoring、base scoring、candidate gate、blockers、diagnostics、candidate confidence caps。 |
| `detection.candidate.extension` | corrected outer 和其它扩展候选的 reassessment。 |
| `detection.candidate.selection` | candidate competition 和 selected candidate。 |
| `detection.decision` | evidence summary、decision signals、decision gate、final reasons、contract applier。 |
| `detection.final` | 已决策结果的 output-adjacent finalization 编排。 |
| `detection.detail` | 稳定 detail read helper，供 report/debug/export/finalization 读取。 |

detection 中的层级方向是：proposal / evidence -> build -> assessment -> selection ->
decision -> finalization。低层不能反向读取高层 decision 语义。

#### 2.5 Foundation 子层

| 子层 | 职责 |
|---|---|
| `geometry` | 纯几何和 profile / search / fit 算法。 |
| `image` | 图像灰度、证据图、deskew、pixel transform 和 crop pixel 操作。 |
| `io` | TIFF I/O。 |
| `cache` | cache adapters，不拥有算法判断。 |

foundation 层不反向依赖 runtime、detection、report、debug、export 或 policy registry。
它们接收参数对象，不接收完整 runtime policy 或 `strip_mode` 字符串。
foundation helper 不隐式生成默认参数；调用方必须显式传入 geometry / image evidence
参数对象；默认值由 runtime policy assembly 明确提供。

#### 2.6 Output Surface 子层

| 子层 | 职责 |
|---|---|
| `output` | output surface、approved geometry adjustment、bleed / overlap helper 和输出几何 read model。 |
| `export` | TIFF crop、review copy 和文件动作。 |
| `report` | ProcessResult 到 JSONL / CSV / sections 的转换。 |
| `debug` | Debug Analysis 图像渲染和状态面板。 |

output surface 只消费 `ProcessResult`、`Detection.detail` 的稳定 read helper 和最终
decision summary。它们不生成候选，不评分，不决定 PASS / REVIEW。
approved geometry adjustment 属于 output-adjacent adjustment：它只在 decision 已 approved
且没有 final review reasons 后调整最终输出范围，不是 detection correction。

## English Guide

### 1. Runtime-Flow Architecture

Runtime flow describes how one job moves from entry to output:

```text
X5_Crop.py / launchers
  -> entry options
  -> runtime bootstrap
  -> workflow
  -> detection
  -> decision
  -> finalization
  -> export / report / debug
```

| Stage | Responsibility | Main location |
|---|---|---|
| Entry | Parse CLI / interactive input into entry options. | `X5_Crop.py`, `x5crop.entry`, launchers |
| Runtime bootstrap | Probe input, resolve layout, assemble runtime config and active policy. | `x5crop.runtime.config`, `input_probe`, `app`, `policy_context` |
| Workflow | Orchestrate one-image processing without owning detection policy. | `x5crop.runtime.workflow` |
| Preprocess | Read TIFF, build gray/evidence input, deskew, and prepare cache. | `x5crop.io`, `x5crop.image`, `x5crop.cache`, `x5crop.runtime.deskew` |
| Detection | Build candidates, evidence, assessment, extension, and selection. | `x5crop.detection` |
| Decision | Convert candidate evidence into final PASS / REVIEW, final reasons, and confidence caps. | `x5crop.detection.decision` |
| Finalization | Apply output-adjacent geometry, bleed, and read-only diagnostics attachment. | `x5crop.detection.final`, `x5crop.output` |
| Export | Write cropped TIFFs or review copies while preserving TIFF output boundaries. | `x5crop.export` |
| Report / Debug | Write reports, summaries, and Debug Analysis without feeding back into selection. | `x5crop.report`, `x5crop.debug` |

Entry code produces options only. Runtime binds options to input, layout, format,
strip mode, and active policy. Workflow runs the ordered process. Detection and
decision own candidate logic and final status. Finalization, export, report, and
debug consume the decision result.

Inside detection, the flow is:

```text
candidate plan
  -> physical proposal
  -> guidance
  -> candidate build
  -> candidate assessment
  -> candidate extension
  -> candidate selection
  -> decision
```

Candidate assessment explains candidate qualification. Final user-visible
reasons are produced by decision.
Workflow computes the output surface path early but creates the output directory
only when crop, review copy, debug, or report output is actually written.

### 2. Source-Layer Architecture

Source layering describes which package owns which knowledge.

#### 2.1 Top-Level Layers

| Layer | Responsibility |
|---|---|
| `x5crop.entry` | User entry and option parsing. |
| `x5crop.runtime` | Runtime config, input probing, workflow, deskew runtime, policy context, analysis reuse. |
| `x5crop.formats` | Format identity, family, count, aspect, and physical facts. |
| `x5crop.policies` | Runtime policy, parameter ownership, policy assembly, decision contract, policy reporting. |
| `x5crop.cache` | Analysis / separator cache adapters. |
| `x5crop.geometry` | Pure geometry, separator profiles, edge pairs, frame fit, layout, outer boxes. |
| `x5crop.image` | Gray images, deskew, evidence images, pixel transforms, crop pixels. |
| `x5crop.io` | TIFF I/O. |
| `x5crop.detection` | Candidates, evidence, assessment, selection, decision, finalization. |
| `x5crop.output` | Output-adjacent bleed / overlap read model and output geometry helpers. |
| `x5crop.export` | Crop writing, review copies, and export actions. |
| `x5crop.report` | Report result building, schema, sections, outputs. |
| `x5crop.debug` | Debug Analysis canvas, panels, gap overlay, writer, status. |
| `tools` | Regression, build, unit tests, and developer utilities outside the runtime package. |

#### 2.2 Runtime Sublayers

`runtime.config` owns runtime config; `runtime.input_probe` owns TIFF probing and
layout; `runtime.app` owns batch startup and workers; `runtime.workflow` owns the
single-image process; `runtime.deskew` owns deskew runtime detail;
`runtime.analysis_reuse` owns compatible report reuse; `runtime.policy_context`
owns active policy context.

Runtime orchestrates but does not own geometry algorithms, candidate algorithms,
or the final decision contract.

#### 2.3 Policy Sublayers

`policies.formats` owns constrained format presets. `policies.parameters` owns
grouped parameter objects, ownership validation, and format override path
mapping. `policies.runtime` owns active runtime policy dataclasses, including
preprocess / physical / candidate / decision / output / diagnostics subpolicies.
`policies.assembly` builds active policy from format facts, mode posture,
grouped parameters, and constrained overrides. `policies.decision` owns the
final decision contract and derives final evidence policy from physical traits.

Format files do not carry algorithm switches; capability enablement belongs to
assembly and runtime policy.
Decision evidence policy does not use format-id override tables. A format name is
only a `FormatSpec` lookup key; behavior differences come from physical traits
such as family, aspect, physical layout, separator width profile, and geometry
support profile.

#### 2.4 Detection Sublayers

| Sublayer | Responsibility |
|---|---|
| `detection.pipeline` | Candidate flow orchestration. |
| `detection.modes` | Special mode routing, such as dual-lane split / merge and review-only. |
| `detection.physical` | Physical outer, separator, and photo-size proposal / evidence helpers. |
| `detection.guidance` | Content-derived outer / separator hints and content-model proposal inputs. |
| `detection.evidence` | Content, separator, photo-width, frame topology, outer alignment, output overlap, read-only diagnostics. |
| `detection.candidate.plan` | Count / offset / source descriptors / execution budget; no build, assessment, or selection. |
| `detection.candidate.proposal` | Non-physical candidate entries such as safety. |
| `detection.candidate.build` | outer + gaps + frames -> unscored Detection. |
| `detection.candidate.assessment` | Support scoring, base scoring, candidate gate, blockers, diagnostics, candidate confidence caps. |
| `detection.candidate.extension` | Reassessment of corrected outer and other extension candidates. |
| `detection.candidate.selection` | Candidate competition and selected candidate. |
| `detection.decision` | Evidence summary, decision signals, decision gate, final reasons, contract applier. |
| `detection.final` | Output-adjacent finalization for an already-decided result. |
| `detection.detail` | Stable detail readers for report/debug/export/finalization. |

The direction is proposal / evidence -> build -> assessment -> selection ->
decision -> finalization. Lower layers must not read higher-level decision
semantics.

#### 2.5 Foundation Sublayers

`geometry`, `image`, `io`, and `cache` are foundation surfaces. They receive
plain parameters and return facts or transformed data. They must not depend back
on runtime, detection, report, debug, export, or the policy registry. Foundation
helpers do not create implicit default parameters; callers pass explicit
parameter objects supplied by runtime policy assembly.

#### 2.6 Output Surfaces

`output`, `export`, `report`, and `debug` consume stable results. They do not
generate candidates, score candidates, or decide PASS / REVIEW. Approved geometry
adjustment belongs here as an output-adjacent range adjustment after decision,
not as detection correction.
