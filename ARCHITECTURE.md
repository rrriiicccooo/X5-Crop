# X5 Crop 架构说明 / Architecture Guide

本文件只描述当前 V4.9 的运行流程和源码分层。用户操作见 `README.md`，版本变化见
`CHANGELOG.md`，协作与验收规则见 `AGENTS.md`。

This document describes only the current V4.9 runtime flow and source layers.
User instructions live in `README.md`, version history in `CHANGELOG.md`, and
repository rules in `AGENTS.md`.

## 1. 运行流程 / Runtime Flow

```text
entry / launchers
  -> runtime bootstrap and policy resolution
  -> TIFF read, layout normalization, calibration, preprocess
  -> DetectionContext
  -> physical observations
  -> count and placement hypotheses
  -> CandidateGeometry
  -> CandidateEvidence
  -> CandidateAssessment + CandidateGate
  -> GeometryResolution
  -> SelectionResult
  -> output protection
  -> DecisionGate
  -> FinalDetection
  -> output finalization
  -> export / report / debug
```

### 1.1 顶层阶段 / Top-Level Stages

| 阶段 / Stage | 职责 / Responsibility | Owner |
|---|---|---|
| Entry | 解析 CLI 或交互输入，不读取图像、不做检测。 Parse user input without image or detection authority. | `X5_Crop.py`, `x5crop.entry` |
| Runtime | 探测输入、解析 layout、装配唯一 runtime policy、编排单图或 worker。 Probe inputs, resolve layout and policy, orchestrate work. | `x5crop.runtime` |
| Preprocess | 读取 TIFF，生成基础灰度和证据灰度，执行 deskew，建立 calibration 与 measurement cache。 Read TIFF, build gray evidence, deskew, calibration, and measurement cache. | `x5crop.io`, `image`, `cache`, `units` |
| Detection | 从物理观测生成候选，测量证据，评估并选择几何。 Build, assess, and resolve geometry from physical observations. | `x5crop.detection` |
| Decision | 将已选几何和输出保护转成最终 PASS/REVIEW。 Convert selected geometry and output protection into final status. | `detection.decision` |
| Finalization | 只调整已决策输出几何，不生成候选或改写决定。 Adjust output geometry without candidate or decision authority. | `detection.final`, `x5crop.output` |
| Export | 写 crop 或 review copy，并保持 TIFF 质量与 metadata。 Write crops or review copies while preserving TIFF properties. | `x5crop.export` |
| Report / Debug | 序列化 current schema，生成三联 Debug Analysis，只解释结果。 Serialize the current schema and render the three-panel analysis without affecting detection. | `x5crop.report`, `x5crop.debug` |

### 1.2 Runtime 边界 / Runtime Boundary

Runtime 是 format、mode 和 policy 的唯一解析边界。它创建 `DetectionContext`，其中包含：

- 原始方向灰度图和统一 horizontal work-space measurement cache。
- `DetectionRequest`：layout、用户选择的 `full/partial`、显式或 auto count。
- `FormatPhysicalSpec`：frame mm、aspect、允许 count、lane 和 occupancy 物理事实。
- 已解析的 detection policy/subpolicies。
- TIFF resolution 形成的可信或不可用 `ScanCalibration`。

Runtime is the only format, mode, and policy resolution boundary. Lower layers
receive resolved specs and explicit parameter objects; they never query a
registry or invent defaults.

输出路径先被计算，只有真的写 crop、review copy、report 或 debug 时才创建目录。Current-schema
cache reuse 必须匹配输入、配置、policy fingerprint 和 schema revision；不匹配时重新检测。

Output paths are calculated without side effects. Directories are created only
when an artifact is written. Analysis reuse accepts only an exact current-schema
match; otherwise the image is detected again.

### 1.3 物理观测 / Physical Observations

检测开始时不直接猜最终 crop，而是测量可复用的物理事实：

- `HolderSpan`：片夹可用范围。
- `FilmSpan`：胶片 frame sequence 的实际范围，与 holder 不是同一概念。
- `SeparatorBandObservation`：band start/end/center、tonal signal、横跨短轴连续性和 provenance。
- 每边独立的 white-holder、tonal-transition、texture-transition、mixed-boundary outer proposal。
- content region、holder texture 和 frame-boundary contact，只用于 guidance、遗漏内容反证和内容保护。

