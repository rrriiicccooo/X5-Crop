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
  -> physical evidence + CandidateGate
  -> AssessedCandidate.evidence_quality
  -> GeometryResolution + deterministic selection
  -> FrameBleedPlan
  -> DecisionGateAssessment
  -> finalization -> FinalDetection
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
| GeometryResolution | 唯一 early-stop 输入；确认 count、placement、content compatibility 和替代几何已解决。 |
| Selection | 按物理目标确定性排序并聚合区间等价解。 |
| FrameBleedPlan | 把用户 bleed 与逐 boundary 的物理叠片保护转换为逐 frame-side 输出计划。 |
| DecisionGate | 唯一创建 `DecisionGateAssessment`、最终 status 和 `final_review_reasons`。 |
| Finalization | 只应用 `FrameBleedPlan` 和 bounds clamp，并创建 `FinalDetection`；不重新检测。 |
| Report / Debug | 只读 typed final results；不补算事实、不参与裁决。 |

`SelectionResult`、`DecisionGateAssessment` 与 `FinalDetection` 是三个独立生命周期结果：selection 拥有候选、
evidence 和 geometry resolution；decision gate assessment 直接拥有 checks、status 和 final reasons；typed `FinalizationPlan` 拥有
layout、图像尺寸、decision geometry 与 `FrameBleedPlan`，final detection 只保存该 plan 的确定性
输出。Report 与 Debug 显式接收所需 typed result，不存在 cache-only optional 字段。

`x5crop.image.deskew` 只生成 immutable line-fit / angle measurements 并计算 measurement
quality。Base/fallback 是否启用及二者择优归 runtime preprocess 编排；foundation 不接收运行模式
字符串，也不产生可变 detail 字典。

### 1.2 Runtime Configuration

Runtime 从 `FormatPhysicalSpec + strip_mode` 创建唯一
`DetectionConfiguration`。它包含：

- 真实 frame mm、derived aspect、允许 count、physical layout 和 holder occupancy traits。
- 全局 adaptive image measurement 参数。
- candidate/observation execution budgets。
- diagnostics configuration。

Format 名字只用于 physical spec lookup，不拥有算法分支或独立参数 profile。Dual-lane
detector kind 是由 `physical_layout + strip_mode` 推导的 property，不作为重复 configuration
字段存储。Lower layers 只接收显式 configuration 子对象、
physical spec 或普通参数对象，不反查 registry。
`FormatPhysicalSpec` 只保存检测实际消费的 count、layout、occupancy trait 与 mm size options；
不保存 family、role、notes 或 frame-size label 等 report-only 描述。Mm size 只有一个
options tuple 事实源，其首项确定 nominal size。Runtime configuration bundle 也只保存一个
resolved tuple，initial configuration 由首项派生，registry 不维护隐藏进程缓存。

`DetectionContext` 只包含 calibration、检测请求、已解析 configuration 与 measurement cache；
TIFF `ImageProfile` 停留在 runtime/I/O/output 数据流，不下沉到 detection。
Request mode、configuration mode、workspace layout、cache layout 与 dual-lane child configuration
在 context 构造边界必须一致；未知 layout 不会被静默解释成 vertical。

### 1.3 Boundary、Sequence 与 Outer

旧 generic outer 已被三个不同物理概念替代：

| Type | Meaning |
|---|---|
| `HolderSpan` | 片夹可用范围。 Holder geometry only. |
| `VisibleSequenceSpan` | 源图中实际可见的照片序列范围。 |
| `CropEnvelope` | 覆盖所有可见内容与 boundary uncertainty 的基础裁切包络；不包含用户 bleed。 |

每条边使用自己的 edge reference、scan direction 和 robust change-point measurement，独立测量
white-holder、tonal、texture 或 canvas boundary interval。Base boundary 不合并相对两端的
tonal identity，也不假设照片一定有黑边；左白右黑、上白下黑等四边混合状态都可成为观测。
Full canvas 只能作为保守 envelope，不能成为 count 或 boundary proof。

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
overlap bleed；corroborated overlap 也不能回头支持 sequence conservation。每个 spacing 的
`kind` 由 signed interval 唯一推导，不能以独立字符串声明出相互矛盾的物理状态。Spacing、
separator evidence 和 output protection 使用同一个 `FrameBoundaryReference`；dual-lane 的
lane identity 不能被展平丢失。

### 1.5 Global Sequence Solver 与 Auto Count

Sequence solver 同时求解所有内部 boundaries，不逐边贪心：

- `PhotoInterval` 和 cuts 必须严格单调，不能产生零宽、负宽或倒序 frame。
- Interior photos 服从同一 `FrameDimensionPrior` option。
- White-holder observation 只生成有界 `HolderOcclusionConstraint` 以放宽搜索，不是遮挡证据。
  Solver 先在该约束下确定单调 frame boundaries，再从首尾 boundary 与可见宽度
  生成 `HolderOcclusionEvidence`，最后构建 signed spacing。Reason 文本不能控制物理分配。
