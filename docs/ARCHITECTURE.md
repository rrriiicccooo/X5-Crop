# X5 Crop V5 架构

本文是 V5 已确认产品合同、物理模型、运行流、数值合同与源码 owner 的唯一说明。版本级变化见
[CHANGELOG.md](CHANGELOG.md)。V5 尚未发布，公开稳定版仍为 `v4.2.8`。

## 1. 产品与输入 authority

X5 Crop 处理用户已经知道 format、片条模式及必要 count 的 Hasselblad / Imacon X5 片夹扫描。

- format 是硬事实，程序不从像素或文件名猜 format。
- count 包括中间空白曝光格；空白格不能删除、合并或改变 ordinal。
- full 表示用户确认片条采用匹配片夹的完整铺满布局；count 自动使用 `full_count`。
- partial 表示片条没有铺满片夹，必须明确输入 `1 <= count <= full_count`。即使 count 相同，
  partial 的 phase 仍可位于片夹长轴任意位置。
- `135-dual` 只允许 full，总计 12 格，每 lane 6 格，表示两条 lane 都是用户确认的完整铺满布局。
  一个 total partial count 无法表达两条片条的分配，因此不提供该模式。
- 片夹匹配先于 matched-holder count 校验。非交互调用发现非法 count 时，在整批 detector 启动前
  以退出码 `2` 停止；交互入口列出全部冲突并返回 mode/count 步骤。
- Holder identity 或 `full_count` 无法唯一确定时保持 `needs_review`，不猜片夹或 count。
- 任一 slot 不安全时，整个 source `needs_review`，不做 slot salvage。V5 不做 blank suppression。

唯一 count 数据流是：

```text
SlotCountRequest
→ MatchedHolder/full_count
→ ResolvedSlotCount
→ ResolvedOutputSlots
```

`ResolvedSlotCount` 同时保存用户给出的 `HolderLayoutAuthority`。片夹匹配只提供 profile 与
`full_count`，不能替用户判断是否铺满。

核心裁切原则是：format 先给出固定照片矩形；检测依据物理证据放置矩形，再只纳入该胜出位置
自身的测量不确定区间。5%/3% 只验证最终结果，不参与搜索、选位或 padding。

## 2. Format、片夹与尺度

尺寸按片条长轴 × 短轴记录：

| format | 固定照片尺寸 | `G_format` 搜索先验 | `full_count` |
|---|---:|---:|---:|
| `135` | 36 × 24 mm | 2 mm | 6 |
| `135-dual` | 每 lane 36 × 24 mm | 2 mm | 12，6/lane |
| `half` | 18 × 24 mm | 1 mm | 12 |
| `xpan` | 65 × 24 mm | 2 mm | 3 |
| `120-645` | 42 × 56 mm | 无 | 4 |
| `120-66` | 56 × 56 mm | 无 | 3 |
| `120-67` | 70 × 56 mm | 无 | 通常 3，短片夹 2 |

120 族只保留 56 mm 短边，不保留 54 mm component。135、half、XPan 的 gap 数值只确定首次
搜索中心，不能证明当前 source 的正常间隙。120 间隙受相机或后背型号影响，不建立联网值或
项目样片先验。

片夹画布只提供宽松尺度：

```text
nominal_px_per_mm = 匹配片夹扫描范围像素尺寸 / 片夹物理尺寸
W_nominal_px      = nominal_px_per_mm × format 长轴尺寸
H_nominal_px      = nominal_px_per_mm × format 短轴尺寸
```

相机片门尺寸偏差与扫描比例偏差对本项目等价，不尝试区分。数值合同为：

```text
W 兼容范围：format 名义宽度 ±1.25%
H 兼容范围：format 名义高度 ±0.40%
片夹 extent：物理名义范围 ±3.5%
```

X5 长图基本没有可用齿孔；源码、测试与 Gate 都不得依赖齿孔。

## 3. 共享物理几何