Detection measures reusable physical facts before it proposes a final crop.
Content may guide placement and disprove unsafe geometry, but it does not define
an exact separator cut or become a boundary oracle.

一维 separator profile 只能发现 band 候选。只有横跨短轴连续性确认后的 observation 才能计入
hard separator sequence、photo-size measurement 或 geometry proof。Separator 宽度和片距可以变化；
照片本体尺寸稳定性使用相邻 separator band 边缘之间的照片宽度，不使用 center pitch。

A one-dimensional profile only proposes separator bands. A band becomes hard
physical support only after cross-axis continuity is confirmed. Separator width
and spacing may vary; photo-size evidence uses photo intervals between measured
band edges, not separator-center pitch.

### 1.4 Count 与 Placement / Count and Placement

Partial auto count 始终按该 format 允许的 count 从大到小评估：

1. Count-independent hard separator observations 只提供 placement。
2. Placement 使用 separator band 边缘和物理 frame 宽度计算 film span，不使用 holder 等分 pitch。
3. Standard observation 不足时才测 observed-width bands；content 只提供定位提示。
4. `135/half/645/67` partial auto 不包含 nominal full count。
5. XPAN 和 120-66 因物理 trait 可包含 nominal count，用来表达完整但未铺满片夹。
6. `count=1` 必须有两侧独立 boundary evidence，或可信 calibration 加 frame-size corroboration。

Partial auto count evaluates allowed counts from largest to smallest. Separator
observations optimize placement but never reorder smaller counts ahead of larger
ones. If no count is physically resolved, selection favors complete coverage and
the fewest physical contradictions, then returns REVIEW when required.

用户入口中的 `full/partial` 仍表示图像是否铺满片夹。内部另外记录：

- `strip_completeness`：frame sequence 是否达到 nominal count。
- `holder_occupancy`：film span 是否铺满 holder，是否存在 leading/trailing slack。
- `complete_underfilled_strip`：仅 XPAN/120-66 可成立，且不能豁免任何 undercrop evidence。

### 1.5 Candidate 数据流 / Candidate Data Flow

每个 hypothesis 依次形成不可变 typed result：

```text
physical proposal
  -> CandidateGeometry
  -> CandidateEvidence
  -> CandidateAssessment
  -> CandidateGate
```

`CandidateEvidence` 包含：frame topology、frame coverage、separator sequence、separator
continuity、frame dimensions、content preservation、holder texture、outer alignment、holder
occupancy、partial edge safety 和 evidence independence。

Outer correction 只能产生新的 `CandidateGeometry`。任何 corrected geometry 都必须重新 build
全部 evidence 并重新 assessment；outer 不能评分、PASS 或 REVIEW。Content correction 只能向外扩张
以保护内容，不能按 content 收缩 film span。

Outer correction only proposes a new geometry. Every corrected geometry is fully
rebuilt and reassessed. Outer code cannot score or decide status, and content may
only expand a span to preserve content.

### 1.6 CandidateGate 与 GeometryResolution

`CandidateGate` 只回答候选是否具备自动处理资格：

- frame topology 没有错序、交叉、无效 extent 或 count mismatch。
- 没有可靠证据确认真实内容被裁断。
- photo dimensions 没有被可信 measurement 明确反证。
- boundary proof 没有循环依赖。
- 至少一条独立 proof path 成立：`separator_led`、`geometry_led`、
  `partial_occupancy_led` 或 dual-lane `mode_composition`。

`GeometryResolution` 是唯一 early-stop 输入。它独立于 CandidateGate 和 confidence，只在 count、
placement、boundaries、coverage、较大 count 和替代几何都已经物理解决时成立。单个候选只能称为
`uncontested`；多个等价候选才称为 `agreed`；实质不同且接近的几何为 `disagreed`。

`GeometryResolution` alone controls early-stop. CandidateGate determines automatic
eligibility, while confidence only ranks candidates within the same physical state
and remains explanatory data.

