# X5 Crop 架构说明 / Architecture Guide

本文件只描述当前 V4.9 的运行流程和源码分层。用户操作见 `README.md`，版本历史见
`CHANGELOG.md`，协作与验收规则见 `AGENTS.md`。

This document describes only the current V4.9 runtime flow and source layers.
User instructions live in `README.md`, version history in `CHANGELOG.md`, and
repository rules in `AGENTS.md`.

## 1. 运行流程 / Runtime Flow

```text
entry
  -> runtime bootstrap + DetectionConfigurationBundle
  -> TIFF read + layout normalization + calibration + preprocess
  -> DetectionContext + exact MeasurementCache
  -> boundary / separator / content observations
  -> count hypotheses + sequence hypotheses
  -> global monotonic sequence solver -> SequenceSolution
  -> mode composition -> CandidateGeometry
  -> physical evidence + EvidenceQuality + CandidateGate
  -> GeometryResolution + deterministic selection
  -> FrameBleedPlan
  -> DecisionGate -> FinalDetection
  -> finalization
  -> TIFF export / current-schema report / three-panel debug
```

### 1.1 权限边界 / Authority Boundaries

| Stage | Canonical responsibility |
|---|---|
| Entry | 只解析 CLI 和 interactive 输入。 Parse user input only. |
| Runtime | 一次性解析 configuration，编排 worker、cache reuse 和写出副作用。 |
| Preprocess | TIFF、layout、gray/evidence image、deskew、calibration 和 root measurements。 |
| Physical detection | 提出并求解 boundary、separator、photo interval、spacing 和 count。 |
| Evidence | 描述观测支持、矛盾或不可用；不决定 PASS/REVIEW。 |
| CandidateGate | 判断单个 typed candidate geometry 是否有独立物理证明且无明确矛盾。 |
| GeometryResolution | 唯一 early-stop 输入；确认 count、placement、coverage 和替代几何已解决。 |
| Selection | 按物理目标确定性排序并聚合区间等价解。 |
| FrameBleedPlan | 把用户 bleed 与逐 boundary 的物理叠片保护转换为逐 frame-side 输出计划。 |
| DecisionGate | 唯一创建最终 status 和 `final_review_reasons`。 |
| Finalization | 只应用 `FrameBleedPlan` 和 bounds clamp；不重新检测。 |
| Report / Debug | 只读 typed final results；不补算事实、不参与裁决。 |

### 1.2 Runtime Configuration

Runtime 从 `FormatPhysicalSpec + strip_mode` 创建唯一
`DetectionConfiguration`。它包含：

- 真实 frame mm、derived aspect、允许 count、physical layout 和 holder occupancy traits。
- 全局 adaptive image measurement 参数。
- candidate/observation execution budgets。
- diagnostics configuration。

Format 名字只用于 physical spec lookup，不拥有算法分支或独立参数 profile。Dual-lane
detector 由 `physical_layout` trait 推导。Lower layers 只接收显式 configuration 子对象、
physical spec 或普通参数对象，不反查 registry。

### 1.3 Boundary、Sequence 与 Outer

旧 generic outer 已被三个不同物理概念替代：

| Type | Meaning |
|---|---|
| `HolderSpan` | 片夹可用范围。 Holder geometry only. |
| `VisibleSequenceSpan` | 源图中实际可见的照片序列范围。 |
| `CropEnvelope` | 覆盖所有可见内容与 boundary uncertainty 的保守输出包络。 |

每条边独立测量 white-holder、tonal、texture 或 canvas boundary interval。Base boundary
不假设照片一定有黑边；黑边、白片夹和四边混合状态都可成为观测。Full canvas 只能作为
保守 envelope，不能成为 count 或 boundary proof。

Content 只允许向外扩张 `CropEnvelope` 以保护可见内容。它不能收缩 sequence span、定义内部
cut 或制造 frame count。

### 1.4 Separator 与 Signed Spacing

`SeparatorBandObservation` 是 count-independent raw pixel band。它在 assignment 前一次性记录
start/end/center、局部 tonal evidence、完整 cross-axis pixel-path measurement 和 root
provenance；后续 evidence 只聚合这些 observation，不重新读取像素。

Candidate-specific assignment 同时满足：

- `BoundaryPositionConstraint`: 该内部切线允许出现的位置区间。
- `SeparatorWidthConstraint`: 相邻照片物理尺寸允许的 separator 宽度区间。

Band 必须整体落入 position constraint，并且 cross-axis path、position 与 width 同时成立，
才能成为独立 separator assignment。只让中心点落入区间、局部相交或 continuity 不成立的
tonal region 只能保留为 diagnostic / geometry-dependent observation。

