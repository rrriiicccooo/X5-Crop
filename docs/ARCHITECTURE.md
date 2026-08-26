# X5 Crop V5 架构

本文是 V5 已确认产品合同、运行流、数值合同和源码 owner 的唯一说明。版本变化见
[CHANGELOG.md](CHANGELOG.md)。V5 尚未发布，公开稳定版仍为 `v4.2.8`。

## 1. 产品定义与输入 authority

X5 Crop 是已知胶片模板的自动对准器，不是通用照片边界检测器。

```text
用户 format + 用户确认 count
→ 固定 W/H 模板
→ 从整条片带到局部边界的有界对准
→ 唯一 placement
→ selected-only source-space 安全 polygon
→ CandidateGate / DecisionGate
→ 可选 lightweight deskew
→ 整张 source 自动输出或人工检查
```

- Format 始终由用户提供，像素、文件名和片夹容量都不能改写。
- Count 包含中间空白曝光格；不做 blank suppression。
- 省略 count 表示用户确认匹配片夹的默认完整格数。
- 明确 count 表示用户确认实际 slot 数，必须满足 `1 <= count <= holder_full_count`。
- 同一 source SHA 可以建立多个显式 count 的独立 evaluation task；它们复用同一物理边界标注，但
  分别验证对应 slot 解释和输出。Source SHA 只固定 format 与像素身份，不固定 count。
- Runtime 不保存 full/partial mode。是否铺满是 placement 选定后的物理事实，不是搜索权限。
- `135-dual` 默认 12 格、每 lane 6 格。其它明确 count 产生
  `unsupported_dual_count` 并进入 review，不猜 lane 分配，不运行自动 placement。
- 任一 slot 不安全时整张 source `needs_review`，不做 slot salvage。

唯一 count 数据流是：

```text
SlotCountRequest
→ matched holder
→ ResolvedSlotCount
→ ResolvedOutputSlots
```

## 2. Format、片夹与尺度

尺寸按照片长轴 × 短轴记录：

| format | 固定 W × H | `G_format` 局部搜索先验 | 默认完整格数 |
|---|---:|---:|---:|
| `135` | 36 × 24 mm | 2 mm | 6 |
| `135-dual` | 每 lane 36 × 24 mm | 2 mm | 12，6/lane |
| `half` | 18 × 24 mm | 1 mm | 12 |
| `xpan` | 65 × 24 mm | 2 mm | 3 |
| `120-645` | 42 × 56 mm | 无 | 4 |
| `120-66` | 56 × 56 mm | 无 | 3 |
| `120-67` | 70 × 56 mm | 无 | 普通片夹 3，短片夹 2 |

片夹画布提供大致 px/mm、有效区域和 format/count 相容性，不提供照片组长轴中心。数值合同：

```text
W compatibility：format 名义宽度 ±1.25%
H compatibility：format 名义高度 ±0.40%
holder extent：物理名义范围 ±3.5%
```

`G_format` 只决定首次理论搜索位置，不能单独建立 phase、pitch 或 placement。相机片门偏差与扫描
比例偏差对本项目等价，不尝试区分。X5 长图不依赖齿孔。

## 3. 几何词汇与权限

“outer”不能再表示多个不同对象：

- `CoarseStripSupport`：片带大致位置、搜索 corridor 和局部测量所需的粗方向。它可以来自片夹边、
  胶片材料边、照片边或其它长距离稳定结构，但不能直接决定 crop 或输出 deskew。
- `OuterBoundaryObservation` / `PhotoBoundaryAnchor`：role-free 像素观察与模板绑定后，才可能
  获得 first、last、top 或 bottom 的照片边界权限。
- `CanonicalPlacement`：format、count、phase、pitch、cross 和至多一次 local advance 共同决定的
  source-axis 固定矩形集合。
- `PhotoGroupOuter`：从已选 placement 的 first start 与 last end 推导的长轴范围；不反向参与选位。
- `OutputFootprint`：联合不确定性、直线残差和产品 bleed 后，在 source 坐标中已经确认安全的区域。

这些词汇只映射到一套 current type：`CoarseStripSupport` 保存 role-free aggregate observation，
`OuterBoundaryObservation` 使用 `BoundaryEdgeObservation`，模板绑定后的 `PhotoBoundaryAnchor` 保存在
sequence/cross provenance，`CanonicalPlacement` 使用 `FormatPlacement`。不再建立同义 wrapper。

