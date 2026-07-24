# X5 Crop 架构说明 / Architecture Guide

本文件是 V4.9 当前运行流、数值几何合同和源码分层的唯一架构说明。用户操作见
`README.md`，版本变化见 `CHANGELOG.md`，长期协作规则见 `AGENTS.md`。

This document is the sole description of the current V4.9 runtime flow,
numerical geometry contract, and source layering.

## 1. 固定运行流 / Fixed Runtime Flow

```text
entry: public input
  -> runtime: TIFF I/O + resolved DetectionConfiguration
  -> detection: ScanCanvasEvidence or lane containment
  -> temporary dense local transition measurements
  -> PhotoEdgeObservation
  -> PhotoEdgeFragment
  -> maximal admissible pair hypotheses
  -> PhotoEdgePairEvidence
      -> TransformGeometryEvidence
      -> image: generic expanded affine transform
      -> mapped PhotoEdgePairGeometry
      -> SharedShortAxisPlan
      -> bound FrameSizeMm
  -> solve_frame_sequence
  -> FrameSequenceSolution -> CandidateGate -> selection
  -> GeometryResolution -> output preparation
  -> DecisionGate -> finalization
  -> runtime/output: TIFF export, report, Debug Analysis
```

短轴只在 source pixels 中观测一次。Deskew 是 detection 的强制消费者，不是可选
预处理；旋转后只映射同一份证据，禁止再次从 pixels 寻找短轴。Runtime 只编排配置、
I/O 和副作用，`image` 只拥有灰度、统计和通用像素变换。

The short axis is observed once in source pixels. Deskew is a mandatory
detection consumer. The mapped workspace reuses that evidence and never
measures another short axis.

### 1.1 权限表 / Authority Table

| Owner | 唯一职责 / Sole responsibility |
|---|---|
| `FramePhysicalSpec` | 照片尺寸事实与离散 `FrameSizeMm`。 / Photo dimensions and discrete frame sizes. |
| `ScanCanvasPhysicalSpec` | 片夹扫描画布事实及 format 兼容关系。 / Holder-scan canvas facts and format compatibility. |
| `ScanCanvasEvidence` | 从 source 像素长短比选择唯一、无匹配或竞争 profile。 / Resolve unique, unmatched, or competing profiles. |
| `CanvasPixelScale` | 唯一 long/short px/mm 尺度与轴向映射。 / Sole pixel scale and work-axis mapping. |
| `PhotoEdgeObservation` | 材料、场景与极性无关的局部像素测量。 / Material-, scene-, and polarity-independent local measurements. |
| `PhotoEdgeFragment` | 同一连续 ridge 的最大、不可拆 build-stage 单元。 / Maximal indivisible continuous-ridge build unit. |
| `PhotoEdgePairEvidence` | 唯一 top/bottom 边缘身份真相与完整 physical label。 / Sole edge-identity truth and complete physical label. |
| `TransformGeometryEvidence` | selected source pair 或 dual joint region 的 transform 消费结果。 / Transform-consumer outcome. |
| `SharedShortAxisPlan` | mapped pair 的全 workspace 安全裁切消费结果。 / Strip-wide safe-crop consumer of the mapped pair. |
| `DetectionWorkspace` | 同一坐标域的 pixels、gray、cache、source/mapped evidence 和 transform。 / Coordinate-domain integrity. |
| `CandidateGate` | 候选自身的物理证明。 / Candidate-local physical proof. |
| GeometryResolution | 唯一 early-stop 输入；判断几何与替代解是否解决。 / Sole early-stop authority. |
| `DecisionGate` | 唯一创建 final status 与 final reasons。 / Sole creator of final status and reasons. |
| report / debug | 只读 typed evidence，不重测、不重算、不裁决。 / Read typed evidence only. |

理论位置、搜索顺序、分数和执行预算都不是物理证明。`CandidateGate` 与
`DecisionGate` 是仅有的两个 Gate，只有 `DecisionGate` 创建
`approved_auto` 或 `needs_review`。

## 2. 物理画布与坐标 / Physical Canvas And Coordinates

照片与画布由不同目录保存。单条片夹按允许 profile 与 source 像素长短比在 0.5%
限制内匹配：

