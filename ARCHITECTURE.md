# X5 Crop 架构说明 / Architecture Guide

本文件只描述当前 V4.9 的运行流、权限边界与源码分层。用户操作见 `README.md`，
版本变化见 `CHANGELOG.md`，长期协作规则见 `AGENTS.md`。

This document is the canonical description of the current V4.9 runtime flow,
authority boundaries, and source layers. It does not duplicate user instructions,
release history, or task status.

## 1. 固定运行流 / Fixed Runtime Flow

```text
entry：CLI / interactive parsing
  -> runtime：TIFF I/O + resolved DetectionConfigurationBundle
  -> detection：原图短轴路径观测
  -> SharedShortAxisPlan（每条 lane 一份）
  -> detection：TransformGeometryEvidence
  -> image：通用像素仿射变换
  -> DetectionWorkspace（同一短轴计划和 lane divider 的坐标映射）
  -> detection：长轴观测、frame sequence、CandidateGate、selection
  -> detection.output_preparation：FrameBleedPlan
  -> detection：DecisionGate
  -> detection.final：finalization plan + FinalDetection
  -> runtime/output：TIFF export / report / Debug Analysis
```

Deskew 是 detection 的强制第一阶段，不是可选的图像预处理功能。Runtime 只编排 TIFF、
配置、并发与写出副作用；它不判断角度、不拥有边缘模型，也不重新解释检测结果。

Deskew is a mandatory first detection stage, not an optional image-preprocessing
feature. Runtime orchestrates I/O and side effects but owns no transform decision
or geometry.

### 1.1 权限表 / Authority Table

| Owner | 唯一职责 / Sole responsibility |
|---|---|
| `entry` | 解析公开输入；不存在 deskew 开关或阈值入口。 / Parse public input; expose no deskew controls. |
| `runtime` | 解析一次配置、读取 TIFF、调用 detection、写出产物。 / Resolve configuration once, perform TIFF I/O, call detection, write artifacts. |
| `detection.workspace` | 原图短轴观测、transform 判断、坐标映射和 `DetectionWorkspace`。 / Own source short-axis observation, transform assessment, coordinate mapping, and workspace construction. |
| `SharedShortAxisPlan` | 上下真实照片边缘与唯一共享短轴。 / Own the two real photo edges and the sole shared short axis. |
| `TransformGeometryEvidence` | 唯一 transform outcome、测量和仿射映射。 / Own the single transform outcome, measurements, and affine map. |
| `image` | 灰度、统计和通用像素变换；不知道 detection 语义。 / Provide gray/statistical and generic pixel operations without detection semantics. |
| `DetectionWorkspace` | 保证 pixels、gray、cache、transform 与 mapped geometry 位于同一坐标域。 / Keep pixels, gray, cache, transform, and mapped geometry in one coordinate domain. |
| physical solver | `solve_frame_sequence` 消费既有共享短轴，只求长轴 frame sequence。 / Consume the prepared short axis and solve only the long-axis sequence. |
| `CandidateGate` | 判断一个候选的物理证明是否成立。 / Assess one candidate's physical proof. |
| selection | 确定性选择物理解并保留替代解关系。 / Select geometry deterministically and retain alternatives. |
| GeometryResolution | 唯一 early-stop 输入；判断几何、搜索与替代解是否已解决。 / Sole early-stop authority for geometry, search, and alternatives. |
| `DecisionGate` | 唯一创建 final status 与 final reasons。 / Sole creator of final status and final reasons. |
| report / debug | 只读 typed results；不测量、不补算、不裁决。 / Read typed results only; never measure, infer, or decide. |

权限始终单向流动。`CandidateGate` 和 `DecisionGate` 是仅有的两个 Gate；只有
`GeometryResolution.supported` 可以触发候选搜索 early-stop，只有 `DecisionGate` 可以创建
`approved_auto` 或 `needs_review`。

## 2. Detection 所有的共享短轴 / Detection-Owned Shared Short Axis

### 2.1 原图观测 / Source Observation

