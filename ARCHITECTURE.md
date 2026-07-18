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

Holder occlusion is endpoint-only geometry: it must hide a positive extent and
may occur only on the first slot's leading side or the final slot's trailing
side. Final sequence identity rejects zero-width, wrong-side, and interior
occlusion states rather than treating them as harmless annotations.

Holder occlusion 只能表达端点几何：必须隐藏正宽度，并且只允许首 slot 的 leading side 或尾
slot 的 trailing side。最终序列 identity 会拒绝零宽、错误 side 与 interior occlusion，而不是
把它们当作无害标注。

### 2.3 Separator 与 Signed Spacing

`SeparatorBandObservation` 是 count-independent 原始像素 band。一个正 separator 的两条边分别
绑定相邻 slots：

```text
band.start -> preceding slot trailing edge
band.end   -> following slot leading edge
```

Candidate-specific assignment 必须同时满足位置、物理宽度、当前 strip 共享测量 span 上的跨短轴
连续性、单调性和 provenance。
足以容纳一张完整照片的宽 tonal run 不能成为一个 hard separator。灰度外观相似、低纹理或
连续性本身都不能证明 material identity。

`InterFrameSpacing` 使用 signed interval：正值是 separator，零是 contact，负值是 overlap。
只有独立像素观测或独立约束共同佐证的 overlap 才能触发输出保护。Geometry 方程推导的负值
不能证明自身，也不能自动增加 bleed。Content crossing 只能佐证两侧 physical roles 已经独立测得的
overlap；由 dimension 或 `FRAME_WIDTH_PATTERN` 分配的 role 不能借 content 升级为
`CORROBORATED_OVERLAP`。

Content crossing may corroborate overlap only when both physical boundary roles
were independently measured. A role assigned by dimensions or
`FRAME_WIDTH_PATTERN` cannot use content to upgrade geometry into
`CORROBORATED_OVERLAP` or output-protection authority.

Final sequence identity also conserves separator measurement and spacing
authority: every typed separator assignment must use cross-axis continuity
measured on the strip's exact shared short-axis span, bind the matching positive
`OBSERVED` spacing at the same boundary, and retain the assigned band's
observation identity. A foreign measurement span or geometry-hypothesis spacing
cannot coexist with a hard separator assignment even when coordinates happen to
match.

最终序列 identity 还必须守恒 separator measurement 与 spacing 权限：每个 typed separator
assignment 必须使用当前 strip 精确共享短轴 span 上测得的跨轴连续性，在同一 boundary 绑定对应的
正值 `OBSERVED` spacing，并保留已分配 band 的观测 identity。即使坐标碰巧一致，来自其他 span 的
measurement 或 geometry-hypothesis spacing 也不能与 hard separator assignment 同时成立。

Every `MeasurementProvenance` is acyclic: its `root_measurement` cannot also
appear in `dependencies`. A derived fact that consumes same-root inputs keeps
their upstream dependencies instead of creating a self-authorizing provenance
loop; runtime construction and current-report validation enforce the same rule.
Within one current report, one `ObservationId` must also map to exactly one full
provenance; conflicting reuse is an identity error, not an alternate description.

每个 `MeasurementProvenance` 都必须无环：`root_measurement` 不得再出现在
`dependencies` 中。派生事实消费同 root 输入时只保留其上游依赖，不得形成
自我授权环；runtime 构造与 current-report 校验共用同一规则。
同一份 current report 内，一个 `ObservationId` 也只能对应一套完整 provenance；
冲突复用是 identity error，不是可接受的替代描述。

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

### 2.5 Sequence Solver Ownership / 序列求解职责

Frame-sequence proof code uses explicit owner modules rather than treating one
solver file as the owner of every lifecycle concept. The current canonical
boundaries are:

| Module | Canonical responsibility |
|---|---|
| `frame_sequence_measurements.py` | `EdgeConstraint`, `MeasuredFrameConstraint`, positive interval facts, measurement compatibility, and strict contributor grouping primitives. |
| `frame_sequence_common_width.py` | Measured/recurring width hypotheses, contributor selection, independent physical-scale corroboration, and final `CommonFrameWidthResolution`. |
| `frame_sequence_search.py` | Common-width option graph, reachability, graph witnesses, assignment-evaluation accounting, and typed budget exhaustion. |
| `frame_sequence_candidates.py` | Candidate build state and rebuild primitives, boundary resolution, separator bindings, inter-frame spacing/objective facts, slot-topology invariants, geometry-alternative clustering, physical Pareto, representative selection, and visible-content conservation. |
| `frame_sequence_consensus.py` | Assignment consensus, dimension-only internal uncertainty envelopes, external safety envelopes, and their provenance. |
| `frame_sequence_separator_assignment.py` | Candidate-specific separator edge roles, double-edge binding, holder-band roles, unique observation assignment, spacing bindings, and final typed separator assignments. |
| `frame_sequence_boundary_roles.py` | Repeated-width, physical-scale, common-width, and adjacent-measurement corroboration of typed boundary roles and provenance. |
| `frame_sequence_candidate_resolution.py` | Holder-boundary lookup, common-width dimension-boundary resolution, unique gray-path assignment, and the ordered boundary-role/common-width physical-resolution pass for one candidate build. |
| `sequence_completion.py` | Measured-sequence slot inference, blank-slot completion, content occupancy, holder-edge occlusion, endpoint/full-sequence eligibility, and completion selection. |
| `frame_sequence_result.py` | Typed solve success/failure outcomes, content-extent and indexed-anchor constraints, and final spacing/overlap physical facts. |
| `frame_sequence_construction.py` | Search-index preparation, canonical path/band/dimension hypotheses, bounded candidate-build enumeration, and count-specific construction. |
| `frame_sequence_solver.py` | Thin top-level validation and lifecycle orchestration across construction, completion, consensus, selection, budget state, and typed result assembly. |