| Profile | 短轴 × 长轴 / Short × long |
|---|---:|
| `135_standard` | 32.22 × 232 mm |
| `135_narrow` | 25.4 × 232 mm |
| `120_standard` | 60 × 226 mm |
| `120_wide` | 63.44 × 224.5 mm |
| `120_66_three_frame` | 63.44 × 188.5 mm |

唯一匹配产生 `CanvasPixelScale`；无匹配为 `aspect_contradicted`，多匹配为
`competing_profiles_unresolved`，两者均不进入固定画布边缘 detector。
`135-dual` 为 `not_applicable`，不虚构物理画布或 px/mm。TIFF resolution 只作
原样保存的 I/O metadata，不参与尺度、搜索、证据或 decision。

固定画布使用像素中心约定：

```text
u_mm = (u_px - (long_extent_px - 1) / 2) / long_axis_px_per_mm
v_mm = (v_px - (short_extent_px - 1) / 2) / short_axis_px_per_mm
```

理论中心只定义搜索 corridor。Measurement domain 在 corridor 外保留完整 halo；
接触 halo 或画布测量边界的 component 是 censored，只能贡献 unavailable 诊断。
Corridor 不能裁窄位置包络，也不能生成 supported evidence。

## 3. 跨区域局部观测 / Cross-Region Local Observation

Detector 在分帧前工作，不知道 transition 属于哪一张照片。证据可以全部来自一个很短的
连续区域，也可以来自多个不连续区域；不要求跨 frame、最小跨度、覆盖率、分桶或上下
观测域重叠。

所有强度计算只使用 `make_base_gray_u8`。每个 anchor 使用 0.5×、1×、2× 三个短轴
尺度，长轴 footprint 始终由一个 `long_support_width` 决定。至少两个尺度的位置包络
相容，并且绝对 intensity、texture 或 gradient effect 明确超过局部 noise，才产生
`supported` transition。不同尺度和 channel 在同一原始位置只合并为一个 observation。

局部状态只有：

- `supported`：实际 transition 在多个尺度稳定存在；
- `neutral`：当前 pixels 无法可靠区分两侧。

Neutral 只汇总，不持久化、不进入拟合分母。局部层没有 contradicted；containment、
top/bottom 顺序和联合几何冲突只属于 pair assessment。Observation 保存
negative/positive side statistics；top/bottom hypothesis 才派生只读 inner/exterior 视图。
Detection 不推断材料、片基颜色、片夹颜色、正负片或画面类型，明暗极性反转不改变身份。

一个 observation 只声称其二维 rectangle 内存在稳定 transition。对 rectangle `R` 和
法向 `n(θ)`，line offset 的约束是：

```text
d ∈ [min(n(θ)·corner(R)), max(n(θ)·corner(R))]
```

它不声称 ridge 覆盖 rectangle 的全部长轴宽度。Dense response、anchor、threshold pixels
和尺度重复都是临时数据。实际 support pixels 的 8 连通关系形成 component；没有连续
pixel support 的 gap 必须断开 fragment。每侧唯一数量下限是三个 uncensored、footprint
互不重叠的 supported observations；除此之外没有最小长度。恰好三个时必须全部共同可行，
不能删除其中一个再用两个点成立。

## 4. 联合法向几何 / Joint Normal Geometry

固定画布 pair 使用：

```text
n(θ) · (u, v) = d_top
n(θ) · (u, v) = d_bottom

physical_height = d_bottom - d_top
center_offset   = (d_top + d_bottom) / 2
```

高度是真实法向距离，不是短轴截距差。物理斜率先转换为 pixel slope：

```text
m_pixel = m_physical
          × short_axis_px_per_mm
          / long_axis_px_per_mm
deskew_angle = atan(m_pixel)
```

Search 与 transform 接受角均以 pixel angle 配置；search 的 4° 包络与 transform 的
2° 接受范围由不同 typed owner 保存。

`PhotoEdgeNormalFeasibleRegion` 是同一二分 θ 网格上的 `NormalRegionCell` 集合。
每个 cell 同时保存 outward-rounded outer enclosure、active constraints、可能的完整
physical labels，以及逐条重新代入所有 observation、order、containment、physical-band
约束后成立的 witness。Outer 非空只证明“可能”，只有 verified witness 证明“存在”。