项目无需把非照片外侧支撑继续分类为 holder edge 或 film edge；两者都只能提供 coarse support，
或在满足完整 enclosing 合同时成为输出边界。同一 raw observation 可以承担多个职责，但 identity
只有一个，不能重复计为独立证据。

## 4. Source-axis placement 与可选 deskew

检测中的 placement 没有角度自由度。每个 lane 独立拥有 phase、pitch、cross center 和 local
advance；全部 aperture frame 的 start/end 与 top/bottom 都沿 source axes。双 lane 只共享相容的
W/H 与 px/mm，不共享检测角度或输出旋转权限。

`SharedStripDirection` 只保留在 cross evidence 内，用来证明局部 fragment 的方向完整、两侧平行或
enclosing support 的同一物理状态；它不是 `FormatPlacement` 属性，不能旋转 frame、改变 phase、
选择 winner、进入 Gate 或拥有 deskew。Role-authorized aperture binding 只能在自己直接采样的 trace
范围内，把短轴 offset 投影到某个 frame center；超出该范围不得外推。投影只移动 fixed-H 的
top/bottom 位置，边界仍与 source axis 平行。

局部 aperture slope、弯曲和逐 trace departure 只扩大 selected placement 的输出保护。只有直接
`ENCLOSING_SUPPORT_PAIR` 因自身就是最终 top/bottom，才在同一联合状态中保留自己的边界 slope。
Sequence 从不提供角度。超过预算就 review，不建立逐帧角度、自由四边形或曲线 detector。

输出 deskew 是与模板无关的 role-free 旁路 observation。只有 `DecisionGate` 已批准输出时，
finalization 才在整条片带的 6–24 个有界稀疏位置读取最外侧暗边；review 不执行这项扫描。两侧分别
稳健拟合，只有 slope、residual 和角度范围相容时才产生角度。它不识别 holder、film 或 photo edge，
不可用或矛盾时返回 typed skip reason 和 `None`，绝不伪造 `0°`。`--deskew auto` 是默认值；
`--deskew off` 不执行这项旁路观测并记录 `user_disabled`。两种模式都不能改变 placement、Gate 或
final status。

Observation 继承 v4.2.8 的数值合同，但保留 V5 的双侧必需与 typed skip：暗像素 `<245`，outer row/
column 支撑至少 1%，outer 长轴至少 100 px；沿长轴约每 350 px 取样，总数限制为 6–24。每条 trace
至少包含 `max(10 px, 5% × short_extent)` 个暗像素；每侧至少 4 点。MAD inlier 容差为
`max(2 px, 3 × MAD)`，最终中位 residual 不超过 `max(3 px, 0.003 × short_extent)`，双侧 slope 差
不超过 `0.006`，可报告观测角绝对值不超过 `2°`。`2°` 只是 measurement plausibility，不授予输出
旋转权限。

## 5. 从整体到局部的模板编译

V5 吸收 v4.2.8 的有效行为，不复制其代码、分数、Grid fallback 或 content equal-split：

```text
format/count/holder 编译固定模板、coarse intents 与工作上界
→ 两个 role-free 全片 aggregate query 建立 CoarseStripSupport
→ coarse support 与固定 lattice 生成有限理论窗口
→ 全部精测窗口一次登记、一次读取
→ region/band-first observation 与局部边界拟合
→ residual pattern
→ placement closure
```

`TemplateMeasurementPlan` 在观察结果产生前冻结：

- `TemplateSpec` 与物理单位；
- sequence、separator、top、bottom 和 content query intents；
- phase、role、cross、placement、像素与内存上界。

Coarse pass 对每个 lane 只执行一个长轴和一个短轴 aggregate query，输出保守 interval 和 receipt；
aggregate interval 本身没有角色、ordinal、placement 或输出 deskew authority。短轴 query 的各条
已注册 trace 若能直接闭合为双侧 track，可以在满足第 8.2 节全部条件时建立 enclosing support；
这份 authority 来自逐 trace 直接观察，不来自 aggregate interval。Long-axis precision 使用固定 lattice 在两个有限 origin
上生成互不重叠的理论窗口；没有 direct coarse observation 时才退回一个保守全长窗口。所有可能被
选中位置使用的精测查询随后一次登记、一次读取；不能为某个 candidate 重读 TIFF、扩张全图搜索或
winner-specific requery。

同一 trace lattice 只建立一次全局 normalization baseline，再由理论窗口切出局部测量。Baseline
不产生 transition 或 placement evidence；其像素和临时内存仍完整计入 receipt，不能伪装成免费工作。

