# X5 Crop 架构说明 / Architecture Guide

本文件只描述当前 V4.9 的运行流程和源码分层。用户操作见 `README.md`，版本历史见
`CHANGELOG.md`，协作与验收规则见 `AGENTS.md`。

This document describes only the current V4.9 runtime flow and source layers.
User instructions live in `README.md`, version history in `CHANGELOG.md`, and
repository rules in `AGENTS.md`.

## 1. 运行流程 / Runtime Flow

```text
entry
  -> runtime bootstrap and one-time policy resolution
  -> TIFF read / layout normalization / calibration / preprocess
  -> DetectionContext + MeasurementCache
  -> BoundaryObservation + SeparatorBandObservation
  -> count hypotheses + SequenceHypothesis
  -> CandidateGeometry
  -> CandidateEvidence + CandidateGate
  -> GeometryResolution + SelectionResult
  -> OutputBleedPlan
  -> DecisionGate -> FinalDetection
  -> output finalization
  -> export / current-schema report / three-panel debug
```

### 1.1 顶层权限 / Top-Level Authority

| 阶段 / Stage | 唯一职责 / Canonical responsibility |
|---|---|
| Entry | 解析 CLI/interactive 输入；不读取图像、不解析 policy。 Parse user input only. |
| Runtime | 探测输入、解析 format/mode/policy、编排 worker 和副作用。 Resolve runtime identity and orchestrate work. |
| Preprocess | TIFF 读取、layout 归一化、gray/evidence image、deskew、calibration、measurement cache。 |
| Detection | 提出和测量物理几何，build/assess/select candidate。 Propose, measure, assess, and select physical geometry. |
| CandidateGate | 判断候选是否有独立物理证明且无明确物理矛盾。 Judge candidate physical eligibility. |
| GeometryResolution | 唯一 early-stop 输入；确认 count、placement、coverage 和替代几何已经解决。 |
| DecisionGate | 唯一创建 PASS/REVIEW 与 `final_review_reasons`。 Sole final-status authority. |
| Finalization | 只应用已批准的 `OutputBleedPlan` 和 canvas clamp。 Apply output bleed only. |
| Export | 写 crop/review TIFF，保留质量与 metadata。 |
| Report / Debug | 只读 `FinalDetection`，写 current schema 和三联图；不补算事实。 |

### 1.2 Runtime 边界 / Runtime Boundary

Runtime 只解析一次 format、strip mode 和 policy，并创建 `DetectionContext`：

- `DetectionRequest`：layout、用户选择的 `full/partial`、显式或 auto count。
- `FormatPhysicalSpec`：frame mm、derived aspect、count、lane 和 holder occupancy 事实。
- 已解析的 sequence、separator、content、candidate、output 和 diagnostics 参数。
- `ScanCalibration`：只接受可信 TIFF resolution；缺失时保持 unavailable。
- `MeasurementCache`：当前图像的 exact root measurements。

Lower layers receive explicit specs, subpolicies, or plain parameter objects.
They never query registries or invent policy defaults.

输出路径先计算，只有实际写 crop、review copy、report 或 debug 时才创建目录。Cache reuse
只接受输入/config/policy fingerprint 和 `frame_sequence_geometry` schema 全部匹配的 record。

### 1.3 Boundary 与 Frame Sequence / Boundary and Frame Sequence

检测使用统一守恒模型：

```text
visible_sequence_length + leading_occlusion + trailing_occlusion
  = frame_count * physical_frame_width + sum(signed_inter_frame_spacing)
```

- 正 spacing 是可见 separator。
- 零 spacing 表示照片接触。
- 负 spacing 表示叠片。
- Holder occlusion 只允许发生在第一张 leading edge 和最后一张 trailing edge。

每边独立测量 `white_holder_transition`、`tonal_transition`、
`texture_transition` 或 `canvas_clip`。没有源图内部 transition 时不能伪造 pixel
observation。`full_canvas` 只是保守包络，不能成为 physical proof。

`VisibleSequenceSpan` 使用 boundary interval midpoint 表示可见序列；`CropEnvelope` 使用
interval 外侧端覆盖全部 boundary uncertainty。CropEnvelope 不添加固定白边。

### 1.4 Separator 与 Physical Dimensions

`SeparatorBandObservation` 是 count-independent raw pixel band，保留 start/end/center、
tonal evidence、continuity 和 provenance。Raw detection 不按 format 或理论宽度删除宽 band。

Candidate build 将 raw observation 分配给具体 frame boundary：