### 1.7 Selection、Decision 与 Output

Selection 按物理 proof、自动处理资格、coverage、矛盾数量、count 和 confidence 排序，并按
frame-relative tolerance 聚类几何。只有实质不同的几何簇接近时，DecisionGate 才收到 geometry
disagreement。

DecisionGate 是最终 status 和 `final_review_reasons` 的唯一 owner。它只消费：

- CandidateGate 的具体失败项。
- automatic-processing eligibility。
- selection geometry consensus。
- output content protection。
- deskew/transform geometry integrity。

DecisionGate does not rebuild evidence, generate candidates, or apply confidence
thresholds. The same physical fact is judged once and projected to one final reason.

叠片 measurement 属于 detection evidence；可执行 bleed 属于 output protection。Bleed 足以覆盖时
可以自动输出，只有保护能力不足时才由 DecisionGate 阻断。Finalization 严格执行同一个
`OutputProtectionPlan`，并可做 output-adjacent approved geometry adjustment；两者都不能改变
PASS/REVIEW。

### 1.8 Special Modes

- `135-dual/full` 先测量中心附近 holder gutter，off-center divider 可以成为主 proposal；正中二分
  只是低优先级 safety proposal。每条 lane 进入普通 strip 的完整 typed pipeline，最后检查 lane
  consistency。
- `135-dual/partial` 保持 review-only。
- Deskew 输出 typed `TransformGeometryEvidence`，DecisionGate 只消费该结果。

## 2. 源码分层 / Source Layers

### 2.1 顶层 package / Top-Level Packages

| 层级 / Layer | 唯一职责 / Canonical Responsibility |
|---|---|
| `x5crop.entry` | CLI 和 interactive 输入。 CLI and interactive input. |
| `x5crop.runtime` | Bootstrap、worker、workflow、deskew orchestration、current-schema reuse。 |
| `x5crop.formats` | Format identity 与真实物理规格。 Format identity and physical facts. |
| `x5crop.policies` | Sample-tuned 参数、runtime subpolicy 和 assembly；不拥有物理事实或 report schema。 |
| `x5crop.units` | `ScanCalibration` 与 `PhysicalLength` 单位解析。 |
| `x5crop.cache` | 只缓存 exact、count/offset-independent measurements。 |
| `x5crop.geometry` | Box、profile、separator search、edge、frame 等纯算法。 |
| `x5crop.image` | Gray、deskew、pixel transform 和 crop pixels。 |
| `x5crop.io` | TIFF read/write。 |
| `x5crop.detection` | Physical proposal 到 FinalDetection 的 typed lifecycle。 |
| `x5crop.output` | Output protection、bleed 和 output geometry adjustment。 |
| `x5crop.export` | Crop TIFF 与 review copy 写出。 |
| `x5crop.report` | Current report read model、record、validation 和输出。 |
| `x5crop.debug` | 三联 Debug Analysis 的纯渲染。 |
| `tools` | Tests、regression diff 和 standalone build；不进入 runtime。 |

### 2.2 Detection 子层 / Detection Sublayers

| 子层 / Sublayer | 权限 / Authority |
|---|---|
| `detection.context` | `DetectionRequest` 和 `DetectionContext`。 |
| `detection.physical` | Outer、separator、photo-size 和 span 的物理 proposal/measurement。 |
| `detection.guidance` | Content-derived outer、separator 和 count-placement hints。 |
| `detection.candidate.plan` | Count hypotheses；不 build、不 assessment、不 selection。 |
| `detection.candidate.proposal` | Candidate-level proposal entry。 |
| `detection.candidate.build` | Proposal + observations -> `CandidateGeometry`。 |
| `detection.evidence` | 只生成 typed physical evidence，不 gate、不 decision。 |
| `detection.candidate.assessment` | Scores、proof paths 和唯一 `CandidateGate`。 |
| `detection.candidate.execution` | 串联 plan、proposal、build、assessment，并按 `GeometryResolution` 停止。 |
| `detection.candidate.extension` | 生成 corrected geometry 并完整 reassess。 |
| `detection.candidate.selection` | Ranking、geometry clustering、resolution 和 selection。 |
| `detection.modes` | Standard、dual-lane 和 review-only composition。 |
| `detection.decision` | 唯一 `DecisionGate` 和 `FinalDetection` factory。 |
| `detection.final` | 已决策 output geometry 的 finalization。 |