### 3.1 `SourceScanGeometry`

同一 source 共享：

- px/mm 扫描比例与 W/H 可行窄范围；
- source 主方向族；
- affine 坐标基准。

不建立 `W_effective_px`、`H_effective_px` 或逐张尺寸。完整 opposite-edge span 只能验证和收紧
共享范围；多组兼容 span 取交集，冲突保持 unresolved，不能平均或分配给不同照片。

### 3.2 `LaneGeometry`

每个 lane 独立拥有：

- 连续中心线；
- 围绕 source 主方向族的小角度偏差；
- sequence phase lattice 与当前 source pitch；
- 局部异常与可见 authority。

双 lane 共享尺度和大致方向族，但不共享中心线、phase、gap 或异常，也不强迫数学上完全平行。
所有照片都是同一 W/H 的矩形：不允许逐张尺寸、逐张旋转或四角自由迎合内容；允许卷曲、片夹
压力与扫描形变造成小而连续的中心线和边缘偏离。Start/end 与 top/bottom 属于近似正交的共同
方向族。水平与垂直扫描只交换规范坐标轴，不能形成两套 detector。Deskew 使用 lane 共同方向，
只需视觉上平直，不追逐照片内部线条。

## 4. Authority 与证据语义

每个物理边界只有三种状态：

- `support`：直接像素观察与候选角色相容；
- `contradiction`：可靠事实否决候选；
- `unobservable`：遮挡、截断、空白、叠片或内容使边界不可观察。

没有检测到边缘不等于边缘不存在；强烈内容线、灰尘、片夹线也不自动成为照片边界。Expected
position 只限定首次搜索走廊和顺序，不能创建 phase 或边界。Partial 可位于画布长轴任意位置；
full 只有在完整正常布局事实成立时才取得条件式居中权限。第一张或最后一张被遮挡时，物理框
可以延伸到 authority 外；项目只保护 TIFF 中可恢复的部分。

Source/lane authority 来自 raster、片夹布局和 lane 几何，不能从“没有内容”推导。

## 5. 唯一 observation 层

Registered measurement 一次生成候选无关、数量有界的观察。

### 5.1 `BoundaryEdgeObservation`

记录单条局部边缘的 source 坐标区间、方向与不确定区间、空间支持区域、极性及原始 observation
ID。单 edge 在模板角色绑定前没有 start/end、ordinal 或 contact authority。

### 5.2 `SeparatorBandObservation`

只有方向、空间支持和极性相容的相邻 edge 才能组成 band：

```text
band[i] = [L[i], R[i]]
L[i]    = end[i]
R[i]    = start[i+1]
g[i]    = R[i] - L[i]
```

Band 保留左右边、gap 区间、黑度、纹理与跨短轴连续性。一条 band 是一份直接像素观察；左右边
不能算两票，但绑定后可同时约束两个 slot。

### 5.3 Top/bottom edge family

只在共享 H 决定的窄走廊中寻找局部连续段。Top 与 bottom 分别聚合，再用共享 H、方向和连续
中心线配对。两个空间分离的长轴区域是最低重复证据；一条长连续线最多按有限的前、中、后区域
提供支持。Count=1 也可在同一照片的不同长轴区域取得重复支持。只在单张照片局部出现的横线
不能改变 source/lane 级边缘族。

项目无需区分照片边缘、胶片边缘和片夹可见边缘；只要候选外没有可恢复照片内容，它们对裁切
等价。已知 top 可由共享 H 推导 bottom，反之亦然；推导边必须标记 `inferred`，不能冒充第二份
直接观察。最终选择能够放置固定 H、未被内容否决的最小安全 pair。

### 5.4 `ContentOccupancyObservation`

内容层保存真正的二维占用单元或连通区域，不把某个长轴位置的内容扩展成贯穿 lane 的 bbox。
内容只作负向否决：可靠连续内容被候选裁断，或可靠内容穿过预计的正常正 separator core，才可
否决候选。