正常片条在 outer、phase/pitch、separator topology、闭环、content 和输出预算均唯一且
相容时，运行时根据已测 residual 停止。Registered measurement 仍保持
candidate-independent；“停止”表示不再开放 local
advance、额外 fit pass 或新 hypothesis，不是按 winner 临时少登记查询。普通 gap residual 已由正常
bleed 覆盖时只保留诊断事实，不增加自由度。

## 6. Observation 与独立证据

Registered measurement 一次生成 role-free、候选无关、数量有界的观察。

### 6.1 `BoundaryEdgeObservation`

保存局部转变的位置区间、方向区间、极性、内外背景关系、空间支持和唯一 observation ID。Raw edge
不知道自己属于哪一格或哪个角色；模板只能在位置与职责相容后绑定它。

### 6.2 `SeparatorBandObservation`

方向、极性和空间支持相容的相邻 END/START edge 才组成 band。Band 保留 material 宽度、位置区间
和两侧 edge identity。一个 separator 的两条边、band、多条 trace 和全部梯度像素是一份物理证据，
不能变成多票。

同一物理 material support 中，source-wide band 优先拥有 END→START 角色；否则只有一对唯一且
极性闭合的局部 edge 可以获得该角色。存在多个局部解释时不按强度或距离挑选。局部 band 可以提供
phase anchor，但 band 宽度本身不能创造 local step。

### 6.3 Cross observation

Top/bottom observation 的局部线段先保持独立。方向相同、坐标接近、残差较小或 trace 较多都不足以
证明多个 fragment 属于同一物理 side track；必须有 source-spanning 连续性，或明确的空间连接和
独立长轴支持。

### 6.4 Content observation

内容层保存二维占用单元或连通区域，只作 negative veto。它不能移动边界、选择 winner、创造
placement、平分照片或把内容 bbox 当 crop。角落擦边、锯齿、尘点、黑片和低纹理保持中性；只有
可靠二维内容连续跨过完整输出边界时才否决。

## 7. Sequence phase、pitch 与偏差

Sequence 在方向规范化长轴上使用固定 lattice：

```text
role = phase
     + slot_index × source_pitch
     + local_prefix[slot]
     + (W if END else 0)
```

- 连续小误差保存在一个 placement 的区间中。
- 不同 ordinal mapping 或相隔明显的 phase 是离散 placements，保留 winner/runner，绝不平均。
- Holder 长轴中心不参与 phase。省略 count 也不提供居中权限。
- 模板投影可以补齐缺失 first/last 或 separator，但 phase 必须来自其它独立 direct anchor。
- 已绑定的直接角色保留自己的 observation interval；模板只传播 inferred role。
- Source pitch 必须由至少两个不同直接 separator 位置或独立同角色 advance 支持。一个 separator
  只能证明自己所在 adjacency。
- 两个 separator 可以收紧 pitch，但不能用同一对事实自证 absolute phase。短片条中的两点投影
  只是一项 phase hypothesis；只有该区间内的完整合法 fit 还绑定了不属于这两个 separator 的独立
  direct support，才可晋升为 phase authority。长片条中的两点还可能跨过一次 direct local advance，
  只能缩小 pitch 搜索。至少三个独立 material 位置形成周期闭环后，separator lattice 才能自行收紧
  absolute phase；不同解释仍保留为离散 placement。
- 未标 ordinal 的 separator lattice 只枚举 `直接 band 对 × 有限 ordinal distance`，并在循环前
  检查编译上界；超界直接产生 `producer_bound_exceeded`，不截断候选。

模板放置后，`template_alignment_diagnostic` 只读比较 theoretical role 与 bound observation，
报告 normal、一次 local step 或 unresolved；它不搜索、不选择、不改变 placement。

局部异常只复用一个 `LocalAdvanceRelation`：

- 直接、ordinal 唯一的 wide/narrow adjacency 可产生一次 suffix shift；
- 只在该 adjacency 以后累加一次，随后恢复共同 pitch；
- 没有 separator material 且 END/START 顺序相等或反转，属于 contact/overlap 风险；
- 需要两个异常、ordinal 不明或存在多种解释时保持 `local_advance_unresolved`。

单个 material 宽度偏离仍可属于正常扫描变化。只有多个独立、source-wide separator support 的
两侧 residual 无法由同一个模板解释时，才构成全局矛盾；不能把一条局部窄 band 当成第二次位移。

当前没有用户确认的 overlap 黄金。Contact、overlap 和 unresolved 不自动批准，也不启用额外 bleed。

## 8. Cross、outer 与固定 H

