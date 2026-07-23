# X5 Crop 架构说明 / Architecture Guide

本文件是当前 V4.9 运行流、权限边界和源码分层的唯一架构说明。用户操作见
`README.md`，版本变化见 `CHANGELOG.md`，长期协作规则见 `AGENTS.md`。

This document is the canonical description of the current V4.9 runtime flow,
authority boundaries, and source layers. User instructions, release history,
and standing collaboration policy live in their respective canonical files.

## 1. 固定运行流 / Fixed Runtime Flow

```text
entry: CLI / interactive parsing
  -> runtime: TIFF I/O + resolved DetectionConfiguration
  -> detection: ScanCanvasEvidence
  -> CanvasPixelScale + theoretical PhotoEdgeSearchBand
  -> detection: source PhotoEdgePairEvidence
  -> detection: TransformGeometryEvidence
  -> image: generic expanded affine pixel transform
  -> detection: map the same photo-edge evidence
  -> DetectionWorkspace
  -> detection: SharedShortAxisPlan + long-axis observations
  -> solve_frame_sequence -> CandidateGate -> selection
  -> GeometryResolution -> output preparation
  -> DecisionGate -> finalization
  -> runtime/output: TIFF export / report / Debug Analysis
```

Deskew 是 detection 对照片边缘证据的一个强制消费者，不是可选预处理。单条片夹先识别
物理画布，再只在理论照片带附近观测真实像素；`135-dual` 先解 lane divider，并在各 lane
内用图像证据观测。仿射后只映射同一份边缘证据，不重新寻找短轴。

Deskew is a mandatory consumer of detection evidence, not an optional
preprocessing feature. A single-strip scan first resolves its physical canvas
and then observes pixels only near the theoretical photo band. `135-dual`
resolves its divider and observes each lane from image evidence. The affine
stage maps the same evidence; it never observes a second short axis.

### 1.1 权限表 / Authority Table

| Owner | 唯一职责 / Sole responsibility |
|---|---|
| `entry` | 解析公开输入；没有 deskew 开关或阈值入口。 / Parse public input; expose no deskew controls. |
| `runtime` | 解析一次配置、执行 TIFF I/O、调用 detection、写出产物。 / Resolve configuration once, perform TIFF I/O, call detection, and write artifacts. |
| `FramePhysicalSpec` | 保存照片尺寸事实及离散 `FrameSizeMm` 选项。 / Own photo dimensions and discrete frame-size options. |
| `ScanCanvasPhysicalSpec` | 保存片夹扫描画布尺寸及 format 兼容关系。 / Own scanned-holder canvas dimensions and format compatibility. |
| `ScanCanvasEvidence` | 根据 source 像素长短比选择零个、一个或多个兼容 profile。 / Match source pixel aspect to compatible canvas profiles. |
| `CanvasPixelScale` | 保存唯一的长轴与短轴 px/mm 尺度及 source 轴向。 / Own the sole long/short-axis px/mm scale and source-axis mapping. |
| `PhotoEdgePairEvidence` | 唯一照片上下边缘真相；保存候选、假设、事实和可选 selected pair。 / Be the sole truth for top/bottom photo-edge identity. |
| `TransformGeometryEvidence` | 表达 deskew 消费结果和唯一仿射映射。 / Own the deskew-consumer outcome and sole affine map. |
| `SharedShortAxisPlan` | 引用 mapped pair，表达整幅 workspace 共享短轴消费结果。 / Reference a mapped pair and assess strip-wide short-axis safety. |
| `image` | 灰度、统计与通用像素变换；不知道 format、deskew 或 decision。 / Provide gray/statistical and generic pixel operations without detection semantics. |
| `DetectionWorkspace` | 约束 source、mapped evidence、pixels、gray、cache 和 transform 的坐标域一致性。 / Enforce one coordinate-domain contract for pixels, gray, cache, transform, and evidence. |
| physical solver | `solve_frame_sequence` 消费既有短轴与尺度，只求长轴 frame sequence。 / Consume existing short-axis evidence and scale, then solve the long-axis sequence. |
| `CandidateGate` | 判断单个候选的物理证明。 / Assess one candidate's physical proof. |
| selection | 确定性选择并保留真实替代解关系。 / Select deterministically while preserving physical alternatives. |
| GeometryResolution | 唯一 early-stop 输入；判断几何、搜索与替代解是否已解决。 / Sole early-stop authority for geometry, search, and alternatives. |
| `DecisionGate` | 唯一创建 final status 与 final reasons。 / Sole creator of final status and final reasons. |
| report / debug | 只读 typed results；不测量、不重算、不裁决。 / Read typed results only; never measure, recompute, or decide. |