以下情况保持中性：没有检测到内容、黑片或低纹理、start/end 外侧的邻片内容、接触或叠片中的
跨边内容、片夹遮挡外不存在像素。黑色区域不能证明大间隙；连续黑区仍须按 count、W 和固定模板
保留所有空白 slot。

角落局部擦边同样中性。Top/bottom 的否决内容必须离开 start/end 角落并在照片长轴内部跨过完整
边界不确定区间；start/end 亦须在照片短轴内部成立。二维结构还必须在边界内外各保持一个内容
测量单元的连续深度。项目保护具有可靠二维延续的有效内容，不把角点、边缘锯齿、尘点或极小
局部擦边升级成 veto。

不保留 basic/enhanced 平行 detector。唯一 measurement owner 可对已登记缺口执行一次有界局部
refinement，但结果仍进入同一 observation ledger。

## 6. Detector 是有界模板编译器

Detector 不从像素重新发明照片，而把用户与片夹 authority 编译成一份有限测量计划：

```text
format + full/partial/count + holder/source authority
→ TemplateMeasurementPlan
→ 一次性注册 sequence / separator / cross / content queries
→ role-free observations
→ SequenceFit + CrossFit
→ FormatPlacement
```

`TemplateMeasurementPlan` 在读取观察结果前就冻结 `TemplateSpec`、物理单位、query intents、phase / role /
cross / placement / pixel / work bounds、正常快车道停止条件和 precision budget。计划 identity 只依赖物理
输入，不依赖当前像素发现了什么。所有候选可能使用的 query 必须在选择前登记；禁止 winner-specific
requery、逐候选重读像素或在全图无限寻找更多边。

正常片条只求少数未知量：phase、source pitch/scale、共同 direction、cross center，以及至多两个由直接
separator 证明的 local gap delta。任何新增模块都必须说明自己估计哪个未知量；内容占用和 Gate 不估计
几何，只否决危险结果。

## 7. Sequence lattice、source pitch 与局部偏差

Sequence 在方向规范化长轴 `q` 上使用固定格点：

```text
role_position = cycle_phase
              + (integer_slot_offset + slot_index) × source_pitch
              + local_prefix[slot]
              + (W if role is END else 0)
```

`cycle_phase` 与离散 `integer_slot_offset` 分开保存。连续小误差进入 interval；不同整数 offset 是两个
不同 placement，必须保留 winner/runner，不能平均。Full 只把片夹中心作为 compatibility；partial 即使
`count == full_count` 也不消费中心权限。

`G_format` 只给第一次局部搜索窗口。至少两个不同 adjacency 的相容同角色 advance 才能把当前
`source_pitch` 从搜索先验升级为 source 证据；一个 separator 的左右 edge 仍只算一个物理位置。直接
角色缺失时，固定 W 与已支持 lattice 可以推导该角色，并在 ledger 标记 `inferred`。直接角色的位置区间
不会被全局残差改写；推导角色才传播 phase、pitch 与 local-prefix 不确定性。已经绑定的同角色直接
观察若跨越多个 slot，可以收窄该 placement 的连续 pitch 不确定区间，但不能升级 source pitch
authority、改变 role 绑定或消除离散 runner。

模板放置后的残差只允许解释为：整体平移、稳定 pitch 漂移、一次或两次直接定位的 local step、孤立
outlier，或无法解释。Local step 必须由已经绑定到同一 adjacency 的 separator 直接证明；每个 delta
只在对应位置以后累加一次。没有直接 ordinal、出现超过模型上限的异常或多种解释时保持
`local_advance_unresolved`，不枚举异常可能落在哪一格。

## 8. Cross、固定 H 与共同方向

Top/bottom observation 只有在 role-specific 外侧背景、方向与空间支持满足合同后才能授权对应角色。
固定 H 是 format authority：直接 top+bottom pair 可验证或收紧位置；source-wide 的单侧直接 edge 可按
固定 H 推导另一侧。局部 fragment 只能验证，不能外推整条 source。