- band 完全落在物理允许区间内，才是独立 separator assignment。
- 只部分相交时，observation 保留，但 assignment 是 geometry-dependent。
- 无交集表示 width/position contradiction。
- 缺失边界可在 dimension window 内做 focused pixel measurement；仍然是
  `DimensionConstrainedBoundary`，永远不增加 hard separator 数量。

照片尺寸由 `FormatPhysicalSpec` 的真实 mm/aspect、可信 calibration、实测 top/bottom 和
photo-edge measurements共同表达。Photo-size 使用 separator band 边缘之间的照片宽度；
separator width variation 本身不 gate。

### 1.5 Count、Placement 与 Guidance

Partial auto count 按允许 count 从大到小评估。普通 format 不把 nominal full count 放入
partial auto；XPAN/120-66 由 physical trait 允许“完整但未铺满片夹”的 nominal count。

Content 只允许：

- 向外扩张 `CropEnvelope` 以覆盖仍可见内容。
- 发现 frame union 外未解释的真实内容。
- 验证可见内容没有被裁断。
- 解释 holder 的低纹理/低内容区域。

Content 不创建或修改 `VisibleSequenceSpan`，不定义 hard separator、frame dimension 或内部
cut，也不能收缩物理 sequence span。
Content-region measurement 使用物理 frame-width reference，不读取 candidate count 或 format
default count。

### 1.6 Candidate、Gate 与 Selection

```text
CountHypothesisPlan
  -> SequenceHypothesis
  -> CandidateGeometry
  -> CandidateEvidence
  -> CandidateAssessment + CandidateGate
  -> geometry clustering / SelectionResult
```

`CandidateGate` 只检查：frame topology、visible-content preservation、photo geometry、
frame-sequence conservation、evidence independence 和至少一条 boundary proof path。
Proof paths 为 `separator_led`、`geometry_led`、`partial_occupancy_led` 或 dual-lane
`mode_composition`。

Confidence 只用于候选排序和解释。Selection 按 frame-relative tolerance 聚类实质几何：
单一候选是 `uncontested`，多个等价候选是 `agreed`，接近但实质不同的簇是 `disagreed`。
`GeometryResolution` 是唯一 early-stop 输入；CandidateGate PASS 本身不能停止搜索。

所有普通物理候选统一使用 `frame_sequence` source；boundary、separator 和 dimensions 是
observation/proof provenance，不再伪装成彼此排他的 candidate identity。

### 1.7 Decision、Envelope 与 Bleed

DecisionGate 只消费：CandidateGate 的具体失败项、automatic eligibility、selection geometry
consensus、OutputBleedPlan feasibility 和 transform geometry。它不重新测量 evidence，也不使用
confidence floor。

输出几何顺序固定为：

```text
VisibleSequenceSpan
  -> CropEnvelope uncertainty applied to edge frames
  -> OutputBleedPlan
  -> final frame boxes clamped to canvas
```

```text
effective_long_axis_bleed
  = max(user_long_axis_bleed, overlap_required_bleed)

effective_short_axis_bleed
  = user_short_axis_bleed
```

Visible-content coverage 在 bleed 前验证；bleed 不能救回错误 candidate。叠片只增加长轴
bleed；超过可用 capacity 才产生 `output_bleed_unresolved`。Finalization 不读取 gray、
separator 或 content，也不重新检测几何。

### 1.8 Special Modes

- `135-dual/full` 测量 holder gutter，分别运行两条普通 sequence pipeline，再检查 lane
  consistency；每条 lane 保留自己的 `CropEnvelope` 和 lane-indexed signed spacing，center split
  只作为 safety hypothesis。
- `135-dual/partial` 是明确的 review-only mode。
- Deskew 输出 typed `TransformGeometryEvidence`，只有 DecisionGate 消费其最终状态。

## 2. 源码分层 / Source Layers

### 2.1 顶层 packages / Top-Level Packages

| Layer | Canonical responsibility |
|---|---|
| `x5crop.entry` | CLI 与 interactive parsing。 |
| `x5crop.runtime` | Bootstrap、workflow、workers、reuse 和 output side effects。 |
| `x5crop.formats` | Format identity 与真实 physical spec。 |
| `x5crop.policies` | Sample-tuned 参数和 runtime assembly；不拥有 physical facts 或 schema。 |
| `x5crop.units` | `ScanCalibration`、`PhysicalLength` 和单位解析。 |
| `x5crop.cache` | Exact count-independent measurement cache。 |
| `x5crop.geometry` | Box/profile 等无业务权限的纯算法。 |
| `x5crop.image` | Gray、deskew、pixel transform 和 crop pixels。 |
| `x5crop.io` | TIFF read/write。 |
| `x5crop.detection` | Typed physical detection lifecycle。 |
| `x5crop.output` | `OutputBleedPlan` 与 output geometry。 |
| `x5crop.export` | Crop/review TIFF 写出。 |
| `x5crop.report` | Current read model、record、validation、restoration 和 outputs。 |
| `x5crop.debug` | 三联 Debug Analysis 的纯渲染。 |
| `tools` | Contract tests、current-schema diff 和 standalone build。 |