- Holder occlusion 只能作用于首张 leading edge 和末张 trailing edge。
- 已确认遮挡的首尾可见宽度不参与普通 photo-dimension contradiction；尺寸一致性只使用未遮挡、
  independently observed 的 frame。
- 单张照片两端同时接白色片夹时，`combined_hidden_width_px` 保存总遮挡区间；leading/trailing
  分配保持 unavailable，不能把同一缺失宽度计算两次。
- Holder occlusion state、side 与 hidden-width interval 必须一致；无交集的 boundary constraints
  是无解状态，不能用合成中点继续求解。
- Position、width、sequence conservation 和 provenance 必须同时成立。
- `SequenceSolution` 在构造边界交叉验证 frames、photo indexes、boundaries、assignments 和
  spacing references；不同事实投影不能漂移。
- 同一 span/count 下所有最大独立-anchor 解都参与 `BoundaryAssignmentConsensus`；不同解的
  cut interval 没有共同交集时，assignment geometry 保持 unresolved。
- Search budget exhausted 时 geometry 保持 unresolved。

Observation、hypothesis、assignment 和 dual-lane proposal 的执行预算都通过 typed result 显式
传播到 `SequenceSolution.search_budget_exhausted`；任何阶段的静默截断都不能形成 resolved
geometry，实际返回的 observation/proposal 数也不得超过声明的预算。

Partial auto count 从允许的较大 count 向较小 count 求解。XPAN 和 120-66 可由 physical trait
包含 nominal count，以表达完整胶片未铺满片夹。`GeometryResolution` 只有在 count、placement、
content preservation compatibility 和实质替代解均已解决时才 supported；CandidateGate PASS
不能替代这一结论。
片夹 occupancy 只由 holder/visible spans 和正向物理证据派生，用户选择的 full/partial mode
不能改写同一几何的 filled/underfilled 状态。
一旦最高的 physically resolved count 出现，最终 candidate pool 只包含该 count 的候选；此前
已评估但 unresolved 的较大 count 保留在 count audit detail 中，不能重新赢回 selection。

### 1.6 Evidence、Assessment 与 Selection

`CandidateGeometry` 是唯一 candidate geometry union：标准 strip 使用 `SequenceSolution`；
dual-lane 使用带有独立 lane solutions 的 `DualLaneSolution`；不支持自动求解的 mode 使用
`ReviewOnlyGeometry`，其 solved frame geometry 必须为空。三者分别进入 standard、dual-lane 和
review-only assessment，不以空字段伪装成另一种物理状态。`DualLaneSolution` 不复制展平的
lane observations 或 boundaries；全局 frames、envelope、residuals 和 assignment consensus 只能
由 lane solutions 确定性派生。Dual-lane 的 composition proof 要求每条 lane 的 CandidateGate 与
GeometryResolution 都成立。

Geometry 不保存重复的 candidate-source string。Geometry type、automatic-processing eligibility、
sequence strategy 与 measurement provenance 共同表达其物理身份。

Candidate evidence 包括 topology、frame coverage、separator sequence、photo dimensions、
content preservation、holder occupancy、sequence conservation 和 evidence independence。
直接进入 CandidateGate 的 topology、preservation、dimensions、conservation 与 independence
在 typed model 边界重算 state/derived measurements；state 不能与 raw physical facts 漂移。
Topology 显式区分 sequence、lane composition 与 unmeasured scope；dual-lane measurement root
保留 lane identity 后再聚合。

`FrameDimensionPrior` 只约束搜索。只有独立 photo-edge measurement 才能形成
`FrameDimensionEvidence`。Content run 数量只做 guidance/diagnostic，不能证明 frame count。
全局 content span 与局部 frame coverage 冲突时保持 unavailable，不能由任一侧单独宣告
preserved 或 undercrop。

Content 是保护性反证，不是 hard physical proof 的许可机关。明确的 uncovered content 会
contradict；content measurement unavailable 不会否决完整 separator/geometry proof。Partial auto
count 仍要求正向 frame coverage 才能声明 count resolved。

`CandidateAssessment` 只保存 canonical evidence 与 CandidateGate。
`AssessedCandidate.evidence_quality` 从 evidence、proof paths 和 geometry residuals 确定性派生；
selection 与 report 只读取该 canonical property，不维护第二事实源或反向调用 assessment。
系统没有 scalar confidence、weighted score、confidence cap 或 confidence gate。

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
`GateCheck` 只表达所属 stage 与 evidence state；所有 check 都是该 Gate 的正式检查，不再保留
未使用的 consequence 维度。Candidate check 不能拥有 final reason，diagnostic 也不能伪装成
GateCheck。