两个局部 pair 只有共享同一直接 observation identity，或具有显式相连的独立物理支持，才能归为一个
连续 group。坐标接近、残差更小、trace 更多或 interval 碰巧重叠都不能把离散答案合并。Source-spanning
方向区间拥有最终 safety；局部共同拟合只在与其相交时确定 canonical direction。双 lane 只共享相容的
source W/H/scale 与方向，不共享 phase、cross center 或 local anomaly。

## 9. Compose、竞争、闭环与工作量

`compose_format_placement` 一次把 `TemplateSpec + SequenceFit + CrossFit + SharedStripDirection` 编译为
固定 W/H、共同方向、ordinal 单调的全部 `TemplateFrame`。照片尺寸不随每条测量边抖动；gap 只改变
位置。Compose 后执行廉价闭环：总跨度、holder/lane authority、W/H、pitch/gap、top/bottom 距离、
方向正交性、slot 顺序和双 lane 共享事实必须彼此相容。

每 lane 只保留最佳 placement 与一个真正不同的 runner。选择使用 typed hard facts 与证据职责，不使用
加权总分、top-K、Pareto 票数补偿或 format/样片专属 margin。相同答案的小 interval 属于一个 placement；
不同坐标、offset、sampling footprint 或安全窗口属于离散竞争。不能明显区分就
`placement_unresolved`。二维内容只在 phase 与 cross 已唯一解析后，对已经 compose 的 placement 做
negative veto；未解析候选上的 content fact 不能取得 Gate 权限，也不能移动边界、重排 winner、平分
照片或创造替代 placement。

每次运行在 development receipt 中保存并由外部 verifier 检查：

```text
measurement/pixel queries
phase hypotheses / role lookups / role bindings / fit passes
local adjacency evaluations
cross registered runs / evaluated fits
placement / boundary / content evaluations
domain pixels / peak temporary bytes
```

Phase 最多执行 5 个具名有界阶段，每阶段每个 hypothesis 只查一次 role，每阶段 local adjacency 检查
不超过 `count-1`；每 lane placement evaluation 不超过 2。像素查询不超过 `128 × source_pixels`，峰值
临时内存不超过 `10 × source_pixels + 32 MiB`。任何编译或运行上界不足都显式产生
`producer_bound_exceeded`，不得 silent first-N。

不得恢复通用 DP、beam、Grid、phase vote、候选笛卡尔积、完整链 materialization/cache、逐帧尺寸、
separator-center 裁切、content bbox placement、candidate-dependent query 或无界全图 evidence。

## 10. 固定框、最小安全裁切与 sampling

每个 slot 先得到固定尺寸 `R_format`。正常间隙、接触、叠片或大间隙只改变位置，不改变尺寸。

```text
SafeCropEnvelope
  = selected R_format
  + selected placement 自身的测量不确定区间
  ∩ source/lane 可见 authority
```

Start/top 取同一胜出位置的最小安全值，end/bottom 取最大安全值。这个范围只计算一次，不再添加
fixed guard、minimum padding 或 bleed。落选位置不能进入 envelope；非嵌套 placement 不能取
union、平均或拼接。内容只能否决位置，不能拖动 format 框包围 content bbox。

Authority 截断不算切内容，也不消耗 5%/3%；被片夹遮挡或未扫描部分不恢复、不 padding。连续
坐标向整数像素的外向取整属于坐标正确性，不是保护层。

Affine sampling kernel 的像素支持由 sampling 层单独验证，不扩大 envelope、不改变 placement、
不参与 budget。旋转后 output AABB 的背景角只属于矩形 raster 表示；budget 使用 source-space
物理 footprint。

Direct-use budget 逐边使用闭区间上限：

```text
start/end 每边 ≤ 5% W
top/bottom 每边 ≤ 3% H
```