Cross 寻找能够确定短轴 offset、fixed H 和局部连续性的直接证据。片夹短轴中心只帮助单侧
anchor 推导 opposite，并验证 enclosing support；它不能选择或否决一对角色正确、固定 H 闭环的
直接 aperture，也不是边界位置或输出 deskew authority。

### 8.1 `APERTURE_PAIR`

Photo aperture 的候选必须有正确 top/bottom 角色、外侧背景、有限位置、局部共同方向和固定 H 闭环。
允许：

- 直接 top + bottom；
- source-wide 单侧 direct anchor + 固定 H 推导 opposite；
- 一个 role-authorized direct binding 在 selected frame domains（数量至少为 3）中逐一有
  direct trace 时，即使 aggregate independent support 只有 2 个区域，也可以作为固定 H 的
  单侧 anchor；这只适用于同一个 binding 的 template-wide domain coverage，不降低普通局部
  two-region edge 的要求；
- 同侧多个相距较远且物理相连的 fragments。

一条短局部线不能外推整条片带。两个不同合法 side tracks 是两个 placements；不按梯度、support
数量或 residual 标量硬选。已有 direct top+bottom 闭环时，不再执行“缺失 opposite”的局部精修；
同一批 raw transitions 的重复拟合不能成为第二个 placement。

Direct top+bottom 的局部方向只验证两侧能否属于同一 fixed-H aperture，并计算逐 trace outward
departure；它不会产生 placement angle。任何 binding 的短轴 offset 投影都必须落在该 binding 的
直接 trace span 内，未覆盖的 frame 不沿 fit direction 外推。`ENCLOSING_SUPPORT_PAIR` 可以保留
自己直接观测的 same-state slope，但这仍不是 placement 或 deskew authority。

Broader same-role track 只有与 local competitor 共享同一个 opposite binding、双方 role-authorized，
且全部 supporting traces 都属于显式 registered trace lattice 时，才可能产生集合支配。存在两种
直接物理证明：若 local 的 registered trace set 是 broader 的严格真子集，且 broader 直接覆盖严格
更多 registered frame domains，则 exact registered-sample containment 已经成立；这条证明不再要求
方向区间相交、allowed-gap 连通或额外的三区域支持。若采样 staggered、local 含有 broader 未命中的
registered trace，则双方必须各自在同一 lattice 上形成单一 connected allowed-gap run，observed/full
direction intervals 直接相交，broader 以至少 3 个独立区域覆盖至少 3 个且严格更多 registered frame
domains，并在长轴上严格包含 local；local 仍须有至少 2 个独立支持区域。Lattice 缺失、trace 未注册、
domain 相等、opposite 不同，或 staggered proof 的 extent 相等/分离、方向不交、任一侧不连通或支持
不足时，runner 必须保留。这不是 fragment 合并、坐标邻近、support/residual 打分或 holder center
选位。

上述 domain-complete anchor 仍必须有完整方向、明确 role authority，并由同一个 direct binding
在每个 selected frame domain 中分别命中 direct trace；selected domain 少于 3 个、缺少一个
domain、把两个不连通 fragments 合计覆盖、role 未授权或方向不完整时，不能拼接或推导 placement，
继续 review。Holder short-axis center
只作兼容事实，不是这一 authority 的必要条件；opposite 仍只由 fixed H 推导，局部 departure
继续进入 selected placement 的 output budget。

### 8.2 `ENCLOSING_SUPPORT_PAIR`

当 aperture 未唯一成立时，可以使用一对直接外侧支撑作为完整输出 top/bottom，但必须同时满足：

- 两侧共享直接 trace 和相容的局部方向；
- 两侧均 source-spanning，或覆盖 3 个独立支持区域和 `min(3, count)` 个长轴 frame domain；
- 直接 span 完整包含 canonical fixed H；
- `H < support_span <= 1.1H`；
- 与片夹短轴中心和 lane authority 相容；
- 只有一个合法 pair。

两侧 `boundary_use` 必须一致，禁止 aperture/support 混用。两侧直接闭环且唯一的 aperture 优先；
若 aperture 只有单侧 direct anchor、另一侧依赖固定 H 推导，或者仍有多个离散 aperture 解，则
唯一且直接证明的 enclosing pair 可以成为更强的输出 authority。Enclosing pair 不声称自己是
照片 aperture，只证明它完整包住可接受的照片区域。

这里的 `support_span` 只由这对直接 observation 的 `observed_span.maximum` 拥有。输出 footprint
是同一 placement 多个联合可行状态的并集，不能把不同状态的 top 与 bottom 组合成新的高度，因而
不能用其包围盒反向计算 enclosing budget。