统一集合关系是 `DISJOINT`、`SUBSET`、`PARTIAL_INTERSECTION` 和
`NUMERICALLY_INDETERMINATE`。达到 1/16 px 对应 offset/θ 分辨率仍不能证明的区域只能
unavailable。Region cell 与 consensus state 使用 sample/lane 级共享
`GeometryWorkBudget`；预算不会为 hypothesis 重置，耗尽也只能 unavailable。

每个可行模型携带完整 label：scan-canvas profile、physical band 和完整
`FrameSizeMm(width_mm, height_mm)`。所有模型无 label 为 contradicted；部分模型无 label
为 unavailable；始终只有同一 label 才可能 supported；始终有 label 但身份不唯一为
competing。下游不能只保存高度后重新选择 120 的 54/56 或 frame width。

## 5. Maximal Consensus 与曲率 / Maximal Consensus And Curvature

Consensus 的 admissible region 是以下约束的交集：

```text
observation rectangles
∩ top/bottom order
∩ independent containment
∩ union(allowed complete physical labels)
```

确定性最小 seed 遇到互斥可加入 fragment 时必须分支。最终只保留按 fragment 集合包含关系
maximal 的 consensus，并按固定网格 cell signature 合并等价区域；不能按点数、残差、
score 或 margin 选一个。全局 state/cell 预算超限时返回 unavailable，不静默截断。

同一连续 ridge 不可拆。位置包络能吸收的轻微偏离仍属于一个直线区域；系统性弯曲、单边
弯曲或连续 ridge 上的多个局部直线不能切出局部三点解。完整 fragment 无 admissible
直线时，transform 与 shared axis 都不可用。

样片级只在恰好一个 supported hypothesis 且其余全部 contradicted 时选择。两个
non-contradicted hypotheses，或 supported 与 unavailable 并存，都成为
`competing_pairs_unresolved`。Pair facts 只有：

```text
observations_unavailable
containment_contradicted
pair_geometry_unavailable
pair_geometry_contradicted
competing_pairs_unresolved
```

## 6. Holder 与 135-dual

Holder 与 photo edge 共用 transition anchor 时只去重，不能同时成为两份证据，也不能
约束该 hypothesis。只有依赖不同 pixels 的 holder observation 提供独立 containment。
照片直接接触 holder 时，实际清晰 transition 仍可成为 photo-edge observation。扫描最外沿
必须满足双边、完整 label 与联合几何，不能凭强 transition 自证。

`135-dual` 先由独立 pixels 解 lane divider。每 lane 独立形成唯一 pair identity，再建立
并保留联合区域 `J`；两 lane 共享同一个真实 pixel angle 和 perpendicular photo height。
1/16 px 只属于 interval solver，不是经验物理容差。每个 J cell 同样需要 outer enclosure
与 verified witness；J 的存在性、唯一性和精度分别由 typed evidence 与消费者判断。

## 7. Transform、映射与共享短轴 / Consumers

Pair identity、transform 和全域裁切是三个独立判断：

- Pair supported 但 angle region 太宽：transform unavailable。
- Transform supported 但完整 workspace 投影太宽：shared axis unavailable。
- 消费者失败不得回写上游 pair。

Transform 以完整 source pixel 长轴 `[0, L - 1]` 的投影误差判断角度精度。Angle region
完全位于 identity tolerance 时为 `identity_within_tolerance`；足够精确且完全位于最大角
范围时为 `deskew_applied`。部分相交或越界为 unavailable / `angle_out_of_range`。
失败 angle 为 `None`，应用角取已证明可行 interval 的 minimax center。

唯一映射链是：

```text
physical work
  -> source work pixels
  -> source image x/y
  -> affine homogeneous-line inverse-transpose
  -> mapped image x/y
  -> mapped work
```

Horizontal/vertical、expanded rotation 平移、divider、pair、audit observations 和最终框
共用一个 `AffineCoordinateTransform`。实际 bilinear rotation 给 mapped top/bottom
envelope 各增加 ±1 px；identity 不增加插值误差。

