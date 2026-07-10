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
| Runtime bootstrap | 探测输入、解析 layout、装配 runtime config 和 active policy bundle。 | `x5crop.run_config`, `x5crop.runtime.input_probe`, `runtime.app`, `policies.runtime.bundle` |
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
- active policy bundle 在 runtime 边界一次性解析当前 format/mode，以及 dual-lane 所需的
  lane full policy。每个 `DetectionPolicy` 直接持有唯一 `FormatPhysicalSpec`；bundle 不再
  复制 format identity，detection 也不能回查 policy 或 format registry。

入口层不读取图像内容，不做候选判断，不决定 PASS / REVIEW。

#### 1.3 Workflow 到 Detection

`workflow` 是编排层：

```text
read TIFF
  -> build base gray / scan calibration / evidence input
  -> deskew when enabled
  -> reuse compatible analysis when available
  -> run detection
  -> apply decision
  -> finalize
  -> export / report / debug
```

workflow 可以决定是否复用已匹配的 analysis report，但 cache record 必须同时匹配 current
schema、输入/config identity 和 active policy fingerprint。复用结果不能被解释成新的检测策略。
检测策略必须来自 active runtime policy，并通过 detection / decision 层执行。
workflow 只计算输出 surface 路径；只有 crop、review copy、debug 或 report 真的写出时才创建输出目录。
workflow 从 TIFF resolution metadata 建立 `ScanCalibration` detail；该 detail 只进入
report / diagnostics 和物理长度解释，不反向放宽 candidate gate 或 final decision。

#### 1.4 Detection 到 Decision

detection 内部按候选生命周期流动：