刚好达到上限通过，四边不能借额度；叠片共享 pixels 不算扩张。

## 11. Gate、输出与可审计事实

`CandidateGate` 只记录 holder/count、measurement plan completeness、source/lane geometry、phase/cross
fit、producer coverage、独立证据、异常 authority、内容保护、selected placement、
selected-only envelope、source/lane authority、5%/3%、deskew、transform 与 sampling typed
assessments。它不重新选择位置，也不机械要求四条边都被直接观察。

`DecisionGate` 独占 `approved_auto`、`needs_review` 与固定 final reasons：

- `no_legal_placement`；
- `placement_unresolved`；
- `content_protection_conflict`；
- `local_advance_unresolved`；
- `producer_bound_exceeded`；
- `direct_use_budget_exceeded`；
- `source_lane_authority_unavailable`；
- `transform_sampling_unavailable`。

一个可靠 phase anchor、supported source pitch、完整正常模板、无同级竞争者且输出安全时可以自动批准。任一 slot
不安全时，整个 source `needs_review`，普通运行不写该 source 的正式照片。

普通 report 只保存输入与配置、holder/count authority、最终选择、每个 slot 的安全框、逐边 budget、
Gate 根因、输出文件和必要 TIFF 事实。Observations、fit winner/runner、偏差 ledger、content veto 与
producer work 只在显式 Debug Analysis 或验证工具中生成。旧 report 不参与 runtime；每次运行都从
原 TIFF 重新检测，不提供跨运行复用、旧 revision reader 或迁移器。

Debug Analysis 消费同一次 runtime 的 development facts，不重算几何、不改变检测、不写正式 TIFF。
Phase 求解器必须以 typed `winner_basis` 记录真正使第一名胜出的物理事实；展示层只读取该事实，
不得重新执行排名或概括成分数。分轴图必须把 role-free observation、最佳 placement 与 runner
分开绘制，写明 runner 差异、winner 所依赖的 phase/cross/content/shared-source 事实，以及第一个
blocking DecisionGate 或全部 Gate 已支持。
最终输出面板只读取 selected-only `SafeCropEnvelope`；review candidate 不得填充为正式输出。显示层坐标
归一化不能改变 source-coordinate placement、crop、budget 或 deskew。

## 12. TIFF、运行与输出发布

正式输入限于单页 unsigned 16-bit、RGB 三通道、contiguous planar TIFF；压缩接受 `NONE`、
`LZW`、`DEFLATE` / `ADOBE_DEFLATE` 或 `ZSTD`。Orientation 1–8 在 decode boundary 转为
canonical coordinates，正式输出写 `Orientation=1`。

`tifffile + imagecodecs` 独占正式 TIFF I/O；OpenCV 只作有界像素测量，SciPy 只作数值与
sampling，Pillow 只在 Debug Analysis 时延迟导入。普通写出关闭后只复开 header，检查可读性、
shape、dtype、channels、ICC、resolution、受支持 metadata、压缩与 `Orientation=1`；完整像素复读
属于 TIFF contract、named-TIFF、platform、端到端与发布验证。

检测灰度图按有界行块从原始 RGB 生成，与整数组计算逐像素一致，不建立整张 float RGB 副本。
Detector 只消费这份廉价灰度与已登记窗口；正式输出仍从原始 16-bit RGB 采样。

生产默认 `--jobs 1`、上限 3；数值库内部线程固定为 1。一次运行先在 target 同父目录写完整 staging，
全部成功后用一次 rename 发布为新的 target。Target 已存在或处理中出现同名目录时直接报错；runtime
不覆盖、接管、遍历或删除旧目录，不建立 lock、journal、ownership inventory、虚拟磁盘预留或文件
系统侦察。实际 I/O 失败直接报告，未完成 staging 不公开。