## 9. Compose、竞争、闭环与 holder fill

`compose_format_placement` 一次把 `TemplateSpec + SequenceFit + CrossFit` 编译为全部 source-axis
固定 frame。之后检查：

- W/H、pitch、cross offset 与 format/source authority 相容；
- ordinal 单调、frame 不交叉；
- first/last、separator、top/bottom 和总跨度闭环；
- 双 lane 的共享尺度与 slot identity 相容。

直接绑定的 sequence start/end 若有稳定直线拟合，`SequenceFit` 只把该 observation 的
reference trace、fit position interval 和 fit direction interval 交给输出安全层。Placement 仍保持
source-axis，不沿该直线移动 phase 或旋转 frame；安全层只计算拟合直线在当前 frame 短轴 support 上
超过既有 full position interval 的向外部分，已经由 full interval 覆盖的 residual 不重复相加。固定 W
推导的 opposite edge 继承同一个直线证据；没有直接方向证据时不创造 slope authority。

选择只使用 typed hard facts 和证据职责，不使用加权总分、confidence 补偿、top-K、投票或
样片/format 特判。同一 template identity、integer offset、local topology 与独立物理 support 下，
相交的 role interval 是一个连续 placement；不同坐标、ordinal、非等价 observation binding、
boundary use 或 required source footprint 是离散竞争。不能明显分胜负就 review。

`PhotoGroupOuter` 只在 selection 后生成。`HolderFillAssessment` 逐侧计算 outer 与 lane authority
之间的空余，并仅用 W 判断：

```text
任一侧空余 >= W  → NOT_FILLED
两侧空余都 < W   → FILLED
区间跨过 W       → UNRESOLVED
```

不加邻接 gap，不重新搜索，不提供 phase。该事实只约束 `135-dual` 的两条完整 lane。

## 10. 联合输出保护、bleed 与预算

安全计算严格晚于唯一 placement：

```text
selected placement
→ PlacementFeasibleSet
→ JointPlacementEnvelope
→ deterministic bleed
→ OutputFootprint
→ authority + direct-use assessment
```

`PlacementFeasibleSet` 保留同一 observation bindings、ordinal topology、boundary use 和 placement
identity 下仍合法的 phase、W、pitch、local delta 与 cross 联合状态；直接 enclosing pair 额外保留
自己的 same-state slope。每个 frame 的边界极值从这个低维联合集合求出，再加入上一节中未被 full
position interval 覆盖的 sequence-line outward departure；不把同一 residual 重复相加，不吸收
runner-up，也不重新读取像素。

产品 bleed：

```text
sequence：max(0.15 mm, 0.7% W)
cross：0.25 mm
```

`APERTURE_PAIR` 四边的完整 expansion（联合不确定性 + 直线 residual + bleed）各自不得超过对应
format 尺寸的 5%。四边不能借额度；刚好达到上限通过。

`ENCLOSING_SUPPORT_PAIR` 的 top/bottom 使用直接 support 边，不再添加 cross bleed，也不使用
aperture 单边 5%；它只接受上节的总 span `<= 1.1H`。Start/end 仍使用正常 sequence bleed 和
单边 5%。

`OutputFootprint` 不得与 source/lane authority 相交后静默缩小。Decision 前只验证联合 source-space
polygon 完整位于 lane authority；任一真正所需区域越界都按 authority side 保存一个 saturation fact
并进入 review。

Content protection 查询的也是同一个最终 `OutputFootprint`，即联合不确定性、局部 residual、完整
pixel-center span 和 bleed 全部加入后的精确 convex polygon。真实画面位于 nominal frame 之外、但仍
在最终 bleed 内，不构成 veto；只有可靠内容越过最终 post-bleed crop 边界才否决。Content 不能回头
移动边界、选择 runner 或创造 phase。

Decision 后 finalization 才执行并评估 lightweight deskew。`needs_review` 不扫描，记录
`output_not_eligible`；approved observation 不可用时使用 identity 且不降级。`auto` 只在观测角绝对值
至少 `0.03°`、长轴端点位移至少 `clamp(0.0005 × long_extent, 3 px, 12 px)`，并且观测角不超过
`0.35°`、端点位移不超过 `120 px` 时应用。低于下限记录 `rotation_not_needed`；高于小整理上限记录
`rotation_exceeds_cleanup_limit`。跳过 deskew 不改变 `approved_auto`。有效旋转对横向 layout 使用观测
角的反号、纵向 layout 使用同号构造 expanded rotation。每个已经确认安全的 polygon 与 source 使用
同一 affine transform，正式轴对齐 box 由旋转后 polygon 的精确半开 AABB 得到，不能先把 polygon
扩成 source AABB，也不能继续裁固定 W×H。