Detection 先在原始灰度坐标系测量短轴路径。每条可用照片带必须同时存在：

- `top_photo_edge`：上边界照片侧的 inner line；
- `bottom_photo_edge`：下边界照片侧的 inner line；
- 连续的照片内侧 appearance；
- 相对整幅灰度动态范围足够的照片/外侧强度跨度；
- 在每个共同截面中与 holder transition 保持独立的尺度化测量间隔；
- 覆盖整条共享裁切域的共同长轴证据和足够的 path samples；
- 合格的 line-fit residual；
- 一致的两条 inner-line slope。

扫描画布外沿、holder transition、空白区域和单边缘都不能生成 resolved shared short axis。
Holder observations 只服务 containment 与 provisional review。无法唯一选出真实双边缘时，
计划保持 typed unresolved；不存在安全坐标的伪造回退。

Scan extrema, holder transitions, empty regions, and single-edge observations
cannot resolve the shared short axis. A photo edge must have scale-adaptive tonal
separation and remain spatially independent from a holder transition across their
shared samples. Scoring may choose a representative only inside one overlapping
physical edge-pair hypothesis; distinct pair hypotheses remain unresolved. Holder
evidence remains containment-only. Automatic shared-crop safety requires common
edge support across the complete long-axis crop domain; partial support remains a
review candidate and is never extrapolated into an auto-safe strip-wide boundary.

### 2.2 唯一模型 / Sole Model

`SharedShortAxisPlan` 是共享短轴唯一模型：

```text
top_photo_edge: GrayBoundaryPathObservation | None
bottom_photo_edge: GrayBoundaryPathObservation | None
span: ShortAxisMeasurementSpan | None
search_outcome: PhysicalSearchOutcome
provenance: MeasurementProvenance
```

当且仅当两条真实照片边缘形成有效 inner-line span 时，`span` 才存在。照片高度、安全性和
不确定度都由这一个 span 派生。每个 `FrameSlot`、separator cross-axis measurement、
`FrameCropEnvelope` 和最终框都消费这同一计划；后续 detection 不得再次求解短轴。

The span exists only when two real photo edges form a valid inner-line interval.
Height, safety, uncertainty, frame crops, and cross-axis measurements derive from
that one plan. No downstream stage re-detects it.

### 2.3 Transform outcome

两条 inner-line slope 的共同估计决定角度。`TransformGeometryEvidence` 只有以下 outcome：

| Outcome | State | Meaning |
|---|---|---|
| `photo_edges_unavailable` | unavailable | 没有完整真实双边缘。 |
| `insufficient_common_support` | unavailable | 双边缘存在，但共同覆盖或 samples 不足。 |
| `edge_slopes_disagree` | contradicted | 两条边或两 lane 的 slope 冲突。 |
| `edge_fit_high_residual` | contradicted | inner-line fit residual 过高。 |
| `identity_within_tolerance` | supported | 双边缘成立，倾斜在 identity 容差内。 |
| `deskew_applied` | supported | 双边缘成立并已应用校正。 |
| `angle_out_of_range` | contradicted | 所需校正超出可信范围。 |

只有两个 supported outcome 能通过 transform 的 DecisionGate check。失败 outcome 的角度为
`None`，不能以 `0°` 伪装成功。阈值只存在于 `DetectionConfiguration.deskew` 的 typed
`DeskewDetectionParameters` 中；它们没有 CLI、interactive 或 runtime fallback 表面。

### 2.4 仿射映射 / Affine Mapping

`image.rotate_array_expand` 只执行通用 expanded rotation，并同时返回唯一的
`AffineCoordinateTransform`。Detection 使用该对象映射：

- 每条边缘的 samples 和 fitted interval；
- `SharedShortAxisPlan`；
- dual-lane divider 与 lane boxes；
- 后续在 workspace 中产生的 frame envelopes 和 final boxes。

旋转后的 workspace 不重新测量短轴。Identity outcome 保留原坐标；applied outcome 对像素和
所有几何使用完全相同的 matrix 与 expanded offset。仿射插值的不确定度进入 mapped path，
不会成为可靠性证据。