权限单向流动。理论几何只能约束搜索和反证，不能生成像素证据；评分不能在两个真实可行的
边缘对之间作身份裁决。`CandidateGate` 与 `DecisionGate` 是仅有的两个 Gate，只有
`DecisionGate` 可以创建 `approved_auto` 或 `needs_review`。

## 2. 物理画布与像素尺度 / Physical Canvas And Pixel Scale

照片事实与扫描画布事实必须分开：

- `FramePhysicalSpec` 只描述底片照片尺寸。120 的短轴是离散的 54 mm 或 56 mm，
  不存在 55 mm 平均选项。
- `ScanCanvasPhysicalSpec` 只描述扫描仪按片夹设置输出的物理画布。
- 配置层按 format 解析允许的 profile 集合；lower layer 不查询目录或制造默认值。

| Profile ID | 短轴 × 长轴 / Short × long | Formats |
|---|---:|---|
| `135_standard` | 32.22 × 232 mm | 135, half, xpan |
| `135_narrow` | 25.4 × 232 mm | 135, half, xpan |
| `120_standard` | 60 × 226 mm | 120-645, 120-66, 120-67 |
| `120_wide` | 63.44 × 224.5 mm | 120-645, 120-66, 120-67 |
| `120_66_three_frame` | 63.44 × 188.5 mm | 120-66 |

`ScanCanvasEvidence` 在 format 允许集合内，以原图工作坐标系的长短轴像素比匹配 profile，
最大相对误差固定为 0.5%：

- 唯一匹配：`supported`，产生一个 `CanvasPixelScale`；
- 无匹配：`aspect_contradicted`；
- 多个匹配：`competing_profiles_unresolved`；
- `135-dual`：`not_applicable`，不虚构统一物理画布或尺度。

`CanvasPixelScale` 只保存 `long_axis_px_per_mm`、`short_axis_px_per_mm` 和
`source_long_axis`。PPI 仅在可读 report 中由 `px/mm × 25.4` 即时展示；TIFF resolution
标签由 I/O 原样保存，但不参与 profile、尺度、证据、Gate 或 decision。

理论照片带只由一个公式产生：

```text
nominal margin = (canvas_short_mm - photo_short_mm) / 2
```

因此 135 的理论边距为 4.11 mm 或 0.70 mm；120 的 60 mm 画布为 3 mm 或 2 mm，
63.44 mm 画布为 4.72 mm 或 3.72 mm。它们只定义容许搜索域。理论位置没有真实像素支持时，
结果仍是 `photo_band_evidence_unavailable`。

## 3. 照片上下边缘证据 / Photo-Edge Pair Evidence

### 3.1 单条片夹的 pair-first 观测

```text
physical PhotoEdgeSearchBand
  -> per-section local top/bottom point pair
  -> common-slope pair track
  -> deterministic equivalent-track merge
  -> PhotoEdgeCandidate
  -> PhotoEdgePairHypothesis
  -> PhotoEdgePairEvidence
```

每个 cross-section 先形成局部上下点对，只保留与某个具体 profile、
`FrameSizeMm`、理论中心偏移和最大角度相容的点对，然后将上下两条路径共同连接。Track
至少跨 3 个独立 section，最多跨过一个缺失 section。局部转折点是生成期临时数据，不进入
report schema；没有 selected pair 时，report/debug 仍保留合并候选和 typed summary。