旋转后 AABB 的角落可以位于安全 polygon 之外；这些表示性角落允许写黑色 no-data，不是检测缺口，
不得回流 `CandidateGate`。Sampling 仍必须保证 polygon 内的已确认区域完整、输出 extent 有界、
16-bit/ICC/resolution/metadata 保真。

## 11. Gate、report 与 Debug Analysis

`CandidateGate` 只汇总 typed facts：输入 authority、measurement completeness、producer bounds、
local advance、唯一 placement、content、holder fill、source-space 联合 footprint 和 budget。Phase、
cross continuity/direction 与 ordinal 的真实失败作为 placement 的 typed root failure 传递，不在已有
complete/selected placement 后重复建立同义 Gate fact。它不读取 deskew observation，不选择 geometry，
也不创建最终文案。

`DecisionGate` 独占 `approved_auto`、`needs_review` 和 final reasons。常见根因包括：

- `no_legal_placement`
- `placement_unresolved`
- `content_protection_conflict`
- `local_advance_unresolved`
- `producer_bound_exceeded`
- `direct_use_budget_exceeded`
- `source_lane_authority_unavailable`

普通 report 只保存输入、holder/count authority、最终选择、OutputFootprint、预算、根因、输出文件
和必要 TIFF 事实。Saturation 只记录越界 `authority_side`；每项预算只按 output `geometry_id` 关联，
不保留不可达的多 placement 或 named-gap 容器。Report 只保存最终 `deskew_assessment`：是否应用、
观测角、实际旋转或 typed skip reason，不重复保存旁路 observation。
Holder/count/output-slot identity 只在 `photo_geometry` 保存一次；finalization 复用每个
`OutputFootprint` 内的 sampling authority 和 `deskew_assessment` 内的唯一 source transform，不再建立
逐 slot 同义 tuple。`needs_review` 不暴露 approved sampling geometry 或 final boxes。每个阻止事实
同时给出最小缺失事实、恢复类别和建议操作。完整 observations、alignment residual、winner/runner、
direct/inferred ledger、content veto 和工作量只属于显式 Debug Analysis 或 verifier。外部 report
validator 位于 `tools/regression/`，不进入用户 standalone。

Debug Analysis 只读取同一次 runtime facts，不重算几何、不改变决定、不写正式 TIFF。它必须展示：

- theoretical template 与 role-free observations；
- 每个 bound role 的 residual 和 normal/local-step/unresolved pattern；
- direct 与 inferred 边界；
- best、runner 及真正不同之处；
- `APERTURE_PAIR` 或 `ENCLOSING_SUPPORT_PAIR`；
- selected-only OutputFootprint，以分帧颜色半透明填充最终 required polygon，不另画白色虚线框，
  并显示四边 bleed/联合 expansion/预算；
- `DESKEW APPLIED`、`ROTATION NOT NEEDED` 或 typed `DESKEW SKIPPED`；
- 第一个 blocking Gate gap，或全部事实已支持。

## 12. 工作量、性能与 TIFF

每次 development receipt 保存实际计数和编译上界：

```text
registered queries / pixels
separator lattice hypotheses
phase hypotheses / lookups / bindings / fit passes
local adjacency evaluations
cross runs / fits
placement / boundary / content evaluations
domain pixels / peak temporary bytes
```

任何上界不足都显式产生 `producer_bound_exceeded`，不得 silent first-N。像素工作上限为
`128 × source_pixels`，峰值临时内存上限为 `10 × source_pixels + 32 MiB`。不得恢复通用 DP、
beam、Grid、phase vote、候选笛卡尔积、完整链 materialization/cache、逐帧尺寸、candidate-dependent
query 或 content-driven placement。

性能合同是 24-source 完整用户路径平均不超过 5 秒；同一均值不超过 3 秒是明确记录但不阻断
提交、发布或平台 receipt 的 challenge。正式计时子进程同时由外部观察未插桩 peak RSS；该值与
带 cProfile 的阶段归因 RSS 分开记录。`runtime_peak_temporary_bytes` 只描述 detector 自报的有界
临时测量缓冲，不代表进程 RSS。Profiler 将完整路径拆成：

```text
unattributed runtime → TIFF decode → workspace gray → coarse support
→ registered measurement → template alignment/decision → output deskew
→ sampling → TIFF encode/write → readback → publish
```