```text
candidate plan
  -> count hypothesis evaluation
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
| Candidate plan | 生成有类型的 count hypotheses，并声明 offset、candidate source descriptors 和 execution budget。 |
| Candidate build | 将 outer、separator gaps 和 frame geometry 组装成未评分 `DetectionCandidate`。 |
| Candidate execution | 执行 source descriptor：调用 proposal、build geometry、补充 geometry evidence，再交给 assessment。 |
| Candidate assessment | 计算 candidate support、candidate gate、candidate blockers、diagnostics 和 confidence caps。 |
| Candidate extension | 对 corrected outer、content-guided separator 等候选重新 build / reassess。 |
| Candidate selection | 在已评估候选之间选择 selected candidate，并记录 count selection 与 competition detail。 |
| Decision | 将 selected `DetectionCandidate` 转成唯一拥有 status / final reasons 的 `FinalDetection`。 |

candidate assessment 只产生候选级解释；最终用户可见原因只由 decision 产生。
CandidateGate 只能阻断或限制候选，不能把分数反向抬高；separator 宽度变化属于 evidence
detail，不是独立 blocker。
用户入口 `strip_mode` 仍表示照片是否铺满片夹；detection 内部另行记录
`strip_completeness` 和 `holder_occupancy`。因此 XPAN / 120-66 可以在 partial
入口下被解释为 `complete_underfilled_strip`：完整张数存在，但片夹前后仍有 holder slack。

#### 1.5 Decision 到 Output

decision 之后的层级只消费结果：

- `detection.final` 只编排已决策结果的 output-adjacent finalization。
- `x5crop.output` 提供 output surface、`OutputProtectionPlan`、approved geometry adjustment 和 bleed 执行。
- `x5crop.export` 写自动裁切 TIFF 或 `needs_review/` copy。
- `x5crop.report` 写 canonical JSONL record 和 CSV 摘要。
- `x5crop.debug` 生成 Debug Analysis 面板。

这些层级不能重新判断 PASS / REVIEW，也不能根据 confidence 自行推导最终状态。
JSONL 每行就是 current `detection_report` record；不再包裹旧 ProcessResult 字段或
嵌套 `report_schema`。

### 2. 源码分层架构

源码分层描述每个 package 拥有什么知识，以及它不能拥有的东西。

#### 2.1 顶层分层

| 层级 | 主要职责 |
|---|---|
| `x5crop.entry` | 用户入口和选项解析。 |
| `x5crop.run_config` | 唯一运行配置模型。 |
| `x5crop.runtime` | 输入探测、workflow、deskew runtime、policy context、analysis reuse。 |
| `x5crop.formats` | format identity、family、count、frame size mm、derived aspect、lane composition 和物理 facts。 |
| `x5crop.units` | `ScanCalibration` 和 `PhysicalLength` 单位模型。 |
| `x5crop.policies` | runtime policy、parameter ownership、policy assembly、decision contract、policy reporting。 |
| `x5crop.cache` | analysis / separator cache adapters。 |
| `x5crop.geometry` | box、gap、separator profile、edge pair、frame fit、layout、outer box 等纯几何能力。 |
| `x5crop.image` | gray、deskew、evidence image、pixel transforms 和 crop pixels。 |
| `x5crop.io` | TIFF 读取和写入相关 I/O。 |
| `x5crop.detection` | 候选、证据、assessment、selection、decision、finalization。 |
| `x5crop.output` | output protection plan、bleed 执行、output surface 和输出几何 helper。 |
| `x5crop.export` | crop 写出、review copy 和 export actions。 |
| `x5crop.report` | report result / canonical record 构建、read models、outputs 和 schema validation。 |
| `x5crop.debug` | Debug Analysis canvas、panels、gap overlay、writer、status。 |
| `tools` | regression、build、unit tests 和开发辅助工具；不进入 runtime package。 |

#### 2.2 Runtime 子层

| 子层 | 职责 |
|---|---|
| `x5crop.run_config` | 运行配置模型。 |
| `runtime.input_probe` | 输入 TIFF 探测和 layout 识别。 |
| `runtime.app` | 批处理启动、worker 调度和用户可见启动摘要。 |
| `runtime.workflow` | 单图处理主流程。 |
| `runtime.deskew` | deskew runtime 调度和 detail 组装。 |
| `runtime.analysis_reuse` | 匹配 current schema、输入/config identity 和 policy fingerprint 后复用已决策输出几何。 |

runtime 可以编排，但不拥有底层几何算法、候选算法或最终 decision contract。

#### 2.3 Policies 子层

| 子层 | 职责 |
|---|---|
| `policies.parameters` | canonical 分组参数 dataclass 和 central typed parameter factory。 |
| `policies.runtime` | active `DetectionPolicy` 及只表达派生 eligibility / composition 的复合 subpolicy。 |
| `policies.assembly` | 从 format facts、mode posture 和分组参数组装 runtime policy。 |
| `policies.decision` | final PASS / REVIEW decision contract，以及由 physical traits 推导的 final evidence policy。 |
| `policies.reporting` | policy detail 的只读 serialization。 |
| `policies.registry` / `consistency` / `identity` | policy lookup、consistency smoke 和 policy identity。 |
| `report.identity` | current report schema identity；不属于 runtime policy。 |

`FormatParameters` 只是装配入口，内部固定分为 `preprocess`、`content`、`outer`、
`separator`、`candidate`、`decision`、`output` 和 `diagnostics` 参数组。assembly 只能从这些
明确分组读取参数，不能恢复扁平 property view、string override path 或 per-format builder。
`FormatParameters` 不保存 format 名称；assembly 接收已解析 `FormatPhysicalSpec`，不能把它
退化成字符串后再次查询 format registry。
`DetectionPolicy` 直接聚合 canonical parameter objects 和真正需要组合语义的 runtime
subpolicies；同一组参数不得再复制成形状相同的 runtime dataclass。Report schema identity
只由 `x5crop.report.identity` 拥有，不能进入 policy 或 policy detail。

format 文件不承载算法开关。`FormatPhysicalSpec.frame_geometry_profile` 是从 family、frame
aspect、count 和 physical layout 派生的唯一几何分类；policy assembly 消费该物理分类，
reporting 只读取并描述它。
decision evidence policy 不使用 format-id override 表；format 名称只作为 `FormatPhysicalSpec`
查询入口，实际差异来自 family、frame size mm 派生的 aspect、physical layout、
complete-underfilled strip trait 等物理事实。Aspect 是底片物理尺寸 fact，不是经验 tuning。
XPAN 和 120-66 的 `complete_strip_can_be_underfilled` 是 format physical trait：
它说明完整胶片可能不铺满片夹，不代表这些 format 拥有独立算法分支。

#### 2.4 Detection 子层

| 子层 | 职责 |
|---|---|
| `detection.pipeline` | 候选流程 orchestration。 |
| `detection.modes` | special mode routing，例如 dual-lane split / merge 和 review-only。 |
| `detection.physical` | outer、separator、photo-size 等物理 proposal / evidence helper。 |
| `detection.guidance` | content-derived outer / separator hints 和 content-model proposal inputs。 |
| `detection.evidence` | content、separator、photo-width、frame topology、strip completeness、holder occupancy、outer alignment、exposure overlap、read-only diagnostics 等证据。 |
| `detection.candidate.plan` | 有类型的 count hypotheses、offset、source descriptors 和 execution budget；不 build、不 assessment、不 selection。 |
| `detection.candidate.proposal` | outer 等 candidate-level proposal 执行入口。 |
| `detection.candidate.build` | outer + gaps + frames -> unscored `DetectionCandidate`。 |
| `detection.candidate.execution` | 将 source descriptor / proposal 输出显式串成 build -> evidence enrichment -> assessment。 |
| `detection.candidate.assessment` | count hypothesis evaluation、support scoring、base scoring、candidate gate、blockers、diagnostics、candidate confidence caps。 |
| `detection.candidate.extension` | corrected outer 和其它扩展候选的 reassessment。 |
| `detection.candidate.selection` | candidate competition 和 selected candidate。 |
| `detection.decision` | evidence summary、decision signals、decision gate、final reasons、contract applier。 |
| `detection.final` | 已决策结果的 output-adjacent finalization 编排。 |
| `detection.detail` | 稳定 detail read helper，供 report/debug/export/finalization 读取。 |

detection 中的层级方向是：plan -> proposal / guidance -> build -> evidence enrichment -> assessment -> selection ->
decision -> finalization。低层不能反向读取高层 decision 语义。
`DetectionCandidate` 不含 status 或 final reasons。DecisionGate 是唯一
`DetectionCandidate -> FinalDetection` 转换点；finalization 只接收并返回
`FinalDetection`，report / debug / export 也不能接收未决候选。
auto count 不在 runtime config 中保存伪默认 count：`requested_count=None` 明确表示自动模式。
`CountHypothesisPlan` 按物理允许范围从大到小生成假设，execution 对每个假设完整 build / assess，
selection 记录最终 count 及其证据；XPAN / 120-66 的 partial auto 可以包含 nominal count。
`exposure_overlap_evidence` 只测量 model boundary 上的连续影像和最宽 overlap band，不知道
bleed capacity 或 REVIEW。`x5crop.output` 根据该 evidence 生成唯一 `OutputProtectionPlan`；
DecisionGate 只阻断不可执行的 plan，finalization 严格执行同一个 plan。所有 format/mode
共享这项物理能力，不再由 format trait 或恒真 capability 开关控制。
`outer_alignment` 是 evidence policy；`content_containment` 是 correction policy。
前者只测量 undercrop / overcontainment，后者只基于已测得 evidence 提出 corrected outer。

#### 2.5 Foundation 子层

| 子层 | 职责 |
|---|---|
| `geometry` | 纯几何和 profile / search / fit 算法。 |
| `image` | 图像灰度、证据图、deskew、pixel transform 和 crop pixel 操作。 |
| `io` | TIFF I/O。 |
| `cache` | cache adapters，不拥有算法判断。 |
| `units` | 物理长度、像素核和 scan calibration 的纯数据模型。 |

foundation 层不反向依赖 runtime、detection、report、debug、export 或 policy registry。
它们接收参数对象，不接收完整 runtime policy 或 `strip_mode` 字符串。
foundation helper 不隐式生成默认参数；调用方必须显式传入 geometry / image evidence
参数对象；默认值由 runtime policy assembly 明确提供。
frame fitting 也遵守该契约：调用方必须显式传入 frame-fit parameters；geometry model
始终提供基础 frame，edge evidence 在可用时进一步拟合，底层不再根据 optional config 猜测行为。
单位规则固定为：物理长度优先由可信 `ScanCalibration` 的 mm 转 px；缺少可信 calibration
时使用 frame / pitch reference ratio；最后才用 min/max px clamp。content coverage、
cross-axis continuity、photo-width CV、aspect error、confidence 等仍是 normalized evidence，
不能伪装成物理长度。

#### 2.6 Output Surface 子层

| 子层 | 职责 |
|---|---|
| `output` | output surface、approved geometry adjustment、bleed / overlap helper 和输出几何 read model。 |
| `export` | TIFF crop、review copy 和文件动作。 |
| `report` | ProcessResult 到 canonical JSONL record 和 CSV 摘要的转换。 |
| `debug` | Debug Analysis 图像渲染和状态面板。 |

output 只消费 final domain types 和 output evidence；report / debug 只通过稳定 detail reader
解释最终结果。它们不生成候选，不评分，不决定 PASS / REVIEW。
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
| Runtime bootstrap | Probe input, resolve layout, assemble runtime config and active policy bundle. | `x5crop.run_config`, `x5crop.runtime.input_probe`, `runtime.app`, `policies.runtime.bundle` |
| Workflow | Orchestrate one-image processing without owning detection policy. | `x5crop.runtime.workflow` |
| Preprocess | Read TIFF, build gray/evidence input, deskew, and prepare cache. | `x5crop.io`, `x5crop.image`, `x5crop.cache`, `x5crop.runtime.deskew` |
| Detection | Build candidates, evidence, assessment, extension, and selection. | `x5crop.detection` |
| Decision | Convert candidate evidence into final PASS / REVIEW, final reasons, and confidence caps. | `x5crop.detection.decision` |
| Finalization | Apply output-adjacent geometry, bleed, and read-only diagnostics attachment. | `x5crop.detection.final`, `x5crop.output` |
| Export | Write cropped TIFFs or review copies while preserving TIFF output boundaries. | `x5crop.export` |
| Report / Debug | Write reports, summaries, and Debug Analysis without feeding back into selection. | `x5crop.report`, `x5crop.debug` |

Entry code produces options only. Runtime binds options to input, layout, format,
strip mode, and active policy bundle. Workflow runs the ordered process. Detection and
decision own candidate logic and final status. Finalization, export, report, and
debug consume the decision result. Workflow also derives `ScanCalibration` from
TIFF resolution metadata; calibration is diagnostic/unit evidence and does not
loosen candidate gates or final decision.

Inside detection, the flow is:

```text
candidate plan
  -> count hypothesis evaluation
  -> physical proposal
  -> guidance
  -> candidate build
  -> candidate assessment
  -> candidate extension
  -> candidate selection
  -> decision