`PhotoEdgeCandidate` 保存路径、局部窗口、稳健拟合、观测区间和 physical band identity，
但不单独宣称 top 或 bottom。`PhotoEdgePairHypothesis` 才赋予角色并绑定具体
scan-canvas profile 与离散 frame option。`PhotoEdgePairEvidence` 是唯一边缘真相。

### 3.2 成立合同 / Qualification Contract

局部窗口状态只有：

- `supported`：边缘两侧至少一种灰度、纹理或梯度差异稳定超过局部噪声，极性不限；
- `neutral`：平滑照片、天空、黑场或 holder 重合不足以支持，也不构成否定；
- `contradicted`：照片内侧独立证据为空、越出 containment，或与成对几何冲突。

一个 pair 要成为 `supported`，必须同时满足：

- 每条边至少 5 个稳健 inlier，inlier ratio 至少 80%；
- 每条边至少 3 个 supported 窗口，并分布在 3 个诊断区段中的至少 2 个；
- 赋予角色后，top 下侧与 bottom 上侧的照片内侧结构必须分别在至少 3 个窗口、2 个区段中
  强于其外侧；强 holder 外沿不能仅凭 transition 幅度冒充照片边缘；
- 使用确定性的 Theil–Sen 初拟合、MAD 异常点识别和 inlier 重拟合；
- 上下 line 的 95% slope interval 相容，在观测域不交叉，分离变化合格；
- 95% 几何置信带被同一 physical search band 完整约束；
- 没有第二个同样成立但物理身份不同的 pair。

观测长度只以原始区间、样本分布和拟合置信带存在。没有 coverage ratio、照片高度倍数、
leverage 数值或身份门槛。局部证据足够即可证明边缘身份；它不必覆盖整条长图。扫描外沿
缺少有效照片内外双侧窗口，不能自证；holder 只提供独立 containment，重合保持 neutral。

95% 置信带与物理区间不相交时记录 `pair_geometry_contradicted`；相交但未被完整约束时保持
unavailable。54 mm 与 56 mm 两个真实假设同时成立时记录
`competing_pairs_unresolved`，分数、排序或 margin 不能消除冲突。

`PhotoEdgePairEvidence` 的 typed facts 为：

```text
paths_unavailable
insufficient_distributed_support
photo_band_evidence_unavailable
photo_band_contradicted
pair_geometry_contradicted
competing_pairs_unresolved
```

### 3.3 Dual lane

`135-dual` 的片夹设置不具有统一物理尺寸。Detection 先在 source 坐标系解 lane divider，
再在每条 lane 内用相同的局部三态与稳健 pair 模型处理纯图像路径，但不创建
`ScanCanvasPhysicalSpec`、`CanvasPixelScale` 或理论照片带。两 lane 都有唯一 supported pair
且角度置信区间相容时才允许全局校正。Divider、两份 pair evidence 和 lane boxes 使用同一
仿射映射；任一缺失、冲突或角度不一致均保持 REVIEW。

## 4. 三个独立消费者 / Three Independent Consumers

### 4.1 Transform

`TransformGeometryEvidence` 只消费 source pair 的共同角度。Outcome 只有：

```text
photo_edge_pair_unavailable
angle_estimation_unavailable
edge_slopes_disagree
identity_within_tolerance
deskew_applied
angle_out_of_range
```

只有 `identity_within_tolerance` 与 `deskew_applied` 为 supported。失败 outcome 的角度为
`None`，不得以 0° 伪装成功。最大角度只由
`TransformDetectionParameters.maximum_angle_degrees` 拥有；底层接收解析好的 typed
参数。

`image.rotate_array_expand` 执行通用 expanded rotation，并返回唯一
`AffineCoordinateTransform`。Detection 用它映射 edge samples、拟合区间、confidence
interval、lane divider 和后续几何。像素与坐标使用完全相同的 matrix 和 expanded offset；
插值不确定度随映射传播，但不提升证据。

### 4.2 Shared short axis

`SharedShortAxisPlan` 不发现、复制或重新拟合照片边缘。它只引用 mapped
`PhotoEdgePairEvidence.observation_id`，并把两条 mapped inner lines 投影到完整
workspace 长轴域。Physical selection 仍只由被引用的 pair evidence 持有。Outcome 只有：