### 2.2 Detection 子层 / Detection Sublayers

| Sublayer | Authority |
|---|---|
| `context` | `DetectionRequest` / `DetectionContext`。 |
| `physical` | Boundary、separator、frame dimensions、signed spacing 和 conservation。 |
| `guidance` | 只向外扩张 `CropEnvelope`；不改物理 sequence geometry。 |
| `candidate.plan` | Count hypothesis descriptors only。 |
| `candidate.proposal` | Sequence hypotheses。 |
| `candidate.build` | Hypothesis + measurements -> `CandidateGeometry`。 |
| `evidence` | Typed physical measurements；不 gate、不 decision。 |
| `candidate.assessment` | Scores、proof paths 和唯一 `CandidateGate`。 |
| `candidate.execution` | 串联 plan/proposal/build/assessment。 |
| `candidate.selection` | Ranking、geometry clusters、count/geometry resolution。 |
| `modes` | Standard、dual-lane、review-only composition。 |
| `decision` | 唯一 `DecisionGate` 和 `FinalDetection` factory。 |
| `final` | 只应用 output bleed geometry。 |

依赖只允许沿上述生命周期向后流动。Physical/evidence/guidance 不 import candidate decision；
report/debug 可读取 typed final models，但不能 import detection computation。

### 2.3 Canonical Types

| Type | Owner | Meaning |
|---|---|---|
| `HolderSpan`, `VisibleSequenceSpan`, `CropEnvelope` | `x5crop.domain` | Holder、可见照片序列和保守裁切包络。 |
| `BoundaryObservation` | `x5crop.domain` | Per-side boundary interval 与 provenance。 |
| `SeparatorBandObservation`, `SeparatorAssignment` | `x5crop.domain` | Raw band 与 candidate-specific assignment。 |
| `FrameBoundary`, `DimensionConstrainedBoundary` | `x5crop.domain` | 实测或尺寸约束切线。 |
| `InterFrameSpacingEvidence`, `SequenceConservationEvidence` | `detection.physical.spacing` | Signed spacing 与守恒。 |
| `CandidateGeometry` | `detection.geometry` | Candidate 的全部物理几何。 |
| `CandidateEvidence`, `CandidateAssessment` | `candidate.model` | Typed evidence、scores 和 CandidateGate。 |
| `GeometryResolution`, `SelectionResult` | `candidate.selection.model` | Early-stop 与最终候选选择。 |
| `OutputBleedPlan` | `x5crop.domain` | 用户 bleed、叠片增量和 feasibility。 |
| `DecisionGateAssessment`, `FinalDetection` | `detection.decision.model` | Final checks、status 和 output facts。 |

Runtime 没有 generic detail dict、alias、shim 或 schema reducer。Stage 之间只传 immutable typed
results；report 层负责 JSON read model。

### 2.4 Policy、Foundation 与 Cache

Format 只保存 mm/aspect/count/lane/occupancy 等物理事实。Format 名字不决定算法分支。
Sample-tuned 参数固定分为 preprocess、content、sequence、separator、candidate、output 和
diagnostics，由 runtime boundary 解析。

Foundation (`geometry/image/io/cache/units`) 不知道 format/mode、CandidateGate、DecisionGate、
status 或 report schema。Helper 必须接收显式参数。

`MeasurementCache` 只缓存 exact root measurements，key 包含所有影响结果的参数和 box。
它不缓存 candidate、gate、decision、final reason 或 approximate geometry。Debug 使用独立
render cache。

### 2.5 Current Schema 与 Enforcement

```text
schema_id: detection_report
schema_revision: frame_sequence_geometry
```

Report 输出 boundary observations、VisibleSequenceSpan、CropEnvelope、holder occlusion、raw
separator bands、assignments、frame boundaries、signed spacing、sequence conservation、
CandidateGate、GeometryResolution、DecisionGate 和 OutputBleedPlan。Old/incomplete records
直接重新检测。

`tools/tests` 使用 AST 与行为契约检查：模块可达、唯一归层、无环依赖、单向权限、current
schema、显式参数、零孤儿、零重复 model 和禁止旧 vocabulary。发现残余时先增加失败契约，
再删除整类根因。冻结验收定义见 `AGENTS.md`。