过宽的欠曝 tonal run 保留为 diagnostic observation，但不能成为 hard separator。缺失 cut 可由
`DimensionConstrainedBoundary` 表示；它不能增加 hard separator 数量。

内部 spacing 使用三个互不兼容的 canonical types：

- `ObservedSpacingEvidence`: 独立像素或 photo-edge measurement。
- `CorroboratedSpacingEvidence`: 可信 calibration、两端实测边界与其余独立 spacing
  唯一共同确定的 overlap；只支持 output protection，不能证明同一 conservation equation。
- `SpacingHypothesis`: geometry equation 推导的未观测假设。

正值是 separator，零是 contact，负值是 overlap。Hypothesis 不能支持 proof path 或自动
overlap bleed；corroborated overlap 也不能回头支持 sequence conservation。

### 1.5 Global Sequence Solver 与 Auto Count

Sequence solver 同时求解所有内部 boundaries，不逐边贪心：

- `PhotoInterval` 和 cuts 必须严格单调，不能产生零宽、负宽或倒序 frame。
- Interior photos 服从同一 `FrameDimensionPrior` option。
- Holder occlusion 只能作用于首张 leading edge 和末张 trailing edge。
- Position、width、sequence conservation 和 provenance 必须同时成立。
- 同一 span/count 下所有最大独立-anchor 解都参与 `BoundaryAssignmentConsensus`；不同解的
  cut interval 没有共同交集时，assignment geometry 保持 unresolved。
- Search budget exhausted 时 geometry 保持 unresolved。

Observation、hypothesis、assignment 和 dual-lane proposal 的执行预算都通过 typed result 显式
传播到 `SequenceSolution.search_budget_exhausted`；任何阶段的静默截断都不能形成 resolved
geometry。

Partial auto count 从允许的较大 count 向较小 count 求解。XPAN 和 120-66 可由 physical trait
包含 nominal count，以表达完整胶片未铺满片夹。`GeometryResolution` 只有在 count、placement、
coverage 和实质替代解均已解决时才 supported；CandidateGate PASS 不能替代这一结论。

### 1.6 Evidence、Assessment 与 Selection

`CandidateGeometry` 是唯一 candidate geometry union：标准 strip 使用 `SequenceSolution`；
dual-lane 使用带有独立 lane solutions 的 `DualLaneSolution`；不支持自动求解的 mode 使用
`ReviewOnlyGeometry`，其 solved frame geometry 必须为空。三者分别进入 standard、dual-lane 和
review-only assessment，不以空字段伪装成另一种物理状态。Dual-lane 的 composition proof 要求
每条 lane 的 CandidateGate 与 GeometryResolution 都成立。

Candidate evidence 包括 topology、frame coverage、separator sequence、photo dimensions、
content preservation、holder occupancy、sequence conservation 和 evidence independence。

`FrameDimensionPrior` 只约束搜索。只有独立 photo-edge measurement 才能形成
`FrameDimensionEvidence`。Content run 数量只做 guidance/diagnostic，不能证明 frame count。
全局 content span 与局部 frame coverage 冲突时保持 unavailable，不能由任一侧单独宣告
preserved 或 undercrop。

`EvidenceQuality` 保存 supported、contradicted、unavailable 项和物理 residual。系统没有
scalar confidence、weighted score、confidence cap 或 confidence gate。

Selection 使用确定性顺序：

1. 最大化真实内容覆盖。
2. 最小化明确物理矛盾。
3. 优先 resolved independent proof。
4. Partial auto 优先较大 count。
5. 最小化 dimension、conservation 和 boundary residual。
6. 使用稳定 source order 收尾。

Geometry consensus 由对应 `PhotoInterval` 和 cut uncertainty 是否相交决定，不使用固定百分比
clustering tolerance。

### 1.7 Gate、Output Protection 与 Finalization

`CandidateGate` 只检查 topology、content preservation、measured photo geometry、sequence
conservation、evidence independence 和 proof paths。

`DecisionGate` 只消费 CandidateGate、GeometryResolution、selection consensus、output
protection 和 transform geometry。它不重新测量 evidence，也不生成候选。

`FrameBleedPlan` 为每个 frame 分别记录 leading、trailing 和 short-axis bleed：

- 用户 `--bleed*` 是每侧输出偏好。
- 只有 independently observed 或 independent-constraint corroborated overlap 才增加相邻两张
  frame 的对应侧。
- 全局最大 overlap 不扩张无关 frame。
- Geometry overlap hypothesis 产生 unresolved output protection，不产生自动 bleed。
- Finalization clamp 到 `CropEnvelope` 和 canvas，不读取 gray/content/separator。

### 1.8 Report、Debug 与 Cache Reuse

Current report identity：

```text
schema_id: detection_report
schema_revision: physical_sequence_resolution
```

