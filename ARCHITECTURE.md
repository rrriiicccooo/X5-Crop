# X5 Crop 架构说明

本文件是 V4.9 当前运行流、数值几何合同和源码分层的唯一架构说明。用户操作见
`docs/user-guide.zh-CN.md` 与 `docs/user-guide.en.md`，版本变化见 `CHANGELOG.md`，
长期协作规则见 `AGENTS.md`。

## 1. 固定运行流

```text
entry: public input
  -> runtime: TIFF I/O + resolved DetectionConfiguration
  -> detection: ScanCanvasEvidence or lane containment
  -> temporary dense local transition measurements
  -> PhotoEdgeObservation
  -> PhotoEdgeRidgeGraph
  -> lazy complete PhotoEdgeFragment paths
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

### 1.1 操作几何主链与校准边界

水平方向措辞下的唯一主链是：

```text
共享照片上下边缘
  -> deskew + mapped 共享短轴
  -> 每张照片成对的长轴边缘
  -> inward-safe FrameCropEnvelope
  -> output-only bleed
```

垂直片条执行完全旋转等价的流程。这个主链保留 typed evidence、唯一 affine 坐标映射、
uncertainty propagation、`CandidateGate`、`DecisionGate` 与 typed unresolved；任何
消费者证据不足都保持 REVIEW，不能用理论位置、score 或 bleed 补证。

黄金集的验收目标不是每个边界达到数学 `0 px`，而是在用户确认基准所校准的方向性容差内，
得到足够准确且不会危险越界的基础裁切。容差应分别检查边缘法向距离、角度、向外越界、
向内内容损失与 uncertainty containment，不能压缩成一个无方向总分。Bleed 只在基础几何
和 Gate 之后扩张输出，可以覆盖物理边缘起伏与直线近似中的微小误差，但不能改变 evidence、
resolution、status 或掩盖明显错误。当前 V4.9 尚未从新黄金集冻结这些容差；基准确认前仍按
现有严格证据合同保持 unresolved / REVIEW。

### 1.2 权限表

| Owner | 唯一职责 |
|---|---|
| `FramePhysicalSpec` | 照片尺寸事实与离散 `FrameSizeMm`。 |
| `ScanCanvasPhysicalSpec` | 片夹扫描画布事实及 format 兼容关系。 |
| `ScanCanvasEvidence` | 从 source 像素长短比选择唯一、无匹配或竞争 profile。 |
| `CanvasPixelScale` | 唯一 long/short px/mm 尺度与轴向映射。 |
| `PhotoEdgeObservation` | 与材料、场景和极性无关的局部像素测量。 |
| `PhotoEdgeRidgeGraph` | 唯一拥有 observation 的连续证据图；edge 只表示相邻 anchor 间的直接证据。 |
| `PhotoEdgeFragment` | graph 中完整 source-to-sink path 的不可变 node-ID 引用；不拥有 observation。 |
| `PhotoEdgePairEvidence` | 唯一 top/bottom 边缘身份真相与完整 physical label。 |
| `TransformGeometryEvidence` | selected source pair 或 dual joint region 的 transform 消费结果。 |
| `SharedShortAxisPlan` | mapped pair 的全 workspace 安全裁切消费结果。 |
| `DetectionWorkspace` | 同一坐标域的 pixels、gray、cache、source/mapped evidence 与 transform。 |
| `CandidateGate` | 候选自身的物理证明。 |
| GeometryResolution | 唯一 early-stop 输入；判断几何与替代解是否解决。 |
| `DecisionGate` | 唯一创建 final status 与 final reasons。 |
| report / debug | 只读 typed evidence，不重测、不重算、不裁决。 |

理论位置、搜索顺序、分数和执行预算都不是物理证明。`CandidateGate` 与
`DecisionGate` 是仅有的两个 Gate，只有 `DecisionGate` 创建
`approved_auto` 或 `needs_review`。

## 2. 物理画布与坐标

照片与画布由不同目录保存。单条片夹按允许 profile 与 source 像素长短比在 0.5%
限制内匹配：

| Profile | 短轴 × 长轴 |
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

## 3. 跨区域局部观测

Detector 在分帧前工作，不知道 transition 属于哪一张照片。证据可以全部来自一个很短的
连续区域，也可以来自多个不连续区域；不要求跨 frame、最小跨度、覆盖率、分桶或上下
观测域重叠。

所有强度计算只使用 `make_base_gray_u8`。每个 anchor 使用 0.5×、1×、2× 三个短轴
尺度，长轴 footprint 始终由一个 `long_support_width` 决定。Intensity、texture、
gradient 各自从自己的 profile 计算 response、local noise 与连续 support interval；
任一 channel 可独立贡献，不要求三者同时出现。每个连续 support 段的端点外扩半个像素，
peak 只作统计，不缩窄位置包络。

实际参加同一 transition 的 support 必须具有非空共同位置交集，并达到不同尺度数量下限。
Support 按区间中心和稳定 identity 顺序扫描；加入下一项会令累计交集为空时立即结束当前
组，因此仅靠传递重叠不能桥接两个 transition。同一 support identity 只计一次，最终
observation 的位置包络是全部参加区间的保守外包。

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
和尺度重复都是临时数据。每个 graph node 唯一拥有一个 observation；edge 仅在相邻采样
位置存在直接连续 support 时建立。没有直接证据就不建 edge，也没有 gap tolerance；真实
缺口形成不同 component。Junction observation 仍只属于一个 node。

`PhotoEdgeFragment` 由 graph 按 source node ID 和每级 outgoing node ID 的字典序惰性生成，
只保存完整 source-to-sink node-ID tuple。无 junction 的单链曲线只生成一条完整 path，
geometry 无权摘取局部直线。Geometry 通过 node ID 解析 observation，并始终按 observation
ID 去重；多条 path 共用 junction 时不能重复贡献证据。不同 component 可以作为完整 path
进入同一 consensus，但这只表示共同支持一个几何集合，不表示 component 之间观测连续。

每侧唯一数量下限是三个 uncensored、footprint 互不重叠的 supported observations；除此
之外没有最小长度。恰好三个时必须全部共同可行，不能删除其中一个再用两个点成立。

## 4. 联合法向几何

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

Line feasible region 始终是 polygon 集合。约束逐 polygon 精确相交，slope 投影也逐项
相交；不再用全局 `min/max slope` 把多个不相连分量填成凸包。结果规范化为排序后的多个
slope/θ 连通分量，只有重叠或间距不超过既有 `_POLYGON_EPSILON` 才合并。每个分量建立独立
hypothesis；fixed-canvas、image-only、seed、outer admissibility 与 slope-sharing 检查
消费同一精确集合。

统一集合关系是 `DISJOINT`、`SUBSET`、`PARTIAL_INTERSECTION` 和
`NUMERICALLY_INDETERMINATE`。达到 1/16 px 对应 offset/θ 分辨率仍不能证明的区域只能
unavailable。Region cell 与 consensus state 使用 sample/lane 级共享
`GeometryWorkBudget`。它是唯一 mutable 计数 owner：`maximum_consensus_states` 限制
累计首次注册的唯一 consensus state，`maximum_region_cells` 限制累计实际调用 evaluator
的 cell 数；暂停、恢复和重复访问不重复扣费，pending 或预约也不扣费。
`GeometryWorkStatistics` 只在求解结束时生成一次不可变快照，不形成第二套计数。预算不会
为 hypothesis 重置，耗尽也只能 unavailable。Production report 为保持既有 schema，
只把同一最终快照的两个累计计数投影到 normal region；这些只读字段不是预算 owner。

θ 区间宽度 `w`、既有 resolution `r` 与最大深度 `D` 的预约上界固定为：

```text
d = 0                              if w <= r
d = min(D, ceil(log2(w / r)))      if w > r
cell_upper_bound = 2^(d + 1) - 1
```

它只用于 admission、预约和执行顺序。稳定顺序键是
`(cell_upper_bound, top_path_id, bottom_path_id, theta_component_id)`；不能进入
evidence、confidence、selection、Gate 或 report。Scheduler 惰性发现 path 与 hypothesis，
保留可恢复 subtree state，并确保预约总量和 pending cell 都不超过剩余 cell 预算。窄候选
先执行；未开始的宽候选可被更窄候选替换。只有 evaluator 调用前才累计扣除一个 cell，
提前剪枝立即释放未用预约。

每个可行模型携带完整 label：scan-canvas profile、physical band 和完整
`FrameSizeMm(width_mm, height_mm)`。所有模型无 label 为 contradicted；部分模型无 label
为 unavailable；始终只有同一 label 才可能 supported；始终有 label 但身份不唯一为
competing。下游不能只保存高度后重新选择 120 的 54/56 或 frame width。

## 5. Maximal Consensus 与曲率

Consensus 的 admissible region 是以下约束的交集：

```text
observation rectangles
∩ top/bottom order
∩ independent containment
∩ union(allowed complete physical labels)
```

确定性最小 seed 遇到互斥可加入 fragment 时必须分支。Consensus 只在父 hypothesis 完成
后惰性创建，并在唯一 state ID 首次注册时扣除累计预算。最终只保留按 fragment 集合包含
关系 maximal 的 consensus，并按固定网格 cell signature 合并等价区域；不能按点数、
残差、score 或 margin 选一个。

Path 或 hypothesis 未枚举、候选未预约、cell search 未完成，或 consensus 分支未覆盖，
都会标记搜索不完整。此时 runtime pair geometry 必须为 `unavailable`，无 selection，也
不进入 finalization；局部完成 witness 无权改变结论。已经确认 path discovery 不完整时
立即停止后续 polygon/search 工作，是 typed unavailable 的执行结果，不是成功 early-stop。

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

## 7. Transform、映射与共享短轴

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

## 8. Workspace、配置、缓存与长轴

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

## 9. Report、Debug 与人工审阅

当前报告标识：

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
axis；它不重算几何。Graph 分叉、junction ownership 和 path 完整性由 contracts 与一次性
只读内部审计验证，不扩充 production report schema。Debug 人工检查只回答最终正式边缘
是否落在真实照片边界；没有正式 geometry 时无边缘可批准。

黄金比较器位于 runtime 外部。Runtime 只产生正式 geometry，或产生 `unavailable` 且不
进入 finalization；比较器才记录 `compared` 或 `production_geometry_unavailable`。存在
正式 geometry 时，比较器分别测量每条边的角度、signed normal distance、危险向外越界、
向内内容损失与 containment。`1e-9` 只作数值零判断，不是实用安全容差；在方向性容差另行
校准并获批前，比较器不据这些数值自动声明 `resolved-safe`。

Baseline 是 runtime 外部的独立审计输入。Runtime、tools 和 tests 均不读取人工标签或
白名单，机器 supported 不能称为 human-confirmed。只有绑定 source SHA 的原图坐标，并由
用户直接点击后明确确认，或由独立校准的外部测量产生，才可能进入 baseline。完整长图的
模型视觉、OpenCV、SciPy、X5 Crop、生成 JPG 或多个算法相互同意都只能形成非权威
proposal；看不清的边界必须保持 unresolved。

用户也可以在保持原始尺寸与方向的 TIFF 副本上直接画红线。外部转换器只能用未修改原图与
标注副本的像素差拟合笔迹中心，并生成原生分辨率复核 JPG；坐标不得从有损 JPG 反测。拟合
记录必须同时绑定 source SHA 与 marked-copy SHA，并保持 pending。只有用户明确确认指定
复核 JPG 后，连续线、交点及确定的整数转换结果才可写入 current baseline schema。这个
项目权威 baseline 表示实用容差内的安全无 bleed 目标，不声称数学零误差；输出 bleed 始终
是独立扩张，不能修复错误基础几何。当前人工审阅状态只见 `PROJECT_MEMORY.md`。

## 10. 源码分层

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
| `tools/verify` | 唯一机械 verifier；Hook 与 CI 只调用它。 |
| `tools/release` | Standalone builder、release archive 与唯一 package manifest。 |
| `tools/regression` | Current-schema report comparison；不拥有人工真相。 |
| `tools/tests/support` | 共享 typed fixtures 与静态合同辅助；不包含 test cases。 |
| `tools/tests/test_*` | 可发现的 current-only contract tests。 |

依赖和权限只沿运行流向前。每个概念只有一个 canonical name、type、owner 和真相来源；
被替代的 API、字段、别名、shim、wrapper 与测试必须同批删除。