退出码为：`0` 完整发布且无 runtime error，`1` 已发布但含 runtime error或全部输入失败而未发布，
`2` CLI/input/preflight 错误，`3` fresh-directory 发布失败。全部 source 都是 `runtime_error` 时不发布
空结果。

数值按职责分为三类：format/片夹尺寸及 1.25%/0.40%/3.5%、5%/3% 是物理或产品合同；像素中心、
Scharr kernel 归一化、MAD consistency factor 是采样/统计恒等量；窗口毫米数、z 门槛、Huber loss
scale、内容 cell 与结构张量门槛是具名测量校准。校准值只能存在于对应 spec，必须带单位和合成/
黄金边界测试，不得散落成 placement、投票或 Gate 的隐藏阈值。

## 13. 源码 owner

下表中的 `photo_geometry/` 均指 `x5crop/detection/photo_geometry/`。

| 路径 | 唯一职责 |
|---|---|
| `x5crop/formats/` | 固定照片尺寸、容差、gap 搜索先验与 holder full count |
| `x5crop/configuration/` | 用户 count、片夹与 runtime configuration |
| `x5crop/io/`、`x5crop/export/` | TIFF domain、Orientation、metadata、sampling 与 write/readback |
| `x5crop/detection/source_core.py` | source/lane 可见 authority |
| `x5crop/detection/evidence/` | 候选无关的 OpenCV/SciPy 二维内容测量 |
| `photo_geometry/model.py`、`measurement_model.py`、`observation_types.py` | 物理测量与 role-free observation 的不可变类型 |
| `photo_geometry/registered_measurement.py`、`robust_line_fit.py` | 一次性 registered 像素测量与 SciPy Huber 数值拟合 |
| `photo_geometry/observations.py`、`transition_tracking.py`、`template_evidence.py` | edge/band identity、独立支持与证据职责 |
| `photo_geometry/source_geometry.py`、`joint_axis_geometry.py` | source 共享 W/H/scale authority |
| `photo_geometry/template_measurement_plan.py`、`template_measurement_plan_model.py` | pixel-free 模板编译，以及 query intents、停止条件与工作上界的 canonical records |
| `photo_geometry/template_model.py`、`template_registration.py` | `TemplateSpec`、phase lattice、role registration 与 canonical ledger |
| `photo_geometry/template_phase.py`、`template_phase_candidates.py`、`template_phase_model.py`、`template_pitch.py`、`template_residual.py` | phase 编排、有限 role binding、fit records、source pitch 与有据 local step |
| `photo_geometry/template_cross.py`、`template_cross_candidates.py`、`template_cross_model.py`、`template_direction.py` | fixed-H cross 编排、物理 role group、fit records 与 source 共同方向 |
| `photo_geometry/template_placement.py`、`template_selection.py` | 一次 compose 的固定 frame placement 与 winner/runner 竞争 |
| `photo_geometry/content_*.py` | placement 后的二维内容 negative veto |
| `photo_geometry/template_precision.py`、`template_output.py`、`output_model.py` | selected-only uncertainty、SafeCrop、budget 与 sampling assessment |
| `photo_geometry/template_runtime_model.py`、`template_gate.py`、`detector.py` | current-only hand-off records、CandidateGate facts 与唯一顶层编排 |
| `x5crop/detection/candidate/`、`decision/`、`final/` | typed facts、最终决定与 approved geometry exposure |
| `x5crop/report/` | compact production report、development facts 与外部 read model |
| `x5crop/runtime/`、`x5crop/output/` | invocation、source workflow、terminal outcome 与全新目录发布 |
| `x5crop/debug/` | 只读 Debug facts、分轴面板与绘图 |
| `tools/verify` | 唯一 tracked verifier 入口 |
| `tools/regression/` | SHA-bound accuracy、diagnostic、performance 与 platform 验证 |
| `tools/install/`、`tools/release/` | standalone 依赖与发布 manifest |
| `tools/tests/` | 按物理、运行、I/O 与工具职责拆分的 focused contracts |