`SharedShortAxisPlan` 只引用 mapped pair ID。它在 `[0, L - 1]` 上传播 geometry 与
interpolation uncertainty，再以内向极值形成安全 span：

```text
safe_top    = maximum(mapped top envelope)
safe_bottom = minimum(mapped bottom envelope)
```

端点 uncertainty 超过 max(照片高度的 2%, 3 px) 时 `span=None`，不得制造 containment
坐标。

## 8. Workspace、配置、缓存与长轴 / Runtime Detection

`DetectionConfiguration` 分别持有 `scan_canvas`、`photo_edges`、`transform`、
`shared_short_axis` 和既有长轴/sequence 参数。Runtime 一次解析；lower layer 不查询
registry、不发明默认值。参数角色保持分离：

- `physical_fact`
- `standard_transform`
- `adaptive_measurement`
- `numerical_safety`
- `execution_budget`
- `user_preference`
- `diagnostics_only`

`DetectionWorkspace` 持有 scan canvas、source pairs、dual joint region、transform、
mapped pairs、shared axes、source/mapped divider、pixels、gray 与 exact measurement
cache。Cache 只保存 count/offset-independent gray/statistical measurements 或 dense
measurement chunk；不保存 observation、fragment、region、selection、Gate、decision 或
final status。

Selected pair 已绑定 frame dimensions。之后 `solve_frame_sequence` 只求长轴观测、
共同 frame width、有序 `FrameSlot`、separator assignments 与 `FrameSequenceSolution`。
Content 可以反证遗漏，不能创造 count 或边界。Execution budget 只限制工作，不能成为
可靠性证据。

## 9. Report、Debug 与人工权威 / Audit Surfaces

Current report identity：

```text
schema_id: detection_report
schema_revision: cross_region_photo_edge_geometry
```

Report 保存 canvas/scale、corridor/halo、测量汇总、fragment compact envelopes 与 hashes、
maximal hypotheses、active/minimum-support witnesses、normal cells、verified witnesses、
完整 labels、source/mapped pair、transform、affine 和 shared-axis outcome。它不保存 dense
responses、threshold pixels、anchor windows、尺度重复、临时 seed/DFS state 或全部冗余
observations。

Debug Analysis 只读取报告证据，显示 corridor/halo、compact fragments、censored summary、
active/witness observations、source pair uncertainty envelope、mapped pair 和 shared short
axis；它不重算几何。人工审阅继续独立且暂停：runtime 不读取人工标签或白名单，机器
supported 不能称为 human-confirmed。

## 10. 源码分层 / Source Layers

| Layer | Canonical responsibility |
|---|---|
| `x5crop.entry` | CLI 与 interactive parsing。 |
| `x5crop.runtime` | Workflow、workers、manifest、TIFF I/O 副作用；无几何所有权。 |
| `x5crop.formats` | `FramePhysicalSpec`、`ScanCanvasPhysicalSpec` 与 format identity。 |
| `x5crop.configuration` | 全部 typed 参数与 runtime resolution。 |
| `x5crop.geometry` | 通用坐标、Box 与 affine。 |
| `x5crop.image` | Gray、statistics 与通用 pixel transform。 |
| `x5crop.io` | TIFF read/write 与 metadata preservation。 |
| `x5crop.cache` | Exact measurement cache。 |
| `x5crop.detection.evidence` | Current typed evidence 与 source/mapped models。 |
| `x5crop.detection.physical` | Observation、joint geometry、shared axis 与 frame sequence。 |
| `x5crop.detection.workspace` | Detection flow、mapping 与 coordinate-domain validation。 |
| `x5crop.detection.candidate` | Proposal、build、assessment、selection 与 `CandidateGate`。 |
| `x5crop.detection.decision` | `DecisionGate`。 |
| `x5crop.detection.final` | Finalization。 |
| `x5crop.output` / `x5crop.export` | Output plans 与 validated TIFF export。 |
| `x5crop.report` / `x5crop.debug` | Current-schema serialization 与只读可视化。 |
| `tools.tests` / `tools.regression` | Contracts、verification 与 current-schema comparison。 |

依赖和权限只沿运行流向前。每个概念只有一个 canonical name、type、owner 和真相来源；
被替代的 API、字段、别名、shim、wrapper 与测试必须同批删除。