```text
supported
photo_edge_pair_unavailable
extrapolation_uncertainty_too_large
mapped_geometry_contradicted
```

因此允许“照片边缘身份与 deskew 已成立，但整条共享裁切短轴的端点外推仍不安全”。没有
supported span 时不得制造 containment 坐标。

### 4.3 Frame dimensions and long axis

Selected pair 同时绑定具体 `FrameSizeMm`；frame solver 不重新选择 54/56。
具有多个离散尺寸选项但尚无 selected pair 时，frame dimension measurement 为
typed unavailable，不生成默认尺寸 prior。
`CanvasPixelScale` 将照片物理宽高转换为 expected pixel intervals，和实测共同宽度及共享
短轴高度相互验证。Full 模式还要求完整张数与 canvas containment；partial 模式可以使用同一
尺度约束照片尺寸，但缺少首帧原点、pitch 或端部边距事实时，不制造绝对长轴位置，也不平均
分配剩余长度。

随后 detection 只求长轴：

1. long-axis raw paths、holder containment、separator bands 与 content observations；
2. count hypotheses 与已绑定的 `FrameDimensionPrior`；
3. global frame-sequence construction、assignment、common-width resolution 与 completion；
4. `FrameSequenceSolution`、candidate evidence 与 `CandidateGate`；
5. deterministic selection 与 `GeometryResolution`。

`FrameSlot` 必须正宽、单调且不交叉。Measured boundary 与 geometry-derived boundary 是不同
事实，后者不能给自己增加独立 proof。Content 只能反证遗漏，不能创造 count、边界或 blank
slot。Full sequence 最多允许一个由完整物理序列唯一推导的 blank slot；partial 不得用空白
区域增加 count。Execution budget 只限制搜索；耗尽是 unavailable，不是可靠性证据。

## 5. DetectionWorkspace、配置与 Gate

`DetectionWorkspace` 集中持有：

```text
pixels
source_gray + mapped gray
exact MeasurementCache
ScanCanvasEvidence
source_photo_edge_pairs
TransformGeometryEvidence
mapped_photo_edge_pairs
shared_short_axes
source/mapped lane divider
WorkspaceIdentity
```

Workspace 验证 source/mapped evidence 一一对应、physical selection 不变、所有 samples 与
span 位于各自坐标域、cache 使用 canonical mapped gray。Production runtime 只有
`prepare_detection_workspace` 一条路径；纯 solver 测试可以显式构造 typed fixture，但不能
形成运行时旁路。

Runtime 由 `FormatPhysicalSpec + strip_mode` 解析唯一 `DetectionConfiguration`，其中
`scan_canvas`、`photo_edges` 与 `transform` 是互不混合的 typed 参数组。Format facts、
adaptive measurements、execution budgets、diagnostics 与 user preference 分离。Lower
layers 不查询 registry、不读取 TIFF DPI、不生成 fallback 或默认值。

每个参数只属于一个正式角色：

- `physical_fact`
- `standard_transform`
- `adaptive_measurement`
- `numerical_safety`
- `execution_budget`
- `user_preference`
- `diagnostics_only`

角色不能互相充当物理证据。`MeasurementCache` 只缓存 exact、
count/offset-independent measurement，不缓存 pair evidence、shared-axis plan、
candidate、Gate、selection、decision 或 approximate geometry。

```text
FrameSlot long-axis interval
  x SharedShortAxisPlan.span
  -> FrameCropEnvelope
  -> FrameBleedPlan
  -> GeometryResolution
  -> DecisionGate
  -> FinalDetection / optional TIFF export
```

`CandidateGate` 检查 candidate-local proof。`DecisionGate` 独立消费 scan-canvas state、
transform state、selected candidate gate、geometry resolution、selection consensus 与
output protection。未知或竞争 canvas、任何 unsupported transform、未解决共享短轴、真实
替代解或输出保护失败都会阻止 auto PASS。Bleed 与 finalization 只应用已决定几何，不反向
改变 evidence。