依赖方向固定为：

```text
context / physical / guidance / plan
  -> build / evidence
  -> assessment
  -> selection
candidate execution orchestrates plan / build / assessment / selection
candidate extension produces new geometry and reuses the same lower stages
pipeline -> execution / extension -> decision
  -> final
```

Lower stages cannot import later-stage authority. Report and debug may import passive
typed models but never detection computation.

### 2.3 Canonical Types

| 类型 / Type | Owner | 含义 / Meaning |
|---|---|---|
| `DetectionContext` | `detection.context` | 一次 detection 所需的不可歧义输入。 |
| `HolderSpan`, `FilmSpan` | `detection.physical.spans` | Holder geometry 与 film geometry 的不同身份。 |
| `SeparatorBandObservation` | `x5crop.domain` | Separator measurement 与 provenance。 |
| `CandidateGeometry` | `detection.geometry` | Count、film span、frames、separator assignments 和 source。 |
| `CandidateEvidence` | `candidate.model` | 该几何的全部物理 evidence。 |
| `CandidateAssessment` | `candidate.model` | Scores、CandidateGate 和 diagnostics；无 final status。 |
| `GeometryResolution` | `candidate.selection.model` | Count/placement/boundary 是否已物理解决；唯一 early-stop input。 |
| `SelectionResult` | `candidate.selection.model` | Selected candidate、clusters、consensus 和 count resolution。 |
| `DecisionGateAssessment` | `detection.decision.model` | Final-stage checks 和 canonical final reasons。 |
| `FinalDetection` | `detection.decision.model` | 唯一拥有 final status、decision geometry 和 output geometry 的结果。 |

运行时没有 generic detail dict。Stage 之间只传 immutable typed results；report 层负责序列化，
detection 类型不知道 report schema。

There is no generic runtime detail bus. Stages exchange immutable typed results;
the report layer owns serialization and detection types do not know the schema.

### 2.4 Policy 与 Foundation 边界

Format 只保存 frame mm、derived aspect、count、family、lane composition 和 occupancy trait。
Format 名字不能决定算法分支。Sample-tuned parameter profiles 位于 `policies.parameters`，
assembly 根据已解析 physical spec 与 mode 组装明确 subpolicy。

Foundation (`geometry/image/io/cache/units`) 不知道 format/mode identity、CandidateGate、
DecisionGate、status 或 report schema。Helper 必须接收显式参数对象，不能静默创建默认 policy。

`MeasurementCache` 只保存 exact root measurements，key 必须包含所有会改变结果的参数和 geometry。
它不缓存 candidates、gates、decisions、final reasons 或 count-dependent guidance。Debug 使用独立
`DebugRenderCache`，不能读取或写 detection measurement cache。

### 2.5 Report、Debug 与 Reuse

Current report identity:

```text
schema_id: detection_report
schema_revision: physical_resolution
```

Canonical record 包含 candidate table、CandidateGate、physical evidence、geometry resolution、
selection、DecisionGate、`final_review_reasons`、decision/output geometry、output protection、
calibration 和 diagnostics。它不保留旧字段 alias 或兼容 projection。

Report and Debug are read-only consumers. Cache reuse validates the complete current
record, restores only `FinalDetection` output facts, and enters the same crop/review
actions as a fresh decision. Old or incomplete schemas are ignored and redetected.

### 2.6 架构验收 / Architecture Enforcement

`tools/tests` 使用 AST 和行为合同检查：模块可达性、唯一层级、import 方向、gate/final authority、
current schema、显式参数、unused symbols、重复模型和旧 vocabulary。发现新的架构残余时，先增加
会失败的合同测试，再删除根因；不建立 alias、shim 或 compatibility branch。

The frozen acceptance contract is defined in `AGENTS.md`. Threshold and sample
calibration are separate work and do not reopen architecture unless a real ownership
violation or an unexpressible physical fact is demonstrated.