Canonical sections：

- `input`: TIFF profile 与 `ScanCalibration`。
- `configuration`: 当前 `DetectionConfiguration` read model。
- `selection`: candidates、typed candidate geometry、evidence、`EvidenceQuality`、CandidateGate、
  GeometryResolution 和 clusters。
- `decision`: status、`final_review_reasons` 和 DecisionGate。
- `output`: decision/final geometry、`FrameBleedPlan` 和写出结果。
- `diagnostics`: transform evidence 与 detection diagnostics。

同一事实不再同时投影为顶层 alias、candidate table 和 evidence summary。Cache reuse 只接受该
schema 与完全匹配的 source/configuration fingerprint；旧 record 直接重新检测。Debug Analysis
保持 original gray、debug boxes、separator evidence 三联图。

## 2. 源码分层 / Source Layers

### 2.1 Top-Level Packages

| Layer | Canonical responsibility |
|---|---|
| `x5crop.entry` | CLI 与 interactive parsing。 |
| `x5crop.runtime` | Bootstrap、workflow、workers、reuse 和 output side effects。 |
| `x5crop.formats` | Format identity 与真实 physical spec。 |
| `x5crop.configuration` | 全局 measurement parameters、execution budgets 和 runtime assembly。 |
| `x5crop.cache` | Exact count-independent root measurement cache。 |
| `x5crop.geometry` | Box/profile 等纯几何算法。 |
| `x5crop.image` | Gray、adaptive statistics、deskew 和 pixel transforms。 |
| `x5crop.io` | TIFF read/write。 |
| `x5crop.detection` | Typed physical proposal、solve、evidence、assessment、selection 和 decision。 |
| `x5crop.output` | `FrameBleedPlan` 与 output geometry。 |
| `x5crop.export` | Crop/review TIFF 写出。 |
| `x5crop.report` | Current read model、validation、restoration 和 outputs。 |
| `x5crop.debug` | 三联 Debug Analysis 的纯渲染。 |
| `tools` | Contract tests、current-schema diff 和 standalone build。 |

### 2.2 Detection Sublayers

| Sublayer | Authority |
|---|---|
| `context` | `DetectionRequest` / `DetectionContext`。 |
| `physical` | Boundary、separator constraints、photo dimensions、spacing 和 global solver。 |
| `guidance` | Content-derived hints；不创建 sequence geometry。 |
| `candidate.plan` | Count descriptors and execution plan only。 |
| `candidate.proposal` | Sequence hypotheses。 |
| `candidate.build` | Hypothesis + measurements -> `BuiltCandidate`。 |
| `evidence` | Typed physical measurements；不 gate、不 decision。 |
| `candidate.assessment` | `EvidenceQuality`、proof paths 和唯一 CandidateGate。 |
| `candidate.execution` | 串联 plan/proposal/build/assessment。 |
| `candidate.selection` | Deterministic ordering、clusters 和 GeometryResolution。 |
| `modes` | Standard、dual-lane、review-only composition。 |
| `decision` | 唯一 DecisionGate 和 `FinalDetection` factory。 |
| `final` | 只应用 frame-side output geometry。 |

Dependencies only flow forward through this lifecycle. Foundation does not know format/mode,
configuration registry, gate, decision or schema. Report/debug may read final typed models but
cannot import detection computation.

### 2.3 Parameter Ownership 与 Cache

每个运行参数和模块级数值常量必须且只能属于一个 canonical role：

| Role | Ownership |
|---|---|
| `physical_fact` | mm、count、layout 和 occupancy 等真实物理规格。 |
| `standard_transform` | luma 和单位换算等标准变换。 |
| `adaptive_measurement` | quantile、采样支持、平滑和 minimum samples。 |
| `numerical_safety` | epsilon 和数值 clamp；不得改变物理语义。 |
| `execution_budget` | observation、solver、deskew 和 worker 的有限计算量。 |
| `user_preference` | bleed、deskew 范围和显式运行选项。 |
| `diagnostics_only` | Debug 渲染；不得反向进入 detection。 |

Physical proof、candidate ordering 和 Gate 不使用 format-family profile、weighted score、scalar
confidence 或 overlap capacity。真实样片阈值校准属于后续独立项目。

`MeasurementCache` 只缓存 exact root measurements，key 包含所有影响结果的参数和 box。它不
缓存 candidate、gate、decision、final reasons 或 approximate geometry。

### 2.4 Enforcement

`tools/tests` 使用 AST 与行为契约检查：模块可达、唯一归层、单向依赖、current schema、显式
参数、零孤儿、零重复 model 和禁止旧 vocabulary。发现残余时先增加失败契约，再删除整类
根因。冻结验收定义见 `AGENTS.md`。
