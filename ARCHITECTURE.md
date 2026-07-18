# X5 Crop 架构说明 / Architecture Guide

本文件只描述当前 V4.9 的运行流程、物理模型和源码分层。用户操作见
`README.md`，版本历史见 `CHANGELOG.md`，协作与封口规则见 `AGENTS.md`。

## 1. 运行流程 / Runtime Flow

```text
entry
  -> runtime bootstrap + DetectionConfigurationBundle
  -> TIFF read + layout normalization + preprocess
  -> PreparedWorkspace + DetectionContext + MeasurementCache
  -> count-independent gray paths + separator bands + content observations
  -> SharedShortAxisCropSpan
  -> count hypotheses + FrameDimensionPrior
  -> global FrameSequenceSolver -> FrameSequenceSolution candidates
  -> physical evidence + CandidateGate
  -> GeometryResolution + deterministic selection
  -> FrameCropEnvelope + FrameBleedPlan
  -> DecisionGateAssessment
  -> finalization -> FinalDetection
  -> TIFF export / current-schema report / three-panel Debug Analysis
```

### 1.1 权限边界 / Authority Boundaries

| Stage | Canonical responsibility |
|---|---|
| Entry | 只解析 CLI 与 interactive 输入。 |
| Runtime | 一次性解析 configuration，编排 worker、cache reuse 和写出副作用。 |
| Preprocess | 读取 TIFF，统一 layout，生成唯一灰度 workspace，测量 deskew 与 metadata。 |
| Observation | 生成 count-independent 灰度 path、separator band、content 与图像统计。 |
| Physical solver | 求解共享短轴、长轴 frame slots、间距、count 与完整序列。 |
| Evidence | 描述支持、矛盾、不可用或不适用，不决定最终状态。 |
| CandidateGate | 判断候选是否具备物理证明且没有明确物理矛盾。 |
| GeometryResolution | 唯一 early-stop 输入，确认 count、slots、替代解与搜索均已解决。 |
| Selection | 按物理目标确定性排序，并聚合区间等价解。 |
| FrameBleedPlan | 合并用户 bleed 与逐 boundary 的叠片保护。 |
| DecisionGate | 唯一创建最终 status 和 `final_review_reasons`。 |
| Finalization | 只应用输出计划和 canvas/lane clamp，不重新检测。 |
| Report / Debug | 只读 typed results，不补算事实或参与裁决。 |

`CandidateGate` 与 `DecisionGate` 是唯一两个 Gate。CandidateGate PASS 不代表几何已经
resolved，也不能触发 early-stop。只有 `GeometryResolution.supported` 可以结束候选扩展，只有
DecisionGate 可以创建 `approved_auto` 或 `needs_review`。

### 1.2 Runtime Configuration

Runtime 从 `FormatPhysicalSpec + strip_mode` 创建唯一 `DetectionConfiguration`。Format spec
只保存真实 frame mm、derived aspect、允许 count、physical layout 与 occupancy trait。Format
名字只用于 lookup，不拥有算法分支或 format-specific threshold。

Lower layers 只接收显式 physical spec、configuration group 或普通参数对象。它们不查询 registry，
不根据 mode 字符串发明默认参数。TIFF resolution metadata 与 `ImageProfile` 停留在 I/O、runtime、
report 与 export 数据流，不进入候选几何或 Gate。

## 2. Frame Slot 物理模型

### 2.1 共享短轴

一条 strip 的所有照片共用同一组 top/bottom 边界。`SharedShortAxisCropSpan` 是每个
`FrameSlot` 唯一使用的短轴范围，因此同一条 strip 不会出现逐张照片上下错位。

短轴 basis 只有两种：

- `photo_edge_bounded`：上下照片边界都有独立测量，可同时提供安全输出范围和照片高度证据。
- `holder_edge_bounded`：只可靠排除片夹。它可以保留片基并仍作为安全输出范围，但不能反推照片高度
  或长轴宽度。

精确排除片基是优选结果，不是自动处理的必要条件。Canvas fallback 只能进入
`ContainmentFallback`，不能成为 resolved shared short axis。

### 2.2 长轴 Frame Slots

`FrameSlot` 表示一次物理卷片或曝光槽位。每个 slot 保存：

- leading/trailing `LongAxisBoundaryResolution`；
- nominal 与 visible long-axis interval；
- content occupancy；
- 可选的首尾 holder occlusion；
- 可选的 `SequenceInferredSlotGeometry`。

所有 slots 必须按长轴严格单调、正宽、不交叉。`CommonFrameWidthResolution` 从独立完整
slots 建立共同照片宽度。照片宽度稳定是主要物理约束；separator 宽度和片距可以变化。

Measured boundary 与 geometry-derived boundary 是不同事实。Dimension constraint、holder
occlusion 或 blank inference 可以解决几何，但其 measurement state 保持 unavailable，不能增加
独立测量、hard separator 数量或 proof path。

### 2.3 Separator 与 Signed Spacing