Dependency direction is one way: common-width resolution consumes measurement
facts; search consumes both lower owners; candidate state consumes measurement facts;
consensus consumes candidate state; separator assignment consumes measurement facts
and candidate state; boundary-role corroboration also consumes measurement facts and
candidate state. Candidate physical resolution consumes measurement facts,
common-width resolution, candidate state, and boundary-role corroboration. Sequence
completion consumes measurement facts, common-width resolution, candidate state,
and candidate physical resolution. Result facts consume measurement facts,
common-width resolution, and candidate state. Construction consumes measurement,
common-width, search, candidate-state, separator-assignment, and candidate-resolution
owners. The solver facade consumes construction together with candidate resolution,
candidate state, consensus, separator assignment, completion, and result facts. No
lower owner imports construction or the solver, and neither facade re-exports migrated
symbols. Architecture contracts check definition owners and import direction, while
physical contracts target the canonical module directly.

Frame-sequence 证明代码按显式 owner 划分，不再把单个 solver 文件视为全部生命周期概念的共同
owner。当前 measurement interval 只由 `frame_sequence_measurements.py` 拥有，common-width
假设、contributor 选择、独立 scale 佐证与最终 resolution 只由
`frame_sequence_common_width.py` 拥有；graph options、reachability、witness 与 typed budget state
只由 `frame_sequence_search.py` 拥有；candidate build state、物理 objectives、geometry alternative
聚类、物理 Pareto、代表解、slot topology 与可见内容守恒只由
`frame_sequence_candidates.py` 拥有；assignment consensus、dimension-only internal uncertainty
与 external safety envelope 只由 `frame_sequence_consensus.py` 拥有；candidate-specific separator
角色、双边绑定、唯一观测分配、spacing binding 与最终 typed assignment 只由
`frame_sequence_separator_assignment.py` 拥有；repeated-width、physical-scale、common-width
与相邻实测的 typed boundary-role corroboration 只由 `frame_sequence_boundary_roles.py` 拥有。
holder boundary 映射、common-width dimension-boundary resolution、唯一 gray-path assignment，
以及 boundary role 与 common-width 的有序 candidate physical-resolution pass 只由
`frame_sequence_candidate_resolution.py` 拥有。measured-sequence slot inference、blank-slot
completion、content occupancy、holder-edge occlusion、endpoint/full-sequence eligibility 与
completion selection 只由 `sequence_completion.py` 拥有。typed solve outcome、content-extent /
indexed-anchor constraints 与最终 spacing/overlap physical facts 只由
`frame_sequence_result.py` 拥有。search-index 准备、规范 path/band/dimension hypotheses、
有界 candidate-build 枚举与 count-specific construction 只由
`frame_sequence_construction.py` 拥有；`frame_sequence_solver.py` 只保留入参校验、
生命周期编排、budget state、selection 与 typed result 组装。
依赖保持单向：measurement facts 供 common-width、search、candidate state、separator assignment
与 boundary-role owner 消费；consensus、separator assignment 与 boundary-role owner 再消费
candidate state；candidate physical resolution 只消费 measurement facts、common-width、candidate
state 与 boundary-role owner；sequence completion 只消费 measurement facts、common-width、
candidate state 与 candidate physical resolution；result facts 只消费 measurement facts、
common-width 与 candidate state；construction 只消费 measurement、common-width、search、
candidate state、separator assignment 与 candidate resolution owners；solver facade 再消费
construction、candidate resolution/state、consensus、separator assignment、completion 与
result facts。低层模块不得反向导入 construction 或 solver，两个 facade 也不兼容
导出已经迁移的符号。

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
Bleed 不修改 frame slots、CandidateGate、GeometryResolution 或 status。Unresolved geometry 或
FrameBleedPlan 中 unresolved overlap protection 永不导出 frame TIFF，即使用户启用
`--export-review`；resolved geometry 可继续供诊断显示，但不获得导出权限。

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