## 6. Report、Debug 与人工权威 / Audit Surfaces

Current report schema：

```text
schema_id: detection_report
schema_revision: scan_canvas_photo_edge_evidence
```

`input` 记录 `ScanCanvasEvidence`、有效 px/mm、即时展示 PPI、source candidates /
summaries / hypotheses / selected pair、transform outcome 与
`AffineCoordinateTransform`、mapped pair、`SharedShortAxisPlan`、lane divider 和 workspace
identity。它不记录原始 section 转折点、TIFF DPI 可信度、第二份 frame scale 或旧 deskew
字段。`configuration`、`selection`、`decision` 和 `output` 各自只序列化当前 owner 的事实；
旧 schema、alias、shim 和兼容解析不存在。

Debug Analysis 是固定三联只读视图：

1. source physical photo-edge evidence：理论带、合并候选、pair 状态与 typed summary；
2. mapped photo edges、shared short axis 与 frame geometry；
3. long-axis boundary、separator 与 output evidence。

第一联只绘制有效或相互竞争的 supported pair；其余失败候选仅显示 typed reason、区段与数量
摘要。即使没有 selected pair，理论带和失败摘要仍然存在，不生成空白审阅页或成百条失败线。
Report 与 Debug 都不重测几何。当前人工审阅保持独立：`manual_baseline.jsonl` 是人工裁切
权威，candidate-level confirmation/rejection 只作只读回归种子，runtime 永不读取人工白名单。
机器 `supported` 不能被描述为 human-confirmed。

## 7. 源码分层 / Source Layers

| Layer | Canonical responsibility |
|---|---|
| `x5crop.entry` | CLI、interactive parsing 与用户消息。 |
| `x5crop.runtime` | Bootstrap、workflow、workers、manifest 与 I/O side effects；无几何所有权。 |
| `x5crop.formats` | `FramePhysicalSpec`、`ScanCanvasPhysicalSpec` 与 format identity。 |
| `x5crop.configuration` | Typed scan-canvas、photo-edge、transform、solver、output 与 diagnostics 参数。 |
| `x5crop.cache` | Exact measurement cache 与 lookup statistics。 |
| `x5crop.geometry` | Box、layout、sampling 与通用 `AffineCoordinateTransform`。 |
| `x5crop.image` | Gray、statistics、evidence image 与通用 pixel transforms。 |
| `x5crop.io` | TIFF read/write、profile 与 metadata preservation。 |
| `x5crop.detection.workspace` | Source observation、transform assessment、mapping 与 workspace preparation。 |
| `x5crop.detection.evidence` | `ScanCanvasEvidence`、`PhotoEdgePairEvidence`、transform 与其他 typed evidence。 |
| `x5crop.detection.physical` | `SharedShortAxisPlan`、frame dimensions、observations 与 `solve_frame_sequence`。 |
| `x5crop.detection.candidate` | Proposal、build、assessment、execution 与 selection。 |
| `x5crop.detection.output_preparation` | 将 selected evidence 单向翻译成 `FrameBleedPlan`。 |
| `x5crop.detection.decision` | `DecisionGate` 与 final reason vocabulary。 |
| `x5crop.detection.final` | Finalization plan 与 `FinalDetection` assembly。 |
| `x5crop.output` | Crop envelopes、bleed 与 side-effect-free output plans。 |
| `x5crop.export` | Output paths 与 validated TIFF export orchestration。 |
| `x5crop.report` | Current-schema serialization、identity 与 validation。 |
| `x5crop.debug` | Read-only visualization。 |
| `tools.tests` | Physical、schema、layer、metadata 与 no-residue contracts。 |
| `tools.regression` | Current-schema comparison 与人工 reference validation。 |

依赖方向是 `entry/runtime -> detection -> geometry/image/cache`，report/debug 只消费上游 typed
结果。Foundation code 不知道 format identity、Gate、decision 或 report schema。每个概念只能
有一个名称、typed owner 和真相来源；被替代的 API、字段、别名、包装层与测试必须在同一变更
中删除。