### 2.5 Dual lane

`135-dual` 先在原图坐标系唯一解析 lane divider，再在两条 source lane 内分别生成
`SharedShortAxisPlan`。两 lane 都必须拥有真实双边缘，且四条 inner line 的 slope 一致，才可
应用一个全局 transform。Divider 和两份计划随后一起映射。Divider 缺失、多解、任一 lane
缺边或角度冲突都保持 REVIEW；不存在逐 lane 独立旋转或 runtime 旁路。

## 3. DetectionWorkspace 与配置 / Workspace And Configuration

`DetectionWorkspace` 集中持有：

```text
transformed pixels
source gray + workspace gray
exact MeasurementCache
source SharedShortAxisPlan tuple
mapped SharedShortAxisPlan tuple
source/mapped lane divider
TransformGeometryEvidence
WorkspaceIdentity
```

它验证 cache 使用当前 canonical gray，且 source/mapped plans 与 dividers 一一对应。
`DetectionContext` 只接受这一个 workspace；standard 与 dual-lane pipeline 都直接消费已映射计划。
Solver 合同测试可以显式构造 typed workspace fixture，但 production runtime 没有绕过
`prepare_detection_workspace` 的路径。

Runtime 由 `FormatPhysicalSpec + strip_mode` 解析唯一 `DetectionConfiguration`。Format spec、
adaptive measurements、execution budgets、diagnostics 与用户偏好彼此分离。Lower layers 只接收
显式 typed inputs，不查询 registry，也不生成默认值。

每个数值参数必须属于一个且仅一个正式角色：`physical_fact` 表示格式物理事实；
`standard_transform` 表示固定的标准色彩/坐标变换；`adaptive_measurement` 表示由当前图像
归一化的测量规则；`numerical_safety` 只防止数值退化；`execution_budget` 只限制工作量；
`user_preference` 只控制输出偏好；`diagnostics_only` 只影响审计可视化。角色不能互相充当
物理证据，尤其 budget、preference 与 diagnostics 永远不能提升可靠性。

`MeasurementCache` 只缓存 exact、count/offset-independent measurements：图像统计、长轴 raw
paths、separator profiles/bands 与 content observations。它不缓存 plan、candidate、Gate、
selection、decision 或 approximate geometry。Source/workspace gray 与 transform uncertainty
属于 cache identity。

## 4. 长轴与最终决策 / Long Axis And Final Decision

### 4.1 Frame sequence

准备完成后，detection 只在 workspace 求长轴：

1. 长轴 raw paths、holder containment、separator bands 与 content observations；
2. count hypotheses 与 `FrameDimensionPrior`；
3. global frame-sequence construction、assignment、common-width resolution 与 completion；
4. `FrameSequenceSolution`、candidate evidence 和 `CandidateGate`；
5. deterministic selection 与 `GeometryResolution`。

`FrameSlot` 必须正宽、单调且不交叉。稳定照片宽度是主要物理约束；separator 宽度和 signed
spacing 可以变化。Measured boundary 与 geometry-derived boundary 是不同事实，后者不能给自己
增加独立 proof。Content 只能反证遗漏，不能创造 count、边界或 blank slot。Full sequence 最多
允许一个由完整物理序列唯一推导的 blank slot；partial 不得用空白区域增加 count。

Execution budget 只限制搜索量。Budget exhaustion 是 unavailable geometry，绝不是可靠性信号。

### 4.2 Output 与 Gate

```text
FrameSlot long-axis interval
  x mapped SharedShortAxisPlan.span
  -> FrameCropEnvelope
  -> FrameBleedPlan
  -> finalization plan
  -> DecisionGate
  -> FinalDetection / optional TIFF export
```

`CandidateGate` 检查 candidate-local 物理证明。`GeometryResolution` 单独确认 count、slots、
共享短轴、content conservation、搜索完整性与替代解。`DecisionGate` 再消费 selected gate、
geometry resolution、selection consensus、bleed feasibility 和 transform state；任何 transform
失败都阻止 auto PASS。Bleed 与 finalization 只应用已决定的几何，不反向改变 evidence。