Detector 只消费 8-bit gray、稀疏 aggregate profile 与有界局部窗口；正式输出仍从已验证的原始
16-bit RGB 通过每-frame 反向 affine ROI 采样，不先旋转整张大图。普通 product path 在 deskew 和
workspace-owned report facts 冻结后、TIFF sampling 前释放 registered gray；development CLI 同样先
冻结完整 facts 再释放，只有 Debug Analysis 为画图保留。是否继续拆分 decode、优化 detector、
sampling 或 I/O 只由阶段证据决定。

Affine sampler 独占每格 contiguous 输出缓冲，writer 完成一格后才分配下一格，避免相邻大 crop 同时
存活；vertical deskew 使用灰度转置 view，registered interval 使用连续 slice view。Transition-line
cache 只在单个 source 内复用并在 source 结束时清空。这些优化不得改变 observation、placement、
winner/runner、provenance、footprint 或输出像素。

正式输入限于单页 unsigned 16-bit、RGB 三通道、contiguous TIFF；压缩接受 `NONE`、`LZW`、
`DEFLATE` / `ADOBE_DEFLATE` 或 `ZSTD`。Orientation 1–8 在 decode boundary 规范化，输出写
`Orientation=1`。

`tifffile + imagecodecs` 独占正式 TIFF I/O；OpenCV 只作有界测量，SciPy 只作数值拟合与 sampling，
Pillow 只在 Debug Analysis 时延迟导入。生产默认 `--jobs 1`、上限 3，内部数值线程固定为 1。

输出先写同父目录 staging，全部完成后一次 rename 到尚不存在的 target。程序不覆盖、接管、遍历或
删除旧 target。

## 13. 源码 owner

下表中的 `photo_geometry/` 指 `x5crop/detection/photo_geometry/`。

| 路径 | 唯一职责 |
|---|---|
| `x5crop/formats/` | 固定 W/H、容差、gap 搜索先验、holder count 与输出保护常量 |
| `x5crop/configuration/`、`x5crop/runtime/` | format/count/deskew mode 输入、matched-holder resolution 与 source workflow |
| `x5crop/detection/source_core.py`、`evidence/scan_canvas.py` | source/lane 与 matched-holder authority |
| `photo_geometry/coarse_strip_support.py`、`coarse_enclosing_model.py`、`coarse_enclosing_support.py` | 两个 role-free aggregate query、粗片带 interval、source-wide 双侧 track 与 receipt |
| `photo_geometry/template_measurement_plan*.py` | pixel-free 模板、有限 query intents、停止与工作上界 |
| `photo_geometry/registered_*.py`、`observations.py`、`separator_*.py` | 一次性 measurement、role-free edge 与 material band |
| `photo_geometry/source_geometry.py`、`joint_axis_geometry.py` | source 共享 W/H/scale authority |
| `photo_geometry/template_phase*.py`、`template_pitch.py`、`template_residual.py` | phase、ordinal、source pitch 与最多一次 direct local advance |
| `photo_geometry/template_alignment_diagnostic.py` | theoretical-vs-observed residual 的只读诊断 |
| `photo_geometry/interval_math.py`、`template_cross*.py`、`template_cross_support.py` | 共享 interval 运算、fixed-H aperture、局部 top/bottom 方向闭合与 enclosing support |
| `photo_geometry/template_placement.py`、`template_selection.py` | source-axis frame 的一次 compose 与离散 winner/runner |
| `photo_geometry/template_holder_fill.py` | selected PhotoGroupOuter 与 W-only fill assessment |
| `photo_geometry/content_*.py` | 最终 post-bleed polygon 上的二维 negative veto |
| `photo_geometry/template_feasible_geometry.py` | selected placement 的低维联合可行集合 |
| `photo_geometry/template_output.py`、`output_model.py` | JointPlacementEnvelope、bleed、OutputFootprint 与 budget |
| `photo_geometry/template_runtime_model.py`、`template_gate.py`、`detector.py` | current-only handoff、CandidateGate facts 与顶层编排 |
| `x5crop/detection/output_deskew.py` | approved-only 6–24 trace、role-free、candidate-independent 的可选输出角度 observation |
| `x5crop/detection/decision/`、`final/` | 最终决定、Decision 后 deskew assessment 与 approved geometry exposure |
| `x5crop/report/` | compact production report 与 development facts 的生成 |
| `x5crop/debug/` | 只读诊断 facts 与面板 |
| `x5crop/io/`、`export/`、`output/` | TIFF domain、affine sampling、metadata 与原子发布 |
| `tools/verify`、`tools/regression/` | 唯一验证入口、外部 report validator、方向性黄金验收与 accuracy/diagnostic/performance/platform 分层证据 |
| `tools/manual_annotation/` | source-SHA-bound 的本地 proposal、原图坐标人工审核与最内侧可接受裁切基准冻结；不进入 production 或 release |