`DecisionGate` 只消费 CandidateGate、GeometryResolution、selection consensus、output
protection 和 transform geometry。它不重新测量 evidence，也不生成候选。
显式 review-only mode、CandidateGate 物理失败、count resolution、geometry resolution 与
selection disagreement 分别拥有自己的 final reason；下游派生检查在上游根因失败时为
`not_applicable`，不重复制造 REVIEW reasons。
最终 reason vocabulary 由 `detection.decision` 独占；项目没有跨层全局 constants bucket。
DecisionGateAssessment 在构造时拒绝 vocabulary 之外的 final reason。

`FrameBleedPlan` 为每个 frame 分别记录 leading、trailing 和 short-axis bleed：

- 用户 `--bleed*` 是每侧输出偏好。
- 每张 frame 的 `frame_output_bounds` 来自 holder canvas 或所属 lane，不复用物理
  `CropEnvelope` 充当输出上限。
- 只有 independently observed 或 independent-constraint corroborated overlap 才增加相邻两张
  frame 的对应侧。
- 全局最大 overlap 不扩张无关 frame。
- Geometry overlap hypothesis 产生 unresolved output protection，不产生自动 bleed。
- Finalization 在 `frame_output_bounds` 内应用 bleed，生成实际 final envelope；它不读取
  gray/content/separator，也不修改 decision geometry。
- `FinalDetection` 在构造时使用同一 `FinalizationPlan` 重算 output geometry；任意扩张、
  第二 factory 或与 plan 不一致的持久化结果都会被拒绝。

Transform evidence、output protection、user bleed 与 final geometry 都在 typed model 边界验证派生
状态；`applied` angle、span pair、feasible、reason 和 unresolved boundaries 不能彼此矛盾。

### 1.8 Report、Debug 与 Cache Reuse

`ImageProfile` 由 `x5crop.io` 独占，是 TIFF I/O 边界创建的 immutable typed input contract。
TIFF rational、enum 和 NumPy scalar 等库特有值在该边界归一化为普通 Python scalar/tuple；
calibration 只接收 resolution 与 unit，cache、report 和 export 不再解析底层 TIFF tag 形状。

Current report identity：

```text
schema_id: detection_report
schema_revision: physical_sequence_resolution
```

Canonical sections：

- `input`: TIFF profile、`ScanCalibration` 与 preprocess transform geometry。
- `configuration`: 当前 `DetectionConfiguration` read model。
- `selection`: candidates、typed candidate geometry、evidence、`EvidenceQuality`、CandidateGate、
  GeometryResolution 和 clusters。
- `decision`: status、`final_review_reasons` 和 DecisionGate。
- `output`: canonical `FinalizationPlan`、final geometry 和写出结果。

同一事实不再同时投影为顶层 alias、candidate table 和 evidence summary。Cache reuse 只接受该
schema 与完全匹配的 source/configuration fingerprint；source identity 包含文件内容 SHA-256，
同一次运行的 lookup 和 report 写入共用同一个 canonical signature。旧 record 或内容不同的同名
文件直接重新检测。Cache restoration 只恢复 DecisionGate 与 typed finalization plan，然后调用
同一 finalization factory 并核对持久化 geometry；它不反序列化 candidate selection。任何 Debug
Preview/Analysis 请求都会执行完整 detection；cached export 只重放必要的
像素 transform，不重建 gray/evidence/configuration。Debug Analysis 保持 original gray、debug
boxes、separator evidence 三联图。
Current validator 精确校验 `GeometryResolution` 字段；旧字段形状即使使用相同 schema identity
也会被拒绝并重新检测。所有 typed result 由 canonical dataclass 结构递归校验，report 自有投影
也使用精确字段集合；configuration、selection、decision 与 output 共用唯一 typed projection，
不再经过第二套通用序列化。任何层级的额外 alias、旧字段或未知 section 都会使 record 失效。
Runtime 对外只传递 report-owned `ReportResult`；它在构造时验证 current schema。共享 domain
不保存 report record、TIFF profile 或用户 bleed 偏好，后者由 `x5crop.output` 独占。

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

Measurement cache 使用 immutable named key：参数身份、精确 `Box` 与可选 threshold 分别占有
明确字段；cache 不使用 `Any` key、位置 tuple、candidate identity 或近似 geometry。
Root measurement arrays 必须使用同一 validated workspace layout 与 shape。Region 在建 key 前只
canonicalize 一次，key 与实际 pixels 必须一致；与 workspace 无交集的 region 直接拒绝。

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
| `candidate.assessment` | Canonical evidence、proof paths 和唯一 CandidateGate。 |
| `candidate.execution` | 串联 plan/proposal/build/assessment。 |
| `candidate.selection` | Deterministic ordering、clusters 和 GeometryResolution。 |
| `modes` | Standard、dual-lane、review-only composition。 |
| `decision` | 唯一 DecisionGate assessment、status 和 final reason owner。 |
| `final` | 只应用 frame-side output geometry，并创建 `FinalDetection`。 |

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