## 5. Report、Debug 与人工权威 / Audit Surfaces

Current report schema：

```text
schema_id: detection_report
schema_revision: detection_owned_shared_short_axis
```

`input` 记录 source 上下边缘 observation IDs/coordinates、mapped plans、单一 transform outcome、
物理命名的 `projected_edge_drift_px` / `identity_drift_threshold_px`、
`AffineCoordinateTransform`、lane divider 和 workspace identity。`configuration` 只记录当前 typed
configuration；`selection`、`decision` 与 `output` 分别保留各自权限。旧 `measurement_outcome`、
`span_px`、`span_threshold_px`、fallback、disabled 或 compatibility 字段无效，旧 schema 不被解析。

Report 与 Debug Analysis 都是只读审计产物。Debug 展示 mapped frame geometry 和当前 evidence；
人工 deskew 审阅图绑定冻结 survey 的 source/mapped typed facts；重建图时若 production
workspace 与 survey 任一事实不完全相同即失败，绝不由图像工具另算一套几何。

`manual_baseline.jsonl` 是人工裁切权威。旧 frame-slot reference 与 sample expectation 只用于
追踪和测试 seed，不能提升为人眼确认，也不能写回 baseline。它们的 source-pixel interval 进入
current report 比较前，必须先经该 report 的同一 `AffineCoordinateTransform` 映射；禁止直接
混比 source/workspace 坐标。人工 deskew 历史的 rejection 与新一轮 pending review 分层保存：
历史结论用于审计，新模型候选在用户确认前始终是 pending。

## 6. 源码分层 / Source Layers

| Layer | Canonical responsibility |
|---|---|
| `x5crop.entry` | CLI、interactive parsing 与用户消息。 |
| `x5crop.runtime` | Bootstrap、workflow、workers、manifest 与 I/O side effects；无几何所有权。 |
| `x5crop.formats` | Format identity 与物理规格。 |
| `x5crop.configuration` | Typed detection、transform、solver、output 与 diagnostics 参数。 |
| `x5crop.cache` | Exact measurement cache 与 lookup statistics。 |
| `x5crop.geometry` | Box/layout/sampling 与通用 `AffineCoordinateTransform`。 |
| `x5crop.image` | Gray、statistics、content/evidence images 与通用 pixel transforms。 |
| `x5crop.io` | TIFF read/write、profile 与 metadata preservation。 |
| `x5crop.detection.workspace` | Source short-axis detection、transform assessment、mapping、workspace preparation。 |
| `x5crop.detection.physical` | Typed observations、`SharedShortAxisPlan`、frame dimensions 与 sequence solver。 |
| `x5crop.detection.evidence` | Typed evidence，包括单一 transform outcome；不 Gate、不 decision。 |
| `x5crop.detection.output_preparation` | 将 selected detection evidence 单向翻译成 `FrameBleedPlan`。 |
| `x5crop.detection.candidate` | Proposal、build、assessment、execution 与 selection。 |
| `x5crop.detection.decision` | `DecisionGate` 与 final reason vocabulary。 |
| `x5crop.detection.final` | Finalization plan 与 `FinalDetection` assembly。 |
| `x5crop.output` | Bleed、crop envelopes 与 side-effect-free output plans。 |
| `x5crop.export` | Output paths 与 validated TIFF export orchestration。 |
| `x5crop.report` | Current-schema serialization、identity 与 validation。 |
| `x5crop.debug` | Read-only visualization。 |
| `tools.tests` | Physical、schema、layer、metadata 与 no-residue contracts。 |
| `tools.regression` | Current-schema comparison 与人工 reference validation。 |

依赖方向是 `entry/runtime -> detection -> geometry/image/cache`，report/debug 只消费上游结果。
Foundation code 不知道 format identity、Gate、decision 或 report schema。新增概念必须有一个名称、
一个 typed owner 和一个真相来源；被替代的 API、字段、别名、包装层与测试在同一变更中删除。