`SeparatorBandObservation` 是 count-independent 原始像素 band。一个正 separator 的两条边分别
绑定相邻 slots：

```text
band.start -> preceding slot trailing edge
band.end   -> following slot leading edge
```

Candidate-specific assignment 必须同时满足位置、物理宽度、跨短轴连续性、单调性和 provenance。
足以容纳一张完整照片的宽 tonal run 不能成为一个 hard separator。灰度外观相似、低纹理或
连续性本身都不能证明 material identity。

`InterFrameSpacing` 使用 signed interval：正值是 separator，零是 contact，负值是 overlap。
只有独立像素观测或独立约束共同佐证的 overlap 才能触发输出保护。Geometry 方程推导的负值
不能证明自身，也不能自动增加 bleed。

### 2.4 空白 Frame Slot

空白曝光区域与 separator 可能在灰度上完全连续。脚本不检测“空白材料”，也不通过无内容、
低纹理或伪造 separator 来证明空白槽位。

Full nominal sequence 最多允许一个唯一推导的空白 slot，位置可以是 leading、interior 或
trailing。`SequenceInferredSlotGeometry` 必须满足：

- 其余真实 slots 已安全解决；
- `CommonFrameWidthResolution` 由独立完整 slots 支持；
- nominal count 与唯一 placement 成立；
- edge blank 有对应 holder safe boundary；
- 推导不移动相邻真实照片的 measured boundaries；
- 没有可靠的未覆盖内容或等价 count/placement；
- execution budget 未耗尽。

Blank slot 的 geometry 可以 resolved，但 measurement state 固定为 unavailable。它不是 separator，
不增加 hard separator 或 proof path。一个 supported blank slot 可以与整体 GeometryResolution PASS
共存；两个 blank slots、位置歧义、共同宽度缺失或 holder safe boundary 缺失都会保持 unresolved。

Partial 可以输出额外空 frame，但空白区域不能帮助 auto count resolution。66/XPAN 的
complete-underfilled trait 只改变 count availability 与 occupancy 解释，不绕过 geometry、coverage
或 preservation。

### 2.5 Global Frame Sequence Solver

`solve_frame_sequence` 对每个允许 count 和 frame-size option 联合求解 `FrameSequenceSolution`：

- 先求一次共享短轴，不枚举逐照片 top/bottom 组合；
- 长轴 raw paths 与 separator bands 形成有序 anchors；
- branch-and-bound 持续传播 count、共同宽度、剩余 span、content coverage 与 endpoint feasibility；
- model boundary 只在共同宽度约束区间内辅助 focused search，不伪装成 measured separator；
- content observations 只能淘汰漏掉可靠可见内容的几何，不能生成、移动或收缩边界；
- assignment consensus 要求全部非支配解对主要 slot intervals 形成共同区间；
- partial auto 从允许的较大 count 向较小 count 求解；
- 未评估更大 count、替代几何未解决或预算耗尽时，GeometryResolution 保持 unavailable。

`FrameDimensionPrior` 由 physical frame mm 与 derived aspect 约束搜索，不是 measurement evidence。
只有独立 photo-edge measurements 可以形成 `FrameDimensionEvidence`。

## 3. Evidence、Assessment 与 Decision

### 3.1 Candidate Evidence

Standard candidate 的 canonical evidence 包括：

- `FrameSlotTopologyEvidence`：slot 顺序、正宽与完整 count；
- `FrameCoverageEvidence`：基础 envelopes 是否覆盖可靠可见内容；
- internal/external frame boundary preservation；
- separator sequence 与 frame dimensions；
- holder boundary、holder occupancy、partial edge safety 与 frame scale observations；
- measurement independence。

Content measurement 只用于遗漏内容反证和 preservation。它不能定义 count、边界或 blank slot，
也不能把“没有内容”提升为支持证据。同一份 count-independent content observation 在 solver 与
最终 evidence 中共享，避免两套覆盖事实漂移。

### 3.2 CandidateGate

CandidateGate 固定检查：

```text
frame_slot_topology
content_preservation
frame_dimension_consistency
evidence_independence
sequence_proof
```

Proof paths 只有 `separator_sequence_led`、`dimension_sequence_led`、`partial_occupancy_led`；
dual-lane composition 使用独立 mode proof。Blank inference 与 holder-bounded 短轴不增加 proof。
CandidateGate 不读取 scalar confidence，也不创建 final reason。

### 3.3 GeometryResolution、Selection 与 DecisionGate

`GeometryResolution` 单独回答：

- count 是否解决；
- frame slots 是否解决；
- shared short axis 是否安全；
- content preservation 是否兼容；
- larger-count hypotheses 是否完成；
- alternative geometries 与 assignment consensus 是否解决；
- physical search 是否完整且未耗尽预算。

Selection 只按 typed facts 确定性排序：先保护可见内容，再减少明确物理矛盾、优先独立 proof、
partial 较大 count、较小 residual/uncertainty，最后使用稳定 source order。