```

Candidate assessment explains candidate qualification. Final user-visible
reasons are produced by decision. CandidateGate may block or cap a candidate,
but it cannot raise its score. Separator-width variation is evidence detail,
not a standalone blocker.
User-facing `strip_mode` still means whether the image fills the holder.
Detection records separate `strip_completeness` and `holder_occupancy` evidence,
so XPAN / 120-66 may be reported as `complete_underfilled_strip`: the default
frame sequence is complete, but the holder still has leading/trailing slack.
Workflow computes the output surface path early but creates the output directory
only when crop, review copy, debug, or report output is actually written.
Finalization builds output geometry on a cloned detection result; it records
`decision_geometry` and `output_geometry` separately instead of mutating the
decision-stage geometry in place.

### 2. Source-Layer Architecture

Source layering describes which package owns which knowledge.

#### 2.1 Top-Level Layers

| Layer | Responsibility |
|---|---|
| `x5crop.entry` | User entry and option parsing. |
| `x5crop.run_config` | Canonical runtime configuration model. |
| `x5crop.runtime` | Input probing, workflow, deskew runtime, and analysis reuse. |
| `x5crop.formats` | Format identity, family, count, frame size mm, derived aspect, and physical facts. |
| `x5crop.units` | `ScanCalibration` and `PhysicalLength` unit models. |
| `x5crop.policies` | Runtime policy, parameter ownership, policy assembly, decision contract, policy reporting. |
| `x5crop.cache` | Analysis / separator cache adapters. |
| `x5crop.geometry` | Pure geometry, separator profiles, edge pairs, frame fit, layout, outer boxes. |
| `x5crop.image` | Gray images, deskew, evidence images, pixel transforms, crop pixels. |
| `x5crop.io` | TIFF I/O. |
| `x5crop.detection` | Candidates, evidence, assessment, selection, decision, finalization. |
| `x5crop.output` | Output protection planning, bleed execution, output surfaces, and output geometry helpers. |
| `x5crop.export` | Crop writing, review copies, and export actions. |
| `x5crop.report` | Report result/canonical-record building, read models, outputs, and schema validation. |
| `x5crop.debug` | Debug Analysis canvas, panels, gap overlay, writer, status. |
| `tools` | Regression, build, unit tests, and developer utilities outside the runtime package. |

#### 2.2 Runtime Sublayers

`x5crop.run_config` owns runtime config; `runtime.input_probe` owns TIFF probing and
layout; `runtime.app` owns batch startup and workers; `runtime.workflow` owns the
single-image process; `runtime.deskew` owns deskew runtime detail;
`runtime.analysis_reuse` owns reuse after current schema, input/config identity,
and policy fingerprint all match. Runtime creates a
`DetectionPolicyBundle` at the boundary and passes explicit policies downward.
Each policy owns one resolved `FormatPhysicalSpec`; the bundle does not maintain
a second format-identity collection.

Runtime orchestrates but does not own geometry algorithms, candidate algorithms,
or the final decision contract.

#### 2.3 Policy Sublayers

`policies.parameters` owns canonical grouped parameter dataclasses and the central typed
parameter factory. `policies.runtime` owns `DetectionPolicy` plus composite
subpolicies that express derived eligibility or composition.
`policies.assembly` builds active policy from format facts, mode posture, and
grouped parameters. `policies.decision` owns the
final decision contract and derives final evidence policy from physical traits.

`FormatParameters` is only the assembly entry. Its contents are grouped as
`preprocess`, `content`, `outer`, `separator`, `candidate`, `decision`, `output`,
and `diagnostics`; assembly reads those explicit groups and must not restore flat
property views, string override paths, or per-format builders.
`FormatParameters` does not store a format name. Assembly receives a resolved
`FormatPhysicalSpec` and may not degrade it to a string for another registry lookup.
`DetectionPolicy` directly aggregates canonical parameter objects and only those
runtime subpolicies that add real composition semantics; it must not duplicate the
same parameters into shape-identical runtime dataclasses. Current report schema
identity belongs solely to `x5crop.report.identity`, never to policy or policy detail.

Format files do not carry algorithm switches. The canonical
`FormatPhysicalSpec.frame_geometry_profile` is derived from family, frame aspect,
count, and physical layout. Policy assembly consumes that physical
classification; reporting only reads and describes it.
Decision evidence policy does not use format-id override tables. A format name is
only a `FormatPhysicalSpec` lookup key; behavior differences come from physical facts
such as family, frame-size-mm-derived aspect, physical layout, and
complete-underfilled strip traits. Aspect is a film-frame physical fact, not
empirical tuning.
XPAN and 120-66 expose `complete_strip_can_be_underfilled` as a physical trait:
it says a complete strip may not fill the holder, not that those formats own
separate algorithms.
Dual-lane composition is also a physical format fact: `FormatPhysicalSpec`
declares the lane count and lane format. Detector policy does not hide a default
`2 x 135` composition.

#### 2.4 Detection Sublayers

| Sublayer | Responsibility |
|---|---|
| `detection.pipeline` | Candidate flow orchestration. |
| `detection.modes` | Special mode routing, such as dual-lane split / merge and review-only. |
| `detection.physical` | Physical outer, separator, and photo-size proposal / evidence helpers. |
| `detection.guidance` | Content-derived outer / separator hints and content-model proposal inputs. |
| `detection.evidence` | Content, separator, photo-width, frame topology, strip completeness, holder occupancy, outer alignment, exposure overlap, and read-only diagnostics. |
| `detection.candidate.plan` | Typed count hypotheses, offsets, source descriptors, and execution budget; no build, assessment, or selection. |
| `detection.candidate.proposal` | Candidate-level outer proposal execution entries. |
| `detection.candidate.build` | outer + gaps + frames -> unscored `DetectionCandidate`. |
| `detection.candidate.execution` | Explicit source descriptor / proposal -> build -> evidence enrichment -> assessment orchestration. |
| `detection.candidate.assessment` | Count-hypothesis evaluation, support scoring, base scoring, candidate gate, blockers, diagnostics, and candidate confidence caps. |
| `detection.candidate.extension` | Reassessment of corrected outer and other extension candidates. |
| `detection.candidate.selection` | Candidate competition and selected candidate. |
| `detection.decision` | Evidence summary, decision signals, decision gate, final reasons, contract applier. |
| `detection.final` | Output-adjacent finalization for an already-decided result. |
| `detection.detail` | Stable detail readers for report/debug/export/finalization. |

The direction is plan -> proposal / guidance -> build -> evidence enrichment -> assessment -> selection ->
decision -> finalization. Lower layers must not read higher-level decision
semantics.
`DetectionCandidate` has no status or final reasons. DecisionGate is the only
`DetectionCandidate -> FinalDetection` conversion point. Finalization only
accepts and returns `FinalDetection`, and report / debug / export cannot consume
an undecided candidate.
Auto count does not store a placeholder default count in runtime config:
`requested_count=None` explicitly means automatic mode. `CountHypothesisPlan`
orders physically permitted hypotheses from largest to smallest, execution fully
builds and assesses each hypothesis, and selection records the chosen count and
its evidence. XPAN and 120-66 partial auto may include the nominal count.
`exposure_overlap_evidence` only measures continuous image content at model
boundaries and the widest overlap band; it does not know bleed capacity or REVIEW.
`x5crop.output` derives one `OutputProtectionPlan` from that evidence. DecisionGate
blocks only an infeasible plan, and finalization executes that same plan. This
physical capability is shared by every format and mode rather than enabled by a
format trait or an always-true capability switch.
`outer_alignment` is evidence policy; `content_containment` is correction policy.
The former only measures undercrop / overcontainment, and the latter only
proposes corrected outer boxes from already-measured evidence.

#### 2.5 Foundation Sublayers

`geometry`, `image`, `io`, `cache`, and `units` are foundation surfaces. They receive
plain parameters and return facts or transformed data. They must not depend back
on runtime, detection, report, debug, export, or the policy registry. Foundation
helpers do not create implicit default parameters; callers pass explicit
parameter objects supplied by runtime policy assembly.
Frame fitting follows the same contract: callers pass frame-fit parameters;
the geometry model always supplies the baseline frames and edge evidence refines
them when available. Geometry does not infer behavior from an optional config.
Physical lengths resolve by trusted `ScanCalibration` first, frame / pitch
reference ratio second, and min/max pixel clamp last. Content coverage,
cross-axis continuity, photo-width CV, aspect error, and confidence remain
normalized evidence, not physical length.

#### 2.6 Output Surfaces

`output`, `export`, `report`, and `debug` consume stable results. They do not
generate candidates, score candidates, or decide PASS / REVIEW. Approved geometry
adjustment belongs here as an output-adjacent range adjustment after decision,
not as detection correction.
Each JSONL line is the current `detection_report` record itself; it no longer wraps
legacy ProcessResult fields or a nested `report_schema`.