人工标注器严格对齐 tracked cohort 与本地 manifest，并以 source SHA 聚合任务。一个 source 只有两条
共享短轴边和一个物理 `boundary_pool`；不同显式 count 任务各自保存 typed `slots` 与
`adjacencies`。普通 separator 使用两条边，contact 的前格 END 与后格 START 复用同一物理 boundary，
overlap 保留顺序交叉的两条边；空曝光、残缺曝光、源截断和未知 slot 不得被静默删除。
页面中的 Orientation 只做可逆显示，持久化权威始终是原 TIFF raster pixel-center 坐标。

独立有界像素拟合、用户红线草稿恢复和有界 JPG 都只能生成 proposal。只有用户逐项审核全部 count、
检查 1:1 原生像素并执行最终确认，记录才成为不可变 `user_confirmed` 本地验收基线。它不声称是
真实内容边界的 100% 测量或 detector 唯一正确答案。确认不自动改写
tracked accuracy cohort；完整操作与文件边界见 [MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)。

人工审核中故意排除的漏光痕迹或小角只形成校准标签，不产生 ignore mask、whitelist 或样片阈值。
这些标签只用于检验、改进对所有样片相同的二维 content 定义；若通用证据仍可靠地越过最终 footprint，
Production `content_veto` 让整张 source 进入 `needs_review` 才是安全行为。正片/负片只允许作为
source-level 校准分层，用于检查覆盖面和通用证据在两类片材上的一致性，不是 runtime input、
format/count authority、Gate 分支或 detector 选择器。

## 14. 验证边界

- `x5crop_directional_minimum_acceptable_crop_v1` 是 gold v1、v2 和以后 baseline schema 共用的
  accuracy 合同。用户确认 polygon 表示最内侧可接受的无 bleed 裁切，不表示真实内容边界的 100%
  测量，也不限定 detector 只能产生一个逐像素相同的答案。
- 黄金比较是方向性的：任何已选 candidate 及 `approved_auto` 的正式 post-bleed
  `required_source_footprint` 都必须完整包含确认 polygon，边、角点或亚像素位置不得向其内侧越界；
  几何 epsilon 只吸收浮点计算误差。每侧向外的总 expansion 不得超过对应确认 W/H span 的 5% 加
  命名的 sampling allowance，uncertainty、residual 与 bleed 均消耗该预算。这不是零像素误差或对称
  接近度要求。
- 上述黄金合同不因 `boundary_use` 改变。`enclosing_support_pair` 的总高度不超过 `1.1H` 仍是 runtime
  自动决策合同，但在黄金 accuracy 中还必须满足逐侧 5% 外扩上限，不能用总 span 隐藏单侧过度外扩。
  Nominal 必须安全自动批准，challenge 允许安全 review。只有不存在 selected candidate 的安全 review
  不产生几何 verdict；cosmetic deskew 精度不阻断黄金，affine polygon envelope 与 TIFF 安全合同仍阻断。
- 受跟踪的 diagnostic cohort 只证明不崩溃、工作量有界、报告闭合和 TIFF 工程合同，不证明几何正确。
- 24-source performance 只证明其绑定 commit、依赖和机器上的完整路径时间与资源；5 秒均值是
  blocking Gate，3 秒均值只是 non-blocking challenge。
- Platform 聚合必须同时收到同一 commit 的 Apple Silicon macOS、Intel macOS 与 Windows x64
  三份实机 receipt。APFS/HFS+ 与 NTFS 分别本机验证；没有独立卷时 exFAT 必须保持
  `best_effort_unverified`，不得静默升级为已验证。
- 合成和变形合同覆盖 coarse support 的统一边框、翻转、横竖转置和亮度/对比度，phase 的平移、缩放
  与 fractional pitch，cosmetic deskew 的可用/跳过及横竖旋转符号，轻微直线 residual、缺边、
  wide/narrow 单次 gap、contact
  review、强内部假边、填充状态、dual lane、联合安全预算和 source-wide 事务。
- 全部 release receipt 必须绑定同一最终 commit；否则 V5 不创建 RC、tag、Release 或公开 ZIP。