DecisionGate 只消费 selected CandidateGate、GeometryResolution、selection consensus、
FrameBleedPlan 和 transform geometry。它不重新测量 evidence，不生成候选，也不以低 confidence
制造 REVIEW。

## 4. Output、Report 与 Debug

### 4.1 FrameCropEnvelope 与 Bleed

每个 final frame 由以下顺序产生：

```text
FrameSlot long-axis interval
  x SharedShortAxisCropSpan
  -> FrameCropEnvelope
  -> FrameBleedPlan
  -> final box
```

Blank frame 使用自己的 `safe_output_interval`，可以保守包含连续片基、separator 或少量 holder，
但不能改写任何真实照片的 crop envelope。用户 bleed 与 blank safe output 是不同概念。

Measured/corroborated overlap 只扩张相关内部 boundary 两侧；无关 frame 不受全局最大值影响。
Bleed 不修改 frame slots、CandidateGate、GeometryResolution 或 status。Unresolved geometry 永不
导出 frame TIFF，即使用户启用 `--export-review`。

### 4.2 Current Report Schema

```text
schema_id: detection_report
schema_revision: frame_slot_sequence_resolution
```

Canonical sections：

- `input`：TIFF profile、workspace extent、resolution metadata 与 transform geometry；
- `configuration`：current `DetectionConfiguration` read model；
- `selection`：candidates、FrameSequenceSolution、evidence、CandidateGate、GeometryResolution 与 clusters；
- `decision`：status、DecisionGate 与 `final_review_reasons`；
- `output`：FrameBleedPlan、optional finalization plan、optional final geometry 与实际写出结果。

Report、cache reuse、regression tools 与 tests 只接受该 schema。旧 schema 直接 cache miss，report
和 restoration 不补算 selection 或 decision。

### 4.3 Debug Analysis

Debug Analysis 固定三联图：原始灰度上下文、FrameSlot/输出几何、boundary/separator evidence。
它只读取 final typed model。内置图例由 diagnostics configuration 生成：

- white dashed: `Holder boundary`；
- yellow: `Raw observation`；
- red: `Measured frame / separator edge`；
- purple dashed: `Dimension-only provisional edge`；
- cyan: `Corroborated overlap`；
- green: `FrameSlot`；
- yellow dashed: `Sequence-inferred FrameSlot`；
- blue dashed: `FrameCropEnvelope / protected output`。

Unresolved geometry 明确标记 `NOT EXPORTABLE`。Debug 可以用彩色线条解释灰度检测，但颜色不
回流 detection。

## 5. 源码分层 / Source Layers

| Layer | Canonical responsibility |
|---|---|
| `x5crop.entry` | CLI、interactive parsing 与用户文本输出。 |
| `x5crop.runtime` | Bootstrap、workflow、workers、reuse 与 output side effects。 |
| `x5crop.formats` | Format identity 与真实 physical spec。 |
| `x5crop.configuration` | Adaptive parameters、execution budgets 与 runtime assembly。 |
| `x5crop.cache` | Exact count-independent measurement cache。 |
| `x5crop.geometry` | 纯 box、layout 与 sampling 算法。 |
| `x5crop.image` | Gray、statistics、deskew 与 pixel transforms。 |
| `x5crop.io` | TIFF read/write 与 metadata ownership。 |
| `x5crop.detection.physical` | Raw observations、shared short axis、frame dimensions 与 global solver。 |
| `x5crop.detection.evidence` | Typed physical measurements，不 Gate、不 decision。 |
| `x5crop.detection.candidate` | Count plan、build、assessment、execution 与 selection。 |
| `x5crop.detection.decision` | DecisionGate 与 final reason vocabulary。 |
| `x5crop.detection.final` | Finalization plan 与 FinalDetection assembly。 |
| `x5crop.output` | Frame bleed、output geometry 与 side-effect-free plans。 |
| `x5crop.export` | Output path 与 TIFF export orchestration。 |
| `x5crop.report` | Current-schema serialization、validation 与 restoration。 |
| `x5crop.debug` | Read-only three-panel visualization。 |
| `tools.tests` | Runtime、physical invariant 与 architecture contracts。 |
| `tools.regression` | Current-schema diff 与 frame-slot reference validation。 |

## 6. 参数与缓存边界

影响检测或输出的数值只能属于 `physical_fact`、`standard_transform`、
`adaptive_measurement`、`numerical_safety`、`execution_budget`、`user_preference` 或
`diagnostics_only`。Format 名字不拥有算法 threshold，隐藏数值不能改变 crop、Gate 或 output。

MeasurementCache 只缓存 exact、count/offset-independent measurements，例如图像统计、raw paths、
separator bands 与 content observations。Candidate、Gate、GeometryResolution、decision、blank
inference 和 approximate geometry 都不缓存。

Execution budget 只限制搜索量。预算耗尽必须产生 typed unavailable，不能成为可靠性或自动处理
信号。
